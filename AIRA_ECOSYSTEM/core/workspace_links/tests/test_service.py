import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.workspace_links.models import LinkKind
from core.workspace_links.service import WorkspaceIntegrationService
from core.workspace_links.store import WorkspaceLinkStore


def _ok_write(_path, _content):
    return SimpleNamespace(success=True, error=None)


def _fail_write(_path, _content):
    return SimpleNamespace(success=False, error="disk penuh")


def _always_true(_session_id):
    return True


def _always_false(_session_id):
    return False


class WorkspaceIntegrationTestBase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = WorkspaceLinkStore(db_path=Path(self.tmp.name) / "workspace_links_test.db")
        self.artifacts = {}
        self.attachments = {}

        self.service = WorkspaceIntegrationService(
            store=self.store,
            write_text=_ok_write,
            workspace_exists=lambda p: p == "Documents/existing.txt",
            session_lookup=_always_true,
            artifact_lookup=lambda p: self.artifacts.get(p),
            attachment_lookup=lambda p: self.attachments.get(p),
            artifacts_for_session=lambda sid: [a for a in self.artifacts.values() if a.session_id == sid],
            attachments_for_session=lambda sid: [a for a in self.attachments.values() if a.session_id == sid],
        )

    def tearDown(self):
        self.tmp.cleanup()


class TestConversationToWorkspace(WorkspaceIntegrationTestBase):

    def test_save_conversation_file_success(self):
        result = self.service.save_conversation_file(
            session_id="s1", relative_path="Documents/note.txt", content="hi", message_id="m1",
        )
        self.assertTrue(result.success, result.errors)
        self.assertEqual(result.link.kind, LinkKind.CONVERSATION.value)
        self.assertEqual(result.link.session_id, "s1")

        fetched = self.store.get_by_path("Documents/note.txt")
        self.assertIsNotNone(fetched)

    def test_missing_session_id_rejected(self):
        result = self.service.save_conversation_file(session_id="", relative_path="a.txt", content="x")
        self.assertFalse(result.success)

    def test_missing_relative_path_rejected(self):
        result = self.service.save_conversation_file(session_id="s1", relative_path="", content="x")
        self.assertFalse(result.success)

    def test_unknown_session_rejected(self):
        service = WorkspaceIntegrationService(
            store=self.store, write_text=_ok_write, session_lookup=_always_false,
        )
        result = service.save_conversation_file(session_id="ghost", relative_path="a.txt", content="x")
        self.assertFalse(result.success)

    def test_write_failure_reported_not_raised(self):
        service = WorkspaceIntegrationService(store=self.store, write_text=_fail_write, session_lookup=_always_true)
        result = service.save_conversation_file(session_id="s1", relative_path="a.txt", content="x")
        self.assertFalse(result.success)
        self.assertIn("disk penuh", result.errors[0])

    def test_write_exception_reported_not_raised(self):
        def boom(_p, _c):
            raise RuntimeError("kaboom")

        service = WorkspaceIntegrationService(store=self.store, write_text=boom, session_lookup=_always_true)
        result = service.save_conversation_file(session_id="s1", relative_path="a.txt", content="x")
        self.assertFalse(result.success)

    def test_reserved_artifacts_prefix_rejected(self):
        result = self.service.save_conversation_file(
            session_id="s1", relative_path="Artifacts/x.docx", content="x",
        )
        self.assertFalse(result.success)

    def test_reserved_attachments_prefix_rejected(self):
        result = self.service.adopt_workspace_file(session_id="s1", relative_path="Attachments/x.pdf")
        self.assertFalse(result.success)

    def test_adopt_existing_workspace_file(self):
        result = self.service.adopt_workspace_file(session_id="s1", relative_path="Documents/existing.txt")
        self.assertTrue(result.success, result.errors)
        self.assertEqual(result.link.kind, LinkKind.CONVERSATION.value)

    def test_adopt_missing_file_rejected(self):
        result = self.service.adopt_workspace_file(session_id="s1", relative_path="Documents/missing.txt")
        self.assertFalse(result.success)


class TestWorkspaceToConversation(WorkspaceIntegrationTestBase):

    def test_resolve_owner_conversation_link(self):
        self.service.save_conversation_file(session_id="s1", relative_path="Documents/note.txt", content="x")

        owner = self.service.resolve_owner("Documents/note.txt")
        self.assertIsNotNone(owner)
        self.assertEqual(owner.session_id, "s1")
        self.assertEqual(owner.kind, LinkKind.CONVERSATION.value)

    def test_resolve_owner_artifact_derived(self):
        self.artifacts["Artifacts/x.docx"] = SimpleNamespace(
            id="artifact_1", session_id="s1", storage_reference="Artifacts/x.docx", created_at=1.0,
        )
        owner = self.service.resolve_owner("Artifacts/x.docx")
        self.assertIsNotNone(owner)
        self.assertEqual(owner.kind, LinkKind.ARTIFACT.value)
        self.assertEqual(owner.ref_id, "artifact_1")

    def test_resolve_owner_attachment_derived(self):
        self.attachments["Attachments/y.pdf"] = SimpleNamespace(
            id="att_1", session_id="s2", message_id="m9",
            storage_reference="Attachments/y.pdf", created_at=2.0,
        )
        owner = self.service.resolve_owner("Attachments/y.pdf")
        self.assertIsNotNone(owner)
        self.assertEqual(owner.kind, LinkKind.ATTACHMENT.value)
        self.assertEqual(owner.ref_id, "att_1")

    def test_resolve_owner_conversation_link_wins_over_artifact(self):
        self.artifacts["shared.txt"] = SimpleNamespace(
            id="artifact_1", session_id="s-other", storage_reference="shared.txt", created_at=1.0,
        )
        self.service.save_conversation_file(session_id="s1", relative_path="shared.txt", content="x")

        owner = self.service.resolve_owner("shared.txt")
        self.assertEqual(owner.kind, LinkKind.CONVERSATION.value)
        self.assertEqual(owner.session_id, "s1")

    def test_resolve_owner_unowned_path_returns_none(self):
        self.assertIsNone(self.service.resolve_owner("nowhere.txt"))

    def test_resolve_owner_empty_path_returns_none(self):
        self.assertIsNone(self.service.resolve_owner(""))

    def test_list_for_session_combines_all_sources(self):
        self.service.save_conversation_file(session_id="s1", relative_path="a.txt", content="x")
        self.artifacts["b.docx"] = SimpleNamespace(
            id="artifact_1", session_id="s1", storage_reference="b.docx", created_at=1.0,
        )
        self.attachments["c.pdf"] = SimpleNamespace(
            id="att_1", session_id="s1", message_id=None,
            storage_reference="c.pdf", created_at=2.0, is_deleted=False,
        )
        self.attachments["d.pdf"] = SimpleNamespace(
            id="att_2", session_id="s1", message_id=None,
            storage_reference="d.pdf", created_at=3.0, is_deleted=True,
        )

        links = self.service.list_for_session("s1")
        paths = {l.relative_path for l in links}
        self.assertIn("a.txt", paths)
        self.assertIn("b.docx", paths)
        self.assertIn("c.pdf", paths)
        self.assertNotIn("d.pdf", paths)  # soft-deleted attachment excluded

    def test_list_for_session_empty_session_id_returns_empty(self):
        self.assertEqual(self.service.list_for_session(""), [])

    def test_list_for_session_source_failure_does_not_raise(self):
        def boom(_sid):
            raise RuntimeError("db down")

        service = WorkspaceIntegrationService(
            store=self.store, session_lookup=_always_true,
            artifacts_for_session=boom, attachments_for_session=boom,
        )
        self.service.save_conversation_file(session_id="s1", relative_path="a.txt", content="x")

        links = service.list_for_session("s1")
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].relative_path, "a.txt")


class TestRelease(WorkspaceIntegrationTestBase):

    def test_release_removes_conversation_links(self):
        self.service.save_conversation_file(session_id="s1", relative_path="a.txt", content="x")
        removed = self.service.release("a.txt")
        self.assertEqual(removed, 1)
        self.assertIsNone(self.service.resolve_owner("a.txt"))


if __name__ == "__main__":
    unittest.main()