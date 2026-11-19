"""TrustOffice "leads service" lane (Phase 1).

Scoped, service-to-service endpoints consumed by the Agentic OS overview
card (Kit's command center) and the Bland.ai calling assistant. Authenticated
with a single static service key sent in the `X-Service-Key` header — NOT a
user JWT. The OS backend calls these server-side, so no browser CORS is
opened here.

Endpoints (mounted under /api/service/leads):
  GET  /latest                 -> 3 newest leads + each lead's 3 latest activities
  GET  /queue                  -> Bland calling queue: leads with a phone in
                                  call-eligible stages (new/engaged/warm/
                                  registered), oldest first, paginated
  GET  /{lead_id}              -> single lead + up to 10 activities (Bland
                                  resolves a lead before dialing)
  POST /{lead_id}/call-outcome -> record an AI call disposition (+ stage
                                  transitions: opt_out/interested/booked)
  POST /{lead_id}/note         -> append a manual note (through the same
                                  _log_activity helper the admin notes use)
  PATCH /{lead_id}/stage       -> set stage (validated) + log a system activity
"""
import logging
import os
import re
import secrets
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from database import db
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

ACTIVITY_CONTENT_LIMIT = 160


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


class CallOutcomeRequest(BaseModel):
    disposition: str
    summary: str = ''
    booking_ref: Optional[str] = Field(default=None, max_length=200)
    opt_out: bool = False
    call_duration_sec: Optional[int] = None


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


@router.get("/queue")
async def get_calling_queue(
    limit: int = Query(default=10, ge=1, le=25),
    offset: int = Query(default=0, ge=0),
):
    """Paginated Bland.ai calling queue, oldest leads first.

    Only leads with a non-empty phone in a call-eligible stage
    (new/engaged/warm/registered) — do_not_call and lost leads are never
    re-called. count is the total matching the filter (after offset/limit
    applied separately) so the caller knows how many remain.
    """
    query = {
        "phone": {
            "$exists": True,
            "$nin": [None, ""],
            # ≥10 consecutive digits (Bland needs a dialable number) — blocks
            # masked CRM junk like '+184****4495'; 'p:+1201…' quirks still pass
            # and are normalized in the view below.
            "$regex": re.compile(r"\d{10}"),
        },
        "stage": {"$in": CALLABLE_STAGES},
    }
    total = await db.leads.count_documents(query)
    leads_out: List[dict] = []
    cursor = (
        db.leads.find(query, LEAD_PROJECTION)
        .sort("created_at", 1)
        .skip(offset)
        .limit(limit)
    )
    async for lead in cursor:
        leads_out.append(_lead_view(lead))

    return {
        "leads": leads_out,
        "count": total,
        "asOf": datetime.now(timezone.utc).isoformat(),
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
async def record_call_outcome(lead_id: str, body: CallOutcomeRequest):
    """Record a Bland.ai call disposition on a lead.

    Stage transitions:
      - opt_out flag true, OR disposition==opt_out -> do_not_call (+ logged)
      - not_interested -> lost
      - booked -> engaged (+ booking_ref logged)
      - anything else -> stage unchanged
    """
    disposition = (body.disposition or "").strip()
    if disposition not in CALL_DISPOSITIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid disposition. Must be one of: {', '.join(CALL_DISPOSITIONS)}",
        )
    lead = await db.leads.find_one({"lead_id": lead_id})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    call_stage = body.call_duration_sec if body.call_duration_sec is not None else None
    content = f"AI call via Bland: {disposition}"
    summary = (body.summary or "").strip()
    if summary:
        content += f" — {summary}"
    if call_stage:
        content += f" ({call_stage}s)"
    await _log_activity(lead_id, "manual", content)

    now = datetime.now(timezone.utc)
    stage = lead.get("stage")
    if body.opt_out or disposition == "opt_out":
        stage = "do_not_call"
        await db.leads.update_one(
            {"lead_id": lead_id},
            {"$set": {"stage": "do_not_call", "updated_at": now.isoformat()}},
        )
        await _log_activity(
            lead_id, "system", "Opt-out recorded from AI call — do not call"
        )
    elif disposition == "not_interested":
        stage = "lost"
        await db.leads.update_one(
            {"lead_id": lead_id},
            {"$set": {"stage": "lost", "updated_at": now.isoformat()}},
        )
    elif disposition == "booked":
        stage = "engaged"
        await db.leads.update_one(
            {"lead_id": lead_id},
            {"$set": {"stage": "engaged", "updated_at": now.isoformat()}},
        )
        if body.booking_ref:
            await _log_activity(lead_id, "manual", f"Booking ref: {body.booking_ref}")

    return {"success": True, "lead_id": lead_id, "stage": stage}


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
