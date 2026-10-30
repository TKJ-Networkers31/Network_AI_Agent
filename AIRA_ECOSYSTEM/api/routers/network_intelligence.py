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
)

logger = logging.getLogger("aira.api.network_intelligence")

router = APIRouter(prefix="/api/intelligence", tags=["network_intelligence"])


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
