"""
WP 4.6.4 Verification Suite — Historical Route Analytics & Immutable Route Snapshots.

Covers all 15 mandatory Section 8.9 test scenarios using isolated temporary SQLite
databases so the workspace `topology.db` baseline remains untouched.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import List

import pytest
from fastapi.testclient import TestClient

from core.routing.route_collector import (
    RouteCollectionResult,
    RouteCollectionStatus,
    RouteCompleteness,
)
from core.routing.route_history import (
    RouteChangeType,
    RouteHistoryStore,
    RouteSnapshotRecord,
    serialize_routes_deterministically,
)
from core.routing.unified_route_parser import NormalizedRoute
from core.topology_db import topology_transaction
from core.topology_engine import TopologyEngine


def _r(
    dst_prefix: str,
    gateway: str = "10.0.0.1",
    *,
    device_id: str = "dev_a",
    routing_table: str = "main",
    protocol: str = "static",
    distance: int = 1,
    metric: int | None = None,
    active: bool = True,
    disabled: bool = False,
    connect: bool = False,
    immediate_gw: str = "",
    gateways: List[str] | None = None,
) -> NormalizedRoute:
    plen = int(dst_prefix.split("/")[1]) if "/" in dst_prefix else 32
    return NormalizedRoute(
        device_id=device_id,
        routing_table=routing_table,
        dst_prefix=dst_prefix,
        prefix_len=plen,
        gateway=gateway,
        gateways=list(gateways) if gateways is not None else ([gateway] if gateway else []),
        immediate_gw=immediate_gw,
        interface_name=gateway if connect else "ether1",
        protocol=protocol,
        distance=distance,
        metric=metric,
        active=active,
        disabled=disabled,
        connect=connect,
        static=(protocol == "static"),
        dynamic=(protocol != "static"),
    )


def _col(
    device_id: str,
    routes: List[NormalizedRoute],
    *,
    ts: float,
    status: str = RouteCollectionStatus.SUCCESS.value,
    completeness: str = RouteCompleteness.COMPLETE.value,
    errors: List[str] | None = None,
    evidence_id: str = "",
) -> RouteCollectionResult:
    tables = sorted({r.routing_table or "main" for r in routes}) or ["main"]
    return RouteCollectionResult(
        device_id=device_id,
        device_identity=device_id.upper(),
        router_os_version="7.15.2",
        status=status,
        completeness=completeness,
        collected_at=ts,
        routes=routes,
        routing_tables=tables,
        errors=list(errors or []),
        evidence_id=evidence_id or f"ev_{device_id}_{int(ts * 1000)}",
    )


def test_01_snapshot_creation_and_immutability_triggers(tmp_path: Path):
    db = tmp_path / "hist_01.db"
    store = RouteHistoryStore(db)
    c1 = _col("dev_a", [_r("0.0.0.0/0", "10.0.0.1"), _r("10.0.0.0/24", "ether1", connect=True, protocol="connected", distance=0)], ts=1000.0)
    snap, chgs = store.create_snapshot_from_collection(c1)

    assert snap.snapshot_id.startswith("rsnap_dev_a_")
    assert snap.route_count == 2
    assert snap.active_route_count == 2
    assert chgs == []  # First snapshot has no prior baseline

    # Verify SQLite BEFORE UPDATE and BEFORE DELETE immutability triggers
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        with topology_transaction(db, write=True) as conn:
            conn.execute("UPDATE route_snapshots SET route_count = 99 WHERE snapshot_id = ?", (snap.snapshot_id,))

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        with topology_transaction(db, write=True) as conn:
            conn.execute("DELETE FROM route_snapshots WHERE snapshot_id = ?", (snap.snapshot_id,))


def test_02_deterministic_checksum_and_integrity_orthogonality(tmp_path: Path):
    db = tmp_path / "hist_02.db"
    store = RouteHistoryStore(db)
    r1 = _r("10.10.0.0/16", "10.0.0.1")
    r2 = _r("0.0.0.0/0", "10.0.0.1")

    # Reversed input order and different collection timestamps must produce identical SHA-256!
    s_a, _ = store.create_snapshot_from_collection(_col("dev_a", [r1, r2], ts=1000.0, evidence_id="ev1"))
    s_b, _ = store.create_snapshot_from_collection(_col("dev_a", [r2, r1], ts=2000.0, evidence_id="ev2"))
    assert s_a.sha256_hash == s_b.sha256_hash

    # Partial snapshot has a VALID SHA-256 hash while remaining explicitly incomplete
    s_part, _ = store.create_snapshot_from_collection(
        _col("dev_b", [r1], ts=3000.0, status=RouteCollectionStatus.PARTIAL.value, completeness=RouteCompleteness.PARTIAL.value)
    )
    ver = store.verify_snapshot(s_part.snapshot_id)
    assert ver is not None
    assert ver["verified"] is True
    assert ver["is_complete"] is False
    assert ver["completeness"] == "PARTIAL"


def test_03_snapshot_verification_and_tamper_detection():
    routes_json = serialize_routes_deterministically([_r("0.0.0.0/0", "10.0.0.1")])
    rec = RouteSnapshotRecord(
        snapshot_id="rsnap_test",
        batch_id="rbatch_test",
        device_id="dev_a",
        device_identity="DEV_A",
        collected_at=1000.0,
        ros_version="7.15",
        routing_tables=["main"],
        routes_json=routes_json,
        route_count=1,
        active_route_count=1,
        completeness="COMPLETE",
        sha256_hash="",
    )
    rec.sha256_hash = rec.calculate_checksum()
    assert rec.verify_integrity() is True

    # Simulate tampered route payload
    rec.routes_json = serialize_routes_deterministically([_r("0.0.0.0/0", "10.99.99.99")])
    assert rec.verify_integrity() is False
    assert rec.to_dict()["integrity_status"] == "compromised"


def test_04_snapshot_persistence_after_store_restart(tmp_path: Path):
    db = tmp_path / "hist_04.db"
    store1 = RouteHistoryStore(db)
    snap, _ = store1.create_snapshot_from_collection(_col("dev_a", [_r("192.168.1.0/24", "10.0.0.2")], ts=1000.0))
    del store1

    store2 = RouteHistoryStore(db)
    loaded = store2.get_snapshot(snap.snapshot_id)
    assert loaded is not None
    assert loaded.sha256_hash == snap.sha256_hash
    assert loaded.verify_integrity() is True
    assert len(loaded.get_routes()) == 1


def test_05_route_additions_and_reappearance(tmp_path: Path):
    db = tmp_path / "hist_05.db"
    store = RouteHistoryStore(db)
    base_r = _r("10.0.0.0/24", "ether1", connect=True, protocol="connected", distance=0)
    extra_r = _r("172.16.50.0/24", "10.0.0.2")

    store.create_snapshot_from_collection(_col("dev_a", [base_r], ts=1000.0))
    _, chgs_add = store.create_snapshot_from_collection(_col("dev_a", [base_r, extra_r], ts=1010.0))
    assert len(chgs_add) == 1
    assert chgs_add[0].change_type == RouteChangeType.ROUTE_ADDED.value

    _, chgs_rem = store.create_snapshot_from_collection(_col("dev_a", [base_r], ts=1020.0))
    assert chgs_rem[0].change_type == RouteChangeType.ROUTE_REMOVED.value

    # Re-adding the previously removed prefix emits ROUTE_REAPPEARED!
    _, chgs_reapp = store.create_snapshot_from_collection(_col("dev_a", [base_r, extra_r], ts=1030.0))
    assert len(chgs_reapp) == 1
    assert chgs_reapp[0].change_type == RouteChangeType.ROUTE_REAPPEARED.value


def test_06_confirmed_route_removals(tmp_path: Path):
    db = tmp_path / "hist_06.db"
    store = RouteHistoryStore(db)
    s1, _ = store.create_snapshot_from_collection(_col("dev_a", [_r("0.0.0.0/0", "10.0.0.1"), _r("10.20.0.0/16", "10.0.0.2")], ts=1000.0))
    s2, chgs = store.create_snapshot_from_collection(_col("dev_a", [_r("0.0.0.0/0", "10.0.0.1")], ts=1010.0))

    assert len(chgs) == 1
    assert chgs[0].change_type == RouteChangeType.ROUTE_REMOVED.value
    assert chgs[0].dst_prefix == "10.20.0.0/16"

    diff = store.compare_snapshots(s1.snapshot_id, s2.snapshot_id)
    assert diff.removal_suppression_active is False
    assert diff.summary_counts[RouteChangeType.ROUTE_REMOVED.value] == 1


def test_07_route_modifications_granular_types(tmp_path: Path):
    db = tmp_path / "hist_07.db"
    store = RouteHistoryStore(db)

    store.create_snapshot_from_collection(_col("dev_a", [
        _r("10.1.0.0/24", "10.0.0.1", distance=1, metric=10, active=True, disabled=False, immediate_gw="10.0.0.1%ether1"),
        _r("10.2.0.0/24", "10.0.0.1,10.0.0.2", gateways=["10.0.0.1", "10.0.0.2"]),
        _r("10.3.0.0/24", "10.0.0.1", routing_table="main"),
    ], ts=1000.0))

    # Gateway changed + ECMP changed + VRF routing_table changed
    _, chgs1 = store.create_snapshot_from_collection(_col("dev_a", [
        _r("10.1.0.0/24", "10.0.0.9", distance=1, metric=10, active=True, disabled=False, immediate_gw="10.0.0.9%ether2"),
        _r("10.2.0.0/24", "10.0.0.1", gateways=["10.0.0.1"]),
        _r("10.3.0.0/24", "10.0.0.1", routing_table="vrf_corp"),
    ], ts=1010.0))
    types1 = {c.dst_prefix: c.change_type for c in chgs1}
    assert types1["10.1.0.0/24"] == RouteChangeType.GATEWAY_CHANGED.value
    assert types1["10.2.0.0/24"] == RouteChangeType.ECMP_CHANGED.value
    assert types1["10.3.0.0/24"] == RouteChangeType.ROUTING_TABLE_CHANGED.value

    # Immediate next-hop changed (configured recursive gateway unchanged) + deactivated + disabled + distance + metric
    _, chgs2 = store.create_snapshot_from_collection(_col("dev_a", [
        _r("10.1.0.0/24", "10.0.0.9", distance=1, metric=10, active=True, disabled=False, immediate_gw="10.0.0.9%ether3"),
        _r("10.2.0.0/24", "10.0.0.1", active=False, gateways=["10.0.0.1"]),
        _r("10.3.0.0/24", "10.0.0.1", routing_table="vrf_corp", disabled=True),
    ], ts=1020.0))
    types2 = {c.dst_prefix: c.change_type for c in chgs2}
    assert types2["10.1.0.0/24"] == RouteChangeType.NEXT_HOP_CHANGED.value
    assert types2["10.2.0.0/24"] == RouteChangeType.ROUTE_DEACTIVATED.value
    assert types2["10.3.0.0/24"] == RouteChangeType.ROUTE_DISABLED.value

    _, chgs3 = store.create_snapshot_from_collection(_col("dev_a", [
        _r("10.1.0.0/24", "10.0.0.9", distance=5, metric=10, active=True, disabled=False, immediate_gw="10.0.0.9%ether3"),
        _r("10.2.0.0/24", "10.0.0.1", active=True, metric=50, gateways=["10.0.0.1"]),
        _r("10.3.0.0/24", "10.0.0.1", routing_table="vrf_corp", disabled=False),
    ], ts=1030.0))
    types3 = {c.dst_prefix: c.change_type for c in chgs3}
    assert types3["10.1.0.0/24"] == RouteChangeType.DISTANCE_CHANGED.value
    assert types3["10.2.0.0/24"] == RouteChangeType.ROUTE_ACTIVATED.value
    assert types3["10.3.0.0/24"] == RouteChangeType.ROUTE_ENABLED.value


def test_08_incomplete_collection_suppresses_false_removals(tmp_path: Path):
    db = tmp_path / "hist_08.db"
    store = RouteHistoryStore(db)
    store.create_snapshot_from_collection(_col("dev_a", [_r("0.0.0.0/0", "10.0.0.1"), _r("10.50.0.0/16", "10.0.0.2")], ts=1000.0))

    # Partial truncated output missing 10.50.0.0/16 -> MUST NOT emit ROUTE_REMOVED!
    _, chgs = store.create_snapshot_from_collection(
        _col("dev_a", [_r("0.0.0.0/0", "10.0.0.1")], ts=1010.0, status=RouteCollectionStatus.PARTIAL.value, completeness=RouteCompleteness.PARTIAL.value)
    )
    assert len(chgs) == 1
    assert chgs[0].change_type == RouteChangeType.ROUTE_STATE_UNKNOWN.value
    assert chgs[0].metadata["suppressed_confirmed_removal"] is True
    assert chgs[0].metadata["reason"] == "COLLECTION_INCOMPLETE"


def test_09_unreachable_device_suppresses_false_removals(tmp_path: Path):
    db = tmp_path / "hist_09.db"
    store = RouteHistoryStore(db)
    store.create_snapshot_from_collection(_col("dev_a", [_r("0.0.0.0/0", "10.0.0.1")], ts=1000.0))

    _, chgs = store.create_snapshot_from_collection(
        _col("dev_a", [], ts=1010.0, status=RouteCollectionStatus.UNREACHABLE.value, completeness=RouteCompleteness.UNREACHABLE.value, errors=["SSH connection timed out"])
    )
    assert len(chgs) == 1
    assert chgs[0].change_type == RouteChangeType.ROUTE_STATE_UNKNOWN.value
    assert chgs[0].metadata["reason"] == "DEVICE_UNREACHABLE"


def test_10_parser_failure_and_expired_evidence_suppress_false_removals(tmp_path: Path):
    db = tmp_path / "hist_10.db"
    store = RouteHistoryStore(db)
    store.create_snapshot_from_collection(_col("dev_a", [_r("0.0.0.0/0", "10.0.0.1")], ts=1000.0))

    _, chgs_pf = store.create_snapshot_from_collection(
        _col("dev_a", [], ts=1010.0, status=RouteCollectionStatus.FAILED.value, completeness=RouteCompleteness.FAILED.value, errors=["Malformed parser block"])
    )
    assert chgs_pf[0].change_type == RouteChangeType.ROUTE_STATE_UNKNOWN.value
    assert chgs_pf[0].metadata["reason"] == "PARSER_FAILURE"

    # Expired evidence metadata also suppresses confirmed deletion
    _, chgs_exp = store.create_snapshot_from_collection(
        _col("dev_a", [], ts=1020.0, completeness=RouteCompleteness.EMPTY.value),
        extra_metadata={"evidence_expired": True},
    )
    assert chgs_exp[0].change_type == RouteChangeType.ROUTE_STATE_UNKNOWN.value
    assert chgs_exp[0].metadata["reason"] == "EVIDENCE_EXPIRED"


def test_11_duplicate_evidence_id_and_unchanged_deduplication(tmp_path: Path):
    db = tmp_path / "hist_11.db"
    store = RouteHistoryStore(db)
    c1 = _col("dev_a", [_r("0.0.0.0/0", "10.0.0.1")], ts=1000.0, evidence_id="ev_same_123")

    s1, _ = store.create_snapshot_from_collection(c1, deduplicate_by_evidence_id=True)
    s2, chgs2 = store.create_snapshot_from_collection(c1, deduplicate_by_evidence_id=True)
    assert s1.snapshot_id == s2.snapshot_id
    assert chgs2 == []

    snaps, total = store.list_snapshots(device_id="dev_a")
    assert total == 1


def test_12_historical_analytics_flapping_and_temporal_correlation(tmp_path: Path):
    db = tmp_path / "hist_12.db"
    topo_engine = TopologyEngine(db_path=db)
    topo_engine.upsert_node("dev_a", name="Router-A", ip="10.0.0.1")

    store = RouteHistoryStore(db)
    base = _r("10.0.0.0/24", "ether1", connect=True, protocol="connected", distance=0)
    flap = _r("198.51.100.0/24", "10.0.0.2")

    t0 = time.time()
    store.create_snapshot_from_collection(_col("dev_a", [base, flap], ts=t0))
    store.create_snapshot_from_collection(_col("dev_a", [base], ts=t0 + 5))
    store.create_snapshot_from_collection(_col("dev_a", [base, flap], ts=t0 + 10))
    store.create_snapshot_from_collection(_col("dev_a", [base], ts=t0 + 15))

    analytics = store.get_historical_analytics(device_id="dev_a", correlation_window_sec=60.0)
    assert len(analytics["flapping_prefixes"]) == 1
    assert analytics["flapping_prefixes"][0]["dst_prefix"] == "198.51.100.0/24"
    assert analytics["flapping_prefixes"][0]["transition_count"] == 3
    assert analytics["route_stability_score"] < 1.0
    # Correlations with topology_changes are explicitly marked NOT proven causation
    for corr in analytics["correlated_topology_and_nms_events"]:
        assert corr["relationship"] == "TEMPORAL_CORRELATION_NOT_PROVEN_CAUSATION"


def test_13_concurrent_multi_thread_snapshot_creation(tmp_path: Path):
    db = tmp_path / "hist_13.db"
    store = RouteHistoryStore(db)
    errors: List[Exception] = []

    def _worker(idx: int) -> None:
        try:
            dev_id = f"dev_{idx % 4}"
            col = _col(
                dev_id,
                [_r(f"10.{idx}.0.0/16", "10.0.0.1", device_id=dev_id)],
                ts=1000.0 + idx,
                evidence_id=f"ev_conc_{idx}",
            )
            store.create_snapshot_from_collection(col)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15.0)

    assert errors == []
    _, total = store.list_snapshots(limit=100)
    assert total == 12


def test_14_database_lock_retry_resilience(tmp_path: Path, monkeypatch):
    from core import topology_db

    db = tmp_path / "hist_14.db"
    store = RouteHistoryStore(db)

    attempts = {"count": 0}
    orig_tx = topology_db.topology_transaction

    def _flaky_tx(path, write=False, **kwargs):
        if write:
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise sqlite3.OperationalError("database is locked")
        return orig_tx(path, write=write, **kwargs)

    from core.routing import route_history
    monkeypatch.setattr(route_history, "topology_transaction", _flaky_tx)

    snap, _ = store.create_snapshot_from_collection(_col("dev_a", [_r("0.0.0.0/0", "10.0.0.1")], ts=2000.0))
    assert attempts["count"] == 2
    assert snap.verify_integrity() is True


def test_15_route_history_api_endpoints_and_topology_history_preservation(tmp_path: Path, monkeypatch):
    db = tmp_path / "hist_15.db"
    topo_engine = TopologyEngine(db_path=db)
    topo_engine.upsert_node("dev_chr", name="CHR", ip="10.66.38.30")
    topo_snap = topo_engine.create_snapshot(trigger_type="manual", description="Baseline topo")
    topo_hash_before = topo_snap.sha256_hash

    store = RouteHistoryStore(db)
    from api.main import app
    from api.routers.topology import require_topology_admin
    from core.routing import route_collector, route_history

    dummy_col = route_collector.MultiDeviceRouteCollector()
    dummy_col._latest_results["dev_chr"] = _col(
        "dev_chr",
        [_r("0.0.0.0/0", "10.66.38.1", device_id="dev_chr"), _r("10.66.38.0/24", "ether1", device_id="dev_chr", connect=True, protocol="connected", distance=0)],
        ts=3000.0,
    )

    monkeypatch.setattr(route_history, "get_route_history_store", lambda db_path=None: store)
    monkeypatch.setattr(route_collector, "get_route_collector", lambda: dummy_col)
    app.dependency_overrides[require_topology_admin] = lambda: "admin_tester"

    try:
        client = TestClient(app)
        r_post = client.post(
            "/api/topology/route-snapshots",
            json={"device_ids": ["dev_chr"], "description": "Snap 1", "topology_snapshot_id": topo_snap.snapshot_id},
        )
        assert r_post.status_code == 200
        snap1_id = r_post.json()["snapshots"][0]["snapshot_id"]

        # Update cached route and take Snap 2
        dummy_col._latest_results["dev_chr"] = _col(
            "dev_chr",
            [_r("0.0.0.0/0", "10.66.38.254", device_id="dev_chr"), _r("10.66.38.0/24", "ether1", device_id="dev_chr", connect=True, protocol="connected", distance=0)],
            ts=3010.0,
        )
        r_post2 = client.post("/api/topology/route-snapshots", json={"device_ids": ["dev_chr"], "description": "Snap 2"})
        snap2_id = r_post2.json()["snapshots"][0]["snapshot_id"]

        r_list = client.get("/api/topology/route-snapshots?device_id=dev_chr")
        assert r_list.status_code == 200
        assert r_list.json()["total"] == 2

        r_ver = client.get(f"/api/topology/route-snapshots/{snap1_id}/verify")
        assert r_ver.status_code == 200
        assert r_ver.json()["verified"] is True

        r_cmp = client.get(f"/api/topology/route-snapshots/compare?base_id={snap1_id}&target_id={snap2_id}")
        assert r_cmp.status_code == 200
        assert r_cmp.json()["diff"]["summary_counts"]["GATEWAY_CHANGED"] == 1

        r_chgs = client.get("/api/topology/route-snapshots/changes?device_id=dev_chr")
        assert r_chgs.status_code == 200
        chg_id = r_chgs.json()["changes"][0]["change_id"]

        r_chg_detail = client.get(f"/api/topology/route-snapshots/changes/{chg_id}")
        assert r_chg_detail.status_code == 200
        assert r_chg_detail.json()["change"]["change_type"] == "GATEWAY_CHANGED"

        r_ana = client.get("/api/topology/route-snapshots/analytics?device_id=dev_chr")
        assert r_ana.status_code == 200
        assert "route_stability_score" in r_ana.json()["analytics"]

        # Existing topology snapshot checksum & row remain 100% intact!
        topo_snap_after = topo_engine.get_snapshot(topo_snap.snapshot_id)
        assert topo_snap_after is not None
        assert topo_snap_after.verify_integrity() is True
        assert topo_snap_after.sha256_hash == topo_hash_before
    finally:
        app.dependency_overrides.pop(require_topology_admin, None)
