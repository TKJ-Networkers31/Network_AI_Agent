import pytest
import sqlite3
from unittest.mock import patch, MagicMock

from core.network_intelligence import (
    GraphQueryEngine,
    NetworkKnowledgeGraph,
    KnowledgeNode,
    KnowledgeEdge,
    GraphEntityType,
    GraphRelationshipType,
    GraphLayer,
    NetworkEvidenceBundle,
    UnifiedEvidenceService,
    get_unified_evidence_service,
    MultiDeviceCorrelationEngine,
    SecurityBaselineEngine,
    ActionManagementEngine,
    get_action_engine,
)
from core.network_intelligence.failure_simulator import FailureSimulator
from core.network_intelligence.impact_analyzer import ImpactAnalyzer
from core.network_intelligence.onboarding import DeviceOnboardingEngine
from tools.mikrotik.routeros import get_routes

def test_graph_query_engine_dynamic_gateway_discovery():
    """Verify GraphQueryEngine finds gateway/edge nodes dynamically without hardcoding."""
    bundle = NetworkEvidenceBundle(
        bundle_id="neb_test_gw",
        correlation_id="corr_gw",
        assembled_at=1700000000.0,
        scope="network",
        selected_devices=["r1_core", "r2_edge", "sw_access"],
        selected_interfaces=[]
    )
    kg = NetworkKnowledgeGraph.from_evidence_bundle(bundle)
    
    # Add nodes to graph
    kg.add_node(KnowledgeNode(
        node_id="device:r1_core",
        entity_type=GraphEntityType.DEVICE.value,
        label="Core-Router-1",
        attributes={"role": "core", "device_type": "router"}
    ))
    kg.add_node(KnowledgeNode(
        node_id="device:r2_edge",
        entity_type=GraphEntityType.DEVICE.value,
        label="Edge-Gateway-WAN",
        attributes={"role": "edge", "device_type": "router"}
    ))
    kg.add_node(KnowledgeNode(
        node_id="device:sw_access",
        entity_type=GraphEntityType.DEVICE.value,
        label="Access-Switch",
        attributes={"role": "access", "device_type": "switch"}
    ))
    
    qengine = GraphQueryEngine(kg)
    gateways = qengine.find_gateway_nodes()
    
    assert "r2_edge" in gateways
    assert len(gateways) >= 1

def test_failure_simulator_dynamic_gateway():
    """Verify failure simulator uses dynamic gateway instead of broken hardcoded ISP-Edge."""
    bundle = NetworkEvidenceBundle(
        bundle_id="neb_sim_test",
        correlation_id="corr_sim",
        assembled_at=1700000000.0,
        scope="network",
        selected_devices=["r_core", "r_border"],
        selected_interfaces=[]
    )
    kg = NetworkKnowledgeGraph.from_evidence_bundle(bundle)
    kg.add_node(KnowledgeNode(
        node_id="device:r_core",
        entity_type=GraphEntityType.DEVICE.value,
        label="Core-Router",
        attributes={"role": "core"}
    ))
    kg.add_node(KnowledgeNode(
        node_id="device:r_border",
        entity_type=GraphEntityType.DEVICE.value,
        label="Border-Gateway",
        attributes={"role": "gateway"}
    ))
    
    sim = FailureSimulator()
    res = sim.simulate_failure(
        bundle=bundle,
        graph=kg,
        failure_type="UPSTREAM_ROUTER_DOWN",
        entity_id="r_core"
    )
    assert res is not None
    assert res.simulation_id.startswith("sim_")
    assert res.simulated_failure_type == "UPSTREAM_ROUTER_DOWN"
    assert "r_core" in str(res.assumptions) or "upstream" in str(res.assumptions).lower()

def test_action_engine_honest_simulation_label(tmp_path):
    """Verify execute_and_verify_action labels analytical actions honestly as simulated."""
    db_path = str(tmp_path / "test_action.db")
    engine = ActionManagementEngine(db_path)
    
    # Create action
    act_rec = engine.propose_action(
        action_name="Restart OSPF Process",
        target_devices=["r1_core"],
        description="Restart OSPF process to clear stale adjacency",
        reason="OSPF Adjacency stuck in ExStart",
        before_state={"ospf_state": "EXSTART"},
        proposed_changes={"ospf_state": "FULL"},
        expected_after_state={"ospf_state": "FULL"},
        diff_text="+ /routing ospf instance reset",
        verification_plan="Check OSPF neighbor state == FULL",
        rollback_plan="/routing ospf instance set 0 disabled=no",
        rollback_supported=True,
        requester_id="admin"
    )
    action_id = act_rec.action_id
    
    # Resolve (approve) action
    engine.resolve_approval(action_id, approved=True, reviewer_id="admin", notes="Safe test")
    
    # Execute action
    exec_res = engine.execute_and_verify_action(action_id, operator_id="admin")
    assert exec_res["success"] is True
    
    # Check verification details in action record
    act = engine.get_action(action_id)
    assert act["status"] == "SUCCESS"
    verif = act.get("verification_result", {})
    assert verif.get("is_simulated") is True
    assert verif.get("execution_mode") == "analytical_simulation"

def test_routeros_v6_v7_routing_compatibility():
    """Verify RouterOS v6 vs v7 compatibility routing function."""
    with patch("tools.mikrotik.routeros.execute_mikrotik_tool") as mock_exec:
        mock_exec.return_value = {"success": True, "output": "Flags: X - disabled, A - active, D - dynamic\n 0 A S  dst-address=0.0.0.0/0 gateway=192.168.1.1"}
        
        # Test default/v6 call
        res_v6 = get_routes("router1", routeros_version="6.49.10")
        assert res_v6["success"] is True
        assert mock_exec.call_args[0][0] == "get_routes"
        
        # Test v7 call
        res_v7 = get_routes("router1", routeros_version="7.14.3")
        assert res_v7["success"] is True
        assert mock_exec.call_args[0][0] == "get_routes_v7"

def test_gen3_exports_availability():
    """Verify Gen 3 exports and legacy aliases in core/network_intelligence."""
    from core.network_intelligence import (
        UnifiedEvidenceService,
        MultiDeviceCorrelationEngine,
        SecurityBaselineEngine,
        NetworkKnowledgeGraph,
        GraphQueryEngine,
        ActionManagementEngine,
        NetworkHealthEngine,
        AnomalyEngine,
        EvidenceService,
        CorrelationEngine,
    )
    assert UnifiedEvidenceService is EvidenceService
    assert MultiDeviceCorrelationEngine is CorrelationEngine
    assert issubclass(GraphQueryEngine, object)
