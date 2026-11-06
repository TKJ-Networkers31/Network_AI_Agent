"""
AIRA OS — PHASE F.2 AUTOMATED ACCEPTANCE TEST SUITE
Tests:
1. Dynamic Interactive Form Generation for Device Registration (DIO)
2. Interactive Form Submission Parsing & Execution via Orchestrator
3. Granular RBAC Permissions (Navigation vs Action Permissions & Aliases)
4. Protected API Endpoints Authorization (Inventory, Logs, Personalization)
5. Personalization Isolation & Custom Instructions Storage
"""

import os
import unittest
from fastapi.testclient import TestClient

from api.main import app
from core.orchestrator import Orchestrator
from core.memory import ConversationMemory
from core.dio.parameter_resolver import build_device_registration_schema
from core.tenant.manager import IdentityManager
from core.tenant.models import TenantContext
from core.tenant.rbac_service import get_rbac_service, ALL_PERMISSIONS, DEFAULT_GROUP_PERMISSIONS
from core.inventory_store import get_inventory_store
from core.topology_engine import get_topology_engine

client = TestClient(app)


class TestPhaseF2DynamicUIRBAC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.id_mgr = IdentityManager()
        cls.rbac = get_rbac_service()
        cls.inv_store = get_inventory_store()
        cls.topo = get_topology_engine()

        # Create test session for lingga_admin (SUPER_ADMIN)
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

        # Create or ensure a limited test user with READ_ONLY group
        cls.readonly_username = "test_f2_readonly"
        user_info = cls.id_mgr.get_user_by_username(cls.readonly_username)
        if not user_info:
            created = cls.id_mgr.create_user(
                username=cls.readonly_username,
                password="ReadOnlyPass123!",
                display_name="F2 Read Only User",
                email="f2_readonly@aira.local",
                group_name="READ_ONLY",
                tenant_id="tenant_default",
            )
            cls.readonly_uid = created.user_id
        else:
            cls.readonly_uid = user_info.user_id

        # Ensure user is in READ_ONLY group only
        cls.rbac.assign_user_groups(cls.readonly_uid, ["READ_ONLY"])

        # Authenticate read-only user via login endpoint
        ro_login = client.post(
            "/api/v1/auth/login",
            json={"username_or_email": cls.readonly_username, "password": "ReadOnlyPass123!"},
        )
        cls.readonly_token = ro_login.json()["token"]
        cls.readonly_headers = {"Authorization": f"Bearer {cls.readonly_token}"}

    @classmethod
    def tearDownClass(cls):
        # Cleanup test device if any left
        cls.inv_store.delete_device("Router_F2_TestDevice")
        cls.topo.delete_node("node_router_f2_testdevice")

    # -------------------------------------------------------------------------
    # 1. DIO Dynamic Interactive Form Schema Generation
    # -------------------------------------------------------------------------
    def test_01_build_device_registration_schema(self):
        """Validates canonical 7-field device registration form schema."""
        schema = build_device_registration_schema(initial_values={"name": "Core-R1"})
        
        self.assertEqual(schema["type"], "interactive_form")
        self.assertEqual(schema["requested_for"], "add_device")
        self.assertEqual(schema["form_id"], "device_registration")
        
        # Check canonical 7 fields in flat fields
        fields = schema.get("fields", [])
        field_names = [f["name"] for f in fields]
        expected_fields = ["name", "host", "username", "password", "device_type", "port", "note"]
        for ef in expected_fields:
            self.assertIn(ef, field_names, f"Field '{ef}' must be in schema fields")

        # Check hierarchical sections structure
        sections = schema.get("sections", [])
        self.assertTrue(len(sections) >= 1)
        section_fields = [f.get("id") or f.get("name") or f.get("key") for s in sections for f in s.get("fields", [])]
        for ef in expected_fields:
            self.assertIn(ef, section_fields, f"Field '{ef}' must be in schema section fields")

        # Check default value passed through
        name_field = next(f for f in fields if f["name"] == "name")
        self.assertEqual(name_field["default"], "Core-R1")

        # Check choice options for device_type
        dtype_field = next(f for f in fields if f["name"] == "device_type")
        opt_values = [o["value"] if isinstance(o, dict) else o for o in dtype_field["options"]]
        self.assertIn("mikrotik", opt_values)
        self.assertIn("linux", opt_values)

    # -------------------------------------------------------------------------
    # 2. Orchestrator Dynamic Form Generation & Submission Execution
    # -------------------------------------------------------------------------
    def test_02_orchestrator_returns_interactive_form_on_add_device_intent(self):
        """
        When user asks: 'Tambahkan router baru ke inventory',
        AIRA MUST return a structured interactive form schema, NOT plain markdown text.
        """
        orch = Orchestrator()
        result = orch.route("Tambahkan router baru ke inventory", ConversationMemory(), context={"username": "lingga_admin"})

        self.assertIn("interaction_schema", result)
        schema = result["interaction_schema"]
        self.assertIsNotNone(schema, "interaction_schema must not be None")
        self.assertEqual(schema["type"], "interactive_form")
        self.assertEqual(schema["requested_for"], "add_device")

        # Must have canonical fields
        field_names = [f["name"] for f in schema.get("fields", [])]
        self.assertIn("name", field_names)
        self.assertIn("host", field_names)
        self.assertIn("username", field_names)

    def test_03_orchestrator_executes_device_registration_form_submission(self):
        """
        When user submits the interactive form with values,
        AIRA parses the submission, checks authorization, executes add_device,
        and registers the device to inventory and topology.
        """
        orch = Orchestrator()
        test_dev_name = "Router_F2_TestDevice"

        # Pre-cleanup in case previous run left artifacts
        self.inv_store.delete_device(test_dev_name)
        self.inv_store.delete_credential(f"{test_dev_name}-ssh")
        self.inv_store.delete_credential(f"{test_dev_name.lower()}-ssh")
        self.topo.delete_node(f"node_{test_dev_name.lower()}")

        submission_text = (
            f"[Form Submission: add_device]\n"
            f"name: {test_dev_name}\n"
            f"host: 192.168.200.1\n"
            f"username: testadmin\n"
            f"password: TestPassword123!\n"
            f"device_type: mikrotik\n"
            f"port: 22\n"
            f"note: Automated F2 integration test device"
        )

        res = orch.route(submission_text, ConversationMemory(), context={"username": "lingga_admin"})
        self.assertIn("answer", res)
        self.assertIn(test_dev_name, res["answer"])
        self.assertIn("berhasil didaftarkan", res["answer"].lower())

        # Verify device actually exists in inventory store
        inv_dev = self.inv_store.get_device(test_dev_name)
        self.assertTrue(inv_dev.get("success"), f"Device '{test_dev_name}' must exist in inventory store")
        self.assertEqual(inv_dev["device"]["host"], "192.168.200.1")

        # Cleanup
        self.inv_store.delete_device(test_dev_name)
        self.inv_store.delete_credential(f"{test_dev_name}-ssh")
        self.inv_store.delete_credential(f"{test_dev_name.lower()}-ssh")
        self.topo.delete_node(f"node_{test_dev_name.lower()}")

    # -------------------------------------------------------------------------
    # 3. RBAC Granularity: Navigation vs Action Permissions & Aliases
    # -------------------------------------------------------------------------
    def test_04_canonical_permissions_coverage(self):
        """Validates that navigation and action permissions are in canonical catalog."""
        all_ids = {p["permission_id"] for p in ALL_PERMISSIONS}

        # Navigation permissions
        nav_perms = [
            "dashboard.view", "workspace.view", "inventory.view", "topology.view",
            "nms.view", "automations.view", "files.view", "models.view",
            "logs.view", "settings.view", "admin.view"
        ]
        for np in nav_perms:
            self.assertIn(np, all_ids, f"Navigation permission '{np}' must exist in catalog")

        # Action permissions
        action_perms = [
            "inventory.device.create", "inventory.device.read", "inventory.device.update",
            "inventory.device.delete", "inventory.device.ssh", "topology.device.discover",
            "nms.monitoring.read", "nms.monitoring.configure",
            "settings.memory.view", "settings.memory.update",
            "settings.persona.view", "settings.persona.update"
        ]
        for ap in action_perms:
            self.assertIn(ap, all_ids, f"Action permission '{ap}' must exist in catalog")

    def test_05_tenant_context_permission_aliases(self):
        """
        Validates that TenantContext.has_permission seamlessly resolves aliases
        between canonical action names and legacy names.
        """
        # User with canonical inventory.device.create
        ctx_create = TenantContext(
            user_id="u_test",
            username="test_user",
            is_internal=False,
            tenant_id=None,
            permissions={"inventory.device.create"},
        )
        self.assertTrue(ctx_create.has_permission("inventory.device.create"))
        self.assertTrue(ctx_create.has_permission("inventory.create"))
        self.assertTrue(ctx_create.has_permission("devices.create"))
        self.assertFalse(ctx_create.has_permission("inventory.device.delete"))

        # User with canonical logs.view
        ctx_logs = TenantContext(
            user_id="u_test2",
            username="test_user2",
            is_internal=False,
            tenant_id=None,
            permissions={"logs.view"},
        )
        self.assertTrue(ctx_logs.has_permission("logs.view"))
        self.assertTrue(ctx_logs.has_permission("audit.read"))

        # Read-only user lacks create permission
        ctx_ro = TenantContext(
            user_id="u_ro",
            username="ro_user",
            is_internal=False,
            tenant_id=None,
            permissions=DEFAULT_GROUP_PERMISSIONS["READ_ONLY"],
        )
        self.assertTrue(ctx_ro.has_permission("inventory.view"))
        self.assertTrue(ctx_ro.has_permission("inventory.device.read"))
        self.assertFalse(ctx_ro.has_permission("inventory.device.create"))
        self.assertFalse(ctx_ro.has_permission("inventory.device.delete"))

    # -------------------------------------------------------------------------
    # 4. Protected API Endpoints Authorization
    # -------------------------------------------------------------------------
    def test_06_devices_api_authorization(self):
        """Validates that GET /api/devices allows read-only and POST blocks read-only."""
        # GET /api/devices should succeed for read-only user
        res_get = client.get("/api/devices", headers=self.readonly_headers)
        self.assertEqual(res_get.status_code, 200)

        # POST /api/devices should return 403 Forbidden for read-only user
        dev_payload = {
            "name": "Unauthorized_Router",
            "host": "10.0.0.99",
            "port": 22,
            "device_type": "mikrotik",
        }
        res_post = client.post("/api/devices", headers=self.readonly_headers, json=dev_payload)
        self.assertEqual(res_post.status_code, 403)
        self.assertIn("Akses ditolak", str(res_post.json()))

    def test_07_personalization_api_authorization(self):
        """Validates memory and persona permission enforcement in personalization API."""
        # Lingga Admin (SUPER_ADMIN) can access and add memory
        mem_payload = {
            "content": "Preferensi konfigurasi router BGP ASN 65001",
            "category": "technical",
            "importance": 85,
        }
        res_admin = client.post(
            "/api/v1/personalization/memories",
            headers=self.admin_headers,
            json=mem_payload,
        )
        self.assertEqual(res_admin.status_code, 200)
        mem_data = res_admin.json()
        self.assertTrue(mem_data["success"])
        created_mem_id = mem_data["memory"]["memory_id"]

        # READ_ONLY user CAN view memory
        res_ro_get = client.get("/api/v1/personalization/memories", headers=self.readonly_headers)
        self.assertEqual(res_ro_get.status_code, 200)

        # READ_ONLY user CANNOT add memory (requires settings.memory.update)
        res_ro_post = client.post(
            "/api/v1/personalization/memories",
            headers=self.readonly_headers,
            json=mem_payload,
        )
        self.assertEqual(res_ro_post.status_code, 403)

        # Cleanup memory
        client.delete(f"/api/v1/personalization/memories/{created_mem_id}", headers=self.admin_headers)

    def test_08_personalization_custom_instructions_persisted(self):
        """Validates that custom instructions are saved and retrieved accurately."""
        test_instructions = "Selalu gunakan sintaks RouterOS v7 dan sertakan rollback plan."
        patch_res = client.patch(
            "/api/v1/personalization/preferences",
            headers=self.admin_headers,
            json={"custom_instructions": test_instructions},
        )
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.json()["preferences"]["custom_instructions"], test_instructions)

        # Verify retrieval via GET
        get_res = client.get("/api/v1/personalization/preferences", headers=self.admin_headers)
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.json()["preferences"]["custom_instructions"], test_instructions)


if __name__ == "__main__":
    unittest.main()
