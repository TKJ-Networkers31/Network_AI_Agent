"""
core/selection/store.py — pemilik database/selection_context.db (Sprint 2.7 / W4).

Selection bersifat sekali-pakai/berumur pendek (TTL default 1 jam) - mirip
pola core/dio/interaction_memory.py, tapi kolom terstruktur (bukan key/value
generik) supaya query per session_id/message_id mudah dan JSON-safe.
"""

import json
import sqlite3
import threading
import time
import logging
from pathlib import Path
from contextlib import closing
from typing import Optional

from core.selection.constants import DEFAULT_SELECTION_TTL_SECONDS
from core.selection.models import SelectionContext

logger = logging.getLogger("aira.selection")

BASE_DIR = Path(__file__).resolve().parents[2]  # AIRA_ECOSYSTEM/
DEFAULT_DB_FILE = BASE_DIR / "database" / "selection_context.db"


class SelectionStore:

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_FILE
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS selection_context (
                    selection_id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    message_id TEXT,
                    conversation_id TEXT,
                    session_id TEXT,
                    selected_text TEXT NOT NULL,
                    surrounding_text TEXT NOT NULL DEFAULT '',
                    start_offset INTEGER,
                    end_offset INTEGER,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    expires_at REAL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_selection_session ON selection_context(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_selection_message ON selection_context(message_id)")
            conn.commit()

    def save(self, selection: SelectionContext, ttl_seconds: Optional[float] = DEFAULT_SELECTION_TTL_SECONDS) -> None:
        expires_at = (selection.created_at + ttl_seconds) if ttl_seconds and ttl_seconds > 0 else None

        with self._lock, closing(self._connect()) as conn:
            conn.execute("""
                INSERT INTO selection_context
                    (selection_id, source_type, message_id, conversation_id, session_id,
                     selected_text, surrounding_text, start_offset, end_offset,
                     metadata, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(selection_id) DO UPDATE SET
                    selected_text = excluded.selected_text,
                    surrounding_text = excluded.surrounding_text,
                    metadata = excluded.metadata,
                    expires_at = excluded.expires_at
            """, (
                selection.selection_id, selection.source_type, selection.message_id,
                selection.conversation_id, selection.session_id,
                selection.selected_text, selection.surrounding_text,
                selection.start_offset, selection.end_offset,
                json.dumps(selection.metadata, ensure_ascii=False, default=str),
                selection.created_at, expires_at,
            ))
            conn.commit()

        logger.debug("SELECTION SAVE | id=%s session=%s", selection.selection_id, selection.session_id)

    def get(self, selection_id: str) -> Optional[SelectionContext]:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM selection_context WHERE selection_id = ?", (selection_id,)
            ).fetchone()

        if not row:
            return None

        if row["expires_at"] is not None and row["expires_at"] < time.time():
            self.delete(selection_id)
            return None

        return self._row_to_selection(row)

    def delete(self, selection_id: str) -> bool:
        with self._lock, closing(self._connect()) as conn:
            cursor = conn.execute("DELETE FROM selection_context WHERE selection_id = ?", (selection_id,))
            conn.commit()
            return cursor.rowcount > 0

    def purge_expired(self) -> int:
        now = time.time()
        with self._lock, closing(self._connect()) as conn:
            cursor = conn.execute(
                "DELETE FROM selection_context WHERE expires_at IS NOT NULL AND expires_at < ?", (now,)
            )
            conn.commit()
            return cursor.rowcount

    @staticmethod
    def _row_to_selection(row: sqlite3.Row) -> SelectionContext:
        try:
            metadata = json.loads(row["metadata"])
        except (json.JSONDecodeError, TypeError):
            metadata = {}

        return SelectionContext(
            selection_id=row["selection_id"],
            source_type=row["source_type"],
            message_id=row["message_id"],
            conversation_id=row["conversation_id"],
            session_id=row["session_id"],
            selected_text=row["selected_text"],
            surrounding_text=row["surrounding_text"],
            start_offset=row["start_offset"],
            end_offset=row["end_offset"],
            metadata=metadata,
            created_at=row["created_at"],
        )


_store_singleton: Optional[SelectionStore] = None
_store_lock = threading.Lock()


def get_selection_store() -> SelectionStore:
    global _store_singleton
    if _store_singleton is None:
        with _store_lock:
            if _store_singleton is None:
                _store_singleton = SelectionStore()
    return _store_singleton