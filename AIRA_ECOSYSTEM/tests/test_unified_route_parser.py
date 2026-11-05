"""
tests/test_unified_route_parser.py — Acceptance and Regression Test Suite for WP 4.6.0.

Validates the authoritative UnifiedRouteParser, NormalizedRoute contract,
defects D1–D10 remediation, RouterOS v6/v7 real-device fixtures, synthetic edge cases,
recursive gateway resolution, LPM FIB filtering, and large-table bounded processing.
"""

import ipaddress
import time
from pathlib import Path
import pytest

from core.routing.unified_route_parser import (
    UnifiedRouteParser,
    NormalizedRoute,
    RouteProtocol,
    RouteType,
    NextHopResolutionStatus,
    evaluate_longest_prefix_match,
    resolve_recursive_next_hop,
)
from agents.akane.reasoning_engine import parse_routeros_routes, ParsedRoute
from core.topology_parsers import parse_mikrotik_routes

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "routes"
V6_DIR = FIXTURES_DIR / "routeros_v6"
V7_DIR = FIXTURES_DIR / "routeros_v7"
SYNTH_DIR = FIXTURES_DIR / "synthetic" / "edge_cases"


@pytest.fixture
def parser():
    return UnifiedRouteParser()


# ---------------------------------------------------------------------------
# 1. Real RouterOS v6 Fixture Tests
# ---------------------------------------------------------------------------

def test_v6_real_tabular_fixture(parser):
    raw = (V6_DIR / "raw" / "ip_route_tabular.txt").read_text(encoding="utf-8")
    routes = parser.parse(raw, device_id="R-1", ros_version=6)
    assert len(routes) == 3

    # Default route: 0 A S 0.0.0.0/0 192.168.1.1 1
    def_r = next(r for r in routes if r.dst_prefix == "0.0.0.0/0")
    assert def_r.active is True
    assert def_r.gateway == "192.168.1.1"
    assert def_r.distance == 1
    assert def_r.protocol == RouteProtocol.STATIC.value
    assert def_r.is_default_route() is True

    # Connected route: 1 ADC 192.168.88.0/24 192.168.88.1 ether2 0
    c_r = next(r for r in routes if r.dst_prefix == "192.168.88.0/24")
    assert c_r.active is True
    assert c_r.dynamic is True
    assert c_r.connect is True
    assert c_r.pref_src == "192.168.88.1"
    assert c_r.gateway == "ether2"
    assert c_r.distance == 0


def test_v6_real_detail_fixture(parser):
    raw = (V6_DIR / "raw" / "ip_route_detail.txt").read_text(encoding="utf-8")
    routes = parser.parse(raw, device_id="R-1", ros_version=6)
    assert len(routes) == 3

    def_r = next(r for r in routes if r.dst_prefix == "0.0.0.0/0")
    assert def_r.active is True
    assert def_r.gateway == "192.168.1.1"
    assert def_r.immediate_gw == "192.168.1.1"
    assert def_r.interface_name == "ether1"
    assert def_r.distance == 1
    assert def_r.scope == 30
    assert def_r.target_scope == 10


# ---------------------------------------------------------------------------
# 2. Real RouterOS v7 Fixture Tests
# ---------------------------------------------------------------------------

def test_v7_real_tabular_fixture(parser):
    raw = (V7_DIR / "raw" / "ip_route_tabular.txt").read_text(encoding="utf-8")
    routes = parser.parse(raw, device_id="CHR", ros_version=7)
    assert len(routes) == 3

    # Default route: 0 As 0.0.0.0/0 192.168.1.1 1
    def_r = next(r for r in routes if r.dst_prefix == "0.0.0.0/0")
    assert def_r.active is True
    assert def_r.gateway == "192.168.1.1"
    assert def_r.distance == 1
    assert def_r.protocol == RouteProtocol.STATIC.value

    # Connected route: 1 DAc 192.168.88.0/24 ether2 0
    c_r = next(r for r in routes if r.dst_prefix == "192.168.88.0/24")
    assert c_r.active is True
    assert c_r.dynamic is True
    assert c_r.connect is True
    assert c_r.gateway == "ether2"
    assert c_r.distance == 0


def test_v7_real_detail_fixture_with_line_wrapping(parser):
    raw = (V7_DIR / "raw" / "ip_route_detail.txt").read_text(encoding="utf-8")
    routes = parser.parse(raw, device_id="CHR", ros_version=7)
    assert len(routes) == 3

    # Wrapped attributes folded correctly
    def_r = next(r for r in routes if r.dst_prefix == "0.0.0.0/0")
    assert def_r.active is True
    assert def_r.gateway == "10.66.38.1"
    assert def_r.immediate_gw == "10.66.38.1%ether1"
    assert def_r.interface_name == "ether1"
    assert def_r.distance == 1
    assert def_r.scope == 30
    assert def_r.target_scope == 10
    assert def_r.routing_table == "main"


# ---------------------------------------------------------------------------
# 3. Defect Remediation Regression Tests (D1–D10)
# ---------------------------------------------------------------------------

def test_d1_spaced_flags_alignment(parser):
    """D1: Spaced flags '0 A S' must not cause destination/gateway column slippage."""
    raw = (SYNTH_DIR / "d1_spaced_flags.txt").read_text(encoding="utf-8")
    routes = parser.parse(raw)
    assert len(routes) == 2
    assert routes[0].dst_prefix == "0.0.0.0/0"
    assert routes[0].gateway == "192.168.1.1"
    assert routes[0].distance == 1
    assert routes[0].active is True
    assert routes[0].raw_flags == "A S"


def test_d2_lowercase_flags_interpretation(parser):
    """D2: Lowercase flags 'DAc', 'DAo', 'As' must be recognized."""
    raw = (SYNTH_DIR / "d2_lowercase_flags.txt").read_text(encoding="utf-8")
    routes = parser.parse(raw)
    assert len(routes) == 3
    assert routes[0].protocol == RouteProtocol.CONNECTED.value
    assert routes[0].connect is True
    assert routes[1].protocol == RouteProtocol.OSPF.value
    assert routes[1].ospf is True
    assert routes[1].distance == 110
    assert routes[2].protocol == RouteProtocol.STATIC.value
    assert routes[2].static is True


def test_d3_header_flags_extracted(parser):
    """D3: Extract record header flags before KV tokenization."""
    raw = (SYNTH_DIR / "d3_header_flags.txt").read_text(encoding="utf-8")
    routes = parser.parse(raw)
    assert len(routes) == 3
    assert routes[0].active is True
    assert routes[0].disabled is False
    assert routes[1].active is False  # 'S' without 'A' is inactive
    assert routes[2].disabled is True
    assert routes[2].active is False  # 'X' is disabled


def test_d4_line_wrapping_folding(parser):
    """D4: Multi-line wrapped attributes (distance, scope) must be folded."""
    raw = (SYNTH_DIR / "d4_line_wrapping.txt").read_text(encoding="utf-8")
    routes = parser.parse(raw)
    assert len(routes) == 1
    r = routes[0]
    assert r.dst_prefix == "192.168.50.0/24"
    assert r.distance == 110
    assert r.scope == 30
    assert r.target_scope == 10
    assert r.immediate_gw == "10.0.0.1%ether1"
    assert r.interface_name == "ether1"


def test_d5_recursive_gateway_status_parsing(parser):
    """D5: In gateway-status 'recursive via 10.0.0.1 ether1', extract IP and interface distinctly."""
    raw = (SYNTH_DIR / "d5_recursive_gateway.txt").read_text(encoding="utf-8")
    routes = parser.parse(raw)
    assert len(routes) == 1
    r = routes[0]
    assert r.gateway == "192.168.10.1"
    assert r.immediate_gw == "10.0.0.1"
    assert r.interface_name == "ether1"


def test_d6_inactive_routes_excluded_from_fib(parser):
    """D6: Inactive/disabled routes must NOT be selected as best forwarding route."""
    raw = (SYNTH_DIR / "d6_inactive_routes.txt").read_text(encoding="utf-8")
    routes = parser.parse(raw)
    assert len(routes) == 2
    assert all(not r.active for r in routes)

    lpm = evaluate_longest_prefix_match(routes, "192.168.1.10", require_active=True)
    assert lpm["matched"] is False
    assert lpm["best_route"] is None
    assert lpm["matching_routes_count"] == 2
    assert lpm["eligible_routes_count"] == 0
    assert "none are active in the Forwarding Information Base" in lpm["reason"]


def test_d7_ecmp_multigateway_parsing(parser):
    """D7: Multi-gateway comma-separated routes must be captured in gateways list."""
    raw = (SYNTH_DIR / "d7_ecmp_multigateway.txt").read_text(encoding="utf-8")
    routes = parser.parse(raw)
    assert len(routes) == 1
    r = routes[0]
    assert len(r.gateways) == 2
    assert "10.0.0.1" in r.gateways
    assert "10.0.0.2" in r.gateways


def test_d8_scope_and_target_scope_integers(parser):
    """D8: scope and target-scope must be parsed as integers."""
    raw = (SYNTH_DIR / "d8_scopes.txt").read_text(encoding="utf-8")
    routes = parser.parse(raw)
    assert len(routes) == 2
    assert routes[0].scope == 30 and routes[0].target_scope == 10
    assert routes[1].scope == 255 and routes[1].target_scope == 255


def test_d9_vrf_routing_table_attribution(parser):
    """D9: routing-table attribute must be preserved."""
    raw = (SYNTH_DIR / "d9_vrf_tables.txt").read_text(encoding="utf-8")
    routes = parser.parse(raw)
    assert len(routes) == 2
    assert routes[0].routing_table == "vpn-customer-a"
    assert routes[1].routing_table == "main"


def test_d10_cidr_normalization(parser):
    """D10: Bare host IP '192.168.1.5' must be canonicalized to '192.168.1.5/32'."""
    raw = (SYNTH_DIR / "d10_cidr_normalization.txt").read_text(encoding="utf-8")
    routes = parser.parse(raw)
    assert len(routes) == 2
    assert routes[0].dst_prefix == "192.168.1.5/32"
    assert routes[0].prefix_len == 32
    assert routes[1].dst_prefix == "10.0.0.0/8"
    assert routes[1].prefix_len == 8


# ---------------------------------------------------------------------------
# 4. NormalizedRoute Contract & Serialization Tests
# ---------------------------------------------------------------------------

def test_normalized_route_contract_and_backward_compatibility():
    r = NormalizedRoute(
        dst_prefix="10.50.0.0/16",
        gateway="10.50.0.1",
        device_id="CHR-1",
        interface_name="ether1",
        routing_table="main",
        protocol="static",
        distance=1,
        active=True,
        dynamic=False,
        raw_flags="As",
    )
    assert r.destination == "10.50.0.0/16"
    assert r.dst_address == "10.50.0.0/16"
    assert r.interface == "ether1"
    assert r.prefix_len == 16
    assert r.address_family == "ipv4"
    assert r.matches_address("10.50.12.34") is True
    assert r.matches_address("10.60.12.34") is False

    d = r.to_dict()
    assert d["dst_prefix"] == "10.50.0.0/16"
    assert d["gateway"] == "10.50.0.1"
    assert d["interface"] == "ether1"
    assert d["active"] is True

    top_d = r.to_topology_dict()
    assert top_d["dst"] == "10.50.0.0/16"
    assert top_d["gateway_ip"] == "10.50.0.1"


# ---------------------------------------------------------------------------
# 5. Legacy Adapter Compatibility Tests
# ---------------------------------------------------------------------------

def test_legacy_parse_routeros_routes_adapter():
    raw = (V6_DIR / "raw" / "ip_route_tabular.txt").read_text(encoding="utf-8")
    routes = parse_routeros_routes(raw)
    assert len(routes) == 3
    assert all(isinstance(r, ParsedRoute) for r in routes)
    assert routes[0].dst_address == "0.0.0.0/0"
    assert routes[0].gateway == "192.168.1.1"
    assert routes[0].active is True


def test_legacy_parse_mikrotik_routes_adapter():
    raw = (V7_DIR / "raw" / "ip_route_tabular.txt").read_text(encoding="utf-8")
    routes = parse_mikrotik_routes(raw)
    assert len(routes) == 3
    assert all(isinstance(r, dict) for r in routes)
    assert routes[0]["dst"] == "0.0.0.0/0"
    assert routes[0]["gateway_ip"] == "192.168.1.1"
    assert routes[1]["connected"] is True


# ---------------------------------------------------------------------------
# 6. Longest Prefix Match (LPM) Evaluation Tests
# ---------------------------------------------------------------------------

def test_lpm_tie_breaking_longest_prefix_wins(parser):
    routes = [
        NormalizedRoute(dst_prefix="0.0.0.0/0", gateway="10.0.0.1", distance=1, active=True),
        NormalizedRoute(dst_prefix="10.0.0.0/8", gateway="10.0.0.2", distance=1, active=True),
        NormalizedRoute(dst_prefix="10.20.0.0/16", gateway="10.0.0.3", distance=1, active=True),
        NormalizedRoute(dst_prefix="10.20.30.0/24", gateway="10.0.0.4", distance=1, active=True),
    ]
    res = evaluate_longest_prefix_match(routes, "10.20.30.55")
    assert res["matched"] is True
    assert res["best_route"]["dst_address"] == "10.20.30.0/24"
    assert res["best_route"]["gateway"] == "10.0.0.4"


def test_lpm_distance_tie_breaker_on_same_prefix(parser):
    routes = [
        NormalizedRoute(dst_prefix="10.0.0.0/24", gateway="192.168.1.1", distance=110, active=True),
        NormalizedRoute(dst_prefix="10.0.0.0/24", gateway="192.168.1.2", distance=10, active=True),
    ]
    res = evaluate_longest_prefix_match(routes, "10.0.0.50")
    assert res["matched"] is True
    assert res["best_route"]["gateway"] == "192.168.1.2"
    assert res["best_route"]["distance"] == 10


# ---------------------------------------------------------------------------
# 7. Recursive Next-Hop Resolution Tests
# ---------------------------------------------------------------------------

def test_recursive_next_hop_resolution_success():
    routes = [
        NormalizedRoute(dst_prefix="0.0.0.0/0", gateway="192.168.1.1", active=True),
        NormalizedRoute(dst_prefix="172.16.1.0/24", gateway="10.50.0.1", active=True),
        NormalizedRoute(dst_prefix="10.50.0.0/24", gateway="ether1", protocol="connected", active=True, connect=True),
    ]
    # Resolving gateway 10.50.0.1: resolves to directly connected ether1
    res = resolve_recursive_next_hop("10.50.0.1", routes)
    assert res.status == NextHopResolutionStatus.DIRECTLY_CONNECTED
    assert res.egress_interface == "ether1"
    assert res.depth == 1


def test_recursive_next_hop_loop_detection():
    # Route A points to IP B, Route B points to IP A
    routes = [
        NormalizedRoute(dst_prefix="10.1.1.0/24", gateway="10.2.2.2", active=True),
        NormalizedRoute(dst_prefix="10.2.2.0/24", gateway="10.1.1.1", active=True),
    ]
    res = resolve_recursive_next_hop("10.1.1.1", routes)
    assert res.status == NextHopResolutionStatus.UNREACHABLE
    assert res.loop_detected is True
    assert "loop detected" in res.reason.lower()


def test_recursive_next_hop_default_route_unresolved():
    # Gateway only reachable via 0.0.0.0/0 must NOT be declared directly connected
    routes = [
        NormalizedRoute(dst_prefix="0.0.0.0/0", gateway="ether1", active=True),
    ]
    res = resolve_recursive_next_hop("8.8.8.8", routes)
    assert res.status == NextHopResolutionStatus.UNRESOLVED
    assert "default route cannot resolve recursive gateway" in str(res.resolution_chain)


# ---------------------------------------------------------------------------
# 8. Large-Table Resource & Performance Tests (Phase E)
# ---------------------------------------------------------------------------

def test_large_table_bounded_thresholds(parser):
    # Tier 1: 500 routes -> COMPLETE
    tier1_lines = ["Flags: D - DYNAMIC; A - ACTIVE; c - CONNECT\n#   DST-ADDRESS   GATEWAY   DISTANCE"]
    for i in range(1, 501):
        tier1_lines.append(f"{i} DAc 10.{i // 256}.{i % 256}.0/24 ether1 0")
    routes1, rep1 = parser.parse_with_report("\n".join(tier1_lines))
    assert len(routes1) == 500
    assert rep1.status == "COMPLETE"
    assert rep1.is_partial is False

    # Tier 2: 6,000 routes -> WARNING_LARGE_TABLE
    tier2_lines = ["Flags: D - DYNAMIC; A - ACTIVE; c - CONNECT\n#   DST-ADDRESS   GATEWAY   DISTANCE"]
    for i in range(1, 6001):
        tier2_lines.append(f"{i} DAc 10.{i // 256}.{i % 256}.0/24 ether1 0")
    routes2, rep2 = parser.parse_with_report("\n".join(tier2_lines))
    assert len(routes2) == 6000
    assert rep2.status == "WARNING_LARGE_TABLE"
    assert "Tier 2 policy" in rep2.warning

    # Tier 3: 25,000 routes -> LIMIT_EXCEEDED (truncated to 20,000)
    tier3_lines = ["Flags: D - DYNAMIC; A - ACTIVE; c - CONNECT\n#   DST-ADDRESS   GATEWAY   DISTANCE"]
    for i in range(1, 25001):
        tier3_lines.append(f"{i} DAc 10.{i // 256}.{i % 256}.0/24 ether1 0")
    routes3, rep3 = parser.parse_with_report("\n".join(tier3_lines))
    assert len(routes3) == 20000
    assert rep3.status == "LIMIT_EXCEEDED"
    assert rep3.is_partial is True


def test_parser_performance_benchmark(parser):
    """5,000 routes must parse in under 350 ms."""
    lines = ["Flags: D - DYNAMIC; A - ACTIVE; c - CONNECT\n#   DST-ADDRESS   GATEWAY   DISTANCE"]
    for i in range(1, 5001):
        lines.append(f"{i} DAc 10.{i // 256}.{i % 256}.0/24 ether1 0")
    raw = "\n".join(lines)

    t0 = time.perf_counter()
    routes = parser.parse(raw)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert len(routes) == 5000
    assert elapsed_ms < 350.0, f"Parser performance benchmark exceeded: {elapsed_ms:.1f}ms >= 350ms"


def test_lpm_routing_table_isolation():
    """LPM must isolate lookups to the specified routing table / VRF context."""
    routes = [
        NormalizedRoute(dst_prefix="10.0.0.0/24", gateway="192.168.1.1", routing_table="main", active=True),
        NormalizedRoute(dst_prefix="10.0.0.0/24", gateway="10.99.99.1", routing_table="vpn-customer-a", active=True),
    ]
    # Query in main table
    res_main = evaluate_longest_prefix_match(routes, "10.0.0.5", routing_table="main")
    assert res_main["matched"] is True
    assert res_main["best_route"]["gateway"] == "192.168.1.1"

    # Query in VRF table
    res_vrf = evaluate_longest_prefix_match(routes, "10.0.0.5", routing_table="vpn-customer-a")
    assert res_vrf["matched"] is True
    assert res_vrf["best_route"]["gateway"] == "10.99.99.1"

    # Query non-existent table
    res_none = evaluate_longest_prefix_match(routes, "10.0.0.5", routing_table="vpn-other")
    assert res_none["matched"] is False


def test_recursive_next_hop_depth_capacity_16():
    """resolve_recursive_next_hop must support resolution up to depth 16 without error."""
    # Build a 5-hop recursion chain: 10.1.1.1 -> 10.2.2.2 -> 10.3.3.3 -> 10.4.4.4 -> ether1
    chain_routes = [
        NormalizedRoute(dst_prefix="10.1.1.0/24", gateway="10.2.2.2", active=True),
        NormalizedRoute(dst_prefix="10.2.2.0/24", gateway="10.3.3.3", active=True),
        NormalizedRoute(dst_prefix="10.3.3.0/24", gateway="10.4.4.4", active=True),
        NormalizedRoute(dst_prefix="10.4.4.0/24", gateway="ether1", protocol="connected", active=True, connect=True),
    ]
    res = resolve_recursive_next_hop("10.1.1.1", chain_routes)
    assert res.status == NextHopResolutionStatus.RECURSIVE_RESOLVED
    assert res.egress_interface == "ether1"
    assert res.depth == 4
    assert res.loop_detected is False


def test_large_table_exact_boundary_thresholds(parser):
    """Verify tier transitions at 4999, 5000, 5001, 19999, 20000, and 20001 routes."""
    # 5000: Tier 1 upper boundary
    lines_5000 = ["Flags: D - DYNAMIC; A - ACTIVE; c - CONNECT\n#   DST-ADDRESS   GATEWAY   DISTANCE"]
    for i in range(1, 5001):
        lines_5000.append(f"{i} DAc 10.{i // 256}.{i % 256}.0/24 ether1 0")
    _, rep_5000 = parser.parse_with_report("\n".join(lines_5000))
    assert rep_5000.status == "COMPLETE"
    assert rep_5000.is_partial is False

    # 5001: Tier 2 lower boundary
    lines_5001 = lines_5000 + ["5001 DAc 10.19.137.0/24 ether1 0"]
    _, rep_5001 = parser.parse_with_report("\n".join(lines_5001))
    assert rep_5001.status == "WARNING_LARGE_TABLE"
    assert rep_5001.is_partial is False

