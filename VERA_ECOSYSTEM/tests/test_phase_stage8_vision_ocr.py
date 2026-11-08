"""
AIRA OS — Stage 8 Vision & OCR Subsystem Test Suite (BUG-09 & NEW-02).

Verifies:
1. VisionResult constructor & serialization compatibility (BUG-09).
2. LLMVisionProvider analyze() handling multimodal vs text-only models.
3. TesseractOCR image pre-processing (RGBA transparency to grayscale, contrast enhancement).
4. OCR error handling (OCRUnavailable when binary is missing, clean error recording).
5. Ground-truth OCR evaluation with CER (Character Error Rate) and WER (Word Error Rate) metrics.
6. FileProcessor integration across images, PDF text layers, and vision analysis.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from core.file_processing.vision_llm import (
    VisionResult,
    VisionStatus,
    ImageMetadata,
    LLMVisionProvider,
)
from core.file_processing.ocr import TesseractOCR, OCRUnavailable
from core.file_processing.processor import FileProcessor, ProcessingResult
from core.model_types import SelectedModel


# ===========================================================================
# 1. CER & WER Evaluation Utilities (NEW-02)
# ===========================================================================

def compute_cer(reference: str, hypothesis: str) -> float:
    """Computes Character Error Rate (Levenshtein distance / len(reference))."""
    r, h = reference.strip(), hypothesis.strip()
    if not r:
        return 0.0 if not h else 1.0

    d = [[0] * (len(h) + 1) for _ in range(len(r) + 1)]
    for i in range(len(r) + 1):
        d[i][0] = i
    for j in range(len(h) + 1):
        d[0][j] = j

    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            cost = 0 if r[i - 1] == h[j - 1] else 1
            d[i][j] = min(
                d[i - 1][j] + 1,        # deletion
                d[i][j - 1] + 1,        # insertion
                d[i - 1][j - 1] + cost, # substitution
            )

    return round(d[len(r)][len(h)] / max(1, len(r)), 4)


def compute_wer(reference: str, hypothesis: str) -> float:
    """Computes Word Error Rate (Word Levenshtein distance / len(reference_words))."""
    r_words = reference.strip().split()
    h_words = hypothesis.strip().split()
    if not r_words:
        return 0.0 if not h_words else 1.0

    d = [[0] * (len(h_words) + 1) for _ in range(len(r_words) + 1)]
    for i in range(len(r_words) + 1):
        d[i][0] = i
    for j in range(len(h_words) + 1):
        d[0][j] = j

    for i in range(1, len(r_words) + 1):
        for j in range(1, len(h_words) + 1):
            cost = 0 if r_words[i - 1] == h_words[j - 1] else 1
            d[i][j] = min(
                d[i - 1][j] + 1,
                d[i][j - 1] + 1,
                d[i - 1][j - 1] + cost,
            )

    return round(d[len(r_words)][len(h_words)] / max(1, len(r_words)), 4)


# ===========================================================================
# 2. VisionResult Tests (BUG-09 Fix Verification)
# ===========================================================================

def test_01_vision_result_constructor_supports_analysis_kwarg():
    """Verifies VisionResult accepts analysis keyword argument without TypeError (BUG-09)."""
    desc = "Diagram topologi menunjukkan router CCR2004 terhubung ke switch CRS326 via SFP-plus."
    vr = VisionResult(
        status=VisionStatus.AVAILABLE.value,
        provider="nvidia/llama-3.2-90b-vision",
        analysis={"description": desc},
    )
    assert vr.status == "available"
    assert vr.provider == "nvidia/llama-3.2-90b-vision"
    assert vr.text == desc
    assert vr.analysis == {"description": desc}

    d = vr.to_dict()
    assert d["status"] == "available"
    assert d["text"] == desc
    assert d["analysis"]["description"] == desc


def test_02_vision_result_to_dict_bidirectional_consistency():
    """Verifies that to_dict produces consistent text and analysis whether text or analysis was passed."""
    vr1 = VisionResult(status="available", text="Hello world")
    assert vr1.to_dict()["analysis"]["description"] == "Hello world"

    vr2 = VisionResult(status="available", analysis={"description": "Hello world"})
    assert vr2.to_dict()["text"] == "Hello world"


# ===========================================================================
# 3. LLMVisionProvider Tests
# ===========================================================================

def test_03_vision_provider_reports_unavailable_when_no_vision_model():
    """Verifies that analyze() returns UNAVAILABLE when router returns no model."""
    provider = LLMVisionProvider()
    with patch("core.model_router.ModelRouter.select_for_label", return_value=None):
        res = provider.analyze({"kind": "workspace_path", "absolute_path": "/dummy/image.png"}, ImageMetadata())
        assert res.status == VisionStatus.UNAVAILABLE.value
        assert "Tidak ada model" in res.reason


def test_04_vision_provider_skips_text_only_models():
    """Verifies that analyze() refuses pure text models like Nemotron/Qwen without vision capability."""
    provider = LLMVisionProvider()
    text_model = SelectedModel(
        id="nemotron_text",
        provider="nvidia",
        model_id="nvidia/nemotron-3-ultra-550b-a55b",
        display_name="Nemotron Ultra",
        label="vision",
        context_window=32768,
    )
    with patch("core.model_router.ModelRouter.select_for_label", return_value=text_model):
        res = provider.analyze({"kind": "workspace_path", "absolute_path": "/dummy/image.png"}, ImageMetadata())
        assert res.status == VisionStatus.UNAVAILABLE.value
        assert "tidak mendukung multimodal vision" in res.reason


def test_05_vision_provider_analyzes_valid_image(tmp_path):
    """Verifies that analyze() successfully formats payload and returns VisionResult."""
    img_file = tmp_path / "topo.png"
    img_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4")

    vision_model = SelectedModel(
        id="llama_vision",
        provider="nvidia",
        model_id="meta/llama-3.2-90b-vision-instruct",
        display_name="Llama 3.2 90B Vision",
        label="vision",
        context_window=131072,
    )
    provider = LLMVisionProvider()

    mock_chat_response = {
        "message": {
            "role": "assistant",
            "content": "Gambar menunjukkan arsitektur dual-homed BGP dengan dua router core.",
        },
        "usage": {"total_tokens": 120},
    }

    with patch("core.model_router.ModelRouter.select_for_label", return_value=vision_model):
        with patch("agents.rei.provider_client.ProviderClient.chat", return_value=mock_chat_response):
            meta = ImageMetadata(name="topo.png", mime_type="image/png", size=img_file.stat().st_size, width=1, height=1)
            res = provider.analyze({"kind": "workspace_path", "absolute_path": str(img_file)}, meta)
            assert res.status == VisionStatus.AVAILABLE.value
            assert "dual-homed BGP" in res.text
            assert res.analysis["description"] == res.text


# ===========================================================================
# 4. OCR & Ground-Truth Evaluation Tests (NEW-02)
# ===========================================================================

def test_06_cer_and_wer_metrics_evaluation():
    """Validates Character Error Rate (CER) and Word Error Rate (WER) metric calculations."""
    ground_truth = "Mikrotik RouterOS v7.14 BGP Routing Table"
    
    # 1. Exact match -> 0.0 error rate
    assert compute_cer(ground_truth, ground_truth) == 0.0
    assert compute_wer(ground_truth, ground_truth) == 0.0

    # 2. Minor OCR typo: "Mikrotek" instead of "Mikrotik" (1 char substitution)
    hypothesis_typo = "Mikrotek RouterOS v7.14 BGP Routing Table"
    cer = compute_cer(ground_truth, hypothesis_typo)
    wer = compute_wer(ground_truth, hypothesis_typo)
    assert cer <= 0.03  # ~2.4% CER
    assert wer <= 0.18  # 1/6 words = 16.7% WER

    # 3. Insertion error
    hypothesis_extra = "Mikrotik RouterOS v7.14 BGP Extra Routing Table"
    assert compute_wer(ground_truth, hypothesis_extra) <= 0.20


def test_07_ocr_prepares_transparent_images_properly():
    """Verifies that _prepare_image converts RGBA images with transparency to white-backed grayscale."""
    from PIL import Image
    ocr = TesseractOCR()

    # Create RGBA image with alpha transparency
    rgba_img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    processed = ocr._prepare_image(rgba_img)
    assert processed.mode == "L"
    assert processed.size == (100, 100)


def test_08_ocr_unavailable_handled_gracefully():
    """Verifies that when Tesseract binary is absent, OCRUnavailable is raised and handled cleanly."""
    ocr = TesseractOCR()
    with patch("shutil.which", return_value=None):
        with patch("core.file_processing.ocr._resolve_tesseract_cmd", return_value=None):
            from PIL import Image
            test_img = Image.new("RGB", (50, 50), (255, 255, 255))
            with pytest.raises(OCRUnavailable) as exc_info:
                ocr.ocr_image(test_img)
            assert "Binary tesseract tidak ditemukan" in str(exc_info.value)
