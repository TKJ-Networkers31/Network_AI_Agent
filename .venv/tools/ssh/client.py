import os
from pathlib import Path

import paramiko
import yaml


BASE_DIR = Path(__file__).resolve().parents[2]

INVENTORY_FILE = (
    BASE_DIR /
    "inventory" /
    "router.yaml"
)


def load_inventory():

    with open(
        INVENTORY_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        return yaml.safe_load(file)


def ssh_execute(
    device_name,
    command
):

    inventory = load_inventory()

    devices = inventory.get(
        "devices",
        {}
    )

    if device_name not in devices:

        return {
            "success": False,
            "error": (
                f"Device '{device_name}' "
                "tidak ditemukan."
            )
        }

    device = devices[device_name]

    password = os.getenv(
        "SSH_PASSWORD"
    )

    if not password:

        return {
            "success": False,
            "error": (
                "SSH_PASSWORD belum diset."
            )
        }

    client = paramiko.SSHClient()

    client.set_missing_host_key_policy(
        paramiko.AutoAddPolicy()
    )

    try:

        client.connect(
            hostname=device["host"],
            port=device.get("port", 22),
            username=device["username"],
            password=password,
            look_for_keys=False,
            allow_agent=False,
            timeout=10,
            banner_timeout=10,
            auth_timeout=10
        )

        stdin, stdout, stderr = (
            client.exec_command(
                command,
                timeout=30
            )
        )

        output = stdout.read().decode(
            errors="replace"
        ).strip()

        error = stderr.read().decode(
            errors="replace"
        ).strip()

        return {
            "success": True,
            "device": device_name,
            "host": device["host"],
            "command": command,
            "output": output,
            "error": error
        }

    except Exception as exc:

        return {
            "success": False,
            "device": device_name,
            "error": str(exc)
        }

    finally:

        client.close()