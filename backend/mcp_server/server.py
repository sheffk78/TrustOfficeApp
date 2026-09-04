"""
MCP Server entrypoint — exposes TrustOffice Admin API operations as MCP tools.

This is the main server module that defines all MCP tools, handles auth,
rate limiting, idempotency, and audit logging for each invocation.

Phase 1: Read-only tools are fully implemented.
         Write tools are stubbed and clearly marked.

Usage:
    ADMIN_API_KEY=<key> python -m mcp_server

Or programmatically:
    from mcp_server.server import MCPServer
    server = MCPServer(api_key="<key>")
    result = await server.call_tool("get_trust_state", {"user_id": "...", "trust_id": "..."})
"""

import json
import uuid
import logging
from typing import Dict, Any, Optional, List

from mcp_server.auth import validate_api_key, check_rate_limit, reset_rate_limits
from mcp_server.audit import log_mcp_action
from mcp_server.admin_client import AdminAPIClient

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "1.0"

# ==================== TOOL DEFINITIONS ====================

TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    # ---- READ-ONLY TOOLS (Phase 1 — fully implemented) ----
    {
        "name": "list_user_trusts",
        "description": "List all trusts for a TrustOffice user. Returns trust count and trust details.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "TrustOffice user ID"},
            },
            "required": ["user_id"],
        },
        "readOnly": True,
    },
    {
        "name": "get_trust_state",
        "description": "Get the current state of a specific trust (name, type, jurisdiction, trustees, EIN, etc.).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "TrustOffice user ID"},
                "trust_id": {"type": "string", "description": "Trust ID"},
            },
            "required": ["user_id", "trust_id"],
        },
        "readOnly": True,
    },
    {
        "name": "get_governance_health",
        "description": "Get the latest governance health score for a trust, including criteria breakdown.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "TrustOffice user ID"},
                "trust_id": {"type": "string", "description": "Trust ID"},
            },
            "required": ["user_id", "trust_id"],
        },
        "readOnly": True,
    },
    {
        "name": "get_tax_calendar",
        "description": "Get tax calendar entries for a trust, including filing status, days remaining, and overdue count.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "TrustOffice user ID"},
                "trust_id": {"type": "string", "description": "Trust ID"},
                "tax_year": {"type": "integer", "description": "Tax year (defaults to current year)"},
            },
            "required": ["user_id", "trust_id"],
        },
        "readOnly": True,
    },
    {
        "name": "get_task_list",
        "description": "Get governance tasks for a trust, optionally filtered by status (pending/completed/overdue).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "TrustOffice user ID"},
                "trust_id": {"type": "string", "description": "Trust ID"},
                "status": {"type": "string", "enum": ["pending", "completed", "overdue"], "description": "Filter by task status"},
            },
            "required": ["user_id", "trust_id"],
        },
        "readOnly": True,
    },
    # ---- WRITE TOOLS (Phase 2 — STUBBED) ----
    {
        "name": "submit_trust_update",
        "description": "[STUBBED — Phase 2] Update trust details (name, jurisdiction, trustees, etc.). Not available in Phase 1.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "trust_id": {"type": "string"},
                "updates": {"type": "object", "description": "Fields to update"},
            },
            "required": ["user_id", "trust_id", "updates"],
        },
        "readOnly": False,  # Intended as write, but not implemented
    },
    {
        "name": "submit_asset_values",
        "description": "[STUBBED — Phase 2] Submit updated asset valuations for a trust. Not available in Phase 1.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "trust_id": {"type": "string"},
                "asset_values": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["user_id", "trust_id", "asset_values"],
        },
        "readOnly": False,
    },
    {
        "name": "complete_task",
        "description": "[STUBBED — Phase 2] Mark a governance task as completed. Not available in Phase 1.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "trust_id": {"type": "string"},
                "task_id": {"type": "string"},
            },
            "required": ["user_id", "trust_id", "task_id"],
        },
        "readOnly": False,
    },
    {
        "name": "submit_minutes_draft",
        "description": "[STUBBED — Phase 2] Submit a draft of meeting minutes for a trust. Not available in Phase 1.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "trust_id": {"type": "string"},
                "minutes_data": {"type": "object"},
            },
            "required": ["user_id", "trust_id", "minutes_data"],
        },
        "readOnly": False,
    },
    {
        "name": "update_beneficiary",
        "description": "[STUBBED — Phase 2] Update beneficiary information for a trust. Not available in Phase 1.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "trust_id": {"type": "string"},
                "beneficiary_id": {"type": "string"},
                "updates": {"type": "object"},
            },
            "required": ["user_id", "trust_id", "beneficiary_id", "updates"],
        },
        "readOnly": False,
    },
]


class MCPServer:
    """
    TrustOffice MCP Server.

    Handles tool dispatch, authentication, rate limiting, idempotency,
    and audit logging. Designed to be testable with a mocked AdminAPIClient.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        client: Optional[AdminAPIClient] = None,
        customer_agent_type: str = "unknown",
    ):
        """
        Args:
            api_key: Admin API key. If None, reads from ADMIN_API_KEY env var.
            client: AdminAPIClient instance. If None, creates a default one.
                    Tests should inject a mock client.
            customer_agent_type: Type of connecting agent (hermes, openclaw, claude-code, unknown).
        """
        self._api_key = api_key or _get_env_api_key()
        self._client = client or AdminAPIClient()
        self._customer_agent_type = customer_agent_type
        self._idempotency_cache: Dict[str, Dict[str, Any]] = {}

    def list_tools(self) -> List[Dict[str, Any]]:
        """Return all tool definitions (MCP tools/list response)."""
        return TOOL_DEFINITIONS

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute an MCP tool call.

        This is the main entry point for tool invocation. It:
        1. Validates auth
        2. Checks rate limit
        3. Checks idempotency cache
        4. Dispatches to the appropriate tool handler
        5. Audit-logs the invocation
        6. Returns the result

        Returns a dict with either the tool result or an error.
        """
        # 1. Auth
        valid, err = validate_api_key(self._api_key)
        if not valid:
            return {"error": err, "status": 401, "tool": tool_name}

        # 2. Rate limit
        exceeded, retry_after = check_rate_limit("mcp_session")
        if exceeded:
            return {
                "error": "rate_limit_exceeded",
                "status": 429,
                "retry_after_seconds": retry_after,
                "tool": tool_name,
            }

        # 3. Idempotency check
        idem_key = idempotency_key or arguments.get("idempotency_key")
        if idem_key:
            user_scope = arguments.get("user_id", "global")
            cache_key = f"{user_scope}:{idem_key}"
            if cache_key in self._idempotency_cache:
                cached = self._idempotency_cache[cache_key]
                logger.info("Idempotent replay for key %s", idem_key)
                return {**cached, "idempotent_replay": True}

        # 4. Dispatch
        handler = self._get_handler(tool_name)
        if handler is None:
            return {
                "error": f"Unknown tool: {tool_name}",
                "status": 404,
                "tool": tool_name,
            }

        try:
            result = await handler(arguments)
        except Exception as exc:
            logger.error("MCP tool %s failed: %s", tool_name, exc, exc_info=True)
            result = {
                "error": f"Internal error: {exc}",
                "status": 500,
                "tool": tool_name,
            }

        # 5. Audit log
        user_id = arguments.get("user_id")
        await log_mcp_action(
            action=tool_name,
            details={
                "tool_name": tool_name,
                "parameters": _sanitize_args(arguments),
                "result_status": result.get("status", 200),
                "result_error": result.get("error") if "error" in result else None,
            },
            user_id=user_id,
            idempotency_key=idem_key,
            customer_agent_type=self._customer_agent_type,
        )

        # 6. Cache for idempotency
        if idem_key and result.get("status") not in (401, 429, 500):
            user_scope = arguments.get("user_id", "global")
            cache_key = f"{user_scope}:{idem_key}"
            self._idempotency_cache[cache_key] = result

        return result

    def _get_handler(self, tool_name: str):
        """Map tool name to handler method."""
        handlers = {
            "list_user_trusts": self._handle_list_user_trusts,
            "get_trust_state": self._handle_get_trust_state,
            "get_governance_health": self._handle_get_governance_health,
            "get_tax_calendar": self._handle_get_tax_calendar,
            "get_task_list": self._handle_get_task_list,
            "submit_trust_update": self._handle_submit_trust_update,
            "submit_asset_values": self._handle_submit_asset_values,
            "complete_task": self._handle_complete_task,
            "submit_minutes_draft": self._handle_submit_minutes_draft,
            "update_beneficiary": self._handle_update_beneficiary,
        }
        return handlers.get(tool_name)

    # ==================== READ-ONLY HANDLERS ====================

    async def _handle_list_user_trusts(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return await self._client.get_user_trusts(args["user_id"])

    async def _handle_get_trust_state(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return await self._client.get_trust_state(args["user_id"], args["trust_id"])

    async def _handle_get_governance_health(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return await self._client.get_governance_health(args["user_id"], args["trust_id"])

    async def _handle_get_tax_calendar(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return await self._client.get_tax_calendar(
            args["user_id"], args["trust_id"], args.get("tax_year")
        )

    async def _handle_get_task_list(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return await self._client.get_task_list(
            args["user_id"], args["trust_id"], args.get("status")
        )

    # ==================== STUBBED WRITE HANDLERS ====================

    async def _handle_submit_trust_update(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return await self._client.submit_trust_update(
            args["user_id"], args["trust_id"], args.get("updates", {})
        )

    async def _handle_submit_asset_values(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return await self._client.submit_asset_values(
            args["user_id"], args["trust_id"], args.get("asset_values", [])
        )

    async def _handle_complete_task(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return await self._client.complete_task(
            args["user_id"], args["trust_id"], args["task_id"]
        )

    async def _handle_submit_minutes_draft(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return await self._client.submit_minutes_draft(
            args["user_id"], args["trust_id"], args.get("minutes_data", {})
        )

    async def _handle_update_beneficiary(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return await self._client.update_beneficiary(
            args["user_id"], args["trust_id"], args["beneficiary_id"], args.get("updates", {})
        )


# ==================== HELPERS ====================

def _get_env_api_key() -> Optional[str]:
    """Read API key from environment."""
    import os
    return os.environ.get("ADMIN_API_KEY")


def _sanitize_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """Remove sensitive fields from args before audit logging."""
    sanitized = {k: v for k, v in args.items() if k not in ("api_key", "password")}
    return sanitized


# ==================== CLI ENTRYPOINT ====================

def main():
    """
    MCP server CLI entrypoint.

    In a full MCP deployment, this would start the stdio transport loop.
    For Phase 1 scaffold, it validates configuration and prints tool list.

    Full MCP stdio transport will be wired in Phase 1 deployment.
    """
    import os
    api_key = os.environ.get("ADMIN_API_KEY")
    if not api_key:
        print("ERROR: ADMIN_API_KEY environment variable not set.", file=__import__("sys").stderr)
        raise SystemExit(1)

    server = MCPServer(api_key=api_key)
    tools = server.list_tools()

    print(f"TrustOffice MCP Server — Phase 1 (read-only)")
    print(f"Protocol version: {PROTOCOL_VERSION}")
    print(f"Tools available: {len(tools)}")
    print()
    for tool in tools:
        status = "READ" if tool.get("readOnly") else "STUBBED (Phase 2)"
        print(f"  [{status}] {tool['name']}: {tool['description']}")
    print()
    print("MCP stdio transport will be activated on deployment.")
    print("See: docs/AGENT-PROTOCOL-SPEC.md for full protocol specification.")


if __name__ == "__main__":
    main()