"""
Deterministic approval handling for the Trust Assistant.

Root cause this fixes: chat history sent to the LLM strips action cards
(role + content only), so when a user types "yes" / "approve it" the model
cannot see there was an action card awaiting approval — it re-asks the same
question. The approve BUTTON path (confirm endpoint) always worked; the
TEXT path silently fell into general_chat.

This module intercepts approval-shaped messages BEFORE intent
classification. If the latest assistant message has a pending action card,
the approval is executed directly through the same execution pipeline the
button uses. Deterministic, no LLM in the loop, cannot re-ask.
"""
import re
import logging
from datetime import datetime, timezone

# Lazy DB import — lets the regex layer be tested without MONGO_URL.
db = None
def _get_db():
    global db
    if db is None:
        from database import db as _db
        db = _db
    return db

logger = logging.getLogger(__name__)

# Words/phrases that constitute approval when an action card is pending.
_APPROVE_PATTERNS = [
    r"^\s*yes\s*[!,.]*\s*$",
    r"^\s*yep\s*[!,.]*\s*$",
    r"^\s*yeah\s*[!,.]*\s*$",
    r"^\s*yup\s*[!,.]*\s*$",
    r"^\s*y\s*$",
    r"^\s*sure\s*[!,.]*\s*$",
    r"^\s*ok(?:ay)?\s*[!,.]*\s*$",
    r"^\s*go(?: ahead)?\s*[!,.]*\s*$",
    r"^\s*do\s+it\s*[!.]*\s*$",
    r"^\s*ok(?:ay)?,?\s+do\s+it\s*[!.]*\s*$",
    r"^\s*yes,?\s+please\s*[!.]*\s*$",
    r"^\s*approved?\s*[!.]*\s*$",
    r"^\s*i\s+approve(?:d)?\s*[!.]*\s*$",
    r"^\s*please\s+do\s*[!.]*\s*$",
    r"^\s*proceed\s*[!.]*\s*$",
    r"^\s*confirm\s*[!.]*\s*$",
    r"^\s*confirmed\s*[!.]*\s*$",
    r"^\s*sounds\s+good\s*[!.]*\s*$",
    r"^\s*that\s+works\s*[!.]*\s*$",
    r"^\s*looks\s+good\s*[!.]*\s*$",
    r"^\s*looks\s+good\s+to\s+me\s*[!.]*\s*$",
    r"^\s*do\s+that\s*[!.]*\s*$",
    r"^\s*add\s+(?:it|him|her|them)\s*[!.]*\s*$",
    r"^\s*create\s+(?:it|him|her|them)\s*[!.]*\s*$",
    r"^\s*send\s+(?:it|him|her|them)\s*[!.]*\s*$",
    r"^\s*make\s+(?:it|him|her|them)\s*[!.]*\s*$",
    r"^\s*that's\s+(?:correct|right|fine)\s*[!.]*\s*$",
    r"^\s*correct\s*[!.]*\s*$",
    r"^\s*right\s*[!.]*\s*$",
    r"^\s*affirmative\s*[!.]*\s*$",
]
_APPROVE_RE = re.compile("|".join(_APPROVE_PATTERNS), re.IGNORECASE)

# Explicit rejections — never treated as approval.
_REJECT_PATTERNS = re.compile(
    r"^\s*(no|nope|nah|cancel|stop|wait|don'?t|do not|reject(?:ed)?|dismiss|"
    r"not\s+(?:yet|now)|hold\s+on)\s*[!,.]*\s*$",
    re.IGNORECASE,
)


def is_approval_message(message: str) -> bool:
    """True if the message text is an unambiguous approval."""
    if not message:
        return False
    return bool(_APPROVE_RE.match(message.strip()))


def is_rejection_message(message: str) -> bool:
    """True if the message text is an unambiguous rejection."""
    if not message:
        return False
    return bool(_REJECT_PATTERNS.match(message.strip()))


async def get_latest_pending_action(conversation_id: str, user_id: str):
    """
    Find the most recent assistant message with a pending action card.

    Returns (message_index, action_card_dict) or (None, None).
    """
    conv = await _get_db().chat_conversations.find_one(
        {"conversation_id": conversation_id, "user_id": user_id},
        {"_id": 0, "messages": 1},
    )
    if not conv:
        return None, None

    messages = conv.get("messages", [])
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if m.get("role") != "assistant":
            continue
        card = m.get("action_card")
        if card and card.get("confirmation_status") == "pending":
            return i, card
    return None, None


def _friendly_summary(card: dict) -> str:
    """One-line human summary of what a card creates, for confirmation text."""
    t = card.get("type", "")
    d = card.get("data", {}) or {}
    name = d.get("name") or d.get("beneficiary_name") or d.get("legal_name") or d.get("description") or ""
    label_map = {
        "entity": "entity",
        "beneficiary": "beneficiary",
        "class_beneficiary": "class beneficiary",
        "asset": "asset",
        "asset_update": "asset update",
        "minutes": "minutes",
        "distribution": "distribution",
        "transaction": "transaction",
        "investment": "investment",
        "task": "task",
        "compensation_plan": "compensation plan",
        "compensation_payment": "compensation payment",
        "document_upload": "vault upload",
        "certificate": "certificate email",
    }
    label = "action"
    for k, v in label_map.items():
        if k in t:
            label = v
            break
    return f"{label}{(': ' + str(name)) if name else ''}"


# ─────────────────────────────────────────────────────────────────────────────
# Reply-link coverage (council P0, 2026-10-23)
# ─────────────────────────────────────────────────────────────────────────────
# Every action type's success reply must carry a REAL link to the record it
# created. The route templates below were each verified to exist in
# frontend/src/App.js. A record type with no member-facing route is NOT
# given a fabricated one — it is named plainly ("<record type> <id>") so the
# member can ask support without chasing a 404.
#
# The link is built from the result envelope. Key precedence:
#   1. an explicit review_link on the result (handlers that know better)
#   2. the endpoint_type + record id, through the map below
#
# IMPORTANT: the minutes link is /minutes/{id} — the DETAIL route. The old
# /minutes/{id}/edit path has no frontend route and 404s (App.js defines
# /minutes/:minutesId only).
REPLY_LINK_ROUTES: dict[str, str] = {
    "minutes":                 "/minutes/{id}",
    "contribute_asset":        "/minutes/{id}",
    "distribution":            "/distributions",
    "distribution_cancel":     "/distributions",
    "asset":                   "/schedule-a",
    "asset_update":            "/schedule-a",
    "beneficiary":             "/beneficiaries?tab=beneficiaries",
    "beneficiary_update":      "/beneficiaries?tab=beneficiaries",
    "beneficiary_removal":     "/beneficiaries?tab=certificates",
    "send_certificate":        "/beneficiaries?tab=certificates",
    "class_beneficiary":       "/beneficiaries?tab=class",
    "class_beneficiary_removal": "/beneficiaries?tab=class",
    "document_upload":         "/vault",
    "compensation_plan":       "/compensation",
    "compensation_payment":    "/compensation",
    "investment":              "/investments",
    "task":                    "/calendar",
    "transaction":             "/transactions",
    "entity":                  "/structures?tab=entities",
    "settings_update":         "/settings",
    "alert_dismiss":           "/dashboard",
}

# Human labels for record types that have no member-facing route.
RECORD_TYPE_LABELS: dict[str, str] = {
    "minutes_records": "draft minutes",
    "minutes_templates": "minutes template",
    "schedule_a_items": "Schedule A asset",
    "distribution_records": "distribution",
    "trust_unit_certificates": "beneficiary certificate",
    "class_beneficiaries": "class beneficiary",
    "vault_documents": "vault document",
    "compensation_plans": "compensation plan",
    "compensation_payments": "compensation payment",
    "investments": "investment",
    "governance_tasks": "governance task",
    "transactions": "transaction",
    "entities": "entity",
    "chat_conversations": "conversation",
    "dismissed_insights": "governance alert",
}


def build_record_link(endpoint_type: str, result: dict) -> str:
    """
    Build the member-facing link (or a plain-language record reference) for
    a completed action.

    Returns "" only when there is genuinely nothing to reference. Never
    returns a route that does not exist in frontend/src/App.js.
    """
    explicit = (result.get("review_link") or "").strip()
    if explicit:
        return explicit

    rid = (
        result.get("record_id")
        or result.get("minutes_id")
        or result.get("schedule_a_id")
        or result.get("distribution_id")
        or result.get("certificate_id")
        or result.get("item_id")
        or result.get("payment_id")
        or result.get("plan_id")
        or result.get("task_id")
        or result.get("transaction_id")
        or result.get("entity_id")
        or result.get("doc_id")
        or result.get("investment_id")
        or result.get("class_beneficiary_id")
    )

    # A couple of actions have no record id but do have a meaningful target.
    if not rid and endpoint_type == "alert_dismiss":
        criterion = (result.get("criterion") or "").strip()
        if criterion:
            return "/dashboard"

    template = REPLY_LINK_ROUTES.get(endpoint_type)
    if template and rid:
        if "{id}" in template:
            return template.replace("{id}", str(rid))
        return template

    # No route for this type — name the record plainly instead of inventing
    # a URL that would 404.
    label = RECORD_TYPE_LABELS.get(endpoint_type, endpoint_type.replace("_", " "))
    if rid:
        return f"{label} {rid}"
    if endpoint_type:
        return label
    return ""


def build_success_message(summary: str, result: dict, endpoint_type: str = "") -> str:
    """
    Build the assistant's post-approval confirmation text.

    2026-10-23 (Jerel Kratt): the confirmation text never carried the link
    to the record that was just created, so the member could not find the
    draft ("there is no drafts tab", "nothing is showing anywhere"). Every
    successful action reply that carries a review_link now ends with the
    link, and any caveat (e.g. a substituted minutes type) is surfaced too.

    2026-10-23 council P0: the link is now derived for EVERY action type
    (not just the ones whose handler happened to set review_link), so a
    member who creates a task, transaction, entity, investment or vault
    document is told where it went. Types with no member-facing route are
    named plainly — no fabricated URLs.
    """
    text = f"Done — {summary} has been created."
    if summary.startswith("distribution"):
        text += " To finalize it, confirm solvency and recusal on the Distributions page."
    elif summary.startswith("minutes"):
        text += " It's saved as a draft — review and finalize on the Minutes page."

    link = build_record_link(endpoint_type, result)
    if link:
        if link.startswith("/"):
            text += f" Open it: {link}"
        else:
            # A plain-language record reference (no route exists for it).
            text += f" It was saved as {link}."
    caveat = (result.get("caveat") or "").strip()
    if caveat:
        text += f" Note: {caveat}"
    return text


async def handle_text_approval(
    conversation_id: str,
    message_index: int,
    action_card: dict,
    user_id: str,
) -> dict:
    """
    Execute a pending action card after text-based approval.

    Mirrors confirm_action(): sets status to approved, runs the same
    _execute_approved_action pipeline, stores the execution result, and
    returns an assistant confirmation message.
    """
    from routers.chat import _execute_approved_action

    conv = await _get_db().chat_conversations.find_one(
        {"conversation_id": conversation_id, "user_id": user_id},
        {"_id": 0, "trust_id": 1},
    )
    trust_id = conv.get("trust_id") if conv else None
    if not trust_id:
        return {
            "success": False,
            "message": "I couldn't find the trust this conversation belongs to. Please approve the action card with the Approve button instead.",
        }

    # Mark approved first (same as the button path)
    await _get_db().chat_conversations.update_one(
        {"conversation_id": conversation_id, "user_id": user_id},
        {"$set": {
            f"messages.{message_index}.action_card.confirmation_status": "approved",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }}
    )

    result = await _execute_approved_action(
        action_card=action_card,
        user_id=user_id,
        trust_id=trust_id,
    )

    await _get_db().chat_conversations.update_one(
        {"conversation_id": conversation_id, "user_id": user_id},
        {"$set": {
            f"messages.{message_index}.action_card.execution_result": result,
            f"messages.{message_index}.action_card.executed_at": datetime.now(timezone.utc).isoformat(),
        }}
    )

    summary = _friendly_summary(action_card)
    if result.get("success"):
        text = build_success_message(
            summary, result, result.get("endpoint_type", "")
        )
        return {"success": True, "message": text, "execution_result": result}
    else:
        err = result.get("error", "the system reported an error")
        # Roll the card back to pending so the user can retry or edit it.
        await _get_db().chat_conversations.update_one(
            {"conversation_id": conversation_id, "user_id": user_id},
            {"$set": {
                f"messages.{message_index}.action_card.confirmation_status": "pending",
            }}
        )
        return {
            "success": False,
            "message": f"I couldn't complete that action: {err}. The action card is still pending — you can edit it or try approving again.",
            "execution_result": result,
        }


async def handle_text_rejection(
    conversation_id: str,
    message_index: int,
    user_id: str,
) -> dict:
    """Mark a pending card rejected when the user declines by text."""
    await _get_db().chat_conversations.update_one(
        {"conversation_id": conversation_id, "user_id": user_id},
        {"$set": {
            f"messages.{message_index}.action_card.confirmation_status": "rejected",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }}
    )
    return {
        "success": True,
        "message": "Got it — I've discarded that action. Nothing was created. What would you like to do instead?",
    }