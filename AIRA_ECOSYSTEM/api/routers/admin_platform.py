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

router = APIRouter(prefix="/api/v1/admin", tags=["admin_platform"])

_identity_mgr = IdentityManager()
_tenant_mgr = TenantManager()
_entitlement_mgr = EntitlementManager()
_approval_engine = CentralizedApprovalEngine()


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
        UserRoleType.PLATFORM_SUPER_ADMIN.value,
        UserRoleType.NOC_ADMIN.value,
    }
    if not any(r in admin_roles for r in ctx.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Platform administration access required.",
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
