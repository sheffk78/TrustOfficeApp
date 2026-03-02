"""
AI Router - FastAPI endpoints for AI-powered features
Provides minutes drafting and governance suggestions using Claude

Note: Claude API key must be provided via CLAUDE_API_KEY or EMERGENT_LLM_KEY environment variable.

=== MANUAL TESTING INSTRUCTIONS ===
To test minutes drafting:
  curl -X POST {BASE_URL}/api/ai/minutes-draft \
    -H "Authorization: Bearer {TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"minutes_type":"quarterly","meeting_date":"2026-01-15","participants":["John Trustee"],"decisions_outline":["Reviewed assets"],"trust_name":"Test Trust"}'
  Then verify the draft appears in the Minutes UI modal.

To test governance suggestions:
  Load the Dashboard with some existing minutes/tasks and confirm suggestions populate
  the AI Recommendations card. Or call directly:
  curl -X POST {BASE_URL}/api/ai/governance-suggestions \
    -H "Authorization: Bearer {TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{}'
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import logging
import asyncio

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
from claude_client import ping_claude, CLAUDE_API_KEY, CLAUDE_SONNET, CLAUDE_HAIKU

router = APIRouter(prefix="/ai", tags=["ai"])
logger = logging.getLogger(__name__)

# ==================== RATE LIMITING ====================
# Simple in-memory rate limiter per user
# Format: { user_id: { endpoint: [(timestamp, ...)] } }
_rate_limit_store: dict = defaultdict(lambda: defaultdict(list))
_rate_limit_lock = asyncio.Lock()

# Rate limits per hour
RATE_LIMITS = {
    "minutes-draft": 10,      # Max 10 AI minutes drafts per user per hour
    "governance-suggestions": 20  # Max 20 AI governance suggestions per user per hour
}


async def check_rate_limit(user_id: str, endpoint: str) -> bool:
    """
    Check if user has exceeded rate limit for the given endpoint.
    Returns True if within limit, raises HTTPException if exceeded.
    """
    limit = RATE_LIMITS.get(endpoint, 20)
    now = datetime.now(timezone.utc)
    one_hour_ago = now - timedelta(hours=1)
    
    async with _rate_limit_lock:
        # Clean up old entries
        _rate_limit_store[user_id][endpoint] = [
            ts for ts in _rate_limit_store[user_id][endpoint]
            if ts > one_hour_ago
        ]
        
        # Check if within limit
        if len(_rate_limit_store[user_id][endpoint]) >= limit:
            logger.warning(f"Rate limit exceeded for user {user_id} on {endpoint}")
            raise HTTPException(
                status_code=429,
                detail=f"AI assistant rate limit reached. Please try again later. (Max {limit} requests per hour)"
            )
        
        # Record this request
        _rate_limit_store[user_id][endpoint].append(now)
    
    return True


def log_ai_call(user_id: str, trust_id: str, endpoint: str, model: str, input_length: int):
    """
    Log a concise entry for each AI call.
    Does NOT log raw content to protect sensitive data.
    """
    logger.info(
        f"AI_CALL | user={user_id} | trust={trust_id} | endpoint={endpoint} | "
        f"model={model} | input_chars={input_length}"
    )


# ==================== ENDPOINTS ====================

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
    
    Rate limit: 10 requests per user per hour.
    """
    user_id = user["user_id"]
    
    # Check rate limit
    await check_rate_limit(user_id, "minutes-draft")
    
    # Get trust info if not provided
    trust_id = "unknown"
    if not request.trust_name:
        trust = await db.trusts.find_one(
            {"user_id": user_id},
            {"_id": 0, "name": 1, "jurisdiction": 1, "trust_id": 1}
        )
        if trust:
            request.trust_name = trust.get("name", "Trust")
            trust_id = trust.get("trust_id", "unknown")
            if not request.jurisdiction:
                request.jurisdiction = trust.get("jurisdiction")
    
    # Calculate approximate input length (for logging, not content)
    input_length = len(request.minutes_type) + len(request.meeting_date) + \
                   sum(len(p) for p in request.participants) + \
                   sum(len(d) for d in request.decisions_outline) + \
                   len(request.trust_name or "") + len(request.additional_context or "")
    
    # Log the AI call (no sensitive content)
    log_ai_call(user_id, trust_id, "minutes-draft", CLAUDE_SONNET, input_length)
    
    try:
        response = await draft_minutes_from_structured_input(request)
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating minutes draft for user {user_id}: {type(e).__name__}")
        raise HTTPException(
            status_code=500,
            detail="AI assistant is currently unavailable. Please try again later."
        )


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
    
    Rate limit: 20 requests per user per hour.
    """
    user_id = user["user_id"]
    
    # Check rate limit
    await check_rate_limit(user_id, "governance-suggestions")
    
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
    
    # Calculate governance health score
    from routers.governance import calculate_health_score
    
    health_data = await calculate_health_score(trust_id, user_id)
    health_score = health_data["total_score"]
    
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
    
    # Calculate approximate input length for logging
    input_length = len(trust_name) + len(str(health_score)) + \
                   sum(len(c.name) + len(c.description) for c in criteria) + \
                   sum(len(a.label) for a in recent_activity)
    
    # Log the AI call (no sensitive content)
    log_ai_call(user_id, trust_id, "governance-suggestions", CLAUDE_HAIKU, input_length)
    
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
        logger.error(f"Error generating governance suggestions for user {user_id}: {type(e).__name__}")
        raise HTTPException(
            status_code=500,
            detail="AI assistant is currently unavailable. Please try again later."
        )


@router.get("/status")
async def get_ai_status(user: dict = Depends(get_current_user)):
    """
    Check if AI services are configured and available.
    """
    ai_enabled = bool(CLAUDE_API_KEY)
    
    return {
        "ai_enabled": ai_enabled,
        "features": {
            "minutes_drafting": ai_enabled,
            "governance_suggestions": ai_enabled
        },
        "models": {
            "drafting": CLAUDE_SONNET if ai_enabled else None,
            "suggestions": CLAUDE_HAIKU if ai_enabled else None
        },
        "rate_limits": RATE_LIMITS if ai_enabled else None
    }


@router.get("/health")
async def ai_health_check(user: dict = Depends(get_current_user)):
    """
    Health check endpoint for AI service.
    
    Performs a simple ping to Claude Haiku to verify the service is operational.
    Returns { "ok": true } on success, { "ok": false, "error": "..." } on failure.
    
    This endpoint is for internal testing only - no Claude error details are exposed.
    """
    if not CLAUDE_API_KEY:
        logger.error("AI health check failed: API key not configured")
        return {"ok": False, "error": "AI service not configured"}
    
    try:
        is_healthy = await ping_claude()
        if is_healthy:
            return {"ok": True}
        else:
            logger.warning("AI health check: ping succeeded but response unexpected")
            return {"ok": False, "error": "AI service responded unexpectedly"}
    except Exception as e:
        logger.error(f"AI health check failed: {type(e).__name__}")
        return {"ok": False, "error": "AI service unavailable"}
