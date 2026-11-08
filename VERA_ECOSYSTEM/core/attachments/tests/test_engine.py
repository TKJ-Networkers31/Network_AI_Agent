import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.attachments.engine import AttachmentEngine
from core.attachments.models import AttachmentStatus
from core.attachments.store import AttachmentStore


def _always_true(_session_id):
    return True


def _always_false(_session_id):
    return False


class AttachmentEngineTestBase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace_root = Path(self.tmp.name) / "workspace"
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.trash_calls = []

        self.store = AttachmentStore(db_path=Path(self.tmp.name) / "attachments_test.db")
        self.engine = AttachmentEngine(
            store=self.store,
            resolve_path=lambda rel: self.workspace_root / rel,
            workspace_exists=lambda rel: (self.workspace_root / rel).exists(),
            trash_delete=self._fake_trash_delete,
            session_lookup=_always_true,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _fake_trash_delete(self, relative_path: str) -> bool:
        self.trash_calls.append(relative_path)
        target = self.workspace_root / relative_path
        if target.exists():
            target.unlink()
        return True


class TestCreateFromUpload(AttachmentEngineTestBase):

    def test_upload_success(self):
        result = self.engine.create_from_upload(
            content=b"hello world", name="note.txt", session_id="s1",
        )
        self.assertTrue(result.success, result.errors)
        att = result.attachment
        self.assertEqual(att.status, AttachmentStatus.AVAILABLE.value)
        self.assertEqual(att.size, len(b"hello world"))
        self.assertTrue(att.storage_reference.startswith("Attachments/"))

        absolute = self.workspace_root / att.storage_reference
        self.assertTrue(absolute.exists())
        self.assertEqual(absolute.read_bytes(), b"hello world")

        fetched = self.store.get(att.id)
        self.assertEqual(fetched.status, AttachmentStatus.AVAILABLE.value)

    def test_upload_infers_mime_from_extension(self):
        result = self.engine.create_from_upload(content=b"\x89PNG", name="photo.png", session_id="s1")
        self.assertTrue(result.success)
        self.assertEqual(result.attachment.mime_type, "image/png")

    def test_upload_rejects_invalid_extension(self):
        result = self.engine.create_from_upload(content=b"MZ...", name="virus.exe", session_id="s1")
        self.assertFalse(result.success)
        self.assertIsNone(result.attachment)

    def test_upload_rejects_missing_session(self):
        engine = AttachmentEngine(
            store=self.store,
            resolve_path=lambda rel: self.workspace_root / rel,
            session_lookup=_always_false,
        )
        result = engine.create_from_upload(content=b"data", name="note.txt", session_id="ghost")
        self.assertFalse(result.success)

    def test_upload_rejects_non_bytes_content(self):
        result = self.engine.create_from_upload(content="not bytes", name="note.txt", session_id="s1")  # type: ignore[arg-type]
        self.assertFalse(result.success)

    def test_upload_resolver_failure_marks_failed_not_raised(self):
        def boom(_rel):
            raise RuntimeError("sandbox denied")

        engine = AttachmentEngine(store=self.store, resolve_path=boom, session_lookup=_always_true)
        result = engine.create_from_upload(content=b"data", name="note.txt", session_id="s1")

        self.assertFalse(result.success)
        self.assertIsNotNone(result.attachment)
        self.assertEqual(result.attachment.status, AttachmentStatus.FAILED.value)
        self.assertIn("error", result.attachment.metadata)

        fetched = self.store.get(result.attachment.id)
        self.assertEqual(fetched.status, AttachmentStatus.FAILED.value)


class TestCreateFromWorkspace(AttachmentEngineTestBase):

    def test_reference_existing_file(self):
        existing = self.workspace_root / "Documents" / "existing.pdf"
        existing.parent.mkdir(parents=True, exist_ok=True)
        existing.write_bytes(b"%PDF-1.4 fake")

        result = self.engine.create_from_workspace(
            relative_path="Documents/existing.pdf", session_id="s1",
        )
        self.assertTrue(result.success, result.errors)
        self.assertEqual(result.attachment.status, AttachmentStatus.AVAILABLE.value)
        self.assertEqual(result.attachment.storage_reference, "Documents/existing.pdf")
        self.assertEqual(result.attachment.size, len(b"%PDF-1.4 fake"))

    def test_missing_file_rejected(self):
        result = self.engine.create_from_workspace(
            relative_path="Documents/missing.pdf", session_id="s1",
        )
        self.assertFalse(result.success)

    def test_empty_path_rejected(self):
        result = self.engine.create_from_workspace(relative_path="", session_id="s1")
        self.assertFalse(result.success)


class TestCreateFromArtifact(AttachmentEngineTestBase):

    def test_wraps_existing_artifact(self):
        artifact = SimpleNamespace(
            id="artifact_1", name="laporan.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size=555, storage_reference="Artifacts/artifact_1.docx",
        )
        result = self.engine.create_from_artifact(artifact=artifact, session_id="s1")

        self.assertTrue(result.success, result.errors)
        self.assertEqual(result.attachment.source, "generated")
        self.assertEqual(result.attachment.storage_reference, "Artifacts/artifact_1.docx")
        self.assertEqual(result.attachment.metadata["artifact_id"], "artifact_1")

    def test_artifact_without_storage_reference_rejected(self):
        artifact = SimpleNamespace(id="a", name="x.docx", mime_type="application/octet-stream",
                                    size=0, storage_reference=None)
        result = self.engine.create_from_artifact(artifact=artifact, session_id="s1")
        self.assertFalse(result.success)


class TestCreateExternal(AttachmentEngineTestBase):

    def test_reference_external_url(self):
        result = self.engine.create_external(
            url="https://example.com/report.pdf", name="report.pdf", session_id="s1",
        )
        self.assertTrue(result.success, result.errors)
        self.assertIsNone(result.attachment.storage_reference)
        self.assertEqual(result.attachment.metadata["url"], "https://example.com/report.pdf")

    def test_invalid_url_rejected(self):
        result = self.engine.create_external(url="ftp://example.com/x.pdf", name="x.pdf", session_id="s1")
        self.assertFalse(result.success)

    def test_empty_url_rejected(self):
        result = self.engine.create_external(url="", name="x.pdf", session_id="s1")
        self.assertFalse(result.success)


class TestReadAndAccessControl(AttachmentEngineTestBase):

    def test_get_returns_none_for_other_session(self):
        created = self.engine.create_from_upload(content=b"x", name="a.txt", session_id="s1")
        self.assertIsNone(self.engine.get(created.attachment.id, session_id="s2"))
        self.assertIsNotNone(self.engine.get(created.attachment.id, session_id="s1"))

    def test_get_without_session_filter_returns_it(self):
        created = self.engine.create_from_upload(content=b"x", name="a.txt", session_id="s1")
        self.assertIsNotNone(self.engine.get(created.attachment.id))

    def test_list_filters_by_session(self):
        self.engine.create_from_upload(content=b"x", name="a.txt", session_id="s1")
        self.engine.create_from_upload(content=b"y", name="b.txt", session_id="s2")

        self.assertEqual(len(self.engine.list(session_id="s1")), 1)

    def test_get_content_reference_workspace_path(self):
        created = self.engine.create_from_upload(content=b"hello", name="a.txt", session_id="s1")
        reference = self.engine.get_content_reference(created.attachment.id)

        self.assertEqual(reference["kind"], "workspace_path")
        self.assertEqual(reference["relative_path"], created.attachment.storage_reference)
        self.assertTrue(reference["absolute_path"].endswith(".txt"))

    def test_get_content_reference_external_url(self):
        created = self.engine.create_external(url="https://example.com/x.pdf", name="x.pdf", session_id="s1")
        reference = self.engine.get_content_reference(created.attachment.id)

        self.assertEqual(reference["kind"], "external_url")
        self.assertEqual(reference["url"], "https://example.com/x.pdf")

    def test_get_content_reference_respects_session_ownership(self):
        created = self.engine.create_from_upload(content=b"x", name="a.txt", session_id="s1")
        self.assertIsNone(self.engine.get_content_reference(created.attachment.id, session_id="s2"))

    def test_get_content_reference_none_for_missing(self):
        self.assertIsNone(self.engine.get_content_reference("does-not-exist"))

    def test_get_content_reference_none_when_not_available(self):
        att_result = self.engine.create_from_upload(content=b"x", name="a.txt", session_id="s1")
        self.engine.mark_failed(att_result.attachment.id, "boom")
        self.assertIsNone(self.engine.get_content_reference(att_result.attachment.id))

    def test_get_content_never_exposes_raw_bytes(self):
        created = self.engine.create_from_upload(content=b"secret bytes", name="a.txt", session_id="s1")
        reference = self.engine.get_content_reference(created.attachment.id)
        self.assertNotIn("content", reference)
        self.assertNotIn(b"secret bytes", str(reference).encode())


class TestAssociateAndDelete(AttachmentEngineTestBase):

    def test_associate_with_message(self):
        created = self.engine.create_from_upload(content=b"x", name="a.txt", session_id="s1")
        result = self.engine.associate_with_message(created.attachment.id, "turn-42")

        self.assertTrue(result.success)
        self.assertEqual(result.attachment.message_id, "turn-42")
        self.assertEqual(self.store.get(created.attachment.id).message_id, "turn-42")

    def test_associate_missing_attachment_fails(self):
        result = self.engine.associate_with_message("does-not-exist", "turn-1")
        self.assertFalse(result.success)

    def test_delete_upload_moves_file_to_trash(self):
        created = self.engine.create_from_upload(content=b"x", name="a.txt", session_id="s1")
        absolute = self.workspace_root / created.attachment.storage_reference
        self.assertTrue(absolute.exists())

        result = self.engine.delete(created.attachment.id)

        self.assertTrue(result.success)
        self.assertEqual(result.attachment.status, AttachmentStatus.DELETED.value)
        self.assertEqual(self.trash_calls, [created.attachment.storage_reference])
        self.assertFalse(absolute.exists())

    def test_delete_workspace_reference_does_not_touch_file(self):
        existing = self.workspace_root / "existing.txt"
        existing.write_bytes(b"do not delete me")

        created = self.engine.create_from_workspace(relative_path="existing.txt", session_id="s1")
        result = self.engine.delete(created.attachment.id)

        self.assertTrue(result.success)
        self.assertEqual(self.trash_calls, [])
        self.assertTrue(existing.exists())

    def test_delete_external_reference_does_not_call_trash(self):
        created = self.engine.create_external(url="https://example.com/x.pdf", name="x.pdf", session_id="s1")
        result = self.engine.delete(created.attachment.id)

        self.assertTrue(result.success)
        self.assertEqual(self.trash_calls, [])

    def test_delete_is_soft_metadata_remains_queryable_with_include_deleted(self):
        created = self.engine.create_from_upload(content=b"x", name="a.txt", session_id="s1")
        self.engine.delete(created.attachment.id)

        self.assertIsNone(self.engine.get(created.attachment.id))  # get() hides deleted
        self.assertEqual(len(self.store.list(include_deleted=True, status="deleted")), 1)

    def test_delete_missing_attachment_fails(self):
        result = self.engine.delete("does-not-exist")
        self.assertFalse(result.success)

    def test_delete_respects_session_ownership(self):
        created = self.engine.create_from_upload(content=b"x", name="a.txt", session_id="s1")
        result = self.engine.delete(created.attachment.id, session_id="s2")
        self.assertFalse(result.success)


class TestMarkFailed(AttachmentEngineTestBase):

    def test_mark_failed_sets_status_and_error(self):
        created = self.engine.create_from_upload(content=b"x", name="a.txt", session_id="s1")
        result = self.engine.mark_failed(created.attachment.id, "checksum mismatch")

        self.assertFalse(result.success)
        self.assertEqual(result.attachment.status, AttachmentStatus.FAILED.value)
        self.assertEqual(result.attachment.metadata["error"], "checksum mismatch")

    def test_mark_failed_missing_attachment(self):
        result = self.engine.mark_failed("does-not-exist", "x")
        self.assertFalse(result.success)


if __name__ == "__main__":
    unittest.main()
