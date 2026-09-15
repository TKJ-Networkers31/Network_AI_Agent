"""
core/dio/tests/dio/test_interaction_memory.py — unit test
InteractionMemory (Phase 2.4). Selalu memakai db_path SEMENTARA
(tempfile) — TIDAK PERNAH menyentuh database/interaction_memory.db asli.

Jalankan dari root AIRA_ECOSYSTEM/:
    python -m unittest core.dio.tests.dio.test_interaction_memory -v
"""

import tempfile
import time
import unittest
from pathlib import Path

from core.dio.interaction_memory import InteractionMemory


class TestInteractionMemory(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmp_dir.name) / "interaction_memory_test.db"
        self.memory = InteractionMemory(db_path=db_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_save_and_load(self):
        self.memory.save("last_project", "aira-os")
        self.assertEqual(self.memory.load("last_project"), "aira-os")

    def test_load_missing_key_returns_none(self):
        self.assertIsNone(self.memory.load("does_not_exist"))

    def test_save_dict_value(self):
        self.memory.save("last_workspace", {"path": "Projects/aira-os"})
        self.assertEqual(self.memory.load("last_workspace"), {"path": "Projects/aira-os"})

    def test_update_merges_dict(self):
        self.memory.save("recent_choice", {"mode": "ssh"})
        self.memory.update("recent_choice", {"verified": True})
        self.assertEqual(self.memory.load("recent_choice"), {"mode": "ssh", "verified": True})

    def test_update_on_missing_key_creates_it(self):
        self.memory.update("last_file", {"name": "hello.txt"})
        self.assertEqual(self.memory.load("last_file"), {"name": "hello.txt"})

    def test_clear_single_key(self):
        self.memory.save("last_date", "2026-09-15")
        self.memory.clear("last_date")
        self.assertIsNone(self.memory.load("last_date"))

    def test_clear_all(self):
        self.memory.save("a", 1)
        self.memory.save("b", 2)
        self.memory.clear()
        self.assertIsNone(self.memory.load("a"))
        self.assertIsNone(self.memory.load("b"))

    def test_ttl_expiry(self):
        self.memory.save("short_lived", "value", ttl_seconds=0.05)
        self.assertEqual(self.memory.load("short_lived"), "value")
        time.sleep(0.1)
        self.assertIsNone(self.memory.load("short_lived"))

    def test_ttl_zero_disables_expiry(self):
        self.memory.save("permanent", "value", ttl_seconds=0)
        self.assertEqual(self.memory.load("permanent"), "value")

    def test_purge_expired(self):
        self.memory.save("will_expire", "x", ttl_seconds=0.05)
        self.memory.save("stays", "y")
        time.sleep(0.1)
        deleted = self.memory.purge_expired()
        self.assertEqual(deleted, 1)
        self.assertEqual(self.memory.load("stays"), "y")


if __name__ == "__main__":
    unittest.main()