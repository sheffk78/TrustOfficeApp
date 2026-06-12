"""
Trustee 101 Course Router
27-lesson curriculum (9 modules × 3 lessons), public enrollment,
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
        "module": 1,
        "module_name": "The Weight of the Role",
        "lessons": [
            {"lesson": 1, "title": "The Highest Standard in American Law", "duration": "~7 min", "free": True},
            {"lesson": 2, "title": "Should You Accept? What Happens When the Grantor Dies", "duration": "~5 min", "free": True},
            {"lesson": 3, "title": "The Trustee's First Seven Days", "duration": "~5 min", "free": True},
        ],
    },
    {
        "module": 2,
        "module_name": "The Paper Trail",
        "lessons": [
            {"lesson": 4, "title": "Accounting Is a Verb with a Capital A", "duration": "~6 min", "free": False},
            {"lesson": 5, "title": "Three Trustees Who Lost Everything Over Records", "duration": "~6 min", "free": False},
            {"lesson": 6, "title": "The 4-Bucket System That Protects You", "duration": "~6 min", "free": False},
        ],
    },
    {
        "module": 3,
        "module_name": "Write It Down",
        "lessons": [
            {"lesson": 7, "title": "The $11,700 Blank Page", "duration": "~5 min", "free": False},
            {"lesson": 8, "title": "Five Decisions That Landed Trustees in Court", "duration": "~6 min", "free": False},
            {"lesson": 9, "title": "The 5-Minute Minute and Court-Ready Resolutions", "duration": "~6 min", "free": False},
        ],
    },
    {
        "module": 4,
        "module_name": "Who Gets What",
        "lessons": [
            {"lesson": 10, "title": "HEMS — The Four Words That Govern Every Dollar", "duration": "~6 min", "free": False},
            {"lesson": 11, "title": "Five HEMS Mistakes That Ended in Lawsuits", "duration": "~6 min", "free": False},
            {"lesson": 12, "title": "The 4-Question Test for Every Distribution", "duration": "~5 min", "free": False},
        ],
    },
    {
        "module": 5,
        "module_name": "The Commingling Trap",
        "lessons": [
            {"lesson": 13, "title": "Six Rules That Keep Trust Money Clean", "duration": "~5 min", "free": False},
            {"lesson": 14, "title": "Six Real Commingling Cases", "duration": "~6 min", "free": False},
            {"lesson": 15, "title": "The Simple Separation Rule", "duration": "~5 min", "free": False},
        ],
    },
    {
        "module": 6,
        "module_name": "Taxes and Deadlines",
        "lessons": [
            {"lesson": 16, "title": "How Trust Taxes Work (And Why They're Different)", "duration": "~6 min", "free": False},
            {"lesson": 17, "title": "Five Tax Mistakes That Cost Trustees Real Money", "duration": "~5 min", "free": False},
            {"lesson": 18, "title": "Your Tax Calendar and the 65-Day Rule", "duration": "~6 min", "free": False},
        ],
    },
    {
        "module": 7,
        "module_name": "Invest and Delegate",
        "lessons": [
            {"lesson": 19, "title": "The Prudent Investor Rule", "duration": "~6 min", "free": False},
            {"lesson": 20, "title": "Four Investment Mistakes That Got Trustees Sued", "duration": "~5 min", "free": False},
            {"lesson": 21, "title": "Your Investment Process and Getting Paid Fairly", "duration": "~6 min", "free": False},
        ],
    },
    {
        "module": 8,
        "module_name": "Communication That Prevents Lawsuits",
        "lessons": [
            {"lesson": 22, "title": "The Communication Duty — What the Law Requires", "duration": "~6 min", "free": False},
            {"lesson": 23, "title": "Five Communication Failures — and What Each Cost", "duration": "~6 min", "free": False},
            {"lesson": 24, "title": "The 4-Pillar Communication System", "duration": "~7 min", "free": False},
        ],
    },
    {
        "module": 9,
        "module_name": "When Family and Trust Collide",
        "lessons": [
            {"lesson": 25, "title": "Two Hats, One Head", "duration": "~5 min", "free": False},
            {"lesson": 26, "title": "Four Family Trust Traps That Destroy Relationships", "duration": "~6 min", "free": False},
            {"lesson": 27, "title": "The 5 Rules for Family Trustees", "duration": "~6 min", "free": False},
        ],
    },
]


def _get_lesson_title(lesson_num: int) -> str:
    """Return the title for a lesson number (1–27)."""
    titles = {
        1: "The Highest Standard in American Law",
        2: "Should You Accept? What Happens When the Grantor Dies",
        3: "The Trustee's First Seven Days",
        4: "Accounting Is a Verb with a Capital A",
        5: "Three Trustees Who Lost Everything Over Records",
        6: "The 4-Bucket System That Protects You",
        7: "The $11,700 Blank Page",
        8: "Five Decisions That Landed Trustees in Court",
        9: "The 5-Minute Minute and Court-Ready Resolutions",
        10: "HEMS — The Four Words That Govern Every Dollar",
        11: "Five HEMS Mistakes That Ended in Lawsuits",
        12: "The 4-Question Test for Every Distribution",
        13: "Six Rules That Keep Trust Money Clean",
        14: "Six Real Commingling Cases",
        15: "The Simple Separation Rule",
        16: "How Trust Taxes Work",
        17: "Five Tax Mistakes",
        18: "Your Tax Calendar and the 65-Day Rule",
        19: "The Prudent Investor Rule",
        20: "Four Investment Mistakes",
        21: "Your Investment Process",
        22: "The Communication Duty",
        23: "Five Communication Failures",
        24: "The 4-Pillar Communication System",
        25: "Two Hats, One Head",
        26: "Four Family Trust Traps",
        27: "The 5 Rules for Family Trustees",
    }
    return titles.get(lesson_num, f"Lesson {lesson_num}")


def _is_free_lesson(lesson_num: int) -> bool:
    """Module 1 (Lessons 1–3) is free. Lessons 4–27 require subscription."""
    return 1 <= lesson_num <= 3


# ==================== SCHEMAS ====================

class CourseEnrollment(BaseModel):
    name: str
    email: EmailStr
    source: Optional[str] = "trustee-101-landing-page"

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
    """Return the full 27-lesson curriculum structure as JSON."""
    return JSONResponse(content={
        "course": "Trustee 101",
        "tagline": "The Course That Should Have Come With Your Trust Document",
        "total_modules": 9,
        "total_lessons": 27,
        "free_lessons": list(range(1, 4)),
        "modules": CURRICULUM,
    })


@router.post("/trustee-101/enroll")
async def enroll_in_trustee_101(enrollment: CourseEnrollment, request: Request):
    """Enroll in free Module 1 of Trustee 101 course.

    Stores lead, sends access email via Postmark with:
    - Video embed for Lesson 1
    - Module 1 lesson list
    - Subscription CTA for full 27-lesson course
    """
    try:
        name = enrollment.name.strip()
        email = enrollment.email.strip().lower()
        source = enrollment.source or "trustee-101-landing-page"

        # Check if already enrolled
        existing = await db.course_leads.find_one({"email": email})
        if existing:
            # Already enrolled — re-send access email
            await _send_module_1_access_email(email, name)
            return {
                "success": True,
                "message": "Access re-sent. Check your email for Module 1.",
                "is_returning": True,
            }

        # Create lead record
        lead = {
            "email": email,
            "name": name,
            "source": source,
            "module_1_access_granted": True,
            "module_1_watched": False,
            "course_purchased": False,
            "stripe_session_id": None,
            "stripe_customer_id": None,
            "nurture_email_sent": {"1": False, "2": False, "3": False},
            "trustoffice_trial_started": False,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        await db.course_leads.insert_one(lead)

        # Send access email
        email_result = await _send_module_1_access_email(email, name)

        return {
            "success": True,
            "message": "Welcome! Check your email for Module 1 access.",
            "is_returning": False,
            "email_sent": email_result.get("success", False),
        }

    except Exception as e:
        logger.error(f"Error enrolling in Trustee 101: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process enrollment. Please try again.")


@router.get("/trustee-101/lesson/{lesson_num}/access")
async def get_lesson_access(lesson_num: int, email: str):
    """Check if user has access to a specific lesson.

    Lessons 1–3 (Module 1): Always free
    Lessons 4–27 (Modules 2–9): Requires active TrustOffice subscription
    """
    email = email.strip().lower()

    if lesson_num < 1 or lesson_num > 27:
        raise HTTPException(status_code=404, detail=f"Lesson {lesson_num} not found. Valid range: 1–27.")

    # Module 1 (Lessons 1–3) is always free
    if _is_free_lesson(lesson_num):
        return {
            "has_access": True,
            "lesson_num": lesson_num,
            "lesson_title": _get_lesson_title(lesson_num),
            "module": (lesson_num - 1) // 3 + 1,
            "type": "free",
        }

    # Paid lessons require an active TrustOffice subscription
    user = await db.users.find_one({"email": email})
    if not user:
        return {
            "has_access": False,
            "lesson_num": lesson_num,
            "lesson_title": _get_lesson_title(lesson_num),
            "module": (lesson_num - 1) // 3 + 1,
            "type": "paid",
            "requires": "active_subscription",
        }

    state = await get_subscription_state(user["user_id"])

    if not state.is_active:
        return {
            "has_access": False,
            "lesson_num": lesson_num,
            "lesson_title": _get_lesson_title(lesson_num),
            "module": (lesson_num - 1) // 3 + 1,
            "type": "paid",
            "requires": "active_subscription",
            "subscription_status": state.status,
        }

    return {
        "has_access": True,
        "lesson_num": lesson_num,
        "lesson_title": _get_lesson_title(lesson_num),
        "module": (lesson_num - 1) // 3 + 1,
        "type": "paid",
        "plan_type": state.plan_type,
    }


# ==================== LANDING PAGE ====================

# Path to the static landing page HTML
_LANDING_PAGE_PATH = Path(__file__).resolve().parent.parent / "static" / "trustee-101.html"


def _get_landing_page_html() -> str:
    """Load the Trustee 101 landing page HTML from the static file."""
    return _LANDING_PAGE_PATH.read_text(encoding="utf-8")


# ==================== EMAIL HELPERS ====================

async def _send_module_1_access_email(email: str, name: str) -> Dict:
    """Send Module 1 access email via Postmark with video embed and lesson list."""

    embed_url = "https://iframe.mediadelivery.net/embed/609821/b095719e-96c6-4a0a-a845-5f003777ff2f"
    pdf_url = "https://api.trustoffice.app/static/trustees-first-7-days-checklist.pdf"
    subscribe_url = "https://app.trustoffice.app/subscription"

    module_1_lessons = [
        ("Lesson 1", "The Highest Standard in American Law"),
        ("Lesson 2", "Should You Accept? What Happens When the Grantor Dies"),
        ("Lesson 3", "The Trustee's First Seven Days"),
    ]

    lesson_list_html = "".join(
        f'<li><strong>{num}:</strong> {title}</li>'
        for num, title in module_1_lessons
    )

    module_list_html = "".join(
        f'<li>{m["module_name"]}</li>' for m in CURRICULUM
    )

    html_content = _base_template(f"""
        <h2>Your Module 1 Access is Ready</h2>
        <p>Hi {name},</p>
        <p>Welcome to <strong>Trustee 101: The Course That Should Have Come With Your Trust Document</strong>.</p>
        <p>Module 1 — <em>The Weight of the Role</em> — is free. Three lessons that cover what every trustee needs to understand before day one.</p>

        <h3 style="color:#010079; margin-top:24px;">📺 Lesson 1: The Highest Standard in American Law</h3>
        <div style="margin: 16px 0; text-align: center;">
            <iframe src="{embed_url}"
                style="width:100%; max-width:560px; height:315px; border:none; border-radius:8px;"
                allow="accelerometer; gyroscope; autoplay; encrypted-media; picture-in-picture"
                allowfullscreen>
            </iframe>
        </div>

        <h3 style="color:#010079;">Module 1: The Weight of the Role</h3>
        <ul>
            {lesson_list_html}
        </ul>

        <div class="success">
            <strong>📋 Download your free checklist:</strong><br>
            <a href="{pdf_url}" style="color: #010079;">"The Trustee's First 7 Days Checklist" (PDF)</a>
            <p style="margin-top: 10px; font-size: 14px;">This checklist covers exactly what to do in your first week as trustee.</p>
        </div>

        <div class="task-card" style="background:#f9f9f9; border-left:4px solid #D5AD36; padding:15px; margin:15px 0;">
            <h3 style="margin:0 0 10px 0;color:#010079;">🔓 Subscribe — Full 27-Lesson Course Included</h3>
            <p style="margin:0 0 10px 0;font-size:14px;">
                Module 1 is free. The full course covers <strong>all 27 lessons across 9 modules</strong> — plus downloadable templates, checklists, and the software to automate everything the course teaches.
            </p>
            <p style="margin:0 0 6px 0; font-size:14px;"><strong>What's included:</strong></p>
            <ul style="font-size:14px; margin:0 0 12px 0; padding-left:20px;">
                {module_list_html}
            </ul>
            <p style="margin:0;text-align:center;">
                <a href="{subscribe_url}" style="display:inline-block;background:#010079;color:#fff;padding:12px 24px;text-decoration:none;font-weight:bold;border-radius:4px;">Subscribe at $79/mo — Full 27-Lesson Course Included</a>
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