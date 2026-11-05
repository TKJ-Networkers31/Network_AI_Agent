"""
AIRA OS — Playbook Automation API Router.

Provides endpoints for:
- Viewing built-in and custom Ansible-compatible playbooks
- Validating YAML syntax and structure
- Isolated execution across network inventory targets
- Risk-based approval checks
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from core.playbooks.runner import PlaybookRunner
from core.tenant.models import TenantContext
from core.tenant.auth_deps import require_permission, get_current_authenticated_user

router = APIRouter(prefix="/api/v1/playbooks", tags=["playbooks"], dependencies=[Depends(require_permission("playbooks.read"))])

_playbook_runner = PlaybookRunner()


class ValidateYamlRequest(BaseModel):
    yaml_content: str


class ExecutePlaybookRequest(BaseModel):
    targets: List[str] = Field(..., min_items=1)
    variables: Optional[Dict[str, Any]] = None
    bypass_approval: bool = False


@router.get("")
def list_playbooks(ctx: TenantContext = Depends(get_current_authenticated_user)):
    """Lists built-in and tenant custom playbooks."""
    playbooks = _playbook_runner.list_playbooks(tenant_id=ctx.tenant_id)
    return {"success": True, "playbooks": playbooks}


@router.get("/{playbook_id}")
def get_playbook(playbook_id: str, ctx: TenantContext = Depends(get_current_authenticated_user)):
    """Retrieves detailed playbook information and YAML content."""
    pb = _playbook_runner.get_playbook(playbook_id)
    if not pb:
        raise HTTPException(status_code=404, detail="Playbook not found.")
    return {"success": True, "playbook": pb}


@router.post("/validate")
def validate_playbook(payload: ValidateYamlRequest, ctx: TenantContext = Depends(get_current_authenticated_user)):
    """Validates Ansible-compatible YAML structure."""
    result = _playbook_runner.validate_playbook_yaml(payload.yaml_content)
    return {"success": True, "result": result}


@router.post("/{playbook_id}/execute")
def execute_playbook(
    playbook_id: str,
    payload: ExecutePlaybookRequest,
    ctx: TenantContext = Depends(require_permission("playbooks.execute")),
):
    """Executes a playbook across targets with security isolation and approval checks."""
    try:
        report = _playbook_runner.execute_playbook(
            playbook_id=playbook_id,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            targets=payload.targets,
            variables=payload.variables,
            bypass_approval=payload.bypass_approval,
        )
        return {"success": True, "report": report}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Playbook execution failed: {exc}")
