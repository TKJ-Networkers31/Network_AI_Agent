"""
tests/test_topology_phase4_1.py — Acceptance Test Suite for Phase 4.1:
Graph Data Model & SQLite Foundation.

Covers all 12 specified test cases:
1. Fresh database initialization (tables created, triggers created, schema v4.1).
2. Migration from existing database schema (preserves legacy nodes, links, evidence).
3. Repeated migration / idempotency (safe multiple _init_db runs).
4. Multiple edges between identical node pairs (parallel physical, L2, L3, logical).
5. Edge-evidence foreign key integrity (validation and cascade delete).
6. Invalid relationship classes (raises ValueError).
7. Invalid lifecycle states (raises ValueError, tombstoned soft-delete).
8. Snapshot immutability (integrity verification and SQLite trigger ABORT on UPDATE/DELETE).
9. Topology change history (delta change recording and retrieval).
10. Transaction rollback (atomic rollback on error).
11. Backward compatibility with existing topology queries (get_topology continues to work).
12. Existing database records preserved intact across restarts.
"""

from __future__ import annotations

from contextlib import closing
import gc
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, Dict

from core.topology_engine import TopologyEngine
from core.topology_models import (
    ConfidenceTier,
    EdgeEvidence,
    EdgeLifecycleState,
    RelationshipClass,
    TopologyChange,
    TopologyChangeType,
    TopologyEdge,
    TopologySnapshot,
)


class TestTopologyPhase4_1(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_topology_4_1.db"
        self.engine = TopologyEngine(self.db_path)

    def tearDown(self):
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def _insert_test_node(self, node_id: str, name: str, ip: str = "192.168.1.1"):
        """Helper to insert a node into topology_nodes."""
        self.engine.upsert_node(
            node_id=node_id,
            name=name,
            ip=ip,
            mac="AA:BB:CC:DD:EE:FF",
            device_type="router",
            status="online",
        )

    # -------------------------------------------------------------------------
    # Test 1: Fresh Database Initialization
    # -------------------------------------------------------------------------
    def test_01_fresh_database_initialization(self):
        """All Phase 4.1 tables, triggers, and schema version v4.1 are initialized cleanly."""
        with self.engine._lock, closing(self.engine._get_connection()) as conn:
            tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            self.assertIn("topology_edges", tables)
            self.assertIn("topology_edge_evidence", tables)
            self.assertIn("topology_snapshots", tables)
            self.assertIn("topology_changes", tables)
            self.assertIn("topology_schema_version", tables)
            self.assertIn("topology_nodes", tables)
            self.assertIn("topology_links", tables)

            triggers = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall()}
            self.assertIn("trg_snapshot_no_update", triggers)
            self.assertIn("trg_snapshot_no_delete", triggers)

            indexes = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
            self.assertIn("idx_edges_nodes", indexes)
            self.assertIn("idx_edges_rel", indexes)
            self.assertIn("idx_edge_ev_edge", indexes)
            self.assertIn("idx_snapshots_created", indexes)

        self.assertEqual(self.engine.get_schema_version(), "4.1")

    # -------------------------------------------------------------------------
    # Test 2: Migration from Existing Database Schema
    # -------------------------------------------------------------------------
    def test_02_migration_from_existing_database(self):
        """Preserves legacy topology_nodes, topology_links, and topology_evidence intact."""
        legacy_db = Path(self.temp_dir.name) / "legacy_v2.db"
        with closing(sqlite3.connect(str(legacy_db))) as conn:
            conn.executescript(
                """
                CREATE TABLE topology_nodes (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    ip TEXT,
                    status TEXT DEFAULT 'online'
                );
                CREATE TABLE topology_links (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    link_type TEXT DEFAULT 'ethernet'
                );
                CREATE TABLE topology_evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject_type TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    evidence_type TEXT NOT NULL,
                    observed_at REAL NOT NULL
                );
                INSERT INTO topology_nodes (id, name, ip) VALUES ('legacy_r1', 'Legacy Router 1', '10.0.0.1');
                INSERT INTO topology_links (id, source_id, target_id) VALUES ('legacy_link_1', 'legacy_r1', 'legacy_r1');
                INSERT INTO topology_evidence (subject_type, subject_id, evidence_type, observed_at)
                VALUES ('node', 'legacy_r1', 'arp_entry', 1700000000.0);
                """
            )
            conn.commit()

        # Instantiate engine on legacy database
        legacy_engine = TopologyEngine(legacy_db)
        self.assertEqual(legacy_engine.get_schema_version(), "4.1")

        with legacy_engine._lock, closing(legacy_engine._get_connection()) as c:
            node = c.execute("SELECT * FROM topology_nodes WHERE id = 'legacy_r1'").fetchone()
            self.assertIsNotNone(node)
            self.assertEqual(node["name"], "Legacy Router 1")

            link = c.execute("SELECT * FROM topology_links WHERE id = 'legacy_link_1'").fetchone()
            self.assertIsNotNone(link)

            ev = c.execute("SELECT * FROM topology_evidence WHERE subject_id = 'legacy_r1'").fetchone()
            self.assertIsNotNone(ev)
            self.assertEqual(ev["evidence_type"], "arp_entry")

    # -------------------------------------------------------------------------
    # Test 3: Repeated Migration / Idempotency
    # -------------------------------------------------------------------------
    def test_03_repeated_migration_idempotency(self):
        """Multiple consecutive runs of _init_db() do not fail or duplicate columns."""
        for _ in range(3):
            self.engine._init_db()
        self.assertEqual(self.engine.get_schema_version(), "4.1")

    # -------------------------------------------------------------------------
    # Test 4: Multiple Edges Between Identical Node Pairs
    # -------------------------------------------------------------------------
    def test_04_multiple_edges_between_identical_nodes(self):
        """Parallel physical, layer2, layer3, and logical edges co-exist between identical nodes."""
        self._insert_test_node("node_r1", "Router 1", "192.168.10.1")
        self._insert_test_node("node_r2", "Router 2", "192.168.10.2")

        # 1. Physical Edge
        e_phys = TopologyEdge(
            id="edge_r1_r2_phys1",
            source_node_id="node_r1",
            target_node_id="node_r2",
            source_interface="ether1",
            target_interface="ether1",
            relationship_class="physical",
            relationship_subtype="direct_copper",
            confidence_tier="CONFIRMED",
            confidence_score=1.0,
            confidence_rationale="Mutual bidirectional LLDP on ether1.",
        )
        # 2. Layer 2 Trunk Edge
        e_l2 = TopologyEdge(
            id="edge_r1_r2_l2_vlan10",
            source_node_id="node_r1",
            target_node_id="node_r2",
            source_interface="vlan10",
            target_interface="vlan10",
            relationship_class="layer2",
            relationship_subtype="vlan_trunk",
            vlan_id=10,
            confidence_tier="HIGH",
            confidence_score=0.9,
            confidence_rationale="802.1Q tagged frame traffic observed.",
        )
        # 3. Layer 3 Routed Edge
        e_l3 = TopologyEdge(
            id="edge_r1_r2_l3_p2p",
            source_node_id="node_r1",
            target_node_id="node_r2",
            relationship_class="layer3",
            relationship_subtype="routed_point_to_point",
            confidence_tier="CONFIRMED",
            confidence_score=1.0,
            confidence_rationale="Mutual /30 subnet and ARP resolution.",
        )
        # 4. Logical Overlay Tunnel Edge
        e_log = TopologyEdge(
            id="edge_r1_r2_wg_tunnel",
            source_node_id="node_r1",
            target_node_id="node_r2",
            source_interface="wg0",
            target_interface="wg0",
            relationship_class="logical",
            relationship_subtype="overlay_tunnel",
            confidence_tier="CONFIRMED",
            confidence_score=1.0,
            confidence_rationale="Active WireGuard peer handshake confirmed.",
        )

        self.engine.insert_edge(e_phys)
        self.engine.insert_edge(e_l2)
        self.engine.insert_edge(e_l3)
        self.engine.insert_edge(e_log)

        all_edges = self.engine.list_edges(source_node_id="node_r1", target_node_id="node_r2")
        self.assertEqual(len(all_edges), 4)

        phys_edges = self.engine.list_edges(relationship_class="physical")
        self.assertEqual(len(phys_edges), 1)
        self.assertEqual(phys_edges[0].id, "edge_r1_r2_phys1")

        l2_edges = self.engine.list_edges(relationship_class="layer2")
        self.assertEqual(len(l2_edges), 1)
        self.assertEqual(l2_edges[0].vlan_id, 10)

        l3_edges = self.engine.list_edges(relationship_class="layer3")
        self.assertEqual(len(l3_edges), 1)

        log_edges = self.engine.list_edges(relationship_class="logical")
        self.assertEqual(len(log_edges), 1)

    # -------------------------------------------------------------------------
    # Test 5: Edge-Evidence Foreign Key Integrity & Cascade Delete
    # -------------------------------------------------------------------------
    def test_05_edge_evidence_foreign_key_integrity(self):
        """EdgeEvidence enforces edge existence, and hard deleting edge cascades to evidence."""
        self._insert_test_node("node_a", "Node A")
        self._insert_test_node("node_b", "Node B")

        # Non-existent edge should raise ValueError
        fake_ev = EdgeEvidence(
            edge_id="non_existent_edge",
            evidence_type="lldp_neighbor",
            observing_device_id="node_a",
            explanation="Unattached evidence",
        )
        with self.assertRaises(ValueError):
            self.engine.insert_edge_evidence(fake_ev)

        # Valid edge
        edge = TopologyEdge(
            id="edge_cascade_test",
            source_node_id="node_a",
            target_node_id="node_b",
            relationship_class="physical",
            confidence_rationale="LLDP verified",
        )
        self.engine.insert_edge(edge)

        ev = EdgeEvidence(
            edge_id="edge_cascade_test",
            evidence_type="lldp_neighbor",
            protocol="lldp",
            observing_device_id="node_a",
            local_interface="ether1",
            raw_excerpt="system-name=NodeB password=SecretPass",
            explanation="Mutual LLDP packet",
        )
        ev_id = self.engine.insert_edge_evidence(ev)
        self.assertGreater(ev_id, 0)

        # Raw excerpt must be sanitized (passwords redacted)
        stored_evs = self.engine.get_edge_evidence("edge_cascade_test")
        self.assertEqual(len(stored_evs), 1)
        self.assertNotIn("SecretPass", stored_evs[0].raw_excerpt)
        self.assertIn("[REDACTED]", stored_evs[0].raw_excerpt)

        # Hard delete cascades to evidence
        self.engine.delete_edge("edge_cascade_test", soft_delete=False)
        self.assertEqual(len(self.engine.get_edge_evidence("edge_cascade_test")), 0)

    # -------------------------------------------------------------------------
    # Test 6: Invalid Relationship Classes
    # -------------------------------------------------------------------------
    def test_06_invalid_relationship_classes(self):
        """Invalid relationship class raises ValueError on creation and update."""
        self._insert_test_node("node_x", "Node X")
        self._insert_test_node("node_y", "Node Y")

        with self.assertRaises(ValueError):
            TopologyEdge(
                id="edge_bad_class",
                source_node_id="node_x",
                target_node_id="node_y",
                relationship_class="magic_link",
                confidence_rationale="Speculation",
            )

        valid_edge = TopologyEdge(
            id="edge_valid_update",
            source_node_id="node_x",
            target_node_id="node_y",
            relationship_class="physical",
            confidence_rationale="Valid direct link",
        )
        self.engine.insert_edge(valid_edge)

        with self.assertRaises(ValueError):
            self.engine.update_edge("edge_valid_update", {"relationship_class": "telepathy"})

    # -------------------------------------------------------------------------
    # Test 7: Invalid Lifecycle States & Soft Deletion
    # -------------------------------------------------------------------------
    def test_07_invalid_lifecycle_states(self):
        """Invalid lifecycle state raises ValueError; soft-delete transitions to tombstoned."""
        self._insert_test_node("node_m", "Node M")
        self._insert_test_node("node_n", "Node N")

        with self.assertRaises(ValueError):
            TopologyEdge(
                id="edge_bad_state",
                source_node_id="node_m",
                target_node_id="node_n",
                relationship_class="physical",
                lifecycle_state="exploded",
                confidence_rationale="Valid rationale",
            )

        edge = TopologyEdge(
            id="edge_tombstone_test",
            source_node_id="node_m",
            target_node_id="node_n",
            relationship_class="physical",
            confidence_rationale="Physical cable",
        )
        self.engine.insert_edge(edge)

        # Soft delete
        self.assertTrue(self.engine.delete_edge("edge_tombstone_test", soft_delete=True))

        # Default list_edges excludes tombstoned
        active_edges = self.engine.list_edges(source_node_id="node_m")
        self.assertEqual(len(active_edges), 0)

        # Explicit include_tombstoned retrieves it
        all_edges = self.engine.list_edges(source_node_id="node_m", include_tombstoned=True)
        self.assertEqual(len(all_edges), 1)
        self.assertEqual(all_edges[0].lifecycle_state, "tombstoned")

    # -------------------------------------------------------------------------
    # Test 8: Snapshot Immutability (Integrity & SQLite Triggers)
    # -------------------------------------------------------------------------
    def test_08_snapshot_immutability(self):
        """Snapshots are protected by SHA-256 integrity and SQLite triggers preventing UPDATE/DELETE."""
        self._insert_test_node("node_snap_1", "Node S1")
        self._insert_test_node("node_snap_2", "Node S2")

        edge = TopologyEdge(
            id="edge_snap_test",
            source_node_id="node_snap_1",
            target_node_id="node_snap_2",
            relationship_class="physical",
            confidence_rationale="Verified connection",
        )
        self.engine.insert_edge(edge)

        snap = self.engine.create_snapshot(description="Pre-Maintenance Snapshot")
        self.assertEqual(snap.node_count, 2)
        self.assertEqual(snap.edge_count, 1)
        self.assertTrue(snap.verify_integrity())

        # Attempt SQLite UPDATE directly -> trigger should abort
        with self.assertRaises(sqlite3.IntegrityError):
            with self.engine._lock, closing(self.engine._get_connection()) as conn:
                conn.execute(
                    "UPDATE topology_snapshots SET description = 'Tampered' WHERE snapshot_id = ?",
                    (snap.snapshot_id,),
                )

        # Attempt SQLite DELETE directly -> trigger should abort
        with self.assertRaises(sqlite3.IntegrityError):
            with self.engine._lock, closing(self.engine._get_connection()) as conn:
                conn.execute(
                    "DELETE FROM topology_snapshots WHERE snapshot_id = ?",
                    (snap.snapshot_id,),
                )

    # -------------------------------------------------------------------------
    # Test 9: Topology Change History
    # -------------------------------------------------------------------------
    def test_09_topology_change_history(self):
        """Records delta changes and queries history filtered by entity and snapshot."""
        # Create a valid snapshot first to satisfy foreign key constraint
        snap = self.engine.create_snapshot(description="Initial change baseline")

        change1 = TopologyChange(
            snapshot_id=snap.snapshot_id,
            change_type="EDGE_ADDED",
            entity_id="edge_alpha",
            change_reason="Newly discovered physical connection",
        )
        change2 = TopologyChange(
            snapshot_id=snap.snapshot_id,
            change_type="STATUS_CHANGED",
            entity_id="edge_alpha",
            attribute_name="oper_status",
            before_value_json='"up"',
            after_value_json='"down"',
            change_reason="Carrier lost on ether1",
        )

        id1 = self.engine.record_change(change1)
        id2 = self.engine.record_change(change2)
        self.assertGreater(id1, 0)
        self.assertGreater(id2, id1)

        changes = self.engine.list_changes(entity_id="edge_alpha")
        self.assertEqual(len(changes), 2)
        types = {c.change_type for c in changes}
        self.assertIn("EDGE_ADDED", types)
        self.assertIn("STATUS_CHANGED", types)

        # Also support standalone changes with snapshot_id=None
        change3 = TopologyChange(
            snapshot_id=None,
            change_type="NODE_ADDED",
            entity_id="node_beta",
            change_reason="Standalone change event",
        )
        id3 = self.engine.record_change(change3)
        self.assertGreater(id3, 0)

        with self.assertRaises(ValueError):
            TopologyChange(entity_id="edge_alpha", change_type="UNSUPPORTED_TYPE")

    # -------------------------------------------------------------------------
    # Test 10: Transaction Rollback
    # -------------------------------------------------------------------------
    def test_10_transaction_rollback(self):
        """Transactional operations cleanly rollback all modifications when an error occurs."""
        self._insert_test_node("node_tx_1", "Node TX 1")
        self._insert_test_node("node_tx_2", "Node TX 2")

        edge_tx = TopologyEdge(
            id="edge_tx_ok",
            source_node_id="node_tx_1",
            target_node_id="node_tx_2",
            relationship_class="physical",
            confidence_rationale="Transaction test edge",
        )

        try:
            with self.engine.transaction() as tx:
                self.engine.insert_edge(edge_tx, conn=tx)
                # Intentionally cause an error
                raise RuntimeError("Simulated failure inside transaction block")
        except RuntimeError:
            pass

        # Assert edge was rolled back and does not exist
        retrieved = self.engine.get_edge("edge_tx_ok")
        self.assertIsNone(retrieved)

    # -------------------------------------------------------------------------
    # Test 11: Backward Compatibility with Existing Topology Queries
    # -------------------------------------------------------------------------
    def test_11_backward_compatibility_get_topology(self):
        """get_topology() returns all legacy graph objects, governance metadata, and statistics."""
        self._insert_test_node("node_chr", "CHR-Main", "10.66.38.30")
        self.engine.upsert_link(
            source_id="node_chr",
            target_id="node_chr",
            source_port="ether1",
            target_port="gw1",
            link_type="routed",
            status="up",
        )

        topo = self.engine.get_topology()
        self.assertIn("nodes", topo)
        self.assertIn("links", topo)
        self.assertIn("stats", topo)
        self.assertIn("policy", topo)
        self.assertEqual(len(topo["nodes"]), 1)
        self.assertEqual(topo["nodes"][0]["id"], "node_chr")
        self.assertEqual(len(topo["links"]), 1)

    # -------------------------------------------------------------------------
    # Test 12: Existing Database Records Preserved Intact
    # -------------------------------------------------------------------------
    def test_12_existing_database_records_preserved(self):
        """Persistent SQLite records remain bit-for-bit intact across engine re-initialization."""
        self._insert_test_node("node_p1", "Persistent Node 1", "172.16.0.1")
        edge_p = TopologyEdge(
            id="edge_persistent",
            source_node_id="node_p1",
            target_node_id="node_p1",
            relationship_class="logical",
            relationship_subtype="parent_child_interface",
            confidence_rationale="Loopback configuration",
        )
        self.engine.insert_edge(edge_p)

        # Close and instantiate a new engine instance on the exact same database file
        new_engine = TopologyEngine(self.db_path)
        e = new_engine.get_edge("edge_persistent")
        self.assertIsNotNone(e)
        self.assertEqual(e.relationship_class, "logical")
        self.assertEqual(e.confidence_rationale, "Loopback configuration")


if __name__ == "__main__":
    unittest.main()
