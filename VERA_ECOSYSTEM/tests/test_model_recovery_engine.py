"""
tests/test_model_recovery_engine.py — Comprehensive Regression & Resilience Suite
VERA P0 Model Registry, Classification & Provider Recovery Engine.

Verifies:
1. Publisher vs Provider separation (Meta/Google/Mistral share NVIDIA endpoint & circuit breaker).
2. Circuit OPEN fast-fails immediately without network transmission.
3. Same-provider fallback rejection (prevents cascade across models sharing same degraded endpoint).
4. Independent-provider fallback execution (switches cleanly to Ollama or secondary provider).
5. HALF_OPEN single probe behavior (only 1 probe permitted, concurrent requests blocked).
6. HALF_OPEN probe success transitions to CLOSED.
7. HALF_OPEN probe failure transitions back to OPEN with restarted cooldown.
8. Classifier fallback when provider is OPEN (instant heuristic fallback).
9. Capability preservation during fallback (tool-calling requirement enforced).
10. Probe slot auto-expiration (recovers from hung probes).
11. 15-class canonical classification coverage (A through O).
12. Live NVIDIA NIM catalog fidelity (verified exact model IDs).
"""

import time
import pytest
from unittest.mock import MagicMock, patch

from core.model_types import (
    SelectedModel,
    TaskClassification,
    DEFAULT_LABEL,
    MODEL_CLASSIFICATION_CLASSES,
)
from core.model_store import ModelStore
from core.model_policy import ModelPolicy
from core.model_router import ModelRouter
from core.provider_health import (
    ProviderHealthManager,
    CircuitState,
    HealthStatus,
    FailureCategory,
)
from core.task_classifier import TaskClassifier
from agents.rei.provider_client import ProviderClient, call_model


@pytest.fixture
def health_mgr():
    """Provides an isolated ProviderHealthManager."""
    mgr = ProviderHealthManager(failure_threshold=2, cooldown_seconds=0.1)
    with patch("core.provider_health.get_provider_health_manager", return_value=mgr), \
         patch("agents.rei.provider_client.get_provider_health_manager", return_value=mgr):
        yield mgr


@pytest.fixture
def store(tmp_path):
    """Provides an isolated seeded ModelStore."""
    db_file = tmp_path / "recovery_engine_test.db"
    return ModelStore(db_path=db_file, seed=True)


def _find_model(store: ModelStore, model_id: str):
    return next((m for m in store.list_models() if m["model_id"] == model_id), None)


# =========================================================================
# 1. Publisher vs Provider Separation
# =========================================================================

def test_publisher_vs_provider_separation(health_mgr, store):
    """
    Publishers (Google, Meta, MistralAI, OpenAI, NVIDIA) share the single
    'nvidia' provider infrastructure. Degraded provider health affects all models
    routed through that endpoint, regardless of publisher.
    """
    gemma = _find_model(store, "google/gemma-4-31b-it")
    mistral = _find_model(store, "mistralai/mistral-large-4-1t-a52b")
    bolt = _find_model(store, "nvidia/nemotron-3.5-bolt-e4b")

    assert gemma is not None and mistral is not None and bolt is not None
    assert gemma["publisher"] == "google"
    assert mistral["publisher"] == "mistralai"
    assert bolt["publisher"] == "nvidia"

    # All share provider 'nvidia'
    assert gemma["provider"] == "nvidia"
    assert mistral["provider"] == "nvidia"
    assert bolt["provider"] == "nvidia"

    # Tripping nvidia affects all of them
    health_mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "Timeout 1")
    health_mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "Timeout 2")

    assert health_mgr.is_provider_available("nvidia") is False
    assert health_mgr.is_endpoint_available("nvidia", gemma["api_endpoint"]) is False
    assert health_mgr.is_endpoint_available("nvidia", mistral["api_endpoint"]) is False


# =========================================================================
# 2. Circuit OPEN Fast-Fail
# =========================================================================

def test_circuit_open_fast_fails_immediately(health_mgr):
    """
    When circuit is OPEN, calls to ProviderClient fast-fail immediately
    without performing HTTP requests or DNS resolution.
    """
    health_mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "Timeout 1")
    health_mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "Timeout 2")
    assert health_mgr.is_provider_available("nvidia") is False

    t0 = time.time()
    res = ProviderClient.chat("nvidia", "nvidia/nemotron-3.5-bolt-e4b", [{"role": "user", "content": "hi"}])
    duration = time.time() - t0

    assert duration < 0.05, f"Fast-fail took too long: {duration}s"
    assert res.get("error_type") == "circuit_open"
    assert "Circuit breaker OPEN" in res.get("error", "")


# =========================================================================
# 3. Same-Provider Fallback Rejection
# =========================================================================

def test_same_provider_fallback_strictly_rejected(health_mgr, store):
    """
    When nvidia circuit is OPEN, VERA must NOT attempt fallback to other nvidia models
    (such as Gemma 4 or Mistral Large 4). It must cleanly fast-fail with an informative message.
    """
    policy = ModelPolicy(store=store)
    router = ModelRouter(store=store)

    # Disable all non-nvidia models to test single-provider outage
    for m in store.list_models():
        if m["provider"] != "nvidia":
            store.update_model(m["id"], enabled=False)

    health_mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "Timeout 1")
    health_mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "Timeout 2")
    assert health_mgr.is_provider_available("nvidia") is False

    bolt_model = router.select_for_label("general")
    assert bolt_model.provider == "nvidia"

    calls = []
    def mock_chat(provider, model, *args, **kwargs):
        calls.append((provider, model))
        return {"error": "Circuit breaker OPEN", "error_type": "circuit_open"}

    with patch.object(ProviderClient, "chat", side_effect=mock_chat):
        result = call_model(
            messages=[{"role": "user", "content": "Help"}],
            tools=[],
            selected_model=bolt_model,
            policy=policy,
            router=router,
        )

        assert "error" in result
        assert result.get("error_type") == "circuit_open"
        assert "tidak ada provider alternatif independen" in result.get("error", "")
        # Only 1 attempt was made on nvidia; no looping across other nvidia models!
        assert len(calls) <= 1


# =========================================================================
# 4. Independent-Provider Fallback Execution
# =========================================================================

def test_independent_provider_fallback_execution(health_mgr, store):
    """
    When nvidia circuit is OPEN, VERA cleanly falls back to an independent,
    healthy provider (e.g. OpenRouter).
    """
    policy = ModelPolicy(store=store)
    router = ModelRouter(store=store)

    # Register an independent fallback provider
    store.create_model(
        provider="openrouter",
        model_id="qwen/qwen-2.5-7b-instruct",
        display_name="Qwen 2.5 7B Instruct (OpenRouter)",
        label="general",
        custom_id="openrouter_qwen_fallback",
        enabled=True,
    )

    # Trip nvidia circuit
    health_mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "Timeout 1")
    health_mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "Timeout 2")
    assert health_mgr.is_provider_available("nvidia") is False
    assert health_mgr.is_provider_available("openrouter") is True

    selected = router.select_for_label("general")
    assert selected.provider == "nvidia"

    calls = []
    def mock_chat(provider, model, *args, **kwargs):
        calls.append((provider, model))
        if provider == "nvidia":
            return {"error": "Circuit breaker OPEN", "error_type": "circuit_open"}
        return {
            "message": {"role": "assistant", "content": "OpenRouter fallback OK."},
            "usage": {"total_tokens": 15},
        }

    with patch.object(ProviderClient, "chat", side_effect=mock_chat):
        result = call_model(
            messages=[{"role": "user", "content": "Ping"}],
            tools=[],
            selected_model=selected,
            policy=policy,
            router=router,
        )

        assert "error" not in result
        assert result["model"]["provider"] == "openrouter"
        assert result["message"]["content"] == "OpenRouter fallback OK."
        assert len(calls) == 2  # 1 on nvidia (fast-fail) + 1 on openrouter (success)


# =========================================================================
# 5. HALF_OPEN Single Probe Behavior
# =========================================================================

def test_half_open_permits_exactly_one_probe(health_mgr):
    """
    When cooldown elapses and circuit transitions to HALF_OPEN,
    exactly one probe slot is acquired. Concurrent requests are rejected.
    """
    health_mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "Timeout 1")
    health_mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "Timeout 2")
    assert health_mgr.is_provider_available("nvidia") is False

    # Wait for cooldown (0.1s in fixture)
    time.sleep(0.12)

    # Read-only query reports available (cooldown elapsed)
    assert health_mgr.is_provider_available("nvidia") is True

    # First caller acquires probe slot
    acquired_1 = health_mgr.acquire_probe_slot("nvidia")
    assert acquired_1 is True

    # State is now HALF_OPEN with probe in flight
    rec = health_mgr.get_record("nvidia")
    assert rec.circuit_state == CircuitState.HALF_OPEN
    assert rec.probe_in_flight is True

    # Concurrent second caller is rejected
    acquired_2 = health_mgr.acquire_probe_slot("nvidia")
    assert acquired_2 is False

    # Read-only query now returns False while probe is in flight
    assert health_mgr.is_provider_available("nvidia") is False


# =========================================================================
# 6. HALF_OPEN Probe Success Transitions to CLOSED
# =========================================================================

def test_half_open_probe_success_resets_circuit(health_mgr):
    """
    When the single probe succeeds in HALF_OPEN, circuit transitions back to CLOSED
    and failure counter resets to 0.
    """
    health_mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "Timeout 1")
    health_mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "Timeout 2")

    time.sleep(0.12)
    assert health_mgr.acquire_probe_slot("nvidia") is True

    # Successful probe
    health_mgr.record_success("nvidia", latency=0.25, model_id="nvidia/nemotron-3.5-bolt-e4b")

    rec = health_mgr.get_record("nvidia")
    assert rec.circuit_state == CircuitState.CLOSED
    assert rec.status == HealthStatus.HEALTHY
    assert rec.consecutive_failures == 0
    assert rec.probe_in_flight is False
    assert health_mgr.is_provider_available("nvidia") is True


# =========================================================================
# 7. HALF_OPEN Probe Failure Reopens Circuit with Restarted Cooldown
# =========================================================================

def test_half_open_probe_failure_reopens_circuit(health_mgr):
    """
    When the probe in HALF_OPEN fails, circuit immediately transitions back to OPEN
    with a new cooldown timestamp.
    """
    health_mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "Timeout 1")
    health_mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "Timeout 2")

    time.sleep(0.12)
    assert health_mgr.acquire_probe_slot("nvidia") is True

    # Probe fails
    t_before = time.time()
    health_mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "Probe timed out")

    rec = health_mgr.get_record("nvidia")
    assert rec.circuit_state == CircuitState.OPEN
    assert rec.status == HealthStatus.UNAVAILABLE
    assert rec.probe_in_flight is False
    assert rec.circuit_opened_at >= t_before
    assert health_mgr.is_provider_available("nvidia") is False


# =========================================================================
# 8. Classifier Decoupling & Instant Heuristic Fallback
# =========================================================================

def test_classifier_instant_heuristic_when_provider_open(health_mgr, store):
    """
    When the general model provider circuit is OPEN, TaskClassifier must NOT
    hang or attempt network requests. It immediately falls back to deterministic heuristics.
    """
    router = ModelRouter(store=store)
    classifier = TaskClassifier(router=router)

    health_mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "Timeout 1")
    health_mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "Timeout 2")
    assert health_mgr.is_provider_available("nvidia") is False

    t0 = time.time()
    result = classifier.classify("Tolong buatkan topologi OSPF area 0 pada MikroTik ether1")
    elapsed = time.time() - t0

    assert elapsed < 0.05, f"Classifier heuristic took too long: {elapsed}s"
    assert result.primary_label == "networking"
    assert result.task_category in ("routing_protocols", "network_topology", "network_configuration")
    assert result.requires_tools is True


# =========================================================================
# 9. Capability Preservation During Fallback
# =========================================================================

def test_capability_preservation_during_fallback(health_mgr, store):
    """
    When tools are required, candidates lacking tool calling capability must be skipped.
    """
    policy = ModelPolicy(store=store)
    bolt = _find_model(store, "nvidia/nemotron-3.5-bolt-e4b")
    assert bolt is not None
    failed = SelectedModel.from_row(bolt)

    # Request requires tool calling
    fallback = policy.on_provider_failure(failed, "timeout", required_capabilities=["supports_tool_calling"])
    assert fallback is not None
    assert fallback.supports_tool_calling is True


# =========================================================================
# 10. Probe Slot Auto-Expiration
# =========================================================================

def test_probe_slot_auto_expiration(health_mgr):
    """
    If a probe slot is acquired in HALF_OPEN but the thread hangs or terminates
    without recording success or failure, the lock automatically expires after 15s.
    """
    health_mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "Timeout 1")
    health_mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "Timeout 2")

    time.sleep(0.12)
    assert health_mgr.acquire_probe_slot("nvidia") is True

    rec = health_mgr.get_record("nvidia")
    assert rec.probe_in_flight is True

    # Simulate 16 seconds having elapsed for hung probe
    rec.probe_started_at = time.time() - 16.0

    # Next check should detect probe expiration and allow retry
    assert health_mgr.is_provider_available("nvidia") is True
    assert health_mgr.acquire_probe_slot("nvidia") is True


# =========================================================================
# 11. 15 Canonical Classifications Coverage (A through O)
# =========================================================================

def test_canonical_15_classes_seeded(store):
    """
    Verifies all 15 canonical classifications (A through O) are populated
    in the database with verified live models.
    """
    models = store.list_models()
    classes_found = set()
    for m in models:
        classification = m.get("classification") or {}
        cls_letter = classification.get("class")
        if cls_letter:
            classes_found.add(cls_letter)

    expected_classes = set(MODEL_CLASSIFICATION_CLASSES.keys())
    missing = expected_classes - classes_found
    assert not missing, f"Missing canonical model classes: {missing}"


# =========================================================================
# 12. Verified Exact NVIDIA NIM Model IDs
# =========================================================================

def test_nvidia_nim_model_ids_fidelity(store):
    """
    Verifies that active seeded NVIDIA NIM models match the verified live catalog.
    No obsolete or hallucinated model IDs.
    """
    nvidia_models = [m for m in store.list_models() if m["provider"] == "nvidia"]
    verified_ids = {
        "nvidia/nemotron-3.5-bolt-e4b",
        "mistralai/mistral-large-4-1t-a52b",
        "google/gemma-4-31b-it",
        "openai/gpt-oss-20b",
        "nvidia/nemotron-3.5-super-vl-120b-a12b",
        "z-ai/glm-5.3-flash",
        "nvidia/cosmos-reason2-8b",
        "poolside/laguna-xs-2.1",
        "moonshotai/kimi-k2.6",
        "minimaxai/minimax-m3.1-flash",
        "deepseek-ai/deepseek-coder-6.7b-instruct",
        "nvidia/nemotron-3-ultra-550b-a55b",
        "nvidia/nemotron-3.5-lightning-30b-a3b",
        "meta/llama-3.2-90b-vision-instruct",
        "deepseek-ai/deepseek-v4.1-flash",
        "meta/muse-glimmer-30b",
        "nvidia/nemotron-parse-2.0",
        "google/deplot",
        "stepfun-ai/step-5-preview",
        "nvidia/nemotron-3-embed-1b",
        "nvidia/nemotron-3.5-embed-1b",
        "snowflake/arctic-embed-l",
        "nvidia/embed-qa-4",
        "nvidia/nemotron-4-340b-reward",
        "nvidia/riva-translate-4b-instruct-v2",
        "nvidia/riva-translate-4b-instruct",
        "nvidia/nemotron-3.5-content-safety",
        "nvidia/llama-3.1-nemoguard-8b-content-safety",
        "nvidia/ai-synthetic-video-detector",
        "nvidia/ising-calibration-1.5-31b",
        "writer/palmyra-fin-70b-32k",
    }

    for m in nvidia_models:
        assert m["model_id"] in verified_ids, f"Model ID '{m['model_id']}' is not in verified NVIDIA NIM catalog!"
