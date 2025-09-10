from __future__ import annotations


import os
from typing import Optional

from fastapi import APIRouter, Request, HTTPException

import stripe

from .config import get_settings
from .db import get_pool
from .schemas import StripeWebhookResult

router = APIRouter(prefix="/stripe", tags=["Stripe"])

# Stripe config from env at import time for speed; keys are required in .env
settings = get_settings()
stripe.api_key = os.getenv("STRIPE_SECRET_KEY") or ""


async def _update_subscription(org_id: str, customer_id: Optional[str], status: str, price_id: Optional[str]) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            insert into subscriptions (org_id, stripe_customer_id, status, price_id)
            values ($1, $2, $3, $4)
            on conflict (org_id) do update set
              stripe_customer_id = excluded.stripe_customer_id,
              status = excluded.status,
              price_id = excluded.price_id
            """,
            org_id, customer_id, status, price_id
        )


# PUBLIC_INTERFACE
@router.post(
    "/webhook",
    response_model=StripeWebhookResult,
    summary="Stripe webhook",
    description="Stripe webhook endpoint to process subscription lifecycle events.",
)
async def stripe_webhook(request: Request) -> StripeWebhookResult:
    """Handle Stripe webhooks and update subscription state in DB."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not webhook_secret:
        raise HTTPException(status_code=500, detail="Stripe webhook not configured")

    try:
        event = stripe.Webhook.construct_event(payload=payload, sig_header=sig_header, secret=webhook_secret)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid webhook: {e}")

    event_type = event["type"]

    # Expecting org_id as metadata on Checkout Session or Subscription in production
    try:
        if event_type == "checkout.session.completed":
            session = event["data"]["object"]
            customer_id = session.get("customer")
            price_id = None
            if session.get("line_items") and session["line_items"]["data"]:
                price_id = session["line_items"]["data"][0]["price"]["id"]
            org_id = (session.get("metadata") or {}).get("org_id")
            if org_id:
                await _update_subscription(org_id, customer_id, "active", price_id)
        elif event_type == "customer.subscription.updated":
            sub = event["data"]["object"]
            status = sub.get("status")
            price_id = None
            if sub.get("items", {}).get("data"):
                price_id = sub["items"]["data"][0]["price"]["id"]
            org_id = (sub.get("metadata") or {}).get("org_id")
            if org_id:
                await _update_subscription(org_id, sub.get("customer"), status, price_id)
        elif event_type == "customer.subscription.deleted":
            sub = event["data"]["object"]
            org_id = (sub.get("metadata") or {}).get("org_id")
            if org_id:
                await _update_subscription(org_id, sub.get("customer"), "canceled", None)
    except Exception:
        # Never fail the webhook due to DB issues; log in real system
        pass

    return StripeWebhookResult(received=True, event_type=event_type)
