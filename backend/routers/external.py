"""
External Partner Provisioning API — WingPoint → TrustOffice Integration

Authentication: API Key via Authorization: Bearer <key> header
Rate Limit: 100 requests/hour per partner key
Audit: All actions logged to external_api_audit collection
Idempotency: By email (account level) + Idempotency-Key header (trust level)

Endpoints:
- POST /external/provision-trustoffice        — Provision user + trust from WingPoint
- POST /external/provision-trustoffice/dry-run — Preview without persisting
- POST /external/provision-trustoffice/resend   — Resend welcome email (fresh token)
- GET  /external/provision-trustoffice/status   — Check provisioning status by wingpoint_ref
- GET  /external/lookup-user                   — Check if a TrustOffice user exists for an email

See: WINGPOINT-TRUSTOFFICE-INTEGRATION-PROPOSAL-v3.md
"""

from fastapi import APIRouter, HTTPException, Depends, Request, Header
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, EmailStr, Field, field_validator
from datetime import datetime, timezone, timedelta
from typing import Optional, Literal
import os
import secrets
import uuid
import hashlib
import hmac
import json
import asyncio
import logging
from urllib.parse import quote
import re

from database import db
from email_service import email_service
from dependencies import get_subscription_state, get_trust_limit, PLAN_TRUST_LIMITS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/external", tags=["external"])

# ==================== AUTHENTICATION ====================

EXTERNAL_API_KEY = os.environ.get("EXTERNAL_API_KEY", "")
WINGPOINT_WEBHOOK_URL = os.environ.get("WINGPOINT_WEBHOOK_URL", "")
WINGPOINT_WEBHOOK_SECRET = os.environ.get("WINGPOINT_WEBHOOK_SECRET", "")

api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


async def verify_external_api_key(request: Request, authorization: str = Header(None)) -> dict:
    """
    Verify the partner API key from Authorization: Bearer <key> header.
    Returns partner info dict on success.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header. Use: Bearer <api_key>"
        )

    key = authorization.split("Bearer ", 1)[1].strip()

    # Check against configured external API keys
    # Accept both the main EXTERNAL_API_KEY and the dedicated TRUSTOFFICE_EXTERNAL_API_KEY
    # In production, these come from the partner_api_keys collection
    valid_keys = [k for k in [EXTERNAL_API_KEY, os.environ.get("TRUSTOFFICE_EXTERNAL_API_KEY", "")] if k]
    for valid_key in valid_keys:
        if hmac.compare_digest(key, valid_key):
            return {
                "partner_id": "wingpoint",
                "partner_name": "WingPoint",
                "key_id": "env_default"
            }

    # Check MongoDB for partner keys
    partner = await db.partner_api_keys.find_one({
        "api_key": key,
        "active": True
    })

    if not partner:
        raise HTTPException(
            status_code=401,
            detail="Invalid or inactive API key"
        )

    return {
        "partner_id": partner["partner_id"],
        "partner_name": partner.get("partner_name", partner["partner_id"]),
        "key_id": partner.get("key_id", "unknown")
    }


# ==================== WINGPOINT TRUST TYPE MAPPING ====================

# WingPoint sends trust_type as: FAMILY_TRUST, BUSINESS_TRUST, PROPERTY_TRUST,
# MINISTRY_TRUST, GENERAL_TRUST
# TrustOffice stores trust_type as: family, charitable, business, ecclesiastical, institutional
WINGPOINT_TRUST_TYPE_MAP = {
    "FAMILY_TRUST": "family",
    "BUSINESS_TRUST": "business",
    "PROPERTY_TRUST": "family",       # Property trusts are typically family trusts in TO
    "MINISTRY_TRUST": "ecclesiastical",
    "GENERAL_TRUST": "institutional",
}

# WingPoint entity_type is always "irrevocable_trust" — we store this for reference
# but TrustOffice's TrustType enum handles the categorization.

# ==================== RATE LIMITING ====================

async def check_rate_limit(partner_id: str):
    """Simple rate limit: 100 requests/hour per partner."""
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    count = await db.external_api_audit.count_documents({
        "partner_id": partner_id,
        "timestamp": {"$gt": one_hour_ago}
    })
    if count >= 100:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Maximum 100 requests per hour.",
            headers={"Retry-After": "3600"}
        )


async def log_audit(partner_id: str, action: str, wingpoint_ref: str, details: dict = None, status: str = "success"):
    """Log all external API actions for audit trail."""
    await db.external_api_audit.insert_one({
        "audit_id": f"ext_{uuid.uuid4().hex[:12]}",
        "partner_id": partner_id,
        "action": action,
        "wingpoint_ref": wingpoint_ref,
        "details": details or {},
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })


# ==================== SMART ROUTING HELPERS ====================

# Map WingPoint packages to recommended TrustOffice tiers
PACKAGE_TO_PLAN = {
    "single_trust": "trustee",      # 1 trust → Trustee ($79/mo, 1 trust)
    "estate_bundle": "estate",      # 2 trusts → Estate ($149/mo, 8 trusts)
    "builder_bundle": "estate",     # 4 trusts → Estate ($149/mo, 8 trusts covers it)
    "wingpoint_annual": "wingpoint", # WingPoint exclusive annual plan
}

# Human-readable plan names for API response
PLAN_DISPLAY_NAMES = {
    "free": "Free",
    "forever_free": "Forever Free",
    "trustee": "Trustee",
    "estate": "Estate",
    "advisor": "Advisor",
    "wingpoint": "WingPoint Annual",
    "monthly": "Legacy Monthly",
    "annual": "Legacy Annual",
    "trial": "Trial",
}


async def _determine_recommended_action(
    user_id: str,
    is_new_user: bool,
    source_package: Optional[str],
    coupon_code: Optional[str],
    frontend_url: str,
) -> dict:
    """
    Determine the recommended action for a provisioned user based on their
    current subscription state, trust count, and whether they already have a password.

    Returns a structured object with:
    - action: set_password | login | login_and_subscribe | login_and_upgrade
    - redirect_url: where WingPoint should send the user
    - message: human-readable explanation
    - suggested_plan: recommended TrustOffice tier
    - needs_upgrade: bool
    - requires_payment: bool
    """
    # Count trusts for this user
    trust_count = await db.trusts.count_documents({"user_id": user_id})

    # Get subscription state
    sub_state = await get_subscription_state(user_id)
    plan_type = sub_state.plan_type
    is_active = sub_state.is_active
    cancel_pending = sub_state.cancel_at_period_end

    # Check if user has a password (existing users who set one already)
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 1})
    has_password = bool(user is not None and user.get("password_hash") is not None)

    # Determine recommended plan based on package or trust count
    suggested_plan = PACKAGE_TO_PLAN.get(source_package, None)
    if not suggested_plan:
        # Fallback: recommend based on trust count
        if trust_count <= 1:
            suggested_plan = "trustee"
        elif trust_count <= 5:
            suggested_plan = "estate"
        else:
            suggested_plan = "advisor"
    else:
        # Validate package-based plan against actual trust count
        # (e.g., user bought multiple Single Trust packages → Trustee won't cover them)
        plan_limit = PLAN_TRUST_LIMITS.get(suggested_plan, 1)
        if plan_limit != float('inf') and trust_count > plan_limit:
            if trust_count <= 5:
                suggested_plan = "estate"
            else:
                suggested_plan = "advisor"

    # Prevent recommending a downgrade for legacy plan users (legacy limit = 10)
    current_limit = get_trust_limit(plan_type, sub_state.legacy_trust_limit)
    suggested_limit = PLAN_TRUST_LIMITS.get(suggested_plan, 1)
    if current_limit != float('inf') and suggested_limit != float('inf') and suggested_limit < current_limit:
        # Don't recommend a plan with fewer trusts than they already have
        if current_limit >= 10:
            suggested_plan = "advisor"  # Only Advisor exceeds legacy 10
        elif trust_count <= 5:
            suggested_plan = "estate"
        else:
            suggested_plan = "advisor"

    needs_upgrade = trust_count > current_limit if current_limit != float('inf') else False

    # Check for past_due status BEFORE is_free_or_trial (past_due has is_active=False but
    # the user needs to update payment, not re-subscribe from scratch)
    sub_status = getattr(sub_state, 'status', None)
    is_past_due = sub_status == 'past_due'

    # Determine if user needs to pay (free/trial/canceled → yes; active paid → no unless upgrade needed)
    is_free_or_trial = plan_type in ("free", "forever_free", "trial") or not is_active
    requires_payment = (is_free_or_trial and not is_past_due) or needs_upgrade or is_past_due

    # Build redirect URL and action
    if is_new_user or not has_password:
        # New user or existing user without password → set password first
        action = "set_password"
        # Set-password URL is built by the caller; we just flag the action
        redirect_url = None  # Caller provides set_password_url
    elif is_past_due:
        # Payment failed but access still active (grace period) → update payment method
        action = "login_and_update_payment"
        redirect_url = f"{frontend_url}/login?wp=1&action=update_payment"
    elif is_free_or_trial:
        # Existing user with password, on free/trial → login then subscribe
        action = "login_and_subscribe"
        params = "?wp=1&action=subscribe"
        if coupon_code:
            params += f"&coupon={quote(coupon_code, safe='')}"
        if suggested_plan:
            params += f"&plan={suggested_plan}"
        redirect_url = f"{frontend_url}/login{params}"
    elif needs_upgrade:
        # Existing paid user whose plan can't handle the trust count → upgrade
        action = "login_and_upgrade"
        redirect_url = f"{frontend_url}/login?wp=1&action=upgrade&plan={suggested_plan}"
    elif cancel_pending:
        # Active subscription but cancellation pending → resubscribe
        action = "login_and_resubscribe"
        redirect_url = f"{frontend_url}/login?wp=1&action=resubscribe"
    else:
        # Existing paid user, plan covers trusts → just log in
        action = "login"
        redirect_url = f"{frontend_url}/login?wp=1&action=welcome"

    # Build human-readable message
    if action == "set_password":
        message = "Check your email to set your password and activate your account."
    elif action == "login_and_subscribe":
        message = f"Your trust has been added. Log in to choose your TrustOffice plan ({PLAN_DISPLAY_NAMES.get(suggested_plan, suggested_plan)})."
    elif action == "login_and_upgrade":
        message = f"Your trust has been added. Log in to upgrade to the {PLAN_DISPLAY_NAMES.get(suggested_plan, suggested_plan)} plan to manage all your trusts."
    elif action == "login_and_resubscribe":
        message = "Your trust has been added. Log in to reactivate your subscription."
    elif action == "login_and_update_payment":
        message = "Your trust has been added. Log in to update your payment method."
    else:
        message = "Your trust has been added to your account. Log in to get started."

    # Return only what WingPoint needs for routing — no internal user state
    return {
        "action": action,
        "redirect_url": redirect_url,
        "message": message,
        "suggested_plan": suggested_plan,
        "suggested_plan_name": PLAN_DISPLAY_NAMES.get(suggested_plan, suggested_plan),
        "needs_upgrade": needs_upgrade,
        "requires_payment": requires_payment,
    }


# ==================== WINGPOINT-AWARE SET-PASSWORD EMAIL ====================

_WINGPOINT_SET_PASSWORD_SUBJECT = "Your WingPoint trust is ready. Let's set up your access"

_WINGPOINT_SET_PASSWORD_TEXT = """Hi {first_name},

You recently purchased a trust package through WingPoint.

TrustOffice is the platform that manages your trust.
WingPoint built your trust.
TrustOffice keeps it running, updated, secure, and accessible whenever you need it.

Here is what happens next:

1. Set your password (30 seconds).
2. Choose your management plan (covers amendments, beneficiary updates, document storage). WingPoint has covered $50 of your first month.
3. Access your trust on your dashboard.

If you have questions, just reply to this email.

Activate your account: {set_password_url}

Welcome aboard,
The TrustOffice Team
In partnership with WingPoint
"""

_WINGPOINT_SET_PASSWORD_HTML_BODY = """
<h2>Hi {first_name},</h2>
<p>You recently purchased a trust package through WingPoint.</p>

<p>TrustOffice is the platform that manages your trust.<br>
WingPoint built your trust.<br>
TrustOffice keeps it running, updated, secure, and accessible whenever you need it.</p>

<h3>Here is what happens next:</h3>
<ol>
  <li><strong>Set your password</strong> (30 seconds).</li>
  <li><strong>Choose your management plan</strong> (covers amendments, beneficiary updates, document storage). WingPoint has covered $50 of your first month.</li>
  <li><strong>Access your trust</strong> on your dashboard.</li>
</ol>

<p>If you have questions, just reply to this email.</p>

<p style="text-align: center; margin: 30px 0;">
  <a href="{set_password_url}" class="button">Activate My Trust Account</a>
</p>

<p style="font-size: 12px; color: #666;">
  If the button doesn't work, copy and paste this link into your browser:<br>
  <span style="word-break: break-all;">{set_password_url}</span>
</p>

<p>Welcome aboard,<br>
The TrustOffice Team<br>
In partnership with WingPoint</p>
"""


def _wingpoint_set_password_html(first_name: str, set_password_url: str) -> str:
    """Build the WingPoint-aware set-password HTML using the base template wrapper."""
    from email_templates import _base_template
    inner = _WINGPOINT_SET_PASSWORD_HTML_BODY.format(
        first_name=first_name,
        set_password_url=set_password_url,
    )
    return _base_template(inner)


def _wingpoint_set_password_text(first_name: str, set_password_url: str) -> str:
    """Build the WingPoint-aware set-password plain-text body."""
    return _WINGPOINT_SET_PASSWORD_TEXT.format(
        first_name=first_name,
        set_password_url=set_password_url,
    )


def _resolve_first_name(
    grantor_first_name: Optional[str] = None,
    grantor_full_name: Optional[str] = None,
    fallback: str = "there",
) -> str:
    """Extract a first name from the provision record or grantor fields."""
    if grantor_first_name and grantor_first_name.strip():
        return grantor_first_name.strip()
    if grantor_full_name and grantor_full_name.strip():
        # Full name is present; take the first token as first name
        return grantor_full_name.strip().split()[0]
    return fallback


async def _send_wingpoint_set_password_email(
    to_email: str,
    first_name: str,
    set_password_url: str,
) -> dict:
    """
    Send the WingPoint-aware warm set-password email.

    All provisions through this external router originate from WingPoint
    (every request carries a wingpoint_ref), so we always send the warm
    WingPoint-branded copy.  The generic send_welcome_set_password_email
    is still used by the admin-created-account path (routers/admin.py)
    which is NOT a WingPoint provision.
    """
    subject = _WINGPOINT_SET_PASSWORD_SUBJECT
    html_body = _wingpoint_set_password_html(first_name, set_password_url)
    text_body = _wingpoint_set_password_text(first_name, set_password_url)
    return await email_service.send_email(
        to_email=to_email,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        to_name=first_name if first_name != "there" else "",
        tag="wingpoint_set_password",
        metadata={"email_type": "wingpoint_set_password"},
    )


# ==================== MODELS ====================

class WingPointProvisionRequest(BaseModel):
    """Full provisioning request from WingPoint."""
    # User/account info
    email: EmailStr
    phone: Optional[str] = None
    grantor_first_name: Optional[str] = None
    grantor_middle_name: Optional[str] = None
    grantor_last_name: Optional[str] = None
    grantor_suffix: Optional[str] = None
    grantor_full_name: Optional[str] = None
    role_for_trust: Literal["grantor", "trustee"] = "trustee"

    # Trust info
    trust_name: str
    entity_type: Literal["irrevocable_trust"] = "irrevocable_trust"
    trust_type: Literal[
        "FAMILY_TRUST", "BUSINESS_TRUST", "PROPERTY_TRUST",
        "MINISTRY_TRUST", "GENERAL_TRUST"
    ] = "FAMILY_TRUST"
    jurisdiction: str = Field(..., max_length=2, description="2-letter US state code")
    ein: Optional[str] = None
    trust_formation_date: Optional[str] = None  # ISO date, can be null

    # Trustee info
    trustee_first_name: Optional[str] = None
    trustee_middle_name: Optional[str] = None
    trustee_last_name: Optional[str] = None
    trustee_suffix: Optional[str] = None
    trustee_full_name: Optional[str] = None
    use_wingpoint_trustee: bool = False

    # Address
    mailing_address_line1: Optional[str] = None
    mailing_address_line2: Optional[str] = None
    mailing_city: Optional[str] = None
    mailing_state: Optional[str] = None
    mailing_zip: Optional[str] = None
    mailing_county: Optional[str] = None

    # Bank + docs
    bank_name: Optional[str] = None
    has_irs_confirmation: Optional[bool] = None
    has_declaration: Optional[bool] = None
    has_certification: Optional[bool] = None
    has_binder_kit: Optional[bool] = None

    # Metadata
    wingpoint_ref: str = Field(..., description="Unique WingPoint reference (used as idempotency key)")
    source_package: Optional[Literal["single_trust", "estate_bundle", "builder_bundle"]] = None
    coupon_code: Optional[str] = Field(None, pattern=r'^[A-Za-z0-9_-]+$', max_length=50)

    # Control flags
    dry_run: bool = False
    resend: bool = False
    # When WingPoint passes the user's actual TrustOffice user_id (connect flow),
    # link the trust to that account instead of matching by email alone.
    existing_trustoffice_user_id: Optional[str] = None

    @field_validator("jurisdiction")
    @classmethod
    def validate_jurisdiction(cls, v):
        """Ensure 2-letter uppercase state code."""
        v = v.strip().upper()
        if not re.match(r"^[A-Z]{2}$", v):
            raise ValueError("jurisdiction must be a 2-letter US state code")
        return v

    @field_validator("ein")
    @classmethod
    def validate_ein(cls, v):
        """Normalize EIN to XX-XXXXXXX format."""
        if v is None:
            return v
        cleaned = re.sub(r"[^0-9]", "", v)
        if len(cleaned) != 9:
            raise ValueError("EIN must be 9 digits")
        return f"{cleaned[:2]}-{cleaned[2:]}"


class LinkTrustRequest(BaseModel):
    """Link a trust to an existing TrustOffice user — no email lookup, no user creation.
    
    Used by the WingPoint connect callback after the user has authenticated on
    TrustOffice. The trustoffice_user_id is guaranteed by the connect token JWT.
    """
    trustoffice_user_id: str = Field(..., description="The user's actual TrustOffice user_id (from connect token)")
    wingpoint_ref: str = Field(..., description="Unique WingPoint reference")
    trust_name: str
    trust_type: Literal[
        "FAMILY_TRUST", "BUSINESS_TRUST", "PROPERTY_TRUST",
        "MINISTRY_TRUST", "GENERAL_TRUST"
    ] = "FAMILY_TRUST"
    jurisdiction: str = Field(..., max_length=2, description="2-letter US state code")
    ein: Optional[str] = None
    trust_formation_date: Optional[str] = None
    entity_type: Literal["irrevocable_trust"] = "irrevocable_trust"
    role_for_trust: Literal["grantor", "trustee"] = "trustee"
    
    # Trustee
    trustee_first_name: Optional[str] = None
    trustee_middle_name: Optional[str] = None
    trustee_last_name: Optional[str] = None
    trustee_suffix: Optional[str] = None
    trustee_full_name: Optional[str] = None
    use_wingpoint_trustee: bool = False
    
    # Address
    mailing_address_line1: Optional[str] = None
    mailing_address_line2: Optional[str] = None
    mailing_city: Optional[str] = None
    mailing_state: Optional[str] = None
    mailing_zip: Optional[str] = None
    mailing_county: Optional[str] = None
    
    # Bank + docs
    bank_name: Optional[str] = None
    has_irs_confirmation: Optional[bool] = None
    has_declaration: Optional[bool] = None
    has_certification: Optional[bool] = None
    has_binder_kit: Optional[bool] = None
    
    # Metadata
    source_package: Optional[Literal["single_trust", "estate_bundle", "builder_bundle"]] = None
    coupon_code: Optional[str] = Field(None, pattern=r'^[A-Za-z0-9_-]+$', max_length=50)
    
    @field_validator("jurisdiction")
    @classmethod
    def validate_jurisdiction(cls, v):
        v = v.strip().upper()
        if not re.match(r"^[A-Z]{2}$", v):
            raise ValueError("jurisdiction must be a 2-letter US state code")
        return v
    
    @field_validator("ein")
    @classmethod
    def validate_ein(cls, v):
        if v is None:
            return v
        cleaned = re.sub(r"[^0-9]", "", v)
        if len(cleaned) != 9:
            raise ValueError("EIN must be 9 digits")
        return f"{cleaned[:2]}-{cleaned[2:]}"


class ResendActivationRequest(BaseModel):
    """Resend welcome email for an existing provisioning."""
    wingpoint_ref: str
    email: EmailStr


class ProvisionStatusRequest(BaseModel):
    """Check provisioning status."""
    wingpoint_ref: str


# ==================== PROVISION HELPERS ====================

def _safe_recommended_action(frontend_url: str) -> dict:
    """Fallback recommended_action when _determine_recommended_action fails."""
    return {
        "action": "login",
        "redirect_url": f"{frontend_url}/login",
        "message": "Your trust has been added to your account. Log in to get started.",
        "suggested_plan": None,
        "suggested_plan_name": None,
        "needs_upgrade": False,
        "requires_payment": False,
    }


async def _handle_idempotent_replay(existing_provision: dict) -> dict:
    """Return an existing provision enriched with a fresh recommended_action."""
    _replay_frontend_url = os.environ.get('FRONTEND_URL', 'https://app.trustoffice.app')
    try:
        replay_recommended = await _determine_recommended_action(
            user_id=existing_provision.get("user_id", ""),
            is_new_user=False,
            source_package=existing_provision.get("request_payload", {}).get("source_package"),
            coupon_code=existing_provision.get("request_payload", {}).get("coupon_code"),
            frontend_url=_replay_frontend_url,
        )
    except Exception as e:
        logger.warning(f"Idempotent replay: _determine_recommended_action failed: {e}")
        replay_recommended = _safe_recommended_action(_replay_frontend_url)
    existing_provision["status"] = "already_exists"
    existing_provision["recommended_action"] = replay_recommended
    return existing_provision


async def _handle_dry_run(request: WingPointProvisionRequest) -> dict:
    """Build a dry-run preview response without persisting anything."""
    dry_run_response = {
        "status": "dry_run",
        "would_create_user": True,
        "would_create_trust": True,
        "user_id": f"dry_run_user_{uuid.uuid4().hex[:8]}",
        "trust_id": f"dry_run_trust_{uuid.uuid4().hex[:8]}",
        "set_password_url": f"{os.environ.get('FRONTEND_URL', 'https://app.trustoffice.app')}/reset-password?token=dry_run",
        "set_password_expires": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "email": request.email,
        "trust_name": request.trust_name,
        "trust_type_mapped": WINGPOINT_TRUST_TYPE_MAP.get(request.trust_type, "family"),
        "would_send_welcome_email": True,
        "would_apply_coupon": request.coupon_code or None,
        "message": "Dry run — no data was persisted or email sent."
    }

    existing_user = await db.users.find_one({"email": request.email.lower().strip()}, {"_id": 0})
    if existing_user:
        dry_run_response["would_create_user"] = False
        dry_run_response["existing_user_id"] = existing_user["user_id"]
        dry_run_response["message"] = "Dry run — user already exists. Trust would be added to existing account."

        existing_trust = await db.trusts.find_one({
            "user_id": existing_user["user_id"],
            "name": request.trust_name
        }, {"_id": 0})
        if existing_trust:
            dry_run_response["would_create_trust"] = False
            dry_run_response["existing_trust_id"] = existing_trust.get("trust_id")

    return dry_run_response


def _derive_display_name(request: WingPointProvisionRequest) -> str:
    """Derive a grantor display name from the request fields."""
    display_name = request.grantor_full_name
    if not display_name:
        parts = [request.grantor_first_name, request.grantor_middle_name,
                 request.grantor_last_name, request.grantor_suffix]
        display_name = " ".join(p for p in parts if p)
    return display_name


def _derive_trustee_str(request: WingPointProvisionRequest) -> str:
    """Derive the trustee string for TrustOffice's existing `trustees` field."""
    trustee_str = request.trustee_full_name
    if not trustee_str:
        parts = [request.trustee_first_name, request.trustee_middle_name,
                 request.trustee_last_name, request.trustee_suffix]
        trustee_str = " ".join(p for p in parts if p)
    return trustee_str


async def _find_existing_user(request: WingPointProvisionRequest) -> dict | None:
    """Find an existing user by explicit user_id or by email.

    existing_trustoffice_user_id takes PRIORITY over email — the connect flow
    passes the user's actual TrustOffice user_id after they authenticate.
    """
    if request.existing_trustoffice_user_id:
        existing_user = await db.users.find_one({"user_id": request.existing_trustoffice_user_id}, {"_id": 0})
        if existing_user:
            return existing_user
    return await db.users.find_one({"email": request.email.lower().strip()}, {"_id": 0})


async def _create_new_user(
    request: WingPointProvisionRequest, user_id: str, email: str,
    display_name: str, now: datetime,
) -> None:
    """Insert a new user document plus subscription + onboarding records."""
    user_doc = {
        "user_id": user_id,
        "email": email,
        "name": display_name or email.split("@")[0],
        "phone": request.phone,
        "is_admin": False,
        "created_at": now.isoformat(),
        "created_via": "wingpoint_provision",
        "source": "wingpoint",
        "wp_ref": request.wingpoint_ref,
        "grantor_first_name": request.grantor_first_name,
        "grantor_middle_name": request.grantor_middle_name,
        "grantor_last_name": request.grantor_last_name,
        "grantor_suffix": request.grantor_suffix,
        "grantor_full_name": request.grantor_full_name,
        "role_for_trust": request.role_for_trust,
        "use_wingpoint_trustee": request.use_wingpoint_trustee,
    }
    await db.users.insert_one(user_doc)

    # Create subscription for new user (none plan — must subscribe for access)
    await db.subscriptions.insert_one({
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
        "notes": "WingPoint provisioned — user must subscribe for access",
        "coupon_code": request.coupon_code,
        "source": "wingpoint",
        "wingpoint_ref": request.wingpoint_ref,
    })

    # Initialize onboarding checklist
    onboarding_doc = {
        "user_id": user_id,
        "formation_date_added": request.trust_formation_date is not None,
        "ein_entered": request.ein is not None,
        "trust_doc_uploaded": False,
        "ein_doc_uploaded": request.has_irs_confirmation is True,
        "beneficiaries_added": False,
        "assets_added": False,
        "minutes_generated": False,
        "calendar_set": False,
        "checklist_dismissed": False,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat()
    }
    await db.user_onboarding.insert_one(onboarding_doc)


async def _resolve_user_id(
    request: WingPointProvisionRequest, email: str, now: datetime,
) -> tuple[str, bool, dict | None]:
    """Find or create a user, returning (user_id, is_new_user, existing_user).

    existing_trustoffice_user_id takes PRIORITY over email.
    """
    existing_user = await _find_existing_user(request)

    if existing_user:
        user_id = existing_user["user_id"]
        logger.info(f"Provision: Adding trust to existing user {user_id} ({email})")
        if not existing_user.get("wp_ref") and request.wingpoint_ref:
            await db.users.update_one(
                {"user_id": user_id},
                {"$set": {"wp_ref": request.wingpoint_ref}},
            )
        return user_id, False, existing_user

    user_id = f"user_{uuid.uuid4().hex[:12]}"
    try:
        await _create_new_user(request, user_id, email, None, now)
        logger.info(f"Provision: Created new user {user_id} ({email}) via WingPoint")
        return user_id, True, None
    except Exception as e:
        if "duplicate key" in str(e).lower() or "E11000" in str(e):
            existing_user = await db.users.find_one({"email": email}, {"_id": 0})
            if existing_user:
                logger.info(f"Provision: Race condition resolved — user {existing_user['user_id']} ({email}) already exists")
                return existing_user["user_id"], False, existing_user
            raise HTTPException(status_code=500, detail="Failed to create user due to concurrent request. Please retry.")
        raise


def _build_trust_doc(
    request: WingPointProvisionRequest, user_id: str, to_trust_type: str,
    trustee_str: str, trust_id: str, now: datetime,
) -> dict:
    """Build the trust document to insert."""
    return {
        "trust_id": trust_id,
        "user_id": user_id,
        "wingpoint_ref": request.wingpoint_ref,
        "name": request.trust_name,
        "trust_type": to_trust_type,
        "entity_type": request.entity_type,
        "jurisdiction": request.jurisdiction,
        "role": request.role_for_trust,
        "start_date": request.trust_formation_date,
        "trustees": trustee_str,
        "ein": request.ein,
        "state_code": request.jurisdiction,
        "source": "wingpoint",
        "use_wingpoint_trustee": request.use_wingpoint_trustee,
        "trustee_first_name": request.trustee_first_name,
        "trustee_middle_name": request.trustee_middle_name,
        "trustee_last_name": request.trustee_last_name,
        "trustee_suffix": request.trustee_suffix,
        "trustee_full_name": request.trustee_full_name,
        "mailing_address_line1": request.mailing_address_line1,
        "mailing_address_line2": request.mailing_address_line2,
        "mailing_city": request.mailing_city,
        "mailing_state": request.mailing_state,
        "mailing_zip": request.mailing_zip,
        "mailing_county": request.mailing_county,
        "bank_name": request.bank_name,
        "has_irs_confirmation": request.has_irs_confirmation,
        "has_declaration": request.has_declaration,
        "has_certification": request.has_certification,
        "has_binder_kit": request.has_binder_kit,
        "source_package": request.source_package,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat()
    }


async def _create_trust(
    request: WingPointProvisionRequest, trust_doc: dict, trust_id: str,
    user_id: str, now: datetime,
) -> str:
    """Insert a trust or reuse an existing one for the same wingpoint_ref.

    If a trust already exists for the wingpoint_ref but is linked to a
    different user, re-link it to the correct user.
    """
    _existing_trust = await db.trusts.find_one(
        {"wingpoint_ref": request.wingpoint_ref},
        {"trust_id": 1, "user_id": 1, "_id": 0}
    )
    if _existing_trust:
        existing_trust_id = _existing_trust["trust_id"]
        if _existing_trust.get("user_id") != user_id:
            await db.trusts.update_one(
                {"trust_id": existing_trust_id},
                {"$set": {"user_id": user_id, "updated_at": now.isoformat()}},
            )
            logger.info(f"Provision: Re-linked trust {existing_trust_id} from user {_existing_trust.get('user_id')} to {user_id}")
        else:
            logger.info(f"Provision: Duplicate trust for wingpoint_ref={request.wingpoint_ref}, using existing trust {existing_trust_id}")
        return existing_trust_id

    await db.trusts.insert_one(trust_doc)
    logger.info(f"Provision: Created trust {trust_id} ('{request.trust_name}') for user {user_id}")
    return trust_id


async def _generate_set_password_token(user_id: str, now: datetime) -> tuple[str, datetime]:
    """Generate and persist a set-password token (7-day expiry)."""
    set_password_token = secrets.token_urlsafe(32)
    expires_at = now + timedelta(days=7)
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
    return set_password_token, expires_at


def _build_set_password_url(
    request: WingPointProvisionRequest, frontend_url: str,
    set_password_token: str,
) -> str:
    """Build the WingPoint set-password URL with coupon + plan params."""
    coupon_param = f"&coupon={quote(request.coupon_code, safe='')}" if request.coupon_code else ""
    _prelim_plan = PACKAGE_TO_PLAN.get(request.source_package or "", "trustee")
    action_plan_param = f"&plan={_prelim_plan}"
    return f"{frontend_url}/wingpoint?action=set_password&token={set_password_token}{coupon_param}{action_plan_param}"


async def _build_provision_record(
    request: WingPointProvisionRequest, idem_key: str, partner_id: str,
    user_id: str, trust_id: str, email: str, is_new_user: bool,
    set_password_url: str, expires_at: datetime,
) -> dict:
    """Build the external_provisions record dict."""
    return {
        "provision_id": f"prov_{uuid.uuid4().hex[:12]}",
        "idem_key": idem_key,
        "wingpoint_ref": request.wingpoint_ref,
        "partner_id": partner_id,
        "user_id": user_id,
        "trust_id": trust_id,
        "email": email,
        "trust_name": request.trust_name,
        "is_new_user": is_new_user,
        "set_password_url": set_password_url,
        "set_password_expires": expires_at.isoformat(),
        "email_status": "pending",
        "status": "pending",
        "coupon_code": request.coupon_code,
        "source_package": request.source_package,
        "use_wingpoint_trustee": request.use_wingpoint_trustee,
        "request_payload": request.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }


async def _insert_provision_record(
    provision_record: dict, idem_key: str, request: WingPointProvisionRequest,
) -> dict | None:
    """Insert a provision record, handling duplicate-key race conditions.

    Returns None on success (caller continues) or a dict to return immediately
    when a race condition resolves to an existing complete/in-progress provision.
    """
    try:
        await db.external_provisions.insert_one(provision_record)
        return None
    except Exception as e:
        if "duplicate key" not in str(e).lower() and "E11000" not in str(e):
            raise
        existing = await db.external_provisions.find_one({"idem_key": idem_key}, {"_id": 0})
        if not existing:
            raise
        logger.info(f"Provision: Duplicate key on provision insert for wingpoint_ref={request.wingpoint_ref} idem_key={idem_key} (race resolved, existing status={existing.get('status')})")
        if existing.get("status") == "complete":
            _race_frontend_url = os.environ.get('FRONTEND_URL', 'https://app.trustoffice.app')
            try:
                race_recommended = await _determine_recommended_action(
                    user_id=existing.get("user_id", ""),
                    is_new_user=False,
                    source_package=existing.get("request_payload", {}).get("source_package"),
                    coupon_code=existing.get("request_payload", {}).get("coupon_code"),
                    frontend_url=_race_frontend_url,
                )
            except Exception:
                race_recommended = _safe_recommended_action(_race_frontend_url)
            return {
                "status": "already_exists",
                "provision": existing,
                "recommended_action": race_recommended,
                "message": "Trust already provisioned"
            }
        return {
            "status": "in_progress",
            "provision": existing,
            "message": "Trust provisioning already in progress"
        }


async def _send_provision_email(
    request: WingPointProvisionRequest, recommended: dict,
    email: str, display_name: str, set_password_url: str,
) -> tuple[dict, str]:
    """Send the appropriate provision email (set-password or skip).

    Returns (email_result, email_status).
    """
    if recommended["action"] == "set_password":
        first_name = _resolve_first_name(
            grantor_first_name=request.grantor_first_name,
            grantor_full_name=request.grantor_full_name,
        )
        try:
            email_result = await _send_wingpoint_set_password_email(
                to_email=email,
                first_name=first_name,
                set_password_url=set_password_url,
            )
            email_status = email_result.get("status", "unknown")
        except Exception as e:
            email_result = {"status": "failed", "error": str(e)}
            email_status = "failed"
            logger.error(f"Provision: Welcome email raised exception for {email}: {e}")
    else:
        email_result = {"status": "skipped", "reason": "existing_user_with_password"}
        email_status = "skipped"
        logger.info(f"Provision: Skipping set-password email for existing user {email} (already has password). Action: {recommended['action']}")
    return email_result, email_status


def _build_provision_response(
    is_new_user: bool, user_id: str, trust_id: str,
    set_password_url: str, expires_at: datetime, email: str,
    request: WingPointProvisionRequest, email_status: str,
    recommended: dict, display_name: str, email_result: dict,
) -> dict:
    """Build the final provision response with a context-appropriate message."""
    response = {
        "status": "created" if is_new_user else "trust_added",
        "user_id": user_id,
        "trust_id": trust_id,
        "set_password_url": set_password_url if recommended["action"] == "set_password" else None,
        "set_password_expires": expires_at.isoformat() if recommended["action"] == "set_password" else None,
        "is_new_user": is_new_user,
        "email": email,
        "trust_name": request.trust_name,
        "email_status": email_status,
        "recommended_action": recommended,
    }

    if email_status == "failed":
        response["message"] = f"Account created, but welcome email failed: {email_result.get('error', 'unknown error')}"
    elif recommended["action"] != "set_password":
        response["message"] = recommended["message"]
    elif email_status == "skipped":
        response["message"] = "Account created, but email service is not configured. Set-password link generated but not emailed."
    else:
        response["message"] = f"Account {'created' if is_new_user else 'updated'}. Welcome email sent to {email}."

    return response


# ==================== ENDPOINTS ====================

@router.post("/provision-trustoffice")
async def provision_trustoffice(
    request: WingPointProvisionRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    partner: dict = Depends(verify_external_api_key)
):
    """
    Provision a TrustOffice account + trust from WingPoint data.
    
    Idempotent:
    - Same email → adds trust to existing account
    - Same Idempotency-Key (wingpoint_ref) → returns existing trust, no side effects
    - Same Idempotency-Key with different payload → 409 Conflict
    
    Use dry_run=true to preview without persisting.
    Use resend=true with an existing wingpoint_ref to re-send the welcome email.
    """
    partner_id = partner["partner_id"]
    logger.info(f"Provision: START wingpoint_ref={request.wingpoint_ref} email={request.email} trust_name='{request.trust_name}' partner={partner_id}")

    # Rate limiting
    await check_rate_limit(partner_id)

    # Use wingpoint_ref as idempotency key if header not provided
    idem_key = idempotency_key or request.wingpoint_ref

    # ---- IDEMPOTENCY CHECK ----
    existing_provision = await db.external_provisions.find_one(
        {"idem_key": idem_key},
        {"_id": 0}
    )

    if existing_provision and not request.dry_run:
        if request.resend:
            return await _resend_activation(existing_provision, partner)

        # Conflict detection: different payload for same idempotency key
        existing_payload = existing_provision.get("request_payload", {})
        if existing_payload.get("trust_name") != request.trust_name or \
           existing_payload.get("email", "").lower() != request.email.lower():
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "Idempotency conflict: this wingpoint_ref was already used with different data.",
                    "message": "Use the existing provision or provide a different wingpoint_ref."
                }
            )

        return await _handle_idempotent_replay(existing_provision)

    # ---- DRY RUN ----
    if request.dry_run:
        return await _handle_dry_run(request)

    # ---- MAP WINGPOINT DATA TO TRUSTOFFICE ----
    to_trust_type = WINGPOINT_TRUST_TYPE_MAP.get(request.trust_type, "family")
    display_name = _derive_display_name(request)
    trustee_str = _derive_trustee_str(request)
    email = request.email.lower().strip()
    now = datetime.now(timezone.utc)

    # ---- FIND OR CREATE USER ----
    user_id, is_new_user, _existing = await _resolve_user_id(request, email, now)

    # ---- CREATE TRUST ----
    trust_id = f"trust_{uuid.uuid4().hex[:12]}"
    trust_doc = _build_trust_doc(request, user_id, to_trust_type, trustee_str, trust_id, now)
    trust_id = await _create_trust(request, trust_doc, trust_id, user_id, now)

    # ---- AUTO-CREATE ENTITY RECORD (matches in-app trust creation) ----
    # The in-app path calls _create_trust_entity which inserts into db.entities.
    # WingPoint provision must do the same so the trust appears in Structures.
    entity_id = f"entity_{uuid.uuid4().hex[:12]}"
    entity_doc = {
        "entity_id": entity_id,
        "user_id": user_id,
        "trust_id": trust_id,
        "name": request.trust_name,
        "entity_type": "Trust",
        "legal_name": request.trust_name,
        "formation_date": request.trust_formation_date,
        "governing_law": request.jurisdiction or "",
        "ein": request.ein,
        "trustee_names": trustee_str,
        "beneficiary_standard": "",
        "article_ref_distribution": "",
        "article_ref_compensation": "",
        "article_ref_amendment": "",
        "oversight_required": False,
        "member_names": "",
        "manager_names": "",
        "article_ref_authority": "",
        "article_ref_profit_distribution": "",
        "created_at": now.isoformat(),
    }
    # Avoid duplicate entity for same trust
    _existing_entity = await db.entities.find_one({"trust_id": trust_id}, {"_id": 1})
    if not _existing_entity:
        try:
            await db.entities.insert_one(entity_doc)
            logger.info(f"Provision: Created entity {entity_id} for trust {trust_id}")
        except Exception as e:
            logger.warning(f"Provision: Failed to create entity for trust {trust_id}: {e}")

    # ---- GENERATE SET-PASSWORD TOKEN (7-day expiry) ----
    set_password_token, expires_at = await _generate_set_password_token(user_id, now)

    frontend_url = os.environ.get('FRONTEND_URL', 'https://app.trustoffice.app')
    # Plan derived from source package; override if trust count exceeds plan limit
    _prelim_plan = PACKAGE_TO_PLAN.get(request.source_package or "", "trustee")
    _prelim_limit = PLAN_TRUST_LIMITS.get(_prelim_plan, 1)
    if _prelim_limit != float('inf'):
        _current_trust_count = await db.trusts.count_documents({"user_id": user_id})
        if _current_trust_count > _prelim_limit:
            _prelim_plan = "estate" if _current_trust_count <= 8 else "advisor"
    coupon_param = f"&coupon={quote(request.coupon_code, safe='')}" if request.coupon_code else ""
    action_plan_param = f"&plan={_prelim_plan}"
    set_password_url = f"{frontend_url}/wingpoint?action=set_password&token={set_password_token}{coupon_param}{action_plan_param}"

    # ---- INSERT PROVISION RECORD EARLY (pending status) ----
    provision_record = await _build_provision_record(
        request, idem_key, partner_id, user_id, trust_id, email,
        is_new_user, set_password_url, expires_at,
    )
    race_result = await _insert_provision_record(provision_record, idem_key, request)
    if race_result is not None:
        return race_result

    # ---- DETERMINE RECOMMENDED ACTION (smart routing) ----
    try:
        recommended = await _determine_recommended_action(
            user_id=user_id,
            is_new_user=is_new_user,
            source_package=request.source_package,
            coupon_code=request.coupon_code,
            frontend_url=frontend_url,
        )
    except Exception as e:
        logger.error(f"Provision: _determine_recommended_action failed for {email}: {e}", exc_info=True)
        recommended = {
            "action": "login",
            "redirect_url": f"{frontend_url}/login?wp=1&action=welcome",
            "message": "Your trust has been added to your account. Log in to get started.",
            "suggested_plan": None,
            "suggested_plan_name": None,
            "needs_upgrade": False,
            "requires_payment": False,
        }

    # ---- SEND EMAIL ----
    email_result, email_status = await _send_provision_email(
        request, recommended, email, display_name, set_password_url,
    )

    if email_status == "failed":
        logger.error(f"Provision: Welcome email failed for {email}: {email_result.get('error')}")
    elif email_status == "skipped":
        logger.warning(f"Provision: Email skipped for {email}: {email_result.get('reason', 'service not configured')}")

    # ---- UPDATE PROVISION RECORD TO COMPLETE ----
    await db.external_provisions.update_one(
        {"idem_key": idem_key},
        {"$set": {
            "status": "complete",
            "email_status": email_status,
            "completed_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    logger.info(f"Provision: COMPLETE wingpoint_ref={request.wingpoint_ref} user_id={user_id} trust_id={trust_id} is_new_user={is_new_user} email_status={email_status} action={recommended['action']}")

    # ---- AUDIT LOG ----
    await log_audit(
        partner_id=partner_id,
        action="provision_trustoffice",
        wingpoint_ref=request.wingpoint_ref,
        details={
            "user_id": user_id,
            "trust_id": trust_id,
            "is_new_user": is_new_user,
            "email": email,
            "trust_name": request.trust_name,
            "dry_run": False,
        },
        status="success"
    )

    # ---- BUILD RESPONSE ----
    return _build_provision_response(
        is_new_user, user_id, trust_id, set_password_url, expires_at,
        email, request, email_status, recommended, display_name, email_result,
    )


@router.post("/provision-trustoffice/resend")
async def resend_activation(
    request: ResendActivationRequest,
    partner: dict = Depends(verify_external_api_key)
):
    """Resend welcome email with a fresh set-password link (7-day expiry)."""
    partner_id = partner["partner_id"]
    await check_rate_limit(partner_id)

    provision = await db.external_provisions.find_one(
        {"wingpoint_ref": request.wingpoint_ref},
        {"_id": 0}
    )

    if not provision:
        raise HTTPException(status_code=404, detail="No provision found for this wingpoint_ref")

    if provision["email"].lower() != request.email.lower():
        raise HTTPException(status_code=400, detail="Email does not match the provisioned account")

    result = await _resend_activation(provision, partner)
    await log_audit(partner_id, "resend_activation", request.wingpoint_ref, {"status": "success"})
    return result


async def _resend_activation(provision: dict, partner: dict) -> dict:
    """Internal: generate fresh token and resend welcome email."""
    user_id = provision["user_id"]
    email = provision["email"]

    # Generate fresh set-password token (7-day expiry)
    now = datetime.now(timezone.utc)
    set_password_token = secrets.token_urlsafe(32)
    expires_at = now + timedelta(days=7)

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

    frontend_url = os.environ.get('FRONTEND_URL', 'https://app.trustoffice.app')
    # Preserve coupon code and plan from original provisioning in resend URL
    coupon_code = provision.get("coupon_code") if provision else None
    coupon_param = f"&coupon={quote(coupon_code, safe='')}" if coupon_code else ""
    _source_pkg = provision.get("request_payload", {}).get("source_package") if provision else None
    _resend_plan = PACKAGE_TO_PLAN.get(_source_pkg or "", "trustee")
    action_plan_param = f"&plan={_resend_plan}"
    set_password_url = f"{frontend_url}/wingpoint?action=set_password&token={set_password_token}{coupon_param}{action_plan_param}"
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})

    # Resolve first name for the WingPoint-aware email.
    # Pull grantor name fields from the original provisioning request payload
    # (stored on the provision record), falling back to "there".
    _payload = provision.get("request_payload", {}) if provision else {}
    first_name = _resolve_first_name(
        grantor_first_name=_payload.get("grantor_first_name"),
        grantor_full_name=_payload.get("grantor_full_name"),
    )

    email_result = await _send_wingpoint_set_password_email(
        to_email=email,
        first_name=first_name,
        set_password_url=set_password_url,
    )

    email_status = email_result.get("status", "unknown")

    # Update provision record
    await db.external_provisions.update_one(
        {"wingpoint_ref": provision["wingpoint_ref"]},
        {"$set": {
            "set_password_url": set_password_url,
            "set_password_expires": expires_at.isoformat(),
            "email_status": email_status,
            "last_resent_at": now.isoformat()
        }}
    )

    return {
        "status": "resent",
        "user_id": user_id,
        "set_password_url": set_password_url,
        "set_password_expires": expires_at.isoformat(),
        "email_status": email_status,
        "message": f"Welcome email resent to {email}."
    }


@router.get("/provision-trustoffice/status")
async def provision_status(
    wingpoint_ref: str,
    partner: dict = Depends(verify_external_api_key)
):
    """Check provisioning status by wingpoint_ref."""
    await check_rate_limit(partner["partner_id"])

    provision = await db.external_provisions.find_one(
        {"wingpoint_ref": wingpoint_ref},
        {"_id": 0, "request_payload": 0}
    )

    if not provision:
        raise HTTPException(status_code=404, detail="No provision found for this wingpoint_ref")

    # Check if user has set password and logged in
    # Use inclusion projection so password_hash is actually returned
    user = await db.users.find_one({"user_id": provision["user_id"]}, {"password_hash": 1, "last_login": 1})
    has_password = bool(user and user.get("password_hash"))
    last_login = user.get("last_login") if user else None

    return {
        "wingpoint_ref": wingpoint_ref,
        "user_id": provision["user_id"],
        "trust_id": provision["trust_id"],
        "email": provision["email"],
        "trust_name": provision["trust_name"],
        "is_new_user": provision.get("is_new_user", True),
        "email_status": provision.get("email_status"),
        "has_set_password": has_password,
        "last_login": last_login,
        "created_at": provision.get("created_at"),
    }


# ==================== USER LOOKUP ====================

@router.get("/lookup-user")
async def lookup_user(
    email: str,
    partner: dict = Depends(verify_external_api_key)
):
    """
    Check if a TrustOffice user already exists for a given email.

    WingPoint uses this to decide whether to pass existing_trustoffice_user_id
    when provisioning, so it doesn't create a duplicate account when a customer
    used a different email on TrustOffice than on WingPoint.

    Query params:
    - email (required): the email address to look up

    Response 200: { "found": true, "user_id": "...", "email": "...",
                    "has_subscription": bool, "trust_count": N }
    Response 404: { "found": false }
    """
    partner_id = partner["partner_id"]
    await check_rate_limit(partner_id)

    normalized_email = email.lower().strip()
    logger.info(f"LookupUser: email={normalized_email} partner={partner_id}")

    user = await db.users.find_one({"email": normalized_email}, {"_id": 0})

    if not user:
        await log_audit(
            partner_id,
            action="lookup_user",
            wingpoint_ref=normalized_email,
            details={"email": normalized_email, "found": False},
            status="not_found",
        )
        raise HTTPException(status_code=404, detail={"found": False})

    user_id = user["user_id"]

    # Trust count for this user
    trust_count = await db.trusts.count_documents({"user_id": user_id})

    # Subscription state — has_subscription is true if they have a non-"none" plan
    has_subscription = False
    try:
        sub_state = await get_subscription_state(user_id)
        has_subscription = sub_state.plan_type not in ("none", "forever_free", "free")
    except Exception as e:
        logger.warning(f"LookupUser: get_subscription_state failed for {user_id}: {e}")

    await log_audit(
        partner_id,
        action="lookup_user",
        wingpoint_ref=normalized_email,
        details={
            "email": normalized_email,
            "found": True,
            "user_id": user_id,
            "has_subscription": has_subscription,
            "trust_count": trust_count,
        },
        status="success",
    )

    return {
        "found": True,
        "user_id": user_id,
        "email": user.get("email", normalized_email),
        "has_subscription": has_subscription,
        "trust_count": trust_count,
    }


# ==================== ACTIVATION WEBHOOKS ====================
# Fired when a WingPoint-provisioned user sets their password or first logs in.
# These notify WingPoint so they can auto-advance CRM lead status.

async def _resolve_provision_for_webhook(user_id: str, event_type: str) -> tuple[dict | None, bool | None, str | None]:
    """Resolve the provision record and password/login metadata for a webhook.

    Returns (provision, _has_password, _last_login) or (None, None, None) if
    the user is not WingPoint-referred and the webhook should be skipped.
    """
    provision = await db.external_provisions.find_one(
        {"user_id": user_id},
        {"_id": 0, "request_payload": 0}
    )

    if provision:
        # Admin-provisioned — password/last_login fetched elsewhere if needed
        return provision, None, None

    # Fall back to the user document for self-service signups
    user_doc = await db.users.find_one(
        {"user_id": user_id},
        {"_id": 0, "password_hash": 0}
    )
    if not user_doc:
        return None, None, None

    wp_ref = user_doc.get("wp_ref")
    if not wp_ref:
        return None, None, None

    provision = {
        "user_id": user_id,
        "email": user_doc.get("email"),
        "trust_id": user_doc.get("trust_id"),
        "trust_name": user_doc.get("wp_trust_name"),
        "wingpoint_ref": wp_ref,
        "partner_id": "wingpoint",
        "is_new_user": True,
        "created_at": user_doc.get("created_at"),
    }

    _has_password = None
    _last_login = None
    if event_type in ("password_set", "first_login"):
        pw_user = await db.users.find_one(
            {"user_id": user_id},
            {"password_hash": 1, "last_login": 1}
        )
        provision["email_status"] = None
        _has_password = bool(pw_user and pw_user.get("password_hash"))
        _last_login = pw_user.get("last_login") if pw_user else None

    return provision, _has_password, _last_login


async def _get_webhook_config(partner_id: str) -> tuple[str | None, str | None]:
    """Resolve webhook URL + secret from partner config, falling back to env vars.

    Returns (webhook_url, webhook_secret).  webhook_url is None if not
    configured or not HTTPS (caller should skip delivery in that case).
    """
    partner = await db.partner_api_keys.find_one(
        {"partner_id": partner_id},
        {"_id": 0}
    )
    webhook_url = (partner.get("webhook_url") if partner else None) or WINGPOINT_WEBHOOK_URL
    webhook_secret = (partner.get("webhook_secret") if partner else None) or WINGPOINT_WEBHOOK_SECRET

    if not webhook_url:
        return None, webhook_secret

    if not webhook_url.startswith("https://"):
        logger.warning(f"Webhook URL for partner {partner_id} is not HTTPS — skipping delivery: {webhook_url[:50]}")
        return None, webhook_secret

    return webhook_url, webhook_secret


def _build_webhook_payload(
    event_type: str, user_id: str, provision: dict, now: datetime,
    _last_login: str | None,
) -> str:
    """Build the JSON webhook payload (HMAC-signed externally) and return payload_json."""
    payload = {
        "event": event_type,
        "user_id": user_id,
        "email": provision.get("email"),
        "trust_id": provision.get("trust_id"),
        "trust_name": provision.get("trust_name"),
        "wingpoint_ref": provision.get("wingpoint_ref"),
        "timestamp": now.isoformat(),
    }

    if event_type == "password_set":
        payload["message"] = "User has set their password and can now log in."
    elif event_type == "first_login":
        payload["message"] = "User has logged in for the first time."
        if _last_login:
            payload["last_login"] = _last_login
    elif event_type == "signup_completed":
        payload["message"] = "User has completed self-service signup."

    return json.dumps(payload, sort_keys=True)


async def _record_webhook_audit(
    partner_id: str, user_id: str, provision: dict, webhook_url: str,
    action: str, now: datetime, response_status: int | None = None, error: str | None = None,
) -> None:
    """Record a webhook delivery audit entry (success or failure)."""
    entry = {
        "action": action,
        "partner_id": partner_id,
        "user_id": user_id,
        "wingpoint_ref": provision.get("wingpoint_ref"),
        "webhook_url": webhook_url,
        "timestamp": now.isoformat(),
    }
    if response_status is not None:
        entry["response_status"] = response_status
    if error is not None:
        entry["error"] = error
    await db.external_api_audit.insert_one(entry)


async def _send_webhook_with_retry(
    client, webhook_url: str, payload_json: str, headers: dict,
    event_type: str, user_id: str, provision: dict, partner_id: str, now: datetime,
    _last_login: str | None,
) -> None:
    """Send a webhook with up to 3 attempts and exponential backoff."""
    import httpx
    for attempt in range(3):
        try:
            resp = await client.post(webhook_url, content=payload_json, headers=headers)

            if 200 <= resp.status_code < 300:
                logger.info(
                    f"Webhook {event_type} delivered for user {user_id}: "
                    f"HTTP {resp.status_code} (attempt {attempt + 1})"
                )
                await _record_webhook_audit(
                    partner_id, user_id, provision, webhook_url,
                    f"webhook_{event_type}", now, response_status=resp.status_code,
                )
                return

            logger.warning(
                f"Webhook {event_type} got HTTP {resp.status_code} for user {user_id}: "
                f"not delivered (attempt {attempt + 1})"
            )
            if attempt < 2:
                await asyncio.sleep(1 * (attempt + 1))
                continue
            await _record_webhook_audit(
                partner_id, user_id, provision, webhook_url,
                f"webhook_{event_type}_failed", now, response_status=resp.status_code,
            )
            return

        except httpx.RequestError as e:
            logger.warning(
                f"Webhook {event_type} delivery failed (attempt {attempt + 1}): {e}"
            )
            if attempt < 2:
                await asyncio.sleep(1 * (attempt + 1))
                continue
    # All retries exhausted via RequestError path
    await _record_webhook_audit(
        partner_id, user_id, provision, webhook_url,
        f"webhook_{event_type}_failed", now, error="max retries exceeded (network errors)",
    )


async def fire_activation_webhook(user_id: str, event_type: str):
    """
    Fire an activation webhook to WingPoint for this user.

    event_type: "password_set" | "first_login" | "signup_completed"

    Works for BOTH admin-provisioned users (external_provisions record
    exists) and self-service signups (no provision record — falls back to
    the user document, which carries wp_ref for WingPoint-referred users).

    For self-service users with no wp_ref, the webhook is skipped silently
    (they were not referred by WingPoint).
    """
    import httpx

    provision, _has_password, _last_login = await _resolve_provision_for_webhook(user_id, event_type)
    if not provision:
        return

    partner_id = provision.get("partner_id", "wingpoint")
    webhook_url, webhook_secret = await _get_webhook_config(partner_id)
    if not webhook_url:
        return

    now = datetime.now(timezone.utc)

    # For first_login, fetch last_login from user record if not already resolved
    if event_type == "first_login" and not _last_login:
        user = await db.users.find_one({"user_id": user_id}, {"last_login": 1})
        if user and user.get("last_login"):
            _last_login = user["last_login"]

    payload_json = _build_webhook_payload(event_type, user_id, provision, now, _last_login)

    # Sign the payload with HMAC-SHA256
    if webhook_secret:
        signature = hmac.new(
            webhook_secret.encode(),
            payload_json.encode(),
            hashlib.sha256
        ).hexdigest()
    else:
        signature = "unsigned"

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": signature,
        "X-Webhook-Event": event_type,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await _send_webhook_with_retry(
                client, webhook_url, payload_json, headers,
                event_type, user_id, provision, partner_id, now, _last_login,
            )
    except Exception as e:
        logger.error(f"Webhook {event_type} delivery failed after retries for user {user_id}: {e}")
        await _record_webhook_audit(
            partner_id, user_id, provision, webhook_url,
            f"webhook_{event_type}_failed", now, error=str(e),
        )


# ==================== LINK TRUST (Authenticate-First Flow) ====================

@router.post("/link-trust")
async def link_trust(
    request: LinkTrustRequest,
    partner: dict = Depends(verify_external_api_key),
):
    """Link a trust to an existing TrustOffice user.
    
    This is the authenticate-first endpoint: WingPoint calls this AFTER the user
    has authenticated on TrustOffice and we have their real user_id from the
    connect token. No email lookup, no user creation, no welcome email.
    
    If a trust already exists for this wingpoint_ref (from a prior admin provision
    to a phantom user), it is re-linked to the authenticated user_id.
    """
    partner_id = partner["partner_id"]
    user_id = request.trustoffice_user_id
    logger.info(f"LinkTrust: START wingpoint_ref={request.wingpoint_ref} user_id={user_id} trust_name='{request.trust_name}'")
    
    # Verify the user exists
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail={
            "error": f"TrustOffice user {user_id} not found",
            "message": "The connect token's user_id does not match any TrustOffice account."
        })
    
    now = datetime.now(timezone.utc)
    
    # Map trust type
    to_trust_type = WINGPOINT_TRUST_TYPE_MAP.get(request.trust_type, "family")
    
    # Build trustee string
    trustee_parts = [
        request.trustee_first_name, request.trustee_middle_name,
        request.trustee_last_name, request.trustee_suffix,
    ]
    trustee_str = " ".join(p for p in trustee_parts if p) or request.trustee_full_name or ""
    
    # Build trust doc
    trust_id = f"trust_{uuid.uuid4().hex[:12]}"
    trust_doc = {
        "trust_id": trust_id,
        "user_id": user_id,
        "wingpoint_ref": request.wingpoint_ref,
        "name": request.trust_name,
        "trust_type": to_trust_type,
        "entity_type": request.entity_type,
        "jurisdiction": request.jurisdiction,
        "role": request.role_for_trust,
        "start_date": request.trust_formation_date,
        "trustees": trustee_str,
        "ein": request.ein,
        "state_code": request.jurisdiction,
        "source": "wingpoint",
        "use_wingpoint_trustee": request.use_wingpoint_trustee,
        "trustee_first_name": request.trustee_first_name,
        "trustee_middle_name": request.trustee_middle_name,
        "trustee_last_name": request.trustee_last_name,
        "trustee_suffix": request.trustee_suffix,
        "trustee_full_name": request.trustee_full_name,
        "mailing_address_line1": request.mailing_address_line1,
        "mailing_address_line2": request.mailing_address_line2,
        "mailing_city": request.mailing_city,
        "mailing_state": request.mailing_state,
        "mailing_zip": request.mailing_zip,
        "mailing_county": request.mailing_county,
        "bank_name": request.bank_name,
        "has_irs_confirmation": request.has_irs_confirmation,
        "has_declaration": request.has_declaration,
        "has_certification": request.has_certification,
        "has_binder_kit": request.has_binder_kit,
        "source_package": request.source_package,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    
    # Check if trust already exists for this wingpoint_ref — re-link if so
    existing_trust = await db.trusts.find_one(
        {"wingpoint_ref": request.wingpoint_ref},
        {"trust_id": 1, "user_id": 1, "_id": 0}
    )
    if existing_trust:
        existing_trust_id = existing_trust["trust_id"]
        if existing_trust.get("user_id") != user_id:
            # Re-link to the authenticated user
            await db.trusts.update_one(
                {"trust_id": existing_trust_id},
                {"$set": {"user_id": user_id, "updated_at": now.isoformat()}},
            )
            logger.info(f"LinkTrust: Re-linked trust {existing_trust_id} from user {existing_trust.get('user_id')} to {user_id}")
        else:
            logger.info(f"LinkTrust: Trust {existing_trust_id} already linked to user {user_id}")
        trust_id = existing_trust_id
    else:
        await db.trusts.insert_one(trust_doc)
        logger.info(f"LinkTrust: Created trust {trust_id} ('{request.trust_name}') for user {user_id}")
    
    # Create entity record (same as provision path)
    entity_id = f"entity_{uuid.uuid4().hex[:12]}"
    entity_doc = {
        "entity_id": entity_id,
        "user_id": user_id,
        "trust_id": trust_id,
        "name": request.trust_name,
        "entity_type": "Trust",
        "legal_name": request.trust_name,
        "formation_date": request.trust_formation_date,
        "governing_law": request.jurisdiction or "",
        "ein": request.ein,
        "trustee_names": trustee_str,
        "beneficiary_standard": "",
        "article_ref_distribution": "",
        "article_ref_compensation": "",
        "article_ref_amendment": "",
        "oversight_required": False,
        "member_names": "",
        "manager_names": "",
        "article_ref_authority": "",
        "article_ref_profit_distribution": "",
        "created_at": now.isoformat(),
    }
    _existing_entity = await db.entities.find_one({"trust_id": trust_id}, {"_id": 1})
    if not _existing_entity:
        try:
            await db.entities.insert_one(entity_doc)
            logger.info(f"LinkTrust: Created entity {entity_id} for trust {trust_id}")
        except Exception as e:
            logger.warning(f"LinkTrust: Failed to create entity for trust {trust_id}: {e}")
    
    # Audit log
    await log_audit(
        partner_id=partner_id,
        action="link_trust",
        wingpoint_ref=request.wingpoint_ref,
        details={
            "user_id": user_id,
            "trust_id": trust_id,
            "trust_name": request.trust_name,
            "re_linked": existing_trust is not None,
        },
        status="success",
    )
    
    logger.info(f"LinkTrust: COMPLETE wingpoint_ref={request.wingpoint_ref} user_id={user_id} trust_id={trust_id}")
    
    return {
        "ok": True,
        "user_id": user_id,
        "trust_id": trust_id,
        "trust_name": request.trust_name,
        "re_linked": existing_trust is not None,
    }