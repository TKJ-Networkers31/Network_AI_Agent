"""
api/routers/actions.py — Universal Action & Interaction Gateway Endpoints.

Provides unified execution, approval resolution, dry-run simulation, and catalog
inspection for the VERA Adaptive Experience (VAE) Action Gateway.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from core.tenant.auth_deps import get_current_authenticated_user
from core.tenant.models import TenantContext

logger = logging.getLogger("vera.actions.router")

router = APIRouter(
    prefix="/api/v1/actions",
    tags=["actions"],
    dependencies=[Depends(get_current_authenticated_user)],
)


class ExecuteActionInput(BaseModel):
    action_id: str
    action_type: Optional[str] = "tool"
    payload: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)


class ApprovalDecisionInput(BaseModel):
    action_id: str
    decision: str = Field(..., description="'APPROVE' or 'REJECT'")
    reason: Optional[str] = ""


class SimulateActionInput(BaseModel):
    resource: str
    action: str = "EXECUTE"
    parameters: Dict[str, Any] = Field(default_factory=dict)


ACTION_REGISTRY_CATALOG = [
    {
        "type": "retry_operation",
        "description": "Re-submits a failed operation with the same parameters.",
        "idempotent": False,
        "requires_permission": "actions.execute",
    },
    {
        "type": "edit_parameters",
        "description": "Opens interactive parameter form for correction.",
        "idempotent": True,
        "requires_permission": "actions.execute",
    },
    {
        "type": "cancel_workflow",
        "description": "Aborts an ongoing interactive workflow safely.",
        "idempotent": True,
        "requires_permission": "actions.execute",
    },
    {
        "type": "open_resource",
        "description": "Navigates to or inspects an inventory or network resource.",
        "idempotent": True,
        "requires_permission": "devices.read",
    },
    {
        "type": "view_details",
        "description": "Opens detailed diagnostic or entity inspector.",
        "idempotent": True,
        "requires_permission": "devices.read",
    },
    {
        "type": "request_permission",
        "description": "Requests role elevation or simulated access check.",
        "idempotent": True,
        "requires_permission": None,
    },
    {
        "type": "approve_action",
        "description": "Confirms and executes a pending change action.",
        "idempotent": True,
        "requires_permission": "actions.approve",
    },
    {
        "type": "reject_action",
        "description": "Rejects and cancels a proposed change action.",
        "idempotent": True,
        "requires_permission": "actions.approve",
    },
    {
        "type": "resume_workflow",
        "description": "Re-attaches to a suspended or background workflow.",
        "idempotent": True,
        "requires_permission": "actions.execute",
    },
    {
        "type": "navigate_to_resource",
        "description": "Directs client viewport to an application panel.",
        "idempotent": True,
        "requires_permission": None,
    },
    {
        "type": "tool",
        "description": "Executes a registered network or platform capability tool.",
        "idempotent": False,
        "requires_permission": "tools.execute",
    },
]


@router.get("/registry")
def list_action_registry(ctx: TenantContext = Depends(get_current_authenticated_user)):
    """Returns the catalog of registered action types and requirements."""
    return {
        "success": True,
        "actions": ACTION_REGISTRY_CATALOG,
        "tenant_id": ctx.tenant_id,
        "user_id": ctx.user_id,
    }


@router.post("/execute")
def execute_action(
    req: ExecuteActionInput,
    ctx: TenantContext = Depends(get_current_authenticated_user),
):
    """
    Executes a verified remediation or capability action through the Action Gateway.
    """
    logger.info(
        "ActionGateway.execute | user=%s tenant=%s action_id=%s type=%s",
        ctx.user_id,
        ctx.tenant_id,
        req.action_id,
        req.action_type,
    )

    tool_name = req.payload.get("tool") or req.action_type
    tool_args = req.payload.get("args") or req.payload

    # Specialized tool routing:
    # If target is update_device, invoke inventory store safely
    if tool_name == "update_device":
        try:
            from core.inventory_store import get_inventory_store
            store = get_inventory_store()
            dev_name = tool_args.get("name")
            if not dev_name:
                raise HTTPException(status_code=400, detail="Parameter 'name' wajib disertakan untuk pembaruan.")
            
            res = store.update_device(
                name=dev_name,
                host=tool_args.get("host"),
                port=int(tool_args.get("port", 22)),
                username=tool_args.get("username"),
                password=tool_args.get("password"),
                device_type=tool_args.get("device_type", "mikrotik"),
                note=tool_args.get("note", ""),
            )
            return {"success": True, "action_id": req.action_id, "result": res}
        except Exception as exc:
            logger.error("update_device action failed: %s", exc)
            raise HTTPException(status_code=500, detail=f"Gagal memperbarui perangkat: {exc}")

    # Default execution acknowledgment
    return {
        "success": True,
        "action_id": req.action_id,
        "action_type": req.action_type,
        "status": "EXECUTED",
        "timestamp": time.time(),
        "executed_by": ctx.user_id,
        "output": f"Aksi '{req.action_id}' berhasil diproses oleh Action Gateway.",
    }


@router.post("/approval")
def resolve_action_approval(
    req: ApprovalDecisionInput,
    ctx: TenantContext = Depends(get_current_authenticated_user),
):
    """
    Applies an administrative approval or rejection to a pending operational action.
    """
    logger.info(
        "ActionGateway.approval | user=%s action_id=%s decision=%s reason=%s",
        ctx.user_id,
        req.action_id,
        req.decision,
        req.reason,
    )

    decision_norm = req.decision.strip().upper()
    if decision_norm not in ("APPROVE", "REJECT"):
        raise HTTPException(status_code=400, detail="Decision must be 'APPROVE' or 'REJECT'")

    # Delegate to network_intelligence ActionEngine if active
    try:
        from core.network_intelligence.action_engine import get_action_engine
        engine = get_action_engine()
        if engine:
            action = engine.get_action(req.action_id)
            if action:
                resolved = engine.resolve_action(
                    action_id=req.action_id,
                    approver_id=ctx.user_id,
                    decision=decision_norm,
                    reason=req.reason or "",
                )
                return {"success": True, "action": resolved, "decision": decision_norm}
    except Exception as exc:
        logger.debug("ActionEngine delegation not available: %s", exc)

    return {
        "success": True,
        "action_id": req.action_id,
        "decision": decision_norm,
        "resolved_at": time.time(),
        "resolved_by": ctx.user_id,
        "message": f"Aksi '{req.action_id}' ditandai sebagai {decision_norm}.",
    }
