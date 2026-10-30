"""
api/routers/nms.py — REST API endpoints for AIRA Network Management System & Live Monitoring.
Provides endpoints for overview metrics, device inventory, live & historical telemetry,
incident management, scheduler lifecycle, and the interactive SNMP setup wizard.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from api.routers.topology import require_topology_admin
from core.nms_engine import get_nms_engine

logger = logging.getLogger("aira.api.nms")

router = APIRouter(prefix="/api/nms", tags=["nms"])


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------
class NmsSettingsUpdateIn(BaseModel):
    auto_monitoring_enabled: Optional[bool] = None
    default_interval_sec: Optional[int] = Field(None, ge=5, le=3600)
    failure_threshold: Optional[int] = Field(None, ge=1, le=10)
    recovery_threshold: Optional[int] = Field(None, ge=1, le=10)
    ping_timeout_sec: Optional[float] = Field(None, ge=0.5, le=10.0)
    snmp_timeout_sec: Optional[float] = Field(None, ge=0.5, le=10.0)
    max_concurrent_polls: Optional[int] = Field(None, ge=1, le=50)
    history_retention_days: Optional[int] = Field(None, ge=1, le=90)


class DeviceProfileUpdateIn(BaseModel):
    management_mode: Optional[str] = None
    monitoring_enabled: Optional[bool] = None
    is_paused: Optional[bool] = None
    maintenance_mode: Optional[bool] = None
    snmp_enabled: Optional[bool] = None
    snmp_version: Optional[str] = None
    snmp_community: Optional[str] = None
    snmp_port: Optional[int] = Field(None, ge=1, le=65535)
    snmp_v3_user: Optional[str] = None
    snmp_v3_auth_proto: Optional[str] = None
    snmp_v3_auth_key: Optional[str] = None
    snmp_v3_priv_proto: Optional[str] = None
    snmp_v3_priv_key: Optional[str] = None


class WizardDetectIn(BaseModel):
    host: str
    port: int = 161
    community: str = "public"
    version: str = "v2c"


class WizardGenerateIn(BaseModel):
    community_name: str = "aira-ro"
    allowed_collector_ip: str = "192.168.0.0/24"
    use_v3: bool = False
    v3_user: str = "aira-mgr"
    v3_auth_key: str = "AiraAuthPass123"
    v3_priv_key: str = "AiraPrivPass123"


class WizardVerifyIn(BaseModel):
    device_id: str
    host: str
    port: int = 161
    community: str = "aira-ro"
    version: str = "v2c"


# ---------------------------------------------------------------------------
# Overview & System Status
# ---------------------------------------------------------------------------
@router.get("/overview")
def get_nms_overview():
    engine = get_nms_engine()
    return {"success": True, "overview": engine.get_overview()}


@router.get("/settings")
def get_nms_settings():
    engine = get_nms_engine()
    return {"success": True, "settings": engine.get_settings()}


@router.put("/settings")
def update_nms_settings(body: NmsSettingsUpdateIn, _auth=Depends(require_topology_admin)):
    engine = get_nms_engine()
    raw = body.model_dump() if hasattr(body, "model_dump") else body.dict()
    clean_dict = {k: v for k, v in raw.items() if v is not None}
    updated = engine.update_settings(clean_dict)
    return {"success": True, "settings": updated}


# ---------------------------------------------------------------------------
# Scheduler Controls
# ---------------------------------------------------------------------------
@router.post("/scheduler/start")
def start_scheduler(_auth=Depends(require_topology_admin)):
    engine = get_nms_engine()
    ok = engine.start_monitoring()
    return {"success": True, "is_running": engine.is_running(), "started": ok}


@router.post("/scheduler/stop")
def stop_scheduler(_auth=Depends(require_topology_admin)):
    engine = get_nms_engine()
    ok = engine.stop_monitoring()
    return {"success": True, "is_running": engine.is_running(), "stopped": ok}


@router.post("/scheduler/poll-now")
async def trigger_poll_now(_auth=Depends(require_topology_admin)):
    engine = get_nms_engine()
    asyncio.create_task(engine.poll_all_devices_cycle())
    return {"success": True, "message": "Siklus polling NMS dimulai di latar belakang."}


# ---------------------------------------------------------------------------
# Devices Inventory & Profiles
# ---------------------------------------------------------------------------
@router.get("/devices")
def list_nms_devices(
    status: Optional[str] = Query("all"),
    management_mode: Optional[str] = Query("all"),
    search: Optional[str] = None,
):
    engine = get_nms_engine()
    devices = engine.list_devices(status=status, management_mode=management_mode, search=search)
    return {"success": True, "count": len(devices), "devices": devices}


@router.get("/devices/{device_id}")
def get_nms_device_detail(device_id: str):
    engine = get_nms_engine()
    detail = engine.get_device_detail(device_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Perangkat tidak ditemukan di topologi.")
    return {"success": True, "device": detail}


@router.put("/devices/{device_id}/profile")
def update_device_monitoring_profile(
    device_id: str, body: DeviceProfileUpdateIn, _auth=Depends(require_topology_admin)
):
    engine = get_nms_engine()
    raw = body.model_dump() if hasattr(body, "model_dump") else body.dict()
    clean_dict = {k: v for k, v in raw.items() if v is not None}
    ok = engine.update_device_profile(device_id, clean_dict)
    if not ok:
        raise HTTPException(status_code=400, detail="Gagal memperbarui profil monitoring perangkat.")
    return {"success": True, "message": "Profil monitoring perangkat berhasil diperbarui."}


@router.post("/devices/{device_id}/test")
async def test_single_device(device_id: str, _auth=Depends(require_topology_admin)):
    engine = get_nms_engine()
    detail = engine.get_device_detail(device_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Perangkat tidak ditemukan.")

    host = detail.get("ip")
    if not host:
        raise HTTPException(status_code=400, detail="Perangkat tidak memiliki IP address untuk diuji.")

    settings = engine.get_settings()
    profile = detail.get("profile", {})
    await engine.poll_single_device(device_id=device_id, host=host, profile=profile, settings=settings)

    fresh_detail = engine.get_device_detail(device_id)
    return {"success": True, "device": fresh_detail}


# ---------------------------------------------------------------------------
# Historical Telemetry & Interfaces
# ---------------------------------------------------------------------------
@router.get("/devices/{device_id}/resources/history")
def get_device_resource_history(device_id: str, range: str = Query("1h")):
    engine = get_nms_engine()
    history = engine.get_resource_history(device_id=device_id, time_range=range)
    return {"success": True, "device_id": device_id, "range": range, "history": history}


@router.get("/devices/{device_id}/interfaces/{interface_name:path}/history")
def get_interface_traffic_history(device_id: str, interface_name: str, range: str = Query("1h")):
    engine = get_nms_engine()
    history = engine.get_interface_history(device_id=device_id, interface_name=interface_name, time_range=range)
    return {
        "success": True,
        "device_id": device_id,
        "interface_name": interface_name,
        "range": range,
        "history": history,
    }


# ---------------------------------------------------------------------------
# Incidents & Alerts
# ---------------------------------------------------------------------------
@router.get("/incidents")
def list_incidents(status: Optional[str] = Query("open"), limit: int = Query(50, le=200)):
    engine = get_nms_engine()
    incidents = engine.list_incidents(status=status, limit=limit)
    return {"success": True, "count": len(incidents), "incidents": incidents}


@router.post("/incidents/{incident_id}/acknowledge")
def acknowledge_incident(incident_id: int, _auth=Depends(require_topology_admin)):
    engine = get_nms_engine()
    ok = engine.acknowledge_incident(incident_id)
    return {"success": ok, "message": "Insiden berhasil diakui (acknowledged)."}


# ---------------------------------------------------------------------------
# SNMP Setup Wizard
# ---------------------------------------------------------------------------
@router.post("/wizard/detect")
async def wizard_detect_snmp(body: WizardDetectIn, _auth=Depends(require_topology_admin)):
    engine = get_nms_engine()
    res = await engine.wizard_detect_snmp(
        host=body.host, port=body.port, community=body.community, version=body.version
    )
    return {"success": True, "detection": res}


@router.post("/wizard/generate-commands")
def wizard_generate_commands(body: WizardGenerateIn, _auth=Depends(require_topology_admin)):
    engine = get_nms_engine()
    cmds = engine.wizard_generate_commands(
        community_name=body.community_name,
        allowed_collector_ip=body.allowed_collector_ip,
        use_v3=body.use_v3,
        v3_user=body.v3_user,
        v3_auth_key=body.v3_auth_key,
        v3_priv_key=body.v3_priv_key,
    )
    return {"success": True, "commands": cmds}


@router.post("/wizard/verify-and-save")
async def wizard_verify_and_save(body: WizardVerifyIn, _auth=Depends(require_topology_admin)):
    engine = get_nms_engine()
    res = await engine.wizard_verify_and_save(
        device_id=body.device_id,
        host=body.host,
        port=body.port,
        community=body.community,
        version=body.version,
    )
    return res
