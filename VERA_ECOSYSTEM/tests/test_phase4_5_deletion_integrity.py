# AIRA_ECOSYSTEM/tests/test_phase4_5_deletion_integrity.py
# Phase 4.5 Critical Deletion & Historical Integrity Acceptance Test Suite

import json
import os
import sqlite3
import tempfile
import time
import pytest
from fastapi.testclient import TestClient

from core.topology_engine import TopologyEngine
from core.topology_models import (
    TopologyEdge,
    EdgeEvidence,
    TopologyChange,
    TopologyChangeType,
)
from api.main import app


@pytest.fixture
def temp_engine():
    """Provides a fresh isolated TopologyEngine on an ephemeral SQLite database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    engine = TopologyEngine(db_path=db_path)

    # Seed nodes
    engine.upsert_node(node_id="node_a", name="Router-A", ip="10.0.0.1", device_type="router")
    engine.upsert_node(node_id="node_b", name="Switch-B", ip="10.0.0.2", device_type="switch")

    yield engine

    try:
        os.remove(db_path)
    except Exception:
        pass


def test_01_active_edge_deletion_does_not_modify_snapshots(temp_engine):
    """Verify deleting an active edge leaves existing snapshots and SHA-256 hashes 100% immutable."""
    # 1. Create an active edge with empirical evidence
    edge_id = temp_engine.insert_edge(
        TopologyEdge(
            id="edge_test_01",
            source_node_id="node_a",
            target_node_id="node_b",
            relationship_class="physical",
            source_interface="ether1",
            target_interface="ether1",
            oper_status="up",
            verification_status="confirmed",
            confidence_tier="CONFIRMED",
            confidence_score=1.0,
            confidence_rationale="Confirmed physical link test",
        )
    )
    temp_engine.insert_edge_evidence(
        EdgeEvidence(
            edge_id=edge_id,
            evidence_type="lldp",
            observing_device_id="node_a",
            local_interface="ether1",
            remote_interface="ether1",
            confidence_contribution="high",
            explanation="Bidirectional LLDP port match",
            observed_at=time.time(),
        )
    )

    # 2. Create immutable snapshot
    snap = temp_engine.create_snapshot(trigger_type="manual", description="Pre-deletion baseline")
    snap_id = snap.snapshot_id
    snap_hash_before = snap.sha256_hash

    # 3. Delete the active edge
    deleted = temp_engine.delete_edge(edge_id, soft_delete=True, reason="Decommissioned link")
    assert deleted is True

    # 4. Verify snapshot remains completely unchanged
    snap_after = temp_engine.get_snapshot(snap_id)
    assert snap_after is not None
    assert snap_after.sha256_hash == snap_hash_before

    # Verify snapshot embedded graph still contains the edge and evidence
    snap_graph = json.loads(snap_after.graph_json)
    snap_edges = [e["id"] for e in snap_graph.get("edges", [])]
    assert edge_id in snap_edges
    snap_ev = [ev["edge_id"] for ev in snap_graph.get("evidence", [])]
    assert edge_id in snap_ev


def test_02_historical_evidence_retrievable_after_deletion(temp_engine):
    """Verify evidence remains retrievable for changes and snapshots after active edge deletion."""
    edge_id = temp_engine.insert_edge(
        TopologyEdge(
            id="edge_test_02",
            source_node_id="node_a",
            target_node_id="node_b",
            relationship_class="layer2",
            source_interface="ether2",
            target_interface="ether2",
            oper_status="up",
            confidence_rationale="Confirmed Layer 2 adjacency test",
        )
    )
    temp_engine.insert_edge_evidence(
        EdgeEvidence(
            edge_id=edge_id,
            evidence_type="mndp",
            observing_device_id="node_a",
            local_interface="ether2",
            remote_interface="ether2",
            confidence_contribution="medium",
            explanation="Single-sided MNDP observation",
            observed_at=time.time(),
        )
    )

    snap = temp_engine.create_snapshot(trigger_type="manual", description="Snapshot with MNDP")

    # Delete the edge
    temp_engine.delete_edge(edge_id, soft_delete=True)

    # Active edge list must NOT return the edge
    active_edges = temp_engine.list_edges(include_tombstoned=False)
    assert edge_id not in [e.id for e in active_edges]

    # But historical snapshot still contains full evidence
    snap_retrieved = temp_engine.get_snapshot(snap.snapshot_id)
    snap_graph = json.loads(snap_retrieved.graph_json)
    ev_records = snap_graph.get("evidence", [])
    matching = [ev for ev in ev_records if ev.get("edge_id") == edge_id]
    assert len(matching) == 1
    assert matching[0]["evidence_type"] == "mndp"


def test_03_auditable_topology_change_recorded_on_deletion(temp_engine):
    """Verify deleting an edge records an auditable EDGE_REMOVED TopologyChange."""
    edge_id = temp_engine.insert_edge(
        TopologyEdge(
            id="edge_test_03",
            source_node_id="node_a",
            target_node_id="node_b",
            relationship_class="layer3",
            source_interface="ether3",
            target_interface="",
            confidence_rationale="Routed L3 reachability test",
        )
    )

    count_before = len(temp_engine.list_changes(entity_id=edge_id))

    # Perform deletion
    temp_engine.delete_edge(edge_id, soft_delete=True, reason="User removed routed link")

    changes = temp_engine.list_changes(entity_id=edge_id)
    assert len(changes) == count_before + 1
    latest_change = changes[0]
    assert latest_change.change_type == "EDGE_REMOVED"
    assert "User removed routed link" in latest_change.change_reason


def test_04_parallel_edges_between_same_nodes_preserved(temp_engine):
    """Verify deleting one edge does NOT delete parallel relationships between identical nodes."""
    # Create two parallel relationships between node_a and node_b:
    # 1. Physical link (ether1 <-> ether1)
    # 2. Layer 3 routed reachability (ether2 <-> ether2)
    edge_phys = temp_engine.insert_edge(
        TopologyEdge(
            id="edge_phys_04",
            source_node_id="node_a",
            target_node_id="node_b",
            relationship_class="physical",
            source_interface="ether1",
            target_interface="ether1",
            confidence_rationale="Physical link test",
        )
    )
    edge_l3 = temp_engine.insert_edge(
        TopologyEdge(
            id="edge_l3_04",
            source_node_id="node_a",
            target_node_id="node_b",
            relationship_class="layer3",
            source_interface="ether2",
            target_interface="ether2",
            confidence_rationale="Layer 3 link test",
        )
    )
    assert edge_phys != edge_l3

    # Delete only the physical edge
    ok = temp_engine.delete_edge(edge_phys, soft_delete=True)
    assert ok is True

    # Verify physical edge is tombstoned, but Layer 3 edge is still active!
    active_edges = temp_engine.list_edges(include_tombstoned=False)
    active_ids = [e.id for e in active_edges]
    assert edge_phys not in active_ids
    assert edge_l3 in active_ids


def test_05_repeated_and_invalid_deletion_handled_predictably(temp_engine):
    """Verify repeated deletion and non-existent IDs return False predictably."""
    # Invalid ID
    assert temp_engine.delete_edge("non_existent_edge_123") is False

    # Valid ID then repeated
    edge_id = temp_engine.insert_edge(
        TopologyEdge(
            id="edge_test_05",
            source_node_id="node_a",
            target_node_id="node_b",
            relationship_class="logical",
            confidence_rationale="Logical test relationship",
        )
    )
    assert temp_engine.delete_edge(edge_id, soft_delete=True) is True
    # Repeated deletion must return False (already deleted)
    assert temp_engine.delete_edge(edge_id, soft_delete=True) is False


def test_06_fastapi_endpoints_authorization_and_safety():
    """Verify DELETE /api/topology/edges/{id} and /links enforce admin authorization and return 404 for missing IDs."""
    client = TestClient(app)

    # Set admin token to enforce token authentication
    os.environ["AIRA_TOPOLOGY_ADMIN_TOKEN"] = "test_adm_secret_token_999"
    try:
        # 1. Without auth header: must be rejected with 403 Forbidden
        res_no_auth = client.delete("/api/topology/edges/edge_test_123")
        assert res_no_auth.status_code == 403

        res_link_no_auth = client.delete("/api/topology/links?link_id=link_test_123")
        assert res_link_no_auth.status_code == 403

        # 2. With invalid token: must be rejected with 403 Forbidden
        res_bad_auth = client.delete(
            "/api/topology/edges/edge_test_123",
            headers={"X-AIRA-Admin-Token": "wrong_token"},
        )
        assert res_bad_auth.status_code == 403

        # 3. With valid admin token but non-existent ID: must return 404 Not Found
        res_404 = client.delete(
            "/api/topology/edges/edge_missing_999",
            headers={"X-AIRA-Admin-Token": "test_adm_secret_token_999"},
        )
        assert res_404.status_code == 404
        assert "tidak ditemukan" in res_404.json()["detail"]

        res_link_404 = client.delete(
            "/api/topology/links?link_id=missing_link_999",
            headers={"X-AIRA-Admin-Token": "test_adm_secret_token_999"},
        )
        assert res_link_404.status_code == 404
    finally:
        os.environ.pop("AIRA_TOPOLOGY_ADMIN_TOKEN", None)
