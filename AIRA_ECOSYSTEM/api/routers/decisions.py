"""
AIRA OS — Operational Decision Intelligence FastAPI Router (Networking VIII / Phase C).

Exposes REST endpoints for:
- Operational decisions listing, inspection, synthesis, and lifecycle transitions
- Append-only decision audit history
- Multi-dimensional health scoring summary (Device, Site, Service, Gateway, Tenant)
- Non-destructive failure simulation and blast radius assessment
- Customer SLA reports and error budget status
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph
from core.operations.decision_engine import OperationalDecisionEngine
from core.operations.health_scoring_engine import DynamicHealthScoringEngine
from core.operations.models import DecisionStatus
from core.operations.risk_engine import RiskAssessmentEngine
from core.operations.sla_engine import SlaManagementEngine
from core.tenant.manager import IdentityManager
from core.tenant.models import Permission, TenantContext

logger = logging.getLogger("aira.api.decisions")

router = APIRouter(prefix="/api/v1/decisions", tags=["decisions"])

_identity_mgr = IdentityManager()
_decision_engine = OperationalDecisionEngine()
_health_engine = DynamicHealthScoringEngine()
_risk_engine = RiskAssessmentEngine()
_sla_engine = SlaManagementEngine()


# ---------------------------------------------------------------------------
# Pydantic Request Models
# ---------------------------------------------------------------------------

class SynthesizeDecisionRequest(BaseModel):
    tenant_id: str
    title: str
    site_id: Optional[str] = None
    affected_services: List[str] = Field(default_factory=list)
    affected_devices: List[str] = Field(default_factory=list)
    expires_in_hours: int = 24


class TransitionDecisionRequest(BaseModel):
    new_status: str
    reason: str


class FailureSimulationRequest(BaseModel):
    tenant_id: str
    failed_devices: List[str] = Field(default_factory=list)
    failed_interfaces: List[str] = Field(default_factory=list)
    scenario_name: str = "Virtual Failure Simulation"


class CreateSlaPolicyRequest(BaseModel):
    tenant_id: str
    service_id: str
    name: str
    target_availability: float = 99.9
    target_response_time_ms: float = 150.0
    target_mttr_minutes: int = 60
    window_type: str = "MONTHLY"
    maintenance_excluded: bool = True


# ---------------------------------------------------------------------------
# Auth Dependency
# ---------------------------------------------------------------------------

def get_current_user_context(authorization: Optional[str] = Header(None)) -> TenantContext:
    """Authenticates human operator / customer user session token."""
    if not authorization or not authorization.startswith("Bearer "):
        if authorization and authorization.startswith("Bearer aira_tok_"):
            token = authorization.split(" ", 1)[1]
            ctx = _identity_mgr.validate_session_token(token)
            if ctx:
                return ctx
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session token.")
        # Default internal admin context for backward compatibility
        return TenantContext(
            user_id="usr_internal_admin",
            username="noc_admin",
            is_internal=True,
            tenant_id=None,
            roles=["NOC_ADMIN"],
            permissions={p.value for p in Permission},
        )

    token = authorization.split(" ", 1)[1]
    ctx = _identity_mgr.validate_session_token(token)
    if not ctx:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session token.")
    return ctx


# ---------------------------------------------------------------------------
# Decision Endpoints
# ---------------------------------------------------------------------------

@router.get("", summary="List operational decisions")
def list_decisions(
    tenant_id: str = Query(...),
    status_filter: Optional[str] = Query(None, alias="status"),
    site_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: TenantContext = Depends(get_current_user_context),
):
    """Lists prioritized operational decisions scoped to a tenant."""
    if not user.can_access_tenant(tenant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot access decisions for another tenant.")

    if not user.has_permission(Permission.RECOMMENDATION_READ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied: recommendation.read required.")

    decisions = _decision_engine.list_decisions(
        tenant_id=tenant_id,
        status=status_filter,
        site_id=site_id,
        limit=limit,
        offset=offset,
    )
    return {"decisions": [d.to_dict() for d in decisions], "total": len(decisions)}


@router.get("/{decision_id}", summary="Get operational decision details")
def get_decision(
    decision_id: str,
    tenant_id: str = Query(...),
    user: TenantContext = Depends(get_current_user_context),
):
    """Retrieves single decision with assessment, alternatives, and checklist."""
    if not user.can_access_tenant(tenant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot access decisions for another tenant.")

    if not user.has_permission(Permission.RECOMMENDATION_READ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied: recommendation.read required.")

    decision = _decision_engine.get_decision(tenant_id=tenant_id, decision_id=decision_id)
    if not decision:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Decision '{decision_id}' not found.")

    return decision.to_dict()


@router.post("", status_code=status.HTTP_201_CREATED, summary="Synthesize operational decision")
def synthesize_decision(
    payload: SynthesizeDecisionRequest,
    user: TenantContext = Depends(get_current_user_context),
):
    """Synthesizes a new operational decision from intelligence."""
    if not user.can_access_tenant(payload.tenant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot synthesize decisions for another tenant.")

    decision = _decision_engine.synthesize_decision(
        tenant_id=payload.tenant_id,
        site_id=payload.site_id,
        problem_title=payload.title,
        affected_services=payload.affected_services,
        affected_devices=payload.affected_devices,
        expires_in_hours=payload.expires_in_hours,
    )
    return decision.to_dict()


@router.post("/{decision_id}/transition", summary="Transition decision status")
def transition_decision(
    decision_id: str,
    payload: TransitionDecisionRequest,
    tenant_id: str = Query(...),
    user: TenantContext = Depends(get_current_user_context),
):
    """Advances decision lifecycle (UNDER_REVIEW, APPROVED, REJECTED, DEFERRED, etc.)."""
    if not user.can_access_tenant(tenant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot transition decisions for another tenant.")

    # Check approval permission if approving
    if payload.new_status == DecisionStatus.APPROVED.value and not user.has_permission(Permission.RECOMMENDATION_APPROVE):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied: recommendation.approve required.")

    try:
        updated = _decision_engine.transition_status(
            decision_id=decision_id,
            tenant_id=tenant_id,
            actor=user.username,
            new_status=payload.new_status,
            reason=payload.reason,
        )
        return updated.to_dict()
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Decision '{decision_id}' not found.")
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))


@router.get("/{decision_id}/history", summary="Get decision audit trail")
def get_decision_history(
    decision_id: str,
    tenant_id: str = Query(...),
    user: TenantContext = Depends(get_current_user_context),
):
    """Returns immutable append-only transition log."""
    if not user.can_access_tenant(tenant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot view history for another tenant.")

    history = _decision_engine.get_decision_history(tenant_id=tenant_id, decision_id=decision_id)
    return {"history": [h.to_dict() for h in history]}


# ---------------------------------------------------------------------------
# Health Scoring Endpoints
# ---------------------------------------------------------------------------

@router.get("/health/summary", summary="Get multi-dimensional health summary")
def get_health_summary(
    tenant_id: str = Query(...),
    site_id: Optional[str] = Query(None),
    user: TenantContext = Depends(get_current_user_context),
):
    """Computes real-time 6-dimension operational health scores."""
    if not user.can_access_tenant(tenant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot view health for another tenant.")

    tenant_health = _health_engine.score_tenant(tenant_id)
    site_health = _health_engine.score_site(tenant_id, site_id) if site_id else None

    return {
        "tenant_health": tenant_health.to_dict(),
        "site_health": site_health.to_dict() if site_health else None,
    }


# ---------------------------------------------------------------------------
# Failure Simulation & Risk Endpoints
# ---------------------------------------------------------------------------

@router.post("/simulations/risk", summary="Run non-destructive failure simulation")
def simulate_risk(
    payload: FailureSimulationRequest,
    user: TenantContext = Depends(get_current_user_context),
):
    """Evaluates blast radius and failure consequences virtually without mutating network."""
    if not user.can_access_tenant(payload.tenant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot simulate failure for another tenant.")

    graph = NetworkKnowledgeGraph()
    res = _risk_engine.simulate_failure(
        tenant_id=payload.tenant_id,
        graph=graph,
        failed_devices=payload.failed_devices,
        failed_interfaces=payload.failed_interfaces,
        scenario_name=payload.scenario_name,
    )
    return res.to_dict()


# ---------------------------------------------------------------------------
# SLA Endpoints
# ---------------------------------------------------------------------------

@router.post("/sla/policies", status_code=status.HTTP_201_CREATED, summary="Create or update SLA policy")
def create_sla_policy(
    payload: CreateSlaPolicyRequest,
    user: TenantContext = Depends(get_current_user_context),
):
    """Sets SLA availability and MTTR target for a customer service."""
    if not user.can_access_tenant(payload.tenant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot configure SLA for another tenant.")

    if not user.has_permission(Permission.SLA_MANAGE):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied: sla.manage required.")

    pol = _sla_engine.create_or_update_policy(
        tenant_id=payload.tenant_id,
        service_id=payload.service_id,
        name=payload.name,
        target_availability=payload.target_availability,
        target_response_time_ms=payload.target_response_time_ms,
        target_mttr_minutes=payload.target_mttr_minutes,
        window_type=payload.window_type,
        maintenance_excluded=payload.maintenance_excluded,
    )
    return pol.to_dict()


@router.get("/sla/reports", summary="Calculate measured SLA report")
def get_sla_report(
    tenant_id: str = Query(...),
    service_id: str = Query(...),
    start_utc: str = Query(...),
    end_utc: str = Query(...),
    user: TenantContext = Depends(get_current_user_context),
):
    """Returns measured availability, data coverage, and remaining error budget."""
    if not user.can_access_tenant(tenant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot view SLA reports for another tenant.")

    if not user.has_permission(Permission.SLA_READ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied: sla.read required.")

    rep = _sla_engine.calculate_sla_report(
        tenant_id=tenant_id,
        service_id=service_id,
        start_time_utc=start_utc,
        end_time_utc=end_utc,
    )
    return rep.to_dict()
