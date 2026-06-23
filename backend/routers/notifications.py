"""
Notifications Router — Admin Notification Feed
Tracks lead events (new lead, stage change, booked call, conversion)
and provides a lightweight polling endpoint for the frontend bell icon.
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from database import db
from routers.admin import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/notifications", tags=["notifications"])

# ==================== SCHEMAS ====================

NOTIFICATION_TYPES = [
    "new_lead",
    "lead_stage_change",
    "booked_call",
    "lead_converted",
    "task_overdue",
]

NOTIFICATION_ICONS = {
    "new_lead": "🆕",
    "lead_stage_change": "🔄",
    "booked_call": "📞",
    "lead_converted": "✅",
    "task_overdue": "⏰",
}

NOTIFICATION_PRIORITIES = {
    "new_lead": "normal",
    "lead_stage_change": "normal",
    "booked_call": "high",
    "lead_converted": "normal",
    "task_overdue": "high",
}


# ==================== CREATE NOTIFICATION ====================


async def create_notification(
    type: str,
    title: str,
    body: str,
    lead_id: Optional[str] = None,
    lead_email: Optional[str] = None,
    lead_name: Optional[str] = None,
    priority: Optional[str] = None,
):
    """Create a notification document in MongoDB. Called from leads.py hooks."""
    if type not in NOTIFICATION_TYPES:
        logger.warning(f"Unknown notification type: {type}")
        return

    now = datetime.now(timezone.utc)
    notification = {
        "notification_id": f"notif_{uuid.uuid4().hex[:12]}",
        "type": type,
        "priority": priority or NOTIFICATION_PRIORITIES.get(type, "normal"),
        "title": title,
        "body": body,
        "lead_id": lead_id,
        "lead_email": lead_email,
        "lead_name": lead_name,
        "read": False,
        "created_at": now.isoformat(),
        "read_at": None,
    }

    await db.notifications.insert_one(notification)
    logger.debug(f"Notification created: {notification['notification_id']} — {type}: {title}")
    return notification


# ==================== ENDPOINTS ====================


@router.get("")
async def get_notifications(
    unread_only: bool = Query(False, description="Only return unread notifications"),
    limit: int = Query(20, ge=1, le=100),
    admin: dict = Depends(require_admin),
):
    """Get the admin's notification feed."""
    query = {}
    if unread_only:
        query["read"] = False

    notifications = await db.notifications.find(
        query, {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)

    unread_count = await db.notifications.count_documents({"read": False})

    return {
        "notifications": notifications,
        "unread_count": unread_count,
    }


@router.get("/unread-count")
async def get_unread_count(
    admin: dict = Depends(require_admin),
):
    """Lightweight endpoint for polling — returns just the unread count."""
    count = await db.notifications.count_documents({"read": False})
    return {"count": count}


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    admin: dict = Depends(require_admin),
):
    """Mark a single notification as read."""
    result = await db.notifications.update_one(
        {"notification_id": notification_id},
        {
            "$set": {
                "read": True,
                "read_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"success": True}


@router.post("/mark-all-read")
async def mark_all_notifications_read(
    admin: dict = Depends(require_admin),
):
    """Mark all notifications as read."""
    result = await db.notifications.update_many(
        {"read": False},
        {
            "$set": {
                "read": True,
                "read_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    return {"success": True, "modified_count": result.modified_count}


# ==================== TRIAGE ENDPOINT ====================


@router.get("/triage")
async def get_lead_triage(
    admin: dict = Depends(require_admin),
):
    """
    Quick triage view: what needs attention right now.
    Returns grouped leads by priority bucket.
    """
    now = datetime.now(timezone.utc)
    yesterday = (now - timedelta(days=1)).isoformat()
    three_days_ago = (now - timedelta(days=3)).isoformat()
    seven_days_ago = (now - timedelta(days=7)).isoformat()

    # New leads today (not yet converted)
    new_today = await db.leads.find(
        {
            "created_at": {"$gte": yesterday},
            "stage": {"$ne": "converted"},
        },
        {"_id": 0},
    ).sort("created_at", -1).limit(10).to_list(10)

    # Booked calls not yet converted
    booked_calls = await db.leads.find(
        {
            "booked_call": True,
            "stage": {"$ne": "converted"},
        },
        {"_id": 0},
    ).sort("booked_call_at", -1).limit(10).to_list(10)

    # Needs follow-up: idle 3+ days, not converted/lost, has actionable next_action
    needs_followup = await db.leads.find(
        {
            "updated_at": {"$lt": three_days_ago},
            "stage": {"$nin": ["converted", "lost"]},
        },
        {"_id": 0},
    ).sort("score", -1).limit(10).to_list(10)

    # High-score idle: score >= 60, not converted
    high_score = await db.leads.find(
        {
            "score": {"$gte": 60},
            "stage": {"$ne": "converted"},
        },
        {"_id": 0},
    ).sort("score", -1).limit(5).to_list(5)

    # Stage summary (funnel counts)
    stage_summary = {}
    for s in ["new", "engaged", "warm", "converted", "lost"]:
        stage_summary[s] = await db.leads.count_documents({"stage": s})
    total = await db.leads.count_documents({})

    # Recent conversions (last 7 days)
    recent_conversions = await db.leads.find(
        {
            "stage": "converted",
            "updated_at": {"$gte": seven_days_ago},
        },
        {"_id": 0},
    ).sort("updated_at", -1).limit(5).to_list(5)

    # Enrich all leads with score/stage/next_action
    from routers.leads import _enrich_lead

    for lead in new_today:
        _enrich_lead(lead)
    for lead in booked_calls:
        _enrich_lead(lead)
    for lead in needs_followup:
        _enrich_lead(lead)
    for lead in high_score:
        _enrich_lead(lead)
    for lead in recent_conversions:
        _enrich_lead(lead)

    return {
        "new_today": new_today,
        "new_today_count": len(new_today),
        "booked_calls": booked_calls,
        "booked_calls_count": len(booked_calls),
        "needs_followup": needs_followup,
        "needs_followup_count": len(needs_followup),
        "high_score_idle": high_score,
        "stage_summary": stage_summary,
        "total_leads": total,
        "recent_conversions": recent_conversions,
    }


# ==================== EMAIL TEMPLATES ====================


@router.get("/templates")
async def list_templates(
    admin: dict = Depends(require_admin),
):
    """List all follow-up email templates. Seeds defaults if empty."""
    templates = await db.lead_email_templates.find({}, {"_id": 0}).to_list(50)
    if not templates:
        templates = await _seed_default_templates()
    return {"templates": templates}


class FollowUpTemplate(BaseModel):
    name: str
    subject: str
    body: str
    trigger_stage: Optional[str] = None


@router.post("/templates")
async def create_template(
    template: FollowUpTemplate,
    admin: dict = Depends(require_admin),
):
    """Create a new follow-up email template."""
    template_id = f"tpl_{uuid.uuid4().hex[:8]}"
    doc = {
        "template_id": template_id,
        "name": template.name,
        "subject": template.subject,
        "body": template.body,
        "trigger_stage": template.trigger_stage,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.lead_email_templates.insert_one(doc)
    return {"success": True, "template_id": template_id}


@router.put("/templates/{template_id}")
async def update_template(
    template_id: str,
    template: FollowUpTemplate,
    admin: dict = Depends(require_admin),
):
    """Update an existing email template."""
    result = await db.lead_email_templates.update_one(
        {"template_id": template_id},
        {
            "$set": {
                "name": template.name,
                "subject": template.subject,
                "body": template.body,
                "trigger_stage": template.trigger_stage,
            }
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"success": True, "modified": result.modified_count > 0}


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: str,
    admin: dict = Depends(require_admin),
):
    """Delete an email template."""
    result = await db.lead_email_templates.delete_one({"template_id": template_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"success": True}


# ==================== SEND FOLLOW-UP EMAIL ====================


class SendEmailRequest(BaseModel):
    """Request body for sending a follow-up email."""
    template_id: str
    custom_subject: Optional[str] = None
    custom_body: Optional[str] = None


@router.post("/{lead_id}/send-email")
async def send_followup_email(
    lead_id: str,
    req: SendEmailRequest,
    admin: dict = Depends(require_admin),
):
    """Send a follow-up email to a lead using a template. Rate-limited: 1 per lead per 5 min."""
    from routers.leads import _log_activity

    lead = await db.leads.find_one({"lead_id": lead_id})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    to_email = lead.get("email")
    if not to_email:
        raise HTTPException(status_code=400, detail="Lead has no email address")

    # Rate limit: 1 email per lead per 5 minutes
    now = datetime.now(timezone.utc)
    five_min_ago = (now - timedelta(minutes=5)).isoformat()
    recent = await db.lead_activities.find_one({
        "lead_id": lead_id,
        "action_type": "email",
        "created_at": {"$gte": five_min_ago},
    })
    if recent:
        raise HTTPException(
            status_code=429,
            detail="Email already sent to this lead recently — please wait 5 minutes"
        )

    template = await db.lead_email_templates.find_one({"template_id": req.template_id})
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Build email body with variable substitution
    def _fill(text):
        return (text or "").replace("{name}", lead.get("name", "")) \
            .replace("{email}", lead.get("email", "")) \
            .replace("{source}", lead.get("source", "")) \
            .replace("{course_url}", "https://trustoffice.app/trustee-101") \
            .replace("{app_url}", "https://app.trustoffice.app")

    body = _fill(req.custom_body or template["body"])
    subject = _fill(req.custom_subject or template["subject"])

    # Send via Postmark
    from email_service import email_service

    try:
        await email_service.send_email(
            to_email=to_email,
            subject=subject,
            html_body=body,
        )
        await _log_activity(lead_id, "email", f"Sent follow-up: {template['name']}")
        logger.info(f"Follow-up email sent to {to_email}: {template['name']}")
        return {"success": True, "message": f"Follow-up sent to {to_email}"}
    except Exception as e:
        logger.error(f"Failed to send follow-up email to {to_email}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")


# ==================== DEFAULT TEMPLATES ====================


async def _seed_default_templates():
    """Seed 5 default follow-up email templates."""
    defaults = [
        {
            "template_id": "tpl_welcome_followup",
            "name": "Welcome Follow-Up",
            "subject": "Quick question, {name}",
            "body": """<p>Hi {name},</p>
<p>I noticed you recently signed up for the Trustee 101 course — welcome!</p>
<p>Quick question: what brought you to TrustOffice? Are you a new trustee, or have you been managing a trust for a while?</p>
<p>Either way, I'd love to hear your story. Just hit reply.</p>
<p>— Kenneth</p>""",
            "trigger_stage": "new",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "template_id": "tpl_course_nudge",
            "name": "Course Nudge",
            "subject": "Lesson 4 is ready for you, {name}",
            "body": """<p>Hi {name},</p>
<p>I noticed you've been working through Trustee 101 — great progress.</p>
<p>Lesson 4 (HEMS Decoded) is where things get really practical. It covers the single most important rule for making trust distributions: Health, Education, Maintenance, and Support.</p>
<p><a href="{course_url}">Continue where you left off →</a></p>
<p>— Kenneth</p>""",
            "trigger_stage": "engaged",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "template_id": "tpl_call_prep",
            "name": "Discovery Call Prep",
            "subject": "Looking forward to our call, {name}",
            "body": """<p>Hi {name},</p>
<p>Looking forward to our discovery call. To make the most of our time, here's what we'll cover:</p>
<ul>
<li>Your current trust situation and what's working</li>
<li>Where you're feeling the friction</li>
<li>Whether TrustOffice is the right fit for you</li>
</ul>
<p>No need to prepare anything — just bring your questions.</p>
<p>— Kenneth</p>""",
            "trigger_stage": "new",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "template_id": "tpl_value_pitch",
            "name": "Value Pitch",
            "subject": "How trustees use TrustOffice — 3-minute tour",
            "body": """<p>Hi {name},</p>
<p>You've been checking out TrustOffice — here's a quick look at what it does for trustees like you:</p>
<ul>
<li><strong>Minutes that write themselves</strong> — guided templates, no blank page</li>
<li><strong>Distribution tracking</strong> — every dollar authorized and documented</li>
<li><strong>Defensibility score</strong> — know where you stand, fix what's weak</li>
</ul>
<p>Your first month is <strong>$29</strong> with code WELCOME29. No commitment beyond that.</p>
<p><a href="{app_url}/pricing">See plans →</a></p>
<p>— Kenneth</p>""",
            "trigger_stage": "warm",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "template_id": "tpl_win_back",
            "name": "Win-Back",
            "subject": "Still thinking about your trust, {name}?",
            "body": """<p>Hi {name},</p>
<p>It's been a little while since you checked out TrustOffice. I wanted to check in.</p>
<p>If the timing wasn't right, no pressure at all. But if you're still dealing with trust administration and wondering if there's a better way — we're here.</p>
<p>Happy to hop on a quick call if that's easier.</p>
<p>— Kenneth</p>""",
            "trigger_stage": "lost",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    ]

    for tpl in defaults:
        try:
            await db.lead_email_templates.update_one(
                {"template_id": tpl["template_id"]},
                {"$setOnInsert": tpl},
                upsert=True,
            )
        except Exception as e:
            logger.warning(f"Failed to seed template {tpl['template_id']}: {e}")

    templates = await db.lead_email_templates.find({}, {"_id": 0}).to_list(50)
    return templates
