"""
Leads Router — Lead Management for Marketing Entry Points
Captures leads from Trustee 101 enrollment, checklist downloads, and any other
marketing form. Tracks them through: new → engaged → warm → converted → lost.
"""
import csv
import io
import re
import os
import uuid
import json
import hmac
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from fastapi.responses import StreamingResponse, PlainTextResponse
from pydantic import BaseModel, EmailStr

from database import db
from routers.admin import require_admin
from discord_service import notify_new_lead, notify_lead_stage_change
from email_service import email_service
from routers.notifications import create_notification
import httpx

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
    "blog-article-pdf",
    "webinar-signup",
    "booked-call",
    "liability-protection-kit",
    "homepage-trustee-101",
    "commingling-explained",
    "distribution-guide",
    "new-trustee-guide",
    "trust-software-guide",
    "admin-checklist",
    "document-distributions",
    "fiduciary-duty-guide",
    "minutes-template",
    "private-trustee-guide",
    "resources-subscribe",
    "pricing-lead",
    "features-lead",
    "how-it-works-lead",
    "about-lead",
    "faq-lead",
    "for-professionals",
    "advisors",
    "get-started",
    "governance-offer",
    "trust-formalities-guide",
    "trust-governance-system",
    "manual",
    "direct",
    "facebook-lead-ad",
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
    referrer: Optional[str] = None  # document.referrer from the browser


class LeadUpdate(BaseModel):
    """Schema for updating a lead's stage or notes."""
    stage: Optional[str] = None
    notes: Optional[str] = None
    next_action: Optional[str] = None


class LeadNote(BaseModel):
    """Schema for adding a note to a lead."""
    content: str
    action_type: str = "manual"  # manual, email, call, system


class BulkStageUpdate(BaseModel):
    """Schema for bulk stage change."""
    lead_ids: List[str]
    stage: str


class BulkNoteAdd(BaseModel):
    """Schema for bulk note addition."""
    lead_ids: List[str]
    content: str
    action_type: str = "manual"


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
        "homepage-trustee-101": 5,      # Same as trustee-101
        "governance-offer": 5,          # Offer page — medium intent
        "trustee-90-day-checklist": 4,
        "commingling-checklist": 4,
        "commingling-explained": 4,     # Content guide — medium intent
        "distribution-guide": 4,
        "new-trustee-guide": 4,
        "trust-software-guide": 4,
        "admin-checklist": 4,
        "document-distributions": 4,
        "fiduciary-duty-guide": 4,
        "minutes-template": 4,
        "private-trustee-guide": 4,
        "trust-formalities-guide": 4,
        "trust-governance-system": 4,
        "for-professionals": 4,         # Professional pages — medium intent
        "advisors": 4,
        "get-started": 3,               # General interest
        "resources-subscribe": 3,
        "pricing-lead": 3,
        "features-lead": 3,
        "how-it-works-lead": 3,
        "about-lead": 2,
        "faq-lead": 2,
        "blog-subscribe": 2,            # Low intent — casual blog reader
        "blog-article-pdf": 2,           # Low intent — casual blog reader
        "direct": 1,                    # Unknown / direct traffic
        "manual": 0,                    # Manually entered
        "facebook-lead-ad": 7,          # Paid lead form submission
    }
    score += SOURCE_QUALITY.get(source, 1)

    return min(score, 100)


def get_score_breakdown(lead: dict) -> dict:
    """
    Return a detailed breakdown of how the lead score is calculated.
    """
    lessons_watched = lead.get("lessons_watched", 0)
    total_lessons = 9
    course_score = int((lessons_watched / total_lessons) * 40)

    days_since_login = _days_since(lead.get("last_login"))
    if days_since_login is not None:
        if days_since_login <= 1:
            login_score = 30
        elif days_since_login <= 3:
            login_score = 20
        elif days_since_login <= 7:
            login_score = 10
        elif days_since_login <= 14:
            login_score = 5
        else:
            login_score = 0
    else:
        login_score = 0

    days_since = _days_since(lead.get("created_at"))
    if days_since is not None:
        if days_since <= 7:
            recency_score = 20
        elif days_since <= 30:
            recency_score = 15
        elif days_since <= 60:
            recency_score = 10
        else:
            recency_score = 5
    else:
        recency_score = 0

    booked_call_score = 15 if lead.get("booked_call") else 0

    source = lead.get("source", "")
    SOURCE_QUALITY = {
        "booked-call": 10,
        "webinar-signup": 8,
        "liability-protection-kit": 6,
        "trustee-101-landing-page": 5,
        "homepage-trustee-101": 5,
        "governance-offer": 5,
        "trustee-90-day-checklist": 4,
        "commingling-checklist": 4,
        "commingling-explained": 4,
        "distribution-guide": 4,
        "new-trustee-guide": 4,
        "trust-software-guide": 4,
        "admin-checklist": 4,
        "document-distributions": 4,
        "fiduciary-duty-guide": 4,
        "minutes-template": 4,
        "private-trustee-guide": 4,
        "trust-formalities-guide": 4,
        "trust-governance-system": 4,
        "for-professionals": 4,
        "advisors": 4,
        "get-started": 3,
        "resources-subscribe": 3,
        "pricing-lead": 3,
        "features-lead": 3,
        "how-it-works-lead": 3,
        "about-lead": 2,
        "faq-lead": 2,
        "blog-subscribe": 2,
        "blog-article-pdf": 2,
        "direct": 1,
        "manual": 0,
        "facebook-lead-ad": 7,
    }
    source_score = SOURCE_QUALITY.get(source, 1)

    return {
        "course_progress": {"score": course_score, "max": 40, "detail": f"{lessons_watched}/{total_lessons} lessons"},
        "login_frequency": {"score": login_score, "max": 30, "detail": f"Last login: {_days_since(lead.get('last_login'))} days ago" if lead.get('last_login') else "Never logged in"},
        "recency": {"score": recency_score, "max": 20, "detail": f"Captured {_days_since(lead.get('created_at'))} days ago" if lead.get('created_at') else "Unknown"},
        "booked_call": {"score": booked_call_score, "max": 15, "detail": "Booked a discovery call" if lead.get("booked_call") else "No call booked"},
        "source_quality": {"score": source_score, "max": 10, "detail": f"Source: {source}"},
    }


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
                "referrer": lead.referrer,
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
        "referrer": lead.referrer,
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

    # Create in-app notification
    await create_notification(
        type="new_lead",
        title=f"New lead: {name}",
        body=f"Source: {source} · Score: 50",
        lead_id=lead_id,
        lead_email=email,
        lead_name=name,
    )

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
    
    # Create in-app notification
    await create_notification(
        type="booked_call",
        title=f"Discovery call booked: {name}",
        body=f"Booked a TrustOffice Discovery Call",
        lead_id=lead_id,
        lead_email=email,
        lead_name=name,
        priority="high",
    )

    return {"success": True, "lead_id": lead_id, "is_returning": False}


# ==================== FACEBOOK LEAD ADS WEBHOOK ====================

# Verify token for Facebook webhook subscription verification.
# Set via Railway env var FB_WEBHOOK_VERIFY_TOKEN.
# Facebook sends this during the initial webhook setup to confirm ownership.
FB_WEBHOOK_VERIFY_TOKEN = os.environ.get("FB_WEBHOOK_VERIFY_TOKEN", "")
FB_PAGE_ACCESS_TOKEN = os.environ.get("FB_PAGE_ACCESS_TOKEN", "")
FB_APP_ID = os.environ.get("FB_APP_ID", "")
FB_APP_SECRET = os.environ.get("FB_APP_SECRET", "")


@router.get("/facebook-webhook", include_in_schema=False)
async def facebook_webhook_verify(
    request: Request,
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    """
    Facebook webhook verification endpoint.
    Facebook sends a GET request with hub.mode=subscribe, hub.verify_token=<your token>,
    and hub.challenge=<a string>. We verify the token and return the challenge.
    This is called once during webhook setup in the Meta Developer dashboard.
    """
    if hub_mode == "subscribe" and hub_verify_token == FB_WEBHOOK_VERIFY_TOKEN:
        logger.info("Facebook webhook verification successful")
        return PlainTextResponse(hub_challenge)
    else:
        logger.warning(
            f"Facebook webhook verification failed — mode={hub_mode}, "
            f"token_match={hub_verify_token == FB_WEBHOOK_VERIFY_TOKEN}"
        )
        raise HTTPException(status_code=403, detail="Webhook verification failed")


@router.post("/facebook-webhook", include_in_schema=False)
async def facebook_webhook_handler(request: Request):
    """
    Facebook Lead Ads webhook endpoint.
    Called by Facebook in real-time when someone submits a lead form on your ad.
    
    Flow:
    1. Facebook sends a webhook event with leadgen_id
    2. We fetch the actual form data from Facebook's Graph API using the Page Access Token
    3. We create/update a lead in the CRM with source="facebook-lead-ad"
    4. Discord notification + welcome email fire automatically
    
    No auth required — Facebook signs the payload with X-Hub-Signature-256.
    We verify the signature using the App Secret for security.
    """
    try:
        body = await request.body()
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Verify X-Hub-Signature-256 header for security
    if FB_APP_SECRET:
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not _verify_facebook_signature(body, signature, FB_APP_SECRET):
            logger.warning("Facebook webhook signature verification failed")
            raise HTTPException(status_code=403, detail="Signature verification failed")

    # Facebook webhook payload structure:
    # {"entry": [{"changes": [{"field": "leadgen", "value": {"leadgen_id": "xxx", "page_id": "yyy", "form_id": "zzz"}}]}], "object": "page"}
    if payload.get("object") != "page":
        logger.info(f"Facebook webhook received non-page object: {payload.get('object')}")
        return {"success": True, "message": "Ignored non-page object"}

    entries = payload.get("entry", [])
    results = []

    for entry in entries:
        page_id = entry.get("id")
        changes = entry.get("changes", [])

        for change in changes:
            if change.get("field") != "leadgen":
                continue

            leadgen_data = change.get("value", {})
            leadgen_id = leadgen_data.get("leadgen_id")
            form_id = leadgen_data.get("form_id")

            if not leadgen_id:
                logger.warning("Facebook webhook: leadgen_id missing from payload")
                continue

            if not FB_PAGE_ACCESS_TOKEN:
                logger.error("FB_PAGE_ACCESS_TOKEN not set — cannot fetch lead data from Facebook")
                results.append({"leadgen_id": leadgen_id, "success": False, "error": "No page access token"})
                continue

            # Fetch the actual lead data from Facebook Graph API
            lead_data = await _fetch_facebook_lead_data(leadgen_id, FB_PAGE_ACCESS_TOKEN)

            if not lead_data:
                logger.error(f"Failed to fetch lead data for leadgen_id={leadgen_id}")
                results.append({"leadgen_id": leadgen_id, "success": False, "error": "Graph API fetch failed"})
                continue

            # Extract name and email from the form data
            field_data = lead_data.get("field_data", [])
            name = ""
            email = ""
            phone = ""
            city = ""
            for field in field_data:
                field_name = field.get("name", "").lower()
                values = field.get("values", [])
                value = values[0] if values else ""

                if field_name in ("full_name", "name", "first_name"):
                    name = value
                elif field_name in ("email", "work_email", "personal_email"):
                    email = value
                elif field_name in ("phone_number", "phone", "mobile"):
                    phone = value
                elif field_name == "city":
                    city = value

            if not name:
                name = lead_data.get("name", "Unknown")

            if not email:
                logger.warning(f"Facebook lead {leadgen_id} has no email — storing with leadgen_id only")
                # Still create the lead so we don't lose it
                email = f"fb_lead_{leadgen_id}@no-email.local"

            email = email.strip().lower()

            # Check if lead already exists by email
            existing = await db.leads.find_one({"email": email})
            if existing:
                await db.leads.update_one(
                    {"email": email},
                    {"$set": {
                        "name": name or existing.get("name", "Unknown"),
                        "source": "facebook-lead-ad",
                        "phone": phone or existing.get("phone"),
                        "city": city or existing.get("city"),
                        "facebook_leadgen_id": leadgen_id,
                        "facebook_form_id": form_id,
                        "facebook_page_id": page_id,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }}
                )
                lead_id = existing["lead_id"]
                await _log_activity(lead_id, "facebook_lead", f"Lead form submitted via Facebook Ad (leadgen_id: {leadgen_id})")
                logger.info(f"Facebook lead updated: {lead_id} — {email}")
                results.append({"leadgen_id": leadgen_id, "lead_id": lead_id, "success": True, "is_returning": True})
                continue

            # Create new lead
            now = datetime.now(timezone.utc)
            lead_id = f"lead_{uuid.uuid4().hex[:12]}"

            lead_doc = {
                "lead_id": lead_id,
                "email": email,
                "name": name,
                "source": "facebook-lead-ad",
                "lead_type": "email_capture",
                "phone": phone,
                "city": city,
                "facebook_leadgen_id": leadgen_id,
                "facebook_form_id": form_id,
                "facebook_page_id": page_id,
                "utm_source": "facebook",
                "utm_medium": "paid-social",
                "utm_campaign": f"meta-lead-ad-{form_id}" if form_id else "meta-lead-ad",
                "stage": "new",
                "manual_stage_override": False,
                "booked_call": False,
                "lessons_watched": 0,
                "subscription_status": None,
                "last_login": None,
                "notes": "",
                "next_action": "Follow up on Facebook lead form submission",
                "score": 70,  # Paid lead form = high intent
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }

            await db.leads.insert_one(lead_doc)
            await _log_activity(lead_id, "created", f"Lead captured via Facebook Lead Ad (form: {form_id})")
            await _log_activity(lead_id, "facebook_lead", f"Lead form submitted via Facebook Ad (leadgen_id: {leadgen_id})")

            # Send Discord notification
            await notify_new_lead(
                name=name,
                email=email,
                source="facebook-lead-ad",
                lead_stage="new"
            )

            # Create in-app notification
            await create_notification(
                type="new_lead",
                title=f"New Facebook lead: {name}",
                body=f"Source: Facebook Lead Ad · Phone: {phone or 'N/A'}",
                lead_id=lead_id,
                lead_email=email,
                lead_name=name,
            )

            # Send welcome email (fire-and-forget — only if we have a real email)
            if email and not email.endswith("@no-email.local"):
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

            logger.info(f"Facebook lead captured: {lead_id} — {name} — {email}")
            results.append({"leadgen_id": leadgen_id, "lead_id": lead_id, "success": True, "is_returning": False})

    return {"success": True, "processed": len(results), "results": results}


def _verify_facebook_signature(payload: bytes, signature: str, app_secret: str) -> bool:
    """
    Verify the X-Hub-Signature-256 header sent by Facebook.
    Facebook computes HMAC-SHA256 of the request body using the App Secret
    and sends it as 'sha256=<hex_digest>'.
    """
    if not signature or not signature.startswith("sha256="):
        return False
    expected = signature.split("=", 1)[1]
    computed = hmac.new(
        app_secret.encode("utf-8"),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, computed)


async def _fetch_facebook_lead_data(leadgen_id: str, access_token: str) -> Optional[dict]:
    """
    Fetch lead data from Facebook Graph API.
    Endpoint: GET /{leadgen_id}?fields=field_data,name
    """
    url = f"https://graph.facebook.com/v18.0/{leadgen_id}"
    params = {
        "fields": "field_data,name",
        "access_token": access_token,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Facebook Graph API error for leadgen_id={leadgen_id}: {e.response.status_code} {e.response.text[:200]}")
        return None
    except Exception as e:
        logger.error(f"Failed to fetch Facebook lead data for {leadgen_id}: {e}")
        return None


@router.get("/analytics")
async def get_lead_analytics(
    admin: dict = Depends(require_admin)
):
    """Get lead analytics: funnel, conversion by source, time-to-convert, trend."""
    now = datetime.now(timezone.utc)

    # 1. Funnel counts
    funnel = {}
    for s in LEAD_STAGES:
        funnel[s] = await db.leads.count_documents({"stage": s})
    total = await db.leads.count_documents({})
    funnel["all"] = total

    # 2. Conversion rate by source
    pipeline = [
        {"$group": {
            "_id": "$source",
            "total": {"$sum": 1},
            "converted": {"$sum": {"$cond": [{"$eq": ["$stage", "converted"]}, 1, 0]}},
        }},
        {"$sort": {"total": -1}},
    ]
    source_stats_raw = await db.leads.aggregate(pipeline).to_list(50)
    source_stats = []
    for s in source_stats_raw:
        source_stats.append({
            "source": s["_id"] or "unknown",
            "total": s["total"],
            "converted": s["converted"],
            "conversion_rate": round(s["converted"] / s["total"] * 100, 1) if s["total"] > 0 else 0,
        })

    # 3. Time-to-convert (median days from capture to conversion)
    converted_leads = await db.leads.find(
        {"stage": "converted", "created_at": {"$ne": None}},
        {"_id": 0, "created_at": 1, "updated_at": 1}
    ).to_list(1000)

    conversion_times = []
    for lead in converted_leads:
        created = _parse_iso_date(lead.get("created_at"))
        updated = _parse_iso_date(lead.get("updated_at"))
        if created and updated:
            days = (updated - created).days
            if days >= 0:
                conversion_times.append(days)

    avg_time_to_convert = round(sum(conversion_times) / len(conversion_times), 1) if conversion_times else None
    median_time_to_convert = sorted(conversion_times)[len(conversion_times) // 2] if conversion_times else None

    # 4. Trend (leads per day for last 30 days)
    thirty_days_ago = (now - timedelta(days=30)).isoformat()
    trend_pipeline = [
        {"$match": {"created_at": {"$gte": thirty_days_ago}}},
        {"$group": {
            "_id": {"$substr": ["$created_at", 0, 10]},
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
    ]
    trend_raw = await db.leads.aggregate(trend_pipeline).to_list(30)
    trend = [{"date": t["_id"], "count": t["count"]} for t in trend_raw]

    # 5. Stage velocity (avg days in each stage)
    # We estimate from activity logs — count stage_change activities per lead
    velocity = {}
    for s in LEAD_STAGES:
        velocity[s] = await db.leads.count_documents({"stage": s})

    return {
        "funnel": funnel,
        "source_stats": source_stats,
        "avg_time_to_convert_days": avg_time_to_convert,
        "median_time_to_convert_days": median_time_to_convert,
        "total_converted": len(conversion_times),
        "trend": trend,
        "total_leads": total,
    }


# ==================== EXPORT ENDPOINT ====================


@router.get("/export")
async def export_leads_csv(
    stage: Optional[str] = Query(None, description="Filter by stage"),
    source: Optional[str] = Query(None, description="Filter by source"),
    admin: dict = Depends(require_admin)
):
    """Export leads as CSV."""
    query = {}
    if stage and stage != "all":
        if stage not in LEAD_STAGES:
            raise HTTPException(status_code=400, detail=f"Invalid stage: {stage}")
        query["stage"] = stage
    if source:
        query["source"] = source

    leads = await db.leads.find(query, {"_id": 0}).sort("created_at", -1).to_list(5000)

    # Enrich all leads
    for lead in leads:
        _enrich_lead(lead)

    # Build CSV
    output = io.StringIO()
    writer = csv.writer(output)

    headers = [
        "Lead ID", "Name", "Email", "Stage", "Score", "Source",
        "UTM Source", "UTM Campaign", "UTM Medium", "Referrer",
        "Lessons Watched", "Booked Call", "Subscription Status",
        "Created At", "Updated At", "Next Action", "Notes"
    ]
    writer.writerow(headers)

    for lead in leads:
        writer.writerow([
            lead.get("lead_id", ""),
            lead.get("name", ""),
            lead.get("email", ""),
            lead.get("stage", ""),
            lead.get("score", 0),
            lead.get("source", ""),
            lead.get("utm_source", ""),
            lead.get("utm_campaign", ""),
            lead.get("utm_medium", ""),
            lead.get("referrer", ""),
            lead.get("lessons_watched", 0),
            "Yes" if lead.get("booked_call") else "No",
            lead.get("subscription_status", ""),
            lead.get("created_at", ""),
            lead.get("updated_at", ""),
            lead.get("next_action", ""),
            lead.get("notes", ""),
        ])

    output.seek(0)
    filename = f"trustoffice-leads-{datetime.now().strftime('%Y-%m-%d')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ==================== BULK ACTION ENDPOINTS ====================


@router.post("/bulk/stage")
async def bulk_update_stage(
    update: BulkStageUpdate,
    admin: dict = Depends(require_admin)
):
    """Bulk update stage for multiple leads."""
    if update.stage not in LEAD_STAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid stage. Must be one of: {', '.join(LEAD_STAGES)}"
        )

    now = datetime.now(timezone.utc)
    result = await db.leads.update_many(
        {"lead_id": {"$in": update.lead_ids}},
        {"$set": {
            "stage": update.stage,
            "manual_stage_override": True,
            "updated_at": now.isoformat(),
        }}
    )

    # Log activities
    for lead_id in update.lead_ids:
        await _log_activity(lead_id, "stage_change", f"Bulk stage change to {update.stage}")

    logger.info(f"Bulk stage update: {result.modified_count} leads changed to {update.stage}")
    return {"success": True, "modified_count": result.modified_count}


@router.post("/bulk/notes")
async def bulk_add_notes(
    note: BulkNoteAdd,
    admin: dict = Depends(require_admin)
):
    """Bulk add notes to multiple leads."""
    for lead_id in note.lead_ids:
        await _log_activity(lead_id, note.action_type, note.content)

    logger.info(f"Bulk note added to {len(note.lead_ids)} leads")
    return {"success": True, "affected_count": len(note.lead_ids)}


@router.post("/bulk/export")
async def bulk_export_csv(
    lead_ids: List[str],
    admin: dict = Depends(require_admin)
):
    """Export selected leads as CSV."""
    leads = await db.leads.find(
        {"lead_id": {"$in": lead_ids}},
        {"_id": 0}
    ).to_list(len(lead_ids))

    for lead in leads:
        _enrich_lead(lead)

    output = io.StringIO()
    writer = csv.writer(output)

    headers = [
        "Lead ID", "Name", "Email", "Stage", "Score", "Source",
        "UTM Source", "UTM Campaign", "UTM Medium", "Referrer",
        "Lessons Watched", "Booked Call", "Subscription Status",
        "Created At", "Updated At", "Next Action", "Notes"
    ]
    writer.writerow(headers)

    for lead in leads:
        writer.writerow([
            lead.get("lead_id", ""),
            lead.get("name", ""),
            lead.get("email", ""),
            lead.get("stage", ""),
            lead.get("score", 0),
            lead.get("source", ""),
            lead.get("utm_source", ""),
            lead.get("utm_campaign", ""),
            lead.get("utm_medium", ""),
            lead.get("referrer", ""),
            lead.get("lessons_watched", 0),
            "Yes" if lead.get("booked_call") else "No",
            lead.get("subscription_status", ""),
            lead.get("created_at", ""),
            lead.get("updated_at", ""),
            lead.get("next_action", ""),
            lead.get("notes", ""),
        ])

    output.seek(0)
    filename = f"trustoffice-selected-leads-{datetime.now().strftime('%Y-%m-%d')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


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
    """Get detailed lead information with score breakdown."""
    lead = await db.leads.find_one({"lead_id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    _enrich_lead(lead)
    lead["score_breakdown"] = get_score_breakdown(lead)

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
            # Create in-app notification for stage change
            await create_notification(
                type="lead_stage_change",
                title=f"Lead stage changed: {lead.get('name', '')}",
                body=f"{old_stage} → {update.stage}",
                lead_id=lead_id,
                lead_email=lead.get("email", ""),
                lead_name=lead.get("name", ""),
            )

            # Create in-app notification for stage change
            from routers.notifications import create_notification
            await create_notification(
                type="lead_stage_change",
                title=f"Lead stage changed: {lead.get('name', '')}",
                body=f"{old_stage} → {update.stage}",
                lead_id=lead_id,
                lead_email=lead.get("email"),
                lead_name=lead.get("name"),
            )

        if update.notes:
            await _log_activity(lead_id, "note_added", update.notes)

    return {"success": True, "lead_id": lead_id}


@router.post("/{lead_id}/course-progress")
async def set_lead_course_progress(
    lead_id: str,
    body: dict,
    admin: dict = Depends(require_admin)
):
    """Set a lead's course progress. Auto-advances stage from new → engaged."""
    lead = await db.leads.find_one({"lead_id": lead_id})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lessons_watched = body.get("lessons_watched", 0)
    email = lead.get("email")
    if email:
        await update_lead_course_progress(email, lessons_watched)
    else:
        # Fallback: update directly
        await db.leads.update_one(
            {"lead_id": lead_id},
            {"$set": {
                "lessons_watched": lessons_watched,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }}
        )

    return {"success": True, "lead_id": lead_id, "lessons_watched": lessons_watched}


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
        # Create in-app notification for conversion
        await create_notification(
            type="lead_converted",
            title=f"Lead converted: {lead.get('name', '')}",
            body=f"Subscribed to TrustOffice (was: {old_stage})",
            lead_id=lead["lead_id"],
            lead_email=email,
            lead_name=lead.get("name", ""),
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
