"""
WP 4.6.5 Acceptance Test Suite — Cross-Device Route Intelligence & Topology Overlay.

Verifies Scenarios A–J (Section 9.7), Section 9.2 anti-fabrication rules, all 12
CrossDeviceInconsistencyType detectors, non-destructive Topology UI route overlay,
and REST API endpoints.
"""

from __future__ import annotations

import time
import pytest
from fastapi.testclient import TestClient

from core.routing.cross_device_routing import (
    CrossDeviceInconsistencyType,
    CrossDeviceRouteIntelligenceEngine,
    OverlaySegmentType,
)
from core.routing.route_analytics import PathResultState
from core.routing.route_collector import (
    RouteCollectionResult,
    RouteCollectionStatus,
    RouteCompleteness,
)
from core.routing.unified_route_parser import NormalizedRoute, RouteProtocol, RouteType


def _r(
    dev_id: str,
    dst: str,
    gw: str = "",
    *,
    iface: str = "",
    pref_src: str = "",
    connect: bool = False,
    static: bool = False,
    ospf: bool = False,
    active: bool = True,
    disabled: bool = False,
    unreachable: bool = False,
    distance: int = 1,
    scope: int = 30,
    target_scope: int = 10,
    table: str = "main",
    gws: list[str] | None = None,
) -> NormalizedRoute:
    proto = (
        RouteProtocol.CONNECTED if connect
        else RouteProtocol.OSPF if ospf
        else RouteProtocol.STATIC
    )
    gw_list = gws if gws is not None else ([gw] if gw else [])
    return NormalizedRoute(
        device_id=dev_id,
        dst_prefix=dst,
        gateway=gw,
        gateways=gw_list,
        interface_name=iface,
        pref_src=pref_src,
        distance=0 if connect else distance,
        scope=10 if connect else scope,
        target_scope=target_scope,
        routing_table=table,
        protocol=proto,
        route_type=RouteType.UNICAST,
        active=active,
        disabled=disabled,
        unreachable=unreachable,
        connect=connect,
        static=static or (not connect and not ospf),
        ospf=ospf,
    )


def _col(
    dev_id: str,
    routes: list[NormalizedRoute],
    *,
    completeness: str = RouteCompleteness.COMPLETE.value,
    status: str = RouteCollectionStatus.SUCCESS.value,
) -> RouteCollectionResult:
    tables = sorted({r.routing_table or "main" for r in routes}) or ["main"]
    return RouteCollectionResult(
        device_id=dev_id,
        device_identity=dev_id.upper(),
        router_os_version="7.15.2",
        status=status,
        completeness=completeness,
        routes=routes,
        routing_tables=tables,
        evidence_id=f"ev_{dev_id}",
        collected_at=time.time(),
    )


def test_scenario_a_simple_two_router_network():
    """Scenario A: Router A -> Router B -> Destination (10.20.0.0/24)."""
    engine = CrossDeviceRouteIntelligenceEngine()
    collections = {
        "dev_a": _col("dev_a", [
            _r("dev_a", "192.168.1.0/24", iface="ether2", pref_src="192.168.1.1", connect=True),
            _r("dev_a", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.1", connect=True),
            _r("dev_a", "10.20.0.0/24", "10.0.12.2", iface="ether1", static=True),
        ]),
        "dev_b": _col("dev_b", [
            _r("dev_b", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.2", connect=True),
            _r("dev_b", "10.20.0.0/24", iface="ether2", pref_src="10.20.0.1", connect=True),
            _r("dev_b", "192.168.1.0/24", "10.0.12.1", iface="ether1", static=True),
        ]),
    }
    report = engine.analyze_network_routing(
        collections,
        source_device="dev_a",
        destination="10.20.0.50",
    )
    assert report.path_evaluation is not None
    assert report.path_evaluation["state"] == PathResultState.PATH_INFERRED.value
    assert [h["device_id"] for h in report.path_evaluation["primary_hops"]] == ["dev_a", "dev_b"]
    # Without L1/L2 topology edge, relationship is GATEWAY_IP_VERIFIED and NOT physical adjacency
    ab_rels = [v for v in report.verified_relationships if v.source_device_id == "dev_a" and v.target_device_id == "dev_b"]
    assert len(ab_rels) == 1
    assert ab_rels[0].verification_state == "GATEWAY_IP_VERIFIED"
    assert ab_rels[0].is_physical_adjacency is False
    assert report.inconsistencies == []


def test_scenario_b_three_router_chain_with_confirmed_topology():
    """Scenario B: Router A -> Router B -> Router C -> Destination with confirmed L1 edges."""
    engine = CrossDeviceRouteIntelligenceEngine()
    collections = {
        "dev_a": _col("dev_a", [
            _r("dev_a", "192.168.10.0/24", iface="bridge-lan", pref_src="192.168.10.1", connect=True),
            _r("dev_a", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.1", connect=True),
            _r("dev_a", "172.16.50.0/24", "10.0.12.2", iface="ether1", ospf=True),
        ]),
        "dev_b": _col("dev_b", [
            _r("dev_b", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.2", connect=True),
            _r("dev_b", "10.0.23.0/30", iface="ether2", pref_src="10.0.23.1", connect=True),
            _r("dev_b", "172.16.50.0/24", "10.0.23.2", iface="ether2", ospf=True),
            _r("dev_b", "192.168.10.0/24", "10.0.12.1", iface="ether1", ospf=True),
        ]),
        "dev_c": _col("dev_c", [
            _r("dev_c", "10.0.23.0/30", iface="ether1", pref_src="10.0.23.2", connect=True),
            _r("dev_c", "172.16.50.0/24", iface="ether3", pref_src="172.16.50.1", connect=True),
            _r("dev_c", "192.168.10.0/24", "10.0.23.1", iface="ether1", ospf=True),
        ]),
    }
    topo_edges = [
        {
            "id": "edge_ab",
            "source_node_id": "dev_a",
            "target_node_id": "dev_b",
            "source_interface": "ether1",
            "target_interface": "ether1",
            "relationship_class": "PHYSICAL_ADJACENCY",
            "confidence_tier": "confirmed",
            "oper_status": "up",
        },
        {
            "id": "edge_bc",
            "source_node_id": "dev_b",
            "target_node_id": "dev_c",
            "source_interface": "ether2",
            "target_interface": "ether1",
            "relationship_class": "PHYSICAL_ADJACENCY",
            "confidence_tier": "confirmed",
            "oper_status": "up",
        },
    ]
    report = engine.analyze_network_routing(
        collections,
        topology_edges=topo_edges,
        source_device="dev_a",
        destination="172.16.50.10",
    )
    assert report.path_evaluation["state"] == PathResultState.PATH_CONFIRMED_BY_EVIDENCE.value
    assert [h["device_id"] for h in report.path_evaluation["primary_hops"]] == ["dev_a", "dev_b", "dev_c"]
    assert report.topology_overlay["mutates_physical_topology"] is False
    segs = report.topology_overlay["segments"]
    assert len(segs) == 3
    assert segs[0]["confirmed_by_topology_adjacency"] is True
    assert segs[0]["is_physical_link"] is False


def test_scenario_c_missing_return_route_and_one_way_hypothesis():
    """Scenario C: Forward route exists, return route missing -> MISSING_RETURN_ROUTE + ONE_WAY_REACHABILITY_HYPOTHESIS."""
    engine = CrossDeviceRouteIntelligenceEngine()
    collections = {
        "dev_a": _col("dev_a", [
            _r("dev_a", "192.168.99.0/24", iface="ether2", pref_src="192.168.99.1", connect=True),
            _r("dev_a", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.1", connect=True),
            _r("dev_a", "10.50.0.0/24", "10.0.12.2", iface="ether1", static=True),
        ]),
        "dev_b": _col("dev_b", [
            _r("dev_b", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.2", connect=True),
            _r("dev_b", "10.50.0.0/24", iface="ether2", pref_src="10.50.0.1", connect=True),
            # No return route back to 192.168.99.0/24!
        ]),
    }
    report = engine.analyze_network_routing(
        collections,
        source_device="dev_a",
        destination="10.50.0.10",
        source_prefix_for_return="192.168.99.0/24",
    )
    types = {i.inconsistency_type: i for i in report.inconsistencies}
    assert CrossDeviceInconsistencyType.MISSING_RETURN_ROUTE.value in types
    assert CrossDeviceInconsistencyType.ONE_WAY_REACHABILITY_HYPOTHESIS.value in types
    # Never claim asymmetric / one-way packet failure as OBSERVED_FACT
    assert types[CrossDeviceInconsistencyType.ONE_WAY_REACHABILITY_HYPOTHESIS.value].epistemic_class == "HYPOTHESIS"


def test_scenario_d_wrong_next_hop_and_missing_upstream():
    """Scenario D: Gateway points toward dev_wrong instead of dev_c which owns destination."""
    engine = CrossDeviceRouteIntelligenceEngine()
    collections = {
        "dev_a": _col("dev_a", [
            _r("dev_a", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.1", connect=True),
            _r("dev_a", "10.0.13.0/30", iface="ether2", pref_src="10.0.13.1", connect=True),
            _r("dev_a", "10.88.0.0/24", "10.0.12.2", iface="ether1", static=True),
        ]),
        "dev_wrong": _col("dev_wrong", [
            _r("dev_wrong", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.2", connect=True),
            # Lacks route to 10.88.0.0/24!
        ]),
        "dev_c": _col("dev_c", [
            _r("dev_c", "10.0.13.0/30", iface="ether1", pref_src="10.0.13.2", connect=True),
            _r("dev_c", "10.88.0.0/24", iface="ether2", pref_src="10.88.0.1", connect=True),
        ]),
    }
    report = engine.analyze_network_routing(
        collections,
        source_device="dev_a",
        destination="10.88.0.5",
        expected_next_hop_device="dev_c",
    )
    itypes = {i.inconsistency_type for i in report.inconsistencies}
    assert CrossDeviceInconsistencyType.WRONG_NEXT_HOP_HYPOTHESIS.value in itypes
    assert CrossDeviceInconsistencyType.MISSING_UPSTREAM_ROUTE.value in itypes
    assert CrossDeviceInconsistencyType.INCONSISTENT_ROUTING_TABLES.value in itypes


def test_scenario_e_recursive_route_overlay():
    """Scenario E: Recursive BGP/static route resolves via IGP route -> RECURSIVE_NEXT_HOP_DEPENDENCY segment."""
    engine = CrossDeviceRouteIntelligenceEngine()
    collections = {
        "dev_a": _col("dev_a", [
            _r("dev_a", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.1", connect=True),
            _r("dev_a", "10.255.0.2/32", "10.0.12.2", iface="ether1", scope=20, target_scope=10, ospf=True),
            _r("dev_a", "172.30.0.0/16", "10.255.0.2", scope=40, target_scope=30, static=True),
        ]),
        "dev_b": _col("dev_b", [
            _r("dev_b", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.2", connect=True),
            _r("dev_b", "10.255.0.2/32", iface="lo", pref_src="10.255.0.2", connect=True),
            _r("dev_b", "172.30.0.0/16", iface="ether2", pref_src="172.30.0.1", connect=True),
        ]),
    }
    report = engine.analyze_network_routing(
        collections,
        source_device="dev_a",
        destination="172.30.1.10",
    )
    segs = report.topology_overlay["segments"]
    assert segs[0]["overlay_segment_type"] == OverlaySegmentType.RECURSIVE_NEXT_HOP_DEPENDENCY.value
    assert segs[0]["immediate_gateway"] == "10.0.12.2"
    assert len(segs[0]["recursive_dependency"]) >= 1


def test_scenario_f_ecmp_preserved():
    """Scenario F: Two valid ECMP next-hop routers preserved in path evaluation & overlay."""
    engine = CrossDeviceRouteIntelligenceEngine()
    collections = {
        "dev_a": _col("dev_a", [
            _r("dev_a", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.1", connect=True),
            _r("dev_a", "10.0.13.0/30", iface="ether2", pref_src="10.0.13.1", connect=True),
            _r("dev_a", "10.90.0.0/24", "10.0.12.2,10.0.13.2", gws=["10.0.12.2", "10.0.13.2"], ospf=True),
        ]),
        "dev_b1": _col("dev_b1", [
            _r("dev_b1", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.2", connect=True),
            _r("dev_b1", "10.90.0.0/24", iface="ether2", pref_src="10.90.0.1", connect=True),
        ]),
        "dev_b2": _col("dev_b2", [
            _r("dev_b2", "10.0.13.0/30", iface="ether1", pref_src="10.0.13.2", connect=True),
            _r("dev_b2", "10.90.0.0/24", iface="ether2", pref_src="10.90.0.2", connect=True),
        ]),
    }
    report = engine.analyze_network_routing(
        collections,
        source_device="dev_a",
        destination="10.90.0.50",
    )
    assert len(report.path_evaluation["ecmp_branches"]) == 2
    branch_hops = {b[0]["next_device_id"] for b in report.path_evaluation["ecmp_branches"]}
    assert branch_hops == {"dev_b1", "dev_b2"}


def test_scenario_g_and_h_upstream_unavailable_and_incomplete_evidence():
    """Scenarios G & H: Upstream router offline / incomplete collection -> ROUTE_POINTING_TO_UNAVAILABLE_NEXT_HOP + ROUTE_UNCERTAINTY."""
    engine = CrossDeviceRouteIntelligenceEngine()
    collections = {
        "dev_a": _col("dev_a", [
            _r("dev_a", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.1", connect=True),
            _r("dev_a", "0.0.0.0/0", "10.0.12.2", iface="ether1", static=True),
        ]),
        "dev_b": _col(
            "dev_b",
            [],
            completeness=RouteCompleteness.UNREACHABLE.value,
            status=RouteCollectionStatus.UNREACHABLE.value,
        ),
    }
    report = engine.analyze_network_routing(
        collections,
        device_ips={"dev_a": ["10.0.12.1"], "dev_b": ["10.0.12.2"]},
        device_oper_states={"dev_a": "online", "dev_b": "offline"},
        source_device="dev_a",
        destination="8.8.8.8",
    )
    assert "dev_b" in report.unavailable_devices
    assert "dev_b" in report.incomplete_devices
    itypes = {i.inconsistency_type for i in report.inconsistencies}
    assert CrossDeviceInconsistencyType.ROUTE_POINTING_TO_UNAVAILABLE_NEXT_HOP.value in itypes
    assert report.path_evaluation["state"] == PathResultState.PATH_PARTIAL.value
    assert report.topology_overlay["segments"][0]["overlay_segment_type"] == OverlaySegmentType.ROUTE_UNCERTAINTY.value


def test_scenario_i_conflicting_topology_and_loop_and_conflicts():
    """Scenario I: Route egress port contradicts confirmed TopologyEdge + routing loop & prefix conflict checks."""
    engine = CrossDeviceRouteIntelligenceEngine()
    collections = {
        "dev_a": _col("dev_a", [
            _r("dev_a", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.1", connect=True),
            _r("dev_a", "10.255.9.9/32", iface="lo", pref_src="10.255.9.9", connect=True),
            _r("dev_a", "0.0.0.0/0", "10.0.12.2", iface="ether1", distance=1, static=True),
            _r("dev_a", "0.0.0.0/0", "10.0.12.2", iface="ether1", distance=5, static=True),
            _r("dev_a", "10.77.0.0/24", "10.0.12.2", iface="ether1", static=True),
            _r("dev_a", "10.66.0.0/24", "10.0.12.2", iface="ether1", static=True),
        ]),
        "dev_b": _col("dev_b", [
            _r("dev_b", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.2", connect=True),
            _r("dev_b", "10.255.9.9/32", iface="lo", pref_src="10.255.9.9", connect=True),  # Duplicate /32!
            _r("dev_b", "10.77.0.0/24", "10.0.12.1", iface="ether1", static=True),  # Loop back to dev_a!
            _r("dev_b", "10.66.0.0/24", "10.0.23.2", active=False, disabled=True, static=True),  # Disabled on peer!
        ]),
        "dev_c": _col("dev_c", [
            _r("dev_c", "10.0.99.0/30", iface="ether1", pref_src="10.0.99.2", connect=True),
        ]),
    }
    # TopologyEdge says dev_a:ether1 is physically wired to dev_c, NOT dev_b!
    topo_edges = [{
        "id": "edge_ac_conflict",
        "source_node_id": "dev_a",
        "target_node_id": "dev_c",
        "source_interface": "ether1",
        "target_interface": "ether1",
        "relationship_class": "PHYSICAL_ADJACENCY",
        "confidence_tier": "confirmed",
        "oper_status": "up",
    }]
    report = engine.analyze_network_routing(
        collections,
        topology_edges=topo_edges,
        source_device="dev_a",
        destination="10.77.0.1",
    )
    assert any(vr.verification_state == "TOPOLOGY_CONFLICT" for vr in report.verified_relationships)
    itypes = {i.inconsistency_type for i in report.inconsistencies}
    assert CrossDeviceInconsistencyType.UNEXPECTED_PATH_DIVERGENCE.value in itypes
    assert CrossDeviceInconsistencyType.POTENTIAL_ROUTING_LOOP.value in itypes
    assert CrossDeviceInconsistencyType.CONFLICTING_DESTINATION_PREFIXES.value in itypes
    assert CrossDeviceInconsistencyType.UNEXPECTED_DEFAULT_ROUTE.value in itypes
    assert CrossDeviceInconsistencyType.INCONSISTENT_ROUTE_STATE_ACROSS_CONNECTED_DEVICES.value in itypes


def test_scenario_j_vrf_separation_and_anti_fabrication():
    """Scenario J: VRF mismatch detection + shared external default gateway NEVER fabricates router-to-router link."""
    engine = CrossDeviceRouteIntelligenceEngine()
    collections = {
        "dev_a": _col("dev_a", [
            _r("dev_a", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.1", connect=True),
            _r("dev_a", "0.0.0.0/0", "203.0.113.1", iface="ether4-wan", static=True),
            _r("dev_a", "10.100.0.0/24", "10.0.12.2", iface="ether1", table="main", static=True),
        ]),
        "dev_b": _col("dev_b", [
            _r("dev_b", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.2", connect=True),
            _r("dev_b", "0.0.0.0/0", "203.0.113.1", iface="ether4-wan", static=True),  # Same ISP GW!
            # Route exists ONLY in vrf_corp on dev_b, NOT in main!
            _r("dev_b", "10.100.0.0/24", iface="vlan100", pref_src="10.100.0.1", table="vrf_corp", connect=True),
        ]),
    }
    report = engine.analyze_network_routing(
        collections,
        source_device="dev_a",
        destination="10.100.0.10",
        routing_table="main",
    )
    itypes = {i.inconsistency_type for i in report.inconsistencies}
    assert CrossDeviceInconsistencyType.INCORRECT_VRF_ASSOCIATION.value in itypes

    # Shared external gateway 203.0.113.1 MUST NOT create a link between dev_a and dev_b
    isp_rels = [vr for vr in report.verified_relationships if vr.gateway_ip == "203.0.113.1"]
    assert len(isp_rels) == 2
    assert all(vr.target_device_id is None and vr.is_physical_adjacency is False for vr in isp_rels)


def test_cross_device_api_and_non_destructive_topology_overlay(tmp_path, monkeypatch):
    """Verifies POST /api/intelligence/routes/cross-device and GET /api/topology/route-overlay without mutating TopologyEngine."""
    import api.routers.topology as topo_router
    import core.topology_engine as tengine
    import core.routing.route_collector as rcol_mod
    import core.routing.route_history as rhist_mod
    from api.main import app
    from api.routers.topology import require_topology_admin

    db_file = tmp_path / "test_wp465.db"
    topo_eng = tengine.TopologyEngine(db_path=db_file)
    topo_eng.upsert_node("dev_a", name="Router-A", ip="10.0.12.1")
    topo_eng.upsert_node("dev_b", name="Router-B", ip="10.0.12.2")
    hist_store = rhist_mod.RouteHistoryStore(db_file)

    dummy_col = rcol_mod.MultiDeviceRouteCollector()
    dummy_col._latest_results["dev_a"] = _col("dev_a", [
        _r("dev_a", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.1", connect=True),
        _r("dev_a", "10.20.0.0/24", "10.0.12.2", iface="ether1", static=True),
    ])
    dummy_col._latest_results["dev_b"] = _col("dev_b", [
        _r("dev_b", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.2", connect=True),
        _r("dev_b", "10.20.0.0/24", iface="ether2", pref_src="10.20.0.1", connect=True),
    ])

    monkeypatch.setattr(tengine, "get_topology_engine", lambda: topo_eng)
    monkeypatch.setattr(topo_router, "get_topology_engine", lambda: topo_eng)
    monkeypatch.setattr(rcol_mod, "get_route_collector", lambda: dummy_col)
    monkeypatch.setattr(rhist_mod, "get_route_history_store", lambda db_path=None: hist_store)
    app.dependency_overrides[require_topology_admin] = lambda: "admin_tester"

    try:
        from tests.auth_helper import get_test_auth_headers
        client = TestClient(app, headers=get_test_auth_headers())
        edges_before = len(topo_eng.get_topology().get("edges", []))

        r1 = client.post(
            "/api/intelligence/routes/cross-device",
            json={"source_device": "dev_a", "destination": "10.20.0.5", "routing_table": "main"},
        )
        assert r1.status_code == 200
        body1 = r1.json()
        assert body1["success"] is True
        assert body1["report"]["path_evaluation"]["state"] == PathResultState.PATH_INFERRED.value

        r2 = client.get(
            "/api/topology/route-overlay",
            params={"source_device": "dev_a", "destination": "10.20.0.5", "routing_table": "main"},
        )
        assert r2.status_code == 200
        body2 = r2.json()
        assert body2["overlay"]["mutates_physical_topology"] is False
        assert body2["overlay"]["segments_count"] == 2

        # Confirm zero physical/topology edges were fabricated in TopologyEngine!
        edges_after = len(topo_eng.get_topology().get("edges", []))
        assert edges_after == edges_before
    finally:
        app.dependency_overrides.pop(require_topology_admin, None)
