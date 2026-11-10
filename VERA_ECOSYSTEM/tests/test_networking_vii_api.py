"""
Tests for Networking VII Phase H (WP 7.9) — FastAPI Operations Gateway Endpoints.
"""

from __future__ import annotations

import time
import pytest
from fastapi.testclient import TestClient

from api.main import app
from tests.auth_helper import get_test_auth_headers


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, headers=get_test_auth_headers())


def test_api_predictive_overview(client: TestClient) -> None:
    """Tests GET /api/operations/predictive/overview."""
    response = client.get("/api/operations/predictive/overview")
    assert response.status_code == 200
    data = response.json()
    assert "report_id" in data
    assert "highest_risk_level" in data
    assert "projections" in data


def test_api_predictive_custom_forecast(client: TestClient) -> None:
    """Tests POST /api/operations/predictive/forecast with custom time series."""
    now = time.time()
    samples = [[now - (15 - i) * 60, 50.0 + (i * 1.5)] for i in range(16)]

    payload = {
        "metric_name": "rx_utilization_percent",
        "entity_type": "interface",
        "entity_id": "ether1",
        "device_id": "Core-1",
        "samples": samples,
        "window": "24h",
        "warning_threshold": 80.0,
        "critical_threshold": 95.0,
    }

    response = client.post("/api/operations/predictive/forecast", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "VALID"
    assert data["trend_direction"] == "RAPID_INCREASE"
    assert data["slope_per_hour"] is not None
    assert data["confidence_score"] >= 0.5


def test_api_change_impact_simulate(client: TestClient) -> None:
    """Tests POST /api/operations/change-impact/simulate."""
    payload = {
        "scenario_id": "scen_api_test",
        "title": "API Trunk Maintenance Simulation",
        "change_type": "INTERFACE_DOWN",
        "target_device": "Core-1",
        "target_entity": "sfp-sfpplus1",
        "description": "Simulate trunk maintenance",
    }

    response = client.post("/api/operations/change-impact/simulate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["is_simulation"] is True
    assert data["change_type"] == "INTERFACE_DOWN"
    assert len(data["preflight_checklist"]) >= 1
    assert len(data["rollback_plan"]) >= 1


def test_api_services_crud_and_health(client: TestClient) -> None:
    """Tests /api/operations/services endpoints."""
    # 1. Create service
    svc_id = f"svc_api_{int(time.time())}"
    create_payload = {
        "service_id": svc_id,
        "name": "API Gateway Cluster",
        "description": "Public REST endpoints",
        "criticality": "TIER_1_MISSION_CRITICAL",
        "owner_team": "APITeam",
        "endpoints": [
            {
                "endpoint_id": f"ep_api_1",
                "endpoint_type": "IP_PORT",
                "endpoint_value": "10.0.0.1:443",
                "target_device_id": "Core-1",
                "target_interface": "ether1",
                "is_primary": True,
            }
        ],
    }

    create_resp = client.post("/api/operations/services", json=create_payload)
    assert create_resp.status_code == 200
    assert create_resp.json()["service_id"] == svc_id

    # 2. List services
    list_resp = client.get("/api/operations/services")
    assert list_resp.status_code == 200
    assert any(s["service_id"] == svc_id for s in list_resp.json())

    # 3. Health check
    health_resp = client.get(f"/api/operations/services/{svc_id}/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["health_score"] == 100.0


def test_api_scheduler_and_job_run(client: TestClient) -> None:
    """Tests /api/operations/scheduler endpoints."""
    # 1. List jobs
    list_resp = client.get("/api/operations/scheduler/jobs")
    assert list_resp.status_code == 200

    # 2. Trigger run of built-in job
    jobs = list_resp.json()
    if jobs:
        target_job_id = jobs[0]["job_id"]
        run_resp = client.post(f"/api/operations/scheduler/jobs/{target_job_id}/run")
        assert run_resp.status_code == 200
        assert run_resp.json()["status"] == "SUCCESS"

    # 3. List recent runs
    runs_resp = client.get("/api/operations/scheduler/runs")
    assert runs_resp.status_code == 200
    assert isinstance(runs_resp.json(), list)


def test_api_calendar_windows_and_ics(client: TestClient) -> None:
    """Tests /api/operations/calendar endpoints."""
    now_iso = "2026-11-04T05:00:00Z"
    end_iso = "2026-11-04T07:00:00Z"

    # 1. Create window
    win_payload = {
        "title": "Scheduled Switch Reboot",
        "description": "Maintenance reboot of access switch",
        "scope_type": "DEVICE",
        "target_entities": ["Switch-01"],
        "start_time_utc": now_iso,
        "end_time_utc": end_iso,
        "suppress_alerts": True,
    }
    create_resp = client.post("/api/operations/calendar/windows", json=win_payload)
    assert create_resp.status_code == 200

    # 2. List windows
    list_resp = client.get("/api/operations/calendar/windows")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1

    # 3. Export ICS
    ics_resp = client.get("/api/operations/calendar/export.ics")
    assert ics_resp.status_code == 200
    assert "BEGIN:VCALENDAR" in ics_resp.text


def test_api_reports_generate(client: TestClient) -> None:
    """Tests GET /api/operations/reports/generate."""
    response = client.get("/api/operations/reports/generate?period=DAILY")
    assert response.status_code == 200
    data = response.json()
    assert data["period"] == "DAILY"
    assert "executive_summary" in data
    assert "markdown" in data
    assert "html" in data
    assert "AIRA OS" in data["markdown"]
