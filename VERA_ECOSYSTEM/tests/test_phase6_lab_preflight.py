"""
tests/test_phase6_lab_preflight.py — Comprehensive tests for Lab Preflight Diagnostic Engine.

Phase 6: Lab Connection Preflight verification against the 7 mandatory statuses:
NOT_CONFIGURED, UNREACHABLE, AUTH_FAILED, IDENTITY_UNVERIFIED,
CONNECTED_READ_ONLY, PARTIAL_CAPABILITY, READY_FOR_DIAGNOSTICS.
Verifies read-only policy, credential non-leakage, and API endpoint integration.
"""

from __future__ import annotations

import socket
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from core.network_intelligence.models import PreflightStatus
from core.network_intelligence.preflight import LabPreflightChecker


@pytest.fixture
def checker():
    return LabPreflightChecker()


@pytest.fixture
def test_client():
    return TestClient(app)


def test_preflight_not_configured_when_target_empty(checker):
    """Empty or whitespace target must return NOT_CONFIGURED immediately."""
    res = checker.run_preflight("   ")
    assert res.status == PreflightStatus.NOT_CONFIGURED.value
    assert res.reachability is False
    assert res.authenticated is False
    assert "tidak ditentukan" in res.message.lower()


def test_preflight_not_configured_when_not_in_inventory_and_no_creds(checker):
    """Target unknown to inventory without supplied credentials returns NOT_CONFIGURED."""
    with patch.object(checker.cm, "_resolve_target", return_value={"success": False, "error": "Not in inventory"}):
        res = checker.run_preflight("Router-Unknown-99")
        assert res.status == PreflightStatus.NOT_CONFIGURED.value
        assert res.reachability is False
        assert "tidak ditemukan di inventory" in res.message.lower()


def test_preflight_unreachable_when_tcp_fails(checker):
    """TCP socket connection refusal or failure must return UNREACHABLE."""
    with patch.object(checker, "_probe_tcp_and_banner", return_value=(False, "Connection refused")):
        res = checker.run_preflight("192.168.88.99", username="admin", password="password123")
        assert res.status == PreflightStatus.UNREACHABLE.value
        assert res.reachability is False
        assert res.authenticated is False
        assert "password123" not in str(res.to_dict())  # Zero credential leakage


def test_preflight_unreachable_when_banner_times_out(checker):
    """TCP connect succeeds but SSH banner times out (e.g. non-SSH port) must return UNREACHABLE."""
    with patch.object(checker, "_probe_tcp_and_banner", return_value=(False, "Handshake soket atau pembacaan banner SSH mengalami timeout")):
        res = checker.run_preflight("192.168.88.1", username="admin", password="password123")
        assert res.status == PreflightStatus.UNREACHABLE.value
        assert res.reachability is False
        assert "timeout" in res.message.lower()


def test_preflight_auth_failed(checker):
    """When SSH transport connection reaches auth but router rejects credentials."""
    with patch.object(checker, "_probe_tcp_and_banner", return_value=(True, "SSH-2.0-RouterOS")):
        with patch.object(checker.cm, "test_target_credentials", return_value={
            "authenticated": False,
            "error_type": "auth_failure",
            "message": "Wrong username or password",
        }):
            res = checker.run_preflight("192.168.88.1", username="wronguser", password="secretpassword")
            assert res.status == PreflightStatus.AUTH_FAILED.value
            assert res.reachability is True
            assert res.authenticated is False
            assert "secretpassword" not in str(res.to_dict())
            assert "ditolak" in res.message.lower()


def test_preflight_identity_unverified(checker):
    """When SSH authentication passes but /system identity print returns empty or fails."""
    with patch.object(checker, "_probe_tcp_and_banner", return_value=(True, "SSH-2.0-RouterOS")):
        with patch.object(checker.cm, "test_target_credentials", return_value={"authenticated": True, "identity": None}):
            with patch.object(checker.cm, "execute_command", return_value={"success": True, "output": ""}):
                res = checker.run_preflight("192.168.88.1", username="admin", password="adminpassword")
                assert res.status == PreflightStatus.IDENTITY_UNVERIFIED.value
                assert res.reachability is True
                assert res.authenticated is True
                assert res.identity is None


def test_preflight_connected_read_only_when_critical_cmd_fails(checker):
    """When connected and identity verified, but critical commands (e.g. routes/interfaces) fail permission."""
    with patch.object(checker, "_probe_tcp_and_banner", return_value=(True, "SSH-2.0-RouterOS")):
        with patch.object(checker.cm, "test_target_credentials", return_value={"authenticated": True, "identity": "RB4011"}):
            def mock_exec(command, **kwargs):
                if "/system identity" in command:
                    return {"success": True, "output": "  name: RB4011", "prompt_matched": True}
                if "/system resource" in command:
                    return {"success": True, "output": "  version: 7.15", "prompt_matched": True}
                if "/ip route" in command:
                    return {"success": True, "output": "failure: not enough permissions (9)", "prompt_matched": True}
                return {"success": True, "output": "active", "prompt_matched": True}

            with patch.object(checker.cm, "execute_command", side_effect=mock_exec):
                res = checker.run_preflight("192.168.88.1", username="audit_user", password="auditpassword")
                assert res.status == PreflightStatus.CONNECTED_READ_ONLY.value
                assert res.identity == "RB4011"
                assert res.ros_major_version == 7
                assert len(res.rejected_commands) > 0


def test_preflight_partial_capability_when_optional_fails(checker):
    """When critical commands pass, but optional command (firewall count) fails."""
    with patch.object(checker, "_probe_tcp_and_banner", return_value=(True, "SSH-2.0-RouterOS")):
        with patch.object(checker.cm, "test_target_credentials", return_value={"authenticated": True, "identity": "Core-Router"}):
            def mock_exec(command, **kwargs):
                if "/system identity" in command:
                    return {"success": True, "output": "  name: Core-Router", "prompt_matched": True}
                if "/system resource" in command:
                    return {"success": True, "output": "  version: 7.14", "prompt_matched": True}
                if "/ip firewall filter print count-only" in command:
                    return {"success": True, "output": "failure: not enough permissions", "prompt_matched": True}
                if "/ip route" in command:
                    return {"success": True, "output": "Columns: DST-ADDRESS, GATEWAY\n0.0.0.0/0  192.168.1.1", "prompt_matched": True}
                if "/ip address" in command:
                    return {"success": True, "output": "# ADDRESS NETWORK INTERFACE\n0 192.168.1.2/24 192.168.1.0 ether1", "prompt_matched": True}
                if "/interface" in command:
                    return {"success": True, "output": "# NAME TYPE ACTUAL-MTU\n0 ether1 ether 1500", "prompt_matched": True}
                return {"success": True, "output": "0", "prompt_matched": True}

            with patch.object(checker.cm, "execute_command", side_effect=mock_exec):
                res = checker.run_preflight("192.168.88.1", username="operator", password="password")
                assert res.status == PreflightStatus.PARTIAL_CAPABILITY.value
                assert res.identity == "Core-Router"
                assert "parsial" in res.message.lower()


def test_preflight_ready_for_diagnostics(checker):
    """When all critical and optional commands execute successfully and normalizers parse tables."""
    with patch.object(checker, "_probe_tcp_and_banner", return_value=(True, "SSH-2.0-RouterOS")):
        with patch.object(checker.cm, "test_target_credentials", return_value={"authenticated": True, "identity": "Gateway-Lab"}):
            def mock_exec(command, **kwargs):
                if "/system identity" in command:
                    return {"success": True, "output": "  name: Gateway-Lab", "prompt_matched": True}
                if "/system resource" in command:
                    return {"success": True, "output": "  version: 7.15.2 (stable)", "prompt_matched": True}
                if "/interface" in command:
                    return {"success": True, "output": "# NAME TYPE ACTUAL-MTU\n0 R ether1 ether 1500", "prompt_matched": True}
                if "/ip address" in command:
                    return {"success": True, "output": "# ADDRESS NETWORK INTERFACE\n0 192.168.88.1/24 192.168.88.0 ether1", "prompt_matched": True}
                if "/ip route" in command:
                    return {"success": True, "output": "Columns: DST-ADDRESS, GATEWAY\n0.0.0.0/0  192.168.88.254", "prompt_matched": True}
                if "/ip firewall filter" in command:
                    return {"success": True, "output": "12", "prompt_matched": True}
                if "/ip firewall nat" in command:
                    return {"success": True, "output": "4", "prompt_matched": True}
                return {"success": True, "output": "", "prompt_matched": True}

            with patch.object(checker.cm, "execute_command", side_effect=mock_exec):
                res = checker.run_preflight("192.168.88.1", username="admin", password="password")
                assert res.status == PreflightStatus.READY_FOR_DIAGNOSTICS.value
                assert res.reachability is True
                assert res.authenticated is True
                assert res.identity == "Gateway-Lab"
                assert res.ros_major_version == 7
                assert "read" in res.effective_permissions
                assert len(res.parser_completeness["parsed_tables"]) >= 4
                assert "siap untuk investigasi" in res.message.lower()


def test_preflight_api_endpoint(test_client):
    """Tests POST /api/intelligence/preflight endpoint contract and status structure."""
    with patch.object(LabPreflightChecker, "run_preflight") as mock_run:
        from core.network_intelligence.models import PreflightResult
        mock_run.return_value = PreflightResult(
            target="192.168.88.1",
            status=PreflightStatus.READY_FOR_DIAGNOSTICS.value,
            reachability=True,
            authenticated=True,
            identity="Lab-Edge",
            routeros_version="7.15",
            ros_major_version=7,
            effective_permissions=["read"],
            correlation_id="preflight_test_123",
            duration_ms=45.2,
            message="Siap investigasi.",
        )

        resp = test_client.post(
            "/api/intelligence/preflight",
            headers={"Authorization": "Bearer topology-admin-token"},
            json={"target": "192.168.88.1", "port": 22, "timeout": 4.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["preflight"]["status"] == "READY_FOR_DIAGNOSTICS"
        assert data["preflight"]["identity"] == "Lab-Edge"
        assert data["preflight"]["correlation_id"] == "preflight_test_123"
