"""
core/persona/engine.py — Persona Engine (Phase 1.3).

Satu-satunya modul yang boleh menyusun System Prompt AIRA. Menyimpan
profile/behavior/preset di database/persona.db - SQLite terpisah dari
long_term_memory.db / chat_sessions.db / logs.db / model_registry.db,
sesuai aturan "satu .db, satu pemilik modul" (docs/database.md).
"""

import json
import sqlite3
import threading
import time
import logging
from pathlib import Path
from contextlib import closing
from typing import Optional

from core.persona.presets import BUILTIN_PRESETS
from core.persona.validator import validate_behavior_fields, validate_profile_fields
from core.persona.prompt_builder import build_prompt
from core.persona.types import PersonaProfile, PersonaBehavior

logger = logging.getLogger("aira.persona")

BASE_DIR = Path(__file__).resolve().parents[2]  # AIRA_ECOSYSTEM/
DATABASE_DIR = BASE_DIR / "database"
DB_FILE = DATABASE_DIR / "persona.db"

DATABASE_DIR.mkdir(exist_ok=True)

DEFAULT_PRESET_ID = "akane"
_write_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with closing(_connect()) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS persona_profile (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                assistant_name TEXT NOT NULL DEFAULT 'AIRA',
                user_name TEXT,
                language TEXT NOT NULL DEFAULT 'id',
                timezone TEXT NOT NULL DEFAULT 'Asia/Jakarta',
                greeting TEXT DEFAULT '',
                active_preset TEXT NOT NULL DEFAULT 'akane',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS persona_behavior (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                professionalism INTEGER NOT NULL DEFAULT 86,
                friendliness INTEGER NOT NULL DEFAULT 84,
                playfulness INTEGER NOT NULL DEFAULT 42,
                verbosity INTEGER NOT NULL DEFAULT 78,
                empathy INTEGER NOT NULL DEFAULT 74,
                teaching_depth INTEGER NOT NULL DEFAULT 96,
                updated_at REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS persona_presets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                is_builtin INTEGER NOT NULL DEFAULT 0,
                profile_json TEXT NOT NULL,
                behavior_json TEXT NOT NULL,
                persona_text_json TEXT NOT NULL DEFAULT '{}',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        conn.commit()

    _seed_builtin_presets()
    _seed_default_profile_and_behavior()


def _seed_builtin_presets() -> None:
    now = time.time()

    with _write_lock:
        with closing(_connect()) as conn:
            for preset_id, preset in BUILTIN_PRESETS.items():
                existing = conn.execute(
                    "SELECT id FROM persona_presets WHERE id = ?", (preset_id,)
                ).fetchone()

                if existing:
                    # Preset built-in SELALU disinkronkan ulang ke definisi
                    # presets.py (sumber kebenaran) setiap startup - update
                    # preset bawaan cukup edit kode, tanpa migrasi manual.
                    # Preset hasil clone milik user (id != builtin) tidak
                    # pernah tersentuh loop ini.
                    conn.execute("""
                        UPDATE persona_presets
                        SET name = ?, description = ?, is_builtin = 1,
                            profile_json = ?, behavior_json = ?,
                            persona_text_json = ?, updated_at = ?
                        WHERE id = ?
                    """, (
                        preset["name"], preset["description"],
                        json.dumps(preset["profile"], ensure_ascii=False),
                        json.dumps(preset["behavior"], ensure_ascii=False),
                        json.dumps(preset.get("persona_text", {}), ensure_ascii=False),
                        now, preset_id,
                    ))
                else:
                    conn.execute("""
                        INSERT INTO persona_presets
                            (id, name, description, is_builtin, profile_json,
                             behavior_json, persona_text_json, created_at, updated_at)
                        VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?)
                    """, (
                        preset_id, preset["name"], preset["description"],
                        json.dumps(preset["profile"], ensure_ascii=False),
                        json.dumps(preset["behavior"], ensure_ascii=False),
                        json.dumps(preset.get("persona_text", {}), ensure_ascii=False),
                        now, now,
                    ))
            conn.commit()


def _seed_default_profile_and_behavior() -> None:
    with closing(_connect()) as conn:
        has_profile = conn.execute("SELECT id FROM persona_profile WHERE id = 1").fetchone()
        has_behavior = conn.execute("SELECT id FROM persona_behavior WHERE id = 1").fetchone()

    if has_profile and has_behavior:
        return

    default_preset = BUILTIN_PRESETS[DEFAULT_PRESET_ID]
    now = time.time()

    with _write_lock:
        with closing(_connect()) as conn:
            if not has_profile:
                profile = default_preset["profile"]
                conn.execute("""
                    INSERT INTO persona_profile
                        (id, assistant_name, user_name, language, timezone,
                         greeting, active_preset, created_at, updated_at)
                    VALUES (1, ?, NULL, ?, ?, ?, ?, ?, ?)
                """, (
                    profile.get("assistant_name", "AIRA"),
                    profile.get("language", "id"),
                    profile.get("timezone", "Asia/Jakarta"),
                    profile.get("greeting", ""),
                    DEFAULT_PRESET_ID, now, now,
                ))

            if not has_behavior:
                behavior = default_preset["behavior"]
                conn.execute("""
                    INSERT INTO persona_behavior
                        (id, professionalism, friendliness, playfulness,
                         verbosity, empathy, teaching_depth, updated_at)
                    VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    behavior["professionalism"], behavior["friendliness"],
                    behavior["playfulness"], behavior["verbosity"],
                    behavior["empathy"], behavior["teaching_depth"], now,
                ))

            conn.commit()

    logger.info("PERSONA | profile & behavior default (%s) tersedia.", DEFAULT_PRESET_ID)


_init_db()


class PersonaEngine:
    """
    Satu-satunya pembuat System Prompt AIRA. REI/planner TIDAK boleh
    menyusun prompt sendiri - hanya memanggil PersonaEngine.build() dan
    mengirim hasilnya apa adanya ke provider LLM. Ganti model di
    Model Management (REI) TIDAK mengubah apa pun di sini.
    """

    # -------------------------- READ --------------------------

    def get_profile(self) -> dict:
        with closing(_connect()) as conn:
            row = conn.execute("SELECT * FROM persona_profile WHERE id = 1").fetchone()
        return dict(row) if row else PersonaProfile().__dict__

    def get_behavior(self) -> dict:
        with closing(_connect()) as conn:
            row = conn.execute("SELECT * FROM persona_behavior WHERE id = 1").fetchone()

        if not row:
            return PersonaBehavior().as_dict()

        data = dict(row)
        data.pop("id", None)
        data.pop("updated_at", None)
        return data

    def get_active_preset_text(self) -> dict:
        profile = self.get_profile()
        preset_id = profile.get("active_preset") or DEFAULT_PRESET_ID

        with closing(_connect()) as conn:
            row = conn.execute(
                "SELECT persona_text_json FROM persona_presets WHERE id = ?",
                (preset_id,),
            ).fetchone()

        if not row:
            return BUILTIN_PRESETS[DEFAULT_PRESET_ID].get("persona_text", {})

        try:
            return json.loads(row["persona_text_json"]) or {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def get_state(self) -> dict:
        """Bentuk gabungan untuk GET /persona - profile + behavior."""
        return {"profile": self.get_profile(), "behavior": self.get_behavior()}

    def list_presets(self) -> list[dict]:
        with closing(_connect()) as conn:
            rows = conn.execute(
                "SELECT id, name, description, is_builtin, created_at, updated_at "
                "FROM persona_presets ORDER BY is_builtin DESC, name ASC"
            ).fetchall()

        active_preset = self.get_profile().get("active_preset")

        result = []
        for row in rows:
            item = dict(row)
            item["is_builtin"] = bool(item["is_builtin"])
            item["is_active"] = item["id"] == active_preset
            result.append(item)

        return result

    def get_preset(self, preset_id: str) -> Optional[dict]:
        with closing(_connect()) as conn:
            row = conn.execute(
                "SELECT * FROM persona_presets WHERE id = ?", (preset_id,)
            ).fetchone()

        if not row:
            return None

        item = dict(row)
        item["is_builtin"] = bool(item["is_builtin"])
        item["profile"] = json.loads(item.pop("profile_json"))
        item["behavior"] = json.loads(item.pop("behavior_json"))
        item["persona_text"] = json.loads(item.pop("persona_text_json") or "{}")
        return item

    # -------------------------- WRITE --------------------------

    def update_profile(self, fields: dict) -> dict:
        cleaned = validate_profile_fields(fields)

        if not cleaned:
            return {"success": True, "profile": self.get_profile()}

        set_clauses = [f"{key} = ?" for key in cleaned]
        params = list(cleaned.values())
        params.append(time.time())

        with _write_lock:
            with closing(_connect()) as conn:
                conn.execute(
                    f"UPDATE persona_profile SET {', '.join(set_clauses)}, "
                    f"updated_at = ? WHERE id = 1",
                    params,
                )
                conn.commit()

        logger.info("PERSONA PROFILE UPDATE | fields=%s", list(cleaned.keys()))

        return {"success": True, "profile": self.get_profile()}

    def update_behavior(self, fields: dict) -> dict:
        cleaned = validate_behavior_fields(fields)

        if not cleaned:
            return {"success": True, "behavior": self.get_behavior()}

        set_clauses = [f"{key} = ?" for key in cleaned]
        params = list(cleaned.values())
        params.append(time.time())

        with _write_lock:
            with closing(_connect()) as conn:
                conn.execute(
                    f"UPDATE persona_behavior SET {', '.join(set_clauses)}, "
                    f"updated_at = ? WHERE id = 1",
                    params,
                )
                conn.commit()

        logger.info("PERSONA BEHAVIOR UPDATE | fields=%s", cleaned)

        return {"success": True, "behavior": self.get_behavior()}

    def apply_preset(self, preset_id: str) -> dict:
        preset = self.get_preset(preset_id)

        if not preset:
            return {"success": False, "error": f"Preset '{preset_id}' tidak ditemukan."}

        now = time.time()
        profile = preset["profile"]
        behavior = preset["behavior"]

        with _write_lock:
            with closing(_connect()) as conn:
                conn.execute("""
                    UPDATE persona_profile SET
                        assistant_name = ?, language = ?, timezone = ?,
                        greeting = ?, active_preset = ?, updated_at = ?
                    WHERE id = 1
                """, (
                    profile.get("assistant_name", "AIRA"),
                    profile.get("language", "id"),
                    profile.get("timezone", "Asia/Jakarta"),
                    profile.get("greeting", ""),
                    preset_id, now,
                ))

                conn.execute("""
                    UPDATE persona_behavior SET
                        professionalism = ?, friendliness = ?, playfulness = ?,
                        verbosity = ?, empathy = ?, teaching_depth = ?, updated_at = ?
                    WHERE id = 1
                """, (
                    behavior["professionalism"], behavior["friendliness"],
                    behavior["playfulness"], behavior["verbosity"],
                    behavior["empathy"], behavior["teaching_depth"], now,
                ))

                conn.commit()

        logger.info("PERSONA PRESET APPLIED | preset_id=%s", preset_id)

        return {"success": True, "state": self.get_state()}

    def clone_preset(self, preset_id: str, new_name: str) -> dict:
        source = self.get_preset(preset_id)

        if not source:
            return {"success": False, "error": f"Preset '{preset_id}' tidak ditemukan."}

        new_name = (new_name or "").strip()

        if not new_name:
            return {"success": False, "error": "Nama preset baru wajib diisi."}

        new_id = _slugify(new_name)
        now = time.time()

        try:
            with _write_lock:
                with closing(_connect()) as conn:
                    conn.execute("""
                        INSERT INTO persona_presets
                            (id, name, description, is_builtin, profile_json,
                             behavior_json, persona_text_json, created_at, updated_at)
                        VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?)
                    """, (
                        new_id, new_name,
                        f"Kloning dari '{source['name']}'.",
                        json.dumps(source["profile"], ensure_ascii=False),
                        json.dumps(source["behavior"], ensure_ascii=False),
                        json.dumps(source["persona_text"], ensure_ascii=False),
                        now, now,
                    ))
                    conn.commit()
        except sqlite3.IntegrityError:
            return {"success": False, "error": f"Preset dengan id '{new_id}' sudah ada."}

        logger.info("PERSONA PRESET CLONED | from=%s to=%s", preset_id, new_id)

        return {"success": True, "preset": self.get_preset(new_id)}

    # -------------------------- PROMPT BUILDING --------------------------

    def build(self, extra_context: str = "") -> str:
        """Dipanggil oleh Chat Session (lewat agents/rei/planner.py) tiap
        giliran percakapan untuk mendapatkan System Prompt final."""
        profile = self.get_profile()
        behavior = self.get_behavior()
        persona_text = self.get_active_preset_text()

        return build_prompt(profile, behavior, persona_text, extra_context)

    def preview(self, extra_context: str = "") -> str:
        """Sama seperti build(), dipakai endpoint /persona/preview - TIDAK
        PERNAH memanggil LLM, murni menampilkan hasil builder."""
        return self.build(extra_context)


def _slugify(name: str) -> str:
    slug = "".join(c.lower() if c.isalnum() else "-" for c in name.strip())
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-") or "preset"

    if slug in BUILTIN_PRESETS:
        slug = f"{slug}-custom"

    return slug


_engine_singleton: Optional[PersonaEngine] = None
_engine_lock = threading.Lock()


def get_engine() -> PersonaEngine:
    global _engine_singleton

    if _engine_singleton is None:
        with _engine_lock:
            if _engine_singleton is None:
                _engine_singleton = PersonaEngine()

    return _engine_singleton