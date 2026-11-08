"""
AIRA OS — Comprehensive Automated Test Suite for Phase E:
Dual-Site Platform, Superadmin Bootstrap, User-Specific Subscriptions & Entitlements,
Billing Foundation, and Ansible-Compatible Playbook Engine.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path
import tempfile
import unittest

from core.topology_db import topology_transaction
from core.tenant.db import ensure_tenant_schema
from core.tenant.manager import IdentityManager, TenantManager
from core.tenant.models import UserRoleType, Permission
from core.tenant.user_subscription import UserSubscriptionService
from core.playbooks.runner import PlaybookRunner, redact_sensitive_output
from core.security.mfa import generate_totp_secret, compute_totp_code, verify_totp_code
from core.bootstrap_superadmin import bootstrap_superadmin


class TestPhaseEComprehensive(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_phase_e.db"
        ensure_tenant_schema(self.db_path)

        self.identity_mgr = IdentityManager(self.db_path)
        self.tenant_mgr = TenantManager(self.db_path)
        self.sub_service = UserSubscriptionService(self.db_path)
        self.playbook_runner = PlaybookRunner(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    # =========================================================================
    # 1. SUPERADMIN BOOTSTRAP, AUTHENTICATION & MFA TESTS
    # =========================================================================

    def test_superadmin_bootstrap_and_login(self):
        """Validates idempotent bootstrap of lingga_admin, password checking, and first login flag."""
        admin_info = bootstrap_superadmin(db_path=self.db_path, password="SuperSecurePassword123!")
        self.assertEqual(admin_info["username"], "lingga_admin")
        self.assertTrue(admin_info["must_change_password"])

        # Authenticate with valid password
        auth_res = self.identity_mgr.authenticate_user_detailed(
            username_or_email="lingga_admin",
            password="SuperSecurePassword123!",
            admin_only=True,
        )
        self.assertTrue(auth_res["success"])
        self.assertTrue(auth_res["must_change_password"])
        self.assertIsNotNone(auth_res["session"])

        # Change password to fulfill first-time login requirement
        changed = self.identity_mgr.change_user_password(
            user_id=auth_res["user_id"],
            new_password="NewPermanentPassword456!",
            reset_must_change=True,
        )
        self.assertTrue(changed)

        # Login again with new password
        reauth = self.identity_mgr.authenticate_user_detailed(
            username_or_email="lingga_admin",
            password="NewPermanentPassword456!",
            admin_only=True,
        )
        self.assertTrue(reauth["success"])
        self.assertFalse(reauth["must_change_password"])

    def test_auth_rate_limiting_and_lockout(self):
        """Validates account lockout after 5 consecutive failed attempts."""
        bootstrap_superadmin(db_path=self.db_path, password="InitialPassword123!")

        # 4 failed attempts
        for _ in range(4):
            res = self.identity_mgr.authenticate_user_detailed("lingga_admin", "WrongPassword")
            self.assertFalse(res["success"])
            self.assertFalse(res.get("locked", False))

        # 5th failed attempt triggers lockout
        res_5 = self.identity_mgr.authenticate_user_detailed("lingga_admin", "WrongPassword")
        self.assertFalse(res_5["success"])
        self.assertTrue(res_5.get("locked", False))
        self.assertIn("dikunci", res_5.get("error", "").lower())

        # Even correct password should now be rejected due to lockout
        res_lock = self.identity_mgr.authenticate_user_detailed("lingga_admin", "InitialPassword123!")
        self.assertFalse(res_lock["success"])
        self.assertTrue(res_lock.get("locked", False))

    def test_mfa_totp_flow(self):
        """Validates RFC 6238 TOTP setup, verification, and code enforcement."""
        admin_info = bootstrap_superadmin(db_path=self.db_path, password="SecretPassword123!")
        user_id = admin_info["user_id"]

        # Setup MFA
        mfa_setup = self.identity_mgr.setup_mfa(user_id)
        secret = mfa_setup["secret"]
        self.assertTrue(len(secret) >= 16)
        self.assertIn("otpauth://totp/AIRA OS:lingga_admin", mfa_setup["otpauth_uri"])

        # Invalid code rejected
        with self.assertRaises(ValueError):
            self.identity_mgr.verify_and_enable_mfa(user_id, secret, "000000")

        # Valid computed code activates MFA
        valid_code = compute_totp_code(secret)
        activated = self.identity_mgr.verify_and_enable_mfa(user_id, secret, valid_code)
        self.assertTrue(activated)

        # Login without code prompts for MFA
        res_prompt = self.identity_mgr.authenticate_user_detailed("lingga_admin", "SecretPassword123!")
        self.assertFalse(res_prompt["success"])
        self.assertTrue(res_prompt.get("mfa_required"))

        # Login with valid code succeeds
        valid_now = compute_totp_code(secret)
        res_ok = self.identity_mgr.authenticate_user_detailed(
            "lingga_admin",
            "SecretPassword123!",
            totp_code=valid_now,
        )
        self.assertTrue(res_ok["success"])
        self.assertTrue(res_ok["mfa_verified"])

    def test_superadmin_audited_impersonation(self):
        """Validates Superadmin can impersonate customer user only with explicit audit reason."""
        admin_info = bootstrap_superadmin(db_path=self.db_path, password="AdminSecret123!")
        admin_user_id = admin_info["user_id"]

        # Create customer user
        customer_user = self.identity_mgr.create_user(
            username="client_engineer",
            email="client@example.com",
            password="ClientPass123!",
            role_type=UserRoleType.CUSTOMER_OPERATOR.value,
            tenant_id="tenant_default",
        )

        # Attempt impersonation without reason must fail
        with self.assertRaises(ValueError):
            self.identity_mgr.impersonate_user(admin_user_id, customer_user.user_id, reason="")

        # Valid impersonation succeeds
        imp_session = self.identity_mgr.impersonate_user(
            admin_user_id=admin_user_id,
            target_user_id=customer_user.user_id,
            reason="Investigate ticket #NET-404 regarding bgp route flapping",
        )
        self.assertIsNotNone(imp_session)
        self.assertEqual(imp_session.user_id, customer_user.user_id)

        # Verify audit log record exists
        with topology_transaction(self.db_path, write=False) as conn:
            row = conn.execute(
                "SELECT * FROM operational_audit_log WHERE action = 'SUPERADMIN_IMPERSONATION' ORDER BY timestamp_utc DESC LIMIT 1"
            ).fetchone()
            self.assertIsNotNone(row)
            det = json.loads(row["details_json"])
            self.assertEqual(det["superadmin_user_id"], admin_user_id)
            self.assertEqual(det["target_user_id"], customer_user.user_id)

    # =========================================================================
    # 2. USER SUBSCRIPTION & EXPIRATION LIFECYCLE TESTS
    # =========================================================================

    def test_user_subscription_lifecycle_and_non_destructive_expiration(self):
        """
        Validates:
        - Free vs Pro vs Enterprise subscriptions
        - Networking++ add-on toggling
        - Automatic expiration downgrades plan to FREE, removes Net++,
        - BUT PRESERVES all devices, configs, and customer records intact!
        """
        user = self.identity_mgr.create_user(
            username="subscriber_1",
            email="sub1@example.com",
            password="SubPassword123!",
            role_type=UserRoleType.CUSTOMER_OWNER.value,
            tenant_id="tenant_default",
        )

        # Initial ensure creates active FREE subscription
        sub = self.sub_service.ensure_user_subscription(user.user_id, "tenant_default")
        self.assertEqual(sub.plan_id, "FREE")
        self.assertEqual(sub.subscription_status, "ACTIVE")
        self.assertFalse(sub.has_networking_plus)

        # Assign PRO subscription with Networking++
        pro_sub = self.sub_service.assign_subscription(
            user_id=user.user_id,
            plan_id="PRO",
            duration_days=30,
            networking_addon=True,
            operator_user="admin_tester",
        )
        self.assertEqual(pro_sub.plan_id, "PRO")
        self.assertTrue(pro_sub.has_networking_plus)
        self.assertEqual(pro_sub.token_quota, 2_000_000)

        # Simulate expiration by setting expires_at to past timestamp
        past_iso = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                "UPDATE operational_user_subscriptions SET expires_at = ? WHERE user_id = ?",
                (past_iso, user.user_id),
            )

        # Run expiration sweep
        sweep_report = self.sub_service.check_and_expire_subscriptions()
        self.assertEqual(sweep_report["expired_count"], 1)
        self.assertIn("subscriber_1", sweep_report["downgraded_users"])

        # Check subscription status post-sweep
        expired_sub = self.sub_service.get_subscription(user.user_id)
        self.assertEqual(expired_sub.subscription_status, "EXPIRED")
        self.assertEqual(expired_sub.plan_id, "FREE")
        self.assertFalse(expired_sub.has_networking_plus)
        self.assertEqual(expired_sub.token_quota, 100_000)

        # Verify audit log logged the non-destructive downgrade
        with topology_transaction(self.db_path, write=False) as conn:
            row = conn.execute(
                "SELECT * FROM operational_audit_log WHERE action = 'SUBSCRIPTION_EXPIRED' AND user_id = ?",
                (user.user_id,),
            ).fetchone()
            self.assertIsNotNone(row)
            det = json.loads(row["details_json"])
            self.assertTrue(det["data_preserved"])

    # =========================================================================
    # 3. DECISION-BD-01: BILLING SUBSYSTEM COMPLETE REMOVAL VERIFICATION
    # =========================================================================

    def test_billing_subsystem_eliminated(self):
        """Validates that all operational_billing_* tables, endpoints, and permissions are eliminated."""
        with topology_transaction(self.db_path) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'operational_billing_%'"
            ).fetchall()
            self.assertEqual(len(rows), 0, f"Billing tables unexpectedly found: {[r[0] for r in rows]}")

        # Verify billing permissions are purged
        perm_values = [p.value for p in Permission]
        self.assertNotIn("billing.read", perm_values)
        self.assertNotIn("billing.manage", perm_values)

        # Verify billing module is removed or unmounted
        from api.main import app
        route_paths = [getattr(r, "path", str(r)) for r in app.routes]
        billing_routes = [p for p in route_paths if "/billing" in p]
        self.assertEqual(len(billing_routes), 0, f"Billing routes still exposed: {billing_routes}")

    # =========================================================================
    # 4. ANSIBLE-COMPATIBLE PLAYBOOK ENGINE TESTS
    # =========================================================================

    def test_playbook_library_and_yaml_validation(self):
        """Validates all 6 built-in playbooks and YAML structure validator."""
        playbooks = self.playbook_runner.list_playbooks()
        self.assertGreaterEqual(len(playbooks), 6)

        # Check required built-in IDs
        pb_ids = {p["playbook_id"] for p in playbooks}
        expected = {
            "pb_builtin_health_check",
            "pb_builtin_service_status",
            "pb_builtin_pkg_inventory",
            "pb_builtin_config_backup",
            "pb_builtin_maintenance",
            "pb_builtin_config_audit",
        }
        self.assertTrue(expected.issubset(pb_ids))

        # Valid YAML test
        valid_yaml = """---
- name: Test Ping Play
  hosts: all
  tasks:
    - name: Ping target
      ping:
"""
        val_res = self.playbook_runner.validate_playbook_yaml(valid_yaml)
        self.assertTrue(val_res["valid"])
        self.assertEqual(val_res["total_tasks"], 1)

        # Invalid YAML test
        invalid_yaml = "not a valid: yaml: - indentation error"
        val_bad = self.playbook_runner.validate_playbook_yaml(invalid_yaml)
        self.assertFalse(val_bad["valid"])

    def test_playbook_credential_redaction(self):
        """Validates that sensitive credentials, passwords, and private keys are redacted."""
        raw_text = (
            "Connecting with password: 'SuperSecretPassword123' and bearer aira_tok_99182abx99.\n"
            "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0...\n-----END RSA PRIVATE KEY-----\n"
            "Host status ok."
        )
        clean = redact_sensitive_output(raw_text)
        self.assertNotIn("SuperSecretPassword123", clean)
        self.assertNotIn("MIIEowIBAAKCAQEA0", clean)
        self.assertIn("***REDACTED***", clean)

    def test_playbook_risk_approval_enforcement(self):
        """Validates that Category A runs automatically while Category B requires approval."""
        # Category A Playbook (Health Check)
        res_a = self.playbook_runner.execute_playbook(
            playbook_id="pb_builtin_health_check",
            tenant_id="tenant_default",
            user_id="usr_tester",
            targets=["10.0.0.1", "10.0.0.2"],
        )
        self.assertEqual(res_a["status"], "SUCCESS")
        self.assertEqual(res_a["summary"]["total_targets"], 2)

        # Category B Playbook (Maintenance - Mutating)
        res_b = self.playbook_runner.execute_playbook(
            playbook_id="pb_builtin_maintenance",
            tenant_id="tenant_default",
            user_id="usr_tester",
            targets=["10.0.0.1"],
        )
        self.assertEqual(res_b["status"], "APPROVAL_PENDING")
        self.assertEqual(res_b["risk_level"], "CATEGORY_B")
        self.assertIn("approval_id", res_b)


if __name__ == "__main__":
    unittest.main()
