"""
tests/test_networking_iii_api.py — Integration tests for Phase Networking III REST API endpoints.
"""

import pytest
from starlette.testclient import TestClient
from api.main import app
from core.network_intelligence.metrics_service import (
    NmsHistoricalMetricsService,
    NormalizedDeviceMetric,
    NormalizedInterfaceMetric,
)


from tests.auth_helper import get_test_auth_headers


@pytest.fixture
def client():
    # Use TestClient with authenticated session and topology admin headers
    return TestClient(app, headers=get_test_auth_headers())


def test_api_multi_device_batch_collect(client):
    res = client.post(
        "/api/intelligence/devices/batch-collect",
        json={
            "targets": ["mock_device_1", "mock_device_2"],
            "required_types": ["interfaces", "ip_addresses", "routes"],
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "summary" in data
    assert data["total_devices"] == 2
    assert "device_summaries" in data["summary"]


def test_api_multi_device_correlation(client):
    res = client.post(
        "/api/intelligence/correlation",
        json={
            "targets": ["mock_device_1", "mock_device_2"],
            "required_types": ["interfaces", "ip_addresses", "routes", "arp"],
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "relationships" in data
    assert "count" in data


def test_api_multi_device_investigation(client):
    res = client.post(
        "/api/intelligence/multi-device-investigation",
        json={
            "primary_device": "Core-1",
            "related_devices": ["ISP-1"],
            "symptom_description": "Uplink packet drop suspected between Core and ISP",
            "incident_type": "DEFAULT_ROUTE_FAILS",
            "severity": "HIGH",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "incident" in data
    inc = data["incident"]
    assert inc["device_identity"] == "Core-1"
    assert "ISP-1" in inc["related_devices"]
    assert inc["investigation_status"] == "DIAGNOSIS_READY"


def test_api_metrics_history(client):
    # Ingest synthetic metric first
    svc = NmsHistoricalMetricsService()
    import time
    now = time.time()
    svc.ingest_device_metric(NormalizedDeviceMetric(
        device_id="ApiTestDev",
        timestamp=now,
        cpu_load_percent=33.5,
        memory_used_percent=45.0,
        latency_ms=4.2,
    ))

    res = client.get(
        "/api/intelligence/metrics/history",
        params={"device_id": "ApiTestDev", "limit": 10},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["device_id"] == "ApiTestDev"
    assert data["count"] >= 1
    assert data["metrics"][0]["cpu_load_percent"] == 33.5
