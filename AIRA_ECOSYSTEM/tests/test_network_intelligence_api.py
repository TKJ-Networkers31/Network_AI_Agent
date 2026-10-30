"""
AIRA_ECOSYSTEM/tests/test_network_intelligence_api.py —
Tests for Network Intelligence REST API Endpoints.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_api_list_playbooks():
    res = client.get("/api/intelligence/playbooks")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["count"] >= 7
    ids = [pb["playbook_id"] for pb in data["playbooks"]]
    assert "PB-LAN-INTERNET" in ids
    assert "PB-OSPF-ADJ" in ids


def test_api_create_investigation():
    mock_bundle = {
        "target": "R1",
        "ros_major_version": 7,
        "display_name": "R1",
        "evidence_items": [],
        "contradictions": [],
        "collection_errors": [],
    }

    with patch("core.network_intelligence.investigator.EvidenceCollector.collect_evidence_bundle", return_value=mock_bundle), \
         patch("core.network_intelligence.investigator.EvidenceCollector.resolve_target_device", return_value=("R1", 7, "R1")):

        res = client.post(
            "/api/intelligence/incidents",
            json={
                "device_identity": "R1",
                "incident_type": "LAN_NO_INTERNET",
                "symptoms": ["Klien tidak bisa ping 8.8.8.8"],
                "user_description": "Internet down untuk subnet kantor",
                "severity": "HIGH",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert "incident_id" in data["incident"]
        assert data["incident"]["incident_type"] == "LAN_NO_INTERNET"

        inc_id = data["incident"]["incident_id"]

        # Test GET /api/intelligence/incidents/{id}
        get_res = client.get(f"/api/intelligence/incidents/{inc_id}")
        assert get_res.status_code == 200
        assert get_res.json()["incident"]["incident_id"] == inc_id


def test_api_create_and_simulate_plan():
    mock_bundle = {
        "target": "R1",
        "ros_major_version": 7,
        "display_name": "R1",
        "evidence_items": [
            MagicMock(
                observation_type="routes",
                collection_status="SUCCESS",
                normalized_value={"routes": [{"dst_address": "0.0.0.0/0", "gateway": "192.168.1.1", "active": True}]},
            ),
            MagicMock(
                observation_type="interfaces",
                collection_status="SUCCESS",
                normalized_value={"interfaces": [{"name": "ether1", "running": True}]},
            ),
            MagicMock(
                observation_type="ip_addresses",
                collection_status="SUCCESS",
                normalized_value={"addresses": []},
            ),
            MagicMock(
                observation_type="bridge",
                collection_status="SUCCESS",
                normalized_value={},
            ),
        ],
        "contradictions": [],
        "collection_errors": [],
    }

    with patch("core.network_intelligence.planner.get_canonical_registry") as mock_get_reg, \
         patch("core.network_intelligence.validator.EvidenceCollector.collect_evidence_bundle", return_value=mock_bundle), \
         patch("core.network_intelligence.simulator.EvidenceCollector.collect_evidence_bundle", return_value=mock_bundle):

        mock_reg = MagicMock()
        mock_reg.resolve_device.return_value = MagicMock(inventory_name="R1", ros_major_version=7, os_version="7.14.3")
        mock_get_reg.return_value = mock_reg

        res = client.post(
            "/api/intelligence/plans",
            json={
                "target_device": "R1",
                "change_type": "ADD_STATIC_ROUTE",
                "parameters": {
                    "dst_address": "172.16.0.0/16",
                    "gateway": "192.168.1.254",
                    "distance": 1,
                },
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        plan = data["plan"]
        assert plan["plan_id"].startswith("plan_")
        assert len(plan["proposed_changes"]) >= 1
        assert "diff" in plan["configuration_diff"].lower() or "+" in plan["configuration_diff"]
        assert plan["simulation_results"] is not None
        assert plan["simulation_results"]["simulation_status"] in ("PASS", "SUCCESS")
