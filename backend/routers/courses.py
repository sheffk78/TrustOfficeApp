"""
Trustee 101 Course Router
9-lesson curriculum (1 lesson = 1 video), public enrollment,
access control, progress tracking, and landing page.
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, EmailStr, field_validator
from datetime import datetime, timezone
from typing import Optional, Dict, List
from pathlib import Path
import uuid
import logging

from database import db
from email_service import email_service
from email_templates import _base_template
from dependencies import get_subscription_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/courses", tags=["courses"])

# ==================== CURRICULUM DATA ====================

CURRICULUM = [
    {
        "lesson": 1,
        "title": "What Is a Trust?",
        "video_guid": "b095719e-96c6-4a0a-a845-5f003777ff2f",
        "duration": "~7 min",
        "free": True,
        "pdf_url": None,
        "status": "ready",
    },
    {
        "lesson": 2,
        "title": "Should You Accept?",
        "video_guid": "670222ba-cde6-4772-b3af-dac84fd91db0",
        "duration": "~6 min",
        "free": True,
        "pdf_url": None,
        "status": "ready",
    },
    {
        "lesson": 3,
        "title": "Meeting Minutes Are Not Optional",
        "video_guid": "9a645c14-7506-4b3d-81fa-ac17f17741cc",
        "duration": "~8 min",
        "free": True,
        "pdf_url": "/pdfs/minute-templates-l3.pdf",
        "status": "ready",
    },
    {
        "lesson": 4,
        "title": "HEMS Decoded",
        "video_guid": "41982ee9-6c8a-4fe7-babd-29671b44a82c",
        "duration": "~16 min",
        "free": False,
        "pdf_url": "/pdfs/hems-decision-framework.pdf",
        "status": "ready",
    },
    {
        "lesson": 5,
        "title": "The Commingling Trap",
        "video_guid": "27edf118-8dc1-41b8-b32a-0c5057a55fec",
        "duration": "~15 min",
        "free": False,
        "pdf_url": "/pdfs/separation-checklist.pdf",
        "status": "ready",
    },
    {
        "lesson": 6,
        "title": "Trust Taxes in Plain English",
        "video_guid": "80134112-c35b-4c83-802d-362e42cc1ad2",
        "duration": "~12 min",
        "free": False,
        "pdf_url": "/pdfs/trust-tax-calendar-l6.pdf",
        "status": "ready",
    },
    {
        "lesson": 7,
        "title": "Prudent Investor Rule",
        "video_guid": "d9b23903-e21f-4696-87c9-582be96c5867",
        "duration": "~12 min",
        "free": False,
        "pdf_url": "/pdfs/investment-policy-statement-template-l7.pdf",
        "status": "ready",
    },
    {
        "lesson": 8,
        "title": "Beneficiary Communication",
        "video_guid": "c8c94726-c534-414b-ac20-0702a2427021",
        "duration": "~13 min",
        "free": False,
        "pdf_url": "/pdfs/beneficiary-communication-templates-l8.pdf",
        "status": "ready",
    },
    {
        "lesson": 9,
        "title": "Family Trusts and Sibling Dynamics",
        "video_guid": "4a9c7291-43ba-4231-9772-8832b232c97a",
        "duration": "~12 min",
        "free": False,
        "pdf_url": "/pdfs/family-governance-framework-l9.pdf",
        "status": "ready",
    },
    {
        "lesson": 10,
        "title": "HEMS Decoded",
        "video_guid": "ac5f3e48-470c-48b7-a142-2db5d632558b",
        "duration": "~8 min",
        "free": False,
        "pdf_url": "/pdfs/hems-decision-framework.pdf",
        "status": "ready",
    },
]


# ==================== SCHEMAS ====================

class CourseEnrollment(BaseModel):
    name: str
    email: EmailStr
    source: Optional[str] = "trustee-101-landing-page"
    utm_source: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_medium: Optional[str] = None

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        v = v.strip()
        if not v:
            raise ValueError('Name is required')
        if len(v) < 2:
            raise ValueError('Name must be at least 2 characters')
        if len(v) > 100:
            raise ValueError('Name must be less than 100 characters')
        return v


# ==================== PUBLIC ENDPOINTS ====================

@router.get("/trustee-101")
async def trustee_101_landing_page():
    """Serve the Trustee 101 landing page. No authentication required."""
    html = _get_landing_page_html()
    return HTMLResponse(content=html)


@router.get("/trustee-101/curriculum")
async def get_curriculum():
    """Return the 9-lesson curriculum as JSON."""
    return JSONResponse(content={
        "course": "Trustee 101",
        "tagline": "The Course That Should Have Come With Your Trust Document",
        "total_lessons": 9,
        "free_lessons": [1, 2, 3],
        "lessons": CURRICULUM,
    })


@router.post("/trustee-101/enroll")
async def enroll_in_trustee_101(enrollment: CourseEnrollment, request: Request):
    """Enroll in free Lesson 1 of Trustee 101 course.

    Stores lead, sends access email via Postmark with:
    - Video embed for Lesson 1
    - Lesson 1 info
    - Subscription CTA for full 9-lesson course
    """
    try:
        name = enrollment.name.strip()
        email = enrollment.email.strip().lower()
        source = enrollment.source or "trustee-101-landing-page"

        # Check if already enrolled
        existing = await db.course_leads.find_one({"email": email})
        if existing:
            # Already enrolled — re-send access email
            await _send_lesson_1_access_email(email, name)
            return {
                "success": True,
                "message": "Access re-sent. Check your email for Lesson 1.",
                "is_returning": True,
            }

        # Create lead record
        lead = {
            "email": email,
            "name": name,
            "source": source,
            "lesson_1_access_granted": True,
            "lesson_1_watched": False,
            "course_purchased": False,
            "stripe_session_id": None,
            "stripe_customer_id": None,
            "nurture_email_sent": {"1": False, "2": False, "3": False},
            "trustoffice_trial_started": False,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        await db.course_leads.insert_one(lead)

        # Also capture in the lead CRM
        try:
            from routers.leads import capture_lead as _capture_lead
            from routers.leads import LeadCapture as _LeadCapture
            await _capture_lead(_LeadCapture(
                name=name,
                email=email,
                source=source,
                utm_source=enrollment.utm_source,
                utm_campaign=enrollment.utm_campaign,
                utm_medium=enrollment.utm_medium,
            ))
        except Exception as e:
            logger.error(f"Failed to capture lead in CRM: {e}")

        # Send access email
        email_result = await _send_lesson_1_access_email(email, name)

        return {
            "success": True,
            "message": "Welcome! Check your email for Lesson 1 access.",
            "is_returning": False,
            "email_sent": email_result.get("success", False),
        }

    except Exception as e:
        logger.error(f"Error enrolling in Trustee 101: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process enrollment. Please try again.")


@router.get("/trustee-101/lesson/{lesson_num}/access")
async def get_lesson_access(lesson_num: int, email: str):
    """Check if user has access to a specific lesson.

    Lessons 1-3: Always free
    Lessons 4-9: Requires enrollment (email captured) or active TrustOffice subscription
    """
    email = email.strip().lower()

    if lesson_num < 1 or lesson_num > 9:
        raise HTTPException(status_code=404, detail=f"Lesson {lesson_num} not found. Valid range: 1-9.")

    lesson_info = next((m for m in CURRICULUM if m["lesson"] == lesson_num), None)
    if not lesson_info:
        raise HTTPException(status_code=404, detail=f"Lesson {lesson_num} not found.")

    if lesson_num <= 3:
        return {
            "has_access": True,
            "lesson": lesson_num,
            "title": lesson_info["title"],
            "type": "free",
        }

    # Lessons 4-9: check if enrolled or subscribed
    lead = await db.course_leads.find_one({"email": email})
    if lead:
        return {
            "has_access": True,
            "lesson": lesson_num,
            "title": lesson_info["title"],
            "type": "enrolled",
        }

    # Check if subscriber
    user = await db.users.find_one({"email": email})
    if user:
        state = await get_subscription_state(user["user_id"])
        if state.is_active:
            return {
                "has_access": True,
                "lesson": lesson_num,
                "title": lesson_info["title"],
                "type": "subscription",
                "plan_type": state.plan_type,
            }

    return {
        "has_access": False,
        "lesson": lesson_num,
        "title": lesson_info["title"],
        "type": "paid",
        "requires": "enrollment_or_subscription",
    }


# ==================== LANDING PAGE ====================

# Path to the static landing page HTML
_LANDING_PAGE_PATH = Path(__file__).resolve().parent.parent / "static" / "trustee-101.html"


def _get_landing_page_html() -> str:
    """Load the Trustee 101 landing page HTML from the static file."""
    return _LANDING_PAGE_PATH.read_text(encoding="utf-8")


# ==================== EMAIL HELPERS ====================

async def _send_lesson_1_access_email(email: str, name: str) -> Dict:
    """Send Lesson 1 access email via Postmark with video embed and lesson info."""

    embed_url = "https://iframe.mediadelivery.net/embed/609821/a5361b44-4f64-4ff9-954b-8ccd89ffb614"
    pdf_url = "https://api.trustoffice.app/static/trustees-first-7-days-checklist.pdf"
    subscribe_url = "https://app.trustoffice.app/subscription"

    lesson_1_info = next((m for m in CURRICULUM if m["lesson"] == 1), None)

    lesson_list_html = "".join(
        f'<li>{m["title"]}</li>' for m in CURRICULUM
    )

    html_content = _base_template(f"""
        <h2>Your Lesson 1 Access is Ready</h2>
        <p>Hi {name},</p>
        <p>Lesson 1 — <em>What Is a Trust?</em> — is free. The foundational video every trustee needs before day one.</p>

        <h3 style="color:#010079; margin-top:24px;">📺 Lesson 1: What Is a Trust?</h3>
        <div style="margin: 16px 0; text-align: center;">
            <iframe src="{embed_url}"
                style="width:100%; max-width:560px; height:315px; border:none; border-radius:8px;"
                allow="accelerometer; gyroscope; autoplay; encrypted-media; picture-in-picture"
                allowfullscreen>
            </iframe>
        </div>

        <div class="success">
            <strong>📋 Download your free checklist:</strong><br>
            <a href="{pdf_url}" style="color: #010079;">"The Trustee's First 7 Days Checklist" (PDF)</a>
            <p style="margin-top: 10px; font-size: 14px;">This checklist covers exactly what to do in your first week as trustee.</p>
        </div>

        <div class="task-card" style="background:#f9f9f9; border-left:4px solid #D5AD36; padding:15px; margin:15px 0;">
            <h3 style="margin:0 0 10px 0;color:#010079;">🔓 Subscribe — Full 9-Lesson Course Included</h3>
                                            <p style="margin:0 0 10px 0;color:#555;font-size:14px;line-height:1.6;">
                                                Lesson 1 is free. The full course covers <strong>all 9 lessons</strong> — plus downloadable templates, checklists, and the software to automate everything the course teaches.
            </p>
            <p style="margin:0 0 6px 0; font-size:14px;"><strong>What's included:</strong></p>
            <ul style="font-size:14px; margin:0 0 12px 0; padding-left:20px;">
                {lesson_list_html}
            </ul>
            <p style="margin:0;text-align:center;">
                <a href="{subscribe_url}" style="display:inline-block;background:#010079;color:#fff;padding:12px 24px;text-decoration:none;font-weight:bold;border-radius:4px;">Subscribe at $79/mo — Full 9-Module Course Included</a>
            </p>
            <p style="margin:10px 0 0 0;font-size:13px;color:#555;text-align:center;">$79/month is a trust expense — paid from the trust, for the trust.</p>
        </div>

        <p style="font-size: 14px; color: #666;">
            <strong>Why subscribe?</strong> The course teaches you the system. TrustOffice automates it — minutes, accounting, distributions, and beneficiary communication — all in one place.
        </p>

        <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #999;">
            <p>You're receiving this because you enrolled in Trustee 101 at trustoffice.app.
            If you didn't sign up, you can safely ignore this email.</p>
        </div>
    """)

    if not email_service.is_configured:
        logger.warning("Email service not configured — skipping send")
        return {"success": False, "message": "Email service not configured"}

    try:
        result = await email_service.send_email(
            to_email=email,
            subject="Your Module 1 Access is Ready — Trustee 101",
            html_body=html_content,
            to_name=name,
            tag="course",
            metadata={"email_type": "course_module_1_access", "module": "1", "course": "trustee-101"},
        )
        return {"success": True, "message": "Email sent"}
    except Exception as e:
        logger.error(f"Failed to send Module 1 access email: {str(e)}")
        return {"success": False, "message": str(e)}