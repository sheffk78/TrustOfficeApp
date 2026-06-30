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


def _format_knowledge_context(user_message: str = "", intent: str = "") -> str:
    """Format relevant knowledge base entries into a single context string.

    The Trust Assistant's product/workflow files are long. If we blindly append
    every file and then truncate the combined context, the newer workflow guide
    can be pushed out of the prompt by unrelated foundational files. Keep the
    feature and workflow guides pinned, then add the most relevant topical files.
    """
    kb = get_knowledge_base()
    if not kb:
        return "No curated knowledge base entries available."

    query = f"{intent} {user_message}".lower()
    # Put high-level training first so "how do I" and scenario guidance survives final prompt truncation.
    pinned_topics = ["15-trustoffice-scenarios", "14-trustoffice-page-playbooks", "13-trustoffice-workflows", "12-trustoffice-features"]

    topic_keywords = {
        "07-distributions": ["distribution", "distribute", "beneficiary payment", "hems", "pay beneficiary"],
        "05-trust-minutes": ["minutes", "meeting", "decision", "resolution", "document a decision"],
        "09-guided-minutes": ["draft minutes", "guided minutes", "meeting template"],
        "04-schedule-a-assets": ["asset", "schedule a", "property", "deed", "account", "inventory"],
        "02-1041-tax-returns": ["1041", "tax", "k-1", "irs", "filing", "ein"],
        "06-state-compliance": ["state", "compliance", "jurisdiction", "law"],
        "08-defensibility-score": ["score", "defensibility", "trust health", "dashboard", "risk", "alert"],
        "10-getting-started": ["start", "onboarding", "first", "setup", "new trustee"],
        "11-video-library": ["video", "lesson", "course", "trustee 101"],
        "03-trustee-duties": ["duty", "fiduciary", "trustee", "responsibility"],
        "01-hems-standard": ["hems", "health", "education", "maintenance", "support"],
    }

    selected = []
    for topic in pinned_topics:
        if topic in kb:
            selected.append(topic)

    for topic, keywords in topic_keywords.items():
        if topic in kb and any(keyword in query for keyword in keywords):
            selected.append(topic)

    # De-duplicate while preserving order, then add one fallback conceptual file.
    selected = list(dict.fromkeys(selected))
    if len(selected) == len([t for t in pinned_topics if t in kb]) and "03-trustee-duties" in kb:
        selected.append("03-trustee-duties")

    def relevant_excerpt(topic: str, content: str) -> str:
        """Return a compact excerpt, preferring the section matching this request."""
        section_hints = {
            "15-trustoffice-scenarios": [
                ("beneficiary", "## Scenario: Beneficiary Asks for Money"),
                ("tax", "## Scenario: Tax Season / Upcoming Filing"),
                ("1041", "## Scenario: Tax Season / Upcoming Filing"),
                ("k-1", "## Scenario: Tax Season / Upcoming Filing"),
                ("missed", "## Scenario: Missed Deadline / Overdue Task"),
                ("overdue", "## Scenario: Missed Deadline / Overdue Task"),
                ("score", "## Scenario: Low Defensibility Score"),
                ("health", "## Scenario: Low Defensibility Score"),
                ("commingling", "## Scenario: Commingling / Personal vs Trust Funds Confusion"),
                ("mixed funds", "## Scenario: Commingling / Personal vs Trust Funds Confusion"),
                ("new trustee", "## Scenario: New Trustee — First 30 Days"),
                ("start", "## Scenario: New Trustee — First 30 Days"),
                ("annual review", "## Scenario: Annual Review"),
                ("prove", "## Scenario: Need to Prove a Decision Was Proper"),
                ("defensible", "## Scenario: Need to Prove a Decision Was Proper"),
                ("resign", "## Scenario: Trustee Resignation / Succession"),
                ("step down", "## Scenario: Trustee Resignation / Succession"),
                ("successor", "## Scenario: Trustee Resignation / Succession"),
                ("handing over", "## Scenario: Trustee Resignation / Succession"),
                ("co-trustee", "## Scenario: Co-Trustee Disagreement"),
                ("disagree", "## Scenario: Co-Trustee Disagreement"),
                ("deadlock", "## Scenario: Co-Trustee Disagreement"),
                ("terminate", "## Scenario: Trust Termination / Final Distribution"),
                ("closing the trust", "## Scenario: Trust Termination / Final Distribution"),
                ("final distribution", "## Scenario: Trust Termination / Final Distribution"),
                ("beneficiary died", "## Scenario: Beneficiary Death or Change in Circumstances"),
                ("per stirpes", "## Scenario: Beneficiary Death or Change in Circumstances"),
                ("incapacitated", "## Scenario: Beneficiary Death or Change in Circumstances"),
                ("compensation", "## Scenario: Trustee Compensation Questions"),
                ("pay myself", "## Scenario: Trustee Compensation Questions"),
                ("trustee pay", "## Scenario: Trustee Compensation Questions"),
            ],
            "14-trustoffice-page-playbooks": [
                ("dashboard", "## Dashboard"),
                ("trust assistant", "## Trust Assistant"),
                ("calendar", "## Governance Calendar"),
                ("governance calendar", "## Governance Calendar"),
                ("minutes", "## Minutes"),
                ("distribution", "## Distributions"),
                ("vault", "## Vault"),
                ("beneficiar", "## Beneficiaries"),
                ("schedule a", "## Schedule A"),
                ("asset", "## Schedule A"),
                ("compensation", "## Compensation"),
                ("settings", "## Settings"),
                ("tax calendar", "## Tax Calendar"),
                ("trust health", "## Trust Health"),
                ("risk", "## Risk Dashboard"),
                ("communication", "## Communications"),
                ("audit", "## Audit Trail"),
            ],
            "13-trustoffice-workflows": [
                ("distribution", "## Workflow: Prepare and Document a Distribution"),
                ("calendar", "## Workflow: Use the Governance Calendar"),
                ("dashboard", "## Workflow: Use Dashboard Alerts and Governance Insights"),
                ("vault", "## Workflow: Use the Document Vault"),
                ("minutes", "## Workflow: Run and Document Trustee Meetings"),
                ("beneficiar", "## Workflow: Add and Maintain Beneficiaries"),
                ("compensation", "## Workflow: Trustee Compensation"),
                ("transaction", "## Workflow: Track Trust Money Movement"),
                ("schedule a", "## Workflow: Maintain Schedule A / Trust Assets"),
                ("asset", "## Workflow: Maintain Schedule A / Trust Assets"),
                ("settings", "## Workflow: Update Trust Settings and Tax Calendar"),
                ("tax", "## Workflow: Update Trust Settings and Tax Calendar"),
            ],
        }
        limits = {
            "15-trustoffice-scenarios": 3000,
            "14-trustoffice-page-playbooks": 2500,
            "13-trustoffice-workflows": 2200,
            "12-trustoffice-features": 1400,
        }
        limit = limits.get(topic, 900)
        for keyword, heading in section_hints.get(topic, []):
            if keyword in query:
                start = content.find(heading)
                if start >= 0:
                    next_heading = content.find("\n## ", start + 4)
                    excerpt = content[start: next_heading if next_heading >= 0 else len(content)]
                    return excerpt[:limit]
        return content[:limit]

    sections = []
    for topic in selected[:5]:
        content = kb[topic]
        sections.append(f"### {topic}\n{relevant_excerpt(topic, content)}")
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
    Only called for write-intents (add_asset, log_minutes, create_distribution, create_beneficiary, create_class_beneficiary, remove_class_beneficiary).
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
        {"_id": 0, "holder_name": 1, "units": 1}
    ).to_list(20)
    context["beneficiaries"] = [
        {
            "name": b.get("holder_name", "Unknown"),
            "units": b.get("units", 0),
        }
        for b in beneficiaries
    ]

    # 6b. Class beneficiaries
    class_bens = await db.class_beneficiaries.find(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0, "class_type": 1, "class_type_label": 1, "percentage": 1, "description": 1}
    ).to_list(20)
    context["class_beneficiaries"] = [
        {
            "class_type": cb.get("class_type", ""),
            "label": cb.get("class_type_label", cb.get("class_type", "")),
            "percentage": cb.get("percentage", 0),
            "description": cb.get("description", ""),
        }
        for cb in class_bens
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

    # 8. Trust Document Analysis (if available)
    analysis = await db.trust_document_analysis.find_one(
        {"trust_id": trust_id, "status": "complete"},
        {"_id": 0, "extracted_fields": 1},
        sort=[("created_at", -1)]
    )
    if analysis:
        fields = analysis.get("extracted_fields", {})
        dist_std = fields.get("distribution_standard", {})
        context["trust_document"] = {
            "grantor": fields.get("grantor_name", ""),
            "trust_type": fields.get("trust_type", ""),
            "distribution_standard": dist_std.get("exact_language", ""),
            "distribution_standard_type": dist_std.get("type", ""),
            "distribution_article": dist_std.get("article_reference", ""),
            "trustee_powers": [
                {"power": p.get("power", ""), "article": p.get("article_reference", "")}
                for p in fields.get("trustee_powers", [])
            ],
            "removal_provisions": fields.get("removal_provisions", {}).get("summary", ""),
            "termination_rules": fields.get("termination_rules", {}).get("summary", ""),
            "beneficiary_names": fields.get("beneficiary_names", []),
        }
        context["trust_document"]["distribution_rules"] = fields.get("distribution_rules", {})
        context["trust_document"]["trustee_powers_detail"] = fields.get("trustee_powers_detail", {})

    # 9. Vault document metadata (titles, categories, descriptions — no file content)
    # This is queried for every request but only injected into the prompt when relevant
    # (see _should_include_vault_context). Keeping it in the context dict is cheap because
    # we exclude file_content — just metadata.
    vault_docs = await db.vault_documents.find(
        {"trust_id": trust_id},
        {
            "_id": 0,
            "file_content": 0,
            "file_content_type": 0,
            "file_size_bytes": 0,
            "storage_path": 0,
        },
    ).sort("created_at", -1).to_list(50)

    context["vault_documents"] = [
        {
            "doc_id": d.get("doc_id", ""),
            "title": d.get("title", "Untitled"),
            "category": d.get("category", "other"),
            "category_label": d.get("category_label", "Other"),
            "date": d.get("date", ""),
            "description": d.get("description", ""),
            "tags": d.get("tags", []),
            "file_name": d.get("file_name", ""),
        }
        for d in vault_docs
    ]

    return context


# ---------------------------------------------------------------------------
# Vault context relevance gate
# ---------------------------------------------------------------------------
# Intents that inherently need vault document awareness
VAULT_RELEVANT_INTENTS = {
    "evaluate_distribution",
    "review_document",
    "create_distribution",
    "upload_document",
    "log_minutes",
    "add_asset",
    "check_deadlines",
    "health_check",
    "recommend_action",
    "create_beneficiary",
    "update_beneficiary",
}

# Keywords that signal a general/ knowledge question is actually about
# the user's own trust documents
VAULT_TRIGGER_KEYWORDS = [
    "trust document", "trust declaration", "trust instrument",
    "vault", "my documents", "certificate", "ein letter",
    "declaration", "amendment", "schedule a",
    "does my trust", "what does my trust", "according to my trust",
    "my trust say", "trust document say", "beneficiary request",
    "distribution request", "the trust document", "my declaration",
    "trust certificate", "cp575", "binder kit",
]


def _should_include_vault_context(intent: str, user_message: str) -> bool:
    """Decide whether vault document metadata should be injected into the prompt.

    Returns True if:
    - The intent is inherently document-relevant (evaluate_distribution, review_document, etc.)
    - OR the user message contains trigger keywords suggesting they're asking about their own docs

    Returns False for:
    - general_chat (greetings, casual)
    - ask_knowledge about abstract concepts with no document references
    """
    if intent in VAULT_RELEVANT_INTENTS:
        return True
    msg_lower = user_message.lower()
    return any(kw in msg_lower for kw in VAULT_TRIGGER_KEYWORDS)


def _format_vault_context(vault_docs: list, trust_document: dict | None) -> str:
    """Format vault document metadata + trust document analysis into a prompt section.

    Tier 1: Trust document analysis (always included when available — it's already extracted
            structured data, just a few hundred tokens).
    Tier 2: Vault document list (titles, categories, descriptions — no file content).
    """
    sections = []

    # --- Tier 1: AI-extracted trust document analysis ---
    if trust_document:
        td_lines = ["## Trust Document Analysis (AI-Extracted)"]
        if trust_document.get("grantor"):
            td_lines.append(f"Grantor: {trust_document['grantor']}")
        if trust_document.get("trust_type"):
            td_lines.append(f"Trust Type: {trust_document['trust_type']}")
        if trust_document.get("distribution_standard"):
            td_lines.append(f"Distribution Standard: {trust_document['distribution_standard']}")
        if trust_document.get("distribution_standard_type"):
            td_lines.append(f"Distribution Standard Type: {trust_document['distribution_standard_type']}")
        if trust_document.get("distribution_article"):
            td_lines.append(f"Distribution Article: {trust_document['distribution_article']}")
        if trust_document.get("beneficiary_names"):
            td_lines.append(f"Named Beneficiaries: {', '.join(trust_document['beneficiary_names'])}")
        if trust_document.get("removal_provisions"):
            td_lines.append(f"Trustee Removal: {trust_document['removal_provisions']}")
        if trust_document.get("termination_rules"):
            td_lines.append(f"Termination Rules: {trust_document['termination_rules']}")

        dist_rules = trust_document.get("distribution_rules", {})
        if dist_rules:
            if dist_rules.get("specific_purposes"):
                td_lines.append(f"Permitted Distribution Purposes: {', '.join(dist_rules['specific_purposes'])}")
            if dist_rules.get("amount_guidance"):
                td_lines.append(f"Amount Guidance: {dist_rules['amount_guidance']}")
            if dist_rules.get("needs_based_factors"):
                td_lines.append(f"Needs-Based Factors: {', '.join(dist_rules['needs_based_factors'])}")
            if dist_rules.get("equal_treatment_requirement"):
                td_lines.append(f"Equal Treatment: {dist_rules['equal_treatment_requirement']}")
            if dist_rules.get("article_reference"):
                td_lines.append(f"Distribution Rules Article: {dist_rules['article_reference']}")

        powers = trust_document.get("trustee_powers", [])
        if powers:
            td_lines.append("Trustee Powers:")
            for p in powers[:10]:
                td_lines.append(f"  - {p.get('power', '')} ({p.get('article', '')})")

        powers_detail = trust_document.get("trustee_powers_detail", {})
        if powers_detail:
            if powers_detail.get("investment_powers"):
                td_lines.append(f"Investment Powers: {powers_detail['investment_powers']}")
            if powers_detail.get("discretion_powers"):
                td_lines.append(f"Discretion Powers: {powers_detail['discretion_powers']}")
            if powers_detail.get("spendthrift_provisions"):
                td_lines.append(f"Spendthrift Provisions: {powers_detail['spendthrift_provisions']}")

        sections.append("\n".join(td_lines))

    # --- Tier 2: Vault document metadata ---
    if vault_docs:
        vault_lines = ["## Vault Documents"]
        for d in vault_docs:
            parts = [f"- **{d.get('title', 'Untitled')}**"]
            if d.get("category_label"):
                parts.append(f" [{d['category_label']}]")
            if d.get("date"):
                parts.append(f" ({d['date']})")
            if d.get("description"):
                parts.append(f" — {d['description']}")
            vault_lines.append("".join(parts))
        sections.append("\n".join(vault_lines))

    return "\n\n".join(sections) if sections else ""


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
    knowledge_context = _format_knowledge_context(user_message=user_message, intent=intent)

    # --- Intelligent vault context gate ---
    # Only include vault documents when the intent or message suggests relevance.
    # This avoids bloating every prompt with document metadata for casual/abstract questions.
    vault_section = ""
    trust_doc = ctx.get("trust_document")
    if _should_include_vault_context(intent, user_message):
        vault_docs = ctx.get("vault_documents", [])
        vault_section = _format_vault_context(vault_docs, trust_doc)
    elif trust_doc:
        # Even for non-document intents, include the trust document analysis if available.
        # It's small structured data and gives the AI baseline awareness of the trust instrument.
        vault_section = _format_vault_context([], trust_doc)

    system_prompt = f"""{CHAT_SYSTEM_PROMPT}

## Current Trust Context
Trust: {trust_info.get('name', 'Unknown')}
Type: {trust_info.get('type', 'Not specified')}
Jurisdiction: {trust_info.get('jurisdiction', 'Not specified')}
State: {trust_info.get('state_code', 'Not specified')}
Beneficiary Standard: {trust_info.get('beneficiary_standard', 'Not specified')}
Defensibility Score: {ctx.get('health_score', {}).get('total', 0)}/100 ({ctx.get('health_score', {}).get('color', 'red')})

{vault_section}

## Upcoming Deadlines (next 14 days)
{json.dumps(ctx.get('upcoming_deadlines', []), indent=2)}

## Pending Items
{json.dumps(ctx.get('pending_items', []), indent=2)}

## Recent Activity (last 30 days)
{json.dumps(ctx.get('recent_activity', []), indent=2)}

## Active Beneficiaries
{json.dumps(ctx.get('beneficiaries', []), indent=2)}

## Class Beneficiaries
{json.dumps(ctx.get('class_beneficiaries', []), indent=2)}

## Tax Deadlines
{json.dumps(ctx.get('tax_deadlines', []), indent=2)}

## Knowledge Base
{knowledge_context[:9500] if knowledge_context else "No knowledge base available."}

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

When referencing trust document details, cite the specific article/section if available
(e.g., "According to your trust instrument, Article 4, Section 4.2...").
If vault documents are listed, reference them by title when relevant to the user's question.

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
    if stripped in ("o", "```", "```", "</s>", "[DONE]", ""):
        return True
    return False


async def generate_response_stream(
    intent: str,
    entities: dict,
    user_message: str,
    trust_context: dict,
    conversation_history: list,
    ai_client_module,
):
    """
    Streaming version of generate_response.
    Yields text chunks for the user-facing response.
    After streaming completes, returns metadata (action_card, citations, caveat)
    via a final non-streaming extraction step.

    Yields:
        str: Text chunks of the AI response
    """
    from ai_client import ai_draft_stream

    action_def = get_action(intent) or ACTION_REGISTRY.get("general_chat", {})
    requires_write = action_def.get("requires_write", False)

    ctx = trust_context
    trust_info = ctx.get("trust", {})
    knowledge_context = _format_knowledge_context(user_message=user_message, intent=intent)

    # --- Intelligent vault context gate (same logic as non-streaming) ---
    vault_section = ""
    trust_doc = ctx.get("trust_document")
    if _should_include_vault_context(intent, user_message):
        vault_docs = ctx.get("vault_documents", [])
        vault_section = _format_vault_context(vault_docs, trust_doc)
    elif trust_doc:
        vault_section = _format_vault_context([], trust_doc)

    # For streaming mode: ask the AI to respond in natural markdown (no JSON wrapper).
    # Action card data is extracted separately if needed.
    system_prompt = f"""{CHAT_SYSTEM_PROMPT}

## Current Trust Context
Trust: {trust_info.get('name', 'Unknown')}
Type: {trust_info.get('type', 'Not specified')}
Jurisdiction: {trust_info.get('jurisdiction', 'Not specified')}
State: {trust_info.get('state_code', 'Not specified')}
Beneficiary Standard: {trust_info.get('beneficiary_standard', 'Not specified')}
Defensibility Score: {ctx.get('health_score', {}).get('total', 0)}/100 ({ctx.get('health_score', {}).get('color', 'red')})

{vault_section}

## Upcoming Deadlines (next 14 days)
{json.dumps(ctx.get('upcoming_deadlines', []), indent=2)}

## Pending Items
{json.dumps(ctx.get('pending_items', []), indent=2)}

## Recent Activity (last 30 days)
{json.dumps(ctx.get('recent_activity', []), indent=2)}

## Active Beneficiaries
{json.dumps(ctx.get('beneficiaries', []), indent=2)}

## Class Beneficiaries
{json.dumps(ctx.get('class_beneficiaries', []), indent=2)}

## Tax Deadlines
{json.dumps(ctx.get('tax_deadlines', []), indent=2)}

## Knowledge Base
{knowledge_context[:9500] if knowledge_context else "No knowledge base available."}

## Conversation History (recent)
{json.dumps(conversation_history[-5:] if conversation_history else [], indent=2)}

## Current Intent
Intent: {intent}
Requires write: {requires_write}

Respond as the Trust Assistant directly to the user. Write your response in clear, well-formatted markdown. Use headings (##), bullet points, bold text, and numbered lists where appropriate. Be conversational but professional.

When referencing trust document details, cite the specific article/section if available
(e.g., "According to your trust instrument, Article 4, Section 4.2...").
If vault documents are listed, reference them by title when relevant to the user's question.

If you are proposing an action (distribution, minutes, adding a beneficiary, etc.), describe what you would do in your response text. The system will generate a separate action card for the user to review.

Do NOT wrap your response in JSON. Do NOT include code blocks around your entire response. Write naturally.
"""

    user_content = f"User message: {user_message}"

    async for chunk in ai_draft_stream(
        system_prompt=system_prompt,
        user_content=user_content,
        max_tokens=2000,
        temperature=0.3,
    ):
        yield chunk


async def generate_action_card(
    intent: str,
    entities: dict,
    user_message: str,
    trust_context: dict,
    response_text: str,
) -> Optional[dict]:
    """
    After streaming response completes, extract action card data if the intent
    requires a write operation. Uses the action extractor prompt.
    """
    from ai_client import ai_draft

    action_def = get_action(intent) or ACTION_REGISTRY.get("general_chat", {})
    requires_write = action_def.get("requires_write", False)

    if not requires_write:
        return None

    # Use the existing action extractor to get structured data
    extracted = await extract_action_data(user_message, intent, entities, None)

    if extracted and extracted.get("extracted"):
        return {
            "type": f"{intent}_preview",
            "data": extracted.get("extracted", {}),
            "requires_confirmation": action_def.get("confirmation_required", True),
        }

    return None


def build_citation_notes(trust_context: dict, intent: str) -> tuple:
    """
    Build citation_note and unknown_note from the trust context.
    Returns (citation_note, unknown_note).
    """
    ctx = trust_context
    citations = []
    unknowns = []

    trust_info = ctx.get("trust", {})
    if trust_info.get("name") and trust_info.get("name") != "Unknown Trust":
        citations.append(f"Trust profile for {trust_info['name']}")

    health = ctx.get("health_score", {})
    if health.get("total", 0) > 0:
        citations.append(f"Defensibility score: {health['total']}/100")

    deadlines = ctx.get("upcoming_deadlines", [])
    if deadlines:
        citations.append(f"{len(deadlines)} upcoming deadline(s) in the next 14 days")

    beneficiaries = ctx.get("beneficiaries", [])
    if beneficiaries:
        citations.append(f"{len(beneficiaries)} active beneficiary record(s)")

    # Trust document analysis citations
    trust_doc = ctx.get("trust_document", {})
    if trust_doc:
        if trust_doc.get("distribution_standard"):
            citations.append(f"Trust instrument: {trust_doc.get('distribution_standard_type', 'distribution standard')} standard")
        if trust_doc.get("distribution_article"):
            citations.append(f"Distribution provisions: {trust_doc['distribution_article']}")
        if trust_doc.get("beneficiary_names"):
            citations.append(f"Named beneficiaries from trust instrument: {', '.join(trust_doc['beneficiary_names'][:5])}")

    # Vault document citations (only when vault context was relevant)
    vault_docs = ctx.get("vault_documents", [])
    if vault_docs and _should_include_vault_context(intent, ctx.get("_user_message", "")):
        doc_titles = [d.get("title", "") for d in vault_docs if d.get("title")]
        if doc_titles:
            citations.append(f"Vault documents referenced: {', '.join(doc_titles[:5])}")

    # Unknowns
    if not trust_info.get("jurisdiction"):
        unknowns.append("Trust jurisdiction is not specified")
    if not trust_info.get("beneficiary_standard") and not trust_doc.get("distribution_standard"):
        unknowns.append("Distribution standard (HEMS vs discretionary) is not specified")
    if health.get("total", 0) == 0:
        unknowns.append("No defensibility score has been calculated yet")
    if not trust_doc:
        unknowns.append("No trust instrument has been uploaded and analyzed yet")

    return (
        "; ".join(citations) if citations else None,
        "; ".join(unknowns) if unknowns else None,
    )