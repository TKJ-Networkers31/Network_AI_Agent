"""
AIRA OS — User Subscription & Entitlement Lifecycle Service.

Manages user-specific subscriptions, multi-tier entitlements (Free, Pro, Enterprise, Networking++),
expiration enforcement, token allocations, and non-destructive downgrade policies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional
import uuid

from core.topology_db import DEFAULT_TOPOLOGY_DB_PATH, topology_transaction
from core.tenant.entitlements import PlanTier, DEFAULT_PLAN_LIMITS

logger = logging.getLogger("aira.tenant.user_subscription")


@dataclass
class UserSubscription:
    subscription_id: str
    user_id: str
    tenant_id: str
    plan_id: str
    subscription_status: str
    starts_at: str
    expires_at: Optional[str]
    renewal_status: str
    token_quota: int
    token_consumed: int
    networking_addon_status: int
    created_at: str
    updated_at: str

    @property
    def is_active(self) -> bool:
        if self.subscription_status != "ACTIVE":
            return False
        if not self.expires_at:
            return True
        try:
            exp = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            return exp > datetime.now(timezone.utc)
        except Exception:
            return True

    @property
    def has_networking_plus(self) -> bool:
        return self.is_active and bool(self.networking_addon_status)

    @property
    def remaining_tokens(self) -> int:
        return max(0, self.token_quota - self.token_consumed)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subscription_id": self.subscription_id,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "plan_id": self.plan_id,
            "subscription_status": self.subscription_status,
            "is_active": self.is_active,
            "has_networking_plus": self.has_networking_plus,
            "starts_at": self.starts_at,
            "expires_at": self.expires_at,
            "renewal_status": self.renewal_status,
            "token_quota": self.token_quota,
            "token_consumed": self.token_consumed,
            "remaining_tokens": self.remaining_tokens,
            "networking_addon_status": self.networking_addon_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class UserSubscriptionService:
    """Authoritative service for user subscription and lifecycle management."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()

    def get_subscription(self, user_id: str) -> Optional[UserSubscription]:
        """Retrieves active or latest subscription for a user."""
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT * FROM operational_user_subscriptions
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()

            if not row:
                return None

            return UserSubscription(
                subscription_id=row["subscription_id"],
                user_id=row["user_id"],
                tenant_id=row["tenant_id"],
                plan_id=row["plan_id"],
                subscription_status=row["subscription_status"],
                starts_at=row["starts_at"],
                expires_at=row["expires_at"],
                renewal_status=row["renewal_status"],
                token_quota=row["token_quota"],
                token_consumed=row["token_consumed"],
                networking_addon_status=row["networking_addon_status"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def get_user_subscription(self, user_id: str) -> Optional[UserSubscription]:
        """Alias for get_subscription."""
        return self.get_subscription(user_id)

    def ensure_user_subscription(self, user_id: str, tenant_id: str, default_tier: str = "FREE") -> UserSubscription:
        """Idempotently ensures user has an active base subscription."""
        sub = self.get_subscription(user_id)
        if sub:
            return sub

        now_iso = datetime.now(timezone.utc).isoformat()
        sub_id = f"sub_{uuid.uuid4().hex[:12]}"
        tier = default_tier.upper()
        quota = DEFAULT_PLAN_LIMITS.get(tier, {}).get("monthly_tokens", 10_000)
        has_netplus = 1 if tier == "ENTERPRISE" else 0

        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO operational_user_subscriptions
                (subscription_id, user_id, tenant_id, plan_id, subscription_status, starts_at, expires_at,
                 renewal_status, token_quota, token_consumed, networking_addon_status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'ACTIVE', ?, NULL, 'NONE', ?, 0, ?, ?, ?)
                """,
                (sub_id, user_id, tenant_id, tier, now_iso, quota, has_netplus, now_iso, now_iso),
            )

        return self.get_subscription(user_id)  # type: ignore

    def assign_subscription(
        self,
        user_id: str,
        plan_id: str,
        duration_days: Optional[int] = 30,
        networking_addon: bool = False,
        renewal_status: str = "MANUAL",
        operator_user: Optional[str] = None,
    ) -> UserSubscription:
        """Assigns or updates a user's subscription tier and entitlement."""
        plan_tier = plan_id.upper()
        if plan_tier not in ["FREE", "PRO", "ENTERPRISE", "CUSTOM"]:
            raise ValueError(f"Invalid plan tier: '{plan_tier}'. Must be FREE, PRO, ENTERPRISE, or CUSTOM.")

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        expires_at_iso = (now + timedelta(days=duration_days)).isoformat() if duration_days else None

        # Determine token quota
        quota = DEFAULT_PLAN_LIMITS.get(plan_tier, {}).get("monthly_tokens", 10_000)
        netplus_val = 1 if (networking_addon or plan_tier == "ENTERPRISE") else 0

        with topology_transaction(self.db_path, write=True) as conn:
            conn.row_factory = sqlite3.Row
            # Check tenant_id
            u_row = conn.execute("SELECT tenant_id, username FROM operational_users WHERE user_id = ?", (user_id,)).fetchone()
            if not u_row:
                raise ValueError(f"User '{user_id}' does not exist.")
            tenant_id = u_row["tenant_id"]

            sub_row = conn.execute("SELECT subscription_id FROM operational_user_subscriptions WHERE user_id = ?", (user_id,)).fetchone()
            if sub_row:
                sub_id = sub_row["subscription_id"]
                conn.execute(
                    """
                    UPDATE operational_user_subscriptions
                    SET plan_id = ?, subscription_status = 'ACTIVE', starts_at = ?, expires_at = ?,
                        renewal_status = ?, token_quota = ?, token_consumed = 0, networking_addon_status = ?,
                        updated_at = ?
                    WHERE user_id = ?
                    """,
                    (plan_tier, now_iso, expires_at_iso, renewal_status, quota, netplus_val, now_iso, user_id),
                )
            else:
                sub_id = f"sub_{uuid.uuid4().hex[:12]}"
                conn.execute(
                    """
                    INSERT INTO operational_user_subscriptions
                    (subscription_id, user_id, tenant_id, plan_id, subscription_status, starts_at, expires_at,
                     renewal_status, token_quota, token_consumed, networking_addon_status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?, 0, ?, ?, ?)
                    """,
                    (sub_id, user_id, tenant_id, plan_tier, now_iso, expires_at_iso, renewal_status, quota, netplus_val, now_iso, now_iso),
                )

            # Record audit log
            audit_id = f"aud_{uuid.uuid4().hex[:16]}"
            details = {
                "action": "ASSIGN_SUBSCRIPTION",
                "plan_id": plan_tier,
                "duration_days": duration_days,
                "networking_addon": bool(netplus_val),
                "operator": operator_user or "SYSTEM",
            }
            conn.execute(
                """
                INSERT INTO operational_audit_log
                (audit_id, tenant_id, user_id, username, action, resource_type, resource_id, details_json, ip_address, timestamp_utc)
                VALUES (?, ?, ?, ?, 'SUBSCRIPTION_UPDATE', 'USER_SUBSCRIPTION', ?, ?, '127.0.0.1', ?)
                """,
                (audit_id, tenant_id, user_id, u_row["username"], sub_id, json.dumps(details), now_iso),
            )

        updated_sub = self.get_subscription(user_id)
        if not updated_sub:
            raise RuntimeError(f"Failed to fetch updated subscription for user '{user_id}'")
        return updated_sub

    def toggle_networking_addon(self, user_id: str, enabled: bool, operator_user: Optional[str] = None) -> UserSubscription:
        """Toggles the independent Networking++ add-on for a user."""
        sub = self.get_subscription(user_id)
        if not sub:
            raise ValueError(f"No subscription found for user '{user_id}'.")

        val = 1 if enabled else 0
        now_iso = datetime.now(timezone.utc).isoformat()

        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                UPDATE operational_user_subscriptions
                SET networking_addon_status = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (val, now_iso, user_id),
            )

            audit_id = f"aud_{uuid.uuid4().hex[:16]}"
            details = {
                "action": "TOGGLE_NETWORKING_ADDON",
                "networking_addon": enabled,
                "operator": operator_user or "SYSTEM",
            }
            conn.execute(
                """
                INSERT INTO operational_audit_log
                (audit_id, tenant_id, user_id, username, action, resource_type, resource_id, details_json, ip_address, timestamp_utc)
                VALUES (?, ?, ?, 'system', 'NETWORKING_ADDON_TOGGLE', 'USER_SUBSCRIPTION', ?, ?, '127.0.0.1', ?)
                """,
                (audit_id, sub.tenant_id, user_id, sub.subscription_id, json.dumps(details), now_iso),
            )

        return self.get_subscription(user_id)  # type: ignore

    def check_and_expire_subscriptions(self) -> Dict[str, Any]:
        """
        Scans for expired subscriptions where expires_at < now.
        Downgrades to FREE plan and revokes Networking++ while PRESERVING ALL CUSTOMER DATA.
        Customer network devices, topology data, configs, and playbooks are strictly kept intact.
        """
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        expired_count = 0
        downgraded_users = []
        expired_users = []

        with topology_transaction(self.db_path, write=True) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT s.*, u.username
                FROM operational_user_subscriptions s
                JOIN operational_users u ON s.user_id = u.user_id
                WHERE s.subscription_status = 'ACTIVE'
                  AND s.expires_at IS NOT NULL
                  AND s.expires_at < ?
                """,
                (now_iso,),
            ).fetchall()

            for row in rows:
                sub_id = row["subscription_id"]
                user_id = row["user_id"]
                tenant_id = row["tenant_id"]
                old_plan = row["plan_id"]
                username = row["username"]

                # Downgrade to FREE plan defaults: 10,000 monthly tokens, networking addon removed
                free_quota = DEFAULT_PLAN_LIMITS["FREE"]["monthly_tokens"]

                conn.execute(
                    """
                    UPDATE operational_user_subscriptions
                    SET subscription_status = 'EXPIRED',
                        plan_id = 'FREE',
                        networking_addon_status = 0,
                        token_quota = ?,
                        updated_at = ?
                    WHERE subscription_id = ?
                    """,
                    (free_quota, now_iso, sub_id),
                )

                # Tamper-evident audit log
                audit_id = f"aud_{uuid.uuid4().hex[:16]}"
                details = {
                    "event": "AUTOMATIC_SUBSCRIPTION_EXPIRATION",
                    "previous_plan": old_plan,
                    "downgraded_to": "FREE",
                    "networking_addon_revoked": True,
                    "data_preserved": True,
                    "reason": "Subscription reached expiration timestamp.",
                }
                conn.execute(
                    """
                    INSERT INTO operational_audit_log
                    (audit_id, tenant_id, user_id, username, action, resource_type, resource_id, details_json, ip_address, timestamp_utc)
                    VALUES (?, ?, ?, ?, 'SUBSCRIPTION_EXPIRED', 'USER_SUBSCRIPTION', ?, ?, '127.0.0.1', ?)
                    """,
                    (audit_id, tenant_id, user_id, username, sub_id, json.dumps(details), now_iso),
                )

                expired_count += 1
                downgraded_users.append(username)
                expired_users.append(user_id)

        if expired_count > 0:
            logger.info("Checked subscriptions: %d expired and gracefully downgraded: %s", expired_count, downgraded_users)

        return {
            "timestamp": now_iso,
            "expired_count": expired_count,
            "downgraded_users": downgraded_users,
            "expired_users": expired_users,
        }

    def list_subscriptions(
        self,
        status: Optional[str] = None,
        plan_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Lists user subscriptions for platform admin overview."""
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            query = """
                SELECT s.*, u.username, u.email, t.name as tenant_name
                FROM operational_user_subscriptions s
                JOIN operational_users u ON s.user_id = u.user_id
                JOIN operational_tenants t ON s.tenant_id = t.tenant_id
                WHERE 1=1
            """
            params: List[Any] = []
            if status:
                query += " AND s.subscription_status = ?"
                params.append(status.upper())
            if plan_id:
                query += " AND s.plan_id = ?"
                params.append(plan_id.upper())

            query += " ORDER BY s.updated_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, tuple(params)).fetchall()
            return [dict(r) for r in rows]
