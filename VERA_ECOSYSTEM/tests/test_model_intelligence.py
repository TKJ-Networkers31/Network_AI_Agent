"""
VERA Model Intelligence Architecture & Provider Routing Test Suite
Covers Scenarios A, B, C, D specified in Section 12.5 of P0 Directive:
- Scenario A: Normal routing and model execution
- Scenario B: Upstream Circuit Breaker fast-fail & prevention of same-provider fallback cascade (P0 Defect Fix)
- Scenario C: Model-specific 404 non-degrading error isolation
- Scenario D: Capability-aware selection (tool calling, vision, long-context)
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from core.model_types import SelectedModel, TaskClassification, DEFAULT_LABEL
from core.model_store import ModelStore
from core.model_policy import ModelPolicy
from core.model_router import ModelRouter
from core.provider_health import (
    ProviderHealthManager,
    CircuitState,
    HealthStatus,
    FailureCategory,
)
from agents.rei.provider_client import ProviderClient, call_model


@pytest.fixture
def clean_health_mgr():
    """Returns a fresh ProviderHealthManager instance for test isolation."""
    mgr = ProviderHealthManager(failure_threshold=2, cooldown_seconds=10.0)
    with patch("core.provider_health.get_provider_health_manager", return_value=mgr), \
         patch("agents.rei.provider_client.get_provider_health_manager", return_value=mgr):
        yield mgr


@pytest.fixture
def mock_store(tmp_path):
    """Provides an isolated ModelStore in a temporary directory."""
    db_file = tmp_path / "test_model_router.db"
    store = ModelStore(db_path=db_file, seed=True)
    return store


# =========================================================================
# SCENARIO A: Normal Operating Conditions
# =========================================================================

def test_scenario_a_normal_operating_conditions(clean_health_mgr, mock_store):
    """
    Scenario A: User submits query.
    ModelRouter selects default general model (Nemotron 3.5 Bolt).
    ProviderClient executes successfully, records latency and success telemetry.
    """
    router = ModelRouter(store=mock_store)
    policy = ModelPolicy(store=mock_store)

    selected = router.select_for_label("general")
    assert selected is not None
    assert selected.provider == "nvidia"
    assert selected.model_id == "nvidia/nemotron-3.5-bolt-e4b"
    assert selected.supports_tool_calling is True

    # Mock successful LLM response
    fake_response = {
        "message": {"role": "assistant", "content": "Interface VLAN 100 configured successfully."},
        "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
    }

    with patch.object(ProviderClient, "chat", return_value=fake_response):
        result = call_model(
            messages=[{"role": "user", "content": "Konfigurasi VLAN 100"}],
            tools=[],
            selected_model=selected,
            policy=policy,
            router=router,
        )

        assert "error" not in result
        assert result["message"]["content"] == "Interface VLAN 100 configured successfully."
        assert result["model"]["model_id"] == "nvidia/nemotron-3.5-bolt-e4b"
        assert result["usage"]["total_tokens"] == 70


# =========================================================================
# SCENARIO B: Upstream Endpoint Read Timeout & Provider Cascade Prevention (P0 DEFECT)
# =========================================================================

def test_scenario_b_circuit_breaker_prevents_same_provider_cascade(clean_health_mgr, mock_store):
    """
    Scenario B (CRITICAL P0 DEFECT VERIFICATION):
    When an upstream endpoint experiences timeouts, the circuit breaker trips to OPEN.
    VERA must FAST-FAIL and MUST NOT attempt the other 15 models sharing the same degraded endpoint.
    If an independent provider exists, it switches to that provider.
    """
    mgr = clean_health_mgr
    policy = ModelPolicy(store=mock_store)
    router = ModelRouter(store=mock_store)

    # 1. Simulate 2 consecutive timeouts on 'nvidia' provider to trip circuit breaker
    mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "ReadTimeout(30s)")
    assert mgr.is_provider_available("nvidia") is True  # 1st failure

    mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "ReadTimeout(30s)")
    assert mgr.is_provider_available("nvidia") is False  # 2nd failure -> Circuit transitions to OPEN

    rec = mgr.get_record("nvidia")
    assert rec.circuit_state == CircuitState.OPEN

    # 2. Register an independent secondary provider (e.g. OpenRouter)
    mock_store.create_model(
        provider="openrouter",
        model_id="qwen2.5:7b-instruct",
        display_name="Qwen 2.5 7B (OpenRouter)",
        label="general",
        custom_id="openrouter_qwen",
    )

    # 3. Attempt to call a model on nvidia while circuit is OPEN
    nvidia_model = router.select_for_label("general")
    assert nvidia_model.provider == "nvidia"

    # Track how many times chat was called
    chat_calls = []

    def mock_chat(provider, model, *args, **kwargs):
        chat_calls.append((provider, model))
        if provider == "nvidia":
            return {"error": "Circuit breaker OPEN untuk provider 'nvidia'", "error_type": "circuit_open"}
        return {
            "message": {"role": "assistant", "content": "Response from OpenRouter fallback."},
            "usage": {"total_tokens": 40},
        }

    with patch.object(ProviderClient, "chat", side_effect=mock_chat):
        result = call_model(
            messages=[{"role": "user", "content": "Cek interface"}],
            tools=[],
            selected_model=nvidia_model,
            policy=policy,
            router=router,
        )

        # 4. CRITICAL ASSERTION:
        # VERA must NOT have looped through all 15 NVIDIA models!
        nvidia_calls = [c for c in chat_calls if c[0] == "nvidia"]
        assert len(nvidia_calls) <= 1, f"Repeated degraded provider calls detected: {nvidia_calls}"

        # 5. Fallback recovered on the independent healthy provider
        assert "error" not in result
        assert result["model"]["provider"] == "openrouter"
        assert result["message"]["content"] == "Response from OpenRouter fallback."


def test_scenario_b_fast_fail_when_no_independent_provider_available(clean_health_mgr, mock_store):
    """
    Scenario B2: When circuit breaker is OPEN on nvidia and no independent provider is online,
    VERA immediately fast-fails with an informative message without cycling through models.
    """
    mgr = clean_health_mgr
    policy = ModelPolicy(store=mock_store)
    router = ModelRouter(store=mock_store)

    # Trip circuit breaker
    mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "ReadTimeout(30s)")
    mgr.record_failure("nvidia", FailureCategory.TIMEOUT, "ReadTimeout(30s)")
    assert mgr.is_provider_available("nvidia") is False

    nvidia_model = router.select_for_label("general")
    chat_calls = []

    def mock_chat(provider, model, *args, **kwargs):
        chat_calls.append((provider, model))
        return {"error": "Circuit breaker OPEN untuk provider 'nvidia'", "error_type": "circuit_open"}

    with patch.object(ProviderClient, "chat", side_effect=mock_chat):
        result = call_model(
            messages=[{"role": "user", "content": "Help"}],
            tools=[],
            selected_model=nvidia_model,
            policy=policy,
            router=router,
        )

        assert "error" in result
        # Should not make repeated calls across all 17 NVIDIA models
        nvidia_calls = [c for c in chat_calls if c[0] == "nvidia"]
        assert len(nvidia_calls) <= 1, f"Repeated calls to degraded provider: {nvidia_calls}"
        assert len(chat_calls) <= 2


# =========================================================================
# SCENARIO C: Model-Specific 404 Error Isolation (Non-Degrading)
# =========================================================================

def test_scenario_c_model_specific_404_does_not_trip_provider_circuit(clean_health_mgr, mock_store):
    """
    Scenario C: A model returns 404 (e.g. discontinued model ID).
    - The provider circuit breaker MUST remain CLOSED.
    - The specific model is marked UNAVAILABLE.
    - Fallback to another model on the same provider succeeds.
    """
    mgr = clean_health_mgr
    policy = ModelPolicy(store=mock_store)
    router = ModelRouter(store=mock_store)

    # Pick primary model
    primary = router.select_for_label("general")
    assert primary.provider == "nvidia"

    # Simulate 404 on this specific model
    mgr.record_failure(
        provider="nvidia",
        category=FailureCategory.NOT_FOUND,
        error_message="HTTP 404 Model Not Found",
        model_id=primary.model_id,
    )

    # Provider circuit breaker MUST remain CLOSED (healthy)
    assert mgr.is_provider_available("nvidia") is True
    # Model-specific health check MUST reflect UNAVAILABLE
    assert mgr.is_model_available("nvidia", primary.model_id) is False

    # Call should succeed by falling back to another enabled model on nvidia
    def mock_chat(provider, model, *args, **kwargs):
        if model == primary.model_id:
            return {"error": "404 Not Found", "error_type": "not_found"}
        return {
            "message": {"role": "assistant", "content": "Response from alternative model."},
            "usage": {"total_tokens": 35},
        }

    with patch.object(ProviderClient, "chat", side_effect=mock_chat):
        result = call_model(
            messages=[{"role": "user", "content": "Status"}],
            tools=[],
            selected_model=primary,
            policy=policy,
            router=router,
        )

        assert "error" not in result
        assert result["message"]["content"] == "Response from alternative model."
        assert mgr.is_provider_available("nvidia") is True


# =========================================================================
# SCENARIO D: Capability-Aware Model Routing
# =========================================================================

def test_scenario_d_capability_aware_model_selection(mock_store):
    """
    Scenario D: Validates capability-aware discovery and routing:
    1. Tool Calling: finds models supporting function execution.
    2. Vision: finds models supporting multimodal vision input.
    3. Long-Context: ModelPolicy upgrades model when estimated tokens exceed window.
    """
    # 1. Tool-calling filter
    tool_models = mock_store.find_models(capability="tool_calling", enabled_only=True)
    assert len(tool_models) > 0
    assert any(m["model_id"] == "nvidia/nemotron-3.5-bolt-e4b" for m in tool_models)
    assert any(m["model_id"] == "poolside/laguna-xs-2.1" for m in tool_models)

    # 2. Vision filter
    vision_models = mock_store.find_models(capability="vision", enabled_only=True)
    assert len(vision_models) > 0
    assert any("vision" in m["model_id"] or m["supports_vision"] for m in vision_models)

    # 3. Long-Context Policy: upgrade model when prompt exceeds token window
    policy = ModelPolicy(store=mock_store)
    small_model = SelectedModel(
        id="small_model",
        display_name="Small Model",
        provider="nvidia",
        model_id="small/test",
        label="general",
        context_window=1000,
    )

    # 1500 tokens exceeds 1000 limit -> policy upgrades to larger model
    checked = policy.check_context(small_model, estimated_tokens=1500)
    assert checked.id != small_model.id
    assert checked.context_window > 1000
