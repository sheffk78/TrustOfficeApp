"""
Fiduciary Compliance Assessment Router
Public endpoint for the fiduciary self-assessment quiz on trustoffice.app/fiduciary-assessment.
Captures leads, stores assessment results, and triggers the nurture sequence.
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, field_validator
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import uuid
import json
import logging

from database import db
from email_service import email_service
from email_templates import _base_template

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assessments", tags=["assessments"])


# ==================== SCHEMAS ====================


class FiduciaryComplianceSubmission(BaseModel):
    """Schema for fiduciary compliance assessment submission."""
    name: str
    email: EmailStr
    score: int
    category: str  # "strong", "needs-work", "at-risk"
    answers: str  # JSON string of 10 answers
    source: Optional[str] = "fiduciary-assessment"
    utm_source: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_medium: Optional[str] = None
    referrer: Optional[str] = None

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

    @field_validator('score')
    @classmethod
    def validate_score(cls, v):
        if v < 0 or v > 10:
            raise ValueError('Score must be between 0 and 10')
        return v

    @field_validator('category')
    @classmethod
    def validate_category(cls, v):
        valid = {"strong", "needs-work", "at-risk"}
        if v not in valid:
            raise ValueError(f'Category must be one of: {", ".join(valid)}')
        return v


# ==================== PUBLIC ENDPOINT ====================


@router.post("/fiduciary-compliance/submit", include_in_schema=False)
async def submit_fiduciary_assessment(submission: FiduciaryComplianceSubmission):
    """
    Submit fiduciary compliance assessment results.
    Public endpoint — no auth required.

    Stores the assessment, creates/updates a lead record, and sends
    the nurture sequence (Email 1 immediately via Postmark).
    """
    try:
        email = submission.email.strip().lower()
        name = submission.name.strip()
        source = submission.source or "fiduciary-assessment"

        # Parse answers JSON
        try:
            answers_list = json.loads(submission.answers)
            if not isinstance(answers_list, list) or len(answers_list) != 10:
                answers_list = [None] * 10
        except (json.JSONDecodeError, TypeError):
            answers_list = [None] * 10

        # Calculate yes count for verification
        yes_count = sum(1 for a in answers_list if a == "yes")

        now = datetime.now(timezone.utc)

        # Check if lead already exists
        existing_lead = await db.leads.find_one({"email": email})

        if existing_lead:
            lead_id = existing_lead["lead_id"]
            # Update existing lead
            await db.leads.update_one(
                {"email": email},
                {"$set": {
                    "name": name,
                    "source": source,
                    "utm_source": submission.utm_source,
                    "utm_campaign": submission.utm_campaign,
                    "utm_medium": submission.utm_medium,
                    "referrer": submission.referrer,
                    "updated_at": now.isoformat(),
                }}
            )
            is_returning = True
        else:
            # Create new lead
            lead_id = f"lead_{uuid.uuid4().hex[:12]}"
            lead_doc = {
                "lead_id": lead_id,
                "email": email,
                "name": name,
                "source": source,
                "lead_type": "fiduciary_assessment",
                "utm_source": submission.utm_source,
                "utm_campaign": submission.utm_campaign,
                "utm_medium": submission.utm_medium,
                "referrer": submission.referrer,
                "stage": "new",
                "manual_stage_override": False,
                "lessons_watched": 0,
                "subscription_status": None,
                "last_login": None,
                "notes": "",
                "next_action": "Monitor — no action needed",
                "score": 50,
                "nurture_step_sent": 1,  # Email 1 sent immediately below
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
            await db.leads.insert_one(lead_doc)
            is_returning = False

        # Store assessment result
        assessment_id = f"fa_{uuid.uuid4().hex[:12]}"
        assessment_doc = {
            "assessment_id": assessment_id,
            "lead_id": lead_id,
            "email": email,
            "name": name,
            "score": submission.score,
            "yes_count": yes_count,
            "category": submission.category,
            "answers": answers_list,
            "source": source,
            "utm_source": submission.utm_source,
            "utm_campaign": submission.utm_campaign,
            "utm_medium": submission.utm_medium,
            "referrer": submission.referrer,
            "created_at": now.isoformat(),
        }
        await db.fiduciary_assessments.insert_one(assessment_doc)

        # Send nurture sequence (Email 1 immediately)
        email_result = await email_service.send_nurture_sequence(
            to_email=email,
            name=name,
            download_url=f"{email_service.app_url}/fiduciary-assessment",
        )

        logger.info(
            f"Fiduciary assessment submitted: {assessment_id} — "
            f"{email} score={submission.score}/10 ({submission.category})"
        )

        return {
            "success": True,
            "assessment_id": assessment_id,
            "lead_id": lead_id,
            "is_returning": is_returning,
            "score": submission.score,
            "category": submission.category,
            "email_sent": email_result.get("status") == "sent",
        }

    except Exception as e:
        logger.error(f"Error processing fiduciary assessment: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to process assessment. Please try again."
        )
