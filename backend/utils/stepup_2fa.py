"""
Step-up 2FA dependency for sensitive actions (vault download, successor-grant
creation).

Contract: when the requesting user has 2FA ENABLED, these routes require a
valid current TOTP code in the `X-2FA-Code` header. Missing/invalid ->
403 {"detail": "2fa_stepup_required"} so the frontend can prompt and retry.
Users WITHOUT 2FA enabled are completely unaffected.

SECURITY NOTE: the header value (a TOTP code) is NEVER logged — not in
security_events, not in any log line. Event type + outcome only
(council review delta 2026-09-12).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException, Request

from database import db
from services import totp_service as totps
from services.security_events import record_security_event

logger = logging.getLogger(__name__)

STEPUP_HEADER = "X-2FA-Code"
STEPUP_DETAIL = "2fa_stepup_required"


def _client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else None


async def require_2fa_stepup(request: Request, user: dict) -> dict:
    """FastAPI dependency enforcing step-up 2FA on sensitive routes.

    Usage:
        user: dict = Depends(get_current_user),
        _stepup: None = Depends(require_2fa_stepup),

    (get_current_user must also be declared so `user` resolves; this
    dependency re-fetches nothing — it receives the same user dict.)
    """
    if not totps.is_2fa_enabled(user):
        return user

    code = request.headers.get(STEPUP_HEADER, "")
    if code and totps.verify_stepup_code(user, code):
        totps.clear_totp_failures(user["user_id"])
        return user

    # Failed or missing step-up — security event (NO code value logged).
    try:
        await record_security_event(
            user["user_id"], "2fa_stepup_failed",
            ip=_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
            details={"path": request.url.path, "reason": "missing" if not code else "invalid"},
        )
    except Exception as exc:
        logger.warning(f"2FA stepup security event failed (non-fatal): {exc}")

    raise HTTPException(status_code=403, detail=STEPUP_DETAIL)