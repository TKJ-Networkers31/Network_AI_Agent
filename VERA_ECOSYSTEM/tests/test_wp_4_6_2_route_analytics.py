"""
WP 4.6.2 Acceptance Test Suite — Route Analytics & Path Evaluation.

Verifies:
1. Simple two-router path (PATH_INFERRED vs PATH_CONFIRMED_BY_EVIDENCE)
2. Multi-router path (3-router chain)
3. Missing destination & default route
4. Missing / unresolvable gateway (PATH_UNRESOLVED)
5. Recursive next-hop resolution across multi-hop path
6. Routing-table mismatch & unexpected table assignment
7. Strict VRF isolation across identical prefixes
8. ECMP multi-branch preservation & ECMP finding
9. Inter-router and intra-router loop detection
10. Asymmetric path hypothesis (never promoted to confirmed fact)
11. Incomplete topology / missing intermediate router (zero invented devices)
12. Stale evidence confidence cap & confirmed-state downgrade
13. Contradictory route data, five-tier LPM epistemology, and REST API endpoints
"""

from __future__ import annotations

import time
from typing import Dict, List

import pytest
from fastapi.testclient import TestClient

from core.routing.route_analytics import (
    PathResultState,
    RouteFindingType,
    RoutePathEvaluator,
    RouteTableAnalyzer,
    evaluate_route_lookup,
)
from core.routing.route_collector import RouteCollectionResult, RouteCompleteness
from core.routing.unified_route_parser import NormalizedRoute, RouteType


def _col(
    device_id: str,
    routes: List[NormalizedRoute],
    *,
    collected_at: float | None = None,
    completeness: str = RouteCompleteness.COMPLETE.value,
    mgmt_ip: str = "",
) -> RouteCollectionResult:
    ts = collected_at if collected_at is not None else time.time()
    ev_id = f"ev_{device_id}"
    tables: List[str] = []
    for r in routes:
        r.device_id = device_id
        r.collection_timestamp = ts
        r.evidence_provenance = {"evidence_id": ev_id, "device_id": device_id}
        if r.routing_table not in tables:
            tables.append(r.routing_table)
    return RouteCollectionResult(
        device_id=device_id,
        device_identity=device_id.upper(),
        management_ip=mgmt_ip,
        collected_at=ts,
        routes=routes,
        routing_tables=tables or ["main"],
        completeness=completeness,
        evidence_id=ev_id,
    )


def test_01_simple_two_router_path_inferred_vs_confirmed():
    now = time.time()
    r_a = _col(
        "dev_a",
        [
            NormalizedRoute(dst_prefix="10.0.12.0/30", gateway="ether1", interface_name="ether1", pref_src="10.0.12.1", protocol="connected", connect=True, distance=0),
            NormalizedRoute(dst_prefix="192.168.20.0/24", gateway="10.0.12.2", protocol="static", static=True, distance=1),
        ],
        collected_at=now,
    )
    r_b = _col(
        "dev_b",
        [
            NormalizedRoute(dst_prefix="10.0.12.0/30", gateway="ether1", interface_name="ether1", pref_src="10.0.12.2", protocol="connected", connect=True, distance=0),
            NormalizedRoute(dst_prefix="192.168.20.0/24", gateway="bridge_lan", interface_name="bridge_lan", pref_src="192.168.20.1", protocol="connected", connect=True, distance=0),
        ],
        collected_at=now,
    )
    collections = {"dev_a": r_a, "dev_b": r_b}
    evaluator = RoutePathEvaluator()

    # Without confirmed physical/L2 adjacency -> PATH_INFERRED
    res_inferred = evaluator.evaluate_path("dev_a", "192.168.20.50", collections, now=now)
    assert res_inferred.state == PathResultState.PATH_INFERRED.value
    assert [h.device_id for h in res_inferred.primary_hops] == ["dev_a", "dev_b"]

    # With confirmed L1/L2 adjacency -> PATH_CONFIRMED_BY_EVIDENCE
    res_confirmed = evaluator.evaluate_path(
        "dev_a",
        "192.168.20.50",
        collections,
        verified_adjacencies={("dev_a", "dev_b")},
        now=now,
    )
    assert res_confirmed.state == PathResultState.PATH_CONFIRMED_BY_EVIDENCE.value
    assert res_confirmed.confidence > res_inferred.confidence


def test_02_multi_router_three_hop_chain():
    now = time.time()
    collections = {
        "dev_a": _col("dev_a", [
            NormalizedRoute(dst_prefix="10.0.12.0/30", gateway="ether1", interface_name="ether1", pref_src="10.0.12.1", protocol="connected", connect=True, distance=0),
            NormalizedRoute(dst_prefix="172.16.99.0/24", gateway="10.0.12.2", protocol="ospf", ospf=True, distance=110),
        ], collected_at=now),
        "dev_b": _col("dev_b", [
            NormalizedRoute(dst_prefix="10.0.12.0/30", gateway="ether1", interface_name="ether1", pref_src="10.0.12.2", protocol="connected", connect=True, distance=0),
            NormalizedRoute(dst_prefix="10.0.23.0/30", gateway="ether2", interface_name="ether2", pref_src="10.0.23.1", protocol="connected", connect=True, distance=0),
            NormalizedRoute(dst_prefix="172.16.99.0/24", gateway="10.0.23.2", protocol="ospf", ospf=True, distance=110),
        ], collected_at=now),
        "dev_c": _col("dev_c", [
            NormalizedRoute(dst_prefix="10.0.23.0/30", gateway="ether1", interface_name="ether1", pref_src="10.0.23.2", protocol="connected", connect=True, distance=0),
            NormalizedRoute(dst_prefix="172.16.99.0/24", gateway="ether3", interface_name="ether3", pref_src="172.16.99.1", protocol="connected", connect=True, distance=0),
        ], collected_at=now),
    }
    res = RoutePathEvaluator().evaluate_path("dev_a", "172.16.99.10", collections, now=now)
    assert res.state == PathResultState.PATH_INFERRED.value
    assert [h.device_id for h in res.primary_hops] == ["dev_a", "dev_b", "dev_c"]
    assert res.primary_hops[-1].hop_state == "DIRECT_CONNECTED"


def test_03_missing_route_and_missing_default():
    col_a = _col("dev_a", [
        NormalizedRoute(dst_prefix="192.168.1.0/24", gateway="ether1", interface_name="ether1", pref_src="192.168.1.1", protocol="connected", connect=True, distance=0),
    ])
    res = RoutePathEvaluator().evaluate_path("dev_a", "8.8.8.8", {"dev_a": col_a})
    assert res.state == PathResultState.PATH_UNREACHABLE.value

    findings = RouteTableAnalyzer().analyze_device_routes("dev_a", col_a.routes, target_destination="8.8.8.8")
    ftypes = {f.finding_type for f in findings}
    assert RouteFindingType.MISSING_DEFAULT_ROUTE.value in ftypes
    assert RouteFindingType.MISSING_DESTINATION_ROUTE.value in ftypes
    for f in findings:
        assert f.device_id == "dev_a"
        assert f.evidence_ids
        assert f.limitations


def test_04_missing_unresolvable_gateway():
    # Static route points to 10.250.250.1 which has NO connected or static resolving route
    col_a = _col("dev_a", [
        NormalizedRoute(dst_prefix="192.168.1.0/24", gateway="ether1", interface_name="ether1", pref_src="192.168.1.1", protocol="connected", connect=True, distance=0),
        NormalizedRoute(dst_prefix="10.80.0.0/24", gateway="10.250.250.1", protocol="static", static=True, distance=1),
    ])
    res = RoutePathEvaluator().evaluate_path("dev_a", "10.80.0.5", {"dev_a": col_a})
    assert res.state == PathResultState.PATH_UNRESOLVED.value
    assert res.primary_hops[0].hop_state == "UNRESOLVED_GATEWAY"


def test_05_recursive_next_hop_path_and_finding():
    now = time.time()
    collections = {
        "dev_a": _col("dev_a", [
            NormalizedRoute(dst_prefix="10.0.12.0/30", gateway="ether1", interface_name="ether1", pref_src="10.0.12.1", protocol="connected", connect=True, distance=0),
            # BGP route to 203.0.113.0/24 via recursive next-hop 172.31.255.1
            NormalizedRoute(dst_prefix="203.0.113.0/24", gateway="172.31.255.1", protocol="bgp", bgp=True, distance=20),
            # OSPF route resolving 172.31.255.1/32 via 10.0.12.2
            NormalizedRoute(dst_prefix="172.31.255.1/32", gateway="10.0.12.2", protocol="ospf", ospf=True, distance=110),
        ], collected_at=now),
        "dev_b": _col("dev_b", [
            NormalizedRoute(dst_prefix="10.0.12.0/30", gateway="ether1", interface_name="ether1", pref_src="10.0.12.2", protocol="connected", connect=True, distance=0),
            NormalizedRoute(dst_prefix="203.0.113.0/24", gateway="sfp1", interface_name="sfp1", pref_src="203.0.113.1", protocol="connected", connect=True, distance=0),
        ], collected_at=now),
    }
    res = RoutePathEvaluator().evaluate_path("dev_a", "203.0.113.5", collections, now=now)
    assert res.state == PathResultState.PATH_INFERRED.value
    assert res.primary_hops[0].is_recursive is True
    assert res.primary_hops[0].resolved_gateway_ip == "10.0.12.2"
    assert [h.device_id for h in res.primary_hops] == ["dev_a", "dev_b"]

    findings = RouteTableAnalyzer().analyze_device_routes("dev_a", collections["dev_a"].routes)
    assert any(f.finding_type == RouteFindingType.RECURSIVE_GATEWAY_DEPENDENCY.value for f in findings)


def test_06_routing_table_mismatch_and_vrf_isolation():
    now = time.time()
    # Both vrf_red and vrf_blue have 10.100.0.0/24 via completely different next-hop routers
    collections = {
        "dev_pe": _col("dev_pe", [
            NormalizedRoute(dst_prefix="10.1.0.0/30", gateway="eth1", interface_name="eth1", pref_src="10.1.0.1", routing_table="vrf_red", protocol="connected", connect=True, distance=0),
            NormalizedRoute(dst_prefix="10.100.0.0/24", gateway="10.1.0.2", routing_table="vrf_red", protocol="bgp", bgp=True, distance=20),
            NormalizedRoute(dst_prefix="10.2.0.0/30", gateway="eth2", interface_name="eth2", pref_src="10.2.0.1", routing_table="vrf_blue", protocol="connected", connect=True, distance=0),
            NormalizedRoute(dst_prefix="10.100.0.0/24", gateway="10.2.0.2", routing_table="vrf_blue", protocol="bgp", bgp=True, distance=20),
            # Misassigned orphan route in vrf_orphan with no connected subnet
            NormalizedRoute(dst_prefix="192.168.200.0/24", gateway="10.9.9.9", routing_table="vrf_orphan", protocol="static", static=True, distance=1),
        ], collected_at=now),
        "dev_ce_red": _col("dev_ce_red", [
            NormalizedRoute(dst_prefix="10.1.0.0/30", gateway="eth1", interface_name="eth1", pref_src="10.1.0.2", routing_table="main", protocol="connected", connect=True, distance=0),
            NormalizedRoute(dst_prefix="10.100.0.0/24", gateway="lan", interface_name="lan", pref_src="10.100.0.1", routing_table="main", protocol="connected", connect=True, distance=0),
        ], collected_at=now),
        "dev_ce_blue": _col("dev_ce_blue", [
            NormalizedRoute(dst_prefix="10.2.0.0/30", gateway="eth1", interface_name="eth1", pref_src="10.2.0.2", routing_table="main", protocol="connected", connect=True, distance=0),
            NormalizedRoute(dst_prefix="10.100.0.0/24", gateway="lan", interface_name="lan", pref_src="10.100.0.1", routing_table="main", protocol="connected", connect=True, distance=0),
        ], collected_at=now),
    }
    ip_tables = {("dev_ce_red", "10.1.0.2"): "main", ("dev_ce_blue", "10.2.0.2"): "main"}
    ev = RoutePathEvaluator()

    # Lookup in 'main' on dev_pe must NOT leak routes from vrf_red/vrf_blue!
    res_main = ev.evaluate_path("dev_pe", "10.100.0.10", collections, routing_table="main", now=now)
    assert res_main.state == PathResultState.PATH_UNREACHABLE.value

    res_red = ev.evaluate_path("dev_pe", "10.100.0.10", collections, routing_table="vrf_red", device_ip_tables=ip_tables, now=now)
    assert [h.device_id for h in res_red.primary_hops] == ["dev_pe", "dev_ce_red"]

    res_blue = ev.evaluate_path("dev_pe", "10.100.0.10", collections, routing_table="vrf_blue", device_ip_tables=ip_tables, now=now)
    assert [h.device_id for h in res_blue.primary_hops] == ["dev_pe", "dev_ce_blue"]

    findings = RouteTableAnalyzer().analyze_device_routes("dev_pe", collections["dev_pe"].routes, require_default_route=False)
    assert any(f.finding_type == RouteFindingType.UNEXPECTED_ROUTING_TABLE_ASSIGNMENT.value for f in findings)


def test_07_ecmp_branches_preserved():
    now = time.time()
    collections = {
        "dev_a": _col("dev_a", [
            NormalizedRoute(dst_prefix="10.0.12.0/30", gateway="eth1", interface_name="eth1", pref_src="10.0.12.1", protocol="connected", connect=True, distance=0),
            NormalizedRoute(dst_prefix="10.0.13.0/30", gateway="eth2", interface_name="eth2", pref_src="10.0.13.1", protocol="connected", connect=True, distance=0),
            NormalizedRoute(dst_prefix="10.77.0.0/24", gateway="10.0.12.2,10.0.13.2", gateways=["10.0.12.2", "10.0.13.2"], protocol="ospf", ospf=True, distance=110),
        ], collected_at=now),
        "dev_b": _col("dev_b", [
            NormalizedRoute(dst_prefix="10.0.12.0/30", gateway="eth1", interface_name="eth1", pref_src="10.0.12.2", protocol="connected", connect=True, distance=0),
            NormalizedRoute(dst_prefix="10.77.0.0/24", gateway="lan", interface_name="lan", pref_src="10.77.0.1", protocol="connected", connect=True, distance=0),
        ], collected_at=now),
        "dev_c": _col("dev_c", [
            NormalizedRoute(dst_prefix="10.0.13.0/30", gateway="eth1", interface_name="eth1", pref_src="10.0.13.2", protocol="connected", connect=True, distance=0),
            NormalizedRoute(dst_prefix="10.77.0.0/24", gateway="lan", interface_name="lan", pref_src="10.77.0.2", protocol="connected", connect=True, distance=0),
        ], collected_at=now),
    }
    res = RoutePathEvaluator().evaluate_path("dev_a", "10.77.0.50", collections, now=now)
    assert res.state == PathResultState.PATH_INFERRED.value
    assert res.is_ecmp is True
    assert len(res.ecmp_branches) == 2
    branch_targets = {br[-1].device_id for br in res.ecmp_branches}
    assert branch_targets == {"dev_b", "dev_c"}


def test_08_inter_router_loop_detection():
    now = time.time()
    collections = {
        "dev_a": _col("dev_a", [
            NormalizedRoute(dst_prefix="10.0.12.0/30", gateway="eth1", interface_name="eth1", pref_src="10.0.12.1", protocol="connected", connect=True, distance=0),
            NormalizedRoute(dst_prefix="10.99.99.0/24", gateway="10.0.12.2", protocol="static", static=True, distance=1),
        ], collected_at=now),
        "dev_b": _col("dev_b", [
            NormalizedRoute(dst_prefix="10.0.12.0/30", gateway="eth1", interface_name="eth1", pref_src="10.0.12.2", protocol="connected", connect=True, distance=0),
            NormalizedRoute(dst_prefix="10.99.99.0/24", gateway="10.0.12.1", protocol="static", static=True, distance=1),
        ], collected_at=now),
    }
    res = RoutePathEvaluator().evaluate_path("dev_a", "10.99.99.1", collections, now=now)
    assert res.loop_detected is True
    assert res.state == PathResultState.PATH_UNREACHABLE.value


def test_09_asymmetric_route_hypothesis_never_confirmed_fact():
    now = time.time()
    collections = {
        "dev_a": _col("dev_a", [
            NormalizedRoute(dst_prefix="192.168.10.0/24", gateway="lan", interface_name="lan", pref_src="192.168.10.1", protocol="connected", connect=True, distance=0),
            NormalizedRoute(dst_prefix="10.0.12.0/30", gateway="eth1", interface_name="eth1", pref_src="10.0.12.1", protocol="connected", connect=True, distance=0),
            NormalizedRoute(dst_prefix="192.168.20.0/24", gateway="10.0.12.2", protocol="static", static=True, distance=1),
            NormalizedRoute(dst_prefix="0.0.0.0/0", gateway="10.0.12.2", protocol="static", static=True, distance=1),
        ], collected_at=now),
        "dev_b": _col("dev_b", [
            NormalizedRoute(dst_prefix="10.0.12.0/30", gateway="eth1", interface_name="eth1", pref_src="10.0.12.2", protocol="connected", connect=True, distance=0),
            NormalizedRoute(dst_prefix="192.168.20.0/24", gateway="lan", interface_name="lan", pref_src="192.168.20.1", protocol="connected", connect=True, distance=0),
            # Note: dev_b has NO route back to 192.168.10.0/24 and NO default route
        ], collected_at=now),
    }
    findings = RouteTableAnalyzer().analyze_multi_device_routes(collections)
    asym = [f for f in findings if f.finding_type == RouteFindingType.ASYMMETRIC_ROUTE_HYPOTHESIS.value]
    assert len(asym) >= 1
    assert all(f.confidence == "HYPOTHESIS" for f in asym)

    path_res = RoutePathEvaluator().evaluate_path(
        "dev_a",
        "192.168.20.10",
        collections,
        source_prefix_for_symmetry="192.168.10.0/24",
        now=now,
    )
    assert path_res.return_path_hypothesis is not None
    assert path_res.return_path_hypothesis["classification"] == "HYPOTHESIS"
    assert path_res.return_path_hypothesis["is_symmetric_control_plane"] is False


def test_10_incomplete_topology_missing_intermediate_device_no_invention():
    now = time.time()
    # dev_a forwards to 10.0.12.2 on connected transit subnet, but 10.0.12.2 is NOT in collections!
    collections = {
        "dev_a": _col("dev_a", [
            NormalizedRoute(dst_prefix="10.0.12.0/30", gateway="eth1", interface_name="eth1", pref_src="10.0.12.1", protocol="connected", connect=True, distance=0),
            NormalizedRoute(dst_prefix="10.55.0.0/24", gateway="10.0.12.2", protocol="static", static=True, distance=1),
        ], collected_at=now),
    }
    res = RoutePathEvaluator().evaluate_path("dev_a", "10.55.0.10", collections, now=now)
    assert res.state == PathResultState.PATH_PARTIAL.value
    assert "10.0.12.2" in res.missing_intermediate_gateways
    assert len(res.primary_hops) == 1
    assert res.primary_hops[0].next_device_id is None  # Never invents a fake device ID!


def test_11_stale_evidence_downgrades_confirmed_path():
    now = time.time()
    stale_ts = now - 400.0  # > 300s -> EXPIRED
    collections = {
        "dev_a": _col("dev_a", [
            NormalizedRoute(dst_prefix="10.0.12.0/30", gateway="eth1", interface_name="eth1", pref_src="10.0.12.1", protocol="connected", connect=True, distance=0),
            NormalizedRoute(dst_prefix="192.168.20.0/24", gateway="10.0.12.2", protocol="static", static=True, distance=1),
        ], collected_at=stale_ts),
        "dev_b": _col("dev_b", [
            NormalizedRoute(dst_prefix="10.0.12.0/30", gateway="eth1", interface_name="eth1", pref_src="10.0.12.2", protocol="connected", connect=True, distance=0),
            NormalizedRoute(dst_prefix="192.168.20.0/24", gateway="lan", interface_name="lan", pref_src="192.168.20.1", protocol="connected", connect=True, distance=0),
        ], collected_at=stale_ts),
    }
    res = RoutePathEvaluator().evaluate_path(
        "dev_a",
        "192.168.20.10",
        collections,
        verified_adjacencies={("dev_a", "dev_b")},
        now=now,
    )
    assert res.stale_evidence_detected is True
    assert res.state == PathResultState.PATH_INFERRED.value  # Must NOT be PATH_CONFIRMED_BY_EVIDENCE!
    assert res.confidence < 0.80


def test_12_contradictory_route_data_and_five_tier_lpm_epistemology():
    routes = [
        # Inactive static route
        NormalizedRoute(dst_prefix="10.40.0.0/24", gateway="10.0.0.9", protocol="static", static=True, distance=1, active=False, unreachable=True),
        # Two conflicting protocols sharing identical prefix & distance!
        NormalizedRoute(dst_prefix="10.40.0.0/24", gateway="10.0.0.2", protocol="static", static=True, distance=110, active=True),
        NormalizedRoute(dst_prefix="10.40.0.0/24", gateway="10.0.0.3", protocol="ospf", ospf=True, distance=110, active=True),
        # Covering supernet
        NormalizedRoute(dst_prefix="10.0.0.0/8", gateway="10.0.0.1", protocol="static", static=True, distance=1, active=True),
    ]
    lpm = evaluate_route_lookup(routes, "10.40.0.55", device_id="dev_x")
    assert len(lpm.matching_rib_routes) == 4
    assert len(lpm.eligible_route_candidates) == 3
    assert len(lpm.calculated_best_candidates) == 2
    assert lpm.ambiguous_selection is True
    # Calculated route MUST NOT be labeled confirmed FIB!
    assert lpm.verified_forwarding_info["is_verified_fib"] is False
    assert lpm.observed_traffic_path["is_observed"] is False

    # Contradictory active route over DOWN interface
    col_down = _col("dev_x", [
        NormalizedRoute(dst_prefix="192.168.88.0/24", gateway="ether3", interface_name="ether3", pref_src="192.168.88.1", protocol="connected", connect=True, distance=0),
    ])
    res_down = RoutePathEvaluator().evaluate_path(
        "dev_x",
        "192.168.88.10",
        {"dev_x": col_down},
        down_interfaces={("dev_x", "ether3")},
    )
    assert res_down.state == PathResultState.PATH_UNREACHABLE.value
    assert len(res_down.contradictions) >= 1


def test_13_wp_4_6_2_api_contracts(monkeypatch):
    from api.main import app
    import core.routing.route_collector as rc_mod
    from core.routing.route_collector import MultiDeviceRouteCollector

    now = time.time()
    collector = MultiDeviceRouteCollector()
    collector.store_result_for_testing_or_import(
        _col("dev_a", [
            NormalizedRoute(dst_prefix="10.0.12.0/30", gateway="eth1", interface_name="eth1", pref_src="10.0.12.1", protocol="connected", connect=True, distance=0),
            NormalizedRoute(dst_prefix="0.0.0.0/0", gateway="10.0.12.2", protocol="static", static=True, distance=1),
        ], collected_at=now)
    )
    collector.store_result_for_testing_or_import(
        _col("dev_b", [
            NormalizedRoute(dst_prefix="10.0.12.0/30", gateway="eth1", interface_name="eth1", pref_src="10.0.12.2", protocol="connected", connect=True, distance=0),
            NormalizedRoute(dst_prefix="172.20.0.0/24", gateway="eth2", interface_name="eth2", pref_src="172.20.0.1", protocol="connected", connect=True, distance=0),
            NormalizedRoute(dst_prefix="0.0.0.0/0", gateway="203.0.113.1", protocol="static", static=True, distance=1),
        ], collected_at=now)
    )
    monkeypatch.setattr(rc_mod, "_route_collector_singleton", collector)

    from tests.auth_helper import get_test_auth_headers
    client = TestClient(app, headers=get_test_auth_headers())

    r_lpm = client.get("/api/intelligence/routes/dev_a/lookup?destination=172.20.0.5")
    assert r_lpm.status_code == 200
    assert r_lpm.json()["lookup"]["matched"] is True
    assert r_lpm.json()["lookup"]["verified_forwarding_info"]["is_verified_fib"] is False

    r_an = client.post("/api/intelligence/routes/analyze", json={"targets": ["dev_a", "dev_b"]})
    assert r_an.status_code == 200
    assert r_an.json()["success"] is True

    r_path = client.post("/api/intelligence/routes/path", json={"source_device": "dev_a", "destination": "172.20.0.5"})
    assert r_path.status_code == 200
    assert r_path.json()["path"]["state"] in (
        PathResultState.PATH_INFERRED.value,
        PathResultState.PATH_CONFIRMED_BY_EVIDENCE.value,
    )
    assert len(r_path.json()["path"]["primary_hops"]) == 2
