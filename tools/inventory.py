from pathlib import Path
import yaml

BASE_DIR = Path(__file__).resolve().parents[1]
INVENTORY_FILE = BASE_DIR / "inventory" / "router.yaml"


def list_devices():
    try:
        with open(INVENTORY_FILE, "r", encoding="utf-8") as file:
            inventory = yaml.safe_load(file) or {}

        devices = inventory.get("devices", {})

        result = []

        for name, device in devices.items():
            result.append({
                "name": name,
                "host": device.get("host"),
                "port": device.get("port", 22),
                "username": device.get("username")
            })

        return {
            "success": True,
            "count": len(result),
            "devices": result
        }

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc)
        }