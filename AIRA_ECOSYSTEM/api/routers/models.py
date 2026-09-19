"""
api/routers/models.py — CRUD model + Default Routing + Policy (Sprint 1).

Pintu HTTP tipis di atas core/model_store.py. Menggantikan endpoint Phase 1.2
(set-default / set-fallback per model) dengan tabel routing per label.

Urutan route penting: path statis (/routing, /policy, /route-preview)
dideklarasikan SEBELUM /{model_id}.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from agents.rei.provider_client import test_connection as _test_connection
from core.model_router import get_model_router
from core.model_store import get_model_store
from core.model_types import VALID_LABELS
from core.task_classifier import get_task_classifier

router = APIRouter(prefix="/api/models", tags=["models"])


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


class ModelUpdateRequest(BaseModel):
    provider: Optional[str] = None
    model_id: Optional[str] = None
    display_name: Optional[str] = None
    label: Optional[str] = None
    context_window: Optional[int] = None
    enabled: Optional[bool] = None


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


# ------------------------------------------------------------ list / create

@router.get("")
def list_models(label: Optional[str] = Query(default=None), search: Optional[str] = Query(default=None)):
    return {"models": get_model_store().list_models(label=label, search=search)}


@router.post("")
def create_model(payload: ModelCreateRequest):
    result = get_model_store().create_model(**_dump(payload))
    if not result.get("success"):
        _raise(result)
    return result


# ------------------------------------------------- routing / policy / preview

@router.get("/routing")
def get_routing():
    store = get_model_store()
    return {"routing": store.get_routing(), "policy": store.get_policy(), "labels": list(VALID_LABELS)}


@router.put("/routing/{task_label}")
def set_default_model(task_label: str, payload: DefaultModelRequest):
    result = get_model_store().set_default_model(task_label, payload.default_model_id)
    if not result.get("success"):
        _raise(result)
    return result


@router.put("/policy")
def update_policy(payload: PolicyUpdateRequest):
    result = get_model_store().set_policy(**_dump(payload, exclude_unset=True))
    if not result.get("success"):
        _raise(result)
    return result


@router.post("/route-preview")
def route_preview(payload: RoutePreviewRequest):
    """Dry-run: klasifikasi + pilih model untuk sebuah prompt (memanggil LLM classifier)."""
    classification = get_task_classifier().classify(payload.prompt)
    selected = get_model_router().select(classification)
    return {
        "classification": classification.to_dict(),
        "selected": selected.to_dict() if selected else None,
    }


# ----------------------------------------------------------- single model

@router.get("/{model_id}")
def get_model(model_id: str):
    model = get_model_store().get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' tidak ditemukan.")
    return model


@router.put("/{model_id}")
def update_model(model_id: str, payload: ModelUpdateRequest):
    result = get_model_store().update_model(model_id, **_dump(payload, exclude_unset=True))
    if not result.get("success"):
        _raise(result)
    return result


@router.delete("/{model_id}")
def delete_model(model_id: str):
    result = get_model_store().delete_model(model_id)
    if not result.get("success"):
        _raise(result)
    return result


@router.post("/{model_id}/test-connection")
def test_connection(model_id: str):
    result = _test_connection(model_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result