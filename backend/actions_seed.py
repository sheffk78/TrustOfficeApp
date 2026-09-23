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
# ==================== CHAT INTENT ACTIONS (2026-09-22 unification) ====================
#
# The Trust Assistant's approval pipeline (routers/chat.py) executes approved
# action cards through THESE handlers via action_layer.call_action() — the
# same code path the UI uses for its own actions. Each is registered @action
# with surfaces=("chat",): reachable from chat and in-process callers, but
# NOT listed/callable on the public POST /api/actions surface.
#
# Port provenance: bodies are mechanical ports of routers/chat.py _exec_* —
# (mapped_data, trust_id, user_id) -> (params, ctx); user docs backfilled via
# _user_doc() when the caller passes user=None; result envelopes unchanged so
# stored action cards keep rendering. Chat 'minutes' intent stays routed
# through routers/chat.py _exec_minutes (its cards carry participants_text /
# decisions_text and status=draft — a different shape from the seed
# generate-minutes action).
#
# Intent bridge consumed by chat._execute_approved_action:
ENDPOINT_TO_ACTION = {
    "distribution": "create-distribution",
    "asset": "add-schedule-a-asset",
    "asset_update": "update-schedule-a-asset",
    "contribute_asset": "contribute-property-to-trust",
    "beneficiary": "create-beneficiary",
    "beneficiary_update": "update-beneficiary",
    "beneficiary_removal": "remove-beneficiary",
    "send_certificate": "send-certificate",
    "distribution_cancel": "cancel-distribution",
    "document_upload": "upload-vault-document",
    "compensation_plan": "create-compensation-plan",
    "compensation_payment": "record-compensation-payment",
    "investment": "add-investment",
    "task": "create-governance-task",
    "transaction": "create-transaction",
    "entity": "create-entity",
    "settings_update": "update-trust-settings",
    "alert_dismiss": "dismiss-alert",
    "class_beneficiary": "add-class-beneficiary",
    "class_beneficiary_removal": "remove-class-beneficiary",
}

CHAT_INTENT_ACTIONS = ENDPOINT_TO_ACTION


def get_chat_intent_action(endpoint_type: str):
    """Map a chat ACTION_EXECUTION_MAP endpoint_type to its action name."""
    return CHAT_INTENT_ACTIONS.get(endpoint_type)


@action(
    name="create-distribution",
    description='Create a trust distribution for a beneficiary (saved in review status; solvency confirmation still required on the Distributions page).',
    write=True,
    trust_scoped=True,
    surfaces=("chat",),
    fields=[
        F("beneficiary_name", "string", required=True),
        F("amount", "number", required=True),
        F("date", "string", required=False),
        F("purpose_classification", "string", required=False),
        F("notes", "string", required=False),
    ],
)
async def _chat_distribution(params: dict, ctx: ActionContext) -> dict:
    """Chat intent 'distribution': distribution."""
    # Route through the real distribution router to ensure validation,
    # activity logging, onboarding updates, and email notifications.
    from routers.distributions import create_distribution as _create_dist
    from models import DistributionCreate, PurposeClassification
    from fastapi import BackgroundTasks

    purpose = params.pop("purpose_classification", "other")
    try:
        purpose_enum = PurposeClassification(purpose)
    except ValueError:
        purpose_enum = PurposeClassification.other

    dist_create = DistributionCreate(
        trust_id=ctx.trust_id,
        beneficiary_name=params.get("beneficiary_name", "Unknown"),
        amount=float(params.get("amount", 0)),
        date=params.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
        purpose_classification=purpose_enum,
        notes=params.get("notes", ""),
        is_benevolence=False,
    )
    # Fetch user dict for the router call
    user = ctx.user or await _user_doc(ctx.user_id)
    result = await _create_dist(
        dist=dist_create,
        background_tasks=BackgroundTasks(),
        user=user,
    )
    # Distribution is created in "review" status with solvency_confirmed=False.
    # The chat must tell the user to confirm solvency on the Distributions page.
    return {
        "success": True,
        "record_id": result.distribution_id,
        "endpoint": "distributions",
        "requires_solvency_confirmation": True,
        "solvency_link": f"/distributions?approve={result.distribution_id}",
    }


@action(
    name="add-schedule-a-asset",
    description="Add an asset to the trust's Schedule A.",
    write=True,
    trust_scoped=True,
    surfaces=("chat",),
    fields=[
        F("category", "string", required=False),
        F("description", "string", required=True),
        F("approximate_value", "number", required=False),
        F("date_conveyed", "string", required=False),
        F("notes", "string", required=False),
    ],
)
async def _chat_asset(params: dict, ctx: ActionContext) -> dict:
    """Chat intent 'asset': asset."""
    # Route through the real schedule_a router to ensure validation.
    from routers.schedule_a import create_schedule_a_item as _create_asset
    from models import ScheduleAItemCreate, AssetCategory
    from fastapi import BackgroundTasks

    category = params.pop("category", "other_property")
    try:
        category_enum = AssetCategory(category)
    except ValueError:
        category_enum = AssetCategory.other_property

    asset_create = ScheduleAItemCreate(
        trust_id=ctx.trust_id,
        category=category_enum,
        description=params.get("description", ""),
        approximate_value=params.get("approximate_value"),
        date_conveyed=params.get("date_conveyed", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
        notes=params.get("notes", ""),
    )
    user = ctx.user or await _user_doc(ctx.user_id)
    result = await _create_asset(item=asset_create, user=user)
    # Update onboarding (schedule_a router doesn't call auto_update_onboarding)
    try:
        from dependencies import auto_update_onboarding
        await auto_update_onboarding(ctx.user_id, ctx.trust_id)
    except Exception:
        pass
    return {"success": True, "record_id": result.item_id, "endpoint": "schedule-a"}


@action(
    name="update-schedule-a-asset",
    description="Update a Schedule A asset's value or description.",
    write=True,
    trust_scoped=True,
    surfaces=("chat",),
    fields=[
        F("asset_description", "string", required=True),
        F("new_value", "number", required=False),
        F("new_description", "string", required=False),
        F("valuation_date", "string", required=False),
        F("notes", "string", required=False),
    ],
)
async def _chat_asset_update(params: dict, ctx: ActionContext) -> dict:
    """Chat intent 'asset_update': asset_update."""
    # Route through the schedule_a router's update_schedule_a_item to
    # enforce ownership verification and validation. Adds audit logging
    # for the valuation update.
    from routers.schedule_a import update_schedule_a_item as _update_asset
    from models import ScheduleAItemUpdate

    # Look up the existing asset by description (fuzzy match)
    asset_desc = params.get("asset_description", "")
    if not asset_desc:
        return {"success": False, "error": "Asset description is required to identify which asset to update."}

    # Try exact match first, then partial match
    existing = await db.schedule_a_items.find_one({
        "trust_id": ctx.trust_id,
        "user_id": ctx.user_id,
        "status": "active",
        "description": {"$regex": re.escape(asset_desc), "$options": "i"}
    })

    if not existing:
        # Try broader partial match
        existing = await db.schedule_a_items.find_one({
            "trust_id": ctx.trust_id,
            "user_id": ctx.user_id,
            "status": "active",
            "description": {"$regex": re.escape(asset_desc.split()[0]), "$options": "i"}
        })

    if not existing:
        return {"success": False, "error": f"Could not find an active asset matching '{asset_desc}'. Please check the description and try again."}

    # Build the ScheduleAItemUpdate model with only provided fields
    update_kwargs = {}
    if params.get("new_value") is not None:
        update_kwargs["approximate_value"] = float(params["new_value"])
    if params.get("new_description"):
        update_kwargs["description"] = params["new_description"]
    if params.get("notes"):
        update_kwargs["notes"] = params["notes"]

    # Always record the valuation date via notes append
    valuation_date = params.get("valuation_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if "notes" in update_kwargs:
        update_kwargs["notes"] = f"{update_kwargs['notes']} | Valuation date: {valuation_date}"
    else:
        update_kwargs["notes"] = f"Valuation date: {valuation_date}"

    if not update_kwargs:
        return {"success": False, "error": "No update fields provided."}

    asset_update = ScheduleAItemUpdate(**update_kwargs)

    user = ctx.user or await _user_doc(ctx.user_id)
    try:
        await _update_asset(
            item_id=existing["item_id"],
            update=asset_update,
            user=user,
        )
        # Audit log the asset valuation update
        from utils.audit import log_audit_event
        await log_audit_event(
            user_id=ctx.user_id,
            action="asset_updated",
            entity_type="schedule_a_item",
            entity_id=existing["item_id"],
            details={
                "trust_id": ctx.trust_id,
                "description": existing.get("description", ""),
                "fields_changed": list(update_kwargs.keys()),
                "valuation_date": valuation_date,
            },
        )
        return {"success": True, "record_id": existing["item_id"], "endpoint": "schedule-a"}
    except HTTPException as e:
        return {"success": False, "error": e.detail}
    except Exception as e:
        return {"success": False, "error": f"Failed to update asset: {str(e)}"}


@action(
    name="contribute-property-to-trust",
    description='Contribute an asset to the trust: Schedule A entry plus acceptance-of-property minutes.',
    write=True,
    trust_scoped=True,
    surfaces=("chat",),
    fields=[
        F("category", "string", required=False),
        F("description", "string", required=True),
        F("approximate_value", "number", required=False),
        F("date_conveyed", "string", required=False),
        F("meeting_date", "string", required=False),
        F("participants_text", "string", required=False),
        F("grantor_name", "string", required=False),
        F("notes", "string", required=False),
    ],
)
async def _chat_contribute_asset(params: dict, ctx: ActionContext) -> dict:
    """Chat intent 'contribute_asset': contribute_asset."""
    # Combined action: create a Schedule A item AND an acceptance-of-property
    # minutes record in one transactional flow.
    from routers.schedule_a import create_schedule_a_item as _create_asset
    from routers.minutes import create_minutes as _create_minutes, generate_template_document
    from models import ScheduleAItemCreate, AssetCategory, MinutesCreate, MinutesType
    from fastapi import BackgroundTasks

    # --- 0) Deduplication check — reject if an active asset with the same description already exists ---
    property_description = params.get("description", "")
    if property_description:
        existing_asset = await db.schedule_a_items.find_one({
            "trust_id": ctx.trust_id,
            "user_id": ctx.user_id,
            "status": "active",
            "description": {"$regex": f"^{re.escape(property_description)}$", "$options": "i"},
        })
        if existing_asset:
            return {
                "success": False,
                "error": f"An active asset with the description '{property_description}' already exists on Schedule A. "
                         f"Use a different description or update the existing asset instead.",
                "endpoint": "contribute_asset",
            }

    # --- 1) Create the Schedule A item (same pattern as the asset block) ---
    category = params.pop("category", "other_property")
    try:
        category_enum = AssetCategory(category)
    except ValueError:
        category_enum = AssetCategory.other_property

    # Build notes: include ownership_pct as a meaningful note if present
    notes = params.get("notes", "")
    ownership_pct = params.get("ownership_pct")
    if ownership_pct is not None:
        ownership_note = f"Ownership: {ownership_pct}%"
        notes = f"{notes}\n{ownership_note}".strip() if notes else ownership_note

    asset_create = ScheduleAItemCreate(
        trust_id=ctx.trust_id,
        category=category_enum,
        description=property_description,
        approximate_value=params.get("approximate_value"),
        date_conveyed=params.get("date_conveyed", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
        notes=notes,
    )
    user = ctx.user or await _user_doc(ctx.user_id)
    asset_result = await _create_asset(item=asset_create, user=user)
    asset_id = asset_result.item_id

    # --- 2) Create the acceptance-of-property minutes record ---
    participants_text = params.get("participants_text", "")
    if isinstance(participants_text, list):
        participants_text = ", ".join(participants_text)

    meeting_date = params.get("meeting_date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    grantor_name = params.get("grantor_name", "")
    property_value = params.get("approximate_value")
    conveyance_date = params.get("date_conveyed", meeting_date)

    # Dynamic decisions_text referencing the actual property being contributed
    decisions_text = f"Acceptance of {property_description or 'property'} contributed to the trust" + (f" (value: ${property_value:,.2f})" if property_value else "")

    # Clean template_data — remove dead fields that create_minutes does not process
    template_data = {
        "grantor_name": grantor_name,
        "property_description": property_description,
        "property_value": property_value,
        "conveyance_date": conveyance_date,
        "meeting_date": meeting_date,
        "trustees_present": [p.strip() for p in participants_text.split(",") if p.strip()],
    }

    minutes_create = MinutesCreate(
        trust_id=ctx.trust_id,
        minutes_type=MinutesType.general,
        meeting_date=meeting_date,
        participants_text=participants_text,
        decisions_text=decisions_text,
        status="draft",
        template_type="acceptance_of_property",
        template_data=template_data,
    )

    # Fetch the trust document for generate_template_document
    trust_doc = await db.trusts.find_one({"trust_id": ctx.trust_id, "user_id": ctx.user_id}, {"_id": 0})

    try:
        minutes_result = await _create_minutes(
            minutes=minutes_create,
            background_tasks=BackgroundTasks(),
            user=user,
        )
    except Exception as minutes_exc:
        # FIX 2 — Partial failure rollback: if minutes creation fails after
        # the Schedule A item was already created, delete the orphaned item
        # so we don't leave a dangling asset with no acceptance minutes.
        logger.error(f"contribute_asset: minutes creation failed, rolling back Schedule A item {asset_id}: {minutes_exc}")
        try:
            # Route through the schedule_a router's delete endpoint
            # to enforce ownership verification and audit logging.
            from routers.schedule_a import delete_schedule_a_item as _delete_asset
            await _delete_asset(item_id=asset_id, user=user)
        except Exception as del_exc:
            logger.error(f"contribute_asset: failed to delete orphaned Schedule A item {asset_id}: {del_exc}")
        return {
            "success": False,
            "error": f"Failed to create acceptance minutes: {minutes_exc}. The Schedule A item was rolled back.",
            "endpoint": "contribute_asset",
        }

    # FIX 1 — Generate WHEREAS/RESOLVED formatted text and update the minutes record
    try:
        if trust_doc:
            generated_text = generate_template_document(trust_doc, "acceptance_of_property", template_data)
            if generated_text:
                # Route through the minutes router's update_minutes endpoint
                # to enforce ownership verification and validation.
                from routers.minutes import update_minutes as _update_minutes
                mock_req = _MockRequest({"decisions_text": generated_text})
                await _update_minutes(
                    minutes_id=minutes_result.minutes_id,
                    request=mock_req,
                    user=user,
                )
    except Exception as gen_exc:
        logger.error(f"contribute_asset: failed to generate template document for minutes {minutes_result.minutes_id}: {gen_exc}")
        # Non-fatal — the minutes record still has the dynamic decisions_text fallback

    # FIX 3 — Set minutes_ref on the Schedule A item pointing to the minutes record
    try:
        # Route through the schedule_a router's update endpoint to
        # enforce ownership verification and validation.
        from routers.schedule_a import update_schedule_a_item as _update_asset
        from models import ScheduleAItemUpdate as _SAItemUpdate
        ref_update = _SAItemUpdate(minutes_ref=minutes_result.minutes_id)
        await _update_asset(
            item_id=asset_id,
            update=ref_update,
            user=user,
        )
    except Exception as ref_exc:
        logger.error(f"contribute_asset: failed to set minutes_ref on Schedule A item {asset_id}: {ref_exc}")
        # Non-fatal — both records exist but the link is missing

    # --- 3) Update onboarding after both records are created ---
    try:
        from dependencies import auto_update_onboarding
        await auto_update_onboarding(ctx.user_id, ctx.trust_id)
    except Exception:
        pass

    return {
        "success": True,
        "schedule_a_id": asset_id,
        "minutes_id": minutes_result.minutes_id,
        "endpoint": "contribute_asset",
        "status": "draft",
        "review_link": f"/minutes/{minutes_result.minutes_id}/edit",
    }


@action(
    name="create-beneficiary",
    description='Create a beneficiary unit certificate.',
    write=True,
    trust_scoped=True,
    surfaces=("chat",),
    fields=[
        F("holder_name", "string", required=True),
        F("email", "string", required=False),
        F("phone", "string", required=False),
        F("units", "number", required=False),
    ],
)
async def _chat_beneficiary(params: dict, ctx: ActionContext) -> dict:
    """Chat intent 'beneficiary': beneficiary."""
    # Route through the real trust_units router to ensure validation
    # (units overflow check, fractional validation, certificate numbering).
    from routers.trust_units import create_unit_certificate as _create_cert
    from models import TrustUnitCertificateCreate

    # Get unit settings for the trust to convert percentage to units
    settings = await db.trust_units_settings.find_one({"trust_id": ctx.trust_id})
    total_authorized = settings.get("total_authorized_units", 0) if settings else 0

    allocation_pct = params.get("units", 0)
    if total_authorized > 0 and isinstance(allocation_pct, (int, float)) and allocation_pct < 100:
        units = max(1, round(total_authorized * allocation_pct / 100))
    elif isinstance(allocation_pct, (int, float)):
        units = int(allocation_pct) if allocation_pct > 0 else 1
    else:
        units = 1

    cert_create = TrustUnitCertificateCreate(
        trust_id=ctx.trust_id,
        holder_name=params.get("holder_name", "Unknown"),
        holder_type=params.get("holder_type", "individual"),
        units=float(units),
        issue_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        email=params.get("email"),
        phone=params.get("phone"),
    )
    user = ctx.user or await _user_doc(ctx.user_id)
    try:
        result = await _create_cert(certificate=cert_create, user=user)
        # Update onboarding checklist
        try:
            from dependencies import auto_update_onboarding
            await auto_update_onboarding(ctx.user_id, ctx.trust_id)
        except Exception:
            pass
        return {"success": True, "record_id": result.certificate_id, "endpoint": "trust-units/certificates"}
    except HTTPException as e:
        return {"success": False, "error": e.detail}
    except Exception as e:
        return {"success": False, "error": f"Failed to create beneficiary: {str(e)}"}


@action(
    name="update-beneficiary",
    description="Update a beneficiary's contact details.",
    write=True,
    trust_scoped=True,
    surfaces=("chat",),
    fields=[
        F("holder_name", "string", required=True),
        F("email", "string", required=False),
        F("phone", "string", required=False),
        F("notes", "string", required=False),
    ],
)
async def _chat_beneficiary_update(params: dict, ctx: ActionContext) -> dict:
    """Chat intent 'beneficiary_update': beneficiary_update."""
    # Route through the beneficiaries router's update_beneficiary to
    # enforce ownership verification (certificate must be active and
    # belong to the user). Adds audit logging for the change.
    from routers.beneficiaries import update_beneficiary as _update_bene
    from models import BeneficiaryUpdate

    # Find the existing beneficiary certificate by holder_name (case-insensitive)
    existing = await db.trust_unit_certificates.find_one({
        "trust_id": ctx.trust_id,
        "user_id": ctx.user_id,
        "holder_name": {"$regex": f"^{re.escape(mapped_data.get('holder_name', ''))}$", "$options": "i"},
        "status": "active",
    })
    if not existing:
        return {"success": False, "error": f"Beneficiary '{mapped_data.get('holder_name', '')}' not found. Use 'Create Beneficiary' to add them first."}

    # Build the BeneficiaryUpdate model with only provided fields
    update_kwargs = {}
    if params.get("email"):
        update_kwargs["email"] = params["email"]
    if params.get("phone"):
        update_kwargs["phone"] = params["phone"]
    if params.get("notes"):
        update_kwargs["notes"] = params["notes"]

    if not update_kwargs:
        return {"success": False, "error": "No update fields provided."}

    bene_update = BeneficiaryUpdate(**update_kwargs)

    user = ctx.user or await _user_doc(ctx.user_id)
    try:
        await _update_beneficiary(
            beneficiary_id=existing["certificate_id"],
            data=bene_update,
            user=user,
        )
        # Audit log the beneficiary update
        from utils.audit import log_audit_event
        await log_audit_event(
            user_id=ctx.user_id,
            action="beneficiary_updated",
            entity_type="trust_unit_certificate",
            entity_id=existing["certificate_id"],
            details={
                "trust_id": ctx.trust_id,
                "holder_name": existing.get("holder_name", ""),
                "fields_changed": list(update_kwargs.keys()),
            },
        )
        return {"success": True, "record_id": existing["certificate_id"], "endpoint": "beneficiaries", "action": "updated"}
    except HTTPException as e:
        return {"success": False, "error": e.detail}
    except Exception as e:
        return {"success": False, "error": f"Failed to update beneficiary: {str(e)}"}


@action(
    name="remove-beneficiary",
    description='Remove (deactivate) a beneficiary certificate.',
    write=True,
    trust_scoped=True,
    surfaces=("chat",),
    fields=[
        F("holder_name", "string", required=True),
        F("reason", "string", required=False),
    ],
)
async def _chat_beneficiary_removal(params: dict, ctx: ActionContext) -> dict:
    """Chat intent 'beneficiary_removal': beneficiary_removal."""
    # Route through the beneficiaries router's delete_beneficiary to
    # enforce ownership verification and preserve the audit trail
    # (soft-delete: marks certificate inactive rather than deleting).
    from routers.beneficiaries import delete_beneficiary as _delete_bene

    existing = await db.trust_unit_certificates.find_one({
        "trust_id": ctx.trust_id,
        "user_id": ctx.user_id,
        "holder_name": {"$regex": f"^{re.escape(mapped_data.get('holder_name', ''))}$", "$options": "i"},
        "status": "active",
    })
    if not existing:
        return {"success": False, "error": f"Beneficiary '{mapped_data.get('holder_name', '')}' not found."}

    user = ctx.user or await _user_doc(ctx.user_id)
    try:
        await _delete_beneficiary(
            beneficiary_id=existing["certificate_id"],
            user=user,
        )
        # Audit log the beneficiary removal
        from utils.audit import log_audit_event
        await log_audit_event(
            user_id=ctx.user_id,
            action="beneficiary_removed",
            entity_type="trust_unit_certificate",
            entity_id=existing["certificate_id"],
            details={
                "trust_id": ctx.trust_id,
                "holder_name": existing.get("holder_name", ""),
                "reason": params.get("reason", ""),
            },
        )
        return {"success": True, "record_id": existing["certificate_id"], "endpoint": "beneficiaries", "action": "removed"}
    except HTTPException as e:
        return {"success": False, "error": e.detail}
    except Exception as e:
        return {"success": False, "error": f"Failed to remove beneficiary: {str(e)}"}


@action(
    name="send-certificate",
    description='Email a beneficiary their unit certificate.',
    write=True,
    trust_scoped=True,
    surfaces=("chat",),
    fields=[
        F("holder_name", "string", required=True),
        F("email", "string", required=True),
        F("notes", "string", required=False),
    ],
)
async def _chat_send_certificate(params: dict, ctx: ActionContext) -> dict:
    """Chat intent 'send_certificate': send_certificate."""
    # Route through the beneficiaries router's send_beneficiary_certificate
    # to enforce trust ownership verification, certificate lookup, email
    # validation, and communication logging. Adds audit logging.
    from routers.beneficiaries import send_beneficiary_certificate as _send_cert
    from models import SendCertificateRequest

    holder_name = params.get("holder_name", "")
    override_email = params.get("email", "")

    cert_req = SendCertificateRequest(
        trust_id=ctx.trust_id,
        beneficiary_name=holder_name,
        email=override_email if override_email else None,
        notes=params.get("notes"),
    )

    user = ctx.user or await _user_doc(ctx.user_id)
    try:
        result = await _send_cert(data=cert_req, user=user)
        # Audit log the certificate send
        from utils.audit import log_audit_event
        await log_audit_event(
            user_id=ctx.user_id,
            action="certificate_sent_via_chat",
            entity_type="trust_unit_certificate",
            entity_id=result.get("certificate_id", ""),
            details={
                "trust_id": ctx.trust_id,
                "beneficiary_name": holder_name,
                "email_sent_to": result.get("email_sent_to", ""),
                "units": result.get("units", 0),
                "percentage": result.get("percentage", 0),
                "source": "chat_assistant",
            },
        )
        return {
            "success": True,
            "record_id": result.get("certificate_id", ""),
            "endpoint": "certificate_notice",
            "action": "emailed",
            "email_sent_to": result.get("email_sent_to", ""),
            "units": result.get("units", 0),
            "percentage": result.get("percentage", 0),
        }
    except HTTPException as e:
        return {"success": False, "error": e.detail}
    except Exception as e:
        return {"success": False, "error": f"Failed to send certificate: {str(e)}"}


@action(
    name="cancel-distribution",
    description='Cancel a distribution record.',
    write=True,
    trust_scoped=True,
    surfaces=("chat",),
    fields=[
        F("beneficiary_name", "string", required=True),
        F("amount", "number", required=True),
        F("date", "string", required=False),
    ],
)
async def _chat_distribution_cancel(params: dict, ctx: ActionContext) -> dict:
    """Chat intent 'distribution_cancel': distribution_cancel."""
    # Route through the distributions router's delete_distribution to
    # enforce ownership verification and audit logging. The chat "cancel"
    # action maps to the canonical delete endpoint, which logs to the
    # audit trail via log_audit_event.
    from routers.distributions import delete_distribution as _delete_dist

    # Find matching distribution by beneficiary name + optional amount/date
    query = {"trust_id": ctx.trust_id, "user_id": ctx.user_id}
    if params.get("beneficiary_name"):
        query["beneficiary_name"] = {"$regex": f"^{mapped_data['beneficiary_name']}$", "$options": "i"}
    if params.get("amount"):
        query["amount"] = float(params["amount"])

    existing = await db.distribution_records.find_one(query, sort=[("created_at", -1)])
    if not existing:
        return {"success": False, "error": "Distribution not found matching those details."}

    # Governance check: cannot cancel an already-approved distribution
    # without first revoking approval (status flow validation)
    if existing.get("approved_at") and existing.get("status") != "cancelled":
        return {
            "success": False,
            "error": "This distribution has already been approved and may have been executed. "
                     "Please revoke approval on the Distributions page before cancelling.",
            "requires_action": "revoke_approval",
            "solvency_link": f"/distributions?approve={existing['distribution_id']}",
        }

    user = ctx.user or await _user_doc(ctx.user_id)
    try:
        await _delete_dist(distribution_id=existing["distribution_id"], user=user)
        return {"success": True, "record_id": existing["distribution_id"], "endpoint": "distributions", "action": "cancelled"}
    except HTTPException as e:
        return {"success": False, "error": e.detail}
    except Exception as e:
        return {"success": False, "error": f"Failed to cancel distribution: {str(e)}"}


@action(
    name="upload-vault-document",
    description='Register a document in the trust vault.',
    write=True,
    trust_scoped=True,
    surfaces=("chat",),
    fields=[
        F("title", "string", required=True),
        F("category", "string", required=False),
        F("notes", "string", required=False),
    ],
)
async def _chat_document_upload(params: dict, ctx: ActionContext) -> dict:
    """Chat intent 'document_upload': document_upload."""
    # Route through the real vault router to ensure validation
    # and onboarding updates.
    from routers.vault import add_document as _add_doc, DocumentCreate

    # Validate category against vault's DOC_CATEGORIES
    category = params.get("category", "other")
    try:
        doc_create = DocumentCreate(
            title=params.get("title", "Untitled Document"),
            category=category,
            description=params.get("notes", ""),
            storage_provider="local_server",
        )
    except Exception as ve:
        return {"success": False, "error": f"Invalid document data: {str(ve)}"}

    user = ctx.user or await _user_doc(ctx.user_id)
    try:
        result = await _add_doc(trust_id=ctx.trust_id, doc=doc_create, user=user)
        return {
            "success": True,
            "record_id": result["doc_id"],
            "endpoint": "vault/documents",
            "action": "created",
            "note": "Document record created. Upload the file in the Vault page to complete.",
        }
    except HTTPException as e:
        return {"success": False, "error": e.detail}
    except Exception as e:
        return {"success": False, "error": f"Failed to create document: {str(e)}"}


@action(
    name="create-compensation-plan",
    description='Create a trustee compensation plan.',
    write=True,
    trust_scoped=True,
    surfaces=("chat",),
    fields=[
        F("trustee_name", "string", required=True),
        F("annual_amount", "number", required=False),
        F("fee_type", "string", required=False),
        F("effective_date", "string", required=False),
        F("role", "string", required=False),
    ],
)
async def _chat_compensation_plan(params: dict, ctx: ActionContext) -> dict:
    """Chat intent 'compensation_plan': compensation_plan."""
    # Route through the real compensation router to ensure validation,
    # primary-plan logic, and onboarding updates.
    from routers.compensation import create_comp_plan as _create_plan
    from models import CompensationPlanCreate

    annual_amount = float(params.get("annual_amount", 0))
    effective_date = params.get("effective_date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    plan_create = CompensationPlanCreate(
        trust_id=ctx.trust_id,
        trustee_name=params.get("trustee_name", ""),
        role=params.get("role", ""),
        annual_amount=annual_amount,
        annual_approved_amount=annual_amount,
        fee_type=params.get("fee_type", "fixed"),
        effective_date=effective_date,
        notes=params.get("notes", ""),
    )
    user = ctx.user or await _user_doc(ctx.user_id)
    try:
        result = await _create_plan(plan=plan_create, user=user)
        return {
            "success": True,
            "record_id": result.plan_id,
            "endpoint": "compensation-plans",
            "action": "created",
        }
    except HTTPException as e:
        return {"success": False, "error": e.detail}
    except Exception as e:
        return {"success": False, "error": f"Failed to create compensation plan: {str(e)}"}


@action(
    name="record-compensation-payment",
    description='Record a trustee compensation payment.',
    write=True,
    trust_scoped=True,
    surfaces=("chat",),
    fields=[
        F("trustee_name", "string", required=True),
        F("amount", "number", required=True),
        F("date", "string", required=False),
        F("classification_text", "string", required=False),
    ],
)
async def _chat_compensation_payment(params: dict, ctx: ActionContext) -> dict:
    """Chat intent 'compensation_payment': compensation_payment."""
    # Route through the real compensation router to ensure validation,
    # exceeds-plan detection, and onboarding updates.
    from routers.compensation import create_comp_payment as _create_payment
    from models import CompensationPaymentCreate

    payment_date = params.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    payment_amount = float(params.get("amount", 0))

    payment_create = CompensationPaymentCreate(
        trust_id=ctx.trust_id,
        amount=payment_amount,
        date=payment_date,
        classification_text=params.get("classification_text", ""),
        trustee_name=params.get("trustee_name") or None,
    )
    user = ctx.user or await _user_doc(ctx.user_id)
    try:
        result = await _create_payment(payment=payment_create, user=user)
        return {
            "success": True,
            "record_id": result.payment_id,
            "endpoint": "compensation-payments",
            "action": "created",
        }
    except HTTPException as e:
        return {"success": False, "error": e.detail}
    except Exception as e:
        return {"success": False, "error": f"Failed to create compensation payment: {str(e)}"}


@action(
    name="add-investment",
    description='Record an investment holding for the trust.',
    write=True,
    trust_scoped=True,
    surfaces=("chat",),
    fields=[
        F("asset_name", "string", required=True),
        F("asset_type", "string", required=False),
        F("cost_basis", "number", required=False),
        F("purchase_date", "string", required=False),
        F("current_value", "number", required=False),
        F("quantity", "number", required=False),
        F("unit", "string", required=False),
        F("custodian", "string", required=False),
        F("notes", "string", required=False),
    ],
)
async def _chat_investment(params: dict, ctx: ActionContext) -> dict:
    """Chat intent 'investment': investment."""
    # Route through the real investments router to ensure validation.
    from routers.investments import create_investment as _create_inv

    cost_basis = float(params.get("cost_basis", 0))
    current_value = float(params.get("current_value", 0)) if params.get("current_value") else cost_basis
    investment_dict = {
        "asset_name": params.get("asset_name", ""),
        "asset_type": params.get("asset_type", "other"),
        "purchase_date": params.get("purchase_date"),
        "cost_basis": cost_basis,
        "current_value": current_value,
        "quantity": float(params.get("quantity", 1)) if params.get("quantity") else 1,
        "unit": params.get("unit", "shares"),
        "custodian": params.get("custodian"),
        "notes": params.get("notes"),
    }
    user = ctx.user or await _user_doc(ctx.user_id)
    try:
        result = await _create_inv(trust_id=ctx.trust_id, investment=investment_dict, user=user)
        # Update onboarding checklist (investments router doesn't call auto_update_onboarding)
        try:
            from dependencies import auto_update_onboarding
            await auto_update_onboarding(ctx.user_id, ctx.trust_id)
        except Exception:
            pass
        return {
            "success": True,
            "record_id": result["investment_id"],
            "endpoint": "investments",
            "action": "created",
        }
    except HTTPException as e:
        return {"success": False, "error": e.detail}
    except Exception as e:
        return {"success": False, "error": f"Failed to create investment: {str(e)}"}


@action(
    name="create-governance-task",
    description='Create a governance task for the trust.',
    write=True,
    trust_scoped=True,
    surfaces=("chat",),
    fields=[
        F("task_type", "string", required=True),
        F("description", "string", required=True),
        F("due_date", "string", required=False),
        F("priority", "string", required=False),
    ],
)
async def _chat_task(params: dict, ctx: ActionContext) -> dict:
    """Chat intent 'task': task."""
    # Route through the real tasks router to ensure validation,
    # checklist template population, and onboarding updates.
    from routers.tasks import create_task as _create_task
    from models import GovernanceTaskCreate, TaskType

    task_type_val = params.get("task_type", "custom")
    try:
        task_type_enum = TaskType(task_type_val)
    except ValueError:
        task_type_enum = TaskType.custom

    task_create = GovernanceTaskCreate(
        trust_id=ctx.trust_id,
        task_type=task_type_enum,
        due_date=params.get("due_date", ""),
        description=params.get("description", ""),
    )
    user = ctx.user or await _user_doc(ctx.user_id)
    try:
        result = await _create_task(task=task_create, user=user)
        return {
            "success": True,
            "record_id": result.task_id,
            "endpoint": "tasks",
            "action": "created",
        }
    except HTTPException as e:
        return {"success": False, "error": e.detail}
    except Exception as e:
        return {"success": False, "error": f"Failed to create task: {str(e)}"}


@action(
    name="create-transaction",
    description='Record a trust transaction.',
    write=True,
    trust_scoped=True,
    surfaces=("chat",),
    fields=[
        F("transaction_type", "string", required=True),
        F("amount", "number", required=True),
        F("category", "string", required=False),
        F("date", "string", required=False),
        F("description", "string", required=False),
    ],
)
async def _chat_transaction(params: dict, ctx: ActionContext) -> dict:
    """Chat intent 'transaction': transaction."""
    # Route through the real transactions router to ensure validation,
    # audit logging, and alert detection.
    from routers.transactions import create_transaction as _create_txn
    from models import TransactionCreate, TransactionDirection, GovernanceClassification

    # The transactions router requires an entity_id — look up the
    # first entity for this trust (typically the Trust entity itself).
    entity = await db.entities.find_one(
        {"trust_id": ctx.trust_id, "user_id": ctx.user_id},
        {"_id": 0},
        sort=[("created_at", 1)],
    )
    if not entity:
        return {
            "success": False,
            "error": "No entity found for this trust. Please create an entity (Trust, Holding LLC, or Operating LLC) before recording transactions.",
        }
    entity_id = entity["entity_id"]

    # Map chat's "transaction_type" to direction + governance_classification.
    # Chat sends transaction_type as "expense"/"income"/etc.
    raw_type = params.get("transaction_type", "expense")
    if raw_type in ("income", "deposit", "inflow"):
        direction_enum = TransactionDirection.inflow
        classification_enum = GovernanceClassification.capital_contribution
    else:
        direction_enum = TransactionDirection.outflow
        classification_enum = GovernanceClassification.operational_expense

    # Map chat's "category" if it matches a known GovernanceClassification
    raw_category = params.get("category", "")
    if raw_category:
        try:
            classification_enum = GovernanceClassification(raw_category)
        except ValueError:
            pass  # keep the default

    txn_create = TransactionCreate(
        trust_id=ctx.trust_id,
        entity_id=entity_id,
        date=params.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
        amount=float(params.get("amount", 0)),
        direction=direction_enum,
        governance_classification=classification_enum,
        purpose_memo=params.get("description", ""),
    )
    user = ctx.user or await _user_doc(ctx.user_id)
    try:
        result = await _create_txn(txn=txn_create, user=user)
        # Update onboarding checklist (transactions router doesn't call auto_update_onboarding)
        try:
            from dependencies import auto_update_onboarding
            await auto_update_onboarding(ctx.user_id, ctx.trust_id)
        except Exception:
            pass
        return {
            "success": True,
            "record_id": result.transaction_id,
            "endpoint": "transactions",
            "action": "created",
        }
    except HTTPException as e:
        return {"success": False, "error": e.detail}
    except Exception as e:
        return {"success": False, "error": f"Failed to create transaction: {str(e)}"}


@action(
    name="create-entity",
    description='Create an entity record for the trust.',
    write=True,
    trust_scoped=True,
    surfaces=("chat",),
    fields=[
        F("name", "string", required=True),
        F("entity_type", "string", required=False),
        F("legal_name", "string", required=False),
        F("governing_law", "string", required=False),
        F("ein", "string", required=False),
        F("formation_date", "string", required=False),
        F("trustee_names", "string", required=False),
        F("member_names", "string", required=False),
        F("manager_names", "string", required=False),
    ],
)
async def _chat_entity(params: dict, ctx: ActionContext) -> dict:
    """Chat intent 'entity': entity."""
    # Route through the real entities router to ensure validation
    # and onboarding updates.
    from routers.entities import create_entity as _create_entity
    from models import EntityCreate, EntityType

    # Validate entity_type — must be one of the allowed values
    raw_type = params.get("entity_type", "Trust")
    entity_type_enum = None
    for et in EntityType:
        if raw_type and raw_type.lower() == et.value.lower():
            entity_type_enum = et
            break
    if not entity_type_enum:
        entity_type_enum = EntityType.trust  # default to Trust if unrecognized

    name = params.get("name", "")
    entity_create = EntityCreate(
        trust_id=ctx.trust_id,
        name=name,
        entity_type=entity_type_enum,
        legal_name=params.get("legal_name", name),
        formation_date=params.get("formation_date"),
        governing_law=params.get("governing_law", ""),
        ein=params.get("ein"),
        trustee_names=params.get("trustee_names", ""),
        member_names=params.get("member_names", ""),
        manager_names=params.get("manager_names", ""),
    )
    user = ctx.user or await _user_doc(ctx.user_id)
    try:
        result = await _create_entity(entity=entity_create, user=user)
        return {
            "success": True,
            "record_id": result.entity_id,
            "endpoint": "entities",
            "action": "created",
        }
    except HTTPException as e:
        return {"success": False, "error": e.detail}
    except Exception as e:
        return {"success": False, "error": f"Failed to create entity: {str(e)}"}


@action(
    name="update-trust-settings",
    description='Update one trust setting field.',
    write=True,
    trust_scoped=True,
    surfaces=("chat",),
    fields=[
        F("field", "string", required=True),
        F("value", "any", required=True),
    ],
)
async def _chat_settings_update(params: dict, ctx: ActionContext) -> dict:
    """Chat intent 'settings_update': settings_update."""
    # Route through the trusts router's update_trust to enforce
    # ownership verification, field validation (EIN format, tax year
    # end), jurisdiction/state_code auto-sync, and audit logging
    # (update_trust calls log_audit_event internally).
    from routers.trusts import update_trust as _update_trust
    from models import TrustUpdate

    field = params.get("field", "")
    value = params.get("value", "")
    field_mapping = {
        "name": "name",
        "trust_type": "trust_type",
        "formation_date": "start_date",
        "ein": "ein",
        "jurisdiction": "jurisdiction",
        "state_code": "state_code",
    }
    db_field = field_mapping.get(field.lower().replace(" ", "_"))
    if not db_field:
        return {"success": False, "error": f"Unknown field: {field}. Valid fields: name, trust_type, formation_date, ein, jurisdiction, state_code"}

    # Build the TrustUpdate model with only the provided field
    update_kwargs = {db_field: value}
    try:
        trust_update = TrustUpdate(**update_kwargs)
    except Exception as ve:
        return {"success": False, "error": f"Invalid value for field '{field}': {str(ve)}"}

    user = ctx.user or await _user_doc(ctx.user_id)
    try:
        await _update_trust(
            trust_id=ctx.trust_id,
            update=trust_update,
            user=user,
        )
        # update_trust already logs to audit trail via log_audit_event,
        # but we add a chat-specific audit entry for traceability.
        from utils.audit import log_audit_event
        await log_audit_event(
            user_id=ctx.user_id,
            action="trust_settings_updated_via_chat",
            entity_type="trust",
            entity_id=ctx.trust_id,
            details={
                "field_changed": db_field,
                "source": "chat_assistant",
            },
        )
        return {"success": True, "record_id": ctx.trust_id, "endpoint": "trusts", "action": "updated", "field": db_field}
    except HTTPException as e:
        return {"success": False, "error": e.detail}
    except Exception as e:
        return {"success": False, "error": f"Failed to update trust settings: {str(e)}"}


@action(
    name="dismiss-alert",
    description='Dismiss a governance alert criterion.',
    write=True,
    trust_scoped=True,
    surfaces=("chat",),
    fields=[
        F("criterion_name", "string", required=True),
    ],
)
async def _chat_alert_dismiss(params: dict, ctx: ActionContext) -> dict:
    """Chat intent 'alert_dismiss': alert_dismiss."""
    # Route through the governance router's dismiss_insight to enforce
    # trust ownership verification. Adds audit logging for the dismissal.
    from routers.governance import dismiss_insight as _dismiss_insight
    from models import DismissedInsightCreate

    criterion = params.get("criterion_name", "")
    if not criterion:
        return {"success": False, "error": "No criterion name provided to dismiss."}

    dismiss_req = DismissedInsightCreate(trust_id=ctx.trust_id, criterion_name=criterion)

    user = ctx.user or await _user_doc(ctx.user_id)
    try:
        await _dismiss_insight(req=dismiss_req, user=user)
        # Audit log the alert dismissal
        from utils.audit import log_audit_event
        await log_audit_event(
            user_id=ctx.user_id,
            action="alert_dismissed_via_chat",
            entity_type="governance_insight",
            entity_id=criterion,
            details={
                "trust_id": ctx.trust_id,
                "criterion_name": criterion,
                "source": "chat_assistant",
            },
        )
        return {"success": True, "endpoint": "insights", "action": "dismissed", "criterion": criterion}
    except HTTPException as e:
        return {"success": False, "error": e.detail}
    except Exception as e:
        return {"success": False, "error": f"Failed to dismiss insight: {str(e)}"}


@action(
    name="add-class-beneficiary",
    description='Add a class of beneficiaries.',
    write=True,
    trust_scoped=True,
    surfaces=("chat",),
    fields=[
        F("class_type", "string", required=True),
        F("description", "string", required=False),
        F("percentage", "number", required=False),
        F("notes", "string", required=False),
    ],
)
async def _chat_class_beneficiary(params: dict, ctx: ActionContext) -> dict:
    """Chat intent 'class_beneficiary': class_beneficiary."""
    # Route through the beneficiaries router's create_class_beneficiary
    # to enforce trust ownership verification and class_type validation
    # via the ClassBeneficiaryType enum. Adds audit logging.
    from routers.beneficiaries import create_class_beneficiary as _create_cb
    from models import ClassBeneficiaryCreate, ClassBeneficiaryType

    class_type_raw = params.get("class_type", "custom")
    try:
        class_type_enum = ClassBeneficiaryType(class_type_raw)
    except ValueError:
        class_type_enum = ClassBeneficiaryType.custom

    cb_create = ClassBeneficiaryCreate(
        trust_id=ctx.trust_id,
        class_type=class_type_enum,
        description=params.get("description", ""),
        percentage=float(params.get("percentage", 0)),
        notes=params.get("notes", ""),
    )

    user = ctx.user or await _user_doc(ctx.user_id)
    try:
        result = await _create_cb(data=cb_create, user=user)
        cb_id = result.get("class_beneficiary_id", "")
        # Audit log the class beneficiary creation
        from utils.audit import log_audit_event
        await log_audit_event(
            user_id=ctx.user_id,
            action="class_beneficiary_created_via_chat",
            entity_type="class_beneficiary",
            entity_id=cb_id,
            details={
                "trust_id": ctx.trust_id,
                "class_type": class_type_enum.value,
                "percentage": float(params.get("percentage", 0)),
                "source": "chat_assistant",
            },
        )
        # Update onboarding checklist
        try:
            from dependencies import auto_update_onboarding
            await auto_update_onboarding(ctx.user_id, ctx.trust_id)
        except Exception:
            pass
        return {"success": True, "record_id": cb_id, "endpoint": "class-beneficiaries", "action": "created"}
    except HTTPException as e:
        return {"success": False, "error": e.detail}
    except Exception as e:
        return {"success": False, "error": f"Failed to create class beneficiary: {str(e)}"}


@action(
    name="remove-class-beneficiary",
    description='Remove a class of beneficiaries.',
    write=True,
    trust_scoped=True,
    surfaces=("chat",),
    fields=[
        F("class_type", "string", required=True),
        F("reason", "string", required=False),
    ],
)
async def _chat_class_beneficiary_removal(params: dict, ctx: ActionContext) -> dict:
    """Chat intent 'class_beneficiary_removal': class_beneficiary_removal."""
    # Route through the beneficiaries router's delete_class_beneficiary
    # to enforce ownership verification (ctx.user_id match). Adds audit logging.
    from routers.beneficiaries import delete_class_beneficiary as _delete_cb

    class_type = params.get("class_type", "")
    existing = await db.class_beneficiaries.find_one({
        "trust_id": ctx.trust_id,
        "user_id": ctx.user_id,
        "class_type": class_type,
    })
    if not existing:
        return {"success": False, "error": f"Class beneficiary '{class_type}' not found for this trust."}

    user = ctx.user or await _user_doc(ctx.user_id)
    try:
        await _delete_cb(
            class_beneficiary_id=existing["class_beneficiary_id"],
            user=user,
        )
        # Audit log the class beneficiary removal
        from utils.audit import log_audit_event
        await log_audit_event(
            user_id=ctx.user_id,
            action="class_beneficiary_removed_via_chat",
            entity_type="class_beneficiary",
            entity_id=existing["class_beneficiary_id"],
            details={
                "trust_id": ctx.trust_id,
                "class_type": class_type,
                "reason": params.get("reason", ""),
                "source": "chat_assistant",
            },
        )
        return {"success": True, "record_id": existing["class_beneficiary_id"], "endpoint": "class-beneficiaries", "action": "removed"}
    except HTTPException as e:
        return {"success": False, "error": e.detail}
    except Exception as e:
        return {"success": False, "error": f"Failed to remove class beneficiary: {str(e)}"}

