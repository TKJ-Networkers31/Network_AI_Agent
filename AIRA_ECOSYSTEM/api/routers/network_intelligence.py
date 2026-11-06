"""
api/routers/network_intelligence.py — REST API for AIRA Network Intelligence & Engineering Copilot.

Provides endpoints for:
- Incident investigations (intake, evidence collection, deterministic analysis, diagnosis)
- Diagnostic playbooks (browsing, stepping, operator inputs)
- Desired-state configuration planning, static validation, and static forwarding simulation.
Strictly read-only; no production configuration changes are executed.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from api.routers.topology import require_topology_admin
from core.network_intelligence import (
    ConfigurationPlanner,
    IncidentRecord,
    IncidentType,
    LabPreflightChecker,
    NetworkInvestigator,
    PlaybookEngine,
    SeverityLevel,
    StaticSimulator,
    StaticValidator,
    get_network_intelligence_store,
)
from core.network_intelligence.models import (
    DesiredStateIn,
    IncidentCreateIn,
    PlaybookAdvanceIn,
    PreflightIn,
    BatchCollectIn,
    CorrelationIn,
    MultiDeviceInvestigationIn,
    AutoDiagnoseIn,
)
from core.network_intelligence.multi_device_collector import MultiDeviceEvidenceOrchestrator
from core.network_intelligence.correlation import CrossDeviceEvidenceCorrelator
from core.network_intelligence.metrics_service import NmsHistoricalMetricsService
from core.network_intelligence.evidence import EvidenceCollector

logger = logging.getLogger("aira.api.network_intelligence")

from core.tenant.auth_deps import require_permission
from fastapi import Depends
router = APIRouter(prefix="/api/intelligence", tags=["network_intelligence"], dependencies=[Depends(require_permission("nms.read"))])


# ---------------------------------------------------------------------------
# Controlled Lab Preflight Endpoints (Phase 6)
# ---------------------------------------------------------------------------

@router.post("/preflight", summary="Run read-only lab connection & diagnostic capability preflight")
def run_lab_preflight(
    body: PreflightIn,
    _auth=Depends(require_topology_admin),
):
    checker = LabPreflightChecker()
    try:
        result = checker.run_preflight(
            target=body.target,
            username=body.username,
            password=body.password,
            port=body.port,
            timeout=body.timeout,
        )
        return {
            "success": True,
            "preflight": result.to_dict(),
        }
    except Exception as exc:
        logger.exception("Lab preflight failed with unhandled error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Preflight error: {str(exc)}",
        )


# ---------------------------------------------------------------------------
# Incidents & Investigations Endpoints
# ---------------------------------------------------------------------------

@router.post("/incidents", summary="Create and run an evidence-driven incident investigation")
def create_investigation(
    body: IncidentCreateIn,
    _auth=Depends(require_topology_admin),
):
    investigator = NetworkInvestigator()
    try:
        record = investigator.create_and_run_investigation(
            device_identity=body.device_identity,
            incident_type=body.incident_type,
            symptoms=body.symptoms,
            user_description=body.user_description,
            severity=body.severity,
            target_ip=body.target_ip,
            correlation_id=body.correlation_id,
        )
        return {
            "success": True,
            "incident": record.to_dict(),
        }
    except Exception as exc:
        logger.exception("Investigation creation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal menjalankan investigasi insiden: {str(exc)}",
        )


@router.get("/incidents", summary="List recent network incident investigations")
def list_investigations(
    limit: int = Query(50, ge=1, le=200),
    device_identity: Optional[str] = Query(None),
):
    store = get_network_intelligence_store()
    records = store.list_incidents(limit=limit, device_identity=device_identity)
    return {
        "success": True,
        "count": len(records),
        "incidents": [r.to_dict() for r in records],
    }


@router.get("/incidents/{incident_id}", summary="Get detailed incident investigation report with evidence")
def get_investigation_detail(incident_id: str):
    store = get_network_intelligence_store()
    record = store.get_incident(incident_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Insiden '{incident_id}' tidak ditemukan.")

    evidence_items = store.get_evidence_for_incident(incident_id)
    return {
        "success": True,
        "incident": record.to_dict(),
        "evidence_items": [it.to_dict() for it in evidence_items],
    }


# ---------------------------------------------------------------------------
# Diagnostic Playbooks Endpoints
# ---------------------------------------------------------------------------

@router.get("/playbooks", summary="List all available deterministic diagnostic playbooks")
def list_playbooks():
    engine = PlaybookEngine()
    pbs = engine.list_playbooks()
    return {
        "success": True,
        "count": len(pbs),
        "playbooks": [pb.to_dict() for pb in pbs],
    }


@router.get("/playbooks/{playbook_id}", summary="Get specific diagnostic playbook schema")
def get_playbook(playbook_id: str):
    engine = PlaybookEngine()
    pb = engine.get_playbook(playbook_id)
    if not pb:
        raise HTTPException(status_code=404, detail=f"Playbook '{playbook_id}' tidak ditemukan.")
    return {"success": True, "playbook": pb.to_dict()}


@router.post("/incidents/{incident_id}/playbook/start", summary="Start diagnostic playbook for an incident")
def start_playbook(
    incident_id: str,
    playbook_id: Optional[str] = Query(None),
    _auth=Depends(require_topology_admin),
):
    store = get_network_intelligence_store()
    inc = store.get_incident(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail=f"Insiden '{incident_id}' tidak ditemukan.")

    engine = PlaybookEngine()
    selected_pb_id = playbook_id
    if not selected_pb_id:
        pb = engine.get_playbook_for_incident(inc.incident_type)
        if not pb:
            raise HTTPException(
                status_code=400,
                detail=f"Tidak ada playbook otomatis yang cocok untuk tipe insiden '{inc.incident_type}'.",
            )
        selected_pb_id = pb.playbook_id

    try:
        run = engine.start_playbook_run(
            playbook_id=selected_pb_id,
            incident_id=incident_id,
            device_identity=inc.device_identity,
        )
        return {"success": True, "playbook_run": run.to_dict()}
    except Exception as exc:
        logger.exception("Failed to start playbook run: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/playbooks/runs/{run_id}/advance", summary="Advance playbook execution step or submit operator input")
def advance_playbook(
    run_id: str,
    body: PlaybookAdvanceIn,
    _auth=Depends(require_topology_admin),
):
    engine = PlaybookEngine()
    try:
        run = engine.advance_playbook(
            run_id=run_id,
            action=body.action,
            operator_input=body.operator_input,
        )
        return {"success": True, "playbook_run": run.to_dict()}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("Failed to advance playbook run: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/playbooks/runs/{run_id}", summary="Get status and step history of a playbook run")
def get_playbook_run(run_id: str):
    store = get_network_intelligence_store()
    run = store.get_playbook_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Playbook run '{run_id}' tidak ditemukan.")
    return {"success": True, "playbook_run": run.to_dict()}


# ---------------------------------------------------------------------------
# Configuration Planning, Static Validation & Simulation Endpoints
# ---------------------------------------------------------------------------

@router.post("/plans", summary="Construct a configuration plan from desired state (Read-Only)")
def create_configuration_plan(
    body: DesiredStateIn,
    _auth=Depends(require_topology_admin),
):
    planner = ConfigurationPlanner()
    validator = StaticValidator()
    simulator = StaticSimulator()

    try:
        plan = planner.generate_plan(
            target_device=body.target_device,
            change_type=body.change_type,
            parameters=body.parameters,
            incident_id=body.incident_id,
        )

        # Run deterministic static validation
        if plan.plan_status != "NEEDS_INPUT":
            plan = validator.validate_plan(plan)
            # Run static forwarding simulation
            simulator.simulate_plan(plan)
            # Re-save plan with validation & simulation
            store = get_network_intelligence_store()
            store.save_plan(plan)

        return {"success": True, "plan": plan.to_dict()}
    except Exception as exc:
        logger.exception("Failed to generate configuration plan: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/plans/{plan_id}", summary="Get configuration plan with diff, validation, and simulation")
def get_configuration_plan(plan_id: str):
    store = get_network_intelligence_store()
    plan = store.get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Rencana konfigurasi '{plan_id}' tidak ditemukan.")
    return {"success": True, "plan": plan.to_dict()}


@router.get("/plans", summary="List configuration plans")
def list_configuration_plans(
    limit: int = Query(50, ge=1, le=200),
    incident_id: Optional[str] = Query(None),
):
    store = get_network_intelligence_store()
    plans = store.list_plans(limit=limit, incident_id=incident_id)
    return {"success": True, "count": len(plans), "plans": [p.to_dict() for p in plans]}


# ---------------------------------------------------------------------------
# Multi-Device Network Intelligence Endpoints (Phase Networking III)
# ---------------------------------------------------------------------------

@router.post("/devices/batch-collect", summary="Collect normalized evidence across multiple network devices concurrently")
def batch_collect_evidence(
    body: BatchCollectIn,
    _auth=Depends(require_topology_admin),
):
    try:
        collector = EvidenceCollector()
        orchestrator = MultiDeviceEvidenceOrchestrator(collector)
        bundle = orchestrator.collect_multi_device_bundle(
            targets=body.targets,
            required_types=body.required_types,
        )
        return {
            "success": True,
            "bundle_id": bundle.bundle_id,
            "summary": bundle.summary.to_dict(),
            "total_devices": len(bundle.device_bundles),
            "cross_device_contradictions": bundle.cross_device_contradictions,
        }
    except Exception as exc:
        logger.exception("Batch evidence collection failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal melakukan pengumpulan bukti multi-perangkat: {str(exc)}",
        )


@router.post("/correlation", summary="Analyze cross-device links, subnets, and routing relationships")
def correlate_devices(
    body: CorrelationIn,
    _auth=Depends(require_topology_admin),
):
    try:
        collector = EvidenceCollector()
        orchestrator = MultiDeviceEvidenceOrchestrator(collector)
        bundle = orchestrator.collect_multi_device_bundle(
            targets=body.targets,
            required_types=body.required_types,
        )
        correlator = CrossDeviceEvidenceCorrelator()
        relationships = correlator.correlate_bundles(bundle.device_bundles)
        return {
            "success": True,
            "count": len(relationships),
            "relationships": [r.to_dict() for r in relationships],
            "cross_device_contradictions": bundle.cross_device_contradictions,
        }
    except Exception as exc:
        logger.exception("Cross-device correlation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal melakukan korelasi relasi multi-perangkat: {str(exc)}",
        )


@router.post("/multi-device-investigation", summary="Run topology-aware root-cause investigation across multiple devices")
def run_multi_device_investigation(
    body: MultiDeviceInvestigationIn,
    _auth=Depends(require_topology_admin),
):
    try:
        investigator = NetworkInvestigator()
        record = investigator.run_multi_device_investigation(
            primary_device=body.primary_device,
            related_devices=body.related_devices,
            symptom_description=body.symptom_description,
            incident_type=body.incident_type,
            target_ip=body.target_ip,
            severity=body.severity,
            correlation_id=body.correlation_id,
        )
        return {
            "success": True,
            "incident": record.to_dict(),
        }
    except Exception as exc:
        logger.exception("Multi-device investigation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal menjalankan investigasi multi-perangkat: {str(exc)}",
        )


@router.get("/metrics/history", summary="Query historical NMS telemetry metrics for devices or interfaces")
def get_metrics_history(
    device_id: str = Query(..., description="Target device ID"),
    interface_name: Optional[str] = Query(None, description="Optional interface name"),
    start_time: Optional[float] = Query(None, description="Start timestamp (epoch seconds)"),
    end_time: Optional[float] = Query(None, description="End timestamp (epoch seconds)"),
    limit: int = Query(500, ge=1, le=2000, description="Max points to retrieve"),
    downsample_points: Optional[int] = Query(None, ge=2, le=500, description="Optional downsample point count"),
):
    try:
        svc = NmsHistoricalMetricsService()
        if interface_name:
            metrics = svc.query_interface_metrics_history(
                device_id=device_id,
                interface_name=interface_name,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
                downsample_points=downsample_points,
            )
        else:
            metrics = svc.query_device_metrics_history(
                device_id=device_id,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
                downsample_points=downsample_points,
            )

        return {
            "success": True,
            "device_id": device_id,
            "interface_name": interface_name,
            "count": len(metrics),
            "metrics": metrics,
        }
    except Exception as exc:
        logger.exception("Failed to query metrics history: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal mengambil riwayat metrik: {str(exc)}",
        )


@router.post("/auto-diagnose", summary="Run unified end-to-end automatic network diagnosis and planning (Read-Only)")
def run_auto_diagnose(body: AutoDiagnoseIn):
    from core.network_intelligence.auto_orchestrator import get_auto_orchestrator
    try:
        orchestrator = get_auto_orchestrator()
        result = orchestrator.execute_auto_diagnosis(
            target_devices=body.target_devices,
            symptom=body.symptom,
            target_ip=body.target_ip,
            auto_plan=body.auto_plan,
            routing_table=body.routing_table,
            require_dio_validation=body.require_dio_validation,
            reuse_fresh_sec=body.reuse_fresh_sec,
            persist_route_snapshot=body.persist_route_snapshot,
        )
        return result
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as exc:
        logger.exception("Error in auto diagnosis pipeline: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal menjalankan diagnostik otomatis: {str(exc)}",
        )


@router.post("/auto-diagnose/{pipeline_id}/cancel", summary="Cancel an active automatic diagnosis pipeline")
def cancel_auto_diagnose_endpoint(
    pipeline_id: str,
    _auth=Depends(require_topology_admin),
):
    from core.network_intelligence.auto_orchestrator import get_auto_orchestrator
    cancelled = get_auto_orchestrator().cancel_pipeline(pipeline_id)
    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline diagnostik aktif '{pipeline_id}' tidak ditemukan atau sudah selesai.",
        )
    return {"success": True, "pipeline_id": pipeline_id, "cancelled": True}


# ---------------------------------------------------------------------------
# Multi-Device Route Collection & Intelligence Endpoints (Networking IV)
# ---------------------------------------------------------------------------

class RouteCollectIn(BaseModel):
    targets: Optional[List[str]] = Field(
        default=None,
        description="Optional list of device IDs/names to collect. Collects all managed devices when omitted.",
    )
    max_concurrency: int = Field(default=3, ge=1, le=8)
    timeout_per_device: float = Field(default=15.0, ge=1.0, le=60.0)
    max_retries: int = Field(default=1, ge=0, le=3)
    verify_identity: bool = Field(default=False)
    reuse_fresh_sec: float = Field(default=0.0, ge=0.0, le=300.0)
    include_routes: bool = Field(default=True)
    route_limit_per_device: int = Field(default=500, ge=1, le=5000)
    persist_snapshot: bool = Field(default=False)


@router.post("/routes/collect", summary="Collect normalized routing evidence from one or multiple registered devices")
def collect_device_routes_endpoint(
    body: RouteCollectIn,
    _auth=Depends(require_topology_admin),
):
    from core.routing.route_collector import get_route_collector
    collector = get_route_collector()
    try:
        report = collector.collect_multi_device_routes(
            targets=body.targets,
            max_concurrency=body.max_concurrency,
            timeout_per_device=body.timeout_per_device,
            max_retries=body.max_retries,
            verify_identity=body.verify_identity,
            reuse_fresh_sec=body.reuse_fresh_sec,
        )
        snapshot_summary = None
        if body.persist_snapshot and report.results:
            from core.routing.route_history import get_route_history_store
            snapshot_summary = get_route_history_store().create_multi_device_snapshots(
                report.results,
                trigger_type="collection",
                description="Auto-persisted during /routes/collect",
            )
        return {
            "success": True,
            "report": report.to_dict(
                include_routes=body.include_routes,
                route_limit_per_device=body.route_limit_per_device,
            ),
            "snapshot_summary": snapshot_summary,
        }
    except Exception as exc:
        logger.exception("Route collection endpoint failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal mengumpulkan data routing: {str(exc)}",
        )


@router.post("/routes/jobs/{job_id}/cancel", summary="Cancel an active multi-device route collection job")
def cancel_route_collection_job(
    job_id: str,
    _auth=Depends(require_topology_admin),
):
    from core.routing.route_collector import get_route_collector
    collector = get_route_collector()
    cancelled = collector.cancel_job(job_id)
    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job pengumpulan rute aktif '{job_id}' tidak ditemukan atau sudah selesai.",
        )
    return {"success": True, "job_id": job_id, "cancelled": True}


@router.get("/routes/status", summary="Get route collection service status and per-device collection metadata")
def get_route_collection_status():
    from core.routing.route_collector import get_route_collector
    collector = get_route_collector()
    return {
        "success": True,
        "status": collector.get_collection_status(),
    }


@router.get("/routes", summary="Retrieve latest normalized route evidence across registered devices")
def list_all_collected_routes(
    device_id: Optional[str] = Query(default=None),
    routing_table: Optional[str] = Query(default=None),
    protocol: Optional[str] = Query(default=None),
    active_only: bool = Query(default=False),
    limit_per_device: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
):
    from core.routing.route_collector import get_route_collector
    collector = get_route_collector()
    if device_id:
        single = collector.get_latest_result(device_id)
        if not single:
            return {
                "success": True,
                "devices_count": 0,
                "devices": {},
            }
        return {
            "success": True,
            "devices_count": 1,
            "devices": {
                single.device_id: single.to_dict(
                    include_routes=True,
                    routing_table=routing_table,
                    protocol=protocol,
                    active_only=active_only,
                    limit=limit_per_device,
                    offset=offset,
                )
            },
        }

    all_results = collector.list_latest_results()
    return {
        "success": True,
        "devices_count": len(all_results),
        "devices": {
            dev_key: res.to_dict(
                include_routes=True,
                routing_table=routing_table,
                protocol=protocol,
                active_only=active_only,
                limit=limit_per_device,
                offset=offset,
            )
            for dev_key, res in all_results.items()
        },
    }


class RouteAnalyzeIn(BaseModel):
    targets: Optional[List[str]] = Field(default=None)
    target_destination: Optional[str] = Field(default=None)
    collect_if_missing: bool = Field(default=False)


class RoutePathIn(BaseModel):
    source_device: str = Field(..., min_length=1, max_length=128)
    destination: str = Field(..., min_length=1, max_length=64)
    routing_table: str = Field(default="main", max_length=64)
    source_prefix_for_symmetry: Optional[str] = Field(default=None, max_length=64)
    collect_if_missing: bool = Field(default=False)


@router.post("/routes/analyze", summary="Analyze single- and multi-device route tables for anomalies and inconsistencies")
def analyze_collected_routes_endpoint(
    body: RouteAnalyzeIn,
    _auth=Depends(require_topology_admin),
):
    from core.canonical_network import get_canonical_registry
    from core.routing.route_analytics import RouteTableAnalyzer
    from core.routing.route_collector import get_route_collector

    collector = get_route_collector()
    registry = get_canonical_registry()
    if body.collect_if_missing:
        collector.collect_multi_device_routes(targets=body.targets, reuse_fresh_sec=60.0)

    all_cached = collector.list_latest_results()
    if body.targets:
        selected = {}
        for t in body.targets:
            res = collector.get_latest_result(t)
            if res:
                selected[res.device_id] = res
    else:
        selected = all_cached

    dev_ips = {d.device_id: list(d.all_ips) for d in registry.list_devices()}
    analyzer = RouteTableAnalyzer()
    findings = analyzer.analyze_multi_device_routes(
        selected,
        device_ips=dev_ips,
        target_destination=body.target_destination,
    )
    return {
        "success": True,
        "devices_analyzed": list(selected.keys()),
        "findings_count": len(findings),
        "findings": [f.to_dict() for f in findings],
    }


@router.post("/routes/path", summary="Reconstruct evidence-backed or inferred multi-router path to destination")
def evaluate_route_path_endpoint(
    body: RoutePathIn,
    _auth=Depends(require_topology_admin),
):
    from core.canonical_network import get_canonical_registry
    from core.routing.route_analytics import RoutePathEvaluator
    from core.routing.route_collector import get_route_collector
    from core.topology_engine import get_topology_engine

    collector = get_route_collector()
    registry = get_canonical_registry()
    src_dev = registry.resolve_device(body.source_device)
    src_id = src_dev.device_id if src_dev else body.source_device

    if body.collect_if_missing and collector.get_latest_result(src_id) is None:
        collector.collect_multi_device_routes(reuse_fresh_sec=60.0)

    collections = collector.list_latest_results()
    dev_ips = {d.device_id: list(d.all_ips) for d in registry.list_devices()}

    # Extract confirmed L1/L2 adjacencies from TopologyEngine without fabricating edges
    verified_adj = set()
    try:
        topo = get_topology_engine().get_topology()
        for edge in topo.get("edges", []):
            rel_cls = str(edge.get("relationship_class") or "").upper()
            conf_tier = str(edge.get("confidence_tier") or "").lower()
            if rel_cls in ("PHYSICAL_ADJACENCY", "LAYER2_ADJACENCY") and conf_tier in ("confirmed", "high"):
                verified_adj.add((str(edge.get("source_node_id")), str(edge.get("target_node_id"))))
    except Exception:
        pass

    evaluator = RoutePathEvaluator()
    path_res = evaluator.evaluate_path(
        src_id,
        body.destination,
        collections,
        routing_table=body.routing_table,
        device_ips=dev_ips,
        verified_adjacencies=verified_adj,
        source_prefix_for_symmetry=body.source_prefix_for_symmetry,
    )
    return {
        "success": True,
        "path": path_res.to_dict(),
    }


class FailureImpactIn(BaseModel):
    failure_type: str = Field(..., min_length=3, max_length=64)
    device_id: Optional[str] = Field(default=None, max_length=128)
    interface_name: Optional[str] = Field(default=None, max_length=128)
    gateway_ip: Optional[str] = Field(default=None, max_length=64)
    dst_prefix: Optional[str] = Field(default=None, max_length=64)
    routing_table: str = Field(default="main", max_length=64)


@router.get("/routes/dependencies", summary="Build ephemeral multi-device or single-device route dependency graph")
def get_route_dependency_graph_endpoint(
    device_id: Optional[str] = Query(default=None, max_length=128),
    routing_table: Optional[str] = Query(default=None, max_length=64),
    max_depth: int = Query(default=16, ge=1, le=32),
):
    from core.canonical_network import get_canonical_registry
    from core.routing.route_collector import get_route_collector
    from core.routing.route_dependency import RouteDependencyAnalyzer

    collector = get_route_collector()
    registry = get_canonical_registry()
    collections = collector.list_latest_results()

    resolved_dev_id = None
    if device_id:
        cdev = registry.resolve_device(device_id)
        resolved_dev_id = cdev.device_id if cdev else device_id
        if resolved_dev_id not in collections:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Belum ada bukti routing yang terkumpul untuk perangkat '{device_id}'.",
            )

    dev_ips = {d.device_id: list(d.all_ips) for d in registry.list_devices()}
    analyzer = RouteDependencyAnalyzer()
    graph = analyzer.build_dependency_graph(
        collections,
        device_ips=dev_ips,
        target_device_id=resolved_dev_id,
        routing_table=routing_table,
        max_depth=max_depth,
    )
    return {
        "success": True,
        "dependency_graph": graph.to_dict(),
    }


@router.post("/routes/failure-impact", summary="Simulate read-only hypothetical failure propagation across route dependencies")
def simulate_route_failure_impact_endpoint(
    body: FailureImpactIn,
    _auth=Depends(require_topology_admin),
):
    from core.canonical_network import get_canonical_registry
    from core.routing.route_collector import get_route_collector
    from core.routing.route_dependency import FailurePropagationAnalyzer, HypotheticalFailureType

    valid_types = {t.value for t in HypotheticalFailureType}
    norm_type = body.failure_type.strip().upper()
    if norm_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipe kegagalan '{body.failure_type}' tidak valid. Pilihan: {sorted(valid_types)}",
        )

    collector = get_route_collector()
    registry = get_canonical_registry()
    collections = collector.list_latest_results()
    registered_devs = registry.list_devices()
    dev_ips = {d.device_id: list(d.all_ips) for d in registered_devs}
    known_ids = [d.device_id for d in registered_devs if d.is_managed]

    resolved_dev_id = None
    if body.device_id:
        cdev = registry.resolve_device(body.device_id)
        resolved_dev_id = cdev.device_id if cdev else body.device_id

    analyzer = FailurePropagationAnalyzer()
    report = analyzer.analyze_failure(
        norm_type,
        collections,
        device_id=resolved_dev_id,
        interface_name=body.interface_name,
        gateway_ip=body.gateway_ip,
        dst_prefix=body.dst_prefix,
        routing_table=body.routing_table,
        device_ips=dev_ips,
        known_registered_device_ids=known_ids,
    )
    return {
        "success": True,
        "impact": report.to_dict(),
    }


class CrossDeviceRouteIn(BaseModel):
    targets: Optional[List[str]] = Field(default=None)
    source_device: Optional[str] = Field(default=None, max_length=128)
    destination: Optional[str] = Field(default=None, max_length=64)
    routing_table: str = Field(default="main", max_length=64)
    source_prefix_for_return: Optional[str] = Field(default=None, max_length=64)
    expected_next_hop_device: Optional[str] = Field(default=None, max_length=128)
    collect_if_missing: bool = Field(default=False)


@router.post("/routes/cross-device", summary="Perform cross-device route correlation, relationship verification, and inconsistency detection")
def analyze_cross_device_routes_endpoint(
    body: CrossDeviceRouteIn,
    _auth=Depends(require_topology_admin),
):
    from core.canonical_network import get_canonical_registry
    from core.routing.cross_device_routing import CrossDeviceRouteIntelligenceEngine
    from core.routing.route_collector import get_route_collector
    from core.routing.route_history import get_route_history_store
    from core.topology_engine import get_topology_engine

    collector = get_route_collector()
    registry = get_canonical_registry()
    if body.collect_if_missing:
        collector.collect_multi_device_routes(targets=body.targets, reuse_fresh_sec=60.0)

    all_cached = collector.list_latest_results()
    if body.targets:
        selected = {}
        for t in body.targets:
            res = collector.get_latest_result(t)
            if res:
                selected[res.device_id] = res
    else:
        selected = all_cached

    registered_devs = registry.list_devices()
    dev_ips = {d.device_id: list(d.all_ips) for d in registered_devs}
    reg_ids = [d.device_id for d in registered_devs if d.is_managed]

    src_id = body.source_device
    if src_id:
        csrc = registry.resolve_device(src_id)
        if csrc:
            src_id = csrc.device_id

    exp_nh_id = body.expected_next_hop_device
    if exp_nh_id:
        cexp = registry.resolve_device(exp_nh_id)
        if cexp:
            exp_nh_id = cexp.device_id

    topo_edges = []
    oper_states = {}
    try:
        topo = get_topology_engine().get_topology()
        topo_edges = topo.get("edges", [])
        for n in topo.get("nodes", []):
            nid = str(n.get("id") or "")
            if nid:
                oper_states[nid] = str(n.get("status") or "online")
    except Exception:
        pass

    recent_changes = []
    try:
        chgs, _ = get_route_history_store().list_changes(limit=25, offset=0)
        recent_changes = [c.to_dict() for c in chgs]
    except Exception:
        pass

    engine = CrossDeviceRouteIntelligenceEngine()
    report = engine.analyze_network_routing(
        selected,
        device_ips=dev_ips,
        topology_edges=topo_edges,
        device_oper_states=oper_states,
        registered_device_ids=reg_ids,
        source_device=src_id,
        destination=body.destination,
        routing_table=body.routing_table,
        source_prefix_for_return=body.source_prefix_for_return,
        expected_next_hop_device=exp_nh_id,
        recent_route_changes=recent_changes,
    )
    return {
        "success": True,
        "report": report.to_dict(),
    }


@router.get("/routes/{device_id}/dependencies", summary="Build ephemeral route dependency graph for a specific device")
def get_device_route_dependencies_endpoint(
    device_id: str,
    routing_table: Optional[str] = Query(default=None, max_length=64),
    max_depth: int = Query(default=16, ge=1, le=32),
):
    return get_route_dependency_graph_endpoint(
        device_id=device_id,
        routing_table=routing_table,
        max_depth=max_depth,
    )


@router.get("/routes/{device_id}/lookup", summary="Evaluate 5-tier Longest Prefix Match (LPM) lookup on a device")
def lookup_device_route_endpoint(
    device_id: str,
    destination: str = Query(..., min_length=1, max_length=64),
    routing_table: str = Query(default="main", max_length=64),
):
    from core.routing.route_analytics import evaluate_route_lookup
    from core.routing.route_collector import get_route_collector

    collector = get_route_collector()
    res = collector.get_latest_result(device_id)
    if res is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Belum ada bukti tabel routing yang terkumpul untuk perangkat '{device_id}'.",
        )
    lpm = evaluate_route_lookup(
        res.routes,
        destination,
        device_id=res.device_id,
        routing_table=routing_table,
        completeness=res.completeness,
    )
    return {
        "success": True,
        "lookup": lpm.to_dict(),
    }


@router.get("/routes/{device_id}", summary="Retrieve current normalized route evidence for a specific device")
def get_device_collected_routes(
    device_id: str,
    routing_table: Optional[str] = Query(default=None),
    protocol: Optional[str] = Query(default=None),
    active_only: bool = Query(default=False),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    from core.routing.route_collector import get_route_collector
    collector = get_route_collector()
    res = collector.get_latest_result(device_id)
    if res is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Belum ada bukti tabel routing yang terkumpul untuk perangkat '{device_id}'.",
        )
    return {
        "success": True,
        "device_routes": res.to_dict(
            include_routes=True,
            routing_table=routing_table,
            protocol=protocol,
            active_only=active_only,
            limit=limit,
            offset=offset,
        ),
    }


# ===========================================================================
# Networking VI — Network Intelligence Core REST API (WP 6.15)
# ===========================================================================

class NLInvestigateIn(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="Natural language investigation query")
    session_id: Optional[str] = Field(default=None, max_length=64, description="Optional conversational session ID")
    user_context: Optional[Dict[str, Any]] = Field(default=None, description="Optional scoped operator context")
    timeout_sec: float = Field(default=30.0, ge=1.0, le=120.0, description="Timeout in seconds")


class ChangeImpactIn(BaseModel):
    target_entity_id: str = Field(..., min_length=1, max_length=128, description="Target entity ID to evaluate impact for")
    target_entity_type: Optional[str] = Field(default=None, max_length=64, description="Optional entity type")
    scope: str = Field(default="POTENTIAL_IMPACT", description="OBSERVED_IMPACT or POTENTIAL_IMPACT")


class FailureSimulationIn(BaseModel):
    failure_type: str = Field(..., min_length=1, max_length=64, description="Failure scenario type (e.g. DEVICE_DOWN, INTERFACE_DOWN, LINK_CUT)")
    entity_id: str = Field(..., min_length=1, max_length=128, description="Target entity ID to simulate failure on")


@router.get("/overview", summary="Retrieve high-level network intelligence summary")
def get_network_intelligence_overview():
    from core.network_intelligence.evidence_service import get_unified_evidence_service
    from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph
    from core.network_intelligence.health_engine import NetworkHealthEngine
    from core.network_intelligence.anomaly_engine import AnomalyEngine
    from core.network_intelligence.historical_intelligence import HistoricalIntelligenceEngine

    evidence_svc = get_unified_evidence_service()
    bundle = evidence_svc.assemble_evidence_bundle(allow_live_collection=False)
    kg = NetworkKnowledgeGraph.from_evidence_bundle(bundle)

    anomaly_engine = AnomalyEngine()
    anomalies = anomaly_engine.detect_anomalies(bundle, graph=kg)

    health_engine = NetworkHealthEngine()
    health = health_engine.evaluate_health(bundle, graph=kg, anomalies=anomalies)

    hist_engine = HistoricalIntelligenceEngine()
    recurring = hist_engine.detect_recurring_incidents()

    from core.inventory_store import get_inventory_store
    from core.nms_engine import get_nms_engine
    from core.network_intelligence.action_engine import get_action_engine
    from core.operations.decision_engine import OperationalDecisionEngine

    store = get_network_intelligence_store()
    recent_incidents = store.list_incidents(limit=10)
    inv_devices = get_inventory_store().list_devices()
    nms_overview = get_nms_engine().get_overview()
    action_engine = get_action_engine()
    recent_actions = action_engine.list_actions(limit=20)
    pending_approvals = [a for a in recent_actions if a.get("status") == "PENDING_APPROVAL"]
    decisions_engine = OperationalDecisionEngine()
    try:
        recent_decisions = decisions_engine.list_decisions(tenant_id="tenant_internal", limit=5)
    except Exception:
        recent_decisions = []

    return {
        "success": True,
        "overview": {
            "network_condition": health.get("status", "HEALTHY"),
            "health_score": health.get("score", 100.0),
            "dimension_scores": health.get("dimensions", {}),
            "device_health": health.get("device_health", {}),
            "total_registered_devices": len(inv_devices),
            "reachable_devices": nms_overview.get("up_count", 0),
            "unreachable_devices": nms_overview.get("down_count", 0) + nms_overview.get("suspected_count", 0),
            "active_investigations": len([i for i in recent_incidents if i.investigation_status != "COMPLETED"]),
            "active_incidents_count": len([i for i in recent_incidents if i.investigation_status != "COMPLETED"]),
            "recent_incidents": [i.to_dict() for i in recent_incidents[:5]],
            "detected_anomalies": len(anomalies),
            "major_anomalies": [a.to_dict() for a in anomalies if a.severity in ("CRITICAL", "HIGH")],
            "recurring_incidents": recurring[:5],
            "pending_approvals": pending_approvals,
            "recent_ai_decisions": [d.to_dict() if hasattr(d, "to_dict") else d for d in recent_decisions],
            "evidence_freshness": bundle.freshness_summary,
            "total_evidence_records": len(bundle.records),
            "observed_devices": list(bundle.device_evidence.keys()) if hasattr(bundle, "device_evidence") else [],
        }
    }


@router.post("/investigate", summary="Submit natural-language query to Network Investigator")
def investigate_natural_language_endpoint(
    body: NLInvestigateIn,
    _auth=Depends(require_topology_admin),
):
    investigator = NetworkInvestigator()
    try:
        report = investigator.investigate_natural_language(
            query=body.question,
            session_id=body.session_id,
            user_context=body.user_context,
            timeout_sec=body.timeout_sec,
        )
        return {
            "success": True,
            "investigation": report,
        }
    except Exception as exc:
        logger.exception("Investigation failed with unexpected error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal memproses penyelidikan: {str(exc)}",
        )


@router.get("/investigations", summary="List historical natural-language network investigations")
def list_investigations_endpoint(
    session_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    store = get_network_intelligence_store()
    items = store.list_intelligence_investigations(session_id=session_id, limit=limit)
    return {
        "success": True,
        "investigations": items,
    }


@router.get("/investigations/{investigation_id}", summary="Retrieve a specific investigation report by ID")
def get_investigation_endpoint(investigation_id: str):
    store = get_network_intelligence_store()
    item = store.get_intelligence_investigation(investigation_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Penyelidikan '{investigation_id}' tidak ditemukan.",
        )
    return {
        "success": True,
        "investigation": item,
    }


@router.post("/investigations/{investigation_id}/cancel", summary="Cancel an ongoing network investigation")
def cancel_investigation_endpoint(
    investigation_id: str,
    _auth=Depends(require_topology_admin),
):
    investigator = NetworkInvestigator()
    ok = investigator.cancel_investigation(investigation_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Penyelidikan '{investigation_id}' tidak aktif atau sudah selesai.",
        )
    return {
        "success": True,
        "message": f"Penyelidikan '{investigation_id}' berhasil dibatalkan.",
    }


@router.get("/graph", summary="Query Network Knowledge Graph entities and relationships")
def get_knowledge_graph_endpoint(
    layer: Optional[str] = Query(default=None, description="physical, l2, l3, protocol, dependency"),
    entity_type: Optional[str] = Query(default=None),
    device_id: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    from core.network_intelligence.evidence_service import get_unified_evidence_service
    from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph
    from core.network_intelligence.graph_queries import GraphQueryEngine

    evidence_svc = get_unified_evidence_service()
    bundle = evidence_svc.assemble_evidence_bundle(allow_live_collection=False)
    kg = NetworkKnowledgeGraph.from_evidence_bundle(bundle)

    nodes = [n.to_dict() for n in kg.nodes.values()]
    edges = [r.to_dict() for r in kg.edges.values()]

    if layer:
        l_lower = layer.lower()
        edges = [e for e in edges if str(e.get("layer", "")).lower() == l_lower]
        valid_ids = set()
        for e in edges:
            valid_ids.add(e["source_id"])
            valid_ids.add(e["target_id"])
        nodes = [n for n in nodes if n["node_id"] in valid_ids]

    if entity_type:
        et_lower = entity_type.lower()
        nodes = [n for n in nodes if str(n["entity_type"]).lower() == et_lower]

    if device_id:
        dev_set = {
            n["node_id"] for n in nodes
            if n.get("device_id") == device_id
            or n.get("attributes", {}).get("device_id") == device_id
            or n["node_id"] == device_id
        }
        edges = [e for e in edges if e["source_id"] in dev_set or e["target_id"] in dev_set]
        nodes = [n for n in nodes if n["node_id"] in dev_set]

    total_nodes = len(nodes)
    total_edges = len(edges)
    paginated_nodes = nodes[offset : offset + limit]

    return {
        "success": True,
        "graph": {
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "nodes": paginated_nodes,
            "edges": edges[:limit],
            "layers_available": ["PHYSICAL", "L2", "L3", "PROTOCOL", "DEPENDENCY"],
        }
    }


@router.get("/paths", summary="Perform hop-by-hop path intelligence analysis")
def get_path_analysis_endpoint(
    destination_ip: str = Query(..., min_length=1, max_length=64),
    source_device_id: Optional[str] = Query(default=None),
    source_ip: Optional[str] = Query(default=None),
    routing_table: str = Query(default="main"),
):
    from core.network_intelligence.evidence_service import get_unified_evidence_service
    from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph
    from core.network_intelligence.path_intelligence import NetworkPathIntelligenceEngine

    evidence_svc = get_unified_evidence_service()
    bundle = evidence_svc.assemble_evidence_bundle(allow_live_collection=False)
    kg = NetworkKnowledgeGraph.from_evidence_bundle(bundle)

    path_engine = NetworkPathIntelligenceEngine()
    path_res = path_engine.analyze_path(
        bundle=bundle,
        graph=kg,
        destination_ip=destination_ip,
        source_device_id=source_device_id,
        source_ip=source_ip,
        routing_table=routing_table,
    )
    return {
        "success": True,
        "path_analysis": path_res.to_dict(),
    }


@router.get("/correlations", summary="Discover cross-device incident and topology correlations")
def get_correlations_endpoint(
    window_sec: float = Query(default=300.0, ge=10.0, le=3600.0),
):
    from core.network_intelligence.evidence_service import get_unified_evidence_service
    from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph
    from core.network_intelligence.correlation_engine import MultiDeviceCorrelationEngine

    evidence_svc = get_unified_evidence_service()
    bundle = evidence_svc.assemble_evidence_bundle(allow_live_collection=False)
    kg = NetworkKnowledgeGraph.from_evidence_bundle(bundle)

    engine = MultiDeviceCorrelationEngine()
    clusters = engine.correlate(bundle, kg, investigation_window_sec=window_sec)

    return {
        "success": True,
        "correlations": [c.to_dict() for c in clusters],
        "total_clusters": len(clusters),
    }


@router.get("/rca", summary="Run root-cause analysis across current evidence and topology")
def get_rca_endpoint(
    scope: str = Query(default="network"),
):
    from core.network_intelligence.evidence_service import get_unified_evidence_service
    from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph
    from core.network_intelligence.correlation_engine import MultiDeviceCorrelationEngine
    from core.network_intelligence.rca_engine import RootCauseAnalysisEngine

    evidence_svc = get_unified_evidence_service()
    bundle = evidence_svc.assemble_evidence_bundle(allow_live_collection=False)
    kg = NetworkKnowledgeGraph.from_evidence_bundle(bundle)

    corr_engine = MultiDeviceCorrelationEngine()
    correlations = corr_engine.correlate(bundle, kg)

    rca_engine = RootCauseAnalysisEngine()
    report = rca_engine.analyze(bundle, kg, scope=scope, correlations=correlations)

    return {
        "success": True,
        "rca_report": report.to_dict(),
    }


@router.get("/anomalies", summary="Retrieve detected telemetry, rate, and interface anomalies")
def get_anomalies_endpoint(
    severity: Optional[str] = Query(default=None),
    device_id: Optional[str] = Query(default=None),
):
    from core.network_intelligence.evidence_service import get_unified_evidence_service
    from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph
    from core.network_intelligence.anomaly_engine import AnomalyEngine

    evidence_svc = get_unified_evidence_service()
    bundle = evidence_svc.assemble_evidence_bundle(allow_live_collection=False)
    kg = NetworkKnowledgeGraph.from_evidence_bundle(bundle)

    engine = AnomalyEngine()
    anomalies = engine.detect_anomalies(bundle, graph=kg)

    if severity:
        s_up = severity.upper()
        anomalies = [a for a in anomalies if a.severity == s_up]
    if device_id:
        anomalies = [a for a in anomalies if a.entity_id == device_id or a.entity_id.startswith(f"{device_id}:")]

    return {
        "success": True,
        "anomalies": [a.to_dict() for a in anomalies],
        "total_anomalies": len(anomalies),
    }


@router.get("/health", summary="Retrieve 8-dimensional network and device health scores")
def get_health_endpoint():
    from core.network_intelligence.evidence_service import get_unified_evidence_service
    from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph
    from core.network_intelligence.anomaly_engine import AnomalyEngine
    from core.network_intelligence.health_engine import NetworkHealthEngine

    evidence_svc = get_unified_evidence_service()
    bundle = evidence_svc.assemble_evidence_bundle(allow_live_collection=False)
    kg = NetworkKnowledgeGraph.from_evidence_bundle(bundle)

    anom_engine = AnomalyEngine()
    anomalies = anom_engine.detect_anomalies(bundle, graph=kg)

    health_engine = NetworkHealthEngine()
    health = health_engine.evaluate_health(bundle, graph=kg, anomalies=anomalies)

    return {
        "success": True,
        "health": health,
    }


@router.post("/impact", summary="Evaluate change impact on network reachability and redundancy")
def analyze_change_impact_endpoint(
    body: ChangeImpactIn,
    _auth=Depends(require_topology_admin),
):
    from core.network_intelligence.evidence_service import get_unified_evidence_service
    from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph
    from core.network_intelligence.impact_analyzer import ImpactAnalyzer

    evidence_svc = get_unified_evidence_service()
    bundle = evidence_svc.assemble_evidence_bundle(allow_live_collection=False)
    kg = NetworkKnowledgeGraph.from_evidence_bundle(bundle)

    analyzer = ImpactAnalyzer()
    res = analyzer.analyze_impact(
        bundle=bundle,
        graph=kg,
        target_entity_id=body.target_entity_id,
        target_entity_type=body.target_entity_type,
        impact_scope_type=body.scope,
    )
    return {
        "success": True,
        "impact": res.to_dict(),
    }


@router.post("/simulations", summary="Run in-memory failure simulation (strictly non-mutating)")
def simulate_failure_endpoint(
    body: FailureSimulationIn,
    _auth=Depends(require_topology_admin),
):
    from core.network_intelligence.evidence_service import get_unified_evidence_service
    from core.network_intelligence.knowledge_graph import NetworkKnowledgeGraph
    from core.network_intelligence.failure_simulator import FailureSimulator

    evidence_svc = get_unified_evidence_service()
    bundle = evidence_svc.assemble_evidence_bundle(allow_live_collection=False)
    kg = NetworkKnowledgeGraph.from_evidence_bundle(bundle)

    sim = FailureSimulator()
    res = sim.simulate_failure(
        bundle=bundle,
        graph=kg,
        failure_type=body.failure_type,
        entity_id=body.entity_id,
    )
    return {
        "success": True,
        "simulation": res.to_dict(),
    }


@router.get("/history", summary="Query historical snapshot differences, trends, and recurring incidents")
def get_historical_intelligence_endpoint(
    older_snapshot_id: Optional[str] = Query(default=None),
    newer_snapshot_id: Optional[str] = Query(default=None),
):
    from core.network_intelligence.historical_intelligence import HistoricalIntelligenceEngine

    engine = HistoricalIntelligenceEngine()
    recurring = engine.detect_recurring_incidents()
    diff = None
    if older_snapshot_id and newer_snapshot_id:
        diff = engine.compare_snapshots(older_snapshot_id, newer_snapshot_id)

    return {
        "success": True,
        "history": {
            "recurring_incidents": recurring,
            "snapshot_diff": diff,
        }
    }


@router.get("/evidence/{evidence_id}", summary="Retrieve a specific canonical evidence artifact")
def get_canonical_evidence_endpoint(evidence_id: str):
    from core.network_intelligence.evidence_service import get_unified_evidence_service
    svc = get_unified_evidence_service()
    rec = svc.get_evidence_by_id(evidence_id)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bukti kanonikal '{evidence_id}' tidak ditemukan di memori atau cache.",
        )
    return {
        "success": True,
        "evidence": rec.to_dict(),
    }


# ---------------------------------------------------------------------------
# Workstream D: Automatic Device Onboarding Endpoints
# ---------------------------------------------------------------------------

class DeviceOnboardIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=64)
    host: str = Field(..., min_length=3, max_length=255)
    port: int = Field(22, ge=1, le=65535)
    device_type: str = "ROUTER"
    vendor: str = "MikroTik"
    username: Optional[str] = None
    password: Optional[str] = None
    credential_ref: Optional[str] = None
    site_id: str = "site_default"
    tenant_id: str = "tenant_internal"


@router.post("/devices/onboard", summary="Execute automated device onboarding, capability discovery, and initial investigation")
def onboard_device_endpoint(body: DeviceOnboardIn):
    from core.network_intelligence.onboarding import get_onboarding_engine
    engine = get_onboarding_engine()
    return engine.onboard_device(
        name=body.name,
        host=body.host,
        port=body.port,
        device_type=body.device_type,
        vendor=body.vendor,
        username=body.username,
        password=body.password,
        credential_ref=body.credential_ref,
        site_id=body.site_id,
        tenant_id=body.tenant_id,
    )


# ---------------------------------------------------------------------------
# Workstream E: AI Action Management, Approval & Execution Endpoints
# ---------------------------------------------------------------------------

class ActionProposeIn(BaseModel):
    action_name: str = Field(..., min_length=2, max_length=128)
    target_devices: List[str] = Field(default_factory=list)
    description: str = Field(..., min_length=5)
    reason: str = Field(..., min_length=5)
    before_state: Dict[str, Any] = Field(default_factory=dict)
    proposed_changes: Dict[str, Any] = Field(default_factory=dict)
    expected_after_state: Dict[str, Any] = Field(default_factory=dict)
    diff_text: str = ""
    verification_plan: str = ""
    rollback_plan: str = ""
    rollback_supported: bool = False
    investigation_id: Optional[str] = None


class ActionResolveIn(BaseModel):
    approved: bool
    notes: str = ""


class OperationsPolicyUpdateIn(BaseModel):
    enable_auto_low_risk: Optional[bool] = None
    require_medium_risk_approval: Optional[bool] = None


@router.get("/actions", summary="List proposed, pending, executing, and completed network actions")
def list_actions_endpoint(status: Optional[str] = Query(None), limit: int = Query(50, ge=1, le=200)):
    from core.network_intelligence.action_engine import get_action_engine
    engine = get_action_engine()
    actions = engine.list_actions(status=status, limit=limit)
    return {"success": True, "actions": actions}


@router.post("/actions", summary="Propose an evidence-backed network configuration or remediation action")
def propose_action_endpoint(body: ActionProposeIn):
    from core.network_intelligence.action_engine import get_action_engine
    engine = get_action_engine()
    action = engine.propose_action(
        action_name=body.action_name,
        target_devices=body.target_devices,
        description=body.description,
        reason=body.reason,
        before_state=body.before_state,
        proposed_changes=body.proposed_changes,
        expected_after_state=body.expected_after_state,
        diff_text=body.diff_text,
        verification_plan=body.verification_plan,
        rollback_plan=body.rollback_plan,
        rollback_supported=body.rollback_supported,
        investigation_id=body.investigation_id,
    )
    return {"success": True, "action": action.to_dict()}


@router.get("/actions/{action_id}", summary="Get detailed action record with diff, verification, and approval info")
def get_action_endpoint(action_id: str):
    from core.network_intelligence.action_engine import get_action_engine
    engine = get_action_engine()
    action = engine.get_action(action_id)
    if not action:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Action '{action_id}' not found.")
    return {"success": True, "action": action}


@router.post("/actions/{action_id}/resolve", summary="Approve or reject a pending action (Admin Control)")
def resolve_action_approval_endpoint(action_id: str, body: ActionResolveIn):
    from core.network_intelligence.action_engine import get_action_engine
    engine = get_action_engine()
    res = engine.resolve_approval(action_id=action_id, approved=body.approved, reviewer_id="admin_user", notes=body.notes)
    if not res.get("success"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=res.get("error", "Failed to resolve approval"))
    return res


@router.post("/actions/{action_id}/execute", summary="Execute an approved action with precondition validation and post-verification")
def execute_action_endpoint(action_id: str):
    from core.network_intelligence.action_engine import get_action_engine
    engine = get_action_engine()
    res = engine.execute_and_verify_action(action_id=action_id, operator_id="admin_operator")
    if not res.get("success"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=res.get("error", "Execution failed"))
    return res


@router.get("/actions/policy", summary="Get AI operations and approval policy")
def get_operations_policy_endpoint(tenant_id: str = "tenant_internal"):
    from core.network_intelligence.action_engine import get_action_engine
    engine = get_action_engine()
    policy = engine.get_operations_policy(tenant_id=tenant_id)
    return {"success": True, "policy": policy.to_dict()}


@router.put("/actions/policy", summary="Update AI operations policy (Strict: High/Critical approval can never be bypassed)")
def update_operations_policy_endpoint(body: OperationsPolicyUpdateIn, tenant_id: str = "tenant_internal"):
    from core.network_intelligence.action_engine import get_action_engine
    engine = get_action_engine()
    policy = engine.update_operations_policy(tenant_id=tenant_id, policy_data=body.dict(exclude_none=True))
    return {"success": True, "policy": policy.to_dict()}
