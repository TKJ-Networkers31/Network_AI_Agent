"""
tests/test_phase6_observability_and_security.py — Tests for Operational Observability & Security.

Phase 6: Verifies:
1. End-to-end correlation ID tracing across investigation and preflight
2. Credential masking and CLI output sanitization (zero secret leakage)
3. Backend read-only command validation and injection prevention
4. API endpoint authorization guards (HTTP 401/403 without token)
5. Multi-target isolation in investigation storage.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from core.network_intelligence.evidence import sanitize_raw_output
from core.network_intelligence.investigator import NetworkInvestigator
from core.network_intelligence.models import IncidentType, SeverityLevel
from core.network_intelligence.security import (
    mask_sensitive_data,
    validate_readonly_command,
)
from core.network_intelligence.store import get_network_intelligence_store


@pytest.fixture
def test_client():
    return TestClient(app)


def test_correlation_id_tracing_and_persistence():
    """Verifies that an investigation carries, stores, and retrieves correlation_id."""
    store = get_network_intelligence_store()
    investigator = NetworkInvestigator()

    test_corr_id = "corr_trace_phase6_998877"

    with patch.object(investigator.collector, "resolve_target_device", return_value=("R1", 7, "R1")):
        with patch.object(investigator.collector, "collect_evidence_bundle", return_value={
            "target": "R1",
            "ros_major_version": 7,
            "display_name": "R1",
            "evidence_items": [],
            "contradictions": [],
            "collection_errors": [],
        }):
            rec = investigator.create_and_run_investigation(
                device_identity="R1",
                incident_type=IncidentType.CUSTOM,
                user_description="Trace test",
                correlation_id=test_corr_id,
            )

            assert rec.correlation_id == test_corr_id

            # Verify persisted in SQLite store and retrieved accurately
            fetched = store.get_incident(rec.incident_id)
            assert fetched is not None
            assert fetched.correlation_id == test_corr_id


def test_credential_masking_in_cli_output():
    """Ensures passwords, secret keys, and tokens are redacted before storage or display."""
    raw_cli_sensitive = (
        "/user add name=backup password=SuperSecretPassword123 group=full\n"
        "/interface wireless security-profiles set default wpa2-pre-shared-key=WifiSecretKey999\n"
        "Authorization: Bearer secret-token-xyz-123456\n"
    )

    sanitized = sanitize_raw_output(raw_cli_sensitive)

    assert "SuperSecretPassword123" not in sanitized
    assert "WifiSecretKey999" not in sanitized
    assert "secret-token-xyz-123456" not in sanitized


def test_readonly_security_enforcement_blocks_mutations():
    """Verifies that mutating, dangerous, and injection commands are rejected."""
    dangerous_commands = [
        "/system reboot",
        "/system reset-configuration",
        "/user add name=hacker password=hacked",
        "/ip address set 0 address=192.168.1.1/24",
        "/ip route remove [find]",
        "/interface ethernet disable ether1",
        "/system identity print; /system reboot",
        "/ip route print & rm -rf /",
    ]

    for cmd in dangerous_commands:
        is_valid, reason = validate_readonly_command(cmd)
        assert is_valid is False, f"Command '{cmd}' should have been blocked, but was accepted!"
        assert len(reason) > 0


def test_api_intelligence_endpoints_require_authorization(test_client):
    """Verifies that intelligence endpoints reject unauthorized requests when admin token is configured."""
    with patch.dict("os.environ", {"AIRA_TOPOLOGY_ADMIN_TOKEN": "phase6-admin-secret"}):
        # 1. POST /api/intelligence/preflight without token
        res = test_client.post("/api/intelligence/preflight", json={"target": "R1"})
        assert res.status_code in (401, 403)

        # 2. POST /api/intelligence/incidents without token
        res = test_client.post("/api/intelligence/incidents", json={"device_identity": "R1"})
        assert res.status_code in (401, 403)

        # 3. POST /api/intelligence/plans without token
        res = test_client.post("/api/intelligence/plans", json={"target_device": "R1", "change_type": "ADD_VLAN"})
        assert res.status_code in (401, 403)


def test_target_investigation_isolation():
    """Verifies that investigations for different target devices remain strictly isolated."""
    store = get_network_intelligence_store()
    investigator = NetworkInvestigator()

    with patch.object(investigator.collector, "resolve_target_device", side_effect=[("R1", 7, "R1"), ("R2", 7, "R2")]):
        with patch.object(investigator.collector, "collect_evidence_bundle", return_value={
            "target": "mock",
            "ros_major_version": 7,
            "display_name": "mock",
            "evidence_items": [],
            "contradictions": [],
            "collection_errors": [],
        }):
            rec1 = investigator.create_and_run_investigation(device_identity="R1", incident_type=IncidentType.CUSTOM)
            rec2 = investigator.create_and_run_investigation(device_identity="R2", incident_type=IncidentType.CUSTOM)

            r1_list = store.list_incidents(device_identity="R1")
            r2_list = store.list_incidents(device_identity="R2")

            assert any(r.incident_id == rec1.incident_id for r in r1_list)
            assert not any(r.incident_id == rec2.incident_id for r in r1_list)

            assert any(r.incident_id == rec2.incident_id for r in r2_list)
            assert not any(r.incident_id == rec1.incident_id for r in r2_list)
