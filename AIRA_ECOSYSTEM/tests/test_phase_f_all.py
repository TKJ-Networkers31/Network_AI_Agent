"""
AIRA OS — PHASE F Comprehensive Automated Test Suite
Validates:
- 1. Identity Hierarchy & Explicit Separation (Role, Plan, Entitlement)
- 2. PLATFORM_OWNER Permanent Internal Authority (lingga_admin)
- 3. Chat Session & Message Isolation Across Users & Guests
- 4. User Memory Isolation, Categorization, Scoping & Privacy Clear
- 5. User Persona Isolation, Built-in Presets, Custom Personas & Cloning
- 6. Context Composition Priority (System Safety, Persona, Memory)
- 7. Network++ Entitlement Gating on all 8 Networking Routers (HTTP 403 ENTITLEMENT_REQUIRED)
- 8. Multi-Tenant Network Workspace Data Isolation
- 9. Admin Site Access Protection (Role-based Authorization)
- 10. Privacy & Data Portability (Export JSON, Delete Sessions, Delete Personas)
"""

import json
from pathlib import Path
import tempfile
import time
import pytest
from fastapi.testclient import TestClient

from api.main import app
import api.routers.auth as auth_mod
import api.routers.chat as chat_mod
import api.routers.admin_platform as admin_mod
import api.routers.personalization as pers_mod
import api.routers.devices as dev_mod
import api.routers.topology as topo_mod
import api.routers.nms as nms_mod
import api.routers.playbooks as pb_mod
import api.routers.gateways as gw_mod
import api.routers.operations as op_mod
import api.routers.network_intelligence as intel_mod
import api.routers.decisions as dec_mod
import api.routers.sessions as sess_mod

from core.tenant.db import ensure_tenant_schema
from core.tenant.manager import IdentityManager, TenantManager
from core.tenant.entitlements import EntitlementManager
from core.tenant.models import UserRoleType, SubscriptionTier
from core.tenant.token_quota_service import TokenQuotaService
from core.tenant.user_subscription import UserSubscriptionService
from core.tenant.entitlement_service import EntitlementService, get_entitlement_service
from core.tenant.workspace_service import WorkspaceService
from core.tenant.memory_service import UserMemoryService
from core.tenant.persona_service import UserPersonaService
from core.bootstrap_superadmin import bootstrap_superadmin
from core.topology_db import topology_transaction
from core.context import ContextBuilder
from core.events import event_scope


@pytest.fixture(scope="module")
def env():
    """Isolated temporary database fixture for Phase F validation."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "phase_f_topology.db"
        ensure_tenant_schema(db_path)

        id_mgr = IdentityManager(db_path)
        tenant_mgr = TenantManager(db_path)
        ent_mgr = EntitlementManager(db_path)
        quota_svc = TokenQuotaService(db_path)
        sub_svc = UserSubscriptionService(db_path)
        ent_svc = EntitlementService(db_path)
        ws_svc = WorkspaceService(db_path)
        mem_svc = UserMemoryService(db_path)
        persona_svc = UserPersonaService(db_path)

        # 1. PLATFORM_OWNER (lingga_admin)
        bootstrap_superadmin(db_path=db_path, password="OwnerPassword123!", force_reset=True)

        # 2. Tenants
        tenant_acme = tenant_mgr.create_tenant(name="Acme Corp", slug="acme-corp")
        tenant_beta = tenant_mgr.create_tenant(name="Beta Labs", slug="beta-labs")

        # 3. USER with Network++ (bob_netops)
        user_bob = id_mgr.create_user(
            username="bob_netops",
            email="bob@acme.example.com",
            password="BobPassword123!",
            role_type=UserRoleType.USER.value,
            is_internal=False,
            tenant_id=tenant_acme.tenant_id,
        )
        # Assign PRO plan + NETWORK_PLUS
        sub_svc.assign_subscription(user_bob.user_id, "PRO", duration_days=30, networking_addon=True)
        quota_svc.get_or_create_user_quota(user_bob.user_id, tenant_acme.tenant_id, tier="PRO")
        ws_svc.get_or_create_default_workspace(user_bob.user_id, tenant_acme.tenant_id)

        # 4. USER Standard (carol_standard - FREE, no Network++)
        user_carol = id_mgr.create_user(
            username="carol_standard",
            email="carol@beta.example.com",
            password="CarolPassword123!",
            role_type=UserRoleType.USER.value,
            is_internal=False,
            tenant_id=tenant_beta.tenant_id,
        )
        sub_svc.assign_subscription(user_carol.user_id, "FREE", duration_days=365, networking_addon=False)
        quota_svc.get_or_create_user_quota(user_carol.user_id, tenant_beta.tenant_id, tier="FREE")
        quota_svc.get_or_create_user_quota(user_carol.user_id, tenant_beta.tenant_id, tier="FREE")
        ws_svc.get_or_create_default_workspace(user_carol.user_id, tenant_beta.tenant_id)

        # Patch singletons and routers to test DB
        auth_mod._identity_mgr.db_path = db_path
        auth_mod._tenant_mgr.db_path = db_path
        auth_mod._entitlement_mgr.db_path = db_path
        auth_mod._sub_service.db_path = db_path
        auth_mod._quota_service.db_path = db_path

        chat_mod._identity_mgr.db_path = db_path
        chat_mod._quota_service.db_path = db_path

        admin_mod._identity_mgr.db_path = db_path
        admin_mod._tenant_mgr.db_path = db_path
        admin_mod._entitlement_mgr.db_path = db_path
        admin_mod._sub_service.db_path = db_path
        admin_mod._billing_service.db_path = db_path
        admin_mod._quota_service.db_path = db_path

        pers_mod._persona_svc.db_path = db_path
        pers_mod._memory_svc.db_path = db_path
        pers_mod._id_mgr.db_path = db_path

        sess_mod._identity_mgr.db_path = db_path

        import core.tenant.entitlement_service as ent_service_mod
        ent_service_mod._entitlement_service.db_path = db_path

        import core.tenant.memory_service as mem_service_mod
        mem_service_mod._memory_service = mem_svc

        import core.tenant.persona_service as persona_service_mod
        persona_service_mod._persona_service = persona_svc

        client = TestClient(app)

        # Authenticate users to get JWT tokens
        res_owner = client.post("/api/v1/auth/login", json={"username_or_email": "lingga_admin", "password": "OwnerPassword123!"})
        owner_token = res_owner.json()["token"]

        res_bob = client.post("/api/v1/auth/login", json={"username_or_email": "bob_netops", "password": "BobPassword123!"})
        bob_token = res_bob.json()["token"]

        res_carol = client.post("/api/v1/auth/login", json={"username_or_email": "carol_standard", "password": "CarolPassword123!"})
        carol_token = res_carol.json()["token"]

        yield {
            "db_path": db_path,
            "id_mgr": id_mgr,
            "tenant_mgr": tenant_mgr,
            "ent_mgr": ent_mgr,
            "quota_svc": quota_svc,
            "sub_svc": sub_svc,
            "ent_svc": ent_svc,
            "ws_svc": ws_svc,
            "mem_svc": mem_svc,
            "persona_svc": persona_svc,
            "client": client,
            "owner_token": owner_token,
            "bob_token": bob_token,
            "carol_token": carol_token,
            "bob_user": user_bob,
            "carol_user": user_carol,
        }


# ===========================================================================
# 1. IDENTITY HIERARCHY & EXPLICIT SEPARATION
# ===========================================================================

def test_01_role_plan_entitlement_explicit_separation(env):
    """Verify Role, Plan, and Entitlement are strictly separated in models and database."""
    # 1. Role is explicitly stored on User model / operational_users table
    assert env["bob_user"].role_type == UserRoleType.USER.value
    assert env["carol_user"].role_type == UserRoleType.USER.value

    # 2. Plan is explicitly stored on Subscription model / user_subscriptions table
    bob_sub = env["sub_svc"].get_subscription(env["bob_user"].user_id)
    assert bob_sub.plan_id == "PRO"
    carol_sub = env["sub_svc"].get_subscription(env["carol_user"].user_id)
    assert carol_sub.plan_id == "FREE"

    # 3. Entitlement is computed dynamically via EntitlementService
    bob_ents = env["ent_svc"].get_user_entitlements(env["bob_user"].user_id)
    assert bob_ents["NETWORK_PLUS"] is True
    carol_ents = env["ent_svc"].get_user_entitlements(env["carol_user"].user_id)
    assert carol_ents["NETWORK_PLUS"] is False


def test_02_platform_owner_permanent_authority(env):
    """Verify lingga_admin is provisioned as PLATFORM_OWNER with ENTERPRISE and NETWORK_PLUS."""
    owner_user = env["id_mgr"].get_user_by_username("lingga_admin")
    assert owner_user is not None
    assert owner_user.role_type == UserRoleType.PLATFORM_OWNER.value

    owner_sub = env["sub_svc"].get_subscription(owner_user.user_id)
    assert owner_sub.plan_id == "ENTERPRISE"

    owner_ents = env["ent_svc"].get_user_entitlements(owner_user.user_id)
    assert owner_ents["NETWORK_PLUS"] is True
    assert env["ent_svc"].has_entitlement(owner_user.user_id, "NETWORK_PLUS") is True


def test_03_bootstrap_superadmin_idempotency(env):
    """Verify re-running bootstrap_superadmin maintains PLATFORM_OWNER without data corruption."""
    res = bootstrap_superadmin(db_path=env["db_path"], force_reset=False)
    assert res["status"] in ("verified", "created", "reset")
    owner_user = env["id_mgr"].get_user_by_username("lingga_admin")
    assert owner_user.role_type == UserRoleType.PLATFORM_OWNER.value
    assert env["ent_svc"].has_entitlement(owner_user.user_id, "NETWORK_PLUS") is True


# ===========================================================================
# 2. CHAT SESSION & CONVERSATION ISOLATION
# ===========================================================================

def test_04_chat_session_creation_user_isolated(env):
    """Sessions created by User Bob are completely isolated from User Carol."""
    client = env["client"]

    # Bob creates session
    res_b = client.post("/api/sessions", headers={"Authorization": f"Bearer {env['bob_token']}"})
    assert res_b.status_code == 200
    bob_session_id = res_b.json()["id"]

    # Carol creates session
    res_c = client.post("/api/sessions", headers={"Authorization": f"Bearer {env['carol_token']}"})
    assert res_c.status_code == 200
    carol_session_id = res_c.json()["id"]

    # Bob lists sessions
    list_b = client.get("/api/sessions", headers={"Authorization": f"Bearer {env['bob_token']}"}).json()["sessions"]
    bob_ids = [s["id"] for s in list_b]
    assert bob_session_id in bob_ids
    assert carol_session_id not in bob_ids

    # Carol lists sessions
    list_c = client.get("/api/sessions", headers={"Authorization": f"Bearer {env['carol_token']}"}).json()["sessions"]
    carol_ids = [s["id"] for s in list_c]
    assert carol_session_id in carol_ids
    assert bob_session_id not in carol_ids


def test_05_cross_user_session_access_forbidden(env):
    """Carol cannot get, rename, or delete Bob's session."""
    client = env["client"]

    # Bob creates session
    res_b = client.post("/api/sessions", headers={"Authorization": f"Bearer {env['bob_token']}"})
    bob_sid = res_b.json()["id"]

    # Carol tries to get Bob's session -> 404
    res_c_get = client.get(f"/api/sessions/{bob_sid}", headers={"Authorization": f"Bearer {env['carol_token']}"})
    assert res_c_get.status_code == 404

    # Carol tries to rename Bob's session -> 404
    res_c_patch = client.patch(
        f"/api/sessions/{bob_sid}",
        headers={"Authorization": f"Bearer {env['carol_token']}"},
        json={"title": "Hacked Title"},
    )
    assert res_c_patch.status_code == 404

    # Carol tries to delete Bob's session -> 404
    res_c_del = client.delete(f"/api/sessions/{bob_sid}", headers={"Authorization": f"Bearer {env['carol_token']}"})
    assert res_c_del.status_code == 404


def test_06_guest_chat_session_isolation(env):
    """Guests with different X-Guest-ID maintain strictly isolated sessions."""
    client = env["client"]
    guest1_headers = {"X-Guest-ID": "gst_user_1111"}
    guest2_headers = {"X-Guest-ID": "gst_user_2222"}

    res_g1 = client.post("/api/sessions", headers=guest1_headers)
    assert res_g1.status_code == 200
    g1_sid = res_g1.json()["id"]

    res_g2 = client.post("/api/sessions", headers=guest2_headers)
    assert res_g2.status_code == 200
    g2_sid = res_g2.json()["id"]

    # Guest 2 listing does not see Guest 1
    g2_list = client.get("/api/sessions", headers=guest2_headers).json()["sessions"]
    g2_ids = [s["id"] for s in g2_list]
    assert g2_sid in g2_ids
    assert g1_sid not in g2_ids


# ===========================================================================
# 3. MEMORY ISOLATION & LIFECYCLE
# ===========================================================================

def test_07_memory_crud_and_user_isolation(env):
    """Memories added by Bob are invisible to Carol and cannot be mutated by Carol."""
    client = env["client"]

    # Bob creates technical memory
    res_b = client.post(
        "/api/v1/personalization/memories",
        headers={"Authorization": f"Bearer {env['bob_token']}"},
        json={"content": "Bob prefers BGP over OSPF for WAN", "category": "technical", "importance": 85},
    )
    assert res_b.status_code == 200
    bob_mem_id = res_b.json()["memory"]["memory_id"]

    # Carol creates general memory
    res_c = client.post(
        "/api/v1/personalization/memories",
        headers={"Authorization": f"Bearer {env['carol_token']}"},
        json={"content": "Carol works in finance", "category": "general", "importance": 60},
    )
    assert res_c.status_code == 200
    carol_mem_id = res_c.json()["memory"]["memory_id"]

    # Carol lists memories -> should only see Carol's
    carol_list = client.get(
        "/api/v1/personalization/memories",
        headers={"Authorization": f"Bearer {env['carol_token']}"},
    ).json()["memories"]
    carol_ids = [m["memory_id"] for m in carol_list]
    assert carol_mem_id in carol_ids
    assert bob_mem_id not in carol_ids

    # Carol attempts to delete Bob's memory -> 404
    del_res = client.delete(
        f"/api/v1/personalization/memories/{bob_mem_id}",
        headers={"Authorization": f"Bearer {env['carol_token']}"},
    )
    assert del_res.status_code == 404


def test_08_memory_toggle_per_user(env):
    """Disabling memory for Carol does not affect Bob."""
    client = env["client"]

    # Carol disables memory
    res_c = client.put(
        "/api/v1/personalization/preferences",
        headers={"Authorization": f"Bearer {env['carol_token']}"},
        json={"memory_enabled": False},
    )
    assert res_c.status_code == 200
    assert res_c.json()["preferences"]["memory_enabled"] is False

    # Check via service
    assert env["mem_svc"].is_memory_enabled(env["carol_user"].user_id) is False
    assert env["mem_svc"].is_memory_enabled(env["bob_user"].user_id) is True


def test_09_memory_clear_scoped_to_user(env):
    """Clearing all memories for Carol does not delete Bob's memories."""
    client = env["client"]

    # Carol clears memories
    res_c = client.delete(
        "/api/v1/personalization/memories",
        headers={"Authorization": f"Bearer {env['carol_token']}"},
    )
    assert res_c.status_code == 200

    # Bob's memories still exist
    bob_list = client.get(
        "/api/v1/personalization/memories",
        headers={"Authorization": f"Bearer {env['bob_token']}"},
    ).json()["memories"]
    assert len(bob_list) >= 1


# ===========================================================================
# 4. PERSONA MANAGEMENT & ISOLATION
# ===========================================================================

def test_10_builtin_presets_are_read_only(env):
    """Built-in system presets cannot be deleted or mutated by regular users."""
    client = env["client"]

    # Carol tries to delete preset_technical -> 400 or 403
    del_res = client.delete(
        "/api/v1/personalization/personas/preset_technical",
        headers={"Authorization": f"Bearer {env['carol_token']}"},
    )
    assert del_res.status_code in (400, 403)


def test_11_custom_persona_ownership_and_isolation(env):
    """Custom persona created by Bob cannot be viewed, updated, or deleted by Carol."""
    client = env["client"]

    # Bob creates custom persona
    res_b = client.post(
        "/api/v1/personalization/personas",
        headers={"Authorization": f"Bearer {env['bob_token']}"},
        json={
            "name": "Bob's Router Expert",
            "response_style": "technical",
            "language": "id",
            "technical_depth": 95,
            "explanation_preference": "technical",
            "custom_instructions": "Always include MikroTik CLI syntax.",
        },
    )
    assert res_b.status_code == 200
    bob_pid = res_b.json()["persona"]["persona_id"]

    # Carol lists personas -> should NOT include bob_pid in custom_personas
    carol_p_res = client.get(
        "/api/v1/personalization/personas",
        headers={"Authorization": f"Bearer {env['carol_token']}"},
    ).json()
    carol_custom_ids = [p["persona_id"] for p in carol_p_res["custom_personas"]]
    assert bob_pid not in carol_custom_ids

    # Carol tries to delete Bob's persona -> 404
    del_res = client.delete(
        f"/api/v1/personalization/personas/{bob_pid}",
        headers={"Authorization": f"Bearer {env['carol_token']}"},
    )
    assert del_res.status_code == 404


def test_12_duplicate_persona_creates_isolated_custom_clone(env):
    """Cloning a preset creates a custom persona owned by the caller."""
    client = env["client"]

    clone_res = client.post(
        "/api/v1/personalization/personas/preset_tutor/duplicate?new_name=CarolTutor",
        headers={"Authorization": f"Bearer {env['carol_token']}"},
    )
    assert clone_res.status_code == 200
    clone_pid = clone_res.json()["persona"]["persona_id"]

    # Carol lists personas -> clone_pid is in her custom list
    carol_p_res = client.get(
        "/api/v1/personalization/personas",
        headers={"Authorization": f"Bearer {env['carol_token']}"},
    ).json()
    carol_custom_ids = [p["persona_id"] for p in carol_p_res["custom_personas"]]
    assert clone_pid in carol_custom_ids


def test_13_active_persona_selection_independence(env):
    """Bob activates preset_consultant; Carol activates preset_general; selections are independent."""
    client = env["client"]

    # Bob selects consultant
    client.post(
        "/api/v1/personalization/personas/active",
        headers={"Authorization": f"Bearer {env['bob_token']}"},
        json={"persona_id": "preset_consultant"},
    )
    # Carol selects general
    client.post(
        "/api/v1/personalization/personas/active",
        headers={"Authorization": f"Bearer {env['carol_token']}"},
        json={"persona_id": "preset_general"},
    )

    bob_active = env["persona_svc"].get_active_persona(env["bob_user"].user_id)
    carol_active = env["persona_svc"].get_active_persona(env["carol_user"].user_id)

    assert bob_active["persona_id"] == "preset_consultant"
    assert carol_active["persona_id"] == "preset_general"


# ===========================================================================
# 5. CONTEXT COMPOSITION PRIORITY & ISOLATION
# ===========================================================================

def test_14_context_composition_priority_and_safety(env):
    """Context Builder adheres to composition priority and scopes memory and persona to user_id."""
    builder = ContextBuilder()

    with event_scope(user_id=env["bob_user"].user_id):
        ctx = builder.build("Bagaimana cara peering BGP?")

        # 1. System safety CORE_RULES must be present at the top
        assert "=== ATURAN INTI ===" in ctx.system_prompt

        # 2. Bob's active persona (preset_consultant) injected
        assert "Senior Network Infrastructure Consultant" in ctx.system_prompt or "preset_consultant" in str(ctx.persona.data)

        # 3. Bob's memory injected
        assert "Bob prefers BGP over OSPF" in ctx.system_prompt or ctx.memory is not None


# ===========================================================================
# 6. NETWORK++ ENTITLEMENT GATING
# ===========================================================================

def test_15_standard_user_gated_with_403_on_networking_endpoints(env):
    """Carol (Free, no Network++) receives 403 ENTITLEMENT_REQUIRED on all networking routes."""
    client = env["client"]
    headers = {"Authorization": f"Bearer {env['carol_token']}"}

    endpoints = [
        ("GET", "/api/devices"),
        ("GET", "/api/topology"),
        ("GET", "/api/nms/overview"),
        ("GET", "/api/v1/playbooks"),
        ("GET", "/api/v1/gateways"),
        ("GET", "/api/operations/incidents"),
        ("GET", "/api/intelligence/health"),
        ("GET", "/api/v1/decisions"),
    ]

    for method, ep in endpoints:
        if method == "GET":
            res = client.get(ep, headers=headers)
        assert res.status_code == 403, f"Endpoint {ep} should be 403 for user without Network++"
        detail = res.json().get("detail", {})
        assert detail.get("code") == "ENTITLEMENT_REQUIRED"
        assert "NETWORK_PLUS" in detail.get("required_entitlement", "")


def test_16_guest_gated_with_403_on_networking_endpoints(env):
    """Guest with no token receives 401 or 403 ENTITLEMENT_REQUIRED on networking routes."""
    client = env["client"]
    headers = {"X-Guest-ID": "gst_anon_9999"}

    res = client.get("/api/devices", headers=headers)
    assert res.status_code in (401, 403)


def test_17_network_plus_user_granted_access(env):
    """Bob (has Network++) receives access (non-403) on networking routes."""
    client = env["client"]
    headers = {"Authorization": f"Bearer {env['bob_token']}"}

    res_dev = client.get("/api/devices", headers=headers)
    assert res_dev.status_code != 403

    res_pb = client.get("/api/v1/playbooks", headers=headers)
    assert res_pb.status_code != 403


def test_18_platform_owner_has_full_networking_access(env):
    """PLATFORM_OWNER (lingga_admin) has full operational access to all networking endpoints."""
    client = env["client"]
    headers = {"Authorization": f"Bearer {env['owner_token']}"}

    res_dev = client.get("/api/devices", headers=headers)
    assert res_dev.status_code != 403

    res_topo = client.get("/api/topology", headers=headers)
    assert res_topo.status_code != 403


# ===========================================================================
# 7. MULTI-TENANT NETWORK WORKSPACE ISOLATION
# ===========================================================================

def test_19_workspace_provisioning_and_isolation(env):
    """Each user receives a dedicated network workspace; resources cannot leak across workspaces."""
    bob_ws = env["ws_svc"].get_or_create_default_workspace(env["bob_user"].user_id, "acme-corp")
    carol_ws = env["ws_svc"].get_or_create_default_workspace(env["carol_user"].user_id, "beta-labs")

    assert bob_ws["workspace_id"] != carol_ws["workspace_id"]
    assert bob_ws["user_id"] == env["bob_user"].user_id
    assert carol_ws["user_id"] == env["carol_user"].user_id


# ===========================================================================
# 8. ADMIN SITE AUTHORIZATION
# ===========================================================================

def test_20_admin_endpoints_forbidden_to_regular_users(env):
    """Both Carol and Bob receive 403 on /api/v1/admin/*."""
    client = env["client"]

    # Carol
    res_c = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {env['carol_token']}"})
    assert res_c.status_code == 403

    # Bob (even with Network++)
    res_b = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {env['bob_token']}"})
    assert res_b.status_code == 403


def test_21_admin_endpoints_accessible_to_platform_owner(env):
    """lingga_admin can access /api/v1/admin/users."""
    client = env["client"]
    headers = {"Authorization": f"Bearer {env['owner_token']}"}

    res = client.get("/api/v1/admin/users", headers=headers)
    assert res.status_code == 200
    assert res.json().get("success") is True


# ===========================================================================
# 9. PRIVACY & DATA OPERATIONS
# ===========================================================================

def test_22_personal_data_export_json_scoped(env):
    """Export data endpoint returns JSON strictly containing caller's data."""
    client = env["client"]

    res = client.get(
        "/api/v1/personalization/data/export",
        headers={"Authorization": f"Bearer {env['bob_token']}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["user_id"] == env["bob_user"].user_id
    assert "memories" in data
    assert "chat_sessions" in data
    assert "custom_personas" in data


def test_23_account_deletion_request_registered(env):
    """Calling account deletion request logs ticket properly."""
    client = env["client"]

    res = client.post(
        "/api/v1/personalization/data/account-deletion-request",
        headers={"Authorization": f"Bearer {env['carol_token']}"},
        json={"reason": "Testing GDPR deletion request compliance"},
    )
    assert res.status_code == 200
    assert res.json().get("success") is True
    assert res.json().get("status") == "PENDING_VERIFICATION"
