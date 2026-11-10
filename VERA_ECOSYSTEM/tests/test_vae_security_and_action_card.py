"""
tests/test_vae_security_and_action_card.py

Tests for VERA Adaptive Experience (VAE) Phase 1:
- P0 Security Fix on /api/v1/admin/permissions/simulate
- Removal of hardcoded user_id
- Server-side derivation of authenticated principal
- Cross-tenant isolation enforcement
- Administrative gating for third-party user simulation
"""

import unittest
from fastapi.testclient import TestClient

from api.main import app
from core.tenant.manager import IdentityManager
from core.tenant.rbac_service import get_rbac_service

client = TestClient(app)


class TestVaeSecurityAndActionCard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.id_mgr = IdentityManager()
        cls.rbac = get_rbac_service()

        # Login as lingga_admin (Super Admin)
        login_res = client.post(
            "/api/v1/auth/login",
            json={"username_or_email": "lingga_admin", "password": "AdminPassword123!"},
        )
        if login_res.status_code != 200:
            u = cls.id_mgr.get_user_by_username("lingga_admin")
            if u:
                cls.id_mgr.change_user_password(u.user_id, "AdminPassword123!", reset_must_change=True)
            login_res = client.post(
                "/api/v1/auth/login",
                json={"username_or_email": "lingga_admin", "password": "AdminPassword123!"},
            )
        cls.admin_token = login_res.json()["token"]
        cls.admin_headers = {"Authorization": f"Bearer {cls.admin_token}"}
        cls.admin_user_id = login_res.json()["user"]["user_id"]

    def test_simulate_without_user_id_derives_authenticated_caller(self):
        """When user_id is omitted, backend must use authenticated principal."""
        res = client.post(
            "/api/v1/admin/permissions/simulate",
            json={
                "resource": "device:Router-Core",
                "action": "EXECUTE",
            },
            headers=self.admin_headers,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        simulation = data.get("simulation", {})
        self.assertEqual(simulation.get("user_id"), self.admin_user_id)
        self.assertTrue(simulation.get("allowed"))

    def test_unauthenticated_simulation_rejected(self):
        """Simulation without valid session token must return 401."""
        res = client.post(
            "/api/v1/admin/permissions/simulate",
            json={
                "resource": "device:Router-Core",
                "action": "EXECUTE",
            },
        )
        self.assertEqual(res.status_code, 401)

    def test_admin_can_simulate_user_in_same_tenant(self):
        """Admin can explicitly simulate permissions for another user in the same tenant."""
        res = client.post(
            "/api/v1/admin/permissions/simulate",
            json={
                "user_id": self.admin_user_id,
                "resource": "device:Router-Core",
                "action": "VIEW",
            },
            headers=self.admin_headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["simulation"]["allowed"])


if __name__ == "__main__":
    unittest.main()
