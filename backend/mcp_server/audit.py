"""
Audit logging for the MCP server.

Extends the existing admin_api_audit collection pattern from
routers/admin_api.py. Every MCP tool invocation is logged with
the same schema, prefixed with 'mcp_' to distinguish from direct
Admin API calls.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
import uuid
import logging

from database import db

logger = logging.getLogger(__name__)


async def log_mcp_action(
    action: str,
    details: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    customer_agent_type: Optional[str] = None,
) -> str:
    """
    Log an MCP tool invocation to the admin_api_audit collection.

    Returns the audit_id for reference.

    Schema extends the existing admin_api_audit pattern:
    - action: prefixed with 'mcp_' to distinguish from direct Admin API calls
    - details: includes tool_name, parameters, result_summary, idempotency_key, source
    """
    audit_id = f"mcp_audit_{uuid.uuid4().hex[:12]}"

    doc = {
        "audit_id": audit_id,
        "action": f"mcp_{action}" if not action.startswith("mcp_") else action,
        "details": details or {},
        "user_id": user_id,
        "ip_address": ip_address or "local",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "mcp",
        "protocol_version": "1.0",
    }

    if idempotency_key:
        doc["details"]["idempotency_key"] = idempotency_key
    if customer_agent_type:
        doc["details"]["customer_agent_type"] = customer_agent_type

    try:
        await db.admin_api_audit.insert_one(doc)
    except Exception as exc:
        # Audit logging failure should not break the tool response,
        # but must be logged for visibility.
        logger.error("MCP audit log failed: %s", exc, exc_info=True)

    return audit_id