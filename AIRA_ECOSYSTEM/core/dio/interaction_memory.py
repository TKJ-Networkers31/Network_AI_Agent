import json
import sqlite3
import threading
import time
import logging
from pathlib import Path
from contextlib import closing
from typing import Any, Optional

from core.dio.constants import DEFAULT_INTERACTION_MEMORY_TTL_SECONDS

logger = logging.getLogger("aira.dio.interaction_memory")

BASE_DIR = Path(__file__).resolve().parents[2]  # AIRA_ECOSYSTEM/
DEFAULT_DB_FILE = BASE_DIR / "database" / "interaction_memory.db"


class InteractionMemory:

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
                CREATE TABLE IF NOT EXISTS interaction_context (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    expires_at REAL
                )
            """)
            conn.commit()

    def save(self, key: str, value: Any, ttl_seconds: Optional[float] = None) -> dict:
        if not key:
            return {"success": False, "error": "key tidak boleh kosong."}

        now = time.time()
        ttl = DEFAULT_INTERACTION_MEMORY_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        expires_at = (now + ttl) if ttl and ttl > 0 else None

        serialized = json.dumps(value, ensure_ascii=False, default=str)

        with self._lock:
            with closing(self._connect()) as conn:
                conn.execute("""
                    INSERT INTO interaction_context (key, value, updated_at, expires_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at,
                        expires_at = excluded.expires_at
                """, (key, serialized, now, expires_at))
                conn.commit()

        logger.debug("INTERACTION MEMORY SAVE | key=%s ttl=%s", key, ttl)
        return {"success": True, "key": key}

    def load(self, key: str) -> Any:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT value, expires_at FROM interaction_context WHERE key = ?", (key,)
            ).fetchone()

        if not row:
            return None

        if row["expires_at"] is not None and row["expires_at"] < time.time():
            self._delete(key)
            return None

        try:
            return json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            return None

    def update(self, key: str, partial: dict, ttl_seconds: Optional[float] = None) -> dict:
        current = self.load(key)
        merged = {**current, **partial} if isinstance(current, dict) else dict(partial)
        return self.save(key, merged, ttl_seconds=ttl_seconds)

    def clear(self, key: Optional[str] = None) -> dict:
        with self._lock:
            with closing(self._connect()) as conn:
                if key is None:
                    cursor = conn.execute("DELETE FROM interaction_context")
                else:
                    cursor = conn.execute("DELETE FROM interaction_context WHERE key = ?", (key,))
                conn.commit()
                deleted = cursor.rowcount

        logger.debug("INTERACTION MEMORY CLEAR | key=%s deleted=%d", key or "*", deleted)
        return {"success": True, "deleted": deleted}

    def _delete(self, key: str) -> None:
        with self._lock:
            with closing(self._connect()) as conn:
                conn.execute("DELETE FROM interaction_context WHERE key = ?", (key,))
                conn.commit()

    def purge_expired(self) -> int:
        now = time.time()

        with self._lock:
            with closing(self._connect()) as conn:
                cursor = conn.execute(
                    "DELETE FROM interaction_context WHERE expires_at IS NOT NULL AND expires_at < ?",
                    (now,),
                )
                conn.commit()
                return cursor.rowcount


_singleton: Optional[InteractionMemory] = None
_singleton_lock = threading.Lock()


def get_interaction_memory() -> InteractionMemory:
    global _singleton

    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = InteractionMemory()

    return _singleton