"""
TOTP two-factor authentication router — mounts under /auth/2fa/.

Endpoints (API CONTRACT — frontend builds against exactly this):
  POST /auth/2fa/enroll   {password}            -> {secret, provisioning_uri}
       (auth required + password re-auth: a hijacked session cannot enroll
        an attacker's own device)
  POST /auth/2fa/verify   {code}                -> {recovery_codes: [10 codes]}
       (activates 2FA; recovery codes bcrypt-hashed at rest, plaintext shown
        exactly once)
  POST /auth/2fa/disable  {totp_code, password} -> {message}
       (requires BOTH a current TOTP code and the account password)
  GET  /auth/2fa/status                         -> {enabled, recovery_codes_remaining, enforced}
       (enforced=true for admin accounts)
  POST /auth/2fa/login    {challenge_token, code} -> normal session response
       (validates TOTP or a single-use recovery code)

Security events: enroll / verify / disable / recovery-code use / failed TOTP
attempts all write to security_events + anomaly alerting. NEVER log the
X-2FA-Code value or any TOTP code — event type + outcome only.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from database import db
from dependencies import (
    ACCESS_TOKEN_EXPIRATION_MINUTES,
    REFRESH_TOKEN_EXPIRATION_DAYS,
    create_jwt_token,
    create_refresh_token_record,
    get_current_user,
    verify_password,
)
from services.security_events import check_security_alert, record_security_event
from services import totp_service as totps
from utils.audit import log_audit_event

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth-2fa"])


# ==================== REQUEST MODELS ====================

class EnrollRequest(BaseModel):
    password: str


class VerifyRequest(BaseModel):
    code: str


class DisableRequest(BaseModel):
    totp_code: str
    password: str


class TwoFactorLoginRequest(BaseModel):
    challenge_token: str
    code: str


# ==================== SHARED HELPERS ====================

def _client_ip(request: Request) -> Optional[str]:
    """Best-effort client IP honoring X-Forwarded-For for proxied requests."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else None


async def _sec_event(user_id: Optional[str], event_type: str, request: Request,
                     details: Optional[dict] = None) -> None:
    """Best-effort security event — never breaks the request path."""
    try:
        await record_security_event(
            user_id, event_type,
            ip=_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
            details=details or {},
        )
    except Exception as exc:  # pragma: no cover
        logger.warning(f"2FA security event '{event_type}' logging failed (non-fatal): {exc}")


# ==================== 1. ENROLL ====================

@router.post("/auth/2fa/enroll")
async def enroll(request: Request, body: EnrollRequest, user: dict = Depends(get_current_user)):
    """Start 2FA enrollment: requires password re-auth, then generates a
    per-user TOTP secret + provisioning URI. Not active until /verify."""
    if not user.get("password_hash"):
        raise HTTPException(status_code=400, detail="This account has no password set. Set a password first, then enable 2FA.")
    if not verify_password(body.password, user["password_hash"]):
        await _sec_event(user["user_id"], "2fa_enroll_failed", request, {"reason": "wrong_password"})
        raise HTTPException(status_code=401, detail="Incorrect password. 2FA enrollment requires your account password.")

    secret = totps.generate_totp_secret()
    provisioning_uri = totps.build_provisioning_uri(secret, user.get("email", ""))

    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "totp.enrollment_secret": secret,
            "totp.created_at": datetime.now(timezone.utc).isoformat(),
            "totp.enabled": False,
        }},
    )

    await _sec_event(user["user_id"], "2fa_enroll_started", request)
    await log_audit_event(user["user_id"], "2fa_enroll_started", "user", user["user_id"], {})

    return {"secret": secret, "provisioning_uri": provisioning_uri}


# ==================== 2. VERIFY / ACTIVATE ====================

@router.post("/auth/2fa/verify")
async def verify_enrollment(request: Request, body: VerifyRequest, user: dict = Depends(get_current_user)):
    """Activate 2FA by confirming a code from the enrolled authenticator.
    Returns 10 single-use recovery codes — plaintext shown exactly once."""
    state = totps.get_totp_state(user)
    secret = state.get("enrollment_secret") or state.get("secret")

    if state.get("enabled"):
        raise HTTPException(status_code=400, detail="Two-factor authentication is already enabled on this account.")
    if not secret:
        raise HTTPException(status_code=400, detail="No 2FA enrollment in progress. Start enrollment first.")

    if not totps.verify_totp_code(secret, body.code):
        totps.record_totp_failure(user["user_id"])
        await _sec_event(user["user_id"], "2fa_verify_failed", request)
        err_body = totps.build_invalid_code_body(user["user_id"])
        raise HTTPException(status_code=401, detail=err_body)

    recovery_plain, recovery_hashed = totps.generate_recovery_codes()

    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "totp.enabled": True,
            "totp.secret": secret,
            "totp.recovery_codes": recovery_hashed,
            "totp.verified_at": datetime.now(timezone.utc).isoformat(),
        },
         "$unset": {"totp.enrollment_secret": ""}},
    )

    await _sec_event(user["user_id"], "2fa_activated", request)
    await log_audit_event(user["user_id"], "2fa_activated", "user", user["user_id"], {})
    totps.clear_totp_failures(user["user_id"])

    return {"recovery_codes": recovery_plain}


# ==================== 3. DISABLE ====================

@router.post("/auth/2fa/disable")
async def disable(request: Request, body: DisableRequest, user: dict = Depends(get_current_user)):
    """Disable 2FA: requires BOTH a current TOTP code AND the account password."""
    state = totps.get_totp_state(user)
    if not state.get("enabled"):
        raise HTTPException(status_code=400, detail="Two-factor authentication is not enabled on this account.")

    if user.get("password_hash") and not verify_password(body.password, user["password_hash"]):
        await _sec_event(user["user_id"], "2fa_disable_failed", request, {"reason": "wrong_password"})
        raise HTTPException(status_code=401, detail="Incorrect password.")

    if not totps.verify_totp_code(state.get("secret"), body.totp_code):
        totps.record_totp_failure(user["user_id"])
        await _sec_event(user["user_id"], "2fa_disable_failed", request, {"reason": "invalid_totp_code"})
        err_body = totps.build_invalid_code_body(user["user_id"])
        raise HTTPException(status_code=401, detail=err_body)

    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "totp.enabled": False,
            "totp.disabled_at": datetime.now(timezone.utc).isoformat(),
        },
         "$unset": {"totp.secret": "", "totp.recovery_codes": "", "totp.enrollment_secret": ""}},
    )

    await _sec_event(user["user_id"], "2fa_disabled", request)
    await log_audit_event(user["user_id"], "2fa_disabled", "user", user["user_id"], {})
    totps.clear_totp_failures(user["user_id"])

    return {"message": "Two-factor authentication has been disabled."}


# ==================== 4. STATUS ====================

@router.get("/auth/2fa/status")
async def status(request: Request, user: dict = Depends(get_current_user)):
    """2FA state for the Settings page."""
    state = totps.get_totp_state(user)
    return {
        "enabled": bool(state.get("enabled")),
        "recovery_codes_remaining": totps.count_unused_recovery_codes(user),
        "enforced": totps.is_admin_user(user),
    }


# ==================== 5. 2FA LOGIN STEP ====================

def _build_login_payload(user_doc: dict, token: str):
    """Normal session response shape (matches POST /auth/login)."""
    PRIMARY_ADMIN_EMAIL = "contact@trustoffice.app"
    email_norm = (user_doc.get("email") or "").lower()
    is_admin = bool(user_doc.get("is_admin")) or email_norm == PRIMARY_ADMIN_EMAIL
    is_wingpoint = bool(
        user_doc.get("wp_ref")
        or user_doc.get("source") == "wingpoint"
        or user_doc.get("created_via") == "wingpoint_provision"
    )
    return {
        "token": token,
        "user": {
            "user_id": user_doc["user_id"],
            "email": user_doc.get("email"),
            "name": user_doc.get("name"),
            "picture": user_doc.get("picture"),
            "is_admin": is_admin,
            "is_stats_user": user_doc.get("is_stats_user", False),
            "is_leads_user": user_doc.get("is_leads_user", False),
            "wp_ref": user_doc.get("wp_ref"),
            "is_wingpoint": is_wingpoint,
        },
    }


@router.post("/auth/2fa/login")
async def login_2fa(request: Request, body: TwoFactorLoginRequest, response: Response):
    """Second login step: validate a TOTP or single-use recovery code against
    a short-lived challenge token, then issue the normal session response."""
    challenge = totps.verify_challenge_token(body.challenge_token)
    if not challenge:
        # Never log the token or code value — outcome only.
        await _sec_event(None, "2fa_login_failed", request, {"reason": "invalid_or_expired_challenge"})
        raise HTTPException(status_code=401, detail="Your two-factor session expired. Please sign in again.")

    user_id = challenge["user_id"]
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=401, detail="Your two-factor session expired. Please sign in again.")

    state = totps.get_totp_state(user_doc)
    if not state.get("enabled"):
        raise HTTPException(status_code=401, detail="Two-factor authentication is not enabled. Please sign in again.")

    if totps.is_totp_rate_limited(user_id):
        await _sec_event(user_id, "2fa_login_rate_limited", request)
        err_body = totps.build_rate_limited_body(user_id)
        raise HTTPException(status_code=429, detail=err_body)

    ok, method = await totps.consume_login_code(user_doc, body.code)
    if not ok:
        if method == "rate_limited":
            await _sec_event(user_id, "2fa_login_rate_limited", request)
            err_body = totps.build_rate_limited_body(user_id)
            raise HTTPException(status_code=429, detail=err_body)
        fail_count = totps.record_totp_failure(user_id)
        await _sec_event(user_id, "2fa_login_failed", request, {
            "reason": method,  # 'invalid' | 'recovery_code' (race) â never the code itself
            "attempt_count_in_window": fail_count,
        })
        try:
            await check_security_alert("2fa_login_failed", user_id=user_id, email=user_doc.get("email", ""))
        except Exception as exc:
            logger.warning(f"2FA anomaly alert check failed (non-fatal): {exc}")
        err_body = totps.build_invalid_code_body(user_id)
        raise HTTPException(status_code=401, detail=err_body)

    # Success: issue the normal session (same shape as POST /auth/login).
    token = create_jwt_token(user_doc["user_id"], user_doc["email"])
    refresh_raw = await create_refresh_token_record(user_doc["user_id"])

    now_iso = datetime.now(timezone.utc).isoformat()
    await db.users.update_one(
        {"user_id": user_doc["user_id"]},
        {"$set": {"last_login": now_iso}},
    )
    await log_audit_event(user_doc["user_id"], "login", "user", user_doc["user_id"],
                          {"email": user_doc.get("email"), "method": f"2fa_{method}"})
    await _sec_event(user_doc["user_id"], "login_success", request, {"method": f"2fa_{method}"})
    if method == "recovery_code":
        # Recovery-code use is a security event (lost-device path in action).
        await _sec_event(user_doc["user_id"], "2fa_recovery_code_used", request)
        await log_audit_event(user_doc["user_id"], "2fa_recovery_code_used", "user", user_doc["user_id"], {})

    # Access token cookie (30-min, httponly)
    response.set_cookie(
        key="session_token", value=token, httponly=True, secure=True,
        samesite="lax", max_age=ACCESS_TOKEN_EXPIRATION_MINUTES * 60, path="/",
    )
    # Refresh token cookie (30d, httponly, secure, samesite=lax, scoped to /auth)
    response.set_cookie(
        key="refresh_token", value=refresh_raw, httponly=True, secure=True,
        samesite="lax", max_age=REFRESH_TOKEN_EXPIRATION_DAYS * 24 * 3600, path="/auth",
    )

    payload = _build_login_payload(user_doc, token)
    # Admin enforcement: nag (never lock out) — enrolled admins skip this.
    if payload["user"]["is_admin"] and not state.get("enabled"):
        payload["needs_2fa_enrollment"] = True
    return payload
