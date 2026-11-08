"""
tests/test_topology.py — Unit tests untuk TopologyEngine dan REST API /api/topology.
"""

import tempfile
import unittest
from pathlib import Path

from core.topology_engine import TopologyEngine


class TestTopologyEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_topology.db"
        self.engine = TopologyEngine(self.db_path)

    def tearDown(self):
        import core.topology_engine as te_module
        import core.inventory_store as inv_module
        import core.nms_engine as nms_module
        te_module._engine_instance = None
        inv_module._store_singleton = None
        nms_module._GLOBAL_NMS_ENGINE = None
        self.temp_dir.cleanup()

    def test_upsert_and_get_nodes(self):
        res1 = self.engine.upsert_node(
            node_id="node_r1",
            name="Router-Core",
            identity="Core-CCR",
            ip="192.168.1.1",
            device_type="router",
            status="online",
            pos_x=100.0,
            pos_y=200.0,
        )
        self.assertTrue(res1["success"])

        res2 = self.engine.upsert_node(
            node_id="node_sw1",
            name="Switch-Floor1",
            identity="SW1",
            ip="192.168.1.2",
            device_type="switch",
            status="online",
            pos_x=300.0,
            pos_y=200.0,
        )
        self.assertTrue(res2["success"])

        # Link them
        link_res = self.engine.upsert_link(
            source_id="node_r1",
            target_id="node_sw1",
            source_port="ether1",
            target_port="ether24",
            bandwidth="1 Gbps",
        )
        self.assertTrue(link_res["success"])

        topo = self.engine.get_topology()
        self.assertEqual(len(topo["nodes"]), 2)
        self.assertEqual(len(topo["links"]), 1)
        self.assertEqual(topo["stats"]["total_nodes"], 2)
        self.assertEqual(topo["stats"]["online"], 2)

    def test_parse_mikrotik_neighbors(self):
        raw = """
 0 interface=ether2 mac-address=48:8F:5A:11:22:33 identity="SW-Distribution"
   platform="MikroTik" version="7.16" address=192.168.88.2 board="CRS326-24G-2S+"

 1 interface=ether3 mac-address=00:15:5D:AA:BB:CC identity="AP-Meeting"
   platform="MikroTik" version="7.16" address=192.168.88.3 board="cAP ax"
"""
        neighbors = self.engine.parse_mikrotik_neighbors(raw)
        self.assertEqual(len(neighbors), 2)
        self.assertEqual(neighbors[0]["identity"], "SW-Distribution")
        self.assertEqual(neighbors[0]["address"], "192.168.88.2")
        self.assertEqual(neighbors[1]["identity"], "AP-Meeting")

    def test_troubleshoot_root_cause_analysis(self):
        # Setup linear topology: Core -> Switch -> AP
        self.engine.upsert_node(node_id="core", name="Core-Router", ip="10.0.0.1", device_type="router", status="online")
        self.engine.upsert_node(node_id="switch", name="Switch-Lt2", ip="10.0.0.2", device_type="switch", status="offline")
        self.engine.upsert_node(node_id="ap", name="AP-Lantai2", ip="10.0.0.3", device_type="access_point", status="offline")

        self.engine.upsert_link(source_id="core", target_id="switch", source_port="sfp1", target_port="sfp1")
        self.engine.upsert_link(source_id="switch", target_id="ap", source_port="ether1", target_port="ether1")

        # Troubleshoot AP: should detect that Switch-Lt2 is the ROOT CAUSE
        report = self.engine.troubleshoot_node("ap")
        self.assertTrue(report["success"])
        self.assertIsNotNone(report["root_cause_node"])
        self.assertEqual(report["root_cause_node"]["id"], "switch")
        self.assertIn("ROOT CAUSE TERDETEKSI", report["diagnosis"])

    def test_add_node_inventory_registration_and_testing(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.routers.topology import router as topology_router
        from core.inventory_store import InventoryStore
        import core.topology_engine as te_module
        import core.inventory_store as inv_module
        import core.nms_engine as nms_module

        inv_path = Path(self.temp_dir.name) / "test_inv.db"
        test_inv = InventoryStore(db_path=inv_path, seed=False)

        te_module._engine_instance = self.engine
        inv_module._store_singleton = test_inv
        nms_module._GLOBAL_NMS_ENGINE = nms_module.NmsEngine(self.db_path)

        try:
            app = FastAPI()
            app.include_router(topology_router)
            client = TestClient(app)

            # 1. Test POST /api/topology/nodes with register_inventory=True
            res = client.post(
                "/api/topology/nodes",
                json={
                    "id": "node_core_test",
                    "name": "Router-Core-HQ",
                    "ip": "192.168.10.1",
                    "port": 22,
                    "username": "admin",
                    "password": "supersecretpassword123",
                    "device_type": "router",
                    "register_inventory": True,
                },
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data.get("success"))
            self.assertNotIn("supersecretpassword123", str(data))

            # Verify registered in InventoryStore
            dev_res = test_inv.get_device("Router-Core-HQ")
            self.assertTrue(dev_res.get("success"))
            dev = dev_res["device"]
            self.assertEqual(dev["host"], "192.168.10.1")
            self.assertEqual(dev["port"], 22)
            self.assertEqual(dev["username"], "admin")
            self.assertTrue(len(dev["credentials"]) > 0)

            # 2. Add duplicate by IP: should link/update and not create duplicate
            res2 = client.post(
                "/api/topology/nodes",
                json={
                    "id": "node_core_dup",
                    "name": "Router-Core-HQ",
                    "ip": "192.168.10.1",
                    "port": 2222,
                    "register_inventory": True,
                },
            )
            self.assertEqual(res2.status_code, 200)
            list_res = test_inv.list_devices()
            self.assertEqual(list_res["count"], 1)

            # 3. Test POST /api/topology/nodes/test
            res_test = client.post(
                "/api/topology/nodes/test",
                json={
                    "host": "127.0.0.1",
                    "port": 65534,
                    "username": "admin",
                    "password": "secret_dont_leak",
                },
            )
            self.assertEqual(res_test.status_code, 200)
            test_data = res_test.json()
            self.assertTrue(test_data["success"])
            self.assertIn("reachable", test_data)
            self.assertNotIn("secret_dont_leak", str(test_data))

        finally:
            te_module._engine_instance = None
            inv_module._store_singleton = None
            nms_module._GLOBAL_NMS_ENGINE = None


if __name__ == "__main__":
    unittest.main()
