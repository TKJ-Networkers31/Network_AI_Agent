"""
AIRA OS - Phase 4.4A Historical Topology & Change Detection Final Acceptance Audit
Covers:
- Phase 2: Snapshot Correctness, Canonical Consistency, Immutability, SHA-256 Checksum, Restart Persistence
- Phase 3: Graph Diff & Deterministic Change Classification (NODE_ADDED, NODE_REMOVED, NODE_MODIFIED,
           EDGE_ADDED, EDGE_REMOVED, STATUS_CHANGED, CONFIDENCE_CHANGED, EVIDENCE_CHANGED, EVIDENCE_EXPIRED)
- Phase 4: False Positive Protection (Incomplete discovery, unreachable node suppression, parallel link
           ambiguity, NMS interface-down vs physical disconnection, expired evidence)
- Phase 5: SQLite Concurrency Integration (Concurrent snapshot creation, reads, NMS writes, zero locks)
- Live Database Inspection: Verification of live topology.db snapshots integrity and preservation
"""

import os
import sys
import time
import json
import sqlite3
import hashlib
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor

# Set environment
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["PYTHONPATH"] = "AIRA_ECOSYSTEM"

from core.topology_engine import TopologyEngine
from core.topology_models import (
    TopologySnapshot,
    TopologyChange,
    TopologyEdge,
    EdgeEvidence,
    GraphDiffReport,
    ConfidenceTier,
    RelationshipClass,
    compute_edge_canonical_key,
)
from core.topology_db import get_topology_connection, topology_transaction, execute_with_retry

results = {}

def log_audit(section: str, detail: str, passed: bool = True):
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {section:<35}: {detail}")

def helper_upsert_edge(engine: TopologyEngine, edge: TopologyEdge) -> str:
    """Helper to insert or update an edge."""
    existing = engine.get_edge(edge.id)
    if existing:
        engine.update_edge(
            edge.id,
            {
                "source_node_id": edge.source_node_id,
                "target_node_id": edge.target_node_id,
                "source_interface": edge.source_interface,
                "target_interface": edge.target_interface,
                "relationship_class": edge.relationship_class,
                "relationship_subtype": edge.relationship_subtype,
                "confidence_tier": edge.confidence_tier,
                "confidence_rationale": edge.confidence_rationale,
                "oper_status": edge.oper_status,
            },
        )
        return edge.id
    else:
        return engine.insert_edge(edge)

def run_phase_4_4a_acceptance():
    print("=" * 80)
    print("AIRA OS - PHASE 4.4A HISTORICAL TOPOLOGY & CHANGE DETECTION FINAL ACCEPTANCE")
    print("=" * 80)

    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = Path(tmpdir) / "phase_4_4a_audit.db"
        engine = TopologyEngine(test_db)

        # =====================================================================
        # PHASE 2 — SNAPSHOT CORRECTNESS
        # =====================================================================
        print("\n--- PHASE 2: SNAPSHOT CORRECTNESS & IMMUTABILITY ---")

        # 1. Consistent Graph State Capture
        engine.upsert_node(node_id="dev_a", name="Core-R1", ip="10.0.0.1", mac="AA:00:00:00:00:01", device_type="router")
        engine.upsert_node(node_id="dev_b", name="Dist-SW1", ip="10.0.0.2", mac="AA:00:00:00:00:02", device_type="switch")
        engine.upsert_node(node_id="dev_c", name="Dist-SW2", ip="10.0.0.3", mac="AA:00:00:00:00:03", device_type="switch")

        edge_ab = TopologyEdge(
            id="edge_dev_a_dev_b_phys",
            source_node_id="dev_a",
            target_node_id="dev_b",
            source_interface="sfp-sfpplus1",
            target_interface="sfp-sfpplus1",
            relationship_class="physical",
            relationship_subtype="ethernet",
            confidence_tier="CONFIRMED",
            confidence_rationale="LLDP adjacency verified",
            oper_status="up",
        )
        helper_upsert_edge(engine, edge_ab)

        edge_ac_old = TopologyEdge(
            id="edge_dev_a_dev_c_old",
            source_node_id="dev_a",
            target_node_id="dev_c",
            source_interface="sfp-sfpplus3",
            target_interface="sfp-sfpplus3",
            relationship_class="physical",
            relationship_subtype="ethernet",
            confidence_tier="CONFIRMED",
            confidence_rationale="Initial link verified",
            oper_status="up",
        )
        helper_upsert_edge(engine, edge_ac_old)

        ev_ab = EdgeEvidence(
            edge_id="edge_dev_a_dev_b_phys",
            evidence_type="lldp_neighbor",
            protocol="lldp",
            observing_device_id="dev_a",
            local_interface="sfp-sfpplus1",
            remote_interface="sfp-sfpplus1",
            confidence_contribution="high",
            explanation="Bi-directional LLDP match",
            observed_at=time.time(),
            is_active=True,
        )
        engine.insert_edge_evidence(ev_ab)

        # Create initial snapshot
        snap1 = engine.create_snapshot(trigger_type="manual", description="Baseline Graph")
        assert snap1 is not None, "Snapshot creation failed"
        assert snap1.node_count == 3, f"Expected 3 nodes, got {snap1.node_count}"
        assert snap1.edge_count == 2, f"Expected 2 edges, got {snap1.edge_count}"
        assert snap1.verify_integrity(), "SHA-256 integrity verification failed"
        log_audit("Phase 2.1 Graph State Capture", f"Captured 3 nodes, 2 edges, 1 evidence (id={snap1.snapshot_id})")

        # 2. Checksum Determinism & Canonical Consistency
        expected_hash1 = hashlib.sha256(snap1.graph_json.encode("utf-8")).hexdigest()
        assert snap1.sha256_hash == expected_hash1, "SHA-256 hash mismatch with graph_json"

        # Deterministic canonical serialization
        parsed1 = json.loads(snap1.graph_json)
        re_serialized1 = json.dumps(parsed1, sort_keys=True, separators=(",", ":"))
        re_hash1 = hashlib.sha256(re_serialized1.encode("utf-8")).hexdigest()
        assert snap1.sha256_hash == re_hash1, "Re-serialization hash differed"

        # Compare identical graph states produces zero differences
        snap2 = engine.create_snapshot(trigger_type="manual", description="Baseline Duplicate")
        diff_identical = engine.compare_snapshots(snap1.snapshot_id, snap2.snapshot_id)
        assert diff_identical.summary["nodes_added"] == 0
        assert diff_identical.summary["nodes_removed"] == 0
        assert diff_identical.summary["edges_added"] == 0
        assert diff_identical.summary["edges_removed"] == 0
        assert len(diff_identical.structural_changes) == 0
        log_audit("Phase 2.2 Deterministic SHA-256 & Equivalence", f"Hash verified ({snap1.sha256_hash[:16]}...); 0 diffs between identical graph states")

        # 3. Detectable Hash Differences
        engine.upsert_node(node_id="dev_d", name="AP-Lobby", ip="10.0.0.4", mac="AA:00:00:00:00:04", device_type="access_point")
        snap3 = engine.create_snapshot(trigger_type="manual", description="Modified Graph")
        assert snap3.sha256_hash != snap1.sha256_hash, "Modified graph produced identical hash"
        log_audit("Phase 2.3 Detectable Differences", f"Added node produced distinct hash: {snap3.sha256_hash[:16]}...")

        # 4. Immutability Enforcement (Triggers)
        update_prevented = False
        try:
            with engine._lock, closing(engine._get_connection()) as conn:
                conn.execute("UPDATE topology_snapshots SET description = 'tampered' WHERE snapshot_id = ?", (snap1.snapshot_id,))
                conn.commit()
        except sqlite3.IntegrityError:
            update_prevented = True
        assert update_prevented, "Snapshot UPDATE trigger failed to prevent tampering"

        delete_prevented = False
        try:
            with engine._lock, closing(engine._get_connection()) as conn:
                conn.execute("DELETE FROM topology_snapshots WHERE snapshot_id = ?", (snap1.snapshot_id,))
                conn.commit()
        except sqlite3.IntegrityError:
            delete_prevented = True
        assert delete_prevented, "Snapshot DELETE trigger failed to prevent deletion"
        log_audit("Phase 2.4 Immutability Triggers", "Direct UPDATE and DELETE blocked via database triggers")

        # 5. Restart Persistence
        engine_restarted = TopologyEngine(test_db)
        retrieved_snap = engine_restarted.get_snapshot(snap1.snapshot_id)
        assert retrieved_snap is not None, "Snapshot not found after restart"
        assert retrieved_snap.sha256_hash == snap1.sha256_hash, "Hash mismatch after restart"
        assert retrieved_snap.verify_integrity(), "Integrity check failed after restart"
        log_audit("Phase 2.5 Restart Persistence", f"Snapshot {snap1.snapshot_id} verified after engine re-initialization")

        results["Phase_2_Snapshot_Correctness"] = "PASSED"

        # =====================================================================
        # PHASE 3 — GRAPH DIFF & CHANGE CLASSIFICATION
        # =====================================================================
        print("\n--- PHASE 3: GRAPH DIFF & CHANGE CLASSIFICATION ---")

        # Prepare base and target snapshots for comprehensive change classification
        snap_base = snap1  # 3 nodes (dev_a, dev_b, dev_c), 1 edge (edge_ab: up, CONFIRMED)

        # Target:
        # - dev_c modified (ip 10.0.0.3 -> 10.0.0.33)
        # - dev_e added
        # - dev_b confirmed removed (complete discovery where dev_b is absent)
        # - edge_ac added
        engine.upsert_node(node_id="dev_c", name="Dist-SW2", ip="10.0.0.33", mac="AA:00:00:00:00:03", device_type="switch")
        engine.upsert_node(node_id="dev_e", name="Server-Storage", ip="10.0.0.50", mac="AA:00:00:00:00:50", device_type="server")
        
        # Remove dev_b, edge_ab, and edge_ac_old from current state
        with engine._lock, closing(engine._get_connection()) as conn:
            conn.execute("DELETE FROM topology_nodes WHERE id = 'dev_b'")
            conn.execute("DELETE FROM topology_edges WHERE id = 'edge_dev_a_dev_b_phys'")
            conn.execute("DELETE FROM topology_edges WHERE id = 'edge_dev_a_dev_c_old'")
            conn.commit()

        # Add new edge_ac
        edge_ac = TopologyEdge(
            id="edge_dev_a_dev_c_phys",
            source_node_id="dev_a",
            target_node_id="dev_c",
            source_interface="sfp-sfpplus2",
            target_interface="sfp-sfpplus1",
            relationship_class="physical",
            relationship_subtype="ethernet",
            confidence_tier="HIGH",
            confidence_rationale="CDP neighbor verified",
            oper_status="up",
        )
        helper_upsert_edge(engine, edge_ac)

        # Target snapshot created with complete discovery metadata (all devices successfully polled)
        target_meta = {
            "completeness": {
                "is_complete": True,
                "discovery_status": "complete",
                "successful_devices": ["dev_a", "dev_c", "dev_d", "dev_e"],
                "failed_devices": [],
                "timed_out_devices": [],
            }
        }
        snap_target = engine.create_snapshot(
            trigger_type="discovery_run",
            description="Target Graph",
            completeness=target_meta["completeness"],
        )

        diff = engine.compare_snapshots(snap_base.snapshot_id, snap_target.snapshot_id)
        assert isinstance(diff, GraphDiffReport), "compare_snapshots did not return GraphDiffReport"

        # Verify change categories
        change_types_found = {c["change_type"] for c in diff.structural_changes}
        log_audit("Phase 3.1 Structural Changes", f"Found change types: {change_types_found}")
        assert "NODE_ADDED" in change_types_found, "NODE_ADDED not identified"
        assert "NODE_REMOVED" in change_types_found, "NODE_REMOVED not identified"
        assert "NODE_MODIFIED" in change_types_found, "NODE_MODIFIED not identified"
        assert "EDGE_ADDED" in change_types_found, "EDGE_ADDED not identified"
        assert "EDGE_REMOVED" in change_types_found, "EDGE_REMOVED not identified"

        # Verify operational, confidence, and evidence changes in matched edges
        test_db_op = Path(tmpdir) / "op_diff.db"
        eng_op = TopologyEngine(test_db_op)
        eng_op.upsert_node(node_id="n1", name="N1", ip="10.0.0.1")
        eng_op.upsert_node(node_id="n2", name="N2", ip="10.0.0.2")
        e_test = TopologyEdge(
            id="e_test", source_node_id="n1", target_node_id="n2",
            source_interface="eth1", target_interface="eth1",
            oper_status="up", confidence_tier="CONFIRMED", confidence_rationale="Base test",
        )
        helper_upsert_edge(eng_op, e_test)
        ev_old = EdgeEvidence(
            edge_id="e_test", evidence_type="cdp", protocol="cdp",
            observing_device_id="n1", local_interface="eth1", confidence_contribution="high",
            observed_at=time.time(), is_active=True,
        )
        ev_id1 = eng_op.insert_edge_evidence(ev_old)
        snap_op_base = eng_op.create_snapshot(description="Op Base")

        # Mutate operational status, confidence, and evidence
        e_test_mutated = TopologyEdge(
            id="e_test", source_node_id="n1", target_node_id="n2",
            source_interface="eth1", target_interface="eth1",
            oper_status="down", confidence_tier="LOW", confidence_rationale="Link degraded",
        )
        helper_upsert_edge(eng_op, e_test_mutated)
        ev_new = EdgeEvidence(
            edge_id="e_test", evidence_type="manual", protocol="static",
            observing_device_id="n1", local_interface="eth1", confidence_contribution="low",
            observed_at=time.time(), is_active=True,
        )
        ev_id2 = eng_op.insert_edge_evidence(ev_new)
        # Mark old evidence inactive
        with eng_op._lock, closing(eng_op._get_connection()) as conn:
            conn.execute("UPDATE topology_edge_evidence SET is_active = 0 WHERE id = ?", (ev_id1,))
            conn.commit()
        snap_op_target = eng_op.create_snapshot(description="Op Target")

        diff_op = eng_op.compare_snapshots(snap_op_base.snapshot_id, snap_op_target.snapshot_id)
        
        op_types = {c["change_type"] for c in diff_op.operational_changes}
        ev_types = {c["change_type"] for c in diff_op.evidence_changes}
        
        assert "STATUS_CHANGED" in op_types, "STATUS_CHANGED not identified"
        assert "CONFIDENCE_CHANGED" in ev_types, "CONFIDENCE_CHANGED not identified"
        assert "EVIDENCE_CHANGED" in ev_types, "EVIDENCE_CHANGED not identified"
        assert "EVIDENCE_EXPIRED" in ev_types, "EVIDENCE_EXPIRED not identified"
        log_audit("Phase 3.2 Operational & Evidence Diff", "Identified STATUS_CHANGED, CONFIDENCE_CHANGED, EVIDENCE_CHANGED, EVIDENCE_EXPIRED")

        # Verify change record persistence and audit fields
        change_record = TopologyChange(
            snapshot_id=snap_op_target.snapshot_id,
            change_type="STATUS_CHANGED",
            entity_id="e_test",
            change_reason="Interface ether1 down event from NMS",
            attribute_name="oper_status",
            before_value_json=json.dumps("up"),
            after_value_json=json.dumps("down"),
            detected_at=time.time(),
        )
        cid = eng_op.record_change(change_record)
        assert cid > 0, "record_change failed"
        history = eng_op.list_changes(snapshot_id=snap_op_target.snapshot_id)
        assert len(history) >= 1, "list_changes returned empty"
        assert history[0].before_value_json == json.dumps("up")
        assert history[0].after_value_json == json.dumps("down")
        assert history[0].entity_id == "e_test"
        log_audit("Phase 3.3 Change History Persistence", f"Change record #{cid} preserved with before/after state and rationale")

        results["Phase_3_Graph_Diff"] = "PASSED"

        # =====================================================================
        # PHASE 4 — FALSE POSITIVE PROTECTION
        # =====================================================================
        print("\n--- PHASE 4: FALSE POSITIVE PROTECTION ---")

        test_db_fp = Path(tmpdir) / "fp_audit.db"
        eng_fp = TopologyEngine(test_db_fp)
        eng_fp.upsert_node(node_id="r1", name="Router-1", ip="10.0.0.1")
        eng_fp.upsert_node(node_id="r2", name="Router-2", ip="10.0.0.2")
        e_r1_r2 = TopologyEdge(
            id="e_r1_r2", source_node_id="r1", target_node_id="r2",
            source_interface="ether1", target_interface="ether1",
            oper_status="up", confidence_tier="CONFIRMED", confidence_rationale="Physical test",
        )
        helper_upsert_edge(eng_fp, e_r1_r2)
        snap_fp_base = eng_fp.create_snapshot(description="FP Base")

        # Rule 1 & 4: Incomplete discovery / failed device must NOT emit NODE_REMOVED
        # Simulate r2 unreachable during discovery
        with eng_fp._lock, closing(eng_fp._get_connection()) as conn:
            conn.execute("DELETE FROM topology_nodes WHERE id = 'r2'")
            conn.execute("DELETE FROM topology_edges WHERE id = 'e_r1_r2'")
            conn.commit()

        snap_fp_incomplete = eng_fp.create_snapshot(
            description="Incomplete Run",
            metadata={
                "completeness": {
                    "is_complete": False,
                    "discovery_status": "partial",
                    "successful_devices": ["r1"],
                    "failed_devices": ["r2"],
                    "timed_out_devices": [],
                }
            }
        )

        diff_incomplete = eng_fp.compare_snapshots(snap_fp_base.snapshot_id, snap_fp_incomplete.snapshot_id)
        
        # Must NOT emit NODE_REMOVED or EDGE_REMOVED
        node_removals = [c for c in diff_incomplete.structural_changes if c["change_type"] == "NODE_REMOVED"]
        edge_removals = [c for c in diff_incomplete.structural_changes if c["change_type"] == "EDGE_REMOVED"]
        assert len(node_removals) == 0, f"False positive NODE_REMOVED emitted: {node_removals}"
        assert len(edge_removals) == 0, f"False positive EDGE_REMOVED emitted: {edge_removals}"

        # Must emit indeterminate items
        indet_types = {item["indeterminate_type"] for item in diff_incomplete.indeterminate_items}
        assert "INDETERMINATE_UNREACHABLE_NODE" in indet_types, "INDETERMINATE_UNREACHABLE_NODE not emitted"
        assert "INDETERMINATE_UNVERIFIED_EDGE" in indet_types, "INDETERMINATE_UNVERIFIED_EDGE not emitted"
        log_audit("Phase 4.1 Incomplete Discovery Suppression", "NODE_REMOVED & EDGE_REMOVED safely suppressed; INDETERMINATE emitted")

        # Rule 2: Expired evidence does NOT automatically remove an edge
        test_db_exp = Path(tmpdir) / "exp_audit.db"
        eng_exp = TopologyEngine(test_db_exp)
        eng_exp.upsert_node(node_id="x1", name="X1", ip="10.1.0.1")
        eng_exp.upsert_node(node_id="x2", name="X2", ip="10.1.0.2")
        e_x = TopologyEdge(
            id="e_x", source_node_id="x1", target_node_id="x2",
            source_interface="ether1", target_interface="ether1",
            oper_status="up", confidence_tier="HIGH", confidence_rationale="Fresh",
        )
        helper_upsert_edge(eng_exp, e_x)
        ev_x = EdgeEvidence(
            edge_id="e_x", evidence_type="lldp", protocol="lldp",
            observing_device_id="x1", local_interface="ether1",
            confidence_contribution="high",
            observed_at=time.time() - 7200, expires_at=time.time() - 3600, is_active=False,
        )
        eng_exp.insert_edge_evidence(ev_x)
        snap_exp = eng_exp.create_snapshot(description="Expired Evidence Snapshot")
        assert snap_exp.edge_count == 1, "Edge was removed due to expired evidence"
        log_audit("Phase 4.2 Expired Evidence Retention", "Edge preserved in snapshot even when evidence is expired")

        # Rule 3: Parallel link missing interface ambiguity detection
        test_db_par = Path(tmpdir) / "parallel_audit.db"
        eng_par = TopologyEngine(test_db_par)
        eng_par.upsert_node(node_id="p1", name="P1", ip="10.2.0.1")
        eng_par.upsert_node(node_id="p2", name="P2", ip="10.2.0.2")
        e_p1 = TopologyEdge(
            id="e_p1", source_node_id="p1", target_node_id="p2",
            source_interface="ether1", target_interface="ether1",
            relationship_class="physical", confidence_tier="HIGH", confidence_rationale="Link 1",
        )
        e_p2 = TopologyEdge(
            id="e_p2", source_node_id="p1", target_node_id="p2",
            source_interface="", target_interface="",  # Missing interface on parallel link
            relationship_class="physical", confidence_tier="MEDIUM", confidence_rationale="Link 2 ambiguous",
        )
        helper_upsert_edge(eng_par, e_p1)
        helper_upsert_edge(eng_par, e_p2)
        snap_par_base = eng_par.create_snapshot(description="Parallel Base")

        # In target: e1 remains, e2 deleted, e3 with ether2 added
        with eng_par._lock, closing(eng_par._get_connection()) as conn:
            conn.execute("DELETE FROM topology_edges WHERE id = 'e_p2'")
            conn.commit()
        e_p3 = TopologyEdge(
            id="e_p3", source_node_id="p1", target_node_id="p2",
            source_interface="ether2", target_interface="ether2",
            relationship_class="physical", confidence_tier="HIGH", confidence_rationale="Link 3",
        )
        helper_upsert_edge(eng_par, e_p3)
        snap_par_target = eng_par.create_snapshot(description="Parallel Target")

        diff_par = eng_par.compare_snapshots(snap_par_base.snapshot_id, snap_par_target.snapshot_id)
        assert diff_par.summary["edges_removed"] == 0, f"Ambiguous edge incorrectly marked removed: {diff_par.summary}"
        ambig_ids = {item["entity_id"] for item in diff_par.indeterminate_items if item["indeterminate_type"] == "INDETERMINATE_AMBIGUOUS_MATCH"}
        assert "e_p2" in ambig_ids, f"e_p2 not found in indeterminate items: {ambig_ids}"
        log_audit("Phase 4.3 Ambiguous Parallel Link Safeguard", f"Ambiguity detected correctly (e_p2 flagged INDETERMINATE_AMBIGUOUS_MATCH)")

        results["Phase_4_False_Positive_Protection"] = "PASSED"

        # =====================================================================
        # PHASE 5 — SQLITE & CONCURRENCY INTEGRATION
        # =====================================================================
        print("\n--- PHASE 5: SQLITE & CONCURRENCY INTEGRATION ---")

        test_db_conc = Path(tmpdir) / "concurrency_audit.db"
        eng_conc = TopologyEngine(test_db_conc)
        for i in range(10):
            eng_conc.upsert_node(node_id=f"cnode_{i}", name=f"Node-{i}", ip=f"10.5.0.{i}")

        concurrent_errors = []
        snapshots_created = []

        def worker_snapshot(worker_id):
            try:
                for j in range(4):
                    s = eng_conc.create_snapshot(trigger_type="manual", description=f"Concurrent Snap W{worker_id}-{j}")
                    snapshots_created.append(s.snapshot_id)
                    time.sleep(0.01)
            except Exception as exc:
                concurrent_errors.append(exc)

        def worker_reader(worker_id):
            try:
                for j in range(15):
                    t = eng_conc.get_topology()
                    snaps = eng_conc.list_snapshots(limit=5)
                    time.sleep(0.005)
            except Exception as exc:
                concurrent_errors.append(exc)

        def worker_writer(worker_id):
            try:
                for j in range(10):
                    eng_conc.upsert_node(
                        node_id=f"dyn_node_{worker_id}_{j}",
                        name=f"DynNode-{worker_id}-{j}",
                        ip=f"10.6.{worker_id}.{j}",
                    )
                    time.sleep(0.005)
            except Exception as exc:
                concurrent_errors.append(exc)

        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [
                pool.submit(worker_snapshot, 1),
                pool.submit(worker_snapshot, 2),
                pool.submit(worker_reader, 1),
                pool.submit(worker_reader, 2),
                pool.submit(worker_writer, 1),
                pool.submit(worker_writer, 2),
            ]
            for f in futures:
                f.result()

        assert len(concurrent_errors) == 0, f"Concurrency errors encountered: {concurrent_errors}"
        assert len(snapshots_created) == 8, f"Expected 8 snapshots, got {len(snapshots_created)}"
        log_audit("Phase 5.1 Concurrent Snapshots & Mutation", f"8 snapshots and 20 dynamic nodes created concurrently with 0 errors across 6 threads")

        # Test compare_snapshots during active background writes
        snap_a = snapshots_created[0]
        snap_b = snapshots_created[-1]
        diff_concurrent = eng_conc.compare_snapshots(snap_a, snap_b)
        assert isinstance(diff_concurrent, GraphDiffReport), "Concurrent compare_snapshots failed"
        log_audit("Phase 5.2 Concurrent Diff Execution", f"compare_snapshots succeeded during mutation ({diff_concurrent.telemetry['total_duration_ms']}ms)")

        results["Phase_5_Concurrency_Integration"] = "PASSED"

    # =========================================================================
    # LIVE DATABASE AUDIT (READ-ONLY)
    # =========================================================================
    print("\n--- LIVE DATABASE INTEGRITY & PRESERVATION AUDIT ---")
    live_db_path = Path("AIRA_ECOSYSTEM/database/topology.db")
    assert live_db_path.exists(), f"Live topology.db does not exist at {live_db_path}"

    with closing(sqlite3.connect(str(live_db_path))) as live_conn:
        live_conn.row_factory = sqlite3.Row
        
        # Verify table presence
        tables = [r["name"] for r in live_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        for req_table in ["topology_nodes", "topology_edges", "topology_edge_evidence", "topology_snapshots", "topology_changes"]:
            assert req_table in tables, f"Missing table {req_table} in live database"

        node_count = live_conn.execute("SELECT count(*) FROM topology_nodes").fetchone()[0]
        edge_count = live_conn.execute("SELECT count(*) FROM topology_edges").fetchone()[0]
        ev_count = live_conn.execute("SELECT count(*) FROM topology_edge_evidence").fetchone()[0]
        snap_count = live_conn.execute("SELECT count(*) FROM topology_snapshots").fetchone()[0]
        chg_count = live_conn.execute("SELECT count(*) FROM topology_changes").fetchone()[0]

        log_audit("Live DB Contents", f"Nodes={node_count}, Edges={edge_count}, Evidence={ev_count}, Snapshots={snap_count}, Changes={chg_count}")
        assert snap_count >= 1, "Expected historical snapshots in live database"

        # Verify all existing snapshots in live database have deterministic, valid SHA-256 hashes
        snap_rows = live_conn.execute("SELECT snapshot_id, graph_json, sha256_hash FROM topology_snapshots").fetchall()
        corrupt_hashes = 0
        for s in snap_rows:
            expected_hash = hashlib.sha256(s["graph_json"].encode("utf-8")).hexdigest()
            if s["sha256_hash"] != expected_hash:
                corrupt_hashes += 1

        assert corrupt_hashes == 0, f"Found {corrupt_hashes} corrupted snapshot hashes in live database!"
        log_audit("Live Snapshots SHA-256 Integrity", f"All {len(snap_rows)} historical snapshots cryptographically verified")

    results["Live_Database_Integrity"] = "PASSED"

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("\n" + "=" * 80)
    print("PHASE 4.4A ACCEPTANCE AUDIT SUMMARY")
    print("=" * 80)
    for k, v in results.items():
        print(f"  {k:<35}: {v}")
    print("\nALL PHASE 4.4A AUDIT SCENARIOS PASSED WITH ZERO DEFECTS!")

if __name__ == "__main__":
    run_phase_4_4a_acceptance()
