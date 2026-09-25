import unittest

from core.vision.models import ImageMetadata, VisionResult, VisionStatus
from core.vision.provider import UnavailableVisionProvider, get_vision_provider


class TestUnavailableVisionProvider(unittest.TestCase):

    def test_always_returns_unavailable(self):
        provider = UnavailableVisionProvider()
        result = provider.analyze(reference={"kind": "workspace_path"}, metadata=ImageMetadata())

        self.assertEqual(result.status, VisionStatus.UNAVAILABLE.value)
        self.assertIsNone(result.analysis)
        self.assertIsNotNone(result.reason)

    def test_returns_unavailable_even_with_no_reference(self):
        provider = UnavailableVisionProvider()
        result = provider.analyze(reference=None, metadata=ImageMetadata(name="a.png"))
        self.assertEqual(result.status, VisionStatus.UNAVAILABLE.value)


class TestGetVisionProvider(unittest.TestCase):

    def test_singleton_is_unavailable_provider(self):
        provider = get_vision_provider()
        self.assertIsInstance(provider, UnavailableVisionProvider)

    def test_result_never_fabricates_available_status(self):
        # Kontrak: tidak ada jalur di modul ini yang membuat VisionResult
        # AVAILABLE tanpa provider ASLI (bukan default) melakukannya.
        provider = get_vision_provider()
        result = provider.analyze(None, ImageMetadata())
        self.assertNotEqual(result.status, VisionStatus.AVAILABLE.value)


class TestVisionResultSerialization(unittest.TestCase):

    def test_analysis_forced_none_when_not_available(self):
        result = VisionResult(status="unavailable", analysis={"caption": "seharusnya hilang"})
        self.assertIsNone(result.analysis)

    def test_to_dict_round_trip_shape(self):
        result = VisionResult(status="unavailable", provider="none", reason="tidak ada provider")
        data = result.to_dict()
        self.assertEqual(data["status"], "unavailable")
        self.assertIsNone(data["analysis"])

    def test_unknown_status_coerced_to_unavailable(self):
        result = VisionResult(status="not-a-real-status")
        self.assertEqual(result.status, VisionStatus.UNAVAILABLE.value)


if __name__ == "__main__":
    unittest.main()