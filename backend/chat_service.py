"""
Chat Service — Business logic for the Trust Assistant conversational AI

Handles intent classification, trust context assembly, knowledge base lookup,
action routing, and response generation with proper fiduciary guardrails.
"""
import os
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta

from action_registry import (
    ACTION_REGISTRY,
    get_action,
    requires_confirmation,
    get_required_fields,
)
from database import db

logger = logging.getLogger(__name__)

# Path to prompt files
PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")

# Knowledge base directory
KNOWLEDGE_DIR = os.path.join(os.path.dirname(__file__), "knowledge")

# Intent classification prompt
with open(os.path.join(PROMPTS_DIR, "intent_classifier.md"), "r") as f:
    INTENT_CLASSIFIER_PROMPT = f.read()

# System prompt (Agent Constitution)
with open(os.path.join(PROMPTS_DIR, "chat_system.md"), "r") as f:
    CHAT_SYSTEM_PROMPT = f.read()

# Action extractor prompt
with open(os.path.join(PROMPTS_DIR, "action_extractor.md"), "r") as f:
    ACTION_EXTRACTOR_PROMPT = f.read()


def _load_knowledge_base() -> Dict[str, str]:
    """Load all knowledge base markdown files into a dict."""
    kb = {}
    if not os.path.isdir(KNOWLEDGE_DIR):
        return kb
    for fname in os.listdir(KNOWLEDGE_DIR):
        if fname.endswith(".md"):
            path = os.path.join(KNOWLEDGE_DIR, fname)
            try:
                with open(path, "r") as f:
                    kb[fname.replace(".md", "")] = f.read()
            except Exception as e:
                logger.warning(f"Failed to load knowledge file {fname}: {e}")
    return kb


# Cache knowledge base at module level
_KNOWLEDGE_BASE_CACHE: Optional[Dict[str, str]] = None


def get_knowledge_base() -> Dict[str, str]:
    """Get knowledge base, loading from disk if not cached."""
    global _KNOWLEDGE_BASE_CACHE
    if _KNOWLEDGE_BASE_CACHE is None:
        _KNOWLEDGE_BASE_CACHE = _load_knowledge_base()
    return _KNOWLEDGE_BASE_CACHE


def _format_knowledge_context() -> str:
    """Format all knowledge base entries into a single context string."""
    kb = get_knowledge_base()
    if not kb:
        return "No curated knowledge base entries available."
    sections = []
    for topic, content in kb.items():
        sections.append(f"### {topic}\n{content[:2000]}")  # Truncate per-entry
    return "\n\n".join(sections)


async def classify_intent(user_message: str, ai_client_module) -> dict:
    """
    Classify the user's message into an intent type.
    Uses the existing AI client (OpenRouter Gemini → Claude fallback).
    """
    from ai_client import ai_draft

    content = f"""Classify this user message for a trust administration assistant.

{INTENT_CLASSIFIER_PROMPT}

USER MESSAGE: {user_message}

Respond with JSON only — no other text."""

    try:
        response = await ai_draft(
            system_prompt="You are an intent classifier for a trust administration AI assistant. Respond with valid JSON only.",
            user_content=content,
            max_tokens=500,
            temperature=0.1,
        )
        if response:
            # Parse JSON from response
            result = json.loads(response.strip())
            return result
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse intent classifier response: {response[:200]}")
    except Exception as e:
        logger.error(f"Intent classifier error: {type(e).__name__}: {e}")

    # Default fallback
    return {"intent": "general_chat", "confidence": 0.3, "entities": {}}


async def extract_action_data(
    user_message: str,
    intent: str,
    entities: dict,
    ai_client_module
) -> dict:
    """
    Extract structured data from the user message for creating records.
    Only called for write-intents (add_asset, log_minutes, create_distribution, add_beneficiary).
    """
    from ai_client import ai_draft

    content = f"""{ACTION_EXTRACTOR_PROMPT}

INTENT: {intent}
USER MESSAGE: {user_message}
CLASSIFIED ENTITIES: {json.dumps(entities)}

Respond with JSON only — no other text."""

    try:
        response = await ai_draft(
            system_prompt="You are a data extractor for a trust administration assistant. Respond with valid JSON only.",
            user_content=content,
            max_tokens=500,
            temperature=0.1,
        )
        if response:
            result = json.loads(response.strip())
            return result
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse action extractor response: {response[:200]}")
    except Exception as e:
        logger.error(f"Action extractor error: {type(e).__name__}: {e}")

    return {"action_type": intent, "extracted": {}, "missing_required": [], "suggested_clarification": None}


async def build_trust_context(user_id: str, trust_id: str) -> dict:
    """
    Assemble the trust context for the AI: trust profile, deadlines,
    recent activity, beneficiaries, pending reviews.
    """
    context = {}

    # 1. Trust profile
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0}
    )
    if trust:
        context["trust"] = {
            "name": trust.get("name", "Unknown Trust"),
            "type": trust.get("trust_type", "Not specified"),
            "jurisdiction": trust.get("jurisdiction", ""),
            "state_code": trust.get("state_code", ""),
            "beneficiary_standard": trust.get("beneficiary_standard", ""),
            "start_date": trust.get("start_date", ""),
            "status": trust.get("status", "active"),
        }
    else:
        context["trust"] = {"name": "Unknown Trust"}

    # 2. Defensibility Score
    health = await db.health_score_snapshots.find_one(
        {"trust_id": trust_id},
        {"_id": 0, "total_score": 1, "score_color": 1, "criteria": 1},
        sort=[("calculated_at", -1)]
    )
    if health:
        context["health_score"] = {
            "total": health.get("total_score", 0),
            "color": health.get("score_color", "red"),
        }
    else:
        context["health_score"] = {"total": 0, "color": "red"}

    # 3. Upcoming deadlines (next 14 days)
    now = datetime.now(timezone.utc)
    two_weeks = (now + timedelta(days=14)).isoformat()
    deadlines = await db.governance_tasks.find(
        {
            "trust_id": trust_id,
            "user_id": user_id,
            "completed_at": None,
            "due_date": {"$lte": two_weeks},
        },
        {"_id": 0, "task_type": 1, "due_date": 1, "description": 1, "priority": 1}
    ).sort("due_date", 1).limit(10).to_list(10)

    context["upcoming_deadlines"] = []
    for d in deadlines:
        context["upcoming_deadlines"].append({
            "type": d.get("task_type", "task"),
            "due_date": d.get("due_date", ""),
            "description": d.get("description", ""),
            "priority": d.get("priority", "normal"),
        })

    # 4. Pending items
    pending_items = []

    # Pending distributions
    pending_dists = await db.distribution_records.find(
        {"trust_id": trust_id, "user_id": user_id, "approved_at": None},
        {"_id": 0, "beneficiary_name": 1, "amount": 1, "date": 1}
    ).sort("date", -1).limit(5).to_list(5)
    for pd in pending_dists:
        pending_items.append({
            "type": "pending_distribution",
            "summary": f"${pd.get('amount', 0):,.2f} to {pd.get('beneficiary_name', 'unknown')}",
            "date": pd.get("date", ""),
        })

    # Overdue tasks
    overdue_tasks = await db.governance_tasks.find(
        {
            "trust_id": trust_id, "user_id": user_id,
            "completed_at": None, "due_date": {"$lt": now.isoformat()}
        },
        {"_id": 0, "task_type": 1, "due_date": 1, "description": 1}
    ).sort("due_date", 1).limit(5).to_list(5)
    for ot in overdue_tasks:
        pending_items.append({
            "type": "overdue_task",
            "summary": ot.get("description", ot.get("task_type", "Overdue task")),
            "due_date": ot.get("due_date", ""),
        })

    context["pending_items"] = pending_items

    # 5. Recent activity (last 30 days)
    thirty_days_ago = (now - timedelta(days=30)).isoformat()
    recent = []

    # Minutes
    recent_mins = await db.minutes_records.find(
        {"trust_id": trust_id, "user_id": user_id, "created_at": {"$gte": thirty_days_ago}},
        {"_id": 0, "minutes_type": 1, "meeting_date": 1, "created_at": 1}
    ).sort("created_at", -1).limit(3).to_list(3)
    for rm in recent_mins:
        recent.append({
            "type": "minutes",
            "label": f"{rm.get('minutes_type', 'Meeting').title()} minutes recorded",
            "date": rm.get("meeting_date", rm.get("created_at", ""))[:10],
        })

    # Distributions
    recent_dists = await db.distribution_records.find(
        {"trust_id": trust_id, "user_id": user_id, "created_at": {"$gte": thirty_days_ago}},
        {"_id": 0, "beneficiary_name": 1, "amount": 1, "date": 1, "approved_at": 1}
    ).sort("created_at", -1).limit(3).to_list(3)
    for rd in recent_dists:
        status = "approved" if rd.get("approved_at") else "pending"
        recent.append({
            "type": "distribution",
            "label": f"${rd.get('amount', 0):,.2f} to {rd.get('beneficiary_name', 'beneficiary')} ({status})",
            "date": rd.get("date", "")[:10],
        })

    context["recent_activity"] = recent

    # 6. Active beneficiaries
    beneficiaries = await db.trust_unit_certificates.find(
        {"trust_id": trust_id, "status": "active"},
        {"_id": 0, "holder_name": 1, "unit_count": 1, "allocation_pct": 1}
    ).to_list(20)
    context["beneficiaries"] = [
        {
            "name": b.get("holder_name", "Unknown"),
            "units": b.get("unit_count", 0),
            "allocation": b.get("allocation_pct", 0),
        }
        for b in beneficiaries
    ]

    # 7. Tax calendar
    upcoming_tax = await db.tax_calendar_entries.find(
        {
            "trust_id": trust_id,
            "status": {"$in": ["pending", "upcoming"]},
            "due_date": {"$gte": now.isoformat()[:10]},
        },
        {"_id": 0, "filing_name": 1, "due_date": 1, "status": 1}
    ).sort("due_date", 1).limit(5).to_list(5)
    context["tax_deadlines"] = [
        {
            "filing": t.get("filing_name", "Tax filing"),
            "due_date": t.get("due_date", ""),
        }
        for t in upcoming_tax
    ]

    return context


async def generate_response(
    intent: str,
    entities: dict,
    user_message: str,
    trust_context: dict,
    conversation_history: list,
    ai_client_module,
) -> dict:
    """
    Generate the AI response based on the classified intent, trust context,
    and conversation history. Returns a structured response dict.
    """
    from ai_client import ai_draft

    action_def = get_action(intent) or ACTION_REGISTRY.get("general_chat", {})
    requires_write = action_def.get("requires_write", False)
    needs_confirm = action_def.get("confirmation_required", False)

    # Format trust context
    ctx = trust_context
    trust_info = ctx.get("trust", {})

    # Build the system prompt with context
    knowledge_context = _format_knowledge_context()

    system_prompt = f"""{CHAT_SYSTEM_PROMPT}

## Current Trust Context
Trust: {trust_info.get('name', 'Unknown')}
Type: {trust_info.get('type', 'Not specified')}
Jurisdiction: {trust_info.get('jurisdiction', 'Not specified')}
State: {trust_info.get('state_code', 'Not specified')}
Beneficiary Standard: {trust_info.get('beneficiary_standard', 'Not specified')}
Defensibility Score: {ctx.get('health_score', {}).get('total', 0)}/100 ({ctx.get('health_score', {}).get('color', 'red')})

## Upcoming Deadlines (next 14 days)
{json.dumps(ctx.get('upcoming_deadlines', []), indent=2)}

## Pending Items
{json.dumps(ctx.get('pending_items', []), indent=2)}

## Recent Activity (last 30 days)
{json.dumps(ctx.get('recent_activity', []), indent=2)}

## Active Beneficiaries
{json.dumps(ctx.get('beneficiaries', []), indent=2)}

## Tax Deadlines
{json.dumps(ctx.get('tax_deadlines', []), indent=2)}

## Knowledge Base
{knowledge_context[:3000] if knowledge_context else "No knowledge base available."}

## Conversation History (recent)
{json.dumps(conversation_history[-5:] if conversation_history else [], indent=2)}

## Current Intent
Intent: {intent}
Requires write: {requires_write}
Confirmation required: {needs_confirm}

Respond as the Trust Assistant. Include:
1. "What I'm basing this on" — cite specific data from the context above
2. "What I don't know" — call out information gaps
3. Caveat language for any action proposals

Format your response as JSON:
{{
  "message": "Your main response text to the user",
  "action_card": {{
    "type": "{intent}_preview" if requires_write else null,
    "data": {{...extracted action fields}},
    "requires_confirmation": {str(needs_confirm).lower()}
  }} or null,
  "citation_note": "What I'm basing this on...",
  "unknown_note": "What I don't know...",
  "caveat": "You should review this with your legal or tax professional..."
}}
"""

    user_content = f"User message: {user_message}"

    try:
        response_text = await ai_draft(
            system_prompt=system_prompt,
            user_content=user_content,
            max_tokens=2000,
            temperature=0.3,
        )

        if response_text and not _is_garbled(response_text):
            # Strip markdown code block fences if present
            clean_text = response_text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            elif clean_text.startswith("```"):
                clean_text = clean_text[3:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]
            clean_text = clean_text.strip()

            # Try to parse as JSON
            try:
                result = json.loads(clean_text)
                return result
            except json.JSONDecodeError:
                # Return as plain text message
                return {
                    "message": response_text.strip(),
                    "action_card": None,
                    "citation_note": None,
                    "unknown_note": None,
                    "caveat": None,
                }
    except Exception as e:
        logger.error(f"AI response generation error: {type(e).__name__}: {e}")

    # Fallback response
    return {
        "message": "I'm having trouble connecting to my AI backend. Please try again in a moment.",
        "action_card": None,
        "citation_note": None,
        "unknown_note": None,
        "caveat": None,
    }


def _is_garbled(text: str) -> bool:
    """Check if response is empty or garbled."""
    if not text or not text.strip():
        return True
    stripped = text.strip()
    if stripped in ("o", "```", "<|endoftext|>", "</s>", "[DONE]", ""):
        return True
    return False