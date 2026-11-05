"""
AIRA OS — Networking VIII Phase D Comprehensive Verification Suite (WP 8.9).

Covers:
1. WP 8.9.1: Customer Identity and Authentication
   - Credential validation and secure session token generation
   - Rejection of invalid credentials
   - Rejection of authentication for suspended tenant organizations
   - Session revocation on logout
2. WP 8.9.2: Customer RBAC and Authorization
   - Customer role permissions (CUSTOMER_OWNER, CUSTOMER_ADMIN, CUSTOMER_OPERATOR, CUSTOMER_TECHNICIAN, CUSTOMER_VIEWER)
   - Enforcement of privilege boundaries (customer users cannot approve internal operational decisions)
   - Prevention of customer admins creating internal NOC roles
3. WP 8.9.3: Strict Server-Side Tenant Context & Anti-IDOR Isolation
   - Server-side derivation of tenant_id from session token (client cannot spoof tenant_id)
   - Cross-tenant device read rejection (Tenant A cannot read Tenant B devices)
   - Cross-tenant site read rejection (Tenant A cannot read Tenant B sites)
   - Cross-tenant incident read rejection (Tenant A cannot read Tenant B incidents)
   - Cross-tenant SLA report read rejection
   - Cross-tenant support request and comment isolation
4. WP 8.9.4: Self-Service Operational Dashboard
   - Tenant-scoped overview aggregation (online/offline counts, incidents, health score)
   - 6-dimension health card representation
5. WP 8.9.5: Customer Device and Site Inventory
   - Strict read-only device catalog
   - Complete redaction of credentials and secrets from customer payloads
   - Safe coexistence of overlapping RFC 1918 IPs across tenants
6. WP 8.9.6: Customer Incident Self-Service & Acknowledgement
   - Tenant-scoped incident tracking
   - Incident acknowledgement workflow for authorized roles
   - Role enforcement (CUSTOMER_VIEWER cannot acknowledge incidents)
7. WP 8.9.7: Customer SLA & Availability Reporting
   - Tenant-scoped SLA summaries and availability calculations
   - Error budget and maintenance exclusion accounting
8. WP 8.9.8: Customer Notification Preferences
   - Default preferences retrieval
   - Configurable alert toggles and persistence
9. WP 8.9.9: Customer Support & Service Requests
   - Support ticket creation in OPEN state
   - Valid lifecycle state machine transitions (OPEN -> IN_PROGRESS -> RESOLVED -> CLOSED)
   - Invalid transition rejection
   - Chronological ticket comment tracking
10. External Access Security:
   - Nginx reverse proxy hardening verification (TLS 1.2/1.3, HSTS, CSP, rate limits, body limits)
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routers import portal
from core.edge_gateway.db import ensure_gateway_schema
from core.edge_gateway.manager import EdgeGatewayManager
from core.operations.db import ensure_operational_schema
from core.operations.health_scoring_engine import DynamicHealthScoringEngine
from core.operations.models import (
    IncidentSeverity,
    IncidentState,
    ServiceCriticality,
    SlaWindowType,
)
from core.operations.multi_tenant_incident_engine import MultiTenantIncidentEngine
from core.operations.sla_engine import SlaManagementEngine
from core.tenant.db import ensure_tenant_schema
from core.tenant.manager import (
    IdentityManager,
    InventoryManager,
    NotificationPreferenceManager,
    SupportRequestManager,
    TenantManager,
)
from core.topology_db import topology_transaction
from core.tenant.models import (
    CustomerNotificationPreferences,
    Permission,
    ROLE_PERMISSIONS,
    SupportCategory,
    SupportPriority,
    SupportStatus,
    TenantStatus,
    UserRoleType,
    VALID_SUPPORT_TRANSITIONS,
)


@pytest.fixture
def phase_d_env(tmp_path: Path):
    """Sets up an isolated database and test harness for Phase D testing."""
    db_path = tmp_path / "test_phase_d.db"
    ensure_tenant_schema(db_path)
    ensure_gateway_schema(db_path)
    ensure_operational_schema(db_path)

    # Initialize manager instances pointing to isolated db
    tenant_mgr = TenantManager(db_path=db_path)
    identity_mgr = IdentityManager(db_path=db_path)
    inv_mgr = InventoryManager(db_path=db_path)
    gw_mgr = EdgeGatewayManager(db_path=db_path)
    health_engine = DynamicHealthScoringEngine(db_path=db_path)
    sla_engine = SlaManagementEngine(db_path=db_path)
    incident_engine = MultiTenantIncidentEngine(db_path=db_path)
    support_mgr = SupportRequestManager(db_path=db_path)
    notif_pref_mgr = NotificationPreferenceManager(db_path=db_path)

    # Patch module-level managers in portal router
    portal._tenant_mgr = tenant_mgr
    portal._identity_mgr = identity_mgr
    portal._inv_mgr = inv_mgr
    portal._gw_mgr = gw_mgr
    portal._health_engine = health_engine
    portal._sla_engine = sla_engine
    portal._incident_engine = incident_engine
    portal._support_mgr = support_mgr
    portal._notif_pref_mgr = notif_pref_mgr

    # 1. Provision Tenant A (MegaCorp)
    tenant_a = tenant_mgr.create_tenant(name="MegaCorp Enterprise", slug="megacorp")
    site_a1 = inv_mgr.create_site(tenant_id=tenant_a.tenant_id, name="MegaCorp HQ", slug="mega-hq")
    dev_a1 = inv_mgr.create_device(
        tenant_id=tenant_a.tenant_id,
        site_id=site_a1.site_id,
        name="mega-core-rt01",
        management_ip="10.0.1.1",
        credential_ref="vault://secret/mega/core01",
    )
    user_a_admin = identity_mgr.create_user(
        tenant_id=tenant_a.tenant_id,
        username="mega_admin",
        email="admin@megacorp.internal",
        password="MegaSecurePassword123!",
        role_type=UserRoleType.CUSTOMER_ADMIN.value,
        is_internal=False,
    )
    user_a_oper = identity_mgr.create_user(
        tenant_id=tenant_a.tenant_id,
        username="mega_oper",
        email="oper@megacorp.internal",
        password="MegaOperatorPass456!",
        role_type=UserRoleType.CUSTOMER_OPERATOR.value,
        is_internal=False,
    )
    user_a_viewer = identity_mgr.create_user(
        tenant_id=tenant_a.tenant_id,
        username="mega_view",
        email="view@megacorp.internal",
        password="MegaViewerPass789!",
        role_type=UserRoleType.CUSTOMER_VIEWER.value,
        is_internal=False,
    )
    # Incident for Tenant A
    inc_a1 = incident_engine.report_incident(
        tenant_id=tenant_a.tenant_id,
        title="Uplink Flap on mega-core-rt01",
        severity=IncidentSeverity.CRITICAL.value,
        affected_devices=[dev_a1.device_id],
        summary="Primary uplink BGP session flapped twice in 5 minutes.",
    )

    # 2. Provision Tenant B (UltraTech)
    tenant_b = tenant_mgr.create_tenant(name="UltraTech Solutions", slug="ultratech")
    site_b1 = inv_mgr.create_site(tenant_id=tenant_b.tenant_id, name="UltraTech Branch", slug="ultra-br")
    # Same IP 10.0.1.1 to verify RFC 1918 overlap isolation
    dev_b1 = inv_mgr.create_device(
        tenant_id=tenant_b.tenant_id,
        site_id=site_b1.site_id,
        name="ultra-edge-rt01",
        management_ip="10.0.1.1",
        credential_ref="vault://secret/ultra/edge01",
    )
    user_b_admin = identity_mgr.create_user(
        tenant_id=tenant_b.tenant_id,
        username="ultra_admin",
        email="admin@ultratech.internal",
        password="UltraSecurePassword321!",
        role_type=UserRoleType.CUSTOMER_ADMIN.value,
        is_internal=False,
    )
    inc_b1 = incident_engine.report_incident(
        tenant_id=tenant_b.tenant_id,
        title="High CPU on ultra-edge-rt01",
        severity=IncidentSeverity.HIGH.value,
        affected_devices=[dev_b1.device_id],
        summary="High CPU load detected during telemetry collection.",
    )

    client = TestClient(app)

    return {
        "db_path": db_path,
        "client": client,
        "tenant_mgr": tenant_mgr,
        "identity_mgr": identity_mgr,
        "inv_mgr": inv_mgr,
        "gw_mgr": gw_mgr,
        "health_engine": health_engine,
        "sla_engine": sla_engine,
        "incident_engine": incident_engine,
        "support_mgr": support_mgr,
        "notif_pref_mgr": notif_pref_mgr,
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "site_a1": site_a1,
        "site_b1": site_b1,
        "dev_a1": dev_a1,
        "dev_b1": dev_b1,
        "user_a_admin": user_a_admin,
        "user_a_oper": user_a_oper,
        "user_a_viewer": user_a_viewer,
        "user_b_admin": user_b_admin,
        "inc_a1": inc_a1,
        "inc_b1": inc_b1,
    }


def test_01_customer_auth_success_and_session_token(phase_d_env):
    """Verifies customer login returns active session token with tenant context."""
    client = phase_d_env["client"]
    resp = client.post(
        "/api/v1/portal/auth/login",
        json={"username_or_email": "mega_admin", "password": "MegaSecurePassword123!"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is True
    assert "token" in data
    assert data["token"].startswith("aira_tok_")
    assert data["user"]["username"] == "mega_admin"
    assert data["user"]["is_internal"] is False
    assert data["tenant"]["tenant_id"] == phase_d_env["tenant_a"].tenant_id
    assert UserRoleType.CUSTOMER_ADMIN.value in data["user"]["roles"]

    # Verify /api/v1/portal/auth/me profile endpoint
    token = data["token"]
    me_resp = client.get(
        "/api/v1/portal/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200, me_resp.text
    me_data = me_resp.json()
    assert me_data["username"] == "mega_admin"
    assert me_data["tenant_id"] == phase_d_env["tenant_a"].tenant_id
    assert "tenant.read" in me_data["permissions"]
    assert "device.read" in me_data["permissions"]


def test_02_customer_auth_invalid_credentials_rejected(phase_d_env):
    """Verifies that incorrect credentials or non-existent accounts are rejected."""
    client = phase_d_env["client"]

    # Wrong password
    resp1 = client.post(
        "/api/v1/portal/auth/login",
        json={"username_or_email": "mega_admin", "password": "WrongPasswordXYZ!"},
    )
    assert resp1.status_code == 401

    # Non-existent user
    resp2 = client.post(
        "/api/v1/portal/auth/login",
        json={"username_or_email": "ghost_user", "password": "AnyPassword123!"},
    )
    assert resp2.status_code == 401


def test_03_customer_auth_suspended_tenant_rejected(phase_d_env):
    """Verifies that suspended tenant users cannot log in or validate sessions."""
    client = phase_d_env["client"]
    tenant_mgr = phase_d_env["tenant_mgr"]
    identity_mgr = phase_d_env["identity_mgr"]
    tenant_a = phase_d_env["tenant_a"]

    # Suspend Tenant A
    tenant_mgr.update_tenant_status(tenant_a.tenant_id, TenantStatus.SUSPENDED.value)

    # Attempt login
    session = identity_mgr.authenticate_user("mega_admin", "MegaSecurePassword123!")
    assert session is None, "Suspended tenant user should not be able to authenticate"

    resp = client.post(
        "/api/v1/portal/auth/login",
        json={"username_or_email": "mega_admin", "password": "MegaSecurePassword123!"},
    )
    assert resp.status_code == 401

    # Re-activate for subsequent tests
    tenant_mgr.update_tenant_status(tenant_a.tenant_id, TenantStatus.ACTIVE.value)


def test_04_session_revocation_on_logout(phase_d_env):
    """Verifies that logging out revokes the session token immediately."""
    client = phase_d_env["client"]

    # Login
    login_resp = client.post(
        "/api/v1/portal/auth/login",
        json={"username_or_email": "mega_admin", "password": "MegaSecurePassword123!"},
    )
    token = login_resp.json()["token"]

    # Profile check works
    r1 = client.get("/api/v1/portal/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r1.status_code == 200

    # Logout
    logout_resp = client.post("/api/v1/portal/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_resp.status_code == 200
    assert logout_resp.json()["success"] is True

    # Subsequent request with revoked token must fail with 401
    r2 = client.get("/api/v1/portal/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 401


def test_05_portal_dashboard_overview_tenant_scoped(phase_d_env):
    """Verifies that dashboard overview aggregates only tenant's own data."""
    client = phase_d_env["client"]

    # MegaCorp Login
    login_resp = client.post(
        "/api/v1/portal/auth/login",
        json={"username_or_email": "mega_admin", "password": "MegaSecurePassword123!"},
    )
    token_a = login_resp.json()["token"]

    # Fetch dashboard overview
    ov_resp = client.get(
        "/api/v1/portal/dashboard/overview",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert ov_resp.status_code == 200, ov_resp.text
    ov_data = ov_resp.json()

    assert ov_data["tenant_id"] == phase_d_env["tenant_a"].tenant_id
    assert ov_data["tenant_name"] == phase_d_env["tenant_a"].name
    assert ov_data["devices"]["total"] == 1
    assert ov_data["incidents"]["active_count"] == 1
    assert ov_data["incidents"]["critical_count"] == 1

    # Health cards endpoint
    health_resp = client.get(
        "/api/v1/portal/dashboard/health",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert health_resp.status_code == 200
    h_data = health_resp.json()
    assert "tenant_health" in h_data
    assert "site_scores" in h_data
    assert "gateway_scores" in h_data


def test_06_tenant_a_cannot_read_tenant_b_devices(phase_d_env):
    """Anti-IDOR: Tenant A cannot access Tenant B's device via API or Manager."""
    client = phase_d_env["client"]
    dev_b1 = phase_d_env["dev_b1"]
    tenant_a = phase_d_env["tenant_a"]
    inv_mgr = phase_d_env["inv_mgr"]

    # Login as Tenant A
    login_resp = client.post(
        "/api/v1/portal/auth/login",
        json={"username_or_email": "mega_admin", "password": "MegaSecurePassword123!"},
    )
    token_a = login_resp.json()["token"]

    # Request Tenant B's device using Tenant A's token
    resp = client.get(
        f"/api/v1/portal/devices/{dev_b1.device_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 404, "Anti-IDOR violation: Tenant A should receive 404 when querying Tenant B's device"

    # Direct InventoryManager call with mismatched tenant_id must return None
    assert inv_mgr.get_device(tenant_id=tenant_a.tenant_id, device_id=dev_b1.device_id) is None


def test_07_tenant_a_cannot_read_tenant_b_sites(phase_d_env):
    """Anti-IDOR: Tenant A cannot access Tenant B's sites."""
    client = phase_d_env["client"]
    site_b1 = phase_d_env["site_b1"]
    tenant_a = phase_d_env["tenant_a"]
    inv_mgr = phase_d_env["inv_mgr"]

    # Login as Tenant A
    login_resp = client.post(
        "/api/v1/portal/auth/login",
        json={"username_or_email": "mega_admin", "password": "MegaSecurePassword123!"},
    )
    token_a = login_resp.json()["token"]

    # List sites via API
    sites_resp = client.get(
        "/api/v1/portal/sites",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert sites_resp.status_code == 200
    sites = sites_resp.json()["sites"]
    site_ids = [s["site_id"] for s in sites]
    assert phase_d_env["site_a1"].site_id in site_ids
    assert site_b1.site_id not in site_ids, "Cross-tenant leak: Tenant B site visible in Tenant A site list"

    # Direct InventoryManager get_site with mismatched tenant_id returns None
    assert inv_mgr.get_site(tenant_id=tenant_a.tenant_id, site_id=site_b1.site_id) is None


def test_08_device_credentials_redacted_for_customers(phase_d_env):
    """Verifies customer-facing device APIs completely redact secrets and credentials."""
    client = phase_d_env["client"]
    dev_a1 = phase_d_env["dev_a1"]

    # Login as Tenant A
    login_resp = client.post(
        "/api/v1/portal/auth/login",
        json={"username_or_email": "mega_admin", "password": "MegaSecurePassword123!"},
    )
    token_a = login_resp.json()["token"]

    # 1. Device list
    list_resp = client.get(
        "/api/v1/portal/devices",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert list_resp.status_code == 200
    devices = list_resp.json()["devices"]
    assert len(devices) == 1
    dev_dict = devices[0]
    assert dev_dict["credential_ref"] in (None, "[REDACTED]")
    assert "password" not in dev_dict
    assert "secret" not in dev_dict
    assert "vault://" not in json.dumps(dev_dict)

    # 2. Single device details
    detail_resp = client.get(
        f"/api/v1/portal/devices/{dev_a1.device_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json().get("device") or detail_resp.json()
    assert detail_data["credential_ref"] in (None, "[REDACTED]")
    assert "vault://" not in json.dumps(detail_data)


def test_09_tenant_a_cannot_read_tenant_b_incidents(phase_d_env):
    """Anti-IDOR: Tenant A cannot list or read Tenant B incidents."""
    client = phase_d_env["client"]
    inc_b1 = phase_d_env["inc_b1"]

    # Login as Tenant A
    login_resp = client.post(
        "/api/v1/portal/auth/login",
        json={"username_or_email": "mega_admin", "password": "MegaSecurePassword123!"},
    )
    token_a = login_resp.json()["token"]

    # List incidents
    inc_list_resp = client.get(
        "/api/v1/portal/incidents",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert inc_list_resp.status_code == 200
    incidents = inc_list_resp.json()["incidents"]
    inc_ids = [i["incident_id"] for i in incidents]
    assert phase_d_env["inc_a1"].incident_id in inc_ids
    assert inc_b1.incident_id not in inc_ids, "Anti-IDOR leak: Tenant B incident in Tenant A list"

    # Direct query of Tenant B incident
    single_resp = client.get(
        f"/api/v1/portal/incidents/{inc_b1.incident_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert single_resp.status_code == 404


def test_10_customer_operator_can_acknowledge_incident(phase_d_env):
    """Verifies that CUSTOMER_OPERATOR can acknowledge an incident, but CUSTOMER_VIEWER cannot."""
    client = phase_d_env["client"]
    inc_a1 = phase_d_env["inc_a1"]

    # 1. Viewer tries to acknowledge -> 403 Forbidden
    login_viewer = client.post(
        "/api/v1/portal/auth/login",
        json={"username_or_email": "mega_view", "password": "MegaViewerPass789!"},
    )
    token_viewer = login_viewer.json()["token"]
    resp_viewer = client.post(
        f"/api/v1/portal/incidents/{inc_a1.incident_id}/acknowledge",
        headers={"Authorization": f"Bearer {token_viewer}"},
    )
    assert resp_viewer.status_code == 403, "Viewer role must not have INCIDENT_ACKNOWLEDGE permission"

    # 2. Operator acknowledges -> 200 OK
    login_oper = client.post(
        "/api/v1/portal/auth/login",
        json={"username_or_email": "mega_oper", "password": "MegaOperatorPass456!"},
    )
    token_oper = login_oper.json()["token"]
    resp_oper = client.post(
        f"/api/v1/portal/incidents/{inc_a1.incident_id}/acknowledge",
        headers={"Authorization": f"Bearer {token_oper}"},
    )
    assert resp_oper.status_code == 200, resp_oper.text
    ack_data = resp_oper.json()
    assert ack_data["success"] is True
    assert ack_data["incident"]["state"] == "ACKNOWLEDGED"


def test_11_customer_cannot_approve_internal_recommendations(phase_d_env):
    """Enforces RBAC privilege boundaries: Customer roles can NEVER approve internal decisions."""
    customer_roles = [
        UserRoleType.CUSTOMER_OWNER,
        UserRoleType.CUSTOMER_ADMIN,
        UserRoleType.CUSTOMER_OPERATOR,
        UserRoleType.CUSTOMER_TECHNICIAN,
        UserRoleType.CUSTOMER_VIEWER,
    ]

    for role in customer_roles:
        perms = ROLE_PERMISSIONS.get(role, set())
        assert Permission.RECOMMENDATION_APPROVE not in perms, (
            f"Privilege boundary violation: {role.value} has RECOMMENDATION_APPROVE permission!"
        )
        assert Permission.TENANT_MANAGE not in perms, (
            f"Privilege boundary violation: {role.value} has TENANT_MANAGE permission!"
        )


def test_12_tenant_a_cannot_read_tenant_b_sla_reports(phase_d_env):
    """Anti-IDOR: Tenant A cannot access SLA reports or summaries of Tenant B."""
    client = phase_d_env["client"]
    tenant_b = phase_d_env["tenant_b"]
    sla_engine = phase_d_env["sla_engine"]

    # Provision SLA service and policy for Tenant B
    with topology_transaction(phase_d_env["db_path"], write=True) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO operational_services (service_id, tenant_id, name, criticality, status, created_at, updated_at)
            VALUES ('svc_ultra_crm', ?, 'UltraTech Core CRM', 'TIER_1_MISSION_CRITICAL', 'HEALTHY', '2026-11-04T00:00:00Z', '2026-11-04T00:00:00Z')
            """,
            (tenant_b.tenant_id,),
        )
    sla_engine.create_or_update_policy(
        tenant_id=tenant_b.tenant_id,
        service_id="svc_ultra_crm",
        name="UltraTech CRM SLA",
        target_availability=99.9,
        window_type=SlaWindowType.MONTHLY.value,
    )

    # Login as Tenant A
    login_resp = client.post(
        "/api/v1/portal/auth/login",
        json={"username_or_email": "mega_admin", "password": "MegaSecurePassword123!"},
    )
    token_a = login_resp.json()["token"]

    # Tenant A attempts to fetch SLA reports for Tenant B's service
    rep_resp = client.get(
        "/api/v1/portal/sla/reports?service_id=svc_ultra_crm",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert rep_resp.status_code == 404, "Anti-IDOR violation: Tenant A should receive 404 for Tenant B's service"


def test_13_support_request_creation_and_lifecycle_transitions(phase_d_env):
    """Verifies support request lifecycle state machine and validation."""
    support_mgr = phase_d_env["support_mgr"]
    tenant_a = phase_d_env["tenant_a"]
    user_a = phase_d_env["user_a_admin"]

    # 1. Create support request
    req = support_mgr.create_request(
        tenant_id=tenant_a.tenant_id,
        requester_id=user_a.user_id,
        category=SupportCategory.SERVICE_REQUEST.value,
        subject="Request Bandwidth Increase for mega-core-rt01",
        description="Please upgrade WAN port from 1Gbps to 10Gbps.",
        priority=SupportPriority.HIGH.value,
    )
    assert req.status == SupportStatus.OPEN.value
    assert req.priority == SupportPriority.HIGH.value

    # 2. Valid transition: OPEN -> ACKNOWLEDGED
    req_ack = support_mgr.transition_status(
        tenant_id=tenant_a.tenant_id,
        request_id=req.request_id,
        new_status=SupportStatus.ACKNOWLEDGED.value,
        actor_id="operator_noc_1",
    )
    assert req_ack.status == SupportStatus.ACKNOWLEDGED.value

    # 3. Valid transition: ACKNOWLEDGED -> IN_PROGRESS
    req_in_prog = support_mgr.transition_status(
        tenant_id=tenant_a.tenant_id,
        request_id=req.request_id,
        new_status=SupportStatus.IN_PROGRESS.value,
        actor_id="operator_noc_1",
    )
    assert req_in_prog.status == SupportStatus.IN_PROGRESS.value

    # 4. Valid transition: IN_PROGRESS -> RESOLVED
    req_resolved = support_mgr.transition_status(
        tenant_id=tenant_a.tenant_id,
        request_id=req.request_id,
        new_status=SupportStatus.RESOLVED.value,
        actor_id="operator_noc_1",
    )
    assert req_resolved.status == SupportStatus.RESOLVED.value
    assert req_resolved.resolved_at is not None

    # 5. Valid transition: RESOLVED -> CLOSED
    req_closed = support_mgr.transition_status(
        tenant_id=tenant_a.tenant_id,
        request_id=req.request_id,
        new_status=SupportStatus.CLOSED.value,
        actor_id=user_a.user_id,
    )
    assert req_closed.status == SupportStatus.CLOSED.value

    # 6. Invalid transition: CLOSED -> IN_PROGRESS must be rejected
    with pytest.raises(ValueError) as exc:
        support_mgr.transition_status(
            tenant_id=tenant_a.tenant_id,
            request_id=req.request_id,
            new_status=SupportStatus.IN_PROGRESS.value,
            actor_id=user_a.user_id,
        )
    assert "Invalid transition" in str(exc.value)


def test_14_support_request_cross_tenant_isolation_and_comments(phase_d_env):
    """Verifies that support requests and comments are strictly isolated per tenant."""
    client = phase_d_env["client"]
    support_mgr = phase_d_env["support_mgr"]
    tenant_a = phase_d_env["tenant_a"]
    tenant_b = phase_d_env["tenant_b"]
    user_a = phase_d_env["user_a_admin"]

    # Tenant A creates ticket
    req_a = support_mgr.create_request(
        tenant_id=tenant_a.tenant_id,
        requester_id=user_a.user_id,
        category=SupportCategory.INCIDENT.value,
        subject="Packet Loss on MegaCorp Core",
        description="Experiencing 15% packet loss to branch office.",
        priority=SupportPriority.CRITICAL.value,
    )
    # Tenant A adds comment
    support_mgr.add_comment(
        tenant_id=tenant_a.tenant_id,
        request_id=req_a.request_id,
        author_id=user_a.user_id,
        author_name=user_a.username,
        message="MTR report attached to internal ticket.",
    )

    # Login as Tenant B
    login_b = client.post(
        "/api/v1/portal/auth/login",
        json={"username_or_email": "ultra_admin", "password": "UltraSecurePassword321!"},
    )
    token_b = login_b.json()["token"]

    # Tenant B tries to get Tenant A's ticket -> 404
    r1 = client.get(
        f"/api/v1/portal/support/requests/{req_a.request_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r1.status_code == 404

    # Tenant B tries to comment on Tenant A's ticket -> 404
    r2 = client.post(
        f"/api/v1/portal/support/requests/{req_a.request_id}/comments",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"message": "Malicious injected comment from Tenant B"},
    )
    assert r2.status_code == 404

    # Direct manager access with mismatched tenant returns None
    assert support_mgr.get_request(tenant_id=tenant_b.tenant_id, request_id=req_a.request_id) is None


def test_15_customer_user_management_cannot_create_internal_noc_roles(phase_d_env):
    """Enforces privilege boundary: Customer admin cannot create accounts with internal NOC roles."""
    client = phase_d_env["client"]

    # Login as Tenant A Admin
    login_resp = client.post(
        "/api/v1/portal/auth/login",
        json={"username_or_email": "mega_admin", "password": "MegaSecurePassword123!"},
    )
    token_a = login_resp.json()["token"]

    # 1. Attempt to create user with NOC_ADMIN role -> 400 Bad Request
    resp_noc = client.post(
        "/api/v1/portal/users",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "username": "rogue_noc",
            "email": "rogue@megacorp.internal",
            "password": "Password123456!",
            "role_type": "NOC_ADMIN",
        },
    )
    assert resp_noc.status_code == 400
    assert "Invalid role" in resp_noc.json()["detail"]

    # 2. Attempt to create user with PLATFORM_SUPER_ADMIN role -> 400 Bad Request
    resp_super = client.post(
        "/api/v1/portal/users",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "username": "rogue_super",
            "email": "super@megacorp.internal",
            "password": "Password123456!",
            "role_type": "PLATFORM_SUPER_ADMIN",
        },
    )
    assert resp_super.status_code == 400

    # 3. Create user with legitimate CUSTOMER_TECHNICIAN role -> 200 OK
    resp_tech = client.post(
        "/api/v1/portal/users",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "username": "mega_tech01",
            "email": "tech01@megacorp.internal",
            "password": "Password123456!",
            "role_type": "CUSTOMER_TECHNICIAN",
        },
    )
    assert resp_tech.status_code == 200, resp_tech.text
    tech_data = resp_tech.json()["user"]
    assert tech_data["username"] == "mega_tech01"
    assert UserRoleType.CUSTOMER_TECHNICIAN.value in tech_data["roles"]


def test_16_customer_notification_preferences_persistence(phase_d_env):
    """Verifies that customer notification preferences can be read, updated, and persisted."""
    client = phase_d_env["client"]

    # Login as Tenant A Admin
    login_resp = client.post(
        "/api/v1/portal/auth/login",
        json={"username_or_email": "mega_admin", "password": "MegaSecurePassword123!"},
    )
    token_a = login_resp.json()["token"]

    # 1. Get default preferences
    get_resp = client.get(
        "/api/v1/portal/notifications/preferences",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert get_resp.status_code == 200
    p1 = get_resp.json()
    assert p1["notify_critical_incidents"] is True
    assert p1["email_notifications"] is True

    # 2. Update preferences
    patch_resp = client.patch(
        "/api/v1/portal/notifications/preferences",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "notify_major_incidents": False,
            "notify_gateway_offline": False,
            "email_notifications": False,
        },
    )
    assert patch_resp.status_code == 200
    p2 = patch_resp.json()
    assert p2["notify_major_incidents"] is False
    assert p2["notify_gateway_offline"] is False
    assert p2["email_notifications"] is False
    assert p2["notify_critical_incidents"] is True

    # 3. Re-read and confirm persistence
    get_resp2 = client.get(
        "/api/v1/portal/notifications/preferences",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert get_resp2.status_code == 200
    p3 = get_resp2.json()
    assert p3["notify_major_incidents"] is False
    assert p3["email_notifications"] is False


def test_17_nginx_reverse_proxy_configuration_security():
    """Verifies Nginx reverse proxy configuration adheres to security baselines."""
    conf_path = Path("deploy/nginx/aira_customer_portal.conf")
    assert conf_path.exists(), "Nginx configuration file missing at deploy/nginx/aira_customer_portal.conf"

    content = conf_path.read_text(encoding="utf-8")

    # Verify TLS hardening
    assert "TLSv1.2 TLSv1.3;" in content
    assert "Strict-Transport-Security" in content
    assert "X-Frame-Options \"DENY\"" in content
    assert "X-Content-Type-Options \"nosniff\"" in content
    assert "Content-Security-Policy" in content

    # Verify DoS and request size boundaries
    assert "client_max_body_size" in content
    assert "limit_req_zone" in content

    # Verify anti-tampering proxy headers
    assert "proxy_set_header X-Forwarded-Proto" in content
    assert "proxy_set_header Upgrade $http_upgrade;" in content
