"""
Feedback router — handles user product feedback / support ticket submissions.

Stores feedback in a user_feedback collection with timestamp, user_id,
trust_id, category, and page context. Submissions from the persistent
SupportWidget include category/page_context/trust_id and are routed to
the team via a Discord alert.

Endpoints:
  POST /feedback            — submit feedback (auth required)
  GET  /feedback            — list the current user's feedback
  GET  /feedback/admin      — admin-only: list all feedback (paginated)
"""
import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from typing import Optional

from database import db
from dependencies import get_current_user, require_write_access
from discord_service import send_discord_message, DISCORD_ALERTS_WEBHOOK_URL, DISCORD_LEADS_WEBHOOK_URL, NAVY

logger = logging.getLogger(__name__)

router = APIRouter(tags=["feedback"])

# Kit bot user ID — mentioning triggers Hermes to investigate automatically
KIT_BOT_ID = "1488210610893230160"

VALID_CATEGORIES = {"Bug", "Feature Request", "Question", "Feedback"}


class FeedbackCreate(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    category: Optional[str] = Field(None, max_length=50)
    page_context: Optional[str] = Field(None, max_length=500)
    trust_id: Optional[str] = Field(None, max_length=100)


async def _require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Dependency that requires the caller to be an admin."""
    user_doc = await db.users.find_one(
        {"user_id": user["user_id"]}, {"_id": 0, "is_admin": 1, "email": 1}
    )
    if not user_doc:
        raise HTTPException(status_code=403, detail="User not found")
    is_admin = user_doc.get("is_admin", False)
    admin_emails = {"contact@trustoffice.app"}
    if user_doc.get("email", "").lower() in admin_emails:
        is_admin = True
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def _send_support_discord(doc: dict, user_email: Optional[str]) -> None:
    """Best-effort Discord notification for a new support ticket.

    Never raises — feedback submission must succeed even if Discord is
    unavailable or unconfigured.
    """
    webhook_url = DISCORD_ALERTS_WEBHOOK_URL or DISCORD_LEADS_WEBHOOK_URL
    if not webhook_url:
        logger.info("Discord webhook not configured — skipping support ticket notification")
        return

    category = doc.get("category") or "Feedback"
    page = doc.get("page_context") or "unknown"
    message_preview = (doc.get("message") or "")[:200]
    email = user_email or doc.get("user_id", "unknown")
    timestamp = doc.get("created_at", "")

    content = (
        f"<@{KIT_BOT_ID}> **New Support Ticket — {category}** — "
        f"from {email} on page `{page}`:\n> {message_preview}"
    )

    embed = {
        "title": f"🎫 Support Ticket — {category}",
        "color": NAVY,
        "fields": [
            {"name": "User", "value": email, "inline": True},
            {"name": "Category", "value": category, "inline": True},
            {"name": "Page", "value": page[:200] or "unknown", "inline": False},
            {"name": "Message", "value": (doc.get("message") or "")[:1024], "inline": False},
        ],
        "footer": {"text": "TrustOffice Support Widget"},
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
    }

    try:
        await send_discord_message(
            webhook_url=webhook_url,
            content=content,
            embeds=[embed],
        )
    except Exception as e:
        logger.error(f"Discord support ticket notification failed: {e}")


@router.post("/feedback")
async def submit_feedback(
    payload: FeedbackCreate,
    user: dict = Depends(require_write_access),
):
    """Submit product feedback / a support ticket from a user."""
    user_id = user["user_id"]
    user_email = user.get("email")
    now = datetime.now(timezone.utc)

    # Normalize category; default to "Feedback" for legacy prompt submissions
    category = payload.category.strip() if payload.category else None
    if category and category not in VALID_CATEGORIES:
        # Accept arbitrary categories but cap length (already capped by Field)
        pass
    if not category:
        category = "Feedback"

    # Submissions from the persistent widget carry category/page_context;
    # legacy dashboard prompt submissions only send a message.
    source = "support_widget" if payload.category or payload.page_context else "dashboard_feedback_prompt"

    doc = {
        "feedback_id": f"fb_{now.strftime('%Y%m%d%H%M%S')}_{user_id[:8]}",
        "user_id": user_id,
        "email": user_email,
        "message": payload.message.strip(),
        "category": category,
        "page_context": (payload.page_context.strip() if payload.page_context else None),
        "trust_id": payload.trust_id,
        "source": source,
        "created_at": now.isoformat(),
        "status": "open",
    }

    await db.user_feedback.insert_one(doc)
    # Strip the Mongo _id from the returned copy
    doc.pop("_id", None)

    # Best-effort Discord notification
    await _send_support_discord(doc, user_email)

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


@router.get("/feedback/admin")
async def list_all_feedback(
    user: dict = Depends(_require_admin),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    """Admin-only: list all feedback/support tickets with pagination."""
    query: dict = {}
    if category:
        query["category"] = category
    if status:
        query["status"] = status

    total = await db.user_feedback.count_documents(query)
    results = (
        await db.user_feedback.find(query, {"_id": 0})
        .sort("created_at", -1)
        .skip(offset)
        .limit(limit)
        .to_list(limit)
    )
    return {
        "feedback": results,
        "total": total,
        "limit": limit,
        "offset": offset,
    }