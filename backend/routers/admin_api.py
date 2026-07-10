"""
Admin API - Programmatic access for AI agents and automation tools.

Authentication: API Key via X-Admin-API-Key header
Rate Limit: 100 requests per minute
Audit: All actions logged to admin_api_audit collection

Endpoints:
- GET  /admin-api/stats/daily     - Daily statistics (new users, trials, purchases)
- GET  /admin-api/stats/summary   - Overall summary statistics
- GET  /admin-api/users           - List users with filters
- GET  /admin-api/users/{user_id} - Get specific user details
- POST /admin-api/users/{user_id}/extend-trial      - Extend trial period
- POST /admin-api/users/{user_id}/gift-subscription - Gift subscription
- POST /admin-api/users/{user_id}/grant-stats      - Grant stats access
- POST /admin-api/subscriptions/{user_id}/fix      - Fix subscription fields
"""

from fastapi import APIRouter, HTTPException, Depends, Request, Query
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
import re
import secrets
from typing import Optional, List
import os
import logging
import uuid
from collections import defaultdict
import time

from database import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin-api", tags=["admin-api"])

# API Key configuration
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY")
api_key_header = APIKeyHeader(name="X-Admin-API-Key", auto_error=False)

# Rate limiting
rate_limit_store = defaultdict(list)
RATE_LIMIT_WINDOW = 60  # 1 minute
RATE_LIMIT_MAX = 100    # 100 requests per minute


# ==================== AUTHENTICATION ====================

async def verify_api_key(request: Request, api_key: str = Depends(api_key_header)):
    """Verify the Admin API key and apply rate limiting."""
    if not ADMIN_API_KEY:
        logger.error("ADMIN_API_KEY not configured")
        raise HTTPException(status_code=500, detail="Admin API not configured")
    
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key. Use X-Admin-API-Key header.")
    
    # Rate limit BEFORE key check (prevents brute-force + DB flooding)
    client_ip = get_client_ip(request)
    if check_rate_limit(client_ip):
        logger.warning(f"Admin API rate limit exceeded for IP: {client_ip}")
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Max 100 requests per minute.")
    
    # Check the key with constant-time comparison (prevents timing attacks)
    if not secrets.compare_digest(api_key, ADMIN_API_KEY):
        # Log failed attempt
        await log_api_action(
            action="auth_failed",
            details={"reason": "invalid_api_key"},
            ip_address=client_ip
        )
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return api_key


def get_client_ip(request: Request) -> str:
    """Extract client IP from request.
    
    Security: Use the rightmost IP in X-Forwarded-For, which is set by
    the closest trusted proxy and harder to spoof than the leftmost IP.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(identifier: str) -> bool:
    """Check if rate limit exceeded. Returns True if exceeded."""
    now = time.time()
    rate_limit_store[identifier] = [t for t in rate_limit_store[identifier] if now - t < RATE_LIMIT_WINDOW]
    
    if len(rate_limit_store[identifier]) >= RATE_LIMIT_MAX:
        return True
    
    rate_limit_store[identifier].append(now)
    return False


async def log_api_action(action: str, details: dict = None, ip_address: str = None, user_id: str = None):
    """Log API action for audit trail."""
    await db.admin_api_audit.insert_one({
        "audit_id": f"api_audit_{uuid.uuid4().hex[:12]}",
        "action": action,
        "details": details or {},
        "user_id": user_id,
        "ip_address": ip_address,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })


# ==================== MODELS ====================

class ExtendTrialRequest(BaseModel):
    days: int = 14  # Days to extend trial


class GiftSubscriptionRequest(BaseModel):
    plan_type: str  # "monthly", "annual", "trustee", "estate", "advisor", or "forever_free"
    reason: Optional[str] = None  # Optional reason for gifting


class UserListParams(BaseModel):
    status: Optional[str] = None  # trialing, active, expired, canceled
    created_after: Optional[str] = None  # ISO date string
    created_before: Optional[str] = None
    limit: int = 50
    skip: int = 0


class FixSubscriptionRequest(BaseModel):
    plan_type: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    status: Optional[str] = None
    current_period_end: Optional[str] = None


# ==================== USER ACCESS GUARD ====================

async def check_admin_access_locked(user_id: str):
    """Check if a user has admin_access_locked enabled in their preferences.
    Raises HTTPException(403) if the user has locked admin access.
    """
    locked_pref = await db.user_preferences.find_one(
        {"user_id": user_id},
        {"_id": 0, "admin_access_locked": 1}
    )
    if locked_pref and locked_pref.get("admin_access_locked") is True:
        raise HTTPException(
            status_code=403,
            detail="This user has locked admin access to their account. They must disable the lock in Settings before admin access is granted."
        )


# ==================== STATS ENDPOINTS ====================

@router.get("/stats/daily")
async def get_daily_stats(
    request: Request,
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format. Defaults to today."),
    api_key: str = Depends(verify_api_key)
):
    """
    Get daily statistics for a specific date.
    
    Returns:
    - new_users: Users who registered on this date
    - new_trials: Users who started trials on this date
    - new_purchases: Users who purchased on this date
    - trial_conversions: Trials that converted to paid on this date
    """
    # Parse date or use today
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    else:
        target_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    next_date = target_date + timedelta(days=1)
    
    # Query for new users
    new_users = await db.users.count_documents({
        "created_at": {
            "$gte": target_date.isoformat(),
            "$lt": next_date.isoformat()
        }
    })
    
    # Query for new users (alternative: check if created_at is a string or datetime)
    # Some records might have different formats, so let's be flexible
    new_users_alt = await db.users.count_documents({
        "$expr": {
            "$and": [
                {"$gte": [{"$substr": ["$created_at", 0, 10]}, target_date.strftime("%Y-%m-%d")]},
                {"$lt": [{"$substr": ["$created_at", 0, 10]}, next_date.strftime("%Y-%m-%d")]}
            ]
        }
    })
    new_users = max(new_users, new_users_alt)
    
    # Query for new trials (users whose trial started on this date)
    new_trials = await db.subscriptions.count_documents({
        "status": "trialing",
        "$expr": {
            "$and": [
                {"$gte": [{"$substr": ["$trial_start", 0, 10]}, target_date.strftime("%Y-%m-%d")]},
                {"$lt": [{"$substr": ["$trial_start", 0, 10]}, next_date.strftime("%Y-%m-%d")]}
            ]
        }
    })
    
    # Query for new purchases (subscriptions that became active on this date)
    new_purchases = await db.subscriptions.count_documents({
        "status": "active",
        "$expr": {
            "$and": [
                {"$gte": [{"$substr": ["$activated_at", 0, 10]}, target_date.strftime("%Y-%m-%d")]},
                {"$lt": [{"$substr": ["$activated_at", 0, 10]}, next_date.strftime("%Y-%m-%d")]}
            ]
        }
    })
    
    # Also check payment transactions for purchases
    purchase_transactions = await db.payment_transactions.count_documents({
        "status": "succeeded",
        "$expr": {
            "$and": [
                {"$gte": [{"$substr": ["$created_at", 0, 10]}, target_date.strftime("%Y-%m-%d")]},
                {"$lt": [{"$substr": ["$created_at", 0, 10]}, next_date.strftime("%Y-%m-%d")]}
            ]
        }
    })
    
    # Log the action
    await log_api_action(
        action="get_daily_stats",
        details={"date": target_date.strftime("%Y-%m-%d")},
        ip_address=get_client_ip(request)
    )
    
    return {
        "date": target_date.strftime("%Y-%m-%d"),
        "stats": {
            "new_users": new_users,
            "new_trials": new_trials,
            "new_purchases": new_purchases,
            "purchase_transactions": purchase_transactions
        },
        "generated_at": datetime.now(timezone.utc).isoformat()
    }


@router.get("/stats/summary")
async def get_summary_stats(
    request: Request,
    api_key: str = Depends(verify_api_key)
):
    """
    Get overall summary statistics.
    
    Returns:
    - total_users: Total registered users
    - active_subscriptions: Users with active paid subscriptions
    - trialing_users: Users currently in trial
    - expired_trials: Users whose trials have expired
    - forever_free: Users with forever free access
    - monthly/annual breakdown
    """
    total_users = await db.users.count_documents({})
    
    # Subscription status breakdown
    active_subscriptions = await db.subscriptions.count_documents({"status": "active"})
    trialing = await db.subscriptions.count_documents({"status": "trialing"})
    expired = await db.subscriptions.count_documents({"status": "expired"})
    canceled = await db.subscriptions.count_documents({"status": "canceled"})
    forever_free = await db.subscriptions.count_documents({"status": "forever_free"})
    gifted = await db.subscriptions.count_documents({"gifted": True})
    
    # Plan breakdown for active subscriptions
    monthly_active = await db.subscriptions.count_documents({"status": "active", "plan_type": "monthly"})
    annual_active = await db.subscriptions.count_documents({"status": "active", "plan_type": "annual"})
    trustee_active = await db.subscriptions.count_documents({"status": "active", "plan_type": "trustee"})
    estate_active = await db.subscriptions.count_documents({"status": "active", "plan_type": "estate"})
    advisor_active = await db.subscriptions.count_documents({"status": "active", "plan_type": "advisor"})
    
    # Users who registered in the last 7 days
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    new_users_7d = await db.users.count_documents({
        "created_at": {"$gte": week_ago}
    })
    
    # Users who registered in the last 30 days
    month_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    new_users_30d = await db.users.count_documents({
        "created_at": {"$gte": month_ago}
    })
    
    # Revenue stats from payment transactions
    revenue_pipeline = [
        {"$match": {"$or": [
            {"payment_status": "paid"},
            {"payment_status": "succeeded"},
            {"status": "succeeded"},
            {"status": "paid"}
        ]}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}}
    ]
    revenue_result = await db.payment_transactions.aggregate(revenue_pipeline).to_list(length=1)
    raw_total = revenue_result[0]["total"] if revenue_result else 0
    total_transactions = revenue_result[0]["count"] if revenue_result else 0
    # Amount field stores dollars, convert to cents for consistent formatting
    total_revenue = int(raw_total * 100) if raw_total else 0
    
    # Also calculate MRR from active subscriptions (for gifted/manual subs without payment_transactions)
    # Check both plan_type and plan fields since schema may vary
    sub_pipeline = [
        {"$match": {"status": "active"}},
        {"$group": {"_id": {"$ifNull": ["$plan_type", {"$ifNull": ["$plan", "monthly"]}]}, "count": {"$sum": 1}}}
    ]
    sub_result = await db.subscriptions.aggregate(sub_pipeline).to_list(length=None)
    # Monthly: $79/mo = 7900 cents; Annual: $790/yr ≈ 6583 cents/mo
    # Trustee: $79/mo = 7900 cents; Estate: $149/mo = 14900 cents; Advisor: $399/mo = 39900 cents
    monthly_mrr = (
        sum(s["count"] * 7900 for s in sub_result if s["_id"] == "monthly")
        + sum(s["count"] * 6583 for s in sub_result if s["_id"] == "annual")
        + sum(s["count"] * 7900 for s in sub_result if s["_id"] == "trustee")
        + sum(s["count"] * 14900 for s in sub_result if s["_id"] == "estate")
        + sum(s["count"] * 39900 for s in sub_result if s["_id"] == "advisor")
    )
    
    await log_api_action(
        action="get_summary_stats",
        ip_address=get_client_ip(request)
    )
    
    return {
        "users": {
            "total": total_users,
            "new_last_7_days": new_users_7d,
            "new_last_30_days": new_users_30d
        },
        "subscriptions": {
            "active": active_subscriptions,
            "trialing": trialing,
            "expired": expired,
            "canceled": canceled,
            "forever_free": forever_free,
            "gifted": gifted
        },
        "plans": {
            "monthly_active": monthly_active,
            "annual_active": annual_active,
            "trustee_active": trustee_active,
            "estate_active": estate_active,
            "advisor_active": advisor_active
        },
        "revenue": {
            "total_cents": total_revenue,
            "total_formatted": f"${total_revenue / 100:,.2f}",
            "transaction_count": total_transactions,
            "mrr_cents": monthly_mrr,
            "mrr_formatted": f"${monthly_mrr / 100:,.2f}"
        },
        "generated_at": datetime.now(timezone.utc).isoformat()
    }


# ==================== USER ENDPOINTS ====================

@router.get("/users")
async def list_users(
    request: Request,
    status: Optional[str] = Query(None, description="Filter by subscription status: trialing, active, expired, canceled, forever_free"),
    created_after: Optional[str] = Query(None, description="Filter users created after this date (YYYY-MM-DD)"),
    created_before: Optional[str] = Query(None, description="Filter users created before this date (YYYY-MM-DD)"),
    search: Optional[str] = Query(None, description="Search by email or name"),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0),
    api_key: str = Depends(verify_api_key)
):
    """
    List users with optional filters.
    """
    query = {}
    
    # Build user query
    if search:
        # Escape regex metacharacters to prevent NoSQL injection / ReDoS
        escaped_search = re.escape(search)
        query["$or"] = [
            {"email": {"$regex": escaped_search, "$options": "i"}},
            {"name": {"$regex": escaped_search, "$options": "i"}}
        ]
    
    if created_after:
        query["created_at"] = {"$gte": created_after}
    
    if created_before:
        if "created_at" in query:
            query["created_at"]["$lt"] = created_before
        else:
            query["created_at"] = {"$lt": created_before}
    
    # Get users
    users = await db.users.find(query, {"_id": 0, "password_hash": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(length=limit)
    
    # If status filter, we need to join with subscriptions
    if status:
        user_ids = [u["user_id"] for u in users]
        subs = await db.subscriptions.find(
            {"user_id": {"$in": user_ids}, "status": status},
            {"_id": 0, "user_id": 1}
        ).to_list(length=len(user_ids))
        valid_user_ids = {s["user_id"] for s in subs}
        users = [u for u in users if u["user_id"] in valid_user_ids]
    
    # Enrich with subscription data
    enriched_users = []
    for user in users:
        sub = await db.subscriptions.find_one(
            {"user_id": user["user_id"]},
            {"_id": 0}
        )
        trust_count = await db.trusts.count_documents({"user_id": user["user_id"]})
        
        enriched_users.append({
            "user_id": user["user_id"],
            "email": user.get("email"),
            "name": user.get("name"),
            "created_at": user.get("created_at"),
            "is_admin": user.get("is_admin", False),
            "subscription": {
                "status": sub.get("status") if sub else "none",
                "plan": sub.get("plan") if sub else None,
                "plan_type": sub.get("plan_type") if sub else None,
                "billing_period": sub.get("billing_period") if sub else None,
                "trial_end": sub.get("trial_end") if sub else None
            } if sub else None,
            "trust_count": trust_count
        })
    
    total = await db.users.count_documents(query)
    
    await log_api_action(
        action="list_users",
        details={"status": status, "limit": limit, "skip": skip},
        ip_address=get_client_ip(request)
    )
    
    return {
        "users": enriched_users,
        "total": total,
        "limit": limit,
        "skip": skip
    }


@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    request: Request,
    api_key: str = Depends(verify_api_key)
):
    """
    Get detailed information about a specific user.
    """
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if user has locked admin access
    await check_admin_access_locked(user_id)
    
    # Get subscription
    subscription = await db.subscriptions.find_one({"user_id": user_id}, {"_id": 0})
    
    # Get trust count
    trust_count = await db.trusts.count_documents({"user_id": user_id})
    
    # Get recent activity
    recent_minutes = await db.minutes_records.count_documents({"user_id": user_id})
    recent_distributions = await db.distribution_records.count_documents({"user_id": user_id})
    
    await log_api_action(
        action="get_user",
        details={"target_user_id": user_id},
        ip_address=get_client_ip(request)
    )
    
    return {
        "user": {
            "user_id": user["user_id"],
            "email": user.get("email"),
            "name": user.get("name"),
            "created_at": user.get("created_at"),
            "is_admin": user.get("is_admin", False)
        },
        "subscription": _enrich_subscription_display(subscription),
        "stats": {
            "trust_count": trust_count,
            "minutes_count": recent_minutes,
            "distributions_count": recent_distributions
        }
    }


def _enrich_subscription_display(subscription):
    """Add tier_display_name to a raw subscription dict for admin display."""
    if not subscription:
        return subscription
    # Make a shallow copy so we don't mutate the DB document
    sub = dict(subscription)
    tier_name_map = {
        "trustee": "Trustee",
        "estate": "Estate",
        "advisor": "Advisor",
        "monthly": "Trustee (Legacy)",
        "annual": "Trustee (Legacy)",
        "forever_free": "Forever Free",
        "free": "Free",
    }
    plan_type = sub.get("plan_type") or ""
    legacy_trust_limit = sub.get("legacy_trust_limit")
    display_name = tier_name_map.get(plan_type, plan_type or "Free")
    # Append (Legacy) for grandfathered users on any tier with legacy_trust_limit set
    if legacy_trust_limit and legacy_trust_limit > 1 and plan_type in ("trustee", "monthly", "annual"):
        if "(Legacy)" not in display_name:
            display_name = f"{display_name} (Legacy)"
    billing_period = sub.get("billing_period")
    if billing_period:
        period_label = billing_period.capitalize()
        display_name = f"{display_name} ({period_label})"
    sub["tier_display_name"] = display_name
    return sub


# ==================== ACTION ENDPOINTS ====================

@router.post("/users/{user_id}/extend-trial")
async def extend_trial(
    user_id: str,
    request: Request,
    body: ExtendTrialRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Extend a user's trial period.
    
    - days: Number of days to extend (default: 14)
    """
    if body.days < 1 or body.days > 365:
        raise HTTPException(status_code=400, detail="Days must be between 1 and 365")
    
    # Check if user has locked admin access
    await check_admin_access_locked(user_id)
    
    # Find user
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Find or create subscription
    subscription = await db.subscriptions.find_one({"user_id": user_id})
    
    if subscription:
        # Calculate new trial end
        current_end = subscription.get("trial_end")
        if current_end:
            try:
                current_end_dt = datetime.fromisoformat(current_end.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                current_end_dt = datetime.now(timezone.utc)
        else:
            current_end_dt = datetime.now(timezone.utc)
        
        # If trial already ended, extend from now
        if current_end_dt < datetime.now(timezone.utc):
            current_end_dt = datetime.now(timezone.utc)
        
        new_trial_end = current_end_dt + timedelta(days=body.days)
        
        await db.subscriptions.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "status": "trialing",
                    "trial_end": new_trial_end.isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
    else:
        # Create new trial subscription
        new_trial_end = datetime.now(timezone.utc) + timedelta(days=body.days)
        await db.subscriptions.insert_one({
            "subscription_id": f"sub_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "status": "trialing",
            "plan": None,
            "trial_start": datetime.now(timezone.utc).isoformat(),
            "trial_end": new_trial_end.isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        })
    
    # Update user's subscription_status
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"subscription_status": "trialing"}}
    )
    
    await log_api_action(
        action="extend_trial",
        details={"target_user_id": user_id, "days": body.days, "new_trial_end": new_trial_end.isoformat()},
        user_id=user_id,
        ip_address=get_client_ip(request)
    )
    
    logger.info(f"API: Extended trial for {user['email']} by {body.days} days")
    
    return {
        "success": True,
        "message": f"Trial extended by {body.days} days",
        "user_id": user_id,
        "email": user.get("email"),
        "new_trial_end": new_trial_end.isoformat()
    }


@router.post("/users/{user_id}/gift-subscription")
async def gift_subscription(
    user_id: str,
    request: Request,
    body: GiftSubscriptionRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Gift a subscription to a user.
    
    - plan_type: "monthly", "annual", "trustee", "estate", "advisor", or "forever_free"
    - reason: Optional reason for gifting (logged for audit)
    """
    valid_plans = ["monthly", "annual", "trustee", "estate", "advisor", "forever_free"]
    if body.plan_type not in valid_plans:
        raise HTTPException(status_code=400, detail=f"Invalid plan_type. Must be one of: {', '.join(valid_plans)}")
    
    # Check if user has locked admin access
    await check_admin_access_locked(user_id)
    
    # Find user
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    now = datetime.now(timezone.utc)
    
    # Calculate subscription end based on plan
    if body.plan_type == "forever_free":
        status = "forever_free"
        current_period_end = None
        plan = "forever_free"
        # Forever free should not show the gifted banner — it's permanent, not time-limited
        subscription_data = {
            "status": status,
            "plan": plan,
            "plan_type": plan,
            "activated_at": now.isoformat(),
            "current_period_end": None,
            "updated_at": now.isoformat()
        }
    elif body.plan_type in ("trustee", "estate", "advisor"):
        status = "active"
        current_period_end = (now + timedelta(days=30)).isoformat()
        plan = body.plan_type
    elif body.plan_type == "monthly":
        status = "active"
        current_period_end = (now + timedelta(days=30)).isoformat()
        plan = "monthly"
    else:  # annual
        status = "active"
        current_period_end = (now + timedelta(days=365)).isoformat()
        plan = "annual"

    # Update or create subscription
    subscription = await db.subscriptions.find_one({"user_id": user_id})

    # Build subscription_data for non-forever_free plans (includes gifted fields)
    if body.plan_type != "forever_free":
        subscription_data = {
            "status": status,
            "plan": plan,
            "plan_type": plan,
            "activated_at": now.isoformat(),
            "current_period_end": current_period_end,
            "gifted": True,
            "gift_type": plan,
            "gift_reason": body.reason,
            "gifted_at": now.isoformat(),
            "updated_at": now.isoformat()
        }
    
    if subscription:
        await db.subscriptions.update_one(
            {"user_id": user_id},
            {"$set": subscription_data}
        )
    else:
        subscription_data.update({
            "subscription_id": f"sub_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "created_at": now.isoformat()
        })
        await db.subscriptions.insert_one(subscription_data)
    
    # Update user's subscription_status
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"subscription_status": status}}
    )
    
    await log_api_action(
        action="gift_subscription",
        details={
            "target_user_id": user_id,
            "plan_type": body.plan_type,
            "reason": body.reason,
            "current_period_end": current_period_end
        },
        user_id=user_id,
        ip_address=get_client_ip(request)
    )
    
    logger.info(f"API: Gifted {body.plan_type} subscription to {user['email']}")
    
    return {
        "success": True,
        "message": f"Gifted {body.plan_type} subscription",
        "user_id": user_id,
        "email": user.get("email"),
        "subscription": {
            "status": status,
            "plan": plan,
            "current_period_end": current_period_end
        }
    }


# ==================== AUDIT LOG ENDPOINT ====================

@router.get("/audit-log")
async def get_audit_log(
    request: Request,
    action: Optional[str] = Query(None, description="Filter by action type"),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0),
    api_key: str = Depends(verify_api_key)
):
    """
    Get Admin API audit log.
    """
    query = {}
    if action:
        query["action"] = action
    
    logs = await db.admin_api_audit.find(
        query,
        {"_id": 0}
    ).sort("timestamp", -1).skip(skip).limit(limit).to_list(length=limit)
    
    total = await db.admin_api_audit.count_documents(query)
    
    return {
        "logs": logs,
        "total": total,
        "limit": limit,
        "skip": skip
    }


@router.post("/users/{user_id}/reset-onboarding")
async def reset_user_onboarding(
    user_id: str,
    api_key: str = Depends(verify_api_key)
):
    """
    Reset a user's onboarding checklist so it reappears on the dashboard.
    Sets checklist_dismissed to False and resets all step flags to False
    so auto-detection can re-evaluate based on actual data.
    """
    # Verify user exists
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Reset onboarding state — auto-detection will re-mark completed steps
    result = await db.user_onboarding.update_one(
        {"user_id": user_id},
        {"$set": {
            "formation_date_added": False,
            "ein_entered": False,
            "trust_doc_uploaded": False,
            "ein_doc_uploaded": False,
            "beneficiaries_added": False,
            "assets_added": False,
            "minutes_generated": False,
            "calendar_set": False,
            "checklist_dismissed": False,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    # If no onboarding record exists yet, create one
    if result.matched_count == 0:
        await db.user_onboarding.insert_one({
            "user_id": user_id,
            "formation_date_added": False,
            "ein_entered": False,
            "trust_doc_uploaded": False,
            "ein_doc_uploaded": False,
            "beneficiaries_added": False,
            "assets_added": False,
            "minutes_generated": False,
            "calendar_set": False,
            "checklist_dismissed": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        })
    
    await log_api_action("reset_onboarding", {"user_id": user_id}, user_id=user_id)
    
    return {
        "message": "Onboarding checklist reset successfully",
        "user_id": user_id,
        "note": "Auto-detection will re-mark completed steps on next dashboard load"
    }


@router.post("/users/{user_id}/grant-stats")
async def grant_stats_access(
    user_id: str,
    request: Request,
    api_key: str = Depends(verify_api_key)
):
    """
    Grant stats access to a user.
    
    Sets is_stats_user: true and stats_granted_at on the user document.
    """
    # Check if user has locked admin access
    await check_admin_access_locked(user_id)
    
    # Verify user exists
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    now = datetime.now(timezone.utc)
    
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "is_stats_user": True,
            "stats_granted_at": now.isoformat()
        }}
    )
    
    await log_api_action(
        action="grant_stats",
        details={"target_user_id": user_id},
        user_id=user_id,
        ip_address=get_client_ip(request)
    )
    
    logger.info(f"API: Granted stats access to {user['email']}")
    
    return {
        "success": True,
        "message": f"Stats access granted to {user.get('email')}",
        "user_id": user_id,
        "email": user.get("email"),
        "is_stats_user": True,
        "stats_granted_at": now.isoformat()
    }


# ==================== SUBSCRIPTION FIX ENDPOINT ====================

@router.post("/subscriptions/{user_id}/fix")
async def fix_subscription(
    user_id: str,
    request: Request,
    body: FixSubscriptionRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Fix a user's subscription fields to correct mismatches between Stripe and the DB.
    
    Accepts any combination of:
    - plan_type: e.g. "monthly", "annual", "forever_free"
    - stripe_subscription_id: Stripe subscription ID
    - stripe_customer_id: Stripe customer ID
    - status: subscription status
    - current_period_end: ISO date string
    """
    # Check if user has locked admin access
    await check_admin_access_locked(user_id)
    
    # Verify user exists
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Verify subscription exists
    subscription = await db.subscriptions.find_one({"user_id": user_id}, {"_id": 0})
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found for this user")
    
    # Build update set from non-None fields
    update_fields = body.dict(exclude_none=True)
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    
    # Validate plan_type if provided
    if body.plan_type is not None:
        valid_plans = ["monthly", "annual", "forever_free", "trustee", "estate", "advisor"]
        if body.plan_type not in valid_plans:
            raise HTTPException(status_code=400, detail=f"Invalid plan_type. Must be one of: {', '.join(valid_plans)}")
    
    # Always update the timestamp
    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db.subscriptions.update_one(
        {"user_id": user_id},
        {"$set": update_fields}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    # Fetch updated subscription to return
    updated_subscription = await db.subscriptions.find_one({"user_id": user_id}, {"_id": 0})
    
    await log_api_action(
        action="fix_subscription",
        details={
            "target_user_id": user_id,
            "updated_fields": list(body.dict(exclude_none=True).keys()),
            "before": {k: subscription.get(k) for k in body.dict(exclude_none=True).keys()},
            "after": {k: updated_subscription.get(k) for k in body.dict(exclude_none=True).keys()}
        },
        user_id=user_id,
        ip_address=get_client_ip(request)
    )
    
    logger.info(f"API: Fixed subscription for {user['email']}: {list(update_fields.keys())}")

    return {
        "success": True,
        "message": f"Subscription updated for {user.get('email')}",
        "user_id": user_id,
        "email": user.get("email"),
        "updated_fields": list(body.dict(exclude_none=True).keys()),
        "subscription": updated_subscription
    }


# ==================== LEAD ENRICHMENT ====================


@router.post("/leads/{lead_id}/enrich")
async def enrich_lead(
    lead_id: str,
    body: dict,
    request: Request,
    api_key: str = Depends(verify_api_key),
):
    """Enrich a lead with course progress, booked_call, stage, etc."""
    lead = await db.leads.find_one({"lead_id": lead_id})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    update_fields = {}
    now = datetime.now(timezone.utc)

    if "lessons_watched" in body:
        update_fields["lessons_watched"] = body["lessons_watched"]
    if "booked_call" in body:
        update_fields["booked_call"] = body["booked_call"]
    if "booked_call_at" in body:
        update_fields["booked_call_at"] = body["booked_call_at"]
    if "last_login" in body:
        update_fields["last_login"] = body["last_login"]
    if "stage" in body:
        update_fields["stage"] = body["stage"]
    if "score" in body:
        update_fields["score"] = body["score"]
    if "notes" in body:
        update_fields["notes"] = body["notes"]

    if update_fields:
        update_fields["updated_at"] = now.isoformat()
        await db.leads.update_one({"lead_id": lead_id}, {"$set": update_fields})

    # Add activity log entry if provided
    if body.get("activity"):
        await db.lead_activities.insert_one({
            "activity_id": f"act_{uuid.uuid4().hex[:12]}",
            "lead_id": lead_id,
            "action_type": body["activity"].get("type", "system"),
            "content": body["activity"]["content"],
            "created_at": body["activity"].get("created_at", now.isoformat()),
        })

    await log_api_action(
        action="enrich_lead",
        details={"lead_id": lead_id, "updated_fields": list(update_fields.keys())},
        ip_address=get_client_ip(request),
    )

    logger.info(f"API: Enriched lead {lead_id}: {list(update_fields.keys())}")
    return {"success": True, "lead_id": lead_id, "updated_fields": list(update_fields.keys())}


# ==================== ADMIN PASSWORD RESET ====================


@router.post("/users/{user_id}/reset-password")
async def reset_admin_password(
    user_id: str,
    body: dict,
    request: Request,
    api_key: str = Depends(verify_api_key),
):
    """Reset a user's password. Requires admin API key."""
    import bcrypt

    # Check if target user has locked admin access
    await check_admin_access_locked(user_id)

    new_password = body.get("password")
    if not new_password or len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    hashed = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    result = await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"password_hash": hashed}}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    await log_api_action(
        action="reset_password",
        details={"target_user_id": user_id},
        ip_address=get_client_ip(request),
    )

    logger.info(f"API: Password reset for user {user_id}")
    return {"success": True, "message": "Password reset successfully"}
