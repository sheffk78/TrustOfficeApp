"""
Frontend error reporting router.

Exposes POST /api/report-error so the TrustOffice frontend can report
client-side errors (uncaught exceptions, failed critical API calls, failed
trust document uploads, etc.) back to the backend. The backend logs the error
with full context and fires a deduped Discord alert via error_alerting.

The endpoint is auth-optional: if a valid session token is present, we
extract user context (user_id, email, trust_id) and include it in the alert.
If no token is present (e.g. error on the login page), we still report the
error but without user context.

Rate limiting: each client (identified by IP) can report at most 20 errors per
5-minute window. This prevents a runaway client from flooding Discord while
still letting real user-facing failures through. The per-fingerprint dedupe
in error_alerting.report_error is the second layer of protection.
"""
from __future__ import annotations

import time
import logging
from collections import defaultdict, deque
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from error_alerting import report_error

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/report-error", tags=["error-reporting"])

# ---------------------------------------------------------------------------
# Per-IP rate limiting
# ---------------------------------------------------------------------------

_RATE_LIMIT_WINDOW = 300  # 5 minutes
_RATE_LIMIT_MAX = 20  # max reports per window per IP
_ip_buckets: Dict[str, deque] = defaultdict(deque)


def _is_rate_limited(ip: str) -> bool:
    """Return True if the IP has exceeded the per-IP rate limit."""
    now = time.time()
    bucket = _ip_buckets[ip]
    # Drop timestamps outside the window
    cutoff = now - _RATE_LIMIT_WINDOW
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if len(bucket) >= _RATE_LIMIT_MAX:
        return True
    bucket.append(now)
    return False


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class FrontendErrorReport(BaseModel):
    """Payload the frontend sends when a critical operation fails."""

    # Short category label, e.g. "uncaught_exception", "api_failure",
    # "trust_upload_failed", "payment_error"
    error_type: str = Field(..., max_length=200)

    # Human-readable error message
    message: str = Field(..., max_length=2000)

    # The page/route or component where the error occurred
    location: Optional[str] = Field(None, max_length=500)

    # The failing operation, e.g. "POST /api/trusts", "fetch /api/vault/upload"
    failing_operation: Optional[str] = Field(None, max_length=500)

    # Client-side stack trace
    stack: Optional[str] = Field(None, max_length=4000)

    # Browser/user-agent string
    user_agent: Optional[str] = Field(None, max_length=500)

    # Optional trust_id if the error happened in a trust context
    trust_id: Optional[str] = Field(None, max_length=100)

    # Free-form extra context (component name, form data, etc.)
    context: Optional[Dict[str, Any]] = Field(None)

    @field_validator("error_type")
    @classmethod
    def validate_error_type(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("error_type is required")
        return v

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message is required")
        return v


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("", status_code=200)
async def report_frontend_error(payload: FrontendErrorReport, request: Request):
    """Report a frontend error. Returns 200 on success (even if alerting was
    deduped or failed) so the frontend doesn't retry indefinitely.

    The endpoint is auth-optional: user context is extracted from the session
    token if present, but unauthenticated reports (e.g. errors on the login
    page) are still accepted.
    """
    client_ip = request.client.host if request.client else "unknown"

    # --- Per-IP rate limit ---
    if _is_rate_limited(client_ip):
        logger.warning(
            f"Frontend error report rate-limited for IP {client_ip}: "
            f"{payload.error_type}: {payload.message[:100]}"
        )
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many error reports. Please try again later."},
        )

    # --- Best-effort user context extraction from JWT (no DB hit) ---
    user_id: Optional[str] = None
    email: Optional[str] = None

    # Try to decode the session token to enrich the alert
    try:
        import os
        import jwt as _jwt

        token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
        else:
            token = request.cookies.get("session_token")

        if token:
            jwt_secret = os.environ.get("JWT_SECRET")
            if jwt_secret:
                decoded = _jwt.decode(
                    token, jwt_secret, algorithms=["HS256"]
                )
                user_id = decoded.get("user_id")
                email = decoded.get("email")
    except Exception:
        pass  # No token or invalid token — still report the error anonymously

    # Use trust_id from payload if provided, otherwise try path/query params
    trust_id = (
        payload.trust_id
        or request.path_params.get("trust_id")
        or request.query_params.get("trust_id")
    )

    # --- Build extra context for the alert ---
    extra_context: Dict[str, Any] = {}
    if payload.location:
        extra_context["location"] = payload.location
    if payload.failing_operation:
        extra_context["operation"] = payload.failing_operation
    if payload.user_agent:
        extra_context["user_agent"] = payload.user_agent
    if payload.context:
        # Merge caller-supplied context, capping each value length
        for k, v in payload.context.items():
            v_str = str(v)
            extra_context[k] = v_str[:400] if len(v_str) > 400 else v_str

    # --- Report the error (logs + deduped Discord alert) ---
    await report_error(
        source="frontend",
        error_type=payload.error_type,
        error_message=payload.message,
        traceback_str=payload.stack,
        request_path=payload.failing_operation or payload.location,
        user_id=user_id,
        email=email,
        trust_id=trust_id,
        extra_context=extra_context,
    )

    return {"status": "reported", "support": "contact@trustoffice.app"}