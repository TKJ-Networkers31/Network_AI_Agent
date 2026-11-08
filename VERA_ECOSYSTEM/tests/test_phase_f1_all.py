"""
AIRA OS — Comprehensive Test Suite for Phase F.1
Architecture Simplification, User Management, Group-Based RBAC,
Network Data Ownership, User Activity Monitoring & AI Tool Authorization.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
import sqlite3
import pytest
from fastapi.testclient import TestClient

from api.main import app
from core.inventory_store import get_inventory_store
from core.topology_engine import get_topology_engine
from core.nms_engine import get_nms_engine
from core.tenant.manager import IdentityManager
from core.tenant.rbac_service import get_rbac_service, ALL_PERMISSIONS
from core.orchestrator import Orchestrator, TOOL_REQUIRED_PERMISSIONS
from core.events import current_event_scope, event_scope
from core import chat_sessions
from scripts.purge_operational_data import purge_operational_data

client = TestClient(app)
identity_mgr = IdentityManager()
rbac_svc = get_rbac_service()


@pytest.fixture(scope="module", autouse=True)
def ensure_clean_start():
    """Ensure operational data is purged to a clean state before testing."""
    purge_operational_data()
    from core.bootstrap_superadmin import bootstrap_superadmin
    bootstrap_superadmin(password="AdminPassword123!", force_reset=True, db_path=identity_mgr.db_path)
    yield
    purge_operational_data()


@pytest.fixture(scope="module")
def admin_token():
    """Authenticates as lingga_admin and returns bearer token."""
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "lingga_admin", "password": "AdminPassword123!"},
    )
    if login_res.status_code != 200:
        u = identity_mgr.get_user_by_username("lingga_admin")
        if not u:
            from core.bootstrap_superadmin import bootstrap_superadmin
            bootstrap_superadmin(password="AdminPassword123!", force_reset=True, db_path=identity_mgr.db_path)
            u = identity_mgr.get_user_by_username("lingga_admin")
        identity_mgr.change_user_password(u.user_id, "AdminPassword123!", reset_must_change=True)
        login_res = client.post(
            "/api/v1/auth/login",
            json={"username_or_email": "lingga_admin", "password": "AdminPassword123!"},
        )
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    return login_res.json()["token"]


# -----------------------------------------------------------------------------
# 1. Clean Start State Verification
# -----------------------------------------------------------------------------
def test_clean_start_state():
    """Verifies that all operational inventory, topology, and telemetry are 0 records."""
    inv = get_inventory_store()
    inv_res = inv.list_devices()
    assert inv_res["success"] is True
    assert inv_res["count"] == 0
    assert len(inv_res["devices"]) == 0

    topo = get_topology_engine()
    t_data = topo.get_topology()
    assert len(t_data["nodes"]) == 0
    assert len(t_data["edges"]) == 0

    # User accounts, groups, permissions preserved
    users = identity_mgr.list_users()
    assert len(users) >= 1
    admin_u = next((u for u in users if u["username"] == "lingga_admin"), None)
    assert admin_u is not None
    assert "SUPER_ADMIN" in admin_u["groups"]

    groups = rbac_svc.list_groups()
    assert len(groups) >= 6
    group_names = {g["name"] for g in groups}
    assert {"SUPER_ADMIN", "ADMIN", "NOC", "SOC", "NETWORK_ENGINEER", "READ_ONLY"}.issubset(group_names)


# -----------------------------------------------------------------------------
# 2. Mandatory Authentication (No Anonymous / Guest Access)
# -----------------------------------------------------------------------------
def test_mandatory_authentication():
    """Unauthenticated calls without Bearer tokens must return HTTP 401."""
    res_inv = client.get("/api/devices")
    assert res_inv.status_code == 401, f"Expected 401, got {res_inv.status_code}"

    res_topo = client.get("/api/topology")
    assert res_topo.status_code == 401, f"Expected 401, got {res_topo.status_code}"

    res_sess = client.get("/api/sessions")
    assert res_sess.status_code == 401, f"Expected 401, got {res_sess.status_code}"

    res_admin = client.get("/api/v1/admin/users")
    assert res_admin.status_code == 401, f"Expected 401, got {res_admin.status_code}"


# -----------------------------------------------------------------------------
# 3. Group-Based RBAC and Explicit DENY Precedence
# -----------------------------------------------------------------------------
def test_group_based_rbac_and_deny_precedence(admin_token):
    """
    Creates custom groups:
    - Group A has ALLOW 'config.apply'
    - Group B has DENY 'config.apply'
    Assigning both to a user must evaluate to NOT having 'config.apply' (DENY overrides ALLOW).
    """
    headers = {"Authorization": f"Bearer {admin_token}"}
    uid = uuid.uuid4().hex[:6]
    grp_a_name = f"GRP_ALLOW_{uid}"
    grp_b_name = f"GRP_DENY_{uid}"
    username = f"user_rbac_{uid}"

    # 1. Create Group A (ALLOW config.apply, devices.read)
    grp_a_res = client.post(
        "/api/v1/admin/groups",
        headers=headers,
        json={
          "name": grp_a_name,
          "description": "Allows config deploy",
          "permissions": [
            {"permission_id": "config.apply", "effect": "ALLOW"},
            {"permission_id": "devices.read", "effect": "ALLOW"},
          ],
        },
    )
    assert grp_a_res.status_code == 201

    # 2. Create Group B (DENY config.apply)
    grp_b_res = client.post(
        "/api/v1/admin/groups",
        headers=headers,
        json={
          "name": grp_b_name,
          "description": "Denies config deploy explicitly",
          "permissions": [
            {"permission_id": "config.apply", "effect": "DENY"},
          ],
        },
    )
    assert grp_b_res.status_code == 201

    # 3. Create test user with both groups
    usr_res = client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
          "username": username,
          "display_name": "Test RBAC Engineer",
          "password": "Password123!",
          "groups": [grp_a_name, grp_b_name],
        },
    )
    assert usr_res.status_code == 201
    test_user_id = usr_res.json()["user_id"]

    # 4. Verify effective permissions
    effective = rbac_svc.get_effective_permissions(test_user_id)
    assert "devices.read" in effective
    assert "config.apply" not in effective, "Explicit DENY must strictly override ALLOW!"

    # 5. SUPER_ADMIN group verification
    admin_effective = rbac_svc.get_effective_permissions_preview(["grp_super_admin"])
    assert len(admin_effective) >= 43


# -----------------------------------------------------------------------------
# 4. Backend-Enforced AI Tool Authorization
# -----------------------------------------------------------------------------
def test_backend_enforced_ai_tool_authorization(admin_token):
    """
    Tests that Orchestrator._execute_tool strictly enforces RBAC:
    - User in NOC group attempts to call apply_config -> blocked with permission error.
    - User in NETWORK_ENGINEER group -> permitted.
    """
    headers = {"Authorization": f"Bearer {admin_token}"}
    uid = uuid.uuid4().hex[:6]
    noc_uname = f"noc_user_{uid}"
    eng_uname = f"eng_user_{uid}"

    # Provision NOC user
    client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "username": noc_uname,
            "display_name": "NOC Operator",
            "password": "Password123!",
            "group_name": "NOC",
        },
    )
    noc_user = identity_mgr.get_user_by_username(noc_uname)
    assert noc_user is not None
    assert "NOC" in noc_user.groups

    # Provision Network Engineer user
    client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "username": eng_uname,
            "display_name": "Senior NetOps",
            "password": "Password123!",
            "group_name": "NETWORK_ENGINEER",
        },
    )
    eng_user = identity_mgr.get_user_by_username(eng_uname)
    assert eng_user is not None
    assert "NETWORK_ENGINEER" in eng_user.groups

    orchestrator = Orchestrator()

    # 1. Test under NOC user scope -> must be BLOCKED
    with event_scope(user_id=noc_user.user_id, username=noc_user.username):
        blocked_result = orchestrator._execute_tool(
            "apply_config",
            {"device_name": "R1", "commands": ["/system identity set name=Pwned"]},
        )
        assert blocked_result.get("success") is False
        err_msg = blocked_result.get("error", "")
        assert "Permission Denied" in err_msg or "tidak memiliki izin" in err_msg
        assert "config.apply" in err_msg

    # 2. Test under Network Engineer scope -> RBAC check passes
    with event_scope(user_id=eng_user.user_id, username=eng_user.username):
        eng_result = orchestrator._execute_tool(
            "apply_config",
            {"device_name": "R1", "commands": ["/system identity set name=Test"]},
        )
        err = eng_result.get("error", "")
        assert "Permission Denied" not in err, f"Network Engineer should have config.apply permission, got: {err}"
        assert "tidak memiliki izin" not in err


# -----------------------------------------------------------------------------
# 5. User Activity Monitoring, Heartbeat & Session Revocation
# -----------------------------------------------------------------------------
def test_user_activity_monitoring_and_session_revocation(admin_token):
    """
    Tests:
    - User login creates active session.
    - POST /api/v1/auth/heartbeat updates last_activity_at and confirms ONLINE status.
    - Session revocation immediately invalidates the session token (HTTP 401).
    - Status transitions to SESSION_EXPIRED or OFFLINE.
    """
    headers_adm = {"Authorization": f"Bearer {admin_token}"}
    uid = uuid.uuid4().hex[:6]
    uname = f"act_user_{uid}"

    # Provision user
    client.post(
        "/api/v1/admin/users",
        headers=headers_adm,
        json={
            "username": uname,
            "display_name": "Activity Test User",
            "password": "Password123!",
            "group_name": "NETWORK_ENGINEER",
        },
    )

    # 1. Login user
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": uname, "password": "Password123!"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["token"]
    user_id = login_res.json()["user"]["user_id"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Send heartbeat
    hb_res = client.post("/api/v1/auth/heartbeat", headers=headers)
    assert hb_res.status_code == 200
    assert hb_res.json()["success"] is True

    # 3. Check status
    status = rbac_svc.get_user_status(user_id)
    assert status == "ONLINE"

    # 4. List sessions via admin
    sessions_res = client.get(f"/api/v1/admin/sessions?user_id={user_id}", headers=headers_adm)
    assert sessions_res.status_code == 200
    sessions = sessions_res.json()["sessions"]
    assert len(sessions) >= 1
    target_session = sessions[0]
    assert "..." in target_session["masked_session_id"]
    assert target_session["is_online"] is True

    # 5. Revoke session via admin
    del_res = client.delete(
        f"/api/v1/admin/sessions/{target_session['session_id']}",
        headers=headers_adm,
    )
    assert del_res.status_code == 200
    assert del_res.json()["revoked"] is True

    # 6. Verify revoked session token cannot access API anymore
    revoked_call = client.get("/api/sessions", headers=headers)
    assert revoked_call.status_code == 401, "Revoked session must be rejected with 401!"


# -----------------------------------------------------------------------------
# 6. Account Disable & Enable Lifecycle
# -----------------------------------------------------------------------------
def test_account_disable_and_enable(admin_token):
    """
    Tests:
    - Disabling user account revokes active sessions.
    - Subsequent login attempts with correct password are rejected.
    - Enabling account allows login again.
    """
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    uid = uuid.uuid4().hex[:6]
    uname = f"toggle_u_{uid}"

    # Provision user
    client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={
            "username": uname,
            "display_name": "Toggle Lifecycle User",
            "password": "Password123!",
            "group_name": "NOC",
        },
    )
    user = identity_mgr.get_user_by_username(uname)

    # 1. Disable account
    toggle_off = client.post(
        f"/api/v1/admin/users/{user.user_id}/toggle-status",
        headers=admin_headers,
        json={"enabled": False},
    )
    assert toggle_off.status_code == 200
    assert toggle_off.json()["account_enabled"] is False

    # 2. Try login -> rejected
    bad_login = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": uname, "password": "Password123!"},
    )
    assert bad_login.status_code in (401, 403)
    assert "dinonaktifkan" in bad_login.json()["detail"].lower()

    # 3. Enable account
    toggle_on = client.post(
        f"/api/v1/admin/users/{user.user_id}/toggle-status",
        headers=admin_headers,
        json={"enabled": True},
    )
    assert toggle_on.status_code == 200
    assert toggle_on.json()["account_enabled"] is True

    # 4. Login now succeeds
    good_login = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": uname, "password": "Password123!"},
    )
    assert good_login.status_code == 200


# -----------------------------------------------------------------------------
# 7. Shared Network Data Ownership
# -----------------------------------------------------------------------------
def test_shared_network_data_ownership(admin_token):
    """
    Tests:
    - Network engineer registers a device.
    - NOC operator reads inventory and sees the exact same device.
    - No per-user duplication or silos.
    """
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    uid = uuid.uuid4().hex[:6]
    noc_uname = f"noc_share_{uid}"
    dev_name = f"CORE-ROUTER-{uid.upper()}"

    # Provision NOC user
    client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={
            "username": noc_uname,
            "display_name": "NOC Share User",
            "password": "Password123!",
            "group_name": "NOC",
        },
    )

    # 1. Create device as admin/engineer
    dev_res = client.post(
        "/api/devices",
        headers=admin_headers,
        json={
            "name": dev_name,
            "host": "192.168.88.1",
            "port": 22,
            "username": "admin",
            "device_type": "mikrotik",
            "note": "Shared Core Router",
        },
    )
    assert dev_res.status_code == 200

    # 2. Login as NOC user (who only has inventory.read, devices.read)
    noc_login = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": noc_uname, "password": "Password123!"},
    )
    assert noc_login.status_code == 200
    noc_headers = {"Authorization": f"Bearer {noc_login.json()['token']}"}

    # 3. NOC reads inventory -> sees the shared device
    noc_inv = client.get("/api/devices", headers=noc_headers)
    assert noc_inv.status_code == 200
    devs = noc_inv.json()["devices"]
    assert any(d["name"] == dev_name for d in devs)

    # 4. NOC attempts to create a device -> blocked with 403 (needs inventory.create)
    noc_create = client.post(
        "/api/devices",
        headers=noc_headers,
        json={"name": f"ROGUE-{uid}", "host": "10.0.0.1"},
    )
    assert noc_create.status_code == 403


# -----------------------------------------------------------------------------
# 8. Private Chat Session Isolation
# -----------------------------------------------------------------------------
def test_private_chat_session_isolation(admin_token):
    """
    Tests:
    - User A creates a chat session.
    - User B cannot see User A's session in session list.
    - User B cannot retrieve User A's messages (HTTP 404).
    """
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    uid = uuid.uuid4().hex[:6]
    chat_uname = f"chat_usr_{uid}"

    # Provision User B
    client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={
            "username": chat_uname,
            "display_name": "Isolated Chat User",
            "password": "Password123!",
            "group_name": "NOC",
        },
    )

    # 1. User A (lingga_admin) creates session
    create_sess_a = client.post("/api/sessions", headers=admin_headers)
    assert create_sess_a.status_code == 200
    sess_a_id = create_sess_a.json()["id"]

    # 2. User B lists sessions
    b_login = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": chat_uname, "password": "Password123!"},
    )
    assert b_login.status_code == 200
    b_headers = {"Authorization": f"Bearer {b_login.json()['token']}"}
    b_list = client.get("/api/sessions", headers=b_headers)
    assert b_list.status_code == 200
    b_sess_ids = [s["id"] for s in b_list.json()["sessions"]]
    assert sess_a_id not in b_sess_ids, "User A's session must not be visible to User B!"

    # 3. User B attempts to read User A's session messages directly
    read_attempt = client.get(f"/api/sessions/{sess_a_id}/messages", headers=b_headers)
    assert read_attempt.status_code == 404, "User B must receive 404 when attempting to access User A's session!"


# -----------------------------------------------------------------------------
# 9. Selection Quote Context in Chat Request
# -----------------------------------------------------------------------------
def test_selection_quote_context_in_chat(admin_token):
    """
    Tests:
    - POST /api/chat with source_message_id, selected_text, and selection_context.
    - Validates chat payload schema accepts quote metadata without 422 errors.
    """
    headers = {"Authorization": f"Bearer {admin_token}"}
    sess_res = client.post("/api/sessions", headers=headers)
    sess_id = sess_res.json()["id"]

    # Post message with selection quote context
    chat_payload = {
        "message": "Apa maksud status interface ini?",
        "session_id": sess_id,
        "source_message_id": "msg_001",
        "selected_text": "ether1 link down, speed 0Mbps",
        "selection_context": "Interface ether1 is unplugged or administratively down",
    }
    chat_res = client.post("/api/chat", headers=headers, json=chat_payload)
    # Even if LLM provider returns error or mock, schema validation succeeded
    assert chat_res.status_code in (200, 500, 502, 503)
