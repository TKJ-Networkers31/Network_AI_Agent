"""
core/model_registry.py — SQLite model registry untuk Phase 1.2 (Model
Management System).

Taruh file ini di: AIRA_ECOSYSTEM/core/model_registry.py

Ini adalah lapisan CRUD MURNI (tidak tahu apa-apa soal HTTP/provider LLM
apa pun) untuk tabel `model_registry`, disimpan di database/model_registry.db
— TERPISAH TOTAL dari database/long_term_memory.db milik core/memory.py
(Database Memory tidak disentuh sama sekali, sesuai Out of Scope Phase 1.2).

agents/rei/provider_client.py adalah satu-satunya konsumen file ini yang
boleh benar-benar memanggil provider LLM; modul ini hanya menyediakan data.
"""

import sqlite3
import time
import threading
import logging
from pathlib import Path
from contextlib import closing
from typing import Any, Optional

logger = logging.getLogger("aira.model_registry")

BASE_DIR = Path(__file__).resolve().parents[1]  # AIRA_ECOSYSTEM/
DATABASE_DIR = BASE_DIR / "database"
DB_FILE = DATABASE_DIR / "model_registry.db"

DATABASE_DIR.mkdir(exist_ok=True)

_write_lock = threading.Lock()

# Provider yang didukung saat ini. Menambah provider baru (mis. "anthropic",
# "groq") CUKUP tambah nama di sini + adapter call/health-check di
# agents/rei/provider_client.py - TIDAK perlu mengubah orchestrator/planner.
VALID_PROVIDERS = {"openrouter", "ollama"}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with closing(_connect()) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS model_registry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nickname TEXT NOT NULL UNIQUE,
                provider TEXT NOT NULL,
                model_id TEXT NOT NULL,
                endpoint TEXT,
                api_key TEXT,
                is_default INTEGER NOT NULL DEFAULT 0,
                is_fallback INTEGER NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1,
                last_ping REAL,
                last_status TEXT DEFAULT 'unknown',
                last_message TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        conn.commit()

    _seed_defaults()


def _seed_defaults() -> None:
    """
    Isi awal supaya sistem tidak "kosong model" begitu Phase 1.2 aktif,
    memigrasikan 4 provider yang dulu hardcoded di PROVIDERS (versi lama
    agents/rei/provider_client.py) menjadi baris registry. Hanya berjalan
    kalau tabel masih benar-benar kosong.
    """
    with closing(_connect()) as conn:
        row = conn.execute("SELECT COUNT(*) as c FROM model_registry").fetchone()
        if row["c"] > 0:
            return

    now = time.time()

    seed_rows = [
        {
            "nickname": "ollama-qwen3-1.7b",
            "provider": "ollama",
            "model_id": "qwen3:1.7b",
            "endpoint": "http://localhost:11434",
            "api_key": None,
            "is_default": 1,
            "is_fallback": 0,
            "enabled": 1,
        },
        {
            "nickname": "ollama-qwen3-4b",
            "provider": "ollama",
            "model_id": "qwen3:4b",
            "endpoint": "http://localhost:11434",
            "api_key": None,
            "is_default": 0,
            "is_fallback": 0,
            "enabled": 1,
        },
        {
            "nickname": "Nemotron 3.5 Lightning",
            "provider": "openrouter",
            "model_id": "nvidia/nemotron-3.5-lightning:free",
            "endpoint": "https://openrouter.ai/api/v1",
            "api_key": None,
            "is_default": 0,
            "is_fallback": 1,
            "enabled": 1,
        },
        {
            "nickname": "Nemotron 3 Super",
            "provider": "openrouter",
            "model_id": "nvidia/nemotron-3-super-120b-a12b:free",
            "endpoint": "https://openrouter.ai/api/v1",
            "api_key": None,
            "is_default": 0,
            "is_fallback": 1,
            "enabled": 1,
        },
    ]

    with _write_lock:
        with closing(_connect()) as conn:
            for r in seed_rows:
                conn.execute("""
                    INSERT INTO model_registry
                        (nickname, provider, model_id, endpoint, api_key,
                         is_default, is_fallback, enabled, last_status,
                         created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'unknown', ?, ?)
                """, (
                    r["nickname"], r["provider"], r["model_id"], r["endpoint"], r["api_key"],
                    r["is_default"], r["is_fallback"], r["enabled"], now, now,
                ))
            conn.commit()

    logger.info("MODEL REGISTRY | seed default terisi (%d model).", len(seed_rows))


init_db()


def _row_to_dict(row: sqlite3.Row, mask_api_key: bool = True) -> dict[str, Any]:
    d = dict(row)
    d["is_default"] = bool(d["is_default"])
    d["is_fallback"] = bool(d["is_fallback"])
    d["enabled"] = bool(d["enabled"])

    has_key = bool(d.get("api_key"))

    if mask_api_key:
        d.pop("api_key", None)
        d["has_api_key"] = has_key
    else:
        d["has_api_key"] = has_key

    return d


def list_models(mask_api_key: bool = True) -> list[dict]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM model_registry ORDER BY is_default DESC, nickname ASC"
        ).fetchall()

    return [_row_to_dict(r, mask_api_key=mask_api_key) for r in rows]


def get_model(nickname: str, mask_api_key: bool = False) -> Optional[dict]:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT * FROM model_registry WHERE nickname = ?", (nickname,)
        ).fetchone()

    return _row_to_dict(row, mask_api_key=mask_api_key) if row else None


def get_default_model(mask_api_key: bool = False) -> Optional[dict]:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT * FROM model_registry WHERE is_default = 1 AND enabled = 1 LIMIT 1"
        ).fetchone()

    if row:
        return _row_to_dict(row, mask_api_key=mask_api_key)

    # Fallback pengaman: kalau tidak ada default yang enabled (mis. user
    # menonaktifkan model default tanpa memilih default baru), pakai
    # model enabled pertama supaya sistem tidak mati total.
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT * FROM model_registry WHERE enabled = 1 ORDER BY id ASC LIMIT 1"
        ).fetchone()

    return _row_to_dict(row, mask_api_key=mask_api_key) if row else None


def get_fallback_model(
    exclude_nickname: Optional[str] = None, mask_api_key: bool = False
) -> Optional[dict]:
    with closing(_connect()) as conn:
        if exclude_nickname:
            row = conn.execute(
                "SELECT * FROM model_registry WHERE is_fallback = 1 AND enabled = 1 "
                "AND nickname != ? ORDER BY id ASC LIMIT 1",
                (exclude_nickname,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM model_registry WHERE is_fallback = 1 AND enabled = 1 "
                "ORDER BY id ASC LIMIT 1"
            ).fetchone()

    return _row_to_dict(row, mask_api_key=mask_api_key) if row else None


def create_model(
    nickname: str,
    provider: str,
    model_id: str,
    endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    is_default: bool = False,
    is_fallback: bool = False,
    enabled: bool = True,
) -> dict:
    if not nickname or not nickname.strip():
        return {"success": False, "error": "nickname wajib diisi."}

    provider = (provider or "").strip().lower()

    if provider not in VALID_PROVIDERS:
        return {
            "success": False,
            "error": f"Provider '{provider}' tidak dikenal. Provider valid: {sorted(VALID_PROVIDERS)}.",
        }

    if not model_id or not model_id.strip():
        return {"success": False, "error": "model_id wajib diisi."}

    now = time.time()

    try:
        with _write_lock:
            with closing(_connect()) as conn:
                if is_default:
                    conn.execute("UPDATE model_registry SET is_default = 0")

                conn.execute("""
                    INSERT INTO model_registry
                        (nickname, provider, model_id, endpoint, api_key,
                         is_default, is_fallback, enabled, last_status,
                         created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'unknown', ?, ?)
                """, (
                    nickname.strip(), provider, model_id.strip(), endpoint, api_key,
                    int(is_default), int(is_fallback), int(enabled), now, now,
                ))
                conn.commit()

    except sqlite3.IntegrityError:
        return {"success": False, "error": f"Model dengan nickname '{nickname}' sudah ada."}

    logger.info("MODEL CREATE | nickname=%s provider=%s", nickname, provider)

    return {"success": True, "model": get_model(nickname, mask_api_key=True)}


def update_model(nickname: str, **fields: Any) -> dict:
    existing = get_model(nickname, mask_api_key=False)

    if not existing:
        return {"success": False, "error": f"Model '{nickname}' tidak ditemukan."}

    allowed = {"provider", "model_id", "endpoint", "api_key", "is_default", "is_fallback", "enabled"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}

    if "provider" in updates:
        updates["provider"] = str(updates["provider"]).strip().lower()

        if updates["provider"] not in VALID_PROVIDERS:
            return {
                "success": False,
                "error": f"Provider '{updates['provider']}' tidak dikenal. Provider valid: {sorted(VALID_PROVIDERS)}.",
            }

    if not updates:
        return {"success": True, "model": get_model(nickname, mask_api_key=True)}

    set_clauses = []
    params: list[Any] = []

    for key, value in updates.items():
        if key in ("is_default", "is_fallback", "enabled"):
            value = int(bool(value))
        set_clauses.append(f"{key} = ?")
        params.append(value)

    set_clauses.append("updated_at = ?")
    params.append(time.time())
    params.append(nickname)

    with _write_lock:
        with closing(_connect()) as conn:
            if updates.get("is_default") == 1:
                conn.execute("UPDATE model_registry SET is_default = 0")

            conn.execute(
                f"UPDATE model_registry SET {', '.join(set_clauses)} WHERE nickname = ?",
                params,
            )
            conn.commit()

    logger.info("MODEL UPDATE | nickname=%s fields=%s", nickname, list(updates.keys()))

    return {"success": True, "model": get_model(nickname, mask_api_key=True)}


def delete_model(nickname: str) -> dict:
    existing = get_model(nickname, mask_api_key=True)

    if not existing:
        return {"success": False, "error": f"Model '{nickname}' tidak ditemukan."}

    with _write_lock:
        with closing(_connect()) as conn:
            cursor = conn.execute("DELETE FROM model_registry WHERE nickname = ?", (nickname,))
            conn.commit()
            deleted = cursor.rowcount > 0

    if deleted:
        logger.info("MODEL DELETE | nickname=%s", nickname)

    return {"success": deleted, "nickname": nickname}


def set_default(nickname: str) -> dict:
    existing = get_model(nickname, mask_api_key=True)

    if not existing:
        return {"success": False, "error": f"Model '{nickname}' tidak ditemukan."}

    if not existing["enabled"]:
        return {
            "success": False,
            "error": "Model dinonaktifkan (enabled=False). Aktifkan dulu sebelum dijadikan default.",
        }

    with _write_lock:
        with closing(_connect()) as conn:
            conn.execute("UPDATE model_registry SET is_default = 0")
            conn.execute(
                "UPDATE model_registry SET is_default = 1, updated_at = ? WHERE nickname = ?",
                (time.time(), nickname),
            )
            conn.commit()

    logger.info("MODEL SET DEFAULT | nickname=%s", nickname)

    return {"success": True, "nickname": nickname}


def set_fallback(nickname: str, is_fallback: bool = True) -> dict:
    existing = get_model(nickname, mask_api_key=True)

    if not existing:
        return {"success": False, "error": f"Model '{nickname}' tidak ditemukan."}

    with _write_lock:
        with closing(_connect()) as conn:
            conn.execute(
                "UPDATE model_registry SET is_fallback = ?, updated_at = ? WHERE nickname = ?",
                (int(bool(is_fallback)), time.time(), nickname),
            )
            conn.commit()

    logger.info("MODEL SET FALLBACK | nickname=%s is_fallback=%s", nickname, is_fallback)

    return {"success": True, "nickname": nickname, "is_fallback": bool(is_fallback)}


def set_enabled(nickname: str, enabled: bool) -> dict:
    existing = get_model(nickname, mask_api_key=True)

    if not existing:
        return {"success": False, "error": f"Model '{nickname}' tidak ditemukan."}

    with _write_lock:
        with closing(_connect()) as conn:
            conn.execute(
                "UPDATE model_registry SET enabled = ?, updated_at = ? WHERE nickname = ?",
                (int(bool(enabled)), time.time(), nickname),
            )

            # Model yang dinonaktifkan tidak boleh tetap jadi default aktif.
            if not enabled:
                conn.execute(
                    "UPDATE model_registry SET is_default = 0 "
                    "WHERE nickname = ? AND is_default = 1",
                    (nickname,),
                )

            conn.commit()

    logger.info("MODEL SET ENABLED | nickname=%s enabled=%s", nickname, enabled)

    return {"success": True, "nickname": nickname, "enabled": bool(enabled)}


def touch_ping(nickname: str, online: bool, message: str = "") -> None:
    """Dipanggil setelah health check (test_connection) untuk mencatat
    status online/offline + waktu ping terakhir, ditampilkan di UI."""

    with _write_lock:
        with closing(_connect()) as conn:
            conn.execute(
                "UPDATE model_registry SET last_ping = ?, last_status = ?, "
                "last_message = ?, updated_at = ? WHERE nickname = ?",
                (
                    time.time(),
                    "online" if online else "offline",
                    message,
                    time.time(),
                    nickname,
                ),
            )
            conn.commit()