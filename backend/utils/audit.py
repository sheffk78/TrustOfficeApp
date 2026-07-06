"""Audit logging utility for TrustOffice.

Provides a shared function to log audit events to the audit_logs collection.
Used by auth, settings (trust updates), and vault routers to capture
security-critical actions that the background task runner doesn't see.

Usage:
    from utils.audit import log_audit_event
    await log_audit_event(user_id, "login", "user", user_id, {"email": email})
"""
import uuid
from datetime import datetime, timezone

from database import db


async def log_audit_event(
    user_id: str,
    action: str,
    entity_type: str,
    entity_id: str,
    details: dict = None,
) -> None:
    """Log an audit event to the audit_logs collection.

    Args:
        user_id: The user performing the action.
        action: What happened (e.g. "login", "password_reset", "trust_updated",
                "vault_upload", "vault_download", "vault_delete").
        entity_type: The type of entity affected (e.g. "user", "trust", "vault_document").
        entity_id: The ID of the entity affected.
        details: Optional dict with additional context (field changes, file name, etc.).
    """
    audit_doc = {
        "audit_id": f"audit_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "details": details or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ip_address": None,
    }
    await db.audit_logs.insert_one(audit_doc)