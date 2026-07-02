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
import re

from database import db
from email_service import email_service

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
    coupon_code: Optional[str] = None

    # Control flags
    dry_run: bool = False
    resend: bool = False

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


class ResendActivationRequest(BaseModel):
    """Resend welcome email for an existing provisioning."""
    wingpoint_ref: str
    email: EmailStr


class ProvisionStatusRequest(BaseModel):
    """Check provisioning status."""
    wingpoint_ref: str


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
        # Same wingpoint_ref already provisioned
        if request.resend:
            # Resend mode: generate fresh set-password token, send new email
            return await _resend_activation(existing_provision, partner)

        # Check if payload matches (conflict detection)
        existing_payload = existing_provision.get("request_payload", {})
        if existing_payload.get("trust_name") != request.trust_name or \
           existing_payload.get("email", "").lower() != request.email.lower():
            # Different data for same idempotency key → 409 Conflict
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "Idempotency conflict: this wingpoint_ref was already used with different data.",
                    "existing_user_id": existing_provision.get("user_id"),
                    "existing_trust_id": existing_provision.get("trust_id"),
                    "existing_set_password_url": existing_provision.get("set_password_url"),
                    "existing_set_password_expires": existing_provision.get("set_password_expires"),
                    "message": "Use the existing provision or provide a different wingpoint_ref."
                }
            )

        # Same payload, same ref → return existing result (idempotent success)
        existing_provision["status"] = "already_exists"
        return existing_provision

    # ---- DRY RUN ----
    if request.dry_run:
        # Validate and return what would be created, without persisting
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

        # Check if user would already exist
        existing_user = await db.users.find_one({"email": request.email.lower().strip()}, {"_id": 0})
        if existing_user:
            dry_run_response["would_create_user"] = False
            dry_run_response["existing_user_id"] = existing_user["user_id"]
            dry_run_response["message"] = "Dry run — user already exists. Trust would be added to existing account."

        # Check if trust name would conflict
        if existing_user:
            existing_trust = await db.trusts.find_one({
                "user_id": existing_user["user_id"],
                "name": request.trust_name
            }, {"_id": 0})
            if existing_trust:
                dry_run_response["would_create_trust"] = False
                dry_run_response["existing_trust_id"] = existing_trust.get("trust_id")

        return dry_run_response

    # ---- MAP WINGPOINT DATA TO TRUSTOFFICE ----
    to_trust_type = WINGPOINT_TRUST_TYPE_MAP.get(request.trust_type, "family")

    # Derive display name
    display_name = request.grantor_full_name
    if not display_name:
        parts = [request.grantor_first_name, request.grantor_middle_name,
                  request.grantor_last_name, request.grantor_suffix]
        display_name = " ".join(p for p in parts if p)

    # Derive trustee string for TrustOffice's existing `trustees` field
    trustee_str = request.trustee_full_name
    if not trustee_str:
        parts = [request.trustee_first_name, request.trustee_middle_name,
                  request.trustee_last_name, request.trustee_suffix]
        trustee_str = " ".join(p for p in parts if p)

    email = request.email.lower().strip()
    now = datetime.now(timezone.utc)

    # ---- FIND OR CREATE USER ----
    existing_user = await db.users.find_one({"email": email}, {"_id": 0})
    is_new_user = existing_user is None

    if existing_user:
        user_id = existing_user["user_id"]
        logger.info(f"Provision: Adding trust to existing user {user_id} ({email})")
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        user_doc = {
            "user_id": user_id,
            "email": email,
            "name": display_name or email.split("@")[0],
            "phone": request.phone,
            "is_admin": False,
            "created_at": now.isoformat(),
            "created_via": "wingpoint_provision",
            "source": "wingpoint",
            "grantor_first_name": request.grantor_first_name,
            "grantor_middle_name": request.grantor_middle_name,
            "grantor_last_name": request.grantor_last_name,
            "grantor_suffix": request.grantor_suffix,
            "grantor_full_name": request.grantor_full_name,
            "role_for_trust": request.role_for_trust,
            "use_wingpoint_trustee": request.use_wingpoint_trustee,
        }
        try:
            await db.users.insert_one(user_doc)
        except Exception as e:
            # Handle race condition: another request may have created this user
            if "duplicate key" in str(e).lower() or "E11000" in str(e):
                existing_user = await db.users.find_one({"email": email}, {"_id": 0})
                if existing_user:
                    user_id = existing_user["user_id"]
                    is_new_user = False
                    logger.info(f"Provision: Race condition resolved — user {user_id} ({email}) already exists")
                else:
                    raise HTTPException(status_code=500, detail="Failed to create user due to concurrent request. Please retry.")
            else:
                raise

        # Create free subscription for new user (only if we actually created the user)
        if is_new_user:
            await db.subscriptions.insert_one({
                "subscription_id": f"sub_{uuid.uuid4().hex[:12]}",
                "user_id": user_id,
                "plan_type": "free",
                "status": "active",
                "trial_start_date": None,
                "trial_end_date": None,
                "stripe_customer_id": None,
                "stripe_subscription_id": None,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "notes": "Free individual trustee account — WingPoint provisioned",
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

        logger.info(f"Provision: Created new user {user_id} ({email}) via WingPoint")

    # ---- CREATE TRUST ----
    trust_id = f"trust_{uuid.uuid4().hex[:12]}"

    trust_doc = {
        "trust_id": trust_id,
        "user_id": user_id,
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
        "wingpoint_ref": request.wingpoint_ref,
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

    await db.trusts.insert_one(trust_doc)
    logger.info(f"Provision: Created trust {trust_id} ('{request.trust_name}') for user {user_id}")

    # ---- GENERATE SET-PASSWORD TOKEN (7-day expiry) ----
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
    set_password_url = f"{frontend_url}/reset-password?token={set_password_token}"

    # ---- INSERT PROVISION RECORD EARLY (pending status) ----
    # Inserted before email send so retries find an existing anchor even if
    # a later step fails.  Updated to "complete" after the email step succeeds.
    # NOTE: A unique index on idem_key should be created in server.py:
    #   await db.external_provisions.create_index("idem_key", unique=True)
    provision_id = f"prov_{uuid.uuid4().hex[:12]}"
    provision_record = {
        "provision_id": provision_id,
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
        "created_at": now.isoformat()
    }

    try:
        await db.external_provisions.insert_one(provision_record)
    except Exception as e:
        if "duplicate key" in str(e).lower() or "E11000" in str(e):
            # Concurrent request with same idem_key already provisioned — return existing
            existing = await db.external_provisions.find_one({"idem_key": idem_key}, {"_id": 0})
            if existing:
                logger.info(f"Idempotent replay for idem_key={idem_key} (race resolved)")
                # Return the existing provision whether pending or complete.
                # Do NOT fall through — that would create a duplicate trust and send a duplicate email.
                if existing.get("status") == "complete":
                    return {
                        "status": "already_exists",
                        "provision": existing,
                        "message": "Trust already provisioned"
                    }
                else:
                    # Pending means another request is mid-flight. Return it as-is.
                    return {
                        "status": "in_progress",
                        "provision": existing,
                        "message": "Trust provisioning already in progress"
                    }
            # If existing is None (record was deleted between error and re-fetch), re-raise
            raise
        else:
            raise

    # ---- SEND WELCOME EMAIL (wrapped so it can't block the provision record) ----
    user_name = display_name or email.split("@")[0]
    try:
        email_result = await email_service.send_welcome_set_password_email(
            to_email=email,
            user_name=user_name,
            set_password_url=set_password_url
        )
        email_status = email_result.get("status", "unknown")
    except Exception as e:
        email_result = {"status": "failed", "error": str(e)}
        email_status = "failed"
        logger.error(f"Provision: Welcome email raised exception for {email}: {e}")

    if email_status == "failed":
        logger.error(f"Provision: Welcome email failed for {email}: {email_result.get('error')}")
    elif email_status == "skipped":
        logger.warning(f"Provision: Email service not configured — welcome email skipped for {email}")

    # ---- UPDATE PROVISION RECORD TO COMPLETE ----
    await db.external_provisions.update_one(
        {"idem_key": idem_key},
        {"$set": {
            "status": "complete",
            "email_status": email_status,
            "completed_at": datetime.now(timezone.utc).isoformat()
        }}
    )

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
    response = {
        "status": "created" if is_new_user else "trust_added",
        "user_id": user_id,
        "trust_id": trust_id,
        "set_password_url": set_password_url,
        "set_password_expires": expires_at.isoformat(),
        "is_new_user": is_new_user,
        "email": email,
        "trust_name": request.trust_name,
        "email_status": email_status,
    }

    if email_status == "failed":
        response["message"] = f"Account created, but welcome email failed: {email_result.get('error', 'unknown error')}"
    elif email_status == "skipped":
        response["message"] = "Account created, but email service is not configured. Set-password link generated but not emailed."
    else:
        response["message"] = f"Account {'created' if is_new_user else 'updated'}. Welcome email sent to {email}."

    return response


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
    set_password_url = f"{frontend_url}/reset-password?token={set_password_token}"

    # Get user name for email
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    user_name = user.get("name", email.split("@")[0]) if user else email.split("@")[0]

    email_result = await email_service.send_welcome_set_password_email(
        to_email=email,
        user_name=user_name,
        set_password_url=set_password_url
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


# ==================== ACTIVATION WEBHOOKS ====================
# Fired when a WingPoint-provisioned user sets their password or first logs in.
# These notify WingPoint so they can auto-advance CRM lead status.

async def fire_activation_webhook(user_id: str, event_type: str):
    """
    Fire an activation webhook to WingPoint if this user was provisioned via external API.
    
    event_type: "password_set" | "first_login"
    
    Looks up the external_provisions record for this user_id, then POSTs
    a signed payload to the partner's webhook_url (if configured).
    """
    import httpx
    
    # Find the provision record for this user
    provision = await db.external_provisions.find_one(
        {"user_id": user_id},
        {"_id": 0, "request_payload": 0}
    )
    
    if not provision:
        # Not a WingPoint-provisioned user — skip silently
        return
    
    # Get partner config to find the webhook URL and secret
    partner_id = provision.get("partner_id", "wingpoint")
    partner = await db.partner_api_keys.find_one(
        {"partner_id": partner_id},
        {"_id": 0}
    )
    
    # Try partner config first, then fall back to env vars
    webhook_url = (partner.get("webhook_url") if partner else None) or WINGPOINT_WEBHOOK_URL
    webhook_secret = (partner.get("webhook_secret") if partner else None) or WINGPOINT_WEBHOOK_SECRET
    
    if not webhook_url:
        # No webhook configured for this partner — skip silently
        return

    # Validate webhook URL is HTTPS to prevent SSRF
    if not webhook_url.startswith("https://"):
        logger.warning(f"Webhook URL for partner {partner_id} is not HTTPS — skipping delivery: {webhook_url[:50]}")
        return
    
    # Build the webhook payload
    now = datetime.now(timezone.utc)
    payload = {
        "event": event_type,
        "user_id": user_id,
        "email": provision.get("email"),
        "trust_id": provision.get("trust_id"),
        "trust_name": provision.get("trust_name"),
        "wingpoint_ref": provision.get("wingpoint_ref"),
        "timestamp": now.isoformat(),
    }
    
    # Add event-specific fields
    if event_type == "password_set":
        payload["message"] = "User has set their password and can now log in."
    elif event_type == "first_login":
        payload["message"] = "User has logged in for the first time."
        # Add last_login timestamp from user record
        user = await db.users.find_one({"user_id": user_id}, {"last_login": 1})
        if user and user.get("last_login"):
            payload["last_login"] = user["last_login"]
    
    # Sign the payload with HMAC-SHA256
    payload_json = json.dumps(payload, sort_keys=True)
    if webhook_secret:
        signature = hmac.new(
            webhook_secret.encode(),
            payload_json.encode(),
            hashlib.sha256
        ).hexdigest()
    else:
        signature = "unsigned"
    
    # Send the webhook with retry (fire-and-forget, non-blocking)
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": signature,
        "X-Webhook-Event": event_type,
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for attempt in range(3):
                try:
                    resp = await client.post(
                        webhook_url,
                        content=payload_json,
                        headers=headers,
                    )

                    if 200 <= resp.status_code < 300:
                        # Success — log and record delivery
                        logger.info(
                            f"Webhook {event_type} delivered for user {user_id}: "
                            f"HTTP {resp.status_code} (attempt {attempt + 1})"
                        )
                        await db.external_api_audit.insert_one({
                            "action": f"webhook_{event_type}",
                            "partner_id": partner_id,
                            "user_id": user_id,
                            "wingpoint_ref": provision.get("wingpoint_ref"),
                            "webhook_url": webhook_url,
                            "response_status": resp.status_code,
                            "timestamp": now.isoformat(),
                        })
                        return  # Success
                    else:
                        # Non-2xx response — not delivered, retry if attempts remain
                        logger.warning(
                            f"Webhook {event_type} got HTTP {resp.status_code} for user {user_id}: "
                            f"not delivered (attempt {attempt + 1})"
                        )
                        if attempt < 2:
                            await asyncio.sleep(1 * (attempt + 1))
                            continue
                        # Last attempt failed — record as failed delivery
                        await db.external_api_audit.insert_one({
                            "action": f"webhook_{event_type}_failed",
                            "partner_id": partner_id,
                            "user_id": user_id,
                            "wingpoint_ref": provision.get("wingpoint_ref"),
                            "webhook_url": webhook_url,
                            "response_status": resp.status_code,
                            "timestamp": now.isoformat(),
                        })
                        return
                except httpx.RequestError as e:
                    logger.warning(
                        f"Webhook {event_type} delivery failed (attempt {attempt + 1}): {e}"
                    )
                    if attempt < 2:
                        await asyncio.sleep(1 * (attempt + 1))  # Backoff: 1s, 2s
                    continue
            # All retries exhausted via RequestError path — record failure
            await db.external_api_audit.insert_one({
                "action": f"webhook_{event_type}_failed",
                "partner_id": partner_id,
                "user_id": user_id,
                "wingpoint_ref": provision.get("wingpoint_ref"),
                "webhook_url": webhook_url,
                "error": "max retries exceeded (network errors)",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
    except Exception as e:
        logger.error(f"Webhook {event_type} delivery failed after retries for user {user_id}: {e}")
        # Record the failure
        await db.external_api_audit.insert_one({
            "action": f"webhook_{event_type}_failed",
            "partner_id": partner_id,
            "user_id": user_id,
            "wingpoint_ref": provision.get("wingpoint_ref"),
            "error": str(e),
            "timestamp": now.isoformat(),
        })