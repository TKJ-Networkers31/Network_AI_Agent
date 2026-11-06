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
from core.tenant.entitlements import EntitlementManager, PlanTier, TokenPolicy
from core.tenant.manager import IdentityManager, TenantManager
from core.tenant.models import Permission, TenantContext, TenantStatus, UserRoleType
from core.tenant.user_subscription import UserSubscriptionService
from core.billing.service import BillingService
from core.tenant.token_quota_service import TokenQuotaService

router = APIRouter(prefix="/api/v1/admin", tags=["admin_platform"])

_identity_mgr = IdentityManager()
_tenant_mgr = TenantManager()
_entitlement_mgr = EntitlementManager()
_approval_engine = CentralizedApprovalEngine()
_sub_service = UserSubscriptionService()
_billing_service = BillingService()
_quota_service = TokenQuotaService()


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
    if not (ctx.is_internal or any(r in admin_roles for r in ctx.roles)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform administration access required. Akses ditolak: AIRA Control Plane memerlukan kredensial staf internal administrator.",
        )
    return ctx


class AssignPlanInput(BaseModel):
    tenant_id: str
    tier: str = Field(..., description="FREE, PRO, ENTERPRISE, CUSTOM")
    networking_plus: bool = False
    monthly_tokens: Optional[int] = None
    valid_until_utc: Optional[str] = None


class UpdateTokenPolicyInput(BaseModel):
    scope_type: str = "GLOBAL"
    scope_id: Optional[str] = None
    tier: str = "FREE"
    monthly_token_allocation: int
    daily_token_limit: int
    networking_plus_enabled: bool = False
    model_cost_mult: Dict[str, float] = Field(default_factory=dict)
    tool_cost_matrix: Dict[str, int] = Field(default_factory=dict)
    max_request_size_tokens: int = 32768
    rate_limit_rpm: int = 60


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
        bal = _entitlement_mgr.get_or_create_balance(t.tenant_id)
        t_dict["token_balance"] = bal.to_dict()
        res.append(t_dict)
    return {"success": True, "tenants": res}


@router.post("/assign-plan")
def assign_plan(payload: AssignPlanInput, admin: TenantContext = Depends(require_platform_admin)):
    """Manually assigns or updates subscription tier, token allocation, and Networking++."""
    _entitlement_mgr.assign_plan(
        tenant_id=payload.tenant_id,
        tier=payload.tier.upper(),
        networking_plus=payload.networking_plus,
        monthly_tokens=payload.monthly_tokens,
        valid_until_utc=payload.valid_until_utc,
    )
    return {
        "success": True,
        "message": f"Successfully updated plan for tenant {payload.tenant_id} to {payload.tier.upper()}.",
        "entitlements": _entitlement_mgr.get_tenant_entitlements(payload.tenant_id),
        "token_balance": _entitlement_mgr.get_or_create_balance(payload.tenant_id).to_dict(),
    }


@router.get("/token-policy")
def get_token_policy(
    scope_type: str = Query(default="GLOBAL"),
    tier: str = Query(default="FREE"),
    admin: TenantContext = Depends(require_platform_admin),
):
    """Retrieves token policy for the given scope and tier."""
    policy = _entitlement_mgr.get_policy(scope_type=scope_type, tier=tier.upper())
    return {"success": True, "policy": policy.to_dict()}


@router.put("/token-policy")
def update_token_policy(payload: UpdateTokenPolicyInput, admin: TenantContext = Depends(require_platform_admin)):
    """Updates token policy configuration."""
    pol = TokenPolicy(
        policy_id=f"pol_{payload.scope_type.lower()}_{payload.tier.lower()}",
        scope_type=payload.scope_type.upper(),
        scope_id=payload.scope_id,
        tier=payload.tier.upper(),
        monthly_token_allocation=payload.monthly_token_allocation,
        daily_token_limit=payload.daily_token_limit,
        networking_plus_enabled=payload.networking_plus_enabled,
        model_cost_mult=payload.model_cost_mult,
        tool_cost_matrix=payload.tool_cost_matrix,
        max_request_size_tokens=payload.max_request_size_tokens,
        rate_limit_rpm=payload.rate_limit_rpm,
    )
    saved = _entitlement_mgr.set_policy(pol)
    return {"success": True, "policy": saved.to_dict()}


@router.get("/usage-ledger")
def get_usage_ledger(
    tenant_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    admin: TenantContext = Depends(require_platform_admin),
):
    """Audits token usage across all or specific tenants."""
    records = _entitlement_mgr.list_usage_ledger(tenant_id=tenant_id, limit=limit)
    return {"success": True, "records": [r.to_dict() for r in records]}


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


@router.get("/billing/invoices")
def list_all_invoices(limit: int = Query(50), admin: TenantContext = Depends(require_platform_admin)):
    """Control plane view of platform billing invoices."""
    invoices = _billing_service.list_invoices(limit=limit)
    return {"success": True, "invoices": invoices}


@router.get("/billing/transactions")
def list_all_transactions(limit: int = Query(50), admin: TenantContext = Depends(require_platform_admin)):
    """Control plane view of platform payment transactions."""
    txns = _billing_service.list_transactions(limit=limit)
    return {"success": True, "transactions": txns}


class AdjustUserQuotaInput(BaseModel):
    target_user_id: str
    new_quota: int = Field(..., ge=0)
    reason: str = Field(..., min_length=3)
    adjustment_type: str = "MANUAL_OVERRIDE"


class ResetUserQuotaInput(BaseModel):
    target_user_id: str
    reason: str = Field(default="Admin manual reset", min_length=3)


class UpdatePlanPolicyInput(BaseModel):
    tier: str
    monthly_token_allocation: int = Field(..., ge=1000)
    daily_token_allocation: int = Field(..., ge=500)
    reset_period: str = "MONTHLY"
    reset_type: str = "CALENDAR"
    reset_timezone: str = "Asia/Jakarta"
    rate_limit_rpm: int = 60


@router.post("/tokens/adjust")
def adjust_user_quota(payload: AdjustUserQuotaInput, admin: TenantContext = Depends(require_platform_admin)):
    """Manually overrides or grants bonus quota to a user with mandatory audit logging."""
    try:
        res = _quota_service.adjust_user_quota(
            admin_user_id=admin.user_id,
            target_user_id=payload.target_user_id,
            new_quota=payload.new_quota,
            reason=payload.reason,
            adjustment_type=payload.adjustment_type,
        )
        return {"success": True, "adjustment": res}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/tokens/reset")
def reset_user_quota(payload: ResetUserQuotaInput, admin: TenantContext = Depends(require_platform_admin)):
    """Manually resets a target user's consumed tokens to zero."""
    try:
        res = _quota_service.reset_user_quota(
            admin_user_id=admin.user_id,
            target_user_id=payload.target_user_id,
            reason=payload.reason,
        )
        return {"success": True, "result": res}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/tokens/adjustments")
def list_token_adjustments(limit: int = Query(50), admin: TenantContext = Depends(require_platform_admin)):
    """Returns audit trail of manual quota overrides and bonus allocations."""
    adjustments = _quota_service.list_quota_adjustments(limit=limit)
    return {"success": True, "adjustments": adjustments}


@router.get("/tokens/policies")
def list_plan_token_policies(admin: TenantContext = Depends(require_platform_admin)):
    """Returns global token quota policies across tiers."""
    policies = _quota_service.list_plan_policies()
    return {"success": True, "policies": policies}


@router.put("/tokens/plan-policy")
def update_plan_token_policy(payload: UpdatePlanPolicyInput, admin: TenantContext = Depends(require_platform_admin)):
    """Updates plan default token allocations, reset cycle, and timezone."""
    try:
        res = _quota_service.update_plan_policy(
            tier=payload.tier,
            monthly_token_allocation=payload.monthly_token_allocation,
            daily_token_allocation=payload.daily_token_allocation,
            reset_period=payload.reset_period,
            reset_type=payload.reset_type,
            reset_timezone=payload.reset_timezone,
            rate_limit_rpm=payload.rate_limit_rpm,
        )
        return {"success": True, "policy": res}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/tokens/sweep")
def trigger_token_sweep(admin: TenantContext = Depends(require_platform_admin)):
    """Manually triggers background sweep of due token balances."""
    res = _quota_service.sweep_due_quotas()
    return {"success": True, "sweep": res}


class PermissionSimulateInput(BaseModel):
    user_id: str
    resource: str
    action: str
    site_id: Optional[str] = None


@router.post("/permissions/simulate")
def simulate_permissions(payload: PermissionSimulateInput, admin: TenantContext = Depends(require_platform_admin)):
    """Simulates permission evaluation across Org -> UserGroup -> Site -> Subtab -> Resource -> Action."""
    from core.tenant.permission_simulation import get_permission_simulation_service
    svc = get_permission_simulation_service()
    result = svc.simulate_permission(
        user_id=payload.user_id,
        resource=payload.resource,
        action=payload.action,
        site_id=payload.site_id,
    )
    return {"success": True, "simulation": result}

