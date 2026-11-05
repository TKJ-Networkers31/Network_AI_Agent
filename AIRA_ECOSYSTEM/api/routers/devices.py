"""
api/routers/devices.py — REST untuk Inventory (device + credential), menggantikan
router lama yang membaca router.yaml.

GET /api/devices tetap mengembalikan {"success", "count", "devices": [...]} sehingga
AkaneWorkspace.jsx dan halaman lama tetap jalan.

Secret TIDAK PERNAH keluar dari API ini (hanya has_secret).
"""

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.inventory_store import CREDENTIAL_TYPES, get_inventory_store
from core.tenant.auth_deps import require_permission
from core.tenant.models import TenantContext

logger = logging.getLogger("aira.devices")

router = APIRouter(prefix="/api", tags=["inventory"], dependencies=[Depends(require_permission("inventory.read"))])


def _dump(model: BaseModel) -> dict:
    dump = getattr(model, "model_dump", None) or model.dict
    return dump(exclude_unset=True)


def _unwrap(result: dict) -> dict:
    if result.get("success"):
        return result

    raise HTTPException(
        status_code=404 if result.get("not_found") else 400,
        detail=result.get("error", "Permintaan gagal."),
    )


# ------------------------------------------------------------ models

class DeviceIn(BaseModel):
    name: str
    host: str
    port: int = 22
    username: Optional[str] = None
    device_type: str = "mikrotik"
    snmp_community: Optional[str] = None
    snmp_port: int = 161
    note: str = ""
    enabled: bool = True
    credential_names: list[str] = Field(default_factory=list)
    new_credentials: Optional[list[dict]] = None


class DeviceUpdate(BaseModel):
    new_name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    device_type: Optional[str] = None
    snmp_community: Optional[str] = None
    snmp_port: Optional[int] = None
    note: Optional[str] = None
    enabled: Optional[bool] = None
    credential_names: Optional[list[str]] = None
    new_credentials: Optional[list[dict]] = None


class LinkIn(BaseModel):
    credential_name: str


class CredentialIn(BaseModel):
    name: str
    type: str
    username: Optional[str] = None
    secret: Optional[str] = None
    note: str = ""


class CredentialUpdate(BaseModel):
    new_name: Optional[str] = None
    username: Optional[str] = None
    secret: Optional[str] = None
    note: Optional[str] = None


# ------------------------------------------------------------ devices

def sync_inventory_and_topology() -> dict:
    """
    SINKRONISASI DUA ARAH (BIDIRECTIONAL INTEGRATION)
    Memastikan semua perangkat di Inventory (devices) terdaftar di Topology & NMS,
    dan semua perangkat di Topology/NMS (hasil scan discovery / tambah manual)
    terdaftar di Inventory.
    """
    try:
        from core.inventory_store import get_inventory_store
        from core.topology_engine import get_topology_engine
        from core.nms_engine import get_nms_engine

        inv = get_inventory_store()
        topo = get_topology_engine()
        nms = get_nms_engine()

        inv_res = inv.list_devices()
        inv_devices = inv_res.get("devices", []) if inv_res.get("success") else []
        topo_data = topo.get_topology()
        topo_nodes = topo_data.get("nodes", [])

        # 1. Inventory -> Topology & NMS
        topo_ips = {n.get("ip"): n for n in topo_nodes if n.get("ip")}
        topo_names = {n.get("name", "").lower(): n for n in topo_nodes if n.get("name")}

        for dev in inv_devices:
            name = dev.get("name")
            host = dev.get("host")
            if not name or not host:
                continue
            matched = topo_ips.get(host) or topo_names.get(name.lower())
            node_id = matched["id"] if matched else f"node_{re.sub(r'[^a-zA-Z0-9_-]', '_', name.lower())}"
            if not matched:
                topo.upsert_node(
                    node_id=node_id,
                    name=name,
                    identity=name,
                    ip=host,
                    device_type=dev.get("device_type") or "router",
                    status="offline",
                    ownership_status="owned",
                    provenance="user_managed",
                )
                nms.upsert_device_profile(
                    device_id=node_id,
                    name=name,
                    ip=host,
                    device_type=dev.get("device_type") or "router",
                    management_mode="managed",
                    ownership_status="owned",
                    monitoring_enabled=True,
                    monitoring_method="icmp_ping",
                )

        # 2. Topology -> Inventory (Keep unmanaged discovered nodes pending; do not inject dummy credentials)
        return {"success": True}
    except Exception as exc:
        logger.warning("Gagal sinkronisasi inventory dan topologi: %s", exc)
        return {"success": False, "error": str(exc)}

@router.get("/devices")
def list_devices():
    sync_inventory_and_topology()
    return _unwrap(get_inventory_store().list_devices())


@router.post("/devices/sync")
def trigger_sync():
    res = sync_inventory_and_topology()
    return {"success": True, "result": res, "devices": _unwrap(get_inventory_store().list_devices())}


@router.post("/devices")
def create_device(body: DeviceIn, _perm: TenantContext = Depends(require_permission("inventory.create"))):
    res = _unwrap(get_inventory_store().create_device(**_dump(body)))
    try:
        from core.topology_engine import get_topology_engine
        from core.nms_engine import get_nms_engine

        node_id = f"node_{re.sub(r'[^a-zA-Z0-9_-]', '_', body.name.lower())}"
        topo = get_topology_engine()
        topo.upsert_node(
            node_id=node_id,
            name=body.name,
            identity=body.name,
            ip=body.host,
            device_type=body.device_type or "router",
            status="offline",
            ownership_status="owned",
            provenance="user_managed",
        )

        nms = get_nms_engine()
        nms.upsert_device_profile(
            device_id=node_id,
            name=body.name,
            ip=body.host,
            device_type=body.device_type or "router",
            management_mode="managed",
            ownership_status="owned",
            monitoring_enabled=True,
            monitoring_method="icmp_ping",
        )
    except Exception as exc:
        logger.warning("Gagal sinkronisasi perangkat ke Topology/NMS: %s", exc)
    return res


@router.get("/devices/pending-discovered")
def list_pending_discovered():
    """
    Lists discovered devices that are pending identification or credentials.
    Exposes clear states: Discovered, SNMP accessible, Credential required.
    """
    try:
        from core.topology_engine import get_topology_engine
        topo = get_topology_engine()
        nodes = topo.get_topology().get("nodes", [])

        inv = get_inventory_store()
        inv_res = inv.list_devices()
        inv_ips = {d.get("host") for d in (inv_res.get("devices") or []) if d.get("host")}
        inv_names = {d.get("name", "").lower() for d in (inv_res.get("devices") or []) if d.get("name")}

        pending = []
        for n in nodes:
            ip = (n.get("ip") or "").strip()
            name = (n.get("name") or "").strip()
            if ip in inv_ips or name.lower() in inv_names:
                continue

            status_desc = "Perangkat terdeteksi — Membutuhkan kredensial akses."
            if n.get("snmp_accessible") or n.get("monitoring_method") == "snmp":
                status_desc = "Device discovered — SNMP available — SSH credentials not configured."
            elif n.get("reachability_status") == "reachable":
                status_desc = "Device discovered — Reachable via ICMP — Credentials required."

            pending.append({
                "node_id": n.get("id"),
                "name": name,
                "ip": ip,
                "device_type": n.get("device_type") or "router",
                "vendor": n.get("vendor") or "MikroTik",
                "discovery_status": n.get("discovery_status") or "discovered",
                "management_status": "credential_required",
                "status_description": status_desc,
                "first_seen": n.get("first_seen"),
                "last_seen": n.get("last_seen"),
                "suggested_action": "Add to Inventory / Configure Access",
            })

        return {"success": True, "count": len(pending), "pending_devices": pending}
    except Exception as exc:
        logger.exception("Failed to list pending discovered devices")
        return {"success": False, "error": str(exc), "pending_devices": []}


@router.post("/devices/promote-discovered")
def promote_discovered(body: PromoteDiscoveredDeviceIn):
    """
    Promotes a discovered topology device to fully managed status in Inventory and NMS.
    Attaches credentials without recreating its topology relationships or interfaces.
    """
    from core.topology_engine import get_topology_engine
    from core.nms_engine import get_nms_engine

    topo = get_topology_engine()
    nodes = topo.get_topology().get("nodes", [])
    target_node = next((n for n in nodes if n.get("id") == body.node_id), None)
    if not target_node:
        raise HTTPException(status_code=404, detail=f"Discovered node '{body.node_id}' not found in topology.")

    dev_name = body.name or target_node.get("name") or target_node.get("identity") or f"device_{body.node_id}"
    dev_host = body.host or target_node.get("ip")
    if not dev_host:
        raise HTTPException(status_code=400, detail="Cannot promote device without valid management IP.")

    inv = get_inventory_store()

    cred_names = list(body.credential_names)
    new_creds = list(body.new_credentials or [])
    if body.password:
        new_creds.append({
            "name": f"cred_{re.sub(r'[^a-zA-Z0-9_-]', '_', dev_name.lower())}_ssh",
            "type": "ssh_password",
            "username": body.username,
            "secret": body.password,
            "note": f"Auto-created credential for promoted device {dev_name}",
        })

    create_res = inv.create_device(
        name=dev_name,
        host=dev_host,
        port=body.port,
        username=body.username,
        device_type=body.device_type or target_node.get("device_type") or "mikrotik",
        credential_names=cred_names,
        new_credentials=new_creds if new_creds else None,
        note=body.note or f"Promoted from discovered topology node ({body.node_id})",
    )
    if not create_res.get("success"):
        raise HTTPException(status_code=400, detail=create_res.get("error", "Failed to add device to inventory."))

    topo.upsert_node(
        node_id=body.node_id,
        name=dev_name,
        identity=dev_name,
        ip=dev_host,
        device_type=body.device_type,
        provenance="user_managed",
        management_status="managed",
    )

    nms = get_nms_engine()
    nms.upsert_device_profile(
        device_id=body.node_id,
        name=dev_name,
        ip=dev_host,
        device_type=body.device_type,
        management_mode="managed",
        ownership_status="owned",
        monitoring_enabled=True,
    )

    return {
        "success": True,
        "message": f"Device '{dev_name}' successfully promoted to managed inventory.",
        "device": create_res.get("device"),
        "node_id": body.node_id,
    }


@router.get("/devices/{name}")
def get_device(name: str):
    return _unwrap(get_inventory_store().get_device(name))


@router.put("/devices/{name}")
def update_device(name: str, body: DeviceUpdate, _perm: TenantContext = Depends(require_permission("inventory.update"))):
    res = _unwrap(get_inventory_store().update_device(name, **_dump(body)))
    try:
        from core.topology_engine import get_topology_engine
        from core.nms_engine import get_nms_engine

        topo = get_topology_engine()
        nms = get_nms_engine()
        node_id = f"node_{re.sub(r'[^a-zA-Z0-9_-]', '_', name.lower())}"

        topo_data = topo.get_topology()
        matched = next((n for n in topo_data.get("nodes", []) if n.get("id") == node_id or n.get("name") == name), None)
        if matched:
            new_name = getattr(body, "new_name", None) or getattr(body, "name", None) or name
            topo.upsert_node(
                node_id=matched["id"],
                name=new_name,
                ip=body.host if body.host else matched.get("ip"),
                device_type=body.device_type if body.device_type else matched.get("device_type", "router"),
                provenance="user_managed",
            )
            nms.upsert_device_profile(
                device_id=matched["id"],
                display_name=new_name,
                host=body.host if body.host else matched.get("ip"),
                management_mode="managed",
            )
    except Exception as exc:
        logger.warning("Gagal sinkronisasi update perangkat ke Topology/NMS: %s", exc)
    return res


@router.delete("/devices/{name}")
def delete_device(name: str, _perm: TenantContext = Depends(require_permission("inventory.delete"))):
    store = get_inventory_store()
    dev_info = store.get_device(name)
    dev_host = dev_info.get("device", {}).get("host") if dev_info.get("success") else None

    res = _unwrap(store.delete_device(name))
    try:
        from core.topology_engine import get_topology_engine

        topo = get_topology_engine()
        node_id = f"node_{re.sub(r'[^a-zA-Z0-9_-]', '_', name.lower())}"
        topo.delete_node(node_id)

        topo_data = topo.get_topology()
        for n in topo_data.get("nodes", []):
            if n.get("name") == name or (dev_host and n.get("ip") == dev_host):
                topo.delete_node(n["id"])
    except Exception as exc:
        logger.warning("Gagal sinkronisasi hapus perangkat ke Topology/NMS: %s", exc)
    return res


@router.post("/devices/{name}/credentials")
def link_credential(name: str, body: LinkIn):
    return _unwrap(get_inventory_store().link_credential(name, body.credential_name))


@router.delete("/devices/{name}/credentials/{credential_name}")
def unlink_credential(name: str, credential_name: str):
    return _unwrap(get_inventory_store().unlink_credential(name, credential_name))


@router.post("/devices/{name}/test")
def test_device(name: str):
    """Diagnostik: tes koneksi ke perangkat RouterOS lewat Network MCP Server."""
    from core.mcp.client import get_network_mcp_client

    result = get_network_mcp_client().call_tool(
        "mikrotik_execute_command",
        {"device_name": name, "command": "/system identity print"},
    )

    return {
        "success": bool(result.get("success")),
        "device": result.get("device", name),
        "host": result.get("host"),
        "output": result.get("output"),
        "error": result.get("error"),
    }


# ------------------------------------------------------------ credentials

@router.get("/credentials")
def list_credentials():
    data = _unwrap(get_inventory_store().list_credentials())
    data["types"] = [{"value": key, "label": label} for key, label in CREDENTIAL_TYPES.items()]
    return data


@router.post("/credentials")
def create_credential(body: CredentialIn):
    return _unwrap(get_inventory_store().create_credential(**_dump(body)))


@router.put("/credentials/{name}")
def update_credential(name: str, body: CredentialUpdate):
    return _unwrap(get_inventory_store().update_credential(name, **_dump(body)))


@router.delete("/credentials/{name}")
def delete_credential(name: str):
    return _unwrap(get_inventory_store().delete_credential(name))

class PromoteDiscoveredDeviceIn(BaseModel):
    node_id: str
    name: Optional[str] = None
    host: Optional[str] = None
    port: int = 22
    username: str = "admin"
    password: Optional[str] = None
    device_type: str = "mikrotik"
    credential_names: list[str] = Field(default_factory=list)
    new_credentials: Optional[list[dict]] = None
    note: str = ""