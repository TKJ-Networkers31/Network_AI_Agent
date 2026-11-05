"""
AIRA OS — Networking VII End-to-End Acceptance Test Suite (WP 7.11).

Validates the full integrated lifecycle of Proactive Network Operations Intelligence:
1. Multi-window predictive analysis projects saturation breach.
2. Proactive incident is automatically raised with preventative remediation.
3. Notification hub evaluates deduplication and quiet hours policy.
4. Pre-change simulation evaluates in-memory blast radius with zero device mutation.
5. Operational report deterministic aggregation verifies end-to-end data integrity.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
import pytest

from core.network_intelligence.intelligence_models import (
    GraphEntityType,
    GraphRelationshipType,
    KnowledgeEdge,
    KnowledgeNode,
    NetworkEvidenceBundle,
)
from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph
from core.operations.calendar.local_provider import LocalCalendarProvider
from core.operations.calendar.manager import CalendarManager
from core.operations.change_impact_engine import ChangeImpactEngine
from core.operations.incident_engine import ProactiveIncidentEngine
from core.operations.models import (
    ChangeScenarioRequest,
    IncidentSeverity,
    IncidentState,
    NotificationDeliveryStatus,
    RiskLevel,
)
from core.operations.notification_hub import NotificationHub
from core.operations.predictive_engine import PredictiveOperationsEngine
from core.operations.reporting_engine import OperationalReportingEngine
from core.operations.scheduler import OperationalSchedulerEngine
from core.operations.service_intelligence import ServiceIntelligenceEngine


@pytest.fixture
def test_db_path(tmp_path: Path) -> Path:
    return tmp_path / "e2e_operations.db"


def test_networking_vii_full_e2e_lifecycle(test_db_path: Path) -> None:
    """Executes the complete end-to-end proactive operations intelligence workflow."""
    # 1. Initialize all operations engines on shared test database
    pred_engine = PredictiveOperationsEngine()
    change_engine = ChangeImpactEngine()
    svc_engine = ServiceIntelligenceEngine(db_path=test_db_path)
    sched_engine = OperationalSchedulerEngine(db_path=test_db_path)
    cal_manager = CalendarManager(local_provider=LocalCalendarProvider(db_path=test_db_path))
    inc_engine = ProactiveIncidentEngine(db_path=test_db_path)
    notif_hub = NotificationHub(db_path=test_db_path, cooldown_sec=120)
    rep_engine = OperationalReportingEngine(
        predictive_engine=pred_engine,
        service_engine=svc_engine,
        scheduler_engine=sched_engine,
        calendar_manager=cal_manager,
        incident_engine=inc_engine,
    )

    now = time.time()
    now_dt = datetime.now(timezone.utc)

    # 2. Step 1: Predictive Saturation Detection
    # 20 samples climbing rapidly from 50% to 78% (1.5% per hour -> breach in 1.3 hours -> CRITICAL)
    samples = [(now - (19 - i) * 180, 50.0 + (i * 1.5)) for i in range(20)]
    projection = pred_engine.analyze_metric_trend(
        metric_name="rx_utilization_percent",
        entity_type="interface",
        entity_id="sfp-sfpplus1",
        device_id="Core-1",
        raw_samples=samples,
    )

    assert projection.risk_level == RiskLevel.CRITICAL.value
    assert projection.hours_to_warning is not None
    assert projection.hours_to_warning <= 24.0

    # 3. Step 2: Automated Proactive Incident Creation
    incident = inc_engine.create_from_prediction(projection)
    assert incident is not None
    assert incident.severity == IncidentSeverity.CRITICAL.value
    assert incident.state == IncidentState.DETECTED.value
    assert "Core-1" in incident.affected_devices

    # 4. Step 3: Controlled Notification Dispatch
    notif = notif_hub.dispatch_notification(
        category="CAPACITY_BREACH",
        severity=incident.severity,
        title=incident.title,
        message=incident.summary,
        identifier="Core-1:sfp-sfpplus1",
        now_utc=now_dt,
    )
    # Critical alert immediately dispatches (SENT), even if during quiet hours
    assert notif.delivery_status == NotificationDeliveryStatus.SENT.value

    # Second identical alert is suppressed by cooldown
    notif_dupe = notif_hub.dispatch_notification(
        category="CAPACITY_BREACH",
        severity=incident.severity,
        title=incident.title,
        message=incident.summary,
        identifier="Core-1:sfp-sfpplus1",
        now_utc=now_dt + timedelta(seconds=10),
    )
    assert notif_dupe.delivery_status == NotificationDeliveryStatus.SUPPRESSED_COOLDOWN.value

    # 5. Step 4: Pre-Change Impact Simulation (Simulate taking link down for emergency maintenance)
    # Build in-memory graph
    graph = NetworkKnowledgeGraph()
    graph.add_node(KnowledgeNode(
        node_id="device:Core-1",
        entity_type=GraphEntityType.DEVICE.value,
        device_id="Core-1",
        label="Core-1",
        observed_at=now,
    ))
    graph.add_node(KnowledgeNode(
        node_id="device:Dist-1",
        entity_type=GraphEntityType.DEVICE.value,
        device_id="Dist-1",
        label="Dist-1",
        observed_at=now,
    ))
    graph.add_node(KnowledgeNode(
        node_id="interface:Core-1:sfp-sfpplus1",
        entity_type=GraphEntityType.INTERFACE.value,
        device_id="Core-1",
        label="sfp-sfpplus1",
        observed_at=now,
    ))
    graph.add_edge(KnowledgeEdge(
        edge_id="edge_core_iface",
        source_id="interface:Core-1:sfp-sfpplus1",
        target_id="device:Dist-1",
        relationship_type=GraphRelationshipType.PHYSICAL_ADJACENCY.value,
        observed_at=now,
    ))

    sim_req = ChangeScenarioRequest(
        scenario_id="scen_maint_001",
        title="Emergency Splicing - Interface Down",
        change_type="INTERFACE_DOWN",
        target_device="Core-1",
        target_entity="sfp-sfpplus1",
    )

    bundle = NetworkEvidenceBundle(
        bundle_id="bnd_e2e",
        correlation_id="corr_e2e",
        assembled_at=now,
        scope="cluster",
    )

    sim_report = change_engine.simulate_change(sim_req, bundle, graph)
    assert sim_report.is_simulation is True
    assert "Dist-1" in sim_report.directly_impacted_devices
    assert len(sim_report.preflight_checklist) >= 1
    assert len(sim_report.rollback_plan) >= 1

    # 6. Step 5: Incident Lifecycle Transition to RESOLVED
    inc_ack = inc_engine.transition_state(incident.incident_id, IncidentState.ACKNOWLEDGED.value)
    assert inc_ack.state == IncidentState.ACKNOWLEDGED.value

    inc_mit = inc_engine.transition_state(incident.incident_id, IncidentState.MITIGATED.value)
    assert inc_mit.state == IncidentState.MITIGATED.value

    inc_res = inc_engine.transition_state(incident.incident_id, IncidentState.RESOLVED.value)
    assert inc_res.state == IncidentState.RESOLVED.value
    assert inc_res.resolved_at is not None

    # 7. Step 6: Operational Report Generation
    report = rep_engine.generate_report(report_period="DAILY", now_dt=now_dt)
    assert report["period"] == "DAILY"
    assert report["executive_summary"]["preventatively_mitigated_incidents"] >= 1
    assert "AIRA OS" in report["markdown"]
    assert "<html" in report["html"]
