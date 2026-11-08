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

from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from core.global_settings import read as settings_read
from core.global_settings import read_all as settings_read_all
from core.global_settings import write as settings_write
from core.tenant.auth_deps import get_current_authenticated_user, require_permission
from core.tenant.models import TenantContext

router = APIRouter(
    prefix="/api/settings",
    tags=["settings"],
    dependencies=[Depends(get_current_authenticated_user)],
)


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
def update_setting(
    key: str,
    payload: SettingUpdateRequest,
    ctx: TenantContext = Depends(require_permission("settings.write")),
):
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
def update_approval_preferences(
    body: UpdateApprovalPreferencesIn,
    tenant_id: str = "tenant_default",
    ctx: TenantContext = Depends(require_permission("settings.write")),
):
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
def get_entitlements_summary(
    tenant_id: str = "tenant_default",
    ctx: TenantContext = Depends(get_current_authenticated_user),
):
    from core.tenant.user_subscription import UserSubscriptionService

    user_id = ctx.user_id
    effective_tenant = ctx.tenant_id or tenant_id

    tier_val = "standard"
    has_net = False
    try:
        sub_svc = UserSubscriptionService()
        sub = sub_svc.get_subscription(user_id)
        if sub:
            tier_val = str(sub.plan_id).lower()
            has_net = bool(sub.has_networking_plus)
    except Exception:
        pass

    return {
        "success": True,
        "entitlements": {
            "tier": tier_val,
            "has_networking_plus": has_net,
        },
        "user_id": user_id,
        "tenant_id": effective_tenant,
    }

