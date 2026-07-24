# Subscriptions router - handles Stripe payments and subscription management
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid
import logging
import os

import stripe
from pymongo import ReturnDocument

from database import db
from dependencies import (
    get_current_user, 
    get_subscription_state, 
    get_user_features,
    get_trust_limit,
    TRIAL_DAYS
)
from models import SubscriptionResponse, CheckoutRequest, PortalRequest, ChangePlanRequest

# Import email service
from email_service import email_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["subscriptions"])

# Stripe Config
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')
STRIPE_MONTHLY_PRICE_ID = os.environ.get('STRIPE_MONTHLY_PRICE_ID')
STRIPE_ANNUAL_PRICE_ID = os.environ.get('STRIPE_ANNUAL_PRICE_ID')

# New 3-tier price IDs (6 total: 3 tiers x 2 billing periods)
STRIPE_TRUSTEE_MONTHLY_PRICE_ID = os.environ.get('STRIPE_TRUSTEE_MONTHLY_PRICE_ID')
STRIPE_TRUSTEE_ANNUAL_PRICE_ID = os.environ.get('STRIPE_TRUSTEE_ANNUAL_PRICE_ID')
STRIPE_ESTATE_MONTHLY_PRICE_ID = os.environ.get('STRIPE_ESTATE_MONTHLY_PRICE_ID')
STRIPE_ESTATE_ANNUAL_PRICE_ID = os.environ.get('STRIPE_ESTATE_ANNUAL_PRICE_ID')
STRIPE_ADVISOR_MONTHLY_PRICE_ID = os.environ.get('STRIPE_ADVISOR_MONTHLY_PRICE_ID')
STRIPE_ADVISOR_ANNUAL_PRICE_ID = os.environ.get('STRIPE_ADVISOR_ANNUAL_PRICE_ID')
STRIPE_WINGPOINT_ANNUAL_PRICE_ID = os.environ.get('STRIPE_WINGPOINT_ANNUAL_PRICE_ID')

# Price ID lookup: (plan_type, billing_period) -> stripe_price_id
PRICE_IDS = {
    ("trustee", "monthly"): STRIPE_TRUSTEE_MONTHLY_PRICE_ID,
    ("trustee", "annual"): STRIPE_TRUSTEE_ANNUAL_PRICE_ID,
    ("estate", "monthly"): STRIPE_ESTATE_MONTHLY_PRICE_ID,
    ("estate", "annual"): STRIPE_ESTATE_ANNUAL_PRICE_ID,
    ("advisor", "monthly"): STRIPE_ADVISOR_MONTHLY_PRICE_ID,
    ("advisor", "annual"): STRIPE_ADVISOR_ANNUAL_PRICE_ID,
    ("wingpoint", "annual"): STRIPE_WINGPOINT_ANNUAL_PRICE_ID,
}

# Amount lookup (for payment_transactions logging)
PLAN_AMOUNTS = {
    ("trustee", "monthly"): 79.00,
    ("trustee", "annual"): 790.00,
    ("estate", "monthly"): 149.00,
    ("wingpoint", "annual"): 1188.00,
    ("advisor", "monthly"): 399.00,
    ("advisor", "annual"): 3990.00,
    # Legacy
    ("monthly", "monthly"): 79.00,
    ("annual", "annual"): 790.00,
}

# Reverse lookup for webhook: price_id -> (plan_type, billing_period)
PRICE_ID_TO_PLAN = {v: (k[0], k[1]) for k, v in PRICE_IDS.items() if v}

# Startup validation: warn if any tier price IDs are missing
_missing_prices = [k for k, v in PRICE_IDS.items() if not v]
if _missing_prices:
    logger.warning(f"Missing Stripe price env vars for tiers: {_missing_prices}. Checkout for these tiers will fail.")

# Legacy price ID mapping (backward compat during migration)
LEGACY_PRICE_MAP = {
    STRIPE_MONTHLY_PRICE_ID: ("trustee", "monthly", 10),   # (plan_type, billing_period, legacy_trust_limit)
    STRIPE_ANNUAL_PRICE_ID: ("trustee", "annual", 10),
}

# Mailercloud Config
from mailercloud_service import add_to_paid_list


# ==================== HELPER FUNCTIONS ====================

async def get_or_create_subscription(user_id: str) -> dict:
    """Get or create subscription for a user (atomic upsert to avoid race conditions)"""
    now = datetime.now(timezone.utc).isoformat()
    default_sub = {
        "subscription_id": f"sub_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "plan_type": "none",
        "status": "expired",
        "trial_start_date": None,
        "trial_end_date": None,
        "stripe_customer_id": None,
        "stripe_subscription_id": None,
        "created_at": now,
        "updated_at": now,
        "notes": "New signup — subscribe to activate"
    }
    # Use find_one_and_update with upsert to atomically get-or-create
    # NOTE: A unique index on user_id is created at app startup (see server.py startup_event)
    sub = await db.subscriptions.find_one_and_update(
        {"user_id": user_id},
        {"$setOnInsert": default_sub},
        upsert=True,
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0}
    )
    return sub


def calculate_subscription_status(sub: dict) -> dict:
    """Calculate current status and days remaining, fetch Stripe data if available"""
    now = datetime.now(timezone.utc)
    
    result = {
        **sub,
        "current_period_end": None,
        "cancel_at_period_end": None
    }
    
    # If there's an active Stripe subscription, fetch details
    if sub.get("stripe_subscription_id") and sub["status"] == "active":
        try:
            stripe_sub = stripe.Subscription.retrieve(sub["stripe_subscription_id"])
            result["current_period_end"] = datetime.fromtimestamp(
                stripe_sub.current_period_end, tz=timezone.utc
            ).isoformat()
            result["cancel_at_period_end"] = stripe_sub.cancel_at_period_end
            result["is_active"] = True
            result["days_remaining"] = None
            
            # Update plan type from Stripe if needed
            if stripe_sub.items.data:
                price_id = stripe_sub.items.data[0].price.id
                # Check new tier price IDs first
                plan_info = PRICE_ID_TO_PLAN.get(price_id)
                if plan_info:
                    result["plan_type"] = plan_info[0]
                    result["billing_period"] = plan_info[1]
                elif price_id in LEGACY_PRICE_MAP:
                    # Legacy price IDs (backward compat)
                    legacy_info = LEGACY_PRICE_MAP[price_id]
                    result["plan_type"] = legacy_info[0]
                    result["billing_period"] = legacy_info[1]
                    result["legacy_trust_limit"] = legacy_info[2]
                # If price_id doesn't match anything, leave plan_type as-is from DB
            
            return result
        except stripe.StripeError as e:
            logger.warning(f"Could not fetch Stripe subscription: {e}")
    
    if sub["status"] == "active":
        return {
            **result,
            "is_active": True,
            "days_remaining": None
        }
    
    if sub["status"] == "trialing" and sub.get("trial_end_date"):
        trial_end = datetime.fromisoformat(sub["trial_end_date"].replace('Z', '+00:00'))
        if trial_end.tzinfo is None:
            trial_end = trial_end.replace(tzinfo=timezone.utc)
        
        days_remaining = (trial_end - now).days
        is_expired = days_remaining < 0
        
        return {
            **result,
            "is_active": not is_expired,
            "days_remaining": max(0, days_remaining),
            "status": "expired" if is_expired else "trialing"
        }
    
    return {
        **result,
        "is_active": sub["status"] == "active",
        "days_remaining": None
    }


# ==================== SUBSCRIPTION ENDPOINTS ====================

@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(user: dict = Depends(get_current_user)):
    """Get current user's subscription details"""
    sub = await get_or_create_subscription(user["user_id"])
    enriched = calculate_subscription_status(sub)
    return SubscriptionResponse(**enriched)


@router.get("/subscription/state")
async def get_subscription_state_endpoint(user: dict = Depends(get_current_user)):
    """
    Get normalized subscription state with all computed fields.
    This endpoint provides the single source of truth for subscription status.
    
    Returns:
        - plan_type: "trial", "free", "forever_free", "monthly", "annual"
        - status: "trialing", "active", "past_due", "canceled", "expired"
        - is_trial: boolean
        - is_active: boolean
        - is_read_only: boolean (determines if write operations are blocked)
        - trial_days_remaining: int or null
        - is_gifted: boolean (whether admin-gifted account)
        - gift_type: "14day", "monthly", "annual" or null
        - gift_days_remaining: int or null
    """
    # Failsafe: Check if user is primary admin by email
    PRIMARY_ADMIN_EMAIL = "contact@trustoffice.app"
    user_email = user.get("email", "").lower()
    is_primary_admin = user_email == PRIMARY_ADMIN_EMAIL
    
    if is_primary_admin:
        # Ensure admin has forever_free subscription in database
        await db.subscriptions.update_one(
            {"user_id": user["user_id"]},
            {"$set": {
                "plan_type": "forever_free",
                "status": "active"
            }},
            upsert=True
        )
    
    state = await get_subscription_state(user["user_id"])
    state_dict = state.model_dump()
    
    # Enrich with trust count and upgrade status for frontend use
    trust_count = await db.trusts.count_documents({"user_id": user["user_id"]})
    current_limit = get_trust_limit(state.plan_type, state.legacy_trust_limit)
    state_dict["trust_count"] = trust_count
    state_dict["trust_limit"] = current_limit if current_limit != float('inf') else "unlimited"
    state_dict["needs_upgrade"] = trust_count > current_limit if current_limit != float('inf') else False
    
    return state_dict


@router.get("/subscription/features")
async def get_subscription_features(user: dict = Depends(get_current_user)):
    """
    Get available features for the user's subscription plan.
    Used by frontend to show/hide premium features.
    
    Returns:
        - plan_type: Current plan
        - is_active: Whether subscription is active
        - is_trial: Whether on trial
        - features: Dict of feature flags (feature_name -> boolean)
    
    Feature flags:
        - minutes_basic, distributions_basic, governance_basic, single_trust (core)
        - pdf_no_watermark, csv_export, multiple_trusts, benevolence_mode,
          beneficiary_dashboard, trust_units, governance_history, advanced_templates (premium)
    """
    return await get_user_features(user["user_id"])


@router.post("/subscription/create-checkout")
async def create_checkout_session(checkout: CheckoutRequest, user: dict = Depends(get_current_user)):
    """Create a Stripe checkout session for subscription"""
    # Support both new 3-tier system and legacy 2-plan system
    valid_new_plans = ["trustee", "estate", "advisor", "wingpoint"]
    valid_legacy_plans = ["monthly", "annual"]
    valid_periods = ["monthly", "annual"]
    
    # Determine billing_period for legacy plan_type values
    if checkout.plan_type in valid_legacy_plans:
        billing_period = checkout.plan_type  # "monthly" or "annual" IS the billing period for legacy
    elif checkout.plan_type in valid_new_plans:
        billing_period = checkout.billing_period or "monthly"
        if billing_period not in valid_periods:
            raise HTTPException(status_code=400, detail="Invalid billing period. Choose 'monthly' or 'annual'.")
    else:
        raise HTTPException(status_code=400, detail="Invalid plan type. Choose 'trustee', 'estate', 'advisor', or 'wingpoint'.")

    # WingPoint plan is annual-only
    if checkout.plan_type == "wingpoint" and billing_period != "annual":
        raise HTTPException(status_code=400, detail="WingPoint plan is annual-only.")
    
    # Get price_id from lookup
    if checkout.plan_type in valid_new_plans:
        price_id = PRICE_IDS.get((checkout.plan_type, billing_period))
        if not price_id:
            raise HTTPException(status_code=500, detail=f"Price ID not configured for {checkout.plan_type}/{billing_period}")
    else:
        # Legacy
        price_id = STRIPE_MONTHLY_PRICE_ID if checkout.plan_type == "monthly" else STRIPE_ANNUAL_PRICE_ID
    
    # Get amount for logging
    _amount_fallbacks = {"trustee": 79.00, "estate": 149.00, "advisor": 399.00, "wingpoint": 1188.00, "monthly": 79.00, "annual": 790.00}
    amount = PLAN_AMOUNTS.get((checkout.plan_type, billing_period), _amount_fallbacks.get(checkout.plan_type, 79.00))
    
    # Get or create subscription to get/create stripe customer
    sub = await get_or_create_subscription(user["user_id"])
    
    try:
        customer_id = None
        
        # Try to use existing customer if we have one
        if sub.get("stripe_customer_id"):
            try:
                # Verify the customer exists in Stripe (handles test->live mode switch)
                stripe.Customer.retrieve(sub["stripe_customer_id"])
                customer_id = sub["stripe_customer_id"]
            except stripe.InvalidRequestError:
                # Customer doesn't exist (likely switched from test to live mode)
                logger.info(f"Customer {sub['stripe_customer_id']} not found in Stripe, creating new one")
                customer_id = None
        
        # Create new customer if needed
        if not customer_id:
            customer = stripe.Customer.create(
                email=user["email"],
                name=user.get("name", ""),
                metadata={"user_id": user["user_id"]}
            )
            customer_id = customer.id
            await db.subscriptions.update_one(
                {"user_id": user["user_id"]},
                {"$set": {"stripe_customer_id": customer_id, "updated_at": datetime.now(timezone.utc).isoformat()}}
            )
        
        # Create checkout session params
        checkout_params = {
            "customer": customer_id,
            "mode": "subscription",
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": checkout.success_url,
            "cancel_url": checkout.cancel_url,
            "metadata": {"user_id": user["user_id"], "plan_type": checkout.plan_type, "billing_period": billing_period},
            "allow_promotion_codes": True  # Always allow entering promo codes
        }
        
        # Pass Rewardful referral ID as client_reference_id for affiliate tracking
        if checkout.referral_id:
            checkout_params["client_reference_id"] = checkout.referral_id
            logger.info(f"Added Rewardful referral ID: {checkout.referral_id}")
        
        # Check for referral discount first (50% off for referred users)
        try:
            from routers.referrals import apply_referral_discount_to_checkout, mark_referee_discount_applied
            referral_coupon = await apply_referral_discount_to_checkout(user["user_id"])
            if referral_coupon:
                checkout_params["discounts"] = [{"coupon": referral_coupon}]
                await mark_referee_discount_applied(user["user_id"])
                logger.info(f"Applied referral discount for user {user['user_id']}")
        except Exception as e:
            logger.error(f"Failed to check/apply referral discount: {e}")
        
        # If no referral discount and a direct coupon is provided, apply it
        if "discounts" not in checkout_params and checkout.coupon:
            try:
                # Verify the coupon exists and is valid
                coupon = stripe.Coupon.retrieve(checkout.coupon)
                if coupon and coupon.valid:
                    checkout_params["discounts"] = [{"coupon": checkout.coupon}]
                    # Remove allow_promotion_codes when applying a coupon directly
                    checkout_params.pop("allow_promotion_codes", None)
                    logger.info(f"Applied coupon: {checkout.coupon}")
                else:
                    logger.warning(f"Coupon {checkout.coupon} is not valid")
            except stripe.InvalidRequestError as coupon_error:
                logger.warning(f"Coupon {checkout.coupon} not found: {coupon_error}")
                # Continue without the coupon - user can still enter codes manually
            except stripe.StripeError as coupon_error:
                logger.warning(f"Could not apply coupon {checkout.coupon}: {coupon_error}")
        
        # If no referral discount/coupon and a specific promotion code is provided, try to apply it
        if "discounts" not in checkout_params and checkout.promotion_code:
            try:
                # Look up the promotion code in Stripe
                promo_codes = stripe.PromotionCode.list(code=checkout.promotion_code, active=True, limit=1)
                if promo_codes.data:
                    checkout_params["discounts"] = [{"promotion_code": promo_codes.data[0].id}]
                    logger.info(f"Applied promotion code: {checkout.promotion_code}")
            except stripe.StripeError as promo_error:
                logger.warning(f"Could not apply promotion code {checkout.promotion_code}: {promo_error}")
                # Continue without the promo code - user can still enter it manually
        
        # Create checkout session
        session = stripe.checkout.Session.create(**checkout_params)
        
        # Record transaction
        await db.payment_transactions.insert_one({
            "transaction_id": f"txn_{uuid.uuid4().hex[:12]}",
            "user_id": user["user_id"],
            "session_id": session.id,
            "amount": amount,
            "currency": "usd",
            "plan_type": checkout.plan_type,
            "billing_period": billing_period,
            "payment_status": "initiated",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        })
        
        return {"checkout_url": session.url, "session_id": session.id}
        
    except stripe.StripeError as e:
        logger.error(f"Stripe error: {e}")
        raise HTTPException(status_code=500, detail="Payment service is currently unavailable. Please try again in a few minutes. If this continues, contact support@trustoffice.app.")


@router.get("/subscription/verify-payment")
async def verify_payment(session_id: str, user: dict = Depends(get_current_user)):
    """Verify a checkout session and update subscription"""
    try:
        session = stripe.checkout.Session.retrieve(session_id)

        # Ownership check: ensure the payment session belongs to the calling user
        session_user_id = session.metadata.get("user_id") if session.metadata else None
        if not session_user_id:
            raise HTTPException(status_code=403, detail="Payment session missing user identity — cannot verify ownership")
        if session_user_id != user["user_id"]:
            raise HTTPException(status_code=403, detail="This payment session belongs to another account")

        if session.payment_status == "paid":
            plan_type = session.metadata.get("plan_type", "monthly")
            billing_period = session.metadata.get("billing_period")
            # For legacy plans, infer billing_period from plan_type
            if not billing_period and plan_type in ("monthly", "annual"):
                billing_period = plan_type
            
            # Update subscription
            await db.subscriptions.update_one(
                {"user_id": user["user_id"]},
                {
                    "$set": {
                        "plan_type": plan_type,
                        "billing_period": billing_period,
                        "status": "active",
                        "stripe_subscription_id": session.subscription,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    },
                    "$unset": {
                        "gifted": "",
                        "gift_type": "",
                        "gift_start_date": "",
                        "gift_end_date": "",
                        "gifted_at": ""
                    }
                },
                upsert=True
            )
            
            # Update transaction
            await db.payment_transactions.update_one(
                {"session_id": session_id},
                {"$set": {"payment_status": "paid", "updated_at": datetime.now(timezone.utc).isoformat()}}
            )
            
            return {"status": "success", "plan_type": plan_type}
        
        return {"status": "pending"}
        
    except stripe.StripeError as e:
        logger.error(f"Stripe verification error: {e}")
        raise HTTPException(status_code=500, detail="Payment verification failed. Please try again. If the charge appears on your card, contact support@trustoffice.app.")


@router.post("/subscription/create-portal")
async def create_customer_portal(portal: PortalRequest, user: dict = Depends(get_current_user)):
    """Create a Stripe customer portal session for managing subscription"""
    sub = await get_or_create_subscription(user["user_id"])
    
    if not sub.get("stripe_customer_id"):
        raise HTTPException(status_code=400, detail="No billing account found. Please subscribe first.")
    
    try:
        session = stripe.billing_portal.Session.create(
            customer=sub["stripe_customer_id"],
            return_url=portal.return_url
        )
        return {"portal_url": session.url}
    except stripe.StripeError as e:
        logger.error(f"Stripe portal error: {e}")
        raise HTTPException(status_code=500, detail="Could not open the billing portal. Please try again. If this continues, contact support@trustoffice.app.")


@router.post("/subscription/cancel")
async def cancel_subscription(user: dict = Depends(get_current_user)):
    """Cancel subscription at end of current billing period"""
    sub = await get_or_create_subscription(user["user_id"])
    
    if not sub.get("stripe_subscription_id"):
        raise HTTPException(status_code=400, detail="No active subscription found. Please subscribe to a plan first at trustoffice.app/settings/billing.")

    try:
        # Cancel at period end (user keeps access until subscription ends)
        stripe_sub = stripe.Subscription.modify(
            sub["stripe_subscription_id"],
            cancel_at_period_end=True
        )
        
        await db.subscriptions.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        
        cancel_date = datetime.fromtimestamp(
            stripe_sub.current_period_end, tz=timezone.utc
        ).strftime('%B %d, %Y')
        
        # Send cancellation email
        if email_service.is_configured:
            try:
                await email_service.send_subscription_canceled(
                    to_email=user["email"],
                    user_name=user.get("name", ""),
                    access_until=cancel_date
                )
            except Exception as e:
                logger.error(f"Failed to send cancellation email: {e}")
        
        return {
            "status": "canceled",
            "message": f"Your subscription will be canceled on {cancel_date}. You'll have access until then.",
            "cancel_at": stripe_sub.current_period_end
        }
    except stripe.StripeError as e:
        logger.error(f"Stripe cancel error: {e}")
        raise HTTPException(status_code=500, detail="Could not cancel subscription. Please try again. If this continues, contact support@trustoffice.app.")


@router.post("/subscription/reactivate")
async def reactivate_subscription(user: dict = Depends(get_current_user)):
    """Reactivate a subscription that was set to cancel at period end"""
    sub = await get_or_create_subscription(user["user_id"])
    
    if not sub.get("stripe_subscription_id"):
        raise HTTPException(status_code=400, detail="No subscription found. Please subscribe to a plan first at trustoffice.app/settings/billing.")
    
    try:
        stripe.Subscription.modify(
            sub["stripe_subscription_id"],
            cancel_at_period_end=False
        )
        
        await db.subscriptions.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        
        return {
            "status": "active",
            "message": "Your subscription has been reactivated."
        }
    except stripe.StripeError as e:
        logger.error(f"Stripe reactivate error: {e}")
        raise HTTPException(status_code=500, detail="Could not reactivate subscription. Please try again. If this continues, contact support@trustoffice.app.")


@router.post("/subscription/upgrade")
async def upgrade_subscription(user: dict = Depends(get_current_user)):
    """Upgrade from monthly to annual plan (legacy endpoint — kept for backward compat).
    
    New clients should use /subscription/change-plan for 3-tier changes.
    """
    sub = await get_or_create_subscription(user["user_id"])
    
    if not sub.get("stripe_subscription_id"):
        raise HTTPException(status_code=400, detail="No active subscription found. Please subscribe to a plan first at trustoffice.app/settings/billing.")
    
    # Determine current plan to find what "annual" means for them
    current_plan = sub.get("plan_type", "monthly")
    current_billing = sub.get("billing_period", "monthly" if current_plan in ("monthly", "trustee") else "annual")
    
    # Map to new tier system: legacy monthly/annual -> trustee
    if current_plan in ("monthly", "annual"):
        target_tier = "trustee"
    else:
        target_tier = current_plan  # keep same tier, just switch billing period
    
    target_price = PRICE_IDS.get((target_tier, "annual"))
    if not target_price:
        raise HTTPException(status_code=500, detail="Annual price not configured")
    
    try:
        stripe_sub = stripe.Subscription.retrieve(sub["stripe_subscription_id"])
        
        stripe.Subscription.modify(
            sub["stripe_subscription_id"],
            items=[{
                "id": stripe_sub["items"]["data"][0]["id"],
                "price": target_price
            }],
            proration_behavior="create_prorations"
        )
        
        await db.subscriptions.update_one(
            {"user_id": user["user_id"]},
            {"$set": {
                "plan_type": target_tier,
                "billing_period": "annual",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        # Send upgrade email
        if email_service.is_configured:
            try:
                await email_service.send_subscription_upgraded(
                    to_email=user["email"],
                    user_name=user.get("name", ""),
                    old_plan=f"{current_plan} ({current_billing})",
                    new_plan=f"{target_tier} (annual)"
                )
            except Exception as e:
                logger.error(f"Failed to send upgrade email: {e}")
        
        return {
            "status": "upgraded",
            "message": "Successfully upgraded to annual billing. You'll be charged the prorated difference.",
            "new_plan": target_tier,
            "billing_period": "annual"
        }
    except stripe.StripeError as e:
        logger.error(f"Stripe upgrade error: {e}")
        raise HTTPException(status_code=500, detail="Could not upgrade subscription. Please try again. If this continues, contact support@trustoffice.app.")


@router.post("/subscription/change-plan")
async def change_plan(request: ChangePlanRequest, user: dict = Depends(get_current_user)):
    """Change plan tier or billing period (3-tier system).
    
    Supports upgrades and downgrades between trustee/estate/advisor,
    and switching between monthly/annual billing.
    Uses Stripe proration for mid-cycle changes.
    """
    valid_plans = ["trustee", "estate", "advisor"]
    valid_periods = ["monthly", "annual"]
    
    if request.plan_type not in valid_plans:
        raise HTTPException(status_code=400, detail="Invalid plan type. Choose 'trustee', 'estate', or 'advisor'.")
    if request.billing_period not in valid_periods:
        raise HTTPException(status_code=400, detail="Invalid billing period. Choose 'monthly' or 'annual'.")
    
    sub = await get_or_create_subscription(user["user_id"])
    
    if not sub.get("stripe_subscription_id"):
        raise HTTPException(status_code=400, detail="No active subscription found. Please subscribe at trustoffice.app/settings/billing.")
    
    new_price_id = PRICE_IDS.get((request.plan_type, request.billing_period))
    if not new_price_id:
        raise HTTPException(status_code=500, detail=f"Price ID not configured for {request.plan_type}/{request.billing_period}")
    
    # Check if already on this plan
    current_plan = sub.get("plan_type", "")
    current_billing = sub.get("billing_period", "")
    if current_plan == request.plan_type and current_billing == request.billing_period:
        raise HTTPException(status_code=400, detail=f"You are already on the {request.plan_type} {request.billing_period} plan.")
    
    try:
        stripe_sub = stripe.Subscription.retrieve(sub["stripe_subscription_id"])
        old_plan_label = f"{current_plan} ({current_billing})" if current_billing else current_plan
        new_plan_label = f"{request.plan_type} ({request.billing_period})"
        
        stripe.Subscription.modify(
            sub["stripe_subscription_id"],
            items=[{
                "id": stripe_sub["items"]["data"][0]["id"],
                "price": new_price_id
            }],
            proration_behavior="create_prorations"
        )
        
        # Clear grandfathering only when changing to a different tier (not billing period switch within same tier)
        update_set = {
            "plan_type": request.plan_type,
            "billing_period": request.billing_period,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        if current_plan != request.plan_type:
            update_set["legacy_trust_limit"] = None
        
        await db.subscriptions.update_one(
            {"user_id": user["user_id"]},
            {"$set": update_set}
        )
        
        # Send upgrade/downgrade email
        if email_service.is_configured:
            try:
                await email_service.send_subscription_upgraded(
                    to_email=user["email"],
                    user_name=user.get("name", ""),
                    old_plan=old_plan_label,
                    new_plan=new_plan_label
                )
            except Exception as e:
                logger.error(f"Failed to send plan change email: {e}")
        
        return {
            "status": "changed",
            "message": f"Successfully changed to {request.plan_type} ({request.billing_period}). Proration will be applied to your next billing cycle.",
            "new_plan": request.plan_type,
            "billing_period": request.billing_period
        }
    except stripe.StripeError as e:
        logger.error(f"Stripe plan change error: {e}")
        raise HTTPException(status_code=500, detail="Could not change plan. Please try again or contact support@trustoffice.app.")


# ==================== STRIPE WEBHOOK ====================

@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events for subscription lifecycle"""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid webhook payload. This endpoint is for Stripe webhooks only.")
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature. The request could not be verified as coming from Stripe.")

    # Check if this event was already processed
    event_id = event.get("id")
    if event_id:
        existing = await db.webhook_events.find_one({"event_id": event_id})
        if existing:
            if existing.get("status") == "completed":
                return JSONResponse(content={"status": "already_processed"})
            # If "processing" or "failed", allow reprocessing
            logger.info(f"Webhook event {event_id} found in status '{existing.get('status')}' — reprocessing")
        # Record the event as processing
        await db.webhook_events.insert_one({
            "event_id": event_id,
            "type": event.get("type"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "processing"
        })

    event_type = event["type"]
    logger.info(f"Stripe webhook received: {event_type}")

    # Helper to get user info from stripe customer ID
    async def get_user_by_customer_id(customer_id: str):
        sub = await db.subscriptions.find_one({"stripe_customer_id": customer_id}, {"_id": 0})
        if sub:
            user = await db.users.find_one({"user_id": sub["user_id"]}, {"_id": 0})
            return user, sub
        return None, None

    # Helper to format date from timestamp
    def format_date(timestamp: int) -> str:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime('%B %d, %Y')

    # Helper to format amount
    def format_amount(amount_cents: int) -> str:
        return f"{amount_cents / 100:.2f}"

    try:
        # ========== CHECKOUT COMPLETED (New subscription) ==========
        if event_type == "checkout.session.completed":
            session = event["data"]["object"]
            user_id = session.get("metadata", {}).get("user_id")
            plan_type = session.get("metadata", {}).get("plan_type", "monthly")
            billing_period = session.get("metadata", {}).get("billing_period")
            
            # For legacy plans, billing_period wasn't in metadata — infer from plan_type
            if not billing_period and plan_type in ("monthly", "annual"):
                billing_period = plan_type

            if user_id:
                # Determine if this is a legacy plan that needs grandfathering
                update_set = {
                    "plan_type": plan_type,
                    "billing_period": billing_period,
                    "status": "active",
                    "stripe_subscription_id": session.get("subscription"),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
                # Grandfather legacy monthly/annual subscribers with 10-trust limit
                if plan_type in ("monthly", "annual"):
                    update_set["legacy_trust_limit"] = 10

                # Update subscription status
                await db.subscriptions.update_one(
                    {"user_id": user_id},
                    {
                        "$set": update_set,
                        "$unset": {
                            "gifted": "",
                            "gift_type": "",
                            "gift_start_date": "",
                            "gift_end_date": "",
                            "gifted_at": ""
                        }
                    },
                    upsert=True
                )

                # Update payment transaction
                await db.payment_transactions.update_one(
                    {"session_id": session["id"]},
                    {"$set": {"payment_status": "paid", "updated_at": datetime.now(timezone.utc).isoformat()}}
                )

                # Process referral conversion - apply reward to referrer
                try:
                    from routers.referrals import process_referral_conversion
                    referral_result = await process_referral_conversion(user_id)
                    if referral_result:
                        logger.info(f"Referral conversion processed for user {user_id}: {referral_result}")
                except Exception as e:
                    logger.error(f"Failed to process referral conversion: {e}")

                # Send activation email
                user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
                amount = str(int(PLAN_AMOUNTS.get((plan_type, billing_period), 79.00)))
                if user and email_service.is_configured:
                    try:
                        # Get subscription details from Stripe
                        stripe_sub = stripe.Subscription.retrieve(session.get("subscription"))
                        next_billing = format_date(stripe_sub.current_period_end)

                        await email_service.send_subscription_activated(
                            to_email=user["email"],
                            user_name=user.get("name", ""),
                            plan_type=plan_type,
                            amount=amount,
                            next_billing_date=next_billing,
                            legacy_trust_limit=10 if plan_type in ("monthly", "annual") else None
                        )

                        # Send admin notification about new purchase
                        await email_service.send_admin_new_purchase_notification(
                            customer_email=user["email"],
                            customer_name=user.get("name", ""),
                            plan_type=plan_type,
                            amount=amount
                        )
                    except Exception as e:
                        logger.error(f"Failed to send activation email: {e}")

                # Mark lead as subscribed in CRM (if they were captured as a lead first)
                if user:
                    try:
                        from routers.leads import mark_lead_as_subscribed
                        await mark_lead_as_subscribed(
                            email=user["email"],
                            user_id=user_id,
                        )
                    except Exception as e:
                        logger.error(f"Failed to mark lead as subscribed: {e}")

                # Add to Mailercloud paid members list
                if user:
                    try:
                        mailercloud_result = await add_to_paid_list(
                            email=user["email"],
                            name=user.get("name", "")
                        )
                        if mailercloud_result and mailercloud_result.get("success"):
                            logger.info(f"Added {user['email']} to Mailercloud paid list")
                        else:
                            logger.warning(f"Could not add {user['email']} to Mailercloud: {mailercloud_result}")
                    except Exception as e:
                        logger.error(f"Failed to add to Mailercloud paid list: {e}")

        # ========== SUBSCRIPTION UPDATED ==========
        elif event_type == "customer.subscription.updated":
            subscription = event["data"]["object"]
            previous_attributes = event["data"].get("previous_attributes", {})
            customer_id = subscription.get("customer")

            user, sub = await get_user_by_customer_id(customer_id)
            if not user:
                return {"status": "ok", "message": "User not found"}

            # Check if plan changed (upgrade)
            if "items" in previous_attributes:
                old_price = previous_attributes.get("items", {}).get("data", [{}])[0].get("price", {}).get("id")
                new_price = subscription.get("items", {}).get("data", [{}])[0].get("price", {}).get("id")

                if old_price and new_price and old_price != new_price:
                    # Determine plan types using new + legacy lookup
                    old_plan_info = PRICE_ID_TO_PLAN.get(old_price)
                    if not old_plan_info:
                        legacy = LEGACY_PRICE_MAP.get(old_price)
                        old_plan_info = (legacy[0], legacy[1]) if legacy else ("monthly", None)
                    new_plan_info = PRICE_ID_TO_PLAN.get(new_price)
                    if not new_plan_info:
                        legacy = LEGACY_PRICE_MAP.get(new_price)
                        new_plan_info = (legacy[0], legacy[1]) if legacy else ("monthly", None)
                    
                    old_plan = old_plan_info[0]
                    new_plan = new_plan_info[0]
                    new_billing_period = new_plan_info[1]

                    # Build update set
                    update_set = {
                        "plan_type": new_plan,
                        "billing_period": new_billing_period,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                    # If migrating from a legacy plan, preserve the 10-trust grandfathering
                    old_price_in_legacy = old_price in LEGACY_PRICE_MAP
                    new_price_in_legacy = new_price in LEGACY_PRICE_MAP
                    if old_price_in_legacy and new_price_in_legacy:
                        update_set["legacy_trust_limit"] = 10

                    # Update database
                    await db.subscriptions.update_one(
                        {"user_id": user["user_id"]},
                        {"$set": update_set}
                    )

                    # Send upgrade email
                    if email_service.is_configured:
                        try:
                            await email_service.send_subscription_upgraded(
                                to_email=user["email"],
                                user_name=user.get("name", ""),
                                old_plan=old_plan,
                                new_plan=new_plan
                            )
                        except Exception as e:
                            logger.error(f"Failed to send upgrade email: {e}")

            # Check if cancel_at_period_end changed (cancellation scheduled)
            if "cancel_at_period_end" in previous_attributes:
                if subscription.get("cancel_at_period_end") and not previous_attributes.get("cancel_at_period_end"):
                    # Subscription scheduled for cancellation
                    access_until = format_date(subscription.get("current_period_end"))

                    if email_service.is_configured:
                        try:
                            await email_service.send_subscription_canceled(
                                to_email=user["email"],
                                user_name=user.get("name", ""),
                                access_until=access_until
                            )
                        except Exception as e:
                            logger.error(f"Failed to send cancellation email: {e}")

        # ========== SUBSCRIPTION DELETED (fully canceled) ==========
        elif event_type == "customer.subscription.deleted":
            subscription = event["data"]["object"]
            await db.subscriptions.update_one(
                {"stripe_subscription_id": subscription["id"]},
                {"$set": {
                    "status": "canceled",
                    "stripe_subscription_id": None,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )

        # ========== INVOICE PAID (renewal) ==========
        elif event_type == "invoice.paid":
            invoice = event["data"]["object"]
            customer_id = invoice.get("customer")

            # Skip if this is the first invoice (handled by checkout.session.completed)
            if invoice.get("billing_reason") == "subscription_create":
                return {"status": "ok", "message": "Initial invoice, skipping"}

            user, sub = await get_user_by_customer_id(customer_id)
            if not user:
                return {"status": "ok", "message": "User not found"}

            # Ensure subscription is active
            await db.subscriptions.update_one(
                {"user_id": user["user_id"]},
                {"$set": {
                    "status": "active",
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )

            # Send renewal email
            if email_service.is_configured and invoice.get("billing_reason") == "subscription_cycle":
                try:
                    # Get next billing date from subscription
                    stripe_sub = stripe.Subscription.retrieve(invoice.get("subscription"))
                    next_billing = format_date(stripe_sub.current_period_end)
                    amount = format_amount(invoice.get("amount_paid", 0))
                    plan_type = sub.get("plan_type", "monthly")

                    await email_service.send_subscription_renewed(
                        to_email=user["email"],
                        user_name=user.get("name", ""),
                        plan_type=plan_type,
                        amount=amount,
                        next_billing_date=next_billing
                    )
                except Exception as e:
                    logger.error(f"Failed to send renewal email: {e}")

        # ========== INVOICE PAYMENT FAILED ==========
        elif event_type == "invoice.payment_failed":
            invoice = event["data"]["object"]
            customer_id = invoice.get("customer")

            user, sub = await get_user_by_customer_id(customer_id)
            if user:
                # Update subscription status
                await db.subscriptions.update_one(
                    {"stripe_customer_id": customer_id},
                    {"$set": {
                        "status": "past_due",
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )

                # Send payment failed email
                if email_service.is_configured:
                    try:
                        amount = format_amount(invoice.get("amount_due", 0))
                        next_attempt = invoice.get("next_payment_attempt")
                        retry_date = format_date(next_attempt) if next_attempt else None

                        await email_service.send_payment_failed(
                            to_email=user["email"],
                            user_name=user.get("name", ""),
                            amount=amount,
                            retry_date=retry_date
                        )
                    except Exception as e:
                        logger.error(f"Failed to send payment failed email: {e}")

    except Exception as e:
        if event_id:
            await db.webhook_events.update_one(
                {"event_id": event_id},
                {"$set": {"status": "failed", "error": str(e)[:500]}}
            )
        raise

    # Mark the event as completed
    if event_id:
        await db.webhook_events.update_one(
            {"event_id": event_id},
            {"$set": {"status": "completed", "processed_at": datetime.now(timezone.utc).isoformat()}}
        )

    return {"status": "ok", "event_type": event_type}
