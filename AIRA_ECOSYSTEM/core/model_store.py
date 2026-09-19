"""
core/model_store.py — pemilik database/model_router.db (Sprint 1).

Tabel (sesuai spec):
    models                (id, provider, model_id, display_name, label,
                           context_window, enabled, created_at)
    model_router_settings (task_label PK, default_model_id)
    model_policy          (id, fallback_model_id, retry_provider)   -> satu baris, id=1

"Migration" = init_db() yang idempotent (CREATE TABLE IF NOT EXISTS + seed
hanya kalau tabel models kosong). Aman dijalankan berkali-kali.

Seed pertama kali: kalau database/model_registry.db (Phase 1.2) ada, model di
sana diimpor (label=general, context_window=0); kalau tidak, 4 model bawaan
yang sama dengan seed lama. Semua label diarahkan ke model default lama.
API key TIDAK disimpan di sini - dibaca dari .env oleh provider_client.
"""

import logging
import re
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.model_types import DEFAULT_LABEL, VALID_LABELS, VALID_PROVIDERS

logger = logging.getLogger("aira.model_store")

BASE_DIR = Path(__file__).resolve().parents[1]  # AIRA_ECOSYSTEM/
DATABASE_DIR = BASE_DIR / "database"
DEFAULT_DB_FILE = DATABASE_DIR / "model_router.db"
LEGACY_DB_FILE = DATABASE_DIR / "model_registry.db"

RESERVED_IDS = {"routing", "policy", "route", "route_preview"}
_UPDATABLE = {"provider", "model_id", "display_name", "label", "context_window", "enabled"}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS models (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT 'general',
    context_window INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_models_label ON models(label);

CREATE TABLE IF NOT EXISTS model_router_settings (
    task_label TEXT PRIMARY KEY,
    default_model_id TEXT
);

CREATE TABLE IF NOT EXISTS model_policy (
    id INTEGER PRIMARY KEY,
    fallback_model_id TEXT,
    retry_provider INTEGER NOT NULL DEFAULT 0
);
"""

_BUILTIN_SEED = [
    {"display_name": "Qwen3 1.7B (Ollama)", "provider": "ollama", "model_id": "qwen3:1.7b"},
    {"display_name": "Qwen3 4B (Ollama)", "provider": "ollama", "model_id": "qwen3:4b"},
    {"display_name": "Nemotron 3.5 Lightning", "provider": "openrouter",
     "model_id": "nvidia/nemotron-3.5-lightning:free"},
    {"display_name": "Nemotron 3 Super", "provider": "openrouter",
     "model_id": "nvidia/nemotron-3-super-120b-a12b:free"},
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "").strip().lower()).strip("_") or "model"


def _unique_id(conn: sqlite3.Connection, base: str) -> str:
    base = f"{base}_model" if base in RESERVED_IDS else base
    candidate, n = base, 2
    while conn.execute("SELECT 1 FROM models WHERE id = ?", (candidate,)).fetchone():
        candidate = f"{base}_{n}"
        n += 1
    return candidate


def _validate_fields(fields: dict, partial: bool) -> tuple[Optional[dict], Optional[str]]:
    """Return (clean, error). partial=True -> hanya field yang ada divalidasi."""
    clean: dict = {}

    if "provider" in fields or not partial:
        provider = str(fields.get("provider") or "").strip().lower()
        if provider not in VALID_PROVIDERS:
            return None, f"Provider '{provider}' tidak valid. Pilihan: {', '.join(VALID_PROVIDERS)}."
        clean["provider"] = provider

    for key, human in (("model_id", "Model ID"), ("display_name", "Display name")):
        if key in fields or not partial:
            value = str(fields.get(key) or "").strip()
            if not value:
                return None, f"{human} wajib diisi."
            clean[key] = value

    if "label" in fields or not partial:
        label = str(fields.get("label") or DEFAULT_LABEL).strip().lower()
        if label not in VALID_LABELS:
            return None, f"Label '{label}' tidak valid. Pilihan: {', '.join(VALID_LABELS)}."
        clean["label"] = label

    if "context_window" in fields or not partial:
        try:
            window = int(fields.get("context_window") or 0)
        except (TypeError, ValueError):
            return None, "Context window harus berupa angka."
        if window < 0:
            return None, "Context window tidak boleh negatif."
        clean["context_window"] = window

    if "enabled" in fields or not partial:
        clean["enabled"] = 1 if fields.get("enabled", True) else 0

    return clean, None


class ModelStore:

    def __init__(self, db_path: Optional[Path] = None, seed: bool = True):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_FILE
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._seed = seed
        self._lock = threading.RLock()
        self.init_db()

    # ------------------------------------------------------------ infra

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _to_dict(row: sqlite3.Row) -> dict:
        data = dict(row)
        data["enabled"] = bool(data["enabled"])
        return data

    def init_db(self) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.executescript(SCHEMA_SQL)
            conn.commit()

        if self._seed:
            self._seed_if_empty()

        with self._lock, closing(self._connect()) as conn:
            for label in VALID_LABELS:
                conn.execute(
                    "INSERT OR IGNORE INTO model_router_settings (task_label, default_model_id) "
                    "VALUES (?, NULL)", (label,),
                )
            conn.execute(
                "INSERT OR IGNORE INTO model_policy (id, fallback_model_id, retry_provider) "
                "VALUES (1, NULL, 1)"
            )
            conn.commit()

    # ------------------------------------------------------------- seed

    def _read_legacy(self) -> list[dict]:
        if not LEGACY_DB_FILE.exists():
            return []
        try:
            from core.model_registry import list_models as legacy_list_models
            rows = legacy_list_models(mask_api_key=True)
        except Exception:
            logger.exception("Gagal membaca registry lama (diabaikan, pakai seed bawaan).")
            return []

        return [{
            "provider": r["provider"], "model_id": r["model_id"],
            "display_name": r["nickname"], "label": DEFAULT_LABEL,
            "context_window": 0, "enabled": r["enabled"],
            "is_default": r["is_default"], "is_fallback": r["is_fallback"],
        } for r in rows]

    def _seed_if_empty(self) -> None:
        with closing(self._connect()) as conn:
            if conn.execute("SELECT COUNT(*) AS c FROM models").fetchone()["c"]:
                return

        specs = self._read_legacy()
        if specs:
            default_idx = next((i for i, s in enumerate(specs) if s["is_default"]), 0)
            fallback_idx = next(
                (i for i, s in enumerate(specs) if s["is_fallback"] and i != default_idx), default_idx
            )
            source = "registry lama"
        else:
            specs, default_idx, fallback_idx, source = list(_BUILTIN_SEED), 0, 2, "seed bawaan"

        with self._lock, closing(self._connect()) as conn:
            ids = []
            for spec in specs:
                new_id = _unique_id(conn, _slugify(spec["display_name"]))
                conn.execute(
                    "INSERT INTO models (id, provider, model_id, display_name, label, "
                    "context_window, enabled, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (new_id, spec["provider"], spec["model_id"], spec["display_name"],
                     spec.get("label", DEFAULT_LABEL), int(spec.get("context_window", 0)),
                     1 if spec.get("enabled", True) else 0, _now_iso()),
                )
                ids.append(new_id)

            for label in VALID_LABELS:
                conn.execute(
                    "INSERT OR REPLACE INTO model_router_settings (task_label, default_model_id) "
                    "VALUES (?, ?)", (label, ids[default_idx]),
                )
            conn.execute(
                "INSERT OR REPLACE INTO model_policy (id, fallback_model_id, retry_provider) "
                "VALUES (1, ?, 1)", (ids[fallback_idx],),
            )
            conn.commit()

        logger.info("MODEL STORE | seed dari %s (%d model).", source, len(specs))

    # ----------------------------------------------------------- models

    def list_models(self, label: Optional[str] = None, search: Optional[str] = None,
                    enabled_only: bool = False) -> list[dict]:
        conditions, params = [], []

        if label and label != "all":
            conditions.append("label = ?")
            params.append(label)
        if enabled_only:
            conditions.append("enabled = 1")
        if search:
            like = f"%{search.strip().lower()}%"
            conditions.append("(LOWER(display_name) LIKE ? OR LOWER(model_id) LIKE ?)")
            params += [like, like]

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        with closing(self._connect()) as conn:
            rows = conn.execute(f"SELECT * FROM models {where} ORDER BY rowid ASC", params).fetchall()

        return [self._to_dict(r) for r in rows]

    def get_model(self, record_id: Optional[str]) -> Optional[dict]:
        if not record_id:
            return None
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM models WHERE id = ?", (record_id,)).fetchone()
        return self._to_dict(row) if row else None

    def create_model(self, provider: str, model_id: str, display_name: str,
                     label: str = DEFAULT_LABEL, context_window: int = 0,
                     enabled: bool = True, custom_id: Optional[str] = None) -> dict:
        clean, error = _validate_fields({
            "provider": provider, "model_id": model_id, "display_name": display_name,
            "label": label, "context_window": context_window, "enabled": enabled,
        }, partial=False)
        if error:
            return {"success": False, "error": error}

        with self._lock, closing(self._connect()) as conn:
            if custom_id:
                new_id = _slugify(custom_id)
                if new_id in RESERVED_IDS or conn.execute(
                    "SELECT 1 FROM models WHERE id = ?", (new_id,)
                ).fetchone():
                    return {"success": False, "error": f"ID '{new_id}' sudah dipakai."}
            else:
                new_id = _unique_id(conn, _slugify(clean["display_name"]))

            conn.execute(
                "INSERT INTO models (id, provider, model_id, display_name, label, "
                "context_window, enabled, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (new_id, clean["provider"], clean["model_id"], clean["display_name"],
                 clean["label"], clean["context_window"], clean["enabled"], _now_iso()),
            )
            conn.commit()

        logger.info("MODEL CREATE | id=%s provider=%s label=%s", new_id, clean["provider"], clean["label"])
        return {"success": True, "model": self.get_model(new_id)}

    def update_model(self, record_id: str, **fields) -> dict:
        if not self.get_model(record_id):
            return {"success": False, "not_found": True, "error": f"Model '{record_id}' tidak ditemukan."}

        fields = {k: v for k, v in fields.items() if k in _UPDATABLE and v is not None}
        clean, error = _validate_fields(fields, partial=True)
        if error:
            return {"success": False, "error": error}
        if not clean:
            return {"success": True, "model": self.get_model(record_id)}

        set_sql = ", ".join(f"{key} = ?" for key in clean)  # key hanya dari _validate_fields

        with self._lock, closing(self._connect()) as conn:
            conn.execute(f"UPDATE models SET {set_sql} WHERE id = ?", [*clean.values(), record_id])
            conn.commit()

        logger.info("MODEL UPDATE | id=%s fields=%s", record_id, list(clean))
        return {"success": True, "model": self.get_model(record_id)}

    def usage_of(self, record_id: str) -> dict:
        with closing(self._connect()) as conn:
            labels = [r["task_label"] for r in conn.execute(
                "SELECT task_label FROM model_router_settings WHERE default_model_id = ?", (record_id,)
            ).fetchall()]
            policy = conn.execute("SELECT fallback_model_id FROM model_policy WHERE id = 1").fetchone()

        return {
            "default_for": labels,
            "is_fallback": bool(policy and policy["fallback_model_id"] == record_id),
        }

    def delete_model(self, record_id: str) -> dict:
        if not self.get_model(record_id):
            return {"success": False, "not_found": True, "error": f"Model '{record_id}' tidak ditemukan."}

        usage = self.usage_of(record_id)
        if usage["default_for"] or usage["is_fallback"]:
            parts = []
            if usage["default_for"]:
                parts.append("default untuk " + ", ".join(usage["default_for"]))
            if usage["is_fallback"]:
                parts.append("model fallback")
            return {
                "success": False, "in_use": True,
                "error": "Model masih dipakai sebagai " + " dan ".join(parts)
                         + ". Ganti dulu di Default Routing.",
            }

        with self._lock, closing(self._connect()) as conn:
            conn.execute("DELETE FROM models WHERE id = ?", (record_id,))
            conn.commit()

        logger.info("MODEL DELETE | id=%s", record_id)
        return {"success": True, "id": record_id}

    # ---------------------------------------------------------- routing

    def get_routing(self) -> dict[str, Optional[str]]:
        routing: dict[str, Optional[str]] = {label: None for label in VALID_LABELS}
        with closing(self._connect()) as conn:
            for row in conn.execute("SELECT task_label, default_model_id FROM model_router_settings"):
                if row["task_label"] in routing:
                    routing[row["task_label"]] = row["default_model_id"]
        return routing

    def set_default_model(self, task_label: str, model_id: str) -> dict:
        label = (task_label or "").strip().lower()
        if label not in VALID_LABELS:
            return {"success": False, "error": f"Label '{label}' tidak valid."}

        model = self.get_model(model_id)
        if not model:
            return {"success": False, "error": f"Model '{model_id}' tidak ditemukan."}
        if not model["enabled"]:
            return {"success": False, "error": "Model dinonaktifkan. Aktifkan dulu sebelum dijadikan default."}

        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO model_router_settings (task_label, default_model_id) VALUES (?, ?) "
                "ON CONFLICT(task_label) DO UPDATE SET default_model_id = excluded.default_model_id",
                (label, model_id),
            )
            conn.commit()

        logger.info("ROUTING SET | label=%s -> %s", label, model_id)
        return {"success": True, "task_label": label, "default_model_id": model_id}

    # ----------------------------------------------------------- policy

    def get_policy(self) -> dict:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT fallback_model_id, retry_provider FROM model_policy WHERE id = 1"
            ).fetchone()
        return dict(row) if row else {"fallback_model_id": None, "retry_provider": 0}

    def set_policy(self, **fields) -> dict:
        updates: dict = {}

        if "fallback_model_id" in fields:
            fallback_id = fields["fallback_model_id"] or None
            if fallback_id:
                model = self.get_model(fallback_id)
                if not model:
                    return {"success": False, "error": f"Model '{fallback_id}' tidak ditemukan."}
                if not model["enabled"]:
                    return {"success": False, "error": "Model fallback harus dalam keadaan enabled."}
            updates["fallback_model_id"] = fallback_id

        if fields.get("retry_provider") is not None:
            try:
                retries = int(fields["retry_provider"])
            except (TypeError, ValueError):
                return {"success": False, "error": "retry_provider harus berupa angka."}
            if not 0 <= retries <= 5:
                return {"success": False, "error": "retry_provider harus antara 0 sampai 5."}
            updates["retry_provider"] = retries

        if updates:
            set_sql = ", ".join(f"{key} = ?" for key in updates)
            with self._lock, closing(self._connect()) as conn:
                conn.execute(f"UPDATE model_policy SET {set_sql} WHERE id = 1", list(updates.values()))
                conn.commit()
            logger.info("POLICY UPDATE | %s", updates)

        return {"success": True, "policy": self.get_policy()}


_store_singleton: Optional[ModelStore] = None
_store_lock = threading.Lock()


def get_model_store() -> ModelStore:
    global _store_singleton
    if _store_singleton is None:
        with _store_lock:
            if _store_singleton is None:
                _store_singleton = ModelStore()
    return _store_singleton