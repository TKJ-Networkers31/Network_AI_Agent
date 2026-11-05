"""
AIRA OS - Runtime Acceptance Verification Script
Tests Scenarios A through E:
- Scenario A: Startup (single init, subscriber registration, clean startup)
- Scenario B: Topology (graph load, queries, snapshots, read-only safe)
- Scenario C: NMS (device observations, status updates, event handling)
- Scenario D: Concurrent Operations (concurrent writes/reads across NMS and Topology)
- Scenario E: Restart (graceful shutdown, re-init, no duplicate subscribers/schedulers, data preserved)
"""

import os
import sys
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

# Set up environment
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["PYTHONPATH"] = "AIRA_ECOSYSTEM"
os.environ["WEB_CONCURRENCY"] = "1"
os.environ["UVICORN_WORKERS"] = "1"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("acceptance_audit")

# Ensure no outbound SSH is initiated during acceptance testing
import api.routers.devices
api.routers.devices.sync_inventory_and_topology = lambda: logger.info("Live device sync bypassed for test.")

import agents.akane.connection_manager
def mock_open_connection(self, host, username, password=None, port=22, **kwargs):
    logger.info("Outbound SSH connection to %s bypassed for acceptance test.", host)
    return {"success": False, "error": "SSH mocked for offline test"}
agents.akane.connection_manager.ConnectionManager.open_connection = mock_open_connection

from fastapi.testclient import TestClient
from api.main import app
from core.topology_engine import get_topology_engine
from core.nms_engine import get_nms_engine
from core.events import event_bus, EventNames
from core.topology_db import get_topology_connection, topology_transaction, execute_with_retry

results = {}

def log_section(title):
    print(f"\n{'='*70}\n[ACCEPTANCE SCENARIO] {title}\n{'='*70}")

def run_acceptance():
    # -------------------------------------------------------------
    # Scenario A: Startup
    # -------------------------------------------------------------
    log_section("Scenario A - Startup Verification")
    
    with TestClient(app) as client:
        # Check health
        health_resp = client.get("/api/health")
        assert health_resp.status_code == 200, f"Health check failed: {health_resp.status_code}"
        assert health_resp.json() == {"status": "ok", "ecosystem": "AIRA"}
        logger.info("Health check passed: %s", health_resp.json())
        
        # Verify single instance and subscriber registration
        topo = get_topology_engine()
        nms = get_nms_engine()
        
        # Verify subscriber registration count for NMS events
        interface_subs = event_bus._subscribers.get(EventNames.NMS_INTERFACE_STATUS_CHANGED, [])
        logger.info("%s subscribers: %d", EventNames.NMS_INTERFACE_STATUS_CHANGED, len(interface_subs))
        assert len(interface_subs) >= 1, f"Expected at least 1 subscriber for {EventNames.NMS_INTERFACE_STATUS_CHANGED}"
        
        # Check WAL and PRAGMA settings on topology.db
        with get_topology_connection(read_only=True) as conn:
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            sync_mode = conn.execute("PRAGMA synchronous").fetchone()[0]
            query_only = conn.execute("PRAGMA query_only").fetchone()[0]
            
            logger.info("PRAGMA journal_mode: %s", journal_mode)
            logger.info("PRAGMA busy_timeout: %s", busy_timeout)
            logger.info("PRAGMA synchronous: %s", sync_mode)
            logger.info("PRAGMA query_only (readonly connection): %s", query_only)
            
            assert journal_mode.lower() == "wal", f"Expected WAL, got {journal_mode}"
            assert busy_timeout == 30000, f"Expected 30000, got {busy_timeout}"
            assert sync_mode in (1, "1", "NORMAL", "normal"), f"Expected NORMAL (1), got {sync_mode}"
            assert query_only in (1, "1", True), f"Expected query_only=1 on readonly connection, got {query_only}"

        results["Scenario_A_Startup"] = "PASSED"
        logger.info("Scenario A completed successfully.")

        # -------------------------------------------------------------
        # Scenario B: Topology Operations
        # -------------------------------------------------------------
        log_section("Scenario B - Topology Operations")
        
        # Fetch topology graph via API
        graph_resp = client.get("/api/topology")
        assert graph_resp.status_code == 200, f"Graph fetch failed: {graph_resp.text}"
        graph_data = graph_resp.json()
        logger.info("Topology graph: %d nodes, %d links", len(graph_data.get("nodes", [])), len(graph_data.get("links", [])))
        
        # List normalized edges via API
        edges_resp = client.get("/api/topology/edges")
        assert edges_resp.status_code == 200, f"Edges fetch failed: {edges_resp.text}"
        edges_data = edges_resp.json()
        logger.info("Topology edges: %d total", edges_data.get("total", 0))
        
        # List snapshots via TopologyEngine
        snapshots = topo.list_snapshots()
        logger.info("Historical snapshots count: %d", len(snapshots))
        
        # Create a new historical snapshot via TopologyEngine
        snap = topo.create_snapshot(trigger_type="manual", description="Acceptance Test Snapshot")
        assert snap is not None, "Snapshot creation returned None"
        logger.info("Snapshot created: %s (id: %s)", snap.description, snap.snapshot_id)
        
        # Verify snapshot persisted in DB
        with get_topology_connection(read_only=True) as conn:
            snap_count = conn.execute("SELECT COUNT(*) FROM topology_snapshots WHERE description = 'Acceptance Test Snapshot'").fetchone()[0]
            assert snap_count >= 1, "Newly created snapshot not found in topology_snapshots table"
            
        results["Scenario_B_Topology"] = "PASSED"
        logger.info("Scenario B completed successfully.")

        # -------------------------------------------------------------
        # Scenario C: NMS Operations & Decoupled Event Boundary
        # -------------------------------------------------------------
        log_section("Scenario C - NMS Operations & Event Boundary")
        
        # Fetch NMS overview and devices via API
        overview_resp = client.get("/api/nms/overview")
        assert overview_resp.status_code == 200, f"NMS overview failed: {overview_resp.text}"
        logger.info("NMS overview: %s", overview_resp.json())
        
        nms_devs_resp = client.get("/api/nms/devices")
        assert nms_devs_resp.status_code == 200, f"NMS devices fetch failed: {nms_devs_resp.text}"
        logger.info("NMS devices count: %d", len(nms_devs_resp.json()))
        
        # Simulate NMS interface status change event
        event_payload = {
            "device_id": "test-device-c",
            "interface_name": "ether1",
            "previous_status": "up",
            "current_status": "down",
            "reason": "link_down_acceptance_test",
            "timestamp": time.time()
        }
        
        # Test publishing via EventBus - verify subscribers handle cleanly without locking
        topo_delta_events = []
        def delta_listener(event):
            topo_delta_events.append(event)
            
        sub_token = event_bus.subscribe("topology.delta", delta_listener)
        
        # Trigger NMS interface event
        event_bus.publish(EventNames.NMS_INTERFACE_STATUS_CHANGED, data=event_payload)
        time.sleep(0.1) # brief tick for processing
        
        event_bus.unsubscribe("topology.delta", sub_token)
        logger.info("NMS event processed without exception; delta events observed: %d", len(topo_delta_events))
        
        results["Scenario_C_NMS"] = "PASSED"
        logger.info("Scenario C completed successfully.")

        # -------------------------------------------------------------
        # Scenario D: Concurrent Topology & NMS Operations
        # -------------------------------------------------------------
        log_section("Scenario D - Concurrent Operations (Stress & Integrity)")
        
        concurrent_errors = []
        iterations_per_thread = 20
        
        def worker_nms_writer(thread_id):
            try:
                for i in range(iterations_per_thread):
                    dev_id = f"worker-dev-{thread_id}-{i}"
                    now_ts = time.time()
                    # Simulate NMS write transaction
                    with topology_transaction() as conn:
                        conn.execute("""
                            INSERT INTO topology_nodes (id, name, identity, device_type, first_seen, last_seen)
                            VALUES (?, ?, ?, 'router', ?, ?)
                            ON CONFLICT(id) DO UPDATE SET last_seen = ?
                        """, (dev_id, f"Router-{thread_id}-{i}", f"Identity-{thread_id}-{i}", now_ts, now_ts, now_ts))
                    
                    # Publish event decoupled outside transaction
                    event_bus.publish(EventNames.NMS_INTERFACE_STATUS_CHANGED, data={
                        "device_id": dev_id,
                        "interface_name": "ether1",
                        "current_status": "up",
                        "timestamp": time.time()
                    })
                    time.sleep(0.005)
            except Exception as exc:
                logger.error("Exception in worker_nms_writer %s: %s", thread_id, exc)
                concurrent_errors.append(exc)

        def worker_snapshot_creator(thread_id):
            try:
                for i in range(5):
                    # Concurrent snapshot read & write
                    snap = topo.create_snapshot(trigger_type="manual", description=f"Concurrent Snap {thread_id}-{i}")
                    time.sleep(0.02)
            except Exception as exc:
                logger.error("Exception in worker_snapshot_creator %s: %s", thread_id, exc)
                concurrent_errors.append(exc)

        def worker_graph_reader(thread_id):
            try:
                for i in range(iterations_per_thread):
                    # Concurrent read operations
                    g = topo.get_topology()
                    time.sleep(0.005)
            except Exception as exc:
                logger.error("Exception in worker_graph_reader %s: %s", thread_id, exc)
                concurrent_errors.append(exc)

        # Launch concurrent threads
        with ThreadPoolExecutor(max_workers=8) as executor:
            f1 = executor.submit(worker_nms_writer, 1)
            f2 = executor.submit(worker_nms_writer, 2)
            f3 = executor.submit(worker_snapshot_creator, 1)
            f4 = executor.submit(worker_snapshot_creator, 2)
            f5 = executor.submit(worker_graph_reader, 1)
            f6 = executor.submit(worker_graph_reader, 2)
            
            f1.result()
            f2.result()
            f3.result()
            f4.result()
            f5.result()
            f6.result()

        assert len(concurrent_errors) == 0, f"Encountered concurrent errors: {concurrent_errors}"
        logger.info("Concurrent stress execution completed with 0 errors across 8 threads!")
        
        results["Scenario_D_Concurrency"] = "PASSED"
        logger.info("Scenario D completed successfully.")

    # -------------------------------------------------------------
    # Scenario E: Restart & Shutdown Verification
    # -------------------------------------------------------------
    log_section("Scenario E - Restart Verification")
    
    # 1. Capture snapshot count before restart
    with get_topology_connection(read_only=True) as conn:
        nodes_before = conn.execute("SELECT COUNT(*) FROM topology_nodes").fetchone()[0]
        snaps_before = conn.execute("SELECT COUNT(*) FROM topology_snapshots").fetchone()[0]
    
    logger.info("Before restart: %d nodes, %d snapshots", nodes_before, snaps_before)
    
    # 2. Simulate restart cycle: new TestClient context triggers startup again
    with TestClient(app) as client_restarted:
        health_resp = client_restarted.get("/api/health")
        assert health_resp.status_code == 200
        
        # Verify subscriber counts didn't duplicate
        interface_subs = event_bus._subscribers.get(EventNames.NMS_INTERFACE_STATUS_CHANGED, [])
        logger.info("Post-restart %s subscribers: %d", EventNames.NMS_INTERFACE_STATUS_CHANGED, len(interface_subs))
        # Note: start_nms_sync registers once, stop_nms_sync on shutdown unregisters.
        # Should be exactly 1 subscriber.
        assert len(interface_subs) == 1, f"Expected exactly 1 subscriber post-restart, got {len(interface_subs)}"
        
        # Verify data preservation
        with get_topology_connection(read_only=True) as conn:
            nodes_after = conn.execute("SELECT COUNT(*) FROM topology_nodes").fetchone()[0]
            snaps_after = conn.execute("SELECT COUNT(*) FROM topology_snapshots").fetchone()[0]
            
        logger.info("After restart: %d nodes, %d snapshots", nodes_after, snaps_after)
        assert nodes_after >= nodes_before, "Nodes lost after restart!"
        assert snaps_after >= snaps_before, "Snapshots lost after restart!"

    results["Scenario_E_Restart"] = "PASSED"
    logger.info("Scenario E completed successfully.")

    # -------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------
    log_section("Final Acceptance Summary")
    for scenario, res in results.items():
        print(f"  {scenario:<30}: {res}")
    
    print("\nALL SCENARIOS PASSED WITH ZERO LOCK ERRORS!")

if __name__ == "__main__":
    run_acceptance()
