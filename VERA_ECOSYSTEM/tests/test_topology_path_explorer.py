"""
Unit tests for Topology Path Explorer & Change Impact Analysis in core/topology_engine.py
"""

from unittest.mock import MagicMock, patch
import pytest

from core.topology_engine import TopologyEngine


@pytest.fixture
def mock_engine(tmp_path):
    eng = TopologyEngine(db_path=tmp_path / "test_topo.db")
    return eng


def test_find_path_linear_graph(mock_engine):
    # Mock get_topology with A -> B -> C
    mock_topo = {
        "nodes": [
            {"id": "node_a", "name": "Core-R1", "status": "online", "latency_ms": 1.2, "device_type": "router"},
            {"id": "node_b", "name": "Dist-SW1", "status": "online", "latency_ms": 2.5, "device_type": "switch"},
            {"id": "node_c", "name": "Access-AP1", "status": "online", "latency_ms": 3.8, "device_type": "ap"},
        ],
        "links": [
            {
                "id": "link_1",
                "source": "node_a",
                "target": "node_b",
                "link_type": "physical",
                "verification_status": "confirmed",
                "local_interface_id": "ether1",
                "remote_interface_id": "sfp1",
                "bandwidth_bps": 1000000000,
            },
            {
                "id": "link_2",
                "source": "node_b",
                "target": "node_c",
                "link_type": "physical",
                "verification_status": "observed",
                "local_interface_id": "ether5",
                "remote_interface_id": "ether1",
                "bandwidth_bps": 1000000000,
            },
        ],
    }

    with patch.object(mock_engine, "get_topology", return_value=mock_topo):
        res = mock_engine.find_path("Core-R1", "Access-AP1")
        assert res["success"] is True
        assert res["path_found"] is True
        assert res["hop_count"] == 2
        assert len(res["nodes"]) == 3
        assert res["path_health"] == "healthy"
        assert len(res["hops"]) == 2
        assert res["hops"][0]["from_node_id"] == "node_a"
        assert res["hops"][0]["to_node_id"] == "node_b"
        assert res["hops"][1]["from_node_id"] == "node_b"
        assert res["hops"][1]["to_node_id"] == "node_c"


def test_find_path_broken_or_degraded(mock_engine):
    mock_topo = {
        "nodes": [
            {"id": "node_a", "name": "R1", "status": "online", "latency_ms": 1.0, "device_type": "router"},
            {"id": "node_b", "name": "R2", "status": "offline", "latency_ms": 0.0, "device_type": "router"},
        ],
        "links": [
            {
                "id": "link_1",
                "source": "node_a",
                "target": "node_b",
                "link_type": "routed",
                "verification_status": "stale",
                "local_interface_id": "ether2",
                "remote_interface_id": "ether1",
            },
        ],
    }

    with patch.object(mock_engine, "get_topology", return_value=mock_topo):
        res = mock_engine.find_path("R1", "R2")
        assert res["success"] is True
        assert res["path_found"] is True
        assert res["path_health"] == "broken"
        assert len(res["bottlenecks"]) >= 1


def test_analyze_change_impact_leaf_vs_core(mock_engine):
    mock_topo = {
        "nodes": [
            {"id": "core_1", "name": "Core-Gateway", "device_type": "router", "ownership_status": "owned", "status": "online"},
            {"id": "sw_1", "name": "Switch-Floor1", "device_type": "switch", "ownership_status": "owned", "status": "online"},
            {"id": "ap_1", "name": "AP-Hall", "device_type": "ap", "ownership_status": "owned", "status": "online"},
        ],
        "links": [
            {"id": "l1", "source": "core_1", "target": "sw_1", "local_interface_id": "sfp-sfpplus1"},
            {"id": "l2", "source": "sw_1", "target": "ap_1", "local_interface_id": "ether2"},
        ],
    }

    with patch.object(mock_engine, "get_topology", return_value=mock_topo):
        # 1. Simulating Leaf AP failure: Low severity, 0 isolated downstream devices
        leaf_impact = mock_engine.analyze_change_impact("AP-Hall")
        assert leaf_impact["success"] is True
        assert leaf_impact["severity"] in ("LOW", "MEDIUM")
        assert leaf_impact["isolated_nodes_count"] == 0

        # 2. Simulating Switch-Floor1 failure: High severity, AP-Hall becomes isolated!
        sw_impact = mock_engine.analyze_change_impact("Switch-Floor1")
        assert sw_impact["success"] is True
        assert sw_impact["severity"] == "HIGH"
        assert sw_impact["isolated_nodes_count"] == 1
        assert sw_impact["isolated_nodes"][0]["name"] == "AP-Hall"

        # 3. Simulating Core Gateway failure: Critical severity
        core_impact = mock_engine.analyze_change_impact("Core-Gateway")
        assert core_impact["success"] is True
        assert core_impact["severity"] == "CRITICAL"
        assert core_impact["is_core_gateway"] is True
