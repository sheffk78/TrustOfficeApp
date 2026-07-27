"""
Client service — CRUD and aggregation for multi-trust client view.

Phase 2 (Multi-Trust Client View) of the TrustOffice council plan.

Clients are stored in db.clients. Trusts are linked via a client_id field
on the trust document in db.trusts. All operations are user-scoped.
"""
from datetime import datetime, timezone
from typing import List, Optional
import uuid

from database import db
from models import ClientCreate, ClientUpdate


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ==================== CLIENT CRUD ====================

async def create_client(payload: ClientCreate, user_id: str) -> dict:
    """Create a new client profile."""
    now = _now()
    doc = {
        "client_id": _new_id("client"),
        "user_id": user_id,
        "name": payload.name,
        "email": payload.email,
        "phone": payload.phone,
        "address": payload.address,
        "notes": payload.notes,
        "wingpoint_ref": payload.wingpoint_ref,
        "created_at": now,
        "updated_at": now,
    }
    await db.clients.insert_one(doc)
    doc.pop("_id", None)
    # Add computed fields
    doc["trust_count"] = 0
    return doc


async def get_client(client_id: str, user_id: str) -> Optional[dict]:
    """Fetch a client only if owned by this user."""
    return await db.clients.find_one(
        {"client_id": client_id, "user_id": user_id}, {"_id": 0}
    )


async def list_clients(user_id: str) -> List[dict]:
    """List all clients for a user, with trust_count computed."""
    cursor = db.clients.find({"user_id": user_id}, {"_id": 0})
    clients = await cursor.to_list(length=None)
    # Compute trust_count for each client
    for client in clients:
        count = await db.trusts.count_documents(
            {"client_id": client["client_id"], "user_id": user_id}
        )
        client["trust_count"] = count
    return clients


async def update_client(
    client_id: str, payload: ClientUpdate, user_id: str
) -> Optional[dict]:
    """Update client profile fields. Returns updated doc or None if not found."""
    client = await get_client(client_id, user_id)
    if not client:
        return None

    update_fields = {}
    for field in ("name", "phone", "address", "notes", "wingpoint_ref"):
        value = getattr(payload, field, None)
        if value is not None:
            update_fields[field] = value
    update_fields["updated_at"] = _now()

    await db.clients.update_one(
        {"client_id": client_id, "user_id": user_id},
        {"$set": update_fields},
    )
    updated = await get_client(client_id, user_id)
    if updated:
        count = await db.trusts.count_documents(
            {"client_id": client_id, "user_id": user_id}
        )
        updated["trust_count"] = count
    return updated


async def delete_client(client_id: str, user_id: str) -> bool:
    """Delete client profile and unlink all trusts. Returns True if deleted."""
    client = await get_client(client_id, user_id)
    if not client:
        return False

    # Unlink all trusts (remove client_id, don't delete the trusts)
    await db.trusts.update_many(
        {"client_id": client_id, "user_id": user_id},
        {"$unset": {"client_id": ""}},
    )
    # Delete the client document
    await db.clients.delete_one({"client_id": client_id, "user_id": user_id})
    return True


# ==================== TRUST LINKING ====================

async def link_trust(client_id: str, trust_id: str, user_id: str) -> Optional[dict]:
    """Link a trust to a client. Returns the updated trust doc or None."""
    # Verify both client and trust belong to this user
    client = await get_client(client_id, user_id)
    if not client:
        return None
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user_id}, {"_id": 0}
    )
    if not trust:
        return None

    await db.trusts.update_one(
        {"trust_id": trust_id, "user_id": user_id},
        {"$set": {"client_id": client_id}},
    )
    return await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user_id}, {"_id": 0}
    )


async def unlink_trust(client_id: str, trust_id: str, user_id: str) -> Optional[dict]:
    """Unlink a trust from a client. Returns the updated trust doc or None."""
    client = await get_client(client_id, user_id)
    if not client:
        return None
    trust = await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user_id, "client_id": client_id},
        {"_id": 0},
    )
    if not trust:
        return None

    await db.trusts.update_one(
        {"trust_id": trust_id, "user_id": user_id},
        {"$unset": {"client_id": ""}},
    )
    return await db.trusts.find_one(
        {"trust_id": trust_id, "user_id": user_id}, {"_id": 0}
    )


# ==================== AGGREGATION ====================

async def get_client_trusts(client_id: str, user_id: str) -> List[dict]:
    """Get all trusts linked to a client."""
    cursor = db.trusts.find(
        {"client_id": client_id, "user_id": user_id}, {"_id": 0}
    )
    return await cursor.to_list(length=None)


async def get_client_detail(client_id: str, user_id: str) -> Optional[dict]:
    """Get client with all linked trust summaries."""
    client = await get_client(client_id, user_id)
    if not client:
        return None

    trusts = await get_client_trusts(client_id, user_id)
    trust_summaries = []
    for t in trusts:
        trust_summaries.append({
            "trust_id": t.get("trust_id", ""),
            "trust_name": t.get("trust_name", ""),
            "trust_type": t.get("trust_type", ""),
            "jurisdiction": t.get("jurisdiction"),
            "governance_score": t.get("governance_score"),
            "health_color": t.get("health_color"),
            "created_at": t.get("created_at", ""),
        })

    client["trusts"] = trust_summaries
    return client


async def get_client_health(client_id: str, user_id: str) -> Optional[dict]:
    """Aggregate health data across all linked trusts."""
    client = await get_client(client_id, user_id)
    if not client:
        return None

    trusts = await get_client_trusts(client_id, user_id)
    trust_ids = [t["trust_id"] for t in trusts]

    # Average governance score
    scores: List[float] = [
        float(t["governance_score"]) for t in trusts
        if t.get("governance_score") is not None
    ]
    avg_score = round(sum(scores) / len(scores), 1) if scores else None

    # Count by health_color
    color_counts: dict = {}
    for t in trusts:
        color = t.get("health_color")
        if color:
            color_counts[color] = color_counts.get(color, 0) + 1

    # Overdue governance tasks across all trusts
    overdue_count = 0
    if trust_ids:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        overdue_count = await db.governance_tasks.count_documents({
            "trust_id": {"$in": trust_ids},
            "user_id": user_id,
            "status": {"$nin": ["completed", "cancelled"]},
            "due_date": {"$lt": today},
        })

    # Upcoming deadlines across all trusts
    upcoming_count = 0
    if trust_ids:
        upcoming_count = await db.deadlines.count_documents({
            "trust_id": {"$in": trust_ids},
            "user_id": user_id,
            "status": {"$in": ["upcoming", "due_soon"]},
        })

    return {
        "client_id": client_id,
        "trust_count": len(trusts),
        "average_health_score": avg_score,
        "trusts_by_health_color": color_counts,
        "total_overdue_tasks": overdue_count,
        "upcoming_deadlines_count": upcoming_count,
        "calculated_at": _now(),
    }


async def get_client_deadlines(client_id: str, user_id: str) -> List[dict]:
    """Get all deadlines across all trusts linked to this client."""
    trusts = await get_client_trusts(client_id, user_id)
    trust_ids = [t["trust_id"] for t in trusts]
    if not trust_ids:
        return []

    cursor = db.deadlines.find(
        {"trust_id": {"$in": trust_ids}, "user_id": user_id},
        {"_id": 0},
    ).sort("due_date", 1)
    return await cursor.to_list(length=None)


async def get_client_meetings(client_id: str, user_id: str) -> List[dict]:
    """Get all meetings across all trusts linked to this client."""
    trusts = await get_client_trusts(client_id, user_id)
    trust_ids = [t["trust_id"] for t in trusts]
    if not trust_ids:
        return []

    cursor = db.meetings.find(
        {"trust_id": {"$in": trust_ids}, "user_id": user_id},
        {"_id": 0},
    ).sort("actual_meeting_date", -1)
    return await cursor.to_list(length=None)
