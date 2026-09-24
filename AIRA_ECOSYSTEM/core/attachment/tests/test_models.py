import unittest

from core.attachments.models import (
    Attachment,
    AttachmentResult,
    AttachmentSource,
    AttachmentStatus,
    ValidationIssue,
    ValidationResult,
)


class TestAttachmentDefaults(unittest.TestCase):

    def test_minimal_construction_has_sane_defaults(self):
        att = Attachment()
        self.assertEqual(att.source, AttachmentSource.USER_UPLOAD.value)
        self.assertEqual(att.status, AttachmentStatus.PENDING.value)
        self.assertEqual(att.name, "untitled")
        self.assertEqual(att.mime_type, "application/octet-stream")
        self.assertEqual(att.size, 0)
        self.assertIsNone(att.storage_reference)
        self.assertTrue(att.id.startswith("att_"))

    def test_invalid_source_raises_via_coerce(self):
        with self.assertRaises(ValueError):
            Attachment(source="not_a_real_source")

    def test_invalid_status_falls_back_to_pending(self):
        att = Attachment(status="bogus")
        self.assertEqual(att.status, AttachmentStatus.PENDING.value)

    def test_empty_name_falls_back_to_untitled(self):
        att = Attachment(name="   ")
        self.assertEqual(att.name, "untitled")

    def test_negative_size_clamped_to_zero(self):
        att = Attachment(size=-5)
        self.assertEqual(att.size, 0)

    def test_non_numeric_size_falls_back_to_zero(self):
        att = Attachment(size="not-a-number")
        self.assertEqual(att.size, 0)

    def test_non_dict_metadata_becomes_empty_dict(self):
        att = Attachment(metadata="not a dict")  # type: ignore[arg-type]
        self.assertEqual(att.metadata, {})


class TestDerivedProperties(unittest.TestCase):

    def test_is_available(self):
        att = Attachment(status=AttachmentStatus.AVAILABLE.value)
        self.assertTrue(att.is_available)
        self.assertFalse(att.is_deleted)

    def test_is_deleted(self):
        att = Attachment(status=AttachmentStatus.DELETED.value)
        self.assertTrue(att.is_deleted)
        self.assertFalse(att.is_available)

    def test_owned_by_session_matches(self):
        att = Attachment(session_id="s1")
        self.assertTrue(att.owned_by_session("s1"))
        self.assertFalse(att.owned_by_session("s2"))
        self.assertFalse(att.owned_by_session(None))

    def test_owned_by_session_none_only_matches_none(self):
        att = Attachment(session_id=None)
        self.assertTrue(att.owned_by_session(None))
        self.assertFalse(att.owned_by_session("s1"))


class TestSerializationRoundTrip(unittest.TestCase):

    def test_to_dict_from_dict_round_trip(self):
        att = Attachment(
            session_id="s1", message_id="m1", name="report.pdf",
            mime_type="application/pdf", size=1234,
            storage_reference="Attachments/att_x.pdf",
            source="user_upload", status="available",
            metadata={"checksum": "abc"},
        )
        restored = Attachment.from_dict(att.to_dict())

        self.assertEqual(restored.id, att.id)
        self.assertEqual(restored.session_id, "s1")
        self.assertEqual(restored.message_id, "m1")
        self.assertEqual(restored.mime_type, "application/pdf")
        self.assertEqual(restored.storage_reference, "Attachments/att_x.pdf")
        self.assertEqual(restored.metadata, {"checksum": "abc"})

    def test_from_dict_tolerates_garbage(self):
        restored = Attachment.from_dict({"name": "x", "unknown_key": 1, "size": "oops"})
        self.assertEqual(restored.name, "x")
        self.assertEqual(restored.size, 0)

    def test_from_dict_of_non_mapping_does_not_raise(self):
        restored = Attachment.from_dict(None)  # type: ignore[arg-type]
        self.assertEqual(restored.name, "untitled")


class TestResultTypes(unittest.TestCase):

    def test_validation_result_to_dict(self):
        result = ValidationResult(is_valid=False, issues=[ValidationIssue("size", "terlalu besar.")])
        data = result.to_dict()
        self.assertFalse(data["is_valid"])
        self.assertEqual(data["issues"][0]["field"], "size")
        self.assertEqual(result.messages(), ["size: terlalu besar."])

    def test_attachment_result_to_dict_without_attachment(self):
        result = AttachmentResult(False, errors=["gagal total"])
        data = result.to_dict()
        self.assertFalse(data["success"])
        self.assertIsNone(data["attachment"])
        self.assertEqual(data["errors"], ["gagal total"])


if __name__ == "__main__":
    unittest.main()
