"""
tests/test_mcp_integration.py — Integration and unit tests for Network MCP Server and MCP Client.
"""

import unittest
from unittest.mock import patch, MagicMock

from mcp_servers.network.server import create_network_mcp_server
from mcp_servers.network.security import validate_network_target, mask_sensitive_data
from core.mcp.client import MCPClient, get_network_mcp_client
from core.orchestrator import AGENT_TOOL_MAP, DANGEROUS_TOOLS


class TestNetworkMCPSecurity(unittest.TestCase):
    """Tests target validation and secret masking."""

    def test_valid_targets_pass(self):
        self.assertEqual(validate_network_target("127.0.0.1"), "127.0.0.1")
        self.assertEqual(validate_network_target("google.com"), "google.com")
        self.assertEqual(validate_network_target("router-core-01"), "router-core-01")

    def test_flag_injection_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_network_target("-v")
        self.assertIn("cannot start with options", str(ctx.exception))

        with self.assertRaises(ValueError):
            validate_network_target("--count=10")

    def test_command_separator_rejected(self):
        with self.assertRaises(ValueError):
            validate_network_target("127.0.0.1; echo evil")

        with self.assertRaises(ValueError):
            validate_network_target("8.8.8.8 | cat /etc/passwd")

        with self.assertRaises(ValueError):
            validate_network_target("1.1.1.1`whoami`")

    def test_sensitive_data_masked(self):
        data = {
            "device": "R1",
            "password": "supersecretpassword",
            "ssh_key": "-----BEGIN PRIVATE KEY-----",
            "community": "public",
            "nested": {
                "token": "secret_token_123",
                "normal": "normal_value",
            },
        }
        masked = mask_sensitive_data(data)
        self.assertEqual(masked["password"], "***")
        self.assertEqual(masked["ssh_key"], "***")
        self.assertEqual(masked["community"], "***")
        self.assertEqual(masked["nested"]["token"], "***")
        self.assertEqual(masked["nested"]["normal"], "normal_value")
        self.assertEqual(masked["device"], "R1")


class TestNetworkMCPServerTools(unittest.TestCase):
    """Tests tool discovery and behavior on the Network MCP Server."""

    def setUp(self):
        self.server = create_network_mcp_server()
        self.client = MCPClient(self.server, server_name="test-network")
        self.client.initialize()

    def test_all_expected_tools_registered(self):
        tools = self.client.tools
        self.assertGreaterEqual(len(tools), 23)
        expected = [
            "network_ping", "network_nslookup", "network_traceroute", "network_list_devices",
            "mikrotik_get_identity", "mikrotik_get_resources", "mikrotik_get_interfaces",
            "mikrotik_get_ip_addresses", "mikrotik_get_routes", "mikrotik_get_firewall",
            "mikrotik_validate_script", "mikrotik_plan_config_change", "mikrotik_apply_config",
            "device_connect", "device_disconnect",
        ]
        for name in expected:
            self.assertIn(name, tools, f"Missing tool: {name}")

    def test_script_validation_safe(self):
        res = self.client.call_tool("mikrotik_validate_script", {
            "script_text": "/ip address add address=192.168.88.1/24 interface=ether1\n/ip route add dst-address=0.0.0.0/0 gateway=192.168.88.254",
        })
        self.assertTrue(res.get("valid"))
        self.assertEqual(res.get("command_count"), 2)
        self.assertEqual(res.get("safety"), "safe")

    def test_script_validation_flags_destructive_commands(self):
        res = self.client.call_tool("mikrotik_validate_script", {
            "script_text": "/system reset-configuration no-defaults=yes",
        })
        self.assertFalse(res.get("valid"))
        self.assertEqual(res.get("safety"), "flagged")
        self.assertTrue(any("destructive" in issue.lower() for issue in res.get("issues", [])))

    def test_script_validation_flags_unbalanced_quotes(self):
        res = self.client.call_tool("mikrotik_validate_script", {
            "script_text": '/ip firewall filter add comment="broken quote chain=forward',
        })
        self.assertFalse(res.get("valid"))
        self.assertTrue(any("quotes" in issue.lower() for issue in res.get("issues", [])))

    def test_apply_config_requires_approval(self):
        res = self.client.call_tool("mikrotik_apply_config", {
            "device_name": "R1",
            "commands": ["/ip dns set servers=8.8.8.8"],
            "approved": False,
        })
        self.assertFalse(res.get("success"))
        self.assertTrue(res.get("requires_approval"))
        self.assertTrue(res.get("confirmation_required"))
        self.assertIn("requires explicit user approval", res.get("message", ""))

    def test_execute_command_blocks_dangerous_wipes(self):
        res = self.client.call_tool("mikrotik_execute_command", {
            "command": "/system reset-configuration no-defaults=yes",
            "device_name": "R1",
        })
        self.assertFalse(res.get("success"))
        self.assertTrue(res.get("flagged"))
        self.assertIn("dangerous operation", res.get("error", "").lower())

    @patch("mcp_servers.network.server.get_connection_manager")
    def test_execute_command_runs_arbitrary_cli(self, mock_get_mgr):
        mock_mgr = MagicMock()
        mock_mgr.execute_command.return_value = {
            "success": True,
            "output": "Flags: X - disabled, I - invalid, D - dynamic\\n 0   ether1   ether   1500",
            "command": "/interface print",
        }
        mock_get_mgr.return_value = mock_mgr

        res = self.client.call_tool("mikrotik_execute_command", {
            "command": "/interface print",
            "host": "192.168.88.1",
            "username": "admin",
            "password": "123",
        })
        self.assertTrue(res.get("success"))
        self.assertIn("ether1", res.get("output", ""))
        mock_mgr.execute_command.assert_called_once()

    @patch("mcp_servers.network.server.get_connection_manager")
    def test_generate_report_collects_sections(self, mock_get_mgr):
        mock_mgr = MagicMock()
        mock_mgr.execute_command.return_value = {
            "success": True,
            "output": "cpu-load: 5%\nfree-memory: 120MiB",
        }
        mock_get_mgr.return_value = mock_mgr

        res = self.client.call_tool("mikrotik_generate_report", {
            "device_name": "R1",
        })
        self.assertTrue(res.get("success"))
        self.assertIn("overall_status", res)
        self.assertIn("resources", res.get("data", {}))
        self.assertEqual(res["overall_status"], "HEALTHY")


class TestOrchestratorMCPIntegration(unittest.TestCase):
    """Tests integration between Orchestrator, AKANE registry, and MCP."""

    def test_mcp_tools_present_in_orchestrator(self):
        self.assertIn("ping", AGENT_TOOL_MAP)
        self.assertIn("validate_script", AGENT_TOOL_MAP)
        self.assertIn("plan_config_change", AGENT_TOOL_MAP)
        self.assertIn("apply_config", AGENT_TOOL_MAP)
        self.assertIn("execute_router_command", AGENT_TOOL_MAP)
        self.assertIn("generate_router_report", AGENT_TOOL_MAP)

    def test_dangerous_tools_contain_apply_config(self):
        self.assertIn("apply_config", DANGEROUS_TOOLS)
        self.assertIn("disconnect_device", DANGEROUS_TOOLS)

    def test_ping_delegation_via_orchestrator(self):
        ping_fn = AGENT_TOOL_MAP["ping"]
        result = ping_fn(target="127.0.0.1", count=1)
        self.assertTrue(result.get("success"))
        self.assertEqual(result.get("tool"), "ping")


if __name__ == "__main__":
    unittest.main()
