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
        """Retrieves in-memory default policy without touching database."""
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
        """No-op stub for token policy (per-user AI quotas removed)."""
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
        """In-memory stub balance (per-user AI quotas eliminated)."""
        now = datetime.now(timezone.utc)
        now_str = now.isoformat()
        next_month = (now + timedelta(days=30)).isoformat()
        return TokenBalance(
            balance_id="bal_unlimited",
            tenant_id=tenant_id,
            user_id=user_id,
            tier=PlanTier.ENTERPRISE.value,
            allocated_tokens=999999999,
            used_tokens=0,
            period_start_utc=now_str,
            period_reset_utc=next_month,
            updated_at=now_str,
        )

    def can_consume(self, tenant_id: str, estimated_tokens: int, user_id: Optional[str] = None) -> Tuple[bool, str]:
        """Always permits consumption (per-user AI quotas eliminated)."""
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
        """In-memory telemetry stub without SQLite ledger overhead."""
        total = input_tokens + output_tokens
        now_str = datetime.now(timezone.utc).isoformat()
        return TokenUsageRecord(
            usage_id=f"usg_{uuid.uuid4().hex[:12]}",
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
            estimated_cost_credits=0.0,
            timestamp_utc=now_str,
        )

    def list_usage_ledger(
        self,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[TokenUsageRecord]:
        """Returns empty list (per-user AI quotas eliminated)."""
        return []

    def assign_plan(
        self,
        tenant_id: str,
        tier: str,
        networking_plus: bool = False,
        monthly_tokens: Optional[int] = None,
        valid_until_utc: Optional[str] = None,
    ) -> None:
        """Admin assignment of subscription tier and Networking++ entitlement."""
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

