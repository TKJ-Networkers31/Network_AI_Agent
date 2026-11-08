"""
AIRA OS — Network Workspace Management Service (Phase F).
Ensures every Network++ subscriber operates within their own isolated network workspace:
user_id -> network_workspace_id -> networking_resources.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional
import uuid

from core.topology_db import DEFAULT_TOPOLOGY_DB_PATH, topology_transaction

logger = logging.getLogger("aira.workspace.service")


class WorkspaceService:
    """Manages isolated network workspaces for users with Network++ entitlement."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()

    def get_or_create_default_workspace(self, user_id: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieves the default network workspace for user, or idempotently provisions one.
        Guarantees every Network++ user has an active workspace scope.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        with topology_transaction(self.db_path, write=True) as conn:
            conn.row_factory = sqlite3.Row

            # 1. Check existing default workspace
            row = conn.execute(
                "SELECT * FROM network_workspaces WHERE user_id = ? AND is_default = 1",
                (user_id,),
            ).fetchone()

            if row:
                return dict(row)

            # Check if any workspace exists for user
            any_row = conn.execute(
                "SELECT * FROM network_workspaces WHERE user_id = ? ORDER BY created_at ASC LIMIT 1",
                (user_id,),
            ).fetchone()
            if any_row:
                return dict(any_row)

            # Resolve tenant_id if not supplied
            resolved_tenant = tenant_id
            if not resolved_tenant:
                u_row = conn.execute("SELECT tenant_id FROM operational_users WHERE user_id = ?", (user_id,)).fetchone()
                resolved_tenant = u_row["tenant_id"] if u_row and u_row["tenant_id"] else "tenant_default"

            # Ensure tenant exists in operational_tenants
            conn.execute(
                "INSERT OR IGNORE INTO operational_tenants (tenant_id, name, slug, status, config_json, created_at, updated_at) "
                "VALUES (?, ?, ?, 'ACTIVE', '{}', ?, ?)",
                (resolved_tenant, f"Tenant {resolved_tenant}", f"slug-{resolved_tenant[:8]}", now_iso, now_iso),
            )

            # Provision new default workspace
            ws_id = f"ws_{uuid.uuid4().hex[:12]}"
            name = "Default Network Workspace"
            conn.execute(
                """
                INSERT INTO network_workspaces
                (workspace_id, user_id, tenant_id, name, description, is_default, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'Primary operational network environment', 1, ?, ?)
                """,
                (ws_id, user_id, resolved_tenant, name, now_iso, now_iso),
            )

            return {
                "workspace_id": ws_id,
                "user_id": user_id,
                "tenant_id": resolved_tenant,
                "name": name,
                "description": "Primary operational network environment",
                "is_default": 1,
                "created_at": now_iso,
                "updated_at": now_iso,
            }

    def list_user_workspaces(self, user_id: str) -> List[Dict[str, Any]]:
        """Lists all workspaces owned by the user."""
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM network_workspaces WHERE user_id = ? ORDER BY is_default DESC, created_at ASC",
                (user_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_workspace(self, workspace_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves workspace verifying user ownership."""
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM network_workspaces WHERE workspace_id = ? AND user_id = ?",
                (workspace_id, user_id),
            ).fetchone()
            return dict(row) if row else None

    def create_workspace(self, user_id: str, name: str, description: str = "", tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Creates an additional isolated network workspace for user."""
        now_iso = datetime.now(timezone.utc).isoformat()
        ws_id = f"ws_{uuid.uuid4().hex[:12]}"

        with topology_transaction(self.db_path, write=True) as conn:
            conn.row_factory = sqlite3.Row
            resolved_tenant = tenant_id
            if not resolved_tenant:
                u_row = conn.execute("SELECT tenant_id FROM operational_users WHERE user_id = ?", (user_id,)).fetchone()
                resolved_tenant = u_row["tenant_id"] if u_row and u_row["tenant_id"] else "tenant_default"

            conn.execute(
                """
                INSERT INTO network_workspaces
                (workspace_id, user_id, tenant_id, name, description, is_default, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (ws_id, user_id, resolved_tenant, name.strip(), description.strip(), now_iso, now_iso),
            )

        return {
            "workspace_id": ws_id,
            "user_id": user_id,
            "tenant_id": resolved_tenant,
            "name": name.strip(),
            "description": description.strip(),
            "is_default": 0,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

    def delete_workspace(self, workspace_id: str, user_id: str) -> bool:
        """Deletes a network workspace if owned by user and not the default."""
        with topology_transaction(self.db_path, write=True) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT is_default FROM network_workspaces WHERE workspace_id = ? AND user_id = ?",
                (workspace_id, user_id),
            ).fetchone()
            if not row or row["is_default"] == 1:
                return False  # Cannot delete default workspace

            conn.execute(
                "DELETE FROM network_workspaces WHERE workspace_id = ? AND user_id = ?",
                (workspace_id, user_id),
            )
            return True
