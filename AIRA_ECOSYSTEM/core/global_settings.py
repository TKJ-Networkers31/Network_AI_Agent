"""
core/global_settings.py — Global Settings Engine (Sprint 2.6, Worker 1).

SATU-SATUNYA pemilik database/global_settings.db - key/value store untuk
pengaturan global AIRA (identitas user, bahasa, tema, dll), terpisah dari
database lain (long_term_memory.db, chat_sessions.db, persona.db, dst)
sesuai aturan "satu .db, satu pemilik modul" (docs/database.md).

Desain mengikuti pola yang SUDAH ADA di repo (core/model_store.py,
core/location/store.py, core/persona/engine.py): SQLite murni lewat
sqlite3 stdlib, init_db() idempotent (CREATE TABLE IF NOT EXISTS), seed
default HANYA untuk key yang belum ada (tidak pernah menimpa nilai yang
sudah diset user), singleton lazy lewat get_global_settings_store().

TIDAK membuat database baru selain global_settings.db, TIDAK membuat ORM
baru - pola query manual + sqlite3.Row yang sama dengan modul lain.

Lapisan:

    SETTINGS_SCHEMA         - definisi tiap key: tipe, default, validator
    GlobalSettingsStore     - CRUD SQLite murni (read/read_all/write)
    read() / read_all() / write()  - fungsi modul-level (dipakai
                              api/routers/settings.py dan, nanti,
                              agents/rei/settings_tools.py)

Event: setiap write() sukses mem-publish "settings.changed" ke Event Bus
YANG SUDAH ADA (core/events.py::event_bus) - TIDAK membuat event bus baru
dan TIDAK menambah nama ke EventNames (mengikuti pola core/filesystem/
operations.py yang juga mem-publish string event literal seperti
"file.created" tanpa mendaftarkannya di EventNames). Kegagalan publish
tidak pernah menggagalkan write() itu sendiri.

Kontrak nilai kembalian mengikuti pola dict {"success": bool, ...} yang
dipakai core/model_store.py dan core/persona/engine.py - aman dikonsumsi
langsung oleh endpoint REST maupun (nanti) oleh tool AI, TANPA AI pernah
menyentuh database secara langsung.
"""

import logging
import re
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("aira.global_settings")

BASE_DIR = Path(__file__).resolve().parents[1]  # AIRA_ECOSYSTEM/
DATABASE_DIR = BASE_DIR / "database"
DEFAULT_DB_FILE = DATABASE_DIR / "global_settings.db"

DATABASE_DIR.mkdir(exist_ok=True)

_TIMEZONE_RE = re.compile(r"^[A-Za-z0-9_+\-]+(/[A-Za-z0-9_+\-]+)+$")
_LANGUAGE_RE = re.compile(r"^[a-z]{2}(-[A-Za-z0-9]{2,8})?$")
_THEME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")


def _validate_timezone(value: str) -> Optional[str]:
    """Return error message, or None kalau valid."""
    if not _TIMEZONE_RE.match(value):
        return "timezone harus berformat 'Region/City', mis. 'Asia/Jakarta'."

    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(value)
    except Exception:
        return f"timezone '{value}' tidak dikenal."

    return None


def _validate_language(value: str) -> Optional[str]:
    if not _LANGUAGE_RE.match(value):
        return "language harus kode BCP-47 sederhana, mis. 'id' atau 'en-US'."
    return None


def _validate_theme(value: str) -> Optional[str]:
    if not _THEME_RE.match(value):
        return "theme harus slug huruf-kecil/angka/tanda hubung, mis. 'arctic-blue'."
    return None


def _validate_greeting_style(value: str) -> Optional[str]:
    allowed = SETTINGS_SCHEMA["greeting_style"]["choices"]
    if value not in allowed:
        return f"greeting_style harus salah satu dari: {', '.join(sorted(allowed))}."
    return None


def _validate_short_text(value: str) -> Optional[str]:
    if not value.strip():
        return "nilai tidak boleh kosong."
    if len(value) > 80:
        return "nilai maksimal 80 karakter."
    return None


# ============================================================
# SCHEMA — satu sumber kebenaran untuk tipe, default, dan validasi
# ============================================================
#
# type       : "string" | "boolean"
# default    : nilai bawaan aman (dipakai saat seed & saat key hilang)
# validator  : Optional[Callable[[str], Optional[str]]] - hanya untuk
#              type == "string"; return pesan error atau None kalau valid
SETTINGS_SCHEMA: dict[str, dict[str, Any]] = {
    "display_name": {"type": "string", "default": "Lingga", "validator": _validate_short_text},
    "nickname": {"type": "string", "default": "Lingga", "validator": _validate_short_text},
    "assistant_name": {"type": "string", "default": "AIRA", "validator": _validate_short_text},
    "timezone": {"type": "string", "default": "Asia/Jakarta", "validator": _validate_timezone},
    "language": {"type": "string", "default": "id", "validator": _validate_language},
    "theme": {"type": "string", "default": "arctic-blue", "validator": _validate_theme},
    "voice_enabled": {"type": "boolean", "default": True},
    "greeting_style": {
        "type": "string",
        "default": "default",
        "choices": {"default", "casual", "formal"},
        "validator": _validate_greeting_style,
    },
}

KNOWN_KEYS = frozenset(SETTINGS_SCHEMA.keys())


def default_settings() -> dict[str, Any]:
    return {key: spec["default"] for key, spec in SETTINGS_SCHEMA.items()}


def _validate(key: str, value: Any) -> tuple[Optional[Any], Optional[str]]:
    """Return (nilai bersih, error). Salah satu selalu None."""
    if key not in SETTINGS_SCHEMA:
        allowed = ", ".join(sorted(KNOWN_KEYS))
        return None, f"Setting '{key}' tidak dikenal. Setting yang tersedia: {allowed}."

    spec = SETTINGS_SCHEMA[key]

    if spec["type"] == "boolean":
        if isinstance(value, bool):
            return value, None
        if isinstance(value, str) and value.strip().lower() in ("true", "false"):
            return value.strip().lower() == "true", None
        return None, f"'{key}' harus berupa boolean (true/false)."

    # type == "string"
    if not isinstance(value, str):
        return None, f"'{key}' harus berupa string."

    cleaned = value.strip()
    validator = spec.get("validator")

    if validator:
        error = validator(cleaned)
        if error:
            return None, f"'{key}': {error}"

    return cleaned, None


class GlobalSettingsStore:
    """
    Dependency Injection: db_path bisa disuntik (unit test memakai file
    sementara) - TIDAK PERNAH menyentuh database/global_settings.db asli
    kecuali lewat singleton produksi.
    """

    def __init__(self, db_path: Optional[Path] = None, seed: bool = True):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_FILE
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

        if seed:
            self._seed_missing_defaults()

    # ------------------------------------------------------------ infra

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS global_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    value_type TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            conn.commit()

    def _seed_missing_defaults(self) -> None:
        """Isi HANYA key yang belum ada - tidak pernah menimpa nilai yang
        sudah diset user (sesuai aturan: jangan override konfigurasi ada)."""
        with self._lock, closing(self._connect()) as conn:
            existing = {row["key"] for row in conn.execute("SELECT key FROM global_settings")}
            now = time.time()
            missing = [key for key in SETTINGS_SCHEMA if key not in existing]

            for key in missing:
                spec = SETTINGS_SCHEMA[key]
                conn.execute(
                    "INSERT INTO global_settings (key, value, value_type, updated_at) "
                    "VALUES (?, ?, ?, ?)",
                    (key, self._encode(spec["default"], spec["type"]), spec["type"], now),
                )

            if missing:
                conn.commit()
                logger.info("GLOBAL SETTINGS | seed default untuk key: %s", missing)

    @staticmethod
    def _encode(value: Any, value_type: str) -> str:
        if value_type == "boolean":
            return "true" if value else "false"
        return str(value)

    @staticmethod
    def _decode(raw: str, value_type: str) -> Any:
        if value_type == "boolean":
            return raw == "true"
        return raw

    # ------------------------------------------------------------- read

    def read(self, key: str) -> dict:
        if key not in KNOWN_KEYS:
            allowed = ", ".join(sorted(KNOWN_KEYS))
            return {"success": False, "error": f"Setting '{key}' tidak dikenal. Setting yang tersedia: {allowed}."}

        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT value, value_type, updated_at FROM global_settings WHERE key = ?", (key,)
            ).fetchone()

        if row is None:
            # Belum pernah diseed (mis. schema bertambah setelah DB dibuat) -
            # kembalikan default apa adanya, tanpa menulis ke DB di jalur baca.
            spec = SETTINGS_SCHEMA[key]
            return {"success": True, "key": key, "value": spec["default"], "updated_at": None}

        value = self._decode(row["value"], row["value_type"])
        return {"success": True, "key": key, "value": value, "updated_at": row["updated_at"]}

    def read_all(self) -> dict:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT key, value, value_type, updated_at FROM global_settings").fetchall()

        settings = default_settings()
        updated_at: dict[str, Optional[float]] = {key: None for key in SETTINGS_SCHEMA}

        for row in rows:
            if row["key"] not in SETTINGS_SCHEMA:
                continue  # baris dari schema lama yang sudah dihapus - diabaikan, bukan error
            settings[row["key"]] = self._decode(row["value"], row["value_type"])
            updated_at[row["key"]] = row["updated_at"]

        return {"success": True, "settings": settings, "updated_at": updated_at}

    # ------------------------------------------------------------ write

    def write(self, key: str, value: Any) -> dict:
        cleaned, error = _validate(key, value)

        if error:
            return {"success": False, "error": error}

        spec = SETTINGS_SCHEMA[key]
        now = time.time()

        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO global_settings (key, value, value_type, updated_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "value_type = excluded.value_type, updated_at = excluded.updated_at",
                (key, self._encode(cleaned, spec["type"]), spec["type"], now),
            )
            conn.commit()

        logger.info("GLOBAL SETTINGS WRITE | key=%s", key)
        _publish_settings_changed(key, cleaned)

        return {"success": True, "key": key, "value": cleaned, "updated_at": now}

    def reset_to_defaults(self) -> dict:
        """Kembalikan SEMUA setting ke default bawaan. Dipakai admin/testing -
        tidak diekspos lewat REST endpoint standar di atas."""
        with self._lock, closing(self._connect()) as conn:
            conn.execute("DELETE FROM global_settings")
            conn.commit()

        self._seed_missing_defaults()
        return self.read_all()


def _publish_settings_changed(key: str, value: Any) -> None:
    """Publish ke Event Bus yang SUDAH ADA. Tidak pernah menggagalkan write()."""
    try:
        from core.events import event_bus
        event_bus.publish("settings.changed", source="SETTINGS", agent="SETTINGS", data={"key": key, "value": value})
    except Exception:
        logger.exception("GLOBAL SETTINGS | gagal publish settings.changed (diabaikan).")


# ============================================================
# SINGLETON + fungsi modul-level (kontrak "Settings Tool")
# ============================================================

_store_singleton: Optional[GlobalSettingsStore] = None
_store_lock = threading.Lock()


def get_global_settings_store() -> GlobalSettingsStore:
    global _store_singleton

    if _store_singleton is None:
        with _store_lock:
            if _store_singleton is None:
                _store_singleton = GlobalSettingsStore()

    return _store_singleton


def read(key: str) -> dict:
    """settings.read(key) - dipakai api/routers/settings.py dan
    agents/rei/settings_tools.py. AI TIDAK PERNAH menyentuh SQLite
    langsung - hanya lewat fungsi ini."""
    return get_global_settings_store().read(key)


def read_all() -> dict:
    """settings.read_all()."""
    return get_global_settings_store().read_all()


def write(key: str, value: Any) -> dict:
    """settings.write(key, value) - tervalidasi lewat SETTINGS_SCHEMA."""
    return get_global_settings_store().write(key, value)
