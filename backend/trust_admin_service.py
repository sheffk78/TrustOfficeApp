# Trust Administrative Services — entitlement + invite-clock logic.
#
# Pure module: no DB, no network, no env reads. Everything testable in isolation.
# The router (routers/trust_admin_service.py) owns I/O; this file owns the rules.
#
# Kenneth directive (2026-09-12, msg 1548317156591276055):
#   The invite clock for a gifted free quarter anchors on the date the user
#   submitted their FIRST trust (earliest trusts.created_at), + 3 months.

from datetime import datetime, date, timezone
from typing import Optional
import calendar


# ==================== DATE MATH ====================

def add_months(d: date, months: int) -> date:
    """Add calendar months, clamping the day to the target month's length.

    Jan 31 + 3 months -> Apr 30 (never May 1, never an error).
    """
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def _as_date(value) -> date:
    """Accept ISO string / datetime / date, return date (UTC for datetimes)."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).date()
    if isinstance(value, str):
        cleaned = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(cleaned)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).date()
    raise TypeError(f"Cannot interpret {type(value).__name__} as a date")


def compute_quarter_end(first_trust_created_at) -> date:
    """Free-quarter end = first trust submission + 3 months."""
    return add_months(_as_date(first_trust_created_at), 3)


def days_past_quarter(first_trust_created_at, now=None):
    """Days past the free-quarter end. Negative = days still remaining.

    None when there is no anchor (user never submitted a trust): no clock yet.
    """
    if first_trust_created_at is None:
        return None
    today = _as_date(now) if now is not None else datetime.now(timezone.utc).date()
    return (today - compute_quarter_end(first_trust_created_at)).days


def invite_due(first_trust_created_at, now=None) -> bool:
    """True when the free quarter has fully elapsed and the purchase invite is due."""
    past = days_past_quarter(first_trust_created_at, now)
    return past is not None and past >= 0


# ==================== ENTITLEMENT ====================

def new_gift_entitlement(granted_by: str, gift_type: str = "free_quarter", note: str = "") -> dict:
    """Doc for subscriptions.trust_admin_service — admin-granted free quarter.

    quarter_ends_at is intentionally NOT stored: it always derives from the
    first-trust anchor at read time, so a later back-dated trust submission
    (document import) automatically corrects the clock.
    """
    return {
        "status": "active",          # active while the free quarter runs
        "source": "gifted",          # gifted | purchased
        "gift_type": gift_type,      # free_quarter (3 months from first trust)
        "granted_by": granted_by,
        "granted_at": datetime.now(timezone.utc).isoformat(),
        "note": note,
    }


def resolve_entitlement(sub_doc: Optional[dict], now=None) -> dict:
    """Resolve the trust-administrative-service entitlement from a subscription doc.

    Returns a normalized dict:
      entitled      bool   — user may schedule / see the dashboard card
      source        str    — purchased | gifted | none
      status        str    — active | expired | none
      quarter_ends  str|None — ISO date the gifted quarter ends (gifted only)
      days_past     int|None
    """
    today = _as_date(now) if now is not None else datetime.now(timezone.utc).date()
    out = {"entitled": False, "source": "none", "status": "none",
           "quarter_ends": None, "days_past": None}
    if not sub_doc:
        return out

    tas = sub_doc.get("trust_admin_service") or {}
    source = tas.get("source")

    if source == "purchased":
        # Purchased stays active unless explicitly cancelled on the doc.
        if tas.get("status") == "cancelled":
            out.update(source="purchased", status="cancelled")
            return out
        out.update(entitled=True, source="purchased", status="active")
        return out

    if source == "gifted":
        anchor = tas.get("anchor_first_trust_at") or sub_doc.get("_first_trust_created_at")
        if anchor is None:
            # Gifted but no trust submitted yet: the service is already live
            # (the clock only governs the future purchase invite).
            out.update(entitled=True, source="gifted", status="active")
            return out
        qe = compute_quarter_end(anchor)
        past = (today - qe).days
        if past >= 0:
            out.update(entitled=False, source="gifted", status="expired",
                       quarter_ends=qe.isoformat(), days_past=past)
        else:
            out.update(entitled=True, source="gifted", status="active",
                       quarter_ends=qe.isoformat(), days_past=past)
        return out

    return out