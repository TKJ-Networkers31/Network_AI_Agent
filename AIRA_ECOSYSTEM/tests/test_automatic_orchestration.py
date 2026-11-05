"""
tests/test_automatic_orchestration.py — Acceptance and Regression Testing for the
Unified Automatic Network Diagnostic & Planning Pipeline.
"""

import unittest
from fastapi.testclient import TestClient

from api.main import app
from core.network_intelligence.auto_orchestrator import AutomaticNetworkOrchestrator, get_auto_orchestrator
from agents.akane.network_tools import auto_diagnose_network
from core.inventory_store import get_inventory_store


class TestAutomaticOrchestration(unittest.TestCase):
    def setUp(self):
        self.orchestrator = AutomaticNetworkOrchestrator()
        self.client = TestClient(app)

    def test_target_resolution_auto_picks_single_inventory_device(self):
        targets = self.orchestrator.resolve_target_devices(None)
        self.assertIsInstance(targets, list)
        self.assertGreaterEqual(len(targets), 1)
        # In current cleaned lab, CHR is the sole device
        self.assertIn("CHR", targets)

    def test_target_resolution_custom_target(self):
        targets = self.orchestrator.resolve_target_devices(["chr"])
        self.assertEqual(targets, ["CHR"])

    def test_end_to_end_auto_diagnosis_execution(self):
        res = self.orchestrator.execute_auto_diagnosis(
            target_devices=["CHR"],
            symptom="Tidak bisa ping ke gateway internet 8.8.8.8",
            target_ip="8.8.8.8",
            auto_plan=True,
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["primary_device"], "CHR")
        self.assertTrue(res["read_only"])
        self.assertIn("observed_facts", res)
        self.assertIsInstance(res["observed_facts"], list)
        self.assertIn("ranked_hypotheses", res)
        self.assertIsInstance(res["ranked_hypotheses"], list)
        self.assertIn("summary", res)
        self.assertIn("safety_disclosure", res)
        self.assertIn("Read-Only", res["safety_disclosure"])

    def test_rest_api_auto_diagnose_endpoint(self):
        response = self.client.post(
            "/api/intelligence/auto-diagnose",
            json={
                "target_devices": ["CHR"],
                "symptom": "Rute terputus dan packet loss tinggi",
                "target_ip": "192.168.43.1",
                "auto_plan": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "completed")
        self.assertEqual(data["primary_device"], "CHR")
        self.assertTrue(data["read_only"])

    def test_akane_agent_tool_auto_diagnose_network(self):
        res = auto_diagnose_network(
            device_name="CHR",
            symptom="Koneksi lambat dan intermittency",
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["primary_device"], "CHR")


if __name__ == "__main__":
    unittest.main()
