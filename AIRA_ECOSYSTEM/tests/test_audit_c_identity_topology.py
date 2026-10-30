"""
tests/test_audit_c_identity_topology.py — Deterministic Fixtures & Tests for Audit C (Identity & Topology).
"""

from unittest.mock import MagicMock, patch
import pytest

from core.canonical_network import CanonicalDevice, CanonicalNetworkRegistry
from core.topology_engine import TopologyEngine


def test_audit_c_conflicting_identities_never_merged():
    """
    Test condition: Two devices share an IP (e.g. IP conflict or fast DHCP lease reuse),
    but possess distinct, incompatible RouterOS identities.
    Expected: Conservative resolution does NOT collapse them into one device.
    """
    reg = CanonicalNetworkRegistry()
    existing_devs = {
        "dev_core1": CanonicalDevice(
            device_id="dev_core1",
            inventory_name="Core-1",
            observed_identity="MikroTik-HQ",
            management_ip="192.168.1.1",
            primary_mac="00:11:22:33:44:55",
        )
    }

    # Candidate node claims same IP but distinct identity and MAC
    candidate_node = {
        "id": "topo_new_dev",
        "name": "Branch-Router",
        "identity": "Branch-Office-RB",
        "ip": "192.168.1.1",
        "mac": "66:77:88:99:AA:BB",
    }

    matched = reg._match_topology_node(candidate_node, existing_devs)
    # MUST NOT match because identities and MACs conflict!
    assert matched is None


def test_audit_c_path_certainty_and_assumptions():
    """
    Test condition:
    1. Fully confirmed graph -> path_certainty == 'confirmed'
    2. Incomplete or stale link graph -> path_certainty == 'inferred_incomplete'
    """
    engine = TopologyEngine()

    # 1. Graph with all confirmed links
    confirmed_topo = {
        "nodes": [
            {"id": "n1", "name": "Core-R1", "status": "online"},
            {"id": "n2", "name": "Dist-SW1", "status": "online"},
        ],
        "links": [
            {"id": "l1", "source": "n1", "target": "n2", "verification_status": "confirmed", "link_type": "physical"},
        ],
    }
    with patch.object(engine, "get_topology", return_value=confirmed_topo):
        p1 = engine.find_path("Core-R1", "Dist-SW1")
        assert p1["success"] is True
        assert p1["path_certainty"] == "confirmed"
        assert len(p1["assumptions"]) >= 2

    # 2. Graph with stale or inferred links
    stale_topo = {
        "nodes": [
            {"id": "n1", "name": "Core-R1", "status": "online"},
            {"id": "n2", "name": "Dist-SW1", "status": "online"},
        ],
        "links": [
            {"id": "l1", "source": "n1", "target": "n2", "verification_status": "stale", "link_type": "inferred"},
        ],
    }
    with patch.object(engine, "get_topology", return_value=stale_topo):
        p2 = engine.find_path("Core-R1", "Dist-SW1")
        assert p2["success"] is True
        assert p2["path_certainty"] == "inferred_incomplete"


def test_audit_c_change_impact_assumptions_and_disclaimer():
    """
    Test condition: Run analyze_change_impact and verify assumptions and disclaimers are explicitly present.
    """
    engine = TopologyEngine()
    mock_topo = {
        "nodes": [
            {"id": "core_1", "name": "Core-Gateway", "device_type": "router", "ownership_status": "owned", "status": "online"},
            {"id": "sw_1", "name": "SW-Branch", "device_type": "switch", "ownership_status": "owned", "status": "online"},
        ],
        "links": [
            {"id": "l1", "source": "core_1", "target": "sw_1"},
        ],
    }
    with patch.object(engine, "get_topology", return_value=mock_topo):
        impact = engine.analyze_change_impact("Core-Gateway")
        assert impact["success"] is True
        assert "simulation_assumptions" in impact
        assert "disclaimer" in impact
        assert "bukan jaminan mutlak" in impact["disclaimer"].lower()
