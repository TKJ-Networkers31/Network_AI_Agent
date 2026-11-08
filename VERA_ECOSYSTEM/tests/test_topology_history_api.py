"""
tests/test_topology_history_api.py — Test Suite for Phase 4.4B Historical Topology REST APIs

Covers:
- Snapshots listing with pagination & metadata summary
- Snapshot retrieval with parsed graph
- Explicit snapshot creation with admin guard
- Snapshot SHA-256 cryptographic integrity verification
- Semantic snapshot diff comparison endpoint
- Change history listing with multi-field filters & time range
- Change detail retrieval with evidence references
- Read-only historical access guarantees
"""

import os
import time
import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Dict, List
import pytest
from fastapi.testclient import TestClient

from api.main import app
import core.topology_engine
from core.topology_engine import TopologyEngine, get_topology_engine
from core.topology_models import (
    TopologySnapshot,
    TopologyChange,
    TopologyEdge,
    EdgeEvidence,
)
from core.tenant.auth_deps import get_current_authenticated_user
from core.tenant.models import TenantContext

@pytest.fixture(autouse=True)
def setup_test_engine(monkeypatch):
    """Provides an isolated test database and TopologyEngine for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = Path(tmpdir) / "test_api_history.db"
        engine = TopologyEngine(test_db)
        monkeypatch.setattr(core.topology_engine, "_engine_instance", engine)
        monkeypatch.setattr("api.routers.topology.get_topology_engine", lambda: engine)

        # Seed initial data
        engine.upsert_node(node_id="r1", name="Router-1", ip="10.0.0.1", device_type="router")
        engine.upsert_node(node_id="sw1", name="Switch-1", ip="10.0.0.2", device_type="switch")
        edge_1 = TopologyEdge(
            id="edge_r1_sw1",
            source_node_id="r1",
            target_node_id="sw1",
            source_interface="eth1",
            target_interface="eth1",
            relationship_class="physical",
            relationship_subtype="ethernet",
            oper_status="up",
            confidence_tier="CONFIRMED",
            confidence_rationale="Verified link",
        )
        engine.insert_edge(edge_1)
        ev_1 = EdgeEvidence(
            edge_id="edge_r1_sw1",
            evidence_type="lldp",
            protocol="lldp",
            observing_device_id="r1",
            local_interface="eth1",
            remote_interface="eth1",
            confidence_contribution="high",
            observed_at=time.time(),
            is_active=True,
        )
        engine.insert_edge_evidence(ev_1)

        # Create two baseline snapshots
        snap1 = engine.create_snapshot(trigger_type="manual", description="Baseline Initial")
        
        # Mutate state for second snapshot
        engine.upsert_node(node_id="sw2", name="Switch-2", ip="10.0.0.3", device_type="switch")
        edge_2 = TopologyEdge(
            id="edge_r1_sw2",
            source_node_id="r1",
            target_node_id="sw2",
            source_interface="eth2",
            target_interface="eth1",
            relationship_class="physical",
            oper_status="up",
            confidence_tier="HIGH",
            confidence_rationale="CDP link",
        )
        engine.insert_edge(edge_2)
        snap2 = engine.create_snapshot(trigger_type="discovery_run", description="Discovery Second")

        # Record a sample change
        chg = TopologyChange(
            snapshot_id=snap2.snapshot_id,
            change_type="NODE_ADDED",
            entity_id="sw2",
            change_reason="Switch-2 discovered in second scan",
            attribute_name="device",
            before_value_json=json.dumps(None),
            after_value_json=json.dumps({"id": "sw2", "name": "Switch-2"}),
            detected_at=time.time(),
        )
        engine.record_change(chg)

        yield {
            "engine": engine,
            "snap1": snap1,
            "snap2": snap2,
            "db_path": test_db,
        }

@pytest.fixture
def client():
    mock_admin_context = TenantContext(
        user_id="usr_25b8282cc548",
        username="lingga_admin",
        is_internal=True,
        tenant_id="tenant_internal",
        roles=["SUPER_ADMIN"],
        groups=["SUPER_ADMIN"],
        permissions={"*"},
        account_enabled=True,
    )
    app.dependency_overrides[get_current_authenticated_user] = lambda: mock_admin_context
    tc = TestClient(app)
    yield tc
    app.dependency_overrides.clear()

# -----------------------------------------------------------------------------
# 1. Snapshot Management API Tests
# -----------------------------------------------------------------------------

def test_list_snapshots_pagination(client, setup_test_engine):
    """Verifies GET /api/topology/snapshots with pagination and graph exclusion."""
    res = client.get("/api/topology/snapshots?limit=1&offset=0")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["total"] == 2
    assert len(data["snapshots"]) == 1
    # graph_json should be excluded by default
    assert "graph_json" not in data["snapshots"][0]
    assert "snapshot_id" in data["snapshots"][0]
    assert "is_complete" in data["snapshots"][0]
    assert "discovery_status" in data["snapshots"][0]

def test_list_snapshots_include_graph(client, setup_test_engine):
    """Verifies include_graph=true parameter returns raw graph_json."""
    res = client.get("/api/topology/snapshots?limit=5&include_graph=true")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "graph_json" in data["snapshots"][0]
    assert len(data["snapshots"][0]["graph_json"]) > 10

def test_list_snapshots_filter_by_trigger(client, setup_test_engine):
    """Verifies trigger_type filtering in snapshot listing."""
    res = client.get("/api/topology/snapshots?trigger_type=manual")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["snapshots"][0]["trigger_type"] == "manual"

def test_get_snapshot_details(client, setup_test_engine):
    """Verifies GET /api/topology/snapshots/{id} returns parsed graph and verification status."""
    snap1_id = setup_test_engine["snap1"].snapshot_id
    res = client.get(f"/api/topology/snapshots/{snap1_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    snap = data["snapshot"]
    assert snap["snapshot_id"] == snap1_id
    assert "graph" in snap
    assert isinstance(snap["graph"], dict)
    assert len(snap["graph"]["nodes"]) == 2
    assert snap["integrity_verified"] is True

def test_get_snapshot_not_found(client):
    """Verifies 404 for non-existent snapshot ID."""
    res = client.get("/api/topology/snapshots/non_existent_snap_999")
    assert res.status_code == 404
    assert "tidak ditemukan" in res.json()["detail"]

def test_create_snapshot_explicit(client, setup_test_engine):
    """Verifies POST /api/topology/snapshots creates a point-in-time snapshot."""
    payload = {
        "description": "User requested audit snapshot",
        "trigger_type": "manual",
    }
    res = client.post("/api/topology/snapshots", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "snapshot" in data
    new_snap = data["snapshot"]
    assert new_snap["description"] == "User requested audit snapshot"
    assert new_snap["node_count"] == 3
    assert new_snap["edge_count"] == 2
    assert new_snap["sha256_hash"] != ""

def test_verify_snapshot_integrity_verified(client, setup_test_engine):
    """Verifies GET /api/topology/snapshots/{id}/verify confirms untampered snapshot."""
    snap1_id = setup_test_engine["snap1"].snapshot_id
    res = client.get(f"/api/topology/snapshots/{snap1_id}/verify")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["verified"] is True
    assert data["integrity_status"] == "verified"
    assert data["sha256_hash"] == data["computed_hash"]

# -----------------------------------------------------------------------------
# 2. Snapshot Comparison API Tests
# -----------------------------------------------------------------------------

def test_compare_snapshots_endpoint(client, setup_test_engine):
    """Verifies GET /api/topology/snapshots/compare produces full GraphDiffReport."""
    snap1_id = setup_test_engine["snap1"].snapshot_id
    snap2_id = setup_test_engine["snap2"].snapshot_id

    res = client.get(f"/api/topology/snapshots/compare?base_id={snap1_id}&target_id={snap2_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    diff = data["diff"]
    assert diff["base_snapshot_id"] == snap1_id
    assert diff["target_snapshot_id"] == snap2_id
    assert diff["summary"]["nodes_added"] == 1
    assert diff["summary"]["edges_added"] == 1
    assert len(diff["structural_changes"]) >= 2
    types = {c["change_type"] for c in diff["structural_changes"]}
    assert "NODE_ADDED" in types
    assert "EDGE_ADDED" in types
    assert "telemetry" in diff
    assert diff["telemetry"]["total_duration_ms"] >= 0

def test_compare_snapshots_invalid_ids(client, setup_test_engine):
    """Verifies 404 when comparing with non-existent snapshot IDs."""
    snap1_id = setup_test_engine["snap1"].snapshot_id
    res = client.get(f"/api/topology/snapshots/compare?base_id={snap1_id}&target_id=invalid_id")
    assert res.status_code == 404

# -----------------------------------------------------------------------------
# 3. Topology Change History API Tests
# -----------------------------------------------------------------------------

def test_list_changes_endpoint(client, setup_test_engine):
    """Verifies GET /api/topology/changes returns recorded delta changes."""
    res = client.get("/api/topology/changes")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["total"] >= 1
    assert len(data["changes"]) >= 1
    chg = data["changes"][0]
    assert chg["change_type"] == "NODE_ADDED"
    assert chg["entity_id"] == "sw2"
    assert chg["before_value"] is None
    assert chg["after_value"]["name"] == "Switch-2"

def test_list_changes_filtering(client, setup_test_engine):
    """Verifies filtering changes by change_type and entity_id."""
    # Matching filter
    res = client.get("/api/topology/changes?change_type=NODE_ADDED&entity_id=sw2")
    assert res.status_code == 200
    assert res.json()["total"] == 1

    # Non-matching filter
    res2 = client.get("/api/topology/changes?change_type=EDGE_REMOVED")
    assert res2.status_code == 200
    assert res2.json()["total"] == 0

def test_get_change_detail_with_evidence(client, setup_test_engine):
    """Verifies GET /api/topology/changes/{id} returns details and evidence references."""
    # List to get ID
    list_res = client.get("/api/topology/changes")
    chg_id = list_res.json()["changes"][0]["id"]

    res = client.get(f"/api/topology/changes/{chg_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    change = data["change"]
    assert change["id"] == chg_id
    assert change["change_type"] == "NODE_ADDED"
    assert "related_evidence" in change

def test_get_change_not_found(client):
    """Verifies 404 for non-existent change ID."""
    res = client.get("/api/topology/changes/999999")
    assert res.status_code == 404

# -----------------------------------------------------------------------------
# 4. Read-Only Historical Safety
# -----------------------------------------------------------------------------

def test_historical_reads_do_not_mutate_topology(client, setup_test_engine):
    """Verifies that reading snapshots and diffs does not mutate current topology."""
    engine = setup_test_engine["engine"]
    topo_before = engine.get_topology()
    snap1_id = setup_test_engine["snap1"].snapshot_id
    snap2_id = setup_test_engine["snap2"].snapshot_id

    # Execute multiple read calls
    client.get(f"/api/topology/snapshots")
    client.get(f"/api/topology/snapshots/{snap1_id}")
    client.get(f"/api/topology/snapshots/{snap1_id}/verify")
    client.get(f"/api/topology/snapshots/compare?base_id={snap1_id}&target_id={snap2_id}")
    client.get("/api/topology/changes")

    topo_after = engine.get_topology()
    assert len(topo_before["nodes"]) == len(topo_after["nodes"])
    assert len(topo_before["edges"]) == len(topo_after["edges"])
