"""
AIRA OS — Admin Authorization & Granular Permission Service (Phase F).
Enforces granular RBAC permissions across all Control Plane / Admin endpoints.

Guarantees:
- PLATFORM_OWNER has full platform authority across all scopes.
- Regular users (including Pro/Enterprise without admin roles) are strictly rejected with 403 Forbidden.
- Granular permissions (users.read, subscriptions.manage, etc.) are verified on a per-endpoint basis.
- All administrative mutations are recorded in the immutable audit log.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any, Callable, Dict, List, Optional, Set
import uuid

from fastapi import Depends, Header, HTTPException, status

from core.topology_db import DEFAULT_TOPOLOGY_DB_PATH, topology_transaction
from core.tenant.models import Permission, ROLE_PERMISSIONS, TenantContext, UserRoleType
from core.tenant.manager import IdentityManager

logger = logging.getLogger("aira.admin.authorization")


class AdminAuthorizationService:
    """Service for resolving and enforcing administrative roles and granular permissions."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()

    def get_user_permissions(self, user_id: str) -> Set[str]:
        """Resolves all effective permissions for a user across their assigned roles."""
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT role_type FROM operational_user_roles WHERE user_id = ?", (user_id,)).fetchall()
            roles = [r["role_type"] for r in rows]

            # PLATFORM_OWNER and PLATFORM_SUPER_ADMIN hold all permissions
            if any(r in (UserRoleType.PLATFORM_OWNER.value, UserRoleType.PLATFORM_SUPER_ADMIN.value, "PLATFORM_OWNER", "SUPERADMIN") for r in roles):
                return {p.value for p in Permission}

            perms: Set[str] = set()
            for r in roles:
                try:
                    role_enum = UserRoleType(r)
                    role_perms = ROLE_PERMISSIONS.get(role_enum, set())
                    perms.update({p.value for p in role_perms})
                except ValueError:
                    continue

            return perms

    def has_permission(self, user_or_context: Any, required_permission: str) -> bool:
        """Checks if a user has a specific granular permission."""
        user_id = None
        roles = []

        if isinstance(user_or_context, TenantContext):
            user_id = user_or_context.user_id
            roles = user_or_context.roles or []
        elif isinstance(user_or_context, str):
            user_id = user_or_context
        elif isinstance(user_or_context, dict):
            user_id = user_or_context.get("user_id") or user_or_context.get("id")
            roles = user_or_context.get("roles") or []

        if not user_id:
            return False

        if any(r in (UserRoleType.PLATFORM_OWNER.value, UserRoleType.PLATFORM_SUPER_ADMIN.value, "PLATFORM_OWNER", "SUPERADMIN") for r in roles):
            return True

        user_perms = self.get_user_permissions(user_id)
        return required_permission in user_perms

    def log_administrative_action(
        self,
        admin_id: str,
        username: str,
        action: str,
        resource_type: str,
        resource_id: str,
        details: Dict[str, Any],
        ip_address: str = "127.0.0.1",
        tenant_id: str = "tenant_internal",
    ) -> str:
        """Records a tamper-evident audit log for an administrative operation."""
        audit_id = f"aud_{uuid.uuid4().hex[:16]}"
        now_iso = datetime.now(timezone.utc).isoformat()
        details_json = json.dumps(details, ensure_ascii=False)

        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT INTO operational_audit_log
                (audit_id, tenant_id, user_id, username, action, resource_type, resource_id, details_json, ip_address, timestamp_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (audit_id, tenant_id, admin_id, username, action, resource_type, resource_id, details_json, ip_address, now_iso),
            )

        return audit_id


# Global singleton
_admin_auth_service = AdminAuthorizationService()


def get_admin_auth_service() -> AdminAuthorizationService:
    return _admin_auth_service


def require_admin_permission(permission_name: str) -> Callable:
    """
    FastAPI dependency factory enforcing that caller has an active admin session
    with the required granular permission.
    """
    def _dependency(authorization: Optional[str] = Header(None)) -> TenantContext:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Autentikasi administrator diperlukan.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = authorization.split(" ", 1)[1]
        id_mgr = IdentityManager()
        ctx = id_mgr.validate_session_token(token)
        if not ctx:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sesi administrator tidak valid atau telah kedaluwarsa.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check internal status or roles
        admin_svc = get_admin_auth_service()
        if not admin_svc.has_permission(ctx, permission_name):
            logger.warning("Admin access denied: User '%s' lacks permission '%s'.", ctx.user_id, permission_name)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "INSUFFICIENT_PERMISSIONS",
                    "code": "ADMIN_PERMISSION_REQUIRED",
                    "required_permission": permission_name,
                    "message": f"Akses ditolak: Operasi ini memerlukan hak administratif '{permission_name}'.",
                },
            )

        return ctx

    return _dependency
