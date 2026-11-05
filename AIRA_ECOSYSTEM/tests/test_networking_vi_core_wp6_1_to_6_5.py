"""
AIRA OS — Gate Verification Suite for Networking VI Core (WP 6.1 – WP 6.5).

Covers:
- WP 6.1: UnifiedEvidenceService, type-aware freshness, None-vs-zero integrity,
          SQLite NMS/Topology cache reuse without duplicate SSH, contradictions & gaps.
- WP 6.2: EntityResolver conservative merge guards, NetworkKnowledgeGraph (21 entity types,
          18 relationship types, layer separation, consistency validation, snapshot diff),
          and all 10 bounded GraphQueryEngine queries.
- WP 6.3: NetworkPathIntelligenceEngine (5 epistemic modes, LPM, AD, ECMP, recursive gateway,
          blackhole, inactive routes, loop detection, egress down, VRF, asymmetric return,
          IPv6 explicit support/limitation, and compare_paths).
- WP 6.4: MultiDeviceCorrelationEngine (Scenarios A–E + temporal-coincidence non-causal guard).
- WP 6.5: ConfidenceScorer (8 factors, is_calibrated_probability=False) &
          RootCauseAnalysisEngine (14-step pipeline, root cause vs secondary symptom,
          contradictory/missing evidence handling, review-only remediation).
"""

from __future__ import annotations

from pathlib import Path
import sqlite3
import time
from unittest.mock import MagicMock

import pytest

from core.canonical_network import CanonicalDevice
from core.network_intelligence.confidence_model import ConfidenceScorer
from core.network_intelligence.correlation_engine import MultiDeviceCorrelationEngine
from core.network_intelligence.entity_resolver import EntityResolver
from core.network_intelligence.evidence_service import (
    UnifiedEvidenceService,
    evaluate_evidence_freshness,
)
from core.network_intelligence.graph_queries import GraphQueryEngine
from core.network_intelligence.intelligence_models import (
    ConfidenceLabel,
    EvidenceQuality,
    FindingClassification,
    GraphEntityType,
    GraphLayer,
    GraphRelationshipType,
    HypothesisCategory,
    IntelligenceFreshness,
    KnowledgeEdge,
    KnowledgeNode,
    PathReasoningMode,
)
from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph
from core.network_intelligence.path_intelligence import NetworkPathIntelligenceEngine
from core.network_intelligence.rca_engine import PIPELINE_STEPS_14, RootCauseAnalysisEngine


# ===========================================================================
# WP 6.1 — UNIFIED EVIDENCE SERVICE & TYPE-AWARE FRESHNESS
# ===========================================================================

class TestWP61UnifiedEvidenceService:
    def test_type_aware_freshness_profiles_and_missing_timestamp(self) -> None:
        now = 1_700_000_000.0
        # Missing or zero timestamp is NEVER FRESH
        assert evaluate_evidence_freshness("cpu", None, now) == IntelligenceFreshness.UNKNOWN.value
        assert evaluate_evidence_freshness("cpu", 0.0, now) == IntelligenceFreshness.UNKNOWN.value
        assert evaluate_evidence_freshness("cpu", -5.0, now) == IntelligenceFreshness.UNKNOWN.value

        # Fast resource metric (cpu: 45 / 120 / 300) vs semi-static config (ip_addresses: 300 / 1800 / 7200)
        assert evaluate_evidence_freshness("cpu", now - 30, now) == IntelligenceFreshness.FRESH.value
        assert evaluate_evidence_freshness("cpu", now - 90, now) == IntelligenceFreshness.AGING.value
        assert evaluate_evidence_freshness("cpu", now - 200, now) == IntelligenceFreshness.STALE.value
        assert evaluate_evidence_freshness("cpu", now - 400, now) == IntelligenceFreshness.EXPIRED.value

        # At 200s age, ip_addresses is still FRESH!
        assert evaluate_evidence_freshness("ip_addresses", now - 200, now) == IntelligenceFreshness.FRESH.value
        assert evaluate_evidence_freshness("ip_addresses", now - 900, now) == IntelligenceFreshness.AGING.value

    def test_preserves_none_for_missing_metrics_and_indexes_evidence_ids(self) -> None:
        now = 1_700_000_000.0
        svc = UnifiedEvidenceService()
        bundle = svc.assemble_evidence_bundle(
            scope="unit_test",
            synthetic_data={
                "devices": {
                    "R1": {
                        "display_name": "R1-Core",
                        "management_ip": "10.0.0.1",
                        "cpu_load_percent": None,  # Missing CPU must stay None, NOT 0.0
                        "latency_ms": None,
                        "observed_at": now - 10,
                        "interfaces": [
                            {
                                "interface_name": "ether1",
                                "oper_status": "up",
                                "rx_rate_bps": None,  # First-sample rate unestablished -> None
                                "tx_rate_bps": None,
                            }
                        ],
                    }
                }
            },
            now=now,
        )

        assert bundle.device_evidence["R1"]["cpu_load_percent"] is None
        assert bundle.device_evidence["R1"]["latency_ms"] is None
        assert bundle.interface_evidence["R1"][0]["rx_rate_bps"] is None
        assert bundle.interface_evidence["R1"][0]["tx_rate_bps"] is None

        assert len(bundle.records) >= 2
        ev0 = bundle.records[0]
        looked_up = svc.get_evidence_by_id(ev0.evidence_id, now=now)
        assert looked_up is not None
        assert looked_up.evidence_id == ev0.evidence_id
        assert looked_up.freshness == IntelligenceFreshness.FRESH.value

    def test_reuses_sqlite_nms_and_topology_without_ssh_polling(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test_topology.db"
        now = time.time()

        with sqlite3.connect(db_file) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS topology_nodes (
                    id TEXT PRIMARY KEY, name TEXT, ip TEXT, mac TEXT,
                    identity TEXT, device_type TEXT, status TEXT, ownership_status TEXT
                )
                """
            )
            conn.execute(
                "INSERT INTO topology_nodes (id, name, ip, mac, identity, device_type, status, ownership_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("Core-1", "Core-1", "10.10.0.1", "AA:BB:CC:00:00:01", "Core-1", "router", "online", "verified_owned"),
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS nms_device_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT, timestamp REAL, reachability_status TEXT,
                    latency_ms REAL, packet_loss_percent REAL, cpu_load_percent REAL,
                    memory_used_percent REAL, uptime_seconds INTEGER
                )
                """
            )
            conn.execute(
                "INSERT INTO nms_device_metrics (device_id, timestamp, reachability_status, latency_ms, packet_loss_percent, cpu_load_percent, memory_used_percent, uptime_seconds) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("Core-1", now - 5.0, "UP", 1.8, 0.0, 14.0, 32.0, 86400),
            )
            conn.commit()

        mock_reg = MagicMock()
        mock_reg.list_devices.return_value = []
        mock_reg.resolve_device.return_value = None
        mock_ssh = MagicMock()

        svc = UnifiedEvidenceService(
            topology_db_path=db_file,
            registry=mock_reg,
            ssh_orchestrator=mock_ssh,
        )
        bundle = svc.assemble_evidence_bundle(
            target_devices=["Core-1"],
            allow_live_collection=False,
            now=now,
        )

        mock_ssh.collect_multi_device_bundle.assert_not_called()
        assert "Core-1" in bundle.device_evidence
        assert bundle.device_evidence["Core-1"]["cpu_load_percent"] == 14.0
        assert bundle.reused_cached_count >= 1
        assert bundle.live_collected_count == 0

    def test_detects_duplicate_ip_and_management_contradictions(self) -> None:
        now = 1_700_000_000.0
        svc = UnifiedEvidenceService()
        bundle = svc.assemble_evidence_bundle(
            synthetic_data={
                "devices": {
                    "Branch-A": {
                        "management_ip": "192.168.88.1",
                        "reachability_status": "MONITORING_UNAVAILABLE",
                        "observed_at": now,
                    },
                    "Branch-B": {
                        "management_ip": "192.168.88.1",
                        "reachability_status": "UP",
                        "observed_at": now,
                    },
                },
                "topology_edges": [
                    {
                        "source_node_id": "Branch-A",
                        "source_interface": "ether1",
                        "target_node_id": "Branch-B",
                        "target_interface": "ether1",
                        "lifecycle_state": "ACTIVE",
                        "observed_at": now,
                    }
                ],
            },
            now=now,
        )
        contra_types = {c.contradiction_type for c in bundle.contradictions}
        assert "DUPLICATE_IP_OBSERVED" in contra_types
        assert "REACHABLE_BUT_MANAGEMENT_FAILED" in contra_types


# ===========================================================================
# WP 6.2 — ENTITY RESOLVER, KNOWLEDGE GRAPH & BOUNDED QUERIES
# ===========================================================================

class TestWP62KnowledgeGraphAndQueries:
    def test_entity_resolver_refuses_false_merge_on_ip_or_hostname_alone(self) -> None:
        # Shared default IP 192.168.88.1 -> MUST NOT merge
        ev_ip = EntityResolver.evaluate_device_merge_candidate(
            {"management_ip": "192.168.88.1", "identity": "Branch1"},
            {"management_ip": "192.168.88.1", "identity": "Branch2"},
        )
        assert ev_ip.should_merge is False
        assert ev_ip.conflict_detected is True

        # Shared default identity "MikroTik" -> MUST NOT merge
        ev_name = EntityResolver.evaluate_device_merge_candidate(
            {"management_ip": "10.0.1.1", "identity": "MikroTik"},
            {"management_ip": "10.0.2.1", "identity": "MikroTik"},
        )
        assert ev_name.should_merge is False

        # Distinct managed inventory IDs -> MUST NOT merge even if MAC matches
        ev_distinct = EntityResolver.evaluate_device_merge_candidate(
            {"device_id": "R1", "is_managed": True, "mac_address": "AA:BB:CC:11:22:33"},
            {"device_id": "R2", "is_managed": True, "mac_address": "AA:BB:CC:11:22:33"},
        )
        assert ev_distinct.should_merge is False

        # Authoritative inventory ID match -> Merge
        ev_same = EntityResolver.evaluate_device_merge_candidate(
            {"device_id": "R1", "is_managed": True},
            {"device_id": "R1", "is_managed": True},
        )
        assert ev_same.should_merge is True

    def test_knowledge_graph_all_layers_epistemic_separation_and_queries(self) -> None:
        now = 1_700_000_000.0
        svc = UnifiedEvidenceService()
        bundle = svc.assemble_evidence_bundle(
            synthetic_data={
                "route_snapshot_refs": {"Core": "rsnap_core_01"},
                "devices": {
                    "ISP-Edge": {
                        "display_name": "ISP-Edge",
                        "management_ip": "10.0.0.1",
                        "mac_address": "AA:BB:CC:00:01:01",
                        "cpu_load_percent": 18.0,
                        "latency_ms": 4.0,
                        "observed_at": now,
                        "interfaces": [
                            {"interface_name": "ether1-wan", "oper_status": "up"},
                            {"interface_name": "ether2-core", "oper_status": "up"},
                            {"interface_name": "gre-branch", "interface_type": "gre-tunnel", "oper_status": "up"},
                        ],
                        "ip_addresses": [
                            {"address": "203.0.113.2/30", "interface": "ether1-wan"},
                            {"address": "10.0.12.1/30", "interface": "ether2-core"},
                        ],
                        "routes": [
                            {"dst_prefix": "0.0.0.0/0", "gateway": "203.0.113.1", "interface_name": "ether1-wan", "protocol": "bgp", "distance": 20, "active": True},
                            {"dst_prefix": "10.20.0.0/24", "gateway": "10.0.12.2", "interface_name": "ether2-core", "protocol": "ospf", "distance": 110, "active": True},
                        ],
                        "ospf_instance": [{"name": "ospf-v2", "router_id": "10.0.0.1"}],
                        "ospf_neighbors": [{"neighbor_id": "10.0.0.2", "address": "10.0.12.2", "state": "Full", "area": "0.0.0.0"}],
                        "bgp_peers": [{"name": "isp-upstream", "remote_address": "203.0.113.1", "remote_as": 65001, "state": "established"}],
                        "dns": {"servers": ["1.1.1.1"]},
                    },
                    "Core": {
                        "display_name": "Core",
                        "management_ip": "10.0.0.2",
                        "mac_address": "AA:BB:CC:00:02:01",
                        "cpu_load_percent": 22.0,
                        "observed_at": now,
                        "interfaces": [
                            {"interface_name": "ether1-edge", "oper_status": "up"},
                            {"interface_name": "bridge-lan", "interface_type": "bridge", "oper_status": "up"},
                            {"interface_name": "ether3-sw", "oper_status": "up"},
                        ],
                        "bridge": [{"name": "bridge-lan", "vlan_filtering": True}],
                        "bridge_ports": [{"interface": "ether3-sw", "bridge": "bridge-lan", "pvid": 1}],
                        "bridge_vlan": [{"bridge": "bridge-lan", "vlan_ids": [20], "tagged": ["ether3-sw"]}],
                        "ip_addresses": [
                            {"address": "10.0.12.2/30", "interface": "ether1-edge"},
                            {"address": "10.20.0.1/24", "interface": "bridge-lan"},
                            {"address": "192.168.50.1/24", "interface": "ether3-sw"},
                        ],
                        "arp": [
                            {"address": "192.168.50.2", "mac_address": "AA:BB:CC:00:03:01", "interface": "ether3-sw"}
                        ],
                        "routes": [
                            {"dst_prefix": "0.0.0.0/0", "gateway": "10.0.12.1", "interface_name": "ether1-edge", "protocol": "ospf", "distance": 110, "active": True},
                            {"dst_prefix": "10.99.0.0/24", "gateway": "10.0.12.1", "routing_table": "vrf-guest", "protocol": "static", "distance": 1, "active": True},
                        ],
                        "ospf_instance": [{"name": "ospf-v2", "router_id": "10.0.0.2"}],
                        "ospf_neighbors": [{"neighbor_id": "10.0.0.1", "address": "10.0.12.1", "state": "Full", "area": "0.0.0.0"}],
                    },
                    "SharedSubnetPeer": {
                        "display_name": "SharedSubnetPeer",
                        "management_ip": "192.168.50.2",
                        "mac_address": "AA:BB:CC:00:03:01",
                        "is_managed": False,
                        "observed_at": now,
                        "ip_addresses": [
                            {"address": "192.168.50.2/24", "interface": "ether1"},
                        ],
                    },
                },
                "topology_edges": [
                    {
                        "source_node_id": "ISP-Edge",
                        "source_interface": "ether2-core",
                        "target_node_id": "Core",
                        "target_interface": "ether1-edge",
                        "layer": "physical",
                        "relationship_type": "PHYSICAL_ADJACENCY",
                        "confidence": 0.96,
                        "observed_at": now,
                    }
                ],
                "incidents": [
                    {
                        "id": "inc_01",
                        "device_id": "ISP-Edge",
                        "severity": "warning",
                        "status": "open",
                        "title": "WAN jitter notice",
                        "started_at": now - 30,
                    }
                ],
            },
            now=now,
        )

        graph = NetworkKnowledgeGraph.from_evidence_bundle(bundle, now=now)

        # Verify all 21 entity types exist in enum and rich subset instantiated
        assert len(GraphEntityType) == 21
        assert len(GraphRelationshipType) == 18
        present_types = {n.entity_type for n in graph.nodes.values()}
        for expected_et in (
            GraphEntityType.DEVICE.value,
            GraphEntityType.INTERFACE.value,
            GraphEntityType.IP_ADDRESS.value,
            GraphEntityType.SUBNET.value,
            GraphEntityType.VLAN.value,
            GraphEntityType.BRIDGE.value,
            GraphEntityType.VRF.value,
            GraphEntityType.ROUTING_TABLE.value,
            GraphEntityType.ROUTE.value,
            GraphEntityType.NEXT_HOP.value,
            GraphEntityType.GATEWAY.value,
            GraphEntityType.ROUTING_PROTOCOL_INSTANCE.value,
            GraphEntityType.OSPF_NEIGHBOR.value,
            GraphEntityType.BGP_PEER.value,
            GraphEntityType.TUNNEL.value,
            GraphEntityType.WAN_CONNECTION.value,
            GraphEntityType.SERVICE_ENDPOINT.value,
            GraphEntityType.NETWORK_SEGMENT.value,
            GraphEntityType.INCIDENT.value,
            GraphEntityType.TELEMETRY_OBSERVATION.value,
            GraphEntityType.CONFIGURATION_SNAPSHOT.value,
        ):
            assert expected_et in present_types, f"Missing entity type {expected_et}"

        # Epistemic rule: SharedSubnetPeer shares 192.168.50.0/24 and ARP with Core,
        # so it may have LAYER2_ADJACENCY, NEVER PHYSICAL_ADJACENCY!
        phys_pairs = {
            (e.source_id, e.target_id)
            for e in graph.edges_by_type(GraphRelationshipType.PHYSICAL_ADJACENCY.value)
        }
        assert ("device:Core", "device:SharedSubnetPeer") not in phys_pairs
        assert ("device:SharedSubnetPeer", "device:Core") not in phys_pairs

        l2_edges = [
            e for e in graph.edges_by_type(GraphRelationshipType.LAYER2_ADJACENCY.value)
            if "SharedSubnetPeer" in (e.source_id + e.target_id)
        ]
        assert len(l2_edges) >= 1

        # Consistency validation tolerant of partial network (SharedSubnetPeer unmanaged)
        consistency = graph.validate_consistency(bundle=bundle, now=now)
        assert consistency.is_consistent is True
        assert consistency.is_partial_network is True

        # Execute all 10 bounded GraphQueryEngine queries
        q = GraphQueryEngine(graph)
        conn_res = q.get_connected_devices("Core")
        conn_ids = {d["device_id"] for d in conn_res["connected_devices"]}
        assert "ISP-Edge" in conn_ids
        assert "SharedSubnetPeer" in conn_ids

        down_res = q.get_downstream_dependencies("ISP-Edge")
        assert any(d["device_id"] == "Core" for d in down_res["direct_dependents"])
        assert q.get_dependent_devices("ISP-Edge")["all_dependents"] == down_res["all_dependents"]

        up_res = q.get_upstream_dependencies("Core")
        assert any(u["device_id"] == "ISP-Edge" for u in up_res["upstreams"])

        seg_res = q.get_reachable_segments("Core")
        assert any(s["segment"] == "10.20.0.0/24" for s in seg_res["segments"])

        nh_res = q.get_routes_using_next_hop("10.0.12.1", device_id="Core")
        assert len(nh_res["routes"]) >= 1

        vlan_res = q.get_interfaces_carrying_vlan(20, device_id="Core")
        assert any(i["interface_name"] == "ether3-sw" for i in vlan_res["interfaces"])

        proto_res = q.get_protocol_participants("ospf")
        assert {p["device_id"] for p in proto_res["participants"]} == {"ISP-Edge", "Core"}

        svc_res = q.get_affected_services("ISP-Edge")
        assert len(svc_res["services"]) >= 1

        alt_res = q.find_alternate_paths("Core", "ISP-Edge")
        assert len(alt_res["paths"]) >= 1

    def test_snapshot_projection_and_graph_diff_non_destructive(self) -> None:
        t1 = 1_700_000_000.0
        t2 = t1 + 300.0
        g_before = NetworkKnowledgeGraph.from_historical_snapshot_dicts(
            snapshot_id="snap_1",
            snapshot_ts=t1,
            topology_nodes=[
                {"id": "R1", "name": "R1", "ip": "10.0.0.1", "status": "UP"},
                {"id": "R2", "name": "R2", "ip": "10.0.0.2", "status": "UP"},
            ],
            topology_edges=[
                {"source_node_id": "R1", "target_node_id": "R2", "layer": "physical", "relationship_type": "PHYSICAL_ADJACENCY"}
            ],
        )
        g_after = NetworkKnowledgeGraph.from_historical_snapshot_dicts(
            snapshot_id="snap_2",
            snapshot_ts=t2,
            topology_nodes=[
                {"id": "R1", "name": "R1", "ip": "10.0.0.1", "status": "UP"},
                {"id": "R2", "name": "R2", "ip": "10.0.0.2", "status": "DOWN"},
            ],
            topology_edges=[],
        )
        diff = NetworkKnowledgeGraph.compare_graphs(g_before, g_after)
        assert "R2" in diff["devices_became_unreachable"]
        assert diff["summary"]["disappeared_count"] >= 1


# ===========================================================================
# WP 6.3 — NETWORK PATH INTELLIGENCE ENGINE
# ===========================================================================

class TestWP63PathIntelligence:
    def _build_path_fixture(self, now: float = 1_700_000_000.0):
        svc = UnifiedEvidenceService()
        bundle = svc.assemble_evidence_bundle(
            synthetic_data={
                "devices": {
                    "R1": {
                        "display_name": "R1",
                        "management_ip": "10.0.0.1",
                        "observed_at": now,
                        "interfaces": [
                            {"interface_name": "ether1-r2", "oper_status": "up"},
                            {"interface_name": "ether2-r3", "oper_status": "up"},
                            {"interface_name": "ether3-down", "oper_status": "down"},
                        ],
                        "ip_addresses": [
                            {"address": "10.1.12.1/30", "interface": "ether1-r2"},
                            {"address": "10.1.13.1/30", "interface": "ether2-r3"},
                            {"address": "10.1.99.1/30", "interface": "ether3-down"},
                        ],
                        "routes": [
                            # Connected
                            {"dst_prefix": "10.1.12.0/30", "gateway": "ether1-r2", "interface_name": "ether1-r2", "connect": True, "protocol": "connect", "distance": 0, "active": True, "selected": True},
                            {"dst_prefix": "10.1.13.0/30", "gateway": "ether2-r3", "interface_name": "ether2-r3", "connect": True, "protocol": "connect", "distance": 0, "active": True, "selected": True},
                            # Default route (/0) vs specific (/24)
                            {"dst_prefix": "0.0.0.0/0", "gateway": "203.0.113.1", "interface_name": "ether1-r2", "protocol": "static", "distance": 1, "active": True},
                            # Specific /24: OSPF distance 110 vs static backup distance 200 vs inactive distance 1
                            {"dst_prefix": "10.50.0.0/24", "gateway": "10.1.12.2", "interface_name": "ether1-r2", "protocol": "ospf", "distance": 110, "active": True, "fib": True},
                            {"dst_prefix": "10.50.0.0/24", "gateway": "10.1.13.2", "interface_name": "ether2-r3", "protocol": "static", "distance": 200, "active": True},
                            {"dst_prefix": "10.50.0.0/24", "gateway": "10.1.99.2", "interface_name": "ether3-down", "protocol": "static", "distance": 1, "active": False},
                            # Recursive route via BGP next-hop 198.51.100.1 resolved via 10.1.12.2
                            {"dst_prefix": "198.51.100.0/24", "gateway": "10.1.12.2", "interface_name": "ether1-r2", "protocol": "ospf", "distance": 110, "active": True, "scope": 20, "target_scope": 10},
                            {"dst_prefix": "172.16.80.0/24", "gateway": "198.51.100.1", "protocol": "bgp", "distance": 20, "active": True, "scope": 40, "target_scope": 30},
                            # Blackhole route
                            {"dst_prefix": "10.66.0.0/24", "route_type": "blackhole", "protocol": "static", "distance": 1, "active": True},
                            # Egress down route
                            {"dst_prefix": "10.77.0.0/24", "gateway": "10.1.99.2", "interface_name": "ether3-down", "protocol": "static", "distance": 1, "active": True},
                            # ECMP route
                            {"dst_prefix": "10.88.0.0/24", "gateway": "10.1.12.2,10.1.13.2", "gateways": ["10.1.12.2", "10.1.13.2"], "protocol": "ospf", "distance": 110, "active": True},
                            # Loop route R1 <-> R3
                            {"dst_prefix": "10.99.99.0/24", "gateway": "10.1.13.2", "interface_name": "ether2-r3", "protocol": "static", "distance": 1, "active": True},
                            # VRF isolated route
                            {"dst_prefix": "10.50.0.0/24", "gateway": "10.1.13.2", "interface_name": "ether2-r3", "routing_table": "vrf-corp", "protocol": "static", "distance": 1, "active": True},
                        ],
                        "forwarding_observations": {
                            "10.50.0.10": {"verified": True, "hops": ["10.1.12.2", "10.50.0.10"]}
                        },
                    },
                    "R2": {
                        "display_name": "R2",
                        "management_ip": "10.0.0.2",
                        "observed_at": now,
                        "interfaces": [
                            {"interface_name": "ether1-r1", "oper_status": "up"},
                            {"interface_name": "ether2-lan", "oper_status": "up"},
                            {"interface_name": "ether3-r3", "oper_status": "up"},
                        ],
                        "ip_addresses": [
                            {"address": "10.1.12.2/30", "interface": "ether1-r1"},
                            {"address": "10.50.0.1/24", "interface": "ether2-lan"},
                            {"address": "10.2.23.1/30", "interface": "ether3-r3"},
                        ],
                        "routes": [
                            {"dst_prefix": "10.50.0.0/24", "gateway": "ether2-lan", "interface_name": "ether2-lan", "connect": True, "protocol": "connect", "distance": 0, "active": True, "fib": True},
                            # Asymmetric return back to R1's 10.1.12.1 via R3!
                            {"dst_prefix": "10.1.12.0/30", "gateway": "10.2.23.2", "interface_name": "ether3-r3", "protocol": "static", "distance": 1, "active": True},
                        ],
                    },
                    "R3": {
                        "display_name": "R3",
                        "management_ip": "10.0.0.3",
                        "observed_at": now,
                        "interfaces": [{"interface_name": "ether1-r1", "oper_status": "up"}],
                        "ip_addresses": [
                            {"address": "10.1.13.2/30", "interface": "ether1-r1"},
                            {"address": "10.2.23.2/30", "interface": "ether1-r1"},
                        ],
                        "routes": [
                            # Loop back to R1
                            {"dst_prefix": "10.99.99.0/24", "gateway": "10.1.13.1", "interface_name": "ether1-r1", "protocol": "static", "distance": 1, "active": True},
                            {"dst_prefix": "10.1.12.0/30", "gateway": "10.1.13.1", "interface_name": "ether1-r1", "protocol": "static", "distance": 1, "active": True},
                        ],
                    },
                }
            },
            now=now,
        )
        graph = NetworkKnowledgeGraph.from_evidence_bundle(bundle, now=now)
        return bundle, graph

    def test_lpm_ad_inactive_rejection_fib_and_observed_forwarding(self) -> None:
        bundle, graph = self._build_path_fixture()
        engine = NetworkPathIntelligenceEngine()

        # 1. 10.50.0.25 -> FIB_CONFIRMED across R1 -> R2 (ignores inactive AD=1 and backup AD=200 and /0)
        res_fib = engine.analyze_path(bundle, graph, destination_ip="10.50.0.25", source_device_id="R1", source_ip="10.1.12.1")
        assert res_fib.outcome == "DELIVERED"
        assert res_fib.mode == PathReasoningMode.FIB_CONFIRMED.value
        assert [h.device_id for h in res_fib.hops] == ["R1", "R2"]
        assert res_fib.hops[0].next_hop_ip == "10.1.12.2"
        # Asymmetric return (R1 -> R2 forward, R2 -> R3 -> R1 return)
        assert res_fib.asymmetric_return_detected is True

        # 2. 10.50.0.10 -> OBSERVED_FORWARDING (corroborated by traceroute probe)
        res_obs = engine.analyze_path(bundle, graph, destination_ip="10.50.0.10", source_device_id="R1")
        assert res_obs.mode == PathReasoningMode.OBSERVED_FORWARDING.value
        assert res_obs.is_directly_observed is True

        # 3. Blackhole route
        res_bh = engine.analyze_path(bundle, graph, destination_ip="10.66.0.5", source_device_id="R1")
        assert res_bh.outcome == "BLACKHOLED"

        # 4. Egress interface down -> PARTIAL_PATH / EGRESS_DOWN
        res_down = engine.analyze_path(bundle, graph, destination_ip="10.77.0.5", source_device_id="R1")
        assert res_down.outcome == "EGRESS_DOWN"
        assert res_down.mode == PathReasoningMode.PARTIAL_PATH.value

        # 5. Routing loop R1 <-> R3 -> LOOP_DETECTED
        res_loop = engine.analyze_path(bundle, graph, destination_ip="10.99.99.5", source_device_id="R1")
        assert res_loop.outcome == "LOOP_DETECTED"

        # 6. Recursive route resolution on R1 (172.16.80.5 -> 198.51.100.1 -> 10.1.12.2)
        res_rec = engine.analyze_path(bundle, graph, destination_ip="172.16.80.5", source_device_id="R1")
        assert res_rec.hops[0].next_hop_ip == "10.1.12.2"
        assert len(res_rec.hops[0].recursive_chain) >= 1

        # 7. ECMP expansion
        res_ecmp = engine.analyze_path(bundle, graph, destination_ip="10.88.0.5", source_device_id="R1")
        assert len(res_ecmp.hops[0].ecmp_gateways) == 2

        # 8. VRF isolation & Path Comparator
        res_vrf = engine.analyze_path(bundle, graph, destination_ip="10.50.0.25", source_device_id="R1", vrf="vrf-corp")
        assert res_vrf.hops[0].next_hop_ip == "10.1.13.2"
        cmp = NetworkPathIntelligenceEngine.compare_paths(res_fib, res_vrf, comparison_dimension="vrf_comparison")
        assert cmp["identical_forwarding_intent"] is False
        assert cmp["difference_count"] >= 1

        # 9. IPv6 without ipv6_routes -> honest UNKNOWN_PATH
        res_v6 = engine.analyze_path(bundle, graph, destination_ip="2001:db8::1", source_device_id="R1")
        assert res_v6.mode == PathReasoningMode.UNKNOWN_PATH.value
        assert res_v6.outcome == "INSUFFICIENT_EVIDENCE"


# ===========================================================================
# WP 6.4 & WP 6.5 — CORRELATION, CONFIDENCE & 14-STEP RCA ENGINE
# ===========================================================================

class TestWP64AndWP65CorrelationAndRCA:
    def test_confidence_scorer_factors_and_epistemic_disclosure(self) -> None:
        svc = UnifiedEvidenceService()
        now = 1_700_000_000.0
        b = svc.assemble_evidence_bundle(
            synthetic_data={
                "devices": {
                    "R1": {"cpu_load_percent": 15.0, "observed_at": now, "interfaces": [{"interface_name": "ether1"}]},
                    "R2": {"cpu_load_percent": 20.0, "observed_at": now},
                }
            },
            now=now,
        )
        high_conf = ConfidenceScorer.evaluate(
            supporting_records=b.records,
            contradictory_count=0,
            missing_count=0,
            topology_consistent=True,
            protocol_consistent=True,
            historical_consistent=True,
        )
        assert high_conf.is_calibrated_probability is False
        assert high_conf.label in (ConfidenceLabel.VERY_HIGH.value, ConfidenceLabel.HIGH.value)

        penalized = ConfidenceScorer.evaluate(
            supporting_records=b.records[:1],
            contradictory_count=2,
            missing_count=3,
            topology_consistent=False,
        )
        assert penalized.score < high_conf.score
        assert penalized.label in (ConfidenceLabel.LOW.value, ConfidenceLabel.INSUFFICIENT.value)

    def test_scenario_a_shared_upstream_separates_root_cause_from_symptoms(self) -> None:
        now = 1_700_000_000.0
        svc = UnifiedEvidenceService()
        bundle = svc.assemble_evidence_bundle(
            synthetic_data={
                "devices": {
                    "Core-Up": {
                        "reachability_status": "DOWN",
                        "management_ip": "10.0.0.1",
                        "observed_at": now,
                        "ip_addresses": [{"address": "10.0.12.1/30", "interface": "ether2"}],
                    },
                    "Dist-1": {
                        "reachability_status": "DOWN",
                        "management_ip": "10.0.0.2",
                        "observed_at": now,
                        "routes": [{"dst_prefix": "0.0.0.0/0", "gateway": "10.0.12.1", "active": True}],
                    },
                    "Dist-2": {
                        "reachability_status": "DOWN",
                        "management_ip": "10.0.0.3",
                        "observed_at": now,
                        "routes": [{"dst_prefix": "0.0.0.0/0", "gateway": "10.0.12.1", "active": True}],
                    },
                },
                "incidents": [
                    {"id": "inc_core", "device_id": "Core-Up", "severity": "critical", "status": "open", "title": "Core-Up unreachable", "started_at": now - 25},
                    {"id": "inc_d1", "device_id": "Dist-1", "severity": "critical", "status": "open", "title": "Dist-1 unreachable", "started_at": now - 20},
                    {"id": "inc_d2", "device_id": "Dist-2", "severity": "critical", "status": "open", "title": "Dist-2 unreachable", "started_at": now - 19},
                ],
            },
            now=now,
        )
        graph = NetworkKnowledgeGraph.from_evidence_bundle(bundle, now=now)
        correlator = MultiDeviceCorrelationEngine()
        groups = correlator.correlate(bundle, graph)

        causal_groups = [g for g in groups if g.is_causal_candidate and g.shared_dependency == "device:Core-Up"]
        assert len(causal_groups) == 1
        assert set(causal_groups[0].related_devices) == {"Core-Up", "Dist-1", "Dist-2"}

        rca = RootCauseAnalysisEngine(correlator).analyze(bundle, graph, correlations=groups, now=now)
        assert rca.pipeline_steps_completed == PIPELINE_STEPS_14
        assert rca.most_likely_root_cause is not None
        assert rca.most_likely_root_cause.root_entity_id == "device:Core-Up"
        assert rca.most_likely_root_cause.classification == FindingClassification.ROOT_CAUSE.value

        symptom_entities = {s["entity_id"] for s in rca.secondary_symptoms}
        assert "device:Dist-1" in symptom_entities
        assert "device:Dist-2" in symptom_entities
        # Alternative explanation (telemetry/power/link) is preserved
        assert len(rca.most_likely_root_cause.alternative_explanations) >= 1
        for rem in rca.proposed_remediation_review_only:
            assert rem.get("auto_execution_allowed") is False

    def test_temporal_coincidence_guard_does_not_claim_causation(self) -> None:
        now = 1_700_000_000.0
        svc = UnifiedEvidenceService()
        bundle = svc.assemble_evidence_bundle(
            synthetic_data={
                "devices": {
                    "Isolated-Site-A": {"management_ip": "10.101.0.1", "reachability_status": "UP", "observed_at": now},
                    "Isolated-Site-B": {"management_ip": "10.202.0.1", "reachability_status": "UP", "observed_at": now},
                },
                "incidents": [
                    {"id": "inc_a", "device_id": "Isolated-Site-A", "severity": "warning", "status": "open", "title": "High CPU A", "started_at": now - 10},
                    {"id": "inc_b", "device_id": "Isolated-Site-B", "severity": "warning", "status": "open", "title": "High CPU B", "started_at": now - 9},
                ],
            },
            now=now,
        )
        graph = NetworkKnowledgeGraph.from_evidence_bundle(bundle, now=now)
        groups = MultiDeviceCorrelationEngine().correlate(bundle, graph)
        for grp in groups:
            if set(grp.related_devices) == {"Isolated-Site-A", "Isolated-Site-B"}:
                assert grp.is_causal_candidate is False

    def test_scenarios_b_c_e_routing_interface_errors_and_wan_degradation(self) -> None:
        now = 1_700_000_000.0
        svc = UnifiedEvidenceService()
        bundle = svc.assemble_evidence_bundle(
            synthetic_data={
                "devices": {
                    "Edge-1": {
                        "management_ip": "10.0.0.1",
                        "reachability_status": "UP",
                        "latency_ms": 185.0,
                        "packet_loss_percent": 12.5,
                        "observed_at": now,
                        "interfaces": [
                            {"interface_name": "ether1-wan", "oper_status": "up", "in_errors": 450, "in_drops": 120},
                        ],
                        "routes": [
                            {"dst_prefix": "0.0.0.0/0", "gateway": "203.0.113.1", "interface_name": "ether1-wan", "active": True},
                        ],
                        "bgp_peers": [
                            {"name": "ISP-BGP", "remote_address": "203.0.113.1", "remote_as": 65001, "state": "idle"},
                        ],
                    }
                }
            },
            now=now,
        )
        graph = NetworkKnowledgeGraph.from_evidence_bundle(bundle, now=now)
        rca = RootCauseAnalysisEngine().analyze(bundle, graph, now=now)
        cats = {h.category for h in rca.hypotheses}
        assert HypothesisCategory.BGP_FAILURE.value in cats
        assert HypothesisCategory.INTERFACE_FAILURE.value in cats
        assert HypothesisCategory.WAN_DEGRADATION.value in cats


# ===========================================================================
# DEFECT-NET-VI-001 REGRESSION TESTS — DEVICE MAP RESOLUTION
# ===========================================================================

class TestDefectNetVi001DeviceMapResolution:
    def test_canonical_device_id_and_device_role(self) -> None:
        """1. CanonicalDevice with device_id and device_role."""
        cd = CanonicalDevice(device_id="dev-1", inventory_name="R1", device_role="core_router")
        svc = UnifiedEvidenceService()
        svc.registry.list_devices = MagicMock(return_value=[cd])

        dev_map = svc._resolve_device_map()
        assert "dev-1" in dev_map
        assert dev_map["dev-1"]["device_id"] == "dev-1"
        assert dev_map["dev-1"]["canonical_id"] == "dev-1"
        assert dev_map["dev-1"]["device_type"] == "core_router"

    def test_canonical_device_with_optional_topology_node_mapping(self) -> None:
        """2. CanonicalDevice with optional topology-node mapping."""
        cd = CanonicalDevice(device_id="dev-2", inventory_name="R2", device_role="distribution_switch")
        setattr(cd, "topology_node_id", "node_dist2")
        svc = UnifiedEvidenceService()
        svc.registry.list_devices = MagicMock(return_value=[cd])

        dev_map = svc._resolve_device_map()
        assert "node_dist2" in dev_map
        assert dev_map["node_dist2"]["device_id"] == "node_dist2"
        assert dev_map["node_dist2"]["canonical_id"] == "dev-2"
        assert dev_map["node_dist2"]["device_type"] == "distribution_switch"

    def test_missing_optional_topology_node_mapping(self) -> None:
        """3. Missing optional topology-node mapping does not raise AttributeError."""
        cd = CanonicalDevice(device_id="dev-3", inventory_name="R3")
        assert not hasattr(cd, "topology_node_id")
        svc = UnifiedEvidenceService()
        svc.registry.list_devices = MagicMock(return_value=[cd])

        dev_map = svc._resolve_device_map()
        assert "dev-3" in dev_map
        assert dev_map["dev-3"]["device_id"] == "dev-3"

    def test_multiple_devices_in_one_evidence_map(self) -> None:
        """4. Multiple devices in one evidence map (both via target_devices and default loop)."""
        cd1 = CanonicalDevice(device_id="dev-a", inventory_name="DevA", device_role="core")
        cd2 = CanonicalDevice(device_id="dev-b", inventory_name="DevB", device_role="edge")
        setattr(cd2, "topology_node_id", "node_b")
        cd3 = CanonicalDevice(device_id="dev-c", inventory_name="DevC", device_role="access")

        svc = UnifiedEvidenceService()
        svc.registry.list_devices = MagicMock(return_value=[cd1, cd2, cd3])
        svc.registry.resolve_device = MagicMock(side_effect=lambda q: {"dev-a": cd1, "DevB": cd2, "node_b": cd2}.get(q))

        # Test full map without target_devices
        full_map = svc._resolve_device_map()
        assert len(full_map) >= 3
        assert "dev-a" in full_map
        assert "node_b" in full_map
        assert "dev-c" in full_map

        # Test selective map with target_devices
        target_map = svc._resolve_device_map(target_devices=["dev-a", "DevB"])
        assert "dev-a" in target_map
        assert "node_b" in target_map
        assert "dev-c" not in target_map

    def test_missing_or_unknown_device_role(self) -> None:
        """5. Missing, empty, or unknown device role defaults safely to 'router' without AttributeError."""
        cd_empty = CanonicalDevice(device_id="dev-no-role", device_role="")
        svc = UnifiedEvidenceService()
        svc.registry.list_devices = MagicMock(return_value=[cd_empty])

        dev_map = svc._resolve_device_map()
        assert dev_map["dev-no-role"]["device_type"] == "router"

    def test_live_database_integration_path(self) -> None:
        """6. Live database integration path operates without AttributeError and produces valid bundle."""
        svc = UnifiedEvidenceService()
        # Direct _resolve_device_map against real DB/registry
        dev_map = svc._resolve_device_map()
        assert len(dev_map) > 0
        for did, meta in dev_map.items():
            assert "device_id" in meta
            assert "canonical_id" in meta
            assert "device_type" in meta
            assert "display_name" in meta

        # Full assemble_evidence_bundle without synthetic data
        bundle = svc.assemble_evidence_bundle(allow_live_collection=False)
        assert bundle is not None
        assert isinstance(bundle.device_evidence, dict)
        assert len(bundle.device_evidence) > 0
        for did, dinfo in bundle.device_evidence.items():
            assert "device_id" in dinfo
            assert "display_name" in dinfo
            assert "device_type" in dinfo

