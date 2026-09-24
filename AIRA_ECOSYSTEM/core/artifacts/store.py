"""
core/artifacts/store.py - SQLite persistence for Artifact metadata
(Sprint 2.7 / W5).

Owns database/artifacts.db exclusively ("satu .db, satu pemilik modul" -
docs/database.md), same shape as core/model_store.py / core/persona/engine.py.
This table stores METADATA ONLY (id, name, type, size, storage_reference,
status, ...) - the actual bytes live in the AIRA Workspace via
core.filesystem, never inside this database.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from typing import Optional

from core.artifacts.models import Artifact

BASE_DIR = Path(__file__).resolve().parents[2]  # AIRA_ECOSYSTEM/
DEFAULT_DB_FILE = BASE_DIR / "database" / "artifacts.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    name TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size INTEGER NOT NULL DEFAULT 0,
    storage_reference TEXT,
    source TEXT NOT NULL DEFAULT 'generated',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_artifacts_session ON artifacts(session_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_type ON artifacts(artifact_type);
"""


class ArtifactStore:

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
        with self._lock, closing(self._connect()) as conn:
            conn.executescript(SCHEMA_SQL)
            conn.commit()

    def save(self, artifact: Artifact) -> Artifact:
        """Insert or update (id is the natural key - re-saving the same id
        overwrites; used e.g. when a FAILED artifact is retried in place)."""
        with self._lock, closing(self._connect()) as conn:
            conn.execute("""
                INSERT INTO artifacts
                    (id, session_id, name, artifact_type, mime_type, size,
                     storage_reference, source, status, created_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    session_id = excluded.session_id,
                    name = excluded.name,
                    artifact_type = excluded.artifact_type,
                    mime_type = excluded.mime_type,
                    size = excluded.size,
                    storage_reference = excluded.storage_reference,
                    source = excluded.source,
                    status = excluded.status,
                    metadata = excluded.metadata
            """, (
                artifact.id, artifact.session_id, artifact.name, artifact.artifact_type,
                artifact.mime_type, artifact.size, artifact.storage_reference,
                artifact.source, artifact.status, artifact.created_at,
                json.dumps(artifact.metadata, ensure_ascii=False, default=str),
            ))
            conn.commit()

        return artifact

    def get(self, artifact_id: str) -> Optional[Artifact]:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()

        return self._row_to_artifact(row) if row else None

    def list(self, session_id: Optional[str] = None, artifact_type: Optional[str] = None) -> list[Artifact]:
        conditions, params = [], []

        if session_id is not None:
            conditions.append("session_id = ?")
            params.append(session_id)
        if artifact_type is not None:
            conditions.append("artifact_type = ?")
            params.append(artifact_type)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT * FROM artifacts {where} ORDER BY created_at DESC", params,
            ).fetchall()

        return [self._row_to_artifact(r) for r in rows]

    def delete(self, artifact_id: str) -> bool:
        with self._lock, closing(self._connect()) as conn:
            cursor = conn.execute("DELETE FROM artifacts WHERE id = ?", (artifact_id,))
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def _row_to_artifact(row: sqlite3.Row) -> Artifact:
        data = dict(row)
        try:
            data["metadata"] = json.loads(data.get("metadata") or "{}")
        except (json.JSONDecodeError, TypeError):
            data["metadata"] = {}
        return Artifact.from_dict(data)


_store_singleton: Optional[ArtifactStore] = None
_store_lock = threading.Lock()


def get_artifact_store() -> ArtifactStore:
    global _store_singleton
    if _store_singleton is None:
        with _store_lock:
            if _store_singleton is None:
                _store_singleton = ArtifactStore()
    return _store_singleton