"""Records Repository purchase router (F1 Delta, 2026-09-12).

POST /repository/purchase — Stripe Checkout session for the Records Repository
SKU, in two modes:
  - plan="annual"   → recurring subscription checkout (Stripe price object via
    env REPOSITORY_STRIPE_PRICE_ANNUAL, default price_1UEqYRJE7N1BszdfddnhZt3s)
  - plan="lifetime" → one-time payment checkout (env
    REPOSITORY_STRIPE_PRICE_LIFETIME, default price_1UEqYRJE7N1BszdfTSPX8GJF)

PRICE STATUS: pending owner confirmation is OVER — the Stripe catalog is live
(owner-approved $49/yr + $199 lifetime, product prod_VFLEoI1IRVvcUc). The
price IDs below are the real ones; do NOT pass unit_amount — the Stripe price
object carries the amount.

Entitlement: the shared Stripe webhook (subscriptions.py
checkout.session.completed handler) stamps repository_entitled/repository_plan
when session metadata carries repository_plan — see
handle_repository_checkout_completed() called from that handler.
"""
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException

from database import db
from dependencies import get_current_user
from models import RepositoryPurchaseRequest, RepositoryPurchaseResponse
from utils.audit import log_audit_event

logger = logging.getLogger(__name__)
router = APIRouter(tags=["repository"])

# Real Stripe catalog (owner-approved 2026-09-12): annual $49/yr subscription,
# lifetime $199 one-time. Product prod_VFLEoI1IRVvcUc. Override via env.
REPOSITORY_STRIPE_PRICE_ANNUAL = os.environ.get(
    "REPOSITORY_STRIPE_PRICE_ANNUAL", "price_1UEqYRJE7N1BszdfddnhZt3s"
)
REPOSITORY_STRIPE_PRICE_LIFETIME = os.environ.get(
    "REPOSITORY_STRIPE_PRICE_LIFETIME", "price_1UEqYRJE7N1BszdfTSPX8GJF"
)

# Default redirect targets when the client doesn't pass URLs (matches the
# existing checkout pattern: the frontend normally sends success/cancel).
_DEFAULT_BILLING_URL = os.environ.get("APP_BASE_URL", "https://app.trustoffice.app") + "/settings/billing"

VALID_PLANS = ("annual", "lifetime")


def _plan_config(plan: str) -> dict:
    """Resolve the Stripe mode + price ID for a repository plan."""
    if plan == "annual":
        return {"mode": "subscription", "price_id": REPOSITORY_STRIPE_PRICE_ANNUAL}
    return {"mode": "payment", "price_id": REPOSITORY_STRIPE_PRICE_LIFETIME}


async def get_or_create_stripe_customer(user: dict) -> str:
    """Reuse the account's Stripe customer (test→live safe) or create one.

    Mirrors the subscriptions.py checkout pattern: read
    subscriptions.stripe_customer_id, verify it still exists in Stripe,
    create + persist one when missing/invalid.
    """
    sub = await db.subscriptions.find_one(
        {"user_id": user["user_id"]}, {"_id": 0, "stripe_customer_id": 1}
    )
    existing = (sub or {}).get("stripe_customer_id")
    if existing:
        try:
            stripe.Customer.retrieve(existing)
            return existing
        except stripe.InvalidRequestError:
            logger.info(f"Customer {existing} not found in Stripe, creating new one")

    customer = stripe.Customer.create(
        email=user.get("email", ""),
        name=user.get("name", ""),
        metadata={"user_id": user["user_id"]},
    )
    await db.subscriptions.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "stripe_customer_id": customer.id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    return customer.id


# Re-exported alias (single definition point; kept for webhook-handler imports).
get_or_create_stripe_customer_id = get_or_create_stripe_customer


@router.post("/repository/purchase", response_model=RepositoryPurchaseResponse)
async def repository_purchase(
    body: RepositoryPurchaseRequest,
    success_url: Optional[str] = None,
    cancel_url: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Create a Stripe Checkout session for the Records Repository.

    Body: {"plan": "annual" | "lifetime"}. Optional ?success_url= / ?cancel_url=
    override the billing-page defaults. Returns {"checkout_url": str}.
    """
    if body.plan not in VALID_PLANS:
        raise HTTPException(status_code=400, detail="Invalid plan. Choose 'annual' or 'lifetime'.")

    config = _plan_config(body.plan)
    try:
        customer_id = await get_or_create_stripe_customer(user)

        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode=config["mode"],
            # Do NOT pass unit_amount — the Stripe price object carries the amount.
            line_items=[{"price": config["price_id"], "quantity": 1}],
            success_url=success_url or _DEFAULT_BILLING_URL,
            cancel_url=cancel_url or _DEFAULT_BILLING_URL,
            metadata={
                "user_id": user["user_id"],
                "purchase_type": "repository",
                "repository_plan": body.plan,
            },
        )
    except stripe.StripeError as e:
        logger.error(f"Stripe error (repository purchase): {e}")
        raise HTTPException(
            status_code=500,
            detail="Payment service is currently unavailable. Please try again in a few minutes. If this continues, contact support@trustoffice.app.",
        )

    await db.payment_transactions.insert_one({
        "transaction_id": f"txn_{os.urandom(6).hex()}",
        "user_id": user["user_id"],
        "session_id": session.id,
        "purchase_type": "repository",
        "repository_plan": body.plan,
        "stripe_price_id": config["price_id"],
        "payment_status": "initiated",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    await log_audit_event(user["user_id"], "repository_purchase_started", "repository", body.plan, {
        "session_id": session.id, "mode": config["mode"],
    })

    return RepositoryPurchaseResponse(checkout_url=session.url or "")


async def handle_repository_checkout_completed(metadata: dict, session) -> None:
    """Stamp repository entitlement on checkout.session.completed.

    Called from the shared Stripe webhook dispatcher in subscriptions.py.
    Marks the account repository_entitled=true with the purchased plan.
    """
    if metadata.get("purchase_type") != "repository":
        return
    user_id = metadata.get("user_id")
    if not user_id:
        return

    await db.repository_entitlements.update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id": user_id,
            "repository_entitled": True,
            "repository_plan": metadata.get("repository_plan", "annual"),
            "stripe_session_id": getattr(session, "id", None),
            "granted_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    logger.info(f"Repository entitlement granted: user={user_id} plan={metadata.get('repository_plan')}")