"""
Contact Memory router — customer memory system for TrustOffice.

Provides endpoints to:
  - Retrieve contact context (profile summary + recent interactions)
  - Log support interactions
  - Update a contact's profile summary
  - Redact a contact's history (privacy)
  - Handle inbound email flow: get-or-create contact, draft an AI reply using
    contact context + knowledge-base snippets, log the interaction, and
    opportunistically update the durable profile summary.

Service layer: services/contact_memory_service.py (owned by another agent).
This router imports and calls the service functions per their contract.
"""
import re
import logging
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from database import db
from dependencies import get_current_user, require_write_access
from ai_client import ai_draft, ai_suggest, AIClientError
from services import contact_memory_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/contact-memory", tags=["contact_memory"])


# ==================== SCHEMAS ====================

class InteractionCreate(BaseModel):
    contact_id: str = Field(..., min_length=1)
    raw_content: str = Field(..., min_length=1)
    generated_reply: Optional[str] = None
    summary: Optional[str] = None
    topics: Optional[List[str]] = None
    sentiment: Optional[str] = None
    urgency: Optional[str] = None
    status: str = Field("resolved")
    channel: str = Field("email")


class ProfileSummaryUpdate(BaseModel):
    new_summary_fields: Dict[str, Any] = Field(...)


class EmailFlowRequest(BaseModel):
    sender_email: str = Field(..., min_length=1)
    raw_content: str = Field(..., min_length=1)
    sender_name: Optional[str] = None


class ContactContextResponse(BaseModel):
    contact: Optional[Dict[str, Any]] = None
    profile_summary: Optional[Dict[str, Any]] = None
    recent_interactions: List[Dict[str, Any]] = Field(default_factory=list)


class EmailFlowResponse(BaseModel):
    reply: str
    interaction_id: str
    contact_id: str


class RedactionResponse(BaseModel):
    contact_id: str
    redacted: bool
    detail: Optional[str] = None


# ==================== ENDPOINTS ====================

@router.get("/context", response_model=ContactContextResponse)
async def get_contact_context_endpoint(
    email: str = Query(..., description="Contact email to look up"),
    user: dict = Depends(get_current_user),
):
    """Retrieve a contact's context: profile summary and recent interactions."""
    if not email or not email.strip():
        raise HTTPException(status_code=400, detail="email query parameter is required.")
    try:
        result = await contact_memory_service.get_contact_context(email, user_id=user.get("user_id"))
    except Exception as exc:
        logger.exception("get_contact_context failed for email=%s", email)
        raise HTTPException(status_code=500, detail=f"Failed to load contact context: {exc}")
    if not result:
        return ContactContextResponse(contact=None, profile_summary=None, recent_interactions=[])
    return ContactContextResponse(
        contact=result.get("contact"),
        profile_summary=result.get("profile_summary"),
        recent_interactions=result.get("recent_interactions", []) or [],
    )


@router.post("/interactions")
async def log_interaction_endpoint(
    payload: InteractionCreate,
    user: dict = Depends(require_write_access),
):
    """Log a support interaction for a contact."""
    try:
        interaction = await contact_memory_service.log_support_interaction(
            contact_id=payload.contact_id,
            raw_content=payload.raw_content,
            generated_reply=payload.generated_reply,
            summary=payload.summary or "",
            topics=payload.topics or [],
            sentiment=payload.sentiment or "neutral",
            urgency=payload.urgency or "low",
            status=payload.status,
            channel=payload.channel,
            user_id=user.get("user_id"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("log_support_interaction failed for contact_id=%s", payload.contact_id)
        raise HTTPException(status_code=500, detail=f"Failed to log interaction: {exc}")
    if not interaction:
        raise HTTPException(status_code=404, detail="Contact not found; interaction not logged.")
    return interaction


@router.patch("/profile/{contact_id}")
async def update_profile_endpoint(
    contact_id: str,
    payload: ProfileSummaryUpdate,
    user: dict = Depends(require_write_access),
):
    """Update a contact's durable profile summary fields."""
    if not payload.new_summary_fields:
        raise HTTPException(status_code=400, detail="new_summary_fields must not be empty.")
    try:
        updated = await contact_memory_service.update_contact_profile_summary(
            contact_id=contact_id,
            new_summary_fields=payload.new_summary_fields,
            user_id=user.get("user_id"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("update_contact_profile_summary failed for contact_id=%s", contact_id)
        raise HTTPException(status_code=500, detail=f"Failed to update profile summary: {exc}")
    if not updated:
        raise HTTPException(status_code=404, detail="Contact not found; profile not updated.")
    return updated


@router.delete("/history/{contact_id}", response_model=RedactionResponse)
async def redact_history_endpoint(
    contact_id: str,
    user: dict = Depends(require_write_access),
):
    """Redact (privacy-delete) a contact's interaction history."""
    try:
        result = await contact_memory_service.redact_contact_history(
            contact_id=contact_id,
            user_id=user.get("user_id"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("redact_contact_history failed for contact_id=%s", contact_id)
        raise HTTPException(status_code=500, detail=f"Failed to redact history: {exc}")
    if not result:
        raise HTTPException(status_code=404, detail="Contact not found; nothing redacted.")
    return RedactionResponse(
        contact_id=result.get("contact_id", contact_id),
        redacted=bool(result.get("redacted", True)),
        detail=result.get("detail"),
    )


# ==================== INBOUND EMAIL FLOW ====================

def _truncate(text: str, limit: int = 1200) -> str:
    """Truncate text to a char limit for prompt inclusion."""
    if not text:
        return ""
    return text[:limit] + ("…" if len(text) > limit else "")


async def _fetch_kb_snippets(raw_content: str, limit: int = 3) -> str:
    """
    Fetch a few published knowledge-base article snippets relevant to the
    inbound email content. Searches title/summary/tags by keyword match.
    Returns a concatenated short snippet string (empty if nothing found).
    """
    # Extract simple keywords from the email content (lowercased, alnum tokens).
    tokens = re.findall(r"[a-zA-Z]{4,}", raw_content.lower())
    # Deduplicate while preserving order; cap to keep the query cheap.
    seen = set()
    keywords = []
    for tok in tokens:
        if tok not in seen and tok not in {"please", "thank", "thanks", "would", "could"}:
            seen.add(tok)
            keywords.append(tok)
        if len(keywords) >= 8:
            break

    if not keywords:
        return ""

    # Build an OR query across title/summary/tags.
    or_clauses = []
    for kw in keywords:
        or_clauses.append({"title": {"$regex": re.escape(kw), "$options": "i"}})
        or_clauses.append({"summary": {"$regex": re.escape(kw), "$options": "i"}})
        or_clauses.append({"tags": {"$in": [kw]}})

    query = {"published": True, "$or": or_clauses}
    try:
        cursor = db.knowledge_articles.find(query, {"title": 1, "summary": 1, "content": 1}).limit(limit)
        articles = await cursor.to_list(length=limit)
    except Exception:
        logger.warning("knowledge_articles lookup failed", exc_info=True)
        return ""

    if not articles:
        return ""

    snippets = []
    for art in articles:
        title = art.get("title", "")
        body = art.get("summary") or _truncate(art.get("content", ""), 200)
        if title:
            snippets.append(f"- {title}: {body}".strip())
    return "\n".join(snippets)


def _build_context_block(contact: Optional[dict], profile_summary: Optional[dict],
                          recent_interactions: List[dict]) -> str:
    """Render a compact context string for the AI prompt."""
    parts: List[str] = []
    if contact:
        name = contact.get("name") or contact.get("sender_name") or ""
        email = contact.get("email", "")
        parts.append(f"Contact: {name} <{email}>".strip())
    if profile_summary:
        # Profile summary may be a dict of durable fields; render compactly.
        fields = {k: v for k, v in profile_summary.items()
                  if k not in {"_id", "contact_id", "user_id"} and v is not None}
        if fields:
            rendered = ", ".join(f"{k}={v}" for k, v in fields.items())
            parts.append(f"Profile summary: {rendered}")
    if recent_interactions:
        recent_lines = []
        for it in recent_interactions[:5]:
            summary = it.get("summary") or _truncate(it.get("raw_content", ""), 120)
            when = it.get("created_at") or it.get("timestamp") or ""
            recent_lines.append(f"  - [{when}] {summary}".strip())
        if recent_lines:
            parts.append("Recent interactions:\n" + "\n".join(recent_lines))
    return "\n".join(parts).strip()


@router.post("/email-flow", response_model=EmailFlowResponse)
async def email_flow_endpoint(
    payload: EmailFlowRequest,
    user: dict = Depends(require_write_access),
):
    """
    Handle an inbound support email end-to-end:
      1. Get-or-create the contact by sender email.
      2. Fetch contact context (profile + recent interactions).
      3. Draft an AI reply using context + a knowledge-base snippet.
      4. Log the support interaction (status='resolved').
      5. Opportunistically update the profile summary with durable info.
    Never 500s on AI failure — falls back to a plain acknowledgment.
    """
    sender_email = payload.sender_email.strip()
    raw_content = payload.raw_content
    sender_name = payload.sender_name

    # 1) Get-or-create contact
    try:
        contact = await contact_memory_service.get_or_create_contact_by_email(
            email=sender_email,
            name=sender_name,
            user_id=user.get("user_id"),
        )
    except Exception as exc:
        logger.exception("get_or_create_contact_by_email failed for email=%s", sender_email)
        raise HTTPException(status_code=500, detail=f"Failed to resolve contact: {exc}")

    if not contact:
        raise HTTPException(status_code=404, detail="Contact could not be resolved or created.")
    contact_id = contact.get("contact_id") or contact.get("id") or ""
    if not contact_id:
        raise HTTPException(status_code=500, detail="Resolved contact has no contact_id.")

    # 2) Fetch context
    try:
        context = await contact_memory_service.get_contact_context(
            email=sender_email, user_id=user.get("user_id")
        )
    except Exception:
        logger.warning("get_contact_context failed during email-flow; continuing without context",
                       exc_info=True)
        context = {"contact": contact, "profile_summary": None, "recent_interactions": []}

    profile = context.get("profile_summary") if context else None
    recent = (context.get("recent_interactions") if context else None) or []
    context_block = _build_context_block(contact, profile, recent)

    # 3) Draft AI reply (+ KB snippet)
    kb_snippet = await _fetch_kb_snippets(raw_content)

    system_prompt = (
        "You are TrustOffice's support assistant. Draft a concise, helpful reply to a "
        "customer's inbound email. Use the provided contact context and any relevant "
        "knowledge-base snippet to personalize the response. Be warm, professional, "
        "and specific. Do not invent facts; if unsure, offer to follow up."
    )
    user_content_parts = [
        f"Sender email: {sender_email}",
    ]
    if sender_name:
        user_content_parts.append(f"Sender name: {sender_name}")
    if context_block:
        user_content_parts.append(f"Contact context:\n{context_block}")
    if kb_snippet:
        user_content_parts.append(f"Relevant knowledge base:\n{kb_snippet}")
    user_content_parts.append(f"Inbound email:\n{_truncate(raw_content, 2000)}")
    user_content = "\n\n".join(user_content_parts)

    reply_text = ""
    summary_text = None
    topics: List[str] = []
    sentiment: Optional[str] = None
    urgency: Optional[str] = None
    durable_fields: Dict[str, Any] = {}

    try:
        reply_text = await ai_draft(system_prompt, user_content, max_tokens=600, temperature=0.3)

        # Short AI-generated summary + topic/sentiment/urgency via a fast call.
        meta_prompt = (
            "Analyze the inbound support email and return a JSON object with keys: "
            '"summary" (one short sentence), "topics" (array of 1-5 short labels), '
            '"sentiment" (one of: positive, neutral, negative), '
            '"urgency" (one of: low, medium, high), '
            '"durable" (an object of any durable customer preferences detected, '
            "e.g. preferred contact time, language, or a stated preference; empty object if none). "
            "Return ONLY the JSON object."
        )
        meta_user = (
            f"Email:\n{_truncate(raw_content, 1500)}\n\n"
            f"Drafted reply:\n{_truncate(reply_text, 800)}"
        )
        meta_text = await ai_suggest(meta_prompt, meta_user, max_tokens=300, temperature=0.1)

        # Tolerant JSON parse
        import json as _json
        try:
            meta = _json.loads(meta_text)
        except Exception:
            # Try to extract a JSON object from the text.
            m = re.search(r"\{.*\}", meta_text, re.DOTALL)
            meta = _json.loads(m.group(0)) if m else {}
        if isinstance(meta, dict):
            summary_text = meta.get("summary") or summary_text
            t = meta.get("topics")
            if isinstance(t, list):
                topics = [str(x) for x in t][:5]
            s = meta.get("sentiment")
            if isinstance(s, str):
                sentiment = s
            u = meta.get("urgency")
            if isinstance(u, str):
                urgency = u
            d = meta.get("durable")
            if isinstance(d, dict) and d:
                durable_fields = {str(k): v for k, v in d.items()}
    except AIClientError as exc:
        logger.warning("AI drafting failed in email-flow; using fallback reply. err=%s", exc)
        reply_text = (
            f"Hi {sender_name or ''},\n\n"
            "Thank you for reaching out to TrustOffice support. We've received your message "
            "and a team member will follow up with you shortly.\n\n"
            "— TrustOffice Support".strip()
        )
    except Exception as exc:
        # Any unexpected AI error still must not 500 the endpoint.
        logger.warning("Unexpected AI error in email-flow; using fallback reply. err=%s", exc)
        reply_text = (
            f"Hi {sender_name or ''},\n\n"
            "Thank you for reaching out to TrustOffice support. We've received your message "
            "and a team member will follow up with you shortly.\n\n"
            "— TrustOffice Support".strip()
        )

    if not summary_text:
        summary_text = _truncate(raw_content, 140) or "Inbound support email."

    # 4) Log the interaction
    try:
        interaction = await contact_memory_service.log_support_interaction(
            contact_id=contact_id,
            raw_content=raw_content,
            generated_reply=reply_text,
            summary=summary_text,
            topics=topics,
            sentiment=sentiment or "neutral",
            urgency=urgency or "low",
            status="resolved",
            channel="email",
            user_id=user.get("user_id"),
        )
    except Exception:
        logger.exception("log_support_interaction failed in email-flow for contact_id=%s", contact_id)
        raise HTTPException(status_code=500, detail="Failed to log interaction.")

    interaction_id = ""
    if isinstance(interaction, dict):
        interaction_id = (
            interaction.get("interaction_id")
            or interaction.get("id")
            or ""
        )

    # 5) Opportunistically update profile summary with durable info
    if durable_fields:
        try:
            await contact_memory_service.update_contact_profile_summary(
                contact_id=contact_id,
                new_summary_fields=durable_fields,
                user_id=user.get("user_id"),
            )
        except Exception:
            logger.warning("update_contact_profile_summary skipped in email-flow for contact_id=%s",
                           contact_id, exc_info=True)

    return EmailFlowResponse(
        reply=reply_text,
        interaction_id=interaction_id,
        contact_id=contact_id,
    )