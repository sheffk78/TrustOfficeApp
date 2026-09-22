"""
Seed actions for the TrustOffice shared action layer.

Five launch actions (Jeff-approved list, 2026-09-21 — see
Kit/life/brands/TrustOffice/reports/agent-native-deepdive-2026-09-21.md):

  generate-minutes        write  trust-scoped  → wraps routers.minutes.create_minutes
  submit-distribution     write  trust-scoped  → wraps routers.distributions.create_distribution
  evaluate-distribution   read   trust-scoped  → pure read (solvency pre-check)
  book-consult            write  trust-agnostic → wraps routers.leads.capture_lead (booked-call)
  chat-assistant          read   trust-agnostic → wraps routers.chat.chat

Each handler is the single source of truth for its capability. The chat
agent's approval pipeline (routers/chat.py ACTION_EXECUTION_MAP) and the
HTTP surface (routers/actions.py) both land on these functions.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import BackgroundTasks

from action_layer import F, ActionContext, ActionError, action
from database import db

logger = logging.getLogger(__name__)

_TODAY = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d")  # noqa: E731


async def _user_doc(user_id: str) -> dict:
    from database import db as _db

    doc = await _db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not doc:
        doc = {"user_id": user_id, "email": "", "name": ""}
    return doc


# ==================== 1. generate-minutes ====================

_MINUTES_TYPES = [
    "annual", "quarterly", "compensation", "distribution", "solvency", "general",
]


@action(
    name="generate-minutes",
    description="Create a draft minutes record for a trust meeting. Saved as a draft for review on the Minutes page.",
    write=True,
    trust_scoped=True,
    fields=[
        F("minutes_type", "string", required=True, enum=_MINUTES_TYPES, description="Type of minutes"),
        F("meeting_date", "string", required=True, description="ISO date of the meeting (YYYY-MM-DD)"),
        F("participants", "list", required=True, description="Meeting participants (trustees)"),
        F("decisions", "list", required=True, description="Decisions or agenda items"),
    ],
)
async def generate_minutes(params: dict, ctx: ActionContext) -> dict:
    from routers.minutes import create_minutes as _create_minutes
    from models import MinutesCreate, MinutesType

    if not ctx.trust_id:
        raise ActionError("action_invalid", "trust_id is required for this action")
    trust_id = ctx.trust_id

    minutes_type_val = params.get("minutes_type", "general")
    try:
        minutes_type_enum = MinutesType(minutes_type_val)
    except ValueError:
        raise ActionError("action_params_invalid", f"Unsupported minutes type '{minutes_type_val}'")

    minutes_create = MinutesCreate(
        trust_id=trust_id,
        minutes_type=minutes_type_enum,
        meeting_date=params.get("meeting_date") or _TODAY(),
        participants_text=", ".join(params.get("participants") or []),
        decisions_text="; ".join(params.get("decisions") or []),
        status="draft",  # chat path convention: drafts, never auto-finalized
    )
    result = await _create_minutes(
        minutes=minutes_create,
        background_tasks=BackgroundTasks(),
        user=ctx.user,
    )
    # Minutes router only updates onboarding for finalized minutes; chat's
    # pipeline updates it for drafts too — keep that behavior here.
    try:
        from dependencies import auto_update_onboarding

        await auto_update_onboarding(ctx.user_id, trust_id)
    except Exception:  # noqa: BLE001 — onboarding refresh is best-effort
        pass
    return {
        "record_id": result.minutes_id,
        "status": "draft",
        "review_link": f"/minutes/{result.minutes_id}/edit",
        "message": "Draft minutes created — review and finalize on the Minutes page.",
    }


# ==================== 2. submit-distribution ====================

_PURPOSES = ["distribution", "compensation", "expense", "other"]


@action(
    name="submit-distribution",
    description="Create a distribution record to a beneficiary. Created in review status — solvency and recusal must be confirmed on the Distributions page before approval.",
    write=True,
    trust_scoped=True,
    fields=[
        F("beneficiary_name", "string", required=True, max_length=200, description="Name of the beneficiary receiving the distribution"),
        F("amount", "number", required=True, description="Distribution amount (must be >= 0)"),
        F("purpose", "string", required=False, enum=_PURPOSES, description="Purpose classification (defaults to 'other')"),
        F("date", "string", required=False, description="Distribution date (YYYY-MM-DD, defaults to today)"),
        F("from_account", "string", required=False, max_length=300, description="Optional source-account note"),
    ],
)
async def submit_distribution(params: dict, ctx: ActionContext) -> dict:
    from routers.distributions import create_distribution as _create_dist
    from models import DistributionCreate, PurposeClassification

    if not ctx.trust_id:
        raise ActionError("action_invalid", "trust_id is required for this action")
    trust_id = ctx.trust_id

    if float(params.get("amount", 0)) < 0:
        raise ActionError("action_params_invalid", "Amount must be >= 0")

    purpose = params.get("purpose") or "other"
    try:
        purpose_enum = PurposeClassification(purpose)
    except ValueError:
        raise ActionError("action_params_invalid", f"Unsupported purpose '{purpose}'")

    dist_create = DistributionCreate(
        trust_id=trust_id,
        beneficiary_name=params.get("beneficiary_name", "Unknown"),
        amount=float(params.get("amount", 0)),
        date=params.get("date") or _TODAY(),
        purpose_classification=purpose_enum,
        notes=params.get("from_account", ""),
        is_benevolence=False,
    )
    result = await _create_dist(
        dist=dist_create,
        background_tasks=BackgroundTasks(),
        user=ctx.user,
    )
    # Distribution is created in "review" status with solvency_confirmed=False;
    # both surfaces must direct the user to the solvency confirmation step.
    return {
        "record_id": result.distribution_id,
        "status": "review",
        "requires_solvency_confirmation": True,
        "solvency_link": f"/distributions?approve={result.distribution_id}",
        "message": "Distribution created in review status — confirm solvency and recusal on the Distributions page to approve it.",
    }


# ==================== 3. evaluate-distribution ====================


@action(
    name="evaluate-distribution",
    description="Read-only pre-flight check for a proposed distribution: verifies the beneficiary exists on the trust, reports lifetime distribution totals for them, and flags whether the trust is in read-only archive mode. Does NOT create anything.",
    write=False,
    trust_scoped=True,
    fields=[
        F("beneficiary_name", "string", required=True, max_length=200, description="Beneficiary to evaluate"),
        F("amount", "number", required=False, description="Proposed amount (informational, returned in the summary)"),
    ],
)
async def evaluate_distribution(params: dict, ctx: ActionContext) -> dict:
    import re as _re

    name = (params.get("beneficiary_name") or "").strip()
    if not name:
        raise ActionError("action_params_invalid", "beneficiary_name is required")

    trust = await db.trusts.find_one(
        {"trust_id": ctx.trust_id, "user_id": ctx.user_id}, {"_id": 0, "status": 1, "name": 1}
    )
    if not trust:
        raise ActionError("action_forbidden", "Trust not found for this user")

    # Beneficiaries live in trust_unit_certificates (active units only),
    # mirroring routers/distributions.py::_find_beneficiary_certificate.
    escaped = _re.escape(name)
    cert = await db.trust_unit_certificates.find_one(
        {
            "trust_id": ctx.trust_id,
            "user_id": ctx.user_id,
            "holder_name": {"$regex": f"^{escaped}$", "$options": "i"},
            "status": "active",
        },
        {"_id": 0, "holder_name": 1, "certificate_id": 1},
    )

    # Lifetime totals for this beneficiary (case-insensitive exact name).
    match_query = {
        "trust_id": ctx.trust_id,
        "user_id": ctx.user_id,
        "beneficiary_name": {"$regex": f"^{escaped}$", "$options": "i"},
        "is_benevolence": {"$ne": True},
    }
    pipeline = [
        {"$match": {**match_query, "amount": {"$type": ["double", "int", "long", "decimal"]}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}},
    ]
    cursor = db.distribution_records.aggregate(pipeline)
    agg = await cursor.to_list(1)
    lifetime_total = round(float(agg[0]["total"]), 2) if agg else 0.0
    distribution_count = agg[0]["count"] if agg else 0

    last = await db.distribution_records.find_one(
        match_query, {"_id": 0, "date": 1, "amount": 1}, sort=[("date", -1)]
    )

    read_only = trust.get("status") == "dissolved_archived"
    return {
        "trust_name": trust.get("name", "Unnamed Trust"),
        "trust_read_only": read_only,
        "known_beneficiary": bool(cert),
        "beneficiary_record": {"holder_name": cert.get("holder_name"), "certificate_id": cert.get("certificate_id")} if cert else None,
        "lifetime_total": lifetime_total,
        "distribution_count": distribution_count,
        "last_distribution": {"date": last.get("date"), "amount": last.get("amount")} if last else None,
        "proposed_amount": params.get("amount"),
        "note": (
            "Trust is dissolved/archived — it is read-only; new distributions are blocked."
            if read_only
            else "Pre-flight only: creating the distribution still requires solvency + recusal confirmation."
        ),
    }


# ==================== 4. book-consult ====================


@action(
    name="book-consult",
    description="Book a consultation: creates (or updates) the lead record with source 'booked-call' and pings Kenneth in Discord when a phone number is provided. Trust-agnostic — available on any surface.",
    write=True,
    trust_scoped=False,
    fields=[
        F("name", "string", required=True, max_length=200, description="Full name of the person booking"),
        F("email", "string", required=True, max_length=320, description="Email address"),
        F("phone", "string", required=False, max_length=32, description="Phone number (optional)"),
        F("notes", "string", required=False, max_length=2000, description="Optional context for the call"),
    ],
)
async def book_consult(params: dict, ctx: ActionContext) -> dict:
    from routers.leads import LeadCapture, capture_lead

    email = (params.get("email") or "").strip()
    name = (params.get("name") or "").strip()
    if not email or "@" not in email:
        raise ActionError("action_params_invalid", "A valid email is required to book a consult")
    if not name:
        raise ActionError("action_params_invalid", "name is required")

    lead = LeadCapture(
        name=name,
        email=email,
        phone=params.get("phone"),
        source="booked-call",
    )
    result = await capture_lead(lead)

    if params.get("notes"):
        try:
            lead_id = result.get("lead_id")
            if lead_id:
                await db.leads.update_one(
                    {"lead_id": lead_id},
                    {"$set": {"notes": params["notes"], "updated_at": datetime.now(timezone.utc).isoformat()}},
                )
        except Exception:  # noqa: BLE001 — notes are best-effort
            logger.warning("book-consult: failed to attach notes", exc_info=True)

    # Phone leads interrupt Kenneth (same contract as web-form capture).
    try:
        from discord_service import notify_new_lead

        await notify_new_lead(
            name=name,
            email=email,
            source="booked-call",
            lead_stage="new",
            phone=params.get("phone"),
            ping_on_phone=True,
        )
    except Exception:  # noqa: BLE001 — notification is best-effort
        logger.warning("book-consult: Discord notification failed", exc_info=True)

    return {
        "lead_id": result.get("lead_id"),
        "is_returning": result.get("is_returning", False),
        "source": "booked-call",
        "message": "Consultation booked — lead captured with source 'booked-call'.",
    }


# ==================== 5. chat-assistant ====================


@action(
    name="chat-assistant",
    description="Send a message to the Trust Assistant on behalf of the user and return its response (with any action cards). Trust-scoped when trust_id is provided; otherwise the caller's active trust is used.",
    write=False,
    trust_scoped=True,
    surfaces=("ui", "chat"),
    fields=[
        F("message", "string", required=True, max_length=5000, description="Message for the Trust Assistant"),
        F("conversation_id", "string", required=False, max_length=64, description="Existing conversation ID to continue"),
    ],
)
async def chat_assistant(params: dict, ctx: ActionContext) -> dict:
    from routers.chat import ChatRequest, chat as chat_endpoint

    request = ChatRequest(
        message=params.get("message", ""),
        conversation_id=params.get("conversation_id"),
        trust_id=ctx.trust_id,
    )
    response = await chat_endpoint(request, user=ctx.user)
    # Response is a ChatResponse pydantic model (or StreamingResponse for the
    # stream endpoint — chat() here is the non-streaming one).
    data = response.model_dump() if hasattr(response, "model_dump") else response
    return {"chat_response": data}