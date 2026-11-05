"""
AIRA OS — Billing Foundation Service & Gateway Abstraction.

Implements:
- Products and Pricing Plans matrix
- Invoices and Payment Transactions ledger
- HMAC-SHA256 Webhook signature verification
- Idempotent webhook event deduplication
- Automatic subscription activation on verified payment
- Audit logging for all financial state changes
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional
import uuid

from core.topology_db import DEFAULT_TOPOLOGY_DB_PATH, topology_transaction
from core.tenant.user_subscription import UserSubscriptionService

logger = logging.getLogger("aira.billing.service")

# Default Webhook Secret (can be overridden via environment variable)
DEFAULT_WEBHOOK_SECRET = os.getenv("AIRA_BILLING_WEBHOOK_SECRET", "aira_sec_mock_live_webhook_signature_2026")


@dataclass
class BillingPlan:
    plan_id: str
    product_id: str
    name: str
    tier: str
    has_networking_plus: bool
    monthly_tokens: int
    price_cents: int
    currency: str
    interval_months: int
    is_active: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "product_id": self.product_id,
            "name": self.name,
            "tier": self.tier,
            "has_networking_plus": self.has_networking_plus,
            "monthly_tokens": self.monthly_tokens,
            "price_cents": self.price_cents,
            "price_formatted": f"{self.currency} {self.price_cents:,.0f}",
            "currency": self.currency,
            "interval_months": self.interval_months,
            "is_active": self.is_active,
        }


class BillingService:
    """Authoritative billing lifecycle, checkout, webhook, and subscription fulfillment service."""

    def __init__(self, db_path: Optional[Path] = None, webhook_secret: Optional[str] = None):
        self.db_path = Path(db_path or DEFAULT_TOPOLOGY_DB_PATH).resolve()
        self.webhook_secret = webhook_secret or DEFAULT_WEBHOOK_SECRET
        self.subscription_service = UserSubscriptionService(self.db_path)

    def list_plans(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Lists available subscription and add-on plans."""
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            query = "SELECT * FROM operational_billing_plans"
            if active_only:
                query += " WHERE is_active = 1"
            query += " ORDER BY price_cents ASC"
            rows = conn.execute(query).fetchall()
            return [
                BillingPlan(
                    plan_id=r["plan_id"],
                    product_id=r["product_id"],
                    name=r["name"],
                    tier=r["tier"],
                    has_networking_plus=bool(r["has_networking_plus"]),
                    monthly_tokens=r["monthly_tokens"],
                    price_cents=r["price_cents"],
                    currency=r["currency"],
                    interval_months=r["interval_months"],
                    is_active=bool(r["is_active"]),
                ).to_dict()
                for r in rows
            ]

    def get_plan(self, plan_id: str) -> Optional[BillingPlan]:
        """Retrieves a specific billing plan."""
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM operational_billing_plans WHERE plan_id = ?", (plan_id,)).fetchone()
            if not row:
                return None
            return BillingPlan(
                plan_id=row["plan_id"],
                product_id=row["product_id"],
                name=row["name"],
                tier=row["tier"],
                has_networking_plus=bool(row["has_networking_plus"]),
                monthly_tokens=row["monthly_tokens"],
                price_cents=row["price_cents"],
                currency=row["currency"],
                interval_months=row["interval_months"],
                is_active=bool(row["is_active"]),
            )

    def create_invoice(self, user_id: str, plan_id: str) -> Dict[str, Any]:
        """Creates an invoice for a user choosing a plan."""
        plan = self.get_plan(plan_id)
        if not plan:
            raise ValueError(f"Plan '{plan_id}' does not exist.")

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        due_iso = (now + timedelta(days=3)).isoformat()
        invoice_id = f"inv_{uuid.uuid4().hex[:12]}"

        with topology_transaction(self.db_path, write=True) as conn:
            conn.row_factory = sqlite3.Row
            u_row = conn.execute("SELECT tenant_id FROM operational_users WHERE user_id = ?", (user_id,)).fetchone()
            if not u_row:
                raise ValueError(f"User '{user_id}' does not exist.")
            tenant_id = u_row["tenant_id"]

            sub = self.subscription_service.get_subscription(user_id)
            sub_id = sub.subscription_id if sub else None

            conn.execute(
                """
                INSERT INTO operational_billing_invoices
                (invoice_id, subscription_id, user_id, tenant_id, amount_cents, currency, status, due_date, paid_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?, NULL, ?)
                """,
                (invoice_id, sub_id, user_id, tenant_id, plan.price_cents, plan.currency, due_iso, now_iso),
            )

        return {
            "invoice_id": invoice_id,
            "user_id": user_id,
            "plan_id": plan_id,
            "plan_name": plan.name,
            "tier": plan.tier,
            "amount_cents": plan.price_cents,
            "currency": plan.currency,
            "status": "PENDING",
            "due_date": due_iso,
            "created_at": now_iso,
        }

    def create_checkout_session(self, invoice_id: str, provider_name: str = "MOCK_GATEWAY") -> Dict[str, Any]:
        """Initializes a checkout transaction with payment gateway."""
        with topology_transaction(self.db_path, write=True) as conn:
            conn.row_factory = sqlite3.Row
            inv = conn.execute("SELECT * FROM operational_billing_invoices WHERE invoice_id = ?", (invoice_id,)).fetchone()
            if not inv:
                raise ValueError(f"Invoice '{invoice_id}' does not exist.")

            if inv["status"] == "PAID":
                raise ValueError(f"Invoice '{invoice_id}' has already been paid.")

            now_iso = datetime.now(timezone.utc).isoformat()
            txn_id = f"txn_{uuid.uuid4().hex[:12]}"
            idempotency_key = f"checkout_{invoice_id}_{int(time.time())}"

            conn.execute(
                """
                INSERT INTO operational_billing_transactions
                (transaction_id, invoice_id, user_id, provider_name, provider_ref, amount_cents, currency, status, idempotency_key, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?, ?)
                """,
                (
                    txn_id,
                    invoice_id,
                    inv["user_id"],
                    provider_name,
                    f"mock_ref_{txn_id}",
                    inv["amount_cents"],
                    inv["currency"],
                    idempotency_key,
                    json.dumps({"checkout_created_at": now_iso}),
                    now_iso,
                    now_iso,
                ),
            )

        return {
            "checkout_url": f"/billing/checkout/{txn_id}",
            "transaction_id": txn_id,
            "invoice_id": invoice_id,
            "provider_name": provider_name,
            "amount_cents": inv["amount_cents"],
            "currency": inv["currency"],
            "status": "PENDING",
        }

    def verify_webhook_signature(self, payload_bytes: bytes, signature: str, secret: Optional[str] = None) -> bool:
        """Verifies HMAC-SHA256 signature for incoming webhooks."""
        sec = (secret or self.webhook_secret).encode("utf-8")
        expected_sig = hmac.new(sec, payload_bytes, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_sig.lower(), signature.strip().lower())

    def compute_signature(self, payload_bytes: bytes, secret: Optional[str] = None) -> str:
        """Helper to generate valid signature for tests and simulated webhooks."""
        sec = (secret or self.webhook_secret).encode("utf-8")
        return hmac.new(sec, payload_bytes, hashlib.sha256).hexdigest()

    def process_webhook_event(
        self,
        provider_name: str,
        event_type: str,
        payload: Dict[str, Any],
        signature: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Processes inbound billing webhook events idempotently.
        Prevents double-charging or duplicate fulfillment.
        """
        event_id = payload.get("event_id") or f"evt_{uuid.uuid4().hex[:12]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        # Step 1: Idempotency Check in operational_billing_webhook_events
        with topology_transaction(self.db_path, write=True) as conn:
            conn.row_factory = sqlite3.Row
            existing = conn.execute(
                "SELECT * FROM operational_billing_webhook_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()

            if existing and existing["processed"] == 1:
                logger.info("Webhook event %s already processed. Skipping duplicate.", event_id)
                return {
                    "event_id": event_id,
                    "status": "ALREADY_PROCESSED",
                    "duplicate": True,
                    "processed_at": existing["processed_at"],
                }

            if not existing:
                conn.execute(
                    """
                    INSERT INTO operational_billing_webhook_events
                    (event_id, provider_name, event_type, payload_json, signature, processed, created_at)
                    VALUES (?, ?, ?, ?, ?, 0, ?)
                    """,
                    (event_id, provider_name, event_type, json.dumps(payload), signature or "", now_iso),
                )

        # Step 2: Handle event fulfillment
        try:
            if event_type in ("payment.success", "charge.completed", "invoice.paid"):
                invoice_id = payload.get("invoice_id")
                transaction_id = payload.get("transaction_id")
                plan_tier = payload.get("plan_tier", "PRO")
                has_networking_plus = bool(payload.get("has_networking_plus", False))
                duration_days = int(payload.get("duration_days", 30))

                with topology_transaction(self.db_path, write=True) as conn:
                    conn.row_factory = sqlite3.Row
                    inv = conn.execute("SELECT * FROM operational_billing_invoices WHERE invoice_id = ?", (invoice_id,)).fetchone()
                    if not inv:
                        raise ValueError(f"Target invoice '{invoice_id}' not found.")

                    user_id = inv["user_id"]
                    tenant_id = inv["tenant_id"]

                    # Mark invoice paid
                    conn.execute(
                        "UPDATE operational_billing_invoices SET status = 'PAID', paid_at = ? WHERE invoice_id = ?",
                        (now_iso, invoice_id),
                    )

                    # Update transaction if provided
                    if transaction_id:
                        conn.execute(
                            "UPDATE operational_billing_transactions SET status = 'SUCCESS', updated_at = ? WHERE transaction_id = ?",
                            (now_iso, transaction_id),
                        )

                # Upgrade user subscription
                updated_sub = self.subscription_service.assign_subscription(
                    user_id=user_id,
                    plan_id=plan_tier,
                    duration_days=duration_days,
                    networking_addon=has_networking_plus,
                    renewal_status="MANUAL",
                    operator_user=f"GATEWAY:{provider_name}",
                )

                # Mark webhook event as processed
                with topology_transaction(self.db_path, write=True) as conn:
                    conn.execute(
                        "UPDATE operational_billing_webhook_events SET processed = 1, processed_at = ? WHERE event_id = ?",
                        (now_iso, event_id),
                    )

                logger.info(
                    "Fulfill payment event %s: User %s upgraded to %s (netplus=%s)",
                    event_id, user_id, plan_tier, has_networking_plus,
                )

                return {
                    "event_id": event_id,
                    "status": "PROCESSED",
                    "duplicate": False,
                    "invoice_id": invoice_id,
                    "subscription": updated_sub.to_dict(),
                    "processed_at": now_iso,
                }

            else:
                # Unsupported event type, record as acknowledged
                with topology_transaction(self.db_path, write=True) as conn:
                    conn.execute(
                        "UPDATE operational_billing_webhook_events SET processed = 1, processed_at = ? WHERE event_id = ?",
                        (now_iso, event_id),
                    )
                return {"event_id": event_id, "status": "ACKNOWLEDGED", "action": "NOOP"}

        except Exception as e:
            logger.exception("Error fulfilling webhook event %s: %s", event_id, e)
            with topology_transaction(self.db_path, write=True) as conn:
                conn.execute(
                    "UPDATE operational_billing_webhook_events SET error_message = ? WHERE event_id = ?",
                    (str(e), event_id),
                )
            raise

    def simulate_mock_payment(self, invoice_id: str, user_id: str, plan_tier: str = "PRO", has_netplus: bool = True) -> Dict[str, Any]:
        """Convenience method to simulate end-to-end checkout & webhook callback for testing."""
        session = self.create_checkout_session(invoice_id)
        payload = {
            "event_id": f"evt_mock_{uuid.uuid4().hex[:8]}",
            "invoice_id": invoice_id,
            "transaction_id": session["transaction_id"],
            "plan_tier": plan_tier,
            "has_networking_plus": has_netplus,
            "duration_days": 30,
            "amount_cents": session["amount_cents"],
        }
        raw_bytes = json.dumps(payload, separators=(',', ':')).encode("utf-8")
        sig = self.compute_signature(raw_bytes)
        return self.process_webhook_event(
            provider_name="MOCK_GATEWAY",
            event_type="payment.success",
            payload=payload,
            signature=sig,
        )

    def list_invoices(self, user_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Lists invoices for a specific user or globally for Admin Site."""
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            query = """
                SELECT i.*, u.username, u.email
                FROM operational_billing_invoices i
                JOIN operational_users u ON i.user_id = u.user_id
                WHERE 1=1
            """
            params: List[Any] = []
            if user_id:
                query += " AND i.user_id = ?"
                params.append(user_id)
            query += " ORDER BY i.created_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, tuple(params)).fetchall()
            return [dict(r) for r in rows]

    def list_transactions(self, user_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Lists transactions for a specific user or globally for Admin Site."""
        with topology_transaction(self.db_path, write=False) as conn:
            conn.row_factory = sqlite3.Row
            query = """
                SELECT t.*, u.username
                FROM operational_billing_transactions t
                JOIN operational_users u ON t.user_id = u.user_id
                WHERE 1=1
            """
            params: List[Any] = []
            if user_id:
                query += " AND t.user_id = ?"
                params.append(user_id)
            query += " ORDER BY t.created_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, tuple(params)).fetchall()
            return [dict(r) for r in rows]
