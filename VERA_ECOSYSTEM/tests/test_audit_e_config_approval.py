import pytest
from unittest.mock import MagicMock, patch
from agents.akane.config_engine import SafeConfigEngine, generate_rollback_for_command
from mcp_servers.network.server import create_network_mcp_server
from core.mcp.client import MCPClient
from core.orchestrator import DANGEROUS_TOOLS

def test_audit_e_unapproved_blocked():
    engine = SafeConfigEngine()
    
    # 1. Direct engine call without approval
    res = engine.apply_change(
        device_name="core-gw",
        commands=["/ip address add address=192.168.10.1/24 interface=ether2"],
        approved=False
    )
    assert res["success"] is False
    assert res["requires_approval"] is True
    assert res["status"] == "APPROVAL_REQUIRED"

    # 2. MCP tool call without approval returns requires_approval and rollback preview
    server = create_network_mcp_server()
    client = MCPClient(server, server_name="audit-e-test")
    client.initialize()

    mcp_res = client.call_tool("mikrotik_apply_config", {
        "device_name": "core-gw",
        "commands": ["/ip address add address=192.168.10.1/24 interface=ether2"],
        "approved": False,
    })
    assert mcp_res["success"] is False
    assert mcp_res["requires_approval"] is True
    assert mcp_res["confirmation_required"] is True
    assert len(mcp_res["rollback_plan"]) > 0

def test_audit_e_dangerous_tools_governance():
    # Verify orchestrator marks dangerous tools
    assert "apply_config" in DANGEROUS_TOOLS
    assert "disconnect_device" in DANGEROUS_TOOLS

def test_audit_e_dangerous_command_rejection():
    engine = SafeConfigEngine()
    dangerous_commands = [
        "/system reset-configuration keep-users=no",
        "/system reboot",
        "/user remove admin",
        "/file remove cert.key"
    ]
    for cmd in dangerous_commands:
        plan = engine.plan_change("core-gw", [cmd])
        assert plan["success"] is False
        assert plan["safety_status"] == "REJECTED_DANGEROUS"
        assert any("dangerous operation detected" in issue for issue in plan["flagged_issues"])

def test_audit_e_semantic_verification_detects_silent_failure():
    engine = SafeConfigEngine()
    
    # Mock connection manager returning successful command execution, but empty table (silent failure)
    mock_mgr = MagicMock()
    mock_mgr.get_ip_addresses.return_value = {
        "success": True,
        "raw_output": "Flags: X - disabled, I - invalid, D - dynamic\n #   ADDRESS            NETWORK         INTERFACE\n 0   10.0.0.1/24        10.0.0.0        ether1\n"
    }
    mock_mgr.get_identity.return_value = {"success": True, "raw_output": "name: core-gw"}

    with patch("agents.akane.config_engine.get_connection_manager", return_value=mock_mgr):
        # We applied 192.168.50.1/24, but running output only has 10.0.0.1/24
        verify_res = engine.verify_change("core-gw", ["/ip address add address=192.168.50.1/24 interface=ether2"])
        assert verify_res["success"] is False
        assert verify_res["status"] == "VERIFICATION_FAILED"
        ip_check = next(c for c in verify_res["checks"] if c["target"] == "ip_addresses")
        assert ip_check["verified"] is False
        assert ip_check["semantic_presence"] is False
        assert "silent failure" in ip_check["error"]

def test_audit_e_rollback_disclaimer_and_inverse_commands():
    engine = SafeConfigEngine()
    
    mock_mgr = MagicMock()
    mock_mgr.execute_for_device.return_value = {"success": True, "output": ""}

    with patch("agents.akane.config_engine.get_connection_manager", return_value=mock_mgr):
        rec_res = engine.recover("core-gw", ['/ip address remove [find address="192.168.10.1/24"]'])
        assert rec_res["success"] is True
        assert rec_res["recovery_mechanism"] == "synthesized_inverse_commands"
        assert rec_res["atomic_hardware_transaction"] is False
        assert "disclaimer" in rec_res
