"""
AIRA OS — Platform Administration Router (/admin).

Provides restricted platform-level endpoints for:
- Tenant & customer organization management
- Subscription plan assignments & Networking++ entitlement governance
- Admin-tunable token policies & tool cost matrices
- Aggregated cross-tenant token usage auditing
- Centralized approval queue management
- Platform security and operational audit logs
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from core.operations.approval_engine import CentralizedApprovalEngine
from core.tenant.entitlements import EntitlementManager, PlanTier
from core.tenant.manager import IdentityManager, TenantManager
from core.tenant.models import Permission, TenantContext, TenantStatus, UserRoleType
from core.tenant.user_subscription import UserSubscriptionService

router = APIRouter(prefix="/api/v1/admin", tags=["admin_platform"])

_identity_mgr = IdentityManager()
_tenant_mgr = TenantManager()
_entitlement_mgr = EntitlementManager()
_approval_engine = CentralizedApprovalEngine()
_sub_service = UserSubscriptionService()


def require_platform_admin(authorization: Optional[str] = Header(None)) -> TenantContext:
    """Enforces that the caller holds PLATFORM_SUPER_ADMIN or NOC_ADMIN role."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1]
    ctx = _identity_mgr.validate_session_token(token)
    if not ctx:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session.")

    admin_roles = {
        UserRoleType.PLATFORM_OWNER.value,
        "PLATFORM_OWNER",
        UserRoleType.SUPERADMIN.value,
        "SUPERADMIN",
        UserRoleType.ADMIN.value,
        "ADMIN",
        UserRoleType.PLATFORM_SUPER_ADMIN.value,
        UserRoleType.NOC_ADMIN.value,
    }
    has_admin_role = any(r in admin_roles for r in ctx.roles)
    if not (ctx.is_internal and has_admin_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform administration access required. Akses ditolak: VERA Control Plane memerlukan kredensial staf internal administrator.",
        )
    return ctx


class AssignPlanInput(BaseModel):
    tenant_id: str
    tier: str = Field(..., description="FREE, PRO, ENTERPRISE, CUSTOM")
    networking_plus: bool = False
    valid_until_utc: Optional[str] = None


class ResolveApprovalInput(BaseModel):
    approved: bool
    review_notes: Optional[str] = None


@router.get("/tenants")
def list_tenants(admin: TenantContext = Depends(require_platform_admin)):
    """Lists all registered customer tenant organizations."""
    tenants = _tenant_mgr.list_tenants()
    res = []
    for t in tenants:
        t_dict = t.to_dict()
        t_dict["entitlements"] = _entitlement_mgr.get_tenant_entitlements(t.tenant_id)
        res.append(t_dict)
    return {"success": True, "tenants": res}


@router.post("/assign-plan")
def assign_plan(payload: AssignPlanInput, admin: TenantContext = Depends(require_platform_admin)):
    """Manually assigns or updates subscription tier and Networking++."""
    _entitlement_mgr.assign_plan(
        tenant_id=payload.tenant_id,
        tier=payload.tier.upper(),
        networking_plus=payload.networking_plus,
        valid_until_utc=payload.valid_until_utc,
    )
    return {
        "success": True,
        "message": f"Successfully updated plan for tenant {payload.tenant_id} to {payload.tier.upper()}.",
        "entitlements": _entitlement_mgr.get_tenant_entitlements(payload.tenant_id),
    }


@router.get("/approvals")
def list_all_approvals(
    tenant_id: Optional[str] = Query(default=None),
    status_filter: str = Query(default="PENDING", alias="status"),
    admin: TenantContext = Depends(require_platform_admin),
):
    """Lists pending approvals across tenants for administrative review."""
    target_tenant = tenant_id or admin.tenant_id or "default"
    approvals = _approval_engine.list_pending_approvals(tenant_id=target_tenant, status=status_filter)
    return {"success": True, "approvals": [a.to_dict() for a in approvals]}


@router.post("/approvals/{approval_id}/resolve")
def resolve_approval(
    approval_id: str,
    payload: ResolveApprovalInput,
    admin: TenantContext = Depends(require_platform_admin),
):
    """Approves or rejects a queued Category B operation."""
    resolved = _approval_engine.resolve_approval(
        approval_id=approval_id,
        reviewer_id=admin.user_id,
        approved=payload.approved,
        review_notes=payload.review_notes,
    )
    if not resolved:
        raise HTTPException(status_code=404, detail="Pending approval not found or already resolved.")
    return {"success": True, "approval": resolved.to_dict()}


class ImpersonateInput(BaseModel):
    target_user_id: str
    reason: str = Field(..., min_length=5, description="Audited justification for account impersonation")


class AssignUserSubscriptionInput(BaseModel):
    user_id: str
    plan_id: str = Field(..., description="FREE, PRO, ENTERPRISE, CUSTOM")
    duration_days: Optional[int] = 30
    networking_addon: bool = False
    renewal_status: str = "MANUAL"


@router.post("/impersonate")
def impersonate_user(payload: ImpersonateInput, admin: TenantContext = Depends(require_platform_admin)):
    """Allows Superadmin to impersonate a customer account for troubleshooting, with mandatory audit reason."""
    try:
        session = _identity_mgr.impersonate_user(
            admin_user_id=admin.user_id,
            target_user_id=payload.target_user_id,
            reason=payload.reason,
        )
        return {
            "success": True,
            "message": "Impersonation session established. All actions are logged.",
            "impersonated_session": {
                "session_id": session.session_id,
                "token": session.token,
                "target_user_id": session.user_id,
                "target_username": session.username,
                "tenant_id": session.tenant_id,
            },
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/subscriptions")
def list_user_subscriptions(
    status: Optional[str] = Query(None),
    plan_id: Optional[str] = Query(None),
    limit: int = Query(100),
    admin: TenantContext = Depends(require_platform_admin),
):
    """Lists customer user subscriptions with plan tiers and status."""
    subs = _sub_service.list_subscriptions(status=status, plan_id=plan_id, limit=limit)
    return {"success": True, "subscriptions": subs}


@router.post("/subscriptions/assign")
def assign_user_subscription(payload: AssignUserSubscriptionInput, admin: TenantContext = Depends(require_platform_admin)):
    """Admin endpoint to manually upgrade or grant entitlements to a user."""
    try:
        sub = _sub_service.assign_subscription(
            user_id=payload.user_id,
            plan_id=payload.plan_id,
            duration_days=payload.duration_days,
            networking_addon=payload.networking_addon,
            renewal_status=payload.renewal_status,
            operator_user=admin.username,
        )
        return {"success": True, "subscription": sub.to_dict()}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/subscriptions/check-expirations")
def check_expirations(admin: TenantContext = Depends(require_platform_admin)):
    """Manually triggers background sweep of expired subscriptions and non-destructive downgrade."""
    report = _sub_service.check_and_expire_subscriptions()
    return {"success": True, "report": report}







