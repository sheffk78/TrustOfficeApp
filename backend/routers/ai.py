"""
AI Router - FastAPI endpoints for AI-powered features
Provides minutes drafting and governance suggestions using Claude

Note: Claude API key must be provided via CLAUDE_API_KEY or EMERGENT_LLM_KEY environment variable.

=== COST PROTECTION LAYERS (applied in order) ===
1. Input Size Validation: Max 10,000 chars for minutes-draft (400 if exceeded)
2. Hourly Rate Limits (in-memory): 10/hr minutes-draft, 20/hr governance-suggestions (429)
3. Daily Caps (MongoDB ai_usage_tracking): 30/day minutes-draft, 50/day governance-suggestions (429)
4. Monthly Budget Kill-Switch: $0.03/Sonnet, $0.002/Haiku vs AI_MONTHLY_BUDGET_CENTS (503)
5. Caching: governance-suggestions cached 1hr per user+trust in ai_suggestion_cache

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

To test admin usage endpoint (admin only - jeff@socialize.video):
  curl -X GET {BASE_URL}/api/ai/usage \
    -H "Authorization: Bearer {ADMIN_TOKEN}"
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import logging
import asyncio
import os

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
from ai_client import ai_health_check as ai_backend_status, AI_PRIMARY_MODEL, AI_FALLBACK_MODEL, AI_ENABLED
from claude_client import ping_claude

router = APIRouter(prefix="/ai", tags=["ai"])
logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================

# Cost estimates per call (in cents) — for budget tracking only
# Ollama is essentially free; Claude is the fallback cost
COST_PER_CALL_CENTS = {
    "minutes-draft": 0.5,        # essentially free via Ollama
    "governance-suggestions": 0.1  # ditto
}

# Daily caps per user (stored in MongoDB)
DAILY_CAPS = {
    "minutes-draft": 30,
    "governance-suggestions": 50
}

# Input size limit for minutes-draft (total chars across all fields)
MAX_INPUT_CHARS_MINUTES_DRAFT = 10000

# Monthly budget default (can be overridden by AI_MONTHLY_BUDGET_CENTS env var)
DEFAULT_MONTHLY_BUDGET_CENTS = 5000

# Cache TTL for governance suggestions (1 hour)
CACHE_TTL_SECONDS = 3600

# Admin email for usage endpoint
ADMIN_EMAIL = "jeff@socialize.video"

# ==================== HOURLY RATE LIMITING (EXISTING - DO NOT MODIFY) ====================
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


# ==================== NEW: DAILY CAP LIMITING (MongoDB) ====================

async def check_daily_cap(user_id: str, endpoint: str) -> bool:
    """
    Check if user has exceeded daily cap for the given endpoint.
    Uses MongoDB ai_usage_tracking collection for persistence.
    Returns True if within limit, raises HTTPException (429) if exceeded.
    """
    cap = DAILY_CAPS.get(endpoint, 100)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Find or create today's usage record for this user+endpoint
    usage = await db.ai_usage_tracking.find_one({
        "user_id": user_id,
        "endpoint": endpoint,
        "date": today_start.isoformat()
    })
    
    current_count = usage.get("count", 0) if usage else 0
    
    if current_count >= cap:
        logger.warning(f"Daily cap exceeded for user {user_id} on {endpoint}: {current_count}/{cap}")
        raise HTTPException(
            status_code=429,
            detail=f"Daily AI limit reached. You've used {current_count}/{cap} requests today. Resets at midnight UTC."
        )
    
    return True


async def record_daily_usage(user_id: str, endpoint: str, cost_cents: float):
    """
    Record a usage event in ai_usage_tracking.
    Increments count and adds to estimated_cost for today.
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    await db.ai_usage_tracking.update_one(
        {
            "user_id": user_id,
            "endpoint": endpoint,
            "date": today_start.isoformat()
        },
        {
            "$inc": {"count": 1, "estimated_cost_cents": cost_cents},
            "$set": {"last_request_at": now.isoformat()}
        },
        upsert=True
    )


# ==================== NEW: MONTHLY BUDGET KILL-SWITCH ====================

async def check_monthly_budget() -> bool:
    """
    Check if the global monthly budget has been exceeded.
    Sums estimated_cost_cents from ai_usage_tracking for current month.
    Returns True if within budget, raises HTTPException (503) if exceeded.
    """
    budget_cents = int(os.environ.get("AI_MONTHLY_BUDGET_CENTS", DEFAULT_MONTHLY_BUDGET_CENTS))
    
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Aggregate total cost for current month
    pipeline = [
        {"$match": {"date": {"$gte": month_start.isoformat()}}},
        {"$group": {"_id": None, "total_cost": {"$sum": "$estimated_cost_cents"}}}
    ]
    
    result = await db.ai_usage_tracking.aggregate(pipeline).to_list(1)
    total_cost = result[0]["total_cost"] if result else 0
    
    if total_cost >= budget_cents:
        logger.error(f"Monthly AI budget exceeded: {total_cost}/{budget_cents} cents")
        raise HTTPException(
            status_code=503,
            detail="AI service temporarily unavailable due to high demand. Please try again later."
        )
    
    return True


# ==================== NEW: INPUT SIZE VALIDATION ====================

def validate_input_size(request: MinutesDraftRequest) -> int:
    """
    Calculate total input size for minutes-draft request.
    Returns total character count.
    Raises HTTPException (400) if exceeds MAX_INPUT_CHARS_MINUTES_DRAFT.
    """
    total_chars = 0
    total_chars += len(request.minutes_type or "")
    total_chars += len(request.meeting_date or "")
    total_chars += sum(len(p) for p in request.participants) if request.participants else 0
    total_chars += sum(len(d) for d in request.decisions_outline) if request.decisions_outline else 0
    total_chars += len(request.trust_name or "")
    total_chars += len(request.jurisdiction or "")
    total_chars += len(request.beneficiary_standard or "")
    total_chars += len(request.additional_context or "")
    
    if total_chars > MAX_INPUT_CHARS_MINUTES_DRAFT:
        logger.warning(f"Input size exceeded: {total_chars} chars (max {MAX_INPUT_CHARS_MINUTES_DRAFT})")
        raise HTTPException(
            status_code=400,
            detail=f"Input too large. Total content is {total_chars} characters (maximum {MAX_INPUT_CHARS_MINUTES_DRAFT}). Please reduce the content size."
        )
    
    return total_chars


# ==================== NEW: CACHING FOR GOVERNANCE SUGGESTIONS ====================

async def get_cached_suggestions(user_id: str, trust_id: str) -> Optional[dict]:
    """
    Check ai_suggestion_cache for a valid cached response.
    Returns cached response dict if found and not expired, None otherwise.
    """
    now = datetime.now(timezone.utc)
    cache_cutoff = (now - timedelta(seconds=CACHE_TTL_SECONDS)).isoformat()
    
    cached = await db.ai_suggestion_cache.find_one({
        "user_id": user_id,
        "trust_id": trust_id,
        "cached_at": {"$gte": cache_cutoff}
    })
    
    if cached:
        logger.info(f"Cache hit for governance-suggestions user={user_id} trust={trust_id}")
        return cached.get("response")
    
    return None


async def set_cached_suggestions(user_id: str, trust_id: str, response: dict):
    """
    Store governance suggestions response in cache.
    Replaces any existing cache for this user+trust.
    """
    now = datetime.now(timezone.utc)
    
    await db.ai_suggestion_cache.update_one(
        {"user_id": user_id, "trust_id": trust_id},
        {
            "$set": {
                "response": response,
                "cached_at": now.isoformat()
            }
        },
        upsert=True
    )


# ==================== LOGGING ====================

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
    
    Uses Gemini (via OpenRouter) to create professional minutes with
    WHEREAS/RESOLVED structure based on the provided input.
    Falls back to Claude if OpenRouter is unavailable.
    
    The draft is returned for review and editing - it should not
    be used as-is without trustee review.
    
    Protection layers (in order):
    1. Input size validation (max 10,000 chars) - 400 if exceeded
    2. Hourly rate limit (10/hour) - 429 if exceeded
    3. Daily cap (30/day) - 429 if exceeded
    4. Monthly budget check - 503 if exceeded
    """
    user_id = user["user_id"]
    endpoint = "minutes-draft"
    
    # 1. INPUT SIZE VALIDATION (new)
    input_length = validate_input_size(request)
    
    # 2. CHECK HOURLY RATE LIMIT (existing)
    await check_rate_limit(user_id, endpoint)
    
    # 3. CHECK DAILY CAP (new)
    await check_daily_cap(user_id, endpoint)
    
    # 4. CHECK MONTHLY BUDGET (new)
    await check_monthly_budget()
    
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
    
    # Log the AI call (no sensitive content)
    log_ai_call(user_id, trust_id, endpoint, AI_PRIMARY_MODEL, input_length)
    
    try:
        response = await draft_minutes_from_structured_input(request)
        
        # Record usage after successful call
        await record_daily_usage(user_id, endpoint, COST_PER_CALL_CENTS[endpoint])
        
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
    
    Protection layers (in order):
    1. Hourly rate limit (20/hour) - 429 if exceeded
    2. Daily cap (50/day) - 429 if exceeded
    3. Monthly budget check - 503 if exceeded
    4. Cache check (1hr TTL) - returns cached if available
    """
    user_id = user["user_id"]
    endpoint = "governance-suggestions"
    
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
    
    # CHECK CACHE FIRST (before any rate limits)
    cached = await get_cached_suggestions(user_id, trust_id)
    if cached:
        return GovernanceSuggestionsResponse(**cached)
    
    # 1. CHECK HOURLY RATE LIMIT (existing)
    await check_rate_limit(user_id, endpoint)
    
    # 2. CHECK DAILY CAP (new)
    await check_daily_cap(user_id, endpoint)
    
    # 3. CHECK MONTHLY BUDGET (new)
    await check_monthly_budget()
    
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
    log_ai_call(user_id, trust_id, endpoint, AI_FALLBACK_MODEL, input_length)
    
    # Build request
    suggestions_request = GovernanceSuggestionsRequest(
        health_score=health_score,
        criteria=criteria,
        recent_activity=recent_activity,
        trust_name=trust_name
    )
    
    try:
        response = await generate_governance_suggestions(suggestions_request)
        
        # Record usage after successful call
        await record_daily_usage(user_id, endpoint, COST_PER_CALL_CENTS[endpoint])
        
        # Cache the response
        await set_cached_suggestions(user_id, trust_id, response.model_dump())
        
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating governance suggestions for user {user_id}: {type(e).__name__}")
        raise HTTPException(
            status_code=500,
            detail="AI assistant is currently unavailable. Please try again later."
        )


@router.get("/usage")
async def get_ai_usage(user: dict = Depends(get_current_user)):
    """
    Admin-only endpoint to view AI usage statistics.
    Returns current month and last month stats.
    
    Restricted to: jeff@socialize.video
    """
    # Verify admin access
    user_email = user.get("email", "")
    if user_email != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Access denied. Admin only.")
    
    now = datetime.now(timezone.utc)
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Calculate last month start
    if current_month_start.month == 1:
        last_month_start = current_month_start.replace(year=current_month_start.year - 1, month=12)
    else:
        last_month_start = current_month_start.replace(month=current_month_start.month - 1)
    
    budget_cents = int(os.environ.get("AI_MONTHLY_BUDGET_CENTS", DEFAULT_MONTHLY_BUDGET_CENTS))
    
    # Aggregate current month stats
    current_month_pipeline = [
        {"$match": {"date": {"$gte": current_month_start.isoformat()}}},
        {"$group": {
            "_id": "$endpoint",
            "total_requests": {"$sum": "$count"},
            "total_cost_cents": {"$sum": "$estimated_cost_cents"},
            "unique_users": {"$addToSet": "$user_id"}
        }}
    ]
    
    # Aggregate last month stats
    last_month_pipeline = [
        {"$match": {
            "date": {
                "$gte": last_month_start.isoformat(),
                "$lt": current_month_start.isoformat()
            }
        }},
        {"$group": {
            "_id": "$endpoint",
            "total_requests": {"$sum": "$count"},
            "total_cost_cents": {"$sum": "$estimated_cost_cents"},
            "unique_users": {"$addToSet": "$user_id"}
        }}
    ]
    
    current_month_results = await db.ai_usage_tracking.aggregate(current_month_pipeline).to_list(10)
    last_month_results = await db.ai_usage_tracking.aggregate(last_month_pipeline).to_list(10)
    
    def format_results(results):
        stats = {}
        total_cost = 0
        total_requests = 0
        for r in results:
            endpoint = r["_id"]
            stats[endpoint] = {
                "requests": r["total_requests"],
                "cost_cents": round(r["total_cost_cents"], 2),
                "unique_users": len(r["unique_users"])
            }
            total_cost += r["total_cost_cents"]
            total_requests += r["total_requests"]
        return {
            "by_endpoint": stats,
            "total_requests": total_requests,
            "total_cost_cents": round(total_cost, 2),
            "total_cost_dollars": round(total_cost / 100, 2)
        }
    
    current_stats = format_results(current_month_results)
    last_stats = format_results(last_month_results)
    
    # Calculate budget status
    budget_used_percent = (current_stats["total_cost_cents"] / budget_cents * 100) if budget_cents > 0 else 0
    days_elapsed = now.day
    days_in_month = 30  # Approximate
    projected_monthly_cost = (current_stats["total_cost_cents"] / days_elapsed * days_in_month) if days_elapsed > 0 else 0
    
    return {
        "budget": {
            "monthly_budget_cents": budget_cents,
            "monthly_budget_dollars": round(budget_cents / 100, 2),
            "current_month_used_cents": current_stats["total_cost_cents"],
            "current_month_used_percent": round(budget_used_percent, 1),
            "projected_monthly_cost_cents": round(projected_monthly_cost, 2),
            "on_track": projected_monthly_cost <= budget_cents
        },
        "current_month": {
            "period": current_month_start.strftime("%Y-%m"),
            **current_stats
        },
        "last_month": {
            "period": last_month_start.strftime("%Y-%m"),
            **last_stats
        },
        "rate_limits": {
            "hourly": RATE_LIMITS,
            "daily": DAILY_CAPS
        },
        "cost_per_call_cents": COST_PER_CALL_CENTS,
        "cache_ttl_seconds": CACHE_TTL_SECONDS
    }


@router.get("/status")
async def get_ai_status(user: dict = Depends(get_current_user)):
    """
    Check if AI services are configured and available.
    """
    return {
        "ai_enabled": AI_ENABLED,
        "features": {
            "minutes_drafting": AI_ENABLED,
            "governance_suggestions": AI_ENABLED
        },
        "models": {
            "drafting": AI_PRIMARY_MODEL if AI_ENABLED else None,
            "suggestions": AI_FALLBACK_MODEL if AI_ENABLED else None
        },
        "rate_limits": RATE_LIMITS if AI_ENABLED else None,
        "daily_caps": DAILY_CAPS if AI_ENABLED else None
    }


@router.get("/health")
async def ai_health_check(user: dict = Depends(get_current_user)):
    """
    Health check endpoint for AI service.
    
    Reports status of both Ollama (primary) and Claude (fallback) backends.
    """
    try:
        status = await ai_backend_status()
        return {
            "ok": status.get("ollama", {}).get("available", False) or status.get("claude", {}).get("available", False),
            "providers": status
        }
    except Exception as e:
        logger.error(f"AI health check failed: {type(e).__name__}: {e}")
        return {"ok": False, "error": "AI backend status unavailable"}
