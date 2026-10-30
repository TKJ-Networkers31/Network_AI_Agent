"""
core/network_intelligence/models.py — Data contracts and typed schemas for AIRA Network Intelligence.

Phase 2-4: Evidence-Driven Incident Investigation, Diagnostic Playbooks,
and Static Configuration Planning & Simulation.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class IncidentType(str, Enum):
    LAN_NO_INTERNET = "LAN_NO_INTERNET"
    DEFAULT_ROUTE_FAILS = "DEFAULT_ROUTE_FAILS"
    NAT_MISMATCH = "NAT_MISMATCH"
    FIREWALL_FORWARD_BLOCKED = "FIREWALL_FORWARD_BLOCKED"
    OSPF_ADJACENCY_FAILURE = "OSPF_ADJACENCY_FAILURE"
    BGP_PREFIXES_MISSING = "BGP_PREFIXES_MISSING"
    VLAN_TRUNK_FAILURE = "VLAN_TRUNK_FAILURE"
    CUSTOM = "CUSTOM"


class PreflightStatus(str, Enum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNREACHABLE = "UNREACHABLE"
    AUTH_FAILED = "AUTH_FAILED"
    IDENTITY_UNVERIFIED = "IDENTITY_UNVERIFIED"
    CONNECTED_READ_ONLY = "CONNECTED_READ_ONLY"
    PARTIAL_CAPABILITY = "PARTIAL_CAPABILITY"
    READY_FOR_DIAGNOSTICS = "READY_FOR_DIAGNOSTICS"


class InvestigationStatus(str, Enum):
    CREATED = "CREATED"
    COLLECTING_EVIDENCE = "COLLECTING_EVIDENCE"
    EVIDENCE_PARTIAL = "EVIDENCE_PARTIAL"
    ANALYZING = "ANALYZING"
    AWAITING_OPERATOR_INPUT = "AWAITING_OPERATOR_INPUT"
    DIAGNOSIS_READY = "DIAGNOSIS_READY"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class SeverityLevel(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class EvidenceFreshness(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class EvidenceState(str, Enum):
    OBSERVED = "OBSERVED"
    DERIVED = "DERIVED"
    STALE = "STALE"
    CONTRADICTORY = "CONTRADICTORY"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"


class PlaybookStatus(str, Enum):
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_FOR_EVIDENCE = "WAITING_FOR_EVIDENCE"
    WAITING_FOR_OPERATOR = "WAITING_FOR_OPERATOR"
    COMPLETED = "COMPLETED"
    INCONCLUSIVE = "INCONCLUSIVE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PlanStatus(str, Enum):
    DRAFT = "DRAFT"
    NEEDS_INPUT = "NEEDS_INPUT"
    VALIDATING = "VALIDATING"
    INVALID = "INVALID"
    VALID_WITH_WARNINGS = "VALID_WITH_WARNINGS"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    STALE = "STALE"
    CANCELLED = "CANCELLED"


class ValidationSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Evidence Models
# ---------------------------------------------------------------------------

@dataclass
class EvidenceItem:
    evidence_id: str
    device_identity: str
    observation_type: str
    source_command: str
    collection_timestamp: float
    collection_status: str = "SUCCESS"  # SUCCESS, PARTIAL, FAILED, TIMEOUT, CACHED
    normalized_value: Any = None
    raw_excerpt: str = ""
    freshness: str = EvidenceFreshness.FRESH.value
    is_derived: bool = False
    limitations: str = ""
    state: str = EvidenceState.OBSERVED.value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "device_identity": self.device_identity,
            "observation_type": self.observation_type,
            "source_command": self.source_command,
            "collection_timestamp": self.collection_timestamp,
            "collection_status": self.collection_status,
            "normalized_value": self.normalized_value,
            "raw_excerpt": self.raw_excerpt,
            "freshness": self.freshness,
            "is_derived": self.is_derived,
            "limitations": self.limitations,
            "state": self.state,
        }


# ---------------------------------------------------------------------------
# Hypothesis Model
# ---------------------------------------------------------------------------

@dataclass
class RankedHypothesis:
    hypothesis_id: str
    title: str
    explanation: str
    supporting_evidence: List[str] = field(default_factory=list)
    contradicting_evidence: List[str] = field(default_factory=list)
    missing_evidence: List[str] = field(default_factory=list)
    recommended_test: str = ""
    confidence: str = ConfidenceLevel.MEDIUM.value
    confidence_explanation: str = ""
    alternative_explanations: List[str] = field(default_factory=list)
    known_limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "title": self.title,
            "explanation": self.explanation,
            "supporting_evidence": list(self.supporting_evidence),
            "contradicting_evidence": list(self.contradicting_evidence),
            "missing_evidence": list(self.missing_evidence),
            "recommended_test": self.recommended_test,
            "confidence": self.confidence,
            "confidence_explanation": self.confidence_explanation,
            "alternative_explanations": list(self.alternative_explanations),
            "known_limitations": list(self.known_limitations),
        }


# ---------------------------------------------------------------------------
# Incident Model
# ---------------------------------------------------------------------------

@dataclass
class IncidentRecord:
    incident_id: str
    device_identity: str
    related_devices: List[str] = field(default_factory=list)
    incident_type: str = IncidentType.CUSTOM.value
    severity: str = SeverityLevel.MEDIUM.value
    symptoms: List[str] = field(default_factory=list)
    user_description: str = ""
    observed_facts: List[str] = field(default_factory=list)
    inferred_hypotheses: List[Dict[str, Any]] = field(default_factory=list)
    missing_evidence: List[str] = field(default_factory=list)
    recommended_tests: List[Dict[str, Any]] = field(default_factory=list)
    evidence_sources: List[str] = field(default_factory=list)
    confidence: str = ConfidenceLevel.MEDIUM.value
    confidence_explanation: str = ""
    investigation_status: str = InvestigationStatus.CREATED.value
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    limitations_disclosure: str = ""
    related_plan_ids: List[str] = field(default_factory=list)
    correlation_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "device_identity": self.device_identity,
            "related_devices": list(self.related_devices),
            "incident_type": self.incident_type,
            "severity": self.severity,
            "symptoms": list(self.symptoms),
            "user_description": self.user_description,
            "observed_facts": list(self.observed_facts),
            "inferred_hypotheses": self.inferred_hypotheses,
            "missing_evidence": list(self.missing_evidence),
            "recommended_tests": self.recommended_tests,
            "evidence_sources": list(self.evidence_sources),
            "confidence": self.confidence,
            "confidence_explanation": self.confidence_explanation,
            "investigation_status": self.investigation_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "limitations_disclosure": self.limitations_disclosure,
            "related_plan_ids": list(self.related_plan_ids),
            "correlation_id": self.correlation_id,
        }


# ---------------------------------------------------------------------------
# Diagnostic Playbook Models
# ---------------------------------------------------------------------------

@dataclass
class PlaybookStep:
    step_id: str
    objective: str
    preconditions: List[str] = field(default_factory=list)
    required_evidence: List[str] = field(default_factory=list)
    action: Dict[str, Any] = field(default_factory=dict)
    expected_results: Dict[str, Any] = field(default_factory=dict)
    decision_rules: List[Dict[str, Any]] = field(default_factory=list)
    next_step: Optional[str] = None
    stop_conditions: List[str] = field(default_factory=list)
    safety_notes: str = ""
    version_compatibility: str = "v6,v7"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "objective": self.objective,
            "preconditions": list(self.preconditions),
            "required_evidence": list(self.required_evidence),
            "action": self.action,
            "expected_results": self.expected_results,
            "decision_rules": self.decision_rules,
            "next_step": self.next_step,
            "stop_conditions": list(self.stop_conditions),
            "safety_notes": self.safety_notes,
            "version_compatibility": self.version_compatibility,
        }


@dataclass
class DiagnosticPlaybook:
    playbook_id: str
    name: str
    description: str
    supported_platforms: List[str] = field(default_factory=lambda: ["MikroTik RouterOS"])
    supported_versions: List[str] = field(default_factory=lambda: ["v6", "v7"])
    incident_types: List[str] = field(default_factory=list)
    prerequisites: List[str] = field(default_factory=list)
    steps: List[PlaybookStep] = field(default_factory=list)
    required_evidence: List[str] = field(default_factory=list)
    decision_rules: List[Dict[str, Any]] = field(default_factory=list)
    expected_outcomes: List[str] = field(default_factory=list)
    failure_branches: Dict[str, str] = field(default_factory=dict)
    risk_level: str = "READ_ONLY"
    read_only: bool = True
    limitations: str = ""
    version: str = "1.0.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "playbook_id": self.playbook_id,
            "name": self.name,
            "description": self.description,
            "supported_platforms": list(self.supported_platforms),
            "supported_versions": list(self.supported_versions),
            "incident_types": list(self.incident_types),
            "prerequisites": list(self.prerequisites),
            "steps": [s.to_dict() for s in self.steps],
            "required_evidence": list(self.required_evidence),
            "decision_rules": self.decision_rules,
            "expected_outcomes": list(self.expected_outcomes),
            "failure_branches": self.failure_branches,
            "risk_level": self.risk_level,
            "read_only": self.read_only,
            "limitations": self.limitations,
            "version": self.version,
        }


@dataclass
class PlaybookRunRecord:
    run_id: str
    playbook_id: str
    incident_id: str
    device_identity: str
    status: str = PlaybookStatus.READY.value
    current_step_id: Optional[str] = None
    completed_steps: List[str] = field(default_factory=list)
    operator_inputs: Dict[str, Any] = field(default_factory=dict)
    step_logs: List[Dict[str, Any]] = field(default_factory=list)
    decision_history: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "playbook_id": self.playbook_id,
            "incident_id": self.incident_id,
            "device_identity": self.device_identity,
            "status": self.status,
            "current_step_id": self.current_step_id,
            "completed_steps": list(self.completed_steps),
            "operator_inputs": self.operator_inputs,
            "step_logs": self.step_logs,
            "decision_history": self.decision_history,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ---------------------------------------------------------------------------
# Configuration Planning & Simulation Models
# ---------------------------------------------------------------------------

@dataclass
class ValidationFinding:
    severity: str  # ERROR, WARNING, INFO, UNKNOWN
    rule_id: str
    description: str
    evidence_references: List[str] = field(default_factory=list)
    affected_object: str = ""
    suggested_resolution: str = ""
    is_blocking: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "rule_id": self.rule_id,
            "description": self.description,
            "evidence_references": list(self.evidence_references),
            "affected_object": self.affected_object,
            "suggested_resolution": self.suggested_resolution,
            "is_blocking": self.is_blocking,
        }


@dataclass
class ProposedCommand:
    command_id: str
    target_device: str
    command: str
    rollback_command: Optional[str] = None
    intended_effect: str = ""
    preconditions: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    risk_level: str = "LOW"
    version_compatibility: str = "v6,v7"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "target_device": self.target_device,
            "command": self.command,
            "rollback_command": self.rollback_command,
            "intended_effect": self.intended_effect,
            "preconditions": list(self.preconditions),
            "dependencies": list(self.dependencies),
            "risk_level": self.risk_level,
            "version_compatibility": self.version_compatibility,
        }


@dataclass
class SimulationResult:
    simulation_status: str  # SUCCESS, WARNING, SIMULATION_INCONCLUSIVE, FAILED
    inputs_summary: Dict[str, Any] = field(default_factory=dict)
    assumptions: List[str] = field(default_factory=list)
    modeled_behavior: Dict[str, Any] = field(default_factory=dict)
    expected_result: str = ""
    unmodeled_behavior: List[str] = field(default_factory=list)
    confidence_limitations: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_status": self.simulation_status,
            "inputs_summary": self.inputs_summary,
            "assumptions": list(self.assumptions),
            "modeled_behavior": self.modeled_behavior,
            "expected_result": self.expected_result,
            "unmodeled_behavior": list(self.unmodeled_behavior),
            "confidence_limitations": self.confidence_limitations,
        }


@dataclass
class ConfigurationPlan:
    plan_id: str
    operation_id: str
    incident_id: Optional[str] = None
    target_devices: List[str] = field(default_factory=list)
    desired_state: Dict[str, Any] = field(default_factory=dict)
    baseline_snapshot_reference: Optional[str] = None
    preconditions: List[str] = field(default_factory=list)
    proposed_changes: List[Dict[str, Any]] = field(default_factory=list)
    configuration_diff: str = ""
    dependencies: List[Dict[str, Any]] = field(default_factory=list)
    risk_level: str = "LOW"
    blast_radius: Dict[str, Any] = field(default_factory=dict)
    management_connectivity_risk: bool = False
    management_risk_explanation: str = ""
    validation_results: List[Dict[str, Any]] = field(default_factory=list)
    simulation_results: Optional[Dict[str, Any]] = None
    expected_postconditions: List[str] = field(default_factory=list)
    rollback_considerations: List[str] = field(default_factory=list)
    required_operator_inputs: List[str] = field(default_factory=list)
    approval_requirements: List[str] = field(default_factory=list)
    limitations_disclosure: str = ""
    plan_status: str = PlanStatus.DRAFT.value
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "operation_id": self.operation_id,
            "incident_id": self.incident_id,
            "target_devices": list(self.target_devices),
            "desired_state": self.desired_state,
            "baseline_snapshot_reference": self.baseline_snapshot_reference,
            "preconditions": list(self.preconditions),
            "proposed_changes": self.proposed_changes,
            "configuration_diff": self.configuration_diff,
            "dependencies": self.dependencies,
            "risk_level": self.risk_level,
            "blast_radius": self.blast_radius,
            "management_connectivity_risk": self.management_connectivity_risk,
            "management_risk_explanation": self.management_risk_explanation,
            "validation_results": self.validation_results,
            "simulation_results": self.simulation_results,
            "expected_postconditions": list(self.expected_postconditions),
            "rollback_considerations": list(self.rollback_considerations),
            "required_operator_inputs": list(self.required_operator_inputs),
            "approval_requirements": list(self.approval_requirements),
            "limitations_disclosure": self.limitations_disclosure,
            "plan_status": self.plan_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class PreflightResult:
    target: str
    status: str = PreflightStatus.NOT_CONFIGURED.value
    reachability: bool = False
    authenticated: bool = False
    identity: Optional[str] = None
    routeros_version: Optional[str] = None
    ros_major_version: Optional[int] = None
    effective_permissions: List[str] = field(default_factory=list)
    allowed_commands_tested: List[str] = field(default_factory=list)
    rejected_commands: List[Dict[str, str]] = field(default_factory=list)
    output_quality: Dict[str, Any] = field(default_factory=dict)
    parser_completeness: Dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""
    duration_ms: float = 0.0
    message: str = ""
    limitations: str = ""
    tested_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target": self.target,
            "status": self.status,
            "reachability": self.reachability,
            "authenticated": self.authenticated,
            "identity": self.identity,
            "routeros_version": self.routeros_version,
            "ros_major_version": self.ros_major_version,
            "effective_permissions": list(self.effective_permissions),
            "allowed_commands_tested": list(self.allowed_commands_tested),
            "rejected_commands": self.rejected_commands,
            "output_quality": self.output_quality,
            "parser_completeness": self.parser_completeness,
            "correlation_id": self.correlation_id,
            "duration_ms": self.duration_ms,
            "message": self.message,
            "limitations": self.limitations,
            "tested_at": self.tested_at,
        }


# ---------------------------------------------------------------------------
# Pydantic Schemas for API Requests
# ---------------------------------------------------------------------------

class PreflightIn(BaseModel):
    target: str = Field(..., description="Target device name, hostname, or IP")
    username: Optional[str] = Field(None, description="Optional SSH username override")
    password: Optional[str] = Field(None, description="Optional SSH password override (never logged)")
    port: int = Field(22, description="SSH port")
    timeout: float = Field(5.0, description="Probe timeout seconds")


class IncidentCreateIn(BaseModel):
    device_identity: str = Field(..., description="Target device name, IP, or identity")
    incident_type: IncidentType = Field(IncidentType.CUSTOM, description="Classified incident type")
    symptoms: List[str] = Field(default_factory=list, description="Observed symptom strings")
    user_description: str = Field("", description="Natural language description of problem")
    severity: SeverityLevel = Field(SeverityLevel.MEDIUM, description="Reported severity")
    target_ip: Optional[str] = Field(None, description="Target destination or client IP under test")
    correlation_id: Optional[str] = Field(None, description="Optional correlation ID for distributed tracing")


class PlaybookAdvanceIn(BaseModel):
    action: str = Field("step", description="'step', 'input', 'cancel'")
    operator_input: Optional[Dict[str, Any]] = Field(None, description="Operator supplied value or confirmation")


class DesiredStateIn(BaseModel):
    target_device: str = Field(..., description="Target device name or IP")
    change_type: str = Field(..., description="E.g. ADD_VLAN, ADD_STATIC_ROUTE, CONFIGURE_NAT, OSPF_PEER, BGP_PEER, FIREWALL_RULE")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Change attributes (vlan_id, subnet, gateway, etc.)")
    incident_id: Optional[str] = Field(None, description="Optional incident ID correlating this change")
