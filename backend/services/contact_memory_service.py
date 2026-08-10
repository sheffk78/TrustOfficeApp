"""
Contact memory service — customer memory / support interaction layer.

Provides:
  - contacts collection: lightweight CRM-ish records (email-keyed, user-scoped)
  - support_interactions collection: inbound support messages with AI-generated
    replies, sentiment, urgency, and resolution status
  - contact_profile_summary collection: structured, updatable running summary
    per contact (phase, preferences, constraints, next actions, etc.)

All operations are user-scoped (filtered by user_id when provided) and follow
the established client_service.py conventions: async/await, `_now()` and
`_new_id(prefix)` helpers, docs returned with `_id` popped.
"""
from datetime import datetime, timezone
from typing import List, Optional
import uuid

from database import db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# Allowed roles for require_role()
ALLOWED_ROLES = {"support", "success", "marketing", "engineering", "admin"}

# Whitelist of structured fields accepted by update_contact_profile_summary.
# Mirrors the fields of models.ContactProfileSummary (excluding contact_id /
# updated_at, which are managed by the service itself).
PROFILE_SUMMARY_FIELDS = {
    "current_phase",
    "key_preferences",
    "constraints",
    "last_major_issue",
    "last_major_issue_outcome",
    "recommended_next_actions",
    "follow_up_notes",
}


def require_role(user: Optional[dict], allowed_roles: List[str]) -> None:
    """Raise PermissionError if the user's role is not in allowed_roles.

    `user` is expected to be a dict with a "role" key (e.g. the decoded JWT
    payload or a user record). A missing/None user or a user with no role
    is treated as insufficient privileges.
    """
    if not user:
        raise PermissionError("Authentication required.")
    user_role = user.get("role") if isinstance(user, dict) else None
    if user_role is None:
        raise PermissionError("User has no assigned role.")
    allowed = set(allowed_roles)
    if user_role not in allowed:
        raise PermissionError(
            f"Role '{user_role}' is not permitted. Allowed roles: "
            f"{sorted(allowed)}."
        )


# ==================== CONTACT CRUD ====================

async def get_or_create_contact_by_email(
    email: str,
    name: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict:
    """Find a contact by email (case-insensitive). Create if missing.

    Returns the contact document with `_id` popped.
    """
    if not email:
        raise ValueError("email is required")

    normalized_email = email.strip().lower()
    query = {"email": normalized_email}
    if user_id is not None:
        query["user_id"] = user_id

    existing = await db.contacts.find_one(query, {"_id": 0})
    if existing:
        return existing

    now = _now()
    doc = {
        "contact_id": _new_id("contact"),
        "name": name or "",
        "email": normalized_email,
        "phone": None,
        "organization": None,
        "role": "prospect",
        "status": "prospect",
        "plan": None,
        "tags": [],
        "created_at": now,
        "updated_at": now,
    }
    if user_id is not None:
        doc["user_id"] = user_id

    await db.contacts.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def get_contact_by_email(
    email: str, user_id: Optional[str] = None
) -> Optional[dict]:
    """Fetch a single contact by email (case-insensitive). Returns None if missing."""
    normalized_email = email.strip().lower()
    query = {"email": normalized_email}
    if user_id is not None:
        query["user_id"] = user_id
    return await db.contacts.find_one(query, {"_id": 0})


async def get_contact_by_id(
    contact_id: str, user_id: Optional[str] = None
) -> Optional[dict]:
    """Fetch a single contact by contact_id. Returns None if missing."""
    query = {"contact_id": contact_id}
    if user_id is not None:
        query["user_id"] = user_id
    return await db.contacts.find_one(query, {"_id": 0})


# ==================== CONTACT CONTEXT ====================

async def get_contact_context(
    email: str, user_id: Optional[str] = None
) -> dict:
    """Return {contact, profile_summary, recent_interactions} for a contact.

    - contact: the contact document (or None if not found)
    - profile_summary: the contact_profile_summary document, or None
    - recent_interactions: last 5 support_interactions sorted by created_at desc
    """
    contact = await get_contact_by_email(email, user_id=user_id)
    if not contact:
        return {
            "contact": None,
            "profile_summary": None,
            "recent_interactions": [],
        }

    contact_id = contact["contact_id"]

    # Profile summary
    ps_query = {"contact_id": contact_id}
    if user_id is not None:
        ps_query["user_id"] = user_id
    profile_summary = await db.contact_profile_summary.find_one(
        ps_query, {"_id": 0}
    )

    # Recent interactions (last 5, newest first)
    si_query = {"contact_id": contact_id}
    if user_id is not None:
        si_query["user_id"] = user_id
    cursor = db.support_interactions.find(si_query, {"_id": 0}).sort(
        "created_at", -1
    )
    recent_interactions = await cursor.to_list(length=5)

    return {
        "contact": contact,
        "profile_summary": profile_summary,
        "recent_interactions": recent_interactions,
    }


# ==================== SUPPORT INTERACTIONS ====================

async def log_support_interaction(
    contact_id: str,
    raw_content: str,
    generated_reply: Optional[str],
    summary: str,
    topics: List[str],
    sentiment: str,
    urgency: int,
    status: str,
    channel: str = "email",
    user_id: Optional[str] = None,
) -> dict:
    """Insert a support interaction for a contact.

    Sets created_at to now, and resolved_at to now if status == 'resolved'.
    Returns the inserted document with `_id` popped.
    """
    if not contact_id:
        raise ValueError("contact_id is required")

    now = _now()
    doc = {
        "interaction_id": _new_id("interaction"),
        "contact_id": contact_id,
        "channel": channel,
        "raw_content": raw_content,
        "generated_reply": generated_reply,
        "summary": summary,
        "topics": topics or [],
        "sentiment": sentiment,
        "urgency": urgency,
        "status": status,
        "created_at": now,
        "resolved_at": now if status == "resolved" else None,
    }
    if user_id is not None:
        doc["user_id"] = user_id

    await db.support_interactions.insert_one(doc)
    doc.pop("_id", None)
    return doc


# ==================== PROFILE SUMMARY UPSERT ====================

async def update_contact_profile_summary(
    contact_id: str,
    new_summary_fields: dict,
    user_id: Optional[str] = None,
) -> dict:
    """Upsert the contact_profile_summary document for a contact.

    Only the structured fields in PROFILE_SUMMARY_FIELDS are accepted; any
    unknown keys in new_summary_fields are silently ignored. `updated_at` is
    always refreshed. `contact_id` is set from the argument and cannot be
    overridden by new_summary_fields.

    Returns the updated/inserted document with `_id` popped.
    """
    if not contact_id:
        raise ValueError("contact_id is required")
    if not isinstance(new_summary_fields, dict):
        raise ValueError("new_summary_fields must be a dict")

    # Filter to whitelist only
    update_fields = {
        k: v for k, v in new_summary_fields.items()
        if k in PROFILE_SUMMARY_FIELDS
    }
    update_fields["updated_at"] = _now()

    # Build the filter for upsert
    filt = {"contact_id": contact_id}
    if user_id is not None:
        filt["user_id"] = user_id

    # Ensure contact_id and user_id are set on insert
    set_on_insert = {"contact_id": contact_id}
    if user_id is not None:
        set_on_insert["user_id"] = user_id

    await db.contact_profile_summary.update_one(
        filt,
        {
            "$set": update_fields,
            "$setOnInsert": set_on_insert,
        },
        upsert=True,
    )

    # Re-fetch and return
    result = await db.contact_profile_summary.find_one(filt, {"_id": 0})
    if result is None:
        # Should not happen after upsert, but guard defensively
        result = dict(update_fields)
        result["contact_id"] = contact_id
        if user_id is not None:
            result["user_id"] = user_id
    return result


# ==================== PRIVACY / REDACTION ====================

async def redact_contact_history(
    contact_id: str, user_id: Optional[str] = None
) -> dict:
    """Privacy capability: redact a contact's full history.

    - Deletes all support_interactions for the contact
    - Deletes the contact_profile_summary for the contact
    - Nulls out sensitive fields (phone, email) on the contact document

    Returns a summary dict of what was redacted.
    """
    if not contact_id:
        raise ValueError("contact_id is required")

    # Scopes
    si_filter = {"contact_id": contact_id}
    ps_filter = {"contact_id": contact_id}
    contact_filter = {"contact_id": contact_id}
    if user_id is not None:
        si_filter["user_id"] = user_id
        ps_filter["user_id"] = user_id
        contact_filter["user_id"] = user_id

    deleted_interactions = await db.support_interactions.delete_many(si_filter)
    deleted_profile = await db.contact_profile_summary.delete_many(ps_filter)

    # Null out sensitive fields on the contact
    redacted_fields = ["phone", "email"]
    await db.contacts.update_one(
        contact_filter,
        {
            "$set": {
                "phone": None,
                "email": None,
                "updated_at": _now(),
            }
        },
    )

    del_inter_count = (
        deleted_interactions.deleted_count
        if hasattr(deleted_interactions, "deleted_count")
        else (deleted_interactions if isinstance(deleted_interactions, int) else 0)
    )
    del_profile_count = (
        deleted_profile.deleted_count
        if hasattr(deleted_profile, "deleted_count")
        else (deleted_profile if isinstance(deleted_profile, int) else 0)
    )

    return {
        "contact_id": contact_id,
        "deleted_interactions_count": del_inter_count,
        "deleted_profile_summary": bool(del_profile_count),
        "redacted_contact_fields": redacted_fields,
        "redacted_at": _now(),
    }


# ==================== LEAD → CONTACT LINKAGE ====================

async def upsert_contact_from_lead(
    email: str,
    name: Optional[str] = None,
    lead: Optional[dict] = None,
    user_id: Optional[str] = None,
) -> dict:
    """Merge a (converted) lead into the contacts collection.

    Called from the Stripe-webhook conversion bridge (mark_lead_as_subscribed).
    Creates the contact if missing, otherwise updates it with any richer
    lead data. Tags the contact with its marketing origin so the admin
    Conversations view can show where each customer came from.

    Returns the contact document with `_id` popped.
    """
    if not email:
        raise ValueError("email is required")

    contact = await get_or_create_contact_by_email(email, name=name, user_id=user_id)
    update_fields = _promote_to_client(contact, name)

    # Carry marketing-origin metadata onto the contact.
    source = (lead or {}).get("source")
    if source:
        update_fields = _apply_marketing_source(contact, update_fields, source)
    if lead and lead.get("utm_campaign"):
        update_fields["utm_campaign"] = lead.get("utm_campaign")
    if lead and lead.get("lead_id"):
        update_fields["lead_id"] = lead.get("lead_id")

    update_fields = _apply_utm(contact, update_fields, lead or {})

    return await _apply_contact_update(contact, update_fields)


async def upsert_contact_from_user(user: dict, user_id: Optional[str] = None) -> dict:
    """Create/update a contact from a registered user (direct conversion, no lead).

    Called from the Stripe webhook when a user completes checkout but has no
    lead record (e.g. went straight to signup then checkout). Captures the
    user's stored UTM/attribution fields so the admin Conversations view can
    attribute the conversion to an ad campaign.

    Returns the contact document with `_id` popped.
    """
    if not user:
        raise ValueError("user is required")
    email = user.get("email")
    if not email:
        raise ValueError("user.email is required")

    contact = await get_or_create_contact_by_email(email, name=user.get("name"), user_id=user_id or user.get("user_id"))
    update_fields = _promote_to_client(contact, user.get("name"))

    # A direct conversion may still carry UTM from the signup form.
    update_fields = _apply_utm(contact, update_fields, user)
    # If the user had no lead but has a wp_ref (WingPoint), tag it as a source.
    if user.get("wp_ref"):
        update_fields = _apply_marketing_source(contact, update_fields, "wingpoint")

    return await _apply_contact_update(contact, update_fields)


# ---------- shared helpers ----------

def _promote_to_client(contact: dict, name: Optional[str]) -> dict:
    """Set status/role to paying-client and refresh name/updated_at."""
    update_fields = {"updated_at": _now()}
    if name:
        update_fields["name"] = name
    if contact.get("status") in (None, "prospect"):
        update_fields["status"] = "active_client"
    if contact.get("role") in (None, "prospect"):
        update_fields["role"] = "trustee"
    return update_fields


def _apply_marketing_source(contact: dict, update_fields: dict, source: str) -> dict:
    """Tag a contact with its marketing source and add a from_marketing tag."""
    origin_tags = [t for t in contact.get("tags", []) if not t.startswith("from_marketing:")]
    origin_tags.append(f"from_marketing:{source}")
    update_fields["tags"] = origin_tags
    update_fields["lead_source"] = source
    return update_fields


def _apply_utm(contact: dict, update_fields: dict, src: dict) -> dict:
    """Carry UTM/attribution fields onto the contact (only when present)."""
    for k in ("utm_source", "utm_campaign", "utm_medium", "referrer"):
        val = src.get(k)
        if val:
            update_fields[k] = str(val)[:200]
    return update_fields


async def _apply_contact_update(contact: dict, update_fields: dict) -> dict:
    """Persist contact updates and return the refreshed doc with `_id` popped."""
    if update_fields:
        await db.contacts.update_one(
            {"contact_id": contact["contact_id"]},
            {"$set": update_fields},
        )
        contact.update(update_fields)
    return contact


# ==================== ADMIN CONVERSATIONS VIEW ====================

async def list_conversations(
    limit: int = 50,
    skip: int = 0,
    min_interactions: int = 0,
    status_filter: Optional[str] = None,
    sentiment_filter: Optional[str] = None,
    search: Optional[str] = None,
) -> dict:
    """Return a paginated list of contacts with conversation context for admin.

    For each contact that has at least one support_interaction, attach:
      - profile_summary (or None)
      - interaction_count
      - last_interaction (the most recent one)
      - marketing_source (lead_source or a from_marketing:* tag)

    Returns {conversations, total, limit, skip}.
    """
    match_stage = {}
    if search:
        import re as _re
        escaped = _re.escape(search.strip().lower())
        match_stage["$or"] = [
            {"name": {"$regex": escaped, "$options": "i"}},
            {"email": {"$regex": escaped, "$options": "i"}},
        ]

    pipeline = [
        ({"$match": match_stage} if match_stage else {"$match": {}}),
        {
            "$lookup": {
                "from": "support_interactions",
                "let": {"cid": "$contact_id"},
                "pipeline": [
                    {"$match": {"$expr": {"$eq": ["$contact_id", "$$cid"]}}},
                ],
                "as": "interactions",
            }
        },
        {"$match": {"interactions.0": {"$exists": True}}},
        {
            "$addFields": {
                "interaction_count": {"$size": "$interactions"},
                "last_interaction": {
                    "$arrayElemAt": [
                        {"$sortArray": {"input": "$interactions", "sortBy": {"created_at": -1}}},
                        0,
                    ]
                },
            }
        },
        {"$sort": {"last_interaction.created_at": -1}},
        {"$skip": skip},
        {"$limit": limit},
        {"$project": {"interactions": 0, "_id": 0}},
    ]

    conversations = await db.contacts.aggregate(pipeline).to_list(length=limit)

    # Attach profile summaries and compute derived fields
    total = 0
    enriched = []
    for conv in conversations:
        ps = await db.contact_profile_summary.find_one(
            {"contact_id": conv["contact_id"]}, {"_id": 0}
        )
        conv["profile_summary"] = ps
        # Marketing origin — from lead_source, else from_marketing:* tag,
        # else the user's stored utm_source (direct conversions), else referrer.
        src = conv.get("lead_source")
        if not src:
            for tag in conv.get("tags", []):
                if tag.startswith("from_marketing:"):
                    src = tag.split(":", 1)[1]
                    break
        if not src and conv.get("utm_source"):
            src = f"utm:{conv['utm_source']}"
        if not src and conv.get("referrer"):
            src = "referrer"
        conv["marketing_source"] = src
        conv["utm_campaign"] = conv.get("utm_campaign")
        conv["utm_source"] = conv.get("utm_source")
        # Latest sentiment/topic for quick scan
        last = conv.get("last_interaction") or {}
        conv["last_sentiment"] = last.get("sentiment")
        conv["last_topics"] = last.get("topics", [])
        conv["last_status"] = last.get("status")
        enriched.append(conv)

    # Post-filter on interaction count / status / sentiment
    filtered = enriched
    if min_interactions:
        filtered = [c for c in filtered if c["interaction_count"] >= min_interactions]
    if status_filter:
        filtered = [c for c in filtered if (c.get("last_status") or "") == status_filter]
    if sentiment_filter:
        filtered = [c for c in filtered if (c.get("last_sentiment") or "") == sentiment_filter]

    total = len(filtered)
    return {
        "conversations": filtered,
        "total": total,
        "limit": limit,
        "skip": skip,
    }