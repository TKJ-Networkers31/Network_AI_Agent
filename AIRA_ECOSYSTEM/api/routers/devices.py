"""
api/routers/devices.py — REST untuk Inventory (device + credential), menggantikan
router lama yang membaca router.yaml.

GET /api/devices tetap mengembalikan {"success", "count", "devices": [...]} sehingga
AkaneWorkspace.jsx dan halaman lama tetap jalan.

Secret TIDAK PERNAH keluar dari API ini (hanya has_secret).
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.inventory_store import CREDENTIAL_TYPES, get_inventory_store

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

@router.get("/devices")
def list_devices():
    return _unwrap(get_inventory_store().list_devices())


@router.post("/devices")
def create_device(body: DeviceIn):
    return _unwrap(get_inventory_store().create_device(**_dump(body)))


@router.get("/devices/{name}")
def get_device(name: str):
    return _unwrap(get_inventory_store().get_device(name))


@router.put("/devices/{name}")
def update_device(name: str, body: DeviceUpdate):
    return _unwrap(get_inventory_store().update_device(name, **_dump(body)))


@router.delete("/devices/{name}")
def delete_device(name: str):
    return _unwrap(get_inventory_store().delete_device(name))


@router.post("/devices/{name}/credentials")
def link_credential(name: str, body: LinkIn):
    return _unwrap(get_inventory_store().link_credential(name, body.credential_name))


@router.delete("/devices/{name}/credentials/{credential_name}")
def unlink_credential(name: str, credential_name: str):
    return _unwrap(get_inventory_store().unlink_credential(name, credential_name))


@router.post("/devices/{name}/test")
def test_device(name: str):
    """Diagnostik: coba SSH sungguhan (/system identity print) lewat pool SSH yang sama dengan tool AIRA."""
    from tools.ssh.client import ssh_execute

    result = ssh_execute(name, "/system identity print")

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