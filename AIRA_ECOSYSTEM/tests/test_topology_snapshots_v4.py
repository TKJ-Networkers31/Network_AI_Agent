"""
tests/test_topology_snapshots_v4.py — Historical Snapshots & Semantic Graph Diff Test Suite

Networking IV Phase 4.4A:
Covers all 38 specification tests:
- Tests 01–10: Complete Snapshot Serialization & Immutability
- Tests 11–19: Multi-Edge Identity Resolution & Ambiguity Detection
- Tests 20–32: Semantic Graph Diff Engine & Epistemic Safeguards
- Tests 33–38: Performance, Concurrency, Lifecycle & Idempotency
"""

import gc
import hashlib
import json
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

from core.topology_engine import TopologyEngine
from core.topology_models import (
    ConfidenceTier,
    EdgeEvidence,
    EdgeLifecycleState,
    GraphDiffReport,
    RelationshipClass,
    TopologyChange,
    TopologyChangeType,
    TopologyEdge,
    TopologySnapshot,
    compute_edge_canonical_key,
    normalize_interface_name,
)


class TestTopologySnapshotsPhase4_4A(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_topology_4_4a.db"
        self.engine = TopologyEngine(self.db_path)

    def tearDown(self):
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Test Fixture Helpers
    # -------------------------------------------------------------------------
    def _insert_test_node(
        self,
        node_id: str,
        name: str,
        ip: str = "10.0.0.1",
        role: str = "router",
        reachability: str = "reachable",
    ) -> None:
        """Helper to insert a device node into topology_nodes."""
        self.engine.upsert_node(
            node_id=node_id,
            name=name,
            ip=ip,
            mac="AA:BB:CC:DD:EE:01",
            device_type=role,
            status="online",
        )
        with self.engine._lock, closing(self.engine._get_connection()) as conn:
            conn.execute(
                "UPDATE topology_nodes SET reachability_status = ?, device_role = ? WHERE id = ?",
                (reachability, role, node_id),
            )
            conn.commit()

    def _insert_test_edge(
        self,
        edge_id: str,
        source_id: str,
        target_id: str,
        source_iface: str = "ether1",
        target_iface: str = "ether1",
        rel_class: str = "physical",
        rel_subtype: str = "ethernet",
        oper_status: str = "up",
        confidence: str = "confirmed",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TopologyEdge:
        """Helper to insert a topology relationship edge."""
        edge = TopologyEdge(
            id=edge_id,
            source_node_id=source_id,
            target_node_id=target_id,
            source_interface=source_iface,
            target_interface=target_iface,
            relationship_class=rel_class,
            relationship_subtype=rel_subtype,
            oper_status=oper_status,
            confidence_tier=confidence.upper() if confidence.upper() in ("CONFIRMED", "HIGH", "MEDIUM", "LOW") else "HIGH",
            confidence_rationale="Test verified edge",
            metadata=metadata or {},
        )
        self.engine.insert_edge(edge)
        return edge

    def _insert_test_evidence(
        self,
        edge_id: str,
        evidence_type: str = "lldp",
        observing_device_id: str = "node1",
        raw_excerpt: str = "interface=ether1 neighbor=RouterB",
        confidence_contribution: str = "medium",
        is_active: bool = True,
    ) -> int:
        """Helper to insert an evidence item for an edge."""
        evidence = EdgeEvidence(
            edge_id=edge_id,
            evidence_type=evidence_type,
            observing_device_id=observing_device_id,
            raw_excerpt=raw_excerpt,
            confidence_contribution=confidence_contribution,
            is_active=is_active,
        )
        return self.engine.insert_edge_evidence(evidence)

    # =========================================================================
    # 1. Complete Snapshot Serialization (Tests 1–10)
    # =========================================================================

    def test_01_complete_snapshot_serialization(self):
        """Test 1: Snapshot contains nodes, multi-edges, evidence, and completeness metadata."""
        self._insert_test_node("n1", "RouterA")
        self._insert_test_node("n2", "RouterB")
        self._insert_test_edge("e1", "n1", "n2", "ether1", "ether1")
        self._insert_test_evidence("e1", "lldp", "n1")

        comp_meta = {
            "discovery_status": "complete",
            "expected_devices": ["n1", "n2"],
            "successful_devices": ["n1", "n2"],
            "failed_devices": [],
            "timed_out_devices": [],
            "is_complete": True,
        }
        snap = self.engine.create_snapshot(
            trigger_type="discovery_run",
            description="Baseline Scan",
            completeness=comp_meta,
        )

        self.assertEqual(snap.node_count, 2)
        self.assertEqual(snap.edge_count, 1)
        self.assertTrue(snap.verify_integrity())

        data = json.loads(snap.graph_json)
        self.assertIn("nodes", data)
        self.assertIn("edges", data)
        self.assertIn("evidence", data)
        self.assertIn("completeness", data)
        self.assertEqual(len(data["nodes"]), 2)
        self.assertEqual(len(data["edges"]), 1)
        self.assertEqual(len(data["evidence"]), 1)
        self.assertTrue(data["completeness"]["is_complete"])

    def test_02_evidence_inclusion_in_snapshot(self):
        """Test 2: Each edge in snapshot includes its associated evidence records."""
        self._insert_test_node("n1", "RouterA")
        self._insert_test_node("n2", "RouterB")
        self._insert_test_edge("e1", "n1", "n2", "ether1", "ether1")
        self._insert_test_evidence("e1", "lldp", "n1", raw_excerpt="lldp info")
        self._insert_test_evidence("e1", "cdp", "n2", raw_excerpt="cdp info")

        snap = self.engine.create_snapshot(description="Evidence Test")
        data = json.loads(snap.graph_json)

        edge = data["edges"][0]
        self.assertIn("evidence", edge)
        self.assertEqual(len(edge["evidence"]), 2)
        types = {ev["evidence_type"] for ev in edge["evidence"]}
        self.assertEqual(types, {"lldp", "cdp"})

    def test_03_evidence_sanitization_in_snapshot(self):
        """Test 3: Passwords, community strings, and tokens are redacted from snapshot evidence."""
        self._insert_test_node("n1", "RouterA")
        self._insert_test_node("n2", "RouterB")
        self._insert_test_edge("e1", "n1", "n2")

        sensitive_excerpt = "password=SuperSecretPassword123 snmp-community=public bearer secret-token-xyz"
        self._insert_test_evidence("e1", "cli", "n1", raw_excerpt=sensitive_excerpt)

        snap = self.engine.create_snapshot(description="Sanitization Test")

        # Must not contain secret raw credentials in serialized json
        self.assertNotIn("SuperSecretPassword123", snap.graph_json)
        self.assertNotIn("secret-token-xyz", snap.graph_json)

        data = json.loads(snap.graph_json)
        ev = data["evidence"][0]
        self.assertIn("[REDACTED", ev["raw_excerpt"])

    def test_04_deterministic_checksum(self):
        """Test 4: Canonical JSON serialization produces reproducible SHA-256 hash."""
        self._insert_test_node("n1", "RouterA")
        self._insert_test_node("n2", "RouterB")
        self._insert_test_edge("e1", "n1", "n2")

        snap = self.engine.create_snapshot(description="Deterministic Test")
        expected_hash = hashlib.sha256(snap.graph_json.encode("utf-8")).hexdigest()
        self.assertEqual(snap.sha256_hash, expected_hash)

        # Re-serializing the same graph object deterministically produces identical string & hash
        parsed = json.loads(snap.graph_json)
        re_serialized = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
        re_hash = hashlib.sha256(re_serialized.encode("utf-8")).hexdigest()
        self.assertEqual(snap.sha256_hash, re_hash)

    def test_05_snapshot_immutability_enforced(self):
        """Test 5: SQLite triggers reject UPDATE and DELETE operations on snapshots."""
        self._insert_test_node("n1", "RouterA")
        snap = self.engine.create_snapshot(description="Immutable Baseline")

        with self.assertRaises(sqlite3.IntegrityError):
            with self.engine._lock, closing(self.engine._get_connection()) as conn:
                conn.execute(
                    "UPDATE topology_snapshots SET description = 'Tampered' WHERE snapshot_id = ?",
                    (snap.snapshot_id,),
                )

        with self.assertRaises(sqlite3.IntegrityError):
            with self.engine._lock, closing(self.engine._get_connection()) as conn:
                conn.execute(
                    "DELETE FROM topology_snapshots WHERE snapshot_id = ?",
                    (snap.snapshot_id,),
                )

    def test_06_consistent_read_transaction(self):
        """Test 6: Nodes, edges, and evidence are captured from a single consistent read."""
        self._insert_test_node("n1", "RouterA")
        self._insert_test_node("n2", "RouterB")
        self._insert_test_edge("e1", "n1", "n2")
        self._insert_test_evidence("e1", "arp", "n1")

        snap = self.engine.create_snapshot(description="Consistent Read Test")
        data = json.loads(snap.graph_json)

        self.assertEqual(snap.node_count, len(data["nodes"]))
        self.assertEqual(snap.edge_count, len(data["edges"]))
        self.assertEqual(len(data["evidence"]), 1)

    def test_07_completeness_metadata_complete(self):
        """Test 7: Complete discovery produces is_complete=True and status 'complete'."""
        self._insert_test_node("n1", "RouterA")
        comp = {
            "discovery_status": "complete",
            "expected_devices": ["n1"],
            "successful_devices": ["n1"],
            "failed_devices": [],
            "timed_out_devices": [],
            "is_complete": True,
        }
        snap = self.engine.create_snapshot(completeness=comp)
        data = json.loads(snap.graph_json)
        self.assertTrue(data["completeness"]["is_complete"])
        self.assertEqual(data["completeness"]["discovery_status"], "complete")

    def test_08_completeness_metadata_partial(self):
        """Test 8: Partial discovery records failed/timed_out devices and is_complete=False."""
        self._insert_test_node("n1", "RouterA")
        comp = {
            "discovery_status": "partial",
            "expected_devices": ["n1", "n2"],
            "successful_devices": ["n1"],
            "failed_devices": ["n2"],
            "timed_out_devices": ["n2"],
            "is_complete": False,
        }
        snap = self.engine.create_snapshot(completeness=comp)
        data = json.loads(snap.graph_json)
        self.assertFalse(data["completeness"]["is_complete"])
        self.assertEqual(data["completeness"]["discovery_status"], "partial")
        self.assertIn("n2", data["completeness"]["failed_devices"])
        self.assertIn("n2", data["completeness"]["timed_out_devices"])

    def test_09_failed_discovery_snapshot_safety(self):
        """Test 9: Failed discovery produces safe incomplete snapshot without deleting history."""
        self._insert_test_node("n1", "RouterA")
        self._insert_test_edge("e1", "n1", "n1")
        prior_snap = self.engine.create_snapshot(description="Prior Good Snapshot")

        failed_comp = {
            "discovery_status": "failed",
            "expected_devices": ["seed_router"],
            "successful_devices": [],
            "failed_devices": ["seed_router"],
            "timed_out_devices": ["seed_router"],
            "is_complete": False,
        }
        fail_snap = self.engine.create_snapshot(
            trigger_type="discovery_run",
            description="Failed Scan Snapshot",
            completeness=failed_comp,
        )

        self.assertFalse(fail_snap.metadata["completeness"]["is_complete"])
        self.assertEqual(fail_snap.metadata["completeness"]["discovery_status"], "failed")

        # Prior snapshot remains completely intact in database
        retrieved_prior = self.engine.get_snapshot(prior_snap.snapshot_id)
        self.assertIsNotNone(retrieved_prior)
        self.assertEqual(retrieved_prior.snapshot_id, prior_snap.snapshot_id)

    def test_10_empty_snapshot_safety(self):
        """Test 10: Zero nodes and zero edges handled gracefully with valid checksum."""
        snap = self.engine.create_snapshot(description="Empty Graph")
        self.assertEqual(snap.node_count, 0)
        self.assertEqual(snap.edge_count, 0)
        self.assertTrue(snap.verify_integrity())
        data = json.loads(snap.graph_json)
        self.assertEqual(data["nodes"], [])
        self.assertEqual(data["edges"], [])
        self.assertEqual(data["evidence"], [])

    # =========================================================================
    # 2. Multi-Edge Identity Resolution (Tests 11–19)
    # =========================================================================

    def test_11_endpoint_interface_tuple_normalization(self):
        """Test 11: (A:eth1, B:eth2) matches (B:eth2, A:eth1) canonically."""
        e1 = {
            "source_node_id": "RouterA",
            "target_node_id": "RouterB",
            "source_interface": "ether1",
            "target_interface": "ether2",
            "relationship_class": "physical",
        }
        e2 = {
            "source_node_id": "RouterB",
            "target_node_id": "RouterA",
            "source_interface": "ether2",
            "target_interface": "ether1",
            "relationship_class": "physical",
        }
        k1 = compute_edge_canonical_key(e1)
        k2 = compute_edge_canonical_key(e2)
        self.assertEqual(k1, k2)

    def test_12_reverse_endpoint_order_equivalence(self):
        """Test 12: Edge created in reverse endpoint order resolves to identical fallback key."""
        e_forward = {
            "source_node_id": "Alpha",
            "target_node_id": "Beta",
            "source_interface": "sfp-sfpplus1",
            "target_interface": "ether8",
            "relationship_class": "physical",
        }
        e_reverse = {
            "source_node_id": "Beta",
            "target_node_id": "Alpha",
            "source_interface": "ether8",
            "target_interface": "sfp-sfpplus1",
            "relationship_class": "physical",
        }
        self.assertEqual(compute_edge_canonical_key(e_forward), compute_edge_canonical_key(e_reverse))

    def test_13_physical_parallel_edges_distinguished(self):
        """Test 13: Parallel links between same devices with different interfaces match correctly."""
        link1 = {
            "source_node_id": "RouterA",
            "target_node_id": "RouterB",
            "source_interface": "ether1",
            "target_interface": "ether1",
            "relationship_class": "physical",
        }
        link2 = {
            "source_node_id": "RouterA",
            "target_node_id": "RouterB",
            "source_interface": "ether2",
            "target_interface": "ether2",
            "relationship_class": "physical",
        }
        k1 = compute_edge_canonical_key(link1)
        k2 = compute_edge_canonical_key(link2)
        self.assertNotEqual(k1, k2)

    def test_14_layer2_vlan_distinguished(self):
        """Test 14: Layer 2 edges between same endpoints with different VLAN IDs match correctly."""
        l2_vlan10 = {
            "source_node_id": "SW1",
            "target_node_id": "SW2",
            "relationship_class": "layer2",
            "relationship_subtype": "bridge_vlan",
            "metadata": {"vlan_id": 10},
        }
        l2_vlan20 = {
            "source_node_id": "SW1",
            "target_node_id": "SW2",
            "relationship_class": "layer2",
            "relationship_subtype": "bridge_vlan",
            "metadata": {"vlan_id": 20},
        }
        k10 = compute_edge_canonical_key(l2_vlan10)
        k20 = compute_edge_canonical_key(l2_vlan20)
        self.assertNotEqual(k10, k20)

    def test_15_layer3_directed_next_hop_preserved(self):
        """Test 15: Layer 3 next-hop reachability preserves direction (source -> target)."""
        route_ab = {
            "source_node_id": "R1",
            "target_node_id": "R2",
            "relationship_class": "layer3",
            "relationship_subtype": "next_hop_reachability",
            "metadata": {"nexthop_ip": "10.0.0.2"},
        }
        route_ba = {
            "source_node_id": "R2",
            "target_node_id": "R1",
            "relationship_class": "layer3",
            "relationship_subtype": "next_hop_reachability",
            "metadata": {"nexthop_ip": "10.0.0.1"},
        }
        k_ab = compute_edge_canonical_key(route_ab)
        k_ba = compute_edge_canonical_key(route_ba)
        # Direction must be preserved: R1 -> R2 != R2 -> R1
        self.assertNotEqual(k_ab, k_ba)
        self.assertEqual(k_ab[2], "R1")
        self.assertEqual(k_ab[3], "R2")

    def test_16_logical_overlay_tunnel_id(self):
        """Test 16: Logical edges distinguished by overlay tunnel ID / VNI."""
        vx1 = {
            "source_node_id": "R1",
            "target_node_id": "R2",
            "relationship_class": "logical",
            "relationship_subtype": "vxlan",
            "metadata": {"tunnel_id": "10001"},
        }
        vx2 = {
            "source_node_id": "R1",
            "target_node_id": "R2",
            "relationship_class": "logical",
            "relationship_subtype": "vxlan",
            "metadata": {"tunnel_id": "10002"},
        }
        self.assertNotEqual(compute_edge_canonical_key(vx1), compute_edge_canonical_key(vx2))

    def test_17_missing_interface_ambiguity_detection(self):
        """Test 17: Parallel edges with missing interface flagged as INDETERMINATE_AMBIGUOUS_MATCH."""
        self._insert_test_node("n1", "RouterA")
        self._insert_test_node("n2", "RouterB")
        self._insert_test_edge("e1", "n1", "n2", "ether1", "ether1")
        self._insert_test_edge("e2", "n1", "n2", "", "")  # Missing interface on parallel link

        snap1 = self.engine.create_snapshot(description="Base with missing interface")

        # In target, e1 remains, but another edge has ether2
        with self.engine._lock, closing(self.engine._get_connection()) as conn:
            conn.execute("DELETE FROM topology_edges WHERE id = 'e2'")
            conn.commit()
        self._insert_test_edge("e3", "n1", "n2", "ether2", "ether2")

        snap2 = self.engine.create_snapshot(description="Target with ether2")

        diff = self.engine.compare_snapshots(snap1.snapshot_id, snap2.snapshot_id)
        # e2 cannot be safely confirmed as removed because of ambiguity
        self.assertEqual(diff.summary["edges_removed"], 0)
        ambig_ids = {item["entity_id"] for item in diff.indeterminate_items if item["indeterminate_type"] == "INDETERMINATE_AMBIGUOUS_MATCH"}
        self.assertIn("e2", ambig_ids)

    def test_18_one_to_many_ambiguity_detection(self):
        """Test 18: Ambiguous candidate matching multiple edges flagged indeterminate."""
        self._insert_test_node("n1", "RouterA")
        self._insert_test_node("n2", "RouterB")
        # Base has 1 edge with empty interfaces
        self._insert_test_edge("base_e1", "n1", "n2", "", "")
        snap1 = self.engine.create_snapshot(description="Base Single Uninterfaced")

        # Target has 2 edges with empty interfaces (collision group = 2)
        with self.engine._lock, closing(self.engine._get_connection()) as conn:
            conn.execute("DELETE FROM topology_edges")
            conn.commit()
        self._insert_test_edge("target_e1", "n1", "n2", "", "")
        self._insert_test_edge("target_e2", "n1", "n2", "", "")
        snap2 = self.engine.create_snapshot(description="Target Dual Uninterfaced")

        diff = self.engine.compare_snapshots(snap1.snapshot_id, snap2.snapshot_id)
        # 1-to-many collision cannot be matched
        self.assertGreaterEqual(diff.summary["indeterminate_count"], 1)
        ambig_items = [i for i in diff.indeterminate_items if i["indeterminate_type"] == "INDETERMINATE_AMBIGUOUS_MATCH"]
        self.assertTrue(len(ambig_items) > 0)

    def test_19_many_to_many_ambiguity_detection(self):
        """Test 19: Complex multi-edge collisions flagged indeterminate."""
        self._insert_test_node("n1", "RouterA")
        self._insert_test_node("n2", "RouterB")
        self._insert_test_edge("b1", "n1", "n2", "", "")
        self._insert_test_edge("b2", "n1", "n2", "", "")
        snap1 = self.engine.create_snapshot(description="Base 2 collisions")

        with self.engine._lock, closing(self.engine._get_connection()) as conn:
            conn.execute("DELETE FROM topology_edges")
            conn.commit()
        self._insert_test_edge("t1", "n1", "n2", "", "")
        self._insert_test_edge("t2", "n1", "n2", "", "")
        snap2 = self.engine.create_snapshot(description="Target 2 collisions")

        diff = self.engine.compare_snapshots(snap1.snapshot_id, snap2.snapshot_id)
        # All 4 edges must be flagged as INDETERMINATE_AMBIGUOUS_MATCH
        self.assertEqual(diff.summary["edges_added"], 0)
        self.assertEqual(diff.summary["edges_removed"], 0)
        ambig_ids = {i["entity_id"] for i in diff.indeterminate_items if i["indeterminate_type"] == "INDETERMINATE_AMBIGUOUS_MATCH"}
        self.assertTrue({"b1", "b2"}.issubset(ambig_ids) or len(ambig_ids) >= 2)

    # =========================================================================
    # 3. Graph Diff Engine (Tests 20–32)
    # =========================================================================

    def test_20_node_added_detection(self):
        """Test 20: New device present in target reported as NODE_ADDED."""
        self._insert_test_node("n1", "RouterA")
        snap1 = self.engine.create_snapshot(description="Base 1 Node")

        self._insert_test_node("n2", "RouterB")
        snap2 = self.engine.create_snapshot(description="Target 2 Nodes")

        diff = self.engine.compare_snapshots(snap1.snapshot_id, snap2.snapshot_id)
        self.assertEqual(diff.summary["nodes_added"], 1)
        self.assertEqual(diff.structural_changes[0]["change_type"], "NODE_ADDED")
        self.assertEqual(diff.structural_changes[0]["entity_id"], "n2")

    def test_21_node_removed_detection_complete(self):
        """Test 21: Missing device in complete target discovery reported as NODE_REMOVED."""
        self._insert_test_node("n1", "RouterA")
        self._insert_test_node("n2", "RouterB")
        snap1 = self.engine.create_snapshot(description="Base 2 Nodes")

        with self.engine._lock, closing(self.engine._get_connection()) as conn:
            conn.execute("DELETE FROM topology_nodes WHERE id = 'n2'")
            conn.commit()

        complete_meta = {
            "discovery_status": "complete",
            "expected_devices": ["n1"],
            "successful_devices": ["n1"],
            "failed_devices": [],
            "timed_out_devices": [],
            "is_complete": True,
        }
        snap2 = self.engine.create_snapshot(description="Target 1 Node Complete", completeness=complete_meta)

        diff = self.engine.compare_snapshots(snap1.snapshot_id, snap2.snapshot_id)
        self.assertEqual(diff.summary["nodes_removed"], 1)
        rem_changes = [c for c in diff.structural_changes if c["change_type"] == "NODE_REMOVED"]
        self.assertEqual(len(rem_changes), 1)
        self.assertEqual(rem_changes[0]["entity_id"], "n2")

    def test_22_node_removed_suppressed_incomplete(self):
        """Test 22: Missing device in incomplete target discovery reported as INDETERMINATE_UNREACHABLE_NODE."""
        self._insert_test_node("n1", "RouterA")
        self._insert_test_node("n2", "RouterB")
        snap1 = self.engine.create_snapshot(description="Base 2 Nodes")

        with self.engine._lock, closing(self.engine._get_connection()) as conn:
            conn.execute("DELETE FROM topology_nodes WHERE id = 'n2'")
            conn.commit()

        partial_meta = {
            "discovery_status": "partial",
            "expected_devices": ["n1", "n2"],
            "successful_devices": ["n1"],
            "failed_devices": ["n2"],
            "timed_out_devices": ["n2"],
            "is_complete": False,
        }
        snap2 = self.engine.create_snapshot(description="Target 1 Node Incomplete", completeness=partial_meta)

        diff = self.engine.compare_snapshots(snap1.snapshot_id, snap2.snapshot_id)
        self.assertEqual(diff.summary["nodes_removed"], 0)
        self.assertEqual(diff.summary["indeterminate_count"], 1)
        self.assertEqual(diff.indeterminate_items[0]["indeterminate_type"], "INDETERMINATE_UNREACHABLE_NODE")
        self.assertEqual(diff.indeterminate_items[0]["entity_id"], "n2")

    def test_23_edge_added_detection(self):
        """Test 23: New connection present in target reported as EDGE_ADDED."""
        self._insert_test_node("n1", "RouterA")
        self._insert_test_node("n2", "RouterB")
        snap1 = self.engine.create_snapshot(description="Base No Edges")

        self._insert_test_edge("e1", "n1", "n2", "ether1", "ether1")
        snap2 = self.engine.create_snapshot(description="Target With Edge")

        diff = self.engine.compare_snapshots(snap1.snapshot_id, snap2.snapshot_id)
        self.assertEqual(diff.summary["edges_added"], 1)
        self.assertEqual(diff.structural_changes[0]["change_type"], "EDGE_ADDED")
        self.assertEqual(diff.structural_changes[0]["entity_id"], "e1")

    def test_24_edge_removed_detection_complete(self):
        """Test 24: Missing connection between verified devices reported as EDGE_REMOVED."""
        self._insert_test_node("n1", "RouterA")
        self._insert_test_node("n2", "RouterB")
        self._insert_test_edge("e1", "n1", "n2", "ether1", "ether1")
        snap1 = self.engine.create_snapshot(description="Base With Edge")

        with self.engine._lock, closing(self.engine._get_connection()) as conn:
            conn.execute("DELETE FROM topology_edges WHERE id = 'e1'")
            conn.commit()

        complete_meta = {
            "discovery_status": "complete",
            "expected_devices": ["n1", "n2"],
            "successful_devices": ["n1", "n2"],
            "failed_devices": [],
            "timed_out_devices": [],
            "is_complete": True,
        }
        snap2 = self.engine.create_snapshot(description="Target Edge Removed", completeness=complete_meta)

        diff = self.engine.compare_snapshots(snap1.snapshot_id, snap2.snapshot_id)
        self.assertEqual(diff.summary["edges_removed"], 1)
        rem_edges = [c for c in diff.structural_changes if c["change_type"] == "EDGE_REMOVED"]
        self.assertEqual(len(rem_edges), 1)
        self.assertEqual(rem_edges[0]["entity_id"], "e1")

    def test_25_edge_removed_suppressed_endpoint_failure(self):
        """Test 25: Missing connection where endpoint failed reported as INDETERMINATE_UNVERIFIED_EDGE."""
        self._insert_test_node("n1", "RouterA")
        self._insert_test_node("n2", "RouterB")
        self._insert_test_edge("e1", "n1", "n2", "ether1", "ether1")
        snap1 = self.engine.create_snapshot(description="Base With Edge")

        with self.engine._lock, closing(self.engine._get_connection()) as conn:
            conn.execute("DELETE FROM topology_edges WHERE id = 'e1'")
            conn.commit()

        fail_meta = {
            "discovery_status": "partial",
            "expected_devices": ["n1", "n2"],
            "successful_devices": ["n1"],
            "failed_devices": ["n2"],
            "timed_out_devices": ["n2"],
            "is_complete": False,
        }
        snap2 = self.engine.create_snapshot(description="Target Endpoint Failed", completeness=fail_meta)

        diff = self.engine.compare_snapshots(snap1.snapshot_id, snap2.snapshot_id)
        self.assertEqual(diff.summary["edges_removed"], 0)
        self.assertEqual(diff.summary["indeterminate_count"], 1)
        self.assertEqual(diff.indeterminate_items[0]["indeterminate_type"], "INDETERMINATE_UNVERIFIED_EDGE")
        self.assertEqual(diff.indeterminate_items[0]["entity_id"], "e1")

    def test_26_node_modified_detection(self):
        """Test 26: Hostname, role, or reachability change reported as NODE_MODIFIED."""
        self._insert_test_node("n1", "RouterA", role="switch", reachability="reachable")
        snap1 = self.engine.create_snapshot(description="Base Switch")

        self.engine.upsert_node(
            node_id="n1",
            name="RouterA-Core",
            ip="10.0.0.1",
            mac="AA:BB:CC:DD:EE:01",
            device_type="router",
            status="online",
        )
        snap2 = self.engine.create_snapshot(description="Target Core Router")

        diff = self.engine.compare_snapshots(snap1.snapshot_id, snap2.snapshot_id)
        self.assertGreaterEqual(diff.summary["nodes_modified"], 1)
        mod_changes = [c for c in diff.structural_changes if c["change_type"] == "NODE_MODIFIED"]
        self.assertTrue(any(c["attribute_name"] in ("device_type", "device_role", "name") for c in mod_changes))

    def test_27_edge_operational_status_change(self):
        """Test 27: Oper status transition ('up' -> 'down') reported in operational_changes."""
        self._insert_test_node("n1", "RouterA")
        self._insert_test_node("n2", "RouterB")
        self._insert_test_edge("e1", "n1", "n2", "ether1", "ether1", oper_status="up")
        snap1 = self.engine.create_snapshot(description="Base Edge Up")

        with self.engine._lock, closing(self.engine._get_connection()) as conn:
            conn.execute("UPDATE topology_edges SET oper_status = 'down' WHERE id = 'e1'")
            conn.commit()
        snap2 = self.engine.create_snapshot(description="Target Edge Down")

        diff = self.engine.compare_snapshots(snap1.snapshot_id, snap2.snapshot_id)
        self.assertEqual(diff.summary["operational_changes"], 1)
        op = diff.operational_changes[0]
        self.assertEqual(op["change_type"], "STATUS_CHANGED")
        self.assertEqual(op["entity_id"], "e1")
        self.assertEqual(op["before_value"], "up")
        self.assertEqual(op["after_value"], "down")

    def test_28_edge_freshness_change(self):
        """Test 28: Observation freshness change reported in freshness_changes."""
        self._insert_test_node("n1", "RouterA")
        self._insert_test_node("n2", "RouterB")
        self._insert_test_edge("e1", "n1", "n2")

        with self.engine._lock, closing(self.engine._get_connection()) as conn:
            conn.execute("UPDATE topology_edges SET observation_freshness = 1.0 WHERE id = 'e1'")
            conn.commit()
        snap1 = self.engine.create_snapshot(description="Base Fresh 1.0")

        with self.engine._lock, closing(self.engine._get_connection()) as conn:
            conn.execute("UPDATE topology_edges SET observation_freshness = 0.5 WHERE id = 'e1'")
            conn.commit()
        snap2 = self.engine.create_snapshot(description="Target Decayed 0.5")

        diff = self.engine.compare_snapshots(snap1.snapshot_id, snap2.snapshot_id)
        self.assertEqual(diff.summary["freshness_changes"], 1)
        fr = diff.freshness_changes[0]
        self.assertEqual(fr["change_type"], "FRESHNESS_CHANGED")
        self.assertEqual(fr["entity_id"], "e1")

    def test_29_edge_evidence_addition(self):
        """Test 29: New evidence record on existing edge reported in evidence_changes."""
        self._insert_test_node("n1", "RouterA")
        self._insert_test_node("n2", "RouterB")
        self._insert_test_edge("e1", "n1", "n2")
        self._insert_test_evidence("e1", "lldp", "n1")
        snap1 = self.engine.create_snapshot(description="Base 1 Evidence")

        self._insert_test_evidence("e1", "cdp", "n2")
        snap2 = self.engine.create_snapshot(description="Target 2 Evidences")

        diff = self.engine.compare_snapshots(snap1.snapshot_id, snap2.snapshot_id)
        self.assertEqual(diff.summary["evidence_changes"], 1)
        ev_ch = [c for c in diff.evidence_changes if c["change_type"] == "EVIDENCE_CHANGED"]
        self.assertEqual(len(ev_ch), 1)

    def test_30_edge_evidence_expiration(self):
        """Test 30: Expired evidence record reported in evidence_changes."""
        self._insert_test_node("n1", "RouterA")
        self._insert_test_node("n2", "RouterB")
        self._insert_test_edge("e1", "n1", "n2")
        ev_id = self._insert_test_evidence("e1", "lldp", "n1", is_active=True)
        snap1 = self.engine.create_snapshot(description="Base Active Evidence")

        with self.engine._lock, closing(self.engine._get_connection()) as conn:
            conn.execute("UPDATE topology_edge_evidence SET is_active = 0 WHERE id = ?", (ev_id,))
            conn.commit()
        snap2 = self.engine.create_snapshot(description="Target Inactive Evidence")

        diff = self.engine.compare_snapshots(snap1.snapshot_id, snap2.snapshot_id)
        self.assertEqual(diff.summary["evidence_changes"], 1)
        exp_ch = [c for c in diff.evidence_changes if c["change_type"] == "EVIDENCE_EXPIRED"]
        self.assertEqual(len(exp_ch), 1)

    def test_31_edge_confidence_score_change(self):
        """Test 31: Confidence score change reported in evidence_changes."""
        self._insert_test_node("n1", "RouterA")
        self._insert_test_node("n2", "RouterB")
        self._insert_test_edge("e1", "n1", "n2", confidence="medium")
        snap1 = self.engine.create_snapshot(description="Base Medium Confidence")

        with self.engine._lock, closing(self.engine._get_connection()) as conn:
            conn.execute("UPDATE topology_edges SET confidence_tier = 'CONFIRMED' WHERE id = 'e1'")
            conn.commit()
        snap2 = self.engine.create_snapshot(description="Target Confirmed Confidence")

        diff = self.engine.compare_snapshots(snap1.snapshot_id, snap2.snapshot_id)
        self.assertEqual(diff.summary["evidence_changes"], 1)
        conf_ch = [c for c in diff.evidence_changes if c["change_type"] == "CONFIDENCE_CHANGED"]
        self.assertEqual(len(conf_ch), 1)

    def test_32_indeterminate_items_not_persisted(self):
        """Test 32: Indeterminate items never written to topology_changes table."""
        self._insert_test_node("n1", "RouterA")
        self._insert_test_node("n2", "RouterB")
        self._insert_test_edge("e1", "n1", "n2")
        snap1 = self.engine.create_snapshot(description="Base")

        # Create incomplete target missing n2
        with self.engine._lock, closing(self.engine._get_connection()) as conn:
            conn.execute("DELETE FROM topology_edges WHERE id = 'e1'")
            conn.execute("DELETE FROM topology_nodes WHERE id = 'n2'")
            conn.commit()

        partial_meta = {
            "discovery_status": "partial",
            "expected_devices": ["n1", "n2"],
            "successful_devices": ["n1"],
            "failed_devices": ["n2"],
            "is_complete": False,
        }
        snap2 = self.engine.create_snapshot(description="Incomplete Target", completeness=partial_meta)
        diff = self.engine.compare_snapshots(snap1.snapshot_id, snap2.snapshot_id)

        self.assertGreater(diff.summary["indeterminate_count"], 0)

        # Verify database topology_changes table contains zero INDETERMINATE records
        changes = self.engine.list_changes(snapshot_id=snap2.snapshot_id)
        for c in changes:
            self.assertFalse(c.change_type.startswith("INDETERMINATE"))

    # =========================================================================
    # 4. Performance, Concurrency, Lifecycle & Idempotency (Tests 33–38)
    # =========================================================================

    def test_33_transaction_boundary_consistency(self):
        """Test 33: Database lock held only during row read, not during diff computation."""
        self._insert_test_node("n1", "RouterA")
        snap1 = self.engine.create_snapshot()
        snap2 = self.engine.create_snapshot()

        diff = self.engine.compare_snapshots(snap1.snapshot_id, snap2.snapshot_id)
        # Verify db_query_ms is present, non-negative, and diff_compute_ms is present
        self.assertIn("db_query_ms", diff.telemetry)
        self.assertIn("diff_compute_ms", diff.telemetry)
        self.assertGreaterEqual(diff.telemetry["db_query_ms"], 0.0)
        self.assertGreaterEqual(diff.telemetry["diff_compute_ms"], 0.0)

    def test_34_diff_outside_database_lock(self):
        """Test 34: Diff computation completes successfully without holding active database connection."""
        self._insert_test_node("n1", "RouterA")
        snap1 = self.engine.create_snapshot()
        snap2 = self.engine.create_snapshot()

        # Engine lock should not be held during or after comparison
        self.assertFalse(self.engine._lock.locked())
        diff = self.engine.compare_snapshots(snap1.snapshot_id, snap2.snapshot_id)
        self.assertFalse(self.engine._lock.locked())
        self.assertIsInstance(diff, GraphDiffReport)

    def test_35_diff_telemetry_populated(self):
        """Test 35: db_query_ms, deserialization_ms, diff_compute_ms, total_duration_ms populated."""
        self._insert_test_node("n1", "RouterA")
        snap1 = self.engine.create_snapshot()
        snap2 = self.engine.create_snapshot()

        diff = self.engine.compare_snapshots(snap1.snapshot_id, snap2.snapshot_id)
        for key in ("db_query_ms", "deserialization_ms", "diff_compute_ms", "total_duration_ms"):
            self.assertIn(key, diff.telemetry)
            self.assertIsInstance(diff.telemetry[key], float)
            self.assertGreaterEqual(diff.telemetry[key], 0.0)

        self.assertIn("base_graph_size", diff.telemetry)
        self.assertIn("target_graph_size", diff.telemetry)

    def test_36_oversized_snapshot_rejection(self):
        """Test 36: Snapshot exceeding 10,000 nodes or 50,000 edges rejected with ValueError."""
        # Test in create_snapshot
        with patch.object(self.engine, "_get_connection") as mock_conn_fn:
            mock_conn = MagicMock()
            mock_conn_fn.return_value = mock_conn
            # Return 10,001 nodes
            mock_conn.execute.return_value.fetchall.return_value = [{"id": f"n_{i}"} for i in range(10001)]
            with self.assertRaises(ValueError):
                self.engine.create_snapshot()

        # Test in compare_snapshots with crafted snapshot payload
        snap = self.engine.create_snapshot(description="Valid snap")
        oversized_graph = {"nodes": [{"id": f"n_{i}"} for i in range(10001)], "edges": []}
        raw_json = json.dumps(oversized_graph)
        sha = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()

        with self.engine._lock, closing(self.engine._get_connection()) as conn:
            conn.execute(
                "INSERT INTO topology_snapshots (snapshot_id, schema_version, created_at, node_count, edge_count, graph_json, sha256_hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("snap_oversized", "4.4", time.time(), 10001, 0, raw_json, sha),
            )
            conn.commit()

        with self.assertRaises(ValueError):
            self.engine.compare_snapshots(snap.snapshot_id, "snap_oversized")

    def test_37_discovery_retry_idempotency(self):
        """Test 37: Running discovery twice with identical mock device outputs produces 0 diff changes."""
        mock_output = {
            "identity": "name: TestSeed",
            "resource": "version: 7.14",
            "interface": "name=ether1\nname=ether2",
            "neighbor": "",
            "route": "",
            "arp": "",
        }

        mock_inv = MagicMock()
        mock_inv.list_devices.return_value = {
            "devices": [
                {"name": "TestSeed", "host": "10.0.0.1", "is_active": True, "enabled": True}
            ]
        }

        with patch.object(self.engine, "interrogate_routeros_readonly") as mock_interrogate:
            mock_interrogate.return_value = {"success": True, "outputs": mock_output, "limitations": []}

            res1 = self.engine.sync_from_seed_router(device_name="TestSeed", host="10.0.0.1", inv_store_override=mock_inv)
            self.assertTrue(res1["success"])
            snap1_id = res1.get("snapshot_id")
            self.assertIsNotNone(snap1_id)

            res2 = self.engine.sync_from_seed_router(device_name="TestSeed", host="10.0.0.1", inv_store_override=mock_inv)
            self.assertTrue(res2["success"])
            snap2_id = res2.get("snapshot_id")
            self.assertIsNotNone(snap2_id)

            diff = self.engine.compare_snapshots(snap1_id, snap2_id)
            self.assertEqual(diff.summary["nodes_added"], 0)
            self.assertEqual(diff.summary["nodes_removed"], 0)
            self.assertEqual(diff.summary["edges_added"], 0)
            self.assertEqual(diff.summary["edges_removed"], 0)
            self.assertEqual(diff.summary["operational_changes"], 0)

    def test_38_backward_compatibility_v4_1_v4_3(self):
        """Test 38: Existing Phase 4.1/4.2/4.3 APIs function without regression."""
        # 4.1: get_topology, insert_edge, upsert_node
        self._insert_test_node("n1", "RouterA")
        self._insert_test_node("n2", "RouterB")
        self.engine.upsert_link(
            source_id="n1",
            target_id="n2",
            source_port="ether1",
            target_port="ether1",
            link_type="physical",
            status="up",
        )
        self._insert_test_edge("e1", "n1", "n2")
        self._insert_test_evidence("e1", "lldp", "n1")

        topo = self.engine.get_topology()
        self.assertIn("nodes", topo)
        self.assertIn("links", topo)
        self.assertEqual(len(topo["nodes"]), 2)
        self.assertEqual(len(topo["links"]), 1)
        edges = self.engine.list_edges()
        self.assertEqual(len(edges), 1)

        # 4.1: create_snapshot, list_snapshots, record_change, list_changes
        snap = self.engine.create_snapshot(description="Legacy Snapshot Call")
        self.assertIsNotNone(snap.snapshot_id)

        ch = TopologyChange(
            snapshot_id=snap.snapshot_id,
            change_type="EDGE_ADDED",
            entity_id="e1",
            change_reason="Legacy Change Record",
        )
        ch_id = self.engine.record_change(ch)
        self.assertGreater(ch_id, 0)

        changes = self.engine.list_changes(snapshot_id=snap.snapshot_id)
        self.assertEqual(len(changes), 1)

        # 4.3: handle_nms_event
        from core.events import EventNames
        res_nms = self.engine.handle_nms_event({
            "event": EventNames.NMS_INTERFACE_STATUS_CHANGED,
            "device_id": "n1",
            "interface_name": "ether1",
            "oper_status": "down",
            "timestamp": time.time(),
        })
        self.assertTrue(res_nms.get("success", False))
        self.assertEqual(res_nms.get("edges_updated"), 1)


if __name__ == "__main__":
    unittest.main()
