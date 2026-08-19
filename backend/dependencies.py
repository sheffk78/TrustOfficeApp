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
import logging

from database import db

logger = logging.getLogger(__name__)

# JWT Config
JWT_SECRET = os.environ.get('JWT_SECRET')
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET environment variable is required — app will not start without it")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24 * 7  # 7 days

TRIAL_DAYS = 14  # Legacy — existing trial users still have this period. New signups go straight to paid.

# Forever free accounts - these emails get unlimited access without payment
FOREVER_FREE_EMAILS = {
    "admin@wingpointtrusts.com",
    "contact@trustoffice.app",
    "jeff@socialize.video",
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
PREMIUM_FEATURE_ERROR_MESSAGE = "This feature requires a paid subscription. Please subscribe or renew to access."
PREMIUM_FEATURE_ERROR_CODE = 402


# ==================== SUBSCRIPTION STATE ====================

class SubscriptionState(BaseModel):
    """Normalized subscription state object for consistent access across modules"""
    user_id: str
    subscription_id: Optional[str] = None
    plan_type: str  # "trustee", "estate", "advisor", "free", "forever_free", legacy: "monthly", "annual"
    status: str  # "trialing", "active", "past_due", "canceled", "expired"
    billing_period: Optional[str] = None  # "monthly" | "annual" (new tiers)
    legacy_trust_limit: Optional[int] = None  # for grandfathered users
    trial_start_date: Optional[str] = None
    trial_end_date: Optional[str] = None
    trial_days_remaining: Optional[int] = None
    is_trial: bool = False
    is_active: bool = False
    is_read_only: bool = True  # Default to read-only for safety
    is_gifted: bool = False  # Whether this is an admin-gifted account
    gift_type: Optional[str] = None  # "14day", "monthly", "annual"
    gift_days_remaining: Optional[int] = None  # Days left on gift
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    current_period_end: Optional[str] = None
    cancel_at_period_end: Optional[bool] = None


PRIMARY_ADMIN_EMAIL = "contact@trustoffice.app"


def _parse_iso_datetime(date_str: Optional[str]) -> Optional[datetime]:
    """Parse an ISO date string into a timezone-aware datetime, or None on failure."""
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError, AttributeError):
        return None


def _resolve_effective_plan_type(sub: dict, is_forever_free: bool) -> str:
    """Map legacy/trial/free plan types based on forever-free eligibility."""
    raw_plan = sub.get("plan_type")
    if raw_plan in ("trial", "forever_free", "free"):
        return "forever_free" if is_forever_free else "free"
    return raw_plan or "trial"


async def _ensure_subscription_exists(user_id: str, now: datetime) -> dict:
    """Fetch subscription for user, creating a 'none' placeholder if missing.
    
    Race-safe: if two concurrent requests both see no subscription and both
    try to insert, catch the E11000 duplicate key error and re-fetch.
    """
    sub = await db.subscriptions.find_one({"user_id": user_id}, {"_id": 0})
    if not sub:
        sub = {
            "subscription_id": f"sub_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "plan_type": "none",
            "status": "expired",
            "trial_start_date": None,
            "trial_end_date": None,
            "stripe_customer_id": None,
            "stripe_subscription_id": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "notes": "No free plan — user must subscribe for access"
        }
        try:
            await db.subscriptions.insert_one(sub)
        except Exception as e:
            # E11000 duplicate key — another concurrent request already inserted.
            # Re-fetch the existing doc instead of crashing.
            logger.warning("Subscription insert race for user=%s: %s — re-fetching", user_id, e)
            sub = await db.subscriptions.find_one({"user_id": user_id}, {"_id": 0})
            if not sub:
                # Should never happen, but don't crash
                logger.error("Subscription re-fetch returned None for user=%s after duplicate key", user_id)
                sub = {"user_id": user_id, "plan_type": "none", "status": "expired"}
    return sub


def _build_forever_free_state(user_id: str, sub: dict) -> SubscriptionState:
    """Build SubscriptionState for a forever-free user."""
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


def _apply_gift_fields_to_free_state(state: SubscriptionState, sub: dict, now: datetime):
    """Apply gifted fields and expiration checks to a free-plan state (in-place).

    A gifted free user (sub['gifted'] truthy) has FULL write access while the
    gift is active, and drops to read-only once it expires. Non-gifted free
    users stay read-only (set by _build_free_state).
    """
    if not sub.get("gifted"):
        return

    state.is_gifted = True
    state.gift_type = sub.get("gift_type", "14day")

    gift_end = sub.get("gift_end_date")
    if gift_end:
        end = _parse_iso_datetime(gift_end)
        if end:
            state.gift_days_remaining = max(0, (end - now).days)
            if end < now:
                # Gift expired -> read-only
                state.status = "expired"
                state.is_active = False
                state.is_read_only = True
                state.is_trial = False
            else:
                # Active gift -> full write access
                state.is_active = True
                state.is_read_only = False
                state.is_trial = False
    elif sub.get("trial_end_date"):
        end = _parse_iso_datetime(sub["trial_end_date"])
        if end:
            state.gift_days_remaining = max(0, (end - now).days)
            if end >= now:
                # Active gift (trial-based) -> full write access
                state.is_active = True
                state.is_read_only = False
                state.is_trial = False
            else:
                state.status = "expired"
                state.is_active = False
                state.is_read_only = True
                state.is_trial = False


def _build_free_state(user_id: str, sub: dict, now: datetime) -> SubscriptionState:
    """Build SubscriptionState for a free-plan user, including gift handling.

    FREE users (non-gifted) are READ-ONLY: they can view their own data but
    cannot do write work. Gifted users get full write access while their gift
    is active (handled in _apply_gift_fields_to_free_state).
    """
    state = SubscriptionState(
        user_id=user_id,
        subscription_id=sub.get("subscription_id"),
        plan_type="free",
        status="active",
        trial_start_date=sub.get("trial_start_date"),
        trial_end_date=sub.get("trial_end_date"),
        trial_days_remaining=None,
        is_trial=True,
        is_active=True,
        is_read_only=True,
        stripe_customer_id=sub.get("stripe_customer_id"),
        stripe_subscription_id=sub.get("stripe_subscription_id"),
        current_period_end=sub.get("current_period_end"),
        cancel_at_period_end=sub.get("cancel_at_period_end"),
    )
    _apply_gift_fields_to_free_state(state, sub, now)
    return state


def _apply_active_status(state: SubscriptionState):
    """Mark state as active paid subscription."""
    state.is_active = True
    state.is_read_only = False
    state.is_trial = False
    state.trial_days_remaining = None


def _apply_trial_status(state: SubscriptionState, sub: dict, now: datetime):
    """Apply trialing status with trial-end validation."""
    trial_end = _parse_iso_datetime(sub.get("trial_end_date"))
    if not trial_end:
        state.is_active = False
        state.is_read_only = True
        state.trial_days_remaining = 0
        return

    days_remaining = (trial_end - now).days
    state.trial_days_remaining = max(0, days_remaining)
    state.is_trial = True

    if trial_end >= now:
        state.is_active = True
        state.is_read_only = False
    else:
        state.status = "expired"
        state.is_active = False
        state.is_read_only = True


def _apply_inactive_status(state: SubscriptionState):
    """Mark state as inactive (canceled, expired, past_due, or unknown)."""
    state.is_active = False
    state.is_read_only = True
    state.is_trial = False


def _apply_gifted_override(state: SubscriptionState, sub: dict, now: datetime):
    """Apply gifted display fields and expiry check for paid plans (in-place)."""
    if not sub.get("gifted") or state.is_gifted:
        return

    state.is_gifted = True
    state.gift_type = sub.get("gift_type", "14day")

    gift_end = _parse_iso_datetime(sub.get("gift_end_date"))
    if not gift_end:
        state.gift_days_remaining = None
        return

    state.gift_days_remaining = max(0, (gift_end - now).days)

    # A gift is not a paid subscription. Only a real Stripe subscription
    # preserves access after the gift window ends.
    has_active_paid_sub = bool(sub.get("stripe_subscription_id"))
    if gift_end < now and not has_active_paid_sub:
        state.status = "expired"
        state.is_active = False
        state.is_read_only = True
        state.is_trial = False


_STATUS_HANDLERS = {
    "active": _apply_active_status,
    "trialing": _apply_trial_status,
}


def _apply_status(state: SubscriptionState, sub: dict, now: datetime):
    """Apply the correct status handler based on subscription status."""
    handler = _STATUS_HANDLERS.get(sub["status"])
    if handler:
        if sub["status"] == "trialing":
            handler(state, sub, now)
        else:
            handler(state)
    else:
        _apply_inactive_status(state)


def _build_paid_state(user_id: str, sub: dict, now: datetime) -> SubscriptionState:
    """Build SubscriptionState for a paid/trial subscription with status-based logic."""
    state = SubscriptionState(
        user_id=user_id,
        subscription_id=sub.get("subscription_id"),
        plan_type=sub.get("plan_type", "trial"),
        status=sub.get("status", "trialing"),
        billing_period=sub.get("billing_period"),
        legacy_trust_limit=sub.get("legacy_trust_limit"),
        trial_start_date=sub.get("trial_start_date"),
        trial_end_date=sub.get("trial_end_date"),
        stripe_customer_id=sub.get("stripe_customer_id"),
        stripe_subscription_id=sub.get("stripe_subscription_id"),
        current_period_end=sub.get("current_period_end"),
        cancel_at_period_end=sub.get("cancel_at_period_end"),
    )

    _apply_status(state, sub, now)
    _apply_gifted_override(state, sub, now)
    return state


async def get_subscription_state(user_id: str) -> SubscriptionState:
    """
    Get normalized subscription state for a user.
    Returns a consistent SubscriptionState object with all computed fields.
    This is the single source of truth for subscription status across all modules.
    """
    now = datetime.now(timezone.utc)

    # Check if user has a forever free account or is an admin
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "is_admin": 1})
    user_email = user.get("email", "").lower() if user else ""
    is_admin = user.get("is_admin", False) if user else False

    is_primary_admin = user_email == PRIMARY_ADMIN_EMAIL

    sub = await _ensure_subscription_exists(user_id, now)
    sub_plan_is_forever_free = sub.get("plan_type") == "forever_free"
    is_forever_free = user_email in FOREVER_FREE_EMAILS or is_admin or is_primary_admin or sub_plan_is_forever_free
    effective_plan_type = _resolve_effective_plan_type(sub, is_forever_free)

    if effective_plan_type == "forever_free":
        return _build_forever_free_state(user_id, sub)

    if effective_plan_type == "free":
        return _build_free_state(user_id, sub, now)

    return _build_paid_state(user_id, sub, now)




# ==================== FEATURE GATING ====================

class Feature:
    """Feature flags for premium gating"""
    # Core features - available to all (trial + paid)
    MINUTES_BASIC = "minutes_basic"
    DISTRIBUTIONS_BASIC = "distributions_basic"
    GOVERNANCE_BASIC = "governance_basic"
    SINGLE_TRUST = "single_trust"
    
    # Premium features - paid only
    PDF_NO_WATERMARK = "pdf_no_watermark"
    CSV_EXPORT = "csv_export"
    MULTIPLE_TRUSTS = "multiple_trusts"
    BENEVOLENCE_MODE = "benevolence_mode"
    BENEFICIARY_DASHBOARD = "beneficiary_dashboard"
    TRUST_UNITS = "trust_units"
    GOVERNANCE_HISTORY = "governance_history"
    ADVANCED_TEMPLATES = "advanced_templates"
    
    # Advisor-tier features (Phase 2 sprint, not yet built)
    CLIENT_VIEW = "client_view"           # Advisor can view client trusts
    WHITE_LABEL_BINDER = "white_label"    # White-label PDF binder export
    MULTI_SIGNATURE = "multi_signature"   # Multi-signature approvals


# Features available to each plan type
PLAN_FEATURES = {
    "trial": {
        Feature.MINUTES_BASIC,
        Feature.DISTRIBUTIONS_BASIC,
        Feature.GOVERNANCE_BASIC,
        Feature.SINGLE_TRUST,
        Feature.MULTIPLE_TRUSTS,
        # Trial gets limited features with watermark (legacy — existing trial users)
    },
    "free": {
        # Free plan — core trust management, up to 10 trusts.
        Feature.MINUTES_BASIC,
        Feature.DISTRIBUTIONS_BASIC,
        Feature.GOVERNANCE_BASIC,
        Feature.SINGLE_TRUST,
        Feature.MULTIPLE_TRUSTS,
    },
    "none": {
        # No features until they subscribe
    },
    # Legacy plans (migrated to trustee but kept for compatibility)
    "monthly": {
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
    "annual": {
        # Same as monthly (legacy)
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
    # New 3-tier system
    "trustee": {
        # All current features, single trust
        Feature.MINUTES_BASIC,
        Feature.DISTRIBUTIONS_BASIC,
        Feature.GOVERNANCE_BASIC,
        Feature.PDF_NO_WATERMARK,
        Feature.CSV_EXPORT,
        Feature.BENEVOLENCE_MODE,
        Feature.BENEFICIARY_DASHBOARD,
        Feature.TRUST_UNITS,
        Feature.GOVERNANCE_HISTORY,
        Feature.ADVANCED_TEMPLATES,
        Feature.SINGLE_TRUST,
    },
    "estate": {
        # Everything in trustee + multi-trust
        Feature.MINUTES_BASIC,
        Feature.DISTRIBUTIONS_BASIC,
        Feature.GOVERNANCE_BASIC,
        Feature.PDF_NO_WATERMARK,
        Feature.CSV_EXPORT,
        Feature.BENEVOLENCE_MODE,
        Feature.BENEFICIARY_DASHBOARD,
        Feature.TRUST_UNITS,
        Feature.GOVERNANCE_HISTORY,
        Feature.ADVANCED_TEMPLATES,
        Feature.MULTIPLE_TRUSTS,
    },
    "advisor": {
        # Everything in estate + advisor-exclusive features
        Feature.MINUTES_BASIC,
        Feature.DISTRIBUTIONS_BASIC,
        Feature.GOVERNANCE_BASIC,
        Feature.PDF_NO_WATERMARK,
        Feature.CSV_EXPORT,
        Feature.BENEVOLENCE_MODE,
        Feature.BENEFICIARY_DASHBOARD,
        Feature.TRUST_UNITS,
        Feature.GOVERNANCE_HISTORY,
        Feature.ADVANCED_TEMPLATES,
        Feature.MULTIPLE_TRUSTS,
        Feature.CLIENT_VIEW,
        Feature.WHITE_LABEL_BINDER,
        Feature.MULTI_SIGNATURE,
    },
    "wingpoint": {
        # WingPoint exclusive annual plan — Estate-level features, unlimited trusts
        Feature.MINUTES_BASIC,
        Feature.DISTRIBUTIONS_BASIC,
        Feature.GOVERNANCE_BASIC,
        Feature.PDF_NO_WATERMARK,
        Feature.CSV_EXPORT,
        Feature.BENEVOLENCE_MODE,
        Feature.BENEFICIARY_DASHBOARD,
        Feature.TRUST_UNITS,
        Feature.GOVERNANCE_HISTORY,
        Feature.ADVANCED_TEMPLATES,
        Feature.MULTIPLE_TRUSTS,
    },
    "forever_free": {
        # Free tier — core trust management, up to 10 trusts.
        Feature.MINUTES_BASIC,
        Feature.DISTRIBUTIONS_BASIC,
        Feature.GOVERNANCE_BASIC,
        Feature.SINGLE_TRUST,
        Feature.MULTIPLE_TRUSTS,
        Feature.BENEFICIARY_DASHBOARD,
        Feature.TRUST_UNITS,
        Feature.GOVERNANCE_HISTORY,
        Feature.ADVANCED_TEMPLATES,
        Feature.PDF_NO_WATERMARK,
        Feature.CSV_EXPORT,
        Feature.BENEVOLENCE_MODE,
    }
}

# ==================== TRUST LIMITS ====================

PLAN_TRUST_LIMITS = {
    "none": 0,
    "free": 1,
    "forever_free": 1,
    "trustee": 1,
    "estate": 8,
    "advisor": float('inf'),  # unlimited
    "wingpoint": float('inf'),  # unlimited — WingPoint exclusive annual plan
    # Legacy (grandfathered)
    "monthly": 10,
    "annual": 10,
    "trial": 10,
}

def get_trust_limit(plan_type: str, legacy_limit: Optional[int] = None) -> float:
    """Get the trust limit for a plan, respecting grandfathered limits."""
    if legacy_limit is not None:
        return legacy_limit  # grandfathered users keep their limit
    return PLAN_TRUST_LIMITS.get(plan_type, 1)


async def check_feature_access(user_id: str, feature: str) -> bool:
    """
    Check if a user has access to a specific feature based on their subscription plan.
    Returns True if access is granted, False otherwise.
    """
    state = await get_subscription_state(user_id)
    
    # If subscription is not active, no premium features
    if not state.is_active:
        return False
    
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
    plan_features = PLAN_FEATURES.get(state.plan_type, set()) if state.is_active else PLAN_FEATURES.get("free", set())
    
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
        "jti": str(uuid.uuid4()),  # Unique token ID for revocation support
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.now(timezone.utc)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def _check_jwt_revocation(jti: Optional[str], user_id: Optional[str], payload: dict):
    """Check if a JWT has been revoked via jti or user-wide revocation. Raises 401 if revoked."""
    if jti:
        revoked = await db.jwt_revocations.find_one({"jti": jti})
        if revoked:
            raise HTTPException(status_code=401, detail="Token revoked")

    if not user_id:
        return

    user_revocation = await db.jwt_revocations.find_one({"user_id": user_id, "jti": "all"})
    if not user_revocation:
        return

    # Check if this token was issued BEFORE the revocation
    token_iat = payload.get("iat")
    if not token_iat:
        raise HTTPException(status_code=401, detail="Invalid token: missing issued-at claim")

    from datetime import datetime as dt
    if isinstance(token_iat, (int, float)):
        token_issued = dt.fromtimestamp(token_iat, tz=timezone.utc)
    else:
        token_issued = token_iat

    revocation_time = user_revocation.get("created_at")
    if revocation_time:
        if isinstance(revocation_time, str):
            revocation_time = dt.fromisoformat(revocation_time)
        if hasattr(revocation_time, 'tzinfo') and revocation_time.tzinfo is None:
            revocation_time = revocation_time.replace(tzinfo=timezone.utc)
        if token_issued < revocation_time:
            raise HTTPException(status_code=401, detail="Token revoked")


def _extract_token(request: Request) -> Optional[str]:
    """Extract JWT token from Authorization header or session cookie."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ")[1]
    return request.cookies.get("session_token")


async def _lookup_session_user(session_token: str) -> Optional[dict]:
    """Look up a user by session token, checking expiry. Returns user dict or None."""
    session = await db.user_sessions.find_one({"session_token": session_token}, {"_id": 0})
    if not session:
        return None

    expires_at = session.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")

    return await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})


async def get_current_user(request: Request) -> dict:
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Try JWT token first
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        await _check_jwt_revocation(payload.get("jti"), payload.get("user_id"), payload)
        user = await db.users.find_one({"user_id": payload["user_id"]}, {"_id": 0})
        if user:
            return user
    except jwt.ExpiredSignatureError:
        pass  # fall through to session cookie/DB lookup
    except jwt.InvalidTokenError:
        pass  # fall through to session cookie/DB lookup
    except HTTPException:
        raise  # revocation 401 must propagate

    # Try session token — use the cookie value, not the Bearer JWT string
    session_token = request.cookies.get("session_token") or token
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = await _lookup_session_user(session_token)
    if user:
        return user

    raise HTTPException(status_code=401, detail="Invalid token")


def _is_subscription_active(sub: dict) -> bool:
    """Check if a raw subscription doc represents an active (non-expired) subscription."""
    if sub["status"] == "active":
        return True
    if sub["status"] == "trialing":
        trial_end = _parse_iso_datetime(sub.get("trial_end_date"))
        if trial_end and trial_end >= datetime.now(timezone.utc):
            return True
    return False


async def should_show_watermark(user_id: str) -> bool:
    """Check if watermark should be shown on PDFs."""
    sub = await db.subscriptions.find_one({"user_id": user_id}, {"_id": 0})
    if not sub:
        return True

    if not _is_subscription_active(sub):
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
            "plan_type": "none",
            "status": "expired",
            "trial_start_date": None,
            "trial_end_date": None,
            "stripe_customer_id": None,
            "stripe_subscription_id": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "notes": "New signup — subscribe to activate"
        }
        await db.subscriptions.insert_one(sub)

    if _is_subscription_active(sub):
        return user

    if sub["status"] == "trialing":
        raise HTTPException(
            status_code=402,
            detail="Trial expired. Please subscribe to continue using TrustOffice."
        )

    raise HTTPException(
        status_code=402,
        detail="Subscription inactive. Please subscribe to continue using TrustOffice."
    )


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
    
    # Check trust profile completion
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user_id}, {"_id": 0})
    if trust:
        if trust.get("start_date"):
            updates["formation_date_added"] = True
        if trust.get("ein"):
            updates["ein_entered"] = True
    
    # Check document uploads in vault (fixed: was checking wrong category names)
    trust_doc_count = await db.vault_documents.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "category": {"$in": ["trust_instrument", "amendment"]}
    })
    if trust_doc_count > 0:
        updates["trust_doc_uploaded"] = True
    
    # Check if trust document has been analyzed by AI
    analysis_count = await db.trust_document_analysis.count_documents({
        "trust_id": trust_id, "status": "complete"
    })
    if analysis_count > 0:
        updates["trust_doc_analyzed"] = True
    
    ein_doc_count = await db.vault_documents.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "category": {"$in": ["ein_letter", "irs_notice"]}
    })
    if ein_doc_count > 0:
        updates["ein_doc_uploaded"] = True
    
    # Check beneficiaries (stored in trust_unit_certificates, not db.beneficiaries)
    beneficiary_count = await db.trust_unit_certificates.count_documents({
        "trust_id": trust_id,
        "user_id": user_id,
        "status": "active"
    })
    if beneficiary_count > 0:
        updates["beneficiaries_added"] = True
    
    # Check assets (via entities)
    entity_count = await db.entities.count_documents({"trust_id": trust_id, "user_id": user_id})
    if entity_count > 0:
        updates["assets_added"] = True
    
    # Check governance tasks (calendar)
    task_count = await db.governance_tasks.count_documents({
        "trust_id": trust_id, 
        "user_id": user_id,
        "task_type": {"$ne": "custom"}
    })
    # Also check that tax deadlines have been generated
    tax_count = await db.tax_calendar.count_documents({
        "trust_id": trust_id
    })
    if task_count > 0 and tax_count > 0:
        updates["calendar_set"] = True
    
    # Check minutes (both records from unified flow and templates from template form)
    minutes_count = await db.minutes_records.count_documents({"trust_id": trust_id, "user_id": user_id})
    templates_count = await db.minutes_templates.count_documents({"trust_id": trust_id, "user_id": user_id})
    if minutes_count > 0 or templates_count > 0:
        updates["minutes_generated"] = True
    
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
        },
        {
            "task_id": f"task_{uuid.uuid4().hex[:12]}",
            "trust_id": trust_id,
            "user_id": user_id,
            "task_type": "asset_revaluation",
            "due_date": (now + timedelta(days=365)).isoformat(),
            "completed_at": None,
            "description": "Annual re-valuation of all Schedule A assets",
            "created_at": now.isoformat()
        }
    ]
    
    await db.governance_tasks.insert_many(default_tasks)



# calculate_health_score has been moved to routers/governance.py
# This wrapper preserves backwards compatibility for callers importing from dependencies.
# We use a lazy import to avoid a circular dependency (governance.py imports from dependencies).
async def calculate_health_score(trust_id: str, user_id: str, save_snapshot: bool = True) -> dict:
    from routers.governance import calculate_health_score as _calc
    return await _calc(trust_id, user_id, save_snapshot=save_snapshot)
