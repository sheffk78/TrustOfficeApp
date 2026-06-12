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
from pydantic import BaseModel, Field

from dependencies import get_current_user
from database import db
from chat_service import (
    classify_intent,
    extract_action_data,
    build_trust_context,
    generate_response,
)
from action_registry import requires_confirmation

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

    convs = await db.chat_conversations.find(
        query,
        {"_id": 0, "conversation_id": 1, "title": 1, "updated_at": 1, "trust_id": 1}
    ).sort("updated_at", -1).limit(min(limit, 50)).to_list(limit)

    result = []
    for c in convs:
        message_count = await db.chat_conversations.count_documents({
            "conversation_id": c["conversation_id"],
        })

        # Get last message preview
        full_conv = await db.chat_conversations.find_one(
            {"conversation_id": c["conversation_id"]},
            {"messages": {"$slice": -1}}
        )
        last_msg = ""
        if full_conv and full_conv.get("messages"):
            last_msg = full_conv["messages"][-1].get("content", "")[:80]

        result.append({
            "conversation_id": c["conversation_id"],
            "title": c.get("title", "Conversation"),
            "message_count": message_count,
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


@router.post("/chat/actions/{conversation_id}/{message_index}/confirm")
async def confirm_action(
    conversation_id: str,
    message_index: int,
    action: str,  # "approve", "reject", or "edit"
    user: dict = Depends(get_current_user),
):
    """
    Confirm, reject, or request edits for an action card.
    
    This is the user's explicit approval step before any write operation executes.
    """
    conv = await db.chat_conversations.find_one(
        {"conversation_id": conversation_id, "user_id": user["user_id"]}
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = conv.get("messages", [])
    if message_index < 0 or message_index >= len(messages):
        raise HTTPException(status_code=400, detail="Invalid message index")

    msg = messages[message_index]
    if msg.get("role") != "assistant" or not msg.get("action_card"):
        raise HTTPException(status_code=400, detail="No action card found at this message index")

    # Update the action card status
    status_map = {"approve": "approved", "reject": "rejected", "edit": "pending"}
    new_status = status_map.get(action, "pending")

    # Use positional operator to update the specific message's action card
    await db.chat_conversations.update_one(
        {
            "conversation_id": conversation_id,
            "user_id": user["user_id"],
        },
        {
            "$set": {
                f"messages.{message_index}.action_card.confirmation_status": new_status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        }
    )

    logger.info(
        f"ACTION | user={user['user_id']} | conversation={conversation_id} | "
        f"message={message_index} | action={action} | status={new_status}"
    )

    return {
        "message": f"Action {action}d",
        "action_status": new_status,
    }


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
        "streaming": False,  # Sprint 1: batch mode only
    }