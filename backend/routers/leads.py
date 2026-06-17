"""
Leads Router — Lead Management for Marketing Entry Points
Captures leads from Trustee 101 enrollment, checklist downloads, and any other
marketing form. Tracks them through: new → engaged → warm → converted → lost.
"""
import re
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from pydantic import BaseModel, EmailStr

from database import db
from routers.admin import require_admin
from discord_service import notify_new_lead, notify_lead_stage_change
from email_service import email_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/leads", tags=["leads"])

# ==================== LEAD STAGES ====================

LEAD_STAGES = [
    "new",         # Just entered their email on a marketing form
    "engaged",     # Watched 1+ lessons / interacted with content
    "warm",        # Been around a while but hasn't engaged yet
    "converted",   # Subscribed to TrustOffice
    "lost",        # Went cold or unsubscribed
]

STAGE_LABELS = {
    "new": "New",
    "engaged": "Engaged",
    "warm": "Warm",
    "converted": "Converted",
    "lost": "Lost",
}

# Valid lead sources — any marketing form that captures emails
LEAD_SOURCES = [
    "trustee-101-landing-page",
    "trustee-90-day-checklist",
    "commingling-checklist",
    "blog-subscribe",
    "webinar-signup",
    "booked-call",
    "liability-protection-kit",
    "manual",
    "direct",
]

# ==================== SCHEMAS ====================


class LeadCapture(BaseModel):
    """
    Schema for capturing a lead from any marketing form.
    This is the primary entry point — called when someone enters their email.
    """
    name: str
    email: EmailStr
    source: str = "trustee-101-landing-page"
    utm_source: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_medium: Optional[str] = None


class LeadUpdate(BaseModel):
    """Schema for updating a lead's stage or notes."""
    stage: Optional[str] = None
    notes: Optional[str] = None
    next_action: Optional[str] = None


class LeadNote(BaseModel):
    """Schema for adding a note to a lead."""
    content: str
    action_type: str = "manual"  # manual, email, call, system


# ==================== DATE HELPERS ====================


def _parse_iso_date(value) -> Optional[datetime]:
    """
    Safely parse a date value that could be a datetime, ISO string, or None.
    The existing codebase stores dates as ISO strings (.isoformat()) in MongoDB.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            if value.endswith('Z'):
                value = value[:-1] + '+00:00'
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return None
    return None


def _days_since(value) -> Optional[int]:
    """Calculate days since a date value (datetime, ISO string, or None)."""
    dt = _parse_iso_date(value)
    if dt is None:
        return None
    return (datetime.now(timezone.utc) - dt).days


# ==================== HELPERS ====================


def calculate_lead_score(lead: dict) -> int:
    """
    Calculate a lead score (0-100) based on:
    - Course progress (40%)
    - Login frequency (30%)
    - Days since capture (20%)
    - Source quality (10%)
    """
    score = 0

    # Course progress (40 points max)
    lessons_watched = lead.get("lessons_watched", 0)
    total_lessons = 9
    score += int((lessons_watched / total_lessons) * 40)

    # Login frequency (30 points max)
    days_since_login = _days_since(lead.get("last_login"))
    if days_since_login is not None:
        if days_since_login <= 1:
            score += 30
        elif days_since_login <= 3:
            score += 20
        elif days_since_login <= 7:
            score += 10
        elif days_since_login <= 14:
            score += 5

    # Days since capture (20 points max — fresh leads score higher)
    days_since = _days_since(lead.get("created_at"))
    if days_since is not None:
        if days_since <= 7:
            score += 20
        elif days_since <= 30:
            score += 15
        elif days_since <= 60:
            score += 10
        else:
            score += 5

    # Booked a call (15 points — strong intent signal)
    if lead.get("booked_call"):
        score += 15

    # Source quality (10 points max)
    source = lead.get("source", "")
    SOURCE_QUALITY = {
        "booked-call": 10,              # Highest intent — booked a discovery call
        "webinar-signup": 8,            # High intent — signed up for an event
        "liability-protection-kit": 6,  # Medium-high — downloaded multiple checklists
        "trustee-101-landing-page": 5,  # Medium — enrolled in the free course
        "trustee-90-day-checklist": 4,
        "commingling-checklist": 4,
        "blog-subscribe": 2,            # Low intent — casual blog reader
        "direct": 1,                    # Unknown / direct traffic
        "manual": 0,                    # Manually entered
    }
    score += SOURCE_QUALITY.get(source, 1)

    return min(score, 100)


def determine_lead_stage(lead: dict) -> str:
    """
    Auto-determine the correct stage for a lead based on their data.
    Respects manual_stage_override flag.
    """
    if lead.get("manual_stage_override"):
        return lead.get("stage", "new")

    status = lead.get("subscription_status")
    lessons_watched = lead.get("lessons_watched", 0)
    days_since = _days_since(lead.get("created_at")) or 0

    # Converted: subscribed to TrustOffice
    if status == "active":
        return "converted"

    # Lost: went cold (30+ days with no engagement)
    if days_since > 30 and lessons_watched == 0:
        return "lost"

    # Engaged: watched 1+ lessons
    if lessons_watched > 0:
        return "engaged"

    # Warm: been around a while but hasn't engaged
    if days_since > 7:
        return "warm"

    # Default: new
    return "new"


def get_next_action(lead: dict) -> str:
    """Auto-calculate the recommended next action for a lead."""
    stage = lead.get("stage", "new")
    lessons_watched = lead.get("lessons_watched", 0)
    days_since = _days_since(lead.get("created_at")) or 0

    if stage == "new" and days_since > 3 and lessons_watched == 0:
        return "Trigger re-engagement email — hasn't started course"
    elif stage == "engaged" and lessons_watched >= 3:
        return "Send subscription pitch — high engagement"
    elif stage == "warm":
        return "Send value email with subscription CTA"
    elif stage == "converted":
        return "No action needed — successfully converted"
    elif stage == "lost":
        return "Consider win-back offer or sunset"
    else:
        return "Monitor — no action needed"


def _enrich_lead(lead: dict) -> dict:
    """Recalculate stage, score, next_action, and stage_label on a lead dict."""
    lead["stage"] = determine_lead_stage(lead)
    lead["score"] = calculate_lead_score(lead)
    lead["next_action"] = get_next_action(lead)
    lead["stage_label"] = STAGE_LABELS.get(lead["stage"], lead["stage"])
    return lead


# ==================== PUBLIC ENDPOINT ====================

# This endpoint is intentionally NOT behind admin auth.
# It's called from marketing forms (Trustee 101, checklists, etc.)
# to capture leads before they become customers.


@router.post("/capture", include_in_schema=False)
async def capture_lead(lead: LeadCapture):
    """
    Capture a lead from any marketing form.
    Public endpoint — no auth required. Called when someone enters their email
    on the Trustee 101 landing page, checklist downloads, blog subscribe, etc.

    Idempotent: if a lead already exists for this email, it updates the
    existing record rather than creating a duplicate.
    """
    email = lead.email.strip().lower()
    name = lead.name.strip()
    source = lead.source or "trustee-101-landing-page"

    # Check if lead already exists by email
    existing = await db.leads.find_one({"email": email})
    if existing:
        logger.info(f"Lead already exists for {email} — updating source")
        await db.leads.update_one(
            {"email": email},
            {"$set": {
                "name": name,
                "source": source,
                "utm_source": lead.utm_source,
                "utm_campaign": lead.utm_campaign,
                "utm_medium": lead.utm_medium,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }}
        )
        return {
            "success": True,
            "lead_id": existing["lead_id"],
            "is_returning": True,
        }

    now = datetime.now(timezone.utc)
    lead_id = f"lead_{uuid.uuid4().hex[:12]}"

    lead_doc = {
        "lead_id": lead_id,
        "email": email,
        "name": name,
        "source": source,
        "lead_type": "email_capture",
        "utm_source": lead.utm_source,
        "utm_campaign": lead.utm_campaign,
        "utm_medium": lead.utm_medium,
        "stage": "new",
        "manual_stage_override": False,
        "lessons_watched": 0,
        "subscription_status": None,
        "last_login": None,
        "notes": "",
        "next_action": "Monitor — no action needed",
        "score": 50,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    await db.leads.insert_one(lead_doc)
    await _log_activity(lead_id, "created", f"Lead captured via {source}")

    # Send Discord notification
    await notify_new_lead(
        name=name,
        email=email,
        source=source,
        lead_stage="new"
    )

    # Send welcome email (fire-and-forget — non-blocking)
    try:
        course_url = f"{email_service.app_url}/courses/trustee-101"
        await email_service.send_lead_welcome(
            to_email=email,
            name=name,
            course_url=course_url
        )
        await _log_activity(lead_id, "email", "Sent welcome email")
    except Exception as e:
        logger.warning(f"Failed to send welcome email to {email}: {e}")

    logger.info(f"Lead captured: {lead_id} — {email} via {source}")
    return {
        "success": True,
        "lead_id": lead_id,
        "is_returning": False,
    }


@router.post("/tidycal-webhook", include_in_schema=False)
async def tidycal_webhook(request: Request):
    """
    Webhook endpoint for TidyCal booking notifications.
    Called when someone books a TrustOffice Discovery Call.
    Creates/updates a lead with source="booked-call" and flags them.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # TidyCal sends different payload shapes depending on version
    # Common fields: name, email, event_type, starts_at, timezone
    name = (
        body.get("name")
        or body.get("customer", {}).get("name")
        or "Unknown"
    )
    email = (
        body.get("email")
        or body.get("customer", {}).get("email")
        or ""
    )
    if not email:
        logger.warning("TidyCal webhook received without email — skipping")
        return {"success": False, "error": "No email provided"}

    email = email.strip().lower()
    booked_at = body.get("starts_at") or body.get("start_time") or datetime.now(timezone.utc).isoformat()

    # Check if lead already exists
    existing = await db.leads.find_one({"email": email})
    if existing:
        await db.leads.update_one(
            {"email": email},
            {"$set": {
                "name": name,
                "source": "booked-call",
                "booked_call": True,
                "booked_call_at": booked_at,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }}
        )
        lead_id = existing["lead_id"]
        await _log_activity(lead_id, "booked_call", f"Booked a TrustOffice Discovery Call at {booked_at}")
        logger.info(f"Lead {lead_id} booked a call — {email}")
        return {"success": True, "lead_id": lead_id, "is_returning": True}

    # Create new lead
    now = datetime.now(timezone.utc)
    lead_id = f"lead_{uuid.uuid4().hex[:12]}"

    lead_doc = {
        "lead_id": lead_id,
        "email": email,
        "name": name,
        "source": "booked-call",
        "lead_type": "email_capture",
        "stage": "new",
        "manual_stage_override": False,
        "booked_call": True,
        "booked_call_at": booked_at,
        "lessons_watched": 0,
        "subscription_status": None,
        "last_login": None,
        "notes": "",
        "next_action": "Prepare for upcoming discovery call",
        "score": 70,  # High score — booked a call is strong intent
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    await db.leads.insert_one(lead_doc)
    await _log_activity(lead_id, "created", "Lead captured via TidyCal booking")
    await _log_activity(lead_id, "booked_call", f"Booked a TrustOffice Discovery Call at {booked_at}")

    await notify_new_lead(
        name=name,
        email=email,
        source="booked-call",
        lead_stage="new"
    )

    logger.info(f"Lead created from TidyCal booking: {lead_id} — {email}")
    return {"success": True, "lead_id": lead_id, "is_returning": False}


# ==================== ADMIN ENDPOINTS ====================


@router.get("")
async def list_leads(
    stage: Optional[str] = Query(None, description="Filter by stage"),
    source: Optional[str] = Query(None, description="Filter by source (e.g. trustee-101-landing-page)"),
    lead_type: Optional[str] = Query(None, description="Filter by type: email_capture, paid_subscriber"),
    search: Optional[str] = Query(None, description="Search by name or email"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    admin: dict = Depends(require_admin)
):
    """List all leads with filtering, search, and pagination."""
    query = {}

    if stage and stage != "all":
        if stage not in LEAD_STAGES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid stage. Must be one of: {', '.join(LEAD_STAGES)}"
            )
        query["stage"] = stage

    if source:
        query["source"] = source

    if lead_type:
        query["lead_type"] = lead_type

    if search:
        escaped = re.escape(search)
        query["$or"] = [
            {"email": {"$regex": escaped, "$options": "i"}},
            {"name": {"$regex": escaped, "$options": "i"}}
        ]

    total = await db.leads.count_documents(query)
    sort_dir = -1 if sort_order == "desc" else 1
    skip = (page - 1) * limit
    leads = await db.leads.find(query, {"_id": 0}).sort(sort_by, sort_dir).skip(skip).limit(limit).to_list(limit)

    for lead in leads:
        _enrich_lead(lead)

    stage_counts = {}
    for s in LEAD_STAGES:
        stage_counts[s] = await db.leads.count_documents({"stage": s})
    stage_counts["all"] = total

    return {
        "leads": leads,
        "total": total,
        "page": page,
        "limit": limit,
        "stages": stage_counts,
    }


@router.get("/{lead_id}")
async def get_lead(
    lead_id: str,
    admin: dict = Depends(require_admin)
):
    """Get detailed lead information."""
    lead = await db.leads.find_one({"lead_id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    _enrich_lead(lead)

    activities = await db.lead_activities.find(
        {"lead_id": lead_id},
        {"_id": 0}
    ).sort("created_at", -1).limit(50).to_list(50)
    lead["activities"] = activities

    return lead


@router.patch("/{lead_id}")
async def update_lead(
    lead_id: str,
    update: LeadUpdate,
    admin: dict = Depends(require_admin)
):
    """Update a lead's stage, notes, or next action."""
    lead = await db.leads.find_one({"lead_id": lead_id})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    update_data = {}
    old_stage = lead.get("stage")

    if update.stage:
        if update.stage not in LEAD_STAGES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid stage. Must be one of: {', '.join(LEAD_STAGES)}"
            )
        update_data["stage"] = update.stage
        update_data["manual_stage_override"] = True

    if update.notes is not None:
        update_data["notes"] = update.notes

    if update.next_action is not None:
        update_data["next_action"] = update.next_action

    if update_data:
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.leads.update_one(
            {"lead_id": lead_id},
            {"$set": update_data}
        )

        if update.stage and update.stage != old_stage:
            await _log_activity(
                lead_id, "stage_change",
                f"Stage changed from {old_stage} to {update.stage} (manual)"
            )
            await notify_lead_stage_change(
                name=lead.get("name", ""),
                email=lead.get("email", ""),
                old_stage=old_stage or "unknown",
                new_stage=update.stage,
                details=update.notes
            )

        if update.notes:
            await _log_activity(lead_id, "note_added", update.notes)

    return {"success": True, "lead_id": lead_id}


@router.post("/{lead_id}/notes")
async def add_lead_note(
    lead_id: str,
    note: LeadNote,
    admin: dict = Depends(require_admin)
):
    """Add a note to a lead's activity log."""
    lead = await db.leads.find_one({"lead_id": lead_id})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    await _log_activity(lead_id, note.action_type, note.content)
    return {"success": True, "lead_id": lead_id}


# ==================== INTERNAL HELPERS ====================


async def _log_activity(lead_id: str, action_type: str, content: str):
    """Log an activity entry for a lead."""
    await db.lead_activities.insert_one({
        "activity_id": f"act_{uuid.uuid4().hex[:12]}",
        "lead_id": lead_id,
        "action_type": action_type,
        "content": content,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


async def mark_lead_as_subscribed(email: str, user_id: str):
    """
    Mark an existing lead as having subscribed to TrustOffice.
    Called from the Stripe webhook when a lead completes checkout.
    This is the bridge between the lead CRM and the subscription system.
    """
    lead = await db.leads.find_one({"email": email})
    if not lead:
        logger.info(f"No lead found for {email} — they subscribed without being a lead first")
        return

    old_stage = lead.get("stage")
    now = datetime.now(timezone.utc)

    await db.leads.update_one(
        {"email": email},
        {"$set": {
            "lead_type": "paid_subscriber",
            "subscription_status": "active",
            "user_id": user_id,
            "stage": "converted",
            "manual_stage_override": False,
            "updated_at": now.isoformat(),
        }}
    )

    if old_stage != "converted":
        await _log_activity(
            lead["lead_id"], "stage_change",
            f"Auto-advanced from {old_stage} to converted (subscribed to TrustOffice)"
        )
        await notify_lead_stage_change(
            name=lead.get("name", ""),
            email=email,
            old_stage=old_stage or "unknown",
            new_stage="converted",
            details="Subscribed to TrustOffice"
        )

    logger.info(f"Lead {lead['lead_id']} marked as subscribed — {email}")


async def update_lead_course_progress(email: str, lessons_watched: int):
    """
    Update a lead's course progress and auto-advance stage.
    Called from the course progress tracking endpoint.
    Does NOT override manual stage overrides.
    """
    lead = await db.leads.find_one({"email": email})
    if not lead:
        return

    if lead.get("manual_stage_override"):
        await db.leads.update_one(
            {"email": email},
            {"$set": {
                "lessons_watched": lessons_watched,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }}
        )
        return

    old_stage = lead.get("stage")
    update = {
        "lessons_watched": lessons_watched,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Auto-advance: new → engaged when they watch their first lesson
    if lessons_watched > 0 and old_stage == "new":
        update["stage"] = "engaged"

    await db.leads.update_one(
        {"email": email},
        {"$set": update}
    )

    if update.get("stage") and update["stage"] != old_stage:
        await _log_activity(
            lead["lead_id"],
            "stage_change",
            f"Auto-advanced from {old_stage} to {update['stage']} (watched {lessons_watched}/9 lessons)"
        )
        await notify_lead_stage_change(
            name=lead.get("name", ""),
            email=email,
            old_stage=old_stage or "unknown",
            new_stage=update["stage"],
            details=f"Watched {lessons_watched}/9 lessons"
        )
