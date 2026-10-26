"""
tools/inventory.py — daftar device untuk AIRA (sekarang dari database/inventory.db).

Bentuk keluaran list_devices() tetap kompatibel dengan versi YAML lama
(name, host, port, username), ditambah field baru.
"""

from core.inventory_store import get_inventory_store


def list_devices(include_disabled: bool = False):
    try:
        result = get_inventory_store().list_devices(enabled_only=not include_disabled)

        if not result.get("success"):
            return {"success": False, "error": result.get("error", "Gagal membaca inventory.")}

        devices = [
            {
                "name": d["name"],
                "host": d["host"],
                "port": d["port"],
                "username": d["username"],
                "device_type": d["device_type"],
                "enabled": d["enabled"],
                "note": d["note"],
                "credentials": [{"name": c["name"], "type": c["type"]} for c in d["credentials"]],
            }
            for d in result["devices"]
        ]

        return {"success": True, "count": len(devices), "devices": devices}

    except Exception as exc:
        return {"success": False, "error": str(exc)}