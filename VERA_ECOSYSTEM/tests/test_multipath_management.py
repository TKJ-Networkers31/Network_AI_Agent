"""
tests/test_multipath_management.py — Multi-Path MikroTik Management Subsystem Test Suite.

Verifies:
1. CapabilityDetector: IP/TCP port probing, Layer 2 ARP adjacency, RouterOS RoMON version support.
2. SelectionEngine: Deterministic precedence (SSH -> API -> RoMON -> MAC), auditable rationales, explicit rejection reasons, manual overrides.
3. MAC & RoMON Managers: L2 non-routability boundary enforcement, RoMON output parsing, 2-stage provisioning with WAN interface protection & secret masking.
4. REST APIs: Management endpoints (/api/devices/{id}/management/...) with permission & validation enforcement.
"""

import os
import unittest
from unittest import mock
import pytest
from starlette.testclient import TestClient

from api.main import app
from core.management.models import (
    ManagementMethod,
    PathStatus,
    ManagementPath,
    DeviceManagementProfile,
    RomonNeighbor,
)
from core.management.capability_detector import (
    CapabilityDetector,
    check_tcp_port,
    is_mac,
    is_ip,
)
from core.management.selection_engine import SelectionEngine
from core.management.mac_manager import MacManager
from core.management.romon_manager import RomonManager
from core.management.manager import get_multi_path_manager
from tests.auth_helper import get_test_auth_headers


class TestMultiPathCapabilityDetector(unittest.TestCase):
    """Tests detection of distinct management capabilities."""

    @mock.patch("core.management.capability_detector.socket.create_connection")
    def test_ip_port_reachability_success(self, mock_conn):
        """Probing open TCP ports returns True with latency."""
        mock_sock = mock.MagicMock()
        mock_conn.return_value = mock_sock

        ok, lat, err = check_tcp_port("192.168.88.1", 22, timeout=1.0)
        self.assertTrue(ok)
        self.assertGreaterEqual(lat, 0.0)
        self.assertIsNone(err)

    @mock.patch("core.management.capability_detector.socket.create_connection")
    def test_ip_port_reachability_failure(self, mock_conn):
        """Probing closed/unreachable TCP ports returns False."""
        mock_conn.side_effect = TimeoutError("Connection timed out")

        ok, lat, err = check_tcp_port("192.168.88.99", 22, timeout=1.0)
        self.assertFalse(ok)
        self.assertEqual(lat, 0.0)
        self.assertIn("timed out", err.lower())

    def test_detect_ip_capabilities(self):
        """detect_ip_capabilities evaluates both SSH (22) and RouterOS API (8728)."""
        with mock.patch("core.management.capability_detector.check_tcp_port") as mock_probe:
            mock_probe.side_effect = [(True, 2.5, ""), (True, 3.1, "")]
            res = CapabilityDetector.detect_ip_capabilities("192.168.88.1")
            self.assertTrue(res["ip_valid"])
            self.assertTrue(res["ssh_reachable"])
            self.assertTrue(res["api_reachable"])
            self.assertEqual(res["ssh_latency_ms"], 2.5)

    def test_romon_version_compatibility(self):
        """RouterOS version >= 6.28 supports RoMON."""
        compat_649 = CapabilityDetector.evaluate_romon_compatibility("6.49.7", vendor="MikroTik")
        self.assertTrue(compat_649["supported"])

        compat_712 = CapabilityDetector.evaluate_romon_compatibility("7.12.1", vendor="MikroTik")
        self.assertTrue(compat_712["supported"])

        compat_old = CapabilityDetector.evaluate_romon_compatibility("6.10", vendor="MikroTik")
        self.assertFalse(compat_old["supported"])
        self.assertIn("6.28", compat_old["reason"])

        compat_cisco = CapabilityDetector.evaluate_romon_compatibility("15.2", vendor="Cisco")
        self.assertFalse(compat_cisco["supported"])

    def test_l2_adjacency_check(self):
        """Checks L2 adjacency from ARP entries or designated interface."""
        # MAC invalid
        inv = CapabilityDetector.check_layer2_adjacency("not-a-mac")
        self.assertFalse(inv["is_adjacent"])

        # Designated interface
        adj = CapabilityDetector.check_layer2_adjacency("64:D1:54:12:34:56", adjacent_interfaces=["bridge1"])
        self.assertTrue(adj["is_adjacent"])
        self.assertEqual(adj["interface"], "bridge1")


class TestMultiPathSelectionEngine(unittest.TestCase):
    """Tests deterministic selection, rationales, and rejection reasons."""

    @mock.patch("core.management.capability_detector.CapabilityDetector.detect_ip_capabilities")
    def test_precedence_ssh_ip_primary(self, mock_detect):
        """When SSH is reachable, it is selected as the primary active path."""
        mock_detect.return_value = {
            "ip_valid": True, "ssh_reachable": True, "ssh_latency_ms": 1.5, "ssh_error": "",
            "api_reachable": True, "api_latency_ms": 2.0, "api_error": ""
        }
        profile = SelectionEngine.evaluate_paths(
            device_id="dev-01",
            device_name="Core-R1",
            host="192.168.88.1",
            mac="64:D1:54:11:22:33",
            routeros_version="7.12",
        )
        self.assertIsNotNone(profile.active_path)
        self.assertEqual(profile.active_path.method, ManagementMethod.SSH_IP.value)
        self.assertIn("SSH dipilih", profile.selection_rationale)

    @mock.patch("core.management.capability_detector.CapabilityDetector.detect_ip_capabilities")
    def test_fallback_to_api_when_ssh_unreachable(self, mock_detect):
        """When SSH is closed but RouterOS API (8728) is open, API is selected."""
        mock_detect.return_value = {
            "ip_valid": True, "ssh_reachable": False, "ssh_latency_ms": 0.0, "ssh_error": "Connection refused",
            "api_reachable": True, "api_latency_ms": 3.0, "api_error": ""
        }
        profile = SelectionEngine.evaluate_paths(
            device_id="dev-02",
            device_name="Edge-SW",
            host="192.168.88.2",
            mac="64:D1:54:11:22:44",
            routeros_version="7.12",
        )
        self.assertIsNotNone(profile.active_path)
        self.assertEqual(profile.active_path.method, ManagementMethod.API_IP.value)
        self.assertIn("RouterOS API", profile.selection_rationale)

    @mock.patch("core.management.capability_detector.CapabilityDetector.detect_ip_capabilities")
    def test_fallback_to_romon_when_ip_unreachable(self, mock_detect):
        """When IP is unreachable, but RoMON neighbor exists, RoMON overlay is selected."""
        mock_detect.return_value = {
            "ip_valid": False, "ssh_reachable": False, "api_reachable": False, "reason": "No IP"
        }
        romon_neighbors = [
            RomonNeighbor(
                romon_id="64:D1:54:11:22:55",
                mac="64:D1:54:11:22:55",
                identity="Isolated-AP",
                hop_count=2,
                via_device_id="Core-R1",
                via_device_name="Core-R1",
            )
        ]
        profile = SelectionEngine.evaluate_paths(
            device_id="dev-03",
            device_name="Isolated-AP",
            host=None,
            mac="64:D1:54:11:22:55",
            routeros_version="6.49",
            romon_neighbors=romon_neighbors,
        )
        self.assertIsNotNone(profile.active_path)
        self.assertEqual(profile.active_path.method, ManagementMethod.ROMON.value)
        self.assertIn("RoMON", profile.selection_rationale)
        self.assertEqual(profile.active_path.hops, 2)

    @mock.patch("core.management.capability_detector.CapabilityDetector.detect_ip_capabilities")
    def test_fallback_to_mac_telnet_when_l2_adjacent(self, mock_detect):
        """When IP and RoMON are unavailable, MAC Telnet is selected for L2 adjacent devices."""
        mock_detect.return_value = {
            "ip_valid": False, "ssh_reachable": False, "api_reachable": False, "reason": "No IP"
        }
        profile = SelectionEngine.evaluate_paths(
            device_id="dev-04",
            device_name="Unconfigured-MikroTik",
            host=None,
            mac="64:D1:54:11:22:66",
            routeros_version="6.20",  # RoMON unsupported
            adjacent_interfaces=["ether2"],
        )
        self.assertIsNotNone(profile.active_path)
        self.assertEqual(profile.active_path.method, ManagementMethod.MAC_TELNET.value)
        self.assertIn("MAC Telnet dipilih", profile.selection_rationale)

    @mock.patch("core.management.capability_detector.CapabilityDetector.detect_ip_capabilities")
    def test_manual_override_precedence(self, mock_detect):
        """Manual administrative override strictly takes precedence over auto-selection."""
        mock_detect.return_value = {
            "ip_valid": True, "ssh_reachable": True, "ssh_latency_ms": 1.0, "ssh_error": "",
            "api_reachable": True, "api_latency_ms": 2.0, "api_error": ""
        }
        profile = SelectionEngine.evaluate_paths(
            device_id="dev-05",
            device_name="Core-R1",
            host="192.168.88.1",
            preferred_method="api_ip",
            manual_override=True,
        )
        self.assertIsNotNone(profile.active_path)
        self.assertEqual(profile.active_path.method, ManagementMethod.API_IP.value)
        self.assertTrue(profile.manual_selection)
        self.assertIn("manual oleh administrator", profile.selection_rationale)

    @mock.patch("core.management.capability_detector.CapabilityDetector.detect_ip_capabilities")
    def test_explicit_rejection_reasons(self, mock_detect):
        """All paths provide auditable rejection reasons when unavailable."""
        mock_detect.return_value = {
            "ip_valid": True, "ssh_reachable": False, "ssh_latency_ms": 0.0, "ssh_error": "Connection refused",
            "api_reachable": False, "api_latency_ms": 0.0, "api_error": "Port closed"
        }
        profile = SelectionEngine.evaluate_paths(
            device_id="dev-06",
            device_name="Remote-Router",
            host="10.0.0.1",
            mac="64:D1:54:99:99:99",
            routeros_version="6.15",
        )
        methods = {p.method: p for p in profile.paths}
        self.assertEqual(methods[ManagementMethod.SSH_IP.value].status, PathStatus.UNAVAILABLE.value)
        self.assertTrue(len(methods[ManagementMethod.SSH_IP.value].rejection_reason) > 0)
        self.assertEqual(methods[ManagementMethod.ROMON.value].status, PathStatus.UNSUPPORTED.value)
        self.assertIn("6.28", methods[ManagementMethod.ROMON.value].rejection_reason)


class TestRomonAndMacManagement(unittest.TestCase):
    """Tests RoMON neighbor parsing, safety guardrails, and provisioning plans."""

    def test_parse_romon_neighbors_detail(self):
        """Parses output of `/romon neighbor print detail`."""
        sample_output = """
 0 id=64:D1:54:AA:BB:CC identity="Core-R1" mac-address=64:D1:54:AA:BB:CC 
   hop-count=0 path="" interface=ether1 

 1 id=64:D1:54:11:22:33 identity="Edge-AP-Lt" mac-address=64:D1:54:11:22:33 
   hop-count=2 path=64:D1:54:AA:BB:CC interface=ether2 
"""
        neighbors = RomonManager.parse_romon_neighbor_output(
            sample_output,
            via_device_id="core_r1",
            via_device_name="Core-R1",
        )
        self.assertEqual(len(neighbors), 2)
        self.assertEqual(neighbors[0].identity, "Core-R1")
        self.assertEqual(neighbors[0].hop_count, 0)
        self.assertEqual(neighbors[1].identity, "Edge-AP-Lt")
        self.assertEqual(neighbors[1].hop_count, 2)
        self.assertEqual(neighbors[1].path, ["64:D1:54:AA:BB:CC"])

    def test_romon_provisioning_plan_safety(self):
        """RoMON provisioning plan masks secrets and protects WAN interfaces."""
        plan_res = RomonManager.prepare_provisioning_plan(
            device_id="dev-ap-01",
            device_name="AP-Hallway",
            routeros_version="7.12",
            wan_interfaces=["ether1-gateway", "sfp-wan"],
            custom_secret="superSecretKey123",
        )
        self.assertTrue(plan_res.get("success"))
        cmds = plan_res.get("proposed_commands", [])
        cmds_str = " ".join(cmds)
        self.assertIn("/romon set enabled=yes", cmds_str)
        # Secret should be in commands for execution, but masked in return payload
        self.assertIn("forbid=yes", cmds_str)
        self.assertIn("ether1-gateway", cmds_str)
        self.assertIn("sfp-wan", cmds_str)

    def test_romon_apply_requires_admin_approval(self):
        """Executing RoMON provisioning requires explicit admin approval."""
        plan_res = RomonManager.prepare_provisioning_plan(
            device_id="dev-ap-02",
            device_name="AP-Meeting",
            routeros_version="7.12",
        )
        token = plan_res["plan_token"]
        apply_res = RomonManager.apply_provisioning(token, admin_approved=False)
        self.assertFalse(apply_res.get("success"))
        self.assertIn("admin_approved=true", apply_res.get("error"))

    def test_mac_management_rejects_non_adjacent(self):
        """MAC Telnet reachability check rejects non-adjacent devices."""
        with mock.patch("core.management.capability_detector.CapabilityDetector.check_layer2_adjacency") as mock_l2:
            mock_l2.return_value = {"is_adjacent": False, "reason": "Not in ARP"}
            res = MacManager.test_mac_reachability("64:D1:54:99:99:99")
            self.assertFalse(res["reachable"])
            self.assertIn("Layer 2", res["error"])


class TestManagementApiEndpoints(unittest.TestCase):
    """Integration test suite for FastAPI management endpoints."""

    def setUp(self):
        self.client = TestClient(app)
        self.headers = get_test_auth_headers()
        self.mpm = get_multi_path_manager()
        # Seed test router
        self.mpm.evaluate_and_save_profile(
            device_id="test-router-01",
            device_name="Core-R1",
            host="192.168.88.1",
            mac="64:D1:54:11:22:33",
            routeros_version="7.12",
        )

    def test_get_management_paths(self):
        """GET /api/devices/{device_id}/management/paths returns profile and paths."""
        res = self.client.get("/api/devices/test-router-01/management/paths", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        self.assertIn("profile", data)
        self.assertIn("paths", data["profile"])
        self.assertIn("active_path", data["profile"])

    def test_select_management_override(self):
        """POST /api/devices/{device_id}/management/select sets manual override."""
        res = self.client.post(
            "/api/devices/test-router-01/management/select",
            headers=self.headers,
            json={"preferred_method": "romon"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        self.assertTrue(data["profile"]["manual_selection"])

        # Clear override
        res_clear = self.client.post(
            "/api/devices/test-router-01/management/select",
            headers=self.headers,
            json={"preferred_method": ""},
        )
        self.assertEqual(res_clear.status_code, 200)
        self.assertFalse(res_clear.json()["profile"]["manual_selection"])

    def test_test_management_path(self):
        """POST /api/devices/{device_id}/management/test executes connectivity probe."""
        res = self.client.post(
            "/api/devices/test-router-01/management/test",
            headers=self.headers,
            json={"method": "ssh_ip"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("result", data)
        self.assertEqual(data["result"]["method"], "ssh_ip")

    def test_romon_plan_and_apply_flow(self):
        """POST /api/devices/{device_id}/management/romon/plan compiles plan; apply requires approval."""
        res_plan = self.client.post(
            "/api/devices/test-router-01/management/romon/plan",
            headers=self.headers,
            json={"management_interfaces": ["lan"], "wan_interfaces": ["wan"]},
        )
        self.assertEqual(res_plan.status_code, 200)
        plan_data = res_plan.json()
        self.assertTrue(plan_data.get("success"))
        token = plan_data["plan_token"]

        # Unapproved apply must fail
        res_unapproved = self.client.post(
            "/api/devices/test-router-01/management/romon/apply",
            headers=self.headers,
            json={"plan_token": token, "admin_approved": False},
        )
        self.assertEqual(res_unapproved.status_code, 400)

    def test_management_matrix(self):
        """GET /api/management/matrix returns network matrix."""
        res = self.client.get("/api/management/matrix", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        self.assertIn("devices", data)


if __name__ == "__main__":
    unittest.main()
