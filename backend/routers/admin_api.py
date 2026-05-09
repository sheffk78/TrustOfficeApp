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
"""

from fastapi import APIRouter, HTTPException, Depends, Request, Query
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
import re
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
    
    if api_key != ADMIN_API_KEY:
        # Log failed attempt
        await log_api_action(
            action="auth_failed",
            details={"reason": "invalid_api_key"},
            ip_address=get_client_ip(request)
        )
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Rate limiting
    client_ip = get_client_ip(request)
    if check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Max 100 requests per minute.")
    
    return api_key


def get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
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
    plan_type: str  # "monthly", "annual", or "forever_free"
    reason: Optional[str] = None  # Optional reason for gifting


class UserListParams(BaseModel):
    status: Optional[str] = None  # trialing, active, expired, canceled
    created_after: Optional[str] = None  # ISO date string
    created_before: Optional[str] = None
    limit: int = 50
    skip: int = 0


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
    
    # Plan breakdown for active subscriptions
    monthly_active = await db.subscriptions.count_documents({"status": "active", "plan": "monthly"})
    annual_active = await db.subscriptions.count_documents({"status": "active", "plan": "annual"})
    
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
    monthly_mrr = sum(s["count"] * 7900 for s in sub_result if s["_id"] == "monthly") + sum(s["count"] * 6583 for s in sub_result if s["_id"] == "annual")
    
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
            "forever_free": forever_free
        },
        "plans": {
            "monthly_active": monthly_active,
            "annual_active": annual_active
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
        "subscription": subscription,
        "stats": {
            "trust_count": trust_count,
            "minutes_count": recent_minutes,
            "distributions_count": recent_distributions
        }
    }


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
    
    - plan_type: "monthly", "annual", or "forever_free"
    - reason: Optional reason for gifting (logged for audit)
    """
    valid_plans = ["monthly", "annual", "forever_free"]
    if body.plan_type not in valid_plans:
        raise HTTPException(status_code=400, detail=f"Invalid plan_type. Must be one of: {', '.join(valid_plans)}")
    
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
    
    subscription_data = {
        "status": status,
        "plan": plan,
        "activated_at": now.isoformat(),
        "current_period_end": current_period_end,
        "gifted": True,
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
