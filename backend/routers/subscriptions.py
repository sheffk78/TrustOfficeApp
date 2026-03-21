# Subscriptions router - handles Stripe payments and subscription management
from fastapi import APIRouter, HTTPException, Depends, Request
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid
import logging
import os

import stripe

from database import db
from dependencies import (
    get_current_user, 
    get_subscription_state, 
    get_user_features,
    TRIAL_DAYS
)
from models import SubscriptionResponse, CheckoutRequest, PortalRequest

# Import email service
from email_service import email_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["subscriptions"])

# Stripe Config
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')
STRIPE_MONTHLY_PRICE_ID = os.environ.get('STRIPE_MONTHLY_PRICE_ID')
STRIPE_ANNUAL_PRICE_ID = os.environ.get('STRIPE_ANNUAL_PRICE_ID')


# ==================== HELPER FUNCTIONS ====================

async def get_or_create_subscription(user_id: str) -> dict:
    """Get or create subscription for a user"""
    sub = await db.subscriptions.find_one({"user_id": user_id}, {"_id": 0})
    
    if not sub:
        now = datetime.now(timezone.utc)
        sub = {
            "subscription_id": f"sub_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "plan_type": "trial",
            "status": "trialing",
            "trial_start_date": now.isoformat(),
            "trial_end_date": (now + timedelta(days=TRIAL_DAYS)).isoformat(),
            "stripe_customer_id": None,
            "stripe_subscription_id": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat()
        }
        await db.subscriptions.insert_one(sub)
    
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
                if price_id == STRIPE_ANNUAL_PRICE_ID:
                    result["plan_type"] = "annual"
                elif price_id == STRIPE_MONTHLY_PRICE_ID:
                    result["plan_type"] = "monthly"
            
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
        - plan_type: "trial", "monthly", "annual"
        - status: "trialing", "active", "past_due", "canceled", "expired"
        - is_trial: boolean
        - is_active: boolean
        - is_read_only: boolean (determines if write operations are blocked)
        - trial_days_remaining: int or null
    """
    state = await get_subscription_state(user["user_id"])
    return state.model_dump()


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
    if checkout.plan_type not in ["monthly", "annual"]:
        raise HTTPException(status_code=400, detail="Invalid plan type")
    
    price_id = STRIPE_MONTHLY_PRICE_ID if checkout.plan_type == "monthly" else STRIPE_ANNUAL_PRICE_ID
    
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
            "metadata": {"user_id": user["user_id"], "plan_type": checkout.plan_type},
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
        
        # If no referral discount and a specific promotion code is provided, try to apply it
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
            "amount": 79.00 if checkout.plan_type == "monthly" else 790.00,
            "currency": "usd",
            "plan_type": checkout.plan_type,
            "payment_status": "initiated",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        })
        
        return {"checkout_url": session.url, "session_id": session.id}
        
    except stripe.StripeError as e:
        logger.error(f"Stripe error: {e}")
        raise HTTPException(status_code=500, detail="Payment service unavailable")


@router.get("/subscription/verify-payment")
async def verify_payment(session_id: str, user: dict = Depends(get_current_user)):
    """Verify a checkout session and update subscription"""
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        
        if session.payment_status == "paid":
            plan_type = session.metadata.get("plan_type", "monthly")
            
            # Update subscription
            await db.subscriptions.update_one(
                {"user_id": user["user_id"]},
                {"$set": {
                    "plan_type": plan_type,
                    "status": "active",
                    "stripe_subscription_id": session.subscription,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
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
        raise HTTPException(status_code=500, detail="Payment verification failed")


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
        raise HTTPException(status_code=500, detail="Could not create billing portal")


@router.post("/subscription/cancel")
async def cancel_subscription(user: dict = Depends(get_current_user)):
    """Cancel subscription at end of current billing period"""
    sub = await get_or_create_subscription(user["user_id"])
    
    if not sub.get("stripe_subscription_id"):
        raise HTTPException(status_code=400, detail="No active subscription found")
    
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
        raise HTTPException(status_code=500, detail="Could not cancel subscription")


@router.post("/subscription/reactivate")
async def reactivate_subscription(user: dict = Depends(get_current_user)):
    """Reactivate a subscription that was set to cancel at period end"""
    sub = await get_or_create_subscription(user["user_id"])
    
    if not sub.get("stripe_subscription_id"):
        raise HTTPException(status_code=400, detail="No subscription found")
    
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
        raise HTTPException(status_code=500, detail="Could not reactivate subscription")


@router.post("/subscription/upgrade")
async def upgrade_subscription(user: dict = Depends(get_current_user)):
    """Upgrade from monthly to annual plan"""
    sub = await get_or_create_subscription(user["user_id"])
    
    if not sub.get("stripe_subscription_id"):
        raise HTTPException(status_code=400, detail="No active subscription found")
    
    if sub.get("plan_type") == "annual":
        raise HTTPException(status_code=400, detail="Already on annual plan")
    
    try:
        # Get current subscription
        stripe_sub = stripe.Subscription.retrieve(sub["stripe_subscription_id"])
        
        # Update to annual price
        stripe.Subscription.modify(
            sub["stripe_subscription_id"],
            items=[{
                "id": stripe_sub["items"]["data"][0]["id"],
                "price": STRIPE_ANNUAL_PRICE_ID
            }],
            proration_behavior="create_prorations"
        )
        
        await db.subscriptions.update_one(
            {"user_id": user["user_id"]},
            {"$set": {
                "plan_type": "annual",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        # Send upgrade email
        if email_service.is_configured:
            try:
                await email_service.send_subscription_upgraded(
                    to_email=user["email"],
                    user_name=user.get("name", ""),
                    old_plan="monthly",
                    new_plan="annual"
                )
            except Exception as e:
                logger.error(f"Failed to send upgrade email: {e}")
        
        return {
            "status": "upgraded",
            "message": "Successfully upgraded to annual plan. You'll be charged the prorated difference.",
            "new_plan": "annual"
        }
    except stripe.StripeError as e:
        logger.error(f"Stripe upgrade error: {e}")
        raise HTTPException(status_code=500, detail="Could not upgrade subscription")


# ==================== STRIPE WEBHOOK ====================

@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events for subscription lifecycle"""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    
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
    
    # ========== CHECKOUT COMPLETED (New subscription) ==========
    if event_type == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("metadata", {}).get("user_id")
        plan_type = session.get("metadata", {}).get("plan_type", "monthly")
        
        if user_id:
            # Update subscription status
            await db.subscriptions.update_one(
                {"user_id": user_id},
                {"$set": {
                    "plan_type": plan_type,
                    "status": "active",
                    "stripe_subscription_id": session.get("subscription"),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
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
            if user and email_service.is_configured:
                try:
                    # Get subscription details from Stripe
                    stripe_sub = stripe.Subscription.retrieve(session.get("subscription"))
                    next_billing = format_date(stripe_sub.current_period_end)
                    amount = "790" if plan_type == "annual" else "79"
                    
                    await email_service.send_subscription_activated(
                        to_email=user["email"],
                        user_name=user.get("name", ""),
                        plan_type=plan_type,
                        amount=amount,
                        next_billing_date=next_billing
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
                # Determine plan types
                old_plan = "annual" if old_price == STRIPE_ANNUAL_PRICE_ID else "monthly"
                new_plan = "annual" if new_price == STRIPE_ANNUAL_PRICE_ID else "monthly"
                
                # Update database
                await db.subscriptions.update_one(
                    {"user_id": user["user_id"]},
                    {"$set": {
                        "plan_type": new_plan,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
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
    
    return {"status": "ok", "event_type": event_type}
