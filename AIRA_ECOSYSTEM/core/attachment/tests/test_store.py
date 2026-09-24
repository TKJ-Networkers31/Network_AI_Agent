import tempfile
import unittest
from pathlib import Path

from core.attachments.models import Attachment
from core.attachments.store import AttachmentStore


class TestAttachmentStore(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = AttachmentStore(db_path=Path(self.tmp.name) / "attachments_test.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_and_get(self):
        att = Attachment(name="report.pdf", mime_type="application/pdf", session_id="s1")
        self.store.save(att)

        fetched = self.store.get(att.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "report.pdf")
        self.assertEqual(fetched.session_id, "s1")

    def test_get_missing_returns_none(self):
        self.assertIsNone(self.store.get("does-not-exist"))

    def test_metadata_round_trip(self):
        att = Attachment(name="a", metadata={"checksum": "x", "nested": {"y": 1}})
        self.store.save(att)
        fetched = self.store.get(att.id)
        self.assertEqual(fetched.metadata, {"checksum": "x", "nested": {"y": 1}})

    def test_save_overwrites_existing_row(self):
        att = Attachment(name="a", status="pending")
        self.store.save(att)

        att.status = "available"
        att.storage_reference = "Attachments/x.txt"
        self.store.save(att)

        fetched = self.store.get(att.id)
        self.assertEqual(fetched.status, "available")
        self.assertEqual(fetched.storage_reference, "Attachments/x.txt")

    def test_list_filters_by_session(self):
        self.store.save(Attachment(name="a", session_id="s1", status="available"))
        self.store.save(Attachment(name="b", session_id="s2", status="available"))

        results = self.store.list(session_id="s1")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "a")

    def test_list_filters_by_message(self):
        self.store.save(Attachment(name="a", message_id="m1", status="available"))
        self.store.save(Attachment(name="b", message_id="m2", status="available"))

        results = self.store.list(message_id="m1")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "a")

    def test_list_filters_by_status(self):
        self.store.save(Attachment(name="a", status="failed"))
        self.store.save(Attachment(name="b", status="available"))

        results = self.store.list(status="failed")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "a")

    def test_list_excludes_deleted_by_default(self):
        self.store.save(Attachment(name="a", status="deleted"))
        self.store.save(Attachment(name="b", status="available"))

        results = self.store.list()
        self.assertEqual([r.name for r in results], ["b"])

    def test_list_includes_deleted_when_requested(self):
        self.store.save(Attachment(name="a", status="deleted"))
        results = self.store.list(include_deleted=True)
        self.assertEqual(len(results), 1)

    def test_list_filters_by_source(self):
        self.store.save(Attachment(name="a", source="workspace", status="available"))
        self.store.save(Attachment(name="b", source="user_upload", status="available"))

        results = self.store.list(source="workspace")
        self.assertEqual([r.name for r in results], ["a"])

    def test_count(self):
        self.store.save(Attachment(name="a", session_id="s1"))
        self.store.save(Attachment(name="b", session_id="s1"))
        self.store.save(Attachment(name="c", session_id="s2"))

        self.assertEqual(self.store.count(), 3)
        self.assertEqual(self.store.count(session_id="s1"), 2)

    def test_delete(self):
        att = Attachment(name="a")
        self.store.save(att)
        self.assertTrue(self.store.delete(att.id))
        self.assertFalse(self.store.delete(att.id))
        self.assertIsNone(self.store.get(att.id))


if __name__ == "__main__":
    unittest.main()
