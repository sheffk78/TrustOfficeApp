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

# Forever free accounts - these emails get unlimited access without payment
FOREVER_FREE_EMAILS = {
    "admin@wingpointtrusts.com",
}

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

# Premium feature error message
PREMIUM_FEATURE_ERROR_MESSAGE = "This feature requires a paid subscription. Please upgrade from trial to access."
PREMIUM_FEATURE_ERROR_CODE = 402


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
    
    # Check if user has a forever free account
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1})
    user_email = user.get("email", "").lower() if user else ""
    is_forever_free = user_email in FOREVER_FREE_EMAILS
    
    sub = await db.subscriptions.find_one({"user_id": user_id}, {"_id": 0})
    
    # If no subscription exists, create one (trial for normal users, active for forever free)
    if not sub:
        if is_forever_free:
            # Forever free account - give them a permanent active subscription
            sub = {
                "subscription_id": f"sub_{uuid.uuid4().hex[:12]}",
                "user_id": user_id,
                "plan_type": "forever_free",
                "status": "active",
                "trial_start_date": None,
                "trial_end_date": None,
                "stripe_customer_id": None,
                "stripe_subscription_id": None,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "notes": "Forever free account - admin@wingpointtrusts.com"
            }
        else:
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
    
    # For forever free accounts, always return active status regardless of stored status
    if is_forever_free:
        return SubscriptionState(
            user_id=user_id,
            subscription_id=sub.get("subscription_id"),
            plan_type="forever_free",
            status="active",
            trial_start_date=None,
            trial_end_date=None,
            trial_days_remaining=None,
            is_trial=False,
            is_active=True,
            is_read_only=False,
            stripe_customer_id=None,
            stripe_subscription_id=None,
            current_period_end=None,
            cancel_at_period_end=None,
        )
    
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




# ==================== FEATURE GATING ====================

class Feature:
    """Feature flags for premium gating"""
    # Core features - available to all (trial + paid)
    MINUTES_BASIC = "minutes_basic"
    DISTRIBUTIONS_BASIC = "distributions_basic"
    GOVERNANCE_BASIC = "governance_basic"
    SINGLE_TRUST = "single_trust"
    
    # Premium features - paid only (monthly/annual)
    PDF_NO_WATERMARK = "pdf_no_watermark"
    CSV_EXPORT = "csv_export"
    MULTIPLE_TRUSTS = "multiple_trusts"
    BENEVOLENCE_MODE = "benevolence_mode"
    BENEFICIARY_DASHBOARD = "beneficiary_dashboard"
    TRUST_UNITS = "trust_units"
    GOVERNANCE_HISTORY = "governance_history"
    ADVANCED_TEMPLATES = "advanced_templates"


# Features available to each plan type
PLAN_FEATURES = {
    "trial": {
        Feature.MINUTES_BASIC,
        Feature.DISTRIBUTIONS_BASIC,
        Feature.GOVERNANCE_BASIC,
        Feature.SINGLE_TRUST,
        # Trial gets limited features with watermark
    },
    "monthly": {
        # All core features
        Feature.MINUTES_BASIC,
        Feature.DISTRIBUTIONS_BASIC,
        Feature.GOVERNANCE_BASIC,
        Feature.SINGLE_TRUST,
        # Plus all premium features
        Feature.PDF_NO_WATERMARK,
        Feature.CSV_EXPORT,
        Feature.MULTIPLE_TRUSTS,
        Feature.BENEVOLENCE_MODE,
        Feature.BENEFICIARY_DASHBOARD,
        Feature.TRUST_UNITS,
        Feature.GOVERNANCE_HISTORY,
        Feature.ADVANCED_TEMPLATES,
    },
    "annual": {
        # Same as monthly
        Feature.MINUTES_BASIC,
        Feature.DISTRIBUTIONS_BASIC,
        Feature.GOVERNANCE_BASIC,
        Feature.SINGLE_TRUST,
        Feature.PDF_NO_WATERMARK,
        Feature.CSV_EXPORT,
        Feature.MULTIPLE_TRUSTS,
        Feature.BENEVOLENCE_MODE,
        Feature.BENEFICIARY_DASHBOARD,
        Feature.TRUST_UNITS,
        Feature.GOVERNANCE_HISTORY,
        Feature.ADVANCED_TEMPLATES,
    },
    "forever_free": {
        # All features - forever free accounts get everything
        Feature.MINUTES_BASIC,
        Feature.DISTRIBUTIONS_BASIC,
        Feature.GOVERNANCE_BASIC,
        Feature.SINGLE_TRUST,
        Feature.PDF_NO_WATERMARK,
        Feature.CSV_EXPORT,
        Feature.MULTIPLE_TRUSTS,
        Feature.BENEVOLENCE_MODE,
        Feature.BENEFICIARY_DASHBOARD,
        Feature.TRUST_UNITS,
        Feature.GOVERNANCE_HISTORY,
        Feature.ADVANCED_TEMPLATES,
    }
}


async def check_feature_access(user_id: str, feature: str) -> bool:
    """
    Check if a user has access to a specific feature based on their subscription plan.
    Returns True if access is granted, False otherwise.
    """
    state = await get_subscription_state(user_id)
    
    # If subscription is not active, no premium features
    if not state.is_active:
        return feature in PLAN_FEATURES.get("trial", set())
    
    plan_features = PLAN_FEATURES.get(state.plan_type, set())
    return feature in plan_features


async def require_feature(feature: str, user: dict) -> dict:
    """
    Dependency that checks if user has access to a specific feature.
    Raises 402 if feature is not available on their plan.
    """
    has_access = await check_feature_access(user["user_id"], feature)
    
    if not has_access:
        state = await get_subscription_state(user["user_id"])
        raise HTTPException(
            status_code=PREMIUM_FEATURE_ERROR_CODE,
            detail=f"{PREMIUM_FEATURE_ERROR_MESSAGE} Feature: {feature}",
            headers={
                "X-Required-Feature": feature,
                "X-Current-Plan": state.plan_type
            }
        )
    
    return user


def require_premium_feature(feature: str):
    """
    Factory function to create a dependency that requires a specific feature.
    Usage: user = Depends(require_premium_feature(Feature.CSV_EXPORT))
    """
    async def _require_feature(user: dict = Depends(get_current_user)) -> dict:
        return await require_feature(feature, user)
    return _require_feature


async def get_user_features(user_id: str) -> dict:
    """
    Get a dictionary of all features and whether the user has access to them.
    Useful for frontend to show/hide features.
    """
    state = await get_subscription_state(user_id)
    plan_features = PLAN_FEATURES.get(state.plan_type, set()) if state.is_active else PLAN_FEATURES.get("trial", set())
    
    return {
        "plan_type": state.plan_type,
        "is_active": state.is_active,
        "is_trial": state.is_trial,
        "features": {
            Feature.MINUTES_BASIC: Feature.MINUTES_BASIC in plan_features,
            Feature.DISTRIBUTIONS_BASIC: Feature.DISTRIBUTIONS_BASIC in plan_features,
            Feature.GOVERNANCE_BASIC: Feature.GOVERNANCE_BASIC in plan_features,
            Feature.SINGLE_TRUST: Feature.SINGLE_TRUST in plan_features,
            Feature.PDF_NO_WATERMARK: Feature.PDF_NO_WATERMARK in plan_features,
            Feature.CSV_EXPORT: Feature.CSV_EXPORT in plan_features,
            Feature.MULTIPLE_TRUSTS: Feature.MULTIPLE_TRUSTS in plan_features,
            Feature.BENEVOLENCE_MODE: Feature.BENEVOLENCE_MODE in plan_features,
            Feature.BENEFICIARY_DASHBOARD: Feature.BENEFICIARY_DASHBOARD in plan_features,
            Feature.TRUST_UNITS: Feature.TRUST_UNITS in plan_features,
            Feature.GOVERNANCE_HISTORY: Feature.GOVERNANCE_HISTORY in plan_features,
            Feature.ADVANCED_TEMPLATES: Feature.ADVANCED_TEMPLATES in plan_features,
        }
    }


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


async def require_write_access(user: dict = Depends(get_current_user)) -> dict:
    """
    Dependency for write operations (create, update, delete).
    Returns user if subscription is active, raises 403 if read-only.
    Use this for all POST, PUT, PATCH, DELETE endpoints that modify user data.
    """
    state = await get_subscription_state(user["user_id"])
    
    if state.is_read_only:
        raise HTTPException(
            status_code=READ_ONLY_ERROR_CODE,
            detail=READ_ONLY_ERROR_MESSAGE,
            headers={"X-Subscription-Status": state.status}
        )
    
    return user


async def get_user_with_subscription(user: dict = Depends(get_current_user)) -> dict:
    """
    Dependency that returns user with subscription state attached.
    Allows read access regardless of subscription status.
    """
    state = await get_subscription_state(user["user_id"])
    return {
        **user,
        "subscription_state": state.model_dump()
    }


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



# Import models for calculate_health_score
from models import HealthColor, HealthScoreCriterion


async def calculate_health_score(trust_id: str, user_id: str) -> dict:
    """
    Calculate governance health score using 5 criteria (20 points each):
    1. Quarterly Minutes - minutes generated this quarter
    2. Task Compliance - no overdue tasks
    3. Compensation Alignment - YTD ≤ approved annual
    4. Distribution Documentation - at least 1 distribution logged
    5. Annual Review - annual_review task completed in last 12 months
    """
    now = datetime.now(timezone.utc)
    criteria = []
    total_score = 0
    
    # 1. Quarterly Minutes (+20)
    quarter_start = get_quarter_start(now)
    quarterly_minutes = await db.minutes_records.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "created_at": {"$gte": quarter_start.isoformat()}
    })
    quarterly_achieved = quarterly_minutes > 0
    criteria.append(HealthScoreCriterion(
        name="Quarterly Minutes",
        description="Minutes generated this quarter",
        points=20 if quarterly_achieved else 0,
        achieved=quarterly_achieved
    ))
    if quarterly_achieved:
        total_score += 20
    
    # 2. Task Compliance (+20)
    overdue_tasks = await db.governance_tasks.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "completed_at": None,
        "due_date": {"$lt": now.isoformat()}
    })
    task_compliance = overdue_tasks == 0
    criteria.append(HealthScoreCriterion(
        name="Task Compliance",
        description="No overdue governance tasks",
        points=20 if task_compliance else 0,
        achieved=task_compliance
    ))
    if task_compliance:
        total_score += 20
    
    # 3. Compensation Alignment (+20)
    year_start = get_year_start(now)
    comp_plan = await db.compensation_plans.find_one(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0},
        sort=[("effective_date", -1)]
    )
    
    if comp_plan:
        # Calculate YTD payments
        ytd_payments = await db.compensation_payments.find(
            {"trust_id": trust_id, "user_id": user_id, "date": {"$gte": year_start.isoformat()}},
            {"_id": 0}
        ).to_list(1000)
        ytd_total = sum(p.get("amount", 0) for p in ytd_payments)
        # Support both annual_approved_amount and annual_fee fields
        approved_amount = comp_plan.get("annual_approved_amount") or comp_plan.get("annual_fee") or comp_plan.get("annual_amount", 0)
        comp_aligned = ytd_total <= approved_amount
    else:
        comp_aligned = True  # No plan means no overage
    
    criteria.append(HealthScoreCriterion(
        name="Compensation Alignment",
        description="YTD compensation within approved plan",
        points=20 if comp_aligned else 0,
        achieved=comp_aligned
    ))
    if comp_aligned:
        total_score += 20
    
    # 4. Distribution Documentation (+20) - includes benevolence documentation quality
    dist_count = await db.distribution_records.count_documents({
        "trust_id": trust_id,
        "user_id": user_id
    })
    
    # Check benevolence documentation quality
    benevolence_dists = await db.distribution_records.find({
        "trust_id": trust_id,
        "user_id": user_id,
        "is_benevolence": True
    }, {"_id": 0}).to_list(1000)
    
    benevolence_count = len(benevolence_dists)
    incomplete_benevolence = 0
    
    for bd in benevolence_dists:
        # Check for missing key fields
        if not bd.get("benevolence_recipient_name") or not bd.get("benevolence_need_description"):
            incomplete_benevolence += 1
        # Check for missing approval/minutes
        elif not bd.get("approved_at") and not bd.get("minutes_record_id"):
            incomplete_benevolence += 1
    
    # Determine points based on documentation completeness
    if dist_count == 0:
        dist_documented = False
        dist_points = 0
        dist_description = "No distributions logged"
    elif benevolence_count > 0 and incomplete_benevolence > 0:
        # Has benevolence distributions but some incomplete
        dist_documented = True  # Partially achieved
        completeness_ratio = (benevolence_count - incomplete_benevolence) / benevolence_count
        dist_points = int(20 * (0.5 + 0.5 * completeness_ratio))  # 10-20 points based on completeness
        dist_description = f"Distributions logged; {incomplete_benevolence}/{benevolence_count} benevolence distributions need documentation"
    else:
        dist_documented = True
        dist_points = 20
        if benevolence_count > 0:
            dist_description = f"All distributions documented ({benevolence_count} benevolence distributions fully documented)"
        else:
            dist_description = "Distributions logged"
    
    criteria.append(HealthScoreCriterion(
        name="Distribution Documentation",
        description=dist_description,
        points=dist_points,
        achieved=dist_documented
    ))
    total_score += dist_points
    
    # 5. Annual Review (+20)
    one_year_ago = (now - timedelta(days=365)).isoformat()
    annual_review = await db.governance_tasks.find_one({
        "trust_id": trust_id,
        "user_id": user_id,
        "task_type": "annual_review",
        "completed_at": {"$gte": one_year_ago}
    }, {"_id": 0})
    annual_done = annual_review is not None
    criteria.append(HealthScoreCriterion(
        name="Annual Review",
        description="Annual review completed in last 12 months",
        points=20 if annual_done else 0,
        achieved=annual_done
    ))
    if annual_done:
        total_score += 20
    
    # Determine color
    if total_score >= 80:
        color = HealthColor.green
    elif total_score >= 60:
        color = HealthColor.yellow
    else:
        color = HealthColor.red
    
    # Save snapshot
    snapshot = {
        "snapshot_id": f"health_{uuid.uuid4().hex[:12]}",
        "trust_id": trust_id,
        "user_id": user_id,
        "score_value": total_score,
        "color": color.value,
        "calculated_at": now.isoformat()
    }
    await db.health_score_snapshots.insert_one(snapshot)
    
    return {
        "trust_id": trust_id,
        "total_score": total_score,
        "max_score": 100,
        "color": color.value,
        "criteria": [c.model_dump() for c in criteria],
        "calculated_at": now.isoformat()
    }
