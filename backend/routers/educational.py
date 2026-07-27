"""
Educational resources router — curated learning content for trust administration.

Phase 4 (Enhanced Features) of the TrustOffice plan.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from typing import Optional

from dependencies import get_current_user
from services import educational_service
from routers.courses import CURRICULUM

router = APIRouter(tags=["educational"])


# ==================== HELPERS ====================

async def _require_owned_trust(trust_id: str, user: dict) -> dict:
    trust = await educational_service.get_owned_trust(trust_id, user["user_id"])
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found.")
    return trust


# ==================== REQUEST BODIES ====================

class EnrollBody(BaseModel):
    name: str
    email: EmailStr
    source: Optional[str] = "trustoffice-app"


# ==================== ENDPOINTS ====================

@router.get("/educational/{trust_id}/resources")
async def get_resources(
    trust_id: str,
    user: dict = Depends(get_current_user),
):
    """Get all educational resources for a trust (courses, articles, guides, recommended)."""
    await _require_owned_trust(trust_id, user)
    try:
        return await educational_service.get_educational_resources(
            trust_id, user["user_id"]
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/educational/{trust_id}/recommended")
async def get_recommended(
    trust_id: str,
    user: dict = Depends(get_current_user),
):
    """Get personalized recommendations based on trust health score."""
    await _require_owned_trust(trust_id, user)
    return await educational_service.get_recommended_resources(
        trust_id, user["user_id"]
    )


@router.get("/educational/trustee-101/curriculum")
async def get_curriculum(user: dict = Depends(get_current_user)):
    """Return the Trustee 101 course curriculum."""
    return {
        "title": "Trustee 101",
        "total_lessons": len(CURRICULUM),
        "free_lessons": [l["lesson"] for l in CURRICULUM if l.get("free")],
        "lessons": CURRICULUM,
    }


@router.post("/educational/trustee-101/enroll")
async def enroll(body: EnrollBody, user: dict = Depends(get_current_user)):
    """Enroll in Trustee 101. Creates the lead record directly."""
    from datetime import datetime, timezone
    from database import db

    email = body.email.strip().lower()
    name = body.name.strip()

    # Check if already enrolled
    existing = await db.course_leads.find_one({"email": email})
    if existing:
        return {
            "success": True,
            "message": "Already enrolled. Access re-sent.",
            "is_returning": True,
        }

    lead = {
        "email": email,
        "name": name,
        "source": body.source or "trustoffice-app",
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

    return {
        "success": True,
        "message": "Enrolled successfully. Check your email for Lesson 1 access.",
        "is_returning": False,
    }
