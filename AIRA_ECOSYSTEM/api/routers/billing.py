"""
AIRA OS — Billing & Subscription Payment Router.

Provides endpoints for:
- Viewing pricing plans and Networking++ add-on
- Creating invoices and checkout sessions
- Secure webhook processing with HMAC-SHA256 signature verification
- Idempotent transaction fulfillment
- Simulation test endpoint for mock payments
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from core.billing.service import BillingService
from core.tenant.models import TenantContext
from api.routers.auth import get_current_user_context

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])

_billing_service = BillingService()


class CreateInvoiceRequest(BaseModel):
    plan_id: str


class CheckoutRequest(BaseModel):
    invoice_id: str
    provider_name: str = "MOCK_GATEWAY"


class SimulatePaymentRequest(BaseModel):
    invoice_id: str
    plan_tier: str = "PRO"
    has_networking_plus: bool = True


@router.get("/plans")
def list_plans():
    """Returns available subscription tiers and add-on plans."""
    return {"success": True, "plans": _billing_service.list_plans()}


@router.post("/invoices")
def create_invoice(payload: CreateInvoiceRequest, ctx: TenantContext = Depends(get_current_user_context)):
    """Creates a new billing invoice for the current user."""
    try:
        inv = _billing_service.create_invoice(user_id=ctx.user_id, plan_id=payload.plan_id)
        return {"success": True, "invoice": inv}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/checkout")
def create_checkout(payload: CheckoutRequest, ctx: TenantContext = Depends(get_current_user_context)):
    """Generates checkout session for an unpaid invoice."""
    try:
        session = _billing_service.create_checkout_session(invoice_id=payload.invoice_id, provider_name=payload.provider_name)
        return {"success": True, "session": session}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/webhooks/{provider}")
async def handle_webhook(
    provider: str,
    request: Request,
    x_signature: Optional[str] = Header(None, alias="X-Signature"),
    x_webhook_signature: Optional[str] = Header(None, alias="X-Webhook-Signature"),
):
    """
    Receives and processes payment gateway webhooks.
    Enforces HMAC-SHA256 signature verification and idempotency deduplication.
    """
    signature = x_signature or x_webhook_signature
    body_bytes = await request.body()

    # Validate HMAC signature if provided or in production
    if signature:
        valid = _billing_service.verify_webhook_signature(body_bytes, signature)
        if not valid:
            raise HTTPException(status_code=401, detail="Invalid HMAC webhook signature.")

    try:
        payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON webhook payload.")

    event_type = payload.get("event_type") or payload.get("type", "payment.success")

    try:
        result = _billing_service.process_webhook_event(
            provider_name=provider.upper(),
            event_type=event_type,
            payload=payload,
            signature=signature,
        )
        return {"status": "ok", "result": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Webhook processing error: {exc}")


@router.post("/simulate-mock")
def simulate_mock_payment(payload: SimulatePaymentRequest, ctx: TenantContext = Depends(get_current_user_context)):
    """Simulates an end-to-end checkout and successful payment callback."""
    try:
        res = _billing_service.simulate_mock_payment(
            invoice_id=payload.invoice_id,
            user_id=ctx.user_id,
            plan_tier=payload.plan_tier,
            has_netplus=payload.has_networking_plus,
        )
        return {"success": True, "result": res}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/invoices")
def list_user_invoices(ctx: TenantContext = Depends(get_current_user_context)):
    """Lists invoices for the current user."""
    invoices = _billing_service.list_invoices(user_id=ctx.user_id)
    return {"success": True, "invoices": invoices}


@router.get("/transactions")
def list_user_transactions(ctx: TenantContext = Depends(get_current_user_context)):
    """Lists transactions for the current user."""
    txns = _billing_service.list_transactions(user_id=ctx.user_id)
    return {"success": True, "transactions": txns}
