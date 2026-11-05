"""
api/routers/settings.py — REST endpoint for the Global Settings Engine
(Sprint 2.6, Worker 1).

Thin HTTP layer over core/global_settings.py - no persistence or
validation logic lives here, same convention as api/routers/persona.py
and api/routers/location.py.

    GET  /api/settings          -> all settings (merged with defaults)
    GET  /api/settings/{key}    -> one setting
    PUT  /api/settings/{key}    -> update one setting (validated)

Registration (api/main.py) — one line, next to the other routers:

    from api.routers import ..., settings
    app.include_router(settings.router)

Not applied automatically here since this worker's scope is limited to
the settings module itself; wiring it into api/main.py's router list is
a one-line, low-risk addition left for integration.
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.global_settings import read as settings_read
from core.global_settings import read_all as settings_read_all
from core.global_settings import write as settings_write

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingUpdateRequest(BaseModel):
    value: Any


@router.get("")
def get_all_settings():
    result = settings_read_all()
    return {"settings": result["settings"], "updated_at": result["updated_at"]}


@router.get("/{key}")
def get_setting(key: str):
    result = settings_read(key)

    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))

    return {"key": result["key"], "value": result["value"], "updated_at": result.get("updated_at")}


@router.put("/{key}")
def update_setting(key: str, payload: SettingUpdateRequest):
    result = settings_write(key, payload.value)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.get("/approvals/preferences")
def get_approval_preferences(tenant_id: str = "tenant_default"):
    from core.operations.approval_engine import get_approval_engine
    engine = get_approval_engine()
    prefs = engine.get_preferences(tenant_id)
    return {"success": True, "preferences": prefs.__dict__}


class UpdateApprovalPreferencesIn(BaseModel):
    mode: str = "ALWAYS_ASK"
    auto_approve_categories: list[str] = ["A"]
    allowed_change_windows: list[str] = []


@router.put("/approvals/preferences")
def update_approval_preferences(body: UpdateApprovalPreferencesIn, tenant_id: str = "tenant_default"):
    from core.operations.approval_engine import get_approval_engine
    engine = get_approval_engine()
    engine.set_preferences(
        tenant_id=tenant_id,
        mode=body.mode,
        auto_approve_categories=body.auto_approve_categories,
        allowed_change_windows=body.allowed_change_windows,
    )
    return {"success": True, "message": "Approval preferences updated successfully."}


@router.get("/entitlements/summary")
def get_entitlements_summary(tenant_id: str = "tenant_default"):
    from core.tenant.entitlements import get_entitlement_manager
    mgr = get_entitlement_manager()
    plan = mgr.get_tenant_plan(tenant_id)
    bal = mgr.get_token_balance(tenant_id)
    return {
        "success": True,
        "entitlements": {
            "tier": plan.tier.value,
            "has_networking_plus": plan.has_networking_plus,
            "monthly_allowance": plan.monthly_token_allowance,
        },
        "balance": {
            "current_balance": bal.current_balance,
            "monthly_allowance": bal.monthly_allowance,
            "tokens_used_this_period": bal.tokens_used_this_period,
            "rollover_tokens": bal.rollover_tokens,
            "period_ends_at": bal.period_ends_at,
        },
    }

