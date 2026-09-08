from fastapi import APIRouter, HTTPException

from backend.schemas import ProviderSelectRequest
from agent.core.providers import (
    list_providers,
    get_active_provider,
    set_active_provider_key,
    get_openrouter_credits,
)

router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("")
def providers():

    active_key, active_config = get_active_provider()
    all_providers = list_providers()

    return {
        "active_key": active_key,
        "providers": [
            {"key": key, "label": cfg["label"], "type": cfg["type"]}
            for key, cfg in all_providers.items()
        ],
    }


@router.post("/select")
def select(payload: ProviderSelectRequest):

    result = set_active_provider_key(payload.key)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.get("/credits")
def credits():

    _, active_config = get_active_provider()

    if active_config["type"] != "openai":
        return {
            "success": False,
            "error": "Provider aktif bukan API eksternal (tidak ada saldo).",
        }

    return get_openrouter_credits(active_config)
