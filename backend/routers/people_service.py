"""TrustOffice "people service" lane (Phase 2 — P2-JOB-20261105-PEOPLE).

Sister router to routers/leads_service.py (P1), mounted under
/api/service/people with the SAME scoped X-Service-Key gate
(`require_leads_service`, imported from there — no second auth scheme).

Endpoints:
  GET /api/service/people              -> roster (people + counts + as_of)
  GET /api/service/people/counts       -> counts dict + as_of only (cheap)
  GET /api/service/people/{id}/emails  -> latest 10 email records, newest first
                                          (unknown id => 200 + empty list,
                                          never a 404)
  GET /api/service/people/{id}/detail  -> P3 bounded per-person bundle:
                                          identity + stage/status + <=10
                                          emails + <=50 activities + <=10
                                          notes + next_action (unknown id
                                          => 200 + empty bundle, never 404)

Read-only: touches ONLY existing collections — leads, users, subscriptions,
lead_activities — plus an inbound-email collection when the live database
actually has one (runtime discovery of db.emails / mail_logs /
inbound_emails / received_emails). This repo owns no inbound-email
collection, so without discovery the emails endpoint returns
lead_activities-derived rows only and NEVER invents received mail.

Conventions (mirrors the P1 module):
  - ids are opaque strings ("lead:<lead_id>" / "purchaser:<lower(email)>")
    that round-trip into /{id}/emails.
  - datetimes render via the same _iso semantics (BSON Date or ISO string
    in, ISO string out, None preserved).
  - counts.by_stage counts the kind=="lead" people only; converted leads
    are purchasers (subscribers) and are counted in counts.purchasers.
"""

import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import db
from routers.leads import _log_activity
from routers.leads_service import (
    ACTIVITY_CONTENT_LIMIT,
    LEAD_PROJECTION,
    _activity_view,
    require_leads_service,
)
# WingPoint membership single source of truth â never re-derive inline.
from services.wingpoint_identity import is_wingpoint_user

logger = logging.getLogger(__name__)

# ==================== ROSTER ENRICHMENT HELPERS (P2 deepen) ====================
#
# Behavior/truth fields added ADDITIVELY to every roster person. Every value is
# derived from real stored data (subscriptions + payment_transactions + users +
# course_leads + fiduciary_assessments). Nothing is synthesized or default-filled:
# when the data does not exist server-side the field is null / the list empty.
#
# NOTE on behavior.page_events / behavior.resources:
#   The TO product does NOT store per-page visits or resource downloads
#   server-side. Page views are client-side GA4/Meta Pixel only; resource access
#   is tracked only as course-lesson flags. So those two lists are emitted empty
#   by design and never fabricated. (See the lane-A report for the probe result.)

# plan_type -> human product label (display only; falls back to raw plan_type).
PRODUCT_LABELS = {
    "trustee": "Trustee",
    "estate": "Estate",
    "advisor": "Advisor",
    "wingpoint": "WingPoint",
    "wingpoint_trustee": "WingPoint Trustee",
}
# WingPoint pricing plan_types (wp_product truth per contract).
WP_PLAN_TYPES = ("wingpoint", "wingpoint_trustee")
# payment_transactions statuses that count as a real payment.
PAID_STATUSES = ("paid", "succeeded")

_PLAN_AMOUNTS_CACHE = None


def _plan_amounts():
    """Lazily import the canonical price map from routers.subscriptions.

    Avoids a hard top-level import of the (heavy) subscriptions router; falls
    back to an empty map if it cannot be loaded so the roster never 500s.
    """
    global _PLAN_AMOUNTS_CACHE
    if _PLAN_AMOUNTS_CACHE is None:
        try:
            from routers.subscriptions import PLAN_AMOUNTS as _pa
            _PLAN_AMOUNTS_CACHE = _pa or {}
        except Exception:
            _PLAN_AMOUNTS_CACHE = {}
    return _PLAN_AMOUNTS_CACHE


def _product_label(plan_type):
    if not plan_type:
        return None
    return PRODUCT_LABELS.get(plan_type, plan_type)


def _amount_cents_for(plan_type, billing_period):
    """Current-cycle price in cents from the canonical (plan_type, billing_period)
    map. Returns None when the stored plan/period isn't a known price (never invents)."""
    if not plan_type:
        return None
    amt = _plan_amounts().get((plan_type, billing_period))
    if amt is None:
        return None
    return int(round(float(amt) * 100))


def _to_cents(amount_dollars):
    """payment_transactions stores dollars; convert to cents. None-safe."""
    if amount_dollars is None:
        return None
    try:
        return int(round(float(amount_dollars) * 100))
    except (TypeError, ValueError):
        return None


def _iso(raw):
    """BSON Date | ISO string | None -> ISO string | None (tz-aware out)."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.isoformat()
    if isinstance(raw, str):
        dt = _as_dt(raw)
        return dt.isoformat() if dt else raw
    return None


def _last_paid_from_stripe(stripe_customer_id):
    """Fail-soft Stripe Invoice retrieve fallback.

    Invoked ONLY when the stored payment_transactions trail is empty and a Stripe
    customer id is present AND STRIPE_SECRET_KEY is in env. Returns (iso_at, cents)
    or (None, None). Any Stripe error is swallowed so the roster never breaks.
    """
    if not stripe_customer_id:
        return None, None
    api_key = os.environ.get("STRIPE_SECRET_KEY")
    if not api_key:
        return None, None
    try:
        import stripe

        stripe.api_key = api_key
        invoices = stripe.Invoice.list(
            customer=stripe_customer_id, status="paid", limit=1
        )
        data = list(getattr(invoices, "data", []) or [])
        if not data:
            return None, None
        inv = data[0]
        if isinstance(inv, dict):
            paid_at = (inv.get("status_transitions") or {}).get("paid_at")
            amount_cents = inv.get("amount_paid")
        else:
            paid_at = getattr(
                getattr(inv, "status_transitions", None), "paid_at", None
            )
            amount_cents = getattr(inv, "amount_paid", None)
        iso_at = (
            datetime.fromtimestamp(paid_at, tz=timezone.utc).isoformat()
            if paid_at
            else None
        )
        return iso_at, (int(amount_cents) if amount_cents is not None else None)
    except Exception as e:  # pragma: no cover - network path
        logger.warning(f"people_service Stripe invoice fallback failed: {e}")
        return None, None


router = APIRouter(
    prefix="/service/people",
    tags=["people-service"],
    dependencies=[Depends(require_leads_service)],
)

PEOPLE_EMAIL_LIMIT = 10  # per-person feed cap (contract: max 10, latest first)

# Lead projection for the roster: the P1 shape + the two linkage fields the
# conversion bridge leaves on converted leads (user_id stamp, converted_at).
ROSTER_LEAD_PROJECTION = {
    **LEAD_PROJECTION,
    "user_id": 1,
    "converted_at": 1,
    # WingPoint membership fields so is_wingpoint_user() can run on lead docs too.
    "wp_ref": 1,
    "created_via": 1,
}

# ---- P3 (per-person detail bundle) ----
PEOPLE_DETAIL_EMAIL_LIMIT = 10   # newest email records in the bundle
PEOPLE_DETAIL_ACT_LIMIT = 50     # activity rows: contact history incl. video/downloads
# Lead doc fields for the bundle identity/status block (P1 shape + P3 extras).
DETAIL_LEAD_PROJECTION = {
    **LEAD_PROJECTION,
    "user_id": 1,
    "converted_at": 1,
    "next_action": 1,
    "booked_call": 1,
    "call_outcome": 1,
}
# note rows: note_added activities carry the note text in `content`.
DETAIL_NOTE_PROJECTION = {
    "_id": 0,
    "action_type": 1,
    "content": 1,
    "created_at": 1,
}
# Identity fields for a user-backed person (users docs carry no phone/company).
DETAIL_USER_PROJECTION = {
    "_id": 0,
    "user_id": 1,
    "full_name": 1,
    "name": 1,
    "first_name": 1,
    "last_name": 1,
    "email": 1,
}

# Contact-history activities use the same projection `_activity_view` expects
# (action_type / content / created_at) so they render in the OS activity shape.
DETAIL_ACTIVITY_PROJECTION = {
    "_id": 0,
    "action_type": 1,
    "content": 1,
    "created_at": 1,
}
# Note-style activity rows surfaced as "notes" in the detail bundle.
NOTE_ACTION_TYPES = ("note_added", "manual")

# ---- P4 (server-side person notes/tasks store, OS people-card writes) ----
# A REAL store owned by this repo: OS writes land HERE (Mongo, service-key
# scoped) instead of living only in the OS host's Mac-local crm.db. person_id
# is stored EXACTLY as sent — colon-prefixed forms included ("lead:<bare>",
# "purchaser:<email>", bare "lead_<hex>") — because round-tripping the exact id
# is the only thing the OS card needs to read its writes back.
PEOPLE_STORE_NOTE_LIMIT = 20   # newest notes carried in one read
PEOPLE_STORE_TASK_LIMIT = 20   # newest tasks carried in one read
PEOPLE_NOTE_TEXT_LIMIT = 2000
PEOPLE_TASK_TITLE_LIMIT = 300
PEOPLE_TASK_STATUSES = ("open", "done")


class PersonNoteRequest(BaseModel):
    text: str


class PersonTaskRequest(BaseModel):
    title: str
    status: str = "open"


class PersonTaskStatusRequest(BaseModel):
    task_id: str
    status: str


def _person_note_view(doc: dict) -> dict:
    """Mongo people_notes doc -> OS wire shape {id, text, at}."""
    return {
        "id": doc.get("note_id") or "",
        "text": doc.get("text") or "",
        "at": _iso(doc.get("at")),
    }


def _person_task_view(doc: dict) -> dict:
    """Mongo people_tasks doc -> OS wire shape {id, title, status, at}."""
    return {
        "id": doc.get("task_id") or "",
        "title": doc.get("title") or "",
        "status": doc.get("status") or "open",
        "at": _iso(doc.get("at")),
    }


async def _store_person_notes(person_id: str, limit: int = PEOPLE_STORE_NOTE_LIMIT) -> List[dict]:
    """Newest-first notes for the EXACT person id (empty list when none)."""
    out: List[dict] = []
    cursor = (
        db.people_notes.find({"person_id": person_id})
        .sort("at", -1)
        .limit(limit)
    )
    async for doc in cursor:
        out.append(_person_note_view(doc))
    return out


async def _store_person_tasks(person_id: str, limit: int = PEOPLE_STORE_TASK_LIMIT) -> List[dict]:
    """Newest-first tasks for the EXACT person id (empty list when none)."""
    out: List[dict] = []
    cursor = (
        db.people_tasks.find({"person_id": person_id})
        .sort("at", -1)
        .limit(limit)
    )
    async for doc in cursor:
        out.append(_person_task_view(doc))
    return out


def _bare_lead_id(person_id: str) -> Optional[str]:
    """"lead:lead_abc" -> "lead_abc"; anything else -> None.

    The legacy lead-activity log is keyed by the BARE lead_id (routes do
    db.leads.find_one({"lead_id": lead_id})), so the side-log only fires when
    the colon is present and always logs the stripped form.
    """
    if person_id.startswith("lead:") and len(person_id) > len("lead:"):
        return person_id.split(":", 1)[1].strip() or None
    return None


async def _side_log_lead_activity(bare_lead_id: str, text: str) -> bool:
    """Best-effort append of a 'manual' activity to the legacy lead log.

    Same _log_activity path routers.leads_service's add_service_note uses, but
    NEVER raises: an unknown/missing lead must not fail a note that already
    landed in people_notes. Returns True when a row was written.
    """
    try:
        lead = await db.leads.find_one({"lead_id": bare_lead_id})
        if not lead:
            return False
        await _log_activity(bare_lead_id, "manual", text)
        return True
    except Exception:
        logger.exception("lead-activity side-log failed for lead %s", bare_lead_id)
        return False


# Runtime-discovery candidates for a live inbound-email collection.
_INBOUND_CANDIDATES = ("emails", "inbound_emails", "mail_logs", "received_emails")
_inbound_cache: dict = {"done": False, "name": None}


async def _inbound_collection_name() -> Optional[str]:
    """Name of the live inbound-email collection, or None.

    Discovery runs at most once per process against the REAL Mongo client
    handle (database.client). Tests run on the mongomock shim, which reports
    no real collections, so they stay on lead_activities data and never
    invent received mail. Any failure => None => same safe fallback.
    """
    if _inbound_cache["done"]:
        return _inbound_cache["name"] or None
    name: Optional[str] = None
    try:
        from database import client as _mongo_client

        real = _mongo_client.get_default_database()
        if real is None:
            real = _mongo_client.get_database(os.environ.get("DB_NAME") or None)
        existing = set(await real.list_collection_names())
        for candidate in _INBOUND_CANDIDATES:
            if candidate in existing:
                name = candidate
                break
    except Exception as exc:  # noqa: BLE001 — discovery must never break the endpoint
        logger.debug("inbound-email collection discovery skipped: %s", exc)
    _inbound_cache["done"] = True
    _inbound_cache["name"] = name
    return name


# ==================== NOISE-SENDER CLASSIFICATION ====================
# ONE helper (is_noise_sender) covers the contract's exclusion list; the
# roster counts every excluded address in counts.excluded_noise.

# (token, literal) — literal tokens are plain substrings; non-literal ones
# require word boundaries so real people ("Claudette Brice") never trip.
_NOISE_TOKENS: Tuple[Tuple[str, bool], ...] = (
    ("no-reply", True),
    ("noreply", True),
    ("dmarc", True),
    ("postmaster", True),
    ("bounce", False),
    ("bounces", False),
    ("mailer-daemon", True),
    ("mailerdaemon", True),
    ("claude", False),
    ("anthropic", False),
    ("google alerts", True),
    ("googlealerts", True),
    ("googleads", True),
    ("google-ads", True),
    ("notifications@", True),
    ("donotreply", True),
    ("do-not-reply", True),
    ("auto-reply", True),
    ("autoreply", True),
    ("abuse@", True),
    ("webmaster@", True),
    ("hostmaster@", True),
    ("no_reply", True),
    ("list-unsubscribe", True),
)

# Whole sender domains that are always system/noise.
_NOISE_DOMAINS = {"google.com", "anthropic.com"}

_WORD_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789_")
_ADDRESS_STRIP = " \t<>()[]{}|,;"


def _noise_token_hit(lowered: str, token: str, literal: bool) -> bool:
    """Substring hit, word-boundary-checked for risky bare words.

    Tokens like "notifications@" or "google alerts" carry separators and
    cannot span word boundaries, so plain `in` is safe. Bare words ("claude",
    "bounce") need boundaries so "Claudette" does not fire while
    "bounces+123@sendgrid.net" does.
    """
    if literal:
        return token in lowered
    start = 0
    while True:
        idx = lowered.find(token, start)
        if idx < 0:
            return False
        before = lowered[idx - 1] if idx > 0 else ""
        after_idx = idx + len(token)
        after = lowered[after_idx] if after_idx < len(lowered) else ""
        boundary = (not before or before not in _WORD_CHARS) and (
            not after or after not in _WORD_CHARS
        )
        # "+"/"." right after the token (bounce+..., bounces+123) still
        # reads as system plumbing — treat those separators as boundaries.
        if literal is False and after in ("+", "."):
            return True
        if boundary:
            return True
        start = idx + 1


def is_noise_sender(email: str = "", name: str = "") -> bool:
    """True when the sender is system plumbing, not a person.

    Covers (case-insensitive): no-reply/noreply, dmarc, postmaster, bounce,
    mailer-daemon, claude, anthropic, google alerts/ads, the whole domains
    google.com and anthropic.com, notifications@ and generic system senders
    (donotreply, auto-reply, abuse@, webmaster@, hostmaster@). Either
    argument can trip the match, so relay aliases with display names like
    "Google Alerts" are caught too.
    """
    for candidate in (email or "", name or ""):
        if not candidate:
            continue
        addr_part = candidate
        if "<" in addr_part and ">" in addr_part:
            addr_part = addr_part.split("<", 1)[1].rsplit(">", 1)[0]
        domain = ""
        if "@" in addr_part:
            domain = addr_part.rsplit("@", 1)[1].strip(_ADDRESS_STRIP).lower()
        if domain in _NOISE_DOMAINS:
            return True
        lowered = candidate.lower()
        for token, literal in _NOISE_TOKENS:
            if _noise_token_hit(lowered, token, literal):
                return True
    return False


# ==================== SMALL HELPERS ====================


def _as_dt(raw) -> Optional[datetime]:
    """Coerce a stored value (BSON Date | ISO string | None) to aware datetime."""
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str):
        try:
            dt = datetime.fromisoformat(raw)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _is_stage_row(action_type: str, content: str) -> bool:
    atype = (action_type or "").strip().lower()
    content_low = (content or "").lower()
    return (
        atype in ("stage_change", "converted")
        or "stage set" in content_low
        or "stage changed" in content_low
    )


def _sub_is_paid_active(sub: dict) -> bool:
    """Paid/active subscription doc (mirrors dependencies._is_subscription_active
    plus the contract's stripe_subscription_id-present-active clause)."""
    status = (sub.get("status") or "").strip().lower()
    if status == "active":
        return True
    if status == "trialing":
        trial_end = _as_dt(sub.get("trial_end_date"))
        if trial_end is None:
            return True  # trialing without an end date: still a live customer
        return trial_end >= datetime.now(timezone.utc)
    if sub.get("stripe_subscription_id") and status not in ("canceled", "expired", "past_due"):
        return True
    return False


def _email_direction(action_type: str, content: str) -> str:
    """Classify a lead_activity row as in / out / system.

    Outbound sends (action_type 'email', or text saying sent / send via
    MailerCloud) are 'out' when a human sent them (manual) and 'system' for
    automated sends; recorded inbound mail is 'in'; everything else (notes,
    stage bookkeeping) is 'system'.
    """
    atype = (action_type or "").strip().lower()
    low = (content or "").lower()
    if "received" in low or atype in ("inbound", "received"):
        return "in"
    if atype == "email" or "sent" in low or "mailercloud" in low:
        return "out"
    return "system"


def _email_subject(content: str) -> str:
    """Subject line: first line, cut at the ' - ' body separator when present."""
    text = (content or "").split("\n", 1)[0]
    if " - " in text:
        text = text.split(" - ", 1)[0]
    return text[:200]


def _email_snippet(content: str) -> str:
    """Snippet = after the ' - ' separator on the first line, or the first
    line's remainder/newline body — capped at 160 chars like the P1 view."""
    text = (content or "").split("\n", 1)[0]
    if " - " in text:
        body = text.split(" - ", 1)[1]
    else:
        parts = (content or "").split("\n", 1)
        body = parts[1] if len(parts) == 2 else parts[0]
    return body.strip()[:ACTIVITY_CONTENT_LIMIT]


def _row_sort_key(row: dict):
    """Sort key over possibly-mixed datetime/ISO-string stamps -> epoch float."""
    dt = _as_dt(row.get("at"))
    return dt.timestamp() if dt else 0.0


def _person_id_for_entry(entry: dict) -> str:
    if entry["kind"] == "purchaser":
        return f"purchaser:{entry['email_key']}"
    # Contract: lead ids are "lead:<lead_id>" so they round-trip into
    # /{id}/emails and /{id}/detail. Fall back to the email key only for the
    # rare lead doc that never got a lead_id stamp.
    lead_ids = entry.get("lead_ids") or []
    if lead_ids and lead_ids[0]:
        return f"lead:{lead_ids[0]}"
    return f"lead:{entry['email_key']}"


async def _person_email_rows(person: dict, activity_query: dict) -> List[dict]:
    """Bounded newest-first email rows for one resolved person (P2/P3 shared).

    Sources: the discovered live inbound-email collection (direction 'in')
    plus lead_activities-derived rows; merged, deduped, newest first, capped
    at PEOPLE_EMAIL_LIMIT. Stamps render as ISO strings on the way out.
    """
    email_rows: List[dict] = []

    # ---- discovered inbound collection (live DB only) -> direction 'in' ----
    inbound_coll = await _inbound_collection_name()
    if inbound_coll and person["email"]:
        addr_icase = {
            "$regex": f"^{re.escape(person['email'])}$",
            "$options": "i",
        }
        inbound_cursor = (
            db[inbound_coll]
            .find({"$or": [{"to": addr_icase}, {"from": addr_icase}]})
            .sort("created_at", -1)
            .limit(PEOPLE_EMAIL_LIMIT)
        )
        async for doc in inbound_cursor:
            email_rows.append(
                {
                    "at": doc.get("created_at") or doc.get("date"),
                    "direction": "in",
                    "subject": (doc.get("subject") or "")[:200],
                    "snippet": (doc.get("snippet") or doc.get("text") or "")[:ACTIVITY_CONTENT_LIMIT],
                    "type": doc.get("type") or "inbound",
                }
            )

    # ---- lead_activities rows (always the base source) ----
    if activity_query:
        cursor = (
            db.lead_activities.find(activity_query)
            .sort("created_at", -1)
            .limit(PEOPLE_EMAIL_LIMIT * 2)
        )
        async for act in cursor:
            email_rows.append(
                {
                    "at": act.get("created_at"),
                    "direction": _email_direction(act.get("action_type"), act.get("content") or ""),
                    "subject": _email_subject(act.get("content") or ""),
                    "snippet": _email_snippet(act.get("content") or ""),
                    "type": act.get("action_type") or "activity",
                }
            )

    # ---- merge, dedupe, newest-first, cap ----
    deduped: List[dict] = []
    seen_rows = set()
    for row in email_rows:
        key = ((row.get("direction") or ""), (row.get("subject") or "").lower()[:80])
        if inbound_coll and key in seen_rows and row.get("direction") == "out":
            # an inbound copy already covers this thread; skip the mirror row
            continue
        if key in seen_rows and row.get("direction") != "out":
            continue
        seen_rows.add(key)
        deduped.append(row)

    deduped.sort(key=_row_sort_key, reverse=True)

    return [
        {
            "at": row["at"].isoformat() if isinstance(row["at"], datetime) else row["at"],
            "direction": row["direction"],
            "subject": row["subject"],
            "snippet": row["snippet"],
            "type": row["type"],
        }
        for row in deduped[:PEOPLE_EMAIL_LIMIT]
    ]


async def _resolve_person(
    person_id: str, email: str = "", name: str = ""
) -> Tuple[dict, Optional[dict], Optional[dict], dict]:
    """Turn an opaque person id into (person, lead, user, activity_query).

    Exact P2 emails-endpoint semantics, extracted so /detail reuses the same
    resolution: lead:<lead_id> matches db.leads.lead_id (activities queried
    even when the lead doc itself is gone — degrade honestly); purchaser:<email>
    matches a lead by case-insensitive email, falling back to a user doc for
    identity only when no lead exists. Unknown shapes/persons resolve to the
    echoed person with empty query — a 200 empty bundle, never a 404.
    """
    person = {"id": person_id, "name": name or "", "email": email or ""}
    lead: Optional[dict] = None
    user: Optional[dict] = None
    activity_query: dict = {}

    if person_id.startswith("lead:"):
        activity_lid = person_id[len("lead:"):]
        if activity_lid and activity_lid not in ("", "null"):
            lead = await db.leads.find_one(
                {"lead_id": activity_lid},
                DETAIL_LEAD_PROJECTION,
            )
            if lead is None and "@" in activity_lid:
                # Ids minted before the lead_id round-trip fix carried the
                # email key in the lead:<...> slot. Resolve by email so old
                # links still land on the right person (no invented data).
                lead = await db.leads.find_one(
                    {
                        "email": {
                            "$regex": f"^{re.escape(activity_lid)}$",
                            "$options": "i",
                        }
                    },
                    DETAIL_LEAD_PROJECTION,
                )
                if lead and lead.get("lead_id"):
                    activity_lid = lead["lead_id"]
            if lead:
                person = {
                    "id": person_id,
                    "name": lead.get("name") or person["name"],
                    "email": lead.get("email") or person["email"],
                }
            activity_query = {"lead_id": activity_lid}
    elif person_id.startswith("purchaser:"):
        p_email = (email or person_id[len("purchaser:"):]).strip().lower()
        person = {"id": person_id, "name": name or "", "email": p_email}
        email_icase = {"$regex": f"^{re.escape(p_email)}$", "$options": "i"} if p_email else None
        if p_email:
            lead = await db.leads.find_one({"email": email_icase}, DETAIL_LEAD_PROJECTION)
        if lead:
            person["name"] = lead.get("name") or person["name"]
            person["email"] = lead.get("email") or p_email
            activity_query = {"lead_id": lead.get("lead_id")}
        else:
            if p_email:
                user = await db.users.find_one(
                    {"email": email_icase},
                    DETAIL_USER_PROJECTION,
                )
            if user:
                person["name"] = (
                    user.get("full_name")
                    or " ".join(p for p in (user.get("first_name"), user.get("last_name")) if p)
                    or user.get("name")
                    or ""
                ) or person["name"]
                person["email"] = (user.get("email") or p_email)

    return person, lead, user, activity_query


def _entry_recency(entry: dict) -> Optional[datetime]:
    """Recency clock for roster sorting (purchasers: purchased_at)."""
    if entry["kind"] == "purchaser":
        return _as_dt(entry.get("purchased_at")) or _as_dt(entry.get("created_at"))
    return _as_dt(entry.get("last_activity_at")) or _as_dt(entry.get("created_at"))


# ==================== ROSTER LOADER ====================


async def _load_roster() -> Tuple[List[dict], dict, datetime]:
    """Assemble the people roster from the existing collections.

    Returns (people_sorted_public, counts, as_of_dt).
    """
    as_of_dt = datetime.now(timezone.utc)

    entries_by_email: dict = {}
    seen_noise: set = set()
    excluded_noise = 0

    # ---- 1. every lead (all stages); converted => purchaser ----
    leads_cursor = db.leads.find({}, ROSTER_LEAD_PROJECTION).sort("created_at", -1).limit(2000)
    async for lead in leads_cursor:
        email = (lead.get("email") or "").strip()
        if not email:
            continue
        key = email.lower()
        name = lead.get("name") or ""
        if is_noise_sender(email=email, name=name):
            if key not in seen_noise:
                seen_noise.add(key)
                excluded_noise += 1
            continue
        converted = (lead.get("stage") or "") == "converted"
        entry = {
            "kind": "purchaser" if converted else "lead",
            "name": name,
            "email": email,
            "email_key": key,
            "stage": lead.get("stage"),
            "plan": None,
            "purchased_at": None,
            "created_at": lead.get("created_at"),
            "last_activity_at": None,
            "source": lead.get("source"),
            "lead_ids": [lead.get("lead_id")] if lead.get("lead_id") else [],
            "user_id": lead.get("user_id"),
            "converted_at": lead.get("converted_at"),
            # WingPoint identity fields (projection widened to carry them)
            "wp_ref": lead.get("wp_ref"),
            "created_via": lead.get("created_via"),
        }
        existing = entries_by_email.get(key)
        if existing is None:
            entries_by_email[key] = entry
            continue
        # Dedupe by lowercase email — converted wins over a plain lead.
        if converted and existing["kind"] != "purchaser":
            entry["lead_ids"] += existing["lead_ids"]
            entries_by_email[key] = entry
        elif not converted and existing["kind"] == "purchaser":
            existing["lead_ids"] += entry["lead_ids"]

    # ---- 2. activity timeline per referenced lead (single bounded query) ----
    all_lead_ids = sorted({lid for e in entries_by_email.values() for lid in e["lead_ids"] if lid})
    last_at_by_lead: dict = {}
    stage_dt_by_lead: dict = {}
    emailish_rows_by_lead: dict = {}
    if all_lead_ids:
        acts_cursor = (
            db.lead_activities.find(
                {"lead_id": {"$in": all_lead_ids}},
                {"lead_id": 1, "action_type": 1, "content": 1, "created_at": 1},
            )
            .sort("created_at", -1)
            .limit(1000)
        )
        async for act in acts_cursor:
            lid = act.get("lead_id")
            if not lid:
                continue
            if lid not in last_at_by_lead:
                last_at_by_lead[lid] = act.get("created_at")
            dt = _as_dt(act.get("created_at"))
            atype = (act.get("action_type") or "").strip().lower()
            content_low = (act.get("content") or "").lower()
            if _is_stage_row(atype, act.get("content") or "") and dt and (
                lid not in stage_dt_by_lead or dt > stage_dt_by_lead[lid]
            ):
                stage_dt_by_lead[lid] = dt
            if atype == "email" or "sent" in content_low or "received" in content_low or "email" in content_low:
                emailish_rows_by_lead[lid] = emailish_rows_by_lead.get(lid, 0) + 1

    # ---- 3. subscription map (all paid/active) + user linkage maps ----
    subs = await db.subscriptions.find(
        {
            "$or": [
                {"status": {"$in": ["active", "trialing"]}},
                {"stripe_subscription_id": {"$nin": [None, ""]}},
            ]
        },
        {
            "_id": 0,
            "user_id": 1,
            "plan_type": 1,
            "status": 1,
            "trial_end_date": 1,
            "stripe_subscription_id": 1,
            "stripe_customer_id": 1,
            "billing_period": 1,
            "current_period_end": 1,
            "created_at": 1,
        },
    ).to_list(2000)
    paid_subs = {}
    for sub in subs:
        if sub.get("user_id") and _sub_is_paid_active(sub):
            paid_subs[sub["user_id"]] = sub

    user_ids = {e["user_id"] for e in entries_by_email.values() if e.get("user_id")}
    user_ids |= set(paid_subs.keys())
    user_by_id: dict = {}
    user_id_by_email: dict = {}
    if user_ids:
        users_cursor = db.users.find(
            {"user_id": {"$in": sorted(user_ids)}},
            {
                "_id": 0,
                "user_id": 1,
                "email": 1,
                "full_name": 1,
                "name": 1,
                "first_name": 1,
                "last_name": 1,
                # WingPoint identity fields so is_wingpoint_user() can run on the user doc
                "wp_ref": 1,
                "source": 1,
                "created_via": 1,
            },
        ).limit(2000)
        async for user in users_cursor:
            uid = user.get("user_id")
            if not uid:
                continue
            user_by_id[uid] = user
            uemail = (user.get("email") or "").strip().lower()
            if uemail and uemail not in user_id_by_email:
                user_id_by_email[uemail] = uid

    # ---- 4. finalize lead-based entries ----
    out_entries: List[dict] = []
    for entry in entries_by_email.values():
        kind = entry["kind"]
        lead_ids = entry["lead_ids"]
        # last_activity_at: newest activity across this person's lead docs
        last_raw = None
        best_dt = None
        for lid in lead_ids:
            raw = last_at_by_lead.get(lid)
            dt = _as_dt(raw)
            if dt and (best_dt is None or dt > best_dt):
                best_dt = dt
                last_raw = raw
        entry["last_activity_at"] = last_raw

        email_count = sum(emailish_rows_by_lead.get(lid, 0) for lid in lead_ids)

        if kind == "purchaser":
            # purchased_at: converted_at stamp on the lead doc first, then the
            # latest stage_change/converted activity across the person's leads
            # (falls back to None when neither is findable — never invented).
            purchased_raw = entry.get("converted_at")
            best_stage_dt: Optional[datetime] = None
            if not purchased_raw:
                for lid in lead_ids:
                    dt = stage_dt_by_lead.get(lid)
                    if dt and (best_stage_dt is None or dt > best_stage_dt):
                        best_stage_dt = dt
                purchased_raw = best_stage_dt
            entry["purchased_at"] = purchased_raw
            # plan: subscription linked by the conversion bridge's user_id
            # stamp first, then by identical email.
            sub = None
            uid = entry.get("user_id")
            linked_uid = None
            if uid and uid in paid_subs:
                sub = paid_subs[uid]
            else:
                linked_uid = user_id_by_email.get(entry["email_key"])
                if linked_uid and linked_uid in paid_subs:
                    sub = paid_subs[linked_uid]
            if sub:
                entry["plan"] = sub.get("plan_type")
                entry["_sub"] = sub
                entry["_uid"] = uid or linked_uid
        entry["email_count"] = email_count
        entry["id"] = _person_id_for_entry(entry)
        out_entries.append(entry)

    # ---- 5. subscription-only purchasers (email not already covered) ----
    for uid, sub in paid_subs.items():
        user = user_by_id.get(uid) or {}
        email = (user.get("email") or "").strip()
        if not email:
            continue
        key = email.lower()
        name = (
            user.get("full_name")
            or " ".join(p for p in (user.get("first_name"), user.get("last_name")) if p)
            or user.get("name")
            or ""
        )
        if key in entries_by_email:
            continue
        if is_noise_sender(email=email, name=name):
            if key not in seen_noise:
                seen_noise.add(key)
                excluded_noise += 1
            continue
        out_entries.append(
            {
                "kind": "purchaser",
                "name": name,
                "email": email,
                "email_key": key,
                "stage": None,
                "plan": sub.get("plan_type"),
                "purchased_at": sub.get("created_at"),
                "created_at": sub.get("created_at"),
                "last_activity_at": None,
                "source": "subscription",
                "lead_ids": [],
                "user_id": uid,
                "email_count": 0,
                "id": f"purchaser:{key}",
                # enrichment hooks (same shape as step-4 purchasers)
                "_sub": sub,
                "_uid": uid,
            }
        )

    # ---- 5b. enrichment: economics + behavior + WingPoint truth (ADDITIVE) ----
    # Every value derived from real stored data. Nothing is synthesized. Where the
    # TO product keeps no server-side record (page visits, resource downloads) the
    # list is emitted empty â never fabricated. See module docstring + lane-A report.
    purchaser_uids = [
        e.get("_uid") for e in out_entries
        if e.get("kind") == "purchaser" and e.get("_uid")
    ]
    stored_paid: dict = {}
    if purchaser_uids:
        txn_cursor = (
            db.payment_transactions.find(
                {
                    "user_id": {"$in": purchaser_uids},
                    "payment_status": {"$in": list(PAID_STATUSES)},
                },
                {"_id": 0, "user_id": 1, "amount": 1, "created_at": 1},
            )
            .sort("created_at", -1)
            .limit(2000)
        )
        async for txn in txn_cursor:
            uid = txn.get("user_id")
            if uid is not None and uid not in stored_paid:
                stored_paid[uid] = txn  # newest first per user

    # Signup rows (newsletter/course + fiduciary assessment) matched by email.
    all_emails = [e["email"] for e in out_entries if e.get("email")]
    signups_by_email: dict = {}
    if all_emails:
        async for cl in db.course_leads.find(
            {"email": {"$in": all_emails}},
            {"_id": 0, "email": 1, "source": 1, "created_at": 1,
             "course_purchased": 1, "lesson_1_watched": 1},
        ):
            e = (cl.get("email") or "").lower()
            signups_by_email.setdefault(e, []).append({
                "kind": "newsletter",
                "source": cl.get("source"),
                "created_at": _iso(cl.get("created_at")),
                "detail": {
                    "course_purchased": cl.get("course_purchased"),
                    "lesson_1_watched": cl.get("lesson_1_watched"),
                },
            })
        async for fa in db.fiduciary_assessments.find(
            {"email": {"$in": all_emails}},
            {"_id": 0, "email": 1, "assessment_id": 1, "score": 1, "created_at": 1},
        ):
            e = (fa.get("email") or "").lower()
            signups_by_email.setdefault(e, []).append({
                "kind": "assessment",
                "source": "fiduciary-assessment",
                "created_at": _iso(fa.get("created_at")),
                "detail": {
                    "assessment_id": fa.get("assessment_id"),
                    "score": fa.get("score"),
                },
            })

    # Per-purchaser economics: current price + last payment + next due.
    economics_by_id: dict = {}
    for entry in out_entries:
        if entry["kind"] != "purchaser":
            continue
        uid = entry.get("_uid")
        sub = entry.get("_sub") or {}
        plan_type = entry.get("plan")
        billing_period = sub.get("billing_period")
        txn = stored_paid.get(uid) if uid else None
        last_paid_at = _iso(txn.get("created_at")) if txn else None
        last_amount_cents = _to_cents(txn.get("amount")) if txn else None
        # Stripe Invoice fallback ONLY when the stored trail is empty.
        if last_paid_at is None and sub.get("stripe_customer_id"):
            fb_at, fb_cents = _last_paid_from_stripe(sub["stripe_customer_id"])
            last_paid_at = last_paid_at or fb_at
            last_amount_cents = last_amount_cents if last_amount_cents is not None else fb_cents
        economics_by_id[entry["id"]] = {
            "product": _product_label(plan_type),
            "amount_cents": _amount_cents_for(plan_type, billing_period),
            "billing_period": billing_period,
            "last_paid_at": last_paid_at,
            "last_amount_cents": last_amount_cents,
            # subscription current_period_end; null when lifetime/one-off or when
            # the Stripe-managed period end is only computed live (not persisted).
            "next_due_at": _iso(sub.get("current_period_end")),
        }

    # WingPoint truth + signups for EVERY entry (behavior available or not).
    for entry in out_entries:
        email_key = entry.get("email_key") or (entry.get("email") or "").lower()
        if entry["kind"] == "purchaser":
            identity_doc = user_by_id.get(entry.get("_uid")) or {}
            wp_product = entry.get("plan") in WP_PLAN_TYPES
        else:
            identity_doc = {
                "source": entry.get("source"),
                "wp_ref": entry.get("wp_ref"),
                "created_via": entry.get("_created_via"),
            }
            wp_product = False
        entry["_wp_origin"] = bool(is_wingpoint_user(identity_doc))
        entry["_wp_product"] = wp_product
        entry["_signups"] = signups_by_email.get(email_key, [])

    # ---- 6. sort (purchasers first by recency, leads by last_activity desc) ----
    def _sort_key(entry: dict):
        rank = 0 if entry["kind"] == "purchaser" else 1
        dt = _entry_recency(entry)
        return (rank, -(dt.timestamp() if dt else 0.0))

    out_entries.sort(key=_sort_key)

    # ---- 7. counts (public projection) ----
    by_stage: dict = {}
    for entry in out_entries:
        if entry["kind"] != "purchaser" and entry.get("stage"):
            by_stage[entry["stage"]] = by_stage.get(entry["stage"], 0) + 1
    counts = {
        "purchasers": sum(1 for e in out_entries if e["kind"] == "purchaser"),
        "leads": sum(1 for e in out_entries if e["kind"] == "lead"),
        "by_stage": by_stage,
        "excluded_noise": excluded_noise,
    }

    public_people = [
        {
            "id": entry["id"],
            "kind": entry["kind"],
            "name": entry["name"] or "",
            "email": entry["email"],
            "stage": entry["stage"] if entry["kind"] == "lead" else None,
            "plan": entry["plan"],
            "purchased_at": entry["purchased_at"] if entry["kind"] == "purchaser" else None,
            "created_at": entry["created_at"],
            "last_activity_at": entry["last_activity_at"],
            "source": entry["source"],
            "email_count": entry.get("email_count", 0),
            # ---- additive enrichment (P2 deepen; all derived from stored data) ----
            # purchaser economics (null for leads)
            "product": economics_by_id.get(entry["id"], {}).get("product"),
            "amount_cents": economics_by_id.get(entry["id"], {}).get("amount_cents"),
            "billing_period": economics_by_id.get(entry["id"], {}).get("billing_period"),
            "last_paid_at": economics_by_id.get(entry["id"], {}).get("last_paid_at"),
            "last_amount_cents": economics_by_id.get(entry["id"], {}).get("last_amount_cents"),
            "next_due_at": economics_by_id.get(entry["id"], {}).get("next_due_at"),
            # WingPoint truth (single source: is_wingpoint_user)
            "wp_origin": entry.get("_wp_origin", False),
            "wp_product": entry.get("_wp_product", False),
            # behavior: page_events/resources not stored server-side -> empty;
            # signups matched by email from course_leads + fiduciary_assessments.
            "behavior": {
                "page_events": [],
                "resources": [],
                "signups": entry.get("_signups", []),
            },
        }
        for entry in out_entries
    ]
    return public_people, counts, as_of_dt


# ==================== ENDPOINTS ====================


@router.get("")
async def get_people_roster():
    """Full people roster for the OS people card (P2 contract)."""
    people, counts, as_of_dt = await _load_roster()
    return {"people": people, "counts": counts, "as_of": as_of_dt.isoformat()}


@router.get("/counts")
async def get_people_counts():
    """Cheap counts-only view (same counts dict as the roster)."""
    people, counts, as_of_dt = await _load_roster()
    return {"counts": counts, "as_of": as_of_dt.isoformat()}


@router.get("/{person_id}/emails")
async def get_person_emails(person_id: str, email: str = "", name: str = ""):
    """Latest 10 email records for one person id.

    Unknown/missing ids are NOT 404s: the contract says unknown persons get
    a 200 with an empty emails list and the person echoed from the path plus
    whatever name/email arrived as query params.
    """
    as_of_dt = datetime.now(timezone.utc)
    person, _lead, _user, activity_query = await _resolve_person(
        person_id, email=email, name=name
    )
    emails = await _person_email_rows(person, activity_query)
    return {
        "person": {
            "id": person["id"],
            "name": person["name"] or "",
            "email": person["email"] or "",
        },
        "emails": emails,
        "as_of": as_of_dt.isoformat(),
    }


@router.get("/{person_id}/detail")
async def get_person_detail(person_id: str, email: str = "", name: str = ""):
    """P3 bounded per-person bundle for the OS People page detail view.

    Identity (name/email/phone/company) + stage/status + latest emails +
    contact-history activities (the /admin/leads activity log shape, incl.
    video opens/watches, downloads, booked_call) + stored notes + stored
    tasks + next_action.

    Unknown/missing ids are NOT 404s: same contract as /emails — a 200 with
    an empty bundle, person echoed from the path + query params, all lists
    empty, identity keys present but blank. Bounded: <=10 emails, <=50
    activities, <=20 stored notes, <=20 stored tasks, newest first
    everywhere, content capped at ACTIVITY_CONTENT_LIMIT; degrades honestly
    (phone/company blank when the source docs never carried them) and never
    invents data.

    "notes"/"tasks" are P4 server-side store rows (people_notes /
    people_tasks, keyed by the EXACT person id) — the OS card's write path.
    The legacy lead-activity note rows ("note_added"/"manual") remain visible
    up in `activities`.
    """
    as_of_dt = datetime.now(timezone.utc)
    person, lead, user, activity_query = await _resolve_person(
        person_id, email=email, name=name
    )

    emails = await _person_email_rows(person, activity_query)

    # ---- contact history: admin activity-log rows, newest first, capped ----
    activities: List[dict] = []
    if activity_query:
        act_cursor = (
            db.lead_activities.find(activity_query, DETAIL_ACTIVITY_PROJECTION)
            .sort("created_at", -1)
            .limit(PEOPLE_DETAIL_ACT_LIMIT)
        )
        async for act in act_cursor:
            activities.append(_activity_view(act))

    # ---- identity + stage/status (empty/None when nothing is known) ----
    identity = {
        "id": person["id"],
        "kind": "purchaser" if person_id.startswith("purchaser:") else "lead",
        "name": person["name"] or "",
        "email": person["email"] or "",
        "phone": (lead.get("phone") if lead else None) or "",
        "company": (lead.get("company") if lead else None) or "",
    }
    status = {
        "stage": (lead.get("stage") if lead else None),
        "source": (lead.get("source") if lead else None),
        "created_at": lead.get("created_at") if lead else None,
        "updated_at": lead.get("updated_at") if lead else None,
        "converted_at": lead.get("converted_at") if lead else None,
        "user_id": (lead.get("user_id") if lead else None)
        or (user.get("user_id") if user else None),
        "booked_call": (lead.get("booked_call") if lead else None),
        "call_outcome": (lead.get("call_outcome") if lead else None),
    }

    notes = await _store_person_notes(person_id)
    tasks = await _store_person_tasks(person_id)
    return {
        "person": identity,
        "status": status,
        "emails": emails[:PEOPLE_DETAIL_EMAIL_LIMIT],
        "activities": activities,
        "notes": notes,
        "tasks": tasks,
        "next_action": lead.get("next_action") if lead else None,
        "as_of": as_of_dt.isoformat(),
    }


# ==================== PERSON NOTES / TASKS STORE (P4 writes) ====================
# Server-side store behind the OS people card (Jeff's flow: add a note or a
# task on any person card — lead or purchaser — flip the task, refresh the
# page, everything is still there). Rows live in people_notes / people_tasks,
# keyed by the person id EXACTLY as the OS sent it; the legacy lead-activity
# log gets a best-effort 'manual' side-log for lead: notes so the admin
# timeline keeps its history. This is the primary store; the OS host's
# Mac-local crm.db is a best-effort side-write at the OS layer, never a
# dependency of these routes.


@router.get("/{person_id}/notes")
async def get_person_notes(person_id: str):
    """Newest-first stored notes for the exact person id (empty when none).

    Unknown ids are NOT 404s — same contract as /emails: a person with no
    notes yet is just an empty list. The id is matched EXACTLY as stored,
    colon-prefixed forms included.
    """
    as_of_dt = datetime.now(timezone.utc)
    notes = await _store_person_notes(person_id)
    return {"person_id": person_id, "notes": notes, "as_of": as_of_dt.isoformat()}


@router.get("/{person_id}/tasks")
async def get_person_tasks(person_id: str):
    """Newest-first stored tasks for the exact person id (empty when none)."""
    as_of_dt = datetime.now(timezone.utc)
    tasks = await _store_person_tasks(person_id)
    return {"person_id": person_id, "tasks": tasks, "as_of": as_of_dt.isoformat()}


@router.post("/{person_id}/note")
async def add_person_note(person_id: str, body: PersonNoteRequest):
    """Append a note to the store, keyed by the EXACT person id sent.

    Convenience side-log: when person_id is a colon-prefixed lead id and no
    people_notes row exists for it yet, the note ALSO lands in the legacy
    lead-activity log via the same '_log_activity("manual", ...)' path the
    admin notes use — with the BARE lead id, so it never 404s the class of
    bare-vs-prefixed id mismatches. Best-effort: a miss there never fails
    the note itself.
    """
    text = (body.text or "").strip()
    if not text or len(text) > PEOPLE_NOTE_TEXT_LIMIT:
        raise HTTPException(
            status_code=400,
            detail=(
                "text must be a non-empty string between 1 and "
                f"{PEOPLE_NOTE_TEXT_LIMIT} characters"
            ),
        )
    now = datetime.now(timezone.utc)
    note_id = f"pn_{uuid.uuid4().hex[:12]}"
    await db.people_notes.insert_one(
        {
            "note_id": note_id,
            "person_id": person_id,
            "text": text,
            "at": now,
            "source": "os_service",
        }
    )
    bare = _bare_lead_id(person_id)
    side_logged = False
    if bare is not None:
        # First stored note for this colon id only — repeat notes live in the
        # store and must not double-log in the legacy lead timeline.
        existing = await db.people_notes.count_documents({"person_id": person_id})
        if existing <= 1:
            side_logged = await _side_log_lead_activity(bare, text)
    return {
        "success": True,
        "note": {"id": note_id, "text": text, "at": now.isoformat()},
        "side_logged": side_logged,
    }


@router.post("/{person_id}/task")
async def add_person_task(person_id: str, body: PersonTaskRequest):
    """Append a task to the store, keyed by the EXACT person id sent."""
    title = (body.title or "").strip()
    if not title or len(title) > PEOPLE_TASK_TITLE_LIMIT:
        raise HTTPException(
            status_code=400,
            detail=(
                "title must be a non-empty string between 1 and "
                f"{PEOPLE_TASK_TITLE_LIMIT} characters"
            ),
        )
    status = (body.status or "open").strip().lower()
    if status not in PEOPLE_TASK_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="Unknown task status — expected one of: "
            + ", ".join(PEOPLE_TASK_STATUSES) + ".",
        )
    now = datetime.now(timezone.utc)
    task_id = f"pt_{uuid.uuid4().hex[:12]}"
    await db.people_tasks.insert_one(
        {
            "task_id": task_id,
            "person_id": person_id,
            "title": title,
            "status": status if status == "done" else "open",
            "at": now,
            "source": "os_service",
        }
    )
    return {
        "success": True,
        "task": {"id": task_id, "title": title, "status": status if status == "done" else "open", "at": now.isoformat()},
    }


@router.post("/{person_id}/task-status")
async def set_person_task_status(person_id: str, body: PersonTaskStatusRequest):
    """Flip one stored task's status (404 when the task id is unknown)."""
    status = (body.status or "").strip().lower()
    if status not in PEOPLE_TASK_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="Unknown task status — expected one of: "
            + ", ".join(PEOPLE_TASK_STATUSES) + ".",
        )
    task_id = (body.task_id or "").strip()
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id is required")
    now = datetime.now(timezone.utc)
    result = await db.people_tasks.update_one(
        {"task_id": task_id, "person_id": person_id},
        {"$set": {"status": status, "updated_at": now}},
    )
    if result.matched_count == 0:
        raise HTTPException(
            status_code=404,
            detail="That task isn't on this person's card anymore.",
        )
    return {"success": True, "task_id": task_id, "status": status}
