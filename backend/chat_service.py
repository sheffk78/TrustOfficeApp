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


def _normalize_trustees(trustees):
    """Normalize trustees field to a comma-joined string.

    Handles both legacy comma-separated strings and new list format.
    """
    if not trustees:
        return ""
    if isinstance(trustees, list):
        return ", ".join(t for t in trustees if t)
    return str(trustees)

# Path to prompt files
PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")

# Knowledge base directory
KNOWLEDGE_DIR = os.path.join(os.path.dirname(__file__), "knowledge")

# Intent classification prompt
with open(os.path.join(PROMPTS_DIR, "intent_classifier.md"), "r") as f:
    INTENT_CLASSIFIER_PROMPT = f.read()

# System prompt — split into core (always), actions (action intents), escalation (fiduciary)
with open(os.path.join(PROMPTS_DIR, "chat_system_core.md"), "r") as f:
    CHAT_SYSTEM_CORE = f.read()

with open(os.path.join(PROMPTS_DIR, "chat_system_actions.md"), "r") as f:
    CHAT_SYSTEM_ACTIONS = f.read()

with open(os.path.join(PROMPTS_DIR, "chat_system_escalation.md"), "r") as f:
    CHAT_SYSTEM_ESCALATION = f.read()

# Legacy full prompt kept for backward compatibility (unused in split mode)
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


# Unified intent classification sets — derived once, used by both
# _format_knowledge_context() and _build_system_prompt(). (MEDIUM-2 fix)
ACTION_INTENTS = {
    "add_asset", "contribute_asset", "update_asset", "log_minutes",
    "create_distribution", "evaluate_distribution", "create_beneficiary",
    "create_class_beneficiary", "remove_class_beneficiary", "update_beneficiary",
    "remove_beneficiary", "send_certificate", "cancel_distribution",
    "upload_document", "setup_compensation", "record_compensation_payment",
    "add_investment", "schedule_task", "add_transaction", "change_settings",
    "create_entity", "review_document", "dismiss_alert", "recommend_action",
    "check_deadlines", "health_check",
}
ESCALATION_INTENTS = ACTION_INTENTS | {"ask_knowledge", "emergency"}


def _format_knowledge_context(user_message: str = "", intent: str = "") -> str:
    """Format relevant knowledge base entries into a single context string.

    The Trust Assistant's product/workflow files are long. If we blindly append
    every file and then truncate the combined context, the newer workflow guide
    can be pushed out of the prompt by unrelated foundational files. Keep the
    feature and workflow guides pinned (for action intents), then add the most
    relevant topical files. For knowledge/chat intents, skip product files to
    save tokens and avoid drowning out trust-type knowledge.
    """
    kb = get_knowledge_base()
    if not kb:
        return "No curated knowledge base entries available."

    query = f"{intent} {user_message}".lower()

    # Product files are only pinned for action-oriented intents. For knowledge
    # questions and casual chat, they waste ~9K chars of context and crowd out
    # the trust-type knowledge the user actually needs.
    # Uses the module-level ACTION_INTENTS set (unified with _build_system_prompt).
    if intent in ACTION_INTENTS:
        pinned_topics = ["15-trustoffice-scenarios", "14-trustoffice-page-playbooks", "13-trustoffice-workflows", "12-trustoffice-features"]
    else:
        pinned_topics = []

    topic_keywords = {
        "16-minutes-types-and-templates": ["minutes", "meeting", "create minutes", "draft minutes", "initial minutes", "first meeting", "trustee meeting", "document a", "resolution", "annual review", "quarterly", "template"],
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
        # --- Trust type knowledge (17-* series) ---
        "17-revocable-living-trust": ["revocable", "living trust", "revocable living", "probate", "inter vivos", "grantor trust", "revocable trust"],
        "17-irrevocable-life-insurance-trust": ["ilit", "life insurance trust", "irrevocable life insurance", "crummey", "insurance trust", "policy proceeds", "gift tax annual exclusion", "notice of withdrawal"],
        "17-dynasty-trust": ["dynasty", "perpetuity", "generation-skipping", "gst exemption", "dynasty trust", "multi-generational", "perpetual trust"],
        "17-charitable-remainder-trust": ["charitable remainder", "crt", "charitable trust", "remainder beneficiary", "5% payout", "annuity trust", "unitrust", "charitable remainder annuity", "charitable remainder unitrust"],
        "17-charitable-lead-trust": ["charitable lead", "clt", "charitable lead annuity", "charitable lead unitrust", "income to charity", "remainder to family"],
        "17-special-needs-trust": ["special needs", "supplemental needs", "ssi", "medicaid", "disability trust", "third-party special needs", "first-party special needs", "payback", "able account", "d4a", "sole benefit"],
        "17-spendthrift-trust": ["spendthrift", "creditor protection", "spendthrift clause", "alienation", "voluntary alienation", "involuntary alienation"],
        "17-asset-protection-trust": ["asset protection", "dapt", "fapt", "domestic asset protection", "foreign asset protection", "self-settled spendthrift", "alaska trust", "nevada trust", "south dakota trust", "fraudulent transfer"],
        "17-blind-trust": ["blind trust", "conflict of interest", "blind trust", "independent trustee", "political trust", "ethics trust"],
        "17-land-trust": ["land trust", "illinois land trust", "florida land trust", "property anonymity", "beneficial interest", "title by trustee"],
        "17-qtip-trust": ["qtip", "qualified terminal interest", "marital deduction", "surviving spouse income", "terminal interest", "qtip election", "estate tax return", "form 706"],
        "17-generation-skipping-trust": ["generation-skipping", "gst", "skip-generation", "gst tax", "gst exemption", "form 709", "grandchildren trust", "generation skipping transfer"],
        "17-bypass-trust": ["bypass trust", "credit shelter", "a-b trust", "exemption trust", "family trust", "portability", "applicable exemption amount", "bypass", "credit shelter trust"],
        "17-grat": ["grat", "grantor retained annuity", "annuity trust", "zeroed-out grat", "estate freeze", "irc 2701", "grantor retained annuity trust"],
        "17-qualified-personal-residence-trust": ["qprt", "qualified personal residence", "personal residence trust", "retained right to occupy", "home to trust", "residence trust", "irc 2702"],
        "17-testamentary-trust": ["testamentary", "will trust", "death trust", "probate trust", "testamentary trust"],
        "17-totten-trust": ["totten", "bank account trust", "payable on death", "pod account", "totten trust"],
        "17-marital-deduction-trust": ["marital deduction", "marital trust", "marital share", "spousal trust", "marital deduction trust", "unlimited marital deduction"],
        "17-minors-trust": ["minor's trust", "2503(c)", "minors trust", "gift to minor", "custodial trust", "child trust"],
        "17-irrevocable-trust-general": ["irrevocable", "irrevocable trust", "irrevocable general", "non-grantor trust", "irrevocable structure"],
        # --- State-specific compliance (18-* series) ---
        "18-state-compliance-california": ["california", "ca compliance", "ca tax", "ca probate", "ca trust", "probate code 16061"],
        "18-state-compliance-texas": ["texas", "tx compliance", "tx trust", "texas trust", "franchise tax"],
        "18-state-compliance-florida": ["florida", "fl compliance", "fl trust", "florida trust code", "florida trust"],
        "18-state-compliance-new-york": ["new york", "ny compliance", "ny trust", "ny tax", "it-205", "ny estate tax"],
        "18-state-compliance-illinois": ["illinois", "il compliance", "il trust", "il-1041", "illinois probate"],
        "18-state-compliance-nevada": ["nevada", "nv compliance", "nv trust", "nevada trust", "nv perpetuity"],
        "18-state-compliance-south-dakota": ["south dakota", "sd compliance", "sd trust", "south dakota trust", "sd perpetuity"],
        "18-state-compliance-delaware": ["delaware", "de compliance", "de trust", "delaware trust", "chancery", "de perpetuity"],
        "18-state-compliance-arizona": ["arizona", "az compliance", "az trust", "arizona trust"],
        "18-state-compliance-washington": ["washington", "wa compliance", "wa trust", "washington trust", "wa estate tax"],
        # --- Communication templates (19-*) ---
        "19-beneficiary-communication-templates": ["beneficiary communication", "distribution letter", "approval letter", "denial letter", "annual accounting", "resignation notice", "beneficiary notice", "trustee communication", "communication template", "write to beneficiary", "notify beneficiary"],
        # --- Trust lifecycle stages (20-*) ---
        "20-trust-lifecycle-stages": ["lifecycle", "initial setup", "first 90 days", "ongoing administration", "trust termination", "wind down", "trust modification", "amendment", "decanting", "final return", "trust stages", "lifecycle stage"],
        # --- Crisis escalation (21-*) ---
        "21-crisis-escalation": ["fraud", "theft", "stolen", "unauthorized", "lawsuit", "litigation", "subpoena", "court order", "audit", "creditor claim", "incapacity", "trustee death", "missing beneficiary", "exploitation", "foreclosure", "emergency", "crisis", "urgent", "police", "law enforcement", "adult protective", "dispute", "threatened"],
        # --- Quarterly review guide (22-*) ---
        "22-quarterly-review-guide": ["quarterly review", "quarterly", "quarter", "review checklist", "what do i do for", "quarterly meeting", "trust review", "annual review", "annual meeting"],
        # --- Beneficiary types and allocation models (23-*) ---
        "23-beneficiary-types-and-allocations": ["beneficiary type", "class beneficiary", "individual beneficiary", "organization beneficiary", "allocation", "units", "percentage", "per capita", "per stirpes", "distribution convention", "allocation mode", "unit mode", "percentage mode", "total allocation", "mixed allocation", "reserved pool", "beneficiary share", "trust units", "authorized units", "which beneficiary type", "should i use a class", "after-born", "descendants class", "children class", "issue", "heirs at law", "blood relatives"],
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
    if not pinned_topics and "03-trustee-duties" in kb and not selected:
        # For knowledge/chat intents with no topic match, add trustee duties as a baseline.
        selected.append("03-trustee-duties")
    elif len(selected) == len([t for t in pinned_topics if t in kb]) and "03-trustee-duties" in kb:
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
                ("contribute", "## Workflow: Maintain Schedule A / Trust Assets"),
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

    # --- FTS5 fallback: if keyword matching found fewer than 3 files, use the
    # SQLite FTS5 index for semantic search. This catches cases where the
    # user's phrasing doesn't match our hand-coded keyword mappings.
    if len(sections) < 3:
        try:
            from services import trust_knowledge
            # Resolve paths the same way knowledge_retrieval.py does:
            # parents[0]=chat_service.py dir (backend), parents[1]=app root.
            # In Railway: /app/KNOWLEDGE/, locally: TrustOfficeApp/KNOWLEDGE/
            brand_root = os.path.dirname(os.path.dirname(__file__))
            registry_path = os.environ.get(
                "TRUST_KNOWLEDGE_REGISTRY",
                os.path.join(brand_root, "KNOWLEDGE", "trustoffice-registry.yaml"),
            )
            db_path = os.environ.get(
                "TRUST_KNOWLEDGE_DB",
                os.path.join(brand_root, "data", "trust_knowledge.db"),
            )
            # Skip FTS if the registry doesn't exist (don't try to build index)
            if os.path.isfile(registry_path):
                if not os.path.isfile(db_path):
                    trust_knowledge.build_index(registry_path, KNOWLEDGE_DIR, db_path)
                fts_result = trust_knowledge.retrieve(
                    user_message,
                    {"db_path": db_path, "limit": 3, "status": "live"},
                )
                existing = "\n".join(sections)
                for item in fts_result.get("results", [])[:2]:
                    item_title = item.get("title", "")
                    item_snippet = item.get("snippet", "")
                    if item_snippet and item_title not in existing:
                        sections.append(f"### FTS: {item_title}\n{item_snippet[:600]}")
            elif logger:
                logger.debug("FTS5 fallback skipped: registry YAML not found at %s", registry_path)
        except Exception as fts_err:
            if logger:
                logger.warning("FTS5 knowledge retrieval failed: %s", fts_err)

    return "\n\n".join(sections)


def _coerce_dict(raw, default=None):
    """Coerce an LLM JSON payload into a dict.

    Prompted models sometimes reply with a JSON scalar (e.g. a JSON-encoded
    string like ``"general_chat"``) or an array instead of the object the
    code expects. ``json.loads`` of a JSON string yields a Python ``str``,
    and a later ``.get(...)`` call then raises ``AttributeError: 'str' object
    has no attribute 'get'``. This helper degrades gracefully: it returns
    ``default`` when the parsed value isn't a dict rather than crashing.
    """
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (list, tuple)) and len(raw) == 1 and isinstance(raw[0], dict):
        return raw[0]
    return default if default is not None else {}


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
            # Parse JSON from response. Guard against scalar/JSON-string
            # replies so a non-dict never leaks into the caller's .get() calls.
            result = _coerce_dict(json.loads(response.strip()), {"intent": "general_chat", "confidence": 0.3, "entities": {}})
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
    Only called for write-intents (add_asset, contribute_asset, log_minutes, create_distribution, create_beneficiary, create_class_beneficiary, remove_class_beneficiary, create_entity).
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
            result = _coerce_dict(json.loads(response.strip()), {"action_type": intent, "extracted": {}, "missing_required": [], "suggested_clarification": None})
            return result
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse action extractor response: {response[:200]}")
    except Exception as e:
        logger.error(f"Action extractor error: {type(e).__name__}: {e}")

    return {"action_type": intent, "extracted": {}, "missing_required": [], "suggested_clarification": None}


async def build_trust_context(user_id: str, trust_id: str, intent: str = "") -> dict:
    """
    Assemble the trust context for the AI: trust profile, deadlines,
    recent activity, beneficiaries, pending reviews.

    When intent is provided and is a lightweight knowledge/chat intent,
    skip the expensive MongoDB queries (beneficiaries, money summary,
    structure summary, vault, recent activity) that aren't needed for
    general questions. This saves 8+ DB round-trips per message.
    """
    # Intents that need full context — action-oriented or health-checking.
    LIGHTWEIGHT_INTENTS = {"ask_knowledge", "general_chat", "emergency"}
    lightweight = intent in LIGHTWEIGHT_INTENTS

    context = {}

    # 1. Trust profile (always needed — minimal cost)
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
            "trustees": _normalize_trustees(trust.get("trustees", "")),
        }
    else:
        context["trust"] = {"name": "Unknown Trust"}

    # 2. Defensibility Score (always included — one query, cheap)
    health = await db.health_score_snapshots.find_one(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0, "score_value": 1, "color": 1, "base_score": 1, "risk_penalty": 1},
        sort=[("calculated_at", -1)]
    )
    if health:
        context["health_score"] = {
            "total": health.get("score_value", 0),
            "color": health.get("color", "red"),
            "base_score": health.get("base_score", health.get("score_value", 0)),
            "risk_penalty": health.get("risk_penalty", 0),
        }
    else:
        context["health_score"] = {"total": 0, "color": "red", "base_score": 0, "risk_penalty": 0}

    # For lightweight intents (ask_knowledge, general_chat, emergency), skip
    # the expensive sections 3-11 below. The AI only needs trust profile +
    # health score for general knowledge questions. This saves 8+ DB queries.
    now = datetime.now(timezone.utc)

    if lightweight:
        context["upcoming_deadlines"] = []
        context["pending_items"] = []
        context["recent_activity"] = []
        context["beneficiaries"] = []
        context["class_beneficiaries"] = []
        context["entities"] = []
        context["tax_deadlines"] = []
        context["vault_documents"] = []
        context["money_summary"] = {}
        context["structure_summary"] = {}

        # Fetch trust document analysis — it's a single find_one query and is
        # essential for knowledge questions about the trust's own provisions.
        # Without this, the AI would say "I don't have your trust instrument"
        # even when it's fully analyzed in the DB. (CRITICAL-2 fix)
        analysis = await db.trust_document_analysis.find_one(
            {"trust_id": trust_id, "user_id": user_id, "status": "complete"},
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
                "beneficiary_names": fields.get("beneficiary_names", []),
            }
        else:
            context["trust_document"] = {}

        return context

    # 3. Upcoming deadlines (next 14 days)
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
        {"trust_id": trust_id, "user_id": user_id, "status": "active"},
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

    # 6c. Entities (Structures) — so the AI knows what structures exist
    entities = await db.entities.find(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0, "entity_id": 1, "name": 1, "entity_type": 1, "legal_name": 1,
         "governing_law": 1, "ein": 1, "formation_date": 1, "trustee_names": 1,
         "member_names": 1, "manager_names": 1}
    ).to_list(20)
    context["entities"] = [
        {
            "name": e.get("name", ""),
            "entity_type": e.get("entity_type", ""),
            "legal_name": e.get("legal_name", ""),
            "governing_law": e.get("governing_law", ""),
            "ein": e.get("ein"),
            "formation_date": e.get("formation_date"),
            "trustee_names": e.get("trustee_names", ""),
            "member_names": e.get("member_names", ""),
            "manager_names": e.get("manager_names", ""),
        }
        for e in entities
    ]

    # 7. Tax calendar
    upcoming_tax = await db.tax_calendar.find(
        {
            "trust_id": trust_id,
            "user_id": user_id,
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
        {"trust_id": trust_id, "user_id": user_id, "status": "complete"},
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
        {"trust_id": trust_id, "user_id": user_id},
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

    # 10. Money section summary (distributions, compensation, investments, transactions)
    context["money_summary"] = await _build_money_summary(trust_id, user_id, now)

    # 11. Structure section summary (entities, beneficiaries, schedule A, communications)
    context["structure_summary"] = await _build_structure_summary(trust_id, user_id)

    return context


async def _build_money_summary(trust_id: str, user_id: str, now: datetime) -> dict:
    """Build a concise summary of Money section data for the AI prompt.

    Returns counts and aggregate amounts — not raw records — to keep the prompt small.
    All queries filter by user_id.
    """
    year_start = datetime(now.year, 1, 1, tzinfo=now.tzinfo).isoformat()
    thirty_days_ago = (now - timedelta(days=30)).isoformat()

    # Distributions: total count + YTD amount
    dist_total = await db.distribution_records.count_documents(
        {"trust_id": trust_id, "user_id": user_id}
    )
    dist_ytd_docs = await db.distribution_records.find(
        {"trust_id": trust_id, "user_id": user_id, "date": {"$gte": year_start}},
        {"_id": 0, "amount": 1},
    ).to_list(1000)
    dist_ytd_total = sum(d.get("amount", 0) or 0 for d in dist_ytd_docs)

    # Compensation: active plans + YTD payments
    active_plans = await db.compensation_plans.count_documents(
        {"trust_id": trust_id, "user_id": user_id, "is_active": True}
    )
    ytd_payments = await db.compensation_payments.find(
        {"trust_id": trust_id, "user_id": user_id, "date": {"$gte": year_start}},
        {"_id": 0, "amount": 1},
    ).to_list(1000)
    comp_ytd_total = sum(p.get("amount", 0) or 0 for p in ytd_payments)

    # Investments: active count + total current value
    investments = await db.investments.find(
        {"trust_id": trust_id, "user_id": user_id, "is_active": True},
        {"_id": 0, "current_value": 1, "asset_type": 1},
    ).to_list(1000)
    inv_count = len(investments)
    inv_total_value = sum(i.get("current_value", 0) or 0 for i in investments)

    # Recent transactions: count in last 30 days
    recent_txn_count = await db.transactions.count_documents(
        {"trust_id": trust_id, "user_id": user_id, "date": {"$gte": thirty_days_ago}}
    )

    return {
        "distributions_total": dist_total,
        "distributions_ytd_amount": round(dist_ytd_total, 2),
        "compensation_active_plans": active_plans,
        "compensation_ytd_paid": round(comp_ytd_total, 2),
        "investments_count": inv_count,
        "investments_total_value": round(inv_total_value, 2),
        "recent_transactions_30d": recent_txn_count,
    }


async def _build_structure_summary(trust_id: str, user_id: str) -> dict:
    """Build a concise summary of Structure section data for the AI prompt.

    Returns counts and aggregate values — not raw records — to keep the prompt small.
    All queries filter by user_id.
    """
    # Entities: count + type breakdown
    entities = await db.entities.find(
        {"trust_id": trust_id, "user_id": user_id},
        {"_id": 0, "entity_type": 1},
    ).to_list(100)
    entity_count = len(entities)
    type_counts: dict[str, int] = {}
    for e in entities:
        etype = e.get("entity_type", "Unknown")
        type_counts[etype] = type_counts.get(etype, 0) + 1

    # Beneficiaries: active count (trust unit certificates)
    bene_count = await db.trust_unit_certificates.count_documents(
        {"trust_id": trust_id, "user_id": user_id, "status": "active"}
    )

    # Schedule A: active asset count + total value
    schedule_a_items = await db.schedule_a_items.find(
        {"trust_id": trust_id, "user_id": user_id, "status": "active"},
        {"_id": 0, "approximate_value": 1},
    ).to_list(1000)
    schedule_a_count = len(schedule_a_items)
    schedule_a_total = sum(a.get("approximate_value", 0) or 0 for a in schedule_a_items)

    # Communications: total count + pending action count
    comm_total = await db.communications.count_documents(
        {"trust_id": trust_id, "user_id": user_id}
    )
    comm_pending = await db.communications.count_documents(
        {"trust_id": trust_id, "user_id": user_id, "action_required": True, "action_completed": False}
    )

    return {
        "entity_count": entity_count,
        "entity_type_counts": type_counts,
        "beneficiary_count": bene_count,
        "schedule_a_asset_count": schedule_a_count,
        "schedule_a_total_value": round(schedule_a_total, 2),
        "communications_total": comm_total,
        "communications_pending_action": comm_pending,
    }


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
    "contribute_asset",
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
    - Returns False for casual/abstract questions (pricing, onboarding, general knowledge)
    """
    if intent in VAULT_RELEVANT_INTENTS:
        return True
    msg_lower = user_message.lower()
    return any(kw in msg_lower for kw in VAULT_TRIGGER_KEYWORDS)


# ---------------------------------------------------------------------------
# Field-level gating for trust document analysis
# ---------------------------------------------------------------------------
# Instead of always injecting ALL extracted fields, we scope which field
# groups are relevant based on intent + message keywords. This keeps the
# system prompt lean — a user asking about pricing doesn't need trustee
# powers and distribution rules burned into every turn.

# Field groups — each maps to keys in the trust_document context dict
TD_BASELINE_FIELDS = {"grantor", "trust_type"}
TD_DISTRIBUTION_FIELDS = {
    "distribution_standard", "distribution_standard_type",
    "distribution_article", "distribution_rules",
}
TD_AUTHORITY_FIELDS = {
    "trustee_powers", "trustee_powers_detail",
    "removal_provisions", "termination_rules",
}
TD_BENEFICIARY_FIELDS = {"beneficiary_names"}

# Intent → field groups (in addition to baseline)
TD_INTENT_FIELD_MAP: dict[str, set[str]] = {
    "evaluate_distribution": TD_BASELINE_FIELDS | TD_DISTRIBUTION_FIELDS | TD_BENEFICIARY_FIELDS,
    "create_distribution": TD_BASELINE_FIELDS | TD_DISTRIBUTION_FIELDS | TD_BENEFICIARY_FIELDS,
    "log_minutes": TD_BASELINE_FIELDS | TD_AUTHORITY_FIELDS,
    "create_beneficiary": TD_BASELINE_FIELDS | TD_BENEFICIARY_FIELDS | TD_DISTRIBUTION_FIELDS,
    "update_beneficiary": TD_BASELINE_FIELDS | TD_BENEFICIARY_FIELDS | TD_DISTRIBUTION_FIELDS,
    "review_document": TD_BASELINE_FIELDS | TD_DISTRIBUTION_FIELDS | TD_AUTHORITY_FIELDS | TD_BENEFICIARY_FIELDS,
    "upload_document": TD_BASELINE_FIELDS | TD_DISTRIBUTION_FIELDS | TD_AUTHORITY_FIELDS | TD_BENEFICIARY_FIELDS,
    "health_check": TD_BASELINE_FIELDS | TD_DISTRIBUTION_FIELDS | TD_AUTHORITY_FIELDS | TD_BENEFICIARY_FIELDS,
    "recommend_action": TD_BASELINE_FIELDS | TD_DISTRIBUTION_FIELDS | TD_AUTHORITY_FIELDS | TD_BENEFICIARY_FIELDS,
    "check_deadlines": TD_BASELINE_FIELDS,
    "add_asset": TD_BASELINE_FIELDS | TD_AUTHORITY_FIELDS,
    "contribute_asset": TD_BASELINE_FIELDS | TD_AUTHORITY_FIELDS,
}

# Keyword triggers for field-group expansion in general_chat
TD_DISTRIBUTION_KEYWORDS = [
    "distribution", "distribute", "pay", "payment", "withdraw",
    "discretionary", "mandatory", "income", "principal", "hem",
    "beneficiary request", "distribution request",
]
TD_AUTHORITY_KEYWORDS = [
    "power", "authority", "trustee power", "removal", "remove trustee",
    "terminate", "termination", "amend", "amendment",
]
TD_BENEFICIARY_KEYWORDS = [
    "beneficiary", "beneficiaries", "heir", "remainder",
]


def _get_trust_doc_scope(intent: str, user_message: str) -> set[str] | None:
    """Determine which trust document fields to include in the prompt.

    Returns a set of field names, or None to include everything
    (used when vault context is fully relevant).
    """
    # When the vault gate is open, include all fields
    if _should_include_vault_context(intent, user_message):
        return None  # None = include everything

    # Otherwise, scope to baseline + keyword-matched groups
    fields = set(TD_BASELINE_FIELDS)
    msg_lower = user_message.lower()

    if any(kw in msg_lower for kw in TD_DISTRIBUTION_KEYWORDS):
        fields |= TD_DISTRIBUTION_FIELDS
    if any(kw in msg_lower for kw in TD_AUTHORITY_KEYWORDS):
        fields |= TD_AUTHORITY_FIELDS
    if any(kw in msg_lower for kw in TD_BENEFICIARY_KEYWORDS):
        fields |= TD_BENEFICIARY_FIELDS

    # Intent-specific expansion even when vault gate is closed
    intent_fields = TD_INTENT_FIELD_MAP.get(intent)
    if intent_fields:
        fields |= intent_fields

    return fields


def _format_distribution_rules(dist_rules: dict, td_lines: list) -> None:
    """Append distribution-rule lines to td_lines when present."""
    if not dist_rules:
        return
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


def _format_trustee_powers_detail(powers_detail: dict, td_lines: list) -> None:
    """Append trustee-power detail lines to td_lines when present."""
    if not powers_detail:
        return
    if powers_detail.get("investment_powers"):
        td_lines.append(f"Investment Powers: {powers_detail['investment_powers']}")
    if powers_detail.get("discretion_powers"):
        td_lines.append(f"Discretion Powers: {powers_detail['discretion_powers']}")
    if powers_detail.get("spendthrift_provisions"):
        td_lines.append(f"Spendthrift Provisions: {powers_detail['spendthrift_provisions']}")


def _format_trust_doc_analysis(trust_document: dict, doc_scope: set[str] | None = None) -> str | None:
    """Format the AI-extracted trust document analysis section (Tier 1).

    Args:
        doc_scope: Set of field names to include, or None to include everything.
    """
    def _in_scope(field: str) -> bool:
        return doc_scope is None or field in doc_scope

    td_lines = ["## Trust Document Analysis (AI-Extracted)"]
    if _in_scope("grantor") and trust_document.get("grantor"):
        td_lines.append(f"Grantor: {trust_document['grantor']}")
    if _in_scope("trust_type") and trust_document.get("trust_type"):
        td_lines.append(f"Trust Type: {trust_document['trust_type']}")
    if _in_scope("distribution_standard") and trust_document.get("distribution_standard"):
        td_lines.append(f"Distribution Standard: {trust_document['distribution_standard']}")
    if _in_scope("distribution_standard") and trust_document.get("distribution_standard_type"):
        td_lines.append(f"Distribution Standard Type: {trust_document['distribution_standard_type']}")
    if _in_scope("distribution_standard") and trust_document.get("distribution_article"):
        td_lines.append(f"Distribution Article: {trust_document['distribution_article']}")
    if _in_scope("beneficiary_names") and trust_document.get("beneficiary_names"):
        td_lines.append(f"Named Beneficiaries: {', '.join(trust_document['beneficiary_names'])}")
    if _in_scope("removal_provisions") and trust_document.get("removal_provisions"):
        td_lines.append(f"Trustee Removal: {trust_document['removal_provisions']}")
    if _in_scope("termination_rules") and trust_document.get("termination_rules"):
        td_lines.append(f"Termination Rules: {trust_document['termination_rules']}")

    if _in_scope("distribution_rules"):
        _format_distribution_rules(trust_document.get("distribution_rules", {}), td_lines)

    if _in_scope("trustee_powers"):
        powers = trust_document.get("trustee_powers", [])
        if powers:
            td_lines.append("Trustee Powers:")
            for p in powers[:10]:
                td_lines.append(f"  - {p.get('power', '')} ({p.get('article', '')})")

    if _in_scope("trustee_powers_detail"):
        _format_trustee_powers_detail(trust_document.get("trustee_powers_detail", {}), td_lines)

    return "\n".join(td_lines)


def _format_vault_doc_list(vault_docs: list) -> str | None:
    """Format the vault document metadata section (Tier 2)."""
    if not vault_docs:
        return None
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
    return "\n".join(vault_lines)


def _format_vault_context(vault_docs: list, trust_document: dict | None, doc_scope: set[str] | None = None) -> str:
    """Format vault document metadata + trust document analysis into a prompt section.

    Tier 1: Trust document analysis (included when available, scoped by doc_scope).
    Tier 2: Vault document list (titles, categories, descriptions — no file content).

    Args:
        doc_scope: Set of field names to include, or None to include everything.
                   Used for field-level gating to avoid bloating the prompt with
                   irrelevant trust document details.
    """
    sections = []

    # --- Tier 1: AI-extracted trust document analysis (field-scoped) ---
    if trust_document:
        td_section = _format_trust_doc_analysis(trust_document, doc_scope)
        if td_section:
            sections.append(td_section)

    # --- Tier 2: Vault document metadata ---
    vault_section = _format_vault_doc_list(vault_docs)
    if vault_section:
        sections.append(vault_section)

    return "\n\n".join(sections) if sections else ""


# ---------------------------------------------------------------------------
# Compact context formatters — replace verbose json.dumps(indent=2) with
# brief text summaries to reduce system prompt token count.
# ---------------------------------------------------------------------------

def _fmt_deadlines(items: list) -> str:
    """Format upcoming deadlines as brief one-liners."""
    if not items:
        return "None"
    return "\n".join(
        f"- {d.get('type','task')} due {d.get('due_date','')}: {d.get('description','')}"
        for d in items
    )


def _fmt_pending(items: list) -> str:
    """Format pending items as brief one-liners."""
    if not items:
        return "None"
    lines = []
    for item in items:
        due = item.get("due_date", item.get("date", ""))
        lines.append(f"- {item.get('type','')}: {item.get('summary','')} ({due})")
    return "\n".join(lines)


def _fmt_activity(items: list) -> str:
    """Format recent activity as brief one-liners."""
    if not items:
        return "None"
    return "\n".join(
        f"- {a.get('label','')} ({a.get('date','')})"
        for a in items
    )


def _fmt_beneficiaries(items: list) -> str:
    """Format active beneficiaries as brief one-liners."""
    if not items:
        return "None"
    return "\n".join(
        f"- {b.get('name','')}: {b.get('units',0)} units"
        for b in items
    )


def _fmt_class_beneficiaries(items: list) -> str:
    """Format class beneficiaries as brief one-liners."""
    if not items:
        return "None"
    return "\n".join(
        f"- {cb.get('label', cb.get('class_type',''))}: {cb.get('percentage',0)}% — {cb.get('description','')}"
        for cb in items
    )


def _fmt_benevolence_policy(policy: Optional[dict], summary: Optional[dict]) -> str:
    """Format benevolence policy context for the AI assistant."""
    if not policy:
        return "No benevolence policy on file."
    lines = []
    v = policy.get("current_version", {})
    lines.append(f"- Policy Status: {policy.get('current_version_status', 'unknown')} (version {v.get('version_label', '?')})")
    lines.append(f"- Charitable Class: {v.get('charitable_class', 'Not specified')}")
    if v.get("per_recipient_annual_limit"):
        lines.append(f"- Per-Recipient Annual Limit: ${v['per_recipient_annual_limit']:,.2f}")
    if v.get("approval_threshold"):
        lines.append(f"- Approval Threshold: ${v['approval_threshold']:,.2f}")
    ats = v.get("assistance_types", [])
    if ats:
        allowed = [a for a in ats if a.get("is_allowed")]
        excluded = [a for a in ats if not a.get("is_allowed")]
        if allowed:
            lines.append(f"- Allowed Types: {', '.join(a.get('purpose','') for a in allowed)}")
        if excluded:
            lines.append(f"- Excluded Types: {', '.join(a.get('purpose','') for a in excluded)}")
    if summary:
        lines.append(f"- Records: {summary.get('total_count', 0)} grants, ${summary.get('total_amount', 0):,.2f} total")
    return "\n".join(lines)


def _fmt_entities(items: list) -> str:
    """Format entities as brief one-liners."""
    if not items:
        return "None"
    lines = []
    for e in items:
        parts = [e.get("name", "")]
        if e.get("entity_type"):
            parts.append(f"({e['entity_type']})")
        if e.get("governing_law"):
            parts.append(f"[{e['governing_law']}]")
        if e.get("ein"):
            parts.append(f"EIN:{e['ein']}")
        lines.append(f"- {' '.join(parts)}")
    return "\n".join(lines)


def _fmt_tax_deadlines(items: list) -> str:
    """Format tax deadlines as brief one-liners."""
    if not items:
        return "None"
    return "\n".join(
        f"- {t.get('filing','')} due {t.get('due_date','')}"
        for t in items
    )


def _fmt_history(history: list) -> str:
    """Format conversation history as brief text (truncated)."""
    if not history:
        return "None"
    lines = []
    for m in history[-5:]:
        role = m.get("role", "")
        content = m.get("content", "")
        if len(content) > 200:
            content = content[:200] + "..."
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _build_vault_section(ctx: dict, intent: str, user_message: str) -> str:
    """Compute the vault/trust-document prompt section shared by both response paths."""
    vault_section = ""
    trust_doc = ctx.get("trust_document")
    doc_scope = _get_trust_doc_scope(intent, user_message)
    if _should_include_vault_context(intent, user_message):
        vault_docs = ctx.get("vault_documents", [])
        vault_section = _format_vault_context(vault_docs, trust_doc, doc_scope=None)
    elif trust_doc:
        # Include scoped trust document analysis for baseline awareness.
        vault_section = _format_vault_context([], trust_doc, doc_scope=doc_scope)
    return vault_section


# --- Trust-type-aware guidance (#1) ---
# Maps the trust profile's trust_type field to the corresponding knowledge file,
# then extracts the "Key Governance Requirements" and "Distribution Rules" sections
# as a brief preamble so the AI proactively applies type-specific guidance.

_TRUST_TYPE_FILE_MAP = {
    "revocable": "17-revocable-living-trust",
    "revocable living": "17-revocable-living-trust",
    "living": "17-revocable-living-trust",
    "revocable living trust": "17-revocable-living-trust",
    "irrevocable": "17-irrevocable-trust-general",
    "irrevocable trust": "17-irrevocable-trust-general",
    "ilit": "17-irrevocable-life-insurance-trust",
    "life insurance": "17-irrevocable-life-insurance-trust",
    "insurance trust": "17-irrevocable-life-insurance-trust",
    "dynasty": "17-dynasty-trust",
    "crt": "17-charitable-remainder-trust",
    "charitable remainder": "17-charitable-remainder-trust",
    "clt": "17-charitable-lead-trust",
    "charitable lead": "17-charitable-lead-trust",
    "special needs": "17-special-needs-trust",
    "supplemental needs": "17-special-needs-trust",
    "snt": "17-special-needs-trust",
    "spendthrift": "17-spendthrift-trust",
    "asset protection": "17-asset-protection-trust",
    "dapt": "17-asset-protection-trust",
    "blind": "17-blind-trust",
    "land trust": "17-land-trust",
    "qtip": "17-qtip-trust",
    "generation skipping": "17-generation-skipping-trust",
    "gst": "17-generation-skipping-trust",
    "bypass": "17-bypass-trust",
    "credit shelter": "17-bypass-trust",
    "a-b": "17-bypass-trust",
    "grat": "17-grat",
    "grantor retained annuity": "17-grat",
    "qprt": "17-qualified-personal-residence-trust",
    "personal residence": "17-qualified-personal-residence-trust",
    "testamentary": "17-testamentary-trust",
    "totten": "17-totten-trust",
    "marital": "17-marital-deduction-trust",
    "marital deduction": "17-marital-deduction-trust",
    "minor": "17-minors-trust",
    "2503(c)": "17-minors-trust",
    "minors trust": "17-minors-trust",
}


def _build_trust_type_guidance(trust_type: str) -> str:
    """Extract a brief trust-type-specific guidance section from the knowledge base.

    Looks up the trust's type in the knowledge file map, then pulls the
    'Key Governance Requirements' and 'Distribution Rules' sections as a
    concise preamble (max 1500 chars). This lets the AI proactively apply
    type-specific guidance without the user asking about it.
    """
    if not trust_type:
        return ""

    type_lower = trust_type.lower().strip()
    kb = get_knowledge_base()

    # Try exact match, then partial match (keyword must be at least 4 chars
    # and only match keyword-in-type_lower, not the reverse, to avoid
    # "blind" matching "blindly" or "test" matching "testamentary" incorrectly)
    file_key = _TRUST_TYPE_FILE_MAP.get(type_lower)
    if not file_key:
        for keyword, key in _TRUST_TYPE_FILE_MAP.items():
            if len(keyword) >= 4 and keyword in type_lower:
                file_key = key
                break
    if not file_key or file_key not in kb:
        return ""

    content = kb[file_key]
    lines = content.split("\n")
    preamble_lines = [f"## Trust Type Guidance ({trust_type})"]
    in_section = False
    char_count = 0
    for line in lines:
        if line.startswith("## Key Governance Requirements"):
            in_section = True
            preamble_lines.append(line)
            char_count += len(line)
            continue
        elif line.startswith("## Distribution Rules"):
            in_section = True
            preamble_lines.append(line)
            char_count += len(line)
            continue
        elif line.startswith("## ") and in_section:
            # Hit the next section after Distribution Rules — stop
            break
        if in_section:
            preamble_lines.append(line)
            char_count += len(line)
            if char_count > 1200:
                preamble_lines.append("  (truncated)")
                break

    result = "\n".join(preamble_lines)
    return result[:1500]


def _build_system_prompt(
    intent: str,
    user_message: str,
    trust_context: dict,
    conversation_history: list,
    *,
    stream_mode: bool = False,
) -> str:
    """Assemble the full system prompt shared by generate_response and generate_response_stream.

    Args:
        stream_mode: When True, emit streaming-mode instructions (natural markdown, no JSON).
    """
    action_def = get_action(intent) or ACTION_REGISTRY.get("general_chat", {})
    requires_write = action_def.get("requires_write", False)
    needs_confirm = action_def.get("confirmation_required", False)
    action_type_value = action_def.get("type", f"{intent}_preview")

    ctx = trust_context
    trust_info = ctx.get("trust", {})

    _money = ctx.get("money_summary", {})
    _struct = ctx.get("structure_summary", {})
    _entity_types = ", ".join(f"{v} {k}" for k, v in _struct.get("entity_type_counts", {}).items()) or "None"

    knowledge_context = _format_knowledge_context(user_message=user_message, intent=intent)
    vault_section = _build_vault_section(ctx, intent, user_message)
    trust_type_guidance = _build_trust_type_guidance(trust_info.get("type", ""))

    health = ctx.get("health_score", {})

    # --- Assemble system prompt from split constitution ---
    # Core is always loaded (~3K chars).
    # Actions section loaded for action intents (~5K chars).
    # Escalation section loaded for any intent touching fiduciary decisions (~2K chars).
    # Uses module-level ACTION_INTENTS and ESCALATION_INTENTS (unified). (MEDIUM-2 fix)

    system_prompt_base = CHAT_SYSTEM_CORE
    if intent in ACTION_INTENTS:
        system_prompt_base += "\n\n" + CHAT_SYSTEM_ACTIONS
    if intent in ESCALATION_INTENTS:
        system_prompt_base += "\n\n" + CHAT_SYSTEM_ESCALATION

    # Distribution evaluation guidance (only for distribution intents)
    if intent in ("create_distribution", "evaluate_distribution"):
        system_prompt_base += """

## Distribution Evaluation Protocol
When a user asks about evaluating a distribution request, help them evaluate it systematically:
1. Reference the trust's distribution standard (HEMS, sole discretion, etc.) from the trust document analysis
2. Check whether the request falls within the trust's permitted distribution categories
3. Reference past distribution patterns to ensure equitable treatment
4. Note any quantitative parameters mentioned in the trust document (e.g., tuition coverage limits, reasonable amounts)
5. Provide a clear recommendation: approved, denied, or needs further review
6. Draft a beneficiary notification if the distribution is approved

When evaluating, always cite the specific trust document language and article references you're basing the recommendation on.
"""

    shared_header = f"""{system_prompt_base}

## Current Trust Context
Trust: {trust_info.get('name', 'Unknown')}
Type: {trust_info.get('type', 'Not specified')}
Jurisdiction: {trust_info.get('jurisdiction', 'Not specified')}
State: {trust_info.get('state_code', 'Not specified')}
Establishment Date: {trust_info.get('start_date', 'Not specified')}
Beneficiary Standard: {trust_info.get('beneficiary_standard', 'Not specified')}
Trustees: {trust_info.get('trustees', 'Not specified')}
Defensibility Score: {health.get('total', 0)}/{health.get('max_score', 100)} ({health.get('color', 'red')})

{vault_section}

{trust_type_guidance}

## Upcoming Deadlines (next 14 days)
{_fmt_deadlines(ctx.get('upcoming_deadlines', []))}

## Pending Items
{_fmt_pending(ctx.get('pending_items', []))}

## Recent Activity (last 30 days)
{_fmt_activity(ctx.get('recent_activity', []))}

## Active Beneficiaries
{_fmt_beneficiaries(ctx.get('beneficiaries', []))}

## Class Beneficiaries
{_fmt_class_beneficiaries(ctx.get('class_beneficiaries', []))}

## Benevolence Policy
{_fmt_benevolence_policy(ctx.get('benevolence_policy', None), ctx.get('benevolence_summary', None))}

## Entities (Structures)
{_fmt_entities(ctx.get('entities', []))}

## Tax Deadlines
{_fmt_tax_deadlines(ctx.get('tax_deadlines', []))}

## Money Summary
Distributions: {_money.get('distributions_total', 0)} total, ${_money.get('distributions_ytd_amount', 0):,.2f} this year
Compensation: {_money.get('compensation_active_plans', 0)} active plans, ${_money.get('compensation_ytd_paid', 0):,.2f} paid YTD
Investments: {_money.get('investments_count', 0)} assets, ${_money.get('investments_total_value', 0):,.2f} total value
Recent transactions: {_money.get('recent_transactions_30d', 0)} in last 30 days

## Structure Summary
Entities: {_struct.get('entity_count', 0)} ({_entity_types})
Beneficiaries: {_struct.get('beneficiary_count', 0)}
Schedule A: {_struct.get('schedule_a_asset_count', 0)} assets, ${_struct.get('schedule_a_total_value', 0):,.2f} total
Communications: {_struct.get('communications_total', 0)} recorded, {_struct.get('communications_pending_action', 0)} pending action

## Knowledge Base
{knowledge_context[:4500] if knowledge_context else "No knowledge base available."}

## Conversation History (recent)
{_fmt_history(conversation_history)}

## Current Intent
Intent: {intent}
Requires write: {requires_write}
"""

    if stream_mode:
        return shared_header + """
Respond as the Trust Assistant directly to the user. Write your response in clear, well-formatted markdown. Use headings (##), bullet points, bold text, and numbered lists where appropriate. Be conversational but professional.

When referencing trust document details, cite the specific article/section if available
(e.g., "According to your trust instrument, Article 4, Section 4.2...").
If vault documents are listed, reference them by title when relevant to the user's question.

If you are proposing an action (distribution, minutes, adding a beneficiary, etc.), describe what you would do in your response text. The system will generate a separate action card for the user to review.

Do NOT wrap your response in JSON. Do NOT include code blocks around your entire response. Write naturally.
"""

    return (
        shared_header
        + f'Confirmation required: {needs_confirm}\n\n'
        + 'Respond as the Trust Assistant. Include:\n'
        + '1. "What I\'m basing this on" — cite specific data from the context above\n'
        + '2. "What I don\'t know" — call out information gaps\n'
        + "3. Caveat language for any action proposals\n\n"
        + "When referencing trust document details, cite the specific article/section if available\n"
        + '(e.g., "According to your trust instrument, Article 4, Section 4.2...").\n'
        + "If vault documents are listed, reference them by title when relevant to the user's question.\n\n"
        + "Format your response as JSON:\n"
        + "{\n"
        + '  "message": "Your main response text to the user",\n'
        + '  "action_card": {\n'
        + f'    "type": "{action_type_value}" if requires_write else null,\n'
        + "    \"data\": {...extracted action fields},\n"
        + f'    "requires_confirmation": {str(needs_confirm).lower()}\n'
        + "  } or null,\n"
        + '  "citation_note": "What I\'m basing this on...",\n'
        + '  "unknown_note": "Trust-specific data gaps only (not domain knowledge gaps)...",\n'
        + '  "caveat": "You should review this with your legal or tax professional..."\n'
        + "}\n"
    )


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

    system_prompt = _build_system_prompt(
        intent, user_message, trust_context, conversation_history, stream_mode=False
    )
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

            # Try to parse as JSON. Guard against scalar replies (a JSON
            # string or list) so a non-dict can never reach ai_response.get().
            try:
                result = _coerce_dict(json.loads(clean_text), {
                    "message": response_text.strip(),
                    "action_card": None,
                    "citation_note": None,
                    "unknown_note": None,
                    "caveat": None,
                })
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

    system_prompt = _build_system_prompt(
        intent, user_message, trust_context, conversation_history, stream_mode=True
    )
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
            "type": action_def.get("type", f"{intent}_preview"),
            "data": extracted.get("extracted", {}),
            "requires_confirmation": action_def.get("confirmation_required", True),
        }

    return None


def _money_citations(money: dict) -> list:
    """Citation lines for the money section summary."""
    out = []
    if not money:
        return out
    if money.get("distributions_total", 0) > 0:
        out.append(f"Distributions: {money['distributions_total']} total, ${money.get('distributions_ytd_amount', 0):,.2f} YTD")
    if money.get("compensation_active_plans", 0) > 0:
        out.append(f"Compensation: {money['compensation_active_plans']} active plan(s), ${money.get('compensation_ytd_paid', 0):,.2f} paid YTD")
    if money.get("investments_count", 0) > 0:
        out.append(f"Investments: {money['investments_count']} holding(s), ${money.get('investments_total_value', 0):,.2f} total")
    if money.get("recent_transactions_30d", 0) > 0:
        out.append(f"Transactions: {money['recent_transactions_30d']} in last 30 days")
    return out


def _structure_citations(struct: dict) -> list:
    """Citation lines for the structure section summary."""
    out = []
    if not struct:
        return out
    if struct.get("entity_count", 0) > 0:
        out.append(f"Entities: {struct['entity_count']} structure(s)")
    if struct.get("schedule_a_asset_count", 0) > 0:
        out.append(f"Schedule A: {struct['schedule_a_asset_count']} asset(s), ${struct.get('schedule_a_total_value', 0):,.2f} total")
    if struct.get("communications_total", 0) > 0:
        out.append(f"Communications: {struct['communications_total']} recorded, {struct.get('communications_pending_action', 0)} pending action")
    return out


def _trust_doc_citations(trust_doc: dict) -> list:
    """Citation lines for the AI-extracted trust document analysis."""
    out = []
    if not trust_doc:
        return out
    if trust_doc.get("distribution_standard"):
        out.append(f"Trust instrument: {trust_doc.get('distribution_standard_type', 'distribution standard')} standard")
    if trust_doc.get("distribution_article"):
        out.append(f"Distribution provisions: {trust_doc['distribution_article']}")
    if trust_doc.get("beneficiary_names"):
        out.append(f"Named beneficiaries from trust instrument: {', '.join(trust_doc['beneficiary_names'][:5])}")
    return out


def _vault_citations(vault_docs: list, intent: str, user_message: str) -> list:
    """Citation lines for vault documents, only when vault context was relevant."""
    out = []
    if not vault_docs:
        return out
    if not _should_include_vault_context(intent, user_message):
        return out
    doc_titles = [d.get("title", "") for d in vault_docs if d.get("title")]
    if doc_titles:
        out.append(f"Vault documents referenced: {', '.join(doc_titles[:5])}")
    return out


def _money_unknowns(money: dict) -> list:
    """Unknown/gap lines for the money section summary."""
    if not money:
        return ["Money section data unavailable"]
    out = []
    if money.get("investments_count", 0) == 0:
        out.append("No investment holdings tracked — portfolio allocation unknown")
    if money.get("compensation_active_plans", 0) == 0:
        out.append("No active trustee compensation plan on file")
    return out


def _structure_unknowns(struct: dict) -> list:
    """Unknown/gap lines for the structure section summary."""
    if not struct:
        return ["Structure section data unavailable"]
    out = []
    if struct.get("schedule_a_asset_count", 0) == 0:
        out.append("No Schedule A assets recorded — trust inventory unknown")
    if struct.get("communications_pending_action", 0) > 0:
        out.append(f"{struct['communications_pending_action']} communication(s) with pending actions")
    return out


def build_citation_notes(trust_context: dict, intent: str, user_message: str = "") -> tuple:
    """
    Build citation_note and unknown_note from the trust context.
    Returns (citation_note, unknown_note).
    """
    ctx = trust_context
    citations: list = []
    unknowns: list = []

    trust_info = ctx.get("trust", {})
    if trust_info.get("name") and trust_info.get("name") != "Unknown Trust":
        citations.append(f"Trust profile for {trust_info['name']}")

    health = ctx.get("health_score", {})
    if health.get("total", 0) > 0:
        citations.append(f"Defensibility score: {health['total']}/{health.get('max_score', 100)}")

    deadlines = ctx.get("upcoming_deadlines", [])
    if deadlines:
        citations.append(f"{len(deadlines)} upcoming deadline(s) in the next 14 days")

    beneficiaries = ctx.get("beneficiaries", [])
    if beneficiaries:
        citations.append(f"{len(beneficiaries)} active beneficiary record(s)")

    money = ctx.get("money_summary", {})
    citations.extend(_money_citations(money))

    struct = ctx.get("structure_summary", {})
    citations.extend(_structure_citations(struct))

    trust_doc = ctx.get("trust_document", {})
    citations.extend(_trust_doc_citations(trust_doc))

    citations.extend(_vault_citations(
        ctx.get("vault_documents", []), intent, user_message
    ))

    # Unknowns
    if not trust_info.get("jurisdiction"):
        unknowns.append("Trust jurisdiction is not specified")
    if not trust_info.get("beneficiary_standard") and not trust_doc.get("distribution_standard"):
        unknowns.append("Distribution standard (HEMS vs discretionary) is not specified")
    if health.get("total", 0) == 0:
        unknowns.append("No defensibility score has been calculated yet")
    if not trust_doc:
        unknowns.append("No trust instrument has been uploaded and analyzed yet")

    unknowns.extend(_money_unknowns(money))
    unknowns.extend(_structure_unknowns(struct))

    return (
        "; ".join(citations) if citations else None,
        "; ".join(unknowns) if unknowns else None,
    )