"""
core/job_store.py — Durable Background Task Execution & Persistent State Store for VERA.

Provides a robust, SQLite-backed persistent state machine for long-running network operations,
diagnostics, analysis runs, and chat turns. Ensures zero state loss across browser reloads,
WS disconnects, or worker restarts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import json
import logging
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional
import uuid

logger = logging.getLogger("vera.job_store")

BASE_DIR = Path(__file__).resolve().parents[1]  # VERA_ECOSYSTEM/
DATABASE_DIR = BASE_DIR / "database"
DATABASE_DIR.mkdir(exist_ok=True)
DB_PATH = DATABASE_DIR / "jobs.db"


class JobState(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    WAITING_FOR_INPUT = "WAITING_FOR_INPUT"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    RETRY_PENDING = "RETRY_PENDING"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"


ACTIVE_STATES = {
    JobState.QUEUED.value,
    JobState.RUNNING.value,
    JobState.PAUSED.value,
    JobState.WAITING_FOR_INPUT.value,
    JobState.WAITING_FOR_APPROVAL.value,
    JobState.RETRY_PENDING.value,
}


@dataclass
class DurableJob:
    job_id: str
    job_type: str
    title: str
    state: str = JobState.QUEUED.value
    progress: float = 0.0
    stage: str = "initialized"
    session_id: Optional[str] = None
    run_id: Optional[str] = None
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    checkpoint_data: Dict[str, Any] = field(default_factory=dict)
    result_data: Dict[str, Any] = field(default_factory=dict)
    error_data: Dict[str, Any] = field(default_factory=dict)
    idempotency_key: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    def is_active(self) -> bool:
        return self.state in ACTIVE_STATES

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "job_type": self.job_type,
            "title": self.title,
            "state": self.state,
            "progress": self.progress,
            "stage": self.stage,
            "checkpoint_data": self.checkpoint_data,
            "result_data": self.result_data,
            "error_data": self.error_data,
            "idempotency_key": self.idempotency_key,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "is_active": self.is_active(),
        }


@dataclass
class JobEvent:
    id: int
    job_id: str
    event_type: str
    event_data: Dict[str, Any]
    session_id: Optional[str] = None
    run_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "event_type": self.event_type,
            "event_data": self.event_data,
            "created_at": self.created_at,
        }


class JobStore:
    """Thread-safe SQLite store for durable background tasks and session jobs."""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS durable_jobs (
                    job_id TEXT PRIMARY KEY,
                    session_id TEXT,
                    run_id TEXT,
                    tenant_id TEXT,
                    user_id TEXT,
                    job_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    state TEXT NOT NULL,
                    progress REAL DEFAULT 0.0,
                    stage TEXT,
                    checkpoint_json TEXT,
                    result_json TEXT,
                    error_json TEXT,
                    idempotency_key TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    completed_at REAL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_session ON durable_jobs(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_state ON durable_jobs(state)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_user ON durable_jobs(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_run ON durable_jobs(run_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_idempotency ON durable_jobs(idempotency_key)")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS job_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    session_id TEXT,
                    run_id TEXT,
                    event_type TEXT NOT NULL,
                    event_data TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_job ON job_events(job_id, id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_session ON job_events(session_id, id)")
            conn.commit()

    def _row_to_job(self, row: sqlite3.Row) -> DurableJob:
        return DurableJob(
            job_id=row["job_id"],
            session_id=row["session_id"],
            run_id=row["run_id"],
            tenant_id=row["tenant_id"],
            user_id=row["user_id"],
            job_type=row["job_type"],
            title=row["title"],
            state=row["state"],
            progress=row["progress"],
            stage=row["stage"] or "",
            checkpoint_data=json.loads(row["checkpoint_json"] or "{}"),
            result_data=json.loads(row["result_json"] or "{}"),
            error_data=json.loads(row["error_json"] or "{}"),
            idempotency_key=row["idempotency_key"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
        )

    def create_job(
        self,
        job_type: str,
        title: str,
        session_id: Optional[str] = None,
        run_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        checkpoint_data: Optional[Dict[str, Any]] = None,
        stage: str = "initialized",
    ) -> DurableJob:
        now = time.time()
        job_id = f"job_{uuid.uuid4().hex[:14]}"

        with self._lock, self._connect() as conn:
            if idempotency_key:
                row = conn.execute(
                    "SELECT * FROM durable_jobs WHERE idempotency_key = ?", (idempotency_key,)
                ).fetchone()
                if row:
                    return self._row_to_job(row)

            conn.execute(
                """
                INSERT INTO durable_jobs (
                    job_id, session_id, run_id, tenant_id, user_id,
                    job_type, title, state, progress, stage,
                    checkpoint_json, result_json, error_json, idempotency_key,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    session_id,
                    run_id,
                    tenant_id,
                    user_id,
                    job_type,
                    title,
                    JobState.RUNNING.value,
                    0.0,
                    stage,
                    json.dumps(checkpoint_data or {}),
                    "{}",
                    "{}",
                    idempotency_key,
                    now,
                    now,
                ),
            )
            conn.commit()

        return self.get_job(job_id)  # type: ignore

    def update_job_progress(
        self,
        job_id: str,
        progress: float,
        stage: Optional[str] = None,
        checkpoint_data: Optional[Dict[str, Any]] = None,
        state: Optional[str] = None,
    ) -> Optional[DurableJob]:
        now = time.time()
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM durable_jobs WHERE job_id = ?", (job_id,)).fetchone()
            if not row:
                return None

            current_ckpt = json.loads(row["checkpoint_json"] or "{}")
            if checkpoint_data:
                current_ckpt.update(checkpoint_data)

            new_stage = stage if stage is not None else row["stage"]
            new_state = state if state is not None else row["state"]

            conn.execute(
                """
                UPDATE durable_jobs
                SET progress = ?, stage = ?, state = ?, checkpoint_json = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (progress, new_stage, new_state, json.dumps(current_ckpt), now, job_id),
            )
            conn.commit()

        return self.get_job(job_id)

    def complete_job(
        self,
        job_id: str,
        result_data: Optional[Dict[str, Any]] = None,
        state: str = JobState.SUCCEEDED.value,
        stage: str = "completed",
    ) -> Optional[DurableJob]:
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE durable_jobs
                SET state = ?, progress = 100.0, stage = ?, result_json = ?, completed_at = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (state, stage, json.dumps(result_data or {}), now, now, job_id),
            )
            conn.commit()

        return self.get_job(job_id)

    def fail_job(
        self,
        job_id: str,
        error_message: str,
        error_details: Optional[Dict[str, Any]] = None,
    ) -> Optional[DurableJob]:
        now = time.time()
        err_dict = {"message": error_message, "details": error_details or {}}
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE durable_jobs
                SET state = ?, stage = 'failed', error_json = ?, completed_at = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (JobState.FAILED.value, json.dumps(err_dict), now, now, job_id),
            )
            conn.commit()

        return self.get_job(job_id)

    def cancel_job(self, job_id: str, reason: str = "Cancelled by user") -> Optional[DurableJob]:
        now = time.time()
        err_dict = {"reason": reason}
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE durable_jobs
                SET state = ?, stage = 'cancelled', error_json = ?, completed_at = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (JobState.CANCELLED.value, json.dumps(err_dict), now, now, job_id),
            )
            conn.commit()

        return self.get_job(job_id)

    def pause_job(
        self,
        job_id: str,
        checkpoint_data: Optional[Dict[str, Any]] = None,
        reason: str = "Paused by user",
    ) -> Optional[DurableJob]:
        now = time.time()
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM durable_jobs WHERE job_id = ?", (job_id,)).fetchone()
            if not row:
                return None

            current_ckpt = json.loads(row["checkpoint_json"] or "{}")
            if checkpoint_data:
                current_ckpt.update(checkpoint_data)
            current_ckpt["pause_reason"] = reason
            current_ckpt["paused_at"] = now

            conn.execute(
                """
                UPDATE durable_jobs
                SET state = ?, stage = 'paused', checkpoint_json = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (JobState.PAUSED.value, json.dumps(current_ckpt), now, job_id),
            )
            conn.commit()

        return self.get_job(job_id)

    def resume_job(
        self,
        job_id: str,
        additional_instructions: Optional[str] = None,
    ) -> Optional[DurableJob]:
        now = time.time()
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM durable_jobs WHERE job_id = ?", (job_id,)).fetchone()
            if not row:
                return None

            current_ckpt = json.loads(row["checkpoint_json"] or "{}")
            if additional_instructions:
                current_ckpt["additional_instructions"] = additional_instructions
            current_ckpt["resumed_at"] = now

            conn.execute(
                """
                UPDATE durable_jobs
                SET state = ?, stage = 'running', checkpoint_json = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (JobState.RUNNING.value, json.dumps(current_ckpt), now, job_id),
            )
            conn.commit()

        return self.get_job(job_id)

    def get_job(self, job_id: str) -> Optional[DurableJob]:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM durable_jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row:
                return self._row_to_job(row)
        return None

    def get_active_job_for_session(self, session_id: str) -> Optional[DurableJob]:
        placeholders = ",".join("?" for _ in ACTIVE_STATES)
        with self._lock, self._connect() as conn:
            query = f"""
                SELECT * FROM durable_jobs
                WHERE session_id = ? AND state IN ({placeholders})
                ORDER BY updated_at DESC LIMIT 1
            """
            row = conn.execute(query, [session_id, *ACTIVE_STATES]).fetchone()
            if row:
                return self._row_to_job(row)
        return None

    def get_active_job_by_run_id(self, run_id: str) -> Optional[DurableJob]:
        placeholders = ",".join("?" for _ in ACTIVE_STATES)
        with self._lock, self._connect() as conn:
            query = f"""
                SELECT * FROM durable_jobs
                WHERE run_id = ? AND state IN ({placeholders})
                ORDER BY updated_at DESC LIMIT 1
            """
            row = conn.execute(query, [run_id, *ACTIVE_STATES]).fetchone()
            if row:
                return self._row_to_job(row)
        return None

    def record_event(
        self,
        job_id: str,
        event_type: str,
        event_data: Dict[str, Any],
        session_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> JobEvent:
        now = time.time()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO job_events (job_id, session_id, run_id, event_type, event_data, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, session_id, run_id, event_type, json.dumps(event_data), now),
            )
            event_id = cursor.lastrowid
            conn.commit()

        return JobEvent(
            id=event_id,
            job_id=job_id,
            session_id=session_id,
            run_id=run_id,
            event_type=event_type,
            event_data=event_data,
            created_at=now,
        )

    def get_events_for_job(
        self, job_id: str, since_id: int = 0, limit: int = 100
    ) -> List[JobEvent]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM job_events
                WHERE job_id = ? AND id > ?
                ORDER BY id ASC LIMIT ?
                """,
                (job_id, since_id, limit),
            ).fetchall()

            return [
                JobEvent(
                    id=row["id"],
                    job_id=row["job_id"],
                    session_id=row["session_id"],
                    run_id=row["run_id"],
                    event_type=row["event_type"],
                    event_data=json.loads(row["event_data"] or "{}"),
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    def list_jobs(
        self,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        state: Optional[str] = None,
        limit: int = 50,
    ) -> List[DurableJob]:
        clauses = []
        params = []
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if user_id:
            clauses.append("user_id = ?")
            params.append(user_id)
        if state:
            clauses.append("state = ?")
            params.append(state)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM durable_jobs {where} ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        with self._lock, self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_job(r) for r in rows]

    def recover_interrupted_jobs(self) -> int:
        """Marks any RUNNING jobs as INTERRUPTED on system boot."""
        now = time.time()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE durable_jobs
                SET state = ?, stage = 'interrupted_system_restart', completed_at = ?, updated_at = ?
                WHERE state = ?
                """,
                (JobState.INTERRUPTED.value, now, now, JobState.RUNNING.value),
            )
            count = cursor.rowcount
            conn.commit()
            if count > 0:
                logger.warning("JOB_STORE | Marked %d interrupted running jobs from previous process.", count)
            return count


_JOB_STORE_INSTANCE: Optional[JobStore] = None


def get_job_store() -> JobStore:
    global _JOB_STORE_INSTANCE
    if _JOB_STORE_INSTANCE is None:
        _JOB_STORE_INSTANCE = JobStore()
    return _JOB_STORE_INSTANCE
