"""
AIRA OS — Proactive Network Operations Domain Models (Networking VII).

Defines canonical dataclasses and enums for:
1. Predictive operations and trend forecasting (WP 7.1).
2. Change impact intelligence and simulations (WP 7.2).
3. Service dependency mappings (WP 7.3).
4. Operational scheduler and job runs (WP 7.4).
5. Maintenance windows and calendar synchronization (WP 7.5).
6. Proactive incident lifecycle (WP 7.6).
7. Notifications and quiet hours (WP 7.7).
8. Operational reports (WP 7.8).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import time
from typing import Any, Dict, List, Optional, Set
import uuid


class RiskLevel(str, Enum):
    """Canonical risk classification for operational health and forecasts."""
    INFO = "INFO"          # Headroom > 30 days, normal variation
    WATCH = "WATCH"        # Mild upward trend, projected warning in 7-30 days
    WARNING = "WARNING"    # Moderate/rapid trend, projected breach in 1-7 days (24-168h)
    CRITICAL = "CRITICAL"  # Urgent breach projected in < 24h or current utilization >= 90%
    UNKNOWN = "UNKNOWN"    # Insufficient telemetry or high volatility


class TimeWindow(str, Enum):
    """Canonical multi-window analysis scopes."""
    ONE_HOUR = "1h"
    SIX_HOURS = "6h"
    TWENTY_FOUR_HOURS = "24h"
    SEVEN_DAYS = "7d"
    THIRTY_DAYS = "30d"


class TrendDirection(str, Enum):
    """Directional velocity of the observed time series."""
    RAPID_INCREASE = "RAPID_INCREASE"
    MODERATE_INCREASE = "MODERATE_INCREASE"
    STABLE = "STABLE"
    MODERATE_DECREASE = "MODERATE_DECREASE"
    RAPID_DECREASE = "RAPID_DECREASE"
    ERRATIC = "ERRATIC"
    UNKNOWN = "UNKNOWN"


class PredictionStatus(str, Enum):
    """Epistemic status of a predictive projection."""
    VALID = "VALID"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NON_STATIONARY = "NON_STATIONARY"
    INSUFFICIENT_VARIATION = "INSUFFICIENT_VARIATION"


class ServiceCriticality(str, Enum):
    """Business criticality tiers for network services."""
    TIER_1_MISSION_CRITICAL = "TIER_1_MISSION_CRITICAL"
    TIER_2_BUSINESS_OPERATIONAL = "TIER_2_BUSINESS_OPERATIONAL"
    TIER_3_OFFICE_PRODUCTIVITY = "TIER_3_OFFICE_PRODUCTIVITY"
    TIER_4_DEVELOPMENT_TEST = "TIER_4_DEVELOPMENT_TEST"


class ServiceHealthStatus(str, Enum):
    """Real-time operational health of a business service."""
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    AT_RISK = "AT_RISK"
    DOWN = "DOWN"
    UNKNOWN = "UNKNOWN"


class JobScheduleType(str, Enum):
    """Operational job schedule types."""
    CRON = "CRON"
    INTERVAL = "INTERVAL"
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


class MissedJobStrategy(str, Enum):
    """Policy for handling missed executions during downtime."""
    RUN_IMMEDIATELY = "RUN_IMMEDIATELY"
    SKIP = "SKIP"
    RESCHEDULE = "RESCHEDULE"


class JobRunStatus(str, Enum):
    """Execution status of an operational job run."""
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class MaintenanceScopeType(str, Enum):
    """Target scope of a maintenance window."""
    DEVICE = "DEVICE"
    SERVICE = "SERVICE"
    INTERFACE = "INTERFACE"
    GLOBAL = "GLOBAL"


class MaintenanceStatus(str, Enum):
    """Lifecycle state of a maintenance window."""
    SCHEDULED = "SCHEDULED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class IncidentState(str, Enum):
    """Lifecycle state machine for proactive operational incidents."""
    DETECTED = "DETECTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATING = "INVESTIGATING"
    MITIGATED = "MITIGATED"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class IncidentSeverity(str, Enum):
    """Severity classification for proactive incidents."""
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class NotificationDeliveryStatus(str, Enum):
    """Delivery status of an operational notification."""
    SENT = "SENT"
    QUEUED_QUIET_HOURS = "QUEUED_QUIET_HOURS"
    SUPPRESSED_COOLDOWN = "SUPPRESSED_COOLDOWN"


# ---------------------------------------------------------------------------
# WP 7.1: Predictive Operations Models
# ---------------------------------------------------------------------------

@dataclass
class PredictiveMetricProjection:
    """Predictive forecast for a single metric on a device or interface."""
    metric_name: str
    entity_type: str                     # e.g., 'interface', 'device', 'route'
    entity_id: str                       # e.g., 'ether1', 'R-1'
    device_id: str
    current_value: Optional[float]
    sample_count: int
    window: str                          # e.g., '24h', '7d'
    trend_direction: str                 # TrendDirection
    slope_per_hour: Optional[float]
    slope_per_day: Optional[float]
    r_squared: Optional[float]
    p95_value: Optional[float]
    max_value: Optional[float]
    warning_threshold: float
    critical_threshold: float
    hours_to_warning: Optional[float]    # None if slope <= 0 or current >= threshold
    hours_to_critical: Optional[float]
    days_to_warning: Optional[float]
    days_to_critical: Optional[float]
    risk_level: str                      # RiskLevel
    status: str                          # PredictionStatus
    confidence_score: float              # 0.0 to 1.0
    confidence_level: str                # HIGH, MEDIUM, LOW, UNKNOWN
    assumptions: List[str] = field(default_factory=list)
    epistemic_limitations: List[str] = field(default_factory=list)
    recommended_action: Optional[str] = None
    projection_id: str = field(default_factory=lambda: f"pred_{uuid.uuid4().hex[:10]}")
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "projection_id": self.projection_id,
            "metric_name": self.metric_name,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "device_id": self.device_id,
            "current_value": self.current_value,
            "sample_count": self.sample_count,
            "window": self.window,
            "trend_direction": self.trend_direction,
            "slope_per_hour": self.slope_per_hour,
            "slope_per_day": self.slope_per_day,
            "r_squared": self.r_squared,
            "p95_value": self.p95_value,
            "max_value": self.max_value,
            "warning_threshold": self.warning_threshold,
            "critical_threshold": self.critical_threshold,
            "hours_to_warning": self.hours_to_warning,
            "hours_to_critical": self.hours_to_critical,
            "days_to_warning": self.days_to_warning,
            "days_to_critical": self.days_to_critical,
            "risk_level": self.risk_level,
            "status": self.status,
            "confidence_score": self.confidence_score,
            "confidence_level": self.confidence_level,
            "assumptions": self.assumptions,
            "epistemic_limitations": self.epistemic_limitations,
            "recommended_action": self.recommended_action,
            "created_at": self.created_at,
        }


@dataclass
class PredictiveAnalysisReport:
    """Aggregated predictive operations report across network entities."""
    report_id: str
    analyzed_at: str
    projections: List[PredictiveMetricProjection]
    highest_risk_level: str
    summary: str
    risk_counts: Dict[str, int]
    action_items: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "analyzed_at": self.analyzed_at,
            "highest_risk_level": self.highest_risk_level,
            "summary": self.summary,
            "risk_counts": self.risk_counts,
            "action_items": self.action_items,
            "projections_count": len(self.projections),
            "projections": [p.to_dict() for p in self.projections],
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# WP 7.2: Change Impact Models
# ---------------------------------------------------------------------------

@dataclass
class ChangeScenarioRequest:
    """Operator change request to simulate in memory."""
    scenario_id: str
    title: str
    change_type: str                     # 'INTERFACE_DOWN', 'ROUTE_WITHDRAWAL', 'VLAN_REMOVE', 'DEVICE_REBOOT'
    target_device: str
    target_entity: str                   # interface name, CIDR, VLAN ID
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DetailedChangeImpactReport:
    """Analytical blast radius and impact assessment of a change request."""
    scenario_id: str
    title: str
    change_type: str
    target_device: str
    target_entity: str
    is_simulation: bool = True
    severity: str = "INFO"               # INFO, LOW, MEDIUM, HIGH, CRITICAL
    directly_impacted_devices: List[str] = field(default_factory=list)
    directly_impacted_subnets: List[str] = field(default_factory=list)
    indirectly_impacted_devices: List[str] = field(default_factory=list)
    affected_services: List[Dict[str, Any]] = field(default_factory=list)
    severed_transit_paths: List[Dict[str, Any]] = field(default_factory=list)
    alternate_paths_available: List[Dict[str, Any]] = field(default_factory=list)
    redundancy_losses: List[str] = field(default_factory=list)
    projected_secondary_link_loads: List[Dict[str, Any]] = field(default_factory=list)
    preflight_checklist: List[str] = field(default_factory=list)
    rollback_plan: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "title": self.title,
            "change_type": self.change_type,
            "target_device": self.target_device,
            "target_entity": self.target_entity,
            "is_simulation": self.is_simulation,
            "severity": self.severity,
            "directly_impacted_devices": self.directly_impacted_devices,
            "directly_impacted_subnets": self.directly_impacted_subnets,
            "indirectly_impacted_devices": self.indirectly_impacted_devices,
            "affected_services": self.affected_services,
            "severed_transit_paths": self.severed_transit_paths,
            "alternate_paths_available": self.alternate_paths_available,
            "redundancy_losses": self.redundancy_losses,
            "projected_secondary_link_loads": self.projected_secondary_link_loads,
            "preflight_checklist": self.preflight_checklist,
            "rollback_plan": self.rollback_plan,
            "assumptions": self.assumptions,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# WP 7.3: Service Dependency Models
# ---------------------------------------------------------------------------

@dataclass
class ServiceEndpointRecord:
    """Network endpoint associated with a business service."""
    endpoint_id: str
    service_id: str
    endpoint_type: str                   # 'IP_PORT', 'SUBNET', 'VLAN', 'URL', 'HOSTNAME'
    endpoint_value: str                  # e.g., '192.168.1.100:443', '10.0.0.0/24'
    target_device_id: Optional[str] = None
    target_interface: Optional[str] = None
    is_primary: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "endpoint_id": self.endpoint_id,
            "service_id": self.service_id,
            "endpoint_type": self.endpoint_type,
            "endpoint_value": self.endpoint_value,
            "target_device_id": self.target_device_id,
            "target_interface": self.target_interface,
            "is_primary": self.is_primary,
            "created_at": self.created_at,
        }


@dataclass
class BusinessServiceRecord:
    """Catalog record for a business service."""
    service_id: str
    name: str
    description: str
    criticality: str                     # ServiceCriticality
    owner_team: str
    health_score: float = 100.0
    status: str = ServiceHealthStatus.HEALTHY.value
    endpoints: List[ServiceEndpointRecord] = field(default_factory=list)
    metadata_json: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service_id": self.service_id,
            "name": self.name,
            "description": self.description,
            "criticality": self.criticality,
            "owner_team": self.owner_team,
            "health_score": self.health_score,
            "status": self.status,
            "endpoints": [ep.to_dict() for ep in self.endpoints],
            "metadata_json": self.metadata_json,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ---------------------------------------------------------------------------
# WP 7.4 & 7.5: Scheduler & Calendar Models
# ---------------------------------------------------------------------------

@dataclass
class OperationalJobRecord:
    """Definition of an operational scheduled job."""
    job_id: str
    name: str
    job_type: str                        # 'HEALTH_AUDIT', 'CAPACITY_FORECAST', 'CERT_CHECK', 'ROUTE_AUDIT'
    description: str
    schedule_type: str                   # JobScheduleType
    schedule_expression: str             # e.g., '0 8 * * *', '3600'
    timezone: str = "Asia/Jakarta"
    is_enabled: bool = True
    missed_strategy: str = MissedJobStrategy.RUN_IMMEDIATELY.value
    parameters_json: Dict[str, Any] = field(default_factory=dict)
    last_run_at: Optional[str] = None
    last_status: Optional[str] = None
    next_due_at: Optional[str] = None
    consecutive_failures: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "name": self.name,
            "job_type": self.job_type,
            "description": self.description,
            "schedule_type": self.schedule_type,
            "schedule_expression": self.schedule_expression,
            "timezone": self.timezone,
            "is_enabled": self.is_enabled,
            "missed_strategy": self.missed_strategy,
            "parameters_json": self.parameters_json,
            "last_run_at": self.last_run_at,
            "last_status": self.last_status,
            "next_due_at": self.next_due_at,
            "consecutive_failures": self.consecutive_failures,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class OperationalJobRunRecord:
    """Historical execution record of an operational job."""
    run_id: str
    job_id: str
    trigger_type: str                    # 'SCHEDULED', 'MANUAL', 'MISSED_RECOVERY'
    started_at: str
    completed_at: Optional[str] = None
    status: str = JobRunStatus.RUNNING.value
    duration_ms: Optional[int] = None
    result_summary: Optional[str] = None
    result_data_json: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "job_id": self.job_id,
            "trigger_type": self.trigger_type,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "result_summary": self.result_summary,
            "result_data_json": self.result_data_json,
            "error_message": self.error_message,
        }


@dataclass
class MaintenanceWindowRecord:
    """Scheduled network maintenance window."""
    window_id: str
    title: str
    description: str
    source_provider: str                 # 'LOCAL', 'GOOGLE', 'ICS'
    external_event_id: Optional[str]
    scope_type: str                      # MaintenanceScopeType
    target_entities: List[str]           # Device IDs, service IDs, interface names
    start_time_utc: str
    end_time_utc: str
    start_time_local: str                # Asia/Jakarta
    end_time_local: str
    status: str = MaintenanceStatus.SCHEDULED.value
    suppress_alerts: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "window_id": self.window_id,
            "title": self.title,
            "description": self.description,
            "source_provider": self.source_provider,
            "external_event_id": self.external_event_id,
            "scope_type": self.scope_type,
            "target_entities": self.target_entities,
            "start_time_utc": self.start_time_utc,
            "end_time_utc": self.end_time_utc,
            "start_time_local": self.start_time_local,
            "end_time_local": self.end_time_local,
            "status": self.status,
            "suppress_alerts": self.suppress_alerts,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ---------------------------------------------------------------------------
# WP 7.6 & 7.7: Proactive Incident & Notification Models
# ---------------------------------------------------------------------------

@dataclass
class ProactiveIncidentRecord:
    """Proactive operational incident tracking preventative remediation."""
    incident_id: str
    title: str
    severity: str                        # IncidentSeverity
    state: str = IncidentState.DETECTED.value
    source_engine: str = "PREDICTIVE"    # 'PREDICTIVE', 'ANOMALY', 'CHANGE_SIMULATION', 'MANUAL'
    affected_services: List[str] = field(default_factory=list)
    affected_devices: List[str] = field(default_factory=list)
    summary: str = ""
    root_cause_analysis: Optional[str] = None
    remediation_plan: Optional[str] = None
    evidence_ids: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "title": self.title,
            "severity": self.severity,
            "state": self.state,
            "source_engine": self.source_engine,
            "affected_services": self.affected_services,
            "affected_devices": self.affected_devices,
            "summary": self.summary,
            "root_cause_analysis": self.root_cause_analysis,
            "remediation_plan": self.remediation_plan,
            "evidence_ids": self.evidence_ids,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "resolved_at": self.resolved_at,
        }


@dataclass
class OperationalNotificationRecord:
    """Notification entry for operational events."""
    notification_id: str
    category: str
    severity: str                        # IncidentSeverity
    title: str
    message: str
    dedup_key: str
    delivery_status: str = NotificationDeliveryStatus.SENT.value
    target_channels: List[str] = field(default_factory=lambda: ["IN_APP", "WEBSOCKET"])
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_read: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "notification_id": self.notification_id,
            "category": self.category,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "dedup_key": self.dedup_key,
            "delivery_status": self.delivery_status,
            "target_channels": self.target_channels,
            "metadata": self.metadata,
            "is_read": self.is_read,
            "created_at": self.created_at,
        }


# ===========================================================================
# NETWORKING VIII / PHASE C: OPERATIONAL DECISION INTELLIGENCE & SLA MODELS
# ===========================================================================

class DecisionStatus(str, Enum):
    """Lifecycle status of an operational decision."""
    GENERATED = "GENERATED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"
    EXPIRED = "EXPIRED"
    COMPLETED = "COMPLETED"
    VERIFIED = "VERIFIED"


VALID_DECISION_TRANSITIONS: Dict[str, Set[str]] = {
    DecisionStatus.GENERATED.value: {
        DecisionStatus.UNDER_REVIEW.value,
        DecisionStatus.EXPIRED.value,
        DecisionStatus.REJECTED.value,
    },
    DecisionStatus.UNDER_REVIEW.value: {
        DecisionStatus.APPROVED.value,
        DecisionStatus.REJECTED.value,
        DecisionStatus.DEFERRED.value,
    },
    DecisionStatus.DEFERRED.value: {
        DecisionStatus.UNDER_REVIEW.value,
        DecisionStatus.EXPIRED.value,
        DecisionStatus.REJECTED.value,
    },
    DecisionStatus.APPROVED.value: {
        DecisionStatus.COMPLETED.value,
        DecisionStatus.REJECTED.value,
    },
    DecisionStatus.COMPLETED.value: {
        DecisionStatus.VERIFIED.value,
        DecisionStatus.UNDER_REVIEW.value,
    },
    DecisionStatus.VERIFIED.value: {
        DecisionStatus.UNDER_REVIEW.value,
    },
    DecisionStatus.REJECTED.value: set(),
    DecisionStatus.EXPIRED.value: set(),
}


@dataclass
class RecommendationAlternative:
    """An alternative remediation strategy with explicit tradeoffs."""
    alternative_id: str
    title: str
    description: str
    risk_level: str                         # RiskLevel
    tradeoffs: List[str] = field(default_factory=list)
    is_preferred: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alternative_id": self.alternative_id,
            "title": self.title,
            "description": self.description,
            "risk_level": self.risk_level,
            "tradeoffs": self.tradeoffs,
            "is_preferred": self.is_preferred,
        }


@dataclass
class DecisionRecommendation:
    """Actionable recommendation structure with human verification checklist."""
    recommendation_id: str
    title: str
    summary: str
    safest_action: str
    alternatives: List[RecommendationAlternative] = field(default_factory=list)
    human_verification_checklist: List[str] = field(default_factory=list)
    requires_approval: bool = True
    approval_role: str = "NOC_OPERATOR"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "title": self.title,
            "summary": self.summary,
            "safest_action": self.safest_action,
            "alternatives": [a.to_dict() for a in self.alternatives],
            "human_verification_checklist": self.human_verification_checklist,
            "requires_approval": self.requires_approval,
            "approval_role": self.approval_role,
        }


@dataclass
class DecisionAssessment:
    """Grounded assessment synthesizing RCA, health, capacity, and uncertainties."""
    problem_statement: str
    root_cause_hypotheses: List[Dict[str, Any]] = field(default_factory=list)
    supporting_evidence_ids: List[str] = field(default_factory=list)
    contradictory_evidence_ids: List[str] = field(default_factory=list)
    missing_evidence_ids: List[str] = field(default_factory=list)
    confidence_score: float = 0.0           # 0.0 - 1.0
    epistemic_status: str = "INSUFFICIENT_EVIDENCE" # CONFIRMED_BY_EVIDENCE, HYPOTHESIS_SUPPORTED, INSUFFICIENT_EVIDENCE
    uncertainty_factors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "problem_statement": self.problem_statement,
            "root_cause_hypotheses": self.root_cause_hypotheses,
            "supporting_evidence_ids": self.supporting_evidence_ids,
            "contradictory_evidence_ids": self.contradictory_evidence_ids,
            "missing_evidence_ids": self.missing_evidence_ids,
            "confidence_score": round(self.confidence_score, 3),
            "epistemic_status": self.epistemic_status,
            "uncertainty_factors": self.uncertainty_factors,
        }


@dataclass
class OperationalDecision:
    """Core decision intelligence entity (WP 8.5)."""
    decision_id: str
    tenant_id: str
    title: str
    priority_score: float                   # 0.0 - 100.0
    risk_level: str                         # RiskLevel
    status: str = DecisionStatus.GENERATED.value
    site_id: Optional[str] = None
    affected_services: List[str] = field(default_factory=list)
    affected_devices: List[str] = field(default_factory=list)
    assessment: DecisionAssessment = field(default_factory=lambda: DecisionAssessment(problem_statement=""))
    recommendation: DecisionRecommendation = field(default_factory=lambda: DecisionRecommendation(
        recommendation_id="", title="", summary="", safest_action=""
    ))
    sla_impact_assessment: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "tenant_id": self.tenant_id,
            "site_id": self.site_id,
            "title": self.title,
            "priority_score": round(self.priority_score, 2),
            "risk_level": self.risk_level,
            "status": self.status,
            "affected_services": self.affected_services,
            "affected_devices": self.affected_devices,
            "assessment": self.assessment.to_dict() if hasattr(self.assessment, "to_dict") else self.assessment,
            "recommendation": self.recommendation.to_dict() if hasattr(self.recommendation, "to_dict") else self.recommendation,
            "sla_impact_assessment": self.sla_impact_assessment,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "updated_at": self.updated_at,
        }


@dataclass
class DecisionHistoryRecord:
    """Audit record for decision state transitions."""
    history_id: str
    decision_id: str
    tenant_id: str
    actor: str
    from_status: str
    to_status: str
    reason: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "history_id": self.history_id,
            "decision_id": self.decision_id,
            "tenant_id": self.tenant_id,
            "actor": self.actor,
            "from_status": self.from_status,
            "to_status": self.to_status,
            "reason": self.reason,
            "created_at": self.created_at,
        }


# ===========================================================================
# HEALTH SCORING MODELS (WP 8.5.1)
# ===========================================================================

class HealthDimensionType(str, Enum):
    DEVICE = "DEVICE"
    INTERFACE = "INTERFACE"
    SITE = "SITE"
    SERVICE = "SERVICE"
    GATEWAY = "GATEWAY"
    TENANT = "TENANT"


class HealthScoreState(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass
class OperationalHealthScoreRecord:
    """Individual health scoring record."""
    score_id: str
    tenant_id: str
    dimension: str                          # HealthDimensionType
    entity_id: str
    state: str                              # HealthScoreState
    score: Optional[float]                  # None if UNKNOWN or INSUFFICIENT_DATA
    site_id: Optional[str] = None
    confidence: float = 1.0
    contributing_factors: List[str] = field(default_factory=list)
    missing_dimensions: List[str] = field(default_factory=list)
    calculated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score_id": self.score_id,
            "tenant_id": self.tenant_id,
            "site_id": self.site_id,
            "dimension": self.dimension,
            "entity_id": self.entity_id,
            "state": self.state,
            "score": round(self.score, 2) if self.score is not None else None,
            "confidence": round(self.confidence, 3),
            "contributing_factors": self.contributing_factors,
            "missing_dimensions": self.missing_dimensions,
            "calculated_at": self.calculated_at,
        }


# ===========================================================================
# SLA & SERVICE MODELS (WP 8.7)
# ===========================================================================

class SlaWindowType(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    ROLLING_30D = "ROLLING_30D"


class SlaStatusType(str, Enum):
    COMPLIANT = "COMPLIANT"
    AT_RISK = "AT_RISK"
    BREACHED = "BREACHED"
    INSUFFICIENT_COVERAGE = "INSUFFICIENT_COVERAGE"


@dataclass
class SlaPolicyRecord:
    """SLA policy definition for a customer business service."""
    policy_id: str
    tenant_id: str
    service_id: str
    name: str
    target_availability: float = 99.9
    target_response_time_ms: float = 150.0
    target_mttr_minutes: int = 60
    window_type: str = SlaWindowType.MONTHLY.value
    maintenance_excluded: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "tenant_id": self.tenant_id,
            "service_id": self.service_id,
            "name": self.name,
            "target_availability": self.target_availability,
            "target_response_time_ms": self.target_response_time_ms,
            "target_mttr_minutes": self.target_mttr_minutes,
            "window_type": self.window_type,
            "maintenance_excluded": self.maintenance_excluded,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class SlaReportRecord:
    """Measured SLA report record."""
    report_id: str
    tenant_id: str
    service_id: str
    policy_id: str
    period_start_utc: str
    period_end_utc: str
    target_availability: float
    measured_availability: Optional[float]
    total_downtime_seconds: float
    maintenance_excluded_seconds: float
    data_coverage_percent: float
    status: str                             # SlaStatusType
    error_budget_remaining_percent: Optional[float]
    incident_count: int = 0
    details: Dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "tenant_id": self.tenant_id,
            "service_id": self.service_id,
            "policy_id": self.policy_id,
            "period_start_utc": self.period_start_utc,
            "period_end_utc": self.period_end_utc,
            "target_availability": self.target_availability,
            "measured_availability": round(self.measured_availability, 3) if self.measured_availability is not None else None,
            "total_downtime_seconds": round(self.total_downtime_seconds, 1),
            "maintenance_excluded_seconds": round(self.maintenance_excluded_seconds, 1),
            "data_coverage_percent": round(self.data_coverage_percent, 2),
            "status": self.status,
            "error_budget_remaining_percent": round(self.error_budget_remaining_percent, 2) if self.error_budget_remaining_percent is not None else None,
            "incident_count": self.incident_count,
            "details": self.details,
            "generated_at": self.generated_at,
        }
