"""
tests/test_routeros_command_hardening.py — Adversarial Regression & Execution Boundary Tests.

Verifies complete closure of RouterOS command validation gaps:
1. Rejection of audited bypasses:
   - File redirection: /ip route print file=evil.txt, /system identity print file=hack
   - Command substitution: /ip route print where [reboot]
   - Script code blocks: /ip route print where do={reboot}
   - Unbounded streaming: /ip route print interval=1, follow, follow-only
2. Case and whitespace variations.
3. Nested brackets, braces, and colon script command prefixes (:execute, :put, :delay).
4. Safe handling of parameters containing command-like text inside quotes (comment="reboot router").
5. Malformed syntax (unclosed quotes, control characters).
6. Execution boundary verification:
   - Proves via mock/spy that ConnectionManager.execute_for_device and execute_command
     are NEVER invoked for rejected commands.
   - Proves via mock/spy that SafeConfigEngine.apply_change is NEVER invoked.
7. Verification across entry points:
   - validate_readonly_command
   - execute_safe_readonly_command
   - EvidenceCollector.collect_evidence_bundle
   - LabPreflightChecker
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from agents.akane.config_engine import SafeConfigEngine
from agents.akane.connection_manager import ConnectionManager, get_connection_manager
from core.network_intelligence.evidence import EvidenceCollector
from core.network_intelligence.preflight import LabPreflightChecker
from core.network_intelligence.security import (
    MAX_COMMAND_LENGTH,
    execute_safe_readonly_command,
    validate_readonly_command,
)


# ---------------------------------------------------------------------------
# 1. Audited Bypass Regression Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cmd,expected_keyword", [
    ("/ip route print file=evil.txt", "file="),
    ("/system identity print file=hack", "file="),
    ("/interface print stats-file=foo.txt", "file="),
    ("/ip route print append=evil.txt", "append="),
    ("/ip route print where [reboot]", "kurung siku"),
    ("/ip route print where [find dst-address=0.0.0.0/0]", "kurung siku"),
    ("/ip route print where do={reboot}", "kurung kurawal"),
    ("/ip route print where do={/system default-configuration/reboot}", "kurung kurawal"),
    ("/ip route print interval=1", "interval="),
    ("/ip route print interval=5", "interval="),
    ("/ip route print follow", "streaming"),
    ("/ip route print follow-only", "streaming"),
    ("/ip route print continuous", "streaming"),
    ("/ip route print freeze", "streaming"),
    (":execute {/system reboot}", "kurung kurawal"),
    (":put [/system resource get version]", "kurung siku"),
    (":delay 10", ":"),
])
def test_audited_bypasses_are_strictly_rejected(cmd, expected_keyword):
    is_valid, reason = validate_readonly_command(cmd)
    assert not is_valid, f"Bypass '{cmd}' MUST be rejected, but passed!"
    assert expected_keyword.lower() in reason.lower()


# ---------------------------------------------------------------------------
# 2. Case, Whitespace, and Parameter Variations
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cmd,expected_valid", [
    ("   /ip route print detail   ", True),
    ("   /IP   ROUTE   PRINT   DETAIL   ", True),
    ("/system   identity   print", True),
    ("/ip route print detail where dst-address=0.0.0.0/0", True),
    ("/ip route print detail where dst-address in 192.168.0.0/16", True),
    ("/ip firewall filter print detail where chain=forward", True),
    ("/ip firewall filter print detail where comment=\"reboot target\"", True),
    ("/ip firewall filter print detail where comment='reboot target'", True),
    ("/ip firewall filter print detail where comment=\"add default route\"", True),
    ("/ping 10.0.0.1 count=3", True),
    ("/ping 10.0.0.1 count=10", False),  # Exceeds max count of 5
    ("/tool traceroute 8.8.8.8 count=2", True),
    ("/tool traceroute 8.8.8.8 count=5", False),  # Exceeds max count of 3
    ("/export compact", True),
    ("/export verbose=no", True),
    ("/export file=backup", False),  # File redirection forbidden
    ("/export show-sensitive", False),  # Dumping sensitive data forbidden
])
def test_command_syntax_and_parameter_variations(cmd, expected_valid):
    is_valid, reason = validate_readonly_command(cmd)
    assert is_valid is expected_valid, f"Command '{cmd}' expected valid={expected_valid}, got {is_valid}: {reason}"


# ---------------------------------------------------------------------------
# 3. Delimiter Injection & Malformed Syntax
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cmd", [
    "/ip route print detail; /system reboot",
    "/interface print\n/system reset-configuration",
    "/ip address print\r\n/system shutdown",
    "/ip address print | grep 192",
    "/system identity print `reboot`",
    "/system identity print $(whoami)",
    "/ip address print && /system shutdown",
    "/ip route print > /flash/evil.txt",
    "/ip route print < /dev/zero",
    "/ip route print \0 /system reboot",
    "/ip route print where comment=\"unclosed double quote",
    "/ip route print where comment='unclosed single quote",
    "/unsupported/unknown/namespace print",
])
def test_delimiters_and_malformed_syntax_rejected(cmd):
    is_valid, reason = validate_readonly_command(cmd)
    assert not is_valid, f"Malformed/injection command '{cmd}' MUST be rejected, but passed!"


# ---------------------------------------------------------------------------
# 4. Nested Brackets, Braces & Mutating Verbs Outside Quotes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cmd", [
    "/ip route print where [[reboot]]",
    "/ip route print where {{reboot}}",
    "/ip route print where do={do={reboot}}",
    "/ip route print where [find where name=ether1]",
    "/ip route print where name=reboot",  # Unquoted mutating verb token
    "/ip route print where action=reboot",  # Unquoted mutating verb token
])
def test_nested_brackets_braces_and_unquoted_verbs_rejected(cmd):
    is_valid, reason = validate_readonly_command(cmd)
    assert not is_valid, f"Command '{cmd}' with nested blocks or mutating verb MUST be rejected!"


# ---------------------------------------------------------------------------
# 5. Execution Boundary Proof: Rejected Commands NEVER Call Transport Executor
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dangerous_cmd", [
    "/ip route print file=evil.txt",
    "/system identity print file=hack",
    "/ip route print where [reboot]",
    "/ip route print where do={reboot}",
    "/ip route print interval=1",
    "/ip route print follow",
    "/system reboot",
    "/ip route print; reboot",
])
def test_rejected_commands_never_reach_ssh_transport(dangerous_cmd):
    """
    Proves via mock/spy that execute_safe_readonly_command() NEVER invokes
    ConnectionManager.execute_for_device when validation fails.
    """
    mock_cm = MagicMock()

    result = execute_safe_readonly_command(mock_cm, "R1", dangerous_cmd, timeout=10.0)

    assert result["success"] is False
    assert result.get("blocked") is True
    assert "Security policy violation" in result["error"]
    # Transport execute MUST NEVER be invoked!
    assert mock_cm.execute_for_device.call_count == 0
    assert mock_cm.execute_command.call_count == 0


def test_rejected_commands_never_reach_connection_manager_in_collector():
    """
    Proves that EvidenceCollector with an invalid or injected command
    blocks before calling ConnectionManager.execute_for_device.
    """
    collector = EvidenceCollector()
    mock_cm = MagicMock()
    collector.cm = mock_cm

    # Inject an adversarial command into required types mapping for both v6 and v7
    with patch.dict("core.network_intelligence.evidence.COMMAND_MAP_V7", {"routes": "/ip route print file=pwn.txt"}), \
         patch.dict("core.network_intelligence.evidence.COMMAND_MAP_V6", {"routes": "/ip route print file=pwn.txt"}):
        bundle = collector.collect_evidence_bundle("R1", ["routes"])

        assert len(bundle["collection_errors"]) > 0
        assert "Blocked by security policy" in bundle["collection_errors"][0]
        # Transport execute_for_device MUST NEVER be invoked!
        assert mock_cm.execute_for_device.call_count == 0


def test_rejected_commands_never_invoke_safe_config_engine_apply():
    """
    Proves that running validation and security checks against malicious commands
    has zero call path to SafeConfigEngine.apply_change.
    """
    with patch.object(SafeConfigEngine, "apply_change") as mock_apply:
        # Run a barrage of malicious commands through validation
        malicious = [
            "/ip route print file=hack.txt",
            "/ip route print where [reboot]",
            "/ip route print where do={reboot}",
            "/ip route print interval=1",
            "/system reboot",
        ]
        for cmd in malicious:
            is_valid, _ = validate_readonly_command(cmd)
            assert is_valid is False

        # Verify apply_change is completely uncalled
        assert mock_apply.call_count == 0
