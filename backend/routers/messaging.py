# In-Platform Messaging System — user-to-user messaging for TrustOffice app users
# (trustees, beneficiaries, advisors, admins). NOT the same as the Communications Log.
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from database import db
from dependencies import get_current_user, require_write_access

router = APIRouter(tags=["messaging"])

# ── Pydantic models ──────────────────────────────────────────────────────────

class ConversationCreate(BaseModel):
    participants: list[str] = Field(..., description="Array of user_ids to include in the conversation")


class MessageCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=5000, description="Message text")


class MessageResponse(BaseModel):
    message_id: str
    conversation_id: str
    sender_id: str
    body: str
    created_at: str
    read: bool


class ConversationPreview(BaseModel):
    conversation_id: str
    participants: list[str]
    last_message: Optional[str] = None
    last_message_at: Optional[str] = None
    unread_count: int = 0
    created_at: str


# ── Helper: build a user lookup dict from db ─────────────────────────────────

async def _lookup_user_names(user_ids: list[str]) -> dict[str, str]:
    """Return {user_id: display_name} for the given user IDs."""
    if not user_ids:
        return {}
    cursor = db.users.find({"user_id": {"$in": user_ids}}, {"_id": 0, "user_id": 1, "name": 1})
    result: dict[str, str] = {}
    async for u in cursor:
        result[u["user_id"]] = u.get("name", u["user_id"]) or u["user_id"]
    return result


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/messaging/conversations")
async def create_conversation(body: ConversationCreate, user: dict = Depends(require_write_access)):
    """Create a new conversation with the given participants."""
    user_id = user["user_id"]
    participants = list(set(body.participants + [user_id]))  # ensure creator is included, deduplicate

    if len(participants) < 2:
        raise HTTPException(status_code=400, detail="A conversation requires at least 2 participants")

    conversation_id = f"conv_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()

    doc = {
        "conversation_id": conversation_id,
        "participants": participants,
        "created_at": now,
        "updated_at": now,
        "last_message_id": None,
    }
    await db.conversations.insert_one(doc)

    # Resolve participant display names for the response
    names = await _lookup_user_names(participants)

    return {
        "conversation_id": conversation_id,
        "participants": [{"user_id": uid, "name": names.get(uid, uid)} for uid in participants],
        "created_at": now,
    }


@router.post("/messaging/conversations/{conversation_id}/messages")
async def send_message(conversation_id: str, body: MessageCreate, user: dict = Depends(require_write_access)):
    """Send a message in an existing conversation."""
    user_id = user["user_id"]
    now = datetime.now(timezone.utc).isoformat()
    message_id = f"msg_{uuid.uuid4().hex[:12]}"

    # Verify conversation exists and user is a participant
    conv = await db.conversations.find_one(
        {"conversation_id": conversation_id, "participants": user_id},
        {"_id": 0},
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msg_doc = {
        "message_id": message_id,
        "conversation_id": conversation_id,
        "sender_id": user_id,
        "body": body.body,
        "created_at": now,
        "read_by": [user_id],  # sender has seen their own message
    }
    await db.messages.insert_one(msg_doc)

    # Update conversation's last message pointer and timestamp
    await db.conversations.update_one(
        {"conversation_id": conversation_id},
        {"$set": {"updated_at": now, "last_message_id": message_id}},
    )

    return {
        "message_id": message_id,
        "conversation_id": conversation_id,
        "sender_id": user_id,
        "body": body.body,
        "created_at": now,
    }


@router.get("/messaging/conversations")
async def list_conversations(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    """List the current user's conversations with last-message preview and unread count."""
    user_id = user["user_id"]

    # Fetch conversations that include this user, sorted by most recent
    convs = await db.conversations.find(
        {"participants": user_id},
        {"_id": 0},
    ).sort("updated_at", -1).skip(skip).limit(limit).to_list(limit)

    # Collect last-message IDs and batch-fetch them
    last_msg_ids = [c["last_message_id"] for c in convs if c.get("last_message_id")]
    msgs_map = {}
    if last_msg_ids:
        msgs_cursor = db.messages.find(
            {"message_id": {"$in": last_msg_ids}},
            {"_id": 0, "message_id": 1, "sender_id": 1, "body": 1, "created_at": 1},
        )
        async for m in msgs_cursor:
            msgs_map[m["message_id"]] = m

    # Batch-fetch unread counts: for each conversation, count messages not in read_by
    conv_ids = [c["conversation_id"] for c in convs]
    unread_pipeline = [
        {"$match": {"conversation_id": {"$in": conv_ids}}},
        {"$addFields": {"is_unread": {"$not": {"$in": [user_id, "$read_by"]}}}},
        {"$match": {"is_unread": True}},
        {"$group": {"_id": "$conversation_id", "count": {"$sum": 1}}},
    ]
    unread_counts = {}
    async for doc in db.messages.aggregate(unread_pipeline):
        unread_counts[doc["_id"]] = doc["count"]

    # Resolve participant names
    all_participant_ids = set()
    for c in convs:
        all_participant_ids.update(c.get("participants", []))
    names = await _lookup_user_names(list(all_participant_ids))

    result = []
    for c in convs:
        last_msg = msgs_map.get(c.get("last_message_id"))
        other_ids = [pid for pid in c.get("participants", []) if pid != user_id]

        result.append({
            "conversation_id": c["conversation_id"],
            "participants": [
                {"user_id": pid, "name": names.get(pid, pid)}
                for pid in c.get("participants", [])
            ],
            "last_message": last_msg["body"][:100] if last_msg else None,
            "last_message_at": last_msg["created_at"] if last_msg else None,
            "last_message_sender_id": last_msg["sender_id"] if last_msg else None,
            "unread_count": unread_counts.get(c["conversation_id"], 0),
            "created_at": c["created_at"],
        })

    return {"conversations": result}


@router.get("/messaging/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    user: dict = Depends(get_current_user),
    before: Optional[str] = Query(None, description="Message ID to paginate before (exclusive)"),
    limit: int = Query(50, ge=1, le=200),
):
    """Get messages for a conversation, newest first. Supports cursor pagination via `before`."""
    user_id = user["user_id"]

    # Verify participation
    conv = await db.conversations.find_one(
        {"conversation_id": conversation_id, "participants": user_id},
        {"_id": 0},
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    query = {"conversation_id": conversation_id}
    if before:
        # Find the created_at of the cursor message so we can paginate correctly
        cursor_msg = await db.messages.find_one(
            {"message_id": before, "conversation_id": conversation_id},
            {"_id": 0, "created_at": 1},
        )
        if cursor_msg:
            query["created_at"] = {"$lt": cursor_msg["created_at"]}

    msgs = await db.messages.find(
        query,
        {"_id": 0},
    ).sort("created_at", -1).limit(limit).to_list(limit)

    # Mark these messages as read
    unread_ids = [m["message_id"] for m in msgs if user_id not in m.get("read_by", [])]
    if unread_ids:
        await db.messages.update_many(
            {"message_id": {"$in": unread_ids}},
            {"$addToSet": {"read_by": user_id}},
        )

    return {"messages": msgs}


@router.patch("/messaging/conversations/{conversation_id}/read")
async def mark_conversation_read(conversation_id: str, user: dict = Depends(get_current_user)):
    """Mark all messages in a conversation as read by the current user."""
    user_id = user["user_id"]

    # Verify participation
    conv = await db.conversations.find_one(
        {"conversation_id": conversation_id, "participants": user_id},
        {"_id": 0},
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await db.messages.update_many(
        {"conversation_id": conversation_id, "sender_id": {"$ne": user_id}},
        {"$addToSet": {"read_by": user_id}},
    )

    return {"message": "All messages marked as read"}