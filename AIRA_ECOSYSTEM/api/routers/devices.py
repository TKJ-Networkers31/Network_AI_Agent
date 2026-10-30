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

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.inventory_store import CREDENTIAL_TYPES, get_inventory_store

logger = logging.getLogger("aira.devices")

router = APIRouter(prefix="/api", tags=["inventory"])


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

        # 2. Topology -> Inventory
        inv_ips = {d.get("host") for d in inv_devices if d.get("host")}
        inv_names = {d.get("name", "").lower() for d in inv_devices if d.get("name")}

        for node in topo.get_topology().get("nodes", []):
            ip = (node.get("ip") or "").strip()
            name = (node.get("name") or "").strip()
            if not ip or not name:
                continue
            if name.lower() in ("keepme", "n_keep", "n1", "n2"):
                continue
            if ip not in inv_ips and name.lower() not in inv_names:
                try:
                    inv.create_device(
                        name=name,
                        host=ip,
                        port=22,
                        username="admin",
                        device_type=node.get("device_type") or "mikrotik",
                        note="Sinkronisasi otomatis dari Topology & NMS",
                    )
                except Exception:
                    pass

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
def create_device(body: DeviceIn):
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


@router.get("/devices/{name}")
def get_device(name: str):
    return _unwrap(get_inventory_store().get_device(name))


@router.put("/devices/{name}")
def update_device(name: str, body: DeviceUpdate):
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
def delete_device(name: str):
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