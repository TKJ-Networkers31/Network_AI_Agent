"""
tests/test_topology_discovery_v4.py — Acceptance Test Suite for Phase 4.2:
Automatic Topology Discovery & Link Resolution Engine.

Verifies:
1. Mathematical Confidence Scoring Formula (S(e)) & qualitative rationale mapping.
2. Temporal decay based on half-life parameters.
3. Contradiction penalties (port overlap, carrier down).
4. Epistemic prohibition: shared subnets and ARP entries strictly barred from physical adjacency.
5. Single-sided Layer 2 neighbor discovery.
6. Bidirectional corroboration upgrade to confirmed physical adjacency.
7. Multi-edge support: parallel physical, L3 routed, and logical overlay tunnel edges.
8. Upstream default gateway transit isolation (strictly Layer 3).
9. Boundary interface detection & ISP upstream scope isolation.
10. CrossDeviceEvidenceCorrelator integration and reconciliation into topology_edges.
11. EdgeEvidence sensitive data sanitization & foreign key cascade delete.
12. Authentic RouterOS v7 CHR discovery parsing and idempotency.
"""

from __future__ import annotations

import gc
import json
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, List

from core.network_intelligence.correlation import (
    CorrelatedRelationship,
    CrossDeviceEvidenceCorrelator,
)
from core.network_intelligence.models import EvidenceItem
from core.network_intelligence.network_models import CorrelationConfidence, LinkType
from core.topology_engine import TopologyEngine
from core.topology_models import (
    ConfidenceTier,
    EdgeEvidence,
    RelationshipClass,
    TopologyEdge,
    calculate_edge_confidence,
)


class TestTopologyDiscoveryPhase4_2(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_topology_4_2.db"
        self.engine = TopologyEngine(self.db_path)

    def tearDown(self):
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def _insert_test_node(self, node_id: str, name: str, ip: str = "10.0.0.1"):
        """Helper to create node in topology_nodes."""
        self.engine.upsert_node(
            node_id=node_id,
            name=name,
            ip=ip,
            mac="AA:BB:CC:DD:EE:FF",
            device_type="router",
            status="online",
        )

    # -------------------------------------------------------------------------
    # Test 1: Mathematical Confidence Scoring Formula S(e)
    # -------------------------------------------------------------------------
    def test_01_mathematical_confidence_scoring_formula(self):
        """Verifies mathematical scoring formula S(e) across protocol weights and tiers."""
        now = 1000.0

        # Bidirectional L2 Neighbor -> CONFIRMED (0.95)
        ev_bi = [{"evidence_type": "bidirectional_l2", "protocol": "lldp", "observed_at": now}]
        score, tier, rationale = calculate_edge_confidence(ev_bi, is_bidirectional=True, now_ts=now)
        self.assertGreaterEqual(score, 0.90)
        self.assertEqual(tier, ConfidenceTier.CONFIRMED.value)
        self.assertIn("Bidirectional", rationale)

        # Single-Sided L2 Neighbor -> HIGH (0.80)
        ev_single_l2 = [{"evidence_type": "single_sided_l2", "protocol": "lldp", "observed_at": now}]
        score, tier, rationale = calculate_edge_confidence(ev_single_l2, is_bidirectional=False, now_ts=now)
        self.assertEqual(score, 0.80)
        self.assertEqual(tier, ConfidenceTier.HIGH.value)
        self.assertIn("Single-sided", rationale)

        # Dedicated Point-to-Point /30 Subnet -> HIGH (0.75)
        ev_p2p = [{"evidence_type": "dedicated_p2p_subnet", "protocol": "arp", "observed_at": now}]
        score, tier, rationale = calculate_edge_confidence(ev_p2p, now_ts=now)
        self.assertEqual(score, 0.75)
        self.assertEqual(tier, ConfidenceTier.HIGH.value)

        # Mutual ARP on Multi-Access Subnet -> MEDIUM (0.55)
        ev_multi_arp = [{"evidence_type": "mutual_arp_multiaccess", "protocol": "arp", "observed_at": now}]
        score, tier, rationale = calculate_edge_confidence(ev_multi_arp, now_ts=now)
        self.assertEqual(score, 0.55)
        self.assertEqual(tier, ConfidenceTier.MEDIUM.value)

        # Single-Sided ARP Entry -> LOW (0.35)
        ev_arp = [{"evidence_type": "single_sided_arp", "protocol": "arp", "observed_at": now}]
        score, tier, rationale = calculate_edge_confidence(ev_arp, now_ts=now)
        self.assertEqual(score, 0.35)
        self.assertEqual(tier, ConfidenceTier.LOW.value)

        # Routing Next-Hop -> LOW (0.30)
        ev_rt = [{"evidence_type": "routing_nexthop", "protocol": "routing_table", "observed_at": now}]
        score, tier, rationale = calculate_edge_confidence(ev_rt, now_ts=now)
        self.assertEqual(score, 0.30)
        self.assertEqual(tier, ConfidenceTier.LOW.value)

        # Randomized MAC -> LOW (0.05)
        ev_rand = [{"evidence_type": "randomized_mac", "protocol": "arp", "observed_at": now}]
        score, tier, rationale = calculate_edge_confidence(ev_rand, now_ts=now)
        self.assertEqual(score, 0.05)
        self.assertEqual(tier, ConfidenceTier.LOW.value)

        # Operator Manual Confirmation -> CONFIRMED (1.0)
        ev_man = [{"evidence_type": "operator_confirmation", "protocol": "manual", "observed_at": now}]
        score, tier, rationale = calculate_edge_confidence(ev_man, now_ts=now)
        self.assertEqual(score, 1.0)
        self.assertEqual(tier, ConfidenceTier.CONFIRMED.value)

    # -------------------------------------------------------------------------
    # Test 2: Temporal Decay Half-Life
    # -------------------------------------------------------------------------
    def test_02_temporal_decay_half_life(self):
        """Verifies exponential half-life decay D(delta_t) = 2^(-delta_t / tau)."""
        t0 = 1000.0

        # LLDP half-life is 180s. Base weight is 0.80.
        # At delta_t = 180s, decay factor = 0.5 => score = 0.80 * 0.5 = 0.40.
        ev_lldp = [{"evidence_type": "single_sided_l2", "protocol": "lldp", "observed_at": t0}]
        score, tier, _ = calculate_edge_confidence(ev_lldp, now_ts=t0 + 180.0)
        self.assertAlmostEqual(score, 0.40, places=2)
        self.assertEqual(tier, ConfidenceTier.MEDIUM.value)

        # At delta_t = 360s (2 half-lives), decay factor = 0.25 => score = 0.80 * 0.25 = 0.20.
        score_2, tier_2, _ = calculate_edge_confidence(ev_lldp, now_ts=t0 + 360.0)
        self.assertAlmostEqual(score_2, 0.20, places=2)
        self.assertEqual(tier_2, ConfidenceTier.LOW.value)

        # Administrator Manual Confirmation: tau = inf => D = 1.0 permanently.
        ev_man = [{"evidence_type": "operator_confirmation", "protocol": "manual", "observed_at": t0}]
        score_man, tier_man, _ = calculate_edge_confidence(ev_man, now_ts=t0 + 100000.0)
        self.assertEqual(score_man, 1.0)
        self.assertEqual(tier_man, ConfidenceTier.CONFIRMED.value)

    # -------------------------------------------------------------------------
    # Test 3: Contradiction Penalties
    # -------------------------------------------------------------------------
    def test_03_contradiction_penalties(self):
        """Verifies contradiction penalty P_contra reducing composite confidence."""
        t0 = 1000.0
        ev = [{"evidence_type": "single_sided_l2", "protocol": "lldp", "observed_at": t0}]

        # Port overlap penalty P_contra = 0.50 => score = 0.80 * (1 - 0.50) = 0.40
        score_half, tier_half, _ = calculate_edge_confidence(ev, contradiction_penalty=0.50, now_ts=t0)
        self.assertAlmostEqual(score_half, 0.40, places=2)
        self.assertEqual(tier_half, ConfidenceTier.MEDIUM.value)

        # Interface carrier down P_contra = 1.00 => score collapses to 0.0
        score_down, tier_down, rat_down = calculate_edge_confidence(ev, contradiction_penalty=1.00, now_ts=t0)
        self.assertEqual(score_down, 0.0)
        self.assertEqual(tier_down, ConfidenceTier.LOW.value)
        self.assertIn("carrier down", rat_down.lower())

    # -------------------------------------------------------------------------
    # Test 4: Epistemic Prohibition: Subnets and ARP Never Physical
    # -------------------------------------------------------------------------
    def test_04_epistemic_prohibition_subnet_and_arp_never_physical(self):
        """A shared subnet and ARP cache entries strictly generate Layer 3 edges, NEVER physical."""
        self._insert_test_node("node_r1", "Core-Router", "192.168.10.1")

        ip_addr_out = "0   address=192.168.10.1/24 network=192.168.10.0 interface=ether2"
        arp_out = "0  D address=192.168.10.50 mac-address=00:11:22:33:44:55 interface=ether2"

        res = self.engine.discover_from_device_output(
            source_name="Core-Router",
            source_ip="192.168.10.1",
            identity_output='name: "Core-Router"',
            resource_output="cpu-load: 5%\nversion: 7.16",
            neighbor_output="",  # No L2 neighbor packets!
            interface_output="0 R ether2 type=ether mtu=1500 mac-address=00:AA:BB:CC:DD:01",
            ip_address_output=ip_addr_out,
            arp_output=arp_out,
        )
        self.assertTrue(res["success"])

        # Check all edges in database
        edges = self.engine.list_edges()
        self.assertGreaterEqual(len(edges), 1)

        for edge in edges:
            # Epistemic Guardrail 1: NEVER physical!
            self.assertNotEqual(
                edge.relationship_class,
                RelationshipClass.PHYSICAL_ADJACENCY.value,
                "Shared subnet/ARP must never be classified as physical adjacency!",
            )
            self.assertIn(edge.relationship_class, ("layer3", "layer2"))
            self.assertIn(edge.confidence_tier, ("MEDIUM", "LOW"))
            self.assertLessEqual(edge.confidence_score, 0.55)

    # -------------------------------------------------------------------------
    # Test 5: Single-Sided Layer 2 Neighbor Discovery
    # -------------------------------------------------------------------------
    def test_05_single_sided_l2_neighbor_discovery(self):
        """Single-sided MNDP/LLDP neighbor creates a Layer 2 edge with HIGH confidence (0.80)."""
        self._insert_test_node("node_core", "Core-Router", "10.0.0.1")

        neighbor_out = (
            "0 interface=ether1 mac-address=08:00:27:11:22:33 identity=SW-Dist-1 "
            "platform=MikroTik version=7.16 interface-name=ether2"
        )
        interface_out = "0 R ether1 type=ether mtu=1500 mac-address=08:00:27:AA:BB:01"

        res = self.engine.discover_from_device_output(
            source_name="Core-Router",
            source_ip="10.0.0.1",
            identity_output='name: "Core-Router"',
            resource_output="cpu-load: 8%\nversion: 7.16",
            neighbor_output=neighbor_out,
            interface_output=interface_out,
        )
        self.assertTrue(res["success"])
        self.assertGreaterEqual(res.get("edges_added", 0), 1)

        # Inspect created edge
        edges = self.engine.list_edges()
        l2_edges = [e for e in edges if e.source_interface == "ether1"]
        self.assertEqual(len(l2_edges), 1)

        edge = l2_edges[0]
        self.assertEqual(edge.relationship_class, "layer2")
        self.assertEqual(edge.source_interface, "ether1")
        self.assertEqual(edge.target_interface, "ether2")
        self.assertEqual(edge.confidence_tier, "HIGH")
        self.assertAlmostEqual(edge.confidence_score, 0.80, places=2)
        self.assertIn("Single-sided", edge.confidence_rationale)

        # Inspect evidence record
        evidence = self.engine.get_edge_evidence(edge.id)
        self.assertGreaterEqual(len(evidence), 1)
        self.assertIn("SW-Dist-1", evidence[0].raw_excerpt)

    # -------------------------------------------------------------------------
    # Test 6: Bidirectional Corroboration Upgrades to Physical
    # -------------------------------------------------------------------------
    def test_06_bidirectional_corroboration_upgrades_to_physical(self):
        """When peer device reports reverse observation on physical ports, edge upgrades to CONFIRMED physical."""
        self._insert_test_node("node_r1", "Router-A", "10.0.0.1")
        self._insert_test_node("node_r2", "Router-B", "10.0.0.2")

        # Step 1: Router A sees Router B (ether1 <-> ether2)
        edge_id = self.engine._reconcile_discovered_edge(
            source_id="node_r1",
            target_id="node_r2",
            relationship_class="layer2",
            source_interface="ether1",
            target_interface="ether2",
            relationship_subtype="direct_copper",
            direction="bidirectional",
            confidence_tier="HIGH",
            confidence_score=0.80,
            confidence_rationale="Single-sided observation from Router-A.",
            now=1000.0,
        )
        edge_before = self.engine.get_edge(edge_id)
        self.assertEqual(edge_before.relationship_class, "layer2")
        self.assertEqual(edge_before.confidence_tier, "HIGH")

        # Step 2: Router B sees Router A (ether2 <-> ether1)
        upgraded_id = self.engine._reconcile_discovered_edge(
            source_id="node_r2",
            target_id="node_r1",
            relationship_class="layer2",
            source_interface="ether2",
            target_interface="ether1",
            relationship_subtype="direct_copper",
            direction="bidirectional",
            confidence_tier="HIGH",
            confidence_score=0.80,
            confidence_rationale="Single-sided observation from Router-B.",
            now=1005.0,
        )
        self.assertEqual(edge_id, upgraded_id, "Must match existing edge instead of duplicating!")

        edge_after = self.engine.get_edge(edge_id)
        self.assertEqual(edge_after.relationship_class, "physical")
        self.assertEqual(edge_after.relationship_subtype, "direct_copper")
        self.assertEqual(edge_after.verification_status, "confirmed")
        self.assertEqual(edge_after.confidence_tier, "CONFIRMED")
        self.assertEqual(edge_after.confidence_score, 1.0)
        self.assertEqual(edge_after.last_verified, 1005.0)
        self.assertIn("Verified physical adjacency", edge_after.confidence_rationale)

    # -------------------------------------------------------------------------
    # Test 7: Multi-Edge Parallel Links Between Same Nodes
    # -------------------------------------------------------------------------
    def test_07_multi_edge_parallel_links_between_same_nodes(self):
        """Parallel physical, L3 routed, and logical overlay edges co-exist between identical nodes."""
        self._insert_test_node("node_branch", "Branch-Router", "10.10.10.1")
        self._insert_test_node("node_hq", "HQ-Router", "10.10.10.2")

        # 1. Physical Edge
        e1 = self.engine._reconcile_discovered_edge(
            source_id="node_branch",
            target_id="node_hq",
            relationship_class="physical",
            source_interface="ether1",
            target_interface="ether1",
            relationship_subtype="direct_copper",
            confidence_tier="CONFIRMED",
            confidence_score=1.0,
            confidence_rationale="Mutual physical LLDP.",
        )

        # 2. Layer 3 Point-to-Point Routed Edge
        e2 = self.engine._reconcile_discovered_edge(
            source_id="node_branch",
            target_id="node_hq",
            relationship_class="layer3",
            relationship_subtype="routed_point_to_point",
            confidence_tier="HIGH",
            confidence_score=0.75,
            confidence_rationale="Point-to-point /30 subnet.",
        )

        # 3. Logical Overlay Tunnel Edge (WireGuard)
        e3 = self.engine._reconcile_discovered_edge(
            source_id="node_branch",
            target_id="node_hq",
            relationship_class="logical",
            source_interface="wg0",
            target_interface="wg0",
            relationship_subtype="overlay_tunnel",
            confidence_tier="HIGH",
            confidence_score=0.85,
            confidence_rationale="WireGuard encrypted overlay tunnel.",
        )

        # Assert all 3 are distinct IDs
        self.assertEqual(len({e1, e2, e3}), 3)

        # Assert all 3 exist concurrently in database
        edges = self.engine.list_edges(source_node_id="node_branch", target_node_id="node_hq")
        self.assertEqual(len(edges), 3)

        classes = {e.relationship_class for e in edges}
        self.assertEqual(classes, {"physical", "layer3", "logical"})

    # -------------------------------------------------------------------------
    # Test 8: Upstream Default Gateway Transit Isolation
    # -------------------------------------------------------------------------
    def test_08_default_route_gateway_isolation(self):
        """Default route 0.0.0.0/0 creates a Layer 3 default_gateway_transit edge, strictly NOT physical."""
        self._insert_test_node("node_gw_test", "Gateway-Router", "10.66.38.30")

        routes_out = "0  s  dst-address=0.0.0.0/0 gateway=10.66.38.1 gateway-status=10.66.38.1 reachable via ether1"
        iface_out = "0 R ether1 type=ether mtu=1500 mac-address=50:00:00:01:00:01"

        res = self.engine.discover_from_device_output(
            source_name="Gateway-Router",
            source_ip="10.66.38.30",
            identity_output='name: "Gateway-Router"',
            resource_output="cpu-load: 4%\nversion: 7.16",
            neighbor_output="",
            interface_output=iface_out,
            route_output=routes_out,
        )
        self.assertTrue(res["success"])

        edges = self.engine.list_edges()
        gw_edges = [e for e in edges if e.relationship_subtype == "default_gateway_transit"]
        self.assertEqual(len(gw_edges), 1)

        edge = gw_edges[0]
        self.assertEqual(edge.relationship_class, "layer3")
        self.assertEqual(edge.source_interface, "ether1")
        self.assertEqual(edge.target_interface, "")
        self.assertEqual(edge.direction, "directed")
        self.assertIn("0.0.0.0/0", edge.confidence_rationale)

    # -------------------------------------------------------------------------
    # Test 9: Boundary Interface & ISP Scope Protection
    # -------------------------------------------------------------------------
    def test_09_boundary_interface_and_isp_scope_protection(self):
        """ISP boundary policy classifies upstream node as isp_upstream and blocks recursive expansion."""
        self._insert_test_node("node_border", "Border-Router", "10.0.0.1")

        policy = {
            "isp_boundary_interfaces": ["ether1"],
            "discovery_mode": "authorized_expansion",
            "allow_routed_expansion": True,
            "require_review_for_unknown_devices": True,
        }

        neighbor_out = (
            "0 interface=ether1 mac-address=00:90:1A:11:22:33 identity=ISP-Core-Gateway "
            "address=203.0.113.1 platform=Cisco interface-name=GigabitEthernet0/0"
        )
        iface_out = "0 R ether1 type=ether mtu=1500 mac-address=00:AA:BB:CC:DD:01"

        res = self.engine.discover_from_device_output(
            source_name="Border-Router",
            source_ip="10.0.0.1",
            identity_output='name: "Border-Router"',
            resource_output="cpu-load: 10%\nversion: 7.16",
            neighbor_output=neighbor_out,
            interface_output=iface_out,
            policy=policy,
        )
        self.assertTrue(res["success"])

        # Upstream ISP node must be classified as isp_upstream
        with self.engine._lock, closing(self.engine._get_connection()) as conn:
            isp_node = conn.execute("SELECT * FROM topology_nodes WHERE ip = '203.0.113.1'").fetchone()
            self.assertIsNotNone(isp_node)
            self.assertEqual(isp_node["topology_scope"], "isp_upstream")
            self.assertEqual(isp_node["trust_zone"], "isp")
            self.assertEqual(isp_node["ownership_status"], "unknown")

        # Crucial check: downstream expansion must NOT include the ISP node
        candidates = res.get("downstream_candidates", [])
        self.assertEqual(len(candidates), 0, "ISP upstream node must never be queued for recursive interrogation!")

    # -------------------------------------------------------------------------
    # Test 10: CrossDeviceEvidenceCorrelator Integration
    # -------------------------------------------------------------------------
    def test_10_cross_device_evidence_correlator_integration(self):
        """CrossDeviceEvidenceCorrelator processes multi-device bundles and reconciles into topology_edges."""
        self._insert_test_node("R1", "Router 1", "10.0.0.1")
        self._insert_test_node("R2", "Router 2", "10.0.0.2")

        bundle_r1 = {
            "target": "R1",
            "evidence_items": [
                EvidenceItem(
                    evidence_id="ev_r1_ip",
                    device_identity="R1",
                    observation_type="ip_addresses",
                    source_command="/ip address print detail",
                    collection_timestamp=100.0,
                    normalized_value={"addresses": [{"address": "10.0.0.1/30", "interface": "ether2"}]},
                ),
                EvidenceItem(
                    evidence_id="ev_r1_if",
                    device_identity="R1",
                    observation_type="interfaces",
                    source_command="/interface print detail",
                    collection_timestamp=100.0,
                    normalized_value={"interfaces": [{"name": "ether2", "mac_address": "00:11:22:33:44:01", "running": True}]},
                ),
                EvidenceItem(
                    evidence_id="ev_r1_arp",
                    device_identity="R1",
                    observation_type="arp",
                    source_command="/ip arp print detail",
                    collection_timestamp=100.0,
                    normalized_value={"entries": [{"address": "10.0.0.2", "mac_address": "00:11:22:33:44:02", "interface": "ether2"}]},
                ),
                EvidenceItem(
                    evidence_id="ev_r1_neigh",
                    device_identity="R1",
                    observation_type="neighbors",
                    source_command="/ip neighbor print detail",
                    collection_timestamp=100.0,
                    normalized_value={"neighbors": [{"interface": "ether2", "interface-name": "ether1", "identity": "R2", "mac-address": "00:11:22:33:44:02"}]},
                ),
            ],
        }

        bundle_r2 = {
            "target": "R2",
            "evidence_items": [
                EvidenceItem(
                    evidence_id="ev_r2_ip",
                    device_identity="R2",
                    observation_type="ip_addresses",
                    source_command="/ip address print detail",
                    collection_timestamp=100.0,
                    normalized_value={"addresses": [{"address": "10.0.0.2/30", "interface": "ether1"}]},
                ),
                EvidenceItem(
                    evidence_id="ev_r2_if",
                    device_identity="R2",
                    observation_type="interfaces",
                    source_command="/interface print detail",
                    collection_timestamp=100.0,
                    normalized_value={"interfaces": [{"name": "ether1", "mac_address": "00:11:22:33:44:02", "running": True}]},
                ),
                EvidenceItem(
                    evidence_id="ev_r2_neigh",
                    device_identity="R2",
                    observation_type="neighbors",
                    source_command="/ip neighbor print detail",
                    collection_timestamp=100.0,
                    normalized_value={"neighbors": [{"interface": "ether1", "interface-name": "ether2", "identity": "R1", "mac-address": "00:11:22:33:44:01"}]},
                ),
            ],
        }

        reconciled = self.engine.correlate_and_reconcile_device_bundles({"R1": bundle_r1, "R2": bundle_r2})
        self.assertGreaterEqual(len(reconciled), 1)

        edges = self.engine.list_edges(source_node_id="R1", target_node_id="R2")
        self.assertGreaterEqual(len(edges), 1)

        # Bidirectional neighbor correlation must yield CONFIRMED physical edge
        phys_edges = [e for e in edges if e.relationship_class == "physical"]
        self.assertEqual(len(phys_edges), 1)
        self.assertEqual(phys_edges[0].confidence_tier, "CONFIRMED")
        self.assertEqual(phys_edges[0].confidence_score, 1.0)

    # -------------------------------------------------------------------------
    # Test 11: EdgeEvidence Sanitization & Cascade Delete
    # -------------------------------------------------------------------------
    def test_11_edge_evidence_sanitization_and_cascade_delete(self):
        """EdgeEvidence redacts sensitive credentials and cascades cleanly on edge deletion."""
        self._insert_test_node("node_s1", "Sec-1", "10.0.0.1")
        self._insert_test_node("node_s2", "Sec-2", "10.0.0.2")

        sensitive_cli = 'interface=ether1 identity="R2" password="SuperSecretPassword123" wpa2-pre-shared-key="MyWifiPSK"'

        edge_id = self.engine._reconcile_discovered_edge(
            source_id="node_s1",
            target_id="node_s2",
            relationship_class="layer2",
            source_interface="ether1",
            target_interface="ether1",
            confidence_tier="HIGH",
            confidence_score=0.80,
            confidence_rationale="Security test edge",
            evidence_item={
                "evidence_type": "lldp_neighbor",
                "protocol": "lldp",
                "raw_excerpt": sensitive_cli,
            },
        )

        ev_list = self.engine.get_edge_evidence(edge_id)
        self.assertEqual(len(ev_list), 1)
        self.assertNotIn("SuperSecretPassword123", ev_list[0].raw_excerpt)
        self.assertIn("REDACTED", ev_list[0].raw_excerpt)

        # Cascade delete test
        del_ok = self.engine.delete_edge(edge_id, soft_delete=False)
        self.assertTrue(del_ok)
        self.assertIsNone(self.engine.get_edge(edge_id))

        # Assert evidence records were deleted by CASCADE
        ev_after = self.engine.get_edge_evidence(edge_id, active_only=False)
        self.assertEqual(len(ev_after), 0)

    # -------------------------------------------------------------------------
    # Test 12: Authentic RouterOS v7 CHR Discovery End-to-End & Idempotency
    # -------------------------------------------------------------------------
    def test_12_mocked_chr_routeros_v7_end_to_end(self):
        """Interrogates authentic RouterOS v7 CHR outputs and verifies idempotent edge generation."""
        # Realistic MikroTik CHR v7 telemetry dump
        identity_out = 'name: "MikroTik-CHR"'
        resource_out = (
            "uptime: 2d14h22m\nversion: 7.16 (stable)\nboard-name: CHR\n"
            "architecture-name: x86_64\ncpu-load: 3%\nfree-memory: 982.4MiB"
        )
        routerboard_out = "routerboard: no"
        iface_out = (
            "Flags: D - DYNAMIC; R - RUNNING; S - SLAVE\n"
            "0  R  name=\"ether1\" type=\"ether\" mtu=1500 mac-address=\"50:00:00:01:00:01\"\n"
            "1  R  name=\"ether2\" type=\"ether\" mtu=1500 mac-address=\"50:00:00:01:00:02\""
        )
        ip_addr_out = (
            "Flags: D - DYNAMIC\n"
            "0   address=10.66.38.30/24 network=10.66.38.0 interface=ether1\n"
            "1   address=192.168.100.1/24 network=192.168.100.0 interface=ether2"
        )
        route_out = (
            "Flags: D - DYNAMIC; A - ACTIVE; c - CONNECT, s - STATIC\n"
            "0  As   dst-address=0.0.0.0/0 gateway=10.66.38.1 immediate-gw=10.66.38.1%ether1 distance=1\n"
            "1  DAc  dst-address=10.66.38.0/24 gateway=ether1 immediate-gw=ether1 distance=0\n"
            "2  DAc  dst-address=192.168.100.0/24 gateway=ether2 immediate-gw=ether2 distance=0"
        )
        neighbor_out = (
            "0 interface=ether2 mac-address=\"48:8F:5A:11:22:33\" identity=\"SW-CRS326\" "
            "platform=\"MikroTik\" version=\"7.16\" interface-name=\"sfp-sfpplus1\""
        )
        arp_out = (
            "Flags: D - DYNAMIC\n"
            "0  D address=10.66.38.1 mac-address=50:00:00:00:00:01 interface=ether1\n"
            "1  D address=192.168.100.25 mac-address=00:E0:4C:68:01:02 interface=ether2"
        )

        # Run 1: Initial Discovery
        res1 = self.engine.discover_from_device_output(
            source_name="MikroTik-CHR",
            source_ip="10.66.38.30",
            identity_output=identity_out,
            resource_output=resource_out,
            neighbor_output=neighbor_out,
            interface_output=iface_out,
            route_output=route_out,
            routerboard_output=routerboard_out,
            ip_address_output=ip_addr_out,
            arp_output=arp_out,
        )
        self.assertTrue(res1["success"])
        edges_first = self.engine.list_edges()
        self.assertGreaterEqual(len(edges_first), 2)

        # Run 2: Idempotent Discovery (must not duplicate nodes or edges)
        res2 = self.engine.discover_from_device_output(
            source_name="MikroTik-CHR",
            source_ip="10.66.38.30",
            identity_output=identity_out,
            resource_output=resource_out,
            neighbor_output=neighbor_out,
            interface_output=iface_out,
            route_output=route_out,
            routerboard_output=routerboard_out,
            ip_address_output=ip_addr_out,
            arp_output=arp_out,
        )
        self.assertTrue(res2["success"])
        edges_second = self.engine.list_edges()
        self.assertEqual(
            len(edges_first),
            len(edges_second),
            "Repeated discovery must be completely idempotent and produce zero duplicate edges!",
        )


if __name__ == "__main__":
    unittest.main()
