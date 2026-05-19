# Communication log router — trustee/beneficiary relationship records
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from typing import Optional
import re
import uuid

from database import db
from dependencies import get_current_user

router = APIRouter(tags=["communications"])

COMM_TYPES = {
    "email": "Email / Digital correspondence",
    "phone": "Phone call / Voicemail",
    "meeting": "In-person / Video meeting",
    "notice": "Formal written notice",
    "financial_report": "Financial report / Accounting",
    "k1_distribution": "K-1 / Distribution notice",
    "other": "Other",
}

@router.post("/trusts/{trust_id}/communications")
async def log_communication(trust_id: str, comm: dict, user: dict = Depends(get_current_user)):
    """Log a trustee-beneficiary communication event."""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "comm_id": f"comm_{uuid.uuid4().hex[:12]}",
        "trust_id": trust_id,
        "comm_type": comm.get("comm_type", "other"),
        "comm_type_label": COMM_TYPES.get(comm.get("comm_type", "other"), "Other"),
        "subject": comm.get("subject", ""),
        "content": comm.get("content", ""),
        "parties": comm.get("parties", []),  # [{"role": "trustee", "name": "..."}, {"role": "beneficiary", "name": "..."}]
        "direction": comm.get("direction", "outbound"),  # outbound, inbound, internal
        "document_ids": comm.get("document_ids", []),
        "action_required": comm.get("action_required", False),
        "action_completed": comm.get("action_completed", False),
        "action_due": comm.get("action_due"),
        "tags": comm.get("tags", []),
        "created_at": comm.get("date", now),
        "updated_at": now,
    }
    await db.communications.insert_one(doc)
    return {"comm_id": doc["comm_id"], "message": "Communication logged"}


@router.get("/trusts/{trust_id}/communications")
async def list_communications(
    trust_id: str,
    comm_type: Optional[str] = None,
    direction: Optional[str] = None,
    action_required: Optional[bool] = None,
    search: Optional[str] = None,
    limit: int = 100,
    user: dict = Depends(get_current_user)
):
    """List communications with filtering."""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    query = {"trust_id": trust_id}
    if comm_type:
        query["comm_type"] = comm_type
    if direction:
        query["direction"] = direction
    if action_required is not None:
        query["action_required"] = action_required

    if search:
        escaped_search = re.escape(search)
        query["$or"] = [
            {"subject": {"$regex": escaped_search, "$options": "i"}},
            {"content": {"$regex": escaped_search, "$options": "i"}},
        ]

    docs = await db.communications.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)

    # Count action items
    action_items = await db.communications.count_documents({
        "trust_id": trust_id, "action_required": True, "action_completed": False
    })

    return {
        "trust_id": trust_id,
        "communications": docs,
        "count": len(docs),
        "action_items_pending": action_items,
        "comm_types": COMM_TYPES,
    }


@router.patch("/communications/{comm_id}")
async def update_communication(comm_id: str, update: dict, user: dict = Depends(get_current_user)):
    """Update a communication — mark action completed, add notes."""
    comm = await db.communications.find_one({"comm_id": comm_id}, {"_id": 0})
    if not comm:
        raise HTTPException(status_code=404, detail="Communication not found")

    trust = await db.trusts.find_one({"trust_id": comm["trust_id"], "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    update_data = {k: v for k, v in update.items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.communications.update_one({"comm_id": comm_id}, {"$set": update_data})
    return {"message": "Updated"}


@router.delete("/communications/{comm_id}")
async def delete_communication(comm_id: str, user: dict = Depends(get_current_user)):
    """Delete a communication record."""
    comm = await db.communications.find_one({"comm_id": comm_id}, {"_id": 0})
    if not comm:
        raise HTTPException(status_code=404, detail="Communication not found")

    trust = await db.trusts.find_one({"trust_id": comm["trust_id"], "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    await db.communications.delete_one({"comm_id": comm_id})
    return {"message": "Deleted"}


@router.get("/trusts/{trust_id}/communications/summary")
async def communications_summary(trust_id: str, user: dict = Depends(get_current_user)):
    """Dashboard-level summary: counts by type, pending actions."""
    trust = await db.trusts.find_one({"trust_id": trust_id, "user_id": user["user_id"]})
    if not trust:
        raise HTTPException(status_code=404, detail="Trust not found")

    total = await db.communications.count_documents({"trust_id": trust_id})
    pending_actions = await db.communications.count_documents({
        "trust_id": trust_id, "action_required": True, "action_completed": False
    })

    by_type = []
    pipeline = [
        {"$match": {"trust_id": trust_id}},
        {"$group": {"_id": "$comm_type", "count": {"$sum": 1}}}
    ]
    async for doc in db.communications.aggregate(pipeline):
        by_type.append({"type": doc["_id"], "count": doc["count"]})

    recent = await db.communications.find(
        {"trust_id": trust_id},
        {"_id": 0, "comm_id": 1, "comm_type": 1, "subject": 1, "created_at": 1, "action_required": 1, "action_completed": 1}
    ).sort("created_at", -1).limit(5).to_list(10)

    return {
        "trust_id": trust_id,
        "total_communications": total,
        "pending_actions": pending_actions,
        "by_type": by_type,
        "recent": recent,
    }
