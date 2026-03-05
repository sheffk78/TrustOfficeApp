# Referrals router - handles refer a friend functionality
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
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

# Referral discount: 50% off
REFERRAL_DISCOUNT_PERCENT = 50


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
                name="Referral Discount - 50% Off First Payment"
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
    
    return {
        "referral_code": referral["code"],
        "referral_link": f"{os.environ.get('FRONTEND_URL', '')}/register?ref={referral['code']}",
        "total_referred": total_referred,
        "pending_referrals": pending_referrals,
        "successful_conversions": successful_conversions,
        "rewards_earned": rewards_earned,
        "referrals": referral_list
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
    Marks the referral as converted and applies reward to referrer.
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
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Mark as converted
    await db.referral_tracking.update_one(
        {"tracking_id": tracking["tracking_id"]},
        {"$set": {
            "status": "converted",
            "converted_at": now,
            "updated_at": now
        }}
    )
    
    # Get referrer's subscription to apply their reward
    referrer_sub = await db.subscriptions.find_one(
        {"user_id": tracking["referrer_user_id"]},
        {"_id": 0}
    )
    
    if referrer_sub and referrer_sub.get("stripe_subscription_id"):
        try:
            # Apply 50% discount to referrer's next invoice
            coupon_id = await get_or_create_stripe_coupon()
            
            # Apply coupon to the referrer's subscription for next billing
            stripe.Subscription.modify(
                referrer_sub["stripe_subscription_id"],
                coupon=coupon_id
            )
            
            # Mark reward as applied
            await db.referral_tracking.update_one(
                {"tracking_id": tracking["tracking_id"]},
                {"$set": {
                    "referrer_reward_applied": True,
                    "referrer_reward_applied_at": now,
                    "updated_at": now
                }}
            )
            
            logger.info(f"Applied referral reward to referrer {tracking['referrer_user_id']}")
            
            return {
                "referrer_user_id": tracking["referrer_user_id"],
                "reward_applied": True
            }
            
        except stripe.StripeError as e:
            logger.error(f"Failed to apply referrer reward: {e}")
            
            # Still mark conversion even if reward fails
            return {
                "referrer_user_id": tracking["referrer_user_id"],
                "reward_applied": False,
                "error": str(e)
            }
    else:
        # Referrer doesn't have active subscription yet
        # Store pending reward for when they subscribe
        await db.referral_tracking.update_one(
            {"tracking_id": tracking["tracking_id"]},
            {"$set": {
                "referrer_reward_pending": True,
                "updated_at": now
            }}
        )
        
        logger.info(f"Referrer {tracking['referrer_user_id']} reward pending (no active subscription)")
        
        return {
            "referrer_user_id": tracking["referrer_user_id"],
            "reward_applied": False,
            "reward_pending": True
        }
