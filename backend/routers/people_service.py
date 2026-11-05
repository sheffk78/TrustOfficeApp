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
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends

from database import db
from routers.leads_service import (
    ACTIVITY_CONTENT_LIMIT,
    LEAD_PROJECTION,
    _activity_view,
    require_leads_service,
)

logger = logging.getLogger(__name__)

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
}

# ---- P3 (per-person detail bundle) ----
PEOPLE_DETAIL_EMAIL_LIMIT = 10   # newest email records in the bundle
PEOPLE_DETAIL_ACT_LIMIT = 50     # activity rows: contact history incl. video/downloads
PEOPLE_DETAIL_NOTE_LIMIT = 10    # latest notes (note_added rows)
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
    return f"lead:{entry.get('lead_id') or entry['email_key']}"


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
            if uid and uid in paid_subs:
                sub = paid_subs[uid]
            else:
                linked_uid = user_id_by_email.get(entry["email_key"])
                if linked_uid and linked_uid in paid_subs:
                    sub = paid_subs[linked_uid]
            if sub:
                entry["plan"] = sub.get("plan_type")
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
            }
        )

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
    video opens/watches, downloads, booked_call) + latest notes + next_action.

    Unknown/missing ids are NOT 404s: same contract as /emails — a 200 with
    an empty bundle, person echoed from the path + query params, all lists
    empty, identity keys present but blank. Bounded: <=10 emails, <=50
    activities, <=10 notes, newest first everywhere, content capped at
    ACTIVITY_CONTENT_LIMIT; degrades honestly (phone/company blank when the
    source docs never carried them) and never invents data.

    "Notes" are the two canonical note writes: admin PATCH-notes rows
    (action_type "note_added") and note-style rows (action_type "manual").
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

    # ---- latest notes: bounded note-action rows, newest first ----
    notes: List[dict] = []
    if activity_query:
        note_cursor = (
            db.lead_activities.find(
                {**activity_query, "action_type": {"$in": list(NOTE_ACTION_TYPES)}},
                DETAIL_NOTE_PROJECTION,
            )
            .sort("created_at", -1)
            .limit(PEOPLE_DETAIL_NOTE_LIMIT)
        )
        async for note in note_cursor:
            notes.append(_activity_view(note))

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

    return {
        "person": identity,
        "status": status,
        "emails": emails[:PEOPLE_DETAIL_EMAIL_LIMIT],
        "activities": activities,
        "notes": notes,
        "next_action": lead.get("next_action") if lead else None,
        "as_of": as_of_dt.isoformat(),
    }
