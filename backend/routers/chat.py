"""
Chat Router — Trust Assistant conversational AI endpoint

Provides POST /api/ai/chat for the Trust Assistant three-column page.
Non-streaming batch response for Sprint 1 (SSE streaming deferred).
"""
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from dependencies import get_current_user
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
            "amount": "amount",
            "frequency": "frequency",
            "effective_date": "effective_date",
            "role": "role",
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
    
    # Normalize: intent classifier sends log_minutes → log_minutes_preview
    TYPE_ALIASES = {
        "log_minutes_preview": "minutes_preview",
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
            # Create distribution record
            from models import PurposeClassification

            purpose = mapped_data.pop("purpose_classification", "other")
            try:
                purpose_enum = PurposeClassification(purpose)
            except ValueError:
                purpose_enum = PurposeClassification.other

            dist_id = f"dist_{uuid.uuid4().hex[:12]}"
            dist_doc = {
                "distribution_id": dist_id,
                "trust_id": trust_id,
                "user_id": user_id,
                "beneficiary_name": mapped_data.get("beneficiary_name", "Unknown"),
                "amount": float(mapped_data.get("amount", 0)),
                "date": mapped_data.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
                "purpose_classification": purpose_enum.value,
                "authority_clause_ref": "",
                "notes": mapped_data.get("notes", ""),
                "solvency_confirmed": False,
                "recusal_acknowledged": False,
                "approved_by": None,
                "approved_at": None,
                "minutes_record_id": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "is_benevolence": False,
                "benevolence_recipient_name": None,
                "benevolence_need_description": None,
                "benevolence_notes": None,
            }
            await db.distribution_records.insert_one(dist_doc)
            return {"success": True, "record_id": dist_id, "endpoint": "distributions"}

        elif endpoint_type == "asset":
            from models import AssetCategory

            category = mapped_data.pop("category", "other_property")
            try:
                category_enum = AssetCategory(category)
            except ValueError:
                category_enum = AssetCategory.other_property

            item_id = f"asset_{uuid.uuid4().hex[:12]}"
            asset_doc = {
                "item_id": item_id,
                "trust_id": trust_id,
                "user_id": user_id,
                "category": category_enum.value,
                "description": mapped_data.get("description", ""),
                "identifier": "",
                "location": "",
                "approximate_value": mapped_data.get("approximate_value"),
                "date_conveyed": mapped_data.get("date_conveyed", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
                "notes": mapped_data.get("notes", ""),
                "status": "active",
                "minutes_ref": None,
                "disposition_minutes_ref": None,
                "disposition_date": None,
                "disposition_notes": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": None,
            }
            await db.schedule_a_items.insert_one(asset_doc)
            return {"success": True, "record_id": item_id, "endpoint": "schedule-a"}

        elif endpoint_type == "minutes":
            from models import MinutesType

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

            minutes_id = f"minutes_{uuid.uuid4().hex[:12]}"
            minutes_doc = {
                "minutes_id": minutes_id,
                "trust_id": trust_id,
                "user_id": user_id,
                "minutes_type": minutes_type_enum.value,
                "meeting_date": mapped_data.get("meeting_date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
                "participants_text": participants_text,
                "decisions_text": decisions_text,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "template_type": None,
                "sections": [],
                "template_data": {},
                "status": "finalized",
                "is_retroactive": False,
                "retroactive_reason": None,
                "retroactive_trusttees_aware": None,
                "retroactive_type": None,
                "manually_edited": False,
            }
            await db.minutes_records.insert_one(minutes_doc)
            return {"success": True, "record_id": minutes_id, "endpoint": "minutes"}

        elif endpoint_type == "beneficiary":
            # Beneficiaries are managed via trust unit certificates
            cert_id = f"cert_{uuid.uuid4().hex[:12]}"
            cert_number = f"TC-{uuid.uuid4().hex[:6].upper()}"

            # Get unit settings for the trust
            settings = await db.trust_unit_settings.find_one(
                {"trust_id": trust_id}
            )
            total_authorized = settings.get("total_authorized_units", 0) if settings else 0

            allocation_pct = mapped_data.get("units", 0)
            # Convert percentage to units if settings exist
            if total_authorized > 0 and isinstance(allocation_pct, (int, float)) and allocation_pct < 100:
                units = max(1, round(total_authorized * allocation_pct / 100))
            elif isinstance(allocation_pct, (int, float)):
                units = int(allocation_pct) if allocation_pct > 0 else 1
            else:
                units = 1

            cert_doc = {
                "certificate_id": cert_id,
                "certificate_number": cert_number,
                "trust_id": trust_id,
                "user_id": user_id,
                "holder_name": mapped_data.get("holder_name", "Unknown"),
                "holder_identifier": "",
                "email": mapped_data.get("email", ""),
                "phone": mapped_data.get("phone", ""),
                "units": units,
                "issue_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "status": "active",
                "notes": "",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.trust_unit_certificates.insert_one(cert_doc)
            return {"success": True, "record_id": cert_id, "endpoint": "trust-units/certificates"}

        elif endpoint_type == "beneficiary_update":
            # Find the existing beneficiary certificate by holder_name
            existing = await db.trust_unit_certificates.find_one({
                "trust_id": trust_id,
                "holder_name": {"$regex": f"^{mapped_data.get('holder_name', '')}$", "$options": "i"},
                "status": "active",
            })
            if not existing:
                return {"success": False, "error": f"Beneficiary '{mapped_data.get('holder_name', '')}' not found. Use 'Create Beneficiary' to add them first."}
            
            update_fields = {}
            if mapped_data.get("email"):
                update_fields["email"] = mapped_data["email"]
            if mapped_data.get("phone"):
                update_fields["phone"] = mapped_data["phone"]
            if mapped_data.get("notes"):
                update_fields["notes"] = mapped_data["notes"]
            
            if update_fields:
                await db.trust_unit_certificates.update_one(
                    {"certificate_id": existing["certificate_id"]},
                    {"$set": update_fields}
                )
            return {"success": True, "record_id": existing["certificate_id"], "endpoint": "beneficiaries", "action": "updated"}

        elif endpoint_type == "beneficiary_removal":
            existing = await db.trust_unit_certificates.find_one({
                "trust_id": trust_id,
                "holder_name": {"$regex": f"^{mapped_data.get('holder_name', '')}$", "$options": "i"},
                "status": "active",
            })
            if not existing:
                return {"success": False, "error": f"Beneficiary '{mapped_data.get('holder_name', '')}' not found."}
            
            await db.trust_unit_certificates.update_one(
                {"certificate_id": existing["certificate_id"]},
                {"$set": {"status": "inactive", "deactivated_at": datetime.now(timezone.utc).isoformat()}}
            )
            return {"success": True, "record_id": existing["certificate_id"], "endpoint": "beneficiaries", "action": "removed"}

        elif endpoint_type == "distribution_cancel":
            # Find matching distribution
            query = {"trust_id": trust_id}
            if mapped_data.get("beneficiary_name"):
                query["beneficiary_name"] = {"$regex": f"^{mapped_data['beneficiary_name']}$", "$options": "i"}
            if mapped_data.get("amount"):
                query["amount"] = float(mapped_data["amount"])
            
            existing = await db.distribution_records.find_one(query, sort=[("created_at", -1)])
            if not existing:
                return {"success": False, "error": "Distribution not found matching those details."}
            
            await db.distribution_records.update_one(
                {"distribution_id": existing["distribution_id"]},
                {"$set": {"status": "cancelled", "cancelled_at": datetime.now(timezone.utc).isoformat()}}
            )
            return {"success": True, "record_id": existing["distribution_id"], "endpoint": "distributions", "action": "cancelled"}

        elif endpoint_type == "document_upload":
            doc_id = f"doc_{uuid.uuid4().hex[:12]}"
            doc_doc = {
                "document_id": doc_id,
                "trust_id": trust_id,
                "user_id": user_id,
                "title": mapped_data.get("title", "Untitled Document"),
                "category": mapped_data.get("category", "other"),
                "notes": mapped_data.get("notes", ""),
                "file_url": "",
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "status": "pending_upload",
            }
            await db.vault_documents.insert_one(doc_doc)
            return {"success": True, "record_id": doc_id, "endpoint": "vault/documents", "action": "created", "note": "Document record created. Upload the file in the Vault page to complete."}

        elif endpoint_type == "compensation_plan":
            plan_id = f"plan_{uuid.uuid4().hex[:12]}"
            plan_doc = {
                "plan_id": plan_id,
                "trust_id": trust_id,
                "user_id": user_id,
                "trustee_name": mapped_data.get("trustee_name", "Trustee"),
                "amount": float(mapped_data.get("amount", 0)),
                "frequency": mapped_data.get("frequency", "monthly"),
                "effective_date": mapped_data.get("effective_date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
                "role": mapped_data.get("role", ""),
                "status": "active",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.compensation_plans.insert_one(plan_doc)
            return {"success": True, "record_id": plan_id, "endpoint": "compensation-plans", "action": "created"}

        elif endpoint_type == "task":
            task_id = f"task_{uuid.uuid4().hex[:12]}"
            task_doc = {
                "task_id": task_id,
                "trust_id": trust_id,
                "user_id": user_id,
                "task_type": mapped_data.get("task_type", "custom"),
                "description": mapped_data.get("description", ""),
                "due_date": mapped_data.get("due_date", ""),
                "priority": mapped_data.get("priority", "normal"),
                "completed_at": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.governance_tasks.insert_one(task_doc)
            return {"success": True, "record_id": task_id, "endpoint": "tasks", "action": "created"}

        elif endpoint_type == "transaction":
            txn_id = f"txn_{uuid.uuid4().hex[:12]}"
            txn_doc = {
                "transaction_id": txn_id,
                "trust_id": trust_id,
                "user_id": user_id,
                "transaction_type": mapped_data.get("transaction_type", "expense"),
                "amount": float(mapped_data.get("amount", 0)),
                "category": mapped_data.get("category", "other_expense"),
                "date": mapped_data.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
                "description": mapped_data.get("description", ""),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.transactions.insert_one(txn_doc)
            return {"success": True, "record_id": txn_id, "endpoint": "transactions", "action": "created"}

        elif endpoint_type == "settings_update":
            field = mapped_data.get("field", "")
            value = mapped_data.get("value", "")
            field_mapping = {
                "name": "name",
                "trust_type": "trust_type",
                "formation_date": "formation_date",
                "ein": "ein",
                "jurisdiction": "jurisdiction",
                "state_code": "state_code",
            }
            db_field = field_mapping.get(field.lower().replace(" ", "_"))
            if not db_field:
                return {"success": False, "error": f"Unknown field: {field}. Valid fields: name, trust_type, formation_date, ein, jurisdiction, state_code"}
            
            await db.trusts.update_one(
                {"trust_id": trust_id, "user_id": user_id},
                {"$set": {db_field: value}}
            )
            return {"success": True, "record_id": trust_id, "endpoint": "trusts", "action": "updated", "field": db_field}

        elif endpoint_type == "alert_dismiss":
            criterion = mapped_data.get("criterion_name", "")
            if not criterion:
                return {"success": False, "error": "No criterion name provided to dismiss."}
            
            await db.dismissed_insights.update_one(
                {"trust_id": trust_id, "criterion_name": criterion},
                {"$set": {
                    "trust_id": trust_id,
                    "criterion_name": criterion,
                    "user_id": user_id,
                    "dismissed_at": datetime.now(timezone.utc).isoformat(),
                }},
                upsert=True
            )
            return {"success": True, "endpoint": "insights", "action": "dismissed", "criterion": criterion}

        elif endpoint_type == "class_beneficiary":
            cb_id = f"cb_{uuid.uuid4().hex[:16]}"
            class_type = mapped_data.get("class_type", "custom")
            class_type_label = {
                "children": "Children (including after-born)",
                "descendants": "Descendants",
                "issue": "Issue (lineal descendants)",
                "heirs": "Heirs",
                "heirs_at_law": "Heirs at Law",
                "blood_relatives": "Blood Relatives",
                "per_stirpes": "Per Stirpes (by branch)",
                "per_capita": "Per Capita (by head)",
                "custom": "Custom Class",
            }.get(class_type, class_type)

            cb_doc = {
                "class_beneficiary_id": cb_id,
                "trust_id": trust_id,
                "user_id": user_id,
                "class_type": class_type,
                "class_type_label": class_type_label,
                "description": mapped_data.get("description", ""),
                "percentage": float(mapped_data.get("percentage", 0)),
                "notes": mapped_data.get("notes", ""),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.class_beneficiaries.insert_one(cb_doc)
            return {"success": True, "record_id": cb_id, "endpoint": "class-beneficiaries", "action": "created"}

        elif endpoint_type == "class_beneficiary_removal":
            class_type = mapped_data.get("class_type", "")
            existing = await db.class_beneficiaries.find_one({
                "trust_id": trust_id,
                "user_id": user_id,
                "class_type": class_type,
            })
            if not existing:
                return {"success": False, "error": f"Class beneficiary '{class_type}' not found for this trust."}
            await db.class_beneficiaries.delete_one({"class_beneficiary_id": existing["class_beneficiary_id"]})
            return {"success": True, "record_id": existing["class_beneficiary_id"], "endpoint": "class-beneficiaries", "action": "removed"}

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

        # 5. Classify intent (non-streamed, fast)
        intent_result = await classify_intent(message, None)
        intent = intent_result.get("intent", "general_chat")
        entities = intent_result.get("entities", {})

        # 6. Build trust context (DB queries, fast)
        trust_context = await build_trust_context(user_id, trust_id_resolved)

        # 7. Stream the response tokens
        full_response_text = ""
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

        # 8. Generate action card if needed (post-stream)
        action_card = None
        try:
            action_card = await generate_action_card(
                intent, entities, message, trust_context, full_response_text
            )
        except Exception as e:
            logger.warning(f"Action card generation failed: {e}")

        # 9. Build citations
        citation_note, unknown_note = build_citation_notes(trust_context, intent)

        # 10. Determine caveat
        caveat = None
        action_def = get_action(intent) if intent else None
        if action_card or (action_def and action_def.get("requires_write")):
            caveat = "This proposed action should be reviewed with your legal or tax professional before execution."

        # 11. Send done event with metadata
        yield await _sse_event("done", {
            "action_card": action_card,
            "citation_note": citation_note,
            "unknown_note": unknown_note,
            "caveat": caveat,
            "intent": intent,
        })

        # 12. Save messages to DB
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
        yield await _sse_event("error", {"message": f"An error occurred while generating the response: {str(e)}"})


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