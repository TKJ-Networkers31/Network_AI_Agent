"""
AIRA OS — ChatGPT & Claude-Style Token Quota & Usage Accounting Engine.

Separates:
1. AI Model Tokens: Exact raw tokens consumed by LLM invocations (input, output, cached).
2. User Usage Quota: Granted periodic limits (Guest, Free, Pro, Enterprise).
3. Internal Credits: Operations costs for network diagnostics and tools.

Supports:
- Configurable reset periods: DAILY, WEEKLY, MONTHLY, CUSTOM_DAYS.
- Timezone support: Asia/Jakarta default (WIB, UTC+7).
- Reset types: CALENDAR-based (e.g. 1st of month at 00:00 WIB) and ANNIVERSARY-based.
- Atomic accounting and transaction serialization against SQLite WAL.
- Manual admin adjustments and bonus grants with mandatory audit logging.
- Guest quota management and restriction enforcement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
import json
import logging
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid
import zoneinfo

from core.topology_db import DEFAULT_TOPOLOGY_DB_PATH, topology_transaction
from core.tenant.entitlements import PlanTier, TokenUsageRecord, DEFAULT_TOOL_COST_MATRIX

logger = logging.getLogger("aira.tenant.quota")

DEFAULT_TIMEZONE = "Asia/Jakarta"


class QuotaResetPeriod(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    CUSTOM_DAYS = "CUSTOM_DAYS"


class QuotaResetType(str, Enum):
    CALENDAR = "CALENDAR"
    ANNIVERSARY = "ANNIVERSARY"


# Plan Default Quota Specifications
DEFAULT_QUOTA_SPECS: Dict[str, Dict[str, Any]] = {
    "GUEST": {
        "monthly_tokens": 15_000,
        "daily_tokens": 2_000,
        "reset_period": QuotaResetPeriod.DAILY.value,
        "reset_type": QuotaResetType.CALENDAR.value,
        "rate_limit_rpm": 20,
    },
    PlanTier.FREE.value: {
        "monthly_tokens": 100_000,
        "daily_tokens": 10_000,
        "reset_period": QuotaResetPeriod.MONTHLY.value,
        "reset_type": QuotaResetType.CALENDAR.value,
        "rate_limit_rpm": 30,
    },
    PlanTier.PRO.value: {
        "monthly_tokens": 2_000_000,
        "daily_tokens": 200_000,
        "reset_period": QuotaResetPeriod.MONTHLY.value,
        "reset_type": QuotaResetType.CALENDAR.value,
        "rate_limit_rpm": 120,
    },
    PlanTier.ENTERPRISE.value: {
        "monthly_tokens": 10_000_000,
        "daily_tokens": 1_000_000,
        "reset_period": QuotaResetPeriod.MONTHLY.value,
        "reset_type": QuotaResetType.CALENDAR.value,
        "rate_limit_rpm": 300,
    },
}


def compute_next_reset_utc(
    period: str = QuotaResetPeriod.MONTHLY.value,
    reset_type: str = QuotaResetType.CALENDAR.value,
    tz_name: str = DEFAULT_TIMEZONE,
    custom_days: int = 30,
    from_utc: Optional[datetime] = None,
) -> Tuple[datetime, datetime]:
    """
    Computes (period_start_utc, period_reset_utc) according to timezone and policy.
    For CALENDAR Monthly in Asia/Jakarta, next reset is the 1st of the next month at 00:00:00 WIB.
    """
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = zoneinfo.ZoneInfo("UTC")

    now_utc = from_utc or datetime.now(timezone.utc)
    local_now = now_utc.astimezone(tz)

    if period == QuotaResetPeriod.DAILY.value:
        # Start of today -> Start of tomorrow
        local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        local_reset = local_start + timedelta(days=1)
    elif period == QuotaResetPeriod.WEEKLY.value:
        # Start of Monday -> Next Monday
        local_start = (local_now - timedelta(days=local_now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        local_reset = local_start + timedelta(days=7)
    elif period == QuotaResetPeriod.MONTHLY.value and reset_type == QuotaResetType.CALENDAR.value:
        # 1st of current month -> 1st of next month
        local_start = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # Advance month
        year = local_now.year + (local_now.month // 12)
        month = (local_now.month % 12) + 1
        local_reset = local_now.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        # Anniversary or Custom days
        local_start = local_now
        local_reset = local_now + timedelta(days=custom_days)

    return local_start.astimezone(timezone.utc), local_reset.astimezone(timezone.utc)


@dataclass
class UserQuotaState:
    user_id: str
    tenant_id: str
    tier: str
    allocated_tokens: int
    used_tokens: int
    period_start_utc: str
    period_reset_utc: str
    reset_period: str
    reset_type: str
    timezone: str
    updated_at: str

    @property
    def remaining_tokens(self) -> int:
        return max(0, self.allocated_tokens - self.used_tokens)

    @property
    def usage_percentage(self) -> float:
        if self.allocated_tokens <= 0:
            return 100.0
        return min(100.0, round((self.used_tokens / self.allocated_tokens) * 100, 1))

    @property
    def next_reset_formatted(self) -> str:
        """Formatted in user-friendly Asia/Jakarta string (e.g. 1 Dec 2026, 00:00 WIB)."""
        try:
            exp_utc = datetime.fromisoformat(self.period_reset_utc.replace("Z", "+00:00"))
            tz = zoneinfo.ZoneInfo(self.timezone or DEFAULT_TIMEZONE)
            local_dt = exp_utc.astimezone(tz)
            # Format: '1 Dec 2026, 00:00 WIB'
            return local_dt.strftime("%d %b %Y, %H:%M WIB")
        except Exception:
            return self.period_reset_utc

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "tier": self.tier,
            "allocated_tokens": self.allocated_tokens,
            "used_tokens": self.used_tokens,
            "remaining_tokens": self.remaining_tokens,
            "usage_percentage": self.usage_percentage,
            "period_start_utc": self.period_start_utc,
            "period_reset_utc": self.period_reset_utc,
            "next_reset_formatted": self.next_reset_formatted,
            "reset_period": self.reset_period,
            "reset_type": self.reset_type,
            "timezone": self.timezone,
            "updated_at": self.updated_at,
        }


class TokenQuotaService:
    """Authoritative service for ChatGPT/Claude-style token quota and reset governance."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()

    def get_or_create_user_quota(self, user_id: str, tenant_id: str, tier: str = "FREE") -> UserQuotaState:
        """Retrieves or resets user token quota, handling automatic reset rollover."""
        now_utc = datetime.now(timezone.utc)
        now_str = now_utc.isoformat()

        with topology_transaction(self.db_path, write=True) as conn:
            conn.row_factory = sqlite3.Row
            # Ensure tenant exists in operational_tenants to satisfy foreign key constraint
            conn.execute(
                """
                INSERT OR IGNORE INTO operational_tenants (tenant_id, name, slug, status, created_at, updated_at)
                VALUES (?, ?, ?, 'ACTIVE', ?, ?)
                """,
                (tenant_id, tenant_id, f"slug-{tenant_id}", now_str, now_str),
            )

            row = conn.execute(
                """
                SELECT * FROM operational_token_balances
                WHERE tenant_id = ? AND user_id = ?
                """,
                (tenant_id, user_id),
            ).fetchone()

            # Load policy configuration for this tier
            plan_tier = tier.upper()
            pol_row = conn.execute(
                "SELECT * FROM operational_token_policies WHERE scope_type = 'GLOBAL' AND tier = ?",
                (plan_tier,),
            ).fetchone()

            reset_period = pol_row["reset_period"] if pol_row and "reset_period" in pol_row.keys() else "MONTHLY"
            reset_type = pol_row["reset_type"] if pol_row and "reset_type" in pol_row.keys() else "CALENDAR"
            tz_name = pol_row["reset_timezone"] if pol_row and "reset_timezone" in pol_row.keys() else DEFAULT_TIMEZONE
            default_alloc = pol_row["monthly_token_allocation"] if pol_row else DEFAULT_QUOTA_SPECS.get(plan_tier, {}).get("monthly_tokens", 100_000)

            if row:
                # Check for automatic reset period expiration
                if row["period_reset_utc"] <= now_str:
                    st_dt, res_dt = compute_next_reset_utc(period=reset_period, reset_type=reset_type, tz_name=tz_name)
                    st_str = st_dt.isoformat()
                    res_str = res_dt.isoformat()

                    conn.execute(
                        """
                        UPDATE operational_token_balances
                        SET used_tokens = 0,
                            period_start_utc = ?,
                            period_reset_utc = ?,
                            updated_at = ?
                        WHERE balance_id = ?
                        """,
                        (st_str, res_str, now_str, row["balance_id"]),
                    )

                    # Also update operational_user_subscriptions token_consumed
                    conn.execute(
                        "UPDATE operational_user_subscriptions SET token_consumed = 0, updated_at = ? WHERE user_id = ?",
                        (now_str, user_id),
                    )

                    logger.info("Automatic quota rollover applied for user %s: used_tokens reset to 0", user_id)

                    return UserQuotaState(
                        user_id=user_id,
                        tenant_id=tenant_id,
                        tier=row["tier"],
                        allocated_tokens=row["allocated_tokens"],
                        used_tokens=0,
                        period_start_utc=st_str,
                        period_reset_utc=res_str,
                        reset_period=reset_period,
                        reset_type=reset_type,
                        timezone=tz_name,
                        updated_at=now_str,
                    )

                return UserQuotaState(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    tier=row["tier"],
                    allocated_tokens=row["allocated_tokens"],
                    used_tokens=row["used_tokens"],
                    period_start_utc=row["period_start_utc"],
                    period_reset_utc=row["period_reset_utc"],
                    reset_period=reset_period,
                    reset_type=reset_type,
                    timezone=tz_name,
                    updated_at=row["updated_at"],
                )

            # Insert initial quota state
            st_dt, res_dt = compute_next_reset_utc(period=reset_period, reset_type=reset_type, tz_name=tz_name)
            balance_id = f"bal_{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO operational_token_balances
                (balance_id, tenant_id, user_id, tier, allocated_tokens, used_tokens, period_start_utc, period_reset_utc, updated_at)
                VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (balance_id, tenant_id, user_id, plan_tier, default_alloc, st_dt.isoformat(), res_dt.isoformat(), now_str),
            )

            return UserQuotaState(
                user_id=user_id,
                tenant_id=tenant_id,
                tier=plan_tier,
                allocated_tokens=default_alloc,
                used_tokens=0,
                period_start_utc=st_dt.isoformat(),
                period_reset_utc=res_dt.isoformat(),
                reset_period=reset_period,
                reset_type=reset_type,
                timezone=tz_name,
                updated_at=now_str,
            )

    def get_guest_quota(self, guest_id: str) -> UserQuotaState:
        """Retrieves or creates isolated token quota for an unauthenticated Guest user."""
        return self.get_or_create_user_quota(user_id=guest_id, tenant_id="tenant_guest", tier="GUEST")

    def check_quota_available(
        self,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        estimated_tokens: int = 100,
        is_guest: bool = False,
        guest_id: Optional[str] = None,
    ) -> Tuple[bool, str, int]:
        """
        Pre-flight check: Verifies if user or guest has sufficient tokens before initiating AI generation.
        Returns: (has_quota: bool, message: str, remaining_tokens: int)
        """
        if is_guest or not user_id:
            gid = guest_id or "guest_anonymous"
            quota = self.get_guest_quota(gid)
            if quota.remaining_tokens < estimated_tokens:
                return (
                    False,
                    "Guest quota limit reached. Please sign in or create a free account to continue using AIRA Workspace.",
                    quota.remaining_tokens,
                )
            return True, "OK", quota.remaining_tokens

        t_id = tenant_id or "tenant_default"
        quota = self.get_or_create_user_quota(user_id=user_id, tenant_id=t_id)
        if quota.remaining_tokens < estimated_tokens:
            return (
                False,
                f"Monthly token quota exceeded. Remaining: {quota.remaining_tokens:,} tokens. Resets on {quota.next_reset_formatted}.",
                quota.remaining_tokens,
            )
        return True, "OK", quota.remaining_tokens

    def consume_tokens(
        self,
        user_id: Optional[str],
        tenant_id: Optional[str],
        session_id: Optional[str],
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
        feature_name: str = "chat",
        tool_name: Optional[str] = None,
        is_guest: bool = False,
        guest_id: Optional[str] = None,
    ) -> TokenUsageRecord:
        """
        Atomically records actual model token consumption into ledger and increments used_tokens.
        """
        target_uid = guest_id if (is_guest or not user_id) else user_id
        target_tid = "tenant_guest" if (is_guest or not user_id) else (tenant_id or "tenant_default")

        total_tokens = input_tokens + output_tokens
        # Cost credit calculation: 1 credit per 1000 input, 2 credits per 1000 output + tool costs
        cost_credits = round((input_tokens * 0.001) + (output_tokens * 0.002), 4)
        if tool_name and tool_name in DEFAULT_TOOL_COST_MATRIX:
            cost_credits += DEFAULT_TOOL_COST_MATRIX[tool_name]

        now_str = datetime.now(timezone.utc).isoformat()
        usage_id = f"usg_{uuid.uuid4().hex[:12]}"

        # Ensure user/guest quota state exists prior to consumption
        self.get_or_create_user_quota(
            user_id=target_uid,
            tenant_id=target_tid,
            tier="GUEST" if (is_guest or not user_id) else "FREE",
        )

        with topology_transaction(self.db_path, write=True) as conn:
            # 1. Append immutable ledger
            conn.execute(
                """
                INSERT INTO operational_token_usage_ledger (
                    usage_id, tenant_id, user_id, session_id, model_name,
                    feature_name, tool_name, input_tokens, output_tokens,
                    cached_tokens, total_tokens, estimated_cost_credits, timestamp_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    usage_id,
                    target_tid,
                    target_uid,
                    session_id,
                    model_name,
                    feature_name,
                    tool_name,
                    input_tokens,
                    output_tokens,
                    cached_tokens,
                    total_tokens,
                    cost_credits,
                    now_str,
                ),
            )

            # 2. Increment used_tokens atomically
            conn.execute(
                """
                UPDATE operational_token_balances
                SET used_tokens = used_tokens + ?, updated_at = ?
                WHERE tenant_id = ? AND user_id = ?
                """,
                (total_tokens, now_str, target_tid, target_uid),
            )

            # 3. If registered user, also sync operational_user_subscriptions
            if not is_guest and user_id:
                conn.execute(
                    """
                    UPDATE operational_user_subscriptions
                    SET token_consumed = token_consumed + ?, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (total_tokens, now_str, user_id),
                )

        return TokenUsageRecord(
            usage_id=usage_id,
            tenant_id=target_tid,
            user_id=target_uid,
            session_id=session_id,
            model_name=model_name,
            feature_name=feature_name,
            tool_name=tool_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            total_tokens=total_tokens,
            estimated_cost_credits=cost_credits,
            timestamp_utc=now_str,
        )

    def adjust_user_quota(
        self,
        admin_user_id: str,
        target_user_id: str,
        new_quota: int,
        reason: str,
        adjustment_type: str = "MANUAL",
    ) -> Dict[str, Any]:
        """Manually adjusts user token quota with mandatory audit trail."""
        if not reason or not reason.strip():
            raise ValueError("Justification reason is mandatory for manual token quota adjustments.")

        now_str = datetime.now(timezone.utc).isoformat()
        adj_id = f"qadj_{uuid.uuid4().hex[:12]}"

        with topology_transaction(self.db_path, write=True) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT balance_id, allocated_tokens FROM operational_token_balances WHERE user_id = ?",
                (target_user_id,),
            ).fetchone()

            prev_quota = row["allocated_tokens"] if row else 0

            # Update or create balance
            if row:
                conn.execute(
                    "UPDATE operational_token_balances SET allocated_tokens = ?, updated_at = ? WHERE user_id = ?",
                    (new_quota, now_str, target_user_id),
                )
            else:
                st_dt, res_dt = compute_next_reset_utc()
                conn.execute(
                    """
                    INSERT INTO operational_token_balances
                    (balance_id, tenant_id, user_id, tier, allocated_tokens, used_tokens, period_start_utc, period_reset_utc, updated_at)
                    VALUES (?, 'tenant_default', ?, 'CUSTOM', ?, 0, ?, ?, ?)
                    """,
                    (f"bal_{uuid.uuid4().hex[:12]}", target_user_id, new_quota, st_dt.isoformat(), res_dt.isoformat(), now_str),
                )

            # Update operational_user_subscriptions if exists
            conn.execute(
                "UPDATE operational_user_subscriptions SET token_quota = ?, updated_at = ? WHERE user_id = ?",
                (new_quota, now_str, target_user_id),
            )

            # Insert immutable adjustment record
            conn.execute(
                """
                INSERT INTO operational_token_quota_adjustments
                (adjustment_id, admin_id, target_user_id, previous_quota, new_quota, adjustment_type, reason, timestamp_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (adj_id, admin_user_id, target_user_id, prev_quota, new_quota, adjustment_type, reason.strip(), now_str),
            )

        return {
            "adjustment_id": adj_id,
            "target_user_id": target_user_id,
            "previous_quota": prev_quota,
            "new_quota": new_quota,
            "adjustment_type": adjustment_type,
            "reason": reason.strip(),
            "timestamp": now_str,
        }

    def reset_user_quota(self, admin_user_id: str, target_user_id: str, reason: str = "Admin reset") -> Dict[str, Any]:
        """Manually resets a user's consumed tokens to 0."""
        now_str = datetime.now(timezone.utc).isoformat()
        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                "UPDATE operational_token_balances SET used_tokens = 0, updated_at = ? WHERE user_id = ?",
                (now_str, target_user_id),
            )
            conn.execute(
                "UPDATE operational_user_subscriptions SET token_consumed = 0, updated_at = ? WHERE user_id = ?",
                (now_str, target_user_id),
            )

            adj_id = f"qadj_{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO operational_token_quota_adjustments
                (adjustment_id, admin_id, target_user_id, previous_quota, new_quota, adjustment_type, reason, timestamp_utc)
                VALUES (?, ?, ?, 0, 0, 'RESET', ?, ?)
                """,
                (adj_id, admin_user_id, target_user_id, reason, now_str),
            )

        return {"success": True, "target_user_id": target_user_id, "used_tokens": 0, "reset_at": now_str}

    def sweep_due_quotas(self) -> Dict[str, Any]:
        """
        Background worker sweep: Resets used_tokens for all balances whose period_reset_utc has elapsed.
        Preserves complete historical ledger in operational_token_usage_ledger.
        """
        now_utc = datetime.now(timezone.utc)
        now_str = now_utc.isoformat()
        reset_count = 0
        reset_users = []

        with topology_transaction(self.db_path, write=True) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM operational_token_balances
                WHERE period_reset_utc <= ?
                """,
                (now_str,),
            ).fetchall()

            for r in rows:
                bal_id = r["balance_id"]
                u_id = r["user_id"]
                tier = r["tier"]

                # Calculate next reset
                st_dt, res_dt = compute_next_reset_utc()
                conn.execute(
                    """
                    UPDATE operational_token_balances
                    SET used_tokens = 0,
                        period_start_utc = ?,
                        period_reset_utc = ?,
                        updated_at = ?
                    WHERE balance_id = ?
                    """,
                    (st_dt.isoformat(), res_dt.isoformat(), now_str, bal_id),
                )

                if u_id:
                    conn.execute(
                        "UPDATE operational_user_subscriptions SET token_consumed = 0, updated_at = ? WHERE user_id = ?",
                        (now_str, u_id),
                    )
                    reset_users.append(u_id)

                reset_count += 1

        if reset_count > 0:
            logger.info("Executed periodic quota reset sweep: %d balances reset (%s)", reset_count, reset_users)

        return {
            "timestamp": now_str,
            "reset_count": reset_count,
            "reset_users": reset_users,
        }

    def list_quota_adjustments(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Lists historical manual quota adjustments for platform audit."""
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT a.*, u.username as target_username
                FROM operational_token_quota_adjustments a
                LEFT JOIN operational_users u ON a.target_user_id = u.user_id
                ORDER BY a.timestamp_utc DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def list_plan_policies(self) -> List[Dict[str, Any]]:
        """Lists global token quota policies across all tiers."""
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM operational_token_policies WHERE scope_type = 'GLOBAL' ORDER BY monthly_token_allocation ASC"
            ).fetchall()
            return [dict(r) for r in rows]

    def update_plan_policy(
        self,
        tier: str,
        monthly_token_allocation: int,
        daily_token_allocation: int,
        reset_period: str = "MONTHLY",
        reset_type: str = "CALENDAR",
        reset_timezone: str = "Asia/Jakarta",
        rate_limit_rpm: int = 60,
    ) -> Dict[str, Any]:
        """Updates or inserts plan token allocation policy."""
        now_str = datetime.now(timezone.utc).isoformat()
        tier_upper = tier.upper()
        policy_id = f"pol_global_{tier_upper.lower()}"

        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT INTO operational_token_policies (
                    policy_id, scope_type, scope_id, tier,
                    monthly_token_allocation, daily_token_limit, networking_plus_enabled,
                    model_cost_multiplier_json, tool_cost_matrix_json, max_request_size_tokens,
                    rate_limit_rpm, reset_period, reset_type, reset_timezone,
                    created_at, updated_at
                ) VALUES (?, 'GLOBAL', 'system', ?, ?, ?, 0, '{}', '{}', 32768, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(policy_id) DO UPDATE SET
                    monthly_token_allocation = excluded.monthly_token_allocation,
                    daily_token_limit = excluded.daily_token_limit,
                    rate_limit_rpm = excluded.rate_limit_rpm,
                    reset_period = excluded.reset_period,
                    reset_type = excluded.reset_type,
                    reset_timezone = excluded.reset_timezone,
                    updated_at = excluded.updated_at
                """,
                (
                    policy_id,
                    tier_upper,
                    monthly_token_allocation,
                    daily_token_allocation,
                    rate_limit_rpm,
                    reset_period,
                    reset_type,
                    reset_timezone,
                    now_str,
                    now_str,
                ),
            )

        return {
            "success": True,
            "tier": tier_upper,
            "monthly_token_allocation": monthly_token_allocation,
            "daily_token_allocation": daily_token_allocation,
            "reset_period": reset_period,
            "reset_type": reset_type,
            "reset_timezone": reset_timezone,
            "rate_limit_rpm": rate_limit_rpm,
            "updated_at": now_str,
        }

