"""
core/workspace_links/store.py - SQLite persistence for WorkspaceLink
records (Sprint 2.7 / Wave 2 / W6).

Owns database/workspace_links.db EXCLUSIVELY ("satu .db, satu pemilik
modul" - docs/database.md), same convention as core/artifacts/store.py
and core/attachments/store.py. Only ever stores CONVERSATION-kind links
(explicit session <-> path ownership for files not already tracked by
core.artifacts/core.attachments) - ARTIFACT/ATTACHMENT-kind WorkspaceLink
objects returned by the service layer are DERIVED at read time from those
other stores and are never written here (no duplicated ownership data).
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from typing import Optional

from core.workspace_links.models import WorkspaceLink

BASE_DIR = Path(__file__).resolve().parents[2]  # AIRA_ECOSYSTEM/
DEFAULT_DB_FILE = BASE_DIR / "database" / "workspace_links.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS workspace_links (
    id TEXT PRIMARY KEY,
    relative_path TEXT NOT NULL,
    session_id TEXT NOT NULL,
    message_id TEXT,
    kind TEXT NOT NULL DEFAULT 'conversation',
    ref_id TEXT,
    note TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_workspace_links_path ON workspace_links(relative_path);
CREATE INDEX IF NOT EXISTS idx_workspace_links_session ON workspace_links(session_id);
"""


class WorkspaceLinkStore:

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

    # ------------------------------------------------------------ write

    def save(self, link: WorkspaceLink) -> WorkspaceLink:
        with self._lock, closing(self._connect()) as conn:
            conn.execute("""
                INSERT INTO workspace_links
                    (id, relative_path, session_id, message_id, kind, ref_id, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    relative_path = excluded.relative_path,
                    session_id = excluded.session_id,
                    message_id = excluded.message_id,
                    kind = excluded.kind,
                    ref_id = excluded.ref_id,
                    note = excluded.note
            """, (
                link.id, link.relative_path, link.session_id, link.message_id,
                link.kind, link.ref_id, link.note, link.created_at,
            ))
            conn.commit()

        return link

    def delete(self, link_id: str) -> bool:
        with self._lock, closing(self._connect()) as conn:
            cursor = conn.execute("DELETE FROM workspace_links WHERE id = ?", (link_id,))
            conn.commit()
            return cursor.rowcount > 0

    def delete_by_path(self, relative_path: str) -> int:
        """Remove ALL conversation-links for a path (e.g. right before the
        path itself is deleted/moved in the Workspace). Returns rows removed."""
        normalized = (relative_path or "").replace("\\", "/").strip("/")

        with self._lock, closing(self._connect()) as conn:
            cursor = conn.execute("DELETE FROM workspace_links WHERE relative_path = ?", (normalized,))
            conn.commit()
            return cursor.rowcount

    # ------------------------------------------------------------- read

    def get(self, link_id: str) -> Optional[WorkspaceLink]:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM workspace_links WHERE id = ?", (link_id,)).fetchone()
        return self._row_to_link(row) if row else None

    def get_by_path(self, relative_path: str) -> Optional[WorkspaceLink]:
        """Most recent CONVERSATION-kind link for this path, if any."""
        normalized = (relative_path or "").replace("\\", "/").strip("/")

        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM workspace_links WHERE relative_path = ? ORDER BY created_at DESC LIMIT 1",
                (normalized,),
            ).fetchone()

        return self._row_to_link(row) if row else None

    def list_for_session(self, session_id: str) -> list[WorkspaceLink]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM workspace_links WHERE session_id = ? ORDER BY created_at DESC",
                (session_id,),
            ).fetchall()

        return [self._row_to_link(r) for r in rows]

    @staticmethod
    def _row_to_link(row: sqlite3.Row) -> WorkspaceLink:
        return WorkspaceLink.from_dict(dict(row))


_store_singleton: Optional[WorkspaceLinkStore] = None
_store_lock = threading.Lock()


def get_workspace_link_store() -> WorkspaceLinkStore:
    global _store_singleton
    if _store_singleton is None:
        with _store_lock:
            if _store_singleton is None:
                _store_singleton = WorkspaceLinkStore()
    return _store_singleton