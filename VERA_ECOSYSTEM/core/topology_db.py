"""
core/topology_db.py — Unified SQLite Concurrency & Access Policy for AIRA OS.

Provides a centralized database policy for topology.db:
- Idempotent WAL mode and synchronous configuration.
- Consistent 30.0s busy timeout across all connections.
- Foreign key enforcement and Row factory.
- Path-scoped reentrant single-writer coordination with queue and wait time metrics.
- Atomic transaction context managers (write=True/False) with rollback safety.
- Bounded retry policy for transient SQLITE_BUSY / SQLITE_LOCKED contention.
- Structured diagnostics without exposing secrets.
"""

from __future__ import annotations

import logging
import os
import random
import sqlite3
import asyncio
import threading
import uuid
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Generator, Optional, TypeVar

logger = logging.getLogger("aira.topology.db")

T = TypeVar("T")

# Resolved absolute database path
BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_DIR = BASE_DIR / "database"
DEFAULT_TOPOLOGY_DB_PATH = (DATABASE_DIR / "topology.db").resolve()

# Concurrency & contention policy constants
DEFAULT_TIMEOUT_SEC = 30.0
DEFAULT_BUSY_TIMEOUT_MS = 30000
MAX_WRITE_RETRIES = 4
BASE_RETRY_DELAY_SEC = 0.05
MAX_RETRY_DELAY_SEC = 1.0
LONG_TRANSACTION_WARN_SEC = 2.0


def is_transient_sqlite_lock_error(exc: BaseException) -> bool:
    """
    Identifies whether an exception is a transient SQLite lock contention error
    (SQLITE_BUSY, SQLITE_LOCKED, database is locked, database is busy).
    Never treats syntax, schema, constraint, or integrity errors as transient.
    """
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    msg = str(exc).lower()
    # Explicit exclusions of permanent operational errors
    non_lock_phrases = (
        "syntax error",
        "no such table",
        "no such column",
        "already exists",
        "cannot rollback",
        "disk i/o error",
        "interrupted",
        "foreign key",
    )
    if any(phrase in msg for phrase in non_lock_phrases):
        return False

    return any(phrase in msg for phrase in (
        "database is locked",
        "database is busy",
        "busy",
        "locked",
        "resource deadlock",
    ))


class TopologyWriteCoordinator:
    """
    Write coordinator scoped to a specific database path.
    Ensures write operations are serialized to prevent uncontrolled SQLite lock contention,
    while supporting reentrancy within the same thread to prevent self-deadlocks.
    Exposes observability metrics: queue depth, lock wait duration, active writes.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or str(DEFAULT_TOPOLOGY_DB_PATH)
        self._lock = threading.RLock()
        self._waiting_writers = 0
        self._active_writers = 0
        self._stats_lock = threading.Lock()
        self._total_write_tx = 0
        self._total_busy_errors = 0
        self._total_wait_ms = 0.0

    @property
    def queue_depth(self) -> int:
        with self._stats_lock:
            return self._waiting_writers

    @property
    def active_writers(self) -> int:
        with self._stats_lock:
            return self._active_writers

    def get_stats(self) -> Dict[str, Any]:
        with self._stats_lock:
            return {
                "db_path": self.db_path,
                "queue_depth": self._waiting_writers,
                "active_writers": self._active_writers,
                "total_write_transactions": self._total_write_tx,
                "total_busy_errors": self._total_busy_errors,
                "total_wait_ms": round(self._total_wait_ms, 2),
            }

    @contextmanager
    def acquire_writer(self, timeout: float = DEFAULT_TIMEOUT_SEC) -> Generator[float, None, None]:
        """
        Acquires the single-writer lock with timeout and wait time tracking.
        Yields the wait duration in milliseconds.
        """
        t0 = time.perf_counter()
        with self._stats_lock:
            self._waiting_writers += 1

        acquired = self._lock.acquire(timeout=timeout)
        wait_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        with self._stats_lock:
            self._waiting_writers = max(0, self._waiting_writers - 1)
            self._total_wait_ms += wait_ms
            if acquired:
                self._active_writers += 1
                self._total_write_tx += 1

        if not acquired:
            with self._stats_lock:
                self._total_busy_errors += 1
            raise sqlite3.OperationalError(
                f"Topology write coordinator timeout after {timeout:.1f}s for {self.db_path} (queue_depth={self.queue_depth})"
            )

        try:
            yield wait_ms
        finally:
            with self._stats_lock:
                self._active_writers = max(0, self._active_writers - 1)
            self._lock.release()


_COORDINATORS: Dict[str, TopologyWriteCoordinator] = {}
_COORDINATOR_LOCK = threading.Lock()


def get_write_coordinator(db_path: Optional[Path | str] = None) -> TopologyWriteCoordinator:
    """Returns the write coordinator for the given database path."""
    resolved = str((Path(db_path) if db_path else DEFAULT_TOPOLOGY_DB_PATH).resolve())
    with _COORDINATOR_LOCK:
        if resolved not in _COORDINATORS:
            _COORDINATORS[resolved] = TopologyWriteCoordinator(resolved)
        return _COORDINATORS[resolved]


def init_topology_database(db_path: Optional[Path | str] = None) -> Path:
    """
    Idempotently initializes topology.db access policy:
    - Ensures parent directory exists.
    - Enables Write-Ahead Logging (WAL) mode.
    - Sets synchronous = NORMAL for optimal durability and concurrent performance.
    - Sets busy_timeout = 30000ms.
    - Enables foreign keys.
    - Verifies journal mode.
    """
    resolved_path = (Path(db_path) if db_path else DEFAULT_TOPOLOGY_DB_PATH).resolve()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    with get_write_coordinator(resolved_path).acquire_writer(timeout=DEFAULT_TIMEOUT_SEC):
        conn = sqlite3.connect(str(resolved_path), timeout=DEFAULT_TIMEOUT_SEC)
        try:
            conn.execute(f"PRAGMA busy_timeout = {DEFAULT_BUSY_TIMEOUT_MS}")
            conn.execute("PRAGMA foreign_keys = ON")

            # Check existing journal mode before updating
            current_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            if str(current_mode).lower() != "wal":
                new_mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
                logger.info("Initialized topology.db journal_mode from %s to %s for %s", current_mode, new_mode, resolved_path.name)
            conn.execute("PRAGMA synchronous = NORMAL")
        finally:
            conn.close()

    return resolved_path


def get_topology_connection(
    db_path: Optional[Path | str] = None,
    read_only: bool = False,
    timeout: float = DEFAULT_TIMEOUT_SEC,
) -> sqlite3.Connection:
    """
    Creates a standardized SQLite connection to topology.db following the unified policy.
    - Correct resolved absolute path.
    - Configured timeout and busy_timeout (30.0s / 30000ms).
    - sqlite3.Row row_factory.
    - foreign_keys = ON.
    - query_only = ON if read_only=True.
    """
    resolved_path = (Path(db_path) if db_path else DEFAULT_TOPOLOGY_DB_PATH).resolve()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(resolved_path), timeout=timeout)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {DEFAULT_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")

    if read_only:
        try:
            conn.execute("PRAGMA query_only = ON")
        except sqlite3.OperationalError:
            pass

    return conn



_thread_local = threading.local()

def _get_thread_tx_stack(resolved_path: str) -> List[Tuple[sqlite3.Connection, Optional[str]]]:
    if not hasattr(_thread_local, "active_tx"):
        _thread_local.active_tx = {}
    return _thread_local.active_tx.setdefault(resolved_path, [])

@contextmanager
def topology_transaction(
    db_path: Optional[Path | str] = None,
    write: bool = True,
    timeout: float = DEFAULT_TIMEOUT_SEC,
    existing_conn: Optional[sqlite3.Connection] = None,
) -> Generator[sqlite3.Connection, None, None]:
    """
    Unified transaction context manager for topology.db supporting:
    - Primary write transactions with BEGIN IMMEDIATE and coordinator lock.
    - Nested write transactions on the same thread using SAVEPOINT semantics (Policy A & B).
    - Detection and rejection of conflicting independent connections on the same thread (Policy C).
    - Clean rollback to SAVEPOINT on nested failure; outer rollback on outer failure.
    - Concurrent read-only transactions with query_only=ON.
    - Max wait and execution deadline tracking.
    """
    resolved_path = str((Path(db_path) if db_path else DEFAULT_TOPOLOGY_DB_PATH).resolve())
    stack = _get_thread_tx_stack(resolved_path)

    # 1. Existing connection provided explicitly
    if existing_conn is not None:
        if len(stack) > 0 and stack[0][0] is not existing_conn and write:
            # Policy C: Rejection of independent connections on the same thread
            raise sqlite3.OperationalError(
                f"Conflicting independent connection provided on thread {threading.get_ident()} "
                f"while an active write transaction is already in progress for {resolved_path}."
            )
        yield existing_conn
        return

    # 2. Write transaction
    if write:
        if len(stack) > 0:
            # Policy A & B: Nested transaction on same thread -> reuse connection with SAVEPOINT
            parent_conn = stack[-1][0]
            sp_name = f"sp_{len(stack)}_{uuid.uuid4().hex[:8]}"
            parent_conn.execute(f"SAVEPOINT {sp_name}")
            stack.append((parent_conn, sp_name))
            try:
                yield parent_conn
                parent_conn.execute(f"RELEASE SAVEPOINT {sp_name}")
            except Exception:
                try:
                    parent_conn.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")
                except Exception as rb_err:
                    logger.warning("Error rolling back savepoint %s: %s", sp_name, rb_err)
                raise
            finally:
                if stack and stack[-1][1] == sp_name:
                    stack.pop()
            return

        # Outermost write transaction on this thread
        with get_write_coordinator(resolved_path).acquire_writer(timeout=timeout) as wait_ms:
            t_start = time.perf_counter()
            conn = get_topology_connection(resolved_path, read_only=False, timeout=timeout)
            try:
                conn.execute("BEGIN IMMEDIATE")
                stack.append((conn, None))
                yield conn
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception as rollback_err:
                    logger.warning("Rollback error during transaction failure: %s", rollback_err)
                raise
            finally:
                if stack:
                    stack.pop()
                conn.close()
                dur_sec = time.perf_counter() - t_start
                if dur_sec > LONG_TRANSACTION_WARN_SEC:
                    logger.warning(
                        "Long topology write transaction detected: %.3fs (lock_wait=%.2fms, path=%s)",
                        dur_sec, wait_ms, Path(resolved_path).name,
                    )
    else:
        # Read-only transaction
        if len(stack) > 0:
            # Re-use active connection if we already have one open on this thread
            yield stack[-1][0]
            return

        conn = get_topology_connection(resolved_path, read_only=True, timeout=timeout)
        try:
            yield conn
        finally:
            conn.close()


def execute_with_retry(
    operation: Callable[[], T],
    max_retries: int = MAX_WRITE_RETRIES,
    base_delay: float = BASE_RETRY_DELAY_SEC,
    max_delay: float = MAX_RETRY_DELAY_SEC,
    total_deadline_sec: float = 30.0,
    idempotent: bool = True,
    cancel_check: Optional[Callable[[], bool]] = None,
    operation_name: str = "topology_operation",
) -> T:
    """
    Executes a database operation with bounded exponential backoff, jitter, and total deadline
    ONLY for positively identified transient SQLite contention errors (SQLITE_BUSY, SQLITE_LOCKED).
    Enforces:
    - Bounded total waiting time across all attempts (total_deadline_sec).
    - Cancellation checks via cancel_check callable.
    - Idempotency guard: non-idempotent operations fail immediately on contention.
    - Zero retry on syntax, constraint, or schema errors.
    """
    last_exc: Optional[Exception] = None
    delay = base_delay
    t_start = time.monotonic()
    t_deadline = t_start + total_deadline_sec

    for attempt in range(1, max_retries + 1):
        if cancel_check is not None and cancel_check():
            raise asyncio.CancelledError(f"Operation {operation_name} cancelled before attempt {attempt}")

        remaining_time = t_deadline - time.monotonic()
        if remaining_time <= 0:
            raise sqlite3.OperationalError(
                f"Retry total deadline exceeded ({total_deadline_sec:.1f}s) for {operation_name} on attempt {attempt}"
            )

        try:
            return operation()
        except sqlite3.OperationalError as exc:
            if not is_transient_sqlite_lock_error(exc):
                # Permanent SQL error — raise immediately without retry
                raise

            if not idempotent:
                logger.warning(
                    "Operation %s encountered SQLite contention but is marked non-idempotent; aborting retry: %s",
                    operation_name, exc,
                )
                raise

            last_exc = exc
            if attempt == max_retries:
                logger.error(
                    "Exhausted %d retries for %s due to SQLite lock contention: %s",
                    max_retries, operation_name, exc,
                )
                raise

            remaining_time = t_deadline - time.monotonic()
            if remaining_time <= 0:
                logger.error(
                    "Retry total deadline (%.1fs) exceeded after %d attempts for %s: %s",
                    total_deadline_sec, attempt, operation_name, exc,
                )
                raise sqlite3.OperationalError(
                    f"Retry deadline exceeded ({total_deadline_sec:.1f}s) for {operation_name}: {exc}"
                )

            jitter = random.uniform(0.5, 1.5) * delay
            actual_delay = min(max_delay, jitter, max(0.001, remaining_time))
            logger.warning(
                "SQLite contention on %s (attempt %d/%d, elapsed=%.2fs): %s. Backing off for %.3fs",
                operation_name, attempt, max_retries, time.monotonic() - t_start, exc, actual_delay,
            )
            time.sleep(actual_delay)
            delay = min(max_delay, delay * 2)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"Unexpected retry failure for {operation_name}")
