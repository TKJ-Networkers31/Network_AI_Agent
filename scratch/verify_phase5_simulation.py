"""
scratch/verify_phase5_simulation.py — Non-Destructive Failure Simulation & Database Integrity Script.
"""

import hashlib
import os
import sqlite3
import sys
import time

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "AIRA_ECOSYSTEM"))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from core.network_intelligence.evidence_service import UnifiedEvidenceService
from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph
from core.network_intelligence.failure_simulator import FailureSimulator
from core.network_intelligence.impact_analyzer import ImpactAnalyzer
from core.routing.unified_route_parser import NormalizedRoute

def get_db_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def get_table_counts(conn: sqlite3.Connection) -> dict:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]
    counts = {}
    for t in tables:
        cur.execute(f"SELECT count(*) FROM {t}")
        counts[t] = cur.fetchone()[0]
    return counts

def run_phase5_simulation():
    print("=" * 70)
    print("STARTING PHASE 5: NON-DESTRUCTIVE FAILURE SIMULATION AUDIT")
    print("=" * 70)

    db_path = os.path.join(WORKSPACE_ROOT, "database", "topology.db")
    pre_hash = get_db_hash(db_path)
    print(f"Pre-Simulation topology.db SHA-256:  {pre_hash}")

    conn = sqlite3.connect(db_path)
    pre_counts = get_table_counts(conn)
    print(f"Pre-Simulation Total Tables: {len(pre_counts)}, Total Snapshots: {pre_counts.get('topology_snapshots', 0)}")

    # Build multi-device test bundle & graph
    now = time.time()
    svc = UnifiedEvidenceService()
    test_network = {
        "devices": {
            "Core-1": {
                "display_name": "Core-1",
                "management_ip": "10.0.0.1",
                "observed_at": now,
                "interfaces": [
                    {"interface_name": "ether1-wan", "oper_status": "up"},
                    {"interface_name": "ether2-dist1", "oper_status": "up"},
                    {"interface_name": "ether3-dist2", "oper_status": "up"},
                ],
                "routes": [
                    {"dst_prefix": "0.0.0.0/0", "gateway": "203.0.113.1", "interface_name": "ether1-wan", "protocol": "static", "distance": 1, "active": True},
                    {"dst_prefix": "0.0.0.0/0", "gateway": "198.51.100.1", "interface_name": "ether1-wan", "protocol": "static", "distance": 200, "active": False},
                ],
            },
            "Dist-1": {
                "display_name": "Dist-1",
                "management_ip": "10.0.0.2",
                "observed_at": now,
                "interfaces": [
                    {"interface_name": "ether1-core", "oper_status": "up"},
                    {"interface_name": "ether2-sw1", "oper_status": "up"},
                ],
                "routes": [
                    {"dst_prefix": "0.0.0.0/0", "gateway": "10.0.12.1", "interface_name": "ether1-core", "active": True},
                    {"dst_prefix": "10.10.10.0/24", "gateway": "ether2-sw1", "interface_name": "ether2-sw1", "active": True},
                ],
            },
            "Dist-2": {
                "display_name": "Dist-2",
                "management_ip": "10.0.0.3",
                "observed_at": now,
                "interfaces": [
                    {"interface_name": "ether1-core", "oper_status": "up"},
                ],
                "routes": [
                    {"dst_prefix": "0.0.0.0/0", "gateway": "10.0.13.1", "interface_name": "ether1-core", "active": True},
                ],
            },
            "SW-1": {
                "display_name": "SW-1",
                "management_ip": "10.0.0.4",
                "observed_at": now,
                "interfaces": [
                    {"interface_name": "ether1-dist1", "oper_status": "up"},
                ],
                "routes": [
                    {"dst_prefix": "0.0.0.0/0", "gateway": "10.0.14.1", "interface_name": "ether1-dist1", "active": True},
                ],
            },
        },
        "topology_edges": [
            {"source_node_id": "Core-1", "source_interface": "ether2-dist1", "target_node_id": "Dist-1", "target_interface": "ether1-core", "layer": "physical", "relationship_type": "PHYSICAL_ADJACENCY", "confidence": 0.99},
            {"source_node_id": "Core-1", "source_interface": "ether3-dist2", "target_node_id": "Dist-2", "target_interface": "ether1-core", "layer": "physical", "relationship_type": "PHYSICAL_ADJACENCY", "confidence": 0.99},
            {"source_node_id": "Dist-1", "source_interface": "ether2-sw1", "target_node_id": "SW-1", "target_interface": "ether1-dist1", "layer": "physical", "relationship_type": "PHYSICAL_ADJACENCY", "confidence": 0.99},
        ],
    }

    bundle = svc.assemble_evidence_bundle(scope="sim_audit", synthetic_data=test_network, now=now)
    graph = NetworkKnowledgeGraph.from_evidence_bundle(bundle, now=now)

    simulator = FailureSimulator()
    analyzer = ImpactAnalyzer()

    # Simulation A: Upstream Router Down
    print("\n--- Running Scenario A: Upstream Router Down (Core-1) ---")
    res_a = simulator.simulate_failure(bundle, graph, failure_type="UPSTREAM_ROUTER_DOWN", entity_id="Core-1")
    print(f" -> Assumptions: {res_a.assumptions[0]}")
    print(f" -> Isolated Devices: {res_a.potentially_isolated_devices}")
    print(f" -> Redundancy Findings: {res_a.redundancy_findings}")
    assert res_a.is_simulation is True

    # Simulation B: Link Failure (Core-1 <-> Dist-1)
    print("\n--- Running Scenario B: Link Failure (Core-1 to Dist-1) ---")
    res_b = simulator.simulate_failure(bundle, graph, failure_type="TRUNK_LOSS", entity_id="Core-1:ether2-dist1")
    print(f" -> Confidence: {res_b.confidence_label}")
    assert res_b.is_simulation is True

    # Simulation C: WAN Route Loss
    print("\n--- Running Scenario C: WAN Route Loss on Core-1 ---")
    res_c = simulator.simulate_failure(bundle, graph, failure_type="WAN_ROUTE_LOSS", entity_id="Core-1")
    print(f" -> Alternate Paths: {len(res_c.alternate_paths_available)}")
    assert res_c.is_simulation is True

    # Simulation D: Change Impact Analysis
    print("\n--- Running Scenario D: Impact Analysis for Device Decommission ---")
    imp_d = analyzer.analyze_impact(bundle, graph, target_entity_id="Dist-1")
    print(f" -> Scope: {imp_d.impact_scope_type}, Redundancy: {imp_d.redundancy_status}, Direct Dependents: {len(imp_d.direct_dependents)}")

    # Post-Simulation Integrity Verification
    print("\n" + "=" * 70)
    print("POST-SIMULATION INTEGRITY VERIFICATION")
    print("=" * 70)
    post_counts = get_table_counts(conn)
    conn.close()

    post_hash = get_db_hash(db_path)
    print(f"Post-Simulation topology.db SHA-256: {post_hash}")

    assert pre_hash == post_hash, "DATABASE MUTATED DURING SIMULATION!"
    assert pre_counts == post_counts, "TABLE ROW COUNTS CHANGED DURING SIMULATION!"
    print(" -> SUCCESS: Zero modifications to topology.db! In-memory isolation confirmed 100%!")

if __name__ == "__main__":
    run_phase5_simulation()
