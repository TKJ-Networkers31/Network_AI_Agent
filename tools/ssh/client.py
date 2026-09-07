import os
import time
import threading
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

# -----------------------------------------------------------------
# Connection pool: satu SSHClient dipertahankan per device selama
# proses agent hidup, alih-alih connect+close di setiap tool call.
# Ini menghilangkan overhead handshake SSH (bisa ratusan ms - detik
# per call) untuk perangkat yang sama dipanggil berkali-kali dalam
# satu sesi atau satu giliran (misal beberapa tool MikroTik
# sekaligus).
#
# Lock per-device mencegah 2 tool call ke device yang sama memakai
# channel yang sama secara bersamaan (paramiko tidak thread-safe
# untuk exec_command paralel pada client yang sama).
# -----------------------------------------------------------------

_pool_lock = threading.Lock()
_connections = {}  # device_name -> {"client": SSHClient|None, "lock": Lock}


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


def _get_pool_entry(device_name):

    with _pool_lock:

        entry = _connections.setdefault(
            device_name,
            {"client": None, "lock": threading.Lock()}
        )

        return entry


def _is_alive(client):

    if client is None:
        return False

    transport = client.get_transport()

    return bool(transport) and transport.is_active()


def _open_connection(device, password):

    client = paramiko.SSHClient()

    client.set_missing_host_key_policy(
        paramiko.AutoAddPolicy()
    )

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

    return client


def close_all_connections():
    """
    Menutup semua koneksi SSH yang sedang di-pool. Panggil ini
    (opsional) saat agent shutdown agar tidak meninggalkan koneksi
    menggantung di perangkat.
    """

    with _pool_lock:

        for entry in _connections.values():

            client = entry.get("client")

            if client:
                try:
                    client.close()
                except Exception:
                    pass

        _connections.clear()


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

    entry = _get_pool_entry(device_name)

    with entry["lock"]:

        last_error = None

        for attempt in range(1, MAX_RETRIES + 2):

            try:

                if not _is_alive(entry["client"]):

                    entry["client"] = _open_connection(
                        device,
                        password
                    )

                    logger.info(
                        f"SSH CONNECT | device={device_name} | "
                        f"koneksi baru dibuat (pool)."
                    )

                client = entry["client"]

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

                # Koneksi kemungkinan rusak, buang supaya dibuat
                # ulang di percobaan berikutnya.
                try:
                    if entry["client"]:
                        entry["client"].close()
                except Exception:
                    pass

                entry["client"] = None

                if attempt <= MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                    continue

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