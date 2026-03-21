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
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, EmailStr
import uuid
import logging

from database import db
from dependencies import get_current_user, hash_password, TRIAL_DAYS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ==================== MODELS ====================

class CustomerListItem(BaseModel):
    user_id: str
    email: str
    name: str
    is_admin: bool = False
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
    user_id: str
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
    is_admin: Optional[bool] = Query(None, description="Filter by admin status"),
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
        query["$or"] = [
            {"email": {"$regex": search, "$options": "i"}},
            {"name": {"$regex": search, "$options": "i"}}
        ]
    
    if is_admin is not None:
        if is_admin:
            query["is_admin"] = True
        else:
            # Users without is_admin field or with is_admin=false
            query["$or"] = query.get("$or", [])
            if not query["$or"]:
                del query["$or"]
            query["is_admin"] = {"$ne": True}
    
    # Get total count
    total = await db.users.count_documents(query)
    
    # Build sort
    sort_dir = -1 if sort_order == "desc" else 1
    
    # Get users
    skip = (page - 1) * limit
    users = await db.users.find(query, {"_id": 0, "password_hash": 0}).sort(sort_by, sort_dir).skip(skip).limit(limit).to_list(limit)
    
    # Enrich with subscription data
    customers = []
    for user in users:
        # Get subscription
        sub = await db.subscriptions.find_one({"user_id": user["user_id"]}, {"_id": 0})
        
        # Get trust count
        trust_count = await db.trusts.count_documents({"user_id": user["user_id"]})
        
        # Filter by status if specified
        sub_status = sub.get("status", "none") if sub else "none"
        if status and sub_status != status:
            continue
        
        customers.append(CustomerListItem(
            user_id=user["user_id"],
            email=user["email"],
            name=user.get("name", ""),
            is_admin=user.get("is_admin", False),
            created_at=user.get("created_at", ""),
            subscription_status=sub_status,
            subscription_plan=sub.get("plan_type", "none") if sub else "none",
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
    """
    now = datetime.now(timezone.utc)
    thirty_days_ago = (now - timedelta(days=30)).isoformat()
    
    # User counts
    total_users = await db.users.count_documents({})
    admin_count = await db.users.count_documents({"is_admin": True})
    new_users_30d = await db.users.count_documents({"created_at": {"$gte": thirty_days_ago}})
    
    # Subscription counts
    active_subscriptions = await db.subscriptions.count_documents({"status": "active"})
    trial_users = await db.subscriptions.count_documents({"status": "trialing"})
    expired_trials = await db.subscriptions.count_documents({"status": "expired"})
    
    # Content counts
    total_trusts = await db.trusts.count_documents({})
    total_minutes = await db.minutes_records.count_documents({})
    total_distributions = await db.distribution_records.count_documents({})
    
    # Revenue estimate (very rough)
    monthly_subs = await db.subscriptions.count_documents({"status": "active", "plan_type": "monthly"})
    annual_subs = await db.subscriptions.count_documents({"status": "active", "plan_type": "annual"})
    revenue_estimate = (monthly_subs * 79) + (annual_subs * 790 / 12)
    
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
        revenue_estimate_monthly=round(revenue_estimate, 2)
    )


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
        "entities_confirmed": False,
        "calendar_set": False,
        "minutes_generated": False,
        "distribution_logged": False,
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
