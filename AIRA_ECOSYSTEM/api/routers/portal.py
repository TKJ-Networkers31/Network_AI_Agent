"""
AIRA OS — Customer Self-Service Portal FastAPI Router (Networking VIII / WP 8.9).

Exposes secure, tenant-isolated REST endpoints for:
- WP 8.9.1: Customer Authentication & Session Management
- WP 8.9.2 & WP 8.9.3: RBAC & Strict Server-Side Tenant Scoping (Anti-IDOR)
- WP 8.9.4: Self-Service Operational Overview & Health Dashboard
- WP 8.9.5: Customer Device and Site Inventory (Read-Only, Redacted Secrets)
- WP 8.9.6: Customer Incident Self-Service & Acknowledgement
- WP 8.9.7: Customer SLA Performance & Availability Reports
- WP 8.9.8: Customer Notification Preferences
- WP 8.9.9: Customer Support Requests & Collaboration Desk
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from core.edge_gateway.manager import EdgeGatewayManager
from core.operations.health_scoring_engine import DynamicHealthScoringEngine
from core.operations.models import SlaStatusType
from core.operations.multi_tenant_incident_engine import MultiTenantIncidentEngine
from core.operations.sla_engine import SlaManagementEngine
from core.tenant.manager import (
    IdentityManager,
    InventoryManager,
    NotificationPreferenceManager,
    SupportRequestManager,
    TenantManager,
)
from core.tenant.models import (
    CustomerNotificationPreferences,
    Permission,
    SupportCategory,
    SupportPriority,
    SupportRequest,
    SupportRequestComment,
    SupportStatus,
    TenantContext,
    UserRoleType,
)
from core.topology_db import topology_transaction

logger = logging.getLogger("aira.api.portal")

router = APIRouter(prefix="/api/v1/portal", tags=["customer_portal"])

# Canonical engine instances
_tenant_mgr = TenantManager()
_identity_mgr = IdentityManager()
_inv_mgr = InventoryManager()
_gw_mgr = EdgeGatewayManager()
_health_engine = DynamicHealthScoringEngine()
_sla_engine = SlaManagementEngine()
_incident_engine = MultiTenantIncidentEngine()
_support_mgr = SupportRequestManager()
_notif_pref_mgr = NotificationPreferenceManager()


# ---------------------------------------------------------------------------
# Pydantic Request Models
# ---------------------------------------------------------------------------

class CustomerLoginRequest(BaseModel):
    username_or_email: str
    password: str


class CreateSupportRequestInput(BaseModel):
    category: str = Field(..., description="INCIDENT, SERVICE_REQUEST, BILLING, GENERAL, CHANGE")
    subject: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=5, max_length=4000)
    priority: str = Field(default="MEDIUM", description="LOW, MEDIUM, HIGH, CRITICAL")


class AddCommentInput(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class CreateTenantUserInput(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., min_length=5, max_length=100)
    password: str = Field(..., min_length=8)
    role_type: str = Field(default="CUSTOMER_OPERATOR", description="CUSTOMER_ADMIN, CUSTOMER_OPERATOR, CUSTOMER_TECHNICIAN, CUSTOMER_VIEWER")


class UpdateNotificationPreferencesInput(BaseModel):
    notify_critical_incidents: Optional[bool] = None
    notify_major_incidents: Optional[bool] = None
    notify_service_degradation: Optional[bool] = None
    notify_gateway_offline: Optional[bool] = None
    notify_sla_breach: Optional[bool] = None
    email_notifications: Optional[bool] = None
    in_app_notifications: Optional[bool] = None


# ---------------------------------------------------------------------------
# Strict Tenant Context Dependency
# ---------------------------------------------------------------------------

def get_current_portal_context(
    authorization: Optional[str] = Header(None),
    tenant_override: Optional[str] = Query(None, alias="tenant_id"),
) -> TenantContext:
    """
    Resolves authenticated TenantContext for customer portal operations.
    Enforces that customer users can NEVER access another organization.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.split(" ", 1)[1]
    ctx = _identity_mgr.validate_session_token(token)
    if not ctx:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session token is invalid or has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # For customer users, ctx.tenant_id is strictly authoritative
    if not ctx.is_internal:
        if not ctx.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Customer account is not associated with an active tenant organization.",
            )
        return ctx

    # Internal NOC operators can inspect a specific tenant if requested
    if ctx.is_internal and tenant_override:
        return TenantContext(
            user_id=ctx.user_id,
            username=ctx.username,
            is_internal=True,
            tenant_id=tenant_override,
            roles=ctx.roles,
            permissions=ctx.permissions,
        )

    return ctx


def require_permission(permission: Permission):
    """Factory creating dependency to enforce granular RBAC permissions."""
    def _perm_checker(ctx: TenantContext = Depends(get_current_portal_context)) -> TenantContext:
        if not ctx.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Missing required permission '{permission.value}'.",
            )
        return ctx
    return _perm_checker


# ---------------------------------------------------------------------------
# 1. Authentication & Session Management (WP 8.9.1)
# ---------------------------------------------------------------------------

@router.post("/auth/login", summary="Customer portal user login")
def portal_login(payload: CustomerLoginRequest):
    """Authenticates credentials and establishes a customer session."""
    session = _identity_mgr.authenticate_user(
        username_or_email=payload.username_or_email,
        password=payload.password,
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    # Resolve tenant metadata
    tenant_info = None
    if session.tenant_id:
        t = _tenant_mgr.get_tenant(session.tenant_id)
        if t:
            tenant_info = t.to_dict()

    return {
        "success": True,
        "token": session.token,
        "session_id": session.session_id,
        "user": {
            "user_id": session.user_id,
            "username": session.username,
            "is_internal": session.is_internal,
            "roles": session.roles,
            "permissions": session.permissions,
        },
        "tenant": tenant_info,
        "expires_at_utc": session.expires_at_utc,
    }


@router.post("/auth/logout", summary="Customer portal logout")
def portal_logout(
    authorization: Optional[str] = Header(None),
    ctx: TenantContext = Depends(get_current_portal_context),
):
    """Invalidates active session token."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
        _identity_mgr.revoke_token(token)
    return {"success": True, "message": "Session invalidated successfully."}


@router.get("/auth/me", summary="Current user profile and organization info")
def portal_get_current_user(ctx: TenantContext = Depends(get_current_portal_context)):
    """Returns authenticated profile, organization metadata, and permissions."""
    tenant_info = None
    if ctx.tenant_id:
        t = _tenant_mgr.get_tenant(ctx.tenant_id)
        if t:
            tenant_info = t.to_dict()

    return {
        "user_id": ctx.user_id,
        "username": ctx.username,
        "is_internal": ctx.is_internal,
        "tenant_id": ctx.tenant_id,
        "roles": ctx.roles,
        "permissions": sorted(list(ctx.permissions)),
        "tenant": tenant_info,
    }


# ---------------------------------------------------------------------------
# 2. Operational Overview & Health Dashboard (WP 8.9.4)
# ---------------------------------------------------------------------------

@router.get("/dashboard/overview", summary="Customer organization overview")
def portal_get_dashboard_overview(ctx: TenantContext = Depends(require_permission(Permission.TENANT_READ))):
    """Aggregates high-level inventory, incident, gateway, and SLA stats for customer."""
    tenant_id = ctx.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required.")

    # 1. Device counts
    devices = _inv_mgr.list_devices(tenant_id=tenant_id)
    total_devices = len(devices)
    online_devices = sum(1 for d in devices if d.status == "ACTIVE")
    offline_devices = sum(1 for d in devices if d.status in ("INACTIVE", "UNREACHABLE"))

    # 2. Gateway status
    gateways = _gw_mgr.list_gateways(tenant_id=tenant_id)
    total_gateways = len(gateways)
    online_gateways = sum(1 for g in gateways if g.status == "ACTIVE")

    # 3. Active Incidents
    incidents = _incident_engine.list_incidents(tenant_id=tenant_id, limit=100)
    active_incidents = [i for i in incidents if i.state in ("DETECTED", "ACKNOWLEDGED", "INVESTIGATING")]
    critical_incidents = [i for i in active_incidents if i.severity == "CRITICAL"]

    # 4. Overall Tenant Health Score
    tenant_health = _health_engine.score_tenant(tenant_id=tenant_id)

    # 5. SLA availability overview (current 30d window)
    now_epoch = time.time()
    start_iso = datetime.fromtimestamp(now_epoch - (30 * 86400), tz=timezone.utc).isoformat()
    end_iso = datetime.fromtimestamp(now_epoch, tz=timezone.utc).isoformat()

    # Look up primary business service if any
    sla_summary = {"status": "NO_POLICY", "measured_availability": None}
    with topology_transaction(_identity_mgr.db_path, write=False) as conn:
        svc_row = conn.execute(
            "SELECT service_id, name FROM operational_services WHERE tenant_id = ? LIMIT 1",
            (tenant_id,),
        ).fetchone()

    if svc_row:
        try:
            report = _sla_engine.calculate_sla_report(
                tenant_id=tenant_id,
                service_id=svc_row["service_id"],
                start_time_utc=start_iso,
                end_time_utc=end_iso,
            )
            sla_summary = {
                "service_id": svc_row["service_id"],
                "service_name": svc_row["name"],
                "target_availability": report.target_availability,
                "measured_availability": report.measured_availability,
                "status": report.status,
                "error_budget_remaining_percent": report.error_budget_remaining_percent,
            }
        except Exception as e:
            logger.warning("Could not calculate quick SLA for tenant %s: %s", tenant_id, e)

    t = _tenant_mgr.get_tenant(tenant_id)
    tenant_name = t.name if t else tenant_id

    return {
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "devices": {
            "total": total_devices,
            "online": online_devices,
            "offline": offline_devices,
        },
        "inventory": {
            "total_devices": total_devices,
            "online_devices": online_devices,
            "offline_devices": offline_devices,
            "total_gateways": total_gateways,
            "online_gateways": online_gateways,
        },
        "incidents": {
            "active_count": len(active_incidents),
            "critical_count": len(critical_incidents),
            "recent_incidents": [i.to_dict() for i in active_incidents[:5]],
        },
        "health": {
            "state": tenant_health.state,
            "score": tenant_health.score,
            "confidence": tenant_health.confidence,
            "contributing_factors": tenant_health.contributing_factors,
        },
        "sla": sla_summary,
    }


@router.get("/dashboard/health", summary="Multi-dimensional health score breakdown")
def portal_get_health_breakdown(ctx: TenantContext = Depends(require_permission(Permission.TENANT_READ))):
    """Returns detailed health score records across all 6 dimensions."""
    tenant_id = ctx.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required.")

    # Calculate live health components
    tenant_rec = _health_engine.score_tenant(tenant_id=tenant_id)
    sites = _inv_mgr.list_sites(tenant_id=tenant_id)
    gateways = _gw_mgr.list_gateways(tenant_id=tenant_id)

    site_scores = [_health_engine.score_site(tenant_id, s.site_id).to_dict() for s in sites[:10]]
    gateway_scores = [_health_engine.score_gateway(tenant_id, g.gateway_id).to_dict() for g in gateways[:10]]

    return {
        "tenant_health": tenant_rec.to_dict(),
        "site_scores": site_scores,
        "gateway_scores": gateway_scores,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# 3. Customer Sites & Devices Management (WP 8.9.5)
# ---------------------------------------------------------------------------

@router.get("/sites", summary="List authorized customer sites")
def portal_list_sites(
    ctx: TenantContext = Depends(require_permission(Permission.SITE_READ)),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Lists customer sites strictly scoped to tenant_id."""
    sites = _inv_mgr.list_sites(tenant_id=ctx.tenant_id)
    return {
        "tenant_id": ctx.tenant_id,
        "total": len(sites),
        "sites": [s.to_dict() for s in sites[offset : offset + limit]],
    }


@router.get("/devices", summary="List authorized customer devices")
def portal_list_devices(
    ctx: TenantContext = Depends(require_permission(Permission.DEVICE_READ)),
    site_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Lists network devices for customer with credentials redacted."""
    devices = _inv_mgr.list_devices(
        tenant_id=ctx.tenant_id,
        site_id=site_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    # Redact credentials and internal refs
    sanitized = []
    for d in devices:
        d_dict = d.to_dict()
        d_dict["credential_ref"] = "[REDACTED]"
        sanitized.append(d_dict)

    return {
        "tenant_id": ctx.tenant_id,
        "count": len(sanitized),
        "devices": sanitized,
    }


@router.get("/devices/{device_id}", summary="Get single device details")
def portal_get_device(
    device_id: str,
    ctx: TenantContext = Depends(require_permission(Permission.DEVICE_READ)),
):
    """Retrieves device details. Returns 404 if not found in customer tenant."""
    dev = _inv_mgr.get_device(tenant_id=ctx.tenant_id, device_id=device_id)
    if not dev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device '{device_id}' not found.",
        )
    d_dict = dev.to_dict()
    d_dict["credential_ref"] = "[REDACTED]"
    return d_dict


@router.get("/devices/{device_id}/traffic", summary="Get interface traffic metrics for device")
def portal_get_device_traffic(
    device_id: str,
    ctx: TenantContext = Depends(require_permission(Permission.DEVICE_READ)),
    range: str = Query("1h", description="Time range for metrics (e.g. 1h, 6h, 24h)"),
):
    """Retrieves interface traffic/metrics for a tenant device."""
    dev = _inv_mgr.get_device(tenant_id=ctx.tenant_id, device_id=device_id)
    if not dev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device '{device_id}' not found.",
        )
    from core.nms_engine import get_nms_engine
    engine = get_nms_engine()
    history = engine.get_interface_history(device_id=device_id, time_range=range)
    return {
        "success": True,
        "device_id": device_id,
        "tenant_id": ctx.tenant_id,
        "range": range,
        "interfaces": history,
    }


# ---------------------------------------------------------------------------
# 4. Incident Self-Service (WP 8.9.6)
# ---------------------------------------------------------------------------

@router.get("/incidents", summary="List customer incidents")
def portal_list_incidents(
    ctx: TenantContext = Depends(require_permission(Permission.INCIDENT_READ)),
    state_filter: Optional[str] = Query(None, alias="state"),
    severity_filter: Optional[str] = Query(None, alias="severity"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Lists operational incidents scoped strictly to customer."""
    incidents = _incident_engine.list_incidents(
        tenant_id=ctx.tenant_id,
        state=state_filter,
        severity=severity_filter,
        limit=limit,
        offset=offset,
    )
    # Sanitize internal diagnostic notes if any
    sanitized = []
    for inc in incidents:
        idict = inc.to_dict()
        # Ensure root_cause_analysis is customer-safe
        if not idict.get("root_cause_analysis"):
            idict["root_cause_analysis"] = "Investigasi otomatis sedang berlangsung oleh sistem monitoring."
        sanitized.append(idict)

    return {
        "tenant_id": ctx.tenant_id,
        "count": len(sanitized),
        "incidents": sanitized,
    }


@router.get("/incidents/{incident_id}", summary="Get incident details")
def portal_get_incident(
    incident_id: str,
    ctx: TenantContext = Depends(require_permission(Permission.INCIDENT_READ)),
):
    """Retrieves single incident details. Returns 404 if not found in customer tenant."""
    inc = _incident_engine.get_incident(tenant_id=ctx.tenant_id, incident_id=incident_id)
    if not inc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident '{incident_id}' not found.")
    return inc.to_dict()


@router.post("/incidents/{incident_id}/acknowledge", summary="Customer acknowledges incident")
def portal_acknowledge_incident(
    incident_id: str,
    ctx: TenantContext = Depends(require_permission(Permission.INCIDENT_ACKNOWLEDGE)),
):
    """Customer acknowledges awareness of active incident."""
    inc = _incident_engine.get_incident(tenant_id=ctx.tenant_id, incident_id=incident_id)
    if not inc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident '{incident_id}' not found.")

    if inc.state == "DETECTED":
        updated = _incident_engine.transition_incident(
            tenant_id=ctx.tenant_id,
            incident_id=incident_id,
            new_state="ACKNOWLEDGED",
            actor=f"CUSTOMER:{ctx.username}",
        )
        return {"success": True, "incident": updated.to_dict()}
    return {"success": True, "incident": inc.to_dict(), "message": "Incident already acknowledged."}


# ---------------------------------------------------------------------------
# 5. SLA & Availability Reporting (WP 8.9.7)
# ---------------------------------------------------------------------------

@router.get("/sla/summary", summary="Customer SLA summary")
def portal_get_sla_summary(ctx: TenantContext = Depends(require_permission(Permission.SLA_READ))):
    """Returns SLA compliance status for customer business services."""
    tenant_id = ctx.tenant_id
    with topology_transaction(_identity_mgr.db_path, write=False) as conn:
        svc_rows = conn.execute(
            "SELECT service_id, name, criticality, status FROM operational_services WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchall()

    services = []
    now_epoch = time.time()
    start_iso = datetime.fromtimestamp(now_epoch - (30 * 86400), tz=timezone.utc).isoformat()
    end_iso = datetime.fromtimestamp(now_epoch, tz=timezone.utc).isoformat()

    for sr in svc_rows:
        policy = _sla_engine.get_policy(tenant_id, sr["service_id"])
        target_avail = policy.target_availability if policy else 99.9
        try:
            report = _sla_engine.calculate_sla_report(tenant_id, sr["service_id"], start_iso, end_iso)
            measured = report.measured_availability
            status_val = report.status
            budget = report.error_budget_remaining_percent
        except Exception:
            measured = None
            status_val = "INSUFFICIENT_COVERAGE"
            budget = None

        services.append({
            "service_id": sr["service_id"],
            "name": sr["name"],
            "criticality": sr["criticality"],
            "target_availability": target_avail,
            "measured_availability": measured,
            "status": status_val,
            "error_budget_remaining_percent": budget,
        })

    return {
        "tenant_id": tenant_id,
        "period": "ROLLING_30_DAYS",
        "services": services,
    }


@router.get("/sla/reports", summary="Generate SLA availability report")
def portal_get_sla_report(
    service_id: str = Query(...),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    ctx: TenantContext = Depends(require_permission(Permission.SLA_READ)),
):
    """Calculates reproducible SLA report for a specific service."""
    # Anti-IDOR: verify service belongs strictly to customer's tenant
    with topology_transaction(_identity_mgr.db_path, write=False) as conn:
        svc = conn.execute(
            "SELECT service_id FROM operational_services WHERE service_id = ? AND tenant_id = ?",
            (service_id, ctx.tenant_id),
        ).fetchone()
        if not svc:
            raise HTTPException(status_code=404, detail=f"Service '{service_id}' not found for tenant '{ctx.tenant_id}'.")

    now_epoch = time.time()
    start_iso = start_time or datetime.fromtimestamp(now_epoch - (30 * 86400), tz=timezone.utc).isoformat()
    end_iso = end_time or datetime.fromtimestamp(now_epoch, tz=timezone.utc).isoformat()

    try:
        report = _sla_engine.calculate_sla_report(
            tenant_id=ctx.tenant_id,
            service_id=service_id,
            start_time_utc=start_iso,
            end_time_utc=end_iso,
        )
        return report.to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail=f"SLA policy or service '{service_id}' not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate SLA report: {str(e)}")


# ---------------------------------------------------------------------------
# 6. Customer Support Requests & Collaboration Desk (WP 8.9.9)
# ---------------------------------------------------------------------------

@router.get("/support/requests", summary="List customer support requests")
def portal_list_support_requests(
    ctx: TenantContext = Depends(require_permission(Permission.SUPPORT_READ)),
    status_filter: Optional[str] = Query(None, alias="status"),
    category_filter: Optional[str] = Query(None, alias="category"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Lists support tickets for customer organization."""
    reqs = _support_mgr.list_requests(
        tenant_id=ctx.tenant_id,
        status=status_filter,
        category=category_filter,
        limit=limit,
        offset=offset,
    )
    return {
        "tenant_id": ctx.tenant_id,
        "total": len(reqs),
        "requests": [r.to_dict() for r in reqs],
    }


@router.post("/support/requests", summary="Submit new customer support ticket")
def portal_create_support_request(
    payload: CreateSupportRequestInput,
    ctx: TenantContext = Depends(require_permission(Permission.SUPPORT_CREATE)),
):
    """Creates a new customer support ticket in OPEN state."""
    try:
        req = _support_mgr.create_request(
            tenant_id=ctx.tenant_id,
            requester_id=ctx.user_id,
            category=payload.category,
            subject=payload.subject,
            description=payload.description,
            priority=payload.priority,
        )
        return req.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/support/requests/{request_id}", summary="Get support ticket details")
def portal_get_support_request(
    request_id: str,
    ctx: TenantContext = Depends(require_permission(Permission.SUPPORT_READ)),
):
    """Retrieves ticket details and comments. Returns 404 if not found in customer tenant."""
    req = _support_mgr.get_request(tenant_id=ctx.tenant_id, request_id=request_id)
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Support request '{request_id}' not found.")
    return req.to_dict()


@router.post("/support/requests/{request_id}/comments", summary="Post comment on support ticket")
def portal_add_support_comment(
    request_id: str,
    payload: AddCommentInput,
    ctx: TenantContext = Depends(require_permission(Permission.SUPPORT_COMMENT)),
):
    """Posts a customer comment on an active support ticket."""
    try:
        comment = _support_mgr.add_comment(
            tenant_id=ctx.tenant_id,
            request_id=request_id,
            author_id=ctx.user_id,
            author_name=ctx.username,
            message=payload.message,
            is_internal=ctx.is_internal,
        )
        return comment.to_dict()
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Support request '{request_id}' not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# 7. Customer User Management (WP 8.9.2)
# ---------------------------------------------------------------------------

@router.get("/users", summary="List customer organization users")
def portal_list_users(ctx: TenantContext = Depends(require_permission(Permission.USER_MANAGE))):
    """Lists authorized users belonging to customer organization."""
    users = _identity_mgr.list_users(tenant_id=ctx.tenant_id)
    return {
        "tenant_id": ctx.tenant_id,
        "users": [
            {
                "user_id": u.user_id,
                "username": u.username,
                "email": u.email,
                "is_active": u.is_active,
                "created_at": u.created_at,
            }
            for u in users
        ],
    }


@router.post("/users", summary="Add new customer user")
def portal_create_user(
    payload: CreateTenantUserInput,
    ctx: TenantContext = Depends(require_permission(Permission.USER_MANAGE)),
):
    """Creates a new customer organization user. Forbids granting internal NOC roles."""
    allowed_customer_roles = {
        UserRoleType.CUSTOMER_ADMIN.value,
        UserRoleType.CUSTOMER_OPERATOR.value,
        UserRoleType.CUSTOMER_TECHNICIAN.value,
        UserRoleType.CUSTOMER_VIEWER.value,
    }
    role_target = payload.role_type.upper()
    if role_target not in allowed_customer_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role '{payload.role_type}'. Customer users may only assign: {sorted(list(allowed_customer_roles))}.",
        )

    try:
        user = _identity_mgr.create_user(
            username=payload.username,
            email=payload.email,
            password=payload.password,
            role_type=role_target,
            is_internal=False,
            tenant_id=ctx.tenant_id,
        )
        return {
            "success": True,
            "user": {
                "user_id": user.user_id,
                "username": user.username,
                "email": user.email,
                "role": role_target,
                "roles": [role_target],
                "tenant_id": user.tenant_id,
                "created_at": user.created_at,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# 8. Notification Preferences (WP 8.9.8)
# ---------------------------------------------------------------------------

@router.get("/notifications/preferences", summary="Get notification preferences")
def portal_get_notification_preferences(ctx: TenantContext = Depends(get_current_portal_context)):
    """Retrieves active user's notification preferences."""
    prefs = _notif_pref_mgr.get_preferences(tenant_id=ctx.tenant_id, user_id=ctx.user_id)
    return prefs.to_dict()


@router.patch("/notifications/preferences", summary="Update notification preferences")
def portal_update_notification_preferences(
    payload: UpdateNotificationPreferencesInput,
    ctx: TenantContext = Depends(require_permission(Permission.NOTIFICATION_MANAGE)),
):
    """Updates active user's notification toggles."""
    updated = _notif_pref_mgr.update_preferences(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        notify_critical_incidents=payload.notify_critical_incidents,
        notify_major_incidents=payload.notify_major_incidents,
        notify_service_degradation=payload.notify_service_degradation,
        notify_gateway_offline=payload.notify_gateway_offline,
        notify_sla_breach=payload.notify_sla_breach,
        email_notifications=payload.email_notifications,
        in_app_notifications=payload.in_app_notifications,
    )
    return updated.to_dict()
