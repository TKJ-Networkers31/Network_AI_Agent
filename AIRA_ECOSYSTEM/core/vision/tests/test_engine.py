import tempfile
import unittest
from pathlib import Path

from core.attachments.engine import AttachmentEngine
from core.attachments.store import AttachmentStore
from core.vision.engine import ImageVisionEngine
from core.vision.models import ImageMetadata, VisionResult, VisionStatus


def _always_true(_session_id):
    return True


class FakeAvailableProvider:
    name = "fake"

    def analyze(self, reference, metadata):
        return VisionResult(status="available", provider=self.name, analysis={"objects": []})


class FakeBoomProvider:
    name = "boom"

    def analyze(self, reference, metadata):
        raise RuntimeError("provider down")


class ImageVisionEngineTestBase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace_root = Path(self.tmp.name) / "workspace"
        self.workspace_root.mkdir(parents=True, exist_ok=True)

        self.attachment_store = AttachmentStore(db_path=Path(self.tmp.name) / "attachments_test.db")
        self.attachment_engine = AttachmentEngine(
            store=self.attachment_store,
            resolve_path=lambda rel: self.workspace_root / rel,
            workspace_exists=lambda rel: (self.workspace_root / rel).exists(),
            session_lookup=_always_true,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _png_bytes(self, width=64, height=32):
        import struct
        sig = b"\x89PNG\r\n\x1a\n"
        ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
        return sig + struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + b"\x00\x00\x00\x00"


class TestCreateImageAttachment(ImageVisionEngineTestBase):

    def setUp(self):
        super().setUp()
        self.engine = ImageVisionEngine(attachment_engine=self.attachment_engine)

    def test_upload_image_success_with_dimensions(self):
        result = self.engine.create_image_attachment(
            content=self._png_bytes(64, 32), name="photo.png", session_id="s1",
        )
        self.assertTrue(result.success, result.errors)
        self.assertEqual(result.attachment.metadata["image"], {"width": 64, "height": 32})
        self.assertNotIn("capture_type", result.attachment.metadata)

    def test_upload_screenshot_tags_capture_type(self):
        result = self.engine.create_image_attachment(
            content=self._png_bytes(), name="shot.png", session_id="s1", is_screenshot=True,
        )
        self.assertTrue(result.success, result.errors)
        self.assertEqual(result.attachment.metadata["capture_type"], "screenshot")

    def test_rejects_non_image_mime(self):
        result = self.engine.create_image_attachment(
            content=b"%PDF-1.4", name="doc.pdf", session_id="s1",
        )
        self.assertFalse(result.success)
        self.assertIsNone(result.attachment)

    def test_rejects_non_bytes_content(self):
        result = self.engine.create_image_attachment(
            content="not bytes", name="photo.png", session_id="s1",  # type: ignore[arg-type]
        )
        self.assertFalse(result.success)

    def test_unparseable_header_still_creates_attachment_with_null_dimensions(self):
        result = self.engine.create_image_attachment(
            content=b"\x89PNG\r\n\x1a\ncorrupt", name="broken.png", session_id="s1",
        )
        self.assertTrue(result.success, result.errors)
        self.assertEqual(result.attachment.metadata["image"], {"width": None, "height": None})


class TestGetImageMetadata(ImageVisionEngineTestBase):

    def setUp(self):
        super().setUp()
        self.engine = ImageVisionEngine(attachment_engine=self.attachment_engine)

    def test_returns_metadata_for_image_attachment(self):
        created = self.engine.create_image_attachment(
            content=self._png_bytes(100, 50), name="a.png", session_id="s1",
        )
        meta = self.engine.get_image_metadata(created.attachment.id, session_id="s1")

        self.assertIsInstance(meta, ImageMetadata)
        self.assertEqual((meta.width, meta.height), (100, 50))

    def test_returns_none_for_missing_attachment(self):
        self.assertIsNone(self.engine.get_image_metadata("does-not-exist"))


class TestGetVisualContext(ImageVisionEngineTestBase):

    def test_default_provider_reports_unavailable(self):
        engine = ImageVisionEngine(attachment_engine=self.attachment_engine)
        created = engine.create_image_attachment(content=self._png_bytes(), name="a.png", session_id="s1")

        packet = engine.get_visual_context(created.attachment.id, session_id="s1")

        self.assertIsNotNone(packet)
        self.assertEqual(packet["data"]["vision"]["status"], VisionStatus.UNAVAILABLE.value)

    def test_injected_available_provider_is_reflected_honestly(self):
        engine = ImageVisionEngine(
            attachment_engine=self.attachment_engine, vision_provider=FakeAvailableProvider(),
        )
        created = engine.create_image_attachment(content=self._png_bytes(), name="a.png", session_id="s1")

        packet = engine.get_visual_context(created.attachment.id, session_id="s1")

        self.assertEqual(packet["data"]["vision"]["status"], "available")
        self.assertEqual(packet["data"]["vision"]["provider"], "fake")

    def test_provider_exception_is_reported_as_unavailable_not_raised(self):
        engine = ImageVisionEngine(
            attachment_engine=self.attachment_engine, vision_provider=FakeBoomProvider(),
        )
        created = engine.create_image_attachment(content=self._png_bytes(), name="a.png", session_id="s1")

        packet = engine.get_visual_context(created.attachment.id, session_id="s1")

        self.assertEqual(packet["data"]["vision"]["status"], VisionStatus.UNAVAILABLE.value)
        self.assertEqual(packet["data"]["vision"]["provider"], "boom")

    def test_returns_none_for_non_image_attachment(self):
        engine = ImageVisionEngine(attachment_engine=self.attachment_engine)
        created = self.attachment_engine.create_from_upload(
            content=b"%PDF-1.4", name="doc.pdf", session_id="s1",
        )
        self.assertIsNone(engine.get_visual_context(created.attachment.id, session_id="s1"))

    def test_skips_provider_when_invoke_provider_false(self):
        engine = ImageVisionEngine(
            attachment_engine=self.attachment_engine, vision_provider=FakeBoomProvider(),
        )
        created = engine.create_image_attachment(content=self._png_bytes(), name="a.png", session_id="s1")

        # invoke_provider=False -> provider (yang akan raise) tidak pernah dipanggil.
        packet = engine.get_visual_context(created.attachment.id, session_id="s1", invoke_provider=False)
        self.assertEqual(packet["data"]["vision"]["status"], VisionStatus.UNAVAILABLE.value)

    def test_respects_session_ownership(self):
        engine = ImageVisionEngine(attachment_engine=self.attachment_engine)
        created = engine.create_image_attachment(content=self._png_bytes(), name="a.png", session_id="s1")

        self.assertIsNone(engine.get_visual_context(created.attachment.id, session_id="s2"))


if __name__ == "__main__":
    unittest.main()