"""
tests/test_chat_sessions.py — Sprint 2.5 (Session): isolasi sesi & tidak ada
pembuatan sesi otomatis di lapisan penyimpanan.

Memakai database SEMENTARA (patch core.chat_sessions.DB_FILE) - TIDAK
menyentuh database/chat_sessions.db asli.

Jalankan dari root AIRA_ECOSYSTEM/:
    python -m unittest tests.test_chat_sessions -v
"""

import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from core import chat_sessions as store


class SessionStoreCase(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = mock.patch.object(store, "DB_FILE", Path(self._tmp.name) / "sessions_test.db")
        patcher.start()
        self.addCleanup(patcher.stop)
        store.init_db()


class TestNoImplicitCreation(SessionStoreCase):

    def test_fresh_store_has_no_sessions(self):
        # Membuka app tidak boleh menghasilkan sesi: penyimpanan kosong tetap kosong.
        self.assertEqual(store.list_sessions(), [])

    def test_listing_never_creates_sessions(self):
        for _ in range(3):
            store.list_sessions()
        self.assertEqual(store.list_sessions(), [])

    def test_each_create_is_explicit_and_unique(self):
        a = store.create_session()
        b = store.create_session()

        self.assertNotEqual(a["id"], b["id"])
        self.assertEqual({s["id"] for s in store.list_sessions()}, {a["id"], b["id"]})

    def test_history_is_newest_first(self):
        old = store.create_session()
        time.sleep(0.01)
        new = store.create_session()

        self.assertEqual([s["id"] for s in store.list_sessions()], [new["id"], old["id"]])


class TestSessionIsolation(SessionStoreCase):

    def test_turns_do_not_leak_between_sessions(self):
        a = store.create_session()["id"]
        b = store.create_session()["id"]

        store.add_turn(a, "user", "pesan A")
        store.add_turn(a, "assistant", "jawaban A")
        store.add_turn(b, "user", "pesan B")

        self.assertEqual([t["content"] for t in store.get_turns(a)], ["pesan A", "jawaban A"])
        self.assertEqual([t["content"] for t in store.get_turns(b)], ["pesan B"])

    def test_new_session_starts_clean(self):
        a = store.create_session()["id"]
        store.add_turn(a, "user", "isi lama")
        store.save_raw_history(a, [{"role": "user", "content": "isi lama"}])

        fresh = store.create_session()["id"]

        self.assertEqual(store.get_turns(fresh), [])
        self.assertEqual(store.load_raw_history(fresh), [])

    def test_raw_history_is_per_session(self):
        a = store.create_session()["id"]
        b = store.create_session()["id"]

        store.save_raw_history(a, [{"role": "user", "content": "A"}])

        self.assertEqual(store.load_raw_history(a), [{"role": "user", "content": "A"}])
        self.assertEqual(store.load_raw_history(b), [])

    def test_delete_removes_only_that_session(self):
        a = store.create_session()["id"]
        b = store.create_session()["id"]
        store.add_turn(a, "user", "A")
        store.add_turn(b, "user", "B")

        self.assertTrue(store.delete_session(a))

        self.assertIsNone(store.get_session_row(a))
        self.assertEqual(store.get_turns(a), [])
        self.assertEqual([t["content"] for t in store.get_turns(b)], ["B"])
        self.assertEqual([s["id"] for s in store.list_sessions()], [b])

    def test_delete_unknown_session_returns_false(self):
        self.assertFalse(store.delete_session("tidak-ada"))

    def test_truncate_only_affects_own_session(self):
        a = store.create_session()["id"]
        b = store.create_session()["id"]
        first = store.add_turn(a, "user", "A1")
        store.add_turn(a, "assistant", "A2")
        store.add_turn(b, "user", "B1")

        deleted = store.truncate_turns_from(a, first)

        self.assertEqual(deleted, 2)
        self.assertEqual(store.get_turns(a), [])
        self.assertEqual([t["content"] for t in store.get_turns(b)], ["B1"])

    def test_autotitle_only_touches_target_session(self):
        a = store.create_session()["id"]
        b = store.create_session()["id"]

        store.maybe_autotitle(a, "cek resource R1")

        self.assertEqual(store.get_session_row(a)["title"], "cek resource R1")
        self.assertEqual(store.get_session_row(b)["title"], store.DEFAULT_TITLE)


if __name__ == "__main__":
    unittest.main()