"""
Section 18 Final End-to-End Acceptance Scenario — Networking IV Complete Campaign.

Models the realistic multi-router topology:
    INTERNET (198.51.100.1)
       |
    Router C (dev_router_c, RouterOS v7.15.2, Edge/WAN)
       |  Transit BC: 10.0.23.0/30 (.2 on C ether2, .1 on B ether1)
    Router B (dev_router_b, RouterOS v6.49.15, Distribution/Transit)
       |  Transit AB: 10.0.12.0/30 (.2 on B ether2, .1 on A ether1)
    Router A (dev_router_a, RouterOS v7.14.3, Access/LAN Gateway)
       |
    LAN Users (192.168.88.0/24 on A bridge_lan)

Verifies all 17 baseline Section 18 capabilities end-to-end and executes all 6 controlled
fault injections in isolated test environments with 100% read-only command enforcement
and zero live RouterOS configuration changes.
"""

from __future__ import annotations

import sqlite3
import time
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from core.canonical_network import CanonicalDevice, CanonicalNetworkRegistry
from core.network_intelligence.auto_orchestrator import AutomaticNetworkOrchestrator
from core.network_intelligence.command_execution import UnifiedCommandExecutor
from core.network_intelligence.security import validate_readonly_command
from core.routing.cross_device_routing import CrossDeviceRouteIntelligenceEngine
from core.routing.route_analytics import PathResultState, RoutePathEvaluator, RouteTableAnalyzer
from core.routing.route_collector import (
    MultiDeviceRouteCollector,
    RouteCollectionStatus,
    RouteCompleteness,
)
from core.routing.route_dependency import (
    DependencyResolutionState,
    FailurePropagationAnalyzer,
    HypotheticalFailureType,
    RouteDependencyAnalyzer,
)
from core.routing.route_history import RouteHistoryStore


# ---------------------------------------------------------------------------
# Realistic RouterOS v7 & v6 CLI Outputs for the 3-Router Topology
# ---------------------------------------------------------------------------

ROUTEROS_V7_ROUTER_A = """Flags: D - dynamic; X - disabled, I - inactive, A - active;
c - connect, s - static, r - rip, b - bgp, o - ospf, i - is-is, d - dhcp, v - vpn, m - modem, y - bgp-mpls-vpn;
H - hw-offloaded; + - ecmp
 0  As   dst-address=0.0.0.0/0 routing-table=main pref-src="" gateway=10.0.12.2 immediate-gw=10.0.12.2%ether1 distance=1 scope=30 target-scope=10 suppress-hw-offload=no

   DAc   dst-address=10.0.12.0/30 routing-table=main gateway=ether1 immediate-gw=ether1 distance=0 scope=10 target-scope=5 local-address=10.0.12.1%ether1

   DAc   dst-address=192.168.88.0/24 routing-table=main gateway=bridge_lan immediate-gw=bridge_lan distance=0 scope=10 target-scope=5 local-address=192.168.88.1%bridge_lan

 1  As   dst-address=10.255.0.3/32 routing-table=main gateway=10.0.12.2 immediate-gw=10.0.12.2%ether1 distance=110 scope=20 target-scope=10

 2  As   dst-address=172.16.200.0/24 routing-table=main gateway=10.255.0.3 immediate-gw=10.0.12.2%ether1 distance=20 scope=40 target-scope=30

   DAc   dst-address=192.168.99.0/24 routing-table=vrf_guest gateway=vlan99 immediate-gw=vlan99 distance=0 scope=10 target-scope=5 local-address=192.168.99.1%vlan99
"""

ROUTEROS_V6_ROUTER_B = """Flags: X - disabled, A - active, D - dynamic, C - connect, S - static, r - rip, b - bgp, o - ospf, m - mme, B - blackhole, U - unreachable, P - prohibit
 0 A S  dst-address=0.0.0.0/0 gateway=10.0.23.2 gateway-status=10.0.23.2 reachable via  ether1 distance=1 scope=30 target-scope=10

 1 ADC  dst-address=10.0.23.0/30 pref-src=10.0.23.1 gateway=ether1 gateway-status=ether1 reachable distance=0 scope=10

 2 ADC  dst-address=10.0.12.0/30 pref-src=10.0.12.2 gateway=ether2 gateway-status=ether2 reachable distance=0 scope=10

 3 ADo  dst-address=192.168.88.0/24 gateway=10.0.12.1 gateway-status=10.0.12.1 reachable via  ether2 distance=110 scope=20 target-scope=10

 4 A S  dst-address=10.255.0.3/32 gateway=10.0.23.2 gateway-status=10.0.23.2 reachable via  ether1 distance=1 scope=30 target-scope=10

 5 A S  dst-address=172.16.200.0/24 gateway=10.0.23.2 gateway-status=10.0.23.2 reachable via  ether1 distance=1 scope=30 target-scope=10
"""

ROUTEROS_V7_ROUTER_C = """Flags: D - dynamic; X - disabled, I - inactive, A - active;
c - connect, s - static, r - rip, b - bgp, o - ospf, d - dhcp; H - hw-offloaded; + - ecmp
 0  As   dst-address=0.0.0.0/0 routing-table=main gateway=198.51.100.1 immediate-gw=198.51.100.1%ether1_wan distance=1 scope=30 target-scope=10

   DAc   dst-address=198.51.100.0/30 routing-table=main gateway=ether1_wan immediate-gw=ether1_wan distance=0 scope=10 target-scope=5 local-address=198.51.100.2%ether1_wan

   DAc   dst-address=10.0.23.0/30 routing-table=main gateway=ether2 immediate-gw=ether2 distance=0 scope=10 target-scope=5 local-address=10.0.23.2%ether2

   DAc   dst-address=10.255.0.3/32 routing-table=main gateway=lo0 immediate-gw=lo0 distance=0 scope=10 target-scope=5 local-address=10.255.0.3%lo0

   DAc   dst-address=172.16.200.0/24 routing-table=main gateway=bridge_dmz immediate-gw=bridge_dmz distance=0 scope=10 target-scope=5 local-address=172.16.200.1%bridge_dmz

 1 DDo   dst-address=192.168.88.0/24 routing-table=main gateway=10.0.23.1 immediate-gw=10.0.23.1%ether2 distance=110 scope=20 target-scope=10
"""


class ThreeRouterRegistry(CanonicalNetworkRegistry):
    def __init__(self, devices: List[CanonicalDevice]):
        super().__init__()
        self._devices = {d.device_id: d for d in devices}

    def list_devices(self, force_refresh: bool = False) -> List[CanonicalDevice]:
        return list(self._devices.values())

    def resolve_device(self, query: str) -> Optional[CanonicalDevice]:
        q = (query or "").strip().lower()
        if not q:
            return None
        for dev in self._devices.values():
            if q in (
                dev.device_id.lower(),
                dev.inventory_name.lower(),
                dev.observed_identity.lower(),
                dev.management_ip.lower(),
            ) or q in [ip.lower() for ip in dev.all_ips]:
                return dev
        return None


def _build_3_router_devices() -> List[CanonicalDevice]:
    return [
        CanonicalDevice(
            device_id="dev_router_a",
            inventory_name="Router-A",
            observed_identity="RTR-A-LAN",
            management_ip="10.0.12.1",
            all_ips=["10.0.12.1", "192.168.88.1", "192.168.99.1"],
            device_type="mikrotik",
            platform="RB5009UG+S+",
            os_version="7.14.3",
            ros_major_version=7,
            is_managed=True,
        ),
        CanonicalDevice(
            device_id="dev_router_b",
            inventory_name="Router-B",
            observed_identity="RTR-B-TRANSIT",
            management_ip="10.0.12.2",
            all_ips=["10.0.12.2", "10.0.23.1"],
            device_type="mikrotik",
            platform="CCR1009-7G-1C-1S+",
            os_version="6.49.15",
            ros_major_version=6,
            is_managed=True,
        ),
        CanonicalDevice(
            device_id="dev_router_c",
            inventory_name="Router-C",
            observed_identity="RTR-C-EDGE",
            management_ip="10.0.23.2",
            all_ips=["10.0.23.2", "198.51.100.2", "10.255.0.3", "172.16.200.1"],
            device_type="mikrotik",
            platform="CCR2004-16G-2S+",
            os_version="7.15.2",
            ros_major_version=7,
            is_managed=True,
        ),
    ]


def _baseline_topology_edges() -> List[Dict[str, Any]]:
    return [
        {
            "id": "edge_ab_phys",
            "source_node_id": "dev_router_a",
            "target_node_id": "dev_router_b",
            "source_interface": "ether1",
            "target_interface": "ether2",
            "relationship_class": "PHYSICAL_ADJACENCY",
            "confidence_tier": "confirmed",
            "oper_status": "up",
        },
        {
            "id": "edge_bc_phys",
            "source_node_id": "dev_router_b",
            "target_node_id": "dev_router_c",
            "source_interface": "ether1",
            "target_interface": "ether2",
            "relationship_class": "PHYSICAL_ADJACENCY",
            "confidence_tier": "confirmed",
            "oper_status": "up",
        },
    ]


def _collect_from_cli_map(
    registry: ThreeRouterRegistry,
    cli_outputs_by_ip: Dict[str, Any],
) -> tuple[Dict[str, Any], List[str]]:
    executed_commands: List[str] = []
    cm = MagicMock()

    def _exec(command: str, device_name: str = "", timeout: float = 15.0, **kwargs):
        executed_commands.append(command)
        dev = registry.resolve_device(device_name)
        ip = dev.management_ip if dev else device_name
        spec = cli_outputs_by_ip.get(ip)
        if spec is None or spec == "UNREACHABLE":
            return {"success": False, "error": f"No route to host {ip} (Host unreachable)"}
        if "identity" in command:
            return {"success": True, "output": f"name: {dev.observed_identity if dev else device_name}"}
        if "resource" in command:
            return {"success": True, "output": f"version: {dev.os_version if dev else '7.15'}"}
        if "ospf route" in command:
            return {"success": True, "output": ""}
        if isinstance(spec, dict):
            return spec
        return {"success": True, "output": str(spec)}

    cm.execute_command.side_effect = _exec
    executor = UnifiedCommandExecutor(connection_manager=cm, registry=registry)
    collector = MultiDeviceRouteCollector(registry=registry, command_executor=executor)
    report = collector.collect_multi_device_routes(
        targets=["Router-A", "Router-B", "Router-C"],
        max_concurrency=3,
        max_retries=0,
    )
    return report.results, executed_commands


def test_section_18_baseline_17_capabilities_end_to_end(tmp_path):
    """Verifies all 17 baseline Section 18 capabilities across the 3-router topology."""
    devices = _build_3_router_devices()
    registry = ThreeRouterRegistry(devices)
    dev_ips = {d.device_id: list(d.all_ips) for d in devices}
    topo_edges = _baseline_topology_edges()
    db_path = tmp_path / "e2e_sec18.db"
    hist_store = RouteHistoryStore(db_path)

    # Seed auxiliary NMS & topology event tables in the isolated test DB for Cap #12
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS nms_alerts (id TEXT PRIMARY KEY, device_id TEXT, alert_type TEXT, severity TEXT, message TEXT, created_at REAL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS topology_changes (id INTEGER PRIMARY KEY AUTOINCREMENT, change_type TEXT, entity_id TEXT, summary TEXT, timestamp REAL)"
    )
    now_ts = time.time()
    conn.execute(
        "INSERT INTO nms_alerts VALUES (?, ?, ?, ?, ?, ?)",
        ("al_1", "dev_router_c", "BGP_UPSTREAM_FLAP", "WARNING", "WAN neighbor state oscillation", now_ts),
    )
    conn.execute(
        "INSERT INTO topology_changes (change_type, entity_id, summary, timestamp) VALUES (?, ?, ?, ?)",
        ("EDGE_VERIFIED", "edge_bc_phys", "Link B-C verified up", now_ts),
    )
    conn.commit()
    conn.close()

    # Cap 1, 2, 3, 4: Resolve all devices, collect routes via read-only CLI, normalize v6+v7, preserve VRFs
    collections, executed_cmds = _collect_from_cli_map(
        registry,
        {
            "10.0.12.1": ROUTEROS_V7_ROUTER_A,
            "10.0.12.2": ROUTEROS_V6_ROUTER_B,
            "10.0.23.2": ROUTEROS_V7_ROUTER_C,
        },
    )
    assert set(collections.keys()) == {"dev_router_a", "dev_router_b", "dev_router_c"}
    for cmd in executed_cmds:
        valid, reason = validate_readonly_command(cmd)
        assert valid, f"Non-read-only command executed: {cmd} ({reason})"

    assert "main" in collections["dev_router_a"].routing_tables
    assert "vrf_guest" in collections["dev_router_a"].routing_tables
    assert collections["dev_router_b"].route_count >= 6  # RouterOS v6 normalized!

    # Cap 5: Reconstruct inferred/confirmed route path across all 3 routers:
    # (a) Internal DMZ prefix 172.16.200.50 (Router A -> Router B -> Router C) => PATH_CONFIRMED_BY_EVIDENCE
    verified_adj = {("dev_router_a", "dev_router_b"), ("dev_router_b", "dev_router_c")}
    path_dmz = RoutePathEvaluator().evaluate_path(
        "dev_router_a",
        "172.16.200.50",
        collections,
        routing_table="main",
        device_ips=dev_ips,
        verified_adjacencies=verified_adj,
    )
    assert path_dmz.state == PathResultState.PATH_CONFIRMED_BY_EVIDENCE.value
    assert [h.device_id for h in path_dmz.primary_hops] == [
        "dev_router_a",
        "dev_router_b",
        "dev_router_c",
    ]
    # (b) External Internet 8.8.8.8 (Router A -> Router B -> Router C -> unmanaged ISP 198.51.100.1) => PATH_PARTIAL
    path_eval = RoutePathEvaluator().evaluate_path(
        "dev_router_a",
        "8.8.8.8",
        collections,
        routing_table="main",
        device_ips=dev_ips,
        verified_adjacencies=verified_adj,
    )
    assert path_eval.state == PathResultState.PATH_PARTIAL.value
    assert [h.device_id for h in path_eval.primary_hops] == [
        "dev_router_a",
        "dev_router_b",
        "dev_router_c",
    ]
    assert path_eval.primary_hops[-1].gateway == "198.51.100.1"

    # Cap 6: Resolve recursive next hops (172.16.200.0/24 -> 10.255.0.3 -> 10.0.12.2 -> ether1)
    dep_analyzer = RouteDependencyAnalyzer()
    dep_graph = dep_analyzer.build_dependency_graph(collections, device_ips=dev_ips, routing_table="main")
    rec_res = [
        r for r in dep_graph.resolutions
        if r.device_id == "dev_router_a" and r.dst_prefix == "172.16.200.0/24"
    ]
    assert len(rec_res) == 1
    assert rec_res[0].state == DependencyResolutionState.RECURSIVE_RESOLVED.value
    assert "ether1" in rec_res[0].resolved_egress_interfaces
    assert dep_graph.to_dict()["persisted_as_topology_edges"] is False

    # Cap 7: Correlate route relationships with TopologyEngine edges & overlay
    xdev_engine = CrossDeviceRouteIntelligenceEngine()
    xdev_report = xdev_engine.analyze_network_routing(
        collections,
        device_ips=dev_ips,
        topology_edges=topo_edges,
        device_oper_states={"dev_router_a": "online", "dev_router_b": "online", "dev_router_c": "online"},
        registered_device_ids=["dev_router_a", "dev_router_b", "dev_router_c"],
        source_device="dev_router_a",
        destination="8.8.8.8",
        routing_table="main",
    )
    assert len(xdev_report.verified_relationships) >= 2
    assert any(r.verification_state == "TOPOLOGY_CONFIRMED" for r in xdev_report.verified_relationships)
    assert xdev_report.topology_overlay["mutates_physical_topology"] is False
    assert all(seg["is_physical_link"] is False for seg in xdev_report.topology_overlay["segments"])

    # Cap 11 & 12: Compare route history & correlate temporally with NMS/topology events
    snap_batch_1 = hist_store.create_multi_device_snapshots(collections, trigger_type="baseline")
    assert snap_batch_1["snapshots_count"] == 3
    hist_analytics = hist_store.get_historical_analytics(limit=20)
    assert hist_analytics["total_snapshots"] == 3

    # Cap 8, 9, 10, 13, 14, 15, 16, 17: Network-wide auto-diagnosis, root causes, evidence, confidence, safe verification
    orch = AutomaticNetworkOrchestrator()
    orch.registry = registry
    diag = orch.execute_auto_diagnosis(
        target_devices=["dev_router_a", "dev_router_b", "dev_router_c"],
        symptom="Why can this LAN not reach the internet?",
        precollected_routes=collections,
        device_ips_override=dev_ips,
        topology_edges_override=topo_edges,
        device_oper_states_override={"dev_router_a": "online", "dev_router_b": "online", "dev_router_c": "online"},
        route_history_store_override=hist_store,
    )
    assert diag["success"] is True
    assert diag["read_only"] is True
    assert diag["auto_remediation_executed"] is False
    assert len(diag["root_causes"]) >= 1
    assert len(diag["root_causes"][0]["evidence_ids"]) >= 1
    assert len(diag["verification_recommendations"]) >= 1
    for rec in diag["verification_recommendations"]:
        ok, _ = validate_readonly_command(rec["command"])
        assert ok is True


def test_section_18_all_6_controlled_fault_injections(tmp_path):
    """
    Injects all 6 controlled fault scenarios from Section 18 in isolated test environments:
    1. Remove a route from a fixture
    2. Mark a gateway unreachable
    3. Simulate an unavailable intermediate router
    4. Introduce a routing-table / VRF mismatch
    5. Introduce conflicting topology vs routing evidence
    6. Simulate incomplete collection
    """
    devices = _build_3_router_devices()
    registry = ThreeRouterRegistry(devices)
    dev_ips = {d.device_id: list(d.all_ips) for d in devices}
    topo_edges = _baseline_topology_edges()
    orch = AutomaticNetworkOrchestrator()
    orch.registry = registry

    baseline_cols, _ = _collect_from_cli_map(
        registry,
        {
            "10.0.12.1": ROUTEROS_V7_ROUTER_A,
            "10.0.12.2": ROUTEROS_V6_ROUTER_B,
            "10.0.23.2": ROUTEROS_V7_ROUTER_C,
        },
    )

    # ------------------------------------------------------------------
    # FAULT 1: Remove a route from a fixture (Remove 0.0.0.0/0 & 172.16.200.0/24 on Router B)
    # ------------------------------------------------------------------
    hist_f1 = RouteHistoryStore(tmp_path / "fault1.db")
    hist_f1.create_multi_device_snapshots(baseline_cols, trigger_type="pre_fault")

    router_b_missing_upstream = """Flags: X - disabled, A - active, D - dynamic, C - connect, S - static
 0 ADC  dst-address=10.0.23.0/30 pref-src=10.0.23.1 gateway=ether1 gateway-status=ether1 reachable distance=0 scope=10
 1 ADC  dst-address=10.0.12.0/30 pref-src=10.0.12.2 gateway=ether2 gateway-status=ether2 reachable distance=0 scope=10
"""
    f1_cols, _ = _collect_from_cli_map(
        registry,
        {
            "10.0.12.1": ROUTEROS_V7_ROUTER_A,
            "10.0.12.2": router_b_missing_upstream,
            "10.0.23.2": ROUTEROS_V7_ROUTER_C,
        },
    )
    hist_f1.create_multi_device_snapshots(f1_cols, trigger_type="post_fault_1")
    f1_diag = orch.execute_auto_diagnosis(
        target_devices=["dev_router_a", "dev_router_b", "dev_router_c"],
        symptom="Analyze what changed before this network became unreachable.",
        precollected_routes=f1_cols,
        device_ips_override=dev_ips,
        topology_edges_override=topo_edges,
        route_history_store_override=hist_f1,
    )
    f1_descs = " ".join(rc["description"] for rc in f1_diag["root_causes"])
    assert "MISSING_UPSTREAM_ROUTE" in f1_descs or "MISSING_DEFAULT_ROUTE" in f1_descs
    assert "ROUTE_REMOVED" in f1_descs

    # ------------------------------------------------------------------
    # FAULT 2: Mark a gateway unreachable (Router A default gateway unreachable)
    # ------------------------------------------------------------------
    router_a_gw_unreachable = """Flags: D - dynamic; X - disabled, I - inactive, A - active; c - connect, s - static
 0  Is   dst-address=0.0.0.0/0 routing-table=main gateway=10.99.99.1 immediate-gw="" distance=1 scope=30 target-scope=10
   DAc   dst-address=192.168.88.0/24 routing-table=main gateway=bridge_lan immediate-gw=bridge_lan distance=0 scope=10 local-address=192.168.88.1%bridge_lan
"""
    f2_cols, _ = _collect_from_cli_map(
        registry,
        {
            "10.0.12.1": router_a_gw_unreachable,
            "10.0.12.2": ROUTEROS_V6_ROUTER_B,
            "10.0.23.2": ROUTEROS_V7_ROUTER_C,
        },
    )
    f2_diag = orch.execute_auto_diagnosis(
        target_devices=["dev_router_a", "dev_router_b", "dev_router_c"],
        symptom="Why can this LAN not reach the internet?",
        precollected_routes=f2_cols,
        device_ips_override=dev_ips,
        route_history_store_override=RouteHistoryStore(tmp_path / "fault2.db"),
    )
    assert f2_diag["epistemic_classification"] == "Confirmed finding"
    assert f2_diag["route_intelligence"]["path_evaluation"]["state"] == PathResultState.PATH_UNREACHABLE.value

    # ------------------------------------------------------------------
    # FAULT 3: Simulate an unavailable intermediate router (Router B SSH unreachable & offline)
    # ------------------------------------------------------------------
    f3_cols, _ = _collect_from_cli_map(
        registry,
        {
            "10.0.12.1": ROUTEROS_V7_ROUTER_A,
            "10.0.12.2": "UNREACHABLE",
            "10.0.23.2": ROUTEROS_V7_ROUTER_C,
        },
    )
    assert f3_cols["dev_router_b"].status == RouteCollectionStatus.UNREACHABLE.value
    f3_diag = orch.execute_auto_diagnosis(
        target_devices=["dev_router_a", "dev_router_b", "dev_router_c"],
        symptom="Why can this LAN not reach the internet?",
        precollected_routes=f3_cols,
        device_ips_override=dev_ips,
        device_oper_states_override={"dev_router_a": "online", "dev_router_b": "offline", "dev_router_c": "online"},
        route_history_store_override=RouteHistoryStore(tmp_path / "fault3.db"),
    )
    assert "dev_router_b" in f3_diag["route_intelligence"]["cross_device"]["unavailable_devices"]
    assert f3_diag["route_intelligence"]["path_evaluation"]["state"] == PathResultState.PATH_PARTIAL.value
    assert any("ROUTE_POINTING_TO_UNAVAILABLE_NEXT_HOP" in rc["description"] for rc in f3_diag["root_causes"])
    assert len(f3_diag["partial_evidence_warnings"]) >= 1
    # Also verify hypothetical failure propagation (WP 4.6.3)
    impact = FailurePropagationAnalyzer().analyze_failure(
        HypotheticalFailureType.INTERMEDIATE_ROUTER_UNAVAILABLE.value,
        baseline_cols,
        device_id="dev_router_b",
        device_ips=dev_ips,
    )
    assert any(d["device_id"] == "dev_router_a" for d in impact.potentially_affected_destinations)

    # ------------------------------------------------------------------
    # FAULT 4: Introduce a routing-table / VRF mismatch
    # ------------------------------------------------------------------
    router_a_vrf_query = ROUTEROS_V7_ROUTER_A + "\n 3  As   dst-address=10.77.0.0/24 routing-table=main gateway=10.0.12.2 immediate-gw=10.0.12.2%ether1 distance=1 scope=30 target-scope=10\n"
    router_b_vrf_isolated = ROUTEROS_V6_ROUTER_B + "\n 6 ADC  dst-address=10.77.0.0/24 pref-src=10.77.0.1 gateway=vlan77 gateway-status=vlan77 reachable distance=0 scope=10 routing-mark=vrf_isolated\n"
    f4_cols, _ = _collect_from_cli_map(
        registry,
        {
            "10.0.12.1": router_a_vrf_query,
            "10.0.12.2": router_b_vrf_isolated,
            "10.0.23.2": ROUTEROS_V7_ROUTER_C,
        },
    )
    f4_diag = orch.execute_auto_diagnosis(
        target_devices=["dev_router_a", "dev_router_b", "dev_router_c"],
        symptom="Analyze the route to 10.77.0.50.",
        precollected_routes=f4_cols,
        device_ips_override=dev_ips,
        route_history_store_override=RouteHistoryStore(tmp_path / "fault4.db"),
    )
    assert any("INCORRECT_VRF_ASSOCIATION" in rc["description"] for rc in f4_diag["root_causes"])

    # ------------------------------------------------------------------
    # FAULT 5: Introduce conflicting topology vs routing evidence
    # ------------------------------------------------------------------
    conflicting_topo = [
        {
            "id": "edge_ac_wrong_cable",
            "source_node_id": "dev_router_a",
            "target_node_id": "dev_router_c",  # Physical edge says A:ether1 -> C:ether2, but A routes 10.0.12.2 (B)!
            "source_interface": "ether1",
            "target_interface": "ether2",
            "relationship_class": "PHYSICAL_ADJACENCY",
            "confidence_tier": "confirmed",
            "oper_status": "up",
        }
    ]
    f5_diag = orch.execute_auto_diagnosis(
        target_devices=["dev_router_a", "dev_router_b", "dev_router_c"],
        symptom="Find possible routing inconsistencies between routers.",
        precollected_routes=baseline_cols,
        device_ips_override=dev_ips,
        topology_edges_override=conflicting_topo,
        route_history_store_override=RouteHistoryStore(tmp_path / "fault5.db"),
    )
    assert any("UNEXPECTED_PATH_DIVERGENCE" in rc["description"] for rc in f5_diag["root_causes"])

    # ------------------------------------------------------------------
    # FAULT 6: Simulate incomplete collection (Router C truncated / PARTIAL)
    # ------------------------------------------------------------------
    hist_f6 = RouteHistoryStore(tmp_path / "fault6.db")
    hist_f6.create_snapshot_from_collection(baseline_cols["dev_router_c"], trigger_type="complete_before")

    partial_c = baseline_cols["dev_router_c"]
    from dataclasses import replace
    partial_c_truncated = replace(
        partial_c,
        routes=partial_c.routes[:1],
        completeness=RouteCompleteness.PARTIAL.value,
        status=RouteCollectionStatus.PARTIAL.value,
        evidence_id="ev_partial_c_after",
        collected_at=time.time() + 10.0,
    )
    _, f6_changes = hist_f6.create_snapshot_from_collection(partial_c_truncated, trigger_type="partial_after")
    # False ROUTE_REMOVED events MUST be suppressed when collection is incomplete!
    chg_types = [c.change_type for c in f6_changes]
    assert "ROUTE_REMOVED" not in chg_types
    assert "ROUTE_STATE_UNKNOWN" in chg_types

    f6_cols = dict(baseline_cols)
    f6_cols["dev_router_c"] = partial_c_truncated
    f6_diag = orch.execute_auto_diagnosis(
        target_devices=["dev_router_a", "dev_router_b", "dev_router_c"],
        symptom="Why can this LAN not reach the internet?",
        precollected_routes=f6_cols,
        device_ips_override=dev_ips,
        route_history_store_override=hist_f6,
    )
    assert len(f6_diag["partial_evidence_warnings"]) >= 1
    assert "dev_router_c" in f6_diag["route_intelligence"]["cross_device"]["incomplete_devices"]
    # Epistemic confidence MUST NOT claim Confirmed finding when upstream evidence is incomplete!
    assert f6_diag["epistemic_classification"] != "Confirmed finding"
