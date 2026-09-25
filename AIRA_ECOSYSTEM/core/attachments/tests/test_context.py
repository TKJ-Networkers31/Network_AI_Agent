import unittest

from core.attachments.context import (
    attachment_to_context_dict,
    attachments_context_section,
    attachments_context_summary_text,
)
from core.attachments.models import Attachment


class TestAttachmentToContextDict(unittest.TestCase):

    def test_only_safe_fields_included(self):
        att = Attachment(
            session_id="s1", message_id="m1", name="a.pdf",
            mime_type="application/pdf", size=10, storage_reference="Attachments/x.pdf",
            source="user_upload", status="available", metadata={"secret": "nope"},
        )
        data = attachment_to_context_dict(att)

        self.assertEqual(data["name"], "a.pdf")
        self.assertEqual(data["storage_reference"], "Attachments/x.pdf")
        self.assertNotIn("metadata", data)
        self.assertNotIn("updated_at", data)

    def test_never_carries_content_key(self):
        att = Attachment(name="a.txt")
        data = attachment_to_context_dict(att)
        self.assertNotIn("content", data)
        self.assertNotIn("bytes", data)


class TestSummaryText(unittest.TestCase):

    def test_lists_available_attachments(self):
        atts = [
            Attachment(name="a.pdf", mime_type="application/pdf", status="available"),
            Attachment(name="b.png", mime_type="image/png", status="available"),
        ]
        text = attachments_context_summary_text(atts)
        self.assertIn("a.pdf", text)
        self.assertIn("b.png", text)

    def test_skips_deleted(self):
        atts = [Attachment(name="a.pdf", status="deleted")]
        text = attachments_context_summary_text(atts)
        self.assertEqual(text, "")

    def test_respects_limit(self):
        atts = [Attachment(name=f"f{i}.txt", status="available") for i in range(5)]
        text = attachments_context_summary_text(atts, limit=2)
        self.assertEqual(len(text.splitlines()), 2)


class TestAttachmentsContextSection(unittest.TestCase):

    def test_returns_none_for_empty_list(self):
        self.assertIsNone(attachments_context_section([]))

    def test_returns_none_when_all_deleted(self):
        atts = [Attachment(name="a.pdf", status="deleted")]
        self.assertIsNone(attachments_context_section(atts))

    def test_data_only_by_default_no_text(self):
        atts = [Attachment(name="a.pdf", status="available")]
        section = attachments_context_section(atts)

        self.assertIn("data", section)
        self.assertNotIn("text", section)
        self.assertEqual(section["data"]["count"], 1)

    def test_text_included_only_when_requested(self):
        atts = [Attachment(name="a.pdf", status="available")]
        section = attachments_context_section(atts, include_text=True)

        self.assertIn("text", section)
        self.assertIn("a.pdf", section["text"])

    def test_data_never_contains_binary_content(self):
        atts = [Attachment(name="a.pdf", status="available", metadata={"raw": b"binary"})]
        section = attachments_context_section(atts)
        self.assertNotIn("raw", section["data"]["items"][0])


if __name__ == "__main__":
    unittest.main()
