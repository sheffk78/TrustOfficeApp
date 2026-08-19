"""
Support ticket router — handles in-app support/feedback submissions.

When a user submits a support request from the floating feedback bubble,
it creates a ticket with:
- User account info (user_id, email, name)
- Current page URL (where they were when they submitted)
- Selected trust context (if any)
- Browser/user agent info
- Category (bug, feedback, question, feature request)
- Message body

Tickets are stored in MongoDB and a notification email is sent to the
support inbox so Kit/Jeff can see and respond quickly.
"""
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from typing import Optional, Literal
import os
import logging

from database import db
from dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["support"])

SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", "support@trustoffice.app")


class TicketCreate(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)
    category: Literal["bug", "feedback", "question", "feature_request"] = "feedback"
    page_url: str = Field(default="", max_length=500)
    user_agent: str = Field(default="", max_length=500)
    trust_id: Optional[str] = None
    trust_name: Optional[str] = None


@router.post("/support/tickets")
async def create_support_ticket(
    payload: TicketCreate,
    user: dict = Depends(get_current_user),
):
    """Create a support ticket from in-app feedback bubble."""
    user_id = user["user_id"]
    now = datetime.now(timezone.utc)

    # Generate ticket number: TO-YYYYMMDD-XXXX
    date_str = now.strftime("%Y%m%d")
    count = await db.support_tickets.count_documents({})
    ticket_number = f"TO-{date_str}-{count + 1:04d}"

    ticket = {
        "ticket_number": ticket_number,
        "user_id": user_id,
        "user_email": user.get("email", ""),
        "user_name": user.get("name", ""),
        "message": payload.message.strip(),
        "category": payload.category,
        "page_url": payload.page_url,
        "user_agent": payload.user_agent,
        "trust_id": payload.trust_id,
        "trust_name": payload.trust_name,
        "status": "open",  # open → in_progress → resolved → closed
        "priority": "normal",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "responses": [],  # Kit/Jeff responses
        "resolved_at": None,
    }

    await db.support_tickets.insert_one(ticket)

    # Send notification email to support inbox
    try:
        from email_service import email_service
        if email_service.is_configured:
            subject = f"[Support Ticket] {ticket_number} — {payload.category} from {user.get('name', user.get('email', 'Unknown'))}"
            body = f"""
New support ticket submitted.

Ticket: {ticket_number}
From: {user.get('name', 'Unknown')} <{user.get('email', 'unknown')}>
Category: {payload.category}
Page: {payload.page_url}
Trust: {payload.trust_name or 'None selected'}

Message:
{payload.message.strip()}

---
View and respond in the admin dashboard.
"""
            await email_service.send_email(
                to_email=SUPPORT_EMAIL,
                subject=subject,
                html_body=f"<pre style='font-family: monospace; white-space: pre-wrap;'>{body}</pre>",
                text_body=body,
                tag="support-ticket",
            )
    except Exception as e:
        logger.warning(f"Failed to send support ticket email: {e}")
        # Don't fail the ticket creation if email fails

    return {
        "ticket_number": ticket_number,
        "message": "Ticket created. We'll get back to you soon.",
    }


@router.get("/support/tickets")
async def list_my_tickets(
    user: dict = Depends(get_current_user),
):
    """List the current user's support tickets."""
    user_id = user["user_id"]
    results = await db.support_tickets.find(
        {"user_id": user_id},
        {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    return {"tickets": results}


@router.get("/support/tickets/{ticket_number}")
async def get_my_ticket(
    ticket_number: str,
    user: dict = Depends(get_current_user),
):
    """Get a specific support ticket (only if it belongs to the user)."""
    ticket = await db.support_tickets.find_one(
        {"ticket_number": ticket_number, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket