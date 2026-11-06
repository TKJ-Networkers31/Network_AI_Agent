"""
AIRA OS — User Memory Management Service (Phase F & Directive).
Authoritative service for managing isolated, per-user persistent memory and preferences.

Guarantees:
- Strict logical isolation: Every memory record is owned by authenticated user_id.
- Account-level persistence: Accessible across Session A, Session B, and Session C for the same user.
- User A's memories NEVER enter User B's AI context.
- Full CRUD, search, category classification, importance scoring, and user-level toggle.
- Automatic candidate extraction from conversations (name, preferred address, communication style, technical facts).
- Guest users never write persistent long-term memories.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List, Optional
import uuid

from core.topology_db import DEFAULT_TOPOLOGY_DB_PATH, topology_transaction

logger = logging.getLogger("aira.memory.service")

VALID_CATEGORIES = {
    "profile": "User Profile & Identity",
    "preferences": "Communication & Response Preferences",
    "technical": "Technical Knowledge & Interests",
    "project": "Projects & Operational Context",
    "facts": "Important Saved Facts",
    "learning": "Learning & Skill Level",
    "communication": "Communication Style & Tone",
    "workflows": "Standard Workflows",
    "general": "General Preferences",
}


def is_guest_user(user_id: Optional[str]) -> bool:
    """Returns True if the user_id represents an anonymous or guest account."""
    if not user_id:
        return True
    uid = str(user_id).lower().strip()
    return uid in ("guest", "anonymous", "none") or uid.startswith("usr_guest") or "sandbox" in uid


class UserMemoryService:
    """Manages isolated long-term user memories, identities, and personalization preferences."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()

    # -------------------------------------------------------------------------
    # User Preferences & Memory Toggle
    # -------------------------------------------------------------------------

    def get_or_create_user_preferences(self, user_id: str) -> Dict[str, Any]:
        """Retrieves or initializes user preferences."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with topology_transaction(self.db_path, write=True) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM user_preferences WHERE user_id = ?", (user_id,)).fetchone()
            if row:
                res = dict(row)
                res["memory_enabled"] = bool(res.get("memory_enabled", 1))
                try:
                    res["settings"] = json.loads(res.get("settings_json") or "{}")
                except Exception:
                    res["settings"] = {}
                return res

            pref_id = f"pref_{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO user_preferences
                (pref_id, user_id, memory_enabled, active_persona_id, custom_instructions, settings_json, created_at, updated_at)
                VALUES (?, ?, 1, 'preset_technical', '', '{}', ?, ?)
                """,
                (pref_id, user_id, now_iso, now_iso),
            )
            return {
                "pref_id": pref_id,
                "user_id": user_id,
                "memory_enabled": True,
                "active_persona_id": "preset_technical",
                "custom_instructions": "",
                "settings_json": "{}",
                "settings": {},
                "created_at": now_iso,
                "updated_at": now_iso,
            }

    def set_memory_enabled(self, user_id: str, enabled: bool) -> bool:
        """Toggles long-term memory for user."""
        self.get_or_create_user_preferences(user_id)
        now_iso = datetime.now(timezone.utc).isoformat()
        val = 1 if enabled else 0
        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                "UPDATE user_preferences SET memory_enabled = ?, updated_at = ? WHERE user_id = ?",
                (val, now_iso, user_id),
            )
            return True

    def update_user_preferences(
        self,
        user_id: str,
        memory_enabled: Optional[bool] = None,
        active_persona_id: Optional[str] = None,
        custom_instructions: Optional[str] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Updates user personalization preferences fields."""
        self.get_or_create_user_preferences(user_id)
        updates = []
        params = []
        now_iso = datetime.now(timezone.utc).isoformat()
        if memory_enabled is not None:
            updates.append("memory_enabled = ?")
            params.append(1 if memory_enabled else 0)
        if active_persona_id is not None:
            updates.append("active_persona_id = ?")
            params.append(active_persona_id)
        if custom_instructions is not None:
            updates.append("custom_instructions = ?")
            params.append(custom_instructions)
        if settings is not None:
            updates.append("settings_json = ?")
            params.append(json.dumps(settings))

        if updates:
            updates.append("updated_at = ?")
            params.append(now_iso)
            params.append(user_id)
            sql = f"UPDATE user_preferences SET {', '.join(updates)} WHERE user_id = ?"
            with topology_transaction(self.db_path, write=True) as conn:
                conn.execute(sql, tuple(params))
        return self.get_or_create_user_preferences(user_id)

    def is_memory_enabled(self, user_id: str) -> bool:
        if is_guest_user(user_id):
            return False
        pref = self.get_or_create_user_preferences(user_id)
        return bool(pref.get("memory_enabled", 1))

    # -------------------------------------------------------------------------
    # User Identity & Preferred Address (Directive Section 3.2)
    # -------------------------------------------------------------------------

    def get_user_identity(self, user_id: str) -> Dict[str, Any]:
        """Retrieves structured user identity information."""
        pref = self.get_or_create_user_preferences(user_id)
        settings = pref.get("settings") or {}
        ident = settings.get("identity") or {}
        return {
            "full_name": ident.get("full_name") or "",
            "preferred_name": ident.get("preferred_name") or "",
            "nickname": ident.get("nickname") or "",
            "title": ident.get("title") or "",
            "language": ident.get("language") or "id",
            "communication_style": ident.get("communication_style") or "casual_technical",
            "explanation_preference": ident.get("explanation_preference") or "step_by_step",
        }

    def update_user_identity(self, user_id: str, identity_data: Dict[str, Any]) -> Dict[str, Any]:
        """Updates persistent user identity and synchronizes profile memory."""
        pref = self.get_or_create_user_preferences(user_id)
        settings = pref.get("settings") or {}
        current_ident = settings.get("identity") or {}

        for k, v in identity_data.items():
            if v is not None and str(v).strip():
                current_ident[k] = str(v).strip()

        settings["identity"] = current_ident
        self.update_user_preferences(user_id, settings=settings)

        # Synchronize profile memory entry for cross-session clarity
        pref_name = current_ident.get("preferred_name")
        full_name = current_ident.get("full_name")
        style = current_ident.get("communication_style")
        expl = current_ident.get("explanation_preference")

        summary_parts = []
        if full_name:
            summary_parts.append(f"Nama lengkap pengguna adalah {full_name}.")
        if pref_name:
            summary_parts.append(f"Pengguna ingin dipanggil dengan nama '{pref_name}'.")
        if style:
            summary_parts.append(f"Gaya komunikasi yang disukai: {style}.")
        if expl:
            summary_parts.append(f"Preferensi penjelasan: {expl}.")

        if summary_parts:
            self.save_memory(
                user_id=user_id,
                category="profile",
                content=" ".join(summary_parts),
                source="USER_EXPLICIT",
                importance=1.0,
                metadata={"identity": current_ident},
            )

        return current_ident

    # -------------------------------------------------------------------------
    # Memories CRUD, Search, Deduplication & Relevance
    # -------------------------------------------------------------------------

    def save_memory(
        self,
        user_id: str,
        category: str,
        content: str,
        source: str = "USER",
        importance: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None,
        memory_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates or updates a memory with deduplication and conflict resolution.
        If a similar memory exists under the same category, updates it to preserve freshness.
        """
        if is_guest_user(user_id):
            return {
                "memory_id": "guest_transient",
                "user_id": user_id,
                "category": category,
                "content": content,
                "skipped": True,
                "reason": "Guest user memory is not persisted.",
            }

        cat = category.lower().strip()
        if cat not in VALID_CATEGORIES:
            cat = "general"

        clean_content = content.strip()
        now_iso = datetime.now(timezone.utc).isoformat()
        meta_json = json.dumps(metadata or {})

        # Check existing memories in category for deduplication / update
        with topology_transaction(self.db_path, write=True) as conn:
            conn.row_factory = sqlite3.Row

            if memory_id:
                # Direct update
                conn.execute(
                    """
                    UPDATE user_memories
                    SET category = ?, content = ?, importance = ?, metadata_json = ?, updated_at = ?
                    WHERE memory_id = ? AND user_id = ?
                    """,
                    (cat, clean_content, float(importance), meta_json, now_iso, memory_id, user_id),
                )
                mem_id = memory_id
            else:
                # Check near-duplicate in category
                existing_row = None
                if cat in ("profile", "preferences"):
                    # Only one active profile summary needed
                    existing_row = conn.execute(
                        "SELECT * FROM user_memories WHERE user_id = ? AND category = ? LIMIT 1",
                        (user_id, cat),
                    ).fetchone()
                else:
                    # Check exact or very high similarity
                    existing_row = conn.execute(
                        "SELECT * FROM user_memories WHERE user_id = ? AND category = ? AND content = ? LIMIT 1",
                        (user_id, cat, clean_content),
                    ).fetchone()

                if existing_row:
                    mem_id = existing_row["memory_id"]
                    conn.execute(
                        """
                        UPDATE user_memories
                        SET content = ?, importance = MAX(importance, ?), metadata_json = ?, updated_at = ?
                        WHERE memory_id = ?
                        """,
                        (clean_content, float(importance), meta_json, now_iso, mem_id),
                    )
                else:
                    mem_id = f"mem_{uuid.uuid4().hex[:12]}"
                    conn.execute(
                        """
                        INSERT INTO user_memories
                        (memory_id, user_id, category, content, source, importance, is_enabled, metadata_json, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                        """,
                        (mem_id, user_id, cat, clean_content, source, float(importance), meta_json, now_iso, now_iso),
                    )

        return self.get_memory(mem_id, user_id) or {}

    def add_memory(
        self,
        user_id: str,
        category: str,
        content: str,
        source: str = "USER",
        importance: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Convenience method for creating a memory entry."""
        return self.save_memory(
            user_id=user_id,
            category=category,
            content=content,
            source=source,
            importance=importance,
            metadata=metadata,
        )

    def list_memories(
        self,
        user_id: str,
        category: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Lists user memories with strict user_id filtering."""
        if is_guest_user(user_id):
            return []

        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            sql = "SELECT * FROM user_memories WHERE user_id = ?"
            params: List[Any] = [user_id]

            if category and category.lower() in VALID_CATEGORIES:
                sql += " AND category = ?"
                params.append(category.lower())

            if query and query.strip():
                sql += " AND content LIKE ?"
                params.append(f"%{query.strip()}%")

            sql += " ORDER BY importance DESC, updated_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(sql, params).fetchall()
            results = []
            for r in rows:
                item = dict(r)
                item["category_label"] = VALID_CATEGORIES.get(item["category"], item["category"])
                try:
                    item["metadata"] = json.loads(item["metadata_json"])
                except Exception:
                    item["metadata"] = {}
                results.append(item)
            return results

    # Alias matching Section 4.3
    get_user_memory = list_memories

    def get_memory(self, memory_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single memory verifying user ownership."""
        if is_guest_user(user_id):
            return None

        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM user_memories WHERE memory_id = ? AND user_id = ?",
                (memory_id, user_id),
            ).fetchone()
            if not row:
                return None
            item = dict(row)
            item["category_label"] = VALID_CATEGORIES.get(item["category"], item["category"])
            try:
                item["metadata"] = json.loads(item["metadata_json"])
            except Exception:
                item["metadata"] = {}
            return item

    def update_memory(
        self,
        memory_id: str,
        user_id: str,
        content: Optional[str] = None,
        category: Optional[str] = None,
        importance: Optional[float] = None,
        is_enabled: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        """Updates memory entry verifying user ownership."""
        if is_guest_user(user_id):
            return None

        existing = self.get_memory(memory_id, user_id)
        if not existing:
            return None

        now_iso = datetime.now(timezone.utc).isoformat()
        updates = ["updated_at = ?"]
        params: List[Any] = [now_iso]

        if content is not None:
            updates.append("content = ?")
            params.append(content.strip())
        if category is not None and category.lower() in VALID_CATEGORIES:
            updates.append("category = ?")
            params.append(category.lower())
        if importance is not None:
            updates.append("importance = ?")
            params.append(float(importance))
        if is_enabled is not None:
            updates.append("is_enabled = ?")
            params.append(1 if is_enabled else 0)

        params.extend([memory_id, user_id])

        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                f"UPDATE user_memories SET {', '.join(updates)} WHERE memory_id = ? AND user_id = ?",
                params,
            )

        return self.get_memory(memory_id, user_id)

    def delete_memory(self, memory_id: str, user_id: str) -> bool:
        """Deletes a memory entry verifying user ownership."""
        if is_guest_user(user_id):
            return False

        with topology_transaction(self.db_path, write=True) as conn:
            res = conn.execute(
                "DELETE FROM user_memories WHERE memory_id = ? AND user_id = ?",
                (memory_id, user_id),
            )
            return res.rowcount > 0

    delete_user_memory = delete_memory

    def clear_all_memories(self, user_id: str) -> int:
        """Deletes all memories owned by the user."""
        if is_guest_user(user_id):
            return 0

        with topology_transaction(self.db_path, write=True) as conn:
            res = conn.execute("DELETE FROM user_memories WHERE user_id = ?", (user_id,))
            return res.rowcount

    def deduplicate_memory(self, user_id: str, category: Optional[str] = None) -> int:
        """Scans and merges duplicate content within the user's memories."""
        if is_guest_user(user_id):
            return 0

        with topology_transaction(self.db_path, write=True) as conn:
            conn.row_factory = sqlite3.Row
            sql = "SELECT memory_id, content, category, created_at FROM user_memories WHERE user_id = ?"
            params = [user_id]
            if category:
                sql += " AND category = ?"
                params.append(category)
            sql += " ORDER BY created_at ASC"

            rows = conn.execute(sql, params).fetchall()
            seen: Dict[tuple, str] = {}
            deleted = 0
            for r in rows:
                key = (r["category"], r["content"].strip().lower())
                if key in seen:
                    conn.execute("DELETE FROM user_memories WHERE memory_id = ?", (r["memory_id"],))
                    deleted += 1
                else:
                    seen[key] = r["memory_id"]
            return deleted

    def rebuild_memory_index(self, user_id: Optional[str] = None) -> bool:
        """Verifies database constraints and rebuilds indexes."""
        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_memories_user ON user_memories(user_id, category)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_memories_created ON user_memories(user_id, created_at)")
            return True

    def get_memory_summary(self, user_id: str) -> Dict[str, Any]:
        """Provides summary of user memory counts and categories."""
        if is_guest_user(user_id):
            return {
                "total_memories": 0,
                "memory_enabled": False,
                "categories": {k: 0 for k in VALID_CATEGORIES},
                "category_labels": VALID_CATEGORIES,
                "is_guest": True,
            }

        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT category, COUNT(*) as count FROM user_memories WHERE user_id = ? GROUP BY category",
                (user_id,),
            ).fetchall()
            cat_counts = {k: 0 for k in VALID_CATEGORIES}
            total = 0
            for r in rows:
                c = r["category"]
                cnt = r["count"]
                if c in cat_counts:
                    cat_counts[c] = cnt
                total += cnt

            enabled = self.is_memory_enabled(user_id)
            identity = self.get_user_identity(user_id)
            return {
                "total_memories": total,
                "memory_enabled": enabled,
                "categories": cat_counts,
                "category_labels": VALID_CATEGORIES,
                "identity": identity,
            }

    def retrieve_context_memories(self, user_id: str, query: str = "", max_items: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieves top relevant memories for prompt context injection.
        Guarantees STRICT USER ISOLATION: Only user_id memories are queried.
        """
        if is_guest_user(user_id) or not self.is_memory_enabled(user_id):
            return []

        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            sql = "SELECT * FROM user_memories WHERE user_id = ? AND is_enabled = 1"
            params: List[Any] = [user_id]

            if query and query.strip():
                keywords = [k for k in query.lower().split() if len(k) > 3][:3]
                if keywords:
                    clauses = ["content LIKE ?" for _ in keywords]
                    sql += f" AND ({' OR '.join(clauses)})"
                    for kw in keywords:
                        params.append(f"%{kw}%")

            sql += " ORDER BY importance DESC, updated_at DESC LIMIT ?"
            params.append(max_items)

            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    retrieve_relevant_memory = retrieve_context_memories

    # -------------------------------------------------------------------------
    # Automatic Memory Candidate Extraction (Directive Section 4.4 & 3.2)
    # -------------------------------------------------------------------------

    def extract_memory_candidates(
        self,
        user_input: str,
        assistant_answer: str,
        user_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Extracts persistent memory candidates and identity preferences from user conversation turns.
        Supports natural self-introduction, preferred names, technical knowledge level, and project facts.
        """
        if is_guest_user(user_id) or not user_input or not user_input.strip():
            return []

        text = user_input.strip()
        saved_items = []

        # 1. Identity & Preferred Name Patterns
        # e.g., "Nama saya Mohamad Lingga Syahputra", "Namaku Lingga", "Panggil aku Master", "Panggil saya Pak Lingga"
        name_match = re.search(r"(?:nama\s+saya|namaku|nama\s+ku)\s+(?:adalah\s+)?([A-Za-z0-9\s]{2,40})", text, re.IGNORECASE)
        pref_match = re.search(r"panggil\s+(?:aku|saya)\s+([A-Za-z0-9\s]{2,30})", text, re.IGNORECASE)

        identity_updates = {}
        if name_match:
            raw_name = name_match.group(1).split(".")[0].split(",")[0].strip()
            # Clean common trailing words
            raw_name = re.sub(r"\s*\b(dan|ya|tolong|panggil|bisa)\b.*", "", raw_name, flags=re.IGNORECASE).strip()
            if len(raw_name) >= 2:
                identity_updates["full_name"] = raw_name

        if pref_match:
            raw_pref = pref_match.group(1).split(".")[0].split(",")[0].strip()
            raw_pref = re.sub(r"\s*\b(dan|ya|tolong|saja|aja|dong|deh)\b.*", "", raw_pref, flags=re.IGNORECASE).strip()
            if len(raw_pref) >= 2:
                identity_updates["preferred_name"] = raw_pref

        # 2. Communication & Style Preferences
        # e.g., "Saya lebih suka penjelasan step by step", "Gunakan bahasa santai tapi teknis"
        if re.search(r"step\s*[-_]?by\s*[-_]?step|langkah\s+demi\s+langkah|bertahap", text, re.IGNORECASE):
            identity_updates["explanation_preference"] = "step_by_step"
        elif re.search(r"langsung\s+ke\s+poin|singkat\s+saja|ringkas|to\s+the\s+point", text, re.IGNORECASE):
            identity_updates["explanation_preference"] = "concise"

        if re.search(r"santai\s+tapi\s+teknis|casual\s+technical", text, re.IGNORECASE):
            identity_updates["communication_style"] = "casual_technical"
        elif re.search(r"formal|resmi|profesional", text, re.IGNORECASE):
            identity_updates["communication_style"] = "formal_technical"

        if identity_updates:
            self.update_user_identity(user_id, identity_updates)
            saved_items.append({"category": "profile", "identity": identity_updates})
            logger.info("MEMORY_EXTRACT: Updated identity for %s: %s", user_id, identity_updates)

        # 3. Technical Knowledge & Platform Preferences
        # e.g., "Kantor kami menggunakan MikroTik RouterOS v7", "Saya mengelola jaringan BGP dan OSPF"
        tech_match = re.search(
            r"(?:kami\s+menggunakan|saya\s+menggunakan|jaringan\s+kami\s+pakai|router\s+kami\s+pakai|kami\s+pakai)\s+([A-Za-z0-9\s\.\-_/]{3,60})",
            text, re.IGNORECASE
        )
        if tech_match:
            tech_val = tech_match.group(1).split(".")[0].strip()
            if len(tech_val) >= 3:
                content = f"Lingkungan jaringan pengguna menggunakan {tech_val}."
                saved = self.save_memory(
                    user_id=user_id,
                    category="technical",
                    content=content,
                    source="AUTO_EXTRACTED",
                    importance=0.7,
                )
                saved_items.append(saved)

        # 4. Explicit Remember Instruction
        # e.g., "Ingat bahwa IP gateway utama adalah 192.168.1.1", "Catat bahwa ..."
        rem_match = re.search(r"(?:ingat\s+bahwa|catat\s+bahwa|simpan\s+fakta)\s+([^\n]{6,200})", text, re.IGNORECASE)
        if rem_match:
            fact_val = rem_match.group(1).strip()
            if len(fact_val) >= 5:
                saved = self.save_memory(
                    user_id=user_id,
                    category="facts",
                    content=fact_val,
                    source="USER_EXPLICIT",
                    importance=0.9,
                )
                saved_items.append(saved)

        return saved_items


_memory_service: Optional[UserMemoryService] = None


def get_memory_service() -> UserMemoryService:
    global _memory_service
    if _memory_service is None:
        _memory_service = UserMemoryService()
    return _memory_service
