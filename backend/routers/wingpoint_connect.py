"""
WingPoint Connect Flow v2 — three-branch resolution at connect entry.

Spec: Kit/life/brands/TrustOffice/specs/2026-10-22-connect-flow-v2.md
(Jeff approved, Discord msg 1562866527668019332, 2026-10-22).

THE PROBLEM THIS SOLVES
-----------------------
WingPoint members arrive at /connect/wingpoint with their email already known
by WingPoint. TrustOffice used to show EVERYONE the same login wall. A member
who was provisioned by the WingPoint flow but never set a password (John
Matthews' case) hit a dead end: no account to log into, no way forward.

THE THREE BRANCHES (decision happens at connect entry, off the member's email)
-------------------------------------------------------------------------------
  no account        -> "new"              prefilled + locked signup, straight to payment
  account, no pwd   -> "needs_activation" set-a-password screen bound to the EXISTING account
  account, has pwd  -> "activated"        prefilled login (unchanged behavior)

SECURITY GUARDRAILS (spec §Security guardrails)
------------------------------------------------
  * The existence/activation lookup is a SCOPED endpoint. It requires a valid
    WingPoint connect context (wp_ref + app_id + a WingPoint redirect_url) —
    there is NO generic public "does this email exist" API.
  * Rate limited per IP, per connect context, and per email fingerprint.
  * Account claim (never-activated -> set password) ALWAYS goes through email
    verification (6-digit code delivered through the existing Postmark
    machinery). A password is never set from the page alone.
  * Member emails are NEVER written to app logs. Only a salted fingerprint is
    logged, so log lines can be correlated without exposing the address.

A provisioned-but-never-activated member MUST NOT spawn a second account: the
existing account holds the provisioned trust, and the claim screen claims THAT
account.
"""

from fastapi import APIRouter, HTTPException, Depends, Request, Response, BackgroundTasks
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urlparse, parse_qs
import hashlib
import hmac
import logging
import os
import re
import secrets
import uuid

from database import db
from dependencies import (
    hash_password,
    verify_password,
    create_jwt_token,
    create_refresh_token_record,
    ACCESS_TOKEN_EXPIRATION_MINUTES,
    REFRESH_TOKEN_EXPIRATION_DAYS,
)
from email_service import email_service
from routers.auth import rate_limit, validate_password_strength
from services.wingpoint_identity import is_wingpoint_user
from utils.audit import log_audit_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wingpoint-connect", tags=["wingpoint-connect"])


# ==================== CONFIG ====================

# Shared secret used to fingerprint connect contexts. Falls back to the same
# chain the connect-token minting uses (routers/auth.py) so the two subsystems
# stay in lockstep.
CONNECT_CONTEXT_SALT = (
    os.environ.get("CONNECT_TOKEN_SECRET")
    or os.environ.get("EXTERNAL_API_KEY")
    or os.environ.get("TRUSTOFFICE_EXTERNAL_API_KEY")
    or "wingpoint-connect-dev-salt"
)

# Hosts a WingPoint connect redirect_url may point at. Anything else is
# rejected — the connect context is only valid when WingPoint sent it.
_ALLOWED_REDIRECT_SUFFIXES = (
    ".wingpointtrust.com",
    ".wingpointtrusts.com",
)
_EXTRA_ALLOWED_REDIRECT_HOSTS = tuple(
    h.strip().lower()
    for h in os.environ.get("WINGPOINT_CONNECT_ALLOWED_HOSTS", "").split(",")
    if h.strip()
)

# Verification code lifetime for the account-claim flow.
CLAIM_CODE_TTL_MINUTES = 20
# Max verification attempts per issued code before it is burned.
CLAIM_CODE_MAX_ATTEMPTS = 5

# Rate limits (per window, in seconds).
RESOLVE_RATE_LIMIT = (20, 60)          # per IP, per path
CONTEXT_RATE_LIMIT = (50, 600)         # per connect context (app_id)
EMAIL_RATE_LIMIT = (5, 600)            # per (context, email fingerprint)

_WP_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,63}$")
_APP_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,63}$")


# ==================== MODELS ====================

class ConnectContext(BaseModel):
    """The WingPoint connect context carried on every connect-flow request."""
    wp_ref: str
    app_id: str
    email: str
    redirect_url: Optional[str] = None


class ResolveRequest(ConnectContext):
    """Body for POST /api/wingpoint-connect/resolve."""


class ClaimCodeRequest(ConnectContext):
    """Body for POST /api/wingpoint-connect/claim/request-code."""


class ClaimVerifyRequest(ConnectContext):
    """Body for POST /api/wingpoint-connect/claim/verify."""
    code: str
    new_password: str


class SignupRequest(ConnectContext):
    """Body for POST /api/wingpoint-connect/signup."""
    name: str = ""
    password: str
    plan_type: Optional[str] = None
    billing_period: Optional[str] = None


# ==================== HELPERS ====================

def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _email_fingerprint(email: str) -> str:
    """Stable, non-reversible fingerprint of an email for logs + rate limits.

    Member emails are never logged verbatim (spec §Security guardrails). The
    fingerprint lets us correlate a request across log lines and rate-limit
    buckets without storing or printing the address.
    """
    normalized = _normalize_email(email)
    return hmac.new(
        CONNECT_CONTEXT_SALT.encode("utf-8"),
        normalized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:24]


def _normalize_email_for_log(email: str) -> str:
    """Log-safe email representation: fingerprint only, never the address."""
    return f"fp:{_email_fingerprint(email)}"


def _extract_app_id(redirect_url: Optional[str]) -> Optional[str]:
    """Pull app_id out of the WingPoint callback URL (it is a query param)."""
    if not redirect_url:
        return None
    try:
        parsed = urlparse(redirect_url)
    except Exception:
        return None
    values = parse_qs(parsed.query or "").get("app_id") or []
    for value in values:
        if value and value.strip():
            return value.strip()
    return None


def _redirect_host_is_wingpoint(redirect_url: str) -> bool:
    try:
        host = (urlparse(redirect_url).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    if host in _EXTRA_ALLOWED_REDIRECT_HOSTS:
        return True
    for suffix in _ALLOWED_REDIRECT_SUFFIXES:
        bare = suffix.lstrip(".")
        if host == bare or host.endswith(f".{bare}"):
            return True
    return False


def _validate_connect_context(
    wp_ref: str, app_id: str, redirect_url: Optional[str],
) -> tuple[str, str]:
    """Validate the WingPoint connect context. Returns (wp_ref, app_id).

    Raises HTTPException(400) when the context is missing or malformed. This
    is the scoping mechanism that keeps account-existence lookups off the
    public internet.
    """
    wp_ref = (wp_ref or "").strip()
    app_id = (app_id or "").strip()

    if not app_id and redirect_url:
        app_id = _extract_app_id(redirect_url) or ""

    if not wp_ref or not _WP_REF_RE.match(wp_ref):
        raise HTTPException(status_code=400, detail="Invalid WingPoint connect context.")
    if not app_id or not _APP_ID_RE.match(app_id):
        raise HTTPException(status_code=400, detail="Invalid WingPoint connect context.")
    if not redirect_url or not _redirect_host_is_wingpoint(redirect_url):
        raise HTTPException(status_code=400, detail="Invalid WingPoint connect context.")
    return wp_ref, app_id


async def _bump_rate_limit_bucket(bucket: str, limit: int, window_seconds: int) -> None:
    """Mongo-backed fixed-window counter. Raises HTTPException(429) on limit."""
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(seconds=window_seconds)
    record = await db.wingpoint_connect_rate_limits.find_one({"bucket": bucket})
    window_started_at = (record or {}).get("window_started_at") or ""
    if not record or window_started_at < window_start.isoformat():
        await db.wingpoint_connect_rate_limits.update_one(
            {"bucket": bucket},
            {
                "$set": {
                    "bucket": bucket,
                    "count": 1,
                    "window_started_at": now.isoformat(),
                }
            },
            upsert=True,
        )
        return

    count = int(record.get("count") or 0) + 1
    await db.wingpoint_connect_rate_limits.update_one(
        {"bucket": bucket},
        {"$set": {"count": count, "last_seen_at": now.isoformat()}},
    )
    if count > limit:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait a moment and try again.",
        )


async def _enforce_connect_rate_limits(
    app_id: str, email: str, ip_bucket_suffix: str,
) -> None:
    """Apply the three connect-flow rate limits (context, email, ip)."""
    fingerprint = _email_fingerprint(email)
    await _bump_rate_limit_bucket(
        f"context:{app_id}", CONTEXT_RATE_LIMIT[0], CONTEXT_RATE_LIMIT[1]
    )
    await _bump_rate_limit_bucket(
        f"email:{app_id}:{fingerprint}", EMAIL_RATE_LIMIT[0], EMAIL_RATE_LIMIT[1]
    )
    await _bump_rate_limit_bucket(
        f"ip:{ip_bucket_suffix}", RESOLVE_RATE_LIMIT[0], RESOLVE_RATE_LIMIT[1]
    )


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _resolve_connect_state(user_doc: Optional[dict]) -> str:
    """Map a user document to one of the three connect branches.

    'new'              — no account for this email
    'needs_activation' — account exists but no password was ever set
    'activated'        — account exists and has a password
    """
    if not user_doc:
        return "new"
    if not user_doc.get("password_hash"):
        return "needs_activation"
    return "activated"


async def _find_user_by_email(email: str) -> Optional[dict]:
    return await db.users.find_one({"email": _normalize_email(email)}, {"_id": 0})


# ==================== ENDPOINTS ====================

@router.post("/resolve")
async def resolve_connect_state(
    body: ResolveRequest,
    request: Request,
    _rl: None = Depends(rate_limit(*RESOLVE_RATE_LIMIT)),
):
    """Resolve which connect branch applies to a member's email.

    SCOPED endpoint — requires a valid WingPoint connect context
    (wp_ref + app_id + WingPoint redirect_url). Rate limited per IP, per
    context, and per email fingerprint. Never logs the member's email.
    """
    wp_ref, app_id = _validate_connect_context(
        body.wp_ref, body.app_id, body.redirect_url
    )
    email = _normalize_email(body.email)
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="A valid email address is required.")

    await _enforce_connect_rate_limits(app_id, email, _client_ip(request))

    user_doc = await _find_user_by_email(email)
    state = _resolve_connect_state(user_doc)

    logger.info(
        f"WingPoint connect resolve: state={state} app_id={app_id} "
        f"wp_ref={wp_ref} email={_normalize_email_for_log(email)}"
    )

    # The response does NOT echo the member's email. The prefill is UI-only:
    # the frontend already holds the address in the URL it was handed by
    # WingPoint, so the server never needs to reflect it back. This also
    # keeps the response free of anything that looks like an email oracle.
    return {
        "state": state,
        "email_locked": True,
        "verification_required": state == "needs_activation",
        "wp_ref": wp_ref,
        "app_id": app_id,
    }


@router.post("/claim/request-code")
async def request_claim_code(
    body: ClaimCodeRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    _rl: None = Depends(rate_limit(*RESOLVE_RATE_LIMIT)),
):
    """Email a 6-digit verification code so a provisioned member can claim
    their EXISTING account by setting a password.

    The response is CONSTANT regardless of whether the account exists — no
    enumeration surface. Codes are only sent for accounts that exist AND
    have never had a password set (the 'needs_activation' branch).
    """
    wp_ref, app_id = _validate_connect_context(
        body.wp_ref, body.app_id, body.redirect_url
    )
    email = _normalize_email(body.email)
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="A valid email address is required.")

    await _enforce_connect_rate_limits(app_id, email, _client_ip(request))

    user_doc = await _find_user_by_email(email)
    code_sent = False

    if user_doc and not user_doc.get("password_hash"):
        code = f"{secrets.randbelow(1_000_000):06d}"
        await _store_claim_code(email, user_doc["user_id"], code)
        try:
            await email_service.send_wingpoint_connect_code_email(
                to_email=email,
                user_name=user_doc.get("name") or email.split("@")[0],
                code=code,
            )
            code_sent = True
        except Exception as exc:  # pragma: no cover - email provider failure
            logger.error(
                f"WingPoint claim code email failed for {_normalize_email_for_log(email)}: {exc}"
            )

    logger.info(
        f"WingPoint claim code requested: sent={code_sent} app_id={app_id} "
        f"wp_ref={wp_ref} email={_normalize_email_for_log(email)}"
    )

    # Constant response — the caller cannot tell whether the account exists.
    return {
        "sent": True,
        "message": (
            "If that account needs a password, we've emailed a 6-digit code. "
            "Check your inbox (and spam folder)."
        ),
    }


@router.post("/claim/verify")
async def verify_claim_code(
    body: ClaimVerifyRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    _rl: None = Depends(rate_limit(*RESOLVE_RATE_LIMIT)),
):
    """Verify the emailed code and set the password on the EXISTING account.

    The password is only ever written to the account that already holds the
    provisioned trust — a claim NEVER creates a second account.
    """
    wp_ref, app_id = _validate_connect_context(
        body.wp_ref, body.app_id, body.redirect_url
    )
    email = _normalize_email(body.email)
    code = (body.code or "").strip()

    is_valid, error_msg = validate_password_strength(body.new_password or "")
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    if not re.fullmatch(r"\d{6}", code):
        raise HTTPException(status_code=400, detail="Enter the 6-digit code from your email.")

    await _enforce_connect_rate_limits(app_id, email, _client_ip(request))

    user_doc = await _find_user_by_email(email)
    if not user_doc:
        # Constant-shape failure — do not confirm or deny account existence.
        raise HTTPException(status_code=400, detail="That code is not valid. Request a new one.")
    if user_doc.get("password_hash"):
        # The account was activated in the meantime — the member should just
        # log in. Never overwrite an existing password from a claim.
        raise HTTPException(
            status_code=409,
            detail="This account already has a password. Sign in instead.",
        )

    verified = await _consume_claim_code(email, code)
    if not verified:
        raise HTTPException(status_code=400, detail="That code is not valid. Request a new one.")

    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"user_id": user_doc["user_id"]},
        {
            "$set": {
                "password_hash": hash_password(body.new_password),
                "password_set_at": now.isoformat(),
                "activated_via": "wingpoint_connect_claim",
            }
        },
    )

    logger.info(
        f"WingPoint claim verified: user_id={user_doc['user_id']} app_id={app_id} "
        f"wp_ref={wp_ref} email={_normalize_email_for_log(email)}"
    )

    await log_audit_event(
        user_doc["user_id"],
        "wingpoint_connect_claim",
        "user",
        user_doc["user_id"],
        {"wp_ref": wp_ref, "app_id": app_id},
    )

    # Fire the WingPoint 'password_set' activation webhook (first password set).
    try:
        from routers.external import fire_activation_webhook
        background_tasks.add_task(
            fire_activation_webhook, user_doc["user_id"], "password_set"
        )
    except Exception as exc:  # pragma: no cover - webhook is best effort
        logger.warning(
            f"Failed to queue password_set webhook for {user_doc['user_id']}: {exc}"
        )

    return await _issue_session(user_doc, response)


@router.post("/signup")
async def connect_signup(
    body: SignupRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    _rl: None = Depends(rate_limit(*RESOLVE_RATE_LIMIT)),
):
    """Create the account for the 'no account' branch, bound to the WP email.

    The account is created with the member's chosen password, stamped with the
    WingPoint reference, and (when a trust for that wp_ref already exists)
    that trust is re-linked to the new account so the member's trust is
    attached before payment.
    """
    wp_ref, app_id = _validate_connect_context(
        body.wp_ref, body.app_id, body.redirect_url
    )
    email = _normalize_email(body.email)
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="A valid email address is required.")

    is_valid, error_msg = validate_password_strength(body.password or "")
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    await _enforce_connect_rate_limits(app_id, email, _client_ip(request))

    existing = await _find_user_by_email(email)
    if existing:
        # Never create a second account for an email that already has one.
        state = _resolve_connect_state(existing)
        raise HTTPException(
            status_code=409,
            detail={
                "message": "An account already exists for this email.",
                "state": state,
            },
        )

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    display_name = (body.name or "").strip() or email.split("@")[0]

    user_doc = {
        "user_id": user_id,
        "email": email,
        "name": display_name,
        "password_hash": hash_password(body.password),
        "created_at": now_iso,
        "created_via": "wingpoint_connect",
        "source": "wingpoint",
        "wp_ref": wp_ref,
        "is_admin": False,
        "agent_enabled": False,
        "agent_consent": False,
    }

    try:
        await db.users.insert_one(dict(user_doc))
    except Exception as exc:
        # Unique index on email — a concurrent signup won the race.
        if "duplicate key" in str(exc).lower() or "E11000" in str(exc):
            existing = await _find_user_by_email(email)
            if existing:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "An account already exists for this email.",
                        "state": _resolve_connect_state(existing),
                    },
                )
        raise

    # Subscription doc — no plan until the member pays (paywall keeps the
    # account product-less until Stripe confirms payment).
    await db.subscriptions.update_one(
        {"user_id": user_id},
        {
            "$setOnInsert": {
                "subscription_id": f"sub_{uuid.uuid4().hex[:12]}",
                "user_id": user_id,
                "plan_type": "none",
                "status": "expired",
                "stripe_customer_id": None,
                "stripe_subscription_id": None,
                "created_at": now_iso,
                "updated_at": now_iso,
                "notes": "WingPoint connect signup — must subscribe for access",
                "source": "wingpoint",
                "wingpoint_ref": wp_ref,
            }
        },
        upsert=True,
    )

    # Onboarding checklist (same shape the provision path writes).
    await db.user_onboarding.update_one(
        {"user_id": user_id},
        {
            "$setOnInsert": {
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
                "created_at": now_iso,
                "updated_at": now_iso,
            }
        },
        upsert=True,
    )

    # Attach the trust: if a trust already carries this wingpoint_ref, re-link
    # it to the new account. Otherwise WingPoint links it after the connect
    # confirm (the /external/link-trust path) using the authenticated user_id.
    attached_trust = await _attach_trust_for_ref(wp_ref, user_id, now)

    logger.info(
        f"WingPoint connect signup: user_id={user_id} app_id={app_id} "
        f"wp_ref={wp_ref} trust_attached={bool(attached_trust)} "
        f"email={_normalize_email_for_log(email)}"
    )

    await log_audit_event(
        user_id,
        "wingpoint_connect_signup",
        "user",
        user_id,
        {"wp_ref": wp_ref, "app_id": app_id, "trust_attached": bool(attached_trust)},
    )

    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0}) or user_doc
    return await _issue_session(user_doc, response)


# ==================== INTERNAL HELPERS ====================

async def _attach_trust_for_ref(
    wp_ref: str, user_id: str, now: datetime,
) -> Optional[str]:
    """Re-link an existing trust for this wingpoint_ref to the given user."""
    try:
        existing = await db.trusts.find_one(
            {"wingpoint_ref": wp_ref}, {"trust_id": 1, "user_id": 1, "_id": 0}
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"WingPoint connect trust lookup failed for wp_ref={wp_ref}: {exc}")
        return None

    if not existing:
        return None

    if existing.get("user_id") != user_id:
        await db.trusts.update_one(
            {"trust_id": existing["trust_id"]},
            {"$set": {"user_id": user_id, "updated_at": now.isoformat()}},
        )
        logger.info(
            f"WingPoint connect: trust {existing['trust_id']} re-linked to new account"
        )
    return existing["trust_id"]


async def _store_claim_code(email: str, user_id: str, code: str) -> None:
    """Persist the verification code (hashed) for the account-claim flow."""
    now = datetime.now(timezone.utc)
    await db.wingpoint_connect_codes.update_one(
        {"email": email},
        {
            "$set": {
                "email": email,
                "user_id": user_id,
                "code_hash": _hash_claim_code(email, code),
                "attempts": 0,
                "created_at": now.isoformat(),
                "expires_at": (now + timedelta(minutes=CLAIM_CODE_TTL_MINUTES)).isoformat(),
            }
        },
        upsert=True,
    )


def _hash_claim_code(email: str, code: str) -> str:
    return hmac.new(
        CONNECT_CONTEXT_SALT.encode("utf-8"),
        f"{email}:{code}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


async def _consume_claim_code(email: str, code: str) -> bool:
    """Verify + burn a claim code. False on mismatch, expiry, or exhaustion."""
    record = await db.wingpoint_connect_codes.find_one({"email": email})
    if not record:
        return False

    expires_at = record.get("expires_at")
    if expires_at:
        try:
            expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
        except Exception:
            expiry = datetime.now(timezone.utc)
        if expiry < datetime.now(timezone.utc):
            await db.wingpoint_connect_codes.delete_one({"email": email})
            return False

    attempts = int(record.get("attempts") or 0)
    if attempts >= CLAIM_CODE_MAX_ATTEMPTS:
        await db.wingpoint_connect_codes.delete_one({"email": email})
        return False

    expected = record.get("code_hash") or ""
    if not hmac.compare_digest(expected, _hash_claim_code(email, code)):
        await db.wingpoint_connect_codes.update_one(
            {"email": email}, {"$inc": {"attempts": 1}}
        )
        return False

    await db.wingpoint_connect_codes.delete_one({"email": email})
    return True


async def _issue_session(user_doc: dict, response: Response) -> dict:
    """Mint the session (access + refresh token) and set the auth cookies."""
    user_id = user_doc["user_id"]
    email = user_doc["email"]
    token = create_jwt_token(user_id, email)
    refresh_raw = await create_refresh_token_record(user_id)

    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRATION_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_raw,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRATION_DAYS * 24 * 3600,
        path="/api/auth",
    )

    return {
        "token": token,
        "user": {
            "user_id": user_id,
            "email": email,
            "name": user_doc.get("name"),
            "is_admin": bool(user_doc.get("is_admin")),
            "wp_ref": user_doc.get("wp_ref"),
            "is_wingpoint": is_wingpoint_user(user_doc),
        },
    }
