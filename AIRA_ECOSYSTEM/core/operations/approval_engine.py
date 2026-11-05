"""
AIRA OS — Centralized Approval & Confirmation Engine.

Governs Category A (Automatic), Category B (Confirmation Required), and Category C (Restricted) operations.
Enforces tenant and user confirmation preferences, impact assessments, risk disclosures,
and approval queues.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
import uuid

from core.topology_db import DEFAULT_TOPOLOGY_DB_PATH, topology_transaction

logger = logging.getLogger("aira.operations.approval")


class AutonomyRiskCategory(str, Enum):
    CATEGORY_A = "CATEGORY_A"  # Automatic (read-only, diagnostic, non-destructive)
    CATEGORY_B = "CATEGORY_B"  # Confirmation required (mutating config, reboot, firewall, credentials)
    CATEGORY_C = "CATEGORY_C"  # Restricted (cross-tenant, unauthorized scopes, prohibited actions)


class ApprovalPolicyMode(str, Enum):
    ALWAYS_ASK = "ALWAYS_ASK"
    ASK_HIGH_RISK = "ASK_HIGH_RISK"
    AUTO_APPROVE_LOW_RISK = "AUTO_APPROVE_LOW_RISK"
    CUSTOM = "CUSTOM"


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass
class ApprovalPreferences:
    pref_id: str
    tenant_id: str
    user_id: Optional[str]
    policy_mode: str = ApprovalPolicyMode.ASK_HIGH_RISK.value
    require_config_deploy_approval: bool = True
    require_credential_change_approval: bool = True
    require_user_change_approval: bool = True
    never_auto_approve_destructive: bool = True
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pref_id": self.pref_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "policy_mode": self.policy_mode,
            "require_config_deploy_approval": self.require_config_deploy_approval,
            "require_credential_change_approval": self.require_credential_change_approval,
            "require_user_change_approval": self.require_user_change_approval,
            "never_auto_approve_destructive": self.never_auto_approve_destructive,
            "updated_at": self.updated_at,
        }


@dataclass
class PendingApproval:
    approval_id: str
    tenant_id: str
    requester_id: str
    requester_name: str
    action_name: str
    risk_level: str
    target_resources: List[str]
    params: Dict[str, Any]
    diff_text: Optional[str]
    reason: str
    status: str = ApprovalStatus.PENDING.value
    reviewer_id: Optional[str] = None
    review_notes: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "tenant_id": self.tenant_id,
            "requester_id": self.requester_id,
            "requester_name": self.requester_name,
            "action_name": self.action_name,
            "risk_level": self.risk_level,
            "target_resources": self.target_resources,
            "params": self.params,
            "diff_text": self.diff_text,
            "reason": self.reason,
            "status": self.status,
            "reviewer_id": self.reviewer_id,
            "review_notes": self.review_notes,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
        }


class CentralizedApprovalEngine:
    """Evaluates operations against confirmation policies and manages pending approvals."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()

    def get_preferences(self, tenant_id: str, user_id: Optional[str] = None) -> ApprovalPreferences:
        """Retrieves confirmation preferences for user/tenant, falling back to secure defaults."""
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT * FROM operational_approval_preferences
                WHERE tenant_id = ? AND (user_id = ? OR (user_id IS NULL AND ? IS NULL))
                """,
                (tenant_id, user_id, user_id),
            ).fetchone()

            if row:
                return ApprovalPreferences(
                    pref_id=row["pref_id"],
                    tenant_id=row["tenant_id"],
                    user_id=row["user_id"],
                    policy_mode=row["policy_mode"],
                    require_config_deploy_approval=bool(row["require_config_deploy_approval"]),
                    require_credential_change_approval=bool(row["require_credential_change_approval"]),
                    require_user_change_approval=bool(row["require_user_change_approval"]),
                    never_auto_approve_destructive=bool(row["never_auto_approve_destructive"]),
                    updated_at=row["updated_at"],
                )

        # Default policy: Ask for high risk, protect configuration and credentials
        return ApprovalPreferences(
            pref_id=f"pref_{tenant_id}",
            tenant_id=tenant_id,
            user_id=user_id,
            policy_mode=ApprovalPolicyMode.ASK_HIGH_RISK.value,
            require_config_deploy_approval=True,
            require_credential_change_approval=True,
            require_user_change_approval=True,
            never_auto_approve_destructive=True,
        )

    def set_preferences(self, prefs: ApprovalPreferences) -> ApprovalPreferences:
        """Saves user or organization-level approval preferences."""
        now_str = datetime.now(timezone.utc).isoformat()
        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT INTO operational_approval_preferences (
                    pref_id, tenant_id, user_id, policy_mode,
                    require_config_deploy_approval, require_credential_change_approval,
                    require_user_change_approval, never_auto_approve_destructive, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id, user_id) DO UPDATE SET
                    policy_mode = excluded.policy_mode,
                    require_config_deploy_approval = excluded.require_config_deploy_approval,
                    require_credential_change_approval = excluded.require_credential_change_approval,
                    require_user_change_approval = excluded.require_user_change_approval,
                    never_auto_approve_destructive = excluded.never_auto_approve_destructive,
                    updated_at = excluded.updated_at
                """,
                (
                    prefs.pref_id or f"pref_{uuid.uuid4().hex[:12]}",
                    prefs.tenant_id,
                    prefs.user_id,
                    prefs.policy_mode,
                    1 if prefs.require_config_deploy_approval else 0,
                    1 if prefs.require_credential_change_approval else 0,
                    1 if prefs.require_user_change_approval else 0,
                    1 if prefs.never_auto_approve_destructive else 0,
                    now_str,
                ),
            )
        prefs.updated_at = now_str
        return prefs

    def evaluate_and_request_approval(
        self,
        tenant_id: str,
        requester_id: str,
        requester_name: str,
        action_name: str,
        risk_level: str,
        target_resources: List[str],
        params: Dict[str, Any],
        reason: str,
        diff_text: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[PendingApproval]]:
        """
        Evaluates an operation against risk category and user preferences.
        Returns:
            (is_approved_immediately: bool, reason_message: str, pending_approval_obj: Optional[PendingApproval])
        """
        # Category C is strictly blocked
        if risk_level == AutonomyRiskCategory.CATEGORY_C.value:
            return False, "Operation Restricted: Execution exceeds authorized security boundary.", None

        # Category A is automatically approved
        if risk_level == AutonomyRiskCategory.CATEGORY_A.value:
            return True, "Operation Approved: Category A non-destructive operation.", None

        # Category B: Check preferences
        prefs = self.get_preferences(tenant_id, requester_id)

        # Destructive checks
        is_destructive = any(
            k in action_name.lower()
            for k in ("reboot", "delete", "destroy", "wipe", "flush", "reset")
        )
        if is_destructive and prefs.never_auto_approve_destructive:
            requires_approval = True
        elif "config" in action_name.lower() and prefs.require_config_deploy_approval:
            requires_approval = True
        elif ("credential" in action_name.lower() or "password" in action_name.lower()) and prefs.require_credential_change_approval:
            requires_approval = True
        elif ("user" in action_name.lower() or "role" in action_name.lower()) and prefs.require_user_change_approval:
            requires_approval = True
        elif prefs.policy_mode == ApprovalPolicyMode.ALWAYS_ASK.value:
            requires_approval = True
        else:
            requires_approval = True  # Standard safe baseline for Category B

        if not requires_approval:
            return True, "Operation Auto-Approved per user policy preferences.", None

        # Create pending approval
        approval_id = f"appr_{uuid.uuid4().hex[:12]}"
        now_str = datetime.now(timezone.utc).isoformat()
        pending = PendingApproval(
            approval_id=approval_id,
            tenant_id=tenant_id,
            requester_id=requester_id,
            requester_name=requester_name,
            action_name=action_name,
            risk_level=risk_level,
            target_resources=target_resources,
            params=params,
            diff_text=diff_text,
            reason=reason,
            status=ApprovalStatus.PENDING.value,
            created_at=now_str,
        )

        with topology_transaction(self.db_path, write=True) as conn:
            conn.execute(
                """
                INSERT INTO operational_pending_approvals (
                    approval_id, tenant_id, requester_id, requester_name,
                    action_name, risk_level, target_resources_json, params_json,
                    diff_text, reason, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval_id,
                    tenant_id,
                    requester_id,
                    requester_name,
                    action_name,
                    risk_level,
                    json.dumps(target_resources),
                    json.dumps(params),
                    diff_text,
                    reason,
                    ApprovalStatus.PENDING.value,
                    now_str,
                ),
            )

        logger.info("Created pending approval %s for action %s by %s", approval_id, action_name, requester_name)
        return False, "Confirmation Required: Action queued for human approval.", pending

    def resolve_approval(
        self,
        approval_id: str,
        reviewer_id: str,
        approved: bool,
        review_notes: Optional[str] = None,
    ) -> Optional[PendingApproval]:
        """Resolves an existing pending approval (APPROVED or REJECTED)."""
        now_str = datetime.now(timezone.utc).isoformat()
        new_status = ApprovalStatus.APPROVED.value if approved else ApprovalStatus.REJECTED.value

        with topology_transaction(self.db_path, write=True) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM operational_pending_approvals WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()

            if not row or row["status"] != ApprovalStatus.PENDING.value:
                return None

            conn.execute(
                """
                UPDATE operational_pending_approvals
                SET status = ?, reviewer_id = ?, review_notes = ?, resolved_at = ?
                WHERE approval_id = ?
                """,
                (new_status, reviewer_id, review_notes, now_str, approval_id),
            )

            return PendingApproval(
                approval_id=approval_id,
                tenant_id=row["tenant_id"],
                requester_id=row["requester_id"],
                requester_name=row["requester_name"],
                action_name=row["action_name"],
                risk_level=row["risk_level"],
                target_resources=json.loads(row["target_resources_json"] or "[]"),
                params=json.loads(row["params_json"] or "{}"),
                diff_text=row["diff_text"],
                reason=row["reason"],
                status=new_status,
                reviewer_id=reviewer_id,
                review_notes=review_notes,
                created_at=row["created_at"],
                resolved_at=now_str,
            )

    def list_pending_approvals(self, tenant_id: str, status: str = ApprovalStatus.PENDING.value, limit: int = 50) -> List[PendingApproval]:
        """Lists pending approvals for a tenant."""
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            query = "SELECT * FROM operational_pending_approvals WHERE tenant_id = ?"
            params: List[Any] = [tenant_id]
            if status != "all":
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(min(limit, 200))

            rows = conn.execute(query, params).fetchall()
            return [
                PendingApproval(
                    approval_id=r["approval_id"],
                    tenant_id=r["tenant_id"],
                    requester_id=r["requester_id"],
                    requester_name=r["requester_name"],
                    action_name=r["action_name"],
                    risk_level=r["risk_level"],
                    target_resources=json.loads(r["target_resources_json"] or "[]"),
                    params=json.loads(r["params_json"] or "{}"),
                    diff_text=r["diff_text"],
                    reason=r["reason"],
                    status=r["status"],
                    reviewer_id=r["reviewer_id"],
                    review_notes=r["review_notes"],
                    created_at=r["created_at"],
                    resolved_at=r["resolved_at"],
                )
                for r in rows
            ]

_GLOBAL_APPROVAL_ENGINE = None

def get_approval_engine(db_path = None):
    global _GLOBAL_APPROVAL_ENGINE
    if _GLOBAL_APPROVAL_ENGINE is None or db_path is not None:
        _GLOBAL_APPROVAL_ENGINE = CentralizedApprovalEngine(db_path=db_path)
    return _GLOBAL_APPROVAL_ENGINE

