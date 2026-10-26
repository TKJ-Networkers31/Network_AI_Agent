"""
agents/rei/inventory_tools.py — tool AIRA untuk mengelola inventory (device + credential).

Semua lewat core/inventory_store.py; AI tidak pernah menyentuh SQLite langsung dan
TIDAK PERNAH menerima secret kembali (hanya has_secret).

Didaftarkan di agents/rei/registry.py (3 baris di akhir file).
"""

from typing import Any, Optional

from core.inventory_store import CREDENTIAL_TYPES, get_inventory_store


def _store():
    return get_inventory_store()


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "ya")
    return bool(value)


def _tag(result: dict, tool: str) -> dict:
    result["tool"] = tool
    return result


# ============================================================ DEVICES

def add_device(
    name: str, host: str, port: Any = 22, username: Optional[str] = "admin",
    device_type: str = "mikrotik", note: str = "", password: Any = None,
    no_password: Any = False, ssh_key: Optional[str] = None,
    credential_name: Optional[str] = None, snmp_community: Optional[str] = None, **_ignored,
) -> dict:
    new_credential = None
    credential_names = None

    if credential_name:
        credential_names = [str(credential_name)]
    elif ssh_key:
        new_credential = {"name": f"{name}-ssh-key", "type": "ssh_key", "username": username, "secret": ssh_key}
    elif _as_bool(no_password):
        new_credential = {"name": f"{name}-ssh", "type": "ssh_password", "username": username, "secret": ""}
    elif password is not None:
        new_credential = {"name": f"{name}-ssh", "type": "ssh_password", "username": username, "secret": str(password)}

    result = _store().create_device(
        name=name, host=host, port=port, username=username, device_type=device_type,
        note=note, snmp_community=snmp_community,
        credential_names=credential_names, new_credential=new_credential,
    )

    if result.get("success"):
        device = result["device"]
        result["note_for_ai"] = (
            f"Device '{device['name']}' TERSIMPAN di inventory. "
            + ("Sekarang panggil connect_device untuk membuka koneksi."
               if device["credentials"] else
               "Device ini BELUM punya credential SSH - minta user memberi password/key (atau 'tanpa password') "
               "lalu panggil add_credential + link_credential sebelum connect_device.")
        )

    return _tag(result, "add_device")


def update_device(
    name: str, new_name: Optional[str] = None, host: Optional[str] = None, port: Any = None,
    username: Optional[str] = None, device_type: Optional[str] = None, note: Optional[str] = None,
    enabled: Any = None, snmp_community: Optional[str] = None, **_ignored,
) -> dict:
    fields = {
        "new_name": new_name, "host": host, "port": port, "username": username,
        "device_type": device_type, "note": note, "snmp_community": snmp_community,
    }
    fields = {key: value for key, value in fields.items() if value is not None}

    if enabled is not None:
        fields["enabled"] = _as_bool(enabled, True)

    if not fields:
        return {"success": False, "tool": "update_device", "error": "Tidak ada field yang diubah."}

    return _tag(_store().update_device(name, **fields), "update_device")


def delete_device(name: str, confirm: Any = False, **_ignored) -> dict:
    if not _as_bool(confirm):
        return {
            "success": False, "tool": "delete_device",
            "error": f"Tanyakan konfirmasi ke user dulu, lalu panggil lagi dengan confirm=true untuk menghapus '{name}'.",
        }

    return _tag(_store().delete_device(name), "delete_device")


# ============================================================ CREDENTIALS

def list_credentials(**_ignored) -> dict:
    return _tag(_store().list_credentials(), "list_credentials")


def add_credential(
    name: str, type: str, secret: Any = None, username: Optional[str] = None,
    note: str = "", no_password: Any = False, link_to_device: Optional[str] = None, **_ignored,
) -> dict:
    if _as_bool(no_password) and type == "ssh_password":
        secret = ""

    result = _store().create_credential(
        name=name, type=type, username=username, note=note,
        secret=None if secret is None else str(secret),
    )

    if result.get("success") and link_to_device:
        linked = _store().link_credential(link_to_device, name)
        result["linked"] = bool(linked.get("success"))
        if not linked.get("success"):
            result["link_error"] = linked.get("error")

    return _tag(result, "add_credential")


def link_credential(device_name: str, credential_name: str, **_ignored) -> dict:
    return _tag(_store().link_credential(device_name, credential_name), "link_credential")


# ============================================================ registry-ready

INVENTORY_TOOLS = {
    "add_device": add_device,
    "update_device": update_device,
    "delete_device": delete_device,
    "list_credentials": list_credentials,
    "add_credential": add_credential,
    "link_credential": link_credential,
}

INVENTORY_TOOL_CATEGORY = {name: "inventory" for name in INVENTORY_TOOLS}

_TYPES = ", ".join(CREDENTIAL_TYPES)

INVENTORY_TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "add_device",
        "description": (
            "MENYIMPAN perangkat baru ke inventory (database). WAJIB dipanggil untuk 'daftarkan/tambah device' - "
            "form saja TIDAK menyimpan apa pun. Jangan pernah bilang device sudah tersimpan sebelum tool ini "
            "mengembalikan success=true. Kalau user memberi password isi 'password'; kalau user bilang tanpa "
            "password isi no_password=true; kalau pakai private key isi 'ssh_key'; kalau credential sudah ada isi "
            "'credential_name'. Credential otomatis dibuat dan dikaitkan ke device. Setelah sukses, lanjut connect_device."
        ),
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Nama unik device, mis. R_tes (tanpa spasi)."},
            "host": {"type": "string", "description": "IP atau hostname, mis. 192.168.1.1."},
            "port": {"type": "integer", "description": "Port SSH (default 22).", "default": 22},
            "username": {"type": "string", "description": "Username SSH (default admin).", "default": "admin"},
            "device_type": {"type": "string", "description": "mikrotik | linux | switch | olt | server | lainnya.", "default": "mikrotik"},
            "password": {"type": "string", "description": "Password SSH."},
            "no_password": {"type": "boolean", "description": "True kalau login TANPA password.", "default": False},
            "ssh_key": {"type": "string", "description": "Isi private key (alternatif password)."},
            "credential_name": {"type": "string", "description": "Pakai credential yang sudah ada (lihat list_credentials)."},
            "snmp_community": {"type": "string", "description": "SNMP community (opsional)."},
            "note": {"type": "string", "description": "Catatan bebas (lokasi, fungsi, dst)."},
        }, "required": ["name", "host"]},
    }},
    {"type": "function", "function": {
        "name": "update_device",
        "description": "Mengubah data device yang sudah ada di inventory (host, port, username, tipe, catatan, aktif/nonaktif, ganti nama via new_name).",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Nama device yang diubah."},
            "new_name": {"type": "string"}, "host": {"type": "string"}, "port": {"type": "integer"},
            "username": {"type": "string"}, "device_type": {"type": "string"}, "note": {"type": "string"},
            "enabled": {"type": "boolean"}, "snmp_community": {"type": "string"},
        }, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "delete_device",
        "description": "Menghapus device dari inventory (credential tetap ada). WAJIB tanya konfirmasi user dulu, lalu panggil dengan confirm=true.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"},
            "confirm": {"type": "boolean", "default": False},
        }, "required": ["name"]},
    }},
    {"type": "function", "function": {
        "name": "list_credentials",
        "description": "Melihat daftar credential di inventory (tanpa isi secret) beserta device yang memakainya.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "add_credential",
        "description": (
            f"Membuat credential baru. type: {_TYPES}. ssh_password boleh secret kosong (no_password=true) untuk "
            "login tanpa password. link_to_device (opsional) langsung mengaitkannya ke device."
        ),
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Nama unik credential."},
            "type": {"type": "string", "description": _TYPES},
            "secret": {"type": "string", "description": "Password / private key / api key / community."},
            "username": {"type": "string"}, "note": {"type": "string"},
            "no_password": {"type": "boolean", "default": False},
            "link_to_device": {"type": "string", "description": "Nama device yang langsung dikaitkan."},
        }, "required": ["name", "type"]},
    }},
    {"type": "function", "function": {
        "name": "link_credential",
        "description": "Mengaitkan credential yang sudah ada ke sebuah device.",
        "parameters": {"type": "object", "properties": {
            "device_name": {"type": "string"}, "credential_name": {"type": "string"},
        }, "required": ["device_name", "credential_name"]},
    }},
]