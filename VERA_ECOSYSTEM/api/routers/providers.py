"""
api/routers/providers.py — AI Provider Registry, Telemetry & Health Manager.

Provides real-time visibility into upstream provider availability,
circuit breaker states, latency telemetry, and manual health probes.
"""

import os
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from core.tenant.auth_deps import get_current_authenticated_user, require_superadmin
from agents.rei.provider_client import get_active_provider, get_openrouter_credits
from core.events import EventNames, event_bus
from core.model_store import get_model_store
from core.provider_health import get_provider_health_manager, CircuitState, FailureCategory

router = APIRouter(prefix="/api/providers", tags=["providers"], dependencies=[Depends(get_current_authenticated_user)])

SUPPORTED_PROVIDERS = [
    {
        "id": "nvidia",
        "name": "NVIDIA NIM",
        "env_key": "NVIDIA_API_KEY",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "description": "Enterprise microservices for high-throughput LLM reasoning & vision",
    },
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "env_key": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "description": "Multi-provider aggregation router for fallback redundancy",
    },
    {
        "id": "gemini",
        "name": "Google Gemini",
        "env_key": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com",
        "description": "Google DeepMind Multimodal Gemini models",
    },
]


@router.get("")
def list_providers():
    """Lists all supported upstream providers with configuration status and health."""
    health_mgr = get_provider_health_manager()
    all_health = health_mgr.get_all_records()
    store = get_model_store()
    all_models = store.list_models()

    providers_summary = []
    for p in SUPPORTED_PROVIDERS:
        pid = p["id"]
        # Check if configured
        env_val = os.getenv(p["env_key"])
        is_configured = bool(env_val)
        health_rec = all_health.get(pid, {})

        model_count = sum(1 for m in all_models if m.get("provider") == pid)

        providers_summary.append({
            "id": pid,
            "name": p["name"],
            "configured": is_configured,
            "base_url": p["base_url"],
            "description": p["description"],
            "models_count": model_count,
            "status": health_rec.get("status", "HEALTHY" if is_configured else "DISABLED"),
            "circuit_state": health_rec.get("circuit_state", CircuitState.CLOSED.value),
            "avg_latency_s": health_rec.get("avg_latency_s", 0.0),
            "consecutive_failures": health_rec.get("consecutive_failures", 0),
            "last_error": health_rec.get("last_error", ""),
            "last_success_ts": health_rec.get("last_success_ts"),
            "last_failure_ts": health_rec.get("last_failure_ts"),
        })

    return {"providers": providers_summary}


@router.get("/health")
def get_providers_health():
    """Returns telemetry and circuit breaker records for all active providers."""
    return {"health": get_provider_health_manager().get_all_records()}


@router.get("/{provider}/health")
def get_provider_health(provider: str):
    """Returns health and circuit breaker record for a single provider."""
    rec = get_provider_health_manager().get_record(provider)
    if not rec:
        return {
            "provider": provider,
            "status": "HEALTHY",
            "circuit_state": CircuitState.CLOSED.value,
            "consecutive_failures": 0,
            "avg_latency_s": 0.0,
            "total_requests": 0,
            "total_failures": 0,
        }
    return rec.to_dict()


@router.post("/{provider}/health-check", dependencies=[Depends(require_superadmin)])
def check_provider_health(provider: str):
    """Probes upstream provider endpoint to test availability and updates health record."""
    health_mgr = get_provider_health_manager()
    t0 = time.time()

    # Find registered model for this provider to probe
    store = get_model_store()
    models = store.find_models(provider=provider, enabled_only=True)
    if not models:
        models = store.find_models(provider=provider, enabled_only=False)

    if models:
        from agents.rei.provider_client import test_connection
        res = test_connection(models[0]["id"])
        latency = round(time.time() - t0, 3)
        online = bool(res.get("online"))
    else:
        # Fallback check based on environment key configuration
        latency = 0.001
        online = bool(os.getenv(f"{provider.upper()}_API_KEY"))
        res = {"online": online, "message": "Configured" if online else "No API key"}

    if online:
        health_mgr.record_success(provider, latency=latency)
    else:
        health_mgr.record_failure(provider, category=FailureCategory.CONNECTION, error_message=res.get("message", "Probe failed"))

    updated_rec = health_mgr.get_record(provider)
    event_bus.publish(
        EventNames.PROVIDER_HEALTH_CHANGED,
        source="PROVIDER_API",
        agent="HEALTH_MANAGER",
        data={"provider": provider, "online": online, "health": updated_rec.to_dict() if updated_rec else {}},
    )

    return {
        "provider": provider,
        "online": online,
        "latency_s": latency,
        "health": updated_rec.to_dict() if updated_rec else {},
    }


@router.post("/{provider}/reset-circuit", dependencies=[Depends(require_superadmin)])
def reset_provider_circuit(provider: str):
    """Resets tripped circuit breaker back to CLOSED and HEALTHY."""
    health_mgr = get_provider_health_manager()
    success = health_mgr.reset_circuit(provider)
    rec = health_mgr.get_record(provider)

    event_bus.publish(
        EventNames.PROVIDER_HEALTH_CHANGED,
        source="PROVIDER_API",
        agent="HEALTH_MANAGER",
        data={"provider": provider, "action": "circuit_reset", "health": rec.to_dict() if rec else {}},
    )

    return {
        "success": success,
        "provider": provider,
        "circuit_state": CircuitState.CLOSED.value,
        "health": rec.to_dict() if rec else {},
    }


@router.get("/credits")
def credits():
    """Saldo OpenRouter untuk model DEFAULT saat ini."""
    _, active_config = get_active_provider()

    if not active_config or active_config.get("type") != "openrouter":
        return {"success": False, "error": "Provider aktif bukan OpenRouter (tidak ada saldo)."}

    return get_openrouter_credits()
