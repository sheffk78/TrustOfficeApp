"""
Admin Router - Backend admin panel for customer management
Provides endpoints for managing users, fixing issues, and administrative tasks.

ADMIN ACCESS:
- Only users with is_admin=True can access these endpoints
- contact@trustoffice.app is the primary admin
- Admins get full TrustOffice access without payment

FEATURES:
- List all customers with filtering/search
- View customer details and subscription status
- Appoint/remove admin status
- Fix referral issues
- Delete accounts
- Grant/revoke access
- View system stats
- View revenue data from Stripe
- Grant/revoke stats access
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
import re
import os
import secrets
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from pydantic import BaseModel, EmailStr
import uuid
import logging

import stripe

from database import db
from dependencies import get_current_user, hash_password, TRIAL_DAYS
from email_service import email_service

logger = logging.getLogger(__name__)

stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
STRIPE_MONTHLY_PRICE_ID = os.environ.get('STRIPE_MONTHLY_PRICE_ID')
STRIPE_ANNUAL_PRICE_ID = os.environ.get('STRIPE_ANNUAL_PRICE_ID')

router = APIRouter(prefix="/admin", tags=["admin"])


# ==================== MODELS ====================

class CustomerListItem(BaseModel):
    user_id: str
    email: str
    name: str
    is_admin: bool = False
    is_stats_user: bool = False
    created_at: str
    subscription_status: str
    subscription_plan: str
    trust_count: int = 0
    last_login: Optional[str] = None


class CustomerDetail(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    is_admin: bool = False
    is_stats_user: bool = False
    created_at: str
    google_id: Optional[str] = None
    subscription: dict
    trusts: List[dict]
    referral_info: Optional[dict] = None
    stats: dict


class AdminActionRequest(BaseModel):
    user_id: str
    reason: Optional[str] = None


class GrantAccessRequest(BaseModel):
    plan_type: str = "annual"  # trial, monthly, annual, forever_free
    days: Optional[int] = None  # For trial extension


class FixReferralRequest(BaseModel):
    referrer_email: str
    referee_email: str
    action: str  # "create", "delete", "update_status"
    status: Optional[str] = None  # For update_status action


class CreateAdminUserRequest(BaseModel):
    email: EmailStr
    name: str
    password: Optional[str] = None  # If None, OAuth-only account


class CreateUserRequest(BaseModel):
    email: EmailStr
    name: str


class SystemStats(BaseModel):
    total_users: int
    active_subscriptions: int
    trial_users: int
    expired_trials: int
    admin_count: int
    total_trusts: int
    total_minutes: int
    total_distributions: int
    new_users_30d: int
    revenue_estimate_monthly: float
    # Real Stripe revenue fields
    stripe_total_revenue_cents: int = 0
    stripe_mrr_cents: int = 0
    stripe_arr_cents: int = 0
    stripe_paid_customers: int = 0
    stripe_total_transactions: int = 0
    monthly_subs: int = 0
    annual_subs: int = 0


# ==================== ADMIN CHECK ====================

async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """
    Dependency that requires user to be an admin.
    Raises 403 if not an admin.
    """
    # Check if user has is_admin flag
    user_doc = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "is_admin": 1, "email": 1})
    
    if not user_doc:
        raise HTTPException(status_code=403, detail="User not found")
    
    is_admin = user_doc.get("is_admin", False)
    
    # Also check by email for bootstrap admin
    admin_emails = {"contact@trustoffice.app"}
    if user_doc.get("email", "").lower() in admin_emails:
        # Auto-set admin flag if not set
        if not is_admin:
            await db.users.update_one(
                {"user_id": user["user_id"]},
                {"$set": {"is_admin": True}}
            )
        is_admin = True
    
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    return user


# ==================== CUSTOMER MANAGEMENT ====================

@router.get("/customers", response_model=dict)
async def list_customers(
    search: Optional[str] = Query(None, description="Search by email or name"),
    status: Optional[str] = Query(None, description="Filter by subscription status"),
    is_admin_filter: Optional[bool] = Query(None, alias="is_admin", description="Filter by admin status"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    admin: dict = Depends(require_admin)
):
    """
    List all customers with filtering, search, and pagination.
    """
    # Build filter query
    query = {}
    
    if search:
        # Escape regex metacharacters to prevent NoSQL injection / ReDoS
        escaped_search = re.escape(search)
        query["$or"] = [
            {"email": {"$regex": escaped_search, "$options": "i"}},
            {"name": {"$regex": escaped_search, "$options": "i"}}
        ]
    
    if is_admin_filter is not None:
        if is_admin_filter:
            query["is_admin"] = True
        else:
            query["is_admin"] = {"$ne": True}
    
    # Get total count
    total = await db.users.count_documents(query)
    logger.info(f"Admin list_customers: query={query}, total={total}")
    
    # Build sort - handle missing created_at field
    sort_dir = -1 if sort_order == "desc" else 1
    
    # Get users
    skip = (page - 1) * limit
    users = await db.users.find(query, {"_id": 0, "password_hash": 0}).sort(sort_by, sort_dir).skip(skip).limit(limit).to_list(limit)
    
    logger.info(f"Admin list_customers: fetched {len(users)} users")
    
    # Enrich with subscription data
    customers = []
    for user in users:
        # Get subscription
        sub = await db.subscriptions.find_one({"user_id": user["user_id"]}, {"_id": 0})
        
        # Get trust count
        trust_count = await db.trusts.count_documents({"user_id": user["user_id"]})
        
        # Determine subscription status
        sub_status = sub.get("status", "none") if sub else "none"
        sub_plan = sub.get("plan_type", "none") if sub else "none"
        
        # Filter by status if specified (do this filtering here)
        if status and status != "all" and sub_status != status:
            continue
        
        customers.append(CustomerListItem(
            user_id=user["user_id"],
            email=user["email"],
            name=user.get("name", ""),
            is_admin=user.get("is_admin", False),
            is_stats_user=user.get("is_stats_user", False),
            created_at=user.get("created_at", ""),
            subscription_status=sub_status,
            subscription_plan=sub_plan,
            trust_count=trust_count,
            last_login=user.get("last_login")
        ).model_dump())
    
    return {
        "customers": customers,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit
    }


@router.get("/customers/{user_id}", response_model=CustomerDetail)
async def get_customer_detail(
    user_id: str,
    admin: dict = Depends(require_admin)
):
    """
    Get detailed information about a specific customer.
    """
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    
    if not user:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Get subscription
    sub = await db.subscriptions.find_one({"user_id": user_id}, {"_id": 0})
    
    # Get trusts
    trusts = await db.trusts.find({"user_id": user_id}, {"_id": 0}).to_list(100)
    
    # Get referral info
    referral_code = await db.referral_codes.find_one({"user_id": user_id}, {"_id": 0})
    referral_tracking = await db.referral_tracking.find_one({"referee_user_id": user_id}, {"_id": 0})
    
    referral_info = None
    if referral_code or referral_tracking:
        # Count successful referrals
        referral_count = await db.referral_tracking.count_documents({
            "referrer_user_id": user_id,
            "status": "converted"
        })
        
        referral_info = {
            "has_referral_code": bool(referral_code),
            "referral_code": referral_code.get("code") if referral_code else None,
            "referred_by": referral_tracking.get("referrer_user_id") if referral_tracking else None,
            "referral_status": referral_tracking.get("status") if referral_tracking else None,
            "successful_referrals": referral_count
        }
    
    # Get stats
    minutes_count = await db.minutes_records.count_documents({"user_id": user_id})
    dist_count = await db.distribution_records.count_documents({"user_id": user_id})
    
    stats = {
        "trusts": len(trusts),
        "minutes": minutes_count,
        "distributions": dist_count
    }
    
    return CustomerDetail(
        user_id=user["user_id"],
        email=user["email"],
        name=user.get("name", ""),
        picture=user.get("picture"),
        is_admin=user.get("is_admin", False),
        is_stats_user=user.get("is_stats_user", False),
        created_at=user.get("created_at", ""),
        google_id=user.get("google_id"),
        subscription=sub or {"status": "none", "plan_type": "none"},
        trusts=[{"trust_id": t["trust_id"], "name": t["name"]} for t in trusts],
        referral_info=referral_info,
        stats=stats
    )


# ==================== ADMIN ACTIONS ====================

@router.post("/customers/{user_id}/make-admin")
async def make_admin(
    user_id: str,
    request: AdminActionRequest,
    admin: dict = Depends(require_admin)
):
    """
    Grant admin privileges to a user.
    This also gives them forever_free subscription access.
    """
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    
    if not user:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    if user.get("is_admin"):
        raise HTTPException(status_code=400, detail="User is already an admin")
    
    # Update user to be admin
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "is_admin": True,
            "admin_granted_by": admin["user_id"],
            "admin_granted_at": datetime.now(timezone.utc).isoformat(),
            "admin_grant_reason": request.reason
        }}
    )
    
    # Give them forever_free subscription
    await db.subscriptions.update_one(
        {"user_id": user_id},
        {"$set": {
            "plan_type": "forever_free",
            "status": "active",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "notes": f"Admin access granted by {admin['email']}"
        }},
        upsert=True
    )
    
    logger.info(f"Admin {admin['email']} granted admin access to {user['email']}")
    
    return {"message": f"Admin privileges granted to {user['email']}"}


@router.post("/customers/{user_id}/remove-admin")
async def remove_admin(
    user_id: str,
    request: AdminActionRequest,
    admin: dict = Depends(require_admin)
):
    """
    Remove admin privileges from a user.
    """
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    
    if not user:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Don't allow removing the primary admin
    if user.get("email", "").lower() == "contact@trustoffice.app":
        raise HTTPException(status_code=400, detail="Cannot remove primary admin")
    
    if not user.get("is_admin"):
        raise HTTPException(status_code=400, detail="User is not an admin")
    
    # Remove admin status
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "is_admin": False,
            "admin_removed_by": admin["user_id"],
            "admin_removed_at": datetime.now(timezone.utc).isoformat(),
            "admin_remove_reason": request.reason
        }}
    )
    
    # Revert to expired trial (they'll need to subscribe)
    await db.subscriptions.update_one(
        {"user_id": user_id},
        {"$set": {
            "plan_type": "trial",
            "status": "expired",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "notes": f"Admin access removed by {admin['email']}"
        }}
    )
    
    logger.info(f"Admin {admin['email']} removed admin access from {user['email']}")
    
    return {"message": f"Admin privileges removed from {user['email']}"}


@router.post("/customers/{user_id}/grant-access")
async def grant_access(
    user_id: str,
    request: GrantAccessRequest,
    admin: dict = Depends(require_admin)
):
    """
    Grant or extend subscription access to a user.
    Useful for:
    - Extending trials
    - Giving complimentary access
    - Fixing billing issues
    """
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    
    if not user:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    now = datetime.now(timezone.utc)
    
    if request.plan_type == "trial":
        # Extend or create trial
        days = request.days or TRIAL_DAYS
        trial_end = (now + timedelta(days=days)).isoformat()
        
        await db.subscriptions.update_one(
            {"user_id": user_id},
            {"$set": {
                "plan_type": "trial",
                "status": "trialing",
                "trial_start_date": now.isoformat(),
                "trial_end_date": trial_end,
                "updated_at": now.isoformat(),
                "notes": f"Trial extended by admin {admin['email']}"
            }},
            upsert=True
        )
        
        return {"message": f"Trial extended by {days} days for {user['email']}"}
    
    elif request.plan_type == "forever_free":
        await db.subscriptions.update_one(
            {"user_id": user_id},
            {"$set": {
                "plan_type": "forever_free",
                "status": "active",
                "updated_at": now.isoformat(),
                "notes": f"Forever free access granted by admin {admin['email']}"
            }},
            upsert=True
        )
        
        return {"message": f"Forever free access granted to {user['email']}"}
    
    else:
        # Grant paid plan access (complimentary)
        await db.subscriptions.update_one(
            {"user_id": user_id},
            {"$set": {
                "plan_type": request.plan_type,
                "status": "active",
                "updated_at": now.isoformat(),
                "notes": f"Complimentary {request.plan_type} access granted by admin {admin['email']}"
            }},
            upsert=True
        )
        
        return {"message": f"Complimentary {request.plan_type} access granted to {user['email']}"}


@router.delete("/customers/{user_id}")
async def delete_customer(
    user_id: str,
    confirm: bool = Query(False, description="Confirm deletion"),
    admin: dict = Depends(require_admin)
):
    """
    Permanently delete a customer and all their data.
    Requires confirm=true query param.
    """
    if not confirm:
        raise HTTPException(status_code=400, detail="Please confirm deletion with confirm=true")
    
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    
    if not user:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Don't allow deleting the primary admin
    if user.get("email", "").lower() == "contact@trustoffice.app":
        raise HTTPException(status_code=400, detail="Cannot delete primary admin")
    
    # Don't allow admins to delete themselves
    if user_id == admin["user_id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    
    # Delete all user data
    collections_to_clean = [
        "trusts",
        "entities",
        "entity_relationships",
        "minutes_records",
        "minutes_templates",
        "distribution_records",
        "compensation_plans",
        "compensation_payments",
        "governance_tasks",
        "schedule_a_items",
        "trust_units_settings",
        "trust_unit_certificates",
        "trust_unit_transfers",
        "benevolence_records",
        "health_score_snapshots",
        "user_onboarding",
        "user_preferences",
        "notification_preferences",
        "subscriptions",
        "user_sessions",
        "password_resets",
        "referral_codes",
        "ai_usage_tracking",
        "ai_suggestion_cache"
    ]
    
    deleted_counts = {}
    for collection in collections_to_clean:
        result = await db[collection].delete_many({"user_id": user_id})
        if result.deleted_count > 0:
            deleted_counts[collection] = result.deleted_count
    
    # Also clean up referral tracking where they're the referee
    await db.referral_tracking.delete_many({"referee_user_id": user_id})
    
    # Delete the user
    await db.users.delete_one({"user_id": user_id})
    
    logger.info(f"Admin {admin['email']} deleted user {user['email']} (user_id: {user_id})")
    
    return {
        "message": f"User {user['email']} and all associated data deleted",
        "deleted_records": deleted_counts
    }


class BulkDeleteRequest(BaseModel):
    user_ids: List[str]


@router.post("/customers/bulk-delete")
async def bulk_delete_customers(
    request: BulkDeleteRequest,
    admin: dict = Depends(require_admin)
):
    """
    Permanently delete multiple customers and all their data.
    Skips admins and the primary admin account.
    """
    if not request.user_ids:
        raise HTTPException(status_code=400, detail="No user IDs provided")
    
    if len(request.user_ids) > 100:
        raise HTTPException(status_code=400, detail="Cannot delete more than 100 accounts at once")
    
    # Filter out protected accounts
    protected_emails = {"contact@trustoffice.app"}
    users_to_delete = []
    skipped = []
    
    for user_id in request.user_ids:
        user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "is_admin": 1})
        if not user:
            skipped.append({"user_id": user_id, "reason": "not found"})
            continue
        
        # Skip primary admin
        if user.get("email", "").lower() in protected_emails:
            skipped.append({"user_id": user_id, "email": user["email"], "reason": "protected account"})
            continue
        
        # Skip admins
        if user.get("is_admin"):
            skipped.append({"user_id": user_id, "email": user["email"], "reason": "admin account"})
            continue
        
        # Skip self-deletion
        if user_id == admin["user_id"]:
            skipped.append({"user_id": user_id, "email": user["email"], "reason": "cannot delete self"})
            continue
        
        users_to_delete.append({"user_id": user_id, "email": user["email"]})
    
    if not users_to_delete:
        raise HTTPException(status_code=400, detail="No deletable accounts found")
    
    # Collections to clean for each user
    collections_to_clean = [
        "trusts",
        "entities",
        "entity_relationships",
        "minutes_records",
        "minutes_templates",
        "distribution_records",
        "compensation_plans",
        "compensation_payments",
        "governance_tasks",
        "schedule_a_items",
        "trust_units_settings",
        "trust_unit_certificates",
        "trust_unit_transfers",
        "benevolence_records",
        "health_score_snapshots",
        "user_onboarding",
        "user_preferences",
        "notification_preferences",
        "subscriptions",
        "user_sessions",
        "password_resets",
        "referral_codes",
        "ai_usage_tracking",
        "ai_suggestion_cache"
    ]
    
    deleted_count = 0
    deleted_emails = []
    
    for user_data in users_to_delete:
        user_id = user_data["user_id"]
        
        # Delete all user data from collections
        for collection in collections_to_clean:
            await db[collection].delete_many({"user_id": user_id})
        
        # Clean up referral tracking
        await db.referral_tracking.delete_many({"referee_user_id": user_id})
        
        # Delete the user
        await db.users.delete_one({"user_id": user_id})
        
        deleted_count += 1
        deleted_emails.append(user_data["email"])
    
    logger.info(f"Admin {admin['email']} bulk deleted {deleted_count} users: {deleted_emails}")
    
    return {
        "message": f"Successfully deleted {deleted_count} account(s)",
        "deleted_count": deleted_count,
        "deleted_emails": deleted_emails,
        "skipped": skipped if skipped else None
    }


# ==================== IMPERSONATION ====================

from dependencies import create_jwt_token

@router.post("/impersonate/{user_id}")
async def impersonate_user(
    user_id: str,
    admin: dict = Depends(require_admin)
):
    """
    Generate a token to impersonate a user.
    Admin can see exactly what the user sees.
    
    Returns a JWT token for the target user.
    The frontend should store the admin's original token to allow "exit impersonation".
    """
    # Get target user
    target_user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Don't allow impersonating other admins
    if target_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Cannot impersonate admin accounts")
    
    # Don't allow impersonating primary admin
    if target_user.get("email", "").lower() == "contact@trustoffice.app":
        raise HTTPException(status_code=403, detail="Cannot impersonate primary admin")
    
    # Generate token for target user
    impersonation_token = create_jwt_token(target_user["user_id"], target_user["email"])
    
    # Log the impersonation action
    await db.admin_audit_log.insert_one({
        "audit_id": f"audit_{uuid.uuid4().hex[:12]}",
        "action": "impersonate_user",
        "admin_user_id": admin["user_id"],
        "admin_email": admin["email"],
        "target_user_id": target_user["user_id"],
        "target_email": target_user["email"],
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    
    logger.info(f"Admin {admin['email']} started impersonating user {target_user['email']}")
    
    return {
        "token": impersonation_token,
        "user": {
            "user_id": target_user["user_id"],
            "email": target_user["email"],
            "name": target_user.get("name", ""),
            "picture": target_user.get("picture")
        },
        "message": f"Now impersonating {target_user['email']}"
    }


@router.post("/impersonation/log-exit")
async def log_impersonation_exit(
    admin: dict = Depends(require_admin)
):
    """
    Log when admin exits impersonation mode.
    This is called when the admin clicks "Exit Impersonation".
    """
    await db.admin_audit_log.insert_one({
        "audit_id": f"audit_{uuid.uuid4().hex[:12]}",
        "action": "exit_impersonation",
        "admin_user_id": admin["user_id"],
        "admin_email": admin["email"],
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    
    logger.info(f"Admin {admin['email']} exited impersonation mode")
    
    return {"message": "Impersonation session ended"}


@router.get("/impersonation/audit-log")
async def get_impersonation_audit_log(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    admin: dict = Depends(require_admin)
):
    """
    Get audit log of all impersonation actions.
    """
    skip = (page - 1) * limit
    
    total = await db.admin_audit_log.count_documents({"action": {"$in": ["impersonate_user", "exit_impersonation"]}})
    
    logs = await db.admin_audit_log.find(
        {"action": {"$in": ["impersonate_user", "exit_impersonation"]}},
        {"_id": 0}
    ).sort("timestamp", -1).skip(skip).limit(limit).to_list(length=limit)
    
    return {
        "logs": logs,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }


# ==================== REFERRAL MANAGEMENT ====================

@router.get("/referrals")
async def list_referrals(
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    admin: dict = Depends(require_admin)
):
    """
    List all referral relationships.
    """
    query = {}
    if status:
        query["status"] = status
    
    total = await db.referral_tracking.count_documents(query)
    skip = (page - 1) * limit
    
    referrals = await db.referral_tracking.find(query, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
    
    # Enrich with user emails
    enriched = []
    for ref in referrals:
        referrer = await db.users.find_one({"user_id": ref["referrer_user_id"]}, {"_id": 0, "email": 1, "name": 1})
        referee = await db.users.find_one({"user_id": ref["referee_user_id"]}, {"_id": 0, "email": 1, "name": 1})
        
        enriched.append({
            **ref,
            "referrer_email": referrer["email"] if referrer else "Unknown",
            "referrer_name": referrer.get("name", "") if referrer else "",
            "referee_email": referee["email"] if referee else "Unknown",
            "referee_name": referee.get("name", "") if referee else ""
        })
    
    return {
        "referrals": enriched,
        "total": total,
        "page": page,
        "limit": limit
    }


@router.post("/referrals/fix")
async def fix_referral(
    request: FixReferralRequest,
    admin: dict = Depends(require_admin)
):
    """
    Fix referral issues:
    - Create missing referral relationship
    - Delete incorrect referral
    - Update referral status
    """
    # Find users by email
    referrer = await db.users.find_one({"email": request.referrer_email.lower()}, {"_id": 0})
    referee = await db.users.find_one({"email": request.referee_email.lower()}, {"_id": 0})
    
    if not referrer:
        raise HTTPException(status_code=404, detail=f"Referrer not found: {request.referrer_email}")
    
    if not referee:
        raise HTTPException(status_code=404, detail=f"Referee not found: {request.referee_email}")
    
    now = datetime.now(timezone.utc).isoformat()
    
    if request.action == "create":
        # Check if referral already exists
        existing = await db.referral_tracking.find_one({"referee_user_id": referee["user_id"]}, {"_id": 0})
        if existing:
            raise HTTPException(status_code=400, detail="Referral already exists for this referee")
        
        # Create referral
        await db.referral_tracking.insert_one({
            "referral_id": f"ref_{uuid.uuid4().hex[:12]}",
            "referrer_user_id": referrer["user_id"],
            "referee_user_id": referee["user_id"],
            "status": "converted",
            "created_at": now,
            "updated_at": now,
            "admin_created": True,
            "admin_note": f"Created by admin {admin['email']}"
        })
        
        return {"message": f"Referral created: {request.referrer_email} -> {request.referee_email}"}
    
    elif request.action == "delete":
        result = await db.referral_tracking.delete_one({"referee_user_id": referee["user_id"]})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Referral not found")
        
        return {"message": f"Referral deleted for {request.referee_email}"}
    
    elif request.action == "update_status":
        if not request.status:
            raise HTTPException(status_code=400, detail="Status required for update_status action")
        
        result = await db.referral_tracking.update_one(
            {"referee_user_id": referee["user_id"]},
            {"$set": {
                "status": request.status,
                "updated_at": now,
                "admin_updated": True,
                "admin_note": f"Status updated by admin {admin['email']}"
            }}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Referral not found")
        
        return {"message": f"Referral status updated to {request.status}"}
    
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {request.action}")


# ==================== SYSTEM STATS ====================

@router.get("/stats", response_model=SystemStats)
async def get_system_stats(admin: dict = Depends(require_admin)):
    """
    Get system-wide statistics for the admin dashboard.
    Now includes real Stripe revenue data alongside estimates.
    """
    now = datetime.now(timezone.utc)
    thirty_days_ago = (now - timedelta(days=30)).isoformat()
    
    # User counts
    total_users = await db.users.count_documents({})
    admin_count = await db.users.count_documents({"is_admin": True})
    new_users_30d = await db.users.count_documents({"created_at": {"$gte": thirty_days_ago}})
    
    logger.info(f"Admin stats: total_users={total_users}, admin_count={admin_count}")
    
    # Subscription counts
    active_subscriptions = await db.subscriptions.count_documents({"status": "active"})
    trial_users = await db.subscriptions.count_documents({"status": "trialing"})
    expired_trials = await db.subscriptions.count_documents({"status": "expired"})
    
    # Content counts
    total_trusts = await db.trusts.count_documents({})
    total_minutes = await db.minutes_records.count_documents({})
    total_distributions = await db.distribution_records.count_documents({})
    
    # Revenue estimate (rough calculation from DB)
    monthly_subs = await db.subscriptions.count_documents({"status": "active", "plan_type": "monthly"})
    annual_subs = await db.subscriptions.count_documents({"status": "active", "plan_type": "annual"})
    revenue_estimate = (monthly_subs * 79) + (annual_subs * 790 / 12)
    
    # Real Stripe revenue data
    stripe_total_revenue_cents = 0
    stripe_mrr_cents = 0
    stripe_arr_cents = 0
    stripe_paid_customers = 0
    stripe_total_transactions = 0
    
    try:
        # Fetch all-time paid invoices from Stripe for total revenue
        all_invoices = stripe.Invoice.list(
            status="paid",
            limit=100,
            created={"gte": int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp())}
        )
        
        customer_ids = set()
        for inv in all_invoices.auto_paging_iter():
            amount = inv.amount_paid or inv.total or 0
            stripe_total_revenue_cents += amount
            stripe_total_transactions += 1
            if inv.customer_id:
                customer_ids.add(inv.customer_id)
        
        stripe_paid_customers = len(customer_ids)
        
        # Calculate MRR from active subscriptions
        # Monthly: $79/mo, Annual: $790/yr ≈ $65.83/mo
        stripe_mrr_cents = (monthly_subs * 7900) + (annual_subs * 6583)
        stripe_arr_cents = stripe_mrr_cents * 12
        
    except stripe.StripeError as e:
        logger.error(f"Stripe API error in /admin/stats: {e}")
    except Exception as e:
        logger.error(f"Error fetching Stripe data in /admin/stats: {e}")
    
    return SystemStats(
        total_users=total_users,
        active_subscriptions=active_subscriptions,
        trial_users=trial_users,
        expired_trials=expired_trials,
        admin_count=admin_count,
        total_trusts=total_trusts,
        total_minutes=total_minutes,
        total_distributions=total_distributions,
        new_users_30d=new_users_30d,
        revenue_estimate_monthly=round(revenue_estimate, 2),
        stripe_total_revenue_cents=stripe_total_revenue_cents,
        stripe_mrr_cents=stripe_mrr_cents,
        stripe_arr_cents=stripe_arr_cents,
        stripe_paid_customers=stripe_paid_customers,
        stripe_total_transactions=stripe_total_transactions,
        monthly_subs=monthly_subs,
        annual_subs=annual_subs,
    )


# ==================== REVENUE ENDPOINT ====================

@router.get("/revenue")
async def get_revenue_data(
    preset: str = Query("last_30_days", description="Date range preset: today, this_week, this_month, last_30_days, last_90_days, all_time"),
    start_date: Optional[str] = Query(None, description="Custom start date (ISO format). Overrides preset."),
    end_date: Optional[str] = Query(None, description="Custom end date (ISO format). Overrides preset."),
    admin: dict = Depends(require_admin)
):
    """
    Get detailed revenue data from Stripe for the admin dashboard.
    Includes customer-level transaction data (admin only).
    """
    # Determine date range
    now = datetime.now(timezone.utc)
    if start_date and end_date:
        try:
            start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            if end_dt <= start_dt:
                raise HTTPException(status_code=400, detail="end_date must be after start_date")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use ISO format.")
    else:
        # Use preset
        if preset == "today":
            start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_dt = now
        elif preset == "this_week":
            days_since_monday = now.weekday()
            start_dt = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
            end_dt = now
        elif preset == "this_month":
            start_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end_dt = now
        elif preset == "last_30_days":
            start_dt = now - timedelta(days=30)
            end_dt = now
        elif preset == "last_90_days":
            start_dt = now - timedelta(days=90)
            end_dt = now
        elif preset == "all_time":
            start_dt = datetime(2020, 1, 1, tzinfo=timezone.utc)
            end_dt = now
        else:
            start_dt = now - timedelta(days=30)
            end_dt = now
    
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())
    
    total_revenue_cents = 0
    total_transactions = 0
    customer_ids = set()
    revenue_by_month = defaultdict(int)
    subscriptions_by_plan = {"monthly": 0, "annual": 0}
    recent_transactions = []
    stripe_error = None
    
    try:
        if not stripe.api_key:
            raise stripe.error.AuthenticationError("Stripe API key not configured (STRIPE_SECRET_KEY missing)")
        has_more = True
        starting_after = None
        invoice_count = 0
        
        while has_more and invoice_count < 5000:
            params = {
                "status": "paid",
                "created": {"gte": start_ts, "lte": end_ts},
                "limit": 100,
            }
            if starting_after:
                params["starting_after"] = starting_after
            
            invoices = stripe.Invoice.list(**params)
            
            for inv in invoices.data:
                invoice_count += 1
                amount = inv.amount_paid or inv.total or 0
                total_revenue_cents += amount
                total_transactions += 1
                
                if inv.customer_id:
                    customer_ids.add(inv.customer_id)
                
                # Revenue by month
                inv_date = datetime.fromtimestamp(inv.created, tz=timezone.utc)
                month_key = inv_date.strftime("%Y-%m")
                revenue_by_month[month_key] += amount
                
                # Plan detection
                plan_type = "monthly"
                for line in inv.lines.data:
                    if line.price and line.price.id:
                        if line.price.id == STRIPE_ANNUAL_PRICE_ID:
                            plan_type = "annual"
                            break
                        elif line.price.id == STRIPE_MONTHLY_PRICE_ID:
                            plan_type = "monthly"
                            break
                
                subscriptions_by_plan[plan_type] = subscriptions_by_plan.get(plan_type, 0) + 1
                
                # Customer email (admin can see)
                customer_email = ""
                try:
                    if inv.customer_id:
                        customer = stripe.Customer.retrieve(inv.customer_id)
                        customer_email = customer.email or ""
                except stripe.StripeError:
                    customer_email = inv.customer_email or ""
                
                recent_transactions.append({
                    "date": inv_date.isoformat(),
                    "customer_email": customer_email,
                    "amount_cents": amount,
                    "plan": plan_type,
                    "status": inv.status,
                    "invoice_id": inv.id,
                })
            
            has_more = invoices.has_more
            if has_more and invoices.data:
                starting_after = invoices.data[-1].id
            else:
                break
                
    except stripe.StripeError as e:
        logger.error(f"Stripe API error in /admin/revenue: {e}")
        stripe_error = str(e)
    except Exception as e:
        logger.error(f"Error fetching revenue data: {e}")
        stripe_error = str(e)
    
    # Sort recent transactions by date descending
    recent_transactions.sort(key=lambda t: t["date"], reverse=True)
    recent_transactions = recent_transactions[:100]
    
    # Format revenue by month
    revenue_by_month_list = [
        {"month": k, "amount_cents": v}
        for k, v in sorted(revenue_by_month.items())
    ]
    
    # Calculate MRR and ARR from DB subscriptions
    monthly_active = await db.subscriptions.count_documents({"status": "active", "plan_type": "monthly"})
    annual_active = await db.subscriptions.count_documents({"status": "active", "plan_type": "annual"})
    mrr_cents = (monthly_active * 7900) + (annual_active * 6583)
    arr_cents = mrr_cents * 12
    
    # Period-specific revenue
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    revenue_today_cents = 0
    revenue_this_week_cents = 0
    revenue_this_month_cents = 0
    revenue_all_time_cents = 0
    
    if not stripe_error:
        try:
            today_data = stripe.Invoice.list(status="paid", limit=100, created={"gte": int(today_start.timestamp())})
            for inv in today_data.auto_paging_iter():
                revenue_today_cents += inv.amount_paid or inv.total or 0
            
            week_data = stripe.Invoice.list(status="paid", limit=100, created={"gte": int(week_start.timestamp())})
            for inv in week_data.auto_paging_iter():
                revenue_this_week_cents += inv.amount_paid or inv.total or 0
            
            month_data = stripe.Invoice.list(status="paid", limit=100, created={"gte": int(month_start.timestamp())})
            for inv in month_data.auto_paging_iter():
                revenue_this_month_cents += inv.amount_paid or inv.total or 0
            
            all_time_data = stripe.Invoice.list(status="paid", limit=100, created={"gte": int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp())})
            for inv in all_time_data.auto_paging_iter():
                revenue_all_time_cents += inv.amount_paid or inv.total or 0
        except stripe.StripeError as e:
            logger.error(f"Stripe API error fetching period revenue: {e}")
            if not stripe_error:
                stripe_error = str(e)
    
    avg_revenue_per_customer_cents = (
        total_revenue_cents // len(customer_ids) if len(customer_ids) > 0 else 0
    )
    
    return {
        "total_revenue_cents": total_revenue_cents,
        "total_revenue_formatted": f"${total_revenue_cents / 100:,.2f}",
        "mrr_cents": mrr_cents,
        "mrr_formatted": f"${mrr_cents / 100:,.2f}",
        "arr_cents": arr_cents,
        "arr_formatted": f"${arr_cents / 100:,.2f}",
        "total_transactions": total_transactions,
        "paid_customers": len(customer_ids),
        "avg_revenue_per_customer_cents": avg_revenue_per_customer_cents,
        "avg_revenue_per_customer_formatted": f"${avg_revenue_per_customer_cents / 100:,.2f}",
        "revenue_by_month": revenue_by_month_list,
        "subscriptions_by_plan": subscriptions_by_plan,
        "revenue_today_cents": revenue_today_cents,
        "revenue_today_formatted": f"${revenue_today_cents / 100:,.2f}",
        "revenue_this_week_cents": revenue_this_week_cents,
        "revenue_this_week_formatted": f"${revenue_this_week_cents / 100:,.2f}",
        "revenue_this_month_cents": revenue_this_month_cents,
        "revenue_this_month_formatted": f"${revenue_this_month_cents / 100:,.2f}",
        "revenue_all_time_cents": revenue_all_time_cents,
        "revenue_all_time_formatted": f"${revenue_all_time_cents / 100:,.2f}",
        "monthly_subs": monthly_active,
        "annual_subs": annual_active,
        "recent_transactions": recent_transactions,
        "date_range": {
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "preset": preset,
        },
        "stripe_error": stripe_error,
    }


# ==================== STATS USER MANAGEMENT ====================

@router.post("/customers/{user_id}/grant-stats")
async def grant_stats_access(
    user_id: str,
    admin: dict = Depends(require_admin)
):
    """Grant stats access to a user."""
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    
    if not user:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "is_stats_user": True,
            "stats_granted_by": admin["user_id"],
            "stats_granted_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    logger.info(f"Admin {admin['email']} granted stats access to {user['email']}")
    
    return {"message": f"Stats access granted to {user['email']}"}


@router.post("/customers/{user_id}/revoke-stats")
async def revoke_stats_access(
    user_id: str,
    admin: dict = Depends(require_admin)
):
    """Revoke stats access from a user."""
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    
    if not user:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "is_stats_user": False,
            "stats_revoked_by": admin["user_id"],
            "stats_revoked_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    logger.info(f"Admin {admin['email']} revoked stats access from {user['email']}")
    
    return {"message": f"Stats access revoked from {user['email']}"}


@router.get("/stats-users")
async def list_stats_users(admin: dict = Depends(require_admin)):
    """List all users with stats access."""
    stats_users = await db.users.find(
        {"is_stats_user": True},
        {"_id": 0, "password_hash": 0}
    ).to_list(100)
    
    return {
        "stats_users": [
            {
                "user_id": u["user_id"],
                "email": u.get("email", ""),
                "name": u.get("name", ""),
                "is_admin": u.get("is_admin", False),
                "created_at": u.get("created_at", ""),
                "stats_granted_at": u.get("stats_granted_at"),
            }
            for u in stats_users
        ]
    }


@router.get("/debug/db-check")
async def debug_db_check(admin: dict = Depends(require_admin)):
    """
    Debug endpoint to check database connectivity and counts.
    """
    try:
        # Get raw counts
        user_count = await db.users.count_documents({})
        sub_count = await db.subscriptions.count_documents({})
        trust_count = await db.trusts.count_documents({})
        
        # Get sample users (just emails)
        sample_users = await db.users.find({}, {"_id": 0, "email": 1, "is_admin": 1}).limit(10).to_list(10)
        
        # Get collection names
        collections = await db.list_collection_names()
        
        return {
            "status": "ok",
            "database": db.name,
            "collections": collections,
            "counts": {
                "users": user_count,
                "subscriptions": sub_count,
                "trusts": trust_count
            },
            "sample_users": [u.get("email") for u in sample_users],
            "admin_requesting": admin.get("email")
        }
    except Exception as e:
        logger.error(f"DB check failed: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


# ==================== ADMIN USER MANAGEMENT ====================

@router.post("/create-admin")
async def create_admin_user(
    request: CreateAdminUserRequest,
    admin: dict = Depends(require_admin)
):
    """
    Create a new admin user account.
    """
    email = request.email.lower().strip()
    
    # Check if user already exists
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    
    if existing:
        # Update existing user to be admin
        await db.users.update_one(
            {"email": email},
            {"$set": {
                "is_admin": True,
                "admin_granted_by": admin["user_id"],
                "admin_granted_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        # Give them forever_free subscription
        await db.subscriptions.update_one(
            {"user_id": existing["user_id"]},
            {"$set": {
                "plan_type": "forever_free",
                "status": "active",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )
        
        return {"message": f"Existing user {email} promoted to admin", "user_id": existing["user_id"]}
    
    # Create new user
    now = datetime.now(timezone.utc)
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    
    user_doc = {
        "user_id": user_id,
        "email": email,
        "name": request.name,
        "is_admin": True,
        "admin_granted_by": admin["user_id"],
        "admin_granted_at": now.isoformat(),
        "created_at": now.isoformat()
    }
    
    if request.password:
        user_doc["password_hash"] = hash_password(request.password)
    
    await db.users.insert_one(user_doc)
    
    # Create forever_free subscription
    await db.subscriptions.insert_one({
        "subscription_id": f"sub_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "plan_type": "forever_free",
        "status": "active",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat()
    })
    
    # Initialize onboarding
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
        "created_at": now.isoformat(),
        "updated_at": now.isoformat()
    })
    
    logger.info(f"Admin {admin['email']} created new admin user {email}")
    
    return {
        "message": f"Admin user {email} created",
        "user_id": user_id,
        "login_method": "password" if request.password else "google_oauth"
    }


@router.post("/create-user")
async def create_user(
    request: CreateUserRequest,
    admin: dict = Depends(require_admin)
):
    """
    Create a new regular user account (name + email only).
    Sends a welcome email with a set-password link.
    User sets their own password on first login.
    """
    email = request.email.lower().strip()
    name = request.name.strip()
    
    # Check if user already exists
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A user with email {email} already exists"
        )
    
    # Create new user (no password — user sets their own via welcome email)
    now = datetime.now(timezone.utc)
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    
    user_doc = {
        "user_id": user_id,
        "email": email,
        "name": name,
        "is_admin": False,
        "created_at": now.isoformat(),
        "created_by": admin["user_id"],
        "created_via": "admin_create"
    }
    
    await db.users.insert_one(user_doc)
    
    # Create trial subscription
    trial_end = now + timedelta(days=TRIAL_DAYS)
    await db.subscriptions.insert_one({
        "subscription_id": f"sub_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "plan_type": "trial",
        "status": "trialing",
        "trial_end": trial_end.isoformat(),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat()
    })
    
    # Initialize onboarding
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
        "created_at": now.isoformat(),
        "updated_at": now.isoformat()
    })
    
    # Generate password set token (expires in 24 hours — longer than normal reset)
    set_password_token = secrets.token_urlsafe(32)
    expires_at = now + timedelta(hours=24)
    
    await db.password_resets.update_one(
        {"user_id": user_id},
        {"$set": {
            "token": set_password_token,
            "expires_at": expires_at.isoformat(),
            "created_at": now.isoformat(),
            "purpose": "set_password"
        }},
        upsert=True
    )
    
    # Build set-password URL
    frontend_url = os.environ.get('FRONTEND_URL', 'https://app.trustoffice.app')
    set_password_url = f"{frontend_url}/reset-password?token={set_password_token}"
    
    # Send welcome + set-password email (awaited so we can report status)
    email_result = await email_service.send_welcome_set_password_email(
        to_email=email,
        user_name=name,
        set_password_url=set_password_url
    )
    
    email_status = email_result.get("status", "unknown")
    email_message = "Welcome email sent with set-password link."
    if email_status == "failed":
        email_message = f"User created, but welcome email failed: {email_result.get('error', 'unknown error')}"
        logger.error(f"Welcome email failed for {email}: {email_result.get('error')}")
    elif email_status == "skipped":
        email_message = "User created, but email service is not configured. Set-password link generated but not emailed."
        logger.warning(f"Email service not configured — welcome email skipped for {email}")
    
    logger.info(f"Admin {admin['email']} created new user {email} (via admin create-user) — email: {email_status}")
    
    return {
        "message": f"User {email} created. {email_message}",
        "user_id": user_id,
        "email": email,
        "name": name,
        "set_password_expires": expires_at.isoformat(),
        "email_status": email_status
    }


@router.get("/admins")
async def list_admins(admin: dict = Depends(require_admin)):
    """
    List all admin users.
    """
    admins = await db.users.find(
        {"is_admin": True},
        {"_id": 0, "password_hash": 0}
    ).to_list(100)
    
    return {
        "admins": [
            {
                "user_id": a["user_id"],
                "email": a["email"],
                "name": a.get("name", ""),
                "created_at": a.get("created_at"),
                "admin_granted_at": a.get("admin_granted_at")
            }
            for a in admins
        ]
    }
