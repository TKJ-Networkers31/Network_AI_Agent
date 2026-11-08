"""
AIRA_ECOSYSTEM/tests/test_network_intelligence_pipeline.py —
Full Unified Pipeline Integration Test.

Tests the complete flow:
Incident intake → Evidence collection → Deterministic checks → Playbook execution →
Diagnosis review → Desired-state planning → Static validation → Forwarding simulation →
Human approval package.
"""

from unittest.mock import MagicMock, patch
import pytest

from core.network_intelligence.investigator import NetworkInvestigator
from core.network_intelligence.models import (
    ConfidenceLevel,
    IncidentType,
    InvestigationStatus,
    PlanStatus,
    PlaybookStatus,
)
from core.network_intelligence.planner import ConfigurationPlanner
from core.network_intelligence.playbooks import PlaybookEngine
from core.network_intelligence.simulator import StaticSimulator
from core.network_intelligence.store import get_network_intelligence_store
from core.network_intelligence.validator import StaticValidator


def test_unified_network_intelligence_pipeline():
    store = get_network_intelligence_store()
    investigator = NetworkInvestigator()
    playbook_engine = PlaybookEngine()
    planner = ConfigurationPlanner()
    validator = StaticValidator()
    simulator = StaticSimulator()

    # Step 1: Incident Intake & Target Resolution
    target_device = "R1_CORE"

    # Step 2 & 3: Evidence Collection & Deterministic Analysis
    from core.network_intelligence.models import EvidenceItem
    import time
    now_ts = time.time()

    mock_bundle = {
        "target": target_device,
        "ros_major_version": 7,
        "display_name": target_device,
        "evidence_items": [
            EvidenceItem("ev_1", target_device, "routes", "/ip route print", now_ts, "SUCCESS", {"routes": [], "has_default_route": False, "has_active_default_route": False}),
            EvidenceItem("ev_2", target_device, "ip_addresses", "/ip address print", now_ts, "SUCCESS", {"addresses": [{"address": "192.168.10.1/24", "interface": "ether2"}]}),
            EvidenceItem("ev_3", target_device, "interfaces", "/interface print", now_ts, "SUCCESS", {"interfaces": [{"name": "ether1", "running": True}, {"name": "ether2", "running": True}]}),
            EvidenceItem("ev_4", target_device, "nat_rules", "/ip firewall nat print", now_ts, "SUCCESS", {"rules": [], "has_masquerade": False}),
            EvidenceItem("ev_5", target_device, "firewall_filter", "/ip firewall filter print", now_ts, "SUCCESS", {"rules": []}),
        ],
        "contradictions": [],
        "collection_errors": [],
    }

    with patch.object(investigator.collector, "collect_evidence_bundle", return_value=mock_bundle), \
         patch.object(investigator.collector, "resolve_target_device", return_value=(target_device, 7, target_device)):

        incident = investigator.create_and_run_investigation(
            device_identity=target_device,
            incident_type=IncidentType.LAN_NO_INTERNET,
            symptoms=["Client 192.168.10.25 cannot access internet"],
            user_description="Semua PC di VLAN kantor tidak dapat browsing",
            target_ip="192.168.10.25",
        )

        assert incident.incident_id.startswith("inc_")
        assert incident.investigation_status == InvestigationStatus.DIAGNOSIS_READY.value
        assert incident.confidence == ConfidenceLevel.HIGH.value
        assert len(incident.inferred_hypotheses) >= 1

        # Step 4: Playbook Selection & Diagnostic Step Execution
        pb = playbook_engine.get_playbook_for_incident(incident.incident_type)
        assert pb is not None
        assert pb.playbook_id == "PB-LAN-INTERNET"

        pb_run = playbook_engine.start_playbook_run(
            playbook_id=pb.playbook_id,
            incident_id=incident.incident_id,
            device_identity=incident.device_identity,
        )
        assert pb_run.status == PlaybookStatus.RUNNING.value

        # Advance playbook with collector mock
        with patch.object(playbook_engine.collector, "collect_evidence_bundle", return_value=mock_bundle):
            advanced_run = playbook_engine.advance_playbook(pb_run.run_id, action="step")
            assert advanced_run.current_step_id is not None or advanced_run.status in (PlaybookStatus.RUNNING.value, PlaybookStatus.COMPLETED.value)

        # Step 5: Diagnosis Review
        # Findings show missing default route and NAT
        assert any("rute" in f.lower() or "default" in f.lower() for f in incident.observed_facts + [h["explanation"] for h in incident.inferred_hypotheses])

        # Step 6 & 7: Desired-State Formulation & Plan Generation
        with patch.object(planner.registry, "resolve_device") as mock_resolve:
            mock_dev = MagicMock(inventory_name=target_device, ros_major_version=7, os_version="7.14.3")
            mock_resolve.return_value = mock_dev

            plan = planner.generate_plan(
                target_device=target_device,
                change_type="ADD_STATIC_ROUTE",
                parameters={
                    "dst_address": "0.0.0.0/0",
                    "gateway": "192.168.1.1",
                    "distance": 1,
                },
                incident_id=incident.incident_id,
            )
            assert plan.plan_id.startswith("plan_")
            assert plan.incident_id == incident.incident_id
            assert len(plan.proposed_changes) == 1
            assert "0.0.0.0/0" in plan.proposed_changes[0]["command"]

        # Step 8: Static Validation
        with patch.object(validator.collector, "collect_evidence_bundle", return_value=mock_bundle), \
             patch.object(validator.registry, "resolve_device", return_value=mock_dev):

            val_plan = validator.validate_plan(plan)
            # Default route modification flags management warning
            assert val_plan.management_connectivity_risk is True
            assert val_plan.plan_status == PlanStatus.VALID_WITH_WARNINGS.value

        # Step 9: Static Forwarding Simulation
        with patch.object(simulator.collector, "collect_evidence_bundle", return_value=mock_bundle):
            sim_res = simulator.simulate_plan(val_plan, test_destinations=["8.8.8.8"])
            assert sim_res.simulation_status in ("PASS", "SUCCESS")
            assert len(sim_res.unmodeled_behavior) >= 4

        # Step 10: Human Review Package
        # Stored plan has diff, validation, and simulation ready for operator review
        store.save_plan(val_plan)
        saved_plan = store.get_plan(val_plan.plan_id)
        assert saved_plan is not None
        assert saved_plan.configuration_diff != ""
        assert saved_plan.simulation_results is not None
        assert saved_plan.approval_requirements != []
        assert saved_plan.plan_status in (PlanStatus.VALID_WITH_WARNINGS.value, PlanStatus.READY_FOR_REVIEW.value)
