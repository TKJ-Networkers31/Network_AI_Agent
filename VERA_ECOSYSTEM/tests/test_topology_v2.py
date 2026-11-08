"""
tests/test_topology_v2.py — Comprehensive 30-Scenario Automated Verification Suite
for AIRA OS Topology Fabric V2:
- Ownership & Trust Boundaries (Scenarios 1–7)
- Multi-Dimensional Device Status, Freshness & Rate-Limited Probes (Scenarios 8–13)
- Port-to-Port Physical Link Verification & Non-Fabricated Ports (Scenarios 14–20)
- Idempotent Reconciliation, Conflict Preservation & V1->V2 SQLite Migration (Scenarios 21–25)
- FastAPI Contract, Admin Security, Secret Redaction & Single-Flight Concurrency (Scenarios 26–30)

All tests run hermetically against temporary SQLite databases and mocked RouterOS CLI outputs.
Zero live network devices are contacted.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.routers.topology as topology_router_module
from core.topology_engine import TopologyEngine
from core.topology_models import bounded_icmp_ping, sanitize_cli_excerpt, sanitize_untrusted_text


class FakeInventoryStore:
    def __init__(self, devices: List[Dict[str, Any]]):
        self._devices = devices

    def list_devices(self) -> Dict[str, Any]:
        return {"success": True, "devices": list(self._devices)}

    def get_device(self, name: str) -> Dict[str, Any]:
        for d in self._devices:
            if d["name"].lower() == name.lower():
                return {"success": True, "device": d}
        return {"success": False, "error": "Not found"}


class FakeConnectionManager:
    def __init__(self, responses_by_device: Dict[str, Dict[str, Any]], fail_devices: set[str] | None = None):
        self.responses_by_device = responses_by_device
        self.fail_devices = {d.lower() for d in (fail_devices or set())}
        self.interrogated_devices: List[str] = []

    def list_sessions(self) -> List[Dict[str, Any]]:
        return []

    def execute_command(self, cmd: str, device_name: str = "", host: str = "", timeout: float = 15.0) -> Dict[str, Any]:
        key = (device_name or host).lower()
        if cmd == "/system identity print":
            self.interrogated_devices.append(device_name or host)
        if key in self.fail_devices:
            return {"success": False, "error": f"SSH timeout connecting to {device_name} password=SuperSecretPassword123"}
        dev_map = self.responses_by_device.get(key, {})
        out = dev_map.get(cmd, "")
        return {"success": True, "output": out}


class TestTopologyFabricV2(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "topology_v2.db"
        self.engine = TopologyEngine(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    # =========================================================================
    # A. OWNERSHIP, ISP BOUNDARY & DISCOVERY SCOPE (Tests 1–7)
    # =========================================================================

    def test_01_isp_neighbor_not_auto_owned(self):
        """1. Neighbor discovered on WAN/ISP boundary interface is NEVER classified as owned."""
        self.engine.discover_from_device_output(
            source_name="R1-Edge",
            source_ip="192.168.88.1",
            identity_output="name: R1-Edge",
            resource_output="version: 7.16\nboard-name: CCR2004",
            interface_output=' 0 R name="ether1" type="ether" mac-address=48:8F:5A:00:00:01\n 1 R name="ether2" type="ether" mac-address=48:8F:5A:00:00:02',
            dhcp_client_output=" 0 interface=ether1 status=bound address=203.0.113.2/30 gateway=203.0.113.1 add-default-route=yes",
            route_output=" 0 DAS dst-address=0.0.0.0/0 gateway=203.0.113.1 interface=ether1",
            nat_output=" 0 chain=srcnat action=masquerade out-interface=ether1",
            neighbor_output=(
                ' 0 interface=ether1 mac-address=DC:2C:6E:AA:BB:CC identity="ISP-Metro-Router" '
                'address=203.0.113.1 platform="MikroTik" board="CCR1036" interface-name="sfp1"'
            ),
            inventory_devices=[{"name": "R1-Edge", "host": "192.168.88.1", "enabled": True}],
        )
        topo = self.engine.get_topology()
        isp_node = next(n for n in topo["nodes"] if n["ip"] == "203.0.113.1")
        self.assertEqual(isp_node["ownership_status"], "unknown")
        self.assertNotEqual(isp_node["ownership_status"], "owned")
        self.assertEqual(isp_node["topology_scope"], "isp_upstream")
        self.assertEqual(isp_node["trust_zone"], "isp")

    def test_02_known_isp_gateway_in_edge_external_scope(self):
        """2. Device matching known_isp_devices is third_party/isp_upstream and hidden in internal_only view."""
        self.engine.update_policy({"known_isp_devices": ["203.0.113.1"]})
        self.engine.discover_from_device_output(
            source_name="R1-Edge",
            source_ip="10.0.0.1",
            identity_output="name: R1-Edge",
            resource_output="version: 7.16",
            interface_output=' 0 R name="ether1" type="ether" mac-address=48:8F:5A:00:00:01',
            route_output=" 0 AS dst-address=0.0.0.0/0 gateway=203.0.113.1 interface=ether1",
            neighbor_output="",
            inventory_devices=[{"name": "R1-Edge", "host": "10.0.0.1", "enabled": True}],
        )
        all_view = self.engine.get_topology(view_mode="internal_and_edge")
        gw = next(n for n in all_view["nodes"] if n["ip"] == "203.0.113.1")
        self.assertEqual(gw["ownership_status"], "third_party")
        self.assertEqual(gw["topology_scope"], "isp_upstream")

        internal_view = self.engine.get_topology(view_mode="internal_only")
        internal_ips = {n["ip"] for n in internal_view["nodes"]}
        self.assertIn("10.0.0.1", internal_ips)
        self.assertNotIn("203.0.113.1", internal_ips)

    def test_03_default_route_alone_not_isp_ownership(self):
        """3. A 0.0.0.0/0 route alone (e.g., internal core next-hop) does not prove ISP ownership."""
        self.engine.discover_from_device_output(
            source_name="Branch-Rtr",
            source_ip="10.10.1.2",
            identity_output="name: Branch-Rtr",
            resource_output="version: 7.15",
            interface_output=' 0 R name="ether1" type="ether" mac-address=48:8F:5A:10:00:01',
            route_output=" 0 AS dst-address=0.0.0.0/0 gateway=10.10.1.1 interface=ether1",
            neighbor_output="",
            inventory_devices=[{"name": "Branch-Rtr", "host": "10.10.1.2", "enabled": True}],
        )
        topo = self.engine.get_topology()
        gw = next(n for n in topo["nodes"] if n["ip"] == "10.10.1.1")
        self.assertEqual(gw["ownership_status"], "unknown")
        self.assertEqual(gw["topology_scope"], "unclassified")
        self.assertEqual(gw["confidence"], "low")

    def test_04_unknown_neighbor_never_recursively_interrogated(self):
        """4. Unknown / unauthorized neighbors are NEVER interrogated via SSH even in multi-hop mode."""
        self.engine.update_policy({"discovery_mode": "enterprise_managed", "discovery_depth": 3})
        inv = FakeInventoryStore([{"name": "Seed-R1", "host": "10.0.0.1", "enabled": True}])
        cm = FakeConnectionManager({
            "seed-r1": {
                "/system identity print": "name: Seed-R1",
                "/system resource print": "version: 7.16",
                "/interface print detail": ' 0 R name="ether1" type="ether" mac-address=48:8F:5A:01:01:01',
                "/ip neighbor print detail": (
                    ' 0 interface=ether1 mac-address=AA:BB:CC:DD:EE:01 address=10.0.0.99 '
                    'identity="Rogue-Router" platform="MikroTik" interface-name="ether1"'
                ),
            },
            "rogue-router": {
                "/system identity print": "name: Rogue-Router",
            },
        })
        res = self.engine.sync_from_seed_router(
            device_name="Seed-R1", mode="enterprise_managed", conn_mgr_override=cm, inv_store_override=inv
        )
        self.assertTrue(res["success"])
        self.assertEqual(cm.interrogated_devices, ["Seed-R1"])

    def test_05_approved_internal_device_recursively_discovered_in_enterprise_managed(self):
        """5. Approved inventory devices in enterprise_subnets ARE recursively interrogated in enterprise_managed mode."""
        self.engine.update_policy({
            "discovery_mode": "enterprise_managed",
            "discovery_depth": 2,
            "enterprise_subnets": ["10.0.0.0/24"],
        })
        inv = FakeInventoryStore([
            {"name": "Core-R1", "host": "10.0.0.1", "enabled": True},
            {"name": "SW-Dist1", "host": "10.0.0.2", "enabled": True},
        ])
        cm = FakeConnectionManager({
            "core-r1": {
                "/system identity print": "name: Core-R1",
                "/system resource print": "version: 7.16",
                "/interface print detail": ' 0 R name="sfp1" type="ether" mac-address=48:8F:5A:00:01:01',
                "/ip neighbor print detail": (
                    ' 0 interface=sfp1 mac-address=48:8F:5A:00:02:01 address=10.0.0.2 '
                    'identity="SW-Dist1" platform="MikroTik" board="CRS326" interface-name="sfp1"'
                ),
            },
            "sw-dist1": {
                "/system identity print": "name: SW-Dist1",
                "/system resource print": "version: 7.16\nboard-name: CRS326",
                "/interface print detail": (
                    ' 0 R name="sfp1" type="ether" mac-address=48:8F:5A:00:02:01\n'
                    ' 1 R name="ether5" type="ether" mac-address=48:8F:5A:00:02:05'
                ),
                "/ip neighbor print detail": (
                    ' 0 interface=ether5 mac-address=48:8F:5A:00:01:01 address=10.0.0.1 '
                    'identity="Core-R1" platform="MikroTik" interface-name="sfp1"\n'
                    ' 1 interface=ether5 mac-address=48:8F:5A:00:03:01 address=10.0.0.11 '
                    'identity="AP-Floor1" platform="MikroTik" board="cAP ax" interface-name="ether1"'
                ),
            },
        })
        # First verify seed_only stops at 1 hop
        res_seed = self.engine.sync_from_seed_router(
            device_name="Core-R1", mode="seed_only", conn_mgr_override=cm, inv_store_override=inv
        )
        self.assertTrue(res_seed["success"])
        self.assertEqual(cm.interrogated_devices, ["Core-R1"])

        # Now run enterprise_managed -> expands to SW-Dist1 and discovers AP-Floor1
        cm.interrogated_devices.clear()
        res_ent = self.engine.sync_from_seed_router(
            device_name="Core-R1", mode="enterprise_managed", conn_mgr_override=cm, inv_store_override=inv
        )
        self.assertTrue(res_ent["success"])
        self.assertEqual(cm.interrogated_devices, ["Core-R1", "SW-Dist1"])
        topo = self.engine.get_topology()
        names = {n["name"] for n in topo["nodes"]}
        self.assertIn("AP-Floor1", names)

    def test_06_excluded_subnet_blocked(self):
        """6. Devices inside excluded_subnets are skipped from active graph import."""
        self.engine.update_policy({"excluded_subnets": ["192.168.99.0/24", "100.64.0.0/10"]})
        self.engine.discover_from_device_output(
            source_name="R1",
            source_ip="10.0.0.1",
            identity_output="name: R1",
            resource_output="version: 7.16",
            interface_output=' 0 R name="ether2" type="ether" mac-address=48:8F:5A:01:01:01',
            neighbor_output=' 0 interface=ether2 mac-address=AA:BB:CC:00:99:01 address=192.168.99.5 identity="Lab-Box"',
            arp_output=" 0 DC address=100.64.1.25 mac-address=AA:BB:CC:00:99:02 interface=ether2",
            inventory_devices=[{"name": "R1", "host": "10.0.0.1", "enabled": True}],
        )
        topo = self.engine.get_topology()
        ips = {n["ip"] for n in topo["nodes"]}
        self.assertNotIn("192.168.99.5", ips)
        self.assertNotIn("100.64.1.25", ips)
        review = self.engine.get_review_queue()
        self.assertTrue(any(c["conflict_type"] == "excluded_subnet_observation" for c in review["conflicts"]))

    def test_07_ownership_and_scope_overrides_survive_rediscovery(self):
        """7. Admin classification overrides (ownership, scope, ISP boundary) survive subsequent scans."""
        self.engine.discover_from_device_output(
            source_name="R1",
            source_ip="10.0.0.1",
            identity_output="name: R1",
            resource_output="version: 7.16",
            interface_output=' 0 R name="ether1" type="ether"',
            neighbor_output=' 0 interface=ether1 mac-address=AA:BB:CC:11:22:33 address=172.16.0.1 identity="Partner-CPE"',
        )
        nid = next(n["id"] for n in self.engine.get_topology()["nodes"] if n["ip"] == "172.16.0.1")
        self.engine.classify_node_override(
            nid,
            ownership_status="managed_external",
            topology_scope="enterprise_edge",
            trust_zone="dmz",
            reason="Verified partner MPLS CPE",
        )
        # Re-run discovery
        self.engine.discover_from_device_output(
            source_name="R1",
            source_ip="10.0.0.1",
            identity_output="name: R1",
            resource_output="version: 7.16",
            interface_output=' 0 R name="ether1" type="ether"',
            neighbor_output=' 0 interface=ether1 mac-address=AA:BB:CC:11:22:33 address=172.16.0.1 identity="Partner-CPE"',
        )
        updated = next(n for n in self.engine.get_topology()["nodes"] if n["id"] == nid)
        self.assertEqual(updated["ownership_status"], "managed_external")
        self.assertEqual(updated["topology_scope"], "enterprise_edge")
        self.assertEqual(updated["trust_zone"], "dmz")
        self.assertEqual(updated["provenance"], "hybrid")

    # =========================================================================
    # B. MULTI-DIMENSIONAL DEVICE STATUS & PROBES (Tests 8–13)
    # =========================================================================

    def test_08_ping_updates_reachability_never_ownership(self):
        """8. Successful ICMP ping updates reachability_status & latency without changing ownership."""
        self.engine.discover_from_device_output(
            source_name="R1",
            source_ip="10.0.0.1",
            identity_output="name: R1",
            resource_output="version: 7.16",
            interface_output=' 0 R name="ether1" type="ether"',
            neighbor_output=' 0 interface=ether1 mac-address=DE:AD:BE:EF:00:01 address=203.0.113.9 identity="External-GW"',
        )
        ext = next(n for n in self.engine.get_topology()["nodes"] if n["ip"] == "203.0.113.9")
        self.assertEqual(ext["ownership_status"], "unknown")

        probe = self.engine.probe_node_icmp(
            ext["id"],
            ping_fn=lambda ip, **kw: {"success": True, "alive": True, "avg_rtt_ms": 3.4, "raw_excerpt": "64 bytes TTL=64"},
        )
        self.assertTrue(probe["success"])
        self.assertEqual(probe["reachability_status"], "reachable")

        ext_after = next(n for n in self.engine.get_topology()["nodes"] if n["id"] == ext["id"])
        self.assertEqual(ext_after["ownership_status"], "unknown")
        self.assertEqual(ext_after["latency_ms"], 3.4)

    def test_09_failed_ping_does_not_delete_node(self):
        """9. Failed ICMP ping marks node unreachable without deleting node or links."""
        self.engine.upsert_node("node_srv", "DB-Server", ip="10.0.50.10", device_type="server")
        res = self.engine.probe_node_icmp(
            "node_srv",
            ping_fn=lambda ip, **kw: {"success": True, "alive": False, "avg_rtt_ms": 0.0, "error": "Timeout"},
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["reachability_status"], "unreachable")
        topo = self.engine.get_topology()
        srv = next((n for n in topo["nodes"] if n["id"] == "node_srv"), None)
        self.assertIsNotNone(srv)
        self.assertEqual(srv["status"], "offline")

    def test_10_arp_alone_neither_reachable_nor_physical_cable(self):
        """10. ARP-only host has reachability_status='unknown' and link_type='inferred' (never online/physical)."""
        self.engine.discover_from_device_output(
            source_name="R1",
            source_ip="10.0.0.1",
            identity_output="name: R1",
            resource_output="version: 7.16",
            interface_output=' 0 R name="bridge-lan" type="bridge"',
            neighbor_output="",
            arp_output=" 0 DC address=10.0.0.155 mac-address=00:11:22:33:44:55 interface=bridge-lan",
        )
        topo = self.engine.get_topology()
        arp_host = next(n for n in topo["nodes"] if n["ip"] == "10.0.0.155")
        self.assertEqual(arp_host["reachability_status"], "unknown")
        self.assertEqual(arp_host["ownership_status"], "unknown")
        self.assertNotEqual(arp_host["status"], "online")

        arp_link = next(l for l in topo["links"] if l["target"] == arp_host["id"])
        self.assertEqual(arp_link["link_type"], "inferred")
        self.assertEqual(arp_link["verification_status"], "inferred")
        self.assertEqual(arp_link["target_port"], "")

    def test_11_stale_observations_marked_stale(self):
        """11. Aging observations transition cleanly from fresh -> stale -> expired."""
        t0 = 1_700_000_000.0
        self.engine.update_policy({"freshness_threshold_sec": 300, "expire_threshold_sec": 3600})
        self.engine.discover_from_device_output(
            source_name="R1",
            source_ip="10.0.0.1",
            identity_output="name: R1",
            resource_output="version: 7.16",
            interface_output=' 0 R name="ether2" type="ether"',
            neighbor_output=' 0 interface=ether2 mac-address=48:8F:5A:AA:BB:CC address=10.0.0.2 identity="SW1"',
            now_ts=t0,
        )
        topo_fresh = self.engine.get_topology(now=t0 + 60)
        sw_fresh = next(n for n in topo_fresh["nodes"] if n["ip"] == "10.0.0.2")
        self.assertEqual(sw_fresh["observation_freshness"], "fresh")

        topo_stale = self.engine.get_topology(now=t0 + 500)
        sw_stale = next(n for n in topo_stale["nodes"] if n["ip"] == "10.0.0.2")
        self.assertEqual(sw_stale["observation_freshness"], "stale")
        self.assertEqual(sw_stale["reachability_status"], "unknown")

        topo_exp = self.engine.get_topology(now=t0 + 4000)
        sw_exp = next(n for n in topo_exp["nodes"] if n["ip"] == "10.0.0.2")
        self.assertEqual(sw_exp["observation_freshness"], "expired")

    def test_12_unreachable_ssh_management_does_not_force_offline(self):
        """12. Unreachable SSH management marks management_unavailable without forcing reachability offline."""
        inv = FakeInventoryStore([
            {"name": "R1", "host": "10.0.0.1", "enabled": True},
            {"name": "SW-Managed", "host": "10.0.0.2", "enabled": True},
        ])
        self.engine.update_policy({"discovery_mode": "enterprise_managed", "discovery_depth": 2})
        cm = FakeConnectionManager(
            responses_by_device={
                "r1": {
                    "/system identity print": "name: R1",
                    "/system resource print": "version: 7.16",
                    "/interface print detail": ' 0 R name="ether2" type="ether"',
                    "/ip neighbor print detail": (
                        ' 0 interface=ether2 mac-address=48:8F:5A:22:22:22 address=10.0.0.2 '
                        'identity="SW-Managed" platform="MikroTik" interface-name="ether1"'
                    ),
                }
            },
            fail_devices={"sw-managed"},
        )
        res = self.engine.sync_from_seed_router(
            device_name="R1", mode="enterprise_managed", conn_mgr_override=cm, inv_store_override=inv
        )
        self.assertTrue(res["success"])
        topo = self.engine.get_topology()
        sw = next(n for n in topo["nodes"] if n["ip"] == "10.0.0.2")
        self.assertEqual(sw["management_status"], "management_unavailable")
        self.assertEqual(sw["reachability_status"], "reachable")
        self.assertEqual(sw["status"], "warning")

    def test_13_probe_rate_limit_and_timeout_enforced(self):
        """13. ICMP probes enforce cooldown rate limits and subprocess timeout bounds."""
        self.engine.update_policy({"probe_cooldown_sec": 30, "probe_timeout_sec": 1, "probe_retries": 0})
        self.engine.upsert_node("n_ping", "Host-A", ip="10.0.0.20")
        calls = []

        def fake_ping(ip, **kw):
            calls.append(ip)
            return {"success": True, "alive": True, "avg_rtt_ms": 1.8}

        t0 = 1_700_000_000.0
        r1 = self.engine.probe_node_icmp("n_ping", now=t0, ping_fn=fake_ping)
        self.assertTrue(r1["success"])
        r2 = self.engine.probe_node_icmp("n_ping", now=t0 + 5, ping_fn=fake_ping)
        self.assertFalse(r2["success"])
        self.assertTrue(r2["rate_limited"])
        self.assertEqual(len(calls), 1)

        with patch("core.topology_models.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ping", timeout=1)):
            tout = bounded_icmp_ping("10.0.0.20", count=1, timeout_sec=1, retries=0)
            self.assertTrue(tout["success"])
            self.assertFalse(tout["alive"])
            self.assertIn("timed out", tout["error"])

    # =========================================================================
    # C. PORT-TO-PORT WIRING & LINK CONFIDENCE (Tests 14–20)
    # =========================================================================

    def test_14_direct_l2_neighbor_and_bidirectional_confirmation(self):
        """14. Single-sided L2 neighbor is 'observed'; bidirectional port agreement upgrades to 'physical'/'confirmed'."""
        inv = [
            {"name": "R1", "host": "10.0.0.1", "enabled": True},
            {"name": "SW1", "host": "10.0.0.2", "enabled": True},
        ]
        self.engine.discover_from_device_output(
            source_name="R1",
            source_ip="10.0.0.1",
            identity_output="name: R1",
            resource_output="version: 7.16",
            interface_output=' 0 R name="ether2" type="ether" mac-address=48:8F:5A:00:01:02',
            neighbor_output=(
                ' 0 interface=ether2 mac-address=48:8F:5A:00:02:24 address=10.0.0.2 '
                'identity="SW1" platform="MikroTik" interface-name="ether24"'
            ),
            inventory_devices=inv,
        )
        links_1 = self.engine.get_topology()["links"]
        self.assertEqual(len(links_1), 1)
        self.assertEqual(links_1[0]["link_type"], "layer2_adjacency")
        self.assertEqual(links_1[0]["verification_status"], "observed")

        # Peer SW1 reports matching reverse port mapping SW1:ether24 <-> R1:ether2
        self.engine.discover_from_device_output(
            source_name="SW1",
            source_ip="10.0.0.2",
            identity_output="name: SW1",
            resource_output="version: 7.16",
            interface_output=' 0 R name="ether24" type="ether" mac-address=48:8F:5A:00:02:24',
            neighbor_output=(
                ' 0 interface=ether24 mac-address=48:8F:5A:00:01:02 address=10.0.0.1 '
                'identity="R1" platform="MikroTik" interface-name="ether2"'
            ),
            inventory_devices=inv,
        )
        links_2 = self.engine.get_topology()["links"]
        self.assertEqual(len(links_2), 1)
        self.assertEqual(links_2[0]["link_type"], "physical")
        self.assertEqual(links_2[0]["verification_status"], "confirmed")
        self.assertEqual(links_2[0]["confidence"], "high")

    def test_15_missing_remote_port_never_confirmed_never_invents_eth0(self):
        """15. Missing remote port stays empty '' (never fabricated 'eth0') and is never 'confirmed'."""
        self.engine.discover_from_device_output(
            source_name="R1",
            source_ip="10.0.0.1",
            identity_output="name: R1",
            resource_output="version: 7.16",
            interface_output=' 0 R name="ether3" type="ether"',
            neighbor_output=' 0 interface=ether3 mac-address=48:8F:5A:77:88:99 address=10.0.0.77 identity="AP-NoRemotePort"',
        )
        link = self.engine.get_topology()["links"][0]
        self.assertEqual(link["source_port"], "ether3")
        self.assertEqual(link["target_port"], "")
        self.assertNotEqual(link["target_port"], "eth0")
        self.assertEqual(link["verification_status"], "observed")
        self.assertEqual(link["confidence"], "low")

    def test_16_ping_only_and_arp_only_never_create_confirmed_physical_cables(self):
        """16. Neither ICMP ping nor ARP+DHCP+FDB observations ever create a confirmed physical link."""
        self.engine.discover_from_device_output(
            source_name="R1",
            source_ip="10.0.0.1",
            identity_output="name: R1",
            resource_output="version: 7.16",
            interface_output=' 0 R name="bridge1" type="bridge"',
            neighbor_output="",
            arp_output=" 0 DC address=10.0.0.88 mac-address=AA:BB:CC:00:00:88 interface=bridge1",
            dhcp_lease_output=' 0 address=10.0.0.88 mac-address=AA:BB:CC:00:00:88 host-name="Laptop-HR" status=bound',
            bridge_host_output=" 0 mac-address=AA:BB:CC:00:00:88 on-interface=ether4 bridge=bridge1",
        )
        topo = self.engine.get_topology()
        host = next(n for n in topo["nodes"] if n["ip"] == "10.0.0.88")
        self.engine.probe_node_icmp(
            host["id"],
            ping_fn=lambda ip, **kw: {"success": True, "alive": True, "avg_rtt_ms": 2.0},
        )
        link = self.engine.get_topology()["links"][0]
        self.assertEqual(link["link_type"], "inferred")
        self.assertEqual(link["verification_status"], "inferred")
        self.assertNotIn(link["verification_status"], ("confirmed", "manual"))

    def test_17_conflicting_port_observations_marked_conflicting(self):
        """17. Mismatched port claims between endpoints mark link 'conflicting' and record a conflict."""
        inv = [
            {"name": "R1", "host": "10.0.0.1", "enabled": True},
            {"name": "SW1", "host": "10.0.0.2", "enabled": True},
        ]
        self.engine.discover_from_device_output(
            source_name="R1",
            source_ip="10.0.0.1",
            identity_output="name: R1",
            resource_output="version: 7.16",
            interface_output=' 0 R name="ether2" type="ether" mac-address=48:8F:5A:00:01:02',
            neighbor_output=' 0 interface=ether2 mac-address=48:8F:5A:00:02:24 address=10.0.0.2 identity="SW1" interface-name="ether24"',
            inventory_devices=inv,
        )
        # SW1 claims it connects to R1 via ether10 -> R1:ether5 (contradicting R1's ether2<->ether24!)
        self.engine.discover_from_device_output(
            source_name="SW1",
            source_ip="10.0.0.2",
            identity_output="name: SW1",
            resource_output="version: 7.16",
            interface_output=' 0 R name="ether10" type="ether" mac-address=48:8F:5A:00:02:24',
            neighbor_output=' 0 interface=ether10 mac-address=48:8F:5A:00:01:02 address=10.0.0.1 identity="R1" interface-name="ether5"',
            inventory_devices=inv,
        )
        link = self.engine.get_topology()["links"][0]
        self.assertEqual(link["verification_status"], "conflicting")
        conflicts = self.engine.get_review_queue()["conflicts"]
        self.assertTrue(any(c["conflict_type"] == "link_port_conflict" for c in conflicts))

    def test_18_routed_and_vpn_links_not_typed_as_physical_ethernet(self):
        """18. Routed gateway links are 'routed' and WireGuard/L2TP tunnel neighbors are 'vpn'."""
        self.engine.discover_from_device_output(
            source_name="HQ-R1",
            source_ip="10.0.0.1",
            identity_output="name: HQ-R1",
            resource_output="version: 7.16",
            interface_output=' 0 R name="ether1" type="ether"\n 1 R name="wireguard-branch" type="wg"',
            route_output=" 0 AS dst-address=0.0.0.0/0 gateway=198.51.100.1 interface=ether1",
            neighbor_output=' 0 interface=wireguard-branch address=10.255.255.2 identity="Branch-WG-Rtr" platform="MikroTik"',
        )
        topo = self.engine.get_topology()
        vpn_node = next(n for n in topo["nodes"] if n["ip"] == "10.255.255.2")
        self.assertEqual(vpn_node["topology_scope"], "vpn_remote")
        vpn_link = next(l for l in topo["links"] if l["target"] == vpn_node["id"])
        self.assertEqual(vpn_link["link_type"], "vpn")

        gw_node = next(n for n in topo["nodes"] if n["ip"] == "198.51.100.1")
        gw_link = next(l for l in topo["links"] if l["target"] == gw_node["id"])
        self.assertEqual(gw_link["link_type"], "routed")

    def test_19_manual_link_confirmations_survive_scans(self):
        """19. Admin-verified or manual links survive subsequent discovery scans without port clobbering."""
        self.engine.discover_from_device_output(
            source_name="R1",
            source_ip="10.0.0.1",
            identity_output="name: R1",
            resource_output="version: 7.16",
            interface_output=' 0 R name="ether2" type="ether"',
            neighbor_output=' 0 interface=ether2 mac-address=48:8F:5A:33:44:55 address=10.0.0.5 identity="SW-Access"',
        )
        link_id = self.engine.get_topology()["links"][0]["id"]
        self.engine.verify_or_override_link(
            link_id,
            verification_status="confirmed",
            source_port="ether2",
            target_port="ether48",
            reason="Physically traced patch cord in Rack A",
        )
        # Re-scan where MNDP still lacks remote port
        self.engine.discover_from_device_output(
            source_name="R1",
            source_ip="10.0.0.1",
            identity_output="name: R1",
            resource_output="version: 7.16",
            interface_output=' 0 R name="ether2" type="ether"',
            neighbor_output=' 0 interface=ether2 mac-address=48:8F:5A:33:44:55 address=10.0.0.5 identity="SW-Access"',
        )
        after = self.engine.get_topology()["links"][0]
        self.assertEqual(after["verification_status"], "confirmed")
        self.assertEqual(after["target_port"], "ether48")

    def test_20_repeated_scans_are_idempotent(self):
        """20. Repeated identical discovery scans produce zero duplicate nodes, links, or evidence bloat."""
        for _ in range(5):
            self.engine.discover_from_device_output(
                source_name="R1",
                source_ip="10.0.0.1",
                identity_output="name: R1",
                resource_output="version: 7.16",
                interface_output=' 0 R name="ether1" type="ether"\n 1 R name="ether2" type="ether"',
                route_output=" 0 AS dst-address=0.0.0.0/0 gateway=203.0.113.1 interface=ether1",
                neighbor_output=' 0 interface=ether2 mac-address=48:8F:5A:11:11:11 address=10.0.0.2 identity="SW1" interface-name="ether1"',
                arp_output=" 0 DC address=10.0.0.50 mac-address=AA:BB:CC:00:00:50 interface=ether2",
            )
        topo = self.engine.get_topology()
        self.assertEqual(len(topo["nodes"]), 4)  # R1, Upstream GW, SW1, ARP Host
        self.assertEqual(len(topo["links"]), 3)
        sw1 = next(n for n in topo["nodes"] if n["ip"] == "10.0.0.2")
        ev = self.engine.get_node_evidence(sw1["id"])
        self.assertEqual(len(ev), 1)

    # =========================================================================
    # D. RECONCILIATION, CONFLICTS & MIGRATION (Tests 21–25)
    # =========================================================================

    def test_21_manual_node_positions_survive_rediscovery(self):
        """21. User drag-and-drop canvas positions are preserved across rediscovery."""
        self.engine.discover_from_device_output(
            source_name="R1",
            source_ip="10.0.0.1",
            identity_output="name: R1",
            resource_output="version: 7.16",
            interface_output=' 0 R name="ether2" type="ether"',
            neighbor_output=' 0 interface=ether2 mac-address=48:8F:5A:11:22:33 address=10.0.0.2 identity="SW1"',
        )
        sw_id = next(n["id"] for n in self.engine.get_topology()["nodes"] if n["ip"] == "10.0.0.2")
        self.engine.update_node_position(sw_id, 812.5, 194.0)

        self.engine.discover_from_device_output(
            source_name="R1",
            source_ip="10.0.0.1",
            identity_output="name: R1",
            resource_output="version: 7.16",
            interface_output=' 0 R name="ether2" type="ether"',
            neighbor_output=' 0 interface=ether2 mac-address=48:8F:5A:11:22:33 address=10.0.0.2 identity="SW1"',
        )
        sw_after = next(n for n in self.engine.get_topology()["nodes"] if n["id"] == sw_id)
        self.assertEqual((sw_after["pos_x"], sw_after["pos_y"]), (812.5, 194.0))

    def test_22_manual_names_and_overrides_survive_rediscovery(self):
        """22. User-edited node display name survives rediscovery even when MNDP sends generic identity."""
        self.engine.discover_from_device_output(
            source_name="R1",
            source_ip="10.0.0.1",
            identity_output="name: R1",
            resource_output="version: 7.16",
            interface_output=' 0 R name="ether2" type="ether"',
            neighbor_output=' 0 interface=ether2 mac-address=48:8F:5A:99:88:77 address=10.0.0.9 identity="MikroTik"',
        )
        nid = next(n["id"] for n in self.engine.get_topology()["nodes"] if n["ip"] == "10.0.0.9")
        self.engine.upsert_node(node_id=nid, name="Switch-Lobby-Utama", ip="10.0.0.9", device_type="switch", provenance="user_managed")

        self.engine.discover_from_device_output(
            source_name="R1",
            source_ip="10.0.0.1",
            identity_output="name: R1",
            resource_output="version: 7.16",
            interface_output=' 0 R name="ether2" type="ether"',
            neighbor_output=' 0 interface=ether2 mac-address=48:8F:5A:99:88:77 address=10.0.0.9 identity="MikroTik"',
        )
        after = next(n for n in self.engine.get_topology()["nodes"] if n["id"] == nid)
        self.assertEqual(after["name"], "Switch-Lobby-Utama")

    def test_23_transient_failed_ssh_scan_preserves_confirmed_topology(self):
        """23. Transient SSH failure on seed router records failed job WITHOUT wiping existing graph."""
        inv = FakeInventoryStore([{"name": "R1", "host": "10.0.0.1", "enabled": True}])
        cm_ok = FakeConnectionManager({
            "r1": {
                "/system identity print": "name: R1",
                "/system resource print": "version: 7.16",
                "/interface print detail": ' 0 R name="ether2" type="ether"',
                "/ip neighbor print detail": ' 0 interface=ether2 mac-address=48:8F:5A:11:22:33 address=10.0.0.2 identity="SW1"',
            }
        })
        r_ok = self.engine.sync_from_seed_router(device_name="R1", conn_mgr_override=cm_ok, inv_store_override=inv)
        self.assertTrue(r_ok["success"])
        self.assertEqual(len(self.engine.get_topology()["nodes"]), 2)

        cm_fail = FakeConnectionManager({}, fail_devices={"r1"})
        r_fail = self.engine.sync_from_seed_router(device_name="R1", conn_mgr_override=cm_fail, inv_store_override=inv)
        self.assertFalse(r_fail["success"])

        topo_after = self.engine.get_topology()
        self.assertEqual(len(topo_after["nodes"]), 2)
        self.assertEqual(len(topo_after["links"]), 1)
        self.assertEqual(topo_after["last_job"]["status"], "failed")

    def test_24_ip_and_hardware_conflicts_do_not_silently_merge(self):
        """24. Duplicate IP with different MAC/identity creates separate node + open ip_conflict."""
        self.engine.discover_from_device_output(
            source_name="R1",
            source_ip="10.0.0.1",
            identity_output="name: R1",
            resource_output="version: 7.16",
            interface_output=' 0 R name="ether2" type="ether"',
            neighbor_output=' 0 interface=ether2 mac-address=48:8F:5A:00:00:AA address=10.0.0.50 identity="SW-Alpha" board="CRS326"',
        )
        # Second device with completely different MAC & hardware claims 10.0.0.50
        self.engine.discover_from_device_output(
            source_name="R1",
            source_ip="10.0.0.1",
            identity_output="name: R1",
            resource_output="version: 7.16",
            interface_output=' 0 R name="ether3" type="ether"',
            neighbor_output=' 0 interface=ether3 mac-address=DC:2C:6E:00:00:BB address=10.0.0.50 identity="Router-Beta" board="RB5009"',
        )
        topo = self.engine.get_topology()
        nodes_at_ip = [n for n in topo["nodes"] if n["ip"] == "10.0.0.50"]
        self.assertEqual(len(nodes_at_ip), 2)
        conflicts = self.engine.get_review_queue()["conflicts"]
        self.assertTrue(any(c["conflict_type"] == "ip_conflict" for c in conflicts))

    def test_25_v1_sqlite_database_migrates_cleanly_to_v2(self):
        """25. Existing V1 topology.db schema migrates non-destructively preserving all rows & positions."""
        v1_db = Path(self.temp_dir.name) / "legacy_v1.db"
        conn = sqlite3.connect(str(v1_db))
        conn.executescript(
            """
            CREATE TABLE topology_nodes (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                identity TEXT,
                ip TEXT,
                mac TEXT,
                device_type TEXT DEFAULT 'router',
                status TEXT DEFAULT 'online',
                latency_ms REAL DEFAULT 0.0,
                pos_x REAL DEFAULT 0.0,
                pos_y REAL DEFAULT 0.0,
                last_seen REAL,
                metadata_json TEXT DEFAULT '{}'
            );
            CREATE TABLE topology_links (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                source_port TEXT DEFAULT '',
                target_port TEXT DEFAULT '',
                link_type TEXT DEFAULT 'ethernet',
                status TEXT DEFAULT 'up',
                bandwidth TEXT DEFAULT '',
                last_checked REAL
            );
            INSERT INTO topology_nodes (id, name, identity, ip, mac, device_type, status, latency_ms, pos_x, pos_y, last_seen, metadata_json)
            VALUES ('node_legacy_1', 'Legacy-CCR', 'Legacy-CCR', '192.168.1.1', '48:8F:5A:01:02:03', 'router', 'online', 1.5, 310.0, 140.0, 1700000000.0, '{"role":"backbone"}');
            INSERT INTO topology_nodes (id, name, identity, ip, mac, device_type, status, latency_ms, pos_x, pos_y, last_seen, metadata_json)
            VALUES ('node_legacy_2', 'Legacy-SW', 'Legacy-SW', '192.168.1.2', '48:8F:5A:01:02:04', 'switch', 'online', 2.0, 310.0, 340.0, 1700000000.0, '{}');
            INSERT INTO topology_links (id, source_id, target_id, source_port, target_port, link_type, status, bandwidth, last_checked)
            VALUES ('lnk_1', 'node_legacy_1', 'node_legacy_2', 'ether1', 'ether24', 'ethernet', 'up', '1 Gbps', 1700000000.0);
            """
        )
        conn.commit()
        conn.close()

        migrated_engine = TopologyEngine(v1_db)
        topo = migrated_engine.get_topology()
        self.assertEqual(len(topo["nodes"]), 2)
        self.assertEqual(len(topo["links"]), 1)
        legacy_rtr = next(n for n in topo["nodes"] if n["id"] == "node_legacy_1")
        self.assertEqual((legacy_rtr["pos_x"], legacy_rtr["pos_y"]), (310.0, 140.0))
        self.assertIn("ownership_status", legacy_rtr)
        self.assertIn("reachability_status", legacy_rtr)

    # =========================================================================
    # E. FASTAPI CONTRACT, SECURITY, CONCURRENCY & PARSERS (Tests 26–30)
    # =========================================================================

    def _build_test_client(self) -> TestClient:
        app = FastAPI()
        app.include_router(topology_router_module.router)
        return TestClient(app)

    def test_26_fastapi_backward_compatible_and_v2_endpoints(self):
        """26. Existing & V2 REST endpoints work end-to-end via FastAPI TestClient."""
        with patch.object(topology_router_module, "get_topology_engine", return_value=self.engine):
            client = self._build_test_client()

            # Policy GET & PUT
            r_pol = client.put("/api/topology/policy", json={"enterprise_subnets": ["10.0.0.0/8"], "discovery_mode": "seed_only"})
            self.assertEqual(r_pol.status_code, 200)
            self.assertEqual(r_pol.json()["policy"]["enterprise_subnets"], ["10.0.0.0/8"])

            # Invalid CIDR rejected with 400
            r_bad_pol = client.put("/api/topology/policy", json={"enterprise_subnets": ["not-a-cidr"]})
            self.assertEqual(r_bad_pol.status_code, 400)

            # Create two nodes + manual link
            self.assertEqual(client.post("/api/topology/nodes", json={"id": "n1", "name": "Core-1", "ip": "10.0.0.1"}).status_code, 200)
            self.assertEqual(client.post("/api/topology/nodes", json={"id": "n2", "name": "ISP-1", "ip": "203.0.113.1", "device_type": "wan"}).status_code, 200)
            r_lnk = client.post("/api/topology/links", json={"source_id": "n1", "target_id": "n2", "source_port": "ether1", "target_port": ""})
            self.assertEqual(r_lnk.status_code, 200)
            link_id = r_lnk.json()["id"]

            # Classify n2 as ISP boundary & verify link
            r_cls = client.post("/api/topology/nodes/n2/classify", json={"ownership_status": "third_party", "is_isp_boundary": True, "reason": "ISP PE"})
            self.assertEqual(r_cls.status_code, 200)

            r_ver = client.post("/api/topology/links/verify", json={"link_id": link_id, "verification_status": "observed", "reason": "WAN handoff"})
            self.assertEqual(r_ver.status_code, 200)

            # Evidence, Review, Audit Log & View Mode filtering
            self.assertGreaterEqual(len(client.get("/api/topology/nodes/n2/evidence").json()["evidence"]), 1)
            self.assertTrue(client.get("/api/topology/review").json()["success"])
            self.assertGreaterEqual(len(client.get("/api/topology/audit-log").json()["audit_log"]), 2)

            internal_only = client.get("/api/topology?view_mode=internal_only").json()
            self.assertEqual([n["id"] for n in internal_only["nodes"]], ["n1"])

    def test_27_security_sanitization_unregistered_seed_and_clear_confirmation(self):
        """27. Unregistered hosts rejected, secrets redacted, admin token enforced, and clear requires confirm=true."""
        with patch.object(topology_router_module, "get_topology_engine", return_value=self.engine):
            client = self._build_test_client()
            client.post("/api/topology/nodes", json={"id": "n_keep", "name": "KeepMe", "ip": "10.0.0.1"})

            # Destructive clear without confirm=true MUST fail with 400
            r_clear_no = client.delete("/api/topology/clear")
            self.assertEqual(r_clear_no.status_code, 400)
            self.assertEqual(len(self.engine.get_topology()["nodes"]), 1)

            # Unregistered host discovery rejected without interrogating arbitrary host
            inv = FakeInventoryStore([{"name": "R1", "host": "10.0.0.1", "enabled": True}])
            cm = FakeConnectionManager({}, fail_devices={"r1"})
            with patch("core.inventory_store.get_inventory_store", return_value=inv), patch(
                "agents.akane.connection_manager.get_connection_manager", return_value=cm
            ):
                r_unreg = client.post("/api/topology/discover", json={"host": "198.51.100.99", "password": "MyRawPassword999"})
                self.assertFalse(r_unreg.json()["success"])
                self.assertNotIn("MyRawPassword999", r_unreg.text)

                # Failing SSH error containing password=... is redacted before returning!
                r_leak = client.post("/api/topology/discover", json={"device_name": "R1"})
                self.assertFalse(r_leak.json()["success"])
                self.assertNotIn("SuperSecretPassword123", r_leak.text)
                self.assertIn("[REDACTED]", r_leak.text)

            # Admin token enforcement when AIRA_TOPOLOGY_ADMIN_TOKEN is configured
            with patch.dict(os.environ, {"AIRA_TOPOLOGY_ADMIN_TOKEN": "top-secret-admin-token"}):
                r_unauth = client.post("/api/topology/nodes", json={"id": "n_bad", "name": "Unauthorized"})
                self.assertEqual(r_unauth.status_code, 403)

                r_auth = client.delete(
                    "/api/topology/clear?confirm=true",
                    headers={"X-AIRA-Admin-Token": "top-secret-admin-token"},
                )
                self.assertEqual(r_auth.status_code, 200)
                self.assertEqual(len(self.engine.get_topology()["nodes"]), 0)

    def test_28_concurrent_discovery_requests_bounded_single_flight(self):
        """28. Concurrent overlapping discovery calls are rejected cleanly with HTTP 409."""
        with patch.object(topology_router_module, "get_topology_engine", return_value=self.engine):
            client = self._build_test_client()
            self.engine._discovery_lock.acquire()
            self.engine._active_job_id = "disc_test_active"
            try:
                resp = client.post("/api/topology/discover", json={})
                self.assertEqual(resp.status_code, 409)
                body = resp.json()
                self.assertTrue(body["already_running"])
                self.assertEqual(body["active_job_id"], "disc_test_active")
            finally:
                self.engine._active_job_id = None
                self.engine._discovery_lock.release()

    def test_29_ui_payload_exposes_unknown_stale_conflicting_inferred_states(self):
        """29. Topology JSON payload exposes unknown, stale, conflicting, and inferred states for UI rendering."""
        t0 = 1_700_000_000.0
        inv = [
            {"name": "R1", "host": "10.0.0.1", "enabled": True},
            {"name": "SW1", "host": "10.0.0.2", "enabled": True},
        ]
        self.engine.discover_from_device_output(
            source_name="R1",
            source_ip="10.0.0.1",
            identity_output="name: R1",
            resource_output="version: 7.16",
            interface_output=' 0 R name="ether2" type="ether" mac-address=48:8F:5A:00:01:02',
            neighbor_output=' 0 interface=ether2 mac-address=48:8F:5A:00:02:24 address=10.0.0.2 identity="SW1" interface-name="ether24"',
            arp_output=" 0 DC address=10.0.0.99 mac-address=AA:BB:CC:00:00:99 interface=ether2",
            inventory_devices=inv,
            now_ts=t0,
        )
        self.engine.discover_from_device_output(
            source_name="SW1",
            source_ip="10.0.0.2",
            identity_output="name: SW1",
            resource_output="version: 7.16",
            interface_output=' 0 R name="ether9" type="ether" mac-address=48:8F:5A:00:02:24',
            neighbor_output=' 0 interface=ether9 mac-address=48:8F:5A:00:01:02 address=10.0.0.1 identity="R1" interface-name="ether5"',
            inventory_devices=inv,
            now_ts=t0,
        )
        payload = self.engine.get_topology(now=t0 + 600)
        stats = payload["stats"]
        self.assertGreaterEqual(stats["ownership"]["unknown"], 1)
        self.assertGreaterEqual(stats["freshness"]["stale"], 1)
        self.assertGreaterEqual(stats["link_verification"]["conflicting"], 1)
        self.assertGreaterEqual(stats["link_verification"]["inferred"], 1)
        self.assertGreaterEqual(stats["open_conflicts"], 1)

    def test_30_routeros_v6_and_v7_parsers_and_llm_context_sanitization(self):
        """30. RouterOS v6/v7 CLI outputs, XSS payloads, and wireless secrets are parsed & sanitized safely."""
        malicious_identity = 'name: "Core<script>alert(1)</script>Router"'
        wireless_secret = ' 0 R name="wlan1" ssid="OfficeWiFi" wpa2-pre-shared-key="UltraSecretWifiKey!"'
        clean_id = sanitize_untrusted_text(malicious_identity)
        clean_wlan = sanitize_cli_excerpt(wireless_secret)
        self.assertNotIn("<script>", clean_id)
        self.assertNotIn("UltraSecretWifiKey!", clean_wlan)
        self.assertIn("[REDACTED]", clean_wlan)

        self.engine.discover_from_device_output(
            source_name="Core-V6",
            source_ip="10.0.0.1",
            identity_output=malicious_identity,
            resource_output="version: 6.49.10 (long-term)\nboard-name: RB4011iGS+",
            interface_output=' 0 R name="ether1" type="ether"',
            neighbor_output=' 0 interface=ether1,bridge-local mac-address=48:8F:5A:55:66:77 address=10.0.0.3 identity="AP-V6" interface-name="ether1"',
            wireless_output=wireless_secret,
        )
        ctx = self.engine.get_llm_topology_context()
        self.assertIn("EVIDENCE-BASED FABRIC V2", ctx)
        self.assertNotIn("<script>", ctx)
        self.assertNotIn("UltraSecretWifiKey!", ctx)


if __name__ == "__main__":
    unittest.main()
