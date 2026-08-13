"""
Feedback router — handles user product feedback submissions.

Stores feedback in a user_feedback collection with timestamp, user_id,
and trust_id for context. Used by the dashboard feedback prompt modal
that triggers after a user has created their 3rd minutes entry.
"""
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from typing import Optional

from database import db
from dependencies import get_current_user, require_write_access

router = APIRouter(tags=["feedback"])


class FeedbackCreate(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)


@router.post("/feedback")
async def submit_feedback(
    payload: FeedbackCreate,
    user: dict = Depends(require_write_access),
):
    """Submit product feedback from a user."""
    user_id = user["user_id"]
    now = datetime.now(timezone.utc)

    doc = {
        "feedback_id": f"fb_{now.strftime('%Y%m%d%H%M%S')}_{user_id[:8]}",
        "user_id": user_id,
        "message": payload.message.strip(),
        "created_at": now.isoformat(),
        "source": "dashboard_feedback_prompt",
    }

    await db.user_feedback.insert_one(doc)

    return {
        "message": "Feedback received. Thank you!",
        "feedback_id": doc["feedback_id"],
    }


@router.get("/feedback")
async def list_feedback(
    user: dict = Depends(get_current_user),
):
    """List the current user's feedback submissions."""
    user_id = user["user_id"]
    results = await db.user_feedback.find(
        {"user_id": user_id},
        {"_id": 0}
    ).to_list(100)
    return {"feedback": results}