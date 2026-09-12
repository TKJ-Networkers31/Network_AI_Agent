"""
api/routers/models.py — REST endpoint CRUD untuk Model Management System.

Taruh file ini di: AIRA_ECOSYSTEM/api/routers/models.py (file BARU).

Semua endpoint di bawah cuma "pintu HTTP" tipis di atas core/model_registry.py
(CRUD murni) dan agents/rei/provider_client.py::test_connection (health
check). Tidak ada logic bisnis tambahan di sini.

Kolom `api_key` TIDAK PERNAH dikirim balik utuh ke frontend - list/get selalu
memakai mask_api_key=True (lihat core/model_registry.py::_row_to_dict), yang
mengganti kolom api_key dengan boolean `has_api_key`.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core import model_registry as registry
from agents.rei.provider_client import test_connection as _test_connection

router = APIRouter(prefix="/api/models", tags=["models"])


def _dump(payload: BaseModel) -> dict:
    """Kompatibel pydantic v1 (.dict()) maupun v2 (.model_dump())."""
    if hasattr(payload, "model_dump"):
        return payload.model_dump()
    return payload.dict()


class ModelCreateRequest(BaseModel):
    nickname: str
    provider: str
    model_id: str
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    is_default: bool = False
    is_fallback: bool = False
    enabled: bool = True


class ModelUpdateRequest(BaseModel):
    provider: Optional[str] = None
    model_id: Optional[str] = None
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    is_default: Optional[bool] = None
    is_fallback: Optional[bool] = None
    enabled: Optional[bool] = None


class SetFallbackRequest(BaseModel):
    is_fallback: bool = True


class SetEnabledRequest(BaseModel):
    enabled: bool


@router.get("")
def list_models():
    return {"models": registry.list_models(mask_api_key=True)}


@router.get("/{nickname}")
def get_model(nickname: str):
    model = registry.get_model(nickname, mask_api_key=True)

    if not model:
        raise HTTPException(status_code=404, detail=f"Model '{nickname}' tidak ditemukan.")

    return model


@router.post("")
def create_model(payload: ModelCreateRequest):
    result = registry.create_model(**_dump(payload))

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.put("/{nickname}")
def update_model(nickname: str, payload: ModelUpdateRequest):
    fields = {k: v for k, v in _dump(payload).items() if v is not None}
    result = registry.update_model(nickname, **fields)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.delete("/{nickname}")
def delete_model(nickname: str):
    result = registry.delete_model(nickname)

    if not result.get("success"):
        raise HTTPException(status_code=404, detail=f"Model '{nickname}' tidak ditemukan.")

    return result


@router.post("/{nickname}/set-default")
def set_default(nickname: str):
    result = registry.set_default(nickname)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/{nickname}/set-fallback")
def set_fallback(nickname: str, payload: SetFallbackRequest):
    result = registry.set_fallback(nickname, is_fallback=payload.is_fallback)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/{nickname}/enable")
def set_enabled(nickname: str, payload: SetEnabledRequest):
    result = registry.set_enabled(nickname, enabled=payload.enabled)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/{nickname}/test-connection")
def test_connection(nickname: str):
    result = _test_connection(nickname)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result