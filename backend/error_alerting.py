"""
Global error alerting service for TrustOffice backend.

Provides:
- `report_error(...)`: async function that logs an error with full context and
  sends a Discord alert via `discord_service.notify_alert`.
- A simple in-memory dedupe cache so identical errors (same fingerprint) are
  only alerted once within a 5-minute window. This prevents Discord spam when
  a route is failing on every request.

The fingerprint is built from the error type + the request path + the first
line of the traceback, which is usually enough to group identical failures
without merging unrelated ones.

Usage from server.py:

    from error_alerting import report_error, ErrorReporter
    ...
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        return await ErrorReporter.handle_uncaught(request, exc)

Frontend errors are reported via the /api/report-error endpoint (see
routers/error_reports.py), which calls `report_error` with the client payload.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, TYPE_CHECKING

import httpx

from discord_service import notify_alert
from database import db

if TYPE_CHECKING:
    # Import only for type-checking to avoid pulling FastAPI/Starlette into
    # module import time for callers that only need `report_error`.
    from starlette.requests import Request
    from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate-limiting / dedupe
# ---------------------------------------------------------------------------

# Fingerprints of recently-alerted errors -> last alerted unix timestamp.
# We keep this in-process; restarts reset it, which is fine: a restart is
# itself a signal that the error stream has stopped, and we want fresh alerts
# after a deploy.
_ALERT_CACHE: Dict[str, float] = {}
_DEDUPE_WINDOW_SECONDS = 300  # 5 minutes

# Cap the cache size so a runaway loop with unique messages can't grow it
# unbounded. After this many distinct fingerprints we start evicting the
# oldest entries.
_MAX_CACHE_SIZE = 1024


def _prune_cache() -> None:
    """Drop entries older than the dedupe window; enforce size cap."""
    now = time.time()
    cutoff = now - _DEDUPE_WINDOW_SECONDS
    # Drop expired entries
    expired = [k for k, ts in _ALERT_CACHE.items() if ts < cutoff]
    for k in expired:
        del _ALERT_CACHE[k]
    # If still too big, evict the oldest by timestamp
    if len(_ALERT_CACHE) > _MAX_CACHE_SIZE:
        # Sort by timestamp ascending and drop the oldest surplus
        sorted_items = sorted(_ALERT_CACHE.items(), key=lambda kv: kv[1])
        for k, _ in sorted_items[: len(_ALERT_CACHE) - _MAX_CACHE_SIZE]:
            del _ALERT_CACHE[k]


def _fingerprint(error_type: str, path: str, tb_first_line: str) -> str:
    """Build a stable fingerprint for dedupe. Returns a hex digest."""
    raw = f"{error_type}|{path}|{tb_first_line}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _is_duplicate(fingerprint: str) -> bool:
    """Return True if this fingerprint was alerted within the dedupe window."""
    now = time.time()
    last = _ALERT_CACHE.get(fingerprint)
    if last is not None and (now - last) < _DEDUPE_WINDOW_SECONDS:
        return True
    _ALERT_CACHE[fingerprint] = now
    _prune_cache()
    return False


# ---------------------------------------------------------------------------
# Stale-bundle detection
# ---------------------------------------------------------------------------

# The current deployed frontend bundle hash. Set via env var so Railway can
# inject it at deploy time. When set, frontend errors with a different bundle
# hash in their stack trace are silently suppressed (the user's browser is
# caching an old JS bundle — the fix is already live, they just need a refresh).
_CURRENT_BUNDLE_HASH = os.environ.get("FRONTEND_BUNDLE_HASH", "").strip()

import re as _re
_BUNDLE_HASH_RE = _re.compile(r"main\.([a-f0-9]+)\.js")


def _extract_bundle_hash(stack_trace: str) -> str:
    """Extract the frontend bundle hash from a stack trace, if present."""
    if not stack_trace:
        return ""
    m = _BUNDLE_HASH_RE.search(stack_trace)
    return m.group(1) if m else ""


def _is_stale_bundle(stack_trace: str) -> bool:
    """True if the error came from an old (non-current) frontend bundle."""
    if not _CURRENT_BUNDLE_HASH:
        return False  # Can't determine — don't suppress
    bundle = _extract_bundle_hash(stack_trace)
    if not bundle:
        return False  # No bundle hash in stack — server error or non-JS error
    return bundle != _CURRENT_BUNDLE_HASH


# ---------------------------------------------------------------------------
# Hermes webhook trigger (autonomous agent)
# ---------------------------------------------------------------------------

_HERMES_WEBHOOK_URL = os.environ.get(
    "HERMES_WEBHOOK_URL",
    "https://to-hook.agentictrust.app/webhooks/trustoffice-error",
).strip()
_HERMES_WEBHOOK_SECRET = os.environ.get(
    "HERMES_WEBHOOK_SECRET",
    "to-err-webhook-2026",
).strip()


def _build_hermes_payload(
    *,
    source: str,
    error_type: str,
    error_message: str,
    traceback_str: Optional[str],
    request_path: Optional[str],
    user_id: Optional[str],
    fingerprint: str,
    bundle_hash: str,
    extra_context: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build the JSON payload for the Hermes webhook."""
    _ctx = extra_context or {}
    return {
        "error_type": error_type,
        "error_message": error_message[:1000] if error_message else "",
        "location": request_path or _ctx.get("location") or "",
        "failing_operation": _ctx.get("operation") or error_type,
        "stack": (traceback_str or "")[:3000],
        "fingerprint": fingerprint,
        "bundle_hash": bundle_hash,
        "user_id": user_id or "None",
        "source": source,
    }


def _compute_hmac_signature(payload_bytes: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 signature for the webhook payload."""
    import hmac as _hmac
    return _hmac.new(
        secret.encode("utf-8"), payload_bytes, hashlib.sha256
    ).hexdigest()


async def _trigger_hermes_agent(payload: Dict[str, Any]) -> bool:
    """POST to the Hermes webhook to trigger an autonomous agent run.

    Returns True if the webhook was called successfully, False on any failure.
    Never raises — webhook failure must not crash the request path.
    """
    if not _HERMES_WEBHOOK_URL:
        return False
    try:
        payload_bytes = json.dumps(payload).encode("utf-8")
        signature = _compute_hmac_signature(payload_bytes, _HERMES_WEBHOOK_SECRET)
        headers = {
            "Content-Type": "application/json",
            "X-Hermes-Signature": f"sha256={signature}",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _HERMES_WEBHOOK_URL, content=payload_bytes, headers=headers
            )
        return resp.status_code in (200, 202)
    except Exception as exc:
        logger.warning(f"Failed to trigger Hermes webhook: {exc}")
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# TrustOffice brand color for error alerts (rust red, matches discord_service)
ERROR_COLOR = 0xB44040


async def report_error(
    *,
    source: str,
    error_type: str,
    error_message: str,
    traceback_str: Optional[str] = None,
    request_path: Optional[str] = None,
    request_method: Optional[str] = None,
    user_id: Optional[str] = None,
    email: Optional[str] = None,
    trust_id: Optional[str] = None,
    extra_context: Optional[Dict[str, Any]] = None,
    alert: bool = True,
) -> Dict[str, Any]:
    """Report an error: log it with full context and (optionally) alert Discord.

    Parameters
    ----------
    source : str
        Where the error originated: "server", "frontend", "background", etc.
    error_type : str
        Exception class name or a short category label for frontend errors.
    error_message : str
        Human-readable error message.
    traceback_str : str, optional
        Full traceback text. Truncated to 1500 chars for the Discord embed.
    request_path : str, optional
        API path that failed, for server errors. For frontend errors, the
        page/route where the error occurred.
    request_method : str, optional
        HTTP method (server errors only).
    user_id, email, trust_id : str, optional
        User context when available. Included in the alert so we can look up
        the affected user.
    extra_context : dict, optional
        Additional key/value context (e.g. browser, component name, stack).
    alert : bool
        If False, only log — don't send to Discord. Used by callers that want
        to suppress alerts for known-acceptable failures.

    Returns
    -------
    dict
        ``{"alerted": bool, "duplicate": bool, "fingerprint": str}``.
        ``alerted`` is False when the error was deduped or Discord isn't
        configured; ``duplicate`` is True when deduped.
    """
    # --- Build the fingerprint for dedupe ---
    # Suppress Discord paging for known browser-extension / crawler noise that
    # ships up from the frontend (unhandled promise rejections from content
    # scripts, ad-blockers, Googlebot/scanners). Defensive net behind the
    # frontend filter in errors.js — still logged (server log below), but never
    # a real-time page. Only applies to frontend reports; server errors always
    # alert.
    _NOISE_PATTERNS = (
        "loading script",
        "runtime.sendMessage",
        "Extension context invalidated",
        "not a registered extension",
        "Script error.",
        "content script",
        "adblock",
        "webRequest",
    )
    if source == "frontend" and error_message:
        msg_lower = error_message.lower()
        if any(p.lower() in msg_lower for p in _NOISE_PATTERNS):
            alert = False
    tb_first_line = ""
    if traceback_str:
        # First non-empty line of the traceback is the most identifying piece
        for line in traceback_str.splitlines():
            if line.strip():
                tb_first_line = line.strip()
                break
    fp = _fingerprint(error_type, request_path or "", tb_first_line)

    # --- Log with full context (always, even if deduped) ---
    log_lines = [
        f"[{source}] {error_type}: {error_message}",
    ]
    if request_method and request_path:
        log_lines.append(f"  request: {request_method} {request_path}")
    if user_id:
        log_lines.append(f"  user_id: {user_id}")
    if email:
        log_lines.append(f"  email: {email}")
    if trust_id:
        log_lines.append(f"  trust_id: {trust_id}")
    if extra_context:
        for k, v in extra_context.items():
            log_lines.append(f"  {k}: {v}")
    if traceback_str:
        log_lines.append("  traceback:\n" + traceback_str)

    full_log = "\n".join(log_lines)
    logger.error(full_log)

    # --- Store in MongoDB error_logs (single source of truth) ---
    # Every report_error() call writes to error_logs so the orchestrator can
    # poll it.  Deduped errors still get stored (with resolved=False) so the
    # loop sees them; the dedupe below only gates the Discord alert.
    _ctx = extra_context or {}
    error_doc = {
        "error_id": f"err_{uuid.uuid4().hex[:12]}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "error_type": (error_type or "unknown")[:200],
        "error_message": (error_message or "")[:4000],
        "stack_trace": (traceback_str or "")[:8000] if traceback_str else None,
        "url": (_ctx.get("location") or request_path or "")[:1000] or None,
        "user_agent": (_ctx.get("user_agent") or "")[:500] or None,
        "component_stack": (_ctx.get("component_stack") or "")[:4000] or None,
        "boundary": False,
        "metadata": {
            "source": source,
            "fingerprint": fp,
            "operation": _ctx.get("operation"),
            **{k: v for k, v in _ctx.items() if k not in ("location", "user_agent", "operation")},
        },
        "resolved": False,
        "ip_address": None,
    }
    try:
        await db.error_logs.insert_one(error_doc)
    except Exception as store_exc:
        logger.warning(f"Failed to store error in MongoDB: {store_exc}")

    # --- Dedupe check ---
    if _is_duplicate(fp):
        logger.debug(f"Suppressed duplicate Discord alert (fingerprint={fp[:8]})")
        return {"alerted": False, "duplicate": True, "fingerprint": fp}

    # --- Send Discord alert ---
    if not alert:
        return {"alerted": False, "duplicate": False, "fingerprint": fp}

    # Build a readable message for the Discord embed
    parts: list[str] = []
    if request_method and request_path:
        parts.append(f"**Request:** `{request_method} {request_path}`")
    elif request_path:
        parts.append(f"**Path:** `{request_path}`")
    parts.append(f"**Error:** `{error_type}: {error_message[:500]}`")

    user_parts: list[str] = []
    if user_id:
        user_parts.append(f"user_id: `{user_id}`")
    if email:
        user_parts.append(f"email: `{email}`")
    if trust_id:
        user_parts.append(f"trust_id: `{trust_id}`")
    if user_parts:
        parts.append("**User:** " + " | ".join(user_parts))

    if extra_context:
        ctx_lines = []
        for k, v in extra_context.items():
            # Truncate long values so the embed doesn't exceed Discord limits
            v_str = str(v)
            if len(v_str) > 400:
                v_str = v_str[:400] + "…"
            ctx_lines.append(f"- {k}: {v_str}")
        if ctx_lines:
            parts.append("**Context:**\n" + "\n".join(ctx_lines))

    if traceback_str:
        # Discord embed description has a 4096-char limit; be conservative
        tb_excerpt = traceback_str[:1500]
        if len(traceback_str) > 1500:
            tb_excerpt += "\n… (truncated)"
        parts.append(f"**Traceback:**\n```\n{tb_excerpt}\n```")

    title_prefix = "🚨 Server Error" if source == "server" else "⚠️ Frontend Error"
    title = f"{title_prefix}: {error_type}"

    # --- Trigger autonomous agent or send Discord alert ---
    # Extract bundle hash for stale-bundle detection
    bundle_hash = _extract_bundle_hash(traceback_str or "")

    # Suppress alerts for stale-bundle errors (user's browser is caching old JS)
    if source == "frontend" and _is_stale_bundle(traceback_str or ""):
        logger.info(f"Suppressed stale-bundle error (bundle={bundle_hash}, current={_CURRENT_BUNDLE_HASH})")
        return {"alerted": False, "duplicate": False, "fingerprint": fp, "stale_bundle": True}

    # Trigger Hermes autonomous agent for real errors (no Discord ping needed)
    if alert and source in ("server", "frontend"):
        hermes_payload = _build_hermes_payload(
            source=source,
            error_type=error_type,
            error_message=error_message,
            traceback_str=traceback_str,
            request_path=request_path,
            user_id=user_id,
            fingerprint=fp,
            bundle_hash=bundle_hash,
            extra_context=extra_context,
        )
        # Fire-and-forget — don't block the response on the webhook call
        triggered = await _trigger_hermes_agent(hermes_payload)
        if triggered:
            # Still send a silent Discord log (no @Kit ping) for visibility
            try:
                await notify_alert(
                    title=title,
                    message="\n".join(parts),
                    color=ERROR_COLOR,
                    ping_kit=False,
                )
            except Exception:
                pass  # Discord is secondary — the webhook is primary
            return {"alerted": True, "duplicate": False, "fingerprint": fp, "hermes_triggered": True}
        # If webhook failed, fall through to Discord alert with ping as fallback
        logger.warning("Hermes webhook failed — falling back to Discord ping")

    # Fallback: Discord alert (with Kit ping if it's a real error)
    should_ping_kit = alert and source in ("server", "frontend")

    try:
        await notify_alert(
            title=title,
            message="\n".join(parts),
            color=ERROR_COLOR,
            ping_kit=should_ping_kit,
        )
        return {"alerted": True, "duplicate": False, "fingerprint": fp}
    except Exception as exc:
        # Never let alerting failure crash the request path
        logger.error(f"Failed to send Discord alert: {exc}", exc_info=True)
        return {"alerted": False, "duplicate": False, "fingerprint": fp, "alert_error": str(exc)}


# ---------------------------------------------------------------------------
# Helper for the FastAPI exception handler
# ---------------------------------------------------------------------------


class ErrorReporter:
    """Convenience wrappers for common error-reporting call sites."""

    @staticmethod
    async def handle_uncaught(request: Request, exc: Exception) -> "JSONResponse":
        """
        Global exception handler for uncaught server errors.

        Extracts user context from the JWT (if present and decodable without
        hitting the DB), logs the full error, fires a deduped Discord alert,
        and returns a generic 500 so we never leak internal details to the
        client.

        Intended to be registered as::

            @app.exception_handler(Exception)
            async def global_exception_handler(request, exc):
                return await ErrorReporter.handle_uncaught(request, exc)
        """
        import jwt as _jwt
        import os as _os

        # Defaults
        user_id: Optional[str] = None
        email: Optional[str] = None
        trust_id: Optional[str] = None

        # Try to extract user context from the token WITHOUT requiring the
        # database. This is best-effort: if the token is missing/invalid we
        # just log the error with no user context.
        token = _extract_token(request)
        if token:
            jwt_secret = _os.environ.get("JWT_SECRET")
            jwt_algorithm = "HS256"
            if jwt_secret:
                try:
                    payload = _jwt.decode(
                        token, jwt_secret, algorithms=[jwt_algorithm]
                    )
                    user_id = payload.get("user_id")
                    email = payload.get("email")
                except Exception:
                    pass  # Token invalid/expired — no user context

        # Trust ID may be in path params or query
        trust_id = (
            request.path_params.get("trust_id")
            if hasattr(request, "path_params")
            else None
        ) or request.query_params.get("trust_id")

        error_type = type(exc).__name__
        error_message = str(exc)
        tb_str = traceback.format_exc()

        await report_error(
            source="server",
            error_type=error_type,
            error_message=error_message,
            traceback_str=tb_str,
            request_path=request.url.path,
            request_method=request.method,
            user_id=user_id,
            email=email,
            trust_id=trust_id,
        )

        # Return a generic 500 — never leak internals
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error. Our team has been notified.",
            },
        )


def _extract_token(request: Request) -> Optional[str]:
    """Pull a JWT token out of the request (Authorization header or cookie)."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1]
    session_token = request.cookies.get("session_token")
    if session_token:
        return session_token
    return None