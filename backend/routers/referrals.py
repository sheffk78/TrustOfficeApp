# Referrals router - handles refer a friend functionality
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid
import secrets
import string
import logging
import os

import stripe

from database import db
from dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["referrals"])

# Stripe Config
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')

# Referral discount: 50% off (referee)
REFERRAL_DISCOUNT_PERCENT = 50

# Referrer reward: flat $50 credit
REFERRAL_CREDIT_AMOUNT = 50  # USD
REFERRAL_CREDIT_LIFETIME_CAP = 500  # USD
REFERRAL_CREDIT_EXPIRY_MONTHS = 12


def generate_referral_code(name: str) -> str:
    """Generate a unique referral code based on user's name"""
    # Take first 4 chars of name (uppercase, alphanumeric only)
    name_part = ''.join(c for c in name.upper() if c.isalnum())[:4]
    if len(name_part) < 4:
        name_part = name_part.ljust(4, 'X')
    
    # Add 4 random alphanumeric chars
    random_part = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
    
    return f"{name_part}{random_part}"


async def get_or_create_stripe_coupon() -> str:
    """Get or create the 50% referral coupon in Stripe"""
    coupon_id = "REFERRAL50"
    
    try:
        # Try to retrieve existing coupon
        coupon = stripe.Coupon.retrieve(coupon_id)
        return coupon.id
    except stripe.InvalidRequestError:
        # Coupon doesn't exist, create it
        try:
            coupon = stripe.Coupon.create(
                id=coupon_id,
                percent_off=REFERRAL_DISCOUNT_PERCENT,
                duration="once",
                name="Referral 50% Off First Payment"
            )
            logger.info(f"Created Stripe coupon: {coupon_id}")
            return coupon.id
        except stripe.StripeError as e:
            logger.error(f"Failed to create Stripe coupon: {e}")
            raise


# ==================== REFERRAL ENDPOINTS ====================

@router.get("/referrals/my-code")
async def get_my_referral_code(user: dict = Depends(get_current_user)):
    """Get the current user's referral code, creating one if it doesn't exist"""
    
    # Check if user already has a referral code
    referral = await db.referral_codes.find_one(
        {"user_id": user["user_id"]},
        {"_id": 0}
    )
    
    if referral:
        return {
            "referral_code": referral["code"],
            "referral_link": f"{os.environ.get('FRONTEND_URL', '')}/register?ref={referral['code']}",
            "created_at": referral["created_at"]
        }
    
    # Generate new referral code
    code = generate_referral_code(user.get("name", "USER"))
    
    # Ensure uniqueness
    attempts = 0
    while await db.referral_codes.find_one({"code": code}):
        code = generate_referral_code(user.get("name", "USER"))
        attempts += 1
        if attempts > 10:
            code = f"REF{secrets.token_hex(4).upper()}"
            break
    
    now = datetime.now(timezone.utc).isoformat()
    
    referral_doc = {
        "referral_id": f"ref_{uuid.uuid4().hex[:12]}",
        "user_id": user["user_id"],
        "code": code,
        "created_at": now,
        "updated_at": now
    }
    
    await db.referral_codes.insert_one(referral_doc)
    
    return {
        "referral_code": code,
        "referral_link": f"{os.environ.get('FRONTEND_URL', '')}/register?ref={code}",
        "created_at": now
    }


@router.get("/referrals/stats")
async def get_referral_stats(user: dict = Depends(get_current_user)):
    """Get referral statistics for the current user"""
    
    # Get referral code
    referral = await db.referral_codes.find_one(
        {"user_id": user["user_id"]},
        {"_id": 0}
    )
    
    if not referral:
        return {
            "referral_code": None,
            "total_referred": 0,
            "pending_referrals": 0,
            "successful_conversions": 0,
            "rewards_earned": 0,
            "referrals": []
        }
    
    # Get all referral tracking records for this referrer
    referrals_cursor = db.referral_tracking.find(
        {"referrer_user_id": user["user_id"]},
        {"_id": 0}
    ).sort("created_at", -1)
    
    referrals = await referrals_cursor.to_list(length=100)
    
    # Calculate stats
    total_referred = len(referrals)
    pending_referrals = sum(1 for r in referrals if r.get("status") == "pending")
    successful_conversions = sum(1 for r in referrals if r.get("status") == "converted")
    rewards_earned = sum(1 for r in referrals if r.get("referrer_reward_applied"))
    
    # Get referee names for the list
    referral_list = []
    for r in referrals[:10]:  # Show last 10
        referee = await db.users.find_one(
            {"user_id": r["referee_user_id"]},
            {"_id": 0, "name": 1, "email": 1}
        )
        referral_list.append({
            "name": referee.get("name", "Unknown") if referee else "Unknown",
            "email": referee.get("email", "")[:3] + "***" if referee else "",  # Partial email for privacy
            "status": r.get("status", "pending"),
            "signed_up_at": r.get("created_at"),
            "converted_at": r.get("converted_at"),
            "referrer_reward_applied": r.get("referrer_reward_applied", False)
        })
    
    # Calculate referral credit summary
    credit_cursor = db.referral_credits.find(
        {"user_id": user["user_id"]},
        {"_id": 0}
    )
    all_credits = await credit_cursor.to_list(length=100)
    
    available_credits = [c for c in all_credits if c["status"] == "pending"]
    available_credit_total = sum(c["amount"] for c in available_credits)
    lifetime_credits = sum(
        c["amount"] for c in all_credits 
        if c["status"] in ("pending", "applied")
    )
    
    # Find soonest expiring pending credit
    credits_expiring = None
    if available_credits:
        soonest = min(available_credits, key=lambda c: c["expires_at"])
        credits_expiring = {
            "credit_id": soonest["credit_id"],
            "amount": soonest["amount"],
            "expires_at": soonest["expires_at"]
        }
    
    return {
        "referral_code": referral["code"],
        "referral_link": f"{os.environ.get('FRONTEND_URL', '')}/register?ref={referral['code']}",
        "total_referred": total_referred,
        "pending_referrals": pending_referrals,
        "successful_conversions": successful_conversions,
        "rewards_earned": rewards_earned,
        "referrals": referral_list,
        "available_credit": available_credit_total,
        "lifetime_credits_earned": lifetime_credits,
        "credits_expiring": credits_expiring,
        "lifetime_cap": REFERRAL_CREDIT_LIFETIME_CAP
    }


@router.get("/referrals/validate/{code}")
async def validate_referral_code(code: str):
    """Validate a referral code (public endpoint for signup page)"""
    
    referral = await db.referral_codes.find_one(
        {"code": code.upper()},
        {"_id": 0}
    )
    
    if not referral:
        return {
            "valid": False,
            "message": "Invalid referral code"
        }
    
    # Get referrer's name
    referrer = await db.users.find_one(
        {"user_id": referral["user_id"]},
        {"_id": 0, "name": 1}
    )
    
    return {
        "valid": True,
        "referrer_name": referrer.get("name", "A friend") if referrer else "A friend",
        "discount_percent": REFERRAL_DISCOUNT_PERCENT,
        "message": f"You'll get {REFERRAL_DISCOUNT_PERCENT}% off your first payment!"
    }


@router.post("/referrals/track")
async def track_referral(
    referee_user_id: str,
    referral_code: str
):
    """
    Track when a new user signs up with a referral code.
    Called internally after user registration.
    """
    
    # Find the referrer
    referral = await db.referral_codes.find_one(
        {"code": referral_code.upper()},
        {"_id": 0}
    )
    
    if not referral:
        logger.warning(f"Invalid referral code used: {referral_code}")
        return {"tracked": False, "reason": "invalid_code"}
    
    # Prevent self-referral
    if referral["user_id"] == referee_user_id:
        logger.warning(f"Self-referral attempt: {referee_user_id}")
        return {"tracked": False, "reason": "self_referral"}
    
    # Check if this user was already referred
    existing = await db.referral_tracking.find_one(
        {"referee_user_id": referee_user_id},
        {"_id": 0}
    )
    
    if existing:
        logger.info(f"User {referee_user_id} already has a referral record")
        return {"tracked": False, "reason": "already_referred"}
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Create tracking record
    tracking_doc = {
        "tracking_id": f"rtrack_{uuid.uuid4().hex[:12]}",
        "referrer_user_id": referral["user_id"],
        "referee_user_id": referee_user_id,
        "referral_code": referral_code.upper(),
        "status": "pending",  # pending -> converted (when referee subscribes)
        "referee_discount_applied": False,
        "referrer_reward_applied": False,
        "created_at": now,
        "updated_at": now
    }
    
    await db.referral_tracking.insert_one(tracking_doc)
    
    logger.info(f"Referral tracked: {referral['user_id']} referred {referee_user_id}")
    
    return {"tracked": True, "referrer_user_id": referral["user_id"]}


async def apply_referral_discount_to_checkout(user_id: str) -> Optional[str]:
    """
    Check if user has a pending referral and return the coupon ID if so.
    Called when creating a checkout session.
    """
    
    # Check if this user was referred
    tracking = await db.referral_tracking.find_one(
        {"referee_user_id": user_id, "referee_discount_applied": False},
        {"_id": 0}
    )
    
    if not tracking:
        return None
    
    try:
        # Ensure the coupon exists
        coupon_id = await get_or_create_stripe_coupon()
        return coupon_id
    except Exception as e:
        logger.error(f"Failed to get/create referral coupon: {e}")
        return None


async def mark_referee_discount_applied(user_id: str):
    """Mark that the referee's discount has been applied"""
    await db.referral_tracking.update_one(
        {"referee_user_id": user_id},
        {"$set": {
            "referee_discount_applied": True,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )


async def process_referral_conversion(referee_user_id: str):
    """
    Process a referral conversion when the referee subscribes.
    Marks the referral as converted and issues a $50 credit to the referrer.
    Called from Stripe webhook when subscription is activated.
    """
    
    # Find the referral tracking record
    tracking = await db.referral_tracking.find_one(
        {"referee_user_id": referee_user_id, "status": "pending"},
        {"_id": 0}
    )
    
    if not tracking:
        logger.info(f"No pending referral for user {referee_user_id}")
        return None
    
    now = datetime.now(timezone.utc)
    
    # Mark as converted
    await db.referral_tracking.update_one(
        {"tracking_id": tracking["tracking_id"]},
        {"$set": {
            "status": "converted",
            "converted_at": now,
            "updated_at": now
        }}
    )
    
    # Check idempotency — if a credit already exists for this referral, skip
    existing_credit = await db.referral_credits.find_one(
        {"source_referral_id": tracking["tracking_id"]},
        {"_id": 0}
    )
    if existing_credit:
        logger.info(f"Credit already issued for referral {tracking['tracking_id']}")
        return {
            "referrer_user_id": tracking["referrer_user_id"],
            "reward_applied": False,
            "reason": "credit_already_issued"
        }
    
    # Check $500 lifetime cap (count all non-clawed-back, non-expired credits)
    pipeline = [
        {"$match": {
            "user_id": tracking["referrer_user_id"],
            "status": {"$in": ["pending", "applied"]}
        }},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]
    cap_result = await db.referral_credits.aggregate(pipeline).to_list(length=1)
    current_lifetime = cap_result[0]["total"] if cap_result else 0
    
    if current_lifetime + REFERRAL_CREDIT_AMOUNT > REFERRAL_CREDIT_LIFETIME_CAP:
        logger.warning(
            f"Referrer {tracking['referrer_user_id']} hit lifetime cap "
            f"(${current_lifetime}/${REFERRAL_CREDIT_LIFETIME_CAP})"
        )
        await db.referral_tracking.update_one(
            {"tracking_id": tracking["tracking_id"]},
            {"$set": {
                "referrer_reward_applied": False,
                "referrer_reward_skipped_reason": "lifetime_cap_reached",
                "updated_at": now
            }}
        )
        return {
            "referrer_user_id": tracking["referrer_user_id"],
            "reward_applied": False,
            "reason": "lifetime_cap_reached"
        }
    
    # Issue the $50 credit
    expires_at = now + timedelta(days=365)  # 12 months
    credit_doc = {
        "credit_id": f"cred_{uuid.uuid4().hex[:12]}",
        "user_id": tracking["referrer_user_id"],
        "amount": REFERRAL_CREDIT_AMOUNT,
        "source_referral_id": tracking["tracking_id"],
        "status": "pending",
        "issued_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "applied_at": None,
        "clawback_reason": None
    }
    
    await db.referral_credits.insert_one(credit_doc)
    
    # Mark reward as applied
    await db.referral_tracking.update_one(
        {"tracking_id": tracking["tracking_id"]},
        {"$set": {
            "referrer_reward_applied": True,
            "referrer_reward_applied_at": now.isoformat(),
            "updated_at": now
        }}
    )
    
    logger.info(
        f"Issued ${REFERRAL_CREDIT_AMOUNT} credit to referrer "
        f"{tracking['referrer_user_id']} for referral {tracking['tracking_id']}"
    )
    
    return {
        "referrer_user_id": tracking["referrer_user_id"],
        "reward_applied": True,
        "credit_id": credit_doc["credit_id"],
        "amount": REFERRAL_CREDIT_AMOUNT
    }


async def apply_pending_credits_to_invoice(user_id: str, invoice_id: str, billing_period: str = "monthly"):
    """
    Apply pending referral credits to a Stripe invoice as negative invoice items.
    Called when the referrer's invoice is created.
    
    billing_period: "monthly" or "annual"
    - Monthly: max 1 credit per billing cycle
    - Annual: unlimited credits, compound
    """
    
    # Get the Stripe invoice to know the amount
    try:
        invoice = stripe.Invoice.retrieve(invoice_id)
    except stripe.StripeError as e:
        logger.error(f"Failed to retrieve invoice {invoice_id}: {e}")
        return {"applied": 0, "reason": "invoice_retrieval_failed"}
    
    invoice_total = invoice.total  # in cents
    if invoice_total <= 0:
        return {"applied": 0, "reason": "zero_invoice"}
    
    # Get pending credits, oldest first
    now = datetime.now(timezone.utc)
    cursor = db.referral_credits.find(
        {
            "user_id": user_id,
            "status": "pending",
            "expires_at": {"$gt": now.isoformat()}
        },
        {"_id": 0}
    ).sort("issued_at", 1)
    
    credits = await cursor.to_list(length=20)
    
    if not credits:
        return {"applied": 0, "reason": "no_pending_credits"}
    
    # Monthly: max 1 credit per billing cycle
    if billing_period == "monthly":
        # Check if a credit was already applied in this billing cycle
        # by checking for applied credits with applied_at within this period
        period_start = datetime.fromtimestamp(invoice.period_start, tz=timezone.utc)
        period_end = datetime.fromtimestamp(invoice.period_end, tz=timezone.utc)
        
        already_applied = await db.referral_credits.find_one({
            "user_id": user_id,
            "status": "applied",
            "applied_at": {
                "$gte": period_start.isoformat(),
                "$lt": period_end.isoformat()
            }
        })
        
        if already_applied:
            logger.info(f"Monthly cap reached for user {user_id}, skipping credit application")
            return {"applied": 0, "reason": "monthly_cap_reached"}
        
        # Apply only 1 credit
        credits = credits[:1]
    
    # For annual: apply all credits up to invoice total
    applied_amount = 0
    applied_count = 0
    
    for credit in credits:
        credit_amount_cents = int(credit["amount"] * 100)
        
        if applied_amount + credit_amount_cents > invoice_total:
            # Credit exceeds remaining invoice amount — skip, leave pending
            break
        
        try:
            # Create negative invoice item
            stripe.InvoiceItem.create(
                customer=invoice.customer,
                invoice=invoice_id,
                amount=-credit_amount_cents,
                currency="usd",
                description=f"Referral credit — ${credit['amount']} off",
                metadata={
                    "credit_id": credit["credit_id"],
                    "source_referral_id": credit.get("source_referral_id", "")
                }
            )
            
            # Mark credit as applied
            await db.referral_credits.update_one(
                {"credit_id": credit["credit_id"]},
                {"$set": {
                    "status": "applied",
                    "applied_at": now.isoformat()
                }}
            )
            
            applied_amount += credit_amount_cents
            applied_count += 1
            logger.info(f"Applied credit {credit['credit_id']} (${credit['amount']}) to invoice {invoice_id}")
            
        except stripe.StripeError as e:
            logger.error(f"Failed to create negative invoice item for credit {credit['credit_id']}: {e}")
            break
    
    return {
        "applied": applied_count,
        "applied_amount_cents": applied_amount,
        "billing_period": billing_period
    }


async def clawback_credit(referee_user_id: str, reason: str = "referee_refunded"):
    """
    Claw back a referrer's credit when the referee gets a refund.
    Sets the credit status to clawed_back and logs the reason.
    """
    
    # Find the referral tracking record
    tracking = await db.referral_tracking.find_one(
        {"referee_user_id": referee_user_id, "status": "converted"},
        {"_id": 0}
    )
    
    if not tracking:
        logger.info(f"No converted referral found for referee {referee_user_id}")
        return {"clawed_back": False, "reason": "no_converted_referral"}
    
    # Find the credit issued for this referral
    credit = await db.referral_credits.find_one(
        {"source_referral_id": tracking["tracking_id"]},
        {"_id": 0}
    )
    
    if not credit:
        logger.info(f"No credit found for referral {tracking['tracking_id']}")
        return {"clawed_back": False, "reason": "no_credit_found"}
    
    if credit["status"] == "clawed_back":
        logger.info(f"Credit {credit['credit_id']} already clawed back")
        return {"clawed_back": False, "reason": "already_clawed_back"}
    
    now = datetime.now(timezone.utc)
    
    await db.referral_credits.update_one(
        {"credit_id": credit["credit_id"]},
        {"$set": {
            "status": "clawed_back",
            "clawback_reason": reason,
            "clawed_back_at": now.isoformat()
        }}
    )
    
    logger.info(
        f"Clawed back credit {credit['credit_id']} (${credit['amount']}) "
        f"for referral {tracking['tracking_id']}, reason: {reason}"
    )
    
    return {
        "clawed_back": True,
        "credit_id": credit["credit_id"],
        "amount": credit["amount"],
        "reason": reason
    }


async def expire_credits():
    """
    Mark all pending credits older than 12 months as expired.
    Should be called periodically (e.g., daily via cron or scheduled task).
    """
    now = datetime.now(timezone.utc)
    
    result = await db.referral_credits.update_many(
        {
            "status": "pending",
            "expires_at": {"$lt": now.isoformat()}
        },
        {"$set": {
            "status": "expired",
            "expired_at": now.isoformat()
        }}
    )
    
    if result.modified_count > 0:
        logger.info(f"Expired {result.modified_count} pending referral credits")
    
    return {"expired": result.modified_count}


@router.get("/referrals/credits")
async def get_referral_credits(user: dict = Depends(get_current_user)):
    """Get the current user's referral credit ledger."""
    
    cursor = db.referral_credits.find(
        {"user_id": user["user_id"]},
        {"_id": 0}
    ).sort("issued_at", -1)
    
    credits = await cursor.to_list(length=100)
    
    # Calculate summary
    available_credits = [c for c in credits if c["status"] == "pending"]
    available_total = sum(c["amount"] for c in available_credits)
    
    lifetime_earned = sum(
        c["amount"] for c in credits 
        if c["status"] in ("pending", "applied")
    )
    
    # Find soonest expiring credit
    expiring = None
    if available_credits:
        soonest = min(available_credits, key=lambda c: c["expires_at"])
        expiring = {
            "credit_id": soonest["credit_id"],
            "amount": soonest["amount"],
            "expires_at": soonest["expires_at"]
        }
    
    return {
        "credits": credits,
        "available_credit": available_total,
        "lifetime_credits_earned": lifetime_earned,
        "credits_expiring": expiring,
        "lifetime_cap": REFERRAL_CREDIT_LIFETIME_CAP
    }
