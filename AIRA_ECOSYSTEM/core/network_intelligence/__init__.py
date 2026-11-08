"""
core/network_intelligence — AIRA Network Intelligence, Incident Investigation,
Diagnostic Playbooks, and Configuration Planning & Simulation.
"""

from core.network_intelligence.models import (
    ConfidenceLevel,
    ConfigurationPlan,
    DiagnosticPlaybook,
    EvidenceFreshness,
    EvidenceItem,
    EvidenceState,
    IncidentRecord,
    IncidentType,
    InvestigationStatus,
    PlanStatus,
    PlaybookRunRecord,
    PlaybookStatus,
    PlaybookStep,
    PreflightResult,
    PreflightStatus,
    RankedHypothesis,
    SeverityLevel,
    SimulationResult,
    ValidationFinding,
    ValidationSeverity,
)
from core.network_intelligence.preflight import LabPreflightChecker
from core.network_intelligence.security import (
    execute_safe_readonly_command,
    redact_sensitive_values,
    validate_readonly_command,
)
from core.network_intelligence.store import (
    NetworkIntelligenceStore,
    get_network_intelligence_store,
)
from core.network_intelligence.evidence import (
    EvidenceCollector,
    determine_freshness,
    sanitize_raw_output,
)
from core.network_intelligence.investigator import NetworkInvestigator, get_network_investigator
from core.network_intelligence.playbooks import PlaybookEngine
from core.network_intelligence.planner import ConfigurationPlanner
from core.network_intelligence.validator import StaticValidator
from core.network_intelligence.simulator import StaticSimulator

# Generation 3 Canonical Services & Models (REC-20)
from core.network_intelligence.intelligence_models import (
    NetworkEvidenceBundle,
    KnowledgeNode,
    KnowledgeEdge,
    IntelligenceFreshness,
    GraphEntityType,
    GraphRelationshipType,
    GraphLayer,
)
from core.network_intelligence.evidence_service import (
    UnifiedEvidenceService,
    get_unified_evidence_service,
)
from core.network_intelligence.correlation_engine import (
    MultiDeviceCorrelationEngine,
)
from core.network_intelligence.security_baseline import (
    SecurityBaselineEngine,
    get_security_baseline_engine,
)
from core.network_intelligence.knowledge_graph import (
    NetworkKnowledgeGraph,
)
from core.network_intelligence.graph_queries import (
    GraphQueryEngine,
)
from core.network_intelligence.action_engine import (
    ActionManagementEngine,
    get_action_engine,
)
from core.network_intelligence.health_engine import (
    NetworkHealthEngine,
)
from core.network_intelligence.anomaly_engine import (
    AnomalyEngine,
)

# Canonical compatibility aliases for legacy callers
EvidenceService = UnifiedEvidenceService
CorrelationEngine = MultiDeviceCorrelationEngine

__all__ = [
    "ConfidenceLevel",
    "ConfigurationPlan",
    "DiagnosticPlaybook",
    "EvidenceFreshness",
    "EvidenceItem",
    "EvidenceState",
    "IncidentRecord",
    "IncidentType",
    "InvestigationStatus",
    "PlanStatus",
    "PlaybookRunRecord",
    "PlaybookStatus",
    "PlaybookStep",
    "PreflightResult",
    "PreflightStatus",
    "RankedHypothesis",
    "SeverityLevel",
    "SimulationResult",
    "ValidationFinding",
    "ValidationSeverity",
    "LabPreflightChecker",
    "NetworkIntelligenceStore",
    "get_network_intelligence_store",
    "EvidenceCollector",
    "determine_freshness",
    "sanitize_raw_output",
    "NetworkInvestigator",
    "get_network_investigator",
    "PlaybookEngine",
    "ConfigurationPlanner",
    "StaticValidator",
    "StaticSimulator",
    "validate_readonly_command",
    "redact_sensitive_values",
    "execute_safe_readonly_command",
    # Gen 3
    "NetworkEvidenceBundle",
    "KnowledgeNode",
    "KnowledgeEdge",
    "UnifiedEvidenceService",
    "get_unified_evidence_service",
    "MultiDeviceCorrelationEngine",
    "SecurityBaselineEngine",
    "get_security_baseline_engine",
    "NetworkKnowledgeGraph",
    "GraphQueryEngine",
    "ActionManagementEngine",
    "get_action_engine",
    "NetworkHealthEngine",
    "AnomalyEngine",
    "EvidenceService",
    "CorrelationEngine",
]
