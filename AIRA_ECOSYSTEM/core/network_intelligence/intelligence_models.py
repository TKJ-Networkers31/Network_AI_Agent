"""
AIRA OS — Networking VI Canonical Intelligence Domain Models (WP 6.1 – WP 6.15).

Defines the deterministic, evidence-driven data contracts across all seven layers
of the Network Intelligence Core:
- Layer 1 & 2: Unified Evidence Normalization & Type-Aware Freshness (WP 6.1)
- Layer 3: Multi-Layer Network Knowledge Graph & Entity Resolution (WP 6.2)
- Layer 4: Path Intelligence (WP 6.3), Multi-Device Correlation (WP 6.4),
           Root Cause Analysis & Confidence Model (WP 6.5), Health/Baselines/Anomalies (WP 6.6),
           Change Impact & Analytical Simulation (WP 6.7), Protocol Intelligence (WP 6.8),
           and Historical Network Intelligence (WP 6.9)
- Layer 5 & 6: Natural-Language Intent, Planning, Scoped Context (WP 6.10) &
               Grounded LLM Reasoning Orchestration (WP 6.11)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ===========================================================================
# 1. EVIDENCE NORMALIZATION & FRESHNESS ENUMS (WP 6.1)
# ===========================================================================

class IntelligenceFreshness(str, Enum):
    FRESH = "FRESH"
    AGING = "AGING"
    STALE = "STALE"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class EvidenceQuality(str, Enum):
    GOOD = "GOOD"
    PARTIAL = "PARTIAL"
    DISCONTINUOUS = "DISCONTINUOUS"
    UNCERTAIN = "UNCERTAIN"
    MISSING = "MISSING"
    CONTRADICTORY = "CONTRADICTORY"
    INVALID = "INVALID"


class EvidenceCompleteness(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    EMPTY = "EMPTY"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass
class CanonicalEvidenceRecord:
    """Typed, timestamped, provenance-tracked evidence unit in Networking VI."""
    evidence_id: str
    device_id: str
    device_identity: str
    evidence_type: str
    source_subsystem: str
    collection_method: str
    collected_at: float
    observed_at: Optional[float] = None
    validity_ttl_sec: float = 120.0
    freshness: str = IntelligenceFreshness.FRESH.value
    quality: str = EvidenceQuality.GOOD.value
    parser_version: str = "6.1.0"
    normalized_payload: Any = None
    source_reference: str = ""
    sanitized_command_ref: str = ""
    confidence: float = 0.9
    completeness: str = EvidenceCompleteness.COMPLETE.value
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "device_id": self.device_id,
            "device_identity": self.device_identity,
            "evidence_type": self.evidence_type,
            "source_subsystem": self.source_subsystem,
            "collection_method": self.collection_method,
            "collected_at": self.collected_at,
            "observed_at": self.observed_at,
            "validity_ttl_sec": self.validity_ttl_sec,
            "freshness": self.freshness,
            "quality": self.quality,
            "parser_version": self.parser_version,
            "normalized_payload": self.normalized_payload,
            "source_reference": self.source_reference,
            "sanitized_command_ref": self.sanitized_command_ref,
            "confidence": round(float(self.confidence), 4),
            "completeness": self.completeness,
            "provenance": dict(self.provenance),
        }


@dataclass
class CollectionGapRecord:
    """Explicit disclosure of missing, unreachable, or uncollected evidence (never fabricated as zero)."""
    gap_id: str
    device_id: str
    evidence_type: str
    gap_reason: str  # TELEMETRY_GAP, DEVICE_UNREACHABLE, MANAGEMENT_UNAVAILABLE, NOT_COLLECTED, UNSUPPORTED_READONLY_BOUNDARY
    detail: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gap_id": self.gap_id,
            "device_id": self.device_id,
            "evidence_type": self.evidence_type,
            "gap_reason": self.gap_reason,
            "detail": self.detail,
            "timestamp": self.timestamp,
        }


@dataclass
class EvidenceContradiction:
    """Preserves conflicting observations across sources or devices without hiding discrepancy."""
    contradiction_id: str
    contradiction_type: str
    description: str
    involved_devices: List[str] = field(default_factory=list)
    evidence_ids: List[str] = field(default_factory=list)
    severity: str = "warning"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contradiction_id": self.contradiction_id,
            "contradiction_type": self.contradiction_type,
            "description": self.description,
            "involved_devices": list(self.involved_devices),
            "evidence_ids": list(self.evidence_ids),
            "severity": self.severity,
        }


@dataclass
class NetworkEvidenceBundle:
    """Unified multi-device evidence projection assembled without duplicate polling."""
    bundle_id: str
    correlation_id: str
    assembled_at: float
    scope: str
    selected_devices: List[str] = field(default_factory=list)
    selected_interfaces: List[str] = field(default_factory=list)
    topology_snapshot_ref: Optional[str] = None
    route_snapshot_refs: Dict[str, str] = field(default_factory=dict)
    records: List[CanonicalEvidenceRecord] = field(default_factory=list)
    device_evidence: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    interface_evidence: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    routing_evidence: Dict[str, List[Any]] = field(default_factory=dict)
    topology_evidence: List[Dict[str, Any]] = field(default_factory=list)
    incident_evidence: List[Dict[str, Any]] = field(default_factory=list)
    protocol_evidence: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    historical_refs: Dict[str, Any] = field(default_factory=dict)
    freshness_summary: Dict[str, int] = field(default_factory=dict)
    completeness_summary: Dict[str, Any] = field(default_factory=dict)
    collection_gaps: List[CollectionGapRecord] = field(default_factory=list)
    contradictions: List[EvidenceContradiction] = field(default_factory=list)
    reused_cached_count: int = 0
    live_collected_count: int = 0

    def get_record(self, evidence_id: str) -> Optional[CanonicalEvidenceRecord]:
        for rec in self.records:
            if rec.evidence_id == evidence_id:
                return rec
        return None

    def records_for_device(self, device_id: str, evidence_type: Optional[str] = None) -> List[CanonicalEvidenceRecord]:
        out = [r for r in self.records if r.device_id == device_id]
        if evidence_type:
            out = [r for r in out if r.evidence_type == evidence_type]
        return out

    def to_dict(self, include_records: bool = True) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "bundle_id": self.bundle_id,
            "correlation_id": self.correlation_id,
            "assembled_at": self.assembled_at,
            "scope": self.scope,
            "selected_devices": list(self.selected_devices),
            "selected_interfaces": list(self.selected_interfaces),
            "topology_snapshot_ref": self.topology_snapshot_ref,
            "route_snapshot_refs": dict(self.route_snapshot_refs),
            "freshness_summary": dict(self.freshness_summary),
            "completeness_summary": dict(self.completeness_summary),
            "collection_gaps": [g.to_dict() for g in self.collection_gaps],
            "contradictions": [c.to_dict() for c in self.contradictions],
            "reused_cached_count": self.reused_cached_count,
            "live_collected_count": self.live_collected_count,
            "record_count": len(self.records),
        }
        if include_records:
            payload["records"] = [r.to_dict() for r in self.records]
        return payload


# ===========================================================================
# 2. NETWORK KNOWLEDGE GRAPH MODELS (WP 6.2)
# ===========================================================================

class GraphEntityType(str, Enum):
    DEVICE = "DEVICE"
    INTERFACE = "INTERFACE"
    IP_ADDRESS = "IP_ADDRESS"
    SUBNET = "SUBNET"
    VLAN = "VLAN"
    BRIDGE = "BRIDGE"
    VRF = "VRF"
    ROUTING_TABLE = "ROUTING_TABLE"
    ROUTE = "ROUTE"
    NEXT_HOP = "NEXT_HOP"
    GATEWAY = "GATEWAY"
    ROUTING_PROTOCOL_INSTANCE = "ROUTING_PROTOCOL_INSTANCE"
    OSPF_NEIGHBOR = "OSPF_NEIGHBOR"
    BGP_PEER = "BGP_PEER"
    TUNNEL = "TUNNEL"
    WAN_CONNECTION = "WAN_CONNECTION"
    SERVICE_ENDPOINT = "SERVICE_ENDPOINT"
    NETWORK_SEGMENT = "NETWORK_SEGMENT"
    INCIDENT = "INCIDENT"
    TELEMETRY_OBSERVATION = "TELEMETRY_OBSERVATION"
    CONFIGURATION_SNAPSHOT = "CONFIGURATION_SNAPSHOT"


class GraphRelationshipType(str, Enum):
    PHYSICAL_ADJACENCY = "PHYSICAL_ADJACENCY"
    LAYER2_ADJACENCY = "LAYER2_ADJACENCY"
    LAYER3_REACHABILITY = "LAYER3_REACHABILITY"
    LOGICAL_RELATIONSHIP = "LOGICAL_RELATIONSHIP"
    HOSTED_ON = "HOSTED_ON"
    MEMBER_OF = "MEMBER_OF"
    ADDRESSED_WITH = "ADDRESSED_WITH"
    ROUTES_TO = "ROUTES_TO"
    NEXT_HOP_OF = "NEXT_HOP_OF"
    PEERS_WITH = "PEERS_WITH"
    ADVERTISES = "ADVERTISES"
    LEARNS = "LEARNS"
    DEPENDS_ON = "DEPENDS_ON"
    CARRIES = "CARRIES"
    CONNECTS_TO = "CONNECTS_TO"
    AFFECTS = "AFFECTS"
    OBSERVED_BY = "OBSERVED_BY"
    CAUSED_POSSIBLY_BY = "CAUSED_POSSIBLY_BY"


class GraphLayer(str, Enum):
    PHYSICAL = "physical"
    LAYER2 = "layer2"
    LAYER3 = "layer3"
    ROUTING = "routing"
    PROTOCOL = "protocol"
    TUNNEL = "tunnel"
    WAN = "wan"
    LOGICAL = "logical"
    TELEMETRY = "telemetry"


@dataclass
class KnowledgeNode:
    node_id: str
    entity_type: str
    label: str
    device_id: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    evidence_ids: List[str] = field(default_factory=list)
    provenance: str = "deterministic"
    confidence: float = 0.9
    observed_at: Optional[float] = None
    freshness: str = IntelligenceFreshness.FRESH.value
    completeness: str = EvidenceCompleteness.COMPLETE.value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "entity_type": self.entity_type,
            "label": self.label,
            "device_id": self.device_id,
            "attributes": dict(self.attributes),
            "evidence_ids": list(self.evidence_ids),
            "provenance": self.provenance,
            "confidence": round(float(self.confidence), 4),
            "observed_at": self.observed_at,
            "freshness": self.freshness,
            "completeness": self.completeness,
        }


@dataclass
class KnowledgeEdge:
    edge_id: str
    source_id: str
    target_id: str
    relationship_type: str
    layer: str = GraphLayer.LOGICAL.value
    bidirectional: bool = False
    is_inferred: bool = False
    evidence_ids: List[str] = field(default_factory=list)
    provenance: str = "deterministic"
    confidence: float = 0.85
    observed_at: Optional[float] = None
    valid_until: Optional[float] = None
    freshness: str = IntelligenceFreshness.FRESH.value
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relationship_type": self.relationship_type,
            "layer": self.layer,
            "bidirectional": self.bidirectional,
            "is_inferred": self.is_inferred,
            "evidence_ids": list(self.evidence_ids),
            "provenance": self.provenance,
            "confidence": round(float(self.confidence), 4),
            "observed_at": self.observed_at,
            "valid_until": self.valid_until,
            "freshness": self.freshness,
            "attributes": dict(self.attributes),
        }


@dataclass
class GraphConsistencyIssue:
    issue_id: str
    issue_type: str  # UNKNOWN_DEVICE, ORPHANED_INTERFACE, INVALID_ENDPOINT, STALE_EVIDENCE, CONFLICTING_OBSERVATION, DUPLICATE_RELATIONSHIP, IDENTITY_CONFLICT, EXPIRED_DEPENDENCY, INCOMPLETE_DISCOVERY
    severity: str
    description: str
    affected_ids: List[str] = field(default_factory=list)
    evidence_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "description": self.description,
            "affected_ids": list(self.affected_ids),
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass
class GraphConsistencyReport:
    is_consistent: bool
    is_partial_network: bool
    total_nodes: int
    total_edges: int
    issues: List[GraphConsistencyIssue] = field(default_factory=list)
    checked_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_consistent": self.is_consistent,
            "is_partial_network": self.is_partial_network,
            "total_nodes": self.total_nodes,
            "total_edges": self.total_edges,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
            "checked_at": self.checked_at,
        }


# ===========================================================================
# 3. NETWORK PATH INTELLIGENCE MODELS (WP 6.3)
# ===========================================================================

class PathReasoningMode(str, Enum):
    RIB_INFERRED = "RIB_INFERRED"
    FIB_CONFIRMED = "FIB_CONFIRMED"
    OBSERVED_FORWARDING = "OBSERVED_FORWARDING"
    PARTIAL_PATH = "PARTIAL_PATH"
    UNKNOWN_PATH = "UNKNOWN_PATH"


@dataclass
class PathHopExplanation:
    hop_index: int
    device_id: str
    device_name: str
    routing_table: str
    vrf: str
    matched_prefix: Optional[str] = None
    selected_route_summary: str = ""
    selection_reason: str = ""
    administrative_distance: Optional[int] = None
    protocol: str = ""
    next_hop_ip: Optional[str] = None
    next_hop_resolution: str = ""
    recursive_chain: List[str] = field(default_factory=list)
    egress_interface: Optional[str] = None
    egress_oper_status: str = "unknown"
    next_device_id: Optional[str] = None
    ecmp_gateways: List[str] = field(default_factory=list)
    fib_confirmed: bool = False
    observed_forwarding: bool = False
    evidence_ids: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hop_index": self.hop_index,
            "device_id": self.device_id,
            "device_name": self.device_name,
            "routing_table": self.routing_table,
            "vrf": self.vrf,
            "matched_prefix": self.matched_prefix,
            "selected_route_summary": self.selected_route_summary,
            "selection_reason": self.selection_reason,
            "administrative_distance": self.administrative_distance,
            "protocol": self.protocol,
            "next_hop_ip": self.next_hop_ip,
            "next_hop_resolution": self.next_hop_resolution,
            "recursive_chain": list(self.recursive_chain),
            "egress_interface": self.egress_interface,
            "egress_oper_status": self.egress_oper_status,
            "next_device_id": self.next_device_id,
            "ecmp_gateways": list(self.ecmp_gateways),
            "fib_confirmed": self.fib_confirmed,
            "observed_forwarding": self.observed_forwarding,
            "evidence_ids": list(self.evidence_ids),
            "warnings": list(self.warnings),
        }


@dataclass
class PathAnalysisResult:
    path_id: str
    source_device_id: Optional[str]
    source_ip: Optional[str]
    destination_ip: str
    destination_device_id: Optional[str]
    routing_table: str
    vrf: str
    mode: str  # PathReasoningMode
    outcome: str  # DELIVERED, PARTIAL_EXTERNAL, BLACKHOLED, UNREACHABLE, LOOP_DETECTED, UNRESOLVED_NEXT_HOP, EGRESS_DOWN, INSUFFICIENT_EVIDENCE
    is_directly_observed: bool
    hops: List[PathHopExplanation] = field(default_factory=list)
    candidate_paths: List[List[str]] = field(default_factory=list)
    asymmetric_return_detected: Optional[bool] = None
    asymmetric_notes: str = ""
    missing_evidence: List[str] = field(default_factory=list)
    evidence_ids: List[str] = field(default_factory=list)
    confidence_label: str = "MODERATE"
    confidence_score: float = 0.65
    explanation: str = ""
    analyzed_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path_id": self.path_id,
            "source_device_id": self.source_device_id,
            "source_ip": self.source_ip,
            "destination_ip": self.destination_ip,
            "destination_device_id": self.destination_device_id,
            "routing_table": self.routing_table,
            "vrf": self.vrf,
            "mode": self.mode,
            "outcome": self.outcome,
            "is_directly_observed": self.is_directly_observed,
            "hops": [h.to_dict() for h in self.hops],
            "candidate_paths": [list(p) for p in self.candidate_paths],
            "asymmetric_return_detected": self.asymmetric_return_detected,
            "asymmetric_notes": self.asymmetric_notes,
            "missing_evidence": list(self.missing_evidence),
            "evidence_ids": list(self.evidence_ids),
            "confidence_label": self.confidence_label,
            "confidence_score": round(float(self.confidence_score), 4),
            "explanation": self.explanation,
            "analyzed_at": self.analyzed_at,
        }


# ===========================================================================
# 4. CORRELATION, CONFIDENCE & ROOT CAUSE ANALYSIS MODELS (WP 6.4 & WP 6.5)
# ===========================================================================

class CorrelationDimension(str, Enum):
    DEVICE_IDENTITY = "device_identity"
    INTERFACE_IDENTITY = "interface_identity"
    SHARED_SUBNET = "shared_subnet"
    TOPOLOGY_DEPENDENCY = "topology_dependency"
    ROUTING_DEPENDENCY = "routing_dependency"
    NEXT_HOP_RELATIONSHIP = "next_hop_relationship"
    PROTOCOL_ADJACENCY = "protocol_adjacency"
    WAN_DEPENDENCY = "wan_dependency"
    VLAN_RELATIONSHIP = "vlan_relationship"
    TUNNEL_DEPENDENCY = "tunnel_dependency"
    TIME_WINDOW = "time_window"
    INCIDENT_TIMELINE = "incident_timeline"
    HISTORICAL_BEHAVIOR = "historical_behavior"


class HypothesisCategory(str, Enum):
    DEVICE_FAILURE = "DEVICE_FAILURE"
    INTERFACE_FAILURE = "INTERFACE_FAILURE"
    PHYSICAL_LINK_FAILURE = "PHYSICAL_LINK_FAILURE"
    LAYER2_FAILURE = "LAYER2_FAILURE"
    VLAN_MISMATCH = "VLAN_MISMATCH"
    ROUTING_FAILURE = "ROUTING_FAILURE"
    OSPF_FAILURE = "OSPF_FAILURE"
    BGP_FAILURE = "BGP_FAILURE"
    NEXT_HOP_FAILURE = "NEXT_HOP_FAILURE"
    WAN_DEGRADATION = "WAN_DEGRADATION"
    DNS_FAILURE = "DNS_FAILURE"
    DHCP_FAILURE = "DHCP_FAILURE"
    TUNNEL_FAILURE = "TUNNEL_FAILURE"
    RESOURCE_EXHAUSTION = "RESOURCE_EXHAUSTION"
    CONFIGURATION_CHANGE = "CONFIGURATION_CHANGE"
    TELEMETRY_FAILURE = "TELEMETRY_FAILURE"
    UNKNOWN = "UNKNOWN"


class FindingClassification(str, Enum):
    ROOT_CAUSE = "ROOT_CAUSE"
    CONTRIBUTING_FACTOR = "CONTRIBUTING_FACTOR"
    SECONDARY_SYMPTOM = "SECONDARY_SYMPTOM"
    CORRELATED_EVENT = "CORRELATED_EVENT"
    UNKNOWN_CAUSE = "UNKNOWN_CAUSE"


class ConfidenceLabel(str, Enum):
    VERY_HIGH = "VERY_HIGH"
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass
class ConfidenceAssessment:
    score: float
    label: str  # ConfidenceLabel
    factors: Dict[str, float] = field(default_factory=dict)
    rationale: List[str] = field(default_factory=list)
    is_calibrated_probability: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(float(self.score), 4),
            "label": self.label,
            "factors": {k: round(float(v), 4) for k, v in self.factors.items()},
            "rationale": list(self.rationale),
            "is_calibrated_probability": self.is_calibrated_probability,
        }


@dataclass
class CorrelationGroupResult:
    correlation_id: str
    investigation_window_sec: float
    dimensions_matched: List[str] = field(default_factory=list)
    related_observations: List[str] = field(default_factory=list)
    related_devices: List[str] = field(default_factory=list)
    related_incidents: List[str] = field(default_factory=list)
    shared_dependency: Optional[str] = None
    candidate_explanation: str = ""
    supporting_evidence: List[str] = field(default_factory=list)
    contradictory_evidence: List[str] = field(default_factory=list)
    confidence: Optional[ConfidenceAssessment] = None
    missing_evidence: List[str] = field(default_factory=list)
    alternative_hypotheses: List[str] = field(default_factory=list)
    is_causal_candidate: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "correlation_id": self.correlation_id,
            "investigation_window_sec": self.investigation_window_sec,
            "dimensions_matched": list(self.dimensions_matched),
            "related_observations": list(self.related_observations),
            "related_devices": list(self.related_devices),
            "related_incidents": list(self.related_incidents),
            "shared_dependency": self.shared_dependency,
            "candidate_explanation": self.candidate_explanation,
            "supporting_evidence": list(self.supporting_evidence),
            "contradictory_evidence": list(self.contradictory_evidence),
            "confidence": self.confidence.to_dict() if self.confidence else None,
            "missing_evidence": list(self.missing_evidence),
            "alternative_hypotheses": list(self.alternative_hypotheses),
            "is_causal_candidate": self.is_causal_candidate,
        }


@dataclass
class RCAHypothesis:
    hypothesis_id: str
    category: str  # HypothesisCategory
    classification: str  # FindingClassification
    title: str
    description: str
    root_entity_id: Optional[str] = None
    affected_scope: List[str] = field(default_factory=list)
    supporting_evidence: List[str] = field(default_factory=list)
    contradictory_evidence: List[str] = field(default_factory=list)
    expected_observations: List[str] = field(default_factory=list)
    missing_observations: List[str] = field(default_factory=list)
    confidence: Optional[ConfidenceAssessment] = None
    status: str = "CANDIDATE"  # LEADING_HYPOTHESIS, CANDIDATE, WEAKENED_BY_CONTRADICTION, INSUFFICIENT_EVIDENCE
    alternative_explanations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "category": self.category,
            "classification": self.classification,
            "title": self.title,
            "description": self.description,
            "root_entity_id": self.root_entity_id,
            "affected_scope": list(self.affected_scope),
            "supporting_evidence": list(self.supporting_evidence),
            "contradictory_evidence": list(self.contradictory_evidence),
            "expected_observations": list(self.expected_observations),
            "missing_observations": list(self.missing_observations),
            "confidence": self.confidence.to_dict() if self.confidence else None,
            "status": self.status,
            "alternative_explanations": list(self.alternative_explanations),
        }


@dataclass
class RCATimelineEvent:
    timestamp: float
    event_type: str  # INCIDENT_START, DEVICE_STATE, ROUTE_CHANGE, PROTOCOL_CHANGE, ALERT, OBSERVATION, RECOVERY
    entity_id: str
    summary: str
    classification: str = FindingClassification.CORRELATED_EVENT.value
    evidence_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "entity_id": self.entity_id,
            "summary": self.summary,
            "classification": self.classification,
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass
class RCAReport:
    rca_id: str
    scope: str
    analyzed_at: float
    executive_summary: str
    technical_diagnosis: str
    most_likely_root_cause: Optional[RCAHypothesis]
    contributing_factors: List[Dict[str, Any]] = field(default_factory=list)
    secondary_symptoms: List[Dict[str, Any]] = field(default_factory=list)
    correlated_events: List[Dict[str, Any]] = field(default_factory=list)
    affected_devices: List[str] = field(default_factory=list)
    affected_services: List[str] = field(default_factory=list)
    timeline: List[RCATimelineEvent] = field(default_factory=list)
    supporting_evidence: List[str] = field(default_factory=list)
    contradictory_evidence: List[str] = field(default_factory=list)
    hypotheses: List[RCAHypothesis] = field(default_factory=list)
    alternative_hypotheses: List[RCAHypothesis] = field(default_factory=list)
    confidence: Optional[ConfidenceAssessment] = None
    missing_evidence: List[str] = field(default_factory=list)
    recommended_investigation_steps: List[str] = field(default_factory=list)
    proposed_remediation_review_only: List[Dict[str, Any]] = field(default_factory=list)
    pipeline_steps_completed: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rca_id": self.rca_id,
            "scope": self.scope,
            "analyzed_at": self.analyzed_at,
            "executive_summary": self.executive_summary,
            "technical_diagnosis": self.technical_diagnosis,
            "most_likely_root_cause": self.most_likely_root_cause.to_dict() if self.most_likely_root_cause else None,
            "contributing_factors": list(self.contributing_factors),
            "secondary_symptoms": list(self.secondary_symptoms),
            "correlated_events": list(self.correlated_events),
            "affected_devices": list(self.affected_devices),
            "affected_services": list(self.affected_services),
            "timeline": [t.to_dict() for t in self.timeline],
            "supporting_evidence": list(self.supporting_evidence),
            "contradictory_evidence": list(self.contradictory_evidence),
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "alternative_hypotheses": [h.to_dict() for h in self.alternative_hypotheses],
            "confidence": self.confidence.to_dict() if self.confidence else None,
            "missing_evidence": list(self.missing_evidence),
            "recommended_investigation_steps": list(self.recommended_investigation_steps),
            "proposed_remediation_review_only": list(self.proposed_remediation_review_only),
            "pipeline_steps_completed": list(self.pipeline_steps_completed),
        }


# ===========================================================================
# 5. HEALTH, BASELINES & ANOMALY MODELS (WP 6.6)
# ===========================================================================

class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass
class DimensionHealthScore:
    dimension: str
    status: str  # HealthStatus
    score: Optional[float]  # 0.0-100.0 when measurable; None when UNKNOWN/INSUFFICIENT_DATA
    measured_entities: int = 0
    missing_entities: int = 0
    reasons: List[str] = field(default_factory=list)
    evidence_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dimension": self.dimension,
            "status": self.status,
            "score": round(float(self.score), 2) if self.score is not None else None,
            "measured_entities": self.measured_entities,
            "missing_entities": self.missing_entities,
            "reasons": list(self.reasons),
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass
class MetricBaselineRecord:
    baseline_id: str
    entity_key: str
    device_id: str
    metric_name: str
    version: int
    sample_count: int
    median_value: float
    mad_value: float
    ewma_value: float
    min_value: float
    max_value: float
    status: str = "ACTIVE"  # ACTIVE, INVALIDATED, INSUFFICIENT_SAMPLES
    invalidation_reason: str = ""
    last_uptime_sec: Optional[int] = None
    topology_ref: str = ""
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "baseline_id": self.baseline_id,
            "entity_key": self.entity_key,
            "device_id": self.device_id,
            "metric_name": self.metric_name,
            "version": self.version,
            "sample_count": self.sample_count,
            "median_value": round(float(self.median_value), 4),
            "mad_value": round(float(self.mad_value), 4),
            "ewma_value": round(float(self.ewma_value), 4),
            "min_value": round(float(self.min_value), 4),
            "max_value": round(float(self.max_value), 4),
            "status": self.status,
            "invalidation_reason": self.invalidation_reason,
            "last_uptime_sec": self.last_uptime_sec,
            "topology_ref": self.topology_ref,
            "updated_at": self.updated_at,
        }


@dataclass
class AnomalyObservation:
    anomaly_id: str
    device_id: str
    interface_name: Optional[str]
    entity_key: str
    metric_name: str
    anomaly_type: str  # BASELINE_DEVIATION, RATE_OF_CHANGE, ERROR_ACCELERATION, UTILIZATION_DEVIATION, PROTOCOL_INSTABILITY, TRAFFIC_PATTERN_DEVIATION
    severity: str  # info, warning, critical
    is_fault_candidate: bool
    what_changed: str
    began_at: float
    detected_at: float
    observed_value: float
    baseline_reference: Optional[Dict[str, Any]]
    unusualness_score: float
    evidence_ids: List[str] = field(default_factory=list)
    is_correlated: bool = False
    correlated_with: List[str] = field(default_factory=list)
    potentially_affected: List[str] = field(default_factory=list)
    additional_evidence_needed: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anomaly_id": self.anomaly_id,
            "device_id": self.device_id,
            "interface_name": self.interface_name,
            "entity_key": self.entity_key,
            "metric_name": self.metric_name,
            "anomaly_type": self.anomaly_type,
            "severity": self.severity,
            "is_fault_candidate": self.is_fault_candidate,
            "what_changed": self.what_changed,
            "began_at": self.began_at,
            "detected_at": self.detected_at,
            "observed_value": round(float(self.observed_value), 4),
            "baseline_reference": self.baseline_reference,
            "unusualness_score": round(float(self.unusualness_score), 4),
            "evidence_ids": list(self.evidence_ids),
            "is_correlated": self.is_correlated,
            "correlated_with": list(self.correlated_with),
            "potentially_affected": list(self.potentially_affected),
            "additional_evidence_needed": list(self.additional_evidence_needed),
        }


# ===========================================================================
# 6. IMPACT, SIMULATION, PROTOCOL & NLP MODELS (WP 6.7 – WP 6.11)
# ===========================================================================

class ImpactScopeType(str, Enum):
    OBSERVED_IMPACT = "OBSERVED_IMPACT"
    POTENTIAL_IMPACT = "POTENTIAL_IMPACT"


class RedundancyStatus(str, Enum):
    FULL_REDUNDANCY = "FULL_REDUNDANCY"
    PARTIAL_REDUNDANCY = "PARTIAL_REDUNDANCY"
    NO_REDUNDANCY = "NO_REDUNDANCY"
    UNKNOWN = "UNKNOWN"


@dataclass
class ImpactAnalysisResult:
    impact_id: str
    target_entity_id: str
    target_entity_type: str
    impact_scope_type: str  # ImpactScopeType
    direct_dependents: List[Dict[str, Any]] = field(default_factory=list)
    indirect_dependents: List[Dict[str, Any]] = field(default_factory=list)
    potentially_affected_subnets: List[str] = field(default_factory=list)
    potentially_affected_devices: List[str] = field(default_factory=list)
    affected_services: List[str] = field(default_factory=list)
    routing_dependencies: List[Dict[str, Any]] = field(default_factory=list)
    protocol_relationships: List[Dict[str, Any]] = field(default_factory=list)
    alternate_paths: List[Dict[str, Any]] = field(default_factory=list)
    redundancy_status: str = RedundancyStatus.UNKNOWN.value
    redundancy_notes: str = ""
    historical_incidents: List[Dict[str, Any]] = field(default_factory=list)
    confidence_score: float = 0.80
    confidence_label: str = "HIGH"
    evidence_ids: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    analyzed_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "impact_id": self.impact_id,
            "target_entity_id": self.target_entity_id,
            "target_entity_type": self.target_entity_type,
            "impact_scope_type": self.impact_scope_type,
            "direct_dependents": list(self.direct_dependents),
            "indirect_dependents": list(self.indirect_dependents),
            "potentially_affected_subnets": list(self.potentially_affected_subnets),
            "potentially_affected_devices": list(self.potentially_affected_devices),
            "affected_services": list(self.affected_services),
            "routing_dependencies": list(self.routing_dependencies),
            "protocol_relationships": list(self.protocol_relationships),
            "alternate_paths": list(self.alternate_paths),
            "redundancy_status": self.redundancy_status,
            "redundancy_notes": self.redundancy_notes,
            "historical_incidents": list(self.historical_incidents),
            "confidence_score": round(float(self.confidence_score), 4),
            "confidence_label": self.confidence_label,
            "evidence_ids": list(self.evidence_ids),
            "limitations": list(self.limitations),
            "analyzed_at": self.analyzed_at,
        }


@dataclass
class SimulationResult:
    simulation_id: str
    simulated_failure_type: str  # UPSTREAM_ROUTER_DOWN, WAN_ROUTE_LOSS, OSPF_NEIGHBOR_LOSS, BGP_PEER_WITHDRAWAL, TRUNK_LOSS, TUNNEL_DOWN
    simulated_entity_id: str
    is_simulation: bool = True  # Mandatory non-destructive flag
    affected_dependency_graph: Dict[str, Any] = field(default_factory=dict)
    potentially_unreachable_segments: List[str] = field(default_factory=list)
    potentially_isolated_devices: List[str] = field(default_factory=list)
    alternate_paths_available: List[Dict[str, Any]] = field(default_factory=list)
    redundancy_findings: str = ""
    assumptions: List[str] = field(default_factory=list)
    unknown_dependencies: List[str] = field(default_factory=list)
    confidence_score: float = 0.85
    confidence_label: str = "HIGH"
    evidence_ids: List[str] = field(default_factory=list)
    simulated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "is_simulation": self.is_simulation,
            "simulated_failure_type": self.simulated_failure_type,
            "simulated_entity_id": self.simulated_entity_id,
            "affected_dependency_graph": dict(self.affected_dependency_graph),
            "potentially_unreachable_segments": list(self.potentially_unreachable_segments),
            "potentially_isolated_devices": list(self.potentially_isolated_devices),
            "alternate_paths_available": list(self.alternate_paths_available),
            "redundancy_findings": self.redundancy_findings,
            "assumptions": list(self.assumptions),
            "unknown_dependencies": list(self.unknown_dependencies),
            "confidence_score": round(float(self.confidence_score), 4),
            "confidence_label": self.confidence_label,
            "evidence_ids": list(self.evidence_ids),
            "simulated_at": self.simulated_at,
        }


class BGPPrefixLifecycleState(str, Enum):
    SESSION_ESTABLISHED = "SESSION_ESTABLISHED"
    ROUTE_RECEIVED = "ROUTE_RECEIVED"
    ROUTE_ACCEPTED = "ROUTE_ACCEPTED"
    ROUTE_SELECTED = "ROUTE_SELECTED"
    ROUTE_INSTALLED = "ROUTE_INSTALLED"
    FORWARDING_VERIFIED = "FORWARDING_VERIFIED"


class InvestigationIntent(str, Enum):
    NETWORK_OVERVIEW = "NETWORK_OVERVIEW"
    DEVICE_INVESTIGATION = "DEVICE_INVESTIGATION"
    INTERFACE_INVESTIGATION = "INTERFACE_INVESTIGATION"
    ROUTE_INVESTIGATION = "ROUTE_INVESTIGATION"
    PATH_ANALYSIS = "PATH_ANALYSIS"
    PROTOCOL_ANALYSIS = "PROTOCOL_ANALYSIS"
    INCIDENT_INVESTIGATION = "INCIDENT_INVESTIGATION"
    ROOT_CAUSE_ANALYSIS = "ROOT_CAUSE_ANALYSIS"
    HEALTH_ASSESSMENT = "HEALTH_ASSESSMENT"
    ANOMALY_INVESTIGATION = "ANOMALY_INVESTIGATION"
    CHANGE_IMPACT = "CHANGE_IMPACT"
    FAILURE_SIMULATION = "FAILURE_SIMULATION"
    HISTORICAL_COMPARISON = "HISTORICAL_COMPARISON"
    NETWORK_CONCEPT_EXPLANATION = "NETWORK_CONCEPT_EXPLANATION"


@dataclass
class InvestigationPlan:
    plan_id: str
    question: str
    intent: str  # InvestigationIntent
    target_entities: Dict[str, Any] = field(default_factory=dict)
    required_evidence: List[str] = field(default_factory=list)
    reusable_evidence: List[str] = field(default_factory=list)
    missing_evidence: List[str] = field(default_factory=list)
    required_analyzers: List[str] = field(default_factory=list)
    time_window_sec: float = 900.0
    resource_budget: Dict[str, Any] = field(default_factory=dict)
    expected_output: str = ""
    is_valid: bool = True
    validation_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "question": self.question,
            "intent": self.intent,
            "target_entities": dict(self.target_entities),
            "required_evidence": list(self.required_evidence),
            "reusable_evidence": list(self.reusable_evidence),
            "missing_evidence": list(self.missing_evidence),
            "required_analyzers": list(self.required_analyzers),
            "time_window_sec": self.time_window_sec,
            "resource_budget": dict(self.resource_budget),
            "expected_output": self.expected_output,
            "is_valid": self.is_valid,
            "validation_notes": list(self.validation_notes),
        }


@dataclass
class GroundedAIExplanation:
    generation_mode: str  # LLM_GROUNDED, DETERMINISTIC_FALLBACK
    summary: str
    confirmed_facts: List[Dict[str, Any]] = field(default_factory=list)
    inferences: List[Dict[str, Any]] = field(default_factory=list)
    hypotheses: List[Dict[str, Any]] = field(default_factory=list)
    contradictions: List[str] = field(default_factory=list)
    missing_evidence: List[str] = field(default_factory=list)
    explanation: str = ""
    recommended_next_steps: List[str] = field(default_factory=list)
    model_used: str = "deterministic"
    validation_warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generation_mode": self.generation_mode,
            "summary": self.summary,
            "confirmed_facts": list(self.confirmed_facts),
            "inferences": list(self.inferences),
            "hypotheses": list(self.hypotheses),
            "contradictions": list(self.contradictions),
            "missing_evidence": list(self.missing_evidence),
            "explanation": self.explanation,
            "recommended_next_steps": list(self.recommended_next_steps),
            "model_used": self.model_used,
            "validation_warnings": list(self.validation_warnings),
        }
