"""
tests/test_phase5_read_only_enforcement.py — Read-Only Security Enforcement & Isolation Tests (Phase 5).

Verifies:
1. Strict allowlist validation of diagnostic commands.
2. Hard rejection of mutating verbs (add, set, remove, enable, disable, reset, reboot).
3. Hard rejection of command injection attempts (semicolons, newlines, pipes, backticks).
4. Redaction of sensitive values (passwords, pre-shared keys, tokens, SNMP communities).
5. Spy/Mock proof that NO apply or mutating executors are called during:
   - Incident investigation
   - Diagnostic playbook stepping
   - Configuration planning
   - Static validation
   - Static forwarding simulation
   - REST API intelligence endpoints
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from api.main import app
from core.network_intelligence.security import (
    MAX_COMMAND_LENGTH,
    execute_safe_readonly_command,
    redact_sensitive_values,
    validate_readonly_command,
)
from core.network_intelligence.investigator import NetworkInvestigator
from core.network_intelligence.playbooks import PlaybookEngine
from core.network_intelligence.planner import ConfigurationPlanner
from core.network_intelligence.validator import StaticValidator
from core.network_intelligence.simulator import StaticSimulator
from core.network_intelligence.models import IncidentType
from agents.akane.config_engine import SafeConfigEngine


# ---------------------------------------------------------------------------
# 1. Allowlist Validation of Diagnostic Commands
# ---------------------------------------------------------------------------

def test_allowlist_permits_safe_diagnostic_commands():
    safe_commands = [
        "/system identity print",
        "/system resource print",
        "/interface print detail",
        "/interface bridge print detail",
        "/interface bridge port print detail",
        "/interface bridge vlan print detail",
        "/ip address print detail",
        "/ip route print detail",
        "/ip route print detail where dst-address=0.0.0.0/0",
        "/ip route rule print detail",
        "/ip firewall filter print detail",
        "/ip firewall filter print detail where chain=forward",
        "/ip firewall nat print detail",
        "/ip firewall mangle print detail",
        "/ip arp print detail",
        "/routing rule print detail",
        "/routing ospf neighbor print",
        "/routing ospf instance print",
        "/routing bgp connection print detail",
        "/ping 8.8.8.8 count=3",
        "/tool traceroute 1.1.1.1 count=2",
    ]

    for cmd in safe_commands:
        is_valid, reason = validate_readonly_command(cmd)
        assert is_valid, f"Command '{cmd}' should be allowed, but failed: {reason}"


# ---------------------------------------------------------------------------
# 2. Rejection of Mutating Commands
# ---------------------------------------------------------------------------

def test_allowlist_rejects_mutating_commands():
    dangerous_commands = [
        "/ip address add address=192.168.1.1/24 interface=ether1",
        "/ip route add dst-address=0.0.0.0/0 gateway=192.168.1.254",
        "/ip route remove [find dst-address=0.0.0.0/0]",
        "/interface disable ether1",
        "/interface enable ether2",
        "/interface set ether1 disabled=yes",
        "/system reboot",
        "/system reset-configuration no-defaults=yes",
        "/ip firewall filter add chain=forward action=drop",
        "/ip firewall nat remove 0",
        "/file remove cert.key",
        "/user add name=attacker password=secret group=full",
        "/system shutdown",
    ]

    for cmd in dangerous_commands:
        is_valid, reason = validate_readonly_command(cmd)
        assert not is_valid, f"Mutating command '{cmd}' MUST be rejected, but passed!"
        assert "tidak diizinkan" in reason or "terlarang" in reason


# ---------------------------------------------------------------------------
# 3. Injection Prevention
# ---------------------------------------------------------------------------

def test_allowlist_rejects_command_injection():
    injection_attacks = [
        "/ip route print detail; /system reboot",
        "/interface print\n/system reset-configuration",
        "/ip address print | grep 192",
        "/system identity print `reboot`",
        "/system identity print $(whoami)",
        "/ip address print && /system shutdown",
    ]

    for cmd in injection_attacks:
        is_valid, reason = validate_readonly_command(cmd)
        assert not is_valid, f"Injection attack '{cmd}' MUST be rejected, but passed!"
        assert "terlarang" in reason or "tidak diizinkan" in reason


def test_allowlist_rejects_oversized_commands():
    huge_cmd = "/system identity print " + "A" * (MAX_COMMAND_LENGTH + 10)
    is_valid, reason = validate_readonly_command(huge_cmd)
    assert not is_valid
    assert "panjang maksimum" in reason


# ---------------------------------------------------------------------------
# 4. Sensitive Value Redaction
# ---------------------------------------------------------------------------

def test_redact_sensitive_values_masks_secrets():
    raw_cli_output = (
        'name="wlan1" ssid="Office-WiFi" wpa2-pre-shared-key="SuperSecretP@ss123!" '
        'user="admin" password="VeryConfidentialPassword" '
        'community="private-snmp-comm" token="bearer_abc123xyz"'
    )

    redacted = redact_sensitive_values(raw_cli_output)

    assert "SuperSecretP@ss123!" not in redacted
    assert "VeryConfidentialPassword" not in redacted
    assert "private-snmp-comm" not in redacted
    assert "bearer_abc123xyz" not in redacted
    assert "******" in redacted


# ---------------------------------------------------------------------------
# 5. Spy Proof: Pipeline & API Never Call Mutating / Apply Executors
# ---------------------------------------------------------------------------

def test_investigation_pipeline_never_invokes_apply_engine():
    investigator = NetworkInvestigator()

    with patch.object(investigator.collector, "resolve_target_device", return_value=("R1-Core", 7, "R1 Core Router")):
        with patch.object(investigator.collector.cm, "execute_for_device") as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": "# feb/28/2026 by RouterOS 7.15\n/ip route print\nFlags: D - DYNAMIC; A - ACTIVE; c - CONNECT\n#   DST-ADDRESS    GATEWAY  DISTANCE\n0 DAc 192.168.1.0/24 ether1   0",
            }

            with patch.object(SafeConfigEngine, "apply_change", autospec=True) as mock_apply:
                record = investigator.create_and_run_investigation(
                    device_identity="R1-Core",
                    incident_type=IncidentType.DEFAULT_ROUTE_FAILS,
                    symptoms=["No internet"],
                )

                # SafeConfigEngine.apply_change MUST NEVER be called
                assert mock_apply.call_count == 0
                assert record.incident_id.startswith("inc_")

                # Verify all executed commands were strictly read-only
                for call_args in mock_exec.call_args_list:
                    cmd = call_args[0][1]
                    is_ro, _ = validate_readonly_command(cmd)
                    assert is_ro, f"Executed command was not read-only: {cmd}"


def test_playbook_engine_never_invokes_apply_engine():
    engine = PlaybookEngine()

    with patch.object(engine.collector, "resolve_target_device", return_value=("R1-Core", 7, "R1 Core Router")):
        with patch.object(engine.collector.cm, "execute_for_device") as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": "0 ether1 192.168.1.1/24",
            }

            with patch.object(SafeConfigEngine, "apply_change", autospec=True) as mock_apply:
                run = engine.start_playbook_run("PB-LAN-INTERNET", "inc_test", "R1-Core")
                advanced_run = engine.advance_playbook(run.run_id, action="step")

                # SafeConfigEngine.apply_change MUST NEVER be called
                assert mock_apply.call_count == 0
                assert advanced_run.status in ("RUNNING", "COMPLETED")


def test_planning_and_simulation_never_invokes_apply_engine():
    planner = ConfigurationPlanner()
    validator = StaticValidator()
    simulator = StaticSimulator()

    with patch.object(SafeConfigEngine, "apply_change", autospec=True) as mock_apply:
        plan = planner.generate_plan(
            target_device="R1-Core",
            change_type="add_ip_address",
            parameters={
                "interface": "ether2",
                "ip_address": "10.0.0.1",
                "netmask": "24",
            },
        )
        validated_plan = validator.validate_plan(plan)
        simulator.simulate_plan(validated_plan)

        # Neither planning nor static simulation may trigger configuration execution
        assert mock_apply.call_count == 0
        assert validated_plan.plan_status in ("READY_FOR_REVIEW", "VALID_WITH_WARNINGS", "DRAFT")


def test_rest_api_intelligence_endpoints_never_invoke_apply_engine():
    client = TestClient(app)

    with patch.object(SafeConfigEngine, "apply_change", autospec=True) as mock_apply:
        # 1. POST /api/intelligence/incidents
        with patch("core.network_intelligence.evidence.EvidenceCollector.resolve_target_device", return_value=("R1-Core", 7, "R1")):
            with patch("agents.akane.connection_manager.ConnectionManager.execute_for_device", return_value={"success": True, "output": ""}):
                resp_inc = client.post(
                    "/api/intelligence/incidents",
                    json={
                        "device_identity": "R1-Core",
                        "incident_type": "LAN_NO_INTERNET",
                        "symptoms": ["Cannot ping gateway"],
                    },
                )
                assert resp_inc.status_code == 200

        # 2. POST /api/intelligence/plans
        resp_plan = client.post(
            "/api/intelligence/plans",
            json={
                "target_device": "R1-Core",
                "change_type": "add_default_route",
                "parameters": {"gateway": "192.168.1.1", "distance": 1},
            },
        )
        assert resp_plan.status_code == 200

        # Verify absolutely zero apply executions occurred across the API
        assert mock_apply.call_count == 0
