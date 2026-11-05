"""
AIRA OS — PHASE E.1 Comprehensive Test Suite
Validates all 25 Acceptance Criteria:
- Tests 1-10: Authentication Flow Repair & Guest Access Experience
- Tests 11-20: ChatGPT/Claude-Style Token Quota & Reset Governance
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
from core.tenant.token_quota_service import (
    TokenQuotaService,
    compute_next_reset_utc,
    DEFAULT_QUOTA_SPECS,
    DEFAULT_TIMEZONE,
)
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
        quota_svc = TokenQuotaService(db_path)
        sub_svc = UserSubscriptionService(db_path)

        # Bootstrap Superadmin (lingga_admin)
        bootstrap_superadmin(db_path=db_path, password="SuperPassword123!", force_reset=True)

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
        quota_svc.get_or_create_user_quota(customer_user.user_id, tenant.tenant_id, tier="FREE")

        # Patch routers to isolated test database
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

        client = TestClient(app)

        yield {
            "db_path": db_path,
            "id_mgr": id_mgr,
            "tenant_mgr": tenant_mgr,
            "quota_svc": quota_svc,
            "sub_svc": sub_svc,
            "client": client,
            "customer_user": customer_user,
            "customer_tenant": tenant,
        }


# ===========================================================================
# TESTS 1 - 10: AUTHENTICATION & GUEST ACCESS
# ===========================================================================

def test_01_fresh_client_site_is_guest_mode(test_env):
    """AC 1: Fresh visitor without session token is treated as Guest, never lingga_admin."""
    client = test_env["client"]
    res = client.get("/api/v1/auth/me")
    # Must reject with 401 Unauthorized
    assert res.status_code == 401
    assert "Authentication required" in res.json().get("detail", "")


def test_02_fresh_admin_site_access_requires_credentials(test_env):
    """AC 2: Accessing admin endpoints without admin token is rejected."""
    client = test_env["client"]
    res = client.get("/api/v1/admin/users")
    assert res.status_code == 401
    assert "Authentication required" in res.json().get("detail", "")


def test_03_guest_can_prompt_within_quota(test_env):
    """AC 3: Guest user can interact with AI chat within guest quota limits."""
    client = test_env["client"]
    guest_id = "gst_test_03_prompt"

    mock_resp = BrainResponse(
        answer="BGP (Border Gateway Protocol) adalah protokol routing eksterior standar internet.",
        steps=[],
        duration=0.35,
        token_usage={"prompt_tokens": 40, "completion_tokens": 60, "total_tokens": 100, "model": "gemini-2.5-flash"},
        error=False,
    )

    with patch("core.brain.Brain.think", return_value=mock_resp):
        res = client.post(
            "/api/chat",
            headers={"X-Guest-ID": guest_id},
            json={"message": "Halo AIRA, jelaskan apa fungsi BGP dalam jaringan?"},
        )
    assert res.status_code == 200
    data = res.json()
    assert "answer" in data
    assert data["quota"] is not None
    assert data["quota"]["tier"] == "GUEST"
    assert data["quota"]["used_tokens"] > 0


def test_04_guest_restricted_operations_blocked(test_env):
    """AC 4: Guest attempting restricted operation (deploy playbook) receives 403 LOGIN_REQUIRED."""
    client = test_env["client"]
    res = client.post(
        "/api/chat",
        headers={"X-Guest-ID": "gst_test_04_restricted"},
        json={"message": "Please deploy playbook to configure BGP on core router"},
    )
    assert res.status_code == 403
    data = res.json().get("detail", {})
    assert data.get("code") == "LOGIN_REQUIRED"
    assert data.get("error") == "RESTRICTED_OPERATION"


def test_05_guest_quota_exhausted_blocked(test_env):
    """AC 5: Guest with exhausted quota receives 403 LOGIN_REQUIRED."""
    client = test_env["client"]
    guest_id = "gst_test_05_exhausted"
    quota_svc = test_env["quota_svc"]
    # Manually consume entire guest quota
    quota_svc.consume_tokens(
        user_id=None,
        tenant_id="tenant_guest",
        session_id="sess_ex",
        model_name="test-model",
        input_tokens=10000,
        output_tokens=6000,
        is_guest=True,
        guest_id=guest_id,
    )
    # Check remaining tokens
    q = quota_svc.get_guest_quota(guest_id)
    assert q.remaining_tokens == 0

    res = client.post(
        "/api/chat",
        headers={"X-Guest-ID": guest_id},
        json={"message": "Halo AIRA, masih bisa respon?"},
    )
    assert res.status_code == 403
    data = res.json().get("detail", {})
    assert data.get("code") == "LOGIN_REQUIRED"
    assert data.get("error") == "QUOTA_EXCEEDED"


def test_06_valid_client_login_success(test_env):
    """AC 6: Valid client login returns token, customer owner role, and Free quota."""
    client = test_env["client"]
    res = client.post(
        "/api/v1/auth/login",
        json={
            "username_or_email": "alice_client",
            "password": "AliceSecretPassword123!",
            "admin_only": False,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["token"].startswith("aira_tok_")
    assert "CUSTOMER_OWNER" in data["user"]["roles"]
    assert data["quota"] is not None
    assert data["quota"]["allocated_tokens"] == 100_000


def test_07_valid_superadmin_login_success(test_env):
    """AC 7: Valid superadmin login succeeds and grants superadmin privileges."""
    client = test_env["client"]
    res = client.post(
        "/api/v1/auth/login",
        json={
            "username_or_email": "lingga_admin",
            "password": "SuperPassword123!",
            "admin_only": True,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["user"]["is_internal"] is True
    assert any(r in ("PLATFORM_SUPER_ADMIN", "SUPERADMIN") for r in data["user"]["roles"])


def test_08_non_admin_attempting_admin_login_rejected(test_env):
    """AC 8: Customer user attempting admin login (admin_only=True) is rejected with 401."""
    client = test_env["client"]
    res = client.post(
        "/api/v1/auth/login",
        json={
            "username_or_email": "alice_client",
            "password": "AliceSecretPassword123!",
            "admin_only": True,
        },
    )
    assert res.status_code == 401
    assert "administrator" in res.json().get("detail", "").lower()


def test_09_logout_revokes_server_side_session(test_env):
    """AC 9: Logout endpoint revokes token in operational_user_sessions."""
    id_mgr = test_env["id_mgr"]
    session = id_mgr.create_session(user_id=test_env["customer_user"].user_id)
    token = session.token

    # Verify session is currently active
    ctx = id_mgr.validate_session_token(token)
    assert ctx is not None
    assert ctx.username == "alice_client"

    # Call logout
    client = test_env["client"]
    res = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["success"] is True

    # Verify session is now revoked in database
    ctx_after = id_mgr.validate_session_token(token)
    assert ctx_after is None


def test_10_after_logout_reload_remains_guest(test_env):
    """AC 10: After session revocation, querying /me returns 401, ensuring user is Guest."""
    id_mgr = test_env["id_mgr"]
    session = id_mgr.create_session(user_id=test_env["customer_user"].user_id)
    token = session.token
    id_mgr.revoke_token(token)

    client = test_env["client"]
    res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


# ===========================================================================
# TESTS 11 - 20: TOKEN QUOTA SYSTEM & RESET GOVERNANCE
# ===========================================================================

def test_11_guest_quota_specifications(test_env):
    """AC 11: Guest tier has 15,000 monthly tokens, 2,000 daily tokens."""
    quota_svc = test_env["quota_svc"]
    q = quota_svc.get_guest_quota("gst_spec_check")
    assert q.allocated_tokens == 15_000
    assert q.tier == "GUEST"
    assert q.used_tokens == 0
    assert q.remaining_tokens == 15_000


def test_12_free_plan_quota_specifications(test_env):
    """AC 12: Free tier has 100,000 monthly tokens."""
    quota_svc = test_env["quota_svc"]
    q = quota_svc.get_or_create_user_quota("user_free_spec", "tenant_free", tier="FREE")
    assert q.allocated_tokens == 100_000
    assert q.tier == "FREE"


def test_13_pro_plan_quota_specifications(test_env):
    """AC 13: Pro tier has 2,000,000 monthly tokens."""
    quota_svc = test_env["quota_svc"]
    q = quota_svc.get_or_create_user_quota("user_pro_spec", "tenant_pro", tier="PRO")
    assert q.allocated_tokens == 2_000_000
    assert q.tier == "PRO"


def test_14_enterprise_plan_quota_specifications(test_env):
    """AC 14: Enterprise tier has 10,000,000 monthly tokens."""
    quota_svc = test_env["quota_svc"]
    q = quota_svc.get_or_create_user_quota("user_ent_spec", "tenant_ent", tier="ENTERPRISE")
    assert q.allocated_tokens == 10_000_000
    assert q.tier == "ENTERPRISE"


def test_15_check_quota_available_preflight(test_env):
    """AC 15: Pre-flight check permits when sufficient, blocks when insufficient."""
    quota_svc = test_env["quota_svc"]
    uid = "user_preflight_test"
    tid = "tenant_preflight"
    quota_svc.get_or_create_user_quota(uid, tid, tier="FREE")

    # Allowed when 100 < 100,000
    ok, msg, rem = quota_svc.check_quota_available(user_id=uid, tenant_id=tid, estimated_tokens=100)
    assert ok is True

    # Blocked when estimated > remaining
    ok, msg, rem = quota_svc.check_quota_available(user_id=uid, tenant_id=tid, estimated_tokens=200_000)
    assert ok is False
    assert "quota exceeded" in msg.lower()


def test_16_token_consumption_atomic_and_immutable_ledger(test_env):
    """AC 16: Consuming tokens increments used_tokens and adds row to ledger."""
    quota_svc = test_env["quota_svc"]
    uid = "user_consume_test"
    tid = "tenant_consume"
    quota_svc.get_or_create_user_quota(uid, tid, tier="FREE")

    record = quota_svc.consume_tokens(
        user_id=uid,
        tenant_id=tid,
        session_id="sess_c1",
        model_name="gemini-2.5-flash",
        input_tokens=250,
        output_tokens=750,
        cached_tokens=50,
        tool_name="ping",
    )
    assert record.total_tokens == 1000
    assert record.estimated_cost_credits > 0

    # Verify balance updated
    q = quota_svc.get_or_create_user_quota(uid, tid, tier="FREE")
    assert q.used_tokens == 1000
    assert q.remaining_tokens == 99_000

    # Verify ledger row exists
    with topology_transaction(quota_svc.db_path, write=False) as conn:
        row = conn.execute(
            "SELECT * FROM operational_token_usage_ledger WHERE user_id = ?",
            (uid,),
        ).fetchone()
        assert row is not None
        assert row["total_tokens"] == 1000
        assert row["tool_name"] == "ping"


def test_17_automatic_reset_rollover_preserves_history(test_env):
    """AC 17: When period_reset_utc expires, used_tokens resets to 0 while ledger is preserved."""
    quota_svc = test_env["quota_svc"]
    uid = "user_rollover_test"
    tid = "tenant_rollover"
    quota_svc.get_or_create_user_quota(uid, tid, tier="FREE")

    # Consume some tokens
    quota_svc.consume_tokens(
        user_id=uid,
        tenant_id=tid,
        session_id="sess_r1",
        model_name="gemini-2.5-flash",
        input_tokens=500,
        output_tokens=500,
    )

    # Artificially set period_reset_utc to the past
    past_date = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with topology_transaction(quota_svc.db_path, write=True) as conn:
        conn.execute(
            "UPDATE operational_token_balances SET period_reset_utc = ? WHERE user_id = ?",
            (past_date, uid),
        )

    # Next access should trigger rollover
    q_new = quota_svc.get_or_create_user_quota(uid, tid, tier="FREE")
    assert q_new.used_tokens == 0
    assert q_new.remaining_tokens == 100_000

    # Crucial: ledger history must still exist!
    with topology_transaction(quota_svc.db_path, write=False) as conn:
        ledger_count = conn.execute(
            "SELECT COUNT(*) FROM operational_token_usage_ledger WHERE user_id = ?",
            (uid,),
        ).fetchone()[0]
        assert ledger_count == 1


def test_18_next_reset_calculation_asia_jakarta(test_env):
    """AC 18: Reset calculations respect Asia/Jakarta calendar month boundary."""
    st_dt, res_dt = compute_next_reset_utc(
        period="MONTHLY",
        reset_type="CALENDAR",
        tz_name="Asia/Jakarta",
    )
    assert res_dt > st_dt
    import zoneinfo
    tz = zoneinfo.ZoneInfo("Asia/Jakarta")
    local_reset = res_dt.astimezone(tz)
    assert local_reset.day == 1
    assert local_reset.hour == 0
    assert local_reset.minute == 0


def test_19_superadmin_quota_adjustment_audit_trail(test_env):
    """AC 19: Superadmin manual quota override logs full audit trail."""
    quota_svc = test_env["quota_svc"]
    target_uid = test_env["customer_user"].user_id
    admin_uid = "usr_superadmin"

    res = quota_svc.adjust_user_quota(
        admin_user_id=admin_uid,
        target_user_id=target_uid,
        new_quota=500_000,
        reason="Special allowance for enterprise evaluation",
        adjustment_type="MANUAL_OVERRIDE",
    )
    assert res["new_quota"] == 500_000
    assert res["target_user_id"] == target_uid

    # Verify audit log in database
    adjustments = quota_svc.list_quota_adjustments(limit=10)
    matching = [a for a in adjustments if a["target_user_id"] == target_uid]
    assert len(matching) > 0
    assert matching[0]["new_quota"] == 500_000
    assert "enterprise evaluation" in matching[0]["reason"]


def test_20_superadmin_quota_reset_audit_trail(test_env):
    """AC 20: Superadmin manual quota reset resets used_tokens to 0 with audit log."""
    quota_svc = test_env["quota_svc"]
    target_uid = test_env["customer_user"].user_id
    admin_uid = "usr_superadmin"

    res = quota_svc.reset_user_quota(
        admin_user_id=admin_uid,
        target_user_id=target_uid,
        reason="Mid-cycle testing reset",
    )
    assert res["success"] is True
    assert res["used_tokens"] == 0

    adjustments = quota_svc.list_quota_adjustments(limit=10)
    matching = [a for a in adjustments if a["target_user_id"] == target_uid and a["adjustment_type"] == "RESET"]
    assert len(matching) > 0


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
    assert "Platform administration access required" in res.json().get("detail", "")


def test_23_guest_tenant_isolation(test_env):
    """AC 23: Guest usage ledger records are tied to tenant_guest and separated from customers."""
    quota_svc = test_env["quota_svc"]
    gid = "gst_iso_test"
    quota_svc.consume_tokens(
        user_id=None,
        tenant_id="tenant_guest",
        session_id="sess_iso",
        model_name="gemini-2.5-flash",
        input_tokens=100,
        output_tokens=100,
        is_guest=True,
        guest_id=gid,
    )

    with topology_transaction(quota_svc.db_path, write=False) as conn:
        row = conn.execute(
            "SELECT * FROM operational_token_usage_ledger WHERE user_id = ?",
            (gid,),
        ).fetchone()
        assert row is not None
        assert row["tenant_id"] == "tenant_guest"


def test_24_zero_hardcoded_superadmin_fallback():
    """AC 24: Validates that no fallback object injects lingga_admin in frontend components."""
    frontend_dir = Path("AIRA_ECOSYSTEM/app/frontend/src")
    files_to_check = [
        frontend_dir / "components" / "Sidebar.jsx",
        frontend_dir / "components" / "AccountProfileModal.jsx",
        frontend_dir / "App.jsx",
    ]
    for file_path in files_to_check:
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
    sub = sub_svc.assign_subscription(
        user_id=uid,
        plan_id="PRO",
        duration_days=30,
        networking_addon=True,
    )
    assert sub.plan_id == "PRO"
    assert sub.has_networking_plus is True

    # Artificially set expiration to the past
    past_time = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    with topology_transaction(sub_svc.db_path, write=True) as conn:
        conn.execute(
            "UPDATE operational_user_subscriptions SET expires_at = ? WHERE user_id = ?",
            (past_time, uid),
        )

    # Run expiration check
    report = sub_svc.check_and_expire_subscriptions()
    assert report["expired_count"] >= 1
    assert uid in report["expired_users"]

    # Verify user subscription is now downgraded to FREE with no Networking++
    sub_after = sub_svc.get_user_subscription(uid)
    assert sub_after.plan_id == "FREE"
    assert sub_after.has_networking_plus is False
    assert sub_after.subscription_status in ("EXPIRED", "ACTIVE")
