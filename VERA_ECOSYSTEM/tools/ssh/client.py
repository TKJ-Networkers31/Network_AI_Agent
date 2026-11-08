import io
import os
import time
import threading
import logging

import paramiko

from core.inventory_store import get_inventory_store
from core.logger import log_event

logger = logging.getLogger("aira.tools.ssh")


def log_error(context, exc):
    logger.error(f"ERROR | context={context} | detail={exc}")


MAX_RETRIES = 2
RETRY_DELAY = 2  # detik

# -----------------------------------------------------------------
# Connection pool: satu SSHClient per device selama proses hidup.
# Lock per-device mencegah dua exec_command bersamaan di client yang sama.
# Entry menyimpan "target" (host, port, username) - kalau device diubah di
# inventory, koneksi lama otomatis dibuang dan dibuat ulang.
# -----------------------------------------------------------------

_pool_lock = threading.Lock()
_connections = {}  # device_name -> {"client", "lock", "target"}


def load_inventory():
    """
    Kompatibilitas: bentuk lama {"devices": {nama: {host, port, username,
    snmp_community, ...}}}, tetapi sekarang dibaca dari database/inventory.db.
    Dipakai tools/snmp/client.py (dan kemungkinan agents/akane).
    """
    return get_inventory_store().export_inventory()


def resolve_device_name(device_name, devices):
    """Cocokkan nama device (case-insensitive). Return nama asli atau None."""
    if device_name in devices:
        return device_name

    lowered = str(device_name or "").strip().lower()

    for key in devices:
        if key.lower() == lowered:
            return key

    return None


def _get_pool_entry(device_name):
    with _pool_lock:
        return _connections.setdefault(
            device_name, {"client": None, "lock": threading.Lock(), "target": None}
        )


def _is_alive(client):
    if client is None:
        return False

    transport = client.get_transport()

    return bool(transport) and transport.is_active()


def _load_pkey(key_text):
    for key_class in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
        try:
            return key_class.from_private_key(io.StringIO(key_text))
        except (paramiko.SSHException, ValueError):
            continue

    raise paramiko.SSHException(
        "Format private key tidak dikenali (didukung: RSA/ECDSA/Ed25519 tanpa passphrase)."
    )


def _open_connection(target):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    pkey = _load_pkey(target["key"]) if target.get("key") else None

    client.connect(
        hostname=target["host"],
        port=target["port"],
        username=target["username"],
        password=target.get("password"),   # "" (tanpa password) tetap dicoba; None = tidak dipakai
        pkey=pkey,
        look_for_keys=False,
        allow_agent=False,
        timeout=10,
        banner_timeout=10,
        auth_timeout=10,
    )

    return client


def close_all_connections():
    with _pool_lock:
        for entry in _connections.values():
            client = entry.get("client")

            if client:
                try:
                    client.close()
                except Exception:
                    pass

        _connections.clear()


def ssh_execute(device_name, command):
    resolved = get_inventory_store().resolve_ssh(device_name)

    if not resolved.get("success"):
        return {
            "success": False,
            "error": (
                f"{resolved.get('error')} Daftarkan device baru lewat menu Devices "
                f"atau tool add_device."
            ),
        }

    device_name = resolved["name"]

    if resolved["password"] is None and not resolved["key"]:
        return {
            "success": False,
            "device": device_name,
            "error": (
                f"Device '{device_name}' belum punya credential SSH. Tambahkan credential "
                f"(ssh_password / ssh_key) dan kaitkan ke device lewat menu Devices, "
                f"atau pakai tool add_credential + link_credential. "
                f"Untuk device tanpa password, buat credential ssh_password dengan secret kosong."
            ),
        }

    target = {
        "host": resolved["host"], "port": resolved["port"], "username": resolved["username"],
        "password": resolved["password"], "key": resolved["key"],
    }
    target_id = (target["host"], target["port"], target["username"])

    entry = _get_pool_entry(device_name)

    with entry["lock"]:

        # Device diubah (host/port/user) -> buang koneksi lama.
        if entry["target"] != target_id and entry["client"] is not None:
            try:
                entry["client"].close()
            except Exception:
                pass
            entry["client"] = None

        entry["target"] = target_id

        last_error = None

        for attempt in range(1, MAX_RETRIES + 2):

            try:
                if not _is_alive(entry["client"]):
                    entry["client"] = _open_connection(target)
                    logger.info(f"SSH CONNECT | device={device_name} | koneksi baru dibuat (pool).")

                client = entry["client"]

                stdin, stdout, stderr = client.exec_command(command, timeout=30)

                output = stdout.read().decode(errors="replace").strip()
                error = stderr.read().decode(errors="replace").strip()

                # RouterOS kadang menaruh pesan error di stderr walau returncode 0.
                success = not bool(error)

                log_event(
                    logger, "INFO" if success else "WARNING",
                    f"SSH exec {'sukses' if success else 'ada stderr'} | {command}",
                    category="ssh",
                    context={"device": device_name, "host": target["host"], "command": command},
                    success=success,
                )

                return {
                    "success": success, "device": device_name, "host": target["host"],
                    "command": command, "output": output, "error": error,
                }

            except paramiko.AuthenticationException as exc:
                # Salah password/key: retry tidak ada gunanya.
                last_error = f"Autentikasi ditolak ({exc}). Cek username/credential device '{device_name}'."
                break

            except Exception as exc:
                last_error = str(exc)

                logger.warning(
                    f"SSH attempt {attempt} gagal untuk device={device_name} command='{command}': {last_error}"
                )

                try:
                    if entry["client"]:
                        entry["client"].close()
                except Exception:
                    pass

                entry["client"] = None

                if attempt <= MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                    continue

        try:
            if entry["client"]:
                entry["client"].close()
        except Exception:
            pass

        entry["client"] = None

        log_error(f"ssh_execute({device_name}, {command})", last_error)

        return {
            "success": False,
            "device": device_name,
            "host": target["host"],
            "error": f"Gagal membuka/menjalankan SSH ke {target['host']}:{target['port']} - {last_error}",
        }