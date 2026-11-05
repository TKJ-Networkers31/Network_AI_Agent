"""
AIRA OS — Proactive Network Operations API Gateway (Networking VII / WP 7.9).

Provides REST and WebSocket endpoints for:
- Predictive capacity and saturation horizons (/predictive)
- Network change impact analytical simulations (/change-impact)
- Business service catalogs and health redundancy (/services)
- Timezone-aware operational job scheduler (/scheduler)
- Maintenance windows and calendar synchronization (/calendar)
- Proactive incident lifecycle tracking (/incidents)
- Controlled notifications and quiet hours (/notifications)
- Automated operational reporting (/reports)
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from core.network_intelligence.evidence_service import UnifiedEvidenceService
from core.network_intelligence.intelligence_models import NetworkEvidenceBundle
from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph
from core.operations.calendar.manager import CalendarManager
from core.operations.change_impact_engine import ChangeImpactEngine
from core.operations.incident_engine import ProactiveIncidentEngine
from core.operations.models import (
    BusinessServiceRecord,
    ChangeScenarioRequest,
    MaintenanceWindowRecord,
    OperationalJobRecord,
    ProactiveIncidentRecord,
    ServiceEndpointRecord,
)
from core.operations.notification_hub import NotificationHub
from core.operations.predictive_engine import PredictiveOperationsEngine
from core.operations.reporting_engine import OperationalReportingEngine
from core.operations.scheduler import OperationalSchedulerEngine
from core.operations.service_intelligence import ServiceIntelligenceEngine

logger = logging.getLogger("aira.api.operations")

from core.tenant.entitlement_service import require_network_plus
from fastapi import Depends
router = APIRouter(prefix="/api/operations", tags=["operations"], dependencies=[Depends(require_network_plus)])

# Shared engine instances
_predictive_engine = PredictiveOperationsEngine()
_change_engine = ChangeImpactEngine()
_service_engine = ServiceIntelligenceEngine()
_scheduler_engine = OperationalSchedulerEngine()
_calendar_manager = CalendarManager()
_incident_engine = ProactiveIncidentEngine()
_notification_hub = NotificationHub()
_reporting_engine = OperationalReportingEngine(
    predictive_engine=_predictive_engine,
    service_engine=_service_engine,
    scheduler_engine=_scheduler_engine,
    calendar_manager=_calendar_manager,
    incident_engine=_incident_engine,
)


# ---------------------------------------------------------------------------
# Pydantic Request Payloads
# ---------------------------------------------------------------------------

class ForecastRequestPayload(BaseModel):
    metric_name: str
    entity_type: str = "interface"
    entity_id: str
    device_id: str
    samples: List[List[float]] = Field(..., description="List of [timestamp, value] pairs")
    window: str = "24h"
    warning_threshold: Optional[float] = None
    critical_threshold: Optional[float] = None


class ChangeSimulatePayload(BaseModel):
    scenario_id: Optional[str] = None
    title: str
    change_type: str  # INTERFACE_DOWN, ROUTE_WITHDRAWAL, DEVICE_REBOOT
    target_device: str
    target_entity: str
    description: str = ""
    parameters: Dict[str, Any] = Field(default_factory=dict)


class ServiceCreatePayload(BaseModel):
    service_id: str
    name: str
    description: str = ""
    criticality: str = "TIER_2_BUSINESS_OPERATIONAL"
    owner_team: str = "NetOps"
    endpoints: List[Dict[str, Any]] = Field(default_factory=list)


class MaintenanceWindowPayload(BaseModel):
    window_id: Optional[str] = None
    title: str
    description: str = ""
    scope_type: str = "DEVICE"
    target_entities: List[str] = Field(default_factory=list)
    start_time_utc: str
    end_time_utc: str
    suppress_alerts: bool = True


class IncidentTransitionPayload(BaseModel):
    new_state: str  # ACKNOWLEDGED, INVESTIGATING, MITIGATED, RESOLVED, CLOSED


# ---------------------------------------------------------------------------
# 1. Predictive Operations Endpoints
# ---------------------------------------------------------------------------

@router.get("/predictive/overview")
async def get_predictive_overview() -> Dict[str, Any]:
    """Generates an operational forecast report across available telemetry."""
    try:
        ev_service = UnifiedEvidenceService()
        bundle = ev_service.assemble_evidence_bundle(allow_live_collection=False)
        report = _predictive_engine.analyze_evidence_bundle(bundle)
        return report.to_dict()
    except Exception as e:
        logger.exception("Failed to generate predictive overview: %s", e)
        # Fallback to sample bundle
        now = datetime.now(timezone.utc).isoformat()
        return {
            "report_id": "pred_rep_empty",
            "analyzed_at": now,
            "highest_risk_level": "INFO",
            "summary": "No cached evidence bundle available; collect evidence to populate forecasts.",
            "risk_counts": {"CRITICAL": 0, "WARNING": 0, "WATCH": 0, "INFO": 0, "UNKNOWN": 0},
            "action_items": [],
            "projections": [],
        }


@router.post("/predictive/forecast")
async def run_custom_forecast(payload: ForecastRequestPayload) -> Dict[str, Any]:
    """Computes a predictive saturation horizon on a custom time series."""
    raw_samples = [(float(s[0]), float(s[1])) for s in payload.samples]
    proj = _predictive_engine.analyze_metric_trend(
        metric_name=payload.metric_name,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        device_id=payload.device_id,
        raw_samples=raw_samples,
        window=payload.window,
        warning_threshold=payload.warning_threshold,
        critical_threshold=payload.critical_threshold,
    )
    return proj.to_dict()


# ---------------------------------------------------------------------------
# 2. Change Impact Endpoints
# ---------------------------------------------------------------------------

@router.post("/change-impact/simulate")
async def simulate_change_impact(payload: ChangeSimulatePayload) -> Dict[str, Any]:
    """Simulates a proposed network change request against an in-memory cloned topology graph."""
    now_ts = datetime.now(timezone.utc).timestamp()
    try:
        ev_service = UnifiedEvidenceService()
        bundle = ev_service.assemble_evidence_bundle(allow_live_collection=False)
    except Exception:
        bundle = NetworkEvidenceBundle(
            bundle_id=f"neb_sim_{int(now_ts)}",
            correlation_id=f"corr_sim_{int(now_ts)}",
            assembled_at=now_ts,
            scope="network",
        )

    # Ingest or build graph
    graph = NetworkKnowledgeGraph()
    try:
        graph = NetworkKnowledgeGraph.from_evidence_bundle(bundle)
    except Exception:
        pass

    scenario = ChangeScenarioRequest(
        scenario_id=payload.scenario_id or f"scen_{int(datetime.now(timezone.utc).timestamp())}",
        title=payload.title,
        change_type=payload.change_type,
        target_device=payload.target_device,
        target_entity=payload.target_entity,
        description=payload.description,
        parameters=payload.parameters,
    )

    report = _change_engine.simulate_change(scenario, bundle, graph)
    return report.to_dict()


# ---------------------------------------------------------------------------
# 3. Business Service Catalog Endpoints
# ---------------------------------------------------------------------------

@router.get("/services")
async def list_business_services() -> List[Dict[str, Any]]:
    """Lists all registered business services."""
    services = _service_engine.list_services()
    return [s.to_dict() for s in services]


@router.post("/services")
async def create_business_service(payload: ServiceCreatePayload) -> Dict[str, Any]:
    """Registers a new business service and its network endpoints."""
    endpoints = [
        ServiceEndpointRecord(
            endpoint_id=ep.get("endpoint_id", f"ep_{i}"),
            service_id=payload.service_id,
            endpoint_type=ep.get("endpoint_type", "IP_PORT"),
            endpoint_value=ep.get("endpoint_value", "127.0.0.1:80"),
            target_device_id=ep.get("target_device_id"),
            target_interface=ep.get("target_interface"),
            is_primary=ep.get("is_primary", True),
        )
        for i, ep in enumerate(payload.endpoints)
    ]

    svc = BusinessServiceRecord(
        service_id=payload.service_id,
        name=payload.name,
        description=payload.description,
        criticality=payload.criticality,
        owner_team=payload.owner_team,
        endpoints=endpoints,
    )

    saved = _service_engine.create_service(svc)
    return saved.to_dict()


@router.get("/services/{service_id}/health")
async def get_service_health(service_id: str) -> Dict[str, Any]:
    """Calculates real-time health score and redundancy tier for a business service."""
    try:
        bundle = UnifiedEvidenceService().assemble_evidence_bundle(allow_live_collection=False)
    except Exception:
        bundle = None
    report = _service_engine.evaluate_service_health(service_id, bundle=bundle)
    if "error" in report:
        raise HTTPException(status_code=404, detail=report["error"])
    return report


# ---------------------------------------------------------------------------
# 4. Operational Job Scheduler Endpoints
# ---------------------------------------------------------------------------

@router.get("/scheduler/jobs")
async def list_operational_jobs() -> List[Dict[str, Any]]:
    """Lists registered operational scheduled jobs."""
    jobs = _scheduler_engine.list_jobs()
    return [j.to_dict() for j in jobs]


@router.post("/scheduler/jobs/{job_id}/run")
async def run_operational_job_now(job_id: str) -> Dict[str, Any]:
    """Triggers immediate manual execution of a scheduled operational job."""
    try:
        run_record = _scheduler_engine.execute_job_now(job_id, trigger_type="MANUAL")
        return run_record.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to execute job '%s': %s", job_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scheduler/runs")
async def list_recent_job_runs(job_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Lists execution history of operational jobs."""
    runs = _scheduler_engine.list_job_runs(job_id=job_id, limit=limit)
    return [r.to_dict() for r in runs]


# ---------------------------------------------------------------------------
# 5. Calendar & Maintenance Window Endpoints
# ---------------------------------------------------------------------------

@router.get("/calendar/windows")
async def list_maintenance_windows() -> List[Dict[str, Any]]:
    """Lists scheduled network maintenance windows."""
    windows = _calendar_manager.list_windows()
    return [w.to_dict() for w in windows]


@router.post("/calendar/windows")
async def create_maintenance_window(payload: MaintenanceWindowPayload) -> Dict[str, Any]:
    """Schedules a new network maintenance window."""
    wid = payload.window_id or f"win_{int(datetime.now(timezone.utc).timestamp())}"
    win = MaintenanceWindowRecord(
        window_id=wid,
        title=payload.title,
        description=payload.description,
        source_provider="LOCAL",
        external_event_id=None,
        scope_type=payload.scope_type,
        target_entities=payload.target_entities,
        start_time_utc=payload.start_time_utc,
        end_time_utc=payload.end_time_utc,
        start_time_local="",
        end_time_local="",
        status="SCHEDULED",
        suppress_alerts=payload.suppress_alerts,
    )
    saved = _calendar_manager.create_window(win)
    return saved.to_dict()


@router.get("/calendar/export.ics")
async def export_calendar_ics() -> Response:
    """Exports all maintenance windows as an RFC 5545 iCalendar (.ics) file."""
    ics_text = _calendar_manager.export_ics()
    return Response(
        content=ics_text,
        media_type="text/calendar",
        headers={"Content-Disposition": "attachment; filename=maintenance_windows.ics"},
    )


# ---------------------------------------------------------------------------
# 6. Proactive Incident Endpoints
# ---------------------------------------------------------------------------

@router.get("/incidents")
async def list_proactive_incidents(state: Optional[str] = None, severity: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lists proactive operational incidents."""
    incidents = _incident_engine.list_incidents(state=state, severity=severity)
    return [i.to_dict() for i in incidents]


@router.post("/incidents/{incident_id}/transition")
async def transition_incident_state(incident_id: str, payload: IncidentTransitionPayload) -> Dict[str, Any]:
    """Advances an incident through its lifecycle state machine."""
    try:
        updated = _incident_engine.transition_state(incident_id, payload.new_state)
        return updated.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# 7. Notifications Endpoints
# ---------------------------------------------------------------------------

@router.get("/notifications")
async def list_operational_notifications(unread_only: bool = False, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieves recent notifications with deduplication and delivery status."""
    notifs = _notification_hub.list_notifications(unread_only=unread_only, limit=limit)
    return [n.to_dict() for n in notifs]


# ---------------------------------------------------------------------------
# 8. Operational Reporting Endpoints
# ---------------------------------------------------------------------------

@router.get("/reports/generate")
async def generate_operational_report(period: str = Query("DAILY", pattern="^(DAILY|WEEKLY|MONTHLY)$")) -> Dict[str, Any]:
    """Generates an operational report in Markdown, JSON, and HTML."""
    return _reporting_engine.generate_report(report_period=period)
