import tempfile
import unittest
from pathlib import Path

from core.workspace_links.models import WorkspaceLink, LinkKind
from core.workspace_links.store import WorkspaceLinkStore


class TestWorkspaceLinkStore(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = WorkspaceLinkStore(db_path=Path(self.tmp.name) / "workspace_links_test.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_and_get(self):
        link = WorkspaceLink(relative_path="Documents/note.txt", session_id="s1")
        self.store.save(link)

        fetched = self.store.get(link.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.relative_path, "Documents/note.txt")
        self.assertEqual(fetched.session_id, "s1")
        self.assertEqual(fetched.kind, LinkKind.CONVERSATION.value)

    def test_get_missing_returns_none(self):
        self.assertIsNone(self.store.get("does-not-exist"))

    def test_get_by_path_returns_latest(self):
        self.store.save(WorkspaceLink(relative_path="Documents/note.txt", session_id="s1"))
        newest = WorkspaceLink(relative_path="Documents/note.txt", session_id="s2")
        self.store.save(newest)

        fetched = self.store.get_by_path("Documents/note.txt")
        self.assertEqual(fetched.session_id, "s2")

    def test_get_by_path_normalizes_slashes(self):
        self.store.save(WorkspaceLink(relative_path="Documents/note.txt", session_id="s1"))
        fetched = self.store.get_by_path("/Documents/note.txt/")
        self.assertIsNotNone(fetched)

    def test_list_for_session(self):
        self.store.save(WorkspaceLink(relative_path="a.txt", session_id="s1"))
        self.store.save(WorkspaceLink(relative_path="b.txt", session_id="s1"))
        self.store.save(WorkspaceLink(relative_path="c.txt", session_id="s2"))

        results = self.store.list_for_session("s1")
        self.assertEqual(len(results), 2)

    def test_delete(self):
        link = WorkspaceLink(relative_path="a.txt", session_id="s1")
        self.store.save(link)
        self.assertTrue(self.store.delete(link.id))
        self.assertFalse(self.store.delete(link.id))

    def test_delete_by_path(self):
        self.store.save(WorkspaceLink(relative_path="a.txt", session_id="s1"))
        self.store.save(WorkspaceLink(relative_path="a.txt", session_id="s2"))
        self.store.save(WorkspaceLink(relative_path="b.txt", session_id="s1"))

        removed = self.store.delete_by_path("a.txt")
        self.assertEqual(removed, 2)
        self.assertIsNone(self.store.get_by_path("a.txt"))


if __name__ == "__main__":
    unittest.main()