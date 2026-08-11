# ARCHIVED - AgentMail removed
# Historical/stale script; do not execute. Use mail_client.py or google-workspace/google_api.py as applicable.

"""
Client Notes Router — Persistent Client Conversation History & CRM Notes

Provides a centralized record of every client interaction, issue, resolution,
and context note. Kit (the AI agent) uses this to reference past interactions
when handling new email requests, so no conversation is handled in isolation.

Authentication:
  Two auth modes are supported on every endpoint:
    1. Admin API Key — X-Admin-API-Key header (for Kit / automation)
    2. Admin User JWT — session_token cookie or Authorization: Bearer (for Jeff / admin UI)

MongoDB collection: client_notes
  Each document is one interaction record (not one-per-client).
  A client is identified by email (always present) and optionally by user_id.

Design decision: separate collection rather than extending `leads`
  - leads are pre-sale marketing entries; client_notes are post-sale / ongoing support.
  - A client may have a lead record AND many client_notes.
  - Separation keeps query patterns clean and avoids polluting lead scoring.
"""
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime, timezone
import os
import uuid
import logging
import secrets

from database import db
from dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/client-notes", tags=["client-notes"])

# ==================== AUTHENTICATION ====================

ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY")
api_key_header = APIKeyHeader(name="X-Admin-API-Key", auto_error=False)


async def verify_note_access(request: Request, api_key: str = Depends(api_key_header)):
    """
    Allow access via either:
      1. Admin API key (X-Admin-API-Key header) — for Kit / automation
      2. Admin user JWT (session_token / Bearer) — for Jeff / admin UI

    Raises 401/403 if neither is valid.
    """
    # --- Path 1: Admin API key ---
    if api_key and ADMIN_API_KEY:
        if secrets.compare_digest(api_key, ADMIN_API_KEY):
            return {"auth_method": "api_key", "identity": "admin-api"}
        raise HTTPException(status_code=401, detail="Invalid API key")

    # --- Path 2: Admin user JWT ---
    # Defer to the existing get_current_user dependency logic.
    # We replicate a minimal version here to avoid Depends ordering issues.
    import jwt
    JWT_SECRET = os.environ.get("JWT_SECRET")
    JWT_ALGORITHM = "HS256"
    if not JWT_SECRET:
        raise HTTPException(status_code=500, detail="Auth not configured")

    session_token = request.cookies.get("session_token")
    auth_header = request.headers.get("Authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    elif session_token:
        token = session_token

    if not token:
        raise HTTPException(status_code=401, detail="Authentication required. Use X-Admin-API-Key header or admin session.")

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Check admin flag
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "is_admin": 1, "email": 1})
    if not user_doc:
        raise HTTPException(status_code=403, detail="User not found")

    is_admin = user_doc.get("is_admin", False)
    admin_emails = {"contact@trustoffice.app"}
    if user_doc.get("email", "").lower() in admin_emails:
        is_admin = True

    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    return {"auth_method": "jwt", "identity": user_id}


# ==================== CONSTANTS ====================

NOTE_TYPES = [
    "support_interaction",   # General support question or help request
    "billing_issue",         # Payment, charge, refund, subscription billing
    "product_feedback",      # Bug report, feature request, UX feedback
    "complaint",             # Dissatisfied customer, service issue
    "compliment",            # Positive feedback, praise
    "account_change",        # Account modification (plan change, access grant, etc.)
    "security",              # Security-related (password reset, suspicious activity)
    "general",               # Catch-all for notes that don't fit other types
]

SEVERITY_LEVELS = [
    "low",      # Minor question, no urgency
    "normal",   # Standard support interaction
    "high",     # Needs attention soon (billing issue affecting access)
    "urgent",   # Critical (legal/regulatory, security, data loss)
]

RESOLUTION_STATUSES = [
    "open",         # Issue reported, no action taken yet
    "in_progress",  # Actively being worked
    "resolved",     # Fixed / answered / closed
    "escalated",    # Sent to Jeff or external (legal, Stripe, etc.)
]

AGENTS = [
    "kit",       # Kit (AI agent) handled this
    "jeff",      # Jeff handled this personally
    "admin",     # Another admin user
    "system",    # Automated system action (webhook, migration, etc.)
    "external",  # External party triggered this (Stripe, partner, etc.)
]


# ==================== SCHEMAS ====================

class CreateNote(BaseModel):
    """Schema for creating a new client note."""
    client_email: EmailStr                          # Primary client identifier (always lowercased)
    client_name: Optional[str] = None               # Display name (denormalized)
    client_user_id: Optional[str] = None            # user_id if registered (denormalized)
    note_type: str = "general"                       # One of NOTE_TYPES
    severity: str = "normal"                         # One of SEVERITY_LEVELS
    subject: str                                      # Brief title / subject line
    body: str                                         # Full note content
    resolution_notes: Optional[str] = None           # What was done (optional at creation)
    resolution_status: str = "open"                  # One of RESOLUTION_STATUSES
    agent: str = "kit"                               # Who handled this
    email_thread_id: Optional[str] = None            # AgentMail thread ID if from email
    email_subject: Optional[str] = None              # Original email subject
    tags: List[str] = []                              # Free-form tags for filtering
    metadata: dict = {}                               # Extra context (Stripe IDs, amounts, etc.)


class UpdateNote(BaseModel):
    """Schema for updating an existing note."""
    note_type: Optional[str] = None
    severity: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    resolution_notes: Optional[str] = None
    resolution_status: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[dict] = None


class ResolveNote(BaseModel):
    """Schema for marking a note as resolved."""
    resolution_notes: str                            # What was done to resolve
    resolution_status: str = "resolved"               # resolved or escalated


# ==================== HELPERS ====================

def _validate_enum(value: str, valid: List[str], field_name: str):
    """Raise 400 if value not in valid list."""
    if value not in valid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}: '{value}'. Must be one of: {', '.join(valid)}"
        )


def _serialize(doc: dict) -> dict:
    """Clean up a MongoDB doc for JSON response (remove _id, convert datetime)."""
    if doc is None:
        return None
    doc.pop("_id", None)
    return doc


async def _enrich_client_info(note: dict):
    """
    Auto-populate client_name and client_user_id from the users collection
    if not provided, so Kit doesn't have to do a separate lookup.
    """
    email = note.get("client_email", "").lower()
    if not email:
        return
    if not note.get("client_user_id") or not note.get("client_name"):
        user_doc = await db.users.find_one(
            {"email": email},
            {"_id": 0, "user_id": 1, "name": 1}
        )
        if user_doc:
            if not note.get("client_user_id"):
                note["client_user_id"] = user_doc.get("user_id")
            if not note.get("client_name"):
                note["client_name"] = user_doc.get("name")


# ==================== ENDPOINTS ====================

@router.post("", summary="Create a client note")
async def create_note(
    note_data: CreateNote,
    auth: dict = Depends(verify_note_access),
):
    """
    Create a new client interaction note.

    This is the primary write endpoint. Kit calls this after handling any
    email that involves a substantive client interaction (support question,
    billing issue, complaint, feedback, etc.).

    If client_name or client_user_id are not provided, they are auto-populated
    from the users collection by email lookup.
    """
    _validate_enum(note_data.note_type, NOTE_TYPES, "note_type")
    _validate_enum(note_data.severity, SEVERITY_LEVELS, "severity")
    _validate_enum(note_data.resolution_status, RESOLUTION_STATUSES, "resolution_status")
    _validate_enum(note_data.agent, AGENTS, "agent")

    now = datetime.now(timezone.utc)
    note_id = f"note_{uuid.uuid4().hex[:12]}"

    doc = note_data.model_dump()
    doc["client_email"] = doc["client_email"].lower().strip()
    doc["note_id"] = note_id
    doc["created_at"] = now.isoformat()
    doc["updated_at"] = now.isoformat()
    doc["resolved_at"] = now.isoformat() if doc["resolution_status"] == "resolved" else None

    # Auto-populate client info from users collection
    await _enrich_client_info(doc)

    await db.client_notes.insert_one(doc)

    logger.info(f"Client note created: {note_id} for {doc['client_email']} (type={doc['note_type']}, agent={doc['agent']})")

    return {
        "success": True,
        "note_id": note_id,
        "note": _serialize(doc),
    }


@router.get("", summary="List client notes with filters")
async def list_notes(
    request: Request,
    client_email: Optional[str] = Query(None, description="Filter by client email"),
    client_user_id: Optional[str] = Query(None, description="Filter by client user_id"),
    note_type: Optional[str] = Query(None, description="Filter by note type"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    resolution_status: Optional[str] = Query(None, description="Filter by resolution status"),
    agent: Optional[str] = Query(None, description="Filter by agent who handled"),
    tag: Optional[str] = Query(None, description="Filter by tag (substring match)"),
    search: Optional[str] = Query(None, description="Full-text search in subject + body"),
    unresolved_only: bool = Query(False, description="Only return open/in_progress/escalated notes"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    auth: dict = Depends(verify_note_access),
):
    """
    List client notes with optional filters.

    Common usage by Kit:
      - GET /client-notes?client_email=user@example.com — full history for a client
      - GET /client-notes?unresolved_only=true — outstanding issues across all clients
      - GET /client-notes?note_type=billing_issue — all billing issues
      - GET /client-notes?search=stripe — full-text search
    """
    query = {}

    if client_email:
        query["client_email"] = client_email.lower().strip()
    if client_user_id:
        query["client_user_id"] = client_user_id
    if note_type:
        _validate_enum(note_type, NOTE_TYPES, "note_type")
        query["note_type"] = note_type
    if severity:
        _validate_enum(severity, SEVERITY_LEVELS, "severity")
        query["severity"] = severity
    if resolution_status:
        _validate_enum(resolution_status, RESOLUTION_STATUSES, "resolution_status")
        query["resolution_status"] = resolution_status
    if agent:
        _validate_enum(agent, AGENTS, "agent")
        query["agent"] = agent
    if tag:
        query["tags"] = {"$regex": tag, "$options": "i"}
    if unresolved_only:
        query["resolution_status"] = {"$in": ["open", "in_progress", "escalated"]}
    if search:
        query["$or"] = [
            {"subject": {"$regex": search, "$options": "i"}},
            {"body": {"$regex": search, "$options": "i"}},
            {"resolution_notes": {"$regex": search, "$options": "i"}},
        ]

    total = await db.client_notes.count_documents(query)
    cursor = db.client_notes.find(query, {"_id": 0}).sort("created_at", -1).skip(offset).limit(limit)
    notes = await cursor.to_list(length=limit)

    return {
        "notes": notes,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total,
    }


@router.get("/{note_id}", summary="Get a single note")
async def get_note(
    note_id: str,
    auth: dict = Depends(verify_note_access),
):
    """Retrieve a single client note by ID."""
    doc = await db.client_notes.find_one({"note_id": note_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"note": doc}


@router.patch("/{note_id}", summary="Update a note")
async def update_note(
    note_id: str,
    update: UpdateNote,
    auth: dict = Depends(verify_note_access),
):
    """
    Update fields on an existing note (e.g., add resolution notes, change severity).

    If resolution_status changes to 'resolved', resolved_at is automatically set.
    """
    existing = await db.client_notes.find_one({"note_id": note_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Note not found")

    updates = {}
    for field in ["note_type", "severity", "subject", "body", "resolution_notes", "resolution_status", "tags", "metadata"]:
        value = getattr(update, field, None)
        if value is not None:
            if field == "note_type" and value:
                _validate_enum(value, NOTE_TYPES, "note_type")
            if field == "severity" and value:
                _validate_enum(value, SEVERITY_LEVELS, "severity")
            if field == "resolution_status" and value:
                _validate_enum(value, RESOLUTION_STATUSES, "resolution_status")
            updates[field] = value

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Track resolution timestamp
    if updates.get("resolution_status") == "resolved" and not existing.get("resolved_at"):
        updates["resolved_at"] = datetime.now(timezone.utc).isoformat()

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.client_notes.update_one({"note_id": note_id}, {"$set": updates})

    updated_doc = await db.client_notes.find_one({"note_id": note_id}, {"_id": 0})
    logger.info(f"Client note updated: {note_id} by {auth['identity']}")

    return {"success": True, "note": updated_doc}


@router.post("/{note_id}/resolve", summary="Resolve a note")
async def resolve_note(
    note_id: str,
    resolve: ResolveNote,
    auth: dict = Depends(verify_note_access),
):
    """
    Shortcut endpoint to mark a note as resolved (or escalated).

    Sets resolution_notes, resolution_status, resolved_at, and updated_at.
    """
    _validate_enum(resolve.resolution_status, ["resolved", "escalated"], "resolution_status")

    existing = await db.client_notes.find_one({"note_id": note_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Note not found")

    now = datetime.now(timezone.utc)
    updates = {
        "resolution_notes": resolve.resolution_notes,
        "resolution_status": resolve.resolution_status,
        "updated_at": now.isoformat(),
    }
    if resolve.resolution_status == "resolved":
        updates["resolved_at"] = now.isoformat()

    await db.client_notes.update_one({"note_id": note_id}, {"$set": updates})

    updated_doc = await db.client_notes.find_one({"note_id": note_id}, {"_id": 0})
    logger.info(f"Client note resolved: {note_id} → {resolve.resolution_status} by {auth['identity']}")

    return {"success": True, "note": updated_doc}


@router.delete("/{note_id}", summary="Delete a note")
async def delete_note(
    note_id: str,
    auth: dict = Depends(verify_note_access),
):
    """Delete a client note. Use with caution — this is irreversible."""
    result = await db.client_notes.delete_one({"note_id": note_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Note not found")

    logger.warning(f"Client note deleted: {note_id} by {auth['identity']}")
    return {"success": True, "deleted": note_id}


@router.get("/summary/{client_email}", summary="Get client interaction summary")
async def get_client_summary(
    client_email: str,
    auth: dict = Depends(verify_note_access),
):
    """
    Get a summary of all interactions for a specific client.

    Returns:
      - total_notes: count of all notes
      - by_type: breakdown by note_type
      - by_severity: breakdown by severity
      - by_status: breakdown by resolution_status
      - open_issues: list of unresolved notes
      - recent_notes: last 5 notes (any status)
      - client_info: name and user_id if found in users collection

    This is the endpoint Kit should call BEFORE handling a new email from a
    client to understand their full history and any outstanding issues.
    """
    email = client_email.lower().strip()

    # Aggregate pipeline for breakdowns
    pipeline = [
        {"$match": {"client_email": email}},
        {"$facet": {
            "by_type": [
                {"$group": {"_id": "$note_type", "count": {"$sum": 1}}},
            ],
            "by_severity": [
                {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
            ],
            "by_status": [
                {"$group": {"_id": "$resolution_status", "count": {"$sum": 1}}},
            ],
            "total": [
                {"$count": "count"},
            ],
        }}
    ]
    agg = await db.client_notes.aggregate(pipeline).to_list(length=1)
    agg = agg[0] if agg else {}

    total = agg.get("total", [{}])[0].get("count", 0) if agg.get("total") else 0

    by_type = {item["_id"]: item["count"] for item in agg.get("by_type", []) if item.get("_id")}
    by_severity = {item["_id"]: item["count"] for item in agg.get("by_severity", []) if item.get("_id")}
    by_status = {item["_id"]: item["count"] for item in agg.get("by_status", []) if item.get("_id")}

    # Open issues (unresolved)
    open_cursor = db.client_notes.find(
        {"client_email": email, "resolution_status": {"$in": ["open", "in_progress", "escalated"]}},
        {"_id": 0}
    ).sort("created_at", -1)
    open_issues = await open_cursor.to_list(length=50)

    # Recent notes (last 5, any status)
    recent_cursor = db.client_notes.find(
        {"client_email": email},
        {"_id": 0}
    ).sort("created_at", -1).limit(5)
    recent_notes = await recent_cursor.to_list(length=5)

    # Client info from users collection
    client_info = None
    user_doc = await db.users.find_one({"email": email}, {"_id": 0, "user_id": 1, "name": 1})
    if user_doc:
        client_info = {
            "user_id": user_doc.get("user_id"),
            "name": user_doc.get("name"),
        }

    return {
        "client_email": email,
        "client_info": client_info,
        "total_notes": total,
        "by_type": by_type,
        "by_severity": by_severity,
        "by_status": by_status,
        "open_issues": open_issues,
        "recent_notes": recent_notes,
    }
