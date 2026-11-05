"""
AIRA OS — Edge Gateway Bounded Local Telemetry Buffer (Networking VIII / WP 8.4.5).

Provides:
- Durable SQLite local queue for edge telemetry (`edge_buffer.db`)
- Bounded capacity (default max 5,000 samples / < 5 MB disk usage)
- FIFO drop policy on capacity breach with dropped-sample accounting
- Monotonic sequence numbering and chronological batch draining
- Safe restart survivability and replay recovery
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import logging
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, Generator, List, Optional
import uuid

logger = logging.getLogger("aira.edge_gateway.buffer")

DEFAULT_MAX_BUFFER_CAPACITY = 5000

BUFFER_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS edge_telemetry_buffer (
    sample_id TEXT PRIMARY KEY,
    sequence_number INTEGER NOT NULL UNIQUE,
    telemetry_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at_epoch REAL NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS edge_buffer_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_buf_seq ON edge_telemetry_buffer(sequence_number ASC);
"""


class EdgeBufferQueue:
    """Bounded, crash-resilient local telemetry buffer on the customer edge gateway."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        max_capacity: int = DEFAULT_MAX_BUFFER_CAPACITY,
    ) -> None:
        self.db_path = Path(db_path or "edge_buffer.db").resolve()
        self.max_capacity = max(1, max_capacity)
        self._init_db()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            conn.executescript(BUFFER_SCHEMA_SQL)
            # Initialize metadata if missing
            conn.execute(
                "INSERT OR IGNORE INTO edge_buffer_meta (key, value) VALUES ('last_sequence', '0')"
            )
            conn.execute(
                "INSERT OR IGNORE INTO edge_buffer_meta (key, value) VALUES ('dropped_total', '0')"
            )

    def enqueue(self, telemetry_type: str, payload: Dict[str, Any]) -> int:
        """
        Enqueues a telemetry payload.
        If queue is at maximum capacity, drops oldest sample (FIFO) and records dropped count.
        Returns the assigned monotonic sequence number.
        """
        now = time.time()
        sample_id = f"smp_{uuid.uuid4().hex[:12]}"
        payload_str = json.dumps(payload)

        with self._get_connection() as conn:
            # Increment monotonic sequence counter
            row = conn.execute("SELECT value FROM edge_buffer_meta WHERE key = 'last_sequence'").fetchone()
            current_seq = int(row["value"]) + 1
            conn.execute("UPDATE edge_buffer_meta SET value = ? WHERE key = 'last_sequence'", (str(current_seq),))

            # Check capacity
            count_row = conn.execute("SELECT COUNT(*) as cnt FROM edge_telemetry_buffer").fetchone()
            current_depth = count_row["cnt"] if count_row else 0

            while current_depth >= self.max_capacity:
                # Capacity breach: Drop oldest sample
                oldest = conn.execute(
                    "SELECT sample_id FROM edge_telemetry_buffer ORDER BY sequence_number ASC LIMIT 1"
                ).fetchone()
                if oldest:
                    conn.execute("DELETE FROM edge_telemetry_buffer WHERE sample_id = ?", (oldest["sample_id"],))
                    # Increment dropped total
                    conn.execute("UPDATE edge_buffer_meta SET value = CAST(value AS INTEGER) + 1 WHERE key = 'dropped_total'")
                    logger.warning("Edge buffer capacity reached (%d). Dropped sample %s", self.max_capacity, oldest["sample_id"])
                    current_depth -= 1
                else:
                    break

            # Insert sample
            conn.execute(
                """
                INSERT INTO edge_telemetry_buffer 
                (sample_id, sequence_number, telemetry_type, payload_json, created_at_epoch, retry_count)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (sample_id, current_seq, telemetry_type, payload_str, now),
            )

        return current_seq

    def peek_batch(self, batch_size: int = 100) -> List[Dict[str, Any]]:
        """Retrieves up to batch_size oldest samples in chronological order without deleting them."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT sample_id, sequence_number, telemetry_type, payload_json, created_at_epoch, retry_count
                FROM edge_telemetry_buffer
                ORDER BY sequence_number ASC
                LIMIT ?
                """,
                (max(1, batch_size),),
            ).fetchall()

            batch: List[Dict[str, Any]] = []
            for r in rows:
                batch.append({
                    "envelope_id": r["sample_id"],
                    "sequence_number": r["sequence_number"],
                    "telemetry_type": r["telemetry_type"],
                    "payload": json.loads(r["payload_json"]),
                    "source_timestamp": r["created_at_epoch"],
                    "retry_count": r["retry_count"],
                })
            return batch

    def acknowledge_batch(self, sample_ids: List[str]) -> int:
        """Deletes acknowledged samples from local queue after Central NOC confirmation."""
        if not sample_ids:
            return 0
        with self._get_connection() as conn:
            placeholders = ",".join("?" for _ in sample_ids)
            cur = conn.execute(
                f"DELETE FROM edge_telemetry_buffer WHERE sample_id IN ({placeholders})",
                sample_ids,
            )
            return cur.rowcount

    def increment_retries(self, sample_ids: List[str]) -> None:
        """Increments retry count for unacknowledged samples."""
        if not sample_ids:
            return
        with self._get_connection() as conn:
            placeholders = ",".join("?" for _ in sample_ids)
            conn.execute(
                f"UPDATE edge_telemetry_buffer SET retry_count = retry_count + 1 WHERE sample_id IN ({placeholders})",
                sample_ids,
            )

    def get_health(self) -> Dict[str, Any]:
        """Returns buffer diagnostics and queue depth."""
        now = time.time()
        with self._get_connection() as conn:
            count_row = conn.execute("SELECT COUNT(*) as cnt FROM edge_telemetry_buffer").fetchone()
            depth = count_row["cnt"] if count_row else 0

            oldest_row = conn.execute(
                "SELECT created_at_epoch FROM edge_telemetry_buffer ORDER BY sequence_number ASC LIMIT 1"
            ).fetchone()
            oldest_age = (now - oldest_row["created_at_epoch"]) if oldest_row else 0.0

            dropped_row = conn.execute("SELECT value FROM edge_buffer_meta WHERE key = 'dropped_total'").fetchone()
            dropped = int(dropped_row["value"]) if dropped_row else 0

            last_seq_row = conn.execute("SELECT value FROM edge_buffer_meta WHERE key = 'last_sequence'").fetchone()
            last_seq = int(last_seq_row["value"]) if last_seq_row else 0

            return {
                "queue_depth": depth,
                "max_capacity": self.max_capacity,
                "oldest_sample_age_sec": round(oldest_age, 2),
                "dropped_samples_total": dropped,
                "last_sequence_number": last_seq,
                "is_full": depth >= self.max_capacity,
            }

    def clear(self) -> None:
        """Empties buffer queue (used in testing or maintenance)."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM edge_telemetry_buffer")
            conn.execute("UPDATE edge_buffer_meta SET value = '0' WHERE key = 'last_sequence'")
            conn.execute("UPDATE edge_buffer_meta SET value = '0' WHERE key = 'dropped_total'")
