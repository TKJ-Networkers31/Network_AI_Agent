import unittest

from core.attachments.models import Attachment
from core.vision.context import (
    build_visual_context_packet,
    image_metadata_from_attachment,
    visual_placeholder_text,
)
from core.vision.models import VisionResult, VisionStatus


def _image_attachment(**overrides):
    defaults = dict(
        name="screenshot.png", mime_type="image/png", size=2048,
        storage_reference="Attachments/att_x.png", status="available",
        metadata={"image": {"width": 1280, "height": 720}, "capture_type": "screenshot"},
    )
    defaults.update(overrides)
    return Attachment(**defaults)


class TestImageMetadataFromAttachment(unittest.TestCase):

    def test_extracts_dimensions_and_screenshot_flag(self):
        meta = image_metadata_from_attachment(_image_attachment())
        self.assertEqual((meta.width, meta.height), (1280, 720))
        self.assertTrue(meta.is_screenshot)
        self.assertTrue(meta.has_dimensions)

    def test_missing_image_metadata_yields_none_dimensions(self):
        att = _image_attachment(metadata={})
        meta = image_metadata_from_attachment(att)
        self.assertIsNone(meta.width)
        self.assertFalse(meta.has_dimensions)
        self.assertFalse(meta.is_screenshot)


class TestBuildVisualContextPacket(unittest.TestCase):

    def test_returns_none_for_non_image_attachment(self):
        att = Attachment(name="doc.pdf", mime_type="application/pdf", status="available")
        self.assertIsNone(build_visual_context_packet(att))

    def test_returns_none_for_deleted_attachment(self):
        att = _image_attachment(status="deleted")
        self.assertIsNone(build_visual_context_packet(att))

    def test_data_only_by_default_no_text(self):
        packet = build_visual_context_packet(_image_attachment())
        self.assertIn("data", packet)
        self.assertNotIn("text", packet)
        self.assertEqual(packet["data"]["image"]["width"], 1280)
        self.assertEqual(packet["data"]["vision"]["status"], VisionStatus.UNAVAILABLE.value)

    def test_defaults_to_unavailable_vision_when_none_given(self):
        packet = build_visual_context_packet(_image_attachment(), vision=None)
        self.assertEqual(packet["data"]["vision"]["status"], VisionStatus.UNAVAILABLE.value)

    def test_uses_supplied_vision_result(self):
        vision = VisionResult(status="unavailable", provider="stub", reason="test")
        packet = build_visual_context_packet(_image_attachment(), vision=vision)
        self.assertEqual(packet["data"]["vision"]["provider"], "stub")

    def test_text_included_only_when_requested(self):
        packet = build_visual_context_packet(_image_attachment(), include_text=True)
        self.assertIn("text", packet)
        self.assertIn("screenshot.png", packet["text"])

    def test_never_carries_raw_bytes(self):
        packet = build_visual_context_packet(_image_attachment())
        flattened = str(packet)
        self.assertNotIn("content", packet["data"])
        self.assertNotIn(b"\x89PNG".decode("latin1"), flattened)


class TestVisualPlaceholderText(unittest.TestCase):

    def test_unknown_dimensions_labeled_explicitly(self):
        meta = image_metadata_from_attachment(_image_attachment(metadata={}))
        text = visual_placeholder_text(meta, VisionResult())
        self.assertIn("dimensi tidak diketahui", text)


if __name__ == "__main__":
    unittest.main()