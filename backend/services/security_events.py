"""
Security event logging + anomaly alerting for TrustOffice.

- `record_security_event(...)`: writes a structured security event to the
  `security_events` MongoDB collection (timestamped UTC ISO). Every DB write is
  wrapped in try/except with a logger.warning on failure so logging can NEVER
  break the request path it was called from.

- Alerting rules (Discord, env-based webhook like error_alerting.py):
    * >=5 login_failed for same user/email within 15 min
    * >20 vault_download per user per hour
    * ANY admin_impersonation
    * ANY refresh_reuse_detected
    * bulk_export >50 records
  Dedup: at most 1 alert per (rule, user) per 30 minutes (in-memory dict).

Usage:
    from services.security_events import record_security_event, check_security_alert
    await record_security_event(user_id, "login_failed", ip=ip, user_agent=ua)
    await record_security_event(user_id, "admin_impersonation",
                                details={"target_user_id": tid, "admin_user_id": aid})
    await check_security_alert("login_failed", user_id=user_id, email=email)
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from discord_service import notify_alert

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

# Per-event-type window (seconds) used to COUNT recent events for thresholding.
# The count is derived by querying the security_events collection; this is the
# lookback window for those queries.
_EVENT_WINDOWS: Dict[str, int] = {
    "login_failed": 15 * 60,        # 15 minutes
    "vault_download": 60 * 60,      # 1 hour
}

# Discord webhook for security anomalies. Falls back to the general alerts
# webhook (set via DISCORD_ALERTS_WEBHOOK_URL in discord_service) if unset.
_SECURITY_WEBHOOK_URL = os.environ.get("DISCORD_SECURITY_WEBHOOK_URL", "").strip() or None

# Brand color for security alerts (rust red, matches error_alerting).
_SECURITY_COLOR = 0xB44040


async def record_security_event(
    user_id: Optional[str],
    event_type: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Persist a security event. Never raises â logging must not break requests.

    Writes {ts UTC ISO, user_id, event_type, ip, user_agent, details} to the
    `security_events` collection. Any DB failure is swallowed and logged at
    WARNING so the calling request completes normally.
    """
    # Best-effort import so a missing/delayed DB connection at import time does
    # not break callers that only use the alerting half of this module.
    try:
        from database import db
    except Exception as exc:  # pragma: no cover - import guard
        logger.warning(f"security_events: could not import db: {exc}")
        return

    doc = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "event_type": event_type,
        "ip": ip,
        "user_agent": user_agent,
        "details": details or {},
    }
    try:
        await db.security_events.insert_one(doc)
    except Exception as exc:
        logger.warning(f"Failed to record security event '{event_type}' for user {user_id}: {exc}")


# ---------------------------------------------------------------------------
# In-memory alert dedupe
# ---------------------------------------------------------------------------

# (rule, user_key) -> last alerted unix timestamp
_ALERT_CACHE: Dict[str, float] = {}
_DEDUPE_WINDOW_SECONDS = 30 * 60  # 30 minutes
_MAX_CACHE_SIZE = 1024


def _prune_alert_cache() -> None:
    now = time.time()
    cutoff = now - _DEDUPE_WINDOW_SECONDS
    expired = [k for k, ts in _ALERT_CACHE.items() if ts < cutoff]
    for k in expired:
        del _ALERT_CACHE[k]
    if len(_ALERT_CACHE) > _MAX_CACHE_SIZE:
        sorted_items = sorted(_ALERT_CACHE.items(), key=lambda kv: kv[1])
        for k, _ in sorted_items[: len(_ALERT_CACHE) - _MAX_CACHE_SIZE]:
            del _ALERT_CACHE[k]


def _is_duplicate_alert(rule: str, user_key: str) -> bool:
    """True if (rule, user_key) already alerted within the dedupe window."""
    key = f"{rule}|{user_key}"
    now = time.time()
    last = _ALERT_CACHE.get(key)
    if last is not None and (now - last) < _DEDUPE_WINDOW_SECONDS:
        return True
    _ALERT_CACHE[key] = now
    _prune_alert_cache()
    return False


# ---------------------------------------------------------------------------
# Threshold evaluation
# ---------------------------------------------------------------------------

# Rule definitions: rule_name -> (event_type, threshold, window_seconds, kind)
# kind "count" counts events in the window; kind "always" fires unconditionally;
# kind "min" fires when `count` exceeds the threshold (for bulk_export).
_RULES: Dict[str, Dict[str, Any]] = {
    "login_failed": {
        "event_type": "login_failed",
        "threshold": 5,
        "window_seconds": 15 * 60,
        "kind": "count",
    },
    "vault_download": {
        "event_type": "vault_download",
        "threshold": 20,
        "window_seconds": 60 * 60,
        "kind": "count",
    },
    "admin_impersonation": {
        "event_type": "admin_impersonation",
        "kind": "always",
    },
    "refresh_reuse_detected": {
        "event_type": "refresh_reuse_detected",
        "kind": "always",
    },
    "bulk_export": {
        "event_type": "bulk_export",
        "threshold": 50,
        "kind": "min",
    },
}


async def _count_recent(
    event_type: str, window_seconds: int, user_id: Optional[str], email: Optional[str]
) -> int:
    """Count events of event_type within window_seconds for user/email."""
    try:
        from database import db
    except Exception:
        return 0

    since = datetime.now(timezone.utc).timestamp() - window_seconds
    since_iso = datetime.fromtimestamp(since, tz=timezone.utc).isoformat()
    query: Dict[str, Any] = {
        "event_type": event_type,
        "ts": {"$gte": since_iso},
    }
    # Match on user_id when available; otherwise fall back to email stored in
    # details (login_failed records store the email there).
    if user_id:
        query["user_id"] = user_id
    elif email:
        query["details.email"] = email
    try:
        return await db.security_events.count_documents(query)
    except Exception as exc:
        logger.warning(f"Failed to count security events '{event_type}': {exc}")
        return 0


async def check_security_alert(
    rule: str,
    *,
    user_id: Optional[str] = None,
    email: Optional[str] = None,
    count: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate a rule and fire a Discord alert if it trips (with dedupe).

    Parameters
    ----------
    rule : str
        One of the keys in _RULES (e.g. "login_failed", "bulk_export").
    user_id, email : optional
        Identity used for both counting (when `count` is None) and dedupe keying.
    count : optional int
        Pre-computed count for "min"-kind rules (e.g. bulk_export record count).
        When provided, thresholding uses it directly instead of querying the DB.
    details : optional dict
        Extra context included in the alert message and omitted from dedupe key.

    Returns
    -------
    dict: {"alerted": bool, "duplicate": bool, "rule": str, "count": int|None}
        `alerted` is False when deduped, below threshold, or no webhook is set.
    """
    spec = _RULES.get(rule)
    if spec is None:
        logger.warning(f"check_security_alert: unknown rule '{rule}'")
        return {"alerted": False, "duplicate": False, "rule": rule, "count": count}

    kind = spec.get("kind")
    threshold = spec.get("threshold")

    if kind == "always":
        triggered = True
        eval_count: Optional[int] = None
    elif kind == "min":
        eval_count = count if count is not None else 0
        triggered = eval_count > int(threshold)  # type: ignore[operator]
    else:  # "count"
        eval_count = await _count_recent(
            spec["event_type"], spec["window_seconds"], user_id, email
        )
        triggered = eval_count >= int(threshold)  # type: ignore[operator]

    if not triggered:
        return {"alerted": False, "duplicate": False, "rule": rule, "count": eval_count}

    # Dedupe key: rule + user identity (email if no user_id, since login_failed
    # may not yet have a user_id for unknown-email attempts).
    user_key = user_id or email or "unknown"
    if _is_duplicate_alert(rule, user_key):
        return {"alerted": False, "duplicate": True, "rule": rule, "count": eval_count}

    # Build a human-readable alert message.
    message = _build_alert_message(rule, user_id, email, eval_count, details)
    title = f"ð¨ Security Alert: {rule.replace('_', ' ').title()}"

    try:
        await notify_alert(title=title, message=message, color=_SECURITY_COLOR)
    except Exception as exc:
        # Alerting failure must never crash the request path.
        logger.error(f"Failed to send security alert for '{rule}': {exc}", exc_info=True)
        return {"alerted": False, "duplicate": False, "rule": rule, "count": eval_count,
                "alert_error": str(exc)}

    return {"alerted": True, "duplicate": False, "rule": rule, "count": eval_count}


async def alert_security_event(
    event_type: str,
    *,
    user_id: Optional[str] = None,
    email: Optional[str] = None,
    count: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convenience: map an event_type to its rule and evaluate it.

    Used by call sites that record an event AND want to run its alert rule in
    one call (e.g. admin_impersonation, refresh_reuse_detected, bulk_export).
    """
    rule = event_type
    if rule not in _RULES:
        logger.warning(f"alert_security_event: no alert rule for event_type '{event_type}'")
        return {"alerted": False, "duplicate": False, "rule": rule, "count": count}
    return await check_security_alert(
        rule, user_id=user_id, email=email, count=count, details=details
    )


def _build_alert_message(
    rule: str,
    user_id: Optional[str],
    email: Optional[str],
    count: Optional[int],
    details: Optional[Dict[str, Any]],
) -> str:
    parts: List[str] = []
    ident = user_id or email or "unknown"
    parts.append(f"**User:** `{ident}`")
    if email and user_id:
        parts.append(f"**Email:** `{email}`")

    if rule == "login_failed":
        parts.append(f"**Failed logins:** {count} within 15 minutes (threshold 5)")
    elif rule == "vault_download":
        parts.append(f"**Vault downloads:** {count} in the last hour (limit 20)")
    elif rule == "admin_impersonation":
        parts.append("An admin started impersonating a user.")
    elif rule == "refresh_reuse_detected":
        parts.append("A refresh/jti token was reused after it should have been revoked.")
    elif rule == "bulk_export":
        parts.append(f"**Records exported:** {count} (threshold 50)")

    if details:
        ctx_lines = []
        for k, v in details.items():
            v_str = str(v)
            if len(v_str) > 400:
                v_str = v_str[:400] + "â¦"
            ctx_lines.append(f"- {k}: {v_str}")
        if ctx_lines:
            parts.append("**Details:**\n" + "\n".join(ctx_lines))

    return "\n".join(parts)
