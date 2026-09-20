"""
core/semantic_memory/store.py — penyimpanan SQLite Semantic Memory (Sprint 2.4).

Pemilik TUNGGAL database/semantic_memory.db (satu .db, satu pemilik modul,
sesuai docs/database.md). Tidak menyentuh long_term_memory.db, chat_sessions.db,
interaction_memory.db, atau database lain.

MemoryStore hanya menyimpan & mengambil MemoryRecord apa adanya. Ia TIDAK
menghitung embedding (itu tugas SemanticMemory di retriever.py) dan TIDAK
menghitung similarity (itu tugas scorer/retriever).

Membuat folder/file database hanya saat MemoryStore() dibuat - mengimpor modul
ini tidak menyentuh disk.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Optional

from core.semantic_memory.defaults import DEFAULT_DB_FILE
from core.semantic_memory.models import MemoryCategory, MemoryRecord

logger = logging.getLogger("aira.semantic_memory.store")

TABLE = "semantic_memory"

_COLUMNS = (
    "id, session_id, text, category, created_at, updated_at, "
    "embedding, metadata, importance"
)


def _require_session(session_id: Any) -> str:
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("session_id tidak boleh kosong.")

    return session_id.strip()


def _check_limit(limit: Any) -> Optional[int]:
    if limit is None:
        return None

    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValueError("limit harus bilangan bulat >= 0.")

    return limit


def _load_json(raw: Any, fallback: Any) -> Any:
    if raw is None:
        return fallback

    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return fallback


class MemoryStore:

    def __init__(
        self,
        db_path: Optional[Path] = None,
        clock: Optional[Callable[[], float]] = None,
    ):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_FILE
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._clock = clock or time.time
        self._lock = threading.RLock()

        self._init_db()

    # ------------------------------------------------------------------ infra

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    category TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    embedding TEXT NOT NULL DEFAULT '[]',
                    metadata TEXT NOT NULL DEFAULT '{{}}',
                    importance REAL NOT NULL DEFAULT 0.5
                )
            """)
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_session ON {TABLE}(session_id)")
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_category ON {TABLE}(category)")
            conn.commit()

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> Optional[MemoryRecord]:
        """Baris rusak dilewati (None), tidak pernah melempar ke pemanggil."""
        embedding = _load_json(row["embedding"], [])
        metadata = _load_json(row["metadata"], {})

        if not isinstance(metadata, dict):
            metadata = {}

        fields = {
            "id": row["id"],
            "session_id": row["session_id"],
            "text": row["text"],
            "category": row["category"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "metadata": metadata,
            "importance": row["importance"],
        }

        try:
            return MemoryRecord(embedding=embedding, **fields)
        except ValueError:
            pass

        try:
            # embedding rusak saja -> tetap kembalikan record (tanpa vektor).
            return MemoryRecord(embedding=[], **fields)
        except ValueError:
            logger.warning("Baris semantic_memory rusak dilewati (id=%s).", row["id"])
            return None

    def _fetch(self, sql: str, params: list[Any]) -> list[MemoryRecord]:
        with closing(self._connect()) as conn:
            rows = conn.execute(sql, params).fetchall()

        records = (self._row_to_record(row) for row in rows)

        return [record for record in records if record is not None]

    # ------------------------------------------------------------------ write

    def add(self, record: MemoryRecord) -> MemoryRecord:
        """Simpan record baru. id yang sudah ada -> ValueError."""
        if not isinstance(record, MemoryRecord):
            raise TypeError("record harus berupa MemoryRecord.")

        with self._lock, closing(self._connect()) as conn:
            try:
                conn.execute(
                    f"INSERT INTO {TABLE} ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        record.id, record.session_id, record.text, record.category.value,
                        record.created_at, record.updated_at,
                        json.dumps(record.embedding),
                        json.dumps(record.metadata, ensure_ascii=False, default=str),
                        record.importance,
                    ),
                )
            except sqlite3.IntegrityError:
                raise ValueError(f"Record dengan id '{record.id}' sudah ada.") from None

            conn.commit()

        return record

    def update(
        self,
        record_id: str,
        *,
        text: Optional[str] = None,
        category: Any = None,
        importance: Optional[float] = None,
        metadata: Optional[dict] = None,
        embedding: Optional[list] = None,
    ) -> Optional[MemoryRecord]:
        """
        Ubah field record. None = tidak diubah (metadata={} berarti dikosongkan;
        metadata DIGANTI, bukan digabung). updated_at diperbarui, created_at
        dan session_id tetap. Return record terbaru, atau None kalau id tidak ada.

        Store tidak meng-embed ulang: kalau `text` berubah, pemanggil bertanggung
        jawab memberi `embedding` baru (SemanticMemory.update melakukannya).
        """
        with self._lock:
            current = self.get(record_id)

            if current is None:
                return None

            changes: dict[str, Any] = {}

            if text is not None:
                changes["text"] = text
            if category is not None:
                changes["category"] = category
            if importance is not None:
                changes["importance"] = importance
            if metadata is not None:
                changes["metadata"] = metadata
            if embedding is not None:
                changes["embedding"] = embedding

            if not changes:
                return current

            updated = replace(current, updated_at=self._clock(), **changes)  # divalidasi ulang

            with closing(self._connect()) as conn:
                conn.execute(
                    f"UPDATE {TABLE} SET text = ?, category = ?, updated_at = ?, "
                    f"embedding = ?, metadata = ?, importance = ? WHERE id = ?",
                    (
                        updated.text, updated.category.value, updated.updated_at,
                        json.dumps(updated.embedding),
                        json.dumps(updated.metadata, ensure_ascii=False, default=str),
                        updated.importance, updated.id,
                    ),
                )
                conn.commit()

            return updated

    def delete(self, record_id: str) -> bool:
        with self._lock, closing(self._connect()) as conn:
            cursor = conn.execute(f"DELETE FROM {TABLE} WHERE id = ?", (record_id,))
            conn.commit()
            return cursor.rowcount > 0

    def clear(self, session_id: Optional[str] = None) -> int:
        """Hapus semua record (atau hanya milik satu sesi). Return jumlah terhapus."""
        with self._lock, closing(self._connect()) as conn:
            if session_id is None:
                cursor = conn.execute(f"DELETE FROM {TABLE}")
            else:
                cursor = conn.execute(
                    f"DELETE FROM {TABLE} WHERE session_id = ?", (_require_session(session_id),),
                )

            conn.commit()
            return cursor.rowcount

    # ------------------------------------------------------------------- read

    def get(self, record_id: str) -> Optional[MemoryRecord]:
        records = self._fetch(f"SELECT {_COLUMNS} FROM {TABLE} WHERE id = ?", [record_id])

        return records[0] if records else None

    def list(
        self,
        session_id: str,
        *,
        category: Any = None,
        limit: Optional[int] = None,
    ) -> "list[MemoryRecord]":
        """Record milik SATU sesi (isolasi sesi), terbaru dulu. Filter kategori opsional."""
        sql = f"SELECT {_COLUMNS} FROM {TABLE} WHERE session_id = ?"
        params: list[Any] = [_require_session(session_id)]

        if category is not None:
            sql += " AND category = ?"
            params.append(MemoryCategory.coerce(category).value)

        sql += " ORDER BY created_at DESC, id ASC"

        limit = _check_limit(limit)
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        return self._fetch(sql, params)

    def search_by_category(
        self,
        category: Any,
        session_id: Optional[str] = None,
        *,
        limit: Optional[int] = None,
    ) -> "list[MemoryRecord]":
        """
        Record satu kategori. session_id=None -> lintas semua sesi (alat
        administrasi); retrieval SELALU memakai list(session_id, ...) untuk
        menjaga isolasi sesi.
        """
        sql = f"SELECT {_COLUMNS} FROM {TABLE} WHERE category = ?"
        params: list[Any] = [MemoryCategory.coerce(category).value]

        if session_id is not None:
            sql += " AND session_id = ?"
            params.append(_require_session(session_id))

        sql += " ORDER BY created_at DESC, id ASC"

        limit = _check_limit(limit)
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        return self._fetch(sql, params)

    def count(self, session_id: Optional[str] = None) -> int:
        with closing(self._connect()) as conn:
            if session_id is None:
                row = conn.execute(f"SELECT COUNT(*) AS c FROM {TABLE}").fetchone()
            else:
                row = conn.execute(
                    f"SELECT COUNT(*) AS c FROM {TABLE} WHERE session_id = ?",
                    (_require_session(session_id),),
                ).fetchone()

        return int(row["c"])
