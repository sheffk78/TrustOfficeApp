"""
AI Router - FastAPI endpoints for AI-powered features
Provides minutes drafting and governance suggestions using Claude
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
import logging

from dependencies import get_current_user, require_write_access
from database import db
from ai_service import (
    MinutesDraftRequest,
    MinutesDraftResponse,
    GovernanceSuggestionsRequest,
    GovernanceSuggestionsResponse,
    GovernanceCriterion,
    RecentActivity,
    draft_minutes_from_structured_input,
    generate_governance_suggestions
)

router = APIRouter(prefix="/ai", tags=["ai"])
logger = logging.getLogger(__name__)


@router.post("/minutes-draft", response_model=MinutesDraftResponse)
async def create_minutes_draft(
    request: MinutesDraftRequest,
    user: dict = Depends(require_write_access)
):
    """
    Generate an AI-drafted meeting minutes document.
    
    Uses Claude Sonnet to create professional minutes with
    WHEREAS/RESOLVED structure based on the provided input.
    
    The draft is returned for review and editing - it should not
    be used as-is without trustee review.
    """
    user_id = user["user_id"]
    
    # If trust_name is not provided, try to get it from user's selected trust
    if not request.trust_name:
        # Get most recent trust
        trust = await db.trusts.find_one(
            {"user_id": user_id},
            {"_id": 0, "name": 1, "jurisdiction": 1}
        )
        if trust:
            request.trust_name = trust.get("name", "Trust")
            if not request.jurisdiction:
                request.jurisdiction = trust.get("jurisdiction")
    
    logger.info(f"Generating minutes draft for user {user_id}, trust: {request.trust_name}")
    
    try:
        response = await draft_minutes_from_structured_input(request)
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating minutes draft: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate minutes draft")


class GovernanceSuggestionsRequestSimple(MinutesDraftRequest):
    """Simplified request - can optionally provide trust_id to auto-populate"""
    pass


@router.post("/governance-suggestions", response_model=GovernanceSuggestionsResponse)
async def get_governance_suggestions(
    trust_id: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """
    Generate AI-powered governance improvement suggestions.
    
    Uses Claude Haiku to analyze the current governance health
    score and provide 2-4 actionable recommendations.
    
    If trust_id is not provided, uses the user's most recent trust.
    """
    user_id = user["user_id"]
    
    # Get trust
    if trust_id:
        trust = await db.trusts.find_one(
            {"trust_id": trust_id, "user_id": user_id},
            {"_id": 0}
        )
        if not trust:
            raise HTTPException(status_code=404, detail="Trust not found")
    else:
        trust = await db.trusts.find_one(
            {"user_id": user_id},
            {"_id": 0},
            sort=[("created_at", -1)]
        )
        if not trust:
            raise HTTPException(status_code=404, detail="No trust found")
    
    trust_id = trust["trust_id"]
    trust_name = trust.get("name", "Trust")
    
    logger.info(f"Generating governance suggestions for user {user_id}, trust: {trust_name}")
    
    # Calculate governance health score (similar to governance router)
    from datetime import datetime, timezone, timedelta
    from routers.governance import calculate_health_score
    
    health_data = await calculate_health_score(trust_id, user_id)
    health_score = health_data["health_score"]
    
    # Build criteria list
    criteria = []
    for c in health_data.get("criteria", []):
        criteria.append(GovernanceCriterion(
            name=c.get("name", ""),
            description=c.get("description", ""),
            points=c.get("points", 0),
            max_points=c.get("max_points", 0),
            achieved=c.get("achieved", False)
        ))
    
    # Get recent activity
    recent_activity = []
    now = datetime.now(timezone.utc)
    thirty_days_ago = (now - timedelta(days=30)).isoformat()
    
    # Get recent minutes
    minutes = await db.minutes_records.find(
        {"trust_id": trust_id, "user_id": user_id, "created_at": {"$gte": thirty_days_ago}},
        {"_id": 0, "minutes_type": 1, "meeting_date": 1, "created_at": 1}
    ).sort("created_at", -1).limit(3).to_list(3)
    
    for m in minutes:
        recent_activity.append(RecentActivity(
            type="minutes",
            date=m.get("meeting_date", m.get("created_at", ""))[:10],
            label=f"{m.get('minutes_type', 'Meeting').title()} minutes recorded"
        ))
    
    # Get recent distributions
    distributions = await db.distribution_records.find(
        {"trust_id": trust_id, "user_id": user_id, "created_at": {"$gte": thirty_days_ago}},
        {"_id": 0, "beneficiary_name": 1, "amount": 1, "date": 1, "approved_at": 1}
    ).sort("created_at", -1).limit(3).to_list(3)
    
    for d in distributions:
        status = "approved" if d.get("approved_at") else "pending"
        recent_activity.append(RecentActivity(
            type="distribution",
            date=d.get("date", "")[:10],
            label=f"${d.get('amount', 0):,.0f} to {d.get('beneficiary_name', 'beneficiary')} ({status})"
        ))
    
    # Get recent tasks
    tasks = await db.governance_tasks.find(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0, "task_type": 1, "due_date": 1, "completed_at": 1, "description": 1}
    ).sort("due_date", 1).limit(3).to_list(3)
    
    for t in tasks:
        status = "completed" if t.get("completed_at") else "pending"
        recent_activity.append(RecentActivity(
            type="task",
            date=t.get("due_date", "")[:10],
            label=f"{t.get('task_type', 'Task').replace('_', ' ').title()} ({status})"
        ))
    
    # Sort by date and limit
    recent_activity.sort(key=lambda x: x.date, reverse=True)
    recent_activity = recent_activity[:5]
    
    # Build request
    suggestions_request = GovernanceSuggestionsRequest(
        health_score=health_score,
        criteria=criteria,
        recent_activity=recent_activity,
        trust_name=trust_name
    )
    
    try:
        response = await generate_governance_suggestions(suggestions_request)
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating governance suggestions: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate suggestions")


@router.get("/status")
async def get_ai_status(user: dict = Depends(get_current_user)):
    """
    Check if AI services are configured and available.
    """
    import os
    
    claude_key = os.environ.get('CLAUDE_API_KEY') or os.environ.get('EMERGENT_LLM_KEY')
    
    return {
        "ai_enabled": bool(claude_key),
        "features": {
            "minutes_drafting": bool(claude_key),
            "governance_suggestions": bool(claude_key)
        },
        "models": {
            "drafting": "claude-sonnet-4-5" if claude_key else None,
            "suggestions": "claude-3-5-haiku" if claude_key else None
        }
    }
