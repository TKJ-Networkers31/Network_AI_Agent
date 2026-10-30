import tempfile
import unittest
from pathlib import Path

from core.inventory_store import InventoryStore
from agents.rei.inventory_tools import add_device, update_device, delete_device, list_credentials


class TestInventoryStore(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test_inventory.db"
        self.store = InventoryStore(db_path=self.db_path, seed=False)

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_device_with_multiple_credentials(self):
        result = self.store.create_device(
            name="Core_R1",
            host="192.168.88.1",
            port=22,
            username="admin",
            device_type="mikrotik",
            new_credentials=[
                {"name": "Core_R1_pass", "type": "ssh_password", "secret": "MikroTik123"},
                {"name": "Core_R1_api", "type": "api_key", "secret": "api-token-xyz"},
            ],
        )
        self.assertTrue(result["success"])
        device = result["device"]
        self.assertEqual(device["name"], "Core_R1")
        self.assertEqual(len(device["credentials"]), 2)

        # Cek resolusi SSH
        ssh_data = self.store.resolve_ssh("Core_R1")
        self.assertTrue(ssh_data["success"])
        self.assertEqual(ssh_data["password"], "MikroTik123")
        self.assertEqual(ssh_data["username"], "admin")

    def test_update_device_and_link_credentials(self):
        self.store.create_device(name="Switch_1", host="10.0.0.2")
        cred = self.store.create_credential(name="snmp_ro", type="snmp_community", secret="public")
        self.assertTrue(cred["success"])

        link_res = self.store.link_credential("Switch_1", "snmp_ro")
        self.assertTrue(link_res["success"])
        self.assertEqual(len(link_res["device"]["credentials"]), 1)

    def test_delete_device_preserves_credential(self):
        self.store.create_device(
            name="Temp_Dev",
            host="10.1.1.1",
            new_credential={"name": "shared_pass", "type": "ssh_password", "secret": "pass123"},
        )
        del_res = self.store.delete_device("Temp_Dev")
        self.assertTrue(del_res["success"])

        creds = self.store.list_credentials()
        self.assertTrue(any(c["name"] == "shared_pass" for c in creds["credentials"]))


if __name__ == "__main__":
    unittest.main()
