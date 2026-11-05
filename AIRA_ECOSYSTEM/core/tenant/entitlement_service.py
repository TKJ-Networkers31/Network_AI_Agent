"""
AIRA OS — Centralized Entitlement Resolver & Gating Service (Phase F).
Authoritative resolver for feature entitlements across AIRA OS.

Primary invariant:
- All networking capabilities require the 'NETWORK_PLUS' entitlement.
- PLATFORM_OWNER holds all platform entitlements unconditionally.
- Feature gating returns HTTP 403 ENTITLEMENT_REQUIRED without leaking resource data.
"""

from __future__ import annotations

import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, Optional, Union

from fastapi import Depends, Header, HTTPException, status

from core.topology_db import DEFAULT_TOPOLOGY_DB_PATH, topology_transaction
from core.tenant.models import TenantContext, UserRoleType
from core.tenant.manager import IdentityManager
from core.tenant.user_subscription import UserSubscriptionService

logger = logging.getLogger("aira.entitlements.service")


class EntitlementService:
    """Centralized authoritative service for evaluating and enforcing user entitlements."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()
        self._sub_svc = UserSubscriptionService(self.db_path)
        self._id_mgr = IdentityManager(self.db_path)

    def has_entitlement(self, user_or_context: Union[TenantContext, str, dict, Any], entitlement_key: str) -> bool:
        """
        Authoritative check whether a user or context holds a specific entitlement.
        Normalized key: 'NETWORK_PLUS' or 'networking_plus'.
        """
        norm_key = entitlement_key.strip().upper().replace(" ", "_")
        if norm_key in ("NETWORKING_PLUS", "NETWORK_PLUS", "NETWORK++", "NETWORKING++"):
            target_key = "NETWORK_PLUS"
        else:
            target_key = norm_key

        # Resolve user_id, tenant_id, roles
        user_id = None
        roles = set()
        tenant_id = None

        if isinstance(user_or_context, TenantContext):
            user_id = user_or_context.user_id
            tenant_id = user_or_context.tenant_id
            roles = set(user_or_context.roles or [])
        elif isinstance(user_or_context, str):
            user_id = user_or_context
        elif isinstance(user_or_context, dict):
            user_id = user_or_context.get("user_id") or user_or_context.get("id")
            tenant_id = user_or_context.get("tenant_id")
            roles = set(user_or_context.get("roles") or [])

        if not user_id:
            return False

        # 1. PLATFORM_OWNER has unconditional access to all platform features
        if UserRoleType.PLATFORM_OWNER.value in roles or "PLATFORM_OWNER" in roles:
            return True

        # Fetch user details from DB if roles not loaded
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            u_row = conn.execute("SELECT * FROM operational_users WHERE user_id = ?", (user_id,)).fetchone()
            if not u_row or not u_row["is_active"]:
                return False

            if not tenant_id:
                tenant_id = u_row["tenant_id"]

            # Check DB roles if not already evaluated
            r_rows = conn.execute("SELECT role_type FROM operational_user_roles WHERE user_id = ?", (user_id,)).fetchall()
            db_roles = {r["role_type"] for r in r_rows}
            if UserRoleType.PLATFORM_OWNER.value in db_roles:
                return True

            # 2. Check User Subscription & Entitlements
            if target_key == "NETWORK_PLUS":
                sub_row = conn.execute(
                    "SELECT plan_id, subscription_status, networking_addon_status FROM operational_user_subscriptions WHERE user_id = ?",
                    (user_id,),
                ).fetchone()

                if sub_row:
                    if sub_row["subscription_status"] == "ACTIVE":
                        if sub_row["networking_addon_status"] == 1 or sub_row["plan_id"] == "ENTERPRISE":
                            return True

                # Check organization-level entitlement
                if tenant_id:
                    ent_row = conn.execute(
                        "SELECT is_enabled FROM operational_tenant_entitlements WHERE tenant_id = ? AND entitlement_key = 'networking_plus'",
                        (tenant_id,),
                    ).fetchone()
                    if ent_row and ent_row["is_enabled"] == 1:
                        return True

        return False

    def get_user_entitlements(self, user_id: str) -> Dict[str, bool]:
        """Returns map of active entitlements for user."""
        return {
            "NETWORK_PLUS": self.has_entitlement(user_id, "NETWORK_PLUS"),
        }


# Global singleton
_entitlement_service = EntitlementService()


def get_entitlement_service() -> EntitlementService:
    return _entitlement_service


def require_network_plus(
    authorization: Optional[str] = Header(None),
) -> TenantContext:
    """
    FastAPI dependency that enforces authenticated session and NETWORK_PLUS entitlement.
    Returns 403 ENTITLEMENT_REQUIRED without leaking any internal resource data.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autentikasi diperlukan. Silakan login terlebih dahulu.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.split(" ", 1)[1]
    ent_svc = get_entitlement_service()
    id_mgr = IdentityManager(db_path=ent_svc.db_path)
    ctx = id_mgr.validate_session_token(token)
    if not ctx:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesi tidak valid atau telah kedaluwarsa.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    ent_svc = get_entitlement_service()
    if not ent_svc.has_entitlement(ctx, "NETWORK_PLUS"):
        logger.warning("Access denied: User '%s' lacks NETWORK_PLUS entitlement.", ctx.user_id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "ENTITLEMENT_REQUIRED",
                "code": "ENTITLEMENT_REQUIRED",
                "required_entitlement": "NETWORK_PLUS",
                "message": "Fitur jaringan memerlukan paket langganan dengan entitlement Network++. Silakan upgrade akun Anda.",
            },
        )

    return ctx
