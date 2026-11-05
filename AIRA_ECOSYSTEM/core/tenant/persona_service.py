"""
AIRA OS — User Persona Management Service (Phase F).
Manages AI behavioral profiles, system built-in presets, and user-isolated custom personas.

Guarantees:
- Built-in personas (owner_id = NULL) are read-only global templates that cannot be mutated by users.
- Custom personas are strictly owned by user_id and can only be modified/deleted by their owner.
- Active persona selection is tracked per-user in user_preferences.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional
import uuid

from core.topology_db import DEFAULT_TOPOLOGY_DB_PATH, topology_transaction

logger = logging.getLogger("aira.persona.service")


class UserPersonaService:
    """Service for managing built-in and user-custom personas."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()

    def list_personas_for_user(self, user_id: str) -> Dict[str, Any]:
        """
        Lists available personas for a user:
        1. Built-in system presets (user_id IS NULL)
        2. User's private custom personas (user_id = ?)
        Also returns user's active_persona_id.
        """
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row

            # Get user preferences for active persona
            pref_row = conn.execute(
                "SELECT active_persona_id FROM user_preferences WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            active_id = pref_row["active_persona_id"] if pref_row and pref_row["active_persona_id"] else "preset_technical"

            # Query system presets + user's personas
            rows = conn.execute(
                """
                SELECT * FROM user_personas
                WHERE user_id IS NULL OR user_id = ?
                ORDER BY (user_id IS NOT NULL) ASC, is_default DESC, created_at ASC
                """,
                (user_id,),
            ).fetchall()

            builtins = []
            customs = []
            for r in rows:
                item = dict(r)
                item["is_builtin"] = item["user_id"] is None
                item["is_active"] = (item["persona_id"] == active_id)
                if item["is_builtin"]:
                    builtins.append(item)
                else:
                    customs.append(item)

            return {
                "active_persona_id": active_id,
                "builtin_presets": builtins,
                "custom_personas": customs,
                "total_available": len(builtins) + len(customs),
            }

    def get_persona(self, persona_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieves a persona if it is a system preset or owned by user."""
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            if user_id:
                row = conn.execute(
                    "SELECT * FROM user_personas WHERE persona_id = ? AND (user_id IS NULL OR user_id = ?)",
                    (persona_id, user_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM user_personas WHERE persona_id = ?",
                    (persona_id,),
                ).fetchone()

            if not row:
                return None

            item = dict(row)
            item["is_builtin"] = item["user_id"] is None
            return item

    def get_active_persona(self, user_id: str) -> Dict[str, Any]:
        """Retrieves the currently active persona for user, falling back to preset_technical."""
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            pref_row = conn.execute(
                "SELECT active_persona_id FROM user_preferences WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            active_id = pref_row["active_persona_id"] if pref_row and pref_row["active_persona_id"] else "preset_technical"

            persona = self.get_persona(active_id, user_id)
            if not persona:
                # Fallback to technical preset
                persona = self.get_persona("preset_technical") or {
                    "persona_id": "fallback",
                    "name": "AIRA Network Assistant",
                    "response_style": "technical",
                    "technical_depth": 85,
                    "explanation_preference": "technical",
                    "custom_instructions": "",
                }
            return persona

    def set_active_persona(self, user_id: str, persona_id: str) -> bool:
        """Sets user's active persona after verifying access."""
        target = self.get_persona(persona_id, user_id)
        if not target:
            raise ValueError(f"Persona '{persona_id}' not found or access denied.")

        now_iso = datetime.now(timezone.utc).isoformat()
        with topology_transaction(self.db_path, write=True) as conn:
            # Ensure preferences row exists
            conn.execute(
                """
                INSERT INTO user_preferences
                (pref_id, user_id, memory_enabled, active_persona_id, custom_instructions, settings_json, created_at, updated_at)
                VALUES (?, ?, 1, ?, '', '{}', ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET active_persona_id = ?, updated_at = ?
                """,
                (f"pref_{uuid.uuid4().hex[:12]}", user_id, persona_id, now_iso, now_iso, persona_id, now_iso),
            )
            return True

    def create_custom_persona(
        self,
        user_id: str,
        name: str,
        description: str = "",
        response_style: str = "concise",
        language: str = "id",
        technical_depth: int = 80,
        explanation_preference: str = "technical",
        custom_instructions: str = "",
    ) -> Dict[str, Any]:
        """Creates a new custom persona owned exclusively by user."""
        now_iso = datetime.now(timezone.utc).isoformat()
        p_id = f"per_{uuid.uuid4().hex[:12]}"

        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT INTO user_personas
                (persona_id, user_id, name, description, response_style, language, technical_depth,
                 explanation_preference, custom_instructions, is_default, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    p_id, user_id, name.strip(), description.strip(), response_style.strip(),
                    language.strip(), int(technical_depth), explanation_preference.strip(),
                    custom_instructions.strip(), now_iso, now_iso
                ),
            )

        return self.get_persona(p_id, user_id)  # type: ignore

    def duplicate_persona(self, persona_id: str, user_id: str, new_name: Optional[str] = None) -> Dict[str, Any]:
        """Duplicates an existing built-in or user persona into a new custom persona."""
        source = self.get_persona(persona_id, user_id)
        if not source:
            raise ValueError(f"Source persona '{persona_id}' not found.")

        target_name = new_name or f"{source['name']} (Salinan)"
        return self.create_custom_persona(
            user_id=user_id,
            name=target_name,
            description=source.get("description", ""),
            response_style=source.get("response_style", "concise"),
            language=source.get("language", "id"),
            technical_depth=source.get("technical_depth", 80),
            explanation_preference=source.get("explanation_preference", "technical"),
            custom_instructions=source.get("custom_instructions", ""),
        )

    def update_custom_persona(
        self,
        persona_id: str,
        user_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        response_style: Optional[str] = None,
        language: Optional[str] = None,
        technical_depth: Optional[int] = None,
        explanation_preference: Optional[str] = None,
        custom_instructions: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Updates user's custom persona. Disallows mutating system presets."""
        existing = self.get_persona(persona_id, user_id)
        if not existing:
            raise ValueError(f"Persona '{persona_id}' not found.")
        if existing["is_builtin"]:
            raise PermissionError("Preset sistem bawaan bersifat hanya-baca (read-only) dan tidak dapat dimodifikasi.")

        now_iso = datetime.now(timezone.utc).isoformat()
        updates = ["updated_at = ?"]
        params: List[Any] = [now_iso]

        if name is not None:
            updates.append("name = ?")
            params.append(name.strip())
        if description is not None:
            updates.append("description = ?")
            params.append(description.strip())
        if response_style is not None:
            updates.append("response_style = ?")
            params.append(response_style.strip())
        if language is not None:
            updates.append("language = ?")
            params.append(language.strip())
        if technical_depth is not None:
            updates.append("technical_depth = ?")
            params.append(int(technical_depth))
        if explanation_preference is not None:
            updates.append("explanation_preference = ?")
            params.append(explanation_preference.strip())
        if custom_instructions is not None:
            updates.append("custom_instructions = ?")
            params.append(custom_instructions.strip())

        params.extend([persona_id, user_id])

        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                f"UPDATE user_personas SET {', '.join(updates)} WHERE persona_id = ? AND user_id = ?",
                params,
            )

        return self.get_persona(persona_id, user_id)  # type: ignore

    def delete_custom_persona(self, persona_id: str, user_id: str) -> bool:
        """Deletes user's custom persona. Disallows deleting system presets."""
        existing = self.get_persona(persona_id, user_id)
        if not existing:
            return False
        if existing["is_builtin"]:
            raise PermissionError("Preset sistem bawaan tidak dapat dihapus.")

        with topology_transaction(self.db_path, write=True) as conn:
            # If deleted persona was active, revert active to preset_technical
            pref_row = conn.execute("SELECT active_persona_id FROM user_preferences WHERE user_id = ?", (user_id,)).fetchone()
            if pref_row and pref_row["active_persona_id"] == persona_id:
                conn.execute(
                    "UPDATE user_preferences SET active_persona_id = 'preset_technical' WHERE user_id = ?",
                    (user_id,),
                )

            res = conn.execute(
                "DELETE FROM user_personas WHERE persona_id = ? AND user_id = ?",
                (persona_id, user_id),
            )
            return res.rowcount > 0

    def delete_all_custom_personas(self, user_id: str) -> int:
        """Deletes all custom personas owned by user (used by Privacy & Data)."""
        with topology_transaction(self.db_path, write=True) as conn:
            # Revert active persona to default
            conn.execute(
                "UPDATE user_preferences SET active_persona_id = 'preset_technical' WHERE user_id = ?",
                (user_id,),
            )
            res = conn.execute("DELETE FROM user_personas WHERE user_id = ?", (user_id,))
            return res.rowcount

    def preview_persona_prompt(self, persona: Dict[str, Any]) -> str:
        """Generates a text preview of how the persona shapes the AI system prompt."""
        lines = [
            f"=== PERSONA INSTRUCTION: {persona.get('name', 'AIRA Assistant')} ===",
            f"Response Style: {persona.get('response_style', 'concise')}",
            f"Language: {persona.get('language', 'id')}",
            f"Technical Depth: {persona.get('technical_depth', 80)}/100",
            f"Explanation Approach: {persona.get('explanation_preference', 'technical')}",
        ]
        if persona.get("custom_instructions"):
            lines.append(f"Custom Instructions: {persona['custom_instructions']}")
        return "\n".join(lines)


_persona_service: Optional[UserPersonaService] = None


def get_persona_service() -> UserPersonaService:
    global _persona_service
    if _persona_service is None:
        _persona_service = UserPersonaService()
    return _persona_service

