# Shared dependencies and helper functions
from fastapi import HTTPException, Request, Depends
from fastapi.security import HTTPBearer
from datetime import datetime, timezone, timedelta
from typing import Optional
from pydantic import BaseModel
import jwt
import bcrypt
import os
import uuid

from database import db

# JWT Config
JWT_SECRET = os.environ.get('JWT_SECRET', 'trustoffice_secret_key_change_in_production')
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24 * 7  # 7 days

TRIAL_DAYS = 14

security = HTTPBearer(auto_error=False)

# Paths that don't require active subscription (allow full access)
SUBSCRIPTION_EXEMPT_PATHS = {
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/session",
    "/api/auth/me",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
    "/api/auth/verify-reset-token",
    "/api/subscription",
    "/api/subscription/create-checkout",
    "/api/subscription/verify-payment",
    "/api/subscription/create-portal",
    "/api/subscription/cancel",
    "/api/subscription/reactivate",
    "/api/subscription/upgrade",
    "/api/stripe/webhook",
    "/api/categories",
}

# Read-only error message for expired subscriptions
READ_ONLY_ERROR_MESSAGE = "Your subscription is inactive. Please subscribe to create, update, or delete data."
READ_ONLY_ERROR_CODE = 403


# ==================== SUBSCRIPTION STATE ====================

class SubscriptionState(BaseModel):
    """Normalized subscription state object for consistent access across modules"""
    user_id: str
    subscription_id: Optional[str] = None
    plan_type: str  # "trial", "monthly", "annual"
    status: str  # "trialing", "active", "past_due", "canceled", "expired"
    trial_start_date: Optional[str] = None
    trial_end_date: Optional[str] = None
    trial_days_remaining: Optional[int] = None
    is_trial: bool = False
    is_active: bool = False
    is_read_only: bool = True  # Default to read-only for safety
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    current_period_end: Optional[str] = None
    cancel_at_period_end: Optional[bool] = None


async def get_subscription_state(user_id: str) -> SubscriptionState:
    """
    Get normalized subscription state for a user.
    Returns a consistent SubscriptionState object with all computed fields.
    This is the single source of truth for subscription status across all modules.
    """
    now = datetime.now(timezone.utc)
    
    sub = await db.subscriptions.find_one({"user_id": user_id}, {"_id": 0})
    
    # If no subscription exists, create a trial
    if not sub:
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
    
    # Initialize state with base values
    state = SubscriptionState(
        user_id=user_id,
        subscription_id=sub.get("subscription_id"),
        plan_type=sub.get("plan_type", "trial"),
        status=sub.get("status", "trialing"),
        trial_start_date=sub.get("trial_start_date"),
        trial_end_date=sub.get("trial_end_date"),
        stripe_customer_id=sub.get("stripe_customer_id"),
        stripe_subscription_id=sub.get("stripe_subscription_id"),
        current_period_end=sub.get("current_period_end"),
        cancel_at_period_end=sub.get("cancel_at_period_end"),
    )
    
    # Determine active status based on subscription type
    if sub["status"] == "active":
        # Active paid subscription
        state.is_active = True
        state.is_read_only = False
        state.is_trial = False
        state.trial_days_remaining = None
        
    elif sub["status"] == "trialing" and sub.get("trial_end_date"):
        # Trial subscription - check if still valid
        try:
            trial_end = datetime.fromisoformat(sub["trial_end_date"].replace('Z', '+00:00'))
            if trial_end.tzinfo is None:
                trial_end = trial_end.replace(tzinfo=timezone.utc)
            
            days_remaining = (trial_end - now).days
            state.trial_days_remaining = max(0, days_remaining)
            state.is_trial = True
            
            if trial_end >= now:
                # Trial is still active
                state.is_active = True
                state.is_read_only = False
            else:
                # Trial expired
                state.status = "expired"
                state.is_active = False
                state.is_read_only = True
                
        except (ValueError, TypeError, AttributeError):
            # Invalid date - treat as expired
            state.status = "expired"
            state.is_active = False
            state.is_read_only = True
            state.trial_days_remaining = 0
            
    elif sub["status"] in ["canceled", "expired", "past_due"]:
        # Inactive subscription
        state.is_active = False
        state.is_read_only = True
        state.is_trial = False
        
    else:
        # Unknown status - default to read-only for safety
        state.is_active = False
        state.is_read_only = True
    
    return state


async def get_subscription_state_for_user(user: dict = Depends("get_current_user")) -> SubscriptionState:
    """Dependency that returns subscription state for authenticated user."""
    return await get_subscription_state(user["user_id"])


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


def create_jwt_token(user_id: str, email: str) -> str:
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.now(timezone.utc)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(request: Request) -> dict:
    session_token = request.cookies.get("session_token")
    auth_header = request.headers.get("Authorization")
    
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    elif session_token:
        token = session_token
    else:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Try JWT token first
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({"user_id": payload["user_id"]}, {"_id": 0})
        if user:
            return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        pass
    
    # Try session token
    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if session:
        expires_at = session.get("expires_at")
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Session expired")
        
        user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
        if user:
            return user
    
    raise HTTPException(status_code=401, detail="Invalid token")


async def should_show_watermark(user_id: str) -> bool:
    """Check if watermark should be shown on PDFs."""
    sub = await db.subscriptions.find_one({"user_id": user_id}, {"_id": 0})
    
    if not sub:
        return True
    
    is_subscribed = False
    if sub["status"] == "active":
        is_subscribed = True
    elif sub["status"] == "trialing" and sub.get("trial_end_date"):
        try:
            trial_end = datetime.fromisoformat(sub["trial_end_date"].replace('Z', '+00:00'))
            if trial_end.tzinfo is None:
                trial_end = trial_end.replace(tzinfo=timezone.utc)
            is_subscribed = trial_end >= datetime.now(timezone.utc)
        except (ValueError, TypeError, AttributeError):
            is_subscribed = False
    
    if not is_subscribed:
        return True
    
    user_prefs = await db.user_preferences.find_one({"user_id": user_id}, {"_id": 0})
    hide_watermark = user_prefs.get("hide_watermark", False) if user_prefs else False
    
    return not hide_watermark


async def check_subscription_active(user: dict = Depends(get_current_user)) -> dict:
    """Dependency that checks if user has active subscription."""
    sub = await db.subscriptions.find_one({"user_id": user["user_id"]}, {"_id": 0})
    
    if not sub:
        now = datetime.now(timezone.utc)
        sub = {
            "subscription_id": f"sub_{uuid.uuid4().hex[:12]}",
            "user_id": user["user_id"],
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
        return user
    
    if sub["status"] == "active":
        return user
    
    if sub["status"] == "trialing" and sub.get("trial_end_date"):
        trial_end = datetime.fromisoformat(sub["trial_end_date"].replace('Z', '+00:00'))
        if trial_end.tzinfo is None:
            trial_end = trial_end.replace(tzinfo=timezone.utc)
        
        if trial_end >= datetime.now(timezone.utc):
            return user
        
        raise HTTPException(
            status_code=402,
            detail="Trial expired. Please subscribe to continue using TrustOffice."
        )
    
    if sub["status"] in ["canceled", "expired", "past_due"]:
        raise HTTPException(
            status_code=402,
            detail="Subscription inactive. Please subscribe to continue using TrustOffice."
        )
    
    return user


def get_task_status(due_date: str, completed_at: Optional[str]) -> str:
    """Calculate task status based on due_date and completed_at"""
    if completed_at:
        return "completed"
    
    try:
        due = datetime.fromisoformat(due_date.replace('Z', '+00:00'))
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        if due < datetime.now(timezone.utc):
            return "overdue"
    except (ValueError, AttributeError):
        pass
    
    return "upcoming"


def get_quarter_start(dt: datetime) -> datetime:
    """Get the start of the current quarter"""
    quarter = (dt.month - 1) // 3
    month = quarter * 3 + 1
    return datetime(dt.year, month, 1, tzinfo=timezone.utc)


def get_year_start(dt: datetime) -> datetime:
    """Get the start of the current year"""
    return datetime(dt.year, 1, 1, tzinfo=timezone.utc)


async def auto_update_onboarding(user_id: str, trust_id: str):
    """Auto-update onboarding state based on user actions"""
    updates = {}
    
    entity_count = await db.entities.count_documents({"trust_id": trust_id, "user_id": user_id})
    if entity_count > 0:
        updates["entities_confirmed"] = True
    
    task_count = await db.governance_tasks.count_documents({
        "trust_id": trust_id, 
        "user_id": user_id,
        "task_type": {"$ne": "custom"}
    })
    if task_count > 0:
        updates["calendar_set"] = True
    
    minutes_count = await db.minutes_records.count_documents({"trust_id": trust_id, "user_id": user_id})
    if minutes_count > 0:
        updates["minutes_generated"] = True
    
    dist_count = await db.distribution_records.count_documents({"trust_id": trust_id, "user_id": user_id})
    comp_count = await db.compensation_payments.count_documents({"trust_id": trust_id, "user_id": user_id})
    if dist_count > 0 or comp_count > 0:
        updates["distribution_logged"] = True
    
    if updates:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.user_onboarding.update_one(
            {"user_id": user_id},
            {"$set": updates},
            upsert=True
        )


async def create_initial_governance_tasks(trust_id: str, user_id: str):
    """Seed a new trust with default governance tasks"""
    now = datetime.now(timezone.utc)
    
    default_tasks = [
        {
            "task_id": f"task_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user_id,
            "task_type": "annual_review",
            "due_date": (now + timedelta(days=365)).isoformat(),
            "completed_at": None,
            "description": "Annual trust review and documentation",
            "created_at": now.isoformat()
        },
        {
            "task_id": f"task_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user_id,
            "task_type": "quarterly_review",
            "due_date": (now + timedelta(days=90)).isoformat(),
            "completed_at": None,
            "description": "Quarterly trust performance review",
            "created_at": now.isoformat()
        },
        {
            "task_id": f"task_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user_id,
            "task_type": "compensation_review",
            "due_date": (now + timedelta(days=180)).isoformat(),
            "completed_at": None,
            "description": "Review trustee compensation arrangements",
            "created_at": now.isoformat()
        }
    ]
    
    await db.governance_tasks.insert_many(default_tasks)
