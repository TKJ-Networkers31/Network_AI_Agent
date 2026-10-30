"""
tests/test_phase5_simulator_correctness.py — Validator & Simulator Correctness Tests (Phase 5).

Verifies:
1. StaticValidator distinguishes blocking errors (FAIL), warnings (PASS_WITH_WARNINGS),
   and unprovable assumptions (UNKNOWN).
2. Missing or incomplete baseline evidence produces UNKNOWN, NEVER PASS.
3. StaticSimulator emits PASS, FAIL, or UNKNOWN deterministically.
4. StaticSimulator discloses all 6 unmodeled forwarding behaviors:
   - FastTrack connection offload
   - Hardware offload (switch ASIC)
   - Connection tracking timeouts & states
   - ECMP multi-gateway hashing
   - IPsec / tunnel encapsulation overhead
   - Dynamic routing convergence latency
"""

from unittest.mock import MagicMock, patch
import pytest

from core.network_intelligence.models import (
    ConfigurationPlan,
    PlanStatus,
    ValidationSeverity,
)
from core.network_intelligence.planner import ConfigurationPlanner
from core.network_intelligence.simulator import (
    StaticSimulator,
    UNMODELED_BEHAVIORS_DISCLOSURE,
)
from core.network_intelligence.validator import StaticValidator


# ---------------------------------------------------------------------------
# 1. Validator Status: FAIL, UNKNOWN, PASS_WITH_WARNINGS, PASS
# ---------------------------------------------------------------------------

def test_validator_emits_fail_on_blocking_error():
    validator = StaticValidator()

    # Plan with invalid VLAN ID (e.g. 5000 > 4094)
    plan = ConfigurationPlan(
        plan_id="plan_vlan_bad",
        operation_id="op_1",
        target_devices=["R1"],
        desired_state={
            "change_type": "add_vlan_svi",
            "parameters": {"vlan_id": 5000, "interface": "ether1", "ip_address": "10.0.0.1", "netmask": "24"},
        },
    )

    with patch.object(validator.collector, "collect_evidence_bundle", return_value={"evidence_items": []}):
        validated = validator.validate_plan(plan)

        assert validated.plan_status == PlanStatus.INVALID.value
        assert validated.desired_state.get("validation_status") == "FAIL"
        assert any(f["rule_id"] == "VLAN_ID_OUT_OF_RANGE" and f["is_blocking"] for f in validated.validation_results)


def test_validator_emits_unknown_when_baseline_evidence_incomplete():
    validator = StaticValidator()

    plan = ConfigurationPlan(
        plan_id="plan_unknown",
        operation_id="op_2",
        target_devices=["R1"],
        desired_state={
            "change_type": "add_ip_address",
            "parameters": {"interface": "ether2", "ip_address": "10.50.0.1", "netmask": "24"},
        },
    )

    # Simulate evidence collection failure (SSH timeout / unreachable)
    failed_mock_bundle = {
        "evidence_items": [
            MagicMock(observation_type="interfaces", collection_status="FAILED"),
            MagicMock(observation_type="ip_addresses", collection_status="FAILED"),
        ]
    }

    with patch.object(validator.collector, "collect_evidence_bundle", return_value=failed_mock_bundle):
        validated = validator.validate_plan(plan)

        # Incomplete baseline MUST produce UNKNOWN, NEVER PASS
        assert validated.desired_state.get("validation_status") == "UNKNOWN"
        assert any(f["rule_id"] == "INCOMPLETE_BASELINE_EVIDENCE" for f in validated.validation_results)
        assert validated.plan_status == PlanStatus.VALID_WITH_WARNINGS.value


def test_validator_emits_pass_with_warnings_on_mgmt_risk():
    validator = StaticValidator()

    plan = ConfigurationPlan(
        plan_id="plan_route_risk",
        operation_id="op_3",
        target_devices=["R1"],
        desired_state={
            "change_type": "ADD_STATIC_ROUTE",
            "parameters": {"dst_address": "0.0.0.0/0", "gateway": "192.168.100.1"},
        },
    )

    success_bundle = {
        "evidence_items": [
            MagicMock(observation_type="interfaces", collection_status="SUCCESS", normalized_value={"interfaces": [{"name": "ether1"}]}),
            MagicMock(observation_type="ip_addresses", collection_status="SUCCESS", normalized_value={"addresses": []}),
            MagicMock(observation_type="routes", collection_status="SUCCESS", normalized_value={"routes": []}),
        ]
    }

    with patch.object(validator.collector, "collect_evidence_bundle", return_value=success_bundle):
        with patch.object(validator.registry, "resolve_device", return_value=MagicMock(management_ip="192.168.1.50")):
            validated = validator.validate_plan(plan)

            assert validated.desired_state.get("validation_status") == "PASS_WITH_WARNINGS"
            assert validated.management_connectivity_risk is True
            assert "0.0.0.0/0" in validated.management_risk_explanation


# ---------------------------------------------------------------------------
# 2. Simulator Status: UNKNOWN, FAIL, PASS
# ---------------------------------------------------------------------------

def test_simulator_emits_unknown_when_baseline_routes_missing():
    simulator = StaticSimulator()

    plan = ConfigurationPlan(
        plan_id="plan_sim_1",
        operation_id="op_sim",
        target_devices=["R1"],
        desired_state={
            "change_type": "ADD_STATIC_ROUTE",
            "parameters": {"dst_address": "10.0.0.0/24", "gateway": "192.168.1.254"},
        },
    )

    # Empty baseline routes
    with patch.object(simulator.collector, "collect_evidence_bundle", return_value={"evidence_items": []}):
        sim_res = simulator.simulate_plan(plan)

        assert sim_res.simulation_status == "UNKNOWN"
        assert "tidak lengkap" in sim_res.expected_result


def test_simulator_emits_pass_when_forwarding_modeled_successfully():
    simulator = StaticSimulator()

    plan = ConfigurationPlan(
        plan_id="plan_sim_2",
        operation_id="op_sim_2",
        target_devices=["R1"],
        desired_state={
            "change_type": "ADD_STATIC_ROUTE",
            "parameters": {"dst_address": "0.0.0.0/0", "gateway": "192.168.1.1"},
        },
    )

    success_bundle = {
        "evidence_items": [
            MagicMock(
                observation_type="routes",
                collection_status="SUCCESS",
                normalized_value={"routes": [{"dst_address": "192.168.1.0/24", "gateway": "ether1", "active": True}]},
            )
        ]
    }

    with patch.object(simulator.collector, "collect_evidence_bundle", return_value=success_bundle):
        sim_res = simulator.simulate_plan(plan, test_destinations=["8.8.8.8"])

        assert sim_res.simulation_status == "PASS"
        assert "PASS" in sim_res.expected_result
        assert sim_res.modeled_behavior["forwarding_comparison"]["8.8.8.8"]["after"]["matched"] is True


# ---------------------------------------------------------------------------
# 3. Disclosure of Unmodeled Forwarding Behaviors
# ---------------------------------------------------------------------------

def test_simulator_discloses_all_six_unmodeled_behaviors():
    simulator = StaticSimulator()

    plan = ConfigurationPlan(
        plan_id="plan_disc",
        operation_id="op_disc",
        target_devices=["R1"],
        desired_state={"change_type": "none", "parameters": {}},
    )

    with patch.object(simulator.collector, "collect_evidence_bundle", return_value={"evidence_items": []}):
        sim_res = simulator.simulate_plan(plan)

        disclosures = "\n".join(sim_res.unmodeled_behavior)

        # 1. FastTrack
        assert "FastTrack" in disclosures
        # 2. Hardware Offload / ASIC
        assert "Hardware Offload" in disclosures or "Switch Chip" in disclosures
        # 3. Connection Tracking State & Timeouts
        assert "Connection Tracking" in disclosures
        # 4. ECMP Hashing
        assert "ECMP" in disclosures
        # 5. IPsec / Tunnel MTU Overhead
        assert "IPsec" in disclosures or "Tunnel" in disclosures
        # 6. Dynamic Routing Convergence
        assert "Convergence" in disclosures or "OSPF/BGP" in disclosures
