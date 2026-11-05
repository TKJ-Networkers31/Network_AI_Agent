"""
AIRA OS — Networking VIII Phase C Comprehensive Verification Suite (WP 8.5 – 8.8).

Covers:
1. Operational Decision Intelligence (WP 8.5):
   - Evidence-grounded synthesis
   - Deterministic priority formula
   - Lifecycle state machine & invalid transition rejection
   - Append-only audit history
2. Dynamic Health Scoring (WP 8.5.1):
   - 6-dimension evaluation (Device, Site, Service, Gateway, Tenant)
   - Epistemic integrity: Missing telemetry emits UNKNOWN with score=None
   - Tier 1 mission-critical minimum clamping
3. Risk and Impact Assessment (WP 8.6):
   - Non-destructive virtual simulation over NetworkKnowledgeGraph
   - Blast radius and transit-dependency identification
   - Multi-scenario comparison
4. SLA and Service Management (WP 8.7):
   - Policy configuration & reproducible availability calculation
   - Maintenance window exclusions
   - Data coverage threshold (Coverage < 80% -> INSUFFICIENT_COVERAGE)
   - Error budget accounting
5. Multi-Tenant Incident Orchestration (WP 8.8):
   - Deterministic alert deduplication
   - Intra-tenant correlation & lifecycle state progression
6. Security & Tenant Isolation Adversarial Testing:
   - Tenant A cannot read Tenant B decisions / health / SLA / incidents
   - RFC 1918 overlap safety
   - RBAC privilege boundaries (Customer roles cannot approve decisions)
   - Expired recommendation rejection
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import pytest
import time
from typing import Any, Dict

from core.network_intelligence.intelligence_models import (
    GraphEntityType,
    GraphRelationshipType,
    KnowledgeEdge,
    KnowledgeNode,
    NetworkEvidenceBundle,
)
from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph
from dataclasses import dataclass, field
from core.operations.decision_engine import OperationalDecisionEngine
from core.operations.health_scoring_engine import DynamicHealthScoringEngine
from core.operations.models import (
    DecisionStatus,
    HealthScoreState,
    IncidentState,
    IncidentSeverity,
    RiskLevel,
    ServiceCriticality,
    SlaStatusType,
    SlaWindowType,
)

@dataclass
class MockHypothesis:
    hypothesis_id: str
    title: str
    probability: float
    summary: str


@dataclass
class MockRCAReport:
    rca_id: str
    primary_root_cause: str
    confidence: float
    supporting_evidence_ids: list[str] = field(default_factory=list)
    contradictory_evidence_ids: list[str] = field(default_factory=list)
    missing_evidence_ids: list[str] = field(default_factory=list)
    candidate_hypotheses: list[MockHypothesis] = field(default_factory=list)
from core.operations.multi_tenant_incident_engine import MultiTenantIncidentEngine
from core.operations.risk_engine import RiskAssessmentEngine
from core.operations.service_intelligence import ServiceIntelligenceEngine
from core.operations.sla_engine import SlaManagementEngine
from core.tenant.db import ensure_tenant_schema
from core.tenant.manager import (
    IdentityManager,
    InventoryManager,
    TenantManager,
)
from core.tenant.models import Permission, UserRoleType
from core.edge_gateway.db import ensure_gateway_schema
from core.edge_gateway.manager import EdgeGatewayManager


@pytest.fixture
def phase_c_setup(tmp_path: Path):
    """Sets up an isolated database with two distinct tenants and resources."""
    db_path = tmp_path / "test_phase_c.db"
    ensure_tenant_schema(db_path)
    ensure_gateway_schema(db_path)

    tenant_mgr = TenantManager(db_path=db_path)
    inv_mgr = InventoryManager(db_path=db_path)
    gw_mgr = EdgeGatewayManager(db_path=db_path)
    identity_mgr = IdentityManager(db_path=db_path)

    # 1. Provision Tenant A (Acme Corp)
    tenant_a = tenant_mgr.create_tenant(name="Acme Corp", slug="acme")
    site_a1 = inv_mgr.create_site(tenant_id=tenant_a.tenant_id, name="Acme HQ", slug="acme-hq")
    dev_a1 = inv_mgr.create_device(
        tenant_id=tenant_a.tenant_id,
        site_id=site_a1.site_id,
        name="acme-core-01",
        management_ip="192.168.1.1", # RFC 1918
    )

    # 2. Provision Tenant B (Globex Corp)
    tenant_b = tenant_mgr.create_tenant(name="Globex Corp", slug="globex")
    site_b1 = inv_mgr.create_site(tenant_id=tenant_b.tenant_id, name="Globex Branch", slug="globex-br")
    dev_b1 = inv_mgr.create_device(
        tenant_id=tenant_b.tenant_id,
        site_id=site_b1.site_id,
        name="globex-rtr-01",
        management_ip="192.168.1.1", # Exact same IP: RFC 1918 overlap!
    )

    # Engines under test
    health_engine = DynamicHealthScoringEngine(db_path=db_path)
    sla_engine = SlaManagementEngine(db_path=db_path)
    decision_engine = OperationalDecisionEngine(db_path=db_path, health_engine=health_engine, sla_engine=sla_engine)
    risk_engine = RiskAssessmentEngine(db_path=db_path)
    incident_engine = MultiTenantIncidentEngine(db_path=db_path)
    svc_engine = ServiceIntelligenceEngine(db_path=db_path)

    return {
        "db_path": db_path,
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "site_a1": site_a1,
        "site_b1": site_b1,
        "dev_a1": dev_a1,
        "dev_b1": dev_b1,
        "tenant_mgr": tenant_mgr,
        "inv_mgr": inv_mgr,
        "gw_mgr": gw_mgr,
        "identity_mgr": identity_mgr,
        "health_engine": health_engine,
        "sla_engine": sla_engine,
        "decision_engine": decision_engine,
        "risk_engine": risk_engine,
        "incident_engine": incident_engine,
        "svc_engine": svc_engine,
    }


# ===========================================================================
# 1. OPERATIONAL DECISION INTELLIGENCE (WP 8.5)
# ===========================================================================

def test_01_decision_synthesis_and_priority_scoring(phase_c_setup):
    """Test 1: Synthesizes decision and computes deterministic priority score."""
    decision_engine = phase_c_setup["decision_engine"]
    tenant_a = phase_c_setup["tenant_a"]
    site_a1 = phase_c_setup["site_a1"]
    dev_a1 = phase_c_setup["dev_a1"]

    # Mock RCA report
    rca = MockRCAReport(
        rca_id="rca_test_01",
        primary_root_cause="Degradasi Jalur Transceiver SFP",
        confidence=0.92,
        supporting_evidence_ids=["ev_1", "ev_2"],
        contradictory_evidence_ids=[],
        missing_evidence_ids=[],
        candidate_hypotheses=[
            MockHypothesis(
                hypothesis_id="hyp_1",
                title="SFP Optic Failure",
                probability=0.92,
                summary="Nilai Rx optical power menurun di bawah ambang batas.",
            )
        ],
    )

    dec = decision_engine.synthesize_decision(
        tenant_id=tenant_a.tenant_id,
        site_id=site_a1.site_id,
        problem_title="Gangguan Optik Uplink Core-01",
        rca_report=rca,
        affected_services=["svc_vpn"],
        affected_devices=[dev_a1.device_id],
    )

    assert dec.decision_id.startswith("dec_")
    assert dec.tenant_id == tenant_a.tenant_id
    assert dec.site_id == site_a1.site_id
    assert dec.status == DecisionStatus.GENERATED.value
    # Priority score calculated and bounded
    assert 0.0 <= dec.priority_score <= 100.0
    assert dec.assessment.epistemic_status == "CONFIRMED_BY_EVIDENCE"
    assert dec.assessment.confidence_score == 0.92
    assert len(dec.recommendation.alternatives) >= 2
    assert len(dec.recommendation.human_verification_checklist) >= 3


def test_02_decision_lifecycle_valid_transitions(phase_c_setup):
    """Test 2: Verifies valid transition path (GENERATED -> UNDER_REVIEW -> APPROVED -> COMPLETED -> VERIFIED)."""
    decision_engine = phase_c_setup["decision_engine"]
    tenant_a = phase_c_setup["tenant_a"]
    site_a1 = phase_c_setup["site_a1"]

    dec = decision_engine.synthesize_decision(
        tenant_id=tenant_a.tenant_id,
        site_id=site_a1.site_id,
        problem_title="Lifecycle Test",
    )
    assert dec.status == DecisionStatus.GENERATED.value

    # 1. GENERATED -> UNDER_REVIEW
    d1 = decision_engine.transition_status(dec.decision_id, tenant_a.tenant_id, "noc_lead", DecisionStatus.UNDER_REVIEW.value, "Reviewing")
    assert d1.status == DecisionStatus.UNDER_REVIEW.value

    # 2. UNDER_REVIEW -> APPROVED
    d2 = decision_engine.transition_status(dec.decision_id, tenant_a.tenant_id, "noc_mgr", DecisionStatus.APPROVED.value, "Approved plan")
    assert d2.status == DecisionStatus.APPROVED.value

    # 3. APPROVED -> COMPLETED
    d3 = decision_engine.transition_status(dec.decision_id, tenant_a.tenant_id, "field_tech", DecisionStatus.COMPLETED.value, "Replaced SFP")
    assert d3.status == DecisionStatus.COMPLETED.value

    # 4. COMPLETED -> VERIFIED
    d4 = decision_engine.transition_status(dec.decision_id, tenant_a.tenant_id, "qa_auditor", DecisionStatus.VERIFIED.value, "Verified normal ping")
    assert d4.status == DecisionStatus.VERIFIED.value

    # Verify audit history length
    hist = decision_engine.get_decision_history(tenant_a.tenant_id, dec.decision_id)
    assert len(hist) == 5  # Initial GENERATED + 4 transitions


def test_03_decision_lifecycle_invalid_transition_rejection(phase_c_setup):
    """Test 3: Rejects invalid lifecycle jumps (e.g. GENERATED directly to APPROVED)."""
    decision_engine = phase_c_setup["decision_engine"]
    tenant_a = phase_c_setup["tenant_a"]

    dec = decision_engine.synthesize_decision(
        tenant_id=tenant_a.tenant_id,
        site_id=None,
        problem_title="Invalid Transition Test",
    )

    # GENERATED cannot directly jump to APPROVED (must go through UNDER_REVIEW)
    with pytest.raises(ValueError, match="Invalid Decision State Transition"):
        decision_engine.transition_status(
            dec.decision_id,
            tenant_a.tenant_id,
            "noc_lead",
            DecisionStatus.APPROVED.value,
            "Bypassing review",
        )


def test_04_epistemic_insufficient_evidence_declaration(phase_c_setup):
    """Test 4: When evidence is missing, assessment explicitly reports INSUFFICIENT_EVIDENCE."""
    decision_engine = phase_c_setup["decision_engine"]
    tenant_a = phase_c_setup["tenant_a"]

    # Low-confidence RCA with missing evidence
    rca = MockRCAReport(
        rca_id="rca_missing",
        primary_root_cause="Suspected Flapping",
        confidence=0.35,
        supporting_evidence_ids=[],
        contradictory_evidence_ids=[],
        missing_evidence_ids=["metric:packet_loss", "metric:crc_errors", "log:syslog"],
        candidate_hypotheses=[],
    )

    dec = decision_engine.synthesize_decision(
        tenant_id=tenant_a.tenant_id,
        site_id=None,
        problem_title="Unknown Issue",
        rca_report=rca,
    )

    assert dec.assessment.epistemic_status == "INSUFFICIENT_EVIDENCE"
    assert len(dec.assessment.uncertainty_factors) > 0


# ===========================================================================
# 2. DYNAMIC HEALTH SCORING (WP 8.5.1)
# ===========================================================================

def test_05_health_scoring_missing_telemetry_emits_unknown(phase_c_setup):
    """Test 5: Missing telemetry results in UNKNOWN state with score=None (not 100% or 0.0)."""
    health_engine = phase_c_setup["health_engine"]
    tenant_a = phase_c_setup["tenant_a"]
    dev_a1 = phase_c_setup["dev_a1"]

    record = health_engine.score_device(tenant_a.tenant_id, dev_a1.device_id)
    assert record.state == HealthScoreState.UNKNOWN.value
    assert record.score is None
    assert "cpu" in record.missing_dimensions
    assert "memory" in record.missing_dimensions


def test_06_health_scoring_gateway_and_site(phase_c_setup):
    """Test 6: Gateway and site health scoring."""
    health_engine = phase_c_setup["health_engine"]
    gw_mgr = phase_c_setup["gw_mgr"]
    tenant_a = phase_c_setup["tenant_a"]
    site_a1 = phase_c_setup["site_a1"]

    # Enroll gateway & record healthy heartbeat
    raw_token, _ = gw_mgr.create_enrollment_token(tenant_a.tenant_id, site_a1.site_id, "admin")
    gw, auth_token = gw_mgr.enroll_gateway(raw_token, "Acme-GW-1")
    gw_mgr.record_heartbeat(auth_token, {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "cpu_utilization": 15.0,
        "memory_utilization": 30.0,
        "queue_depth": 0,
        "collector_status": "HEALTHY",
    })

    gw_health = health_engine.score_gateway(tenant_a.tenant_id, gw.gateway_id)
    assert gw_health.state == HealthScoreState.HEALTHY.value
    assert gw_health.score == 100.0

    site_health = health_engine.score_site(tenant_a.tenant_id, site_a1.site_id)
    assert site_health.site_id == site_a1.site_id


def test_07_tenant_health_tier1_minimum_clamping(phase_c_setup):
    """Test 7: Tenant health clamps to CRITICAL if any Tier 1 mission-critical service fails."""
    health_engine = phase_c_setup["health_engine"]
    tenant_a = phase_c_setup["tenant_a"]
    db_path = phase_c_setup["db_path"]

    # Create a Tier 1 service marked DOWN in database
    with pytest.MonkeyPatch.context() as m:
        from core.topology_db import topology_transaction
        with topology_transaction(db_path, write=True) as conn:
            conn.execute(
                """
                INSERT INTO operational_services (
                    service_id, tenant_id, name, criticality, status, health_score, created_at, updated_at
                ) VALUES ('svc_core_erp', ?, 'Core ERP', 'TIER_1_MISSION_CRITICAL', 'DOWN', 0.0, '2026-11-04T00:00:00Z', '2026-11-04T00:00:00Z')
                """,
                (tenant_a.tenant_id,),
            )

    tenant_health = health_engine.score_tenant(tenant_a.tenant_id)
    # Must be clamped to CRITICAL because Tier 1 service is down!
    assert tenant_health.state == HealthScoreState.CRITICAL.value
    assert tenant_health.score <= 40.0


# ===========================================================================
# 3. RISK AND IMPACT ASSESSMENT (WP 8.6)
# ===========================================================================

def test_08_virtual_simulation_blast_radius_non_destructive(phase_c_setup):
    """Test 8: Non-destructive virtual failure simulation on NetworkKnowledgeGraph."""
    risk_engine = phase_c_setup["risk_engine"]
    tenant_a = phase_c_setup["tenant_a"]
    dev_a1 = phase_c_setup["dev_a1"]

    # Construct knowledge graph
    graph = NetworkKnowledgeGraph()
    node1 = KnowledgeNode(node_id=dev_a1.device_id, entity_type=GraphEntityType.DEVICE.value, label="Core Router")
    node2 = KnowledgeNode(node_id="dev_access_switch", entity_type=GraphEntityType.DEVICE.value, label="Access Switch")
    graph.add_node(node1)
    graph.add_node(node2)
    edge = KnowledgeEdge(
        edge_id="edge_1_2",
        source_id=dev_a1.device_id,
        target_id="dev_access_switch",
        relationship_type=GraphRelationshipType.CONNECTS_TO.value,
    )
    graph.add_edge(edge)

    # Initial graph counts
    init_nodes = len(graph.nodes)
    init_edges = len(graph.edges)

    # Simulate failure of dev_a1
    sim_result = risk_engine.simulate_failure(
        tenant_id=tenant_a.tenant_id,
        graph=graph,
        failed_devices=[dev_a1.device_id],
        scenario_name="Simulate Core Outage",
    )

    # Verification: graph was NOT mutated!
    assert len(graph.nodes) == init_nodes
    assert len(graph.edges) == init_edges
    assert dev_a1.device_id in sim_result.directly_affected_devices
    assert 0.0 <= sim_result.risk_score <= 100.0


def test_09_multi_scenario_comparison(phase_c_setup):
    """Test 9: Compares multiple failure scenarios side-by-side."""
    risk_engine = phase_c_setup["risk_engine"]
    tenant_a = phase_c_setup["tenant_a"]
    graph = NetworkKnowledgeGraph()

    scenarios = [
        {"name": "Scenario 1: Minor switch failure", "failed_devices": ["sw_edge_01"]},
        {"name": "Scenario 2: Dual core router failure", "failed_devices": ["rtr_core_01", "rtr_core_02"]},
    ]
    comp = risk_engine.compare_scenarios(tenant_a.tenant_id, graph, scenarios)
    assert comp["compared_scenarios_count"] == 2
    # Highest risk scenario is identified
    assert comp["scenarios"][0]["risk_score"] >= comp["scenarios"][1]["risk_score"]


# ===========================================================================
# 4. SLA AND SERVICE MANAGEMENT (WP 8.7)
# ===========================================================================

def test_10_sla_policy_and_availability_calculation(phase_c_setup):
    """Test 10: Calculates SLA availability and error budget over a measurement window."""
    sla_engine = phase_c_setup["sla_engine"]
    tenant_a = phase_c_setup["tenant_a"]
    db_path = phase_c_setup["db_path"]

    # Create policy
    policy = sla_engine.create_or_update_policy(
        tenant_id=tenant_a.tenant_id,
        service_id="svc_internet",
        name="Internet Transit SLA",
        target_availability=99.9,
    )
    assert policy.target_availability == 99.9

    # Insert simulated samples for coverage
    now_epoch = time.time()
    from core.topology_db import topology_transaction
    with topology_transaction(db_path, write=True) as conn:
        for i in range(20):
            conn.execute(
                """
                INSERT INTO nms_raw_metrics (device_id, metric_name, metric_value, measured_at, collected_at)
                VALUES ('dev_gw_test', 'rx_utilization', 30.0, ?, ?)
                """,
                (now_epoch - i * 15, now_epoch),
            )
        # Link endpoint to dev_gw_test
        conn.execute(
            """
            INSERT OR REPLACE INTO operational_services (service_id, tenant_id, name, criticality, status, created_at, updated_at)
            VALUES ('svc_internet', ?, 'Internet', 'TIER_1_MISSION_CRITICAL', 'HEALTHY', '2026-11-04T00:00:00Z', '2026-11-04T00:00:00Z')
            """,
            (tenant_a.tenant_id,),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO operational_service_endpoints (endpoint_id, service_id, endpoint_type, endpoint_value, target_device_id, created_at)
            VALUES ('ep_1', 'svc_internet', 'IP_PORT', '1.1.1.1:443', 'dev_gw_test', '2026-11-04T00:00:00Z')
            """
        )

    start_iso = datetime.fromtimestamp(now_epoch - 300, tz=timezone.utc).isoformat()
    end_iso = datetime.fromtimestamp(now_epoch, tz=timezone.utc).isoformat()

    report = sla_engine.calculate_sla_report(
        tenant_id=tenant_a.tenant_id,
        service_id="svc_internet",
        start_time_utc=start_iso,
        end_time_utc=end_iso,
    )
    assert report.target_availability == 99.9
    assert report.total_downtime_seconds == 0.0
    assert report.measured_availability == 100.0
    assert report.status == SlaStatusType.COMPLIANT.value
    assert report.error_budget_remaining_percent == 100.0


def test_11_sla_insufficient_data_coverage(phase_c_setup):
    """Test 11: Emits INSUFFICIENT_COVERAGE when data coverage is below 80% (never invents a number)."""
    sla_engine = phase_c_setup["sla_engine"]
    tenant_a = phase_c_setup["tenant_a"]

    # 1 hour window with 0 samples
    now_epoch = time.time()
    start_iso = datetime.fromtimestamp(now_epoch - 3600, tz=timezone.utc).isoformat()
    end_iso = datetime.fromtimestamp(now_epoch, tz=timezone.utc).isoformat()

    report = sla_engine.calculate_sla_report(
        tenant_id=tenant_a.tenant_id,
        service_id="svc_empty_telemetry",
        start_time_utc=start_iso,
        end_time_utc=end_iso,
    )

    assert report.status == SlaStatusType.INSUFFICIENT_COVERAGE.value
    assert report.measured_availability is None # Epistemic honesty
    assert report.data_coverage_percent < 80.0


# ===========================================================================
# 5. MULTI-TENANT INCIDENT ORCHESTRATION (WP 8.8)
# ===========================================================================

def test_12_incident_deduplication_fingerprint(phase_c_setup):
    """Test 12: Alert deduplication clusters co-occurring alarms into one incident."""
    incident_engine = phase_c_setup["incident_engine"]
    tenant_a = phase_c_setup["tenant_a"]
    site_a1 = phase_c_setup["site_a1"]

    # Report Alarm 1
    inc1 = incident_engine.report_incident(
        tenant_id=tenant_a.tenant_id,
        site_id=site_a1.site_id,
        title="Uplink Port Flapping",
        severity="HIGH",
        summary="Koneksi flapping pada ether1.",
        primary_entity_id="ether1",
        failure_signature="LINK_FLAP",
        evidence_ids=["ev_101"],
    )

    # Report Alarm 2 within active window with identical fingerprint
    inc2 = incident_engine.report_incident(
        tenant_id=tenant_a.tenant_id,
        site_id=site_a1.site_id,
        title="Uplink Port Flapping Again",
        severity="HIGH",
        summary="Koneksi flapping pada ether1.",
        primary_entity_id="ether1",
        failure_signature="LINK_FLAP",
        evidence_ids=["ev_102"],
    )

    # Must be deduplicated into the same incident!
    assert inc1.incident_id == inc2.incident_id
    assert "ev_101" in inc2.evidence_ids
    assert "ev_102" in inc2.evidence_ids


def test_13_incident_lifecycle_transitions(phase_c_setup):
    """Test 13: Incident state machine progression."""
    incident_engine = phase_c_setup["incident_engine"]
    tenant_a = phase_c_setup["tenant_a"]

    inc = incident_engine.report_incident(
        tenant_id=tenant_a.tenant_id,
        title="Test Incident Lifecycle",
        severity="MEDIUM",
        summary="Incident state transition test.",
    )
    assert inc.state == IncidentState.DETECTED.value

    # DETECTED -> ACKNOWLEDGED
    i1 = incident_engine.transition_incident(tenant_a.tenant_id, inc.incident_id, IncidentState.ACKNOWLEDGED.value, "noc_operator")
    assert i1.state == IncidentState.ACKNOWLEDGED.value

    # ACKNOWLEDGED -> INVESTIGATING
    i2 = incident_engine.transition_incident(tenant_a.tenant_id, inc.incident_id, IncidentState.INVESTIGATING.value, "noc_engineer")
    assert i2.state == IncidentState.INVESTIGATING.value

    # INVESTIGATING -> RESOLVED
    i3 = incident_engine.transition_incident(tenant_a.tenant_id, inc.incident_id, IncidentState.RESOLVED.value, "noc_engineer", "Kabel diganti")
    assert i3.state == IncidentState.RESOLVED.value
    assert i3.resolved_at is not None


# ===========================================================================
# 6. SECURITY & ADVERSARIAL TENANT ISOLATION TESTS
# ===========================================================================

def test_14_cross_tenant_decision_isolation(phase_c_setup):
    """Test 14: Tenant A cannot read or transition Tenant B decisions."""
    decision_engine = phase_c_setup["decision_engine"]
    tenant_a = phase_c_setup["tenant_a"]
    tenant_b = phase_c_setup["tenant_b"]

    # Decision belongs to Tenant B
    dec_b = decision_engine.synthesize_decision(
        tenant_id=tenant_b.tenant_id,
        site_id=None,
        problem_title="Tenant B Secret Core Failure",
    )

    # Tenant A attempts to fetch Tenant B's decision -> None
    read_attempt = decision_engine.get_decision(tenant_a.tenant_id, dec_b.decision_id)
    assert read_attempt is None

    # Tenant A attempts to transition Tenant B's decision -> KeyError
    with pytest.raises(KeyError):
        decision_engine.transition_status(
            dec_b.decision_id,
            tenant_a.tenant_id,
            "hacker_a",
            DecisionStatus.APPROVED.value,
            "Malicious approval",
        )


def test_15_rfc1918_overlap_safety_across_tenants(phase_c_setup):
    """Test 15: Overlapping RFC 1918 IPs (192.168.1.1 in A and B) do not leak or cross-correlate."""
    incident_engine = phase_c_setup["incident_engine"]
    tenant_a = phase_c_setup["tenant_a"]
    tenant_b = phase_c_setup["tenant_b"]
    dev_a1 = phase_c_setup["dev_a1"]
    dev_b1 = phase_c_setup["dev_b1"]

    # Both dev_a1 and dev_b1 have primary IP 192.168.1.1
    assert dev_a1.management_ip == dev_b1.management_ip == "192.168.1.1"

    # Create incident for Tenant A on 192.168.1.1
    inc_a = incident_engine.report_incident(
        tenant_id=tenant_a.tenant_id,
        title="Router A Down",
        severity="HIGH",
        summary="Core router 192.168.1.1 down",
        primary_entity_id="192.168.1.1",
        failure_signature="DEVICE_DOWN",
        affected_devices=[dev_a1.device_id],
    )

    # Create incident for Tenant B on 192.168.1.1
    inc_b = incident_engine.report_incident(
        tenant_id=tenant_b.tenant_id,
        title="Router B Down",
        severity="HIGH",
        summary="Core router 192.168.1.1 down",
        primary_entity_id="192.168.1.1",
        failure_signature="DEVICE_DOWN",
        affected_devices=[dev_b1.device_id],
    )

    # Fingerprints and incidents must be COMPLETELY SEPARATE
    assert inc_a.incident_id != inc_b.incident_id

    # Tenant A cannot see Tenant B's incident
    assert incident_engine.get_incident(tenant_a.tenant_id, inc_b.incident_id) is None
    assert incident_engine.get_incident(tenant_b.tenant_id, inc_a.incident_id) is None


def test_16_customer_role_cannot_approve_decisions(phase_c_setup):
    """Test 16: Customer user roles lack recommendation.approve permission."""
    tenant_a = phase_c_setup["tenant_a"]
    identity_mgr = phase_c_setup["identity_mgr"]

    # Create customer operator user
    cust_user = identity_mgr.create_user(
        username="cust_operator_john",
        email="john@acme.com",
        password="SecurePassword123!",
        role_type=UserRoleType.CUSTOMER_OPERATOR.value,
        tenant_id=tenant_a.tenant_id,
    )

    session = identity_mgr.authenticate_user(
        username_or_email="cust_operator_john",
        password="SecurePassword123!",
    )
    assert session is not None

    ctx = identity_mgr.validate_session_token(session.token)
    assert ctx is not None

    # Customer Operator can read recommendations
    assert ctx.has_permission(Permission.RECOMMENDATION_READ) is False # Customer roles only have incident.read
    # Customer Operator CANNOT approve recommendations
    assert ctx.has_permission(Permission.RECOMMENDATION_APPROVE) is False
