"""
api/routers/management.py — REST API for Multi-Path Device Management (IP, MAC, RoMON).

Provides administrative control and observability over management paths:
- Device management profile & path inspection
- Manual administrative path override
- Per-path connectivity diagnostics
- RoMON neighbor discovery & multi-hop topology
- Controlled, approval-governed RoMON provisioning & rollback
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.management import (
    DeviceManagementProfile,
    ManagementMethod,
    MultiPathManager,
    RomonManager,
    get_multi_path_manager,
)
from core.tenant.auth_deps import require_permission
from core.tenant.models import TenantContext

logger = logging.getLogger("vera.api.management")

router = APIRouter(prefix="/api", tags=["management"], dependencies=[Depends(require_permission("devices.read"))])


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------
class SelectManagementPathIn(BaseModel):
    preferred_method: Optional[str] = Field(None, description="Method name: ssh_ip | api_ip | mac_telnet | mac_winbox | romon")
    method: Optional[str] = None


class TestPathIn(BaseModel):
    method: str = Field(..., description="Method name to test: ssh_ip | api_ip | mac_telnet | romon")


class RomonPlanIn(BaseModel):
    management_interfaces: Optional[List[str]] = Field(default_factory=lambda: ["bridge", "lan"])
    wan_interfaces: Optional[List[str]] = Field(default_factory=lambda: ["ether1", "wan"])
    custom_secret: Optional[str] = None


class RomonApplyIn(BaseModel):
    plan_token: str
    admin_approved: bool = Field(..., description="Must be explicitly set to True by administrator")


class RomonRollbackIn(BaseModel):
    plan_token: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/devices/{device_id}/management/paths")
def get_device_management_paths(device_id: str):
    """Returns the complete management profile for a device."""
    mgr = get_multi_path_manager()
    profile = mgr.get_profile(device_id)

    if not profile:
        # If not evaluated yet, query inventory/topology to build initial profile
        try:
            from core.inventory_store import get_inventory_store
            inv = get_inventory_store()
            dev_res = inv.get_device(device_id)
            if dev_res.get("success") and dev_res.get("device"):
                dev = dev_res["device"]
                profile = mgr.evaluate_and_save_profile(
                    device_id=device_id,
                    device_name=dev.get("name") or device_id,
                    host=dev.get("host"),
                    mac=dev.get("mac") or None,
                    vendor=dev.get("vendor") or "MikroTik",
                    model=dev.get("model") or "",
                    routeros_version=dev.get("routeros_version") or "",
                )
        except Exception as exc:
            logger.debug("Gagal query inventory untuk initial management profile: %s", exc)

    if not profile:
        raise HTTPException(status_code=404, detail=f"Perangkat '{device_id}' tidak ditemukan di inventory.")

    return {"success": True, "profile": profile.to_dict()}


@router.post("/devices/{device_id}/management/select")
def select_preferred_management_path(
    device_id: str,
    payload: SelectManagementPathIn,
    _auth=Depends(require_permission("devices.execute")),
):
    """Sets an administrative manual override for the preferred management path."""
    mgr = get_multi_path_manager()
    chosen_method = payload.preferred_method or payload.method
    try:
        updated = mgr.set_manual_override(device_id, chosen_method)
        return {
            "success": True,
            "message": f"Metode manajemen '{chosen_method}' berhasil diset sebagai pilihan utama." if chosen_method else "Manual override dinonaktifkan (kembali ke auto-select).",
            "profile": updated.to_dict(),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/devices/{device_id}/management/test")
def test_management_path(
    device_id: str,
    payload: TestPathIn,
    _auth=Depends(require_permission("devices.read")),
):
    """Tests connectivity and latency for a specific management path."""
    mgr = get_multi_path_manager()
    result = mgr.test_path(device_id, payload.method)
    return {"success": result.get("success", False), "result": result}


@router.get("/devices/{device_id}/management/romon/neighbors")
def list_romon_neighbors_for_device(device_id: str):
    """Lists RoMON neighbors discovered via this router or cached globally."""
    mgr = get_multi_path_manager()
    all_neighbors = mgr.list_romon_neighbors()
    # Filter neighbors seen via this device or return all if query is device_id=='all'
    if device_id.lower() != "all":
        neighbors = [n for n in all_neighbors if n.via_device_id == device_id or n.via_device_name == device_id]
        if not neighbors and all_neighbors:
            neighbors = all_neighbors  # Fallback to all discovered neighbors
    else:
        neighbors = all_neighbors

    return {
        "success": True,
        "count": len(neighbors),
        "neighbors": [n.to_dict() for n in neighbors],
    }


@router.post("/devices/{device_id}/management/romon/discover")
def trigger_romon_discovery(
    device_id: str,
    _auth=Depends(require_permission("devices.execute")),
):
    """Triggers `/romon neighbor print detail` on the router and updates RoMON neighbor cache."""
    mgr = get_multi_path_manager()
    profile = mgr.get_profile(device_id)
    device_name = profile.device_name if profile else device_id

    neighbors = RomonManager.discover_neighbors_via_intermediary(
        intermediary_device_id=device_id,
        intermediary_device_name=device_name,
    )
    if neighbors:
        mgr.update_romon_neighbors(neighbors)

    return {
        "success": True,
        "device_id": device_id,
        "device_name": device_name,
        "discovered_count": len(neighbors),
        "neighbors": [n.to_dict() for n in neighbors],
    }


@router.post("/devices/{device_id}/management/romon/plan")
def create_romon_provisioning_plan(
    device_id: str,
    payload: RomonPlanIn,
    _auth=Depends(require_permission("devices.execute")),
):
    """Stage 1: Generates a controlled RoMON provisioning plan requiring approval."""
    mgr = get_multi_path_manager()
    profile = mgr.get_profile(device_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Perangkat '{device_id}' tidak ditemukan.")

    res = RomonManager.prepare_provisioning_plan(
        device_id=device_id,
        device_name=profile.device_name,
        routeros_version=profile.routeros_version,
        management_interfaces=payload.management_interfaces,
        wan_interfaces=payload.wan_interfaces,
        custom_secret=payload.custom_secret,
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error"))

    return res


@router.post("/devices/{device_id}/management/romon/apply")
def apply_romon_provisioning(
    device_id: str,
    payload: RomonApplyIn,
    _auth=Depends(require_permission("devices.execute")),
):
    """Stage 2: Applies RoMON configuration with mandatory administrator approval and verification."""
    res = RomonManager.apply_provisioning(
        plan_token=payload.plan_token,
        admin_approved=payload.admin_approved,
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error"))

    # Refresh device management profile
    mgr = get_multi_path_manager()
    profile = mgr.get_profile(device_id)
    if profile:
        mgr.evaluate_and_save_profile(
            device_id=profile.device_id,
            device_name=profile.device_name,
            host=profile.ip,
            mac=profile.mac,
            vendor=profile.vendor,
            model=profile.model,
            routeros_version=profile.routeros_version,
        )

    return res


@router.post("/devices/{device_id}/management/romon/rollback")
def rollback_romon_provisioning(
    device_id: str,
    payload: RomonRollbackIn,
    _auth=Depends(require_permission("devices.execute")),
):
    """Rolls back an applied RoMON provisioning plan."""
    res = RomonManager.rollback_provisioning(payload.plan_token)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error"))
    return res


@router.get("/management/matrix")
def get_management_matrix():
    """Returns a consolidated multi-path management matrix across all inventory devices."""
    mgr = get_multi_path_manager()
    try:
        from core.inventory_store import get_inventory_store
        inv = get_inventory_store()
        devices = inv.list_devices().get("devices", [])
    except Exception:
        devices = []

    matrix = []
    for d in devices:
        d_name = d.get("name")
        if not d_name:
            continue
        prof = mgr.get_profile(d_name)
        if not prof:
            prof = mgr.evaluate_and_save_profile(
                device_id=d_name,
                device_name=d_name,
                host=d.get("host"),
                mac=d.get("mac"),
                vendor=d.get("vendor") or "MikroTik",
                model=d.get("model") or "",
                routeros_version=d.get("routeros_version") or "",
            )
        matrix.append(prof.to_dict())

    return {
        "success": True,
        "count": len(matrix),
        "devices": matrix,
    }
