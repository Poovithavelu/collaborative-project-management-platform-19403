from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Header, Body, Request
from .config import get_settings
from .security import decode_token
from .schemas import CheckoutSessionRequest, CheckoutSessionResponse, CustomerPortalRequest, CustomerPortalResponse

router = APIRouter(prefix="/billing", tags=["Billing"])


async def _get_current_user_payload(authorization: Optional[str] = Header(default=None)) -> dict:
    """Extract and validate user info from Bearer token."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid Authorization header")
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return payload


def _stripe_client():
    """Internal helper to get Stripe SDK client configured from environment."""
    import stripe  # lazy import to keep optional when not used
    settings = get_settings()
    if not settings.stripe_api_key:
        raise HTTPException(status_code=500, detail="Stripe is not configured (STRIPE_API_KEY missing)")
    stripe.api_key = settings.stripe_api_key
    return stripe


# PUBLIC_INTERFACE
@router.post(
    "/checkout-session",
    response_model=CheckoutSessionResponse,
    summary="Create Stripe Checkout session",
    description="Create a Stripe Checkout session for the provided price_id and return the hosted url.",
)
async def create_checkout_session(
    data: CheckoutSessionRequest = Body(...),
    payload: dict = Depends(_get_current_user_payload),
) -> CheckoutSessionResponse:
    """Create a Stripe Checkout session and return the URL for redirect."""
    stripe = _stripe_client()
    # In a full implementation, you would map the org/user to a Stripe customer id.
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": data.price_id, "quantity": 1}],
        success_url=data.success_url,
        cancel_url=data.cancel_url,
        allow_promotion_codes=True,
    )
    return CheckoutSessionResponse(url=session.get("url"))


# PUBLIC_INTERFACE
@router.post(
    "/customer-portal",
    response_model=CustomerPortalResponse,
    summary="Create Stripe customer portal link",
    description="Create a Stripe Billing Portal session URL and return it.",
)
async def create_customer_portal(
    data: CustomerPortalRequest = Body(...),
    payload: dict = Depends(_get_current_user_payload),
) -> CustomerPortalResponse:
    """Create a Stripe Billing Portal link for the current customer context."""
    stripe = _stripe_client()
    settings = get_settings()
    # NOTE: In production, retrieve or create a stripe.Customer for the org/user.
    # For now we create a placeholder customer portal session without specifying customer; this requires config with default customer in account.
    # Preferably pass a real 'customer' id here.
    args = {
        "return_url": data.return_url,
    }
    if settings.stripe_billing_portal_config_id:
        args["flow_data"] = {"type": "payment_method_update"}
        args["configuration"] = settings.stripe_billing_portal_config_id
    portal = stripe.billing_portal.Session.create(**args)
    return CustomerPortalResponse(url=portal.get("url"))


# PUBLIC_INTERFACE
@router.post(
    "/webhook",
    summary="Stripe webhook endpoint",
    description="Receives Stripe webhooks and verifies signatures if STRIPE_WEBHOOK_SECRET is set.",
)
async def stripe_webhook(request: Request) -> dict:
    """Receive Stripe webhooks, verify signature if configured, and acknowledge."""
    payload = await request.body()
    settings = get_settings()
    import stripe
    if settings.stripe_webhook_secret:
        sig_header = request.headers.get("stripe-signature")
        try:
            stripe.Webhook.construct_event(
                payload=payload, sig_header=sig_header, secret=settings.stripe_webhook_secret
            )
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid webhook signature")
    else:
        # If no secret configured, accept raw JSON (dev environments).
        try:
            await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid payload")

    # TODO: handle event types (checkout.session.completed, customer.subscription.updated, etc.)
    return {"received": True}
