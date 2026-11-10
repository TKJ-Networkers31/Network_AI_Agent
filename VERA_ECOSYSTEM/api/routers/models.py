"""
api/routers/models.py — Centralized AI Model Management & Synchronization API.

Pintu HTTP authoritative di atas core/model_store.py, core/model_router.py,
dan core/provider_health.py.

Single Source of Truth untuk Model Catalog VERA:
- Read endpoints: diakses oleh semua pengguna terautentikasi (get_current_authenticated_user).
- Mutating / admin endpoints: dibatasi ketat ke Superadmin (require_superadmin).
- Semua mutasi mem-publish EventBus EventNames.MODEL_* yang diteruskan
  secara realtime oleh WebSocket bridge ke seluruh client VERA frontend.
"""

from typing import Any, Dict, List, Optional
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from core.tenant.auth_deps import get_current_authenticated_user, require_superadmin
from pydantic import BaseModel

from agents.rei.provider_client import test_connection as _test_connection
from core.events import EventNames, event_bus
from core.model_router import get_model_router
from core.model_store import get_model_store
from core.model_types import (
    VALID_LABELS,
    TASK_CLASSIFICATION_CATEGORIES,
    CATEGORY_TO_LABEL_MAP,
    TaskClassification,
)
from core.provider_health import get_provider_health_manager
from core.task_classifier import get_task_classifier

router = APIRouter(prefix="/api/models", tags=["models"], dependencies=[Depends(get_current_authenticated_user)])


def _dump(payload: BaseModel, exclude_unset: bool = False) -> dict:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_unset=exclude_unset)
    return payload.dict(exclude_unset=exclude_unset)


class ModelCreateRequest(BaseModel):
    provider: str
    model_id: str
    display_name: str
    label: str = "general"
    context_window: int = 0
    enabled: bool = True
    publisher: Optional[str] = ""
    api_endpoint: Optional[str] = ""
    model_type: Optional[str] = "dense"
    max_output_tokens: Optional[int] = 4096
    supports_streaming: Optional[bool] = True
    supports_tool_calling: Optional[bool] = False
    supports_structured_output: Optional[bool] = True
    supports_vision: Optional[bool] = False
    priority: Optional[int] = 10


class ModelUpdateRequest(BaseModel):
    provider: Optional[str] = None
    model_id: Optional[str] = None
    display_name: Optional[str] = None
    label: Optional[str] = None
    context_window: Optional[int] = None
    enabled: Optional[bool] = None
    publisher: Optional[str] = None
    api_endpoint: Optional[str] = None
    model_type: Optional[str] = None
    max_output_tokens: Optional[int] = None
    supports_streaming: Optional[bool] = None
    supports_tool_calling: Optional[bool] = None
    supports_structured_output: Optional[bool] = None
    supports_vision: Optional[bool] = None
    priority: Optional[int] = None
    availability_status: Optional[str] = None
    lifecycle_status: Optional[str] = None
    health_status: Optional[str] = None


class ModelStatusUpdateRequest(BaseModel):
    enabled: bool


class ModelPriorityUpdateRequest(BaseModel):
    priority: int


class CatalogSyncRequest(BaseModel):
    provider: str = "nvidia"
    api_key: Optional[str] = None


class DefaultModelRequest(BaseModel):
    default_model_id: str


class PolicyUpdateRequest(BaseModel):
    fallback_model_id: Optional[str] = None
    retry_provider: Optional[int] = None


class RoutePreviewRequest(BaseModel):
    prompt: str


def _raise(result: dict) -> None:
    if result.get("not_found"):
        raise HTTPException(status_code=404, detail=result["error"])
    if result.get("in_use"):
        raise HTTPException(status_code=409, detail=result["error"])
    raise HTTPException(status_code=400, detail=result.get("error", "Permintaan gagal."))


# ============================================================
# READ ENDPOINTS (Accessible to all authenticated users)
# ============================================================

@router.get("")
def list_models(
    label: Optional[str] = Query(default=None),
    classification: Optional[str] = Query(default=None),
    capability: Optional[str] = Query(default=None),
    modality: Optional[str] = Query(default=None),
    provider: Optional[str] = Query(default=None),
    availability: Optional[str] = Query(default=None),
    lifecycle: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    enabled_only: bool = Query(default=False),
):
    models = get_model_store().find_models(
        capability=capability,
        modality=modality,
        task=classification or label,
        label=label,
        provider=provider,
        status=availability or lifecycle,
        lifecycle=lifecycle,
        availability=availability,
        search=search,
        enabled_only=enabled_only,
    )
    return {"models": models}


@router.get("/active")
def get_active_model(label: str = Query(default="general")):
    """
    Returns the currently active model configuration:
    - preferred_model: configured default for the task
    - executing_model: model that actually executes given provider health / circuit state
    - fallback_model: configured fallback
    - active_by_label: current defaults per label
    - provider_health: current health status of upstream endpoints
    """
    store = get_model_store()
    router_inst = get_model_router()
    health_mgr = get_provider_health_manager()

    routing = store.get_routing()
    policy = store.get_policy()
    models_by_id = {m["id"]: m for m in store.list_models()}

    preferred_id = routing.get(label)
    preferred_model = models_by_id.get(preferred_id) if preferred_id else None

    # Resolve executing candidate
    category_str = label if label in TASK_CLASSIFICATION_CATEGORIES else "general_chat"
    dummy_classification = TaskClassification(
        primary_label=label if label in VALID_LABELS else "general",
        task_category=category_str,
    )
    executing_candidate = router_inst.select(dummy_classification)
    executing_model = None
    if executing_candidate:
        executing_model = store.get_model(executing_candidate.model_id) or {
            "model_id": executing_candidate.model_id,
            "provider": executing_candidate.provider,
            "display_name": executing_candidate.display_name,
        }

    fallback_id = policy.get("fallback_model_id")
    fallback_model = models_by_id.get(fallback_id) if fallback_id else None

    active_by_label = {}
    for lbl, mid in routing.items():
        active_by_label[lbl] = models_by_id.get(mid)

    return {
        "task_label": label,
        "preferred_model": preferred_model,
        "executing_model": executing_model,
        "fallback_model": fallback_model,
        "active_by_label": active_by_label,
        "provider_health": health_mgr.get_all_records(),
    }


@router.get("/classifications")
def get_model_classifications():
    """Returns all 28 unified task categories and models supporting each."""
    store = get_model_store()
    all_models = store.list_models()

    categories_data = []
    for cat_val in TASK_CLASSIFICATION_CATEGORIES:
        matched = []
        for m in all_models:
            supp_tasks = m.get("supported_tasks", [])
            primary_lbl = CATEGORY_TO_LABEL_MAP.get(cat_val, "general")
            if cat_val in supp_tasks or m.get("label") == cat_val or m.get("label") == primary_lbl:
                matched.append(m["id"])
        categories_data.append({
            "category": cat_val,
            "name": cat_val.replace("_", " ").title(),
            "models_count": len(matched),
            "model_ids": matched,
        })
    return {"classifications": categories_data}


@router.get("/capabilities")
def get_model_capabilities():
    """Returns models grouped by recognized capabilities."""
    store = get_model_store()
    all_models = store.list_models()

    capabilities_list = [
        "tool_calling", "streaming", "vision", "audio", "video",
        "structured_output", "code_generation", "reasoning", "multilingual",
    ]
    caps_data = {}
    for cap in capabilities_list:
        matching = []
        for m in all_models:
            caps = m.get("capabilities", [])
            if cap in caps or m.get(f"supports_{cap}"):
                matching.append({
                    "id": m["id"],
                    "model_id": m["model_id"],
                    "display_name": m["display_name"],
                    "provider": m["provider"],
                    "priority": m.get("priority", 10),
                    "health_status": m.get("health_status", "HEALTHY"),
                    "lifecycle_status": m.get("lifecycle_status", "ACTIVE"),
                })
        caps_data[cap] = matching
    return {"capabilities": caps_data}


@router.get("/benchmarks")
def get_model_benchmarks():
    """Returns verified model benchmark telemetry and lifecycle status."""
    store = get_model_store()
    all_models = store.list_models()
    benchmarks = []
    for m in all_models:
        benchmarks.append({
            "id": m["id"],
            "model_id": m["model_id"],
            "display_name": m["display_name"],
            "provider": m["provider"],
            "publisher": m.get("publisher", ""),
            "model_type": m.get("model_type", "dense"),
            "context_window": m.get("context_window", 0),
            "max_output_tokens": m.get("max_output_tokens", 4096),
            "priority": m.get("priority", 10),
            "health_status": m.get("health_status", "HEALTHY"),
            "lifecycle_status": m.get("lifecycle_status", "ACTIVE"),
            "availability_status": m.get("availability_status", "ACTIVE"),
            "verified_at": m.get("verified_at", ""),
        })
    return {"benchmarks": benchmarks}


@router.get("/sync-status")
def get_sync_status():
    """Returns catalog discovery and synchronization status."""
    return get_model_store().get_sync_status()


@router.get("/routing")
def get_routing():
    store = get_model_store()
    return {"routing": store.get_routing(), "policy": store.get_policy(), "labels": list(VALID_LABELS)}


@router.post("/route-preview")
def route_preview(payload: RoutePreviewRequest):
    """Dry-run: klasifikasi + pilih model untuk sebuah prompt."""
    classification = get_task_classifier().classify(payload.prompt)
    selected = get_model_router().select(classification)
    return {
        "classification": classification.to_dict(),
        "selected": selected.to_dict() if selected else None,
    }


# ============================================================
# ADMINISTRATIVE & MUTATION ENDPOINTS (require_superadmin)
# ============================================================

@router.post("", dependencies=[Depends(require_superadmin)])
def create_model(payload: ModelCreateRequest):
    store = get_model_store()
    result = store.create_model(**_dump(payload))
    if not result.get("success"):
        _raise(result)

    created_model = result.get("model")
    event_bus.publish(
        EventNames.MODEL_STATUS_CHANGED,
        source="MODEL_API",
        agent="MODEL_ROUTER",
        data={"action": "created", "model": created_model},
    )
    event_bus.publish(
        EventNames.MODEL_REGISTRY_UPDATED,
        source="MODEL_API",
        agent="MODEL_ROUTER",
        data={"action": "created", "model": created_model},
    )
    return result


@router.put("/routing/{task_label}", dependencies=[Depends(require_superadmin)])
def set_default_model(task_label: str, payload: DefaultModelRequest):
    store = get_model_store()
    result = store.set_default_model(task_label, payload.default_model_id)
    if not result.get("success"):
        _raise(result)

    event_bus.publish(
        EventNames.ACTIVE_MODEL_CHANGED,
        source="MODEL_API",
        agent="MODEL_ROUTER",
        data={"task_label": task_label, "default_model_id": payload.default_model_id},
    )
    event_bus.publish(
        EventNames.MODEL_REGISTRY_UPDATED,
        source="MODEL_API",
        agent="MODEL_ROUTER",
        data={"action": "routing_updated", "task_label": task_label, "default_model_id": payload.default_model_id},
    )
    return result


@router.put("/policy", dependencies=[Depends(require_superadmin)])
def update_policy(payload: PolicyUpdateRequest):
    store = get_model_store()
    result = store.set_policy(**_dump(payload, exclude_unset=True))
    if not result.get("success"):
        _raise(result)

    event_bus.publish(
        EventNames.ACTIVE_MODEL_CHANGED,
        source="MODEL_API",
        agent="MODEL_ROUTER",
        data={"action": "policy_updated", "policy": store.get_policy()},
    )
    event_bus.publish(
        EventNames.MODEL_REGISTRY_UPDATED,
        source="MODEL_API",
        agent="MODEL_ROUTER",
        data={"action": "policy_updated", "policy": store.get_policy()},
    )
    return result


@router.post("/sync", dependencies=[Depends(require_superadmin)])
def sync_remote_catalog(payload: Optional[CatalogSyncRequest] = None):
    provider = payload.provider if payload else "nvidia"
    api_key = payload.api_key if payload else None
    store = get_model_store()
    result = store.sync_from_remote_catalog(provider=provider, api_key=api_key)

    if result.get("success"):
        event_bus.publish(
            EventNames.MODEL_DISCOVERY_COMPLETED,
            source="MODEL_API",
            agent="MODEL_ROUTER",
            data=result,
        )
        event_bus.publish(
            EventNames.MODEL_REGISTRY_UPDATED,
            source="MODEL_API",
            agent="MODEL_ROUTER",
            data={"action": "sync_completed", "result": result},
        )
        return result
    else:
        event_bus.publish(
            EventNames.MODEL_SYNC_FAILED,
            source="MODEL_API",
            agent="MODEL_ROUTER",
            data=result,
        )
        raise HTTPException(status_code=502, detail=result.get("error", "Sinkronisasi katalog gagal."))


# ----------------------------------------------------------- single model

@router.get("/{model_id}")
def get_model(model_id: str):
    model = get_model_store().get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' tidak ditemukan.")
    return model


@router.put("/{model_id}", dependencies=[Depends(require_superadmin)])
def update_model(model_id: str, payload: ModelUpdateRequest):
    store = get_model_store()
    result = store.update_model(model_id, **_dump(payload, exclude_unset=True))
    if not result.get("success"):
        _raise(result)

    updated_model = store.get_model(model_id)
    event_bus.publish(
        EventNames.MODEL_STATUS_CHANGED,
        source="MODEL_API",
        agent="MODEL_ROUTER",
        data={"action": "updated", "model_id": model_id, "model": updated_model},
    )
    event_bus.publish(
        EventNames.MODEL_REGISTRY_UPDATED,
        source="MODEL_API",
        agent="MODEL_ROUTER",
        data={"action": "updated", "model_id": model_id, "model": updated_model},
    )
    return result


@router.put("/{model_id}/status", dependencies=[Depends(require_superadmin)])
def update_model_status(model_id: str, payload: ModelStatusUpdateRequest):
    store = get_model_store()
    target = store.get_model(model_id)
    if not target:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' tidak ditemukan.")

    avail_status = "ACTIVE" if payload.enabled else "DISABLED"
    result = store.update_model(model_id, enabled=payload.enabled, availability_status=avail_status)
    if not result.get("success"):
        _raise(result)

    updated_model = store.get_model(model_id)
    event_bus.publish(
        EventNames.MODEL_STATUS_CHANGED,
        source="MODEL_API",
        agent="MODEL_ROUTER",
        data={"model_id": model_id, "enabled": payload.enabled, "model": updated_model},
    )
    event_bus.publish(
        EventNames.MODEL_AVAILABILITY_CHANGED,
        source="MODEL_API",
        agent="MODEL_ROUTER",
        data={"model_id": model_id, "availability_status": avail_status, "model": updated_model},
    )
    event_bus.publish(
        EventNames.MODEL_REGISTRY_UPDATED,
        source="MODEL_API",
        agent="MODEL_ROUTER",
        data={"action": "status_changed", "model_id": model_id, "model": updated_model},
    )
    return {"success": True, "model": updated_model}


@router.put("/{model_id}/priority", dependencies=[Depends(require_superadmin)])
def update_model_priority(model_id: str, payload: ModelPriorityUpdateRequest):
    store = get_model_store()
    target = store.get_model(model_id)
    if not target:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' tidak ditemukan.")

    result = store.update_model(model_id, priority=payload.priority)
    if not result.get("success"):
        _raise(result)

    updated_model = store.get_model(model_id)
    event_bus.publish(
        EventNames.MODEL_PRIORITY_CHANGED,
        source="MODEL_API",
        agent="MODEL_ROUTER",
        data={"model_id": model_id, "priority": payload.priority, "model": updated_model},
    )
    event_bus.publish(
        EventNames.MODEL_REGISTRY_UPDATED,
        source="MODEL_API",
        agent="MODEL_ROUTER",
        data={"action": "priority_changed", "model_id": model_id, "model": updated_model},
    )
    return {"success": True, "model": updated_model}


@router.delete("/{model_id}", dependencies=[Depends(require_superadmin)])
def delete_model(model_id: str):
    store = get_model_store()
    result = store.delete_model(model_id)
    if not result.get("success"):
        _raise(result)

    event_bus.publish(
        EventNames.MODEL_REGISTRY_UPDATED,
        source="MODEL_API",
        agent="MODEL_ROUTER",
        data={"action": "deleted", "model_id": model_id},
    )
    return result


@router.post("/{model_id}/health-check", dependencies=[Depends(require_superadmin)])
def health_check_model(model_id: str):
    store = get_model_store()
    target = store.get_model(model_id)
    if not target:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' tidak ditemukan.")

    test_res = _test_connection(model_id)
    online = bool(test_res.get("online"))
    health_status = "HEALTHY" if online else "UNAVAILABLE"

    store.update_model_health(model_id, status=health_status, verified=online)
    if online and target.get("lifecycle_status") in ("DEPRECATED_PENDING", "UNVERIFIED"):
        store.update_model(model_id, lifecycle_status="ACTIVE")
    updated_model = store.get_model(model_id)

    event_bus.publish(
        EventNames.MODEL_STATUS_CHANGED,
        source="MODEL_API",
        agent="MODEL_ROUTER",
        data={"model_id": model_id, "online": online, "health_status": health_status, "model": updated_model},
    )
    event_bus.publish(
        EventNames.MODEL_REGISTRY_UPDATED,
        source="MODEL_API",
        agent="MODEL_ROUTER",
        data={"action": "health_check", "model_id": model_id, "online": online, "health_status": health_status},
    )
    return {
        "success": True,
        "online": online,
        "health_status": health_status,
        "message": test_res.get("message", "OK" if online else "Offline"),
        "model": updated_model,
    }


@router.post("/{model_id}/test-connection", dependencies=[Depends(require_superadmin)])
def test_connection(model_id: str):
    result = _test_connection(model_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result
