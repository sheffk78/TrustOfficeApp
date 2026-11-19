"""TrustOffice "leads service" lane (Phase 1).

Scoped, service-to-service endpoints consumed by the Agentic OS overview
card (Kit's command center) and the Bland.ai calling assistant. Authenticated
with a single static service key sent in the `X-Service-Key` header — NOT a
user JWT. The OS backend calls these server-side, so no browser CORS is
opened here.

Founder fallback email (2026-11-18): after a successful AI-call outcome write,
an instant actionable email goes to the founder (Jeff) when
  (a) disposition == callback_requested, OR
  (b) disposition == booked with NO confirmed booking_ref.
It is the backup channel for direct in-call bookings that fail — the booking
app already auto-notifies for direct bookings, so booked-with-ref never
triggers it. Dedupe: max 1 email per lead per 6 hours (activity marker
`fallback_email_sent`); send runs as a FastAPI background task (never blocks
nor fails the call-outcome response; failures mark `fallback_email_failed`).
Recipient: TRUSTOFFICE_FALLBACK_EMAIL (default kenneth@agentictrust.app;
set it EMPTY to disable the feature — kill switch).

Endpoints (mounted under /api/service/leads):
  GET  /latest                 -> 3 newest leads + each lead's 3 latest activities
  GET  /queue                  -> Bland calling queue: leads with a phone in
                                  call-eligible stages (new/engaged/warm/
                                  registered), oldest first, paginated. Leads
                                  called within BLAND_RETRY_COOLDOWN_HOURS
                                  (default 24h) are excluded and surfaced as
                                  meta "cooldown"; claimed leads stay in the
                                  payload with claimed_by/claimed_until and
                                  are surfaced as meta "claimed".
  GET  /{lead_id}              -> single lead + up to 10 activities (Bland
                                  resolves a lead before dialing)
  POST /{lead_id}/call-outcome -> record an AI call disposition (+ stage
                                  transitions: opt_out/interested/booked);
                                  stamps last_ai_call_at + ai_call_attempts
                                  for the cooldown guard
  POST /{lead_id}/claim        -> Bland worker claims a lead before dispatch
                                  (TTL auto-release; 409 when someone else
                                  holds an unexpired claim)
  DELETE /{lead_id}/claim      -> explicit release after the outcome
  POST /{lead_id}/note         -> append a manual note (through the same
                                  _log_activity helper the admin notes use)
  PATCH /{lead_id}/stage       -> set stage (validated) + log a system activity

Bland's call-completed webhook receiver lives in routers/bland_webhook.py
(mounted at /api/service/bland/webhook) and reuses _apply_call_outcome below.
"""
import html
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from pymongo import ReturnDocument

from database import db
from email_service import email_service as _email_service
from routers.leads import LEAD_STAGES, _log_activity

logger = logging.getLogger(__name__)

# Service key header (constant-time compare against TRUSTOFFICE_LEADS_SERVICE_KEY).
SERVICE_KEY_HEADER = APIKeyHeader(name="X-Service-Key", auto_error=False)

# Projected lead fields returned to the OS card (never the Mongo _id).
LEAD_PROJECTION = {
    "_id": 0,
    "lead_id": 1,
    "name": 1,
    "email": 1,
    "phone": 1,
    "stage": 1,
    "source": 1,
    "created_at": 1,
    "updated_at": 1,
    "notes": 1,
}

# Activity feed display cap (read-side render; storage is always full content).
# 2026-11-18: AI-call summaries from Bland were being cut at ~150 visible chars
# — our chain was the cutter (this view cap at 160). Raised so a call-outcome
# summary of the full validated allowance (CALL_SUMMARY_MAX = 500) always
# displays uncut: "AI call via Bland: {disposition}" prefix + " — {summary}" +
# optional " ({sec}s)" stays under 600.
ACTIVITY_CONTENT_LIMIT = 600
# POST /{lead_id}/call-outcome accepted summary length (agent retry hardening,
# 2026-11-18): call-outcome summaries above this reject with 400, never
# truncate; anything ≤ 500 renders uncut in activity feeds (see cap above).
CALL_SUMMARY_MAX = 500


# ==================== FOUNDER FALLBACK EMAIL (2026-11-18) ====================
# Instant backup channel for AI-call bookings that did not land: the founder
# (Jeff) emails/confirm-manually within minutes. Deterministic trigger in
# _apply_call_outcome (shared by the call-outcome endpoint AND the Bland
# webhook receiver) so behavior is identical on both paths.

# Recipient at request time. Kill switch: set TRUSTOFFICE_FALLBACK_EMAIL to an
# EMPTY string to disable the feature entirely (tests use this); unset uses
# the founder default.
FOUNDER_FALLBACK_EMAIL_DEFAULT = "kenneth@agentictrust.app"
EMAIL_TAG_FALLBACK = "ai-call-fallback"
# Anti-spam: max 1 fallback email per lead per 6 hours — dedupe checks the
# most recent `fallback_email_sent` activity marker's timestamp.
FALLBACK_EMAIL_DEDUPE_HOURS = 6
# Confirm/hold link for the founder (booking app, 14-day window).
BOOKING_SLOTS_URL_DEFAULT = (
    "https://booking-trustoffice-production.up.railway.app/slots?days=14"
)

# Slot date-time phrase extraction (best-effort, deterministic): a chunk of
# the call summary that contains BOTH a day-ish token and a time token is
# surfaced to the founder as "Reported agreed slot: <phrase>".
_SLOT_DAY_RE = re.compile(
    r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"
    r"|\b(?:january|february|march|april|may|june|july|august"
    r"|september|october|november|december)\s+\d{1,2}(?:st|nd|rd|th)?\b"
    r"|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b"
    r"|\b(?:today|tomorrow|tonight)\b",
    re.IGNORECASE,
)
# 12h clock with am/pm, or 24h clock (not a duration like "3:25 minutes").
_SLOT_TIME_RE = re.compile(
    r"\b\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)\b"
    r"|\b(?:[01]?\d|2[0-3]):[0-5]\d\b(?!\s*(?:min|mins|minutes|sec|seconds|hrs|hours)\b)",
    re.IGNORECASE,
)
_SLOT_MAX_CHARS = 120


def _fallback_recipient() -> str:
    """Founder email at request time; empty string disables the feature."""
    raw = os.environ.get("TRUSTOFFICE_FALLBACK_EMAIL")
    if raw is None:
        return FOUNDER_FALLBACK_EMAIL_DEFAULT
    return raw.strip()


def _booking_slots_url() -> str:
    raw = (os.environ.get("TRUSTOFFICE_BOOKING_SLOTS_URL") or "").strip()
    return raw or BOOKING_SLOTS_URL_DEFAULT


def _fallback_email_due(disposition: str, booking_ref: Optional[str]) -> bool:
    """Deterministic trigger rule: callback_requested, or booked unconfirmed.

    booked WITH a booking_ref is a verified direct booking — the booking app
    already auto-notifies those, so the fallback must NOT double-fire.
    """
    if disposition == "callback_requested":
        return True
    if disposition == "booked" and not (booking_ref or "").strip():
        return True
    return False


def _fallback_reason(disposition: str, booking_ref: Optional[str]) -> str:
    if disposition == "callback_requested":
        return 'the AI call ended with disposition "callback_requested"'
    if disposition == "booked":
        return (
            'the AI call reported "booked" but no booking reference was '
            "confirmed — the direct booking is NOT verified"
        )
    return f"AI call disposition: {disposition}"


def _extract_slot(text: str) -> Optional[str]:
    """Best-effort date-time phrase out of a call summary (or None).

    Splits the summary into sentence-ish chunks and returns the first chunk
    holding both a day-ish token and a time token, trimmed to the phrase
    spanning both tokens ("Tuesday, November 24 at 2:00 PM").
    """
    for chunk in re.split(r"[.;\n]", text or ""):
        day = _SLOT_DAY_RE.search(chunk)
        time_m = _SLOT_TIME_RE.search(chunk)
        if not (day and time_m):
            continue
        start = min(day.start(), time_m.start())
        end = max(day.end(), time_m.end())
        phrase = chunk[start:end].strip(" ,:-")
        phrase = re.sub(r"^(?:on|at|for|around|maybe)\s+", "", phrase,
                        flags=re.IGNORECASE)
        if phrase:
            return phrase[:_SLOT_MAX_CHARS]
    return None


def _fallback_email_subject(lead: dict, disposition: str) -> str:
    name = ((lead or {}).get("name") or "").strip()
    return f"[AI CALL] {name or 'Unknown lead'} — {disposition}"


def _fallback_email_text(lead: dict, disposition: str, summary: str,
                         booking_ref: Optional[str]) -> str:
    """Plain-text body: lead identity, FULL summary, slot (if any), CTA."""
    slot = _extract_slot(summary)
    lines = ["AI CALL — instant founder fallback (TrustOffice leads)", ""]
    if slot:
        lines += [f"Reported agreed slot: {slot}", ""]
    lines += [
        f"Fallback reason: {_fallback_reason(disposition, booking_ref)}",
        "",
        "LEAD",
        f"  name:    {((lead or {}).get('name') or '').strip() or 'n/a'}",
        f"  email:   {(lead or {}).get('email') or 'n/a'}",
        f"  phone:   {(lead or {}).get('phone') or 'n/a'}",
        f"  stage:   {(lead or {}).get('stage') or 'n/a'}",
        f"  lead_id: {(lead or {}).get('lead_id') or 'n/a'}",
        "",
        f"CALL SUMMARY (disposition: {disposition})",
        (summary or "").strip() or "(no summary captured)",
        "",
        f"Confirm/hold the slot now: {_booking_slots_url()}",
        "",
        "(Automated backup channel from TrustOfficeApp — sent because the "
        "outcome matched the fallback trigger. The booking app still sends "
        "its own notice for direct confirmed bookings.)",
    ]
    return "\n".join(lines)


def _fallback_email_html(lead: dict, disposition: str, summary: str,
                         booking_ref: Optional[str]) -> str:
    """HTML body mirroring the text body; slot line prominent when present."""
    esc = html.escape
    slot = _extract_slot(summary)
    name = esc(((lead or {}).get("name") or "").strip() or "n/a")
    email = esc((lead or {}).get("email") or "n/a")
    phone = esc((lead or {}).get("phone") or "n/a")
    stage = esc((lead or {}).get("stage") or "n/a")
    lead_id = esc((lead or {}).get("lead_id") or "n/a")
    summary_escaped = esc((summary or "").strip() or "(no summary captured)")
    reason = esc(_fallback_reason(disposition, booking_ref))
    url = esc(_booking_slots_url())
    slot_html = (
        f'<p style="margin:0 0 12px;font-size:17px;font-weight:700;'
        f'color:#b45309">Reported agreed slot: {esc(slot)}</p>'
        if slot else ""
    )
    return (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;'
        'color:#1f2937;max-width:640px">'
        '<h2 style="margin:0 0 8px;font-size:18px">AI call — instant founder'
        ' fallback (TrustOffice leads)</h2>'
        f"{slot_html}"
        f'<p style="margin:0 0 16px;color:#374151">Fallback reason: {reason}</p>'
        '<table style="border-collapse:collapse;font-size:14px">'
        f"<tr><td style='padding:2px 12px 2px 0;color:#6b7280'>name</td>"
        f"<td style='padding:2px 0'>{name}</td></tr>"
        f"<tr><td style='padding:2px 12px 2px 0;color:#6b7280'>email</td>"
        f"<td style='padding:2px 0'>{email}</td></tr>"
        f"<tr><td style='padding:2px 12px 2px 0;color:#6b7280'>phone</td>"
        f"<td style='padding:2px 0'>{phone}</td></tr>"
        f"<tr><td style='padding:2px 12px 2px 0;color:#6b7280'>stage</td>"
        f"<td style='padding:2px 0'>{stage}</td></tr>"
        f"<tr><td style='padding:2px 12px 2px 0;color:#6b7280'>lead_id</td>"
        f"<td style='padding:2px 0'>{lead_id}</td></tr>"
        "</table>"
        f'<p style="margin:16px 0 4px;font-weight:600">Call summary —'
        f" disposition: {esc(disposition)}</p>"
        f'<blockquote style="margin:0 0 16px;padding:8px 12px;border-left:'
        f'3px solid #d1d5db;white-space:pre-wrap">{summary_escaped}</blockquote>'
        f'<p style="margin:0 0 8px">Confirm/hold the slot now: '
        f'<a href="{url}">{url}</a></p>'
        '<p style="margin:16px 0 0;color:#6b7280;font-size:12px">Automated '
        "backup channel from TrustOfficeApp — outcome matched the fallback "
        "trigger. The booking app still sends its own notice for direct "
        "confirmed bookings.</p>"
        "</div>"
    )


async def _send_founder_fallback_email(
    lead_id: str,
    *,
    disposition: str,
    summary: str = "",
    booking_ref: Optional[str] = None,
) -> None:
    """Send the founder fallback email for one outcome + record the marker.

    Runs as a FastAPI background task (or inline for direct helper callers) —
    NEVER blocks or fails the call-outcome response. Dedupes on the
    `fallback_email_sent` activity marker (max 1 per lead per 6 hours);
    provider status != "sent" (incl. not-configured) records
    `fallback_email_failed` instead, so a later legit trigger can retry.
    """
    recipient = _fallback_recipient()
    if not recipient:
        return
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(
            hours=FALLBACK_EMAIL_DEDUPE_HOURS
        )
        recent = await db.lead_activities.find_one(
            {
                "lead_id": lead_id,
                "action_type": "fallback_email_sent",
                "created_at": {"$gte": cutoff},
            }
        )
        if recent:
            logger.info(
                "Founder fallback email suppressed for %s (sent at %s, "
                "dedupe window %sh)", lead_id, recent.get("created_at"),
                FALLBACK_EMAIL_DEDUPE_HOURS,
            )
            return
        lead = await db.leads.find_one(
            {"lead_id": lead_id},
            {"_id": 0, "lead_id": 1, "name": 1, "email": 1, "phone": 1,
             "stage": 1},
        )
        if not lead:
            logger.warning(
                "Founder fallback email skipped for %s: lead not found",
                lead_id,
            )
            return
        result = await _email_service.send_email(
            to_email=recipient,
            subject=_fallback_email_subject(lead, disposition),
            html_body=_fallback_email_html(lead, disposition, summary,
                                           booking_ref),
            text_body=_fallback_email_text(lead, disposition, summary,
                                           booking_ref),
            to_name="Jeff",
            tag=EMAIL_TAG_FALLBACK,
            metadata={
                "lead_id": lead_id[:20],
                "disposition": disposition[:20],
            },
        )
        if isinstance(result, dict) and result.get("status") == "sent":
            msg_id = str(result.get("message_id") or "").strip()
            marker = f"Founder fallback email sent — {disposition}"
            marker += f" — postmark {msg_id}" if msg_id else ""
            await _log_activity(lead_id, "fallback_email_sent", marker)
        else:
            err = ""
            if isinstance(result, dict):
                err = str(result.get("error") or result.get("reason")
                          or "unknown provider status")
            await _log_activity(
                lead_id,
                "fallback_email_failed",
                f"Founder fallback email failed — {disposition}: "
                f"{err[:300]}",
            )
            logger.warning("Founder fallback email failed for %s: %s",
                           lead_id, err)
    except Exception:  # noqa: BLE001 — must never propagate to the response
        logger.exception("Founder fallback email pipeline error for %s",
                         lead_id)
        try:
            await _log_activity(
                lead_id, "fallback_email_failed",
                "Founder fallback email pipeline error (see server logs)",
            )
        except Exception:  # noqa: BLE001 — last resort, log only
            logger.exception(
                "Could not record fallback_email_failed for %s", lead_id
            )


# ==================== AUTH ====================

async def require_leads_service(service_key: str = Depends(SERVICE_KEY_HEADER)) -> str:
    """Gate every endpoint on the scoped service key.

    Reads the expected key at request time (not import time) so test/live
    envs can supply it without reloading the module.
    """
    expected = os.environ.get("TRUSTOFFICE_LEADS_SERVICE_KEY")
    if not expected:
        # Service key not provisioned in this environment.
        raise HTTPException(status_code=503, detail="leads service not configured")
    if not service_key:
        raise HTTPException(
            status_code=401,
            detail="Missing service key. Send the key in the X-Service-Key header.",
        )
    if not secrets.compare_digest(service_key, expected):
        raise HTTPException(status_code=401, detail="Invalid service key")
    return service_key


# ==================== MODELS ====================

class ServiceNoteRequest(BaseModel):
    content: str


class ServiceStageRequest(BaseModel):
    stage: str


# Valid dispositions the Bland.ai agent can report back after a call.
CALL_DISPOSITIONS = [
    "interested",
    "booked",
    "not_interested",
    "opt_out",
    "voicemail",
    "no_answer",
    "callback_requested",
]

# Stages a lead must be in to appear in the Bland calling queue. do_not_call
# (opt-out) and lost (went cold) are deliberately excluded — never re-call.
CALLABLE_STAGES = ["new", "engaged", "warm", "registered"]

# Set form for the webhook mapping layer (routers/bland_webhook.py); same
# vocabulary as CALL_DISPOSITIONS, order-independent membership checks.
WEBHOOK_DISPOSITIONS = set(CALL_DISPOSITIONS)


# ---------------------------------------------------------------------------
# Jeff's annoyance-proof suppression rules (server-side)
#
# These live in the shared queue logic so the no-param path and every tier
# path inherit them â no dispatcher behavior can violate them:
#   1. APPOINTMENT/CONSULT SUPPRESSION (permanent): any lead with a
#      lead_activities action_type `booked_call` is never queued again.
#   2. HUMAN-TOUCH PAUSE: a lead whose latest activity is human-style
#      (not "AI call via Bland: ...-prefixed and not system/bookkeeping:
#      booked_call, booking_reminder_*, fallback_email_sent/failed,
#      diagnostic notes) is paused â the queue never talks over a human.
#   3. THIRTY-DAY ATTEMPT CAP: >= 3 ok==true bland_call_log entries per
#      lead_id within the last 30 days exhausts the lead; failed Bland
#      submissions do not count.
#
# Meta (additive, on top of cooldown/claimed): suppressed_booked,
# suppressed_human_touch, exhausted_30d. Lead shapes are otherwise
# byte-identical.
# ---------------------------------------------------------------------------

AI_CALL_PREFIX = "AI call via Bland:"

# System/bookkeeping activity types that are never "human touches".
BOOKED_CALL_ACTION = "booked_call"
SYSTEM_ACTION_TYPES = {
    BOOKED_CALL_ACTION,
    "fallback_email_sent",
    "fallback_email_failed",
}
REMINDER_ACTION_PREFIX = "booking_reminder_"

# Explicit human-touch indicators (whitelist). A lead pauses only when its
# latest activity matches one of these explicitly human-logged types; every
# other activity -- AI call reports, system/bookkeeping types, reminders,
# diagnostics, AND automated production types (email via MailerCloud,
# Facebook lead capture, CRM create, ...) that are not on the system list --
# keeps the lead callable. The old blacklist treated every unlisted type as
# human, which false-positive paused nearly all leads once the CRM vocabulary
# outgrew the short exemption list (production regression: queue count 0,
# suppressed_human_touch=102).
HUMAN_ACTION_TYPES = {"manual", "note"}

THIRTY_DAYS = timedelta(days=30)
ATTEMPT_CAP_30D = 3


def _is_ai_call_activity(activity: dict) -> bool:
    """True when the activity content is an AI call report from Bland."""
    content = activity.get("content") or ""
    return content.startswith(AI_CALL_PREFIX)


def _is_system_activity(activity: dict) -> bool:
    """True when the activity is system/bookkeeping, never a human touch."""
    at = activity.get("action_type") or ""
    if at in SYSTEM_ACTION_TYPES or at.startswith(REMINDER_ACTION_PREFIX):
        return True
    content = activity.get("content") or ""
    return "diagnostic" in content.lower()


def _latest_activity_is_human(latest: Optional[dict]) -> bool:
    """True only when the latest activity is a genuine human touch (whitelist).

    AI-prefixed and system/bookkeeping latest activities keep the lead
    callable. A lead pauses only when its latest activity is explicitly
    human-logged (action_type manual/note with non-AI, non-diagnostic
    content). Automated production types (email, facebook_lead, created, ...)
    that are not on the system exemption list are treated as system -- they
    never trigger the human-touch pause.
    """
    if latest is None:
        return False
    if _is_ai_call_activity(latest):
        return False
    if _is_system_activity(latest):
        return False
    at = latest.get("action_type") or ""
    return at in HUMAN_ACTION_TYPES


class CallOutcomeRequest(BaseModel):
    disposition: str
    summary: str = ''
    booking_ref: Optional[str] = Field(default=None, max_length=200)
    opt_out: bool = False
    call_duration_sec: Optional[int] = None


# ---- Batch-mode dedupe guard (claim / cooldown) -------------------------
# Cooldown env knob: leads called within this window fall out of /queue.
# Default 24h; fractional hours allowed (e.g. "0.25" = 15min for tests).
DEFAULT_RETRY_COOLDOWN_HOURS = 24.0
DEFAULT_CLAIM_TTL_MINUTES = 20
MAX_CLAIM_TTL_MINUTES = 60


def _cooldown_hours() -> float:
    """BLAND_RETRY_COOLDOWN_HOURS at request time; falls back to 24h."""
    raw = (os.environ.get("BLAND_RETRY_COOLDOWN_HOURS") or "").strip()
    if not raw:
        return DEFAULT_RETRY_COOLDOWN_HOURS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_RETRY_COOLDOWN_HOURS
    if value < 0:
        return DEFAULT_RETRY_COOLDOWN_HOURS
    return value


def _iso_utc_now() -> str:
    """Canonical timestamp for claim/cooldown fields (aware UTC ISO strings).

    Kept as one format everywhere so the string comparisons in Mongo queries
    (claimed_until > now, last_ai_call_at < cutoff) stay lexicographically
    correct.
    """
    return datetime.now(timezone.utc).isoformat()


class ClaimRequest(BaseModel):
    """Bland worker claims a lead before dispatching the call."""

    claimed_by: str = Field(min_length=1, max_length=200)
    ttl_minutes: int = Field(
        default=DEFAULT_CLAIM_TTL_MINUTES, ge=1, le=MAX_CLAIM_TTL_MINUTES
    )


class BookingByEmailRequest(BaseModel):
    """Body the booking app POSTs after a successful (immediate or confirmed) booking."""

    status: Optional[str] = None
    when: Optional[str] = None
    booking_ref: Optional[str] = Field(default=None, max_length=200)
    event_type: Optional[str] = None
    channel: Optional[str] = None


# ==================== ROUTER ====================

router = APIRouter(
    prefix="/service/leads",
    tags=["leads-service"],
    dependencies=[Depends(require_leads_service)],
)


def _iso(value):
    """Render a datetime as ISO; pass through strings/None."""
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _activity_view(activity: dict) -> dict:
    content = activity.get("content") or ""
    return {
        "action_type": activity.get("action_type"),
        "content": content[:ACTIVITY_CONTENT_LIMIT],
        "created_at": _iso(activity.get("created_at")),
    }


@router.get("/latest")
async def get_latest_leads():
    """Return the 3 newest leads, each with its 3 most recent activities."""
    leads_out: List[dict] = []

    cursor = (
        db.leads.find({}, LEAD_PROJECTION)
        .sort("created_at", -1)
        .limit(3)
    )
    async for lead in cursor:
        lead_id = lead.get("lead_id")
        activities: List[dict] = []
        act_cursor = (
            db.lead_activities.find({"lead_id": lead_id})
            .sort("created_at", -1)
            .limit(3)
        )
        async for act in act_cursor:
            activities.append(_activity_view(act))
        leads_out.append(
            {
                "lead_id": lead_id,
                "name": lead.get("name"),
                "email": lead.get("email"),
                "phone": _normalize_phone(lead.get("phone")),
                "stage": lead.get("stage"),
                "source": lead.get("source"),
                "created_at": _iso(lead.get("created_at")),
                "updated_at": _iso(lead.get("updated_at")),
                "notes": lead.get("notes"),
                "activities": activities,
            }
        )

    return {"leads": leads_out, "asOf": datetime.now(timezone.utc).isoformat()}


# ==================== BLAND.AI CALLING (Bland agent fe709e36) ====================

def _normalize_phone(raw):
    """Normalize a stored phone for the calling lane — view-layer only,
    never a DB write, never raises.

    The Meta ad-export backfill stores phones like 'p:+1XXXXXXXXXX' (leading
    'p:' quirk) and some CRM rows carry masked junk. Strips a leading
    'p:'/'p' + whitespace (case-insensitive), then removes spaces, dashes,
    dots and parens; keeps '+' and digit runs intact. None (or any non-str)
    passes through unchanged; a malformed value is returned as-is rather
    than raising.
    """
    if raw is None or not isinstance(raw, str):
        return raw
    try:
        s = raw.strip()
        s = re.sub(r"^[pP]\s*:?\s*", "", s)  # 'p:+1…' / 'P: +1…' / 'p +1…'
        s = re.sub(r"[ \-.\(\)]", "", s)  # separators out, '+' and digits stay
        return s
    except Exception:
        return raw


def _lead_view(lead: dict) -> dict:
    """Shared projection shape for queue + single-lead lookups (no Mongo _id)."""
    return {
        "lead_id": lead.get("lead_id"),
        "name": lead.get("name"),
        "email": lead.get("email"),
        "phone": _normalize_phone(lead.get("phone")),
        "stage": lead.get("stage"),
        "source": lead.get("source"),
        "created_at": _iso(lead.get("created_at")),
        "updated_at": _iso(lead.get("updated_at")),
        "notes": lead.get("notes"),
    }


async def _activities_for(lead_id: str, limit: int = 10) -> List[dict]:
    """Most recent N activities for a lead, newest first, trimmed view."""
    activities: List[dict] = []
    act_cursor = (
        db.lead_activities.find({"lead_id": lead_id})
        .sort("created_at", -1)
        .limit(limit)
    )
    async for act in act_cursor:
        activities.append(_activity_view(act))
    return activities


# ==================== TIERED CALLING QUEUE ====================
# Additive tier selection on GET /queue (absent/empty tier = exactly the
# legacy no-param path). tier=fresh is the speed lane (newest-first, restricted
# to the BLAND_FRESH_WINDOW_HOURS window); tier=aged is the drip lane (the
# suppression-filtered remainder, warm-first priority, hard per-UTC-day
# BLAND_AGED_DAILY_CAP enforced through a bland_aged_budget ledger). The only
# write the tier path makes is the ledger doc -- leads themselves are never
# mutated here.

QUEUE_TIER_FRESH = "fresh"
QUEUE_TIER_AGED = "aged"
DEFAULT_FRESH_WINDOW_HOURS = 168.0  # 7 days of hot inbound
DEFAULT_AGED_DAILY_CAP = 10
AGED_BUDGET_COLLECTION = "bland_aged_budget"


def _fresh_window_hours() -> float:
    """BLAND_FRESH_WINDOW_HOURS at request time; falls back to 168h.

    Read at request time so tests and ops can retune without redeploy;
    mirrors the _cooldown_hours() pattern.
    """
    raw = (os.environ.get("BLAND_FRESH_WINDOW_HOURS") or "").strip()
    if not raw:
        return DEFAULT_FRESH_WINDOW_HOURS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_FRESH_WINDOW_HOURS
    if value < 0:
        return DEFAULT_FRESH_WINDOW_HOURS
    return value


def _aged_daily_cap() -> int:
    """BLAND_AGED_DAILY_CAP at request time; falls back to 10.

    Cap 0 is honored as "nothing emits today" (the drip lane is off but the
    ledger/idempotent contract still holds); negatives fall back to default.
    """
    raw = (os.environ.get("BLAND_AGED_DAILY_CAP") or "").strip()
    if not raw:
        return DEFAULT_AGED_DAILY_CAP
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_AGED_DAILY_CAP
    if value < 0:
        return DEFAULT_AGED_DAILY_CAP
    return value


def _aged_budget_day() -> str:
    """UTC date key for the aged daily-cap ledger (patchable in tests)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# Aged priority: warm leads (recent nurture engagement) first, then engaged,
# then new. `registered` stays callable (legacy CALLABLE_STAGES) but sinks
# below new -- it is post-nurture and never a drip priority.
_AGED_STAGE_PRIORITY = {"warm": 0, "engaged": 1, "new": 2, "registered": 3}


def _aged_priority(lead: dict) -> int:
    return _AGED_STAGE_PRIORITY.get(
        lead.get("stage") or "", len(_AGED_STAGE_PRIORITY)
    )


def _queued_view(lead: dict, now_iso: str) -> dict:
    """Lead projection + active-claim surfacing, shared by every queue path
    (legacy, fresh, aged) so lead shapes stay byte-identical."""
    view = _lead_view(lead)
    claim = lead.get("claim")
    if isinstance(claim, dict) and claim.get("claimed_until"):
        if claim["claimed_until"] > now_iso:  # still active
            view["claimed_by"] = claim.get("claimed_by")
            view["claimed_until"] = claim.get("claimed_until")
    return view


async def _fresh_tier_response(
    final_query: dict,
    meta: dict,
    limit: int,
    offset: int,
    now_iso: str,
) -> dict:
    """tier=fresh speed lane: newest-first over the suppression-filtered set
    restricted to leads created within the fresh window.

    Same base payload keys as the legacy queue (leads/count/cooldown/claimed/
    suppressed_*/asOf) plus tier + fresh_cutoff; leads shapes identical.
    """
    cutoff_iso = (
        datetime.now(timezone.utc) - timedelta(hours=_fresh_window_hours())
    ).isoformat()
    window_query = {**final_query, "created_at": {"$gte": cutoff_iso}}
    total = await db.leads.count_documents(window_query)
    leads_out: List[dict] = []
    cursor = (
        db.leads.find(window_query, {**LEAD_PROJECTION, "claim": 1})
        .sort("created_at", -1)
        .skip(offset)
        .limit(limit)
    )
    async for lead in cursor:
        leads_out.append(_queued_view(lead, now_iso))
    return {
        "leads": leads_out,
        "count": total,
        "tier": "fresh",
        "fresh_cutoff": cutoff_iso,
        **meta,
        "asOf": now_iso,
    }


async def _aged_tier_response(
    final_query: dict,
    meta: dict,
    limit: int,
    now_iso: str,
) -> dict:
    """tier=aged drip lane: the suppression-filtered remainder outside the
    fresh window, warm-first priority, hard per-UTC-day cap via the
    bland_aged_budget ledger.

    Budget contract: one ledger doc per UTC day ({day, lead_ids}); emitters
    append with findOneAndUpdate($addToSet $each, upsert) -- atomic, and
    re-adds of an already-lead_id never double-count. A same-day re-query
    therefore returns the already-emitted set idempotently instead of
    emitting fresh leads behind the cap.
    """
    cutoff_iso = (
        datetime.now(timezone.utc) - timedelta(hours=_fresh_window_hours())
    ).isoformat()
    aged_query = {**final_query, "created_at": {"$lt": cutoff_iso}}
    total = await db.leads.count_documents(aged_query)
    aged_docs = await db.leads.find(
        aged_query, {**LEAD_PROJECTION, "claim": 1}
    ).to_list(None)
    # warm > engaged > new (registered sinks below new); newest updated_at
    # first inside a stage; created_at breaks exact ties deterministically
    # (stable sorts applied last-priority-first).
    aged_docs.sort(key=lambda d: d.get("created_at") or "", reverse=True)
    aged_docs.sort(key=lambda d: d.get("updated_at") or "", reverse=True)
    aged_docs.sort(key=_aged_priority)

    budget_day = _aged_budget_day()
    budget_coll = db[AGED_BUDGET_COLLECTION]
    budget_doc = await budget_coll.find_one({"day": budget_day})
    emitted = list((budget_doc or {}).get("lead_ids") or [])
    cap = _aged_daily_cap()
    room = cap - len(emitted)
    new_ids: List[str] = []
    emitted_set: set = set(emitted)
    if room > 0:
        for doc in aged_docs:  # priority order = budget refill order
            lid = doc.get("lead_id")
            if not lid or lid in emitted_set:
                continue
            new_ids.append(lid)
            emitted_set.add(lid)
            room -= 1
            if room == 0:
                break
    if new_ids:
        saved = await budget_coll.find_one_and_update(
            {"day": budget_day},
            {
                "$addToSet": {"lead_ids": {"$each": new_ids}},
                "$setOnInsert": {"created_at": now_iso},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        emitted = list((saved or {}).get("lead_ids") or [])
        emitted_set = set(emitted)

    # Response = current aged set intersected with the day ledger (already
    # emitted leads stay visible idempotently), still priority-ordered.
    aged_leads: List[dict] = []
    for doc in aged_docs:
        if doc.get("lead_id") in emitted_set:
            aged_leads.append(_queued_view(doc, now_iso))
            if len(aged_leads) >= limit:
                break
    return {
        "leads": aged_leads,
        "count": total,
        "tier": "aged",
        "aged_emitted_today": len(emitted),
        # Budget consumed AND the caller asked for more than it got back.
        "daily_cap_reached": len(emitted) >= cap and len(aged_leads) < limit,
        **meta,
        "asOf": now_iso,
    }


@router.get("/queue")
async def get_calling_queue(
    limit: int = Query(default=10, ge=1, le=25),
    offset: int = Query(default=0, ge=0),
    # Plain Optional (NOT Query()): the dispatcher calls get_calling_queue()
    # directly with plain kwargs, so a Query object default would leak
    # through. FastAPI still coerces this for HTTP query params.
    tier: Optional[str] = None,
):
    """Paginated Bland.ai calling queue, oldest leads first.

    Only leads with a non-empty phone in a call-eligible stage
    (new/engaged/warm/registered) Ã¢ÂÂ do_not_call and lost leads are never
    re-called. count is the total matching the filter (after offset/limit
    applied separately) so the caller knows how many remain.

    Jeff's annoyance-proof suppression rules (server-side, live in the
    shared queue logic so the no-param path and every tier path inherit
    them Ã¢ÂÂ no dispatcher behavior can violate them):

    1. APPOINTMENT/CONSULT SUPPRESSION (permanent): a lead with any
       lead_activities action_type `booked_call` is never queued again Ã¢ÂÂ
       Jeff's pipeline owns booked/consulted people forever (booked AND met
       both covered).
    2. HUMAN-TOUCH PAUSE: a lead whose latest activity is human-style
       (content/action does NOT start with the AI prefix "AI call via
       Bland:" and is not a system/bookkeeping type Ã¢ÂÂ booked_call,
       booking_reminder_*, fallback_email_sent, fallback_email_failed,
       diagnostic notes) is paused Ã¢ÂÂ the queue never talks over a human.
       An AI-prefixed or system latest activity keeps the lead callable.
    3. THIRTY-DAY ATTEMPT CAP: a lead with >= 3 ok==true entries in
       bland_call_log (per lead_id, 30-day window) is exhausted. Failed
       Bland submissions do not count.

    A lead excluded by an earlier rule is counted under that rule only,
    so suppressed_booked + suppressed_human_touch + exhausted_30d + count
    == the pre-suppression fresh-eligible total.

    Batch-mode guard meta (additive):
      cooldown: eligible leads currently excluded because last_ai_call_at is
        within BLAND_RETRY_COOLDOWN_HOURS (default 24h).
      claimed: leads in the result set holding an unexpired claim. Claimed
        leads are NOT hidden Ã¢ÂÂ they carry claimed_by/claimed_until so Norm's
        worker skips them itself while keeping queue visibility.

    Suppression meta (additive):
      suppressed_booked: leads excluded by rule 1 (booked/consult)
      suppressed_human_touch: leads excluded by rule 2 (human-touch pause)
      exhausted_30d: leads excluded by rule 3 (3-in-30 attempt cap)

    Tier selection (additive; every tier inherits the same suppression
    pipeline, cooldown/claim guards and lead shapes -- no-param is unchanged):

      tier=fresh  speed lane: suppression-filtered leads created within
        BLAND_FRESH_WINDOW_HOURS (default 168h), created_at DESC (newest
        first). Meta: fresh_cutoff (ISO instant of the window start).
      tier=aged   drip lane: the suppression-filtered remainder (created_at
        older than the fresh window), ordered warm > engaged > new
        (registered sinks below new) with updated_at DESC inside a stage.
        Hard daily cap BLAND_AGED_DAILY_CAP (default 10) unique leads per
        UTC day, enforced through the bland_aged_budget ledger
        ({day, lead_ids}; atomic findOneAndUpdate $addToSet append, no
        double-count). Same-day re-queries return the already-emitted set
        idempotently. Meta: aged_emitted_today, daily_cap_reached (budget
        consumed and the caller asked for more than it got back).
      anything else -> 400 invalid_tier; absent/empty -> legacy path.
    """
    now_iso = _iso_utc_now()
    # Tier validation happens before any pipeline work; empty/absent tier is
    # exactly the legacy no-param behavior.
    tier_key = (tier or "").strip().lower()
    if tier_key and tier_key not in (QUEUE_TIER_FRESH, QUEUE_TIER_AGED):
        raise HTTPException(status_code=400, detail="invalid_tier")
    cutoff_iso = (
        datetime.now(timezone.utc) - timedelta(hours=_cooldown_hours())
    ).isoformat()
    query = {
        "phone": {
            "$exists": True,
            "$nin": [None, ""],
            # Ã¢ÂÂ¥10 consecutive digits (Bland needs a dialable number) Ã¢ÂÂ blocks
            # masked CRM junk like '+184****4495'; 'p:+1201Ã¢ÂÂ¦' quirks still pass
            # and are normalized in the view below.
            "$regex": re.compile(r"\d{10}"),
        },
        "stage": {"$in": CALLABLE_STAGES},
    }
    # Cooldown guard: a fresh last_ai_call_at (missing/null never matches the
    # $lt comparison, so they pass either branch) keeps the lead out of the
    # result set. All stamps are same-format ISO strings Ã¢ÂÂ lexical compare ok.
    fresh_clause = {
        "$or": [
            {"last_ai_call_at": {"$exists": False}},
            {"last_ai_call_at": None},
            {"last_ai_call_at": {"$lt": cutoff_iso}},
        ]
    }
    eligible_total = await db.leads.count_documents(query)
    fresh_query = {**query, **fresh_clause}
    total_pre = await db.leads.count_documents(fresh_query)
    cooldown_count = eligible_total - total_pre
    # "claimed" meta: fresh-eligible leads with an unexpired claim (TTL is a
    # plain field comparison Ã¢ÂÂ expired claims are ignored, no Mongo TTL index).
    claimed_count = await db.leads.count_documents(
        {**fresh_query, "claim.claimed_until": {"$gt": now_iso}}
    )

    # ---- Suppression rules (shared by tier + no-param paths) ----
    candidate_ids = [
        doc["lead_id"]
        async for doc in db.leads.find(fresh_query, {"lead_id": 1}).sort(
            "created_at", 1
        )
    ]

    suppressed_booked = suppressed_human_touch = exhausted_30d = 0
    suppressed_all: set[str] = set()
    if candidate_ids:
        candidate_set = set(candidate_ids)

        # Rule 1 Ã¢ÂÂ permanent: any booked_call activity ever.
        booked_ids = await db.lead_activities.distinct(
            "lead_id", {"action_type": BOOKED_CALL_ACTION}
        )
        booked_set = {
            lid for lid in (booked_ids or []) if lid in candidate_set
        }

        # Rule 2 Ã¢ÂÂ human-touch pause: latest activity is human-style.
        latest_by_lead: dict[str, dict] = {}
        act_cursor = db.lead_activities.find(
            {"lead_id": {"$in": candidate_ids}}
        ).sort("created_at", -1)
        async for act in act_cursor:
            lid = act.get("lead_id")
            if lid not in latest_by_lead:
                latest_by_lead[lid] = act
        human_set = {
            lid
            for lid, act in latest_by_lead.items()
            if lid not in booked_set and _latest_activity_is_human(act)
        }

        # Rule 3 Ã¢ÂÂ 30-day attempt cap: >= 3 ok==true bland_call_log entries.
        thirty_d_ago_iso = (
            datetime.now(timezone.utc) - THIRTY_DAYS
        ).isoformat()
        remaining = [
            lid
            for lid in candidate_ids
            if lid not in booked_set and lid not in human_set
        ]
        attempt_counts: dict[str, int] = {}
        if remaining:
            log_cursor = db.bland_call_log.find(
                {
                    "ok": True,
                    "ts": {"$gte": thirty_d_ago_iso},
                    "lead_id": {"$in": remaining},
                }
            )
            async for log in log_cursor:
                lid = log.get("lead_id")
                attempt_counts[lid] = attempt_counts.get(lid, 0) + 1
        exhausted_set = {
            lid for lid in remaining if attempt_counts.get(lid, 0) >= 3
        }

        suppressed_booked = len(booked_set)
        suppressed_human_touch = len(human_set)
        exhausted_30d = len(exhausted_set)
        suppressed_all = booked_set | human_set | exhausted_set

    final_query = (
        {**fresh_query, "lead_id": {"$nin": sorted(suppressed_all)}}
        if suppressed_all
        else fresh_query
    )
    total = await db.leads.count_documents(final_query)

    # ---- Tier dispatch (additive; absent/empty tier falls through) ----
    meta = {
        "cooldown": cooldown_count,
        "claimed": claimed_count,
        "suppressed_booked": suppressed_booked,
        "suppressed_human_touch": suppressed_human_touch,
        "exhausted_30d": exhausted_30d,
    }
    if tier_key == QUEUE_TIER_FRESH:
        return await _fresh_tier_response(
            final_query, meta, limit, offset, now_iso
        )
    if tier_key == QUEUE_TIER_AGED:
        return await _aged_tier_response(final_query, meta, limit, now_iso)

    leads_out: List[dict] = []
    cursor = (
        db.leads.find(final_query, {**LEAD_PROJECTION, "claim": 1})
        .sort("created_at", 1)
        .skip(offset)
        .limit(limit)
    )
    async for lead in cursor:
        view = _lead_view(lead)
        claim = lead.get("claim")
        if isinstance(claim, dict) and claim.get("claimed_until"):
            if claim["claimed_until"] > now_iso:  # still active
                view["claimed_by"] = claim.get("claimed_by")
                view["claimed_until"] = claim.get("claimed_until")
        leads_out.append(view)

    return {
        "leads": leads_out,
        "count": total,
        "cooldown": cooldown_count,
        "claimed": claimed_count,
        "suppressed_booked": suppressed_booked,
        "suppressed_human_touch": suppressed_human_touch,
        "exhausted_30d": exhausted_30d,
        "asOf": now_iso,
    }


@router.get("/{lead_id}")
async def get_service_lead(lead_id: str):
    """Single-lead lookup: same projection as /latest plus up to 10 activities.

    Bland uses this to resolve (and re-contextualize) a lead before dialing.
    """
    lead = await db.leads.find_one({"lead_id": lead_id}, LEAD_PROJECTION)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    view = _lead_view(lead)
    view["activities"] = await _activities_for(lead_id, limit=10)
    return {"lead": view}


@router.post("/{lead_id}/call-outcome")
async def record_call_outcome(
    lead_id: str,
    body: CallOutcomeRequest,
    background_tasks: BackgroundTasks,
):
    """Record a Bland.ai call disposition on a lead.

    Stage transitions:
      - opt_out flag true, OR disposition==opt_out -> do_not_call (+ logged)
      - not_interested -> lost
      - booked -> engaged (+ booking_ref logged)
      - anything else -> stage unchanged

    Batch-mode guard: every outcome also stamps last_ai_call_at=now (UTC) and
    increments ai_call_attempts so /queue can hold the lead out for the
    BLAND_RETRY_COOLDOWN_HOURS window (default 24h).

    Founder fallback email: callback_requested, or booked with no confirmed
    booking_ref, queues an instant founder email as a background task (never
    blocks or fails this response).
    """
    disposition = (body.disposition or "").strip()
    if disposition not in CALL_DISPOSITIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid disposition. Must be one of: {', '.join(CALL_DISPOSITIONS)}",
        )
    # 2026-11-18 (agent retry hardening): validate the summary length with an
    # explicit 400 instead of letting any layer silently cut the agent's words.
    if len(body.summary or "") > CALL_SUMMARY_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid summary: {len(body.summary)} chars exceeds the {CALL_SUMMARY_MAX}-char limit",
        )
    lead = await db.leads.find_one({"lead_id": lead_id})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    stage = await _apply_call_outcome(
        lead_id,
        disposition=disposition,
        summary=body.summary or "",
        booking_ref=body.booking_ref,
        opt_out=body.opt_out,
        call_duration_sec=body.call_duration_sec,
        current_stage=lead.get("stage"),
        background_tasks=background_tasks,
    )
    return {"success": True, "lead_id": lead_id, "stage": stage}


async def _apply_call_outcome(
    lead_id: str,
    *,
    disposition: str,
    summary: str = '',
    booking_ref: Optional[str] = None,
    opt_out: bool = False,
    call_duration_sec: Optional[int] = None,
    current_stage: Optional[str] = None,
    background_tasks: Optional[BackgroundTasks] = None,
) -> Optional[str]:
    """Shared AI-call outcome write path (call-outcome endpoint + webhook).

    Logs the activity, applies the stage transition, and stamps the cooldown
    guard (last_ai_call_at + ai_call_attempts). Lead existence is checked by
    the caller. Returns the resulting stage.

    When background_tasks is provided (both HTTP callers do), a due founder
    fallback email is queued on it and runs after the response; direct
    (non-HTTP) callers run the email inline, deterministically.
    """
    content = f"AI call via Bland: {disposition}"
    summary = (summary or "").strip()
    if summary:
        content += f" — {summary}"
    if call_duration_sec:
        content += f" ({call_duration_sec}s)"
    await _log_activity(lead_id, "manual", content)

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    if current_stage is None:
        lead = await db.leads.find_one({"lead_id": lead_id}, {"stage": 1})
        current_stage = (lead or {}).get("stage")
    stage = current_stage
    if opt_out or disposition == "opt_out":
        stage = "do_not_call"
        await db.leads.update_one(
            {"lead_id": lead_id},
            {"$set": {"stage": "do_not_call", "updated_at": now_iso}},
        )
        await _log_activity(
            lead_id, "system", "Opt-out recorded from AI call — do not call"
        )
    elif disposition == "not_interested":
        stage = "lost"
        await db.leads.update_one(
            {"lead_id": lead_id},
            {"$set": {"stage": "lost", "updated_at": now_iso}},
        )
    elif disposition == "booked":
        stage = "engaged"
        await db.leads.update_one(
            {"lead_id": lead_id},
            {"$set": {"stage": "engaged", "updated_at": now_iso}},
        )
        if booking_ref:
            await _log_activity(lead_id, "manual", f"Booking ref: {booking_ref}")

    # Cooldown stamp — ISO string (lexicographic compare in the queue filter).
    await db.leads.update_one(
        {"lead_id": lead_id},
        {"$set": {"last_ai_call_at": now_iso}, "$inc": {"ai_call_attempts": 1}},
    )
    # Founder fallback email (2026-11-18): deterministic trigger AFTER the
    # outcome write — callback_requested, or booked with no confirmed ref.
    # Background task keeps the HTTP response fast; provider errors never
    # propagate (they mark fallback_email_failed instead). The scheduling call
    # itself is guarded so the outcome write can never fail because of it.
    if _fallback_email_due(disposition, booking_ref):
        try:
            if background_tasks is not None:
                background_tasks.add_task(
                    _send_founder_fallback_email,
                    lead_id,
                    disposition=disposition,
                    summary=summary,
                    booking_ref=booking_ref,
                )
            else:
                # Direct helper callers (non-HTTP paths / unit tests) run
                # inline so the effect is deterministic.
                await _send_founder_fallback_email(
                    lead_id,
                    disposition=disposition,
                    summary=summary,
                    booking_ref=booking_ref,
                )
        except Exception:  # noqa: BLE001 — outcome already written; never fail it
            logger.exception(
                "Founder fallback email scheduling failed for %s", lead_id
            )
    return stage


@router.post("/{lead_id}/claim")
async def claim_lead_for_call(lead_id: str, body: ClaimRequest):
    """Bland worker claims a lead before dispatching the call.

    Batch-mode dedupe guard: prevents two workers calling the same lead.
    - 200 {"success": true, "claimed_until": ...} when free, or when the SAME
      claimed_by refreshes its own (even expired) claim.
    - 409 {"detail": "already_claimed", "claimed_until": ...} when a DIFFERENT
      claimant holds an unexpired claim.
    Expired claims (claimed_until <= now) are ignored — TTL auto-release via a
    plain field comparison, no Mongo TTL index needed.
    """
    lead = await db.leads.find_one({"lead_id": lead_id})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    existing = lead.get("claim")
    if isinstance(existing, dict):
        existing_until = existing.get("claimed_until")
        existing_by = existing.get("claimed_by")
        if (
            isinstance(existing_until, str)
            and existing_until > _iso_utc_now()
            and existing_by
            and existing_by != body.claimed_by
        ):
            logger.info(
                "Lead %s claim conflict: held by %s until %s (requested by %s)",
                lead_id, existing_by, existing_until, body.claimed_by,
            )
            return JSONResponse(
                status_code=409,
                content={
                    "detail": "already_claimed",
                    "claimed_by": existing_by,
                    "claimed_until": existing_until,
                },
            )

    until_iso = (
        datetime.now(timezone.utc) + timedelta(minutes=body.ttl_minutes)
    ).isoformat()
    claim_doc = {
        "claimed_by": body.claimed_by,
        "claimed_until": until_iso,
        "claimed_at": _iso_utc_now(),
    }
    await db.leads.update_one(
        {"lead_id": lead_id}, {"$set": {"claim": claim_doc}}
    )
    return {
        "success": True,
        "lead_id": lead_id,
        "claimed_by": body.claimed_by,
        "ttl_minutes": body.ttl_minutes,
        "claimed_until": until_iso,
    }


@router.delete("/{lead_id}/claim")
async def release_claim_for_call(lead_id: str):
    """Explicit claim release (Norm's worker calls this after the outcome).

    Idempotent — releasing an unclaimed (or expired) lead is still 200.
    """
    lead = await db.leads.find_one({"lead_id": lead_id})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    await db.leads.update_one({"lead_id": lead_id}, {"$unset": {"claim": ""}})
    return {"success": True, "lead_id": lead_id}


@router.post("/{lead_id}/note")
async def add_service_note(lead_id: str, body: ServiceNoteRequest):
    """Append a manual note to a lead's activity log."""
    lead = await db.leads.find_one({"lead_id": lead_id})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    content = (body.content or "").strip()
    if not content or len(content) > 2000:
        raise HTTPException(
            status_code=400,
            detail="content must be a non-empty string between 1 and 2000 characters",
        )

    await _log_activity(lead_id, "manual", content)
    return {"success": True}


@router.patch("/{lead_id}/stage")
async def set_service_stage(lead_id: str, body: ServiceStageRequest):
    """Set a lead's stage (validated) and log a system activity."""
    stage = (body.stage or "").strip()
    if stage not in LEAD_STAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid stage. Must be one of: {', '.join(LEAD_STAGES)}",
        )

    lead = await db.leads.find_one({"lead_id": lead_id})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    now = datetime.now(timezone.utc)
    await db.leads.update_one(
        {"lead_id": lead_id},
        {"$set": {"stage": stage, "updated_at": now.isoformat()}},
    )
    await _log_activity(
        lead_id, "system", f"Stage set to {stage} from OS overview by Kit"
    )
    return {"success": True, "stage": stage}


@router.post("/by-email/{email}/booking")
async def record_booking_by_email(email: str, body: BookingByEmailRequest):
    """Record a governance-consultation booking by lead email (booking-app callback).

    Consumed by the TrustOffice booking service after ANY successful booking
    confirm (public click OR agent/trusted immediate booking). Idempotent by
    email; a miss returns success+matched=false with no side effects.
    """
    raw_email = (email or "").strip().lower()
    when = (body.when or "").strip()
    booking_ref = (body.booking_ref or "").strip()
    event_type = (body.event_type or "governance-consultation").strip() or "governance-consultation"

    lead = await db.leads.find_one(
        {"email": {"$regex": f"^{re.escape(raw_email)}$", "$options": "i"}},
    )
    if not lead:
        # Unknown lead: no side effects, just log server-side.
        logger.info("Booking callback for unknown lead email: %s", raw_email)
        return {"success": True, "matched": False}

    lead_id = lead.get("lead_id")
    stage = lead.get("stage") or "new"
    content = f"Governance consultation BOOKED — slot {when or 'n/a'}, ref {booking_ref or 'n/a'}"

    now = datetime.now(timezone.utc)
    if stage == "do_not_call":
        # Opted out: never re-engage via a booking callback; log only.
        content += f" (stage: {stage} — not changed)"
    else:
        if stage != "engaged":
            content += f" (stage: {stage} → engaged)"
        stage = "engaged"
        await db.leads.update_one(
            {"lead_id": lead_id},
            {"$set": {"stage": "engaged", "updated_at": now.isoformat()}},
        )

    await _log_activity(lead_id, "system", content)

    return {"success": True, "matched": True, "lead_id": lead_id, "stage": stage}
