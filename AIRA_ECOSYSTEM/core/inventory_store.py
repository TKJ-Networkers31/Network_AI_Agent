"""
core/inventory_store.py — pemilik database/inventory.db (Inventory Engine).

Menggantikan inventory/router.yaml yang statis. Isi:

    devices              perangkat (nama, host, port, username, tipe, catatan, ...)
    credentials          kredensial (ssh_password, ssh_key, api_key, snmp_community, token, other)
    device_credentials   relasi many-to-many device <-> credential

Aturan keamanan:
  - Secret (password / private key / api key) disimpan TERENKRIPSI (Fernet).
    Kunci dari env AIRA_SECRET_KEY, atau dibuat otomatis di database/.inventory.key.
  - Secret TIDAK PERNAH dikembalikan oleh list/get (hanya has_secret). Satu-satunya
    jalur membaca secret adalah resolve_ssh() / export_inventory(), dipakai tools/ssh.
  - Password KOSONG ("tanpa password") berbeda dari "tidak ada password":
    secret "" disimpan sebagai secret valid, None = belum ada.

Semua method publik mengembalikan dict {"success": bool, ...} dan tidak pernah raise.
Pertama kali dijalankan dengan tabel devices kosong, isi inventory/router.yaml
diimpor otomatis (satu kali).
"""

from __future__ import annotations

import base64
import functools
import logging
import os
import re
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

logger = logging.getLogger("aira.inventory")

BASE_DIR = Path(__file__).resolve().parents[1]  # AIRA_ECOSYSTEM/
load_dotenv(BASE_DIR / ".env")

DATABASE_DIR = BASE_DIR / "database"
DEFAULT_DB_FILE = DATABASE_DIR / "inventory.db"
KEY_FILE = DATABASE_DIR / ".inventory.key"
LEGACY_YAML = BASE_DIR / "inventory" / "router.yaml"

CREDENTIAL_TYPES = {
    "ssh_password": "SSH Password",
    "ssh_key": "SSH Key (private key)",
    "api_key": "API Key",
    "snmp_community": "SNMP Community",
    "token": "Token",
    "other": "Lainnya",
}

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$")
_TYPE_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,39}$")
_HOST_RE = re.compile(r"^[A-Za-z0-9._:\-\[\]]{1,255}$")

_UNSET = object()


class InventoryError(Exception):
    def __init__(self, message: str, not_found: bool = False):
        super().__init__(message)
        self.not_found = not_found


# ============================================================ ENKRIPSI

_fernet_cache: Any = None
_fernet_lock = threading.Lock()


def _get_fernet():
    """Fernet siap pakai, atau None kalau paket cryptography tidak ada."""
    global _fernet_cache

    if _fernet_cache is not None:
        return _fernet_cache or None

    with _fernet_lock:
        if _fernet_cache is not None:
            return _fernet_cache or None

        try:
            from cryptography.fernet import Fernet
        except ImportError:
            logger.warning(
                "INVENTORY | paket 'cryptography' belum terpasang - secret disimpan TANPA enkripsi "
                "(hanya base64). Jalankan: pip install cryptography"
            )
            _fernet_cache = False
            return None

        key = os.getenv("AIRA_SECRET_KEY", "").strip().encode()

        if not key:
            DATABASE_DIR.mkdir(parents=True, exist_ok=True)

            if KEY_FILE.exists():
                key = KEY_FILE.read_bytes().strip()
            else:
                key = Fernet.generate_key()
                KEY_FILE.write_bytes(key)
                try:
                    os.chmod(KEY_FILE, 0o600)
                except OSError:
                    pass
                logger.info("INVENTORY | kunci enkripsi baru dibuat di %s (JANGAN dihapus/di-commit).", KEY_FILE)

        try:
            _fernet_cache = Fernet(key)
        except Exception:
            logger.exception("INVENTORY | AIRA_SECRET_KEY tidak valid (harus kunci Fernet).")
            _fernet_cache = False
            return None

    return _fernet_cache


def encrypt_secret(plain: Optional[str]) -> Optional[str]:
    if plain is None:
        return None

    fernet = _get_fernet()
    data = str(plain).encode("utf-8")

    if fernet is not None:
        return "enc:" + fernet.encrypt(data).decode("ascii")

    return "b64:" + base64.b64encode(data).decode("ascii")


def decrypt_secret(stored: Optional[str]) -> Optional[str]:
    if stored is None:
        return None

    if stored.startswith("b64:"):
        return base64.b64decode(stored[4:]).decode("utf-8")

    if stored.startswith("enc:"):
        fernet = _get_fernet()

        if fernet is None:
            raise InventoryError("Secret terenkripsi tetapi paket 'cryptography' tidak tersedia.")

        try:
            return fernet.decrypt(stored[4:].encode("ascii")).decode("utf-8")
        except Exception:
            raise InventoryError(
                "Secret tidak bisa didekripsi (kunci berubah?). Cek AIRA_SECRET_KEY / database/.inventory.key."
            )

    return stored


# ============================================================ VALIDASI

def _clean_name(value: Any, label: str = "nama") -> str:
    text = str(value or "").strip()

    if not _NAME_RE.match(text):
        raise InventoryError(
            f"{label} '{text}' tidak valid: pakai huruf/angka/'_'/'-'/'.' (maks 64, diawali huruf/angka), tanpa spasi."
        )

    return text


def _clean_host(value: Any) -> str:
    text = str(value or "").strip()

    if not _HOST_RE.match(text):
        raise InventoryError(f"host '{text}' tidak valid (IP atau hostname, tanpa spasi).")

    return text


def _clean_port(value: Any, label: str = "port") -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise InventoryError(f"{label} harus berupa angka 1-65535.")

    if not 1 <= port <= 65535:
        raise InventoryError(f"{label} harus antara 1 dan 65535.")

    return port


def _clean_type(value: Any) -> str:
    text = str(value or "mikrotik").strip().lower()

    if not _TYPE_RE.match(text):
        raise InventoryError("device_type harus huruf kecil/angka/'-'/'_' (mis. mikrotik, linux, olt, switch).")

    return text


def _opt(value: Any, limit: int = 200) -> Optional[str]:
    if value is None:
        return None

    text = str(value).strip()

    return text[:limit] if text else None


def _check_secret(ctype: str, secret: Any) -> Optional[str]:
    """Validasi secret menurut tipe. Return string (boleh "" khusus ssh_password) atau raise."""
    if ctype == "ssh_password":
        if secret is None:
            raise InventoryError('ssh_password butuh secret (isi "" kalau memang tanpa password).')
        return str(secret)

    if secret is None or str(secret).strip() == "":
        raise InventoryError(f"credential tipe '{ctype}' butuh secret yang tidak kosong.")

    text = str(secret)

    if ctype == "ssh_key" and "PRIVATE KEY" not in text:
        raise InventoryError("ssh_key harus berisi isi private key lengkap (-----BEGIN ... PRIVATE KEY-----).")

    return text


def _guarded(fn):
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        except InventoryError as exc:
            return {"success": False, "error": str(exc), "not_found": exc.not_found}
        except sqlite3.IntegrityError as exc:
            return {"success": False, "error": f"Data bentrok (nama sudah dipakai?): {exc}", "not_found": False}
        except Exception as exc:
            logger.exception("INVENTORY | %s gagal tak terduga", fn.__name__)
            return {"success": False, "error": f"{type(exc).__name__}: {exc}", "not_found": False}

    return wrapper


def _publish(kind: str, name: str) -> None:
    try:
        from core.events import event_bus
        event_bus.publish("inventory.changed", source="INVENTORY", agent="INVENTORY",
                          data={"kind": kind, "name": name})
    except Exception:
        logger.debug("INVENTORY | gagal publish inventory.changed (diabaikan).", exc_info=True)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS credentials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    type TEXT NOT NULL,
    username TEXT,
    secret_enc TEXT,
    note TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    host TEXT NOT NULL,
    port INTEGER NOT NULL DEFAULT 22,
    username TEXT,
    device_type TEXT NOT NULL DEFAULT 'mikrotik',
    snmp_community TEXT,
    snmp_port INTEGER NOT NULL DEFAULT 161,
    note TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS device_credentials (
    device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    credential_id INTEGER NOT NULL REFERENCES credentials(id) ON DELETE CASCADE,
    PRIMARY KEY (device_id, credential_id)
);
"""


class InventoryStore:

    def __init__(self, db_path: Optional[Path] = None, seed: bool = True):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_FILE
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

        if seed:
            self._seed_from_yaml()

    # ------------------------------------------------------------ infra

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.executescript(SCHEMA_SQL)
            conn.commit()

    def _seed_from_yaml(self) -> None:
        """Impor SEKALI dari inventory/router.yaml kalau tabel devices masih kosong."""
        with closing(self._connect()) as conn:
            if conn.execute("SELECT COUNT(*) AS c FROM devices").fetchone()["c"]:
                return

        if not LEGACY_YAML.exists():
            return

        try:
            import yaml
            with open(LEGACY_YAML, "r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
        except Exception:
            logger.exception("INVENTORY | gagal membaca %s (impor dilewati).", LEGACY_YAML)
            return

        env_password = os.getenv("SSH_PASSWORD")
        imported = 0

        for name, entry in (data.get("devices") or {}).items():
            if not isinstance(entry, dict) or not entry.get("host"):
                continue

            credential = None

            if env_password is not None:
                credential = {
                    "name": f"{name}-ssh", "type": "ssh_password",
                    "username": entry.get("username"), "secret": env_password,
                    "note": "Diimpor dari SSH_PASSWORD (.env)",
                }

            result = self.create_device(
                name=name, host=entry["host"], port=entry.get("port", 22),
                username=entry.get("username"), snmp_community=entry.get("snmp_community"),
                snmp_port=entry.get("snmp_port", 161),
                note="Diimpor dari inventory/router.yaml", new_credential=credential,
            )

            if result.get("success"):
                imported += 1
            else:
                logger.warning("INVENTORY | impor '%s' gagal: %s", name, result.get("error"))

        logger.info("INVENTORY | %d device diimpor dari router.yaml.", imported)

    # ------------------------------------------------------------ helper baca

    @staticmethod
    def _device_row(conn, name: str):
        row = conn.execute("SELECT * FROM devices WHERE name = ?", (str(name or "").strip(),)).fetchone()

        if row is None:
            known = ", ".join(r["name"] for r in conn.execute("SELECT name FROM devices ORDER BY name")) or "(kosong)"
            raise InventoryError(f"Device '{name}' tidak ditemukan. Device terdaftar: {known}.", not_found=True)

        return row

    @staticmethod
    def _credential_row(conn, name: str):
        row = conn.execute("SELECT * FROM credentials WHERE name = ?", (str(name or "").strip(),)).fetchone()

        if row is None:
            known = ", ".join(r["name"] for r in conn.execute("SELECT name FROM credentials ORDER BY name")) or "(kosong)"
            raise InventoryError(f"Credential '{name}' tidak ditemukan. Credential terdaftar: {known}.", not_found=True)

        return row

    @staticmethod
    def _linked(conn, device_id: int) -> list:
        return conn.execute(
            "SELECT c.* FROM credentials c JOIN device_credentials dc ON dc.credential_id = c.id "
            "WHERE dc.device_id = ? ORDER BY c.name",
            (device_id,),
        ).fetchall()

    def _device_dict(self, conn, row, include_secrets: bool = False) -> dict:
        data = {
            "id": row["id"], "name": row["name"], "host": row["host"], "port": row["port"],
            "username": row["username"], "device_type": row["device_type"],
            "snmp_port": row["snmp_port"], "note": row["note"], "enabled": bool(row["enabled"]),
            "created_at": row["created_at"], "updated_at": row["updated_at"],
            "credentials": [
                {"name": c["name"], "type": c["type"], "username": c["username"],
                 "has_secret": c["secret_enc"] is not None}
                for c in self._linked(conn, row["id"])
            ],
        }

        if include_secrets:
            data["snmp_community"] = row["snmp_community"]
        else:
            data["has_snmp_community"] = bool(row["snmp_community"])

        return data

    @staticmethod
    def _credential_dict(conn, row) -> dict:
        used_by = [
            r["name"] for r in conn.execute(
                "SELECT d.name FROM devices d JOIN device_credentials dc ON dc.device_id = d.id "
                "WHERE dc.credential_id = ? ORDER BY d.name", (row["id"],),
            )
        ]
        return {
            "id": row["id"], "name": row["name"], "type": row["type"], "username": row["username"],
            "has_secret": row["secret_enc"] is not None, "note": row["note"],
            "created_at": row["created_at"], "updated_at": row["updated_at"], "used_by": used_by,
        }

    @staticmethod
    def _insert_credential(conn, *, name, type, username=None, secret=None, note="") -> int:
        cname = _clean_name(name, "nama credential")
        ctype = str(type or "").strip().lower()

        if ctype not in CREDENTIAL_TYPES:
            raise InventoryError(f"type '{ctype}' tidak dikenal. Pilihan: {', '.join(CREDENTIAL_TYPES)}.")

        if conn.execute("SELECT 1 FROM credentials WHERE name = ?", (cname,)).fetchone():
            raise InventoryError(f"Credential '{cname}' sudah ada.")

        stored = encrypt_secret(_check_secret(ctype, secret))
        now = time.time()

        cursor = conn.execute(
            "INSERT INTO credentials (name, type, username, secret_enc, note, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (cname, ctype, _opt(username, 80), stored, str(note or "")[:500], now, now),
        )
        return cursor.lastrowid

    def _link(self, conn, device_id: int, credential_name: str) -> None:
        cred = self._credential_row(conn, credential_name)
        conn.execute(
            "INSERT OR IGNORE INTO device_credentials (device_id, credential_id) VALUES (?, ?)",
            (device_id, cred["id"]),
        )

    # ============================================================ DEVICES

    @_guarded
    def list_devices(self, include_secrets: bool = False, enabled_only: bool = False) -> dict:
        with closing(self._connect()) as conn:
            where = "WHERE enabled = 1" if enabled_only else ""
            rows = conn.execute(f"SELECT * FROM devices {where} ORDER BY name").fetchall()
            devices = [self._device_dict(conn, r, include_secrets) for r in rows]

        return {"success": True, "count": len(devices), "devices": devices}

    @_guarded
    def get_device(self, name: str) -> dict:
        with closing(self._connect()) as conn:
            return {"success": True, "device": self._device_dict(conn, self._device_row(conn, name))}

    @_guarded
    def create_device(
        self, *, name, host, port=22, username=None, device_type="mikrotik",
        snmp_community=None, snmp_port=161, note="", enabled=True,
        credential_names=None, new_credential: Optional[dict] = None,
    ) -> dict:
        clean_name = _clean_name(name, "nama device")
        values = (
            clean_name, _clean_host(host), _clean_port(port), _opt(username, 80), _clean_type(device_type),
            _opt(snmp_community, 120), _clean_port(snmp_port, "snmp_port"), str(note or "")[:500],
            1 if enabled else 0,
        )
        now = time.time()

        with self._lock, closing(self._connect()) as conn:
            if conn.execute("SELECT 1 FROM devices WHERE name = ?", (clean_name,)).fetchone():
                raise InventoryError(f"Device '{clean_name}' sudah ada. Pakai update_device untuk mengubahnya.")

            cursor = conn.execute(
                "INSERT INTO devices (name, host, port, username, device_type, snmp_community, snmp_port, "
                "note, enabled, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (*values, now, now),
            )
            device_id = cursor.lastrowid

            if new_credential:
                credential_id = self._insert_credential(conn, **new_credential)
                conn.execute(
                    "INSERT OR IGNORE INTO device_credentials (device_id, credential_id) VALUES (?, ?)",
                    (device_id, credential_id),
                )

            for cname in credential_names or []:
                self._link(conn, device_id, cname)

            conn.commit()
            device = self._device_dict(conn, self._device_row(conn, clean_name))

        logger.info("INVENTORY | device dibuat: %s (%s)", clean_name, device["host"])
        _publish("device.created", clean_name)

        return {"success": True, "device": device}

    @_guarded
    def update_device(self, name: str, **fields) -> dict:
        allowed = {
            "new_name", "host", "port", "username", "device_type", "snmp_community",
            "snmp_port", "note", "enabled", "credential_names",
        }
        unknown = set(fields) - allowed

        if unknown:
            raise InventoryError(f"Field tidak dikenal: {', '.join(sorted(unknown))}.")

        with self._lock, closing(self._connect()) as conn:
            row = self._device_row(conn, name)
            updates: dict[str, Any] = {}

            if "new_name" in fields and fields["new_name"] not in (None, ""):
                new_name = _clean_name(fields["new_name"], "nama device")
                clash = conn.execute("SELECT id FROM devices WHERE name = ?", (new_name,)).fetchone()
                if clash and clash["id"] != row["id"]:
                    raise InventoryError(f"Device '{new_name}' sudah ada.")
                updates["name"] = new_name
            if "host" in fields:
                updates["host"] = _clean_host(fields["host"])
            if "port" in fields:
                updates["port"] = _clean_port(fields["port"])
            if "username" in fields:
                updates["username"] = _opt(fields["username"], 80)
            if "device_type" in fields:
                updates["device_type"] = _clean_type(fields["device_type"])
            if "snmp_community" in fields:
                updates["snmp_community"] = _opt(fields["snmp_community"], 120)
            if "snmp_port" in fields:
                updates["snmp_port"] = _clean_port(fields["snmp_port"], "snmp_port")
            if "note" in fields:
                updates["note"] = str(fields["note"] or "")[:500]
            if "enabled" in fields:
                updates["enabled"] = 1 if fields["enabled"] else 0

            if updates:
                updates["updated_at"] = time.time()
                set_sql = ", ".join(f"{key} = ?" for key in updates)
                conn.execute(f"UPDATE devices SET {set_sql} WHERE id = ?", [*updates.values(), row["id"]])

            if fields.get("credential_names") is not None:
                conn.execute("DELETE FROM device_credentials WHERE device_id = ?", (row["id"],))
                for cname in fields["credential_names"]:
                    self._link(conn, row["id"], cname)
                conn.execute("UPDATE devices SET updated_at = ? WHERE id = ?", (time.time(), row["id"]))

            conn.commit()
            device = self._device_dict(conn, conn.execute("SELECT * FROM devices WHERE id = ?", (row["id"],)).fetchone())

        logger.info("INVENTORY | device diubah: %s", device["name"])
        _publish("device.updated", device["name"])

        return {"success": True, "device": device}

    @_guarded
    def delete_device(self, name: str) -> dict:
        with self._lock, closing(self._connect()) as conn:
            row = self._device_row(conn, name)
            conn.execute("DELETE FROM devices WHERE id = ?", (row["id"],))
            conn.commit()

        logger.info("INVENTORY | device dihapus: %s", row["name"])
        _publish("device.deleted", row["name"])

        return {"success": True, "name": row["name"]}

    @_guarded
    def link_credential(self, device_name: str, credential_name: str) -> dict:
        with self._lock, closing(self._connect()) as conn:
            row = self._device_row(conn, device_name)
            self._link(conn, row["id"], credential_name)
            conn.execute("UPDATE devices SET updated_at = ? WHERE id = ?", (time.time(), row["id"]))
            conn.commit()
            device = self._device_dict(conn, self._device_row(conn, device_name))

        _publish("device.updated", device["name"])
        return {"success": True, "device": device}

    @_guarded
    def unlink_credential(self, device_name: str, credential_name: str) -> dict:
        with self._lock, closing(self._connect()) as conn:
            row = self._device_row(conn, device_name)
            cred = self._credential_row(conn, credential_name)
            conn.execute(
                "DELETE FROM device_credentials WHERE device_id = ? AND credential_id = ?",
                (row["id"], cred["id"]),
            )
            conn.commit()
            device = self._device_dict(conn, self._device_row(conn, device_name))

        _publish("device.updated", device["name"])
        return {"success": True, "device": device}

    # ============================================================ CREDENTIALS

    @_guarded
    def list_credentials(self) -> dict:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM credentials ORDER BY name").fetchall()
            items = [self._credential_dict(conn, r) for r in rows]

        return {"success": True, "count": len(items), "credentials": items}

    @_guarded
    def create_credential(self, *, name, type, username=None, secret=None, note="") -> dict:
        with self._lock, closing(self._connect()) as conn:
            credential_id = self._insert_credential(
                conn, name=name, type=type, username=username, secret=secret, note=note,
            )
            conn.commit()
            row = conn.execute("SELECT * FROM credentials WHERE id = ?", (credential_id,)).fetchone()
            data = self._credential_dict(conn, row)

        logger.info("INVENTORY | credential dibuat: %s (%s)", data["name"], data["type"])
        _publish("credential.created", data["name"])

        return {"success": True, "credential": data}

    @_guarded
    def update_credential(self, name: str, **fields) -> dict:
        allowed = {"new_name", "username", "secret", "note"}
        unknown = set(fields) - allowed

        if unknown:
            raise InventoryError(f"Field tidak dikenal: {', '.join(sorted(unknown))}.")

        with self._lock, closing(self._connect()) as conn:
            row = self._credential_row(conn, name)
            updates: dict[str, Any] = {}

            if fields.get("new_name") not in (None, ""):
                new_name = _clean_name(fields["new_name"], "nama credential")
                clash = conn.execute("SELECT id FROM credentials WHERE name = ?", (new_name,)).fetchone()
                if clash and clash["id"] != row["id"]:
                    raise InventoryError(f"Credential '{new_name}' sudah ada.")
                updates["name"] = new_name
            if "username" in fields:
                updates["username"] = _opt(fields["username"], 80)
            if "note" in fields:
                updates["note"] = str(fields["note"] or "")[:500]
            if "secret" in fields and fields["secret"] is not None:
                updates["secret_enc"] = encrypt_secret(_check_secret(row["type"], fields["secret"]))

            if updates:
                updates["updated_at"] = time.time()
                set_sql = ", ".join(f"{key} = ?" for key in updates)
                conn.execute(f"UPDATE credentials SET {set_sql} WHERE id = ?", [*updates.values(), row["id"]])
                conn.commit()

            data = self._credential_dict(
                conn, conn.execute("SELECT * FROM credentials WHERE id = ?", (row["id"],)).fetchone(),
            )

        _publish("credential.updated", data["name"])
        return {"success": True, "credential": data}

    @_guarded
    def delete_credential(self, name: str) -> dict:
        with self._lock, closing(self._connect()) as conn:
            row = self._credential_row(conn, name)
            conn.execute("DELETE FROM credentials WHERE id = ?", (row["id"],))
            conn.commit()

        _publish("credential.deleted", row["name"])
        return {"success": True, "name": row["name"]}

    # ============================================================ RESOLUSI (satu-satunya jalur baca secret)

    @staticmethod
    def _ssh_material(credentials: list) -> dict:
        password = key = username = None
        names: list[str] = []
        has_ssh_credential = False

        for cred in credentials:
            if cred["type"] == "ssh_password" and password is None:
                has_ssh_credential = True
                password = decrypt_secret(cred["secret_enc"])
                username = username or cred["username"]
                names.append(cred["name"])
            elif cred["type"] == "ssh_key" and key is None:
                has_ssh_credential = True
                key = decrypt_secret(cred["secret_enc"])
                username = username or cred["username"]
                names.append(cred["name"])

        return {"password": password, "key": key, "username": username,
                "credential_names": names, "has_ssh_credential": has_ssh_credential}

    @staticmethod
    def _snmp_community(row, credentials: list) -> Optional[str]:
        if row["snmp_community"]:
            return row["snmp_community"]

        for cred in credentials:
            if cred["type"] == "snmp_community":
                return decrypt_secret(cred["secret_enc"])

        return None

    @_guarded
    def resolve_ssh(self, device_name: str) -> dict:
        """Data lengkap untuk membuka SSH (TERMASUK secret). Hanya dipakai tools/ssh."""
        with closing(self._connect()) as conn:
            row = self._device_row(conn, device_name)

            if not row["enabled"]:
                raise InventoryError(f"Device '{row['name']}' dinonaktifkan di inventory.")

            material = self._ssh_material(self._linked(conn, row["id"]))

        password = material["password"]

        # Kompatibilitas lama: device tanpa credential SSH sama sekali -> SSH_PASSWORD dari .env.
        if not material["has_ssh_credential"] and os.getenv("SSH_PASSWORD") is not None:
            password = os.getenv("SSH_PASSWORD")

        return {
            "success": True, "name": row["name"], "host": row["host"], "port": row["port"],
            "username": material["username"] or row["username"] or "admin",
            "password": password, "key": material["key"],
            "credential_names": material["credential_names"],
            "has_ssh_credential": material["has_ssh_credential"],
        }

    def export_inventory(self) -> dict:
        """Bentuk lama {"devices": {nama: {...}}} untuk kode yang masih memakai load_inventory()."""
        out: dict[str, dict] = {}

        try:
            with closing(self._connect()) as conn:
                for row in conn.execute("SELECT * FROM devices ORDER BY name").fetchall():
                    credentials = self._linked(conn, row["id"])

                    try:
                        material = self._ssh_material(credentials)
                        community = self._snmp_community(row, credentials)
                    except InventoryError:
                        material = {"password": None, "key": None, "username": None}
                        community = row["snmp_community"]

                    out[row["name"]] = {
                        "host": row["host"], "port": row["port"],
                        "username": material["username"] or row["username"],
                        "snmp_community": community, "snmp_port": row["snmp_port"],
                        "device_type": row["device_type"], "enabled": bool(row["enabled"]),
                        "password": material["password"], "ssh_key": material["key"],
                    }
        except Exception:
            logger.exception("INVENTORY | export_inventory gagal.")

        return {"devices": out}


_store_singleton: Optional[InventoryStore] = None
_store_lock = threading.Lock()


def get_inventory_store() -> InventoryStore:
    global _store_singleton

    if _store_singleton is None:
        with _store_lock:
            if _store_singleton is None:
                _store_singleton = InventoryStore()

    return _store_singleton