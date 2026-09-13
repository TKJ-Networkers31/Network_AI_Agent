"""
core/filesystem/workspace.py — WorkspaceManager (root dari File System
Engine, Sprint 02).

SATU-SATUNYA titik yang boleh menerjemahkan path relatif menjadi path
absolut di disk. Modul FSE lain (operations.py, history.py, trash.py,
permissions.py) menerima path yang SUDAH di-resolve lewat
WorkspaceManager.resolve() - tidak ada yang membangun Path sendiri dari
input user mentah.

Sandbox: setiap path hasil resolve() WAJIB berada di dalam
workspace_root. Percobaan keluar akan ditolak dengan PathTraversalError.
"""

import logging
from pathlib import Path
from typing import Optional

from core.host import get_default_adapter, get_host_info
from core.filesystem.models import FileEntry, TreeNode
from core.events import event_bus

logger = logging.getLogger("aira.filesystem.workspace")

SUBFOLDERS = ("Projects", "Documents", "Images", "Temp", "Trash", ".aira_history")


class PathTraversalError(Exception):
    """Dilempar ketika path hasil resolve() keluar dari workspace_root."""


class WorkspaceManager:
    """
    Dependency Injection: adapter HAL diterima lewat konstruktor
    (default: get_default_adapter()) - TIDAK pernah mendeteksi OS
    sendiri.
    """

    def __init__(self, adapter=None):
        self.adapter = adapter or get_default_adapter()
        self.host_info = get_host_info()
        self.root = Path(self.adapter.get_workspace()).resolve()

    # ------------------------------------------------------------
    # INIT
    # ------------------------------------------------------------

    def initialize(self) -> dict:
        """Buat root workspace + subfolder standar. Idempotent."""

        created = []

        self.root.mkdir(parents=True, exist_ok=True)

        for sub in SUBFOLDERS:
            folder = self.root / sub
            if not folder.exists():
                folder.mkdir(parents=True, exist_ok=True)
                created.append(sub)

        logger.info("WORKSPACE INITIALIZED | root=%s created=%s", self.root, created)

        try:
            event_bus.publish(
                "workspace.initialized", agent="FSE",
                data={"root": str(self.root), "created": created},
            )
        except Exception:
            logger.exception("Gagal publish event workspace.initialized (diabaikan).")

        return {"success": True, "root": str(self.root), "created": created}

    # ------------------------------------------------------------
    # RESOLVE / SANDBOX
    # ------------------------------------------------------------

    def resolve(self, relative_path: str) -> Path:
        """Terjemahkan path relatif jadi Path absolut di dalam
        workspace. SATU-SATUNYA pintu sandbox enforcement untuk FSE."""

        relative_path = (relative_path or "").strip()

        candidate = self.adapter.resolve_relative(self.root, relative_path)

        try:
            candidate.relative_to(self.root)
        except ValueError:
            logger.warning(
                "PATH TRAVERSAL DITOLAK | input=%r resolved=%s root=%s",
                relative_path, candidate, self.root,
            )
            raise PathTraversalError(
                f"Path '{relative_path}' berada di luar workspace sandbox."
            )

        return candidate

    def exists(self, relative_path: str) -> bool:
        try:
            return self.resolve(relative_path).exists()
        except PathTraversalError:
            return False

    # ------------------------------------------------------------
    # TREE
    # ------------------------------------------------------------

    def _build_entry(self, absolute_path: Path) -> FileEntry:
        stat = absolute_path.stat()
        relative = absolute_path.relative_to(self.root)

        return FileEntry(
            name=absolute_path.name,
            path=str(relative).replace("\\", "/"),
            is_dir=absolute_path.is_dir(),
            size=0 if absolute_path.is_dir() else stat.st_size,
            modified_at=stat.st_mtime,
        )

    def tree(self, relative_path: str = "", max_depth: int = 6) -> TreeNode:
        start = self.resolve(relative_path) if relative_path else self.root

        if not start.exists():
            raise FileNotFoundError(f"Path tidak ditemukan: {relative_path or '/'}")

        return self._walk(start, max_depth)

    def _walk(self, absolute_path: Path, depth_remaining: int) -> TreeNode:
        entry = self._build_entry(absolute_path)
        node = TreeNode(entry=entry, children=[])

        if absolute_path.is_dir() and depth_remaining > 0:
            try:
                children = sorted(
                    absolute_path.iterdir(),
                    key=lambda p: (not p.is_dir(), p.name.lower()),
                )
            except PermissionError:
                children = []

            for child in children:
                node.children.append(self._walk(child, depth_remaining - 1))

        return node


_manager_singleton: Optional[WorkspaceManager] = None


def get_workspace_manager() -> WorkspaceManager:
    global _manager_singleton

    if _manager_singleton is None:
        _manager_singleton = WorkspaceManager()
        _manager_singleton.initialize()

    return _manager_singleton