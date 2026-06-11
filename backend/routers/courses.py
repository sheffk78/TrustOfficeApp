"""
Trustee 101 Course Router
Public enrollment, access control, and progress tracking
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, field_validator
from datetime import datetime, timezone
from typing import Optional, Dict
import uuid
import logging
import time

from database import db
from email_service import email_service
from email_templates import _base_template
from dependencies import get_subscription_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/courses", tags=["courses"])

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

@router.post("/trustee-101/enroll")
async def enroll_in_trustee_101(enrollment: CourseEnrollment, request: Request):
    """Enroll in the free Lesson 1 of Trustee 101 course.
    
    Stores lead, sends access email via Postmark with:
    - Video embed link
    - Checklist PDF download
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
                "is_returning": True
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
            "nuture_email_sent": {"1": False, "2": False, "3": False},
            "trustoffice_trial_started": False,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        await db.course_leads.insert_one(lead)

        # Send access email
        email_result = await _send_lesson_1_access_email(email, name)

        return {
            "success": True,
            "message": "Welcome! Check your email for Lesson 1 access.",
            "is_returning": False,
            "email_sent": email_result.get("success", False)
        }

    except Exception as e:
        logger.error(f"Error enrolling in Trustee 101: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process enrollment. Please try again.")


@router.get("/trustee-101/lesson/{lesson_num}/access")
async def get_lesson_access(lesson_num: int, email: str):
    """Check if user has access to a specific lesson.
    
    Lesson 1: Always public (free lead magnet)
    Lessons 2-9: Requires active TrustOffice subscription
    Lessons 10-12: Requires annual subscription
    """
    email = email.strip().lower()

    # Lesson 1 is always public
    if lesson_num == 1:
        return {
            "has_access": True,
            "lesson_num": lesson_num,
            "lesson_title": _get_lesson_title(lesson_num),
            "type": "free"
        }

    # Paid lessons require an active TrustOffice subscription
    # Look up user by email to get user_id
    user = await db.users.find_one({"email": email})
    if not user:
        return {
            "has_access": False,
            "lesson_num": lesson_num,
            "lesson_title": _get_lesson_title(lesson_num),
            "type": "paid",
            "requires": "active_subscription"
        }

    state = await get_subscription_state(user["user_id"])
    
    if not state.is_active:
        return {
            "has_access": False,
            "lesson_num": lesson_num,
            "lesson_title": _get_lesson_title(lesson_num),
            "type": "paid",
            "requires": "active_subscription",
            "subscription_status": state.status,
            "coupon": "TRUSTEE101"
        }

    # For lessons 10-12, require annual subscription
    if lesson_num >= 10:
        if state.plan_type != "annual":
            return {
                "has_access": False,
                "lesson_num": lesson_num,
                "lesson_title": _get_lesson_title(lesson_num),
                "type": "bonus",
                "requires": "annual_subscription"
            }

    return {
        "has_access": True,
        "lesson_num": lesson_num,
        "lesson_title": _get_lesson_title(lesson_num),
        "type": "paid",
        "plan_type": state.plan_type
    }


# ==================== HELPER FUNCTIONS ====================

async def _send_lesson_1_access_email(email: str, name: str) -> Dict:
    """Send Lesson 1 access email via Postmark with video embed and PDF download."""
    
    embed_url = "https://iframe.mediadelivery.net/embed/609821/b095719e-96c6-4a0a-a845-5f003777ff2f"
    pdf_url = "https://trustoffice.app/assets/trustees-first-7-days-checklist.pdf"
    
    app_url = "https://app.trustoffice.app/subscription?coupon=TRUSTEE101"
    
    html_content = _base_template(f"""
        <h2>Your First Lesson is Ready</h2>
        <p>Hi {name},</p>
        <p>Welcome to <strong>Trustee 101: The Course That Should Have Come With Your Trust Document</strong>.</p>
        <p>Your first lesson - <em>What Fiduciary Actually Means</em> - is ready to watch below.</p>
        
        <div style="margin: 30px 0; text-align: center;">
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
            <h3 style="margin:0 0 10px 0;color:#010079;">📺 Want the full 9-lesson course?</h3>
            <p style="margin:0 0 10px 0;font-size:14px;">Subscribe to TrustOffice and unlock <strong>all 9 lessons</strong> plus downloadable templates, checklists, and the software to automate everything the course teaches.</p>
            <p style="margin:0;text-align:center;">
                <a href="{app_url}" style="display:inline-block;background:#010079;color:#fff;padding:12px 24px;text-decoration:none;font-weight:bold;">Subscribe &amp; Use Code TRUSTEE101</a>
            </p>
            <p style="margin:8px 0 0 0;font-size:12px;color:#666;text-align:center;">Use coupon code <strong>TRUSTEE101</strong> at checkout for a discount on your first month. Cancel anytime.</p>
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
            subject="Your Trustee 101 Lesson 1 is Ready",
            html_body=html_content,
            to_name=name,
            tag="course",
            metadata={"email_type": "course_lesson_access", "lesson": "1", "course": "trustee-101"}
        )
        return {"success": True, "message": "Email sent"}
    except Exception as e:
        logger.error(f"Failed to send Lesson 1 access email: {str(e)}")
        return {"success": False, "message": str(e)}


def _get_lesson_title(lesson_num: int) -> str:
    titles = {
        1: "What Fiduciary Actually Means",
        2: "Recordkeeping That Saves You From Court",
        3: "Meeting Minutes Are Not Optional",
        4: "HEMS Decoded",
        5: "The Commingling Trap",
        6: "Trust Taxes in Plain English",
        7: "Investments and When to Delegate",
        8: "Beneficiary Communication That Prevents Lawsuits",
        9: "Family Trusts and Sibling Dynamics",
        10: "State-Specific Trustee Duties",
        11: "When Things Go Wrong",
        12: "Building Your Trustee System",
    }
    return titles.get(lesson_num, f"Lesson {lesson_num}")