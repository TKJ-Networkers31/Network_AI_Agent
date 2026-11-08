"""
AIRA_ECOSYSTEM/tests/test_network_intelligence_planning.py —
Tests for Configuration Planning, Static Validation, and Forwarding Simulation.
"""

from unittest.mock import MagicMock, patch
import pytest

from core.network_intelligence.models import (
    PlanStatus,
    ValidationSeverity,
)
from core.network_intelligence.planner import ConfigurationPlanner
from core.network_intelligence.simulator import StaticSimulator
from core.network_intelligence.validator import StaticValidator


def test_missing_mandatory_desired_state_returns_needs_input():
    planner = ConfigurationPlanner()

    # ADD_VLAN without vlan_id
    plan = planner.generate_plan(
        target_device="R1",
        change_type="ADD_VLAN",
        parameters={"bridge": "bridge1"},
    )
    assert plan.plan_status == PlanStatus.NEEDS_INPUT.value
    assert len(plan.required_operator_inputs) > 0
    assert any("vlan_id" in inp for inp in plan.required_operator_inputs)


def test_v6_vs_v7_syntax_generation():
    planner = ConfigurationPlanner()

    # Test BGP generation on v6 vs v7
    with patch.object(planner.registry, "resolve_device") as mock_resolve:
        # Mock v6 device
        mock_dev_v6 = MagicMock(inventory_name="R_V6", ros_major_version=6, os_version="6.49.10")
        mock_resolve.return_value = mock_dev_v6

        plan_v6 = planner.generate_plan(
            target_device="R_V6",
            change_type="CONFIGURE_BGP",
            parameters={"remote_as": 65001, "remote_ip": "10.255.0.1"},
        )
        cmd_v6 = plan_v6.proposed_changes[0]["command"]
        assert "/routing bgp peer add" in cmd_v6
        assert "remote-as=65001" in cmd_v6

        # Mock v7 device
        mock_dev_v7 = MagicMock(inventory_name="R_V7", ros_major_version=7, os_version="7.14.3")
        mock_resolve.return_value = mock_dev_v7

        plan_v7 = planner.generate_plan(
            target_device="R_V7",
            change_type="CONFIGURE_BGP",
            parameters={"remote_as": 65002, "remote_ip": "10.255.0.2"},
        )
        cmd_v7 = plan_v7.proposed_changes[0]["command"]
        assert "/routing bgp connection add" in cmd_v7
        assert "remote.as=65002" in cmd_v7


def test_static_validation_catches_subnet_overlap_and_invalid_vlan():
    planner = ConfigurationPlanner()
    validator = StaticValidator()

    # Mock router having existing subnet 192.168.10.0/24 and interface ether1
    mock_bundle = {
        "evidence_items": [
            MagicMock(
                observation_type="ip_addresses",
                collection_status="SUCCESS",
                normalized_value={"addresses": [{"address": "192.168.10.1/24", "interface": "ether1"}]},
            ),
            MagicMock(
                observation_type="interfaces",
                collection_status="SUCCESS",
                normalized_value={"interfaces": [{"name": "ether1", "running": True}]},
            ),
            MagicMock(observation_type="routes", collection_status="SUCCESS", normalized_value={"routes": []}),
            MagicMock(observation_type="bridge", collection_status="SUCCESS", normalized_value={}),
        ]
    }

    with patch.object(validator.collector, "collect_evidence_bundle", return_value=mock_bundle):
        # 1. Test invalid VLAN ID (> 4094)
        plan_bad_vlan = planner.generate_plan(
            target_device="R1",
            change_type="ADD_VLAN",
            parameters={"vlan_id": 5000, "interface": "ether1"},
        )
        val_vlan = validator.validate_plan(plan_bad_vlan)
        assert val_vlan.plan_status == PlanStatus.INVALID.value
        assert any(f["rule_id"] == "VLAN_ID_OUT_OF_RANGE" for f in val_vlan.validation_results)

        # 2. Test Subnet Overlap (192.168.10.0/25 overlaps 192.168.10.0/24)
        plan_overlap = planner.generate_plan(
            target_device="R1",
            change_type="ADD_VLAN",
            parameters={"vlan_id": 100, "interface": "ether1", "subnet": "192.168.10.64/26"},
        )
        val_overlap = validator.validate_plan(plan_overlap)
        assert val_overlap.plan_status == PlanStatus.INVALID.value
        assert any(f["rule_id"] == "SUBNET_OVERLAP" for f in val_overlap.validation_results)

        # 3. Test Unknown Interface
        plan_unknown_if = planner.generate_plan(
            target_device="R1",
            change_type="ADD_VLAN",
            parameters={"vlan_id": 200, "interface": "sfp-sfpplus99"},
        )
        val_unknown_if = validator.validate_plan(plan_unknown_if)
        assert val_unknown_if.plan_status == PlanStatus.INVALID.value
        assert any(f["rule_id"] == "INTERFACE_NOT_FOUND" for f in val_unknown_if.validation_results)


def test_static_forwarding_simulation_and_unmodeled_disclosures():
    planner = ConfigurationPlanner()
    simulator = StaticSimulator()

    mock_routes = [
        {"dst_address": "0.0.0.0/0", "gateway": "192.168.1.1", "distance": 1, "active": True},
        {"dst_address": "10.0.0.0/8", "gateway": "10.255.0.1", "distance": 1, "active": True},
    ]

    mock_bundle = {
        "evidence_items": [
            MagicMock(
                observation_type="routes",
                collection_status="SUCCESS",
                normalized_value={"routes": mock_routes},
            ),
            MagicMock(observation_type="ip_addresses", collection_status="SUCCESS", normalized_value={}),
            MagicMock(observation_type="interfaces", collection_status="SUCCESS", normalized_value={}),
        ]
    }

    # Propose adding static route for 10.10.10.0/24 via gateway 10.255.0.50
    plan = planner.generate_plan(
        target_device="R1",
        change_type="ADD_STATIC_ROUTE",
        parameters={"dst_address": "10.10.10.0/24", "gateway": "10.255.0.50", "distance": 1},
    )

    with patch.object(simulator.collector, "collect_evidence_bundle", return_value=mock_bundle):
        sim = simulator.simulate_plan(plan, test_destinations=["10.10.10.5", "8.8.8.8"])

        assert sim.simulation_status in ("PASS", "SUCCESS")
        assert len(sim.unmodeled_behavior) >= 4
        assert any("FastTrack" in u for u in sim.unmodeled_behavior)
        assert any("Hardware Offload" in u for u in sim.unmodeled_behavior)

        # Check LPM forward before vs after for 10.10.10.5:
        # Before: matches 10.0.0.0/8 via 10.255.0.1
        # After: matches 10.10.10.0/24 via 10.255.0.50
        comp = sim.modeled_behavior["forwarding_comparison"]["10.10.10.5"]
        assert comp["before"]["gateway"] == "10.255.0.1"
        assert comp["after"]["gateway"] == "10.255.0.50"
        assert comp["route_changed"] is True
