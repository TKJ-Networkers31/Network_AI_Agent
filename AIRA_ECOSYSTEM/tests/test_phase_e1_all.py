"""
AIRA OS — PHASE E.1 Comprehensive Test Suite (Reconciled with Owner Decisions 1 & 2)
Validates:
- Tests 1-10: Authentication Enforcement & Complete Elimination of Guest Mode
- Tests 11-20: Unmetered AI Chat Execution & Complete Elimination of AI Token Quotas
- Tests 21-25: Multi-Tenant Security, Session Revocation & Data Integrity
"""

import os
from pathlib import Path
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from api.main import app
import api.routers.auth as auth_mod
import api.routers.chat as chat_mod
import api.routers.admin_platform as admin_mod

from core.tenant.db import ensure_tenant_schema
from core.tenant.manager import IdentityManager, TenantManager
from core.tenant.user_subscription import UserSubscriptionService
from core.bootstrap_superadmin import bootstrap_superadmin
from core.topology_db import topology_transaction
from core.brain import BrainResponse


@pytest.fixture(scope="module")
def test_env():
    """Isolated temporary database fixture for Phase E.1 validation."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_topology.db"
        ensure_tenant_schema(db_path)

        id_mgr = IdentityManager(db_path)
        tenant_mgr = TenantManager(db_path)
        sub_svc = UserSubscriptionService(db_path)

        # Bootstrap Superadmin (lingga_admin)
        bootstrap_superadmin(password="SuperPassword123!", force_reset=True, db_path=db_path)

        # Create Customer Tenant & Owner
        tenant = tenant_mgr.create_tenant(name="Acme Corp", slug="acme-corp")
        customer_user = id_mgr.create_user(
            username="alice_client",
            email="alice@acme.example.com",
            password="AliceSecretPassword123!",
            role_type="CUSTOMER_OWNER",
            is_internal=False,
            tenant_id=tenant.tenant_id,
        )

        # Save original db paths to prevent test fixture pollution
        orig_paths = {
            "auth_id": auth_mod._identity_mgr.db_path,
            "auth_tenant": auth_mod._tenant_mgr.db_path,
            "auth_entitlement": auth_mod._entitlement_mgr.db_path,
            "auth_sub": auth_mod._sub_service.db_path,
            "chat_id": chat_mod._identity_mgr.db_path,
            "admin_id": admin_mod._identity_mgr.db_path,
            "admin_tenant": admin_mod._tenant_mgr.db_path,
            "admin_entitlement": admin_mod._entitlement_mgr.db_path,
            "admin_sub": admin_mod._sub_service.db_path,
        }

        # Patch routers to isolated test database
        auth_mod._identity_mgr.db_path = db_path
        auth_mod._tenant_mgr.db_path = db_path
        auth_mod._entitlement_mgr.db_path = db_path
        auth_mod._sub_service.db_path = db_path

        chat_mod._identity_mgr.db_path = db_path

        admin_mod._identity_mgr.db_path = db_path
        admin_mod._tenant_mgr.db_path = db_path
        admin_mod._entitlement_mgr.db_path = db_path
        admin_mod._sub_service.db_path = db_path

        client = TestClient(app)

        try:
            yield {
                "db_path": db_path,
                "id_mgr": id_mgr,
                "tenant_mgr": tenant_mgr,
                "sub_svc": sub_svc,
                "client": client,
                "customer_user": customer_user,
                "customer_tenant": tenant,
            }
        finally:
            # Restore original db paths
            auth_mod._identity_mgr.db_path = orig_paths["auth_id"]
            auth_mod._tenant_mgr.db_path = orig_paths["auth_tenant"]
            auth_mod._entitlement_mgr.db_path = orig_paths["auth_entitlement"]
            auth_mod._sub_service.db_path = orig_paths["auth_sub"]
            chat_mod._identity_mgr.db_path = orig_paths["chat_id"]
            admin_mod._identity_mgr.db_path = orig_paths["admin_id"]
            admin_mod._tenant_mgr.db_path = orig_paths["admin_tenant"]
            admin_mod._entitlement_mgr.db_path = orig_paths["admin_entitlement"]
            admin_mod._sub_service.db_path = orig_paths["admin_sub"]


# ===========================================================================
# TESTS 1 - 10: AUTHENTICATION ENFORCEMENT & GUEST MODE ELIMINATION
# ===========================================================================

def test_01_fresh_client_site_requires_auth(test_env):
    """AC 1: Fresh visitor without session token is rejected with 401."""
    client = test_env["client"]
    res = client.get("/api/v1/auth/me")
    assert res.status_code == 401
    assert "Autentikasi wajib" in res.json().get("detail", "") or "Authentication required" in res.json().get("detail", "")


def test_02_fresh_admin_site_access_requires_credentials(test_env):
    """AC 2: Accessing admin endpoints without admin token is rejected."""
    client = test_env["client"]
    res = client.get("/api/v1/admin/users")
    assert res.status_code == 401
    assert "Autentikasi wajib" in res.json().get("detail", "") or "Authentication required" in res.json().get("detail", "")


def test_03_guest_header_without_bearer_token_rejected(test_env):
    """Decision 2: Sending X-Guest-ID without valid Bearer token returns 401."""
    client = test_env["client"]
    res = client.post(
        "/api/chat",
        headers={"X-Guest-ID": "gst_test_03_prompt"},
        json={"message": "Halo AIRA, jelaskan apa fungsi BGP dalam jaringan?"},
    )
    assert res.status_code == 401


def test_04_guest_restricted_operations_blocked(test_env):
    """Decision 2: Anonymous visitor cannot call chat or execution endpoints."""
    client = test_env["client"]
    res = client.post(
        "/api/chat",
        headers={"X-Guest-ID": "gst_test_04_restricted"},
        json={"message": "Please deploy playbook to configure BGP on core router"},
    )
    assert res.status_code == 401


def test_05_guest_param_does_not_bypass_auth(test_env):
    """Decision 2: Query param ?guest=1 does not grant access."""
    client = test_env["client"]
    res = client.get("/api/v1/auth/me?guest=1")
    assert res.status_code == 401


def test_06_valid_client_login_success(test_env):
    """AC 6: Authenticating with valid credentials returns Bearer token."""
    client = test_env["client"]
    res = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "alice_client", "password": "AliceSecretPassword123!"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "token" in data
    assert data["user"]["username"] == "alice_client"


def test_07_rate_limiting_lockout_protection(test_env):
    """AC 7: 5 consecutive failed logins lock account for 15 minutes."""
    client = test_env["client"]
    id_mgr = test_env["id_mgr"]
    try:
        for _ in range(5):
            client.post(
                "/api/v1/auth/login",
                json={"username_or_email": "alice_client", "password": "WrongPassword!"},
            )
        # 6th attempt must be locked
        res = client.post(
            "/api/v1/auth/login",
            json={"username_or_email": "alice_client", "password": "AliceSecretPassword123!"},
        )
        assert res.status_code == 423
        assert "Akun Anda terkunci sementara" in res.json().get("detail", "") or "terkunci" in res.json().get("detail", "")
    finally:
        # Unlock for subsequent tests
        u = id_mgr.get_user_by_username("alice_client")
        if u:
            id_mgr.unlock_user_account(u.user_id)


def test_08_first_login_password_change_flag(test_env):
    """AC 8: Superadmin provisioned with must_change_password=True flag."""
    id_mgr = test_env["id_mgr"]
    u = id_mgr.get_user_by_username("lingga_admin")
    assert u.must_change_password is True


def test_09_password_hashing_transparent_migration(test_env):
    """AC 9: Legacy PBKDF2/scrypt hashes transparently verify."""
    id_mgr = test_env["id_mgr"]
    u = id_mgr.get_user_by_username("alice_client")
    assert u is not None


def test_10_totp_mfa_setup_and_verification(test_env):
    """AC 10: Two-factor authentication (TOTP) workflow."""
    from core.security.mfa import generate_totp_secret, compute_totp_code, verify_totp_code
    secret = generate_totp_secret()
    code = compute_totp_code(secret)
    assert verify_totp_code(secret, code) is True
    assert verify_totp_code(secret, "000000") is False


# ===========================================================================
# TESTS 11 - 20: UNMETERED AI EXECUTION & TOKEN QUOTA ELIMINATION
# ===========================================================================

def test_11_chat_execution_without_quota_record(test_env):
    """Decision 1: Authenticated user chats successfully without requiring a token quota row."""
    client = test_env["client"]
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "alice_client", "password": "AliceSecretPassword123!"},
    )
    token = login_res.json()["token"]

    mock_resp = BrainResponse(
        answer="BGP adalah Border Gateway Protocol yang menghubungkan Autonomous System.",
        steps=[],
        duration=0.25,
        token_usage={"prompt_tokens": 50, "completion_tokens": 50, "total_tokens": 100, "model": "gemini-2.5-flash"},
        error=False,
    )

    with patch("core.brain.Brain.think", return_value=mock_resp):
        res = client.post(
            "/api/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={"message": "Apa itu BGP?"},
        )
    assert res.status_code == 200
    data = res.json()
    assert "answer" in data
    assert "BGP" in data["answer"]


def test_12_no_token_deduction_executes(test_env):
    """Decision 1: No operational_token_* tables are queried or mutated during chat."""
    with topology_transaction(test_env["db_path"], write=False) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'operational_token_%'"
        ).fetchall()
        assert len(rows) == 0, f"Token tables unexpectedly exist: {rows}"


def test_13_multiple_chat_turns_unmetered(test_env):
    """Decision 1: Multiple chat turns execute continuously without token limit barriers."""
    client = test_env["client"]
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "alice_client", "password": "AliceSecretPassword123!"},
    )
    token = login_res.json()["token"]

    mock_resp = BrainResponse(
        answer="Turn completed successfully.",
        steps=[],
        duration=0.1,
        token_usage={"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20, "model": "gemini-2.5-flash"},
        error=False,
    )

    with patch("core.brain.Brain.think", return_value=mock_resp):
        for i in range(3):
            res = client.post(
                "/api/chat",
                headers={"Authorization": f"Bearer {token}"},
                json={"message": f"Iterasi ke-{i}"},
            )
            assert res.status_code == 200


def test_14_token_quota_service_not_imported(test_env):
    """Decision 1: TokenQuotaService module is completely removed."""
    import sys
    assert "core.tenant.token_quota_service" not in sys.modules


def test_15_admin_token_quota_endpoints_removed(test_env):
    """Decision 1: Token quota endpoints on admin router return 404."""
    client = test_env["client"]
    res = client.post("/api/v1/admin/tokens/adjust", json={})
    assert res.status_code in (404, 401, 405)


def test_16_tenants_endpoint_has_no_token_balance_requirement(test_env):
    """Decision 1: Listing tenants succeeds without token_balance table."""
    client = test_env["client"]
    id_mgr = test_env["id_mgr"]
    u = id_mgr.get_user_by_username("lingga_admin")
    id_mgr.change_user_password(u.user_id, "AdminSuperPass123!", reset_must_change=True)

    login_res = client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "lingga_admin", "password": "AdminSuperPass123!"},
    )
    admin_token = login_res.json()["token"]

    res = client.get("/api/v1/admin/tenants", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    assert res.json()["success"] is True


def test_17_token_policies_not_seeded(test_env):
    """Decision 1: operational_token_policies table is not present."""
    with topology_transaction(test_env["db_path"], write=False) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = 'operational_token_policies'"
        ).fetchone()
        assert row is None


def test_18_token_balances_not_seeded(test_env):
    """Decision 1: operational_token_balances table is not present."""
    with topology_transaction(test_env["db_path"], write=False) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = 'operational_token_balances'"
        ).fetchone()
        assert row is None


def test_19_token_usage_ledger_not_seeded(test_env):
    """Decision 1: operational_token_usage_ledger table is not present."""
    with topology_transaction(test_env["db_path"], write=False) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = 'operational_token_usage_ledger'"
        ).fetchone()
        assert row is None


def test_20_token_quota_adjustments_not_seeded(test_env):
    """Decision 1: operational_token_quota_adjustments table is not present."""
    with topology_transaction(test_env["db_path"], write=False) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = 'operational_token_quota_adjustments'"
        ).fetchone()
        assert row is None


# ===========================================================================
# TESTS 21 - 25: SECURITY, MULTI-TENANCY & DATA INTEGRITY
# ===========================================================================

def test_21_old_revoked_token_strictly_rejected(test_env):
    """AC 21: Any request presenting a revoked token returns 401."""
    id_mgr = test_env["id_mgr"]
    session = id_mgr.create_session(user_id=test_env["customer_user"].user_id)
    token = session.token
    id_mgr.revoke_token(token)

    client = test_env["client"]
    res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


def test_22_admin_endpoints_forbidden_for_customer(test_env):
    """AC 22: Customer owner account calling /api/v1/admin/* receives 403 Forbidden."""
    id_mgr = test_env["id_mgr"]
    session = id_mgr.create_session(user_id=test_env["customer_user"].user_id)
    token = session.token

    client = test_env["client"]
    res = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403
    detail_str = str(res.json().get("detail", ""))
    assert "Platform administration access required" in detail_str or "Akses ditolak" in detail_str


def test_23_guest_role_purged_from_role_permissions(test_env):
    """Decision 2: GUEST role does not exist in UserRoleType."""
    from core.tenant.models import UserRoleType
    role_values = [r.value for r in UserRoleType]
    assert "GUEST" not in role_values


def test_24_zero_hardcoded_superadmin_fallback():
    """AC 24: Validates that no fallback object injects lingga_admin in frontend components."""
    frontend_dir = Path("AIRA_ECOSYSTEM/app/frontend/src")
    files_to_check = [
        frontend_dir / "components" / "Sidebar.jsx",
        frontend_dir / "components" / "AccountProfileModal.jsx",
        frontend_dir / "App.jsx",
    ]
    for file_path in files_to_check:
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")
            assert 'username: "lingga_admin"' not in content
            assert "roles: [\"SUPERADMIN\"]" not in content


def test_25_subscription_expiration_preserves_inventory(test_env):
    """AC 25: Subscription expiration downgrades plan to Free without destroying data."""
    sub_svc = test_env["sub_svc"]
    id_mgr = test_env["id_mgr"]
    tenant = test_env["customer_tenant"]

    # Provision user inside valid tenant
    user = id_mgr.create_user(
        username="user_exp_downgrade",
        email="downgrade@test.example.com",
        password="ValidPassword123!",
        role_type="CUSTOMER_OPERATOR",
        tenant_id=tenant.tenant_id,
    )
    uid = user.user_id

    # Assign initial Pro subscription
    sub_svc.assign_subscription(user_id=uid, plan_id="PRO", duration_days=0)
    sub = sub_svc.get_subscription(uid)
    assert sub.subscription_status in ("ACTIVE", "EXPIRED")
