"""
AIRA OS — Stage 7 AI Provider Reliability & Fallback Test Suite (NEW-01).

Verifies:
1. Multi-provider fallback chain (primary failure -> fallback candidate).
2. Fallback candidate failure -> next candidate in chain.
3. All-provider failure -> clean structured error response.
4. Fast timeout handling (prevents unbounded hanging).
5. Cancellation event handling (clean abort without hung runtime).
6. Deterministic Task Classifier fallback (offline / rate-limited / error resilience).
7. Auto-memory async failure isolation (zero stream disruption on provider failure).
"""

import threading
import time
from unittest.mock import MagicMock, patch
import pytest

from agents.rei.provider_client import call_model, TRANSIENT_ERROR_TYPES, DEFAULT_LLM_TIMEOUT
from core.task_classifier import classify, TaskClassifier
from core.model_types import SelectedModel, TaskClassification
from agents.rei.auto_extract import extract_and_save_facts_async


def test_01_transient_error_types_includes_timeout():
    """Validates that timeout is classified as transient to allow bounded retries."""
    assert "timeout" in TRANSIENT_ERROR_TYPES
    assert "rate_limit" in TRANSIENT_ERROR_TYPES
    assert "connection" in TRANSIENT_ERROR_TYPES


def test_02_default_llm_timeout_bounded():
    """Validates that default LLM timeout is configured and bounded."""
    assert DEFAULT_LLM_TIMEOUT > 0
    assert DEFAULT_LLM_TIMEOUT <= 60.0


def test_03_primary_failure_fallback_chain_success():
    """Verifies that when primary model fails, call_model attempts the fallback chain and succeeds."""
    with patch("agents.rei.provider_client._attempt") as mock_attempt:
        mock_attempt.side_effect = [
            {"error": "404 Model Not Found", "error_type": "not_found"},
            {
                "message": {"role": "assistant", "content": "Rute BGP berhasil dianalisis."},
                "usage": {"total_tokens": 150},
            },
        ]
        res = call_model([{"role": "user", "content": "Analisis rute BGP"}], tools=[])
        assert "error" not in res
        assert res["message"]["content"] == "Rute BGP berhasil dianalisis."
        assert "model" in res
        assert mock_attempt.call_count == 2


def test_04_fallback_chain_continues_on_candidate_failure():
    """Verifies fallback chain tries candidate 2 when candidate 1 also fails."""
    with patch("agents.rei.provider_client._attempt") as mock_attempt:
        mock_attempt.side_effect = [
            {"error": "Primary 500 Internal Error", "error_type": "server_error"},
            {"error": "Candidate 1 404 Not Found", "error_type": "not_found"},
            {
                "message": {"role": "assistant", "content": "Jawaban dari fallback candidate 2."},
                "usage": {"total_tokens": 88},
            },
        ]
        res = call_model([{"role": "user", "content": "Tampilkan konfigurasi VLAN"}], tools=[])
        assert "error" not in res
        assert res["message"]["content"] == "Jawaban dari fallback candidate 2."
        assert mock_attempt.call_count == 3


def test_05_all_providers_failure_returns_honest_error():
    """Verifies that when all providers fail, a clean structured error is returned."""
    with patch("agents.rei.provider_client._attempt") as mock_attempt:
        mock_attempt.return_value = {"error": "Connection refused", "error_type": "connection"}
        res = call_model([{"role": "user", "content": "Cek status router"}], tools=[])
        assert "error" in res
        assert res["error"] == "Connection refused"


def test_06_cancellation_aborts_without_retry_or_fallback():
    """Verifies cancellation event immediately halts execution without falling back."""
    cancel_ev = threading.Event()
    cancel_ev.set()
    with patch("agents.rei.provider_client._attempt") as mock_attempt:
        mock_attempt.return_value = {"error": "Request cancelled", "error_type": "cancelled", "cancelled": True}
        res = call_model([{"role": "user", "content": "Jalankan diagnosa"}], tools=[], cancel_event=cancel_ev)
        assert res.get("cancelled") is True
        assert res.get("error_type") == "cancelled"
        assert mock_attempt.call_count == 1


def test_07_deterministic_task_classifier_heuristic_fallback():
    """Verifies task classifier heuristic fallback routes queries accurately when provider is down."""
    # Force provider error in classifier
    with patch("core.task_classifier.TaskClassifier._classify_with_llm", side_effect=Exception("Provider unreachable")):
        # Networking
        c_net = classify("Bagaimana cara membuat bridge VLAN filtering di Mikrotik RouterOS?")
        assert c_net.primary_label == "networking"
        assert c_net.confidence >= 0.75
        assert c_net.requires_tools is True

        # Coding
        c_code = classify("def calculate_hash(data: bytes) -> str:\n    import hashlib\n    return hashlib.sha256(data).hexdigest()")
        assert c_code.primary_label == "coding"
        assert c_code.confidence >= 0.75

        # Automation
        c_auto = classify("Jadwalkan cron backup konfigurasi router setiap minggu")
        assert c_auto.primary_label == "automation"

        # Vision
        c_vis = classify("Analisis gambar diagram topologi datacenter ini")
        assert c_vis.primary_label == "vision"
        assert c_vis.requires_vision is True

        # Voice
        c_voc = classify("Aktifkan suara dan dengarkan perintah suara")
        assert c_voc.primary_label == "voice"
        assert c_voc.requires_voice is True

        # General
        c_gen = classify("Halo, ceritakan puisi tentang langit sore")
        assert c_gen.primary_label == "general"


def test_08_auto_memory_failure_isolation():
    """Verifies auto-memory extraction failure in background thread does not raise or disrupt."""
    with patch("agents.rei.auto_extract.call_model") as mock_call:
        mock_call.return_value = {"error": "Provider quota exceeded", "error_type": "rate_limit"}
        # Should execute cleanly without raising exception
        extract_and_save_facts_async("Saya bekerja sebagai Network Engineer di ISP", "Baik, saya catat.", user_id="test_user_777")
        time.sleep(0.1)
