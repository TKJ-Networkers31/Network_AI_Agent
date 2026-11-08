"""
tests/host/test_host_adapters.py — unit test Windows/Linux adapter (HAL).

Jalankan dari root AIRA_ECOSYSTEM/:
    python -m unittest tests.host.test_host_adapters -v
"""

import tempfile
import unittest
from pathlib import Path, PureWindowsPath, PurePosixPath

from core.host.models import HostInfo
from core.host.windows import WindowsHostAdapter
from core.host.linux import LinuxHostAdapter


def _fake_host_info(os_name: str, workspace_root: str, home: str) -> HostInfo:
    return HostInfo(
        os_name=os_name, os_version="test", architecture="x86_64",
        hostname="test-host", username="test-user",
        home_directory=home, workspace_root=workspace_root,
        separator="\\" if os_name == "windows" else "/",
        case_sensitive=(os_name != "windows"),
    )


class TestWindowsAdapter(unittest.TestCase):

    def setUp(self):
        self.info = _fake_host_info("windows", "D:/AIRA_WORKSPACE", "C:/Users/test")
        self.adapter = WindowsHostAdapter(self.info)

    def test_normalize_path_converts_forward_slash(self):
        result = self.adapter.normalize_path("Projects/foo/bar.txt")
        self.assertIsInstance(result, PureWindowsPath)
        self.assertEqual(str(result), "Projects\\foo\\bar.txt")

    def test_normalize_path_keeps_backslash(self):
        result = self.adapter.normalize_path("Projects\\foo\\bar.txt")
        self.assertEqual(str(result), "Projects\\foo\\bar.txt")

    def test_resolve_relative_joins_base_and_relative(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            resolved = self.adapter.resolve_relative(base, "Projects/demo.txt")
            self.assertTrue(str(resolved).startswith(str(base.resolve())))
            self.assertTrue(str(resolved).endswith("demo.txt"))

    def test_resolve_relative_traversal_escapes_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "workspace"
            base.mkdir()
            resolved = self.adapter.resolve_relative(base, "../outside.txt")
            self.assertFalse(str(resolved).startswith(str(base)))

    def test_is_case_sensitive_false(self):
        self.assertFalse(self.adapter.is_case_sensitive())

    def test_path_separator(self):
        self.assertEqual(self.adapter.path_separator(), "\\")


class TestLinuxAdapter(unittest.TestCase):

    def setUp(self):
        self.info = _fake_host_info("linux", "/home/test/AIRA_WORKSPACE", "/home/test")
        self.adapter = LinuxHostAdapter(self.info)

    def test_normalize_path_converts_backslash(self):
        result = self.adapter.normalize_path("Projects\\foo\\bar.txt")
        self.assertIsInstance(result, PurePosixPath)
        self.assertEqual(str(result), "Projects/foo/bar.txt")

    def test_resolve_relative_joins_base_and_relative(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            resolved = self.adapter.resolve_relative(base, "Projects/demo.txt")
            self.assertTrue(str(resolved).startswith(str(base.resolve())))

    def test_resolve_relative_traversal_escapes_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "workspace"
            base.mkdir()
            resolved = self.adapter.resolve_relative(base, "../outside.txt")
            self.assertFalse(str(resolved).startswith(str(base)))

    def test_is_case_sensitive_true(self):
        self.assertTrue(self.adapter.is_case_sensitive())

    def test_path_separator(self):
        self.assertEqual(self.adapter.path_separator(), "/")


if __name__ == "__main__":
    unittest.main()