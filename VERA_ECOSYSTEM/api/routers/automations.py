"""
AIRA OS — Automation & Scheduled Workflows Router.

Exposes REST endpoints for:
- Standard action catalog inspection
- Interval-based and event-driven automation creation
- Manual run triggers and pause/resume control
- Granular execution history and logs
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from core.scheduler import (
    ACTION_CATALOG,
    AutomationDefinition,
    AutomationExecutionRecord,
    TriggerType,
    get_automation_engine,
)
from core.tenant.auth_deps import get_current_authenticated_user, require_permission
from core.tenant.models import TenantContext

router = APIRouter(
    prefix="/api/v1/automations",
    tags=["automations"],
    dependencies=[Depends(get_current_authenticated_user)],
)


class CreateAutomationInput(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: str = Field(default="", max_length=500)
    trigger_type: str = Field(..., description="INTERVAL, CRON, or EVENT")
    trigger_params: Dict[str, Any] = Field(default_factory=dict)
    action_name: str = Field(..., description="Action from action catalog")
    action_params: Dict[str, Any] = Field(default_factory=dict)
    target_resources: List[str] = Field(default_factory=list)
    approval_required: bool = False
    notify_on_failure: bool = True
    tenant_id: Optional[str] = "default"


class ToggleAutomationInput(BaseModel):
    is_enabled: bool


@router.get("/catalog")
def get_action_catalog():
    """Returns the standardized catalog of available automation actions."""
    return {"success": True, "actions": ACTION_CATALOG}


@router.get("")
def list_automations(tenant_id: str = Query(default="default")):
    """Lists all configured automations for the specified tenant."""
    engine = get_automation_engine()
    jobs = engine.list_automations(tenant_id=tenant_id)
    return {"success": True, "automations": [j.to_dict() for j in jobs]}


@router.post("")
def create_automation(
    payload: CreateAutomationInput,
    ctx: TenantContext = Depends(require_permission("automation.create")),
):
    """Registers a new automation."""
    engine = get_automation_engine()
    try:
        job = engine.create_automation(
            tenant_id=payload.tenant_id or "default",
            name=payload.name,
            description=payload.description,
            trigger_type=payload.trigger_type,
            trigger_params=payload.trigger_params,
            action_name=payload.action_name,
            action_params=payload.action_params,
            target_resources=payload.target_resources,
            approval_required=payload.approval_required,
            notify_on_failure=payload.notify_on_failure,
        )
        return {"success": True, "automation": job.to_dict()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{job_id}")
def get_automation(job_id: str):
    """Retrieves an automation definition by ID."""
    engine = get_automation_engine()
    job = engine.get_automation(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Automation not found.")
    return {"success": True, "automation": job.to_dict()}


@router.post("/{job_id}/toggle")
def toggle_automation(
    job_id: str,
    payload: ToggleAutomationInput,
    ctx: TenantContext = Depends(require_permission("automation.update")),
):
    """Enables or pauses an automation."""
    engine = get_automation_engine()
    job = engine.toggle_automation(job_id, payload.is_enabled)
    if not job:
        raise HTTPException(status_code=404, detail="Automation not found.")
    return {"success": True, "automation": job.to_dict()}


@router.post("/{job_id}/run")
def run_automation_now(
    job_id: str,
    ctx: TenantContext = Depends(require_permission("automation.execute")),
):
    """Triggers immediate execution of an automation."""
    engine = get_automation_engine()
    job = engine.get_automation(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Automation not found.")
    exec_record = engine.execute_job(job, trigger_source="MANUAL")
    return {"success": True, "execution": exec_record.to_dict()}


@router.delete("/{job_id}")
def delete_automation(
    job_id: str,
    ctx: TenantContext = Depends(require_permission("automation.update")),
):
    """Deletes an automation."""
    engine = get_automation_engine()
    ok = engine.delete_automation(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Automation not found.")
    return {"success": True, "deleted": True}


@router.get("/{job_id}/executions")
def list_job_executions(job_id: str, limit: int = Query(default=30, ge=1, le=100)):
    """Retrieves execution logs for an automation."""
    engine = get_automation_engine()
    runs = engine.list_executions(job_id=job_id, limit=limit)
    return {"success": True, "executions": [r.to_dict() for r in runs]}
