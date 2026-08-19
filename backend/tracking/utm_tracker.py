"""
UTM / Referral Tracking Module — TrustOffice
=============================================
Core attribution logic: UTM capture, canonical source resolution,
signup attribution recording, and source-of-truth helpers.

This module is imported by auth.py, leads.py, and subscriptions.py.
It does NOT depend on FastAPI request objects — it works with plain dicts
so it can be used in webhook handlers and cron jobs.
"""
import re
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from database import db

logger = logging.getLogger(__name__)

# ==================== SANITIZATION ====================


def clean_utm(value: Optional[str], max_len: int = 200) -> Optional[str]:
    """Sanitize a UTM or referrer string for safe storage.

    - Strips leading/trailing whitespace
    - Removes control characters and HTML tags
    - Caps length to prevent DB bloat
    - Returns None for empty strings
    """
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    # Remove control characters and angle brackets
    cleaned = re.sub(r"[\x00-\x1f\x7f<>]", "", cleaned)
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:max_len] if cleaned else None


# ==================== CANONICAL SOURCE RESOLUTION ====================


def resolve_signup_source(user: Dict[str, Any]) -> str:
    """Compute a deterministic canonical signup source string.

    Priority:
        1. WingPoint partner referral (wp_ref present)
        2. Friend referral (referral_code present)
        3. UTM-derived source (utm_source + utm_medium)
        4. Direct (no attribution data)

    Args:
        user: User dict or UserCreate-like object with optional fields.

    Returns:
        A stable lowercase source string suitable for reporting.
    """
    if user.get("wp_ref"):
        return "wingpoint_referral"
    if user.get("referral_code"):
        return "friend_referral"
    utm_source = user.get("utm_source")
    utm_medium = user.get("utm_medium")
    if utm_source:
        medium = utm_medium or "unknown"
        # Keep it alphanumeric-ish for clean reporting
        safe = re.sub(r"[^a-zA-Z0-9_-]", "_", f"{utm_source}_{medium}")
        return safe.lower()
    return "direct"


def resolve_signup_source_from_payload(payload: Dict[str, Any]) -> str:
    """Same as resolve_signup_source but accepts a plain payload dict.

    Used when a full user record hasn't been created yet (e.g. lead capture).
    """
    if payload.get("wp_ref"):
        return "wingpoint_referral"
    if payload.get("referral_code"):
        return "friend_referral"
    utm_source = payload.get("utm_source")
    utm_medium = payload.get("utm_medium")
    if utm_source:
        medium = utm_medium or "unknown"
        safe = re.sub(r"[^a-zA-Z0-9_-]", "_", f"{utm_source}_{medium}")
        return safe.lower()
    return "direct"


# ==================== UTM EXTRACTION FROM URL ====================


def extract_utm_params(query_dict: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Extract and sanitize UTM params from a query-string dict.

    Args:
        query_dict: Typically request.query_params or parsed URL query.

    Returns:
        Dict with keys: utm_source, utm_medium, utm_campaign, utm_content,
        utm_term, referrer, referral_code, wp_ref.
    """
    return {
        "utm_source": clean_utm(query_dict.get("utm_source")),
        "utm_medium": clean_utm(query_dict.get("utm_medium")),
        "utm_campaign": clean_utm(query_dict.get("utm_campaign")),
        "utm_content": clean_utm(query_dict.get("utm_content")),
        "utm_term": clean_utm(query_dict.get("utm_term")),
        "referrer": clean_utm(query_dict.get("referrer"), max_len=500),
        "referral_code": clean_utm(query_dict.get("ref") or query_dict.get("referral_code")),
        "wp_ref": clean_utm(query_dict.get("wp_ref")),
    }


# ==================== SIGNUP ATTRIBUTION ====================


async def record_signup_attribution(
    *,
    user_id: str,
    email: str,
    source: str,
    utm_source: Optional[str] = None,
    utm_medium: Optional[str] = None,
    utm_campaign: Optional[str] = None,
    utm_content: Optional[str] = None,
    utm_term: Optional[str] = None,
    referrer: Optional[str] = None,
    referral_code: Optional[str] = None,
    wp_ref: Optional[str] = None,
) -> Dict[str, Any]:
    """Record a durable signup attribution event in analytics_events.

    Idempotent by user_id — safe to call multiple times.
    """
    from routers.analytics import _record_event  # lazy import to avoid circularity

    idempotency_key = f"signup_{user_id}"
    metadata = {
        "email": email,
        "source": source,
        "utm_source": utm_source,
        "utm_medium": utm_medium,
        "utm_campaign": utm_campaign,
        "utm_content": utm_content,
        "utm_term": utm_term,
        "referrer": referrer,
        "referral_code": referral_code,
        "wp_ref": wp_ref,
    }
    # Remove None values for cleanliness
    metadata = {k: v for k, v in metadata.items() if v is not None}

    return await _record_event(
        event_name="signup_complete",
        user_id=user_id,
        session_id=None,
        metadata=metadata,
        idempotency_key=idempotency_key,
    )


# ==================== CHECKOUT METADATA BUILDER ====================


def build_checkout_metadata(
    *,
    user_id: str,
    plan_type: str,
    billing_period: str,
    utm_source: Optional[str] = None,
    utm_medium: Optional[str] = None,
    utm_campaign: Optional[str] = None,
    utm_content: Optional[str] = None,
    referral_code: Optional[str] = None,
    wp_ref: Optional[str] = None,
) -> Dict[str, str]:
    """Build Stripe checkout session metadata dict with attribution.

    Stripe metadata values must be strings and ≤ 500 chars each.
    """
    metadata: Dict[str, str] = {
        "user_id": user_id,
        "plan_type": plan_type,
        "billing_period": billing_period,
    }
    if utm_source:
        metadata["utm_source"] = utm_source[:500]
    if utm_medium:
        metadata["utm_medium"] = utm_medium[:500]
    if utm_campaign:
        metadata["utm_campaign"] = utm_campaign[:500]
    if utm_content:
        metadata["utm_content"] = utm_content[:500]
    if referral_code:
        metadata["referral_code"] = referral_code[:500]
    if wp_ref:
        metadata["wp_ref"] = wp_ref[:500]
    return metadata


# ==================== SOURCE-LEVEL REPORTING HELPERS ====================


async def get_attribution_summary(start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
    """Return a summary of signups and purchases grouped by canonical source.

    Used by admin dashboards and weekly reporting.
    """
    match_stage: Dict[str, Any] = {}
    if start_date or end_date:
        match_stage["created_at"] = {}
        if start_date:
            match_stage["created_at"]["$gte"] = start_date
        if end_date:
            match_stage["created_at"]["$lte"] = end_date

    # Signups by source
    signup_pipeline = [
        {"$match": {**match_stage, "event_name": "signup_complete"}},
        {"$group": {
            "_id": "$metadata.source",
            "count": {"$sum": 1},
        }},
        {"$sort": {"count": -1}},
    ]
    signups = list(await db.analytics_events.aggregate(signup_pipeline).to_list(100))

    # Purchases by source
    purchase_pipeline = [
        {"$match": {**match_stage, "event_name": "purchase_complete"}},
        {"$group": {
            "_id": "$metadata.source",
            "count": {"$sum": 1},
            "revenue": {"$sum": "$metadata.amount"},
        }},
        {"$sort": {"count": -1}},
    ]
    purchases = list(await db.analytics_events.aggregate(purchase_pipeline).to_list(100))

    return {
        "signups_by_source": [{"source": s["_id"], "count": s["count"]} for s in signups],
        "purchases_by_source": [{"source": p["_id"], "count": p["count"], "revenue": p["revenue"]} for p in purchases],
    }
