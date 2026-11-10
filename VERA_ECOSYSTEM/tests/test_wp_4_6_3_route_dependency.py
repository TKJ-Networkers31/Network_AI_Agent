"""
WP 4.6.3 Verification Suite — Route Dependency & Recursive Failure Propagation.

Covers all 12 mandatory Section 7.5 scenarios plus REST API contract and
zero-fabricated-physical-link invariants.
"""

from __future__ import annotations

import time
from typing import Dict, List

import pytest
from fastapi.testclient import TestClient

from core.routing.route_collector import (
    RouteCollectionResult,
    RouteCollectionStatus,
    RouteCompleteness,
)
from core.routing.route_dependency import (
    DependencyNodeType,
    DependencyRelationType,
    DependencyResolutionState,
    FailurePropagationAnalyzer,
    HypotheticalFailureType,
    RouteDependencyAnalyzer,
)
from core.routing.unified_route_parser import NormalizedRoute
from core.topology_engine import TopologyEngine


def _mk_route(
    dst_prefix: str,
    gateway: str = "",
    *,
    device_id: str = "dev_a",
    routing_table: str = "main",
    protocol: str = "static",
    distance: int = 1,
    active: bool = True,
    disabled: bool = False,
    connect: bool = False,
    unreachable: bool = False,
    interface_name: str = "",
    pref_src: str = "",
    gateways: List[str] | None = None,
) -> NormalizedRoute:
    p_len = int(dst_prefix.split("/")[1]) if "/" in dst_prefix else 32
    return NormalizedRoute(
        device_id=device_id,
        routing_table=routing_table,
        dst_prefix=dst_prefix,
        prefix_len=p_len,
        gateway=gateway,
        gateways=list(gateways) if gateways is not None else ([gateway] if gateway else []),
        interface_name=interface_name or (gateway if connect else ""),
        pref_src=pref_src,
        protocol=protocol,
        distance=distance,
        active=active,
        disabled=disabled,
        connect=connect,
        static=(protocol == "static"),
        dynamic=(protocol != "static"),
        unreachable=unreachable,
    )


def _mk_col(
    device_id: str,
    routes: List[NormalizedRoute],
    *,
    completeness: str = RouteCompleteness.COMPLETE.value,
    evidence_id: str = "",
) -> RouteCollectionResult:
    tables = sorted({r.routing_table or "main" for r in routes}) or ["main"]
    return RouteCollectionResult(
        device_id=device_id,
        device_identity=device_id.upper(),
        status=RouteCollectionStatus.SUCCESS.value,
        completeness=completeness,
        collected_at=time.time(),
        routes=routes,
        routing_tables=tables,
        evidence_id=evidence_id or f"ev_{device_id}",
    )


def test_01_direct_gateway_resolution():
    analyzer = RouteDependencyAnalyzer()
    r_conn = _mk_route("10.0.12.0/30", "ether1", connect=True, protocol="connected", distance=0, interface_name="ether1")
    r_def = _mk_route("0.0.0.0/0", "10.0.12.2")
    res = analyzer.resolve_single_route("dev_a", r_def, [r_conn, r_def], ip_owner_map={"10.0.12.2": ["dev_b"]})

    assert res.state == DependencyResolutionState.DIRECTLY_CONNECTED.value
    assert res.max_depth_reached == 1
    assert res.resolved_egress_interfaces == ["ether1"]
    assert res.resolved_immediate_gateways == ["10.0.12.2"]
    assert res.upstream_device_ids == ["dev_b"]
    assert not res.cycle_detected


def test_02_recursive_gateway_resolution():
    analyzer = RouteDependencyAnalyzer()
    r_conn = _mk_route("10.0.12.0/30", "ether1", connect=True, protocol="connected", distance=0, interface_name="ether1")
    r_transit = _mk_route("8.8.8.8/32", "10.0.12.2")
    r_rec = _mk_route("0.0.0.0/0", "8.8.8.8")

    res = analyzer.resolve_single_route("dev_a", r_rec, [r_conn, r_transit, r_rec], ip_owner_map={"10.0.12.2": ["dev_b"]})
    assert res.state == DependencyResolutionState.RECURSIVE_RESOLVED.value
    assert res.max_depth_reached == 2
    assert res.resolved_egress_interfaces == ["ether1"]
    assert res.resolved_immediate_gateways == ["10.0.12.2"]
    assert res.upstream_device_ids == ["dev_b"]


def test_03_multiple_recursion_levels():
    analyzer = RouteDependencyAnalyzer()
    routes = [
        _mk_route("10.0.12.0/30", "ether1", connect=True, protocol="connected", distance=0, interface_name="ether1"),
        _mk_route("172.16.10.0/24", "10.0.12.2"),
        _mk_route("192.0.2.0/24", "172.16.10.1"),
        _mk_route("198.51.100.0/24", "192.0.2.1"),
    ]
    res = analyzer.resolve_single_route("dev_a", routes[-1], routes)
    assert res.state == DependencyResolutionState.RECURSIVE_RESOLVED.value
    assert res.max_depth_reached == 3
    assert res.resolved_egress_interfaces == ["ether1"]
    assert res.visited_gateways == ["192.0.2.1", "172.16.10.1", "10.0.12.2"]
    assert len(res.evidence_chain) >= 4


def test_04_loop_detection():
    analyzer = RouteDependencyAnalyzer()
    r_a = _mk_route("10.1.0.0/16", "10.2.0.1")
    r_b = _mk_route("10.2.0.0/16", "10.1.0.1")
    res = analyzer.resolve_single_route("dev_a", r_a, [r_a, r_b])

    assert res.state == DependencyResolutionState.CYCLE_DETECTED.value
    assert res.cycle_detected is True
    assert any(step.get("event") in ("CYCLE_DETECTED", "ROUTE_CYCLE_DETECTED") for step in res.evidence_chain)


def test_05_depth_limit_enforcement():
    analyzer = RouteDependencyAnalyzer()
    routes = [
        _mk_route("10.0.0.0/30", "ether1", connect=True, protocol="connected", distance=0, interface_name="ether1"),
        _mk_route("10.1.0.0/24", "10.0.0.2"),
        _mk_route("10.2.0.0/24", "10.1.0.1"),
        _mk_route("10.3.0.0/24", "10.2.0.1"),
        _mk_route("10.4.0.0/24", "10.3.0.1"),
        _mk_route("10.5.0.0/24", "10.4.0.1"),
    ]
    res = analyzer.resolve_single_route("dev_a", routes[-1], routes, max_depth=3)
    assert res.state == DependencyResolutionState.DEPTH_LIMIT_EXCEEDED.value
    assert any(step.get("event") == "DEPTH_LIMIT_EXCEEDED" for step in res.evidence_chain)


def test_06_unreachable_and_missing_gateway():
    analyzer = RouteDependencyAnalyzer()
    r_unreach = _mk_route("10.88.0.0/16", "192.168.254.1", active=False, unreachable=True)
    res_u = analyzer.resolve_single_route("dev_a", r_unreach, [r_unreach])
    assert res_u.state == DependencyResolutionState.GATEWAY_UNREACHABLE.value

    r_missing = _mk_route("10.99.0.0/16", "203.0.113.99", active=True)
    res_m = analyzer.resolve_single_route("dev_a", r_missing, [r_missing])
    assert res_m.state == DependencyResolutionState.UNRESOLVED_MISSING_ROUTE.value


def test_07_multiple_possible_gateway_routes():
    analyzer = RouteDependencyAnalyzer()
    routes = [
        _mk_route("10.0.1.0/30", "ether1", connect=True, protocol="connected", distance=0, interface_name="ether1"),
        _mk_route("10.0.2.0/30", "ether2", connect=True, protocol="connected", distance=0, interface_name="ether2"),
        # Equal-preference ECMP resolvers for 172.20.0.1
        _mk_route("172.20.0.0/24", "10.0.1.2", protocol="ospf", distance=110),
        _mk_route("172.20.0.0/24", "10.0.2.2", protocol="ospf", distance=110),
        # Lower-preference supernet/floating backup for 172.20.0.1
        _mk_route("172.20.0.0/16", "10.0.2.2", protocol="static", distance=200),
        _mk_route("198.51.100.0/24", "172.20.0.1"),
    ]
    res = analyzer.resolve_single_route("dev_a", routes[-1], routes)
    assert res.state == DependencyResolutionState.MULTI_PATH_RESOLVED.value
    assert set(res.resolved_egress_interfaces) == {"ether1", "ether2"}
    assert len(res.alternative_gateway_routes) == 1
    assert res.alternative_gateway_routes[0]["dst_prefix"] == "172.20.0.0/16"


def test_08_missing_device_and_unknown_dependencies():
    dep_analyzer = RouteDependencyAnalyzer()
    prop_analyzer = FailurePropagationAnalyzer(dep_analyzer)

    col_a = _mk_col("dev_a", [
        _mk_route("10.0.12.0/30", "ether1", device_id="dev_a", connect=True, protocol="connected", distance=0, interface_name="ether1", pref_src="10.0.12.1"),
        _mk_route("0.0.0.0/0", "10.0.12.2", device_id="dev_a"),
    ])
    # dev_b and dev_c are registered in inventory, but neither has collected routes!
    graph = dep_analyzer.build_dependency_graph({"dev_a": col_a})
    assert any(n.node_id == "upstream:unresolved:10.0.12.2" and not n.resolved for n in graph.nodes.values())

    report = prop_analyzer.analyze_failure(
        HypotheticalFailureType.INTERFACE_DOWN.value,
        {"dev_a": col_a},
        device_id="dev_a",
        interface_name="ether1",
        known_registered_device_ids=["dev_a", "dev_b", "dev_c"],
    )
    unknown_ids = {u["device_id"] for u in report.unknown_dependencies}
    assert {"dev_b", "dev_c"}.issubset(unknown_ids)
    # Crucial invariant: uncollected devices dev_b and dev_c are NEVER claimed affected!
    affected_devs = {a["device_id"] for a in report.potentially_affected_destinations}
    assert "dev_b" not in affected_devs
    assert "dev_c" not in affected_devs


def test_09_interface_dependency_blast_radius():
    prop = FailurePropagationAnalyzer()
    col_a = _mk_col("dev_a", [
        _mk_route("10.0.12.0/30", "ether1", device_id="dev_a", connect=True, protocol="connected", distance=0, interface_name="ether1"),
        _mk_route("192.168.10.0/24", "bridge-lan", device_id="dev_a", connect=True, protocol="connected", distance=0, interface_name="bridge-lan"),
        _mk_route("172.16.0.0/16", "10.0.12.2", device_id="dev_a"),
        _mk_route("0.0.0.0/0", "172.16.1.1", device_id="dev_a"),  # Recursive via 172.16.0.0/16 -> ether1!
    ])
    rep = prop.analyze_failure(
        HypotheticalFailureType.INTERFACE_DOWN.value,
        {"dev_a": col_a},
        device_id="dev_a",
        interface_name="ether1",
    )
    direct_pfxs = {d["dst_prefix"] for d in rep.direct_dependencies}
    indirect_pfxs = {d["dst_prefix"] for d in rep.indirect_dependencies}
    assert "10.0.12.0/30" in direct_pfxs
    assert "172.16.0.0/16" in direct_pfxs
    assert "0.0.0.0/0" in indirect_pfxs
    assert "192.168.10.0/24" not in direct_pfxs | indirect_pfxs


def test_10_upstream_default_route_dependency_propagation():
    """3-router chain: dev_a -> dev_b -> dev_c -> Internet (0.0.0.0/0)."""
    prop = FailurePropagationAnalyzer()
    collections: Dict[str, RouteCollectionResult] = {
        "dev_a": _mk_col("dev_a", [
            _mk_route("10.0.12.0/30", "ether1", device_id="dev_a", connect=True, protocol="connected", distance=0, interface_name="ether1", pref_src="10.0.12.1"),
            _mk_route("0.0.0.0/0", "10.0.12.2", device_id="dev_a"),
        ]),
        "dev_b": _mk_col("dev_b", [
            _mk_route("10.0.12.0/30", "ether2", device_id="dev_b", connect=True, protocol="connected", distance=0, interface_name="ether2", pref_src="10.0.12.2"),
            _mk_route("10.0.23.0/30", "ether1", device_id="dev_b", connect=True, protocol="connected", distance=0, interface_name="ether1", pref_src="10.0.23.1"),
            _mk_route("0.0.0.0/0", "10.0.23.2", device_id="dev_b"),
        ]),
        "dev_c": _mk_col("dev_c", [
            _mk_route("10.0.23.0/30", "ether2", device_id="dev_c", connect=True, protocol="connected", distance=0, interface_name="ether2", pref_src="10.0.23.2"),
            _mk_route("203.0.113.0/30", "ether1-wan", device_id="dev_c", connect=True, protocol="connected", distance=0, interface_name="ether1-wan", pref_src="203.0.113.2"),
            _mk_route("0.0.0.0/0", "203.0.113.1", device_id="dev_c"),
        ]),
    }

    rep = prop.analyze_failure(
        HypotheticalFailureType.UPSTREAM_DEFAULT_ROUTE_LOSS.value,
        collections,
        device_id="dev_c",
    )
    assert len(rep.direct_dependencies) == 1
    assert rep.direct_dependencies[0]["device_id"] == "dev_c"
    indirect_devs = {d["device_id"] for d in rep.indirect_dependencies}
    assert indirect_devs == {"dev_b", "dev_a"}
    assert rep.confidence_label == "HIGH"


def test_11_failure_propagation_remaining_scenarios():
    prop = FailurePropagationAnalyzer()
    collections = {
        "dev_a": _mk_col("dev_a", [
            _mk_route("10.0.12.0/30", "ether1", device_id="dev_a", connect=True, protocol="connected", distance=0, interface_name="ether1", pref_src="10.0.12.1"),
            _mk_route("10.0.13.0/30", "ether2", device_id="dev_a", connect=True, protocol="connected", distance=0, interface_name="ether2", pref_src="10.0.13.1"),
            _mk_route("172.16.0.0/16", "10.0.12.2", device_id="dev_a"),
            _mk_route("198.51.100.0/24", "172.16.1.1", device_id="dev_a"),
            _mk_route("10.50.0.0/24", "10.0.12.2,10.0.13.2", device_id="dev_a", gateways=["10.0.12.2", "10.0.13.2"]),
            _mk_route("10.90.0.0/24", "10.0.12.2", device_id="dev_a", routing_table="vrf_blue"),
        ]),
        "dev_b": _mk_col("dev_b", [
            _mk_route("10.0.12.0/30", "ether1", device_id="dev_b", connect=True, protocol="connected", distance=0, interface_name="ether1", pref_src="10.0.12.2"),
            _mk_route("172.16.0.0/16", "bridge-srv", device_id="dev_b", connect=True, protocol="connected", distance=0, interface_name="bridge-srv", pref_src="172.16.0.1"),
        ]),
    }

    # GATEWAY_UNREACHABLE
    r_gw = prop.analyze_failure(HypotheticalFailureType.GATEWAY_UNREACHABLE.value, collections, gateway_ip="10.0.12.2")
    assert any(d["dst_prefix"] == "172.16.0.0/16" for d in r_gw.direct_dependencies)
    assert any(d["dst_prefix"] == "198.51.100.0/24" for d in r_gw.indirect_dependencies)

    # INTERMEDIATE_ROUTER_UNAVAILABLE
    r_ir = prop.analyze_failure(HypotheticalFailureType.INTERMEDIATE_ROUTER_UNAVAILABLE.value, collections, device_id="dev_b")
    assert any(d["device_id"] == "dev_a" for d in r_ir.direct_dependencies + r_ir.indirect_dependencies)

    # MISSING_ROUTE
    r_mr = prop.analyze_failure(HypotheticalFailureType.MISSING_ROUTE.value, collections, device_id="dev_a", dst_prefix="172.16.0.0/16")
    assert any(d["dst_prefix"] == "172.16.0.0/16" for d in r_mr.direct_dependencies)
    assert any(d["dst_prefix"] == "198.51.100.0/24" for d in r_mr.indirect_dependencies)

    # ROUTING_TABLE_MISMATCH
    r_vrf = prop.analyze_failure(HypotheticalFailureType.ROUTING_TABLE_MISMATCH.value, collections, device_id="dev_a", routing_table="vrf_blue")
    assert len(r_vrf.direct_dependencies) == 1
    assert r_vrf.direct_dependencies[0]["dst_prefix"] == "10.90.0.0/24"

    # RECURSIVE_NEXT_HOP_FAILURE
    r_rec = prop.analyze_failure(HypotheticalFailureType.RECURSIVE_NEXT_HOP_FAILURE.value, collections, device_id="dev_a")
    assert any(d["dst_prefix"] == "198.51.100.0/24" for d in r_rec.direct_dependencies)

    # ECMP_BRANCH_LOSS
    r_ecmp = prop.analyze_failure(HypotheticalFailureType.ECMP_BRANCH_LOSS.value, collections, device_id="dev_a", gateway_ip="10.0.12.2")
    assert any(d["dst_prefix"] == "10.50.0.0/24" for d in r_ecmp.direct_dependencies)
    assert any(a["alternative_gateway"] == "10.0.13.2" for a in r_ecmp.alternative_paths)


def test_12_alternative_branches_api_and_zero_fabricated_topology_edges(tmp_path, monkeypatch):
    topo_db = tmp_path / "isolated_topo.db"
    engine = TopologyEngine(db_path=topo_db)
    edges_before = len(engine.get_topology().get("edges", []))

    col_a = _mk_col("dev_chr", [
        _mk_route("10.0.12.0/30", "ether1", device_id="dev_chr", connect=True, protocol="connected", distance=0, interface_name="ether1", pref_src="10.0.12.1"),
        _mk_route("10.0.13.0/30", "ether2", device_id="dev_chr", connect=True, protocol="connected", distance=0, interface_name="ether2", pref_src="10.0.13.1"),
        _mk_route("0.0.0.0/0", "10.0.12.2", device_id="dev_chr", distance=1, active=True),
        _mk_route("0.0.0.0/0", "10.0.13.2", device_id="dev_chr", distance=10, active=False),
    ])

    dep_analyzer = RouteDependencyAnalyzer()
    graph = dep_analyzer.build_dependency_graph({"dev_chr": col_a})
    g_dict = graph.to_dict()

    assert g_dict["semantic_domain"] == "ROUTE_DEPENDENCY"
    assert g_dict["persisted_as_topology_edges"] is False
    assert len(g_dict["alternative_branches"]) == 1
    assert g_dict["alternative_branches"][0]["alternative_gateway"] == "10.0.13.2"

    # Distinct typed relationship edges (not a single generic edge type!)
    rel_types = {e["relation_type"] for e in g_dict["edges"]}
    assert DependencyRelationType.OWNED_BY_DEVICE.value in rel_types
    assert DependencyRelationType.IN_ROUTING_TABLE.value in rel_types
    assert DependencyRelationType.DEPENDS_ON_NEXT_HOP.value in rel_types
    assert DependencyRelationType.USES_GATEWAY_IP.value in rel_types
    assert DependencyRelationType.ALTERNATIVE_CANDIDATE_FOR_PREFIX.value in rel_types

    # Verify TopologyEngine was NOT polluted with physical links
    edges_after = len(engine.get_topology().get("edges", []))
    assert edges_after == edges_before == 0

    # Verify FastAPI endpoints
    from api.main import app
    from api.routers.topology import require_topology_admin
    from core.routing import route_collector

    dummy_collector = route_collector.MultiDeviceRouteCollector()
    dummy_collector._latest_results["dev_chr"] = col_a
    monkeypatch.setattr(route_collector, "get_route_collector", lambda: dummy_collector)
    app.dependency_overrides[require_topology_admin] = lambda: {"role": "admin"}

    try:
        from tests.auth_helper import get_test_auth_headers
        client = TestClient(app, headers=get_test_auth_headers())
        resp_g = client.get("/api/intelligence/routes/dependencies?device_id=dev_chr")
        assert resp_g.status_code == 200
        assert resp_g.json()["dependency_graph"]["semantic_domain"] == "ROUTE_DEPENDENCY"

        resp_imp = client.post(
            "/api/intelligence/routes/failure-impact",
            json={
                "failure_type": "GATEWAY_UNREACHABLE",
                "device_id": "dev_chr",
                "gateway_ip": "10.0.12.2",
            },
        )
        assert resp_imp.status_code == 200
        imp = resp_imp.json()["impact"]
        assert imp["potentially_affected_destinations"][0]["impact_state"] == "DEGRADED_REROUTED_VIA_ALTERNATIVE"
    finally:
        app.dependency_overrides.pop(require_topology_admin, None)
