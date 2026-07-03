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
import logging
import time
import traceback
from typing import Any, Dict, Optional, TYPE_CHECKING

from discord_service import notify_alert

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

    try:
        await notify_alert(
            title=title,
            message="\n".join(parts),
            color=ERROR_COLOR,
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