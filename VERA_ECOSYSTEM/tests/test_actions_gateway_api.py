"""
tests/test_actions_gateway_api.py — Action Gateway REST Endpoints Tests.

Validates:
- GET /api/v1/actions/registry returns standard typed actions.
- POST /api/v1/actions/execute handles action execution.
- POST /api/v1/actions/approval handles approve/reject decisions.
"""

import unittest
from fastapi.testclient import TestClient

from api.main import app
from tests.auth_helper import get_test_auth_headers


class TestActionsGatewayApi(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.client.headers.update(get_test_auth_headers())

    def test_get_action_registry(self):
        resp = self.client.get("/api/v1/actions/registry")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        actions = data.get("actions", [])
        types = [a["type"] for a in actions]
        self.assertIn("retry_operation", types)
        self.assertIn("edit_parameters", types)
        self.assertIn("cancel_workflow", types)
        self.assertIn("approve_action", types)

    def test_execute_generic_action(self):
        payload = {
            "action_id": "act_test_001",
            "action_type": "tool",
            "payload": {"tool": "network_ping", "args": {"target": "127.0.0.1"}},
        }
        resp = self.client.post("/api/v1/actions/execute", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("action_id"), "act_test_001")

    def test_submit_action_approval(self):
        payload = {
            "action_id": "act_plan_002",
            "decision": "APPROVE",
            "reason": "Operator confirmed safety window",
        }
        resp = self.client.post("/api/v1/actions/approval", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("decision"), "APPROVE")


if __name__ == "__main__":
    unittest.main()
