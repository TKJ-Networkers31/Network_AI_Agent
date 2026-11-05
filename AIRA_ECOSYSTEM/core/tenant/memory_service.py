"""
AIRA OS — User Memory Management Service (Phase F).
Authoritative service for managing isolated, per-user persistent memory and preferences.

Guarantees:
- Strict logical isolation: Every memory record is owned by user_id.
- User A's memories NEVER enter User B's AI context.
- Full CRUD, search, category classification, importance scoring, and user-level toggle.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional
import uuid

from core.topology_db import DEFAULT_TOPOLOGY_DB_PATH, topology_transaction

logger = logging.getLogger("aira.memory.service")

VALID_CATEGORIES = {
    "learning": "Learning preferences",
    "technical": "Technical interests",
    "project": "Project context",
    "communication": "Communication preferences",
    "workflows": "Workflows",
    "general": "General preferences",
}


class UserMemoryService:
    """Manages isolated long-term user memories and personalization preferences."""

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
        if updates:
            updates.append("updated_at = ?")
            params.append(now_iso)
            params.append(user_id)
            sql = f"UPDATE user_preferences SET {', '.join(updates)} WHERE user_id = ?"
            with topology_transaction(self.db_path, write=True) as conn:
                conn.execute(sql, tuple(params))
        return self.get_or_create_user_preferences(user_id)

    def is_memory_enabled(self, user_id: str) -> bool:
        pref = self.get_or_create_user_preferences(user_id)
        return bool(pref.get("memory_enabled", 1))

    # -------------------------------------------------------------------------
    # Memories CRUD & Search
    # -------------------------------------------------------------------------

    def add_memory(
        self,
        user_id: str,
        category: str,
        content: str,
        source: str = "USER",
        importance: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Creates a new isolated memory entry for user."""
        cat = category.lower().strip()
        if cat not in VALID_CATEGORIES:
            cat = "general"

        now_iso = datetime.now(timezone.utc).isoformat()
        mem_id = f"mem_{uuid.uuid4().hex[:12]}"
        meta_json = json.dumps(metadata or {})

        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT INTO user_memories
                (memory_id, user_id, category, content, source, importance, is_enabled, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                """,
                (mem_id, user_id, cat, content.strip(), source, float(importance), meta_json, now_iso, now_iso),
            )

        return {
            "memory_id": mem_id,
            "user_id": user_id,
            "category": cat,
            "category_label": VALID_CATEGORIES.get(cat, cat),
            "content": content.strip(),
            "source": source,
            "importance": float(importance),
            "is_enabled": 1,
            "metadata": metadata or {},
            "created_at": now_iso,
            "updated_at": now_iso,
        }

    def list_memories(
        self,
        user_id: str,
        category: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Lists user memories with strict user_id filtering."""
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

    def get_memory(self, memory_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single memory verifying user ownership."""
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
        with topology_transaction(self.db_path, write=True) as conn:
            res = conn.execute(
                "DELETE FROM user_memories WHERE memory_id = ? AND user_id = ?",
                (memory_id, user_id),
            )
            return res.rowcount > 0

    def clear_all_memories(self, user_id: str) -> int:
        """Deletes all memories owned by the user."""
        with topology_transaction(self.db_path, write=True) as conn:
            res = conn.execute("DELETE FROM user_memories WHERE user_id = ?", (user_id,))
            return res.rowcount

    def get_memory_summary(self, user_id: str) -> Dict[str, Any]:
        """Provides summary of user memory counts and categories."""
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
            return {
                "total_memories": total,
                "memory_enabled": enabled,
                "categories": cat_counts,
                "category_labels": VALID_CATEGORIES,
            }

    def retrieve_context_memories(self, user_id: str, query: str = "", max_items: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieves top relevant memories for prompt context injection.
        Guarantees STRICT USER ISOLATION: Only user_id memories are queried.
        """
        if not self.is_memory_enabled(user_id):
            return []

        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            sql = "SELECT * FROM user_memories WHERE user_id = ? AND is_enabled = 1"
            params: List[Any] = [user_id]

            if query and query.strip():
                # Bounded keyword relevance matching
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


_memory_service: Optional[UserMemoryService] = None


def get_memory_service() -> UserMemoryService:
    global _memory_service
    if _memory_service is None:
        _memory_service = UserMemoryService()
    return _memory_service

