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

from fastapi import APIRouter, Header, HTTPException
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
def get_entitlements_summary(
    tenant_id: str = "tenant_default",
    authorization: Optional[str] = Header(None),
):
    import time
    from datetime import datetime
    from core.tenant.entitlements import get_entitlement_manager
    from core.tenant.user_subscription import UserSubscriptionService

    user_id = None
    if isinstance(authorization, str) and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            from core.tenant.manager import IdentityManager
            ctx = IdentityManager().validate_session_token(token)
            if ctx:
                user_id = ctx.user_id
                tenant_id = ctx.tenant_id or tenant_id
        except Exception:
            pass

    mgr = get_entitlement_manager()
    policy = mgr.get_policy(scope_id=tenant_id, scope_type="TENANT")
    bal = mgr.get_or_create_balance(tenant_id=tenant_id, user_id=user_id)

    # Check user-specific subscription if user_id resolved
    sub = None
    if user_id:
        try:
            sub_svc = UserSubscriptionService()
            sub = sub_svc.get_subscription(user_id)
        except Exception:
            sub = None

    if sub:
        tier_val = str(sub.plan_id).lower()
        has_net = bool(sub.has_networking_plus)
        monthly_allowance = int(sub.token_quota)
        used_tokens = int(sub.token_consumed)
        current_balance = int(sub.remaining_tokens)
    else:
        tier_val = getattr(policy.tier, "value", str(policy.tier)).lower()
        has_net = bool(mgr.has_networking_access(tenant_id))
        monthly_allowance = int(bal.allocated_tokens or policy.monthly_token_allocation)
        used_tokens = int(bal.used_tokens)
        current_balance = int(bal.remaining_tokens)

    period_ends_epoch = None
    if bal.period_reset_utc:
        try:
            dt = datetime.fromisoformat(bal.period_reset_utc.replace("Z", "+00:00"))
            period_ends_epoch = int(dt.timestamp())
        except Exception:
            period_ends_epoch = int(time.time() + 30 * 86400)
    else:
        period_ends_epoch = int(time.time() + 30 * 86400)

    return {
        "success": True,
        "entitlements": {
            "tier": tier_val,
            "has_networking_plus": has_net,
            "monthly_allowance": monthly_allowance,
        },
        "balance": {
            "current_balance": current_balance,
            "monthly_allowance": monthly_allowance,
            "tokens_used_this_period": used_tokens,
            "rollover_tokens": 0,
            "period_ends_at": period_ends_epoch,
        },
    }

