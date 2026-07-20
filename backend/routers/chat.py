"""
Chat Router — Trust Assistant conversational AI endpoint

Provides POST /api/ai/chat for the Trust Assistant three-column page.
Non-streaming batch response for Sprint 1 (SSE streaming deferred).
"""
import json
import logging
import re
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from dependencies import get_current_user, get_subscription_state
from database import db
from chat_service import (
    classify_intent,
    extract_action_data,
    build_trust_context,
    generate_response,
    generate_response_stream,
    generate_action_card,
    build_citation_notes,
)
from action_registry import requires_confirmation, get_action, ACTION_REGISTRY

router = APIRouter(prefix="/ai", tags=["ai", "chat"])
logger = logging.getLogger(__name__)

# Rate limit config: handled by the middleware in security.py
# Chat-specific limits
MAX_MESSAGE_LENGTH = 5000
MAX_CONVERSATION_HISTORY = 50  # Max messages kept per conversation
CONVERSATION_TTL_DAYS = 180  # Auto-clean conversations older than 6 months


# ==================== PYDANTIC MODELS ====================

class ChatRequest(BaseModel):
    message: str = Field(..., max_length=MAX_MESSAGE_LENGTH, description="User's message to the Trust Assistant")
    conversation_id: Optional[str] = Field(None, description="Existing conversation ID to continue, or None for new conversation")
    trust_id: Optional[str] = Field(None, description="Trust ID to scope the conversation. Uses active trust if not specified.")


class ChatAction(BaseModel):
    """An action card presented to the user for review/approval"""
    type: str = Field(..., description="Action type: minutes_preview, distribution_preview, asset_preview, beneficiary_preview")
    data: dict = Field(default_factory=dict, description="Action data payload")
    requires_confirmation: bool = Field(default=True, description="Whether user confirmation is required before execution")
    confirmation_status: Optional[str] = Field(None, description="confirmation status: pending, approved, or rejected")
    warning_summary: Optional[str] = Field(None, description="Brief warning about this action, if any")


class ChatMessage(BaseModel):
    """A single message in the conversation"""
    role: str = Field(..., description="user or assistant")
    content: str = Field(..., description="Message text")
    action_card: Optional[ChatAction] = Field(None, description="Action card attached to this message, if any")
    citation_note: Optional[str] = Field(None, description="What the AI is basing this response on")
    unknown_note: Optional[str] = Field(None, description="What the AI doesn't know")
    caveat: Optional[str] = Field(None, description="Required caveat language")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ChatResponse(BaseModel):
    """Non-streaming chat response"""
    message: ChatMessage
    conversation_id: str
    trust_context_summary: Optional[dict] = Field(None, description="Snapshot data for the column UI")
    has_pending_actions: bool = Field(default=False, description="Whether the user has unreviewed actions")


class ConversationListItem(BaseModel):
    """Summary of a conversation for the history list"""
    conversation_id: str
    title: str
    message_count: int
    last_message_preview: str
    updated_at: str
    trust_id: Optional[str] = None


# ==================== UTILITY FUNCTIONS ====================

async def _generate_conversation_title(ai_client_module, user_message: str) -> str:
    """Generate a short title for a conversation from the first message."""
    from ai_client import ai_draft
    try:
        title_response = await ai_draft(
            system_prompt="Generate a short title (max 6 words) for this conversation starter. Respond with ONLY the title text, no quotes, no punctuation.",
            user_content=f"Conversation starts with: {user_message}",
            max_tokens=30,
            temperature=0.3,
        )
        if title_response and len(title_response.strip()) > 2:
            return title_response.strip().strip('"\'')
    except Exception as e:
        logger.warning(f"Title generation failed: {e}")
    return "Trust Assistant conversation"


async def _get_or_create_conversation(
    conversation_id: Optional[str],
    user_id: str,
    trust_id: str,
    first_message: str,
) -> tuple[str, bool]:
    """Get existing conversation or create a new one. Returns (conversation_id, is_new)."""
    if conversation_id:
        existing = await db.chat_conversations.find_one({
            "conversation_id": conversation_id,
            "user_id": user_id,
        })
        if existing:
            # Check if conversation has timed out (2 hours of inactivity = auto-thread)
            last_update = existing.get("updated_at", "")
            if last_update:
                try:
                    last_dt = datetime.fromisoformat(last_update)
                    if (datetime.now(timezone.utc) - last_dt) > timedelta(hours=2):
                        # Auto-thread: create new conversation, keep old one
                        new_id = f"conv_{uuid.uuid4().hex[:12]}"
                        title = await _generate_conversation_title(None, first_message)
                        now = datetime.now(timezone.utc).isoformat()
                        await db.chat_conversations.insert_one({
                            "conversation_id": new_id,
                            "user_id": user_id,
                            "trust_id": trust_id,
                            "title": title,
                            "messages": [],
                            "created_at": now,
                            "updated_at": now,
                        })
                        return new_id, True
                except (ValueError, TypeError):
                    pass
            return conversation_id, False

    # Create new conversation
    new_id = f"conv_{uuid.uuid4().hex[:12]}"
    title = await _generate_conversation_title(None, first_message)
    now = datetime.now(timezone.utc).isoformat()
    await db.chat_conversations.insert_one({
        "conversation_id": new_id,
        "user_id": user_id,
        "trust_id": trust_id,
        "title": title,
        "messages": [],
        "created_at": now,
        "updated_at": now,
    })
    return new_id, True


async def _get_active_trust(user_id: str, trust_id: Optional[str] = None) -> tuple[Optional[str], str]:
    """Get the active trust ID and name. Uses specified trust or user's most recent."""
    trust = None
    if trust_id:
        trust = await db.trusts.find_one(
            {"trust_id": trust_id, "user_id": user_id},
            {"_id": 0, "trust_id": 1, "name": 1}
        )
    if not trust:
        trust = await db.trusts.find_one(
            {"user_id": user_id},
            {"_id": 0, "trust_id": 1, "name": 1},
            sort=[("created_at", -1)]
        )
    if not trust:
        return None, "No trust found"
    return trust.get("trust_id"), trust.get("name", "Trust")


# ==================== ENDPOINTS ====================


@router.post("/chat")
async def chat(
    request: ChatRequest,
    user: dict = Depends(get_current_user),
):
    """
    Chat with the Trust Assistant.
    
    Non-streaming endpoint. Accepts a message and conversation context,
    returns the AI response with optional action cards.
    """
    user_id = user["user_id"]
    start_time = datetime.now(timezone.utc)

    # 1. Get active trust
    trust_id, trust_name = await _get_active_trust(user_id, request.trust_id)
    if not trust_id:
        raise HTTPException(status_code=404, detail="No trust found. Create a trust first to use the Trust Assistant.")

    # 2. Get or create conversation
    conv_id, is_new = await _get_or_create_conversation(
        request.conversation_id, user_id, trust_id, request.message
    )

    # 3. Load conversation history
    conversation = await db.chat_conversations.find_one(
        {"conversation_id": conv_id, "user_id": user_id}
    )
    messages = conversation.get("messages", []) if conversation else []
    history_for_ai = [{"role": m.get("role"), "content": m.get("content")} for m in messages[-20:]]

    # 4. Classify intent
    intent_result = await classify_intent(request.message, None)
    intent = intent_result.get("intent", "general_chat")
    entities = intent_result.get("entities", {})

    # 5. Build trust context
    trust_context = await build_trust_context(user_id, trust_id)

    # 6. Generate response
    ai_response = await generate_response(
        intent=intent,
        entities=entities,
        user_message=request.message,
        trust_context=trust_context,
        conversation_history=history_for_ai,
        ai_client_module=None,
    )

    # 7. Build action card if applicable
    action_card = None
    if ai_response.get("action_card") and ai_response["action_card"].get("type"):
        action_data = ai_response["action_card"]
        action_card = ChatAction(
            type=action_data.get("type", f"{intent}_preview"),
            data=action_data.get("data", {}),
            requires_confirmation=action_data.get("requires_confirmation", requires_confirmation(intent)),
            confirmation_status="pending",
        )

    # 8. Save user message
    user_msg_doc = ChatMessage(
        role="user",
        content=request.message,
    )

    # 9. Save assistant message
    assistant_msg_doc = ChatMessage(
        role="assistant",
        content=ai_response.get("message", "I'm not sure how to respond. Could you rephrase that?"),
        action_card=action_card,
        citation_note=ai_response.get("citation_note"),
        unknown_note=ai_response.get("unknown_note"),
        caveat=ai_response.get("caveat"),
    )

    # Update conversation in MongoDB
    now = datetime.now(timezone.utc).isoformat()
    await db.chat_conversations.update_one(
        {"conversation_id": conv_id, "user_id": user_id},
        {
            "$push": {
                "messages": {
                    "$each": [
                        user_msg_doc.model_dump(),
                        assistant_msg_doc.model_dump(),
                    ]
                }
            },
            "$set": {"updated_at": now},
            "$inc": {"message_count": 2},
        }
    )

    # 10. Build trust context summary for the Snapshot column
    ctx = trust_context
    trust_context_summary = {
        "trust_name": ctx.get("trust", {}).get("name", trust_name),
        "health_score": ctx.get("health_score", {}).get("total", 0),
        "health_color": ctx.get("health_score", {}).get("color", "red"),
        "upcoming_deadlines": ctx.get("upcoming_deadlines", [])[:3],
        "pending_items": ctx.get("pending_items", [])[:3],
        "beneficiary_count": len(ctx.get("beneficiaries", [])),
    }

    # 11. Check for pending actions (any unapproved action cards)
    pending_count = await db.chat_conversations.count_documents({
        "user_id": user_id,
        "messages": {
            "$elemMatch": {
                "role": "assistant",
                "action_card.confirmation_status": "pending",
            }
        },
    })

    response_time = (datetime.now(timezone.utc) - start_time).total_seconds()
    logger.info(
        f"CHAT | user={user_id} | trust={trust_id} | conversation={conv_id} | "
        f"intent={intent} | response_time={response_time:.2f}s | "
        f"has_action={'yes' if action_card else 'no'}"
    )

    return ChatResponse(
        message=assistant_msg_doc,
        conversation_id=conv_id,
        trust_context_summary=trust_context_summary,
        has_pending_actions=pending_count > 0,
    )


@router.get("/chat/conversations")
async def list_conversations(
    trust_id: Optional[str] = None,
    limit: int = 20,
    user: dict = Depends(get_current_user),
):
    """List recent conversations for the user."""
    query = {"user_id": user["user_id"]}
    if trust_id:
        query["trust_id"] = trust_id

    # Fetch conversations — include messages with $slice to get last message for preview
    # Note: message_count here will be approximate (1 if has messages, 0 if empty)
    # The total message count is stored on the conversation document
    convs = await db.chat_conversations.find(
        query,
        {"_id": 0, "conversation_id": 1, "title": 1, "updated_at": 1, "trust_id": 1, "messages": {"$slice": -1}}
    ).sort("updated_at", -1).limit(min(limit, 50)).to_list(limit)

    result = []
    for c in convs:
        messages = c.get("messages", [])
        last_msg = ""
        if messages:
            last_msg = messages[-1].get("content", "")[:80]

        result.append({
            "conversation_id": c["conversation_id"],
            "title": c.get("title", "Conversation"),
            "message_count": c.get("message_count", len(messages) if messages else 0),
            "last_message_preview": last_msg,
            "updated_at": c.get("updated_at", ""),
            "trust_id": c.get("trust_id"),
        })

    return {"conversations": result}


@router.get("/chat/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    user: dict = Depends(get_current_user),
):
    """Get a full conversation by ID."""
    conv = await db.chat_conversations.find_one(
        {"conversation_id": conversation_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.delete("/chat/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user: dict = Depends(get_current_user),
):
    """Delete a conversation."""
    result = await db.chat_conversations.delete_one({
        "conversation_id": conversation_id,
        "user_id": user["user_id"],
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"message": "Conversation deleted"}


class ConfirmActionRequest(BaseModel):
    action: str = Field(..., description="Action to take: approve, reject, or edit")
    edited_data: Optional[dict] = Field(None, description="Updated data if action=edit")


# Maps action_card type to the backend write endpoint and field mappings
ACTION_EXECUTION_MAP = {
    "distribution_preview": {
        "endpoint_type": "distribution",
        "field_map": {
            "beneficiary_name": "beneficiary_name",
            "amount": "amount",
            "purpose": "purpose_classification",
            "date": "date",
            "from_account": "notes",
        },
    },
    "asset_preview": {
        "endpoint_type": "asset",
        "field_map": {
            "asset_type": "category",
            "description": "description",
            "value": "approximate_value",
            "date_acquired": "date_conveyed",
            "ownership_pct": "notes",
        },
    },
    "contribute_asset_preview": {
        "endpoint_type": "contribute_asset",
        "field_map": {
            "asset_type": "category",
            "description": "description",
            "value": "approximate_value",
            "date_acquired": "date_conveyed",
            "meeting_date": "meeting_date",
            "participants": "participants_text",
            "grantor_name": "grantor_name",
            "ownership_pct": "notes",
        },
    },
    "asset_update_preview": {
        "endpoint_type": "asset_update",
        "field_map": {
            "asset_description": "asset_description",
            "new_value": "new_value",
            "new_description": "new_description",
            "valuation_date": "valuation_date",
            "notes": "notes",
        },
    },
    "minutes_preview": {
        "endpoint_type": "minutes",
        "field_map": {
            "minutes_type": "minutes_type",
            "meeting_date": "meeting_date",
            "participants": "participants_text",
            "decisions": "decisions_text",
            "trust_name": "notes",
        },
    },
    "beneficiary_preview": {
        "endpoint_type": "beneficiary",
        "field_map": {
            "name": "holder_name",
            "email": "email",
            "phone": "phone",
            "allocation_pct": "units",
        },
    },
    "beneficiary_update_preview": {
        "endpoint_type": "beneficiary_update",
        "field_map": {
            "beneficiary_name": "holder_name",
            "email": "email",
            "phone": "phone",
            "notes": "notes",
        },
    },
    "beneficiary_removal_preview": {
        "endpoint_type": "beneficiary_removal",
        "field_map": {
            "beneficiary_name": "holder_name",
            "reason": "reason",
        },
    },
    "certificate_preview": {
        "endpoint_type": "send_certificate",
        "field_map": {
            "beneficiary_name": "holder_name",
            "email": "email",
            "notes": "notes",
        },
    },
    "distribution_cancel_preview": {
        "endpoint_type": "distribution_cancel",
        "field_map": {
            "beneficiary_name": "beneficiary_name",
            "amount": "amount",
            "date": "date",
        },
    },
    "document_upload_preview": {
        "endpoint_type": "document_upload",
        "field_map": {
            "title": "title",
            "category": "category",
            "notes": "notes",
        },
    },
    "compensation_plan_preview": {
        "endpoint_type": "compensation_plan",
        "field_map": {
            "trustee_name": "trustee_name",
            "annual_amount": "annual_amount",
            "fee_type": "fee_type",
            "effective_date": "effective_date",
            "role": "role",
        },
    },
    "compensation_payment_preview": {
        "endpoint_type": "compensation_payment",
        "field_map": {
            "trustee_name": "trustee_name",
            "amount": "amount",
            "date": "date",
            "classification_text": "classification_text",
        },
    },
    "investment_preview": {
        "endpoint_type": "investment",
        "field_map": {
            "asset_name": "asset_name",
            "asset_type": "asset_type",
            "cost_basis": "cost_basis",
            "purchase_date": "purchase_date",
            "current_value": "current_value",
            "quantity": "quantity",
            "unit": "unit",
            "custodian": "custodian",
            "notes": "notes",
        },
    },
    "task_preview": {
        "endpoint_type": "task",
        "field_map": {
            "task_type": "task_type",
            "description": "description",
            "due_date": "due_date",
            "priority": "priority",
        },
    },
    "transaction_preview": {
        "endpoint_type": "transaction",
        "field_map": {
            "type": "transaction_type",
            "amount": "amount",
            "category": "category",
            "date": "date",
            "description": "description",
        },
    },
    "settings_update_preview": {
        "endpoint_type": "settings_update",
        "field_map": {
            "field": "field",
            "value": "value",
        },
    },
    "entity_preview": {
        "endpoint_type": "entity",
        "field_map": {
            "name": "name",
            "entity_type": "entity_type",
            "legal_name": "legal_name",
            "governing_law": "governing_law",
            "ein": "ein",
            "formation_date": "formation_date",
            "trustee_names": "trustee_names",
            "member_names": "member_names",
            "manager_names": "manager_names",
        },
    },
    "alert_dismiss": {
        "endpoint_type": "alert_dismiss",
        "field_map": {
            "criterion_name": "criterion_name",
        },
    },
    "class_beneficiary_preview": {
        "endpoint_type": "class_beneficiary",
        "field_map": {
            "class_type": "class_type",
            "description": "description",
            "percentage": "percentage",
            "notes": "notes",
        },
    },
    "class_beneficiary_removal_preview": {
        "endpoint_type": "class_beneficiary_removal",
        "field_map": {
            "class_type": "class_type",
            "reason": "reason",
        },
    },
}


async def _execute_approved_action(
    action_card: dict,
    user_id: str,
    trust_id: str,
) -> dict:
    """
    Execute the real backend write operation for an approved action card.
    Creates the corresponding record in the database.
    """
    card_type = action_card.get("type", "")
    action_data = action_card.get("data", {})
    
    # Write-access gate: check subscription state before executing any action
    sub_state = await get_subscription_state(user_id)
    if sub_state.is_read_only:
        return {"success": False, "error": "Read-only mode: your subscription does not allow write actions."}
    
    # Normalize: intent classifier sends log_minutes → log_minutes_preview
    TYPE_ALIASES = {
        "log_minutes_preview": "minutes_preview",
        "create_distribution_preview": "distribution_preview",
        "record_compensation_payment_preview": "compensation_payment_preview",
        "setup_compensation_preview": "compensation_plan_preview",
        "add_investment_preview": "investment_preview",
    }
    card_type = TYPE_ALIASES.get(card_type, card_type)
    
    mapping = ACTION_EXECUTION_MAP.get(card_type)

    if not mapping:
        return {"success": False, "error": f"Unknown action type: {card_type}"}

    endpoint_type = mapping["endpoint_type"]
    field_map = mapping["field_map"]

    # Map action_card fields to backend model fields
    mapped_data = {}
    for src_key, dst_key in field_map.items():
        if src_key in action_data and action_data[src_key] is not None:
            mapped_data[dst_key] = action_data[src_key]

    # Always include trust_id and user_id
    mapped_data["trust_id"] = trust_id

    try:
        if endpoint_type == "distribution":
            # Route through the real distribution router to ensure validation,
            # activity logging, onboarding updates, and email notifications.
            from routers.distributions import create_distribution as _create_dist
            from models import DistributionCreate, PurposeClassification
            from fastapi import BackgroundTasks

            purpose = mapped_data.pop("purpose_classification", "other")
            try:
                purpose_enum = PurposeClassification(purpose)
            except ValueError:
                purpose_enum = PurposeClassification.other

            dist_create = DistributionCreate(
                trust_id=trust_id,
                beneficiary_name=mapped_data.get("beneficiary_name", "Unknown"),
                amount=float(mapped_data.get("amount", 0)),
                date=mapped_data.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
                purpose_classification=purpose_enum,
                notes=mapped_data.get("notes", ""),
                is_benevolence=False,
            )
            # Fetch user dict for the router call
            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            if not user_doc:
                user_doc = {"user_id": user_id, "email": "", "name": ""}
            result = await _create_dist(
                dist=dist_create,
                background_tasks=BackgroundTasks(),
                user=user_doc,
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

        elif endpoint_type == "asset":
            # Route through the real schedule_a router to ensure validation.
            from routers.schedule_a import create_schedule_a_item as _create_asset
            from models import ScheduleAItemCreate, AssetCategory
            from fastapi import BackgroundTasks

            category = mapped_data.pop("category", "other_property")
            try:
                category_enum = AssetCategory(category)
            except ValueError:
                category_enum = AssetCategory.other_property

            asset_create = ScheduleAItemCreate(
                trust_id=trust_id,
                category=category_enum,
                description=mapped_data.get("description", ""),
                approximate_value=mapped_data.get("approximate_value"),
                date_conveyed=mapped_data.get("date_conveyed", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
                notes=mapped_data.get("notes", ""),
            )
            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            if not user_doc:
                user_doc = {"user_id": user_id, "email": "", "name": ""}
            result = await _create_asset(item=asset_create, user=user_doc)
            # Update onboarding (schedule_a router doesn't call auto_update_onboarding)
            try:
                from dependencies import auto_update_onboarding
                await auto_update_onboarding(user_id, trust_id)
            except Exception:
                pass
            return {"success": True, "record_id": result.item_id, "endpoint": "schedule-a"}

        elif endpoint_type == "asset_update":
            # Route through the schedule_a router's update_schedule_a_item to
            # enforce ownership verification and validation. Adds audit logging
            # for the valuation update.
            from routers.schedule_a import update_schedule_a_item as _update_asset
            from models import ScheduleAItemUpdate

            # Look up the existing asset by description (fuzzy match)
            asset_desc = mapped_data.get("asset_description", "")
            if not asset_desc:
                return {"success": False, "error": "Asset description is required to identify which asset to update."}

            # Try exact match first, then partial match
            existing = await db.schedule_a_items.find_one({
                "trust_id": trust_id,
                "user_id": user_id,
                "status": "active",
                "description": {"$regex": re.escape(asset_desc), "$options": "i"}
            })

            if not existing:
                # Try broader partial match
                existing = await db.schedule_a_items.find_one({
                    "trust_id": trust_id,
                    "user_id": user_id,
                    "status": "active",
                    "description": {"$regex": re.escape(asset_desc.split()[0]), "$options": "i"}
                })

            if not existing:
                return {"success": False, "error": f"Could not find an active asset matching '{asset_desc}'. Please check the description and try again."}

            # Build the ScheduleAItemUpdate model with only provided fields
            update_kwargs = {}
            if mapped_data.get("new_value") is not None:
                update_kwargs["approximate_value"] = float(mapped_data["new_value"])
            if mapped_data.get("new_description"):
                update_kwargs["description"] = mapped_data["new_description"]
            if mapped_data.get("notes"):
                update_kwargs["notes"] = mapped_data["notes"]

            # Always record the valuation date via notes append
            valuation_date = mapped_data.get("valuation_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if "notes" in update_kwargs:
                update_kwargs["notes"] = f"{update_kwargs['notes']} | Valuation date: {valuation_date}"
            else:
                update_kwargs["notes"] = f"Valuation date: {valuation_date}"

            if not update_kwargs:
                return {"success": False, "error": "No update fields provided."}

            asset_update = ScheduleAItemUpdate(**update_kwargs)

            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            if not user_doc:
                user_doc = {"user_id": user_id, "email": "", "name": ""}
            try:
                await _update_asset(
                    item_id=existing["item_id"],
                    update=asset_update,
                    user=user_doc,
                )
                # Audit log the asset valuation update
                from utils.audit import log_audit_event
                await log_audit_event(
                    user_id=user_id,
                    action="asset_updated",
                    entity_type="schedule_a_item",
                    entity_id=existing["item_id"],
                    details={
                        "trust_id": trust_id,
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

        elif endpoint_type == "minutes":
            # Route through the real minutes router to ensure validation,
            # onboarding updates, and email notifications.
            # Fix 4b: chat minutes must be status="draft", not "finalized".
            from routers.minutes import create_minutes as _create_minutes
            from models import MinutesCreate, MinutesType
            from fastapi import BackgroundTasks

            minutes_type_val = mapped_data.pop("minutes_type", "general")
            try:
                minutes_type_enum = MinutesType(minutes_type_val)
            except ValueError:
                minutes_type_enum = MinutesType.general

            participants_text = mapped_data.get("participants_text", "")
            if isinstance(participants_text, list):
                participants_text = ", ".join(participants_text)

            decisions_text = mapped_data.get("decisions_text", "")
            if isinstance(decisions_text, list):
                decisions_text = "; ".join(decisions_text)

            minutes_create = MinutesCreate(
                trust_id=trust_id,
                minutes_type=minutes_type_enum,
                meeting_date=mapped_data.get("meeting_date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
                participants_text=participants_text,
                decisions_text=decisions_text,
                status="draft",  # Fix 4b: draft, not finalized
            )
            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            if not user_doc:
                user_doc = {"user_id": user_id, "email": "", "name": ""}
            result = await _create_minutes(
                minutes=minutes_create,
                background_tasks=BackgroundTasks(),
                user=user_doc,
            )
            # Onboarding update: minutes router only calls auto_update_onboarding
            # for finalized minutes, but chat creates drafts. Update here so
            # the onboarding checklist reflects that minutes were generated.
            try:
                from dependencies import auto_update_onboarding
                await auto_update_onboarding(user_id, trust_id)
            except Exception:
                pass
            return {
                "success": True,
                "record_id": result.minutes_id,
                "endpoint": "minutes",
                "status": "draft",
                "review_link": f"/minutes/{result.minutes_id}/edit",
            }

        elif endpoint_type == "contribute_asset":
            # Combined action: create a Schedule A item AND an acceptance-of-property
            # minutes record in one transactional flow.
            from routers.schedule_a import create_schedule_a_item as _create_asset
            from routers.minutes import create_minutes as _create_minutes, generate_template_document
            from models import ScheduleAItemCreate, AssetCategory, MinutesCreate, MinutesType
            from fastapi import BackgroundTasks

            # --- 0) Deduplication check — reject if an active asset with the same description already exists ---
            property_description = mapped_data.get("description", "")
            if property_description:
                existing_asset = await db.schedule_a_items.find_one({
                    "trust_id": trust_id,
                    "user_id": user_id,
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
            category = mapped_data.pop("category", "other_property")
            try:
                category_enum = AssetCategory(category)
            except ValueError:
                category_enum = AssetCategory.other_property

            # Build notes: include ownership_pct as a meaningful note if present
            notes = mapped_data.get("notes", "")
            ownership_pct = mapped_data.get("ownership_pct")
            if ownership_pct is not None:
                ownership_note = f"Ownership: {ownership_pct}%"
                notes = f"{notes}\n{ownership_note}".strip() if notes else ownership_note

            asset_create = ScheduleAItemCreate(
                trust_id=trust_id,
                category=category_enum,
                description=property_description,
                approximate_value=mapped_data.get("approximate_value"),
                date_conveyed=mapped_data.get("date_conveyed", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
                notes=notes,
            )
            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            if not user_doc:
                user_doc = {"user_id": user_id, "email": "", "name": ""}
            asset_result = await _create_asset(item=asset_create, user=user_doc)
            asset_id = asset_result.item_id

            # --- 2) Create the acceptance-of-property minutes record ---
            participants_text = mapped_data.get("participants_text", "")
            if isinstance(participants_text, list):
                participants_text = ", ".join(participants_text)

            meeting_date = mapped_data.get("meeting_date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
            grantor_name = mapped_data.get("grantor_name", "")
            property_value = mapped_data.get("approximate_value")
            conveyance_date = mapped_data.get("date_conveyed", meeting_date)

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
                trust_id=trust_id,
                minutes_type=MinutesType.general,
                meeting_date=meeting_date,
                participants_text=participants_text,
                decisions_text=decisions_text,
                status="draft",
                template_type="acceptance_of_property",
                template_data=template_data,
            )

            # Fetch the trust document for generate_template_document
            trust_doc = await db.trusts.find_one({"trust_id": trust_id, "user_id": user_id}, {"_id": 0})

            try:
                minutes_result = await _create_minutes(
                    minutes=minutes_create,
                    background_tasks=BackgroundTasks(),
                    user=user_doc,
                )
            except Exception as minutes_exc:
                # FIX 2 — Partial failure rollback: if minutes creation fails after
                # the Schedule A item was already created, delete the orphaned item
                # so we don't leave a dangling asset with no acceptance minutes.
                logger.error(f"contribute_asset: minutes creation failed, rolling back Schedule A item {asset_id}: {minutes_exc}")
                try:
                    await db.schedule_a_items.delete_one({"item_id": asset_id, "user_id": user_id})
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
                        await db.minutes_records.update_one(
                            {"minutes_id": minutes_result.minutes_id},
                            {"$set": {"decisions_text": generated_text}},
                        )
            except Exception as gen_exc:
                logger.error(f"contribute_asset: failed to generate template document for minutes {minutes_result.minutes_id}: {gen_exc}")
                # Non-fatal — the minutes record still has the dynamic decisions_text fallback

            # FIX 3 — Set minutes_ref on the Schedule A item pointing to the minutes record
            try:
                await db.schedule_a_items.update_one(
                    {"item_id": asset_id, "user_id": user_id},
                    {"$set": {"minutes_ref": minutes_result.minutes_id}},
                )
            except Exception as ref_exc:
                logger.error(f"contribute_asset: failed to set minutes_ref on Schedule A item {asset_id}: {ref_exc}")
                # Non-fatal — both records exist but the link is missing

            # --- 3) Update onboarding after both records are created ---
            try:
                from dependencies import auto_update_onboarding
                await auto_update_onboarding(user_id, trust_id)
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

        elif endpoint_type == "beneficiary":
            # Route through the real trust_units router to ensure validation
            # (units overflow check, fractional validation, certificate numbering).
            from routers.trust_units import create_unit_certificate as _create_cert
            from models import TrustUnitCertificateCreate

            # Get unit settings for the trust to convert percentage to units
            settings = await db.trust_units_settings.find_one({"trust_id": trust_id})
            total_authorized = settings.get("total_authorized_units", 0) if settings else 0

            allocation_pct = mapped_data.get("units", 0)
            if total_authorized > 0 and isinstance(allocation_pct, (int, float)) and allocation_pct < 100:
                units = max(1, round(total_authorized * allocation_pct / 100))
            elif isinstance(allocation_pct, (int, float)):
                units = int(allocation_pct) if allocation_pct > 0 else 1
            else:
                units = 1

            cert_create = TrustUnitCertificateCreate(
                trust_id=trust_id,
                holder_name=mapped_data.get("holder_name", "Unknown"),
                holder_type=mapped_data.get("holder_type", "individual"),
                units=float(units),
                issue_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                email=mapped_data.get("email"),
                phone=mapped_data.get("phone"),
            )
            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            if not user_doc:
                user_doc = {"user_id": user_id, "email": "", "name": ""}
            try:
                result = await _create_cert(certificate=cert_create, user=user_doc)
                # Update onboarding checklist
                try:
                    from dependencies import auto_update_onboarding
                    await auto_update_onboarding(user_id, trust_id)
                except Exception:
                    pass
                return {"success": True, "record_id": result.certificate_id, "endpoint": "trust-units/certificates"}
            except HTTPException as e:
                return {"success": False, "error": e.detail}
            except Exception as e:
                return {"success": False, "error": f"Failed to create beneficiary: {str(e)}"}

        elif endpoint_type == "beneficiary_update":
            # Route through the beneficiaries router's update_beneficiary to
            # enforce ownership verification (certificate must be active and
            # belong to the user). Adds audit logging for the change.
            from routers.beneficiaries import update_beneficiary as _update_bene
            from models import BeneficiaryUpdate

            # Find the existing beneficiary certificate by holder_name (case-insensitive)
            existing = await db.trust_unit_certificates.find_one({
                "trust_id": trust_id,
                "user_id": user_id,
                "holder_name": {"$regex": f"^{re.escape(mapped_data.get('holder_name', ''))}$", "$options": "i"},
                "status": "active",
            })
            if not existing:
                return {"success": False, "error": f"Beneficiary '{mapped_data.get('holder_name', '')}' not found. Use 'Create Beneficiary' to add them first."}

            # Build the BeneficiaryUpdate model with only provided fields
            update_kwargs = {}
            if mapped_data.get("email"):
                update_kwargs["email"] = mapped_data["email"]
            if mapped_data.get("phone"):
                update_kwargs["phone"] = mapped_data["phone"]
            if mapped_data.get("notes"):
                update_kwargs["notes"] = mapped_data["notes"]

            if not update_kwargs:
                return {"success": False, "error": "No update fields provided."}

            bene_update = BeneficiaryUpdate(**update_kwargs)

            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            if not user_doc:
                user_doc = {"user_id": user_id, "email": "", "name": ""}
            try:
                await _update_beneficiary(
                    beneficiary_id=existing["certificate_id"],
                    data=bene_update,
                    user=user_doc,
                )
                # Audit log the beneficiary update
                from utils.audit import log_audit_event
                await log_audit_event(
                    user_id=user_id,
                    action="beneficiary_updated",
                    entity_type="trust_unit_certificate",
                    entity_id=existing["certificate_id"],
                    details={
                        "trust_id": trust_id,
                        "holder_name": existing.get("holder_name", ""),
                        "fields_changed": list(update_kwargs.keys()),
                    },
                )
                return {"success": True, "record_id": existing["certificate_id"], "endpoint": "beneficiaries", "action": "updated"}
            except HTTPException as e:
                return {"success": False, "error": e.detail}
            except Exception as e:
                return {"success": False, "error": f"Failed to update beneficiary: {str(e)}"}

        elif endpoint_type == "beneficiary_removal":
            # Route through the beneficiaries router's delete_beneficiary to
            # enforce ownership verification and preserve the audit trail
            # (soft-delete: marks certificate inactive rather than deleting).
            from routers.beneficiaries import delete_beneficiary as _delete_bene

            existing = await db.trust_unit_certificates.find_one({
                "trust_id": trust_id,
                "user_id": user_id,
                "holder_name": {"$regex": f"^{re.escape(mapped_data.get('holder_name', ''))}$", "$options": "i"},
                "status": "active",
            })
            if not existing:
                return {"success": False, "error": f"Beneficiary '{mapped_data.get('holder_name', '')}' not found."}

            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            if not user_doc:
                user_doc = {"user_id": user_id, "email": "", "name": ""}
            try:
                await _delete_beneficiary(
                    beneficiary_id=existing["certificate_id"],
                    user=user_doc,
                )
                # Audit log the beneficiary removal
                from utils.audit import log_audit_event
                await log_audit_event(
                    user_id=user_id,
                    action="beneficiary_removed",
                    entity_type="trust_unit_certificate",
                    entity_id=existing["certificate_id"],
                    details={
                        "trust_id": trust_id,
                        "holder_name": existing.get("holder_name", ""),
                        "reason": mapped_data.get("reason", ""),
                    },
                )
                return {"success": True, "record_id": existing["certificate_id"], "endpoint": "beneficiaries", "action": "removed"}
            except HTTPException as e:
                return {"success": False, "error": e.detail}
            except Exception as e:
                return {"success": False, "error": f"Failed to remove beneficiary: {str(e)}"}

        elif endpoint_type == "send_certificate":
            # Route through the beneficiaries router's send_beneficiary_certificate
            # to enforce trust ownership verification, certificate lookup, email
            # validation, and communication logging. Adds audit logging.
            from routers.beneficiaries import send_beneficiary_certificate as _send_cert
            from models import SendCertificateRequest

            holder_name = mapped_data.get("holder_name", "")
            override_email = mapped_data.get("email", "")

            cert_req = SendCertificateRequest(
                trust_id=trust_id,
                beneficiary_name=holder_name,
                email=override_email if override_email else None,
                notes=mapped_data.get("notes"),
            )

            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            if not user_doc:
                user_doc = {"user_id": user_id, "email": "", "name": ""}
            try:
                result = await _send_cert(data=cert_req, user=user_doc)
                # Audit log the certificate send
                from utils.audit import log_audit_event
                await log_audit_event(
                    user_id=user_id,
                    action="certificate_sent_via_chat",
                    entity_type="trust_unit_certificate",
                    entity_id=result.get("certificate_id", ""),
                    details={
                        "trust_id": trust_id,
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

        elif endpoint_type == "distribution_cancel":
            # Route through the distributions router's delete_distribution to
            # enforce ownership verification and audit logging. The chat "cancel"
            # action maps to the canonical delete endpoint, which logs to the
            # audit trail via log_audit_event.
            from routers.distributions import delete_distribution as _delete_dist

            # Find matching distribution by beneficiary name + optional amount/date
            query = {"trust_id": trust_id, "user_id": user_id}
            if mapped_data.get("beneficiary_name"):
                query["beneficiary_name"] = {"$regex": f"^{mapped_data['beneficiary_name']}$", "$options": "i"}
            if mapped_data.get("amount"):
                query["amount"] = float(mapped_data["amount"])

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

            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            if not user_doc:
                user_doc = {"user_id": user_id, "email": "", "name": ""}
            try:
                await _delete_dist(distribution_id=existing["distribution_id"], user=user_doc)
                return {"success": True, "record_id": existing["distribution_id"], "endpoint": "distributions", "action": "cancelled"}
            except HTTPException as e:
                return {"success": False, "error": e.detail}
            except Exception as e:
                return {"success": False, "error": f"Failed to cancel distribution: {str(e)}"}

        elif endpoint_type == "document_upload":
            # Route through the real vault router to ensure validation
            # and onboarding updates.
            from routers.vault import add_document as _add_doc, DocumentCreate

            # Validate category against vault's DOC_CATEGORIES
            category = mapped_data.get("category", "other")
            try:
                doc_create = DocumentCreate(
                    title=mapped_data.get("title", "Untitled Document"),
                    category=category,
                    description=mapped_data.get("notes", ""),
                    storage_provider="local_server",
                )
            except Exception as ve:
                return {"success": False, "error": f"Invalid document data: {str(ve)}"}

            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            if not user_doc:
                user_doc = {"user_id": user_id, "email": "", "name": ""}
            try:
                result = await _add_doc(trust_id=trust_id, doc=doc_create, user=user_doc)
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

        elif endpoint_type == "compensation_plan":
            # Route through the real compensation router to ensure validation,
            # primary-plan logic, and onboarding updates.
            from routers.compensation import create_comp_plan as _create_plan
            from models import CompensationPlanCreate

            annual_amount = float(mapped_data.get("annual_amount", 0))
            effective_date = mapped_data.get("effective_date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

            plan_create = CompensationPlanCreate(
                trust_id=trust_id,
                trustee_name=mapped_data.get("trustee_name", ""),
                role=mapped_data.get("role", ""),
                annual_amount=annual_amount,
                annual_approved_amount=annual_amount,
                fee_type=mapped_data.get("fee_type", "fixed"),
                effective_date=effective_date,
                notes=mapped_data.get("notes", ""),
            )
            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            if not user_doc:
                user_doc = {"user_id": user_id, "email": "", "name": ""}
            try:
                result = await _create_plan(plan=plan_create, user=user_doc)
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

        elif endpoint_type == "compensation_payment":
            # Route through the real compensation router to ensure validation,
            # exceeds-plan detection, and onboarding updates.
            from routers.compensation import create_comp_payment as _create_payment
            from models import CompensationPaymentCreate

            payment_date = mapped_data.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
            payment_amount = float(mapped_data.get("amount", 0))

            payment_create = CompensationPaymentCreate(
                trust_id=trust_id,
                amount=payment_amount,
                date=payment_date,
                classification_text=mapped_data.get("classification_text", ""),
                trustee_name=mapped_data.get("trustee_name") or None,
            )
            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            if not user_doc:
                user_doc = {"user_id": user_id, "email": "", "name": ""}
            try:
                result = await _create_payment(payment=payment_create, user=user_doc)
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

        elif endpoint_type == "investment":
            # Route through the real investments router to ensure validation.
            from routers.investments import create_investment as _create_inv

            cost_basis = float(mapped_data.get("cost_basis", 0))
            current_value = float(mapped_data.get("current_value", 0)) if mapped_data.get("current_value") else cost_basis
            investment_dict = {
                "asset_name": mapped_data.get("asset_name", ""),
                "asset_type": mapped_data.get("asset_type", "other"),
                "purchase_date": mapped_data.get("purchase_date"),
                "cost_basis": cost_basis,
                "current_value": current_value,
                "quantity": float(mapped_data.get("quantity", 1)) if mapped_data.get("quantity") else 1,
                "unit": mapped_data.get("unit", "shares"),
                "custodian": mapped_data.get("custodian"),
                "notes": mapped_data.get("notes"),
            }
            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            if not user_doc:
                user_doc = {"user_id": user_id, "email": "", "name": ""}
            try:
                result = await _create_inv(trust_id=trust_id, investment=investment_dict, user=user_doc)
                # Update onboarding checklist (investments router doesn't call auto_update_onboarding)
                try:
                    from dependencies import auto_update_onboarding
                    await auto_update_onboarding(user_id, trust_id)
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

        elif endpoint_type == "task":
            # Route through the real tasks router to ensure validation,
            # checklist template population, and onboarding updates.
            from routers.tasks import create_task as _create_task
            from models import GovernanceTaskCreate, TaskType

            task_type_val = mapped_data.get("task_type", "custom")
            try:
                task_type_enum = TaskType(task_type_val)
            except ValueError:
                task_type_enum = TaskType.custom

            task_create = GovernanceTaskCreate(
                trust_id=trust_id,
                task_type=task_type_enum,
                due_date=mapped_data.get("due_date", ""),
                description=mapped_data.get("description", ""),
            )
            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            if not user_doc:
                user_doc = {"user_id": user_id, "email": "", "name": ""}
            try:
                result = await _create_task(task=task_create, user=user_doc)
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

        elif endpoint_type == "transaction":
            # Route through the real transactions router to ensure validation,
            # audit logging, and alert detection.
            from routers.transactions import create_transaction as _create_txn
            from models import TransactionCreate, TransactionDirection, GovernanceClassification

            # The transactions router requires an entity_id — look up the
            # first entity for this trust (typically the Trust entity itself).
            entity = await db.entities.find_one(
                {"trust_id": trust_id, "user_id": user_id},
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
            raw_type = mapped_data.get("transaction_type", "expense")
            if raw_type in ("income", "deposit", "inflow"):
                direction_enum = TransactionDirection.inflow
                classification_enum = GovernanceClassification.capital_contribution
            else:
                direction_enum = TransactionDirection.outflow
                classification_enum = GovernanceClassification.operational_expense

            # Map chat's "category" if it matches a known GovernanceClassification
            raw_category = mapped_data.get("category", "")
            if raw_category:
                try:
                    classification_enum = GovernanceClassification(raw_category)
                except ValueError:
                    pass  # keep the default

            txn_create = TransactionCreate(
                trust_id=trust_id,
                entity_id=entity_id,
                date=mapped_data.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
                amount=float(mapped_data.get("amount", 0)),
                direction=direction_enum,
                governance_classification=classification_enum,
                purpose_memo=mapped_data.get("description", ""),
            )
            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            if not user_doc:
                user_doc = {"user_id": user_id, "email": "", "name": ""}
            try:
                result = await _create_txn(txn=txn_create, user=user_doc)
                # Update onboarding checklist (transactions router doesn't call auto_update_onboarding)
                try:
                    from dependencies import auto_update_onboarding
                    await auto_update_onboarding(user_id, trust_id)
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

        elif endpoint_type == "entity":
            # Route through the real entities router to ensure validation
            # and onboarding updates.
            from routers.entities import create_entity as _create_entity
            from models import EntityCreate, EntityType

            # Validate entity_type — must be one of the allowed values
            raw_type = mapped_data.get("entity_type", "Trust")
            entity_type_enum = None
            for et in EntityType:
                if raw_type and raw_type.lower() == et.value.lower():
                    entity_type_enum = et
                    break
            if not entity_type_enum:
                entity_type_enum = EntityType.trust  # default to Trust if unrecognized

            name = mapped_data.get("name", "")
            entity_create = EntityCreate(
                trust_id=trust_id,
                name=name,
                entity_type=entity_type_enum,
                legal_name=mapped_data.get("legal_name", name),
                formation_date=mapped_data.get("formation_date"),
                governing_law=mapped_data.get("governing_law", ""),
                ein=mapped_data.get("ein"),
                trustee_names=mapped_data.get("trustee_names", ""),
                member_names=mapped_data.get("member_names", ""),
                manager_names=mapped_data.get("manager_names", ""),
            )
            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            if not user_doc:
                user_doc = {"user_id": user_id, "email": "", "name": ""}
            try:
                result = await _create_entity(entity=entity_create, user=user_doc)
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

        elif endpoint_type == "settings_update":
            # Route through the trusts router's update_trust to enforce
            # ownership verification, field validation (EIN format, tax year
            # end), jurisdiction/state_code auto-sync, and audit logging
            # (update_trust calls log_audit_event internally).
            from routers.trusts import update_trust as _update_trust
            from models import TrustUpdate

            field = mapped_data.get("field", "")
            value = mapped_data.get("value", "")
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

            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            if not user_doc:
                user_doc = {"user_id": user_id, "email": "", "name": ""}
            try:
                await _update_trust(
                    trust_id=trust_id,
                    update=trust_update,
                    user=user_doc,
                )
                # update_trust already logs to audit trail via log_audit_event,
                # but we add a chat-specific audit entry for traceability.
                from utils.audit import log_audit_event
                await log_audit_event(
                    user_id=user_id,
                    action="trust_settings_updated_via_chat",
                    entity_type="trust",
                    entity_id=trust_id,
                    details={
                        "field_changed": db_field,
                        "source": "chat_assistant",
                    },
                )
                return {"success": True, "record_id": trust_id, "endpoint": "trusts", "action": "updated", "field": db_field}
            except HTTPException as e:
                return {"success": False, "error": e.detail}
            except Exception as e:
                return {"success": False, "error": f"Failed to update trust settings: {str(e)}"}

        elif endpoint_type == "alert_dismiss":
            # Route through the governance router's dismiss_insight to enforce
            # trust ownership verification. Adds audit logging for the dismissal.
            from routers.governance import dismiss_insight as _dismiss_insight
            from models import DismissedInsightCreate

            criterion = mapped_data.get("criterion_name", "")
            if not criterion:
                return {"success": False, "error": "No criterion name provided to dismiss."}

            dismiss_req = DismissedInsightCreate(trust_id=trust_id, criterion_name=criterion)

            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            if not user_doc:
                user_doc = {"user_id": user_id, "email": "", "name": ""}
            try:
                await _dismiss_insight(req=dismiss_req, user=user_doc)
                # Audit log the alert dismissal
                from utils.audit import log_audit_event
                await log_audit_event(
                    user_id=user_id,
                    action="alert_dismissed_via_chat",
                    entity_type="governance_insight",
                    entity_id=criterion,
                    details={
                        "trust_id": trust_id,
                        "criterion_name": criterion,
                        "source": "chat_assistant",
                    },
                )
                return {"success": True, "endpoint": "insights", "action": "dismissed", "criterion": criterion}
            except HTTPException as e:
                return {"success": False, "error": e.detail}
            except Exception as e:
                return {"success": False, "error": f"Failed to dismiss insight: {str(e)}"}

        elif endpoint_type == "class_beneficiary":
            # Route through the beneficiaries router's create_class_beneficiary
            # to enforce trust ownership verification and class_type validation
            # via the ClassBeneficiaryType enum. Adds audit logging.
            from routers.beneficiaries import create_class_beneficiary as _create_cb
            from models import ClassBeneficiaryCreate, ClassBeneficiaryType

            class_type_raw = mapped_data.get("class_type", "custom")
            try:
                class_type_enum = ClassBeneficiaryType(class_type_raw)
            except ValueError:
                class_type_enum = ClassBeneficiaryType.custom

            cb_create = ClassBeneficiaryCreate(
                trust_id=trust_id,
                class_type=class_type_enum,
                description=mapped_data.get("description", ""),
                percentage=float(mapped_data.get("percentage", 0)),
                notes=mapped_data.get("notes", ""),
            )

            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            if not user_doc:
                user_doc = {"user_id": user_id, "email": "", "name": ""}
            try:
                result = await _create_cb(data=cb_create, user=user_doc)
                cb_id = result.get("class_beneficiary_id", "")
                # Audit log the class beneficiary creation
                from utils.audit import log_audit_event
                await log_audit_event(
                    user_id=user_id,
                    action="class_beneficiary_created_via_chat",
                    entity_type="class_beneficiary",
                    entity_id=cb_id,
                    details={
                        "trust_id": trust_id,
                        "class_type": class_type_enum.value,
                        "percentage": float(mapped_data.get("percentage", 0)),
                        "source": "chat_assistant",
                    },
                )
                # Update onboarding checklist
                try:
                    from dependencies import auto_update_onboarding
                    await auto_update_onboarding(user_id, trust_id)
                except Exception:
                    pass
                return {"success": True, "record_id": cb_id, "endpoint": "class-beneficiaries", "action": "created"}
            except HTTPException as e:
                return {"success": False, "error": e.detail}
            except Exception as e:
                return {"success": False, "error": f"Failed to create class beneficiary: {str(e)}"}

        elif endpoint_type == "class_beneficiary_removal":
            # Route through the beneficiaries router's delete_class_beneficiary
            # to enforce ownership verification (user_id match). Adds audit logging.
            from routers.beneficiaries import delete_class_beneficiary as _delete_cb

            class_type = mapped_data.get("class_type", "")
            existing = await db.class_beneficiaries.find_one({
                "trust_id": trust_id,
                "user_id": user_id,
                "class_type": class_type,
            })
            if not existing:
                return {"success": False, "error": f"Class beneficiary '{class_type}' not found for this trust."}

            user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
            if not user_doc:
                user_doc = {"user_id": user_id, "email": "", "name": ""}
            try:
                await _delete_cb(
                    class_beneficiary_id=existing["class_beneficiary_id"],
                    user=user_doc,
                )
                # Audit log the class beneficiary removal
                from utils.audit import log_audit_event
                await log_audit_event(
                    user_id=user_id,
                    action="class_beneficiary_removed_via_chat",
                    entity_type="class_beneficiary",
                    entity_id=existing["class_beneficiary_id"],
                    details={
                        "trust_id": trust_id,
                        "class_type": class_type,
                        "reason": mapped_data.get("reason", ""),
                        "source": "chat_assistant",
                    },
                )
                return {"success": True, "record_id": existing["class_beneficiary_id"], "endpoint": "class-beneficiaries", "action": "removed"}
            except HTTPException as e:
                return {"success": False, "error": e.detail}
            except Exception as e:
                return {"success": False, "error": f"Failed to remove class beneficiary: {str(e)}"}

        return {"success": False, "error": f"Unhandled endpoint type: {endpoint_type}"}

    except Exception as e:
        logger.error(f"Action execution error: {type(e).__name__}: {e}")
        return {"success": False, "error": str(e)}


@router.post("/chat/actions/{conversation_id}/{message_index}/confirm")
async def confirm_action(
    conversation_id: str,
    message_index: int,
    request: ConfirmActionRequest,
    user: dict = Depends(get_current_user),
):
    """
    Confirm, reject, or request edits for an action card.
    
    When approved, this endpoint:
    1. Marks the action card as approved
    2. Executes the real backend write operation (creating the actual record)
    
    For reject/edit, only the action card status is updated.
    """
    user_id = user["user_id"]

    conv = await db.chat_conversations.find_one(
        {"conversation_id": conversation_id, "user_id": user_id}
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = conv.get("messages", [])
    if message_index < 0 or message_index >= len(messages):
        raise HTTPException(status_code=400, detail="Invalid message index")

    msg = messages[message_index]
    if msg.get("role") != "assistant" or not msg.get("action_card"):
        raise HTTPException(status_code=400, detail="No action card found at this message index")

    action_card = msg["action_card"]

    # Update the action card status
    status_map = {"approve": "approved", "reject": "rejected", "edit": "pending"}
    new_status = status_map.get(request.action, "pending")

    # If editing, update the action card data with the edited fields
    update_fields = {
        f"messages.{message_index}.action_card.confirmation_status": new_status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if request.action == "edit" and request.edited_data:
        # Merge edited data into the existing action card data
        for key, value in request.edited_data.items():
            update_fields[f"messages.{message_index}.action_card.data.{key}"] = value

    await db.chat_conversations.update_one(
        {
            "conversation_id": conversation_id,
            "user_id": user_id,
        },
        {"$set": update_fields}
    )

    # Execute the real write operation on approval
    execution_result = None
    if request.action == "approve":
        trust_id = conv.get("trust_id")
        if trust_id:
            execution_result = await _execute_approved_action(
                action_card=action_card,
                user_id=user_id,
                trust_id=trust_id,
            )
            # Store the execution result in the action card
            if execution_result:
                await db.chat_conversations.update_one(
                    {"conversation_id": conversation_id, "user_id": user_id},
                    {"$set": {
                        f"messages.{message_index}.action_card.execution_result": execution_result,
                        f"messages.{message_index}.action_card.executed_at": datetime.now(timezone.utc).isoformat(),
                    }}
                )

    logger.info(
        f"ACTION | user={user_id} | conversation={conversation_id} | "
        f"message={message_index} | action={request.action} | status={new_status} | "
        f"executed={execution_result.get('success') if execution_result else 'N/A'}"
    )

    response = {
        "message": f"Action {request.action}d",
        "action_status": new_status,
    }
    if execution_result:
        response["execution_result"] = execution_result

    return response


@router.post("/chat/conversations/{conversation_id}/rename")
async def rename_conversation(
    conversation_id: str,
    title: str,
    user: dict = Depends(get_current_user),
):
    """Rename a conversation."""
    if not title or len(title.strip()) == 0 or len(title) > 100:
        raise HTTPException(status_code=400, detail="Title must be 1-100 characters")

    result = await db.chat_conversations.update_one(
        {"conversation_id": conversation_id, "user_id": user["user_id"]},
        {"$set": {"title": title.strip(), "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"message": "Conversation renamed", "title": title.strip()}


@router.get("/chat/status")
async def chat_status(user: dict = Depends(get_current_user)):
    """Check if the chat feature is available."""
    return {
        "chat_enabled": True,
        "conversation_count": await db.chat_conversations.count_documents({
            "user_id": user["user_id"],
        }),
        "max_message_length": MAX_MESSAGE_LENGTH,
        "streaming": True,
    }


# ==================== SSE STREAMING ENDPOINT ====================

async def _sse_event(event_type: str, data: dict) -> str:
    """Format a Server-Sent Event."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


async def _chat_stream_generator(
    user_id: str,
    message: str,
    conversation_id: Optional[str],
    trust_id: Optional[str],
):
    """
    Generator that yields SSE events for a streaming chat response.

    Event types:
    - meta: conversation_id, trust_context (sent first)
    - token: text chunk (sent as AI generates)
    - done: final metadata (action_card, citations, caveat)
    - error: error message
    """
    try:
        # 1. Get active trust
        trust_id_resolved, trust_name = await _get_active_trust(user_id, trust_id)
        if not trust_id_resolved:
            yield await _sse_event("error", {"message": "No trust found. Create a trust first to use the Trust Assistant."})
            return

        # 2. Get or create conversation
        conv_id, is_new = await _get_or_create_conversation(
            conversation_id, user_id, trust_id_resolved, message
        )

        # 3. Load conversation history
        conversation = await db.chat_conversations.find_one(
            {"conversation_id": conv_id, "user_id": user_id}
        )
        messages = conversation.get("messages", []) if conversation else []
        history_for_ai = [{"role": m.get("role"), "content": m.get("content")} for m in messages[-20:]]

        # 4. Send meta event with conversation_id
        yield await _sse_event("meta", {
            "conversation_id": conv_id,
            "is_new": is_new,
        })

        # 4b. Send status event so frontend knows we're processing
        yield await _sse_event("status", {"phase": "thinking"})

        # 5. Classify intent AND build trust context in parallel
        intent_task = asyncio.create_task(classify_intent(message, None))
        trust_context = await build_trust_context(user_id, trust_id_resolved)
        intent_result = await intent_task

        intent = intent_result.get("intent", "general_chat")
        entities = intent_result.get("entities", {})

        # 6. Stream the response tokens
        full_response_text = ""
        try:
            async for chunk in generate_response_stream(
                intent=intent,
                entities=entities,
                user_message=message,
                trust_context=trust_context,
                conversation_history=history_for_ai,
                ai_client_module=None,
            ):
                full_response_text += chunk
                yield await _sse_event("token", {"text": chunk})
        except (asyncio.CancelledError, GeneratorExit):
            # Client disconnected mid-stream — save partial response before propagating
            if full_response_text:
                user_msg_doc = ChatMessage(role="user", content=message)
                partial_assistant = ChatMessage(
                    role="assistant",
                    content=full_response_text,
                    action_card=None,
                    citation_note=None,
                    unknown_note=None,
                    caveat=None,
                )
                now_partial = datetime.now(timezone.utc).isoformat()
                await db.chat_conversations.update_one(
                    {"conversation_id": conv_id, "user_id": user_id},
                    {
                        "$push": {
                            "messages": {
                                "$each": [
                                    user_msg_doc.model_dump(),
                                    partial_assistant.model_dump(),
                                ]
                            }
                        },
                        "$set": {"updated_at": now_partial},
                        "$inc": {"message_count": 2},
                    },
                )
                logger.info(f"CHAT_STREAM_DISCONNECT | user={user_id} | conversation={conv_id} | partial_len={len(full_response_text)}")
            raise

        # 7. Build citations
        citation_note, unknown_note = build_citation_notes(trust_context, intent)

        # 8. Determine caveat
        caveat = None
        action_def = get_action(intent) if intent else None
        if action_def and action_def.get("requires_write"):
            caveat = "This proposed action should be reviewed with your legal or tax professional before execution."

        # 9. Send done event immediately — user sees response is complete
        yield await _sse_event("done", {
            "action_card": None,
            "citation_note": citation_note,
            "unknown_note": unknown_note,
            "caveat": caveat,
            "intent": intent,
        })

        # 10. Generate action card lazily (after done event) and send as separate event
        action_card = None
        try:
            action_def_check = get_action(intent) if intent else None
            if action_def_check and action_def_check.get("requires_write"):
                action_card = await generate_action_card(
                    intent, entities, message, trust_context, full_response_text
                )
                if action_card:
                    # Send the action card as a separate SSE event so the
                    # frontend can render it without blocking the done event.
                    yield await _sse_event("action_card", {
                        "action_card": action_card,
                    })
        except Exception as e:
            logger.warning(f"Action card generation failed: {e}")

        # 11. Save messages to DB
        user_msg_doc = ChatMessage(role="user", content=message)

        action_card_for_db = None
        if action_card:
            action_card_for_db = ChatAction(
                type=action_card.get("type", f"{intent}_preview"),
                data=action_card.get("data", {}),
                requires_confirmation=action_card.get("requires_confirmation", True),
                confirmation_status="pending",
            )

        assistant_msg_doc = ChatMessage(
            role="assistant",
            content=full_response_text,
            action_card=action_card_for_db,
            citation_note=citation_note,
            unknown_note=unknown_note,
            caveat=caveat,
        )

        now = datetime.now(timezone.utc).isoformat()
        await db.chat_conversations.update_one(
            {"conversation_id": conv_id, "user_id": user_id},
            {
                "$push": {
                    "messages": {
                        "$each": [
                            user_msg_doc.model_dump(),
                            assistant_msg_doc.model_dump(),
                        ]
                    }
                },
                "$set": {"updated_at": now},
                "$inc": {"message_count": 2},
            }
        )

        logger.info(f"CHAT_STREAM | user={user_id} | conversation={conv_id} | intent={intent} | response_len={len(full_response_text)}")

    except Exception as e:
        logger.error(f"Chat stream error: {type(e).__name__}: {e}", exc_info=True)
        yield await _sse_event("error", {"message": "An error occurred while generating the response. Please try again."})


@router.get("/chat/conversations/{conversation_id}/latest")
async def get_latest_assistant_message(
    conversation_id: str,
    user: dict = Depends(get_current_user),
):
    """
    Polling endpoint for disconnected clients.

    Returns the latest assistant message in a conversation. If the client
    disconnected mid-stream and reconnected, they can poll this endpoint to
    retrieve the assistant's response (full or partial).
    """
    conv = await db.chat_conversations.find_one(
        {"conversation_id": conversation_id, "user_id": user["user_id"]},
        {"_id": 0, "messages": 1, "updated_at": 1, "title": 1}
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = conv.get("messages", [])
    if not messages:
        raise HTTPException(status_code=404, detail="No messages in this conversation")

    # Walk backwards to find the latest assistant message
    latest_assistant = None
    latest_index = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "assistant":
            latest_assistant = messages[i]
            latest_index = i
            break

    if not latest_assistant:
        raise HTTPException(status_code=404, detail="No assistant message found")

    return {
        "conversation_id": conversation_id,
        "message_index": latest_index,
        "message": {
            "role": "assistant",
            "content": latest_assistant.get("content", ""),
            "action_card": latest_assistant.get("action_card"),
            "citation_note": latest_assistant.get("citation_note"),
            "unknown_note": latest_assistant.get("unknown_note"),
            "caveat": latest_assistant.get("caveat"),
            "timestamp": latest_assistant.get("timestamp", ""),
        },
        "updated_at": conv.get("updated_at", ""),
    }


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    user: dict = Depends(get_current_user),
):
    """
    Streaming chat endpoint using Server-Sent Events (SSE).

    Returns a text/event-stream with:
    - event: meta  (conversation_id)
    - event: token (text chunk)
    - event: done  (action_card, citations, caveat)
    - event: error (error message)
    """
    user_id = user["user_id"]

    # Validate message
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if len(request.message) > MAX_MESSAGE_LENGTH:
        raise HTTPException(status_code=400, detail=f"Message exceeds maximum length of {MAX_MESSAGE_LENGTH} characters")

    return StreamingResponse(
        _chat_stream_generator(
            user_id=user_id,
            message=request.message,
            conversation_id=request.conversation_id,
            trust_id=request.trust_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
        },
    )