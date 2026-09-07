import os
import time
from pathlib import Path

import paramiko
import yaml
from dotenv import load_dotenv

from agent.logger import logger, log_error


BASE_DIR = Path(__file__).resolve().parents[2]

load_dotenv(BASE_DIR / ".env")

INVENTORY_FILE = (
    BASE_DIR /
    "inventory" /
    "router.yaml"
)

MAX_RETRIES = 2
RETRY_DELAY = 2  # detik


def load_inventory():

    with open(
        INVENTORY_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        return yaml.safe_load(file)


def resolve_device_name(device_name, devices):
    """
    Mencocokkan device_name secara case-insensitive.
    Mengembalikan nama device asli (sesuai key di YAML) atau None.
    """

    if device_name in devices:
        return device_name

    lowered = device_name.strip().lower()

    for key in devices:
        if key.lower() == lowered:
            return key

    return None


def ssh_execute(
    device_name,
    command
):

    inventory = load_inventory()

    devices = inventory.get(
        "devices",
        {}
    )

    resolved_name = resolve_device_name(
        device_name,
        devices
    )

    if resolved_name is None:

        available = ", ".join(devices.keys()) or "(kosong)"

        return {
            "success": False,
            "error": (
                f"Device '{device_name}' tidak ditemukan. "
                f"Device yang terdaftar: {available}. "
                f"Gunakan tool 'list_devices' untuk melihat daftar lengkap."
            )
        }

    device_name = resolved_name
    device = devices[device_name]

    password = os.getenv(
        "SSH_PASSWORD"
    )

    if not password:

        return {
            "success": False,
            "error": (
                "SSH_PASSWORD belum diset. "
                "Pastikan file .env ada di root proyek "
                "dan berisi SSH_PASSWORD=..."
            )
        }

    last_error = None

    for attempt in range(1, MAX_RETRIES + 2):

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

            # RouterOS kadang mengembalikan pesan error di stderr
            # walau returncode tetap 0, jadi kita perlakukan
            # sebagai kegagalan logis.
            success = not bool(error)

            return {
                "success": success,
                "device": device_name,
                "host": device["host"],
                "command": command,
                "output": output,
                "error": error
            }

        except Exception as exc:

            last_error = str(exc)

            logger.warning(
                f"SSH attempt {attempt} gagal untuk "
                f"device={device_name} command='{command}': {last_error}"
            )

            if attempt <= MAX_RETRIES:
                time.sleep(RETRY_DELAY)
                continue

        finally:

            client.close()

    log_error(
        f"ssh_execute({device_name}, {command})",
        last_error
    )

    return {
        "success": False,
        "device": device_name,
        "error": (
            f"Gagal setelah {MAX_RETRIES + 1} percobaan: {last_error}"
        )
    }