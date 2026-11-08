"""
core/filesystem/operations.py — CRUD File Operations untuk File System
Engine (FSE), Sprint 02.

Semua fungsi menerima path RELATIF terhadap workspace root, selalu
lewat WorkspaceManager.resolve() (sandbox), PermissionEngine (izin),
dan HistoryEngine/TrashEngine untuk snapshot & trash sebelum data
hilang.
"""

import logging
import shutil
from typing import Optional

from core.filesystem.workspace import WorkspaceManager, PathTraversalError, get_workspace_manager
from core.filesystem.permissions import PermissionEngine, get_permission_engine
from core.filesystem.history import HistoryEngine
from core.filesystem.trash import TrashEngine
from core.filesystem.models import ReadResult, WriteResult, OperationResult
from core.events import event_bus

logger = logging.getLogger("aira.filesystem.operations")


class FileOperations:
    """Dependency Injection untuk workspace/permissions/history/trash -
    kalau tidak diberikan, memakai singleton default."""

    def __init__(
        self,
        workspace: Optional[WorkspaceManager] = None,
        permissions: Optional[PermissionEngine] = None,
        history: Optional[HistoryEngine] = None,
        trash: Optional[TrashEngine] = None,
    ):
        self.workspace = workspace or get_workspace_manager()
        self.permissions = permissions or get_permission_engine()
        self.history = history or HistoryEngine(self.workspace.root)
        self.trash = trash or TrashEngine(self.workspace.root)

    def _deny(self, relative_path: str, action: str) -> OperationResult:
        logger.warning("PERMISSION DENIED | path=%s action=%s", relative_path, action)

        try:
            event_bus.publish(
                "permission.denied", agent="FSE",
                data={"path": relative_path, "action": action},
            )
        except Exception:
            logger.exception("Gagal publish event permission.denied (diabaikan).")

        return OperationResult(
            success=False, path=relative_path,
            error=f"Izin ditolak untuk aksi '{action}' pada '{relative_path}'.",
        )

    # ------------------------------------------------------------
    # READ
    # ------------------------------------------------------------

    def read_text(self, relative_path: str, encoding: str = "utf-8") -> ReadResult:
        if not self.permissions.can_read(relative_path):
            denied = self._deny(relative_path, "read")
            return ReadResult(success=False, path=relative_path, error=denied.error)

        try:
            absolute = self.workspace.resolve(relative_path)
        except PathTraversalError as exc:
            return ReadResult(success=False, path=relative_path, error=str(exc))

        if not absolute.exists() or not absolute.is_file():
            return ReadResult(success=False, path=relative_path, error="File tidak ditemukan.")

        try:
            content = absolute.read_text(encoding=encoding)
        except Exception as exc:
            logger.exception("Gagal membaca file %s", relative_path)
            return ReadResult(success=False, path=relative_path, error=str(exc))

        return ReadResult(success=True, path=relative_path, content=content)

    # ------------------------------------------------------------
    # WRITE
    # ------------------------------------------------------------

    def write_text(self, relative_path: str, content: str, encoding: str = "utf-8") -> WriteResult:
        if not self.permissions.can_write(relative_path):
            denied = self._deny(relative_path, "write")
            return WriteResult(success=False, path=relative_path, error=denied.error)

        try:
            absolute = self.workspace.resolve(relative_path)
        except PathTraversalError as exc:
            return WriteResult(success=False, path=relative_path, error=str(exc))

        snapshot_id = None
        is_update = absolute.exists() and absolute.is_file()

        try:
            if is_update:
                snapshot = self.history.create_snapshot(relative_path, absolute)
                snapshot_id = snapshot.snapshot_id

            absolute.parent.mkdir(parents=True, exist_ok=True)
            absolute.write_text(content, encoding=encoding)

        except Exception as exc:
            logger.exception("Gagal menulis file %s", relative_path)
            return WriteResult(success=False, path=relative_path, error=str(exc))

        try:
            event_bus.publish(
                "file.updated" if is_update else "file.created", agent="FSE",
                data={"path": relative_path, "snapshot_id": snapshot_id},
            )
        except Exception:
            logger.exception("Gagal publish event file.created/updated (diabaikan).")

        logger.info(
            "WRITE %s | path=%s snapshot_id=%s",
            "UPDATE" if is_update else "CREATE", relative_path, snapshot_id,
        )

        return WriteResult(success=True, path=relative_path, snapshot_id=snapshot_id)

    # ------------------------------------------------------------
    # MKDIR
    # ------------------------------------------------------------

    def mkdir(self, relative_path: str) -> OperationResult:
        if not self.permissions.can_write(relative_path):
            return self._deny(relative_path, "mkdir")

        try:
            absolute = self.workspace.resolve(relative_path)
        except PathTraversalError as exc:
            return OperationResult(success=False, path=relative_path, error=str(exc))

        try:
            absolute.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.exception("Gagal membuat folder %s", relative_path)
            return OperationResult(success=False, path=relative_path, error=str(exc))

        try:
            event_bus.publish("file.created", agent="FSE", data={"path": relative_path, "is_dir": True})
        except Exception:
            logger.exception("Gagal publish event file.created (diabaikan).")

        logger.info("MKDIR | path=%s", relative_path)

        return OperationResult(success=True, path=relative_path, message="Folder dibuat.")

    # ------------------------------------------------------------
    # MOVE / RENAME / COPY
    # ------------------------------------------------------------

    def move(self, source_relative: str, destination_relative: str) -> OperationResult:
        return self._move_or_rename(source_relative, destination_relative, action="move")

    def rename(self, source_relative: str, destination_relative: str) -> OperationResult:
        return self._move_or_rename(source_relative, destination_relative, action="rename")

    def _move_or_rename(self, source_relative: str, destination_relative: str, action: str) -> OperationResult:
        if not self.permissions.can_write(source_relative) or not self.permissions.can_write(destination_relative):
            return self._deny(f"{source_relative} -> {destination_relative}", action)

        try:
            source_abs = self.workspace.resolve(source_relative)
            dest_abs = self.workspace.resolve(destination_relative)
        except PathTraversalError as exc:
            return OperationResult(success=False, error=str(exc))

        if not source_abs.exists():
            return OperationResult(success=False, path=source_relative, error="Sumber tidak ditemukan.")

        try:
            dest_abs.parent.mkdir(parents=True, exist_ok=True)
            source_abs.rename(dest_abs)
        except Exception as exc:
            logger.exception("Gagal %s %s -> %s", action, source_relative, destination_relative)
            return OperationResult(success=False, error=str(exc))

        try:
            event_bus.publish(
                "file.updated", agent="FSE",
                data={"action": action, "from": source_relative, "to": destination_relative},
            )
        except Exception:
            logger.exception("Gagal publish event file.updated (diabaikan).")

        logger.info("%s | %s -> %s", action.upper(), source_relative, destination_relative)

        return OperationResult(success=True, path=destination_relative, message=f"{action} berhasil.")

    def copy(self, source_relative: str, destination_relative: str) -> OperationResult:
        if not self.permissions.can_read(source_relative) or not self.permissions.can_write(destination_relative):
            return self._deny(f"{source_relative} -> {destination_relative}", "copy")

        try:
            source_abs = self.workspace.resolve(source_relative)
            dest_abs = self.workspace.resolve(destination_relative)
        except PathTraversalError as exc:
            return OperationResult(success=False, error=str(exc))

        if not source_abs.exists():
            return OperationResult(success=False, path=source_relative, error="Sumber tidak ditemukan.")

        try:
            dest_abs.parent.mkdir(parents=True, exist_ok=True)

            if source_abs.is_dir():
                shutil.copytree(source_abs, dest_abs, dirs_exist_ok=True)
            else:
                shutil.copy2(source_abs, dest_abs)

        except Exception as exc:
            logger.exception("Gagal copy %s -> %s", source_relative, destination_relative)
            return OperationResult(success=False, error=str(exc))

        try:
            event_bus.publish(
                "file.created", agent="FSE",
                data={"action": "copy", "from": source_relative, "to": destination_relative},
            )
        except Exception:
            logger.exception("Gagal publish event file.created (diabaikan).")

        logger.info("COPY | %s -> %s", source_relative, destination_relative)

        return OperationResult(success=True, path=destination_relative, message="Copy berhasil.")

    # ------------------------------------------------------------
    # DELETE (-> Trash, TIDAK PERNAH permanen di sini)
    # ------------------------------------------------------------

    def delete(self, relative_path: str) -> OperationResult:
        if not self.permissions.can_write(relative_path):
            return self._deny(relative_path, "delete")

        try:
            absolute = self.workspace.resolve(relative_path)
        except PathTraversalError as exc:
            return OperationResult(success=False, path=relative_path, error=str(exc))

        if not absolute.exists():
            return OperationResult(success=False, path=relative_path, error="Path tidak ditemukan.")

        try:
            entry = self.trash.move_to_trash(relative_path, absolute)
        except Exception as exc:
            logger.exception("Gagal memindahkan ke trash: %s", relative_path)
            return OperationResult(success=False, path=relative_path, error=str(exc))

        try:
            event_bus.publish(
                "file.deleted", agent="FSE",
                data={"path": relative_path, "trash_id": entry.trash_id},
            )
        except Exception:
            logger.exception("Gagal publish event file.deleted (diabaikan).")

        logger.info("DELETE (-> TRASH) | path=%s trash_id=%s", relative_path, entry.trash_id)

        return OperationResult(
            success=True, path=relative_path,
            message=f"Dipindahkan ke Trash (trash_id={entry.trash_id}).",
        )

    # ------------------------------------------------------------
    # RESTORE (dari Trash)
    # ------------------------------------------------------------

    def restore(self, trash_id: str) -> OperationResult:
        ok = self.trash.restore(trash_id)

        if not ok:
            return OperationResult(success=False, error=f"trash_id '{trash_id}' tidak ditemukan atau gagal di-restore.")

        try:
            event_bus.publish("file.restored", agent="FSE", data={"trash_id": trash_id})
        except Exception:
            logger.exception("Gagal publish event file.restored (diabaikan).")

        return OperationResult(success=True, message=f"Restore berhasil (trash_id={trash_id}).")