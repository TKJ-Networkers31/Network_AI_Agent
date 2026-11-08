"""
tests/filesystem/test_workspace_and_operations.py — unit test untuk
WorkspaceManager, FileOperations, HistoryEngine, TrashEngine, dan
PermissionEngine (FSE), Sprint 02.

Setiap test memakai workspace SEMENTARA (tempfile.TemporaryDirectory) -
TIDAK PERNAH menyentuh workspace asli milik user.

Jalankan dari root AIRA_ECOSYSTEM/:
    python -m unittest tests.filesystem.test_workspace_and_operations -v
"""

import tempfile
import unittest
from pathlib import Path

from core.host.models import HostInfo
from core.host.linux import LinuxHostAdapter
from core.filesystem.workspace import WorkspaceManager, PathTraversalError
from core.filesystem.operations import FileOperations
from core.filesystem.permissions import PermissionEngine
from core.filesystem.history import HistoryEngine
from core.filesystem.trash import TrashEngine
from core.filesystem.models import PermissionLevel


def _make_workspace(tmp_dir: str) -> WorkspaceManager:
    workspace_root = str(Path(tmp_dir) / "AIRA_WORKSPACE")

    info = HostInfo(
        os_name="linux", os_version="test", architecture="x86_64",
        hostname="test-host", username="test-user",
        home_directory=tmp_dir, workspace_root=workspace_root,
        separator="/", case_sensitive=True,
    )

    manager = WorkspaceManager(adapter=LinuxHostAdapter(info))
    manager.initialize()

    return manager


class TestWorkspaceInitialization(unittest.TestCase):

    def test_initialize_creates_standard_subfolders(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = _make_workspace(tmp)

            for sub in ("Projects", "Documents", "Images", "Temp", "Trash", ".aira_history"):
                self.assertTrue((manager.root / sub).exists(), f"subfolder hilang: {sub}")

    def test_initialize_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = _make_workspace(tmp)
            result = manager.initialize()
            self.assertTrue(result["success"])


class TestPathTraversal(unittest.TestCase):

    def test_resolve_rejects_traversal_outside_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = _make_workspace(tmp)
            with self.assertRaises(PathTraversalError):
                manager.resolve("../../etc/passwd")

    def test_resolve_allows_path_inside_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = _make_workspace(tmp)
            resolved = manager.resolve("Projects/demo.txt")
            self.assertTrue(str(resolved).startswith(str(manager.root)))

    def test_exists_returns_false_for_traversal_instead_of_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = _make_workspace(tmp)
            self.assertFalse(manager.exists("../../etc/passwd"))


class TestWriteAndSnapshot(unittest.TestCase):

    def test_write_then_overwrite_creates_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = _make_workspace(tmp)
            ops = FileOperations(
                workspace=manager, permissions=PermissionEngine(),
                history=HistoryEngine(manager.root), trash=TrashEngine(manager.root),
            )

            first = ops.write_text("Documents/note.txt", "versi 1")
            self.assertTrue(first.success)
            self.assertIsNone(first.snapshot_id)

            second = ops.write_text("Documents/note.txt", "versi 2")
            self.assertTrue(second.success)
            self.assertIsNotNone(second.snapshot_id)

            read_back = ops.read_text("Documents/note.txt")
            self.assertEqual(read_back.content, "versi 2")

            history = HistoryEngine(manager.root).list_history("Documents/note.txt")
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0].snapshot_id, second.snapshot_id)

    def test_restore_snapshot_brings_back_old_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = _make_workspace(tmp)
            history_engine = HistoryEngine(manager.root)
            ops = FileOperations(
                workspace=manager, permissions=PermissionEngine(),
                history=history_engine, trash=TrashEngine(manager.root),
            )

            ops.write_text("Documents/note.txt", "versi 1")
            second = ops.write_text("Documents/note.txt", "versi 2")

            self.assertTrue(history_engine.restore(second.snapshot_id))

            read_back = ops.read_text("Documents/note.txt")
            self.assertEqual(read_back.content, "versi 1")


class TestDeleteAndRestore(unittest.TestCase):

    def test_delete_moves_to_trash_not_permanent(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = _make_workspace(tmp)
            ops = FileOperations(
                workspace=manager, permissions=PermissionEngine(),
                history=HistoryEngine(manager.root), trash=TrashEngine(manager.root),
            )

            ops.write_text("Documents/note.txt", "isi")
            self.assertTrue(manager.exists("Documents/note.txt"))

            result = ops.delete("Documents/note.txt")
            self.assertTrue(result.success)
            self.assertFalse(manager.exists("Documents/note.txt"))

            trash_entries = TrashEngine(manager.root).list_trash()
            self.assertEqual(len(trash_entries), 1)
            self.assertEqual(trash_entries[0].original_path, "Documents/note.txt")

    def test_restore_from_trash_brings_file_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = _make_workspace(tmp)
            trash_engine = TrashEngine(manager.root)
            ops = FileOperations(
                workspace=manager, permissions=PermissionEngine(),
                history=HistoryEngine(manager.root), trash=trash_engine,
            )

            ops.write_text("Documents/note.txt", "isi penting")
            ops.delete("Documents/note.txt")

            trash_id = trash_engine.list_trash()[0].trash_id
            restore_result = ops.restore(trash_id)

            self.assertTrue(restore_result.success)
            self.assertTrue(manager.exists("Documents/note.txt"))

            read_back = ops.read_text("Documents/note.txt")
            self.assertEqual(read_back.content, "isi penting")


class TestPermissions(unittest.TestCase):

    def test_deny_blocks_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = _make_workspace(tmp)
            permissions = PermissionEngine()
            permissions.grant("Documents", PermissionLevel.READ_ONLY)

            ops = FileOperations(
                workspace=manager, permissions=permissions,
                history=HistoryEngine(manager.root), trash=TrashEngine(manager.root),
            )

            result = ops.write_text("Documents/blocked.txt", "harusnya gagal")
            self.assertFalse(result.success)
            self.assertFalse(manager.exists("Documents/blocked.txt"))

    def test_default_permission_is_read_write(self):
        permissions = PermissionEngine()
        self.assertTrue(permissions.can_read("Projects/anything"))
        self.assertTrue(permissions.can_write("Projects/anything"))


if __name__ == "__main__":
    unittest.main()