"""
WP 4.6.6 Acceptance Test Suite — Auto-Diagnosis Integration & Optimization.

Covers all 17 scenarios in Section 10.8, all 9 natural-language routing intents in
Section 10.2, all 10 mandatory root-cause fields in Section 10.4, DIO missing-field
handling, single-pass evidence reuse, cooperative cancellation, and 100% read-only enforcement.
"""

from __future__ import annotations

import threading
import time
import pytest

from core.network_intelligence.auto_orchestrator import (
    AutomaticNetworkOrchestrator,
    RoutingDiagnosisIntent,
    filter_safe_readonly_commands,
)
from core.network_intelligence.models import EvidenceItem
from core.network_intelligence.multi_device_collector import (
    DeviceCollectionSummary,
    MultiDeviceCollectionSummary,
    MultiDeviceEvidenceBundle,
)
from core.routing.route_collector import (
    RouteCollectionResult,
    RouteCollectionStatus,
    RouteCompleteness,
)
from core.routing.route_history import RouteHistoryStore
from core.routing.unified_route_parser import NormalizedRoute, RouteProtocol, RouteType

MANDATORY_RC_FIELDS = {
    "description",
    "affected_device",
    "affected_prefix",
    "evidence_ids",
    "route_chain",
    "related_topology",
    "confidence",
    "alternative_explanations",
    "missing_evidence",
    "recommended_verification_steps",
}
VALID_EPISTEMIC_TIERS = {
    "Confirmed finding",
    "Strong hypothesis",
    "Weak hypothesis",
    "Insufficient evidence",
}


def _r(
    dev_id: str,
    dst: str,
    gw: str = "",
    *,
    iface: str = "ether1",
    pref_src: str = "",
    connect: bool = False,
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
    proto = RouteProtocol.CONNECTED if connect else (RouteProtocol.OSPF if ospf else RouteProtocol.STATIC)
    return NormalizedRoute(
        device_id=dev_id,
        dst_prefix=dst,
        gateway=gw,
        gateways=gws if gws is not None else ([gw] if gw else []),
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
        static=(not connect and not ospf),
        ospf=ospf,
    )


def _col(
    dev_id: str,
    routes: list[NormalizedRoute],
    *,
    completeness: str = RouteCompleteness.COMPLETE.value,
    status: str = RouteCollectionStatus.SUCCESS.value,
    ts: float | None = None,
) -> RouteCollectionResult:
    now = ts or time.time()
    tables = sorted({r.routing_table or "main" for r in routes}) or ["main"]
    return RouteCollectionResult(
        device_id=dev_id,
        device_identity=dev_id.upper(),
        router_os_version="7.15.2",
        status=status,
        completeness=completeness,
        routes=routes,
        routing_tables=tables,
        evidence_id=f"ev_{dev_id}_{int(now * 1000)}",
        collected_at=now,
    )


def _assert_valid_root_causes(res: dict) -> None:
    assert res["read_only"] is True
    assert res["auto_remediation_executed"] is False
    assert len(res["root_causes"]) >= 1
    for rc in res["root_causes"]:
        assert MANDATORY_RC_FIELDS.issubset(rc.keys())
        assert rc["epistemic_tier"] in VALID_EPISTEMIC_TIERS


def test_01_single_router_diagnosis_and_all_9_natural_language_intents(tmp_path):
    orch = AutomaticNetworkOrchestrator()
    hist = RouteHistoryStore(tmp_path / "wp466_01.db")

    # Verify all 9 natural-language intent categories in Section 10.2
    expected_intents = [
        ("Analyze routing on all registered routers.", RoutingDiagnosisIntent.ANALYZE_ALL_ROUTERS),
        ("Why can this LAN not reach the internet?", RoutingDiagnosisIntent.LAN_INTERNET_REACHABILITY),
        ("Find the upstream dependency of this router.", RoutingDiagnosisIntent.UPSTREAM_DEPENDENCY_ANALYSIS),
        ("Check whether the default route is correct.", RoutingDiagnosisIntent.DEFAULT_ROUTE_VERIFICATION),
        ("Analyze the route to 10.10.10.0/24.", RoutingDiagnosisIntent.SPECIFIC_PREFIX_PATH_ANALYSIS),
        ("Determine whether this gateway is reachable through the network 10.0.0.1.", RoutingDiagnosisIntent.GATEWAY_REACHABILITY_ANALYSIS),
        ("Find possible routing inconsistencies between routers.", RoutingDiagnosisIntent.CROSS_DEVICE_INCONSISTENCY_SCAN),
        ("Compare current routing state with the previous snapshot.", RoutingDiagnosisIntent.HISTORICAL_SNAPSHOT_COMPARISON),
        ("Analyze what changed before this network became unreachable.", RoutingDiagnosisIntent.PRE_FAILURE_CHANGE_CORRELATION),
    ]
    for prompt, exp in expected_intents:
        meta = orch.classify_routing_intent(prompt)
        assert meta["intent"] == exp, f"Failed for prompt: {prompt}"

    # Single-router clean diagnosis
    routes = {
        "dev_a": _col("dev_a", [
            _r("dev_a", "192.168.1.0/24", iface="ether2", pref_src="192.168.1.1", connect=True),
            _r("dev_a", "10.0.0.0/30", iface="ether1", pref_src="10.0.0.2", connect=True),
            _r("dev_a", "0.0.0.0/0", "10.0.0.1", iface="ether1"),
        ]),
    }
    res = orch.execute_auto_diagnosis(
        target_devices=["dev_a"],
        symptom="Check whether the default route is correct.",
        precollected_routes=routes,
        route_history_store_override=hist,
    )
    assert res["success"] is True
    assert res["routing_intent"] == RoutingDiagnosisIntent.DEFAULT_ROUTE_VERIFICATION
    _assert_valid_root_causes(res)


def test_02_two_router_route_diagnosis(tmp_path):
    orch = AutomaticNetworkOrchestrator()
    hist = RouteHistoryStore(tmp_path / "wp466_02.db")
    routes = {
        "dev_a": _col("dev_a", [
            _r("dev_a", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.1", connect=True),
            _r("dev_a", "10.10.10.0/24", "10.0.12.2", iface="ether1"),
            _r("dev_a", "0.0.0.0/0", "10.0.12.2", iface="ether1"),
        ]),
        "dev_b": _col("dev_b", [
            _r("dev_b", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.2", connect=True),
            _r("dev_b", "10.10.10.0/24", iface="ether2", pref_src="10.10.10.1", connect=True),
            _r("dev_b", "0.0.0.0/0", "203.0.113.1", iface="ether3"),
        ]),
    }
    res = orch.execute_auto_diagnosis(
        target_devices=["dev_a", "dev_b"],
        symptom="Analyze the route to 10.10.10.0/24.",
        precollected_routes=routes,
        route_history_store_override=hist,
    )
    assert res["destination"] == "10.10.10.0/24"
    hops = res["route_intelligence"]["path_evaluation"]["primary_hops"]
    assert [h["device_id"] for h in hops] == ["dev_a", "dev_b"]
    _assert_valid_root_causes(res)


def test_03_three_router_route_diagnosis(tmp_path):
    orch = AutomaticNetworkOrchestrator()
    hist = RouteHistoryStore(tmp_path / "wp466_03.db")
    routes = {
        "dev_a": _col("dev_a", [
            _r("dev_a", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.1", connect=True),
            _r("dev_a", "0.0.0.0/0", "10.0.12.2", iface="ether1"),
        ]),
        "dev_b": _col("dev_b", [
            _r("dev_b", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.2", connect=True),
            _r("dev_b", "10.0.23.0/30", iface="ether2", pref_src="10.0.23.1", connect=True),
            _r("dev_b", "0.0.0.0/0", "10.0.23.2", iface="ether2"),
        ]),
        "dev_c": _col("dev_c", [
            _r("dev_c", "10.0.23.0/30", iface="ether1", pref_src="10.0.23.2", connect=True),
            _r("dev_c", "172.20.0.0/24", iface="ether2", pref_src="172.20.0.1", connect=True),
            _r("dev_c", "0.0.0.0/0", "198.51.100.1", iface="ether3"),
        ]),
    }
    res = orch.execute_auto_diagnosis(
        target_devices=["dev_a", "dev_b", "dev_c"],
        symptom="Analyze the route to 172.20.0.55.",
        precollected_routes=routes,
        route_history_store_override=hist,
    )
    hops = res["route_intelligence"]["path_evaluation"]["primary_hops"]
    assert [h["device_id"] for h in hops] == ["dev_a", "dev_b", "dev_c"]
    assert len(res["root_causes"][0]["route_chain"]) == 3
    _assert_valid_root_causes(res)


def test_04_missing_default_route(tmp_path):
    orch = AutomaticNetworkOrchestrator()
    hist = RouteHistoryStore(tmp_path / "wp466_04.db")
    routes = {
        "dev_a": _col("dev_a", [
            _r("dev_a", "192.168.1.0/24", iface="ether2", pref_src="192.168.1.1", connect=True),
        ]),
    }
    res = orch.execute_auto_diagnosis(
        target_devices=["dev_a"],
        symptom="Why can this LAN not reach the internet?",
        precollected_routes=routes,
        route_history_store_override=hist,
        auto_plan=True,
    )
    assert res["epistemic_classification"] == "Confirmed finding"
    assert any("MISSING_DEFAULT_ROUTE" in rc["description"] for rc in res["root_causes"])
    assert res["recommended_plan"] is not None
    assert res["rollback_proposal"] is not None
    assert res["auto_remediation_executed"] is False
    _assert_valid_root_causes(res)


def test_05_gateway_unreachable(tmp_path):
    orch = AutomaticNetworkOrchestrator()
    hist = RouteHistoryStore(tmp_path / "wp466_05.db")
    routes = {
        "dev_a": _col("dev_a", [
            _r("dev_a", "192.168.1.0/24", iface="ether2", pref_src="192.168.1.1", connect=True),
            _r("dev_a", "0.0.0.0/0", "10.99.99.1", iface="ether1", active=False, unreachable=True),
        ]),
    }
    res = orch.execute_auto_diagnosis(
        target_devices=["dev_a"],
        symptom="Determine whether this gateway is reachable through the network 10.99.99.1.",
        precollected_routes=routes,
        route_history_store_override=hist,
    )
    assert res["epistemic_classification"] == "Confirmed finding"
    assert any(
        "UNREACHABLE" in rc["description"] or "MISSING_DEFAULT_ROUTE" in rc["description"]
        for rc in res["root_causes"]
    )
    _assert_valid_root_causes(res)


def test_06_recursive_route_failure(tmp_path):
    orch = AutomaticNetworkOrchestrator()
    hist = RouteHistoryStore(tmp_path / "wp466_06.db")
    routes = {
        "dev_a": _col("dev_a", [
            _r("dev_a", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.1", connect=True),
            _r("dev_a", "0.0.0.0/0", "10.0.12.2", iface="ether1"),
            # Recursive route pointing to 10.255.255.9 which has NO specific supporting route (only default, scope=30 > target_scope=20!)
            _r("dev_a", "172.18.0.0/16", "10.255.255.9", scope=40, target_scope=20),
        ]),
    }
    res = orch.execute_auto_diagnosis(
        target_devices=["dev_a"],
        symptom="Find the upstream dependency of this router for 172.18.0.1.",
        precollected_routes=routes,
        route_history_store_override=hist,
    )
    assert any("rekursif" in rc["description"].lower() or "RECURSIVE" in rc["description"] for rc in res["root_causes"])
    _assert_valid_root_causes(res)


def test_07_route_mismatch_cross_device(tmp_path):
    orch = AutomaticNetworkOrchestrator()
    hist = RouteHistoryStore(tmp_path / "wp466_07.db")
    routes = {
        "dev_a": _col("dev_a", [
            _r("dev_a", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.1", connect=True),
            _r("dev_a", "0.0.0.0/0", "10.0.12.2", iface="ether1"),
            _r("dev_a", "10.55.0.0/24", "10.0.12.2", iface="ether1"),
        ]),
        "dev_b": _col("dev_b", [
            _r("dev_b", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.2", connect=True),
            # dev_b has NO route to 10.55.0.0/24 and NO default route!
        ]),
    }
    res = orch.execute_auto_diagnosis(
        target_devices=["dev_a", "dev_b"],
        symptom="Find possible routing inconsistencies between routers.",
        precollected_routes=routes,
        route_history_store_override=hist,
    )
    assert any("MISSING_UPSTREAM_ROUTE" in rc["description"] for rc in res["root_causes"])
    _assert_valid_root_causes(res)


def test_08_vrf_mismatch(tmp_path):
    orch = AutomaticNetworkOrchestrator()
    hist = RouteHistoryStore(tmp_path / "wp466_08.db")
    routes = {
        "dev_a": _col("dev_a", [
            _r("dev_a", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.1", connect=True),
            _r("dev_a", "0.0.0.0/0", "10.0.12.2", iface="ether1"),
            _r("dev_a", "10.200.0.0/24", "10.0.12.2", iface="ether1", table="main"),
        ]),
        "dev_b": _col("dev_b", [
            _r("dev_b", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.2", connect=True),
            _r("dev_b", "0.0.0.0/0", "203.0.113.1", iface="ether2"),
            _r("dev_b", "10.200.0.0/24", iface="vlan200", pref_src="10.200.0.1", connect=True, table="vrf_finance"),
        ]),
    }
    res = orch.execute_auto_diagnosis(
        target_devices=["dev_a", "dev_b"],
        symptom="Analyze the route to 10.200.0.10.",
        precollected_routes=routes,
        route_history_store_override=hist,
    )
    assert any("INCORRECT_VRF_ASSOCIATION" in rc["description"] for rc in res["root_causes"])
    _assert_valid_root_causes(res)


def test_09_ecmp_ambiguity(tmp_path):
    orch = AutomaticNetworkOrchestrator()
    hist = RouteHistoryStore(tmp_path / "wp466_09.db")
    routes = {
        "dev_a": _col("dev_a", [
            _r("dev_a", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.1", connect=True),
            _r("dev_a", "10.0.13.0/30", iface="ether2", pref_src="10.0.13.1", connect=True),
            _r("dev_a", "0.0.0.0/0", "10.0.12.2,10.0.13.2", gws=["10.0.12.2", "10.0.13.2"], ospf=True),
        ]),
    }
    res = orch.execute_auto_diagnosis(
        target_devices=["dev_a"],
        symptom="Check whether the default route is correct.",
        precollected_routes=routes,
        route_history_store_override=hist,
    )
    assert res["route_intelligence"]["path_evaluation"]["is_ecmp"] is True
    _assert_valid_root_causes(res)


def test_10_upstream_device_unavailable(tmp_path):
    orch = AutomaticNetworkOrchestrator()
    hist = RouteHistoryStore(tmp_path / "wp466_10.db")
    routes = {
        "dev_a": _col("dev_a", [
            _r("dev_a", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.1", connect=True),
            _r("dev_a", "0.0.0.0/0", "10.0.12.2", iface="ether1"),
        ]),
        "dev_b": _col(
            "dev_b",
            [],
            completeness=RouteCompleteness.UNREACHABLE.value,
            status=RouteCollectionStatus.UNREACHABLE.value,
        ),
    }
    res = orch.execute_auto_diagnosis(
        target_devices=["dev_a", "dev_b"],
        symptom="Why can this LAN not reach the internet?",
        precollected_routes=routes,
        device_ips_override={"dev_a": ["10.0.12.1"], "dev_b": ["10.0.12.2"]},
        device_oper_states_override={"dev_a": "online", "dev_b": "offline"},
        route_history_store_override=hist,
    )
    assert any("ROUTE_POINTING_TO_UNAVAILABLE_NEXT_HOP" in rc["description"] for rc in res["root_causes"])
    assert len(res["partial_evidence_warnings"]) >= 1
    _assert_valid_root_causes(res)


def test_11_incomplete_collection_and_insufficient_evidence(tmp_path):
    orch = AutomaticNetworkOrchestrator()
    hist = RouteHistoryStore(tmp_path / "wp466_11.db")
    routes_empty = {
        "dev_a": _col("dev_a", [], completeness=RouteCompleteness.FAILED.value, status=RouteCollectionStatus.FAILED.value),
    }
    res = orch.execute_auto_diagnosis(
        target_devices=["dev_a"],
        symptom="Analyze routing on all registered routers.",
        precollected_routes=routes_empty,
        route_history_store_override=hist,
    )
    assert res["epistemic_classification"] == "Insufficient evidence"
    assert res["root_causes"][0]["epistemic_tier"] == "Insufficient evidence"
    assert len(res["root_causes"][0]["missing_evidence"]) >= 1
    _assert_valid_root_causes(res)


def test_12_historical_route_change_correlation(tmp_path):
    orch = AutomaticNetworkOrchestrator()
    hist = RouteHistoryStore(tmp_path / "wp466_12.db")
    c_before = _col("dev_a", [
        _r("dev_a", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.1", connect=True),
        _r("dev_a", "0.0.0.0/0", "10.0.12.2", iface="ether1"),
        _r("dev_a", "10.44.0.0/24", "10.0.12.2", iface="ether1"),
    ], ts=1000.0)
    c_after = _col("dev_a", [
        _r("dev_a", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.1", connect=True),
        _r("dev_a", "0.0.0.0/0", "10.0.12.2", iface="ether1"),
        # 10.44.0.0/24 removed!
    ], ts=1060.0)
    hist.create_snapshot_from_collection(c_before)
    hist.create_snapshot_from_collection(c_after)

    res = orch.execute_auto_diagnosis(
        target_devices=["dev_a"],
        symptom="Analyze what changed before this network became unreachable.",
        precollected_routes={"dev_a": c_after},
        route_history_store_override=hist,
    )
    assert res["routing_intent"] == RoutingDiagnosisIntent.PRE_FAILURE_CHANGE_CORRELATION
    assert res["route_intelligence"]["historical_comparison"]["total_recorded_changes"] >= 1
    assert any("ROUTE_REMOVED" in rc["description"] for rc in res["root_causes"])
    _assert_valid_root_causes(res)


def test_13_topology_conflict(tmp_path):
    orch = AutomaticNetworkOrchestrator()
    hist = RouteHistoryStore(tmp_path / "wp466_13.db")
    routes = {
        "dev_a": _col("dev_a", [
            _r("dev_a", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.1", connect=True),
            _r("dev_a", "0.0.0.0/0", "10.0.12.2", iface="ether1"),
        ]),
        "dev_b": _col("dev_b", [
            _r("dev_b", "10.0.12.0/30", iface="ether1", pref_src="10.0.12.2", connect=True),
            _r("dev_b", "0.0.0.0/0", "203.0.113.1", iface="ether2"),
        ]),
        "dev_c": _col("dev_c", [
            _r("dev_c", "10.0.99.0/30", iface="ether1", pref_src="10.0.99.2", connect=True),
            _r("dev_c", "0.0.0.0/0", "203.0.113.1", iface="ether2"),
        ]),
    }
    topo_edges = [{
        "id": "e_conflict",
        "source_node_id": "dev_a",
        "target_node_id": "dev_c",
        "source_interface": "ether1",
        "target_interface": "ether1",
        "relationship_class": "PHYSICAL_ADJACENCY",
        "confidence_tier": "confirmed",
        "oper_status": "up",
    }]
    res = orch.execute_auto_diagnosis(
        target_devices=["dev_a", "dev_b", "dev_c"],
        symptom="Find possible routing inconsistencies between routers.",
        precollected_routes=routes,
        topology_edges_override=topo_edges,
        route_history_store_override=hist,
    )
    assert any("UNEXPECTED_PATH_DIVERGENCE" in rc["description"] for rc in res["root_causes"])
    _assert_valid_root_causes(res)


def test_14_duplicate_evidence_prevention_and_ttl_reuse(tmp_path, monkeypatch):
    import core.network_intelligence.auto_orchestrator as ao_mod

    orch = AutomaticNetworkOrchestrator()
    hist = RouteHistoryStore(tmp_path / "wp466_14.db")
    call_counter = {"count": 0}

    def _fake_collect(self, targets, required_types=None, max_concurrency=3, timeout_per_cmd=10.0):
        call_counter["count"] += 1
        ev = EvidenceItem(
            evidence_id="ev_single_pass_1",
            device_identity="CHR",
            observation_type="routes",
            source_command="/routing route print",
            collection_timestamp=time.time(),
            collection_status="SUCCESS",
            normalized_value={
                "routes": [
                    {"dst_prefix": "10.0.0.0/24", "gateway": "ether1", "interface_name": "ether1", "pref_src": "10.0.0.2", "connect": True, "active": True},
                    {"dst_prefix": "0.0.0.0/0", "gateway": "10.0.0.1", "interface_name": "ether1", "static": True, "active": True},
                ]
            },
        )
        return MultiDeviceEvidenceBundle(
            bundle_id="mb_test_single",
            timestamp=time.time(),
            device_bundles={"CHR": {"target": "CHR", "ros_major_version": 7, "display_name": "CHR", "evidence_items": [ev], "contradictions": [], "collection_errors": []}},
            summary=MultiDeviceCollectionSummary(
                total_devices=1, successful_devices=1, partial_devices=0, failed_devices=0,
                total_commands=1, successful_commands=1, failed_commands=0, unsupported_commands=0,
                total_duration_ms=5.0,
                device_summaries={"CHR": DeviceCollectionSummary("CHR", "CHR", "SUCCESS", 1, 1, 0, 0, 5.0)},
            ),
        )

    monkeypatch.setattr(ao_mod.MultiDeviceEvidenceOrchestrator, "collect_multi_device_bundle", _fake_collect)

    # First run: collects MultiDeviceEvidenceBundle ONCE (not twice!)
    res1 = orch.execute_auto_diagnosis(
        target_devices=["CHR"],
        symptom="Check whether the default route is correct.",
        reuse_fresh_sec=60.0,
        route_history_store_override=hist,
    )
    assert res1["success"] is True
    assert call_counter["count"] == 1
    assert res1["evidence_reused"] is False

    # Second run within TTL: reuses cached bundle -> ZERO new collection calls!
    res2 = orch.execute_auto_diagnosis(
        target_devices=["CHR"],
        symptom="Check whether the default route is correct.",
        reuse_fresh_sec=60.0,
        route_history_store_override=hist,
    )
    assert res2["success"] is True
    assert call_counter["count"] == 1
    assert res2["evidence_reused"] is True


def test_15_dio_requirement_collection():
    orch = AutomaticNetworkOrchestrator()
    res = orch.execute_auto_diagnosis(
        target_devices=["CHR"],
        symptom="Analyze the route to",  # Missing destination IP/prefix!
        require_dio_validation=True,
    )
    assert res["status"] == "needs_input"
    assert res["dio_required"] is True
    missing_keys = [m["key"] for m in res["dio_interaction_plan"]["missing_data"]]
    assert "target_ip" in missing_keys


def test_16_automatic_pipeline_cancellation():
    orch = AutomaticNetworkOrchestrator()
    cancel_evt = threading.Event()
    cancel_evt.set()
    res = orch.execute_auto_diagnosis(
        target_devices=["CHR"],
        symptom="Analyze routing on all registered routers.",
        cancel_event=cancel_evt,
    )
    assert res["status"] == "cancelled"
    assert res["cancelled"] is True
    assert res["read_only"] is True
    assert res["auto_remediation_executed"] is False


def test_17_read_only_enforcement_on_recommendations():
    unsafe_and_safe = [
        "/routing route print",
        "/ip route add dst-address=0.0.0.0/0 gateway=10.0.0.1",
        "/system reboot",
        "/interface disable ether1",
        "/ip firewall nat set 0 disabled=yes",
        "/ip route print; /system reset-configuration",
        "/ip address print",
    ]
    filtered = filter_safe_readonly_commands(unsafe_and_safe)
    assert filtered == ["/routing route print", "/ip address print"]
