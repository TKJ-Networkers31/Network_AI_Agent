"""
AIRA OS — Entitlements & Configurable Token Policy Engine.

Provides authoritative governance for:
- Product classifications: Free, Pro, Enterprise
- Specialized Networking++ entitlement (independent add-on)
- Admin-configurable token allocations, tool costs, and daily/monthly quotas
- Atomic token metering across input, output, and cached tokens
- Tenant feature authorization checks
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

from core.topology_db import DEFAULT_TOPOLOGY_DB_PATH, topology_transaction

logger = logging.getLogger("aira.tenant.entitlements")


class PlanTier(str, Enum):
    FREE = "FREE"
    PRO = "PRO"
    ENTERPRISE = "ENTERPRISE"
    CUSTOM = "CUSTOM"


class EntitlementKey(str, Enum):
    NETWORKING_PLUS = "networking_plus"
    ADVANCED_ARTIFACTS = "advanced_artifacts"
    SCHEDULED_AUTOMATIONS = "scheduled_automations"
    CUSTOM_MODELS = "custom_models"


# Default Token Policy Configurations (Admin-tunable)
DEFAULT_PLAN_LIMITS: Dict[str, Dict[str, Any]] = {
    PlanTier.FREE.value: {
        "monthly_tokens": 100_000,
        "daily_tokens": 10_000,
        "networking_plus": False,
        "rate_limit_rpm": 30,
        "max_request_size": 16_384,
    },
    PlanTier.PRO.value: {
        "monthly_tokens": 2_000_000,
        "daily_tokens": 200_000,
        "networking_plus": False,  # add-on by default, can be toggled
        "rate_limit_rpm": 120,
        "max_request_size": 65_536,
    },
    PlanTier.ENTERPRISE.value: {
        "monthly_tokens": 10_000_000,
        "daily_tokens": 1_000_000,
        "networking_plus": True,   # included in Enterprise
        "rate_limit_rpm": 300,
        "max_request_size": 131_072,
    },
}

# Standard Tool Token Costs (in credits/tokens)
DEFAULT_TOOL_COST_MATRIX: Dict[str, int] = {
    "device_ping": 5,
    "device_diagnostics": 50,
    "config_analysis": 100,
    "topology_discovery": 150,
    "config_push": 200,
    "document_generate": 100,
}


@dataclass
class TokenPolicy:
    policy_id: str
    scope_type: str = "GLOBAL"  # GLOBAL, TENANT, USER
    scope_id: Optional[str] = None
    tier: str = PlanTier.FREE.value
    monthly_token_allocation: int = 100_000
    daily_token_limit: int = 10_000
    networking_plus_enabled: bool = False
    model_cost_mult: Dict[str, float] = field(default_factory=dict)
    tool_cost_matrix: Dict[str, int] = field(default_factory=dict)
    max_request_size_tokens: int = 32_768
    rate_limit_rpm: int = 60
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "scope_type": self.scope_type,
            "scope_id": self.scope_id,
            "tier": self.tier,
            "monthly_token_allocation": self.monthly_token_allocation,
            "daily_token_limit": self.daily_token_limit,
            "networking_plus_enabled": self.networking_plus_enabled,
            "model_cost_mult": self.model_cost_mult,
            "tool_cost_matrix": self.tool_cost_matrix or DEFAULT_TOOL_COST_MATRIX,
            "max_request_size_tokens": self.max_request_size_tokens,
            "rate_limit_rpm": self.rate_limit_rpm,
            "updated_at": self.updated_at,
        }


@dataclass
class TokenBalance:
    balance_id: str
    tenant_id: str
    user_id: Optional[str]
    tier: str
    allocated_tokens: int
    used_tokens: int
    period_start_utc: str
    period_reset_utc: str
    updated_at: str

    @property
    def remaining_tokens(self) -> int:
        return max(0, self.allocated_tokens - self.used_tokens)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "balance_id": self.balance_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "tier": self.tier,
            "allocated_tokens": self.allocated_tokens,
            "used_tokens": self.used_tokens,
            "remaining_tokens": self.remaining_tokens,
            "period_start_utc": self.period_start_utc,
            "period_reset_utc": self.period_reset_utc,
            "updated_at": self.updated_at,
        }


@dataclass
class TokenUsageRecord:
    usage_id: str
    tenant_id: str
    user_id: Optional[str]
    session_id: Optional[str]
    model_name: Optional[str]
    feature_name: str
    tool_name: Optional[str]
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    total_tokens: int
    estimated_cost_credits: float
    timestamp_utc: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "usage_id": self.usage_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "model_name": self.model_name,
            "feature_name": self.feature_name,
            "tool_name": self.tool_name,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_tokens": self.cached_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost_credits": self.estimated_cost_credits,
            "timestamp_utc": self.timestamp_utc,
        }


class EntitlementManager:
    """Central authority for subscription tiers, entitlements, and atomic token metering."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()

    def get_policy(self, scope_type: str = "GLOBAL", scope_id: Optional[str] = None, tier: str = PlanTier.FREE.value) -> TokenPolicy:
        """Retrieves active policy matching scope, falling back to global defaults."""
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT * FROM operational_token_policies
                WHERE scope_type = ? AND (scope_id = ? OR (scope_id IS NULL AND ? IS NULL)) AND tier = ?
                """,
                (scope_type, scope_id, scope_id, tier),
            ).fetchone()

            if row:
                return TokenPolicy(
                    policy_id=row["policy_id"],
                    scope_type=row["scope_type"],
                    scope_id=row["scope_id"],
                    tier=row["tier"],
                    monthly_token_allocation=row["monthly_token_allocation"],
                    daily_token_limit=row["daily_token_limit"],
                    networking_plus_enabled=bool(row["networking_plus_enabled"]),
                    model_cost_mult=json.loads(row["model_cost_mult_json"] or "{}"),
                    tool_cost_matrix=json.loads(row["tool_cost_matrix_json"] or "{}"),
                    max_request_size_tokens=row["max_request_size_tokens"],
                    rate_limit_rpm=row["rate_limit_rpm"],
                    updated_at=row["updated_at"],
                )

        # Fallback to in-memory default template
        plan_def = DEFAULT_PLAN_LIMITS.get(tier, DEFAULT_PLAN_LIMITS[PlanTier.FREE.value])
        return TokenPolicy(
            policy_id=f"default_{tier.lower()}",
            scope_type="GLOBAL",
            scope_id=None,
            tier=tier,
            monthly_token_allocation=plan_def["monthly_tokens"],
            daily_token_limit=plan_def["daily_tokens"],
            networking_plus_enabled=plan_def["networking_plus"],
            model_cost_mult={},
            tool_cost_matrix=DEFAULT_TOOL_COST_MATRIX,
            max_request_size_tokens=plan_def["max_request_size"],
            rate_limit_rpm=plan_def["rate_limit_rpm"],
        )

    def set_policy(self, policy: TokenPolicy) -> TokenPolicy:
        """Saves or updates a token policy configuration."""
        now_str = datetime.now(timezone.utc).isoformat()
        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT INTO operational_token_policies (
                    policy_id, scope_type, scope_id, tier,
                    monthly_token_allocation, daily_token_limit, networking_plus_enabled,
                    model_cost_mult_json, tool_cost_matrix_json, max_request_size_tokens,
                    rate_limit_rpm, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope_type, scope_id, tier) DO UPDATE SET
                    monthly_token_allocation = excluded.monthly_token_allocation,
                    daily_token_limit = excluded.daily_token_limit,
                    networking_plus_enabled = excluded.networking_plus_enabled,
                    model_cost_mult_json = excluded.model_cost_mult_json,
                    tool_cost_matrix_json = excluded.tool_cost_matrix_json,
                    max_request_size_tokens = excluded.max_request_size_tokens,
                    rate_limit_rpm = excluded.rate_limit_rpm,
                    updated_at = excluded.updated_at
                """,
                (
                    policy.policy_id or f"pol_{uuid.uuid4().hex[:12]}",
                    policy.scope_type,
                    policy.scope_id,
                    policy.tier,
                    policy.monthly_token_allocation,
                    policy.daily_token_limit,
                    1 if policy.networking_plus_enabled else 0,
                    json.dumps(policy.model_cost_mult),
                    json.dumps(policy.tool_cost_matrix),
                    policy.max_request_size_tokens,
                    policy.rate_limit_rpm,
                    now_str,
                ),
            )
        policy.updated_at = now_str
        return policy

    def get_tenant_entitlements(self, tenant_id: str) -> Dict[str, bool]:
        """Returns map of active entitlements for the specified tenant."""
        if not tenant_id:
            return {}
        result: Dict[str, bool] = {}
        now_str = datetime.now(timezone.utc).isoformat()
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT entitlement_key, is_enabled, expires_at_utc
                FROM operational_tenant_entitlements
                WHERE tenant_id = ?
                """,
                (tenant_id,),
            ).fetchall()
            for r in rows:
                is_active = bool(r["is_enabled"])
                if is_active and r["expires_at_utc"] and r["expires_at_utc"] < now_str:
                    is_active = False
                result[r["entitlement_key"]] = is_active
        return result

    def set_tenant_entitlement(
        self,
        tenant_id: str,
        entitlement_key: str,
        is_enabled: bool = True,
        expires_at_utc: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Explicitly grants or revokes an entitlement (e.g. Networking++)."""
        now_str = datetime.now(timezone.utc).isoformat()
        ent_id = f"ent_{uuid.uuid4().hex[:12]}"
        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT INTO operational_tenant_entitlements (
                    entitlement_id, tenant_id, entitlement_key, is_enabled,
                    granted_at, expires_at_utc, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id, entitlement_key) DO UPDATE SET
                    is_enabled = excluded.is_enabled,
                    expires_at_utc = excluded.expires_at_utc,
                    metadata_json = excluded.metadata_json
                """,
                (
                    ent_id,
                    tenant_id,
                    entitlement_key,
                    1 if is_enabled else 0,
                    now_str,
                    expires_at_utc,
                    json.dumps(metadata or {}),
                ),
            )

    def has_networking_access(self, tenant_id: Optional[str]) -> bool:
        """
        Determines whether a tenant has Networking++ entitlement.
        Internal NOC / super-admins always have access.
        Customer tenants require Enterprise plan or explicit 'networking_plus' entitlement.
        """
        if not tenant_id:
            return True  # Internal unconstrained operation

        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            # Check subscription tier
            sub_row = conn.execute(
                "SELECT tier FROM operational_tenant_subscriptions WHERE tenant_id = ? AND is_active = 1",
                (tenant_id,),
            ).fetchone()
            if sub_row and sub_row["tier"] in (PlanTier.ENTERPRISE.value, PlanTier.CUSTOM.value):
                return True

        # Check explicit add-on
        ents = self.get_tenant_entitlements(tenant_id)
        return bool(ents.get(EntitlementKey.NETWORKING_PLUS.value, False))

    def get_or_create_balance(self, tenant_id: str, user_id: Optional[str] = None) -> TokenBalance:
        """Retrieves or resets user/tenant token balance, handling monthly rollover."""
        now = datetime.now(timezone.utc)
        now_str = now.isoformat()
        next_month = (now + timedelta(days=30)).isoformat()

        with topology_transaction(self.db_path, write=True) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT * FROM operational_token_balances
                WHERE tenant_id = ? AND (user_id = ? OR (user_id IS NULL AND ? IS NULL))
                """,
                (tenant_id, user_id, user_id),
            ).fetchone()

            if row:
                # Check for rollover
                if row["period_reset_utc"] < now_str:
                    # Reset period
                    conn.execute(
                        """
                        UPDATE operational_token_balances
                        SET used_tokens = 0,
                            period_start_utc = ?,
                            period_reset_utc = ?,
                            updated_at = ?
                        WHERE balance_id = ?
                        """,
                        (now_str, next_month, now_str, row["balance_id"]),
                    )
                    return TokenBalance(
                        balance_id=row["balance_id"],
                        tenant_id=tenant_id,
                        user_id=user_id,
                        tier=row["tier"],
                        allocated_tokens=row["allocated_tokens"],
                        used_tokens=0,
                        period_start_utc=now_str,
                        period_reset_utc=next_month,
                        updated_at=now_str,
                    )

                return TokenBalance(
                    balance_id=row["balance_id"],
                    tenant_id=tenant_id,
                    user_id=user_id,
                    tier=row["tier"],
                    allocated_tokens=row["allocated_tokens"],
                    used_tokens=row["used_tokens"],
                    period_start_utc=row["period_start_utc"],
                    period_reset_utc=row["period_reset_utc"],
                    updated_at=row["updated_at"],
                )

            # Resolve tier and default allocation
            sub_row = conn.execute(
                "SELECT tier FROM operational_tenant_subscriptions WHERE tenant_id = ? AND is_active = 1",
                (tenant_id,),
            ).fetchone()
            tier = sub_row["tier"] if sub_row else PlanTier.FREE.value
            policy = self.get_policy(scope_type="GLOBAL", tier=tier)
            alloc = policy.monthly_token_allocation

            balance_id = f"bal_{uuid.uuid4().hex[:12]}"
            conn.execute(
                """
                INSERT INTO operational_token_balances (
                    balance_id, tenant_id, user_id, tier,
                    allocated_tokens, used_tokens, period_start_utc, period_reset_utc, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (balance_id, tenant_id, user_id, tier, alloc, 0, now_str, next_month, now_str),
            )
            return TokenBalance(
                balance_id=balance_id,
                tenant_id=tenant_id,
                user_id=user_id,
                tier=tier,
                allocated_tokens=alloc,
                used_tokens=0,
                period_start_utc=now_str,
                period_reset_utc=next_month,
                updated_at=now_str,
            )

    def can_consume(self, tenant_id: str, estimated_tokens: int, user_id: Optional[str] = None) -> Tuple[bool, str]:
        """Checks whether the tenant or user has sufficient token budget remaining."""
        if not tenant_id:
            return True, "Internal operation"
        balance = self.get_or_create_balance(tenant_id, user_id)
        if balance.remaining_tokens < estimated_tokens:
            return False, f"Quota Exceeded: Requested {estimated_tokens} tokens exceeds remaining balance of {balance.remaining_tokens}."
        return True, "OK"

    def record_usage(
        self,
        tenant_id: str,
        user_id: Optional[str],
        session_id: Optional[str],
        model_name: Optional[str],
        feature_name: str,
        tool_name: Optional[str],
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
    ) -> TokenUsageRecord:
        """
        Atomically records token consumption to the ledger and updates remaining balance.
        Prevents concurrency bypass using SQLite transaction serialization.
        """
        total = input_tokens + output_tokens
        # Basic cost estimation credit: 1 credit per 1000 input tokens, 2 credits per 1000 output tokens
        cost_credits = round((input_tokens * 0.001) + (output_tokens * 0.002), 4)
        if tool_name and tool_name in DEFAULT_TOOL_COST_MATRIX:
            cost_credits += DEFAULT_TOOL_COST_MATRIX[tool_name]

        now_str = datetime.now(timezone.utc).isoformat()
        usage_id = f"usg_{uuid.uuid4().hex[:12]}"

        with topology_transaction(self.db_path, write=True) as conn:
            # 1. Append to immutable ledger
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
                    tenant_id or "internal",
                    user_id,
                    session_id,
                    model_name,
                    feature_name,
                    tool_name,
                    input_tokens,
                    output_tokens,
                    cached_tokens,
                    total,
                    cost_credits,
                    now_str,
                ),
            )

            # 2. Atomically update balance if tenant_id is valid
            if tenant_id:
                conn.execute(
                    """
                    UPDATE operational_token_balances
                    SET used_tokens = used_tokens + ?,
                        updated_at = ?
                    WHERE tenant_id = ? AND (user_id = ? OR (user_id IS NULL AND NOT EXISTS (SELECT 1 FROM operational_token_balances WHERE tenant_id = ? AND user_id = ?)))
                    """,
                    (total, now_str, tenant_id, user_id, tenant_id, user_id),
                )

        return TokenUsageRecord(
            usage_id=usage_id,
            tenant_id=tenant_id or "internal",
            user_id=user_id,
            session_id=session_id,
            model_name=model_name,
            feature_name=feature_name,
            tool_name=tool_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            total_tokens=total,
            estimated_cost_credits=cost_credits,
            timestamp_utc=now_str,
        )

    def list_usage_ledger(
        self,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[TokenUsageRecord]:
        """Lists recent token usage entries, optionally filtered by tenant or user."""
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            query = "SELECT * FROM operational_token_usage_ledger WHERE 1=1"
            params: List[Any] = []
            if tenant_id:
                query += " AND tenant_id = ?"
                params.append(tenant_id)
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            query += " ORDER BY timestamp_utc DESC LIMIT ?"
            params.append(min(limit, 500))

            rows = conn.execute(query, params).fetchall()
            return [
                TokenUsageRecord(
                    usage_id=r["usage_id"],
                    tenant_id=r["tenant_id"],
                    user_id=r["user_id"],
                    session_id=r["session_id"],
                    model_name=r["model_name"],
                    feature_name=r["feature_name"],
                    tool_name=r["tool_name"],
                    input_tokens=r["input_tokens"],
                    output_tokens=r["output_tokens"],
                    cached_tokens=r["cached_tokens"],
                    total_tokens=r["total_tokens"],
                    estimated_cost_credits=r["estimated_cost_credits"],
                    timestamp_utc=r["timestamp_utc"],
                )
                for r in rows
            ]

    def assign_plan(
        self,
        tenant_id: str,
        tier: str,
        networking_plus: bool = False,
        monthly_tokens: Optional[int] = None,
        valid_until_utc: Optional[str] = None,
    ) -> None:
        """Admin assignment of subscription tier, Networking++ entitlement, and token quota."""
        plan_limits = DEFAULT_PLAN_LIMITS.get(tier, DEFAULT_PLAN_LIMITS[PlanTier.FREE.value])
        alloc = monthly_tokens if monthly_tokens is not None else plan_limits["monthly_tokens"]
        now_str = datetime.now(timezone.utc).isoformat()
        next_month = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

        sub_tier = "ENTERPRISE" if tier == "ENTERPRISE" else "STANDARD" if tier in ("PRO", "STANDARD") else "COMMUNITY"
        with topology_transaction(self.db_path, write=True) as conn:
            # Update or insert subscription
            conn.execute(
                """
                UPDATE operational_tenant_subscriptions
                SET tier = ?, is_active = 1, valid_until_utc = ?
                WHERE tenant_id = ?
                """,
                (sub_tier, valid_until_utc, tenant_id),
            )

            # Update or reset token balance
            conn.execute(
                """
                INSERT INTO operational_token_balances (
                    balance_id, tenant_id, user_id, tier,
                    allocated_tokens, used_tokens, period_start_utc, period_reset_utc, updated_at
                ) VALUES (?, ?, NULL, ?, ?, 0, ?, ?, ?)
                ON CONFLICT(tenant_id, user_id) DO UPDATE SET
                    tier = excluded.tier,
                    allocated_tokens = excluded.allocated_tokens,
                    updated_at = excluded.updated_at
                """,
                (
                    f"bal_{uuid.uuid4().hex[:12]}",
                    tenant_id,
                    tier,
                    alloc,
                    now_str,
                    next_month,
                    now_str,
                ),
            )

        # Update Networking++ entitlement
        self.set_tenant_entitlement(
            tenant_id=tenant_id,
            entitlement_key=EntitlementKey.NETWORKING_PLUS.value,
            is_enabled=networking_plus or (tier in (PlanTier.ENTERPRISE.value, PlanTier.CUSTOM.value)),
            expires_at_utc=valid_until_utc,
        )

_GLOBAL_ENTITLEMENT_MANAGER = None

def get_entitlement_manager(db_path = None):
    global _GLOBAL_ENTITLEMENT_MANAGER
    if _GLOBAL_ENTITLEMENT_MANAGER is None or db_path is not None:
        _GLOBAL_ENTITLEMENT_MANAGER = EntitlementManager(db_path=db_path)
    return _GLOBAL_ENTITLEMENT_MANAGER

