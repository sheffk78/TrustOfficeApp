# MCP Bridge — read-only customer-state surface for external AI agents.
# (Consolidated with /api/bridge council conditions, 2026-10-18.)
#
# Protocol: TrustOffice is the system of record; the customer's agent plugs in
# as a governed interface. This router implements the MCP streamable-HTTP
# (JSON-RPC) surface INSIDE the existing FastAPI app:
#
# - READ-ONLY tools first (deadlines/calendar, trust facts, document status).
#   The guarded-write workflow is a later phase, gated on the template audit +
#   legal review (JOB-20261018-TO-AGENT-BRIDGE).
# - Auth: scoped agent tokens (`agent_tokens` collection), deliberately kept
#   separate from user JWTs. One token per (user, agent-name); read-only
#   scope; independently revocable; 90-day expiry; per-token rate limit 60/h.
#   A leaked agent token is not an account takeover — it cannot read anything
#   its user cannot, and it can be killed without touching the user's sessions.
# - Every JSON-RPC call is server-side validated (hash, status, expiry, rate).
# - Every tools/call lands in `agent_audit_log` as a tamper-evident hash-chain
#   entry (seq, prev_hash, entry_hash, server timestamp), matching bridge_audit.
# - Tool result payloads include `as_of` / `valid_until` freshness metadata
#   without changing the JSON-RPC result envelope.
# - The MCP payload is hand-rolled JSON-RPC because the mcp/fastmcp SDKs
#   conflict with the backend pin (fastmcp 4.x needs starlette>=1.0; server.py
#   uses Router(on_startup=...) which starlette 1.x removed). No new dependencies.
#
# UPL posture: every tool returns process/record data, never legal advice;
# tool descriptions say so explicitly.

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from database import db
from dependencies import get_current_user
from services import bridge_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp_bridge"])

MCP_PROTOCOL_VERSION = "2025-06-18"
MCP_SERVER_NAME = "trustoffice"
MCP_SERVER_VERSION = "0.2.0"


class AgentTokenCreate(BaseModel):
    agent_name: str


# ==================== AGENT TOKEN ADMIN (human-facing, JWT-authed) ====================

@router.post("/tokens")
async def create_agent_token(payload: AgentTokenCreate, user: dict = Depends(get_current_user)):
    """Issue a scoped read-only MCP token for one external agent."""
    from server import get_subscription_state
    state = await get_subscription_state(user["user_id"])
    if not state.is_active:
        raise HTTPException(403, "An active subscription is required to connect an AI agent.")
    name = (payload.agent_name or "").strip()
    if not name or len(name) > 80:
        raise HTTPException(422, "agent_name required (max 80 chars)")
    result = await bridge_service.issue_mcp_token(
        user_id=user["user_id"],
        agent_name=name,
        scopes=["read"],
    )
    return result


@router.get("/tokens")
async def list_agent_tokens(user: dict = Depends(get_current_user)):
    tokens = await bridge_service.list_mcp_tokens(user["user_id"])
    return {"tokens": tokens}


@router.delete("/tokens/{token_id}")
async def revoke_agent_token(token_id: str, user: dict = Depends(get_current_user)):
    revoked = await bridge_service.revoke_mcp_token(token_id, user["user_id"])
    if not revoked:
        raise HTTPException(404, "token not found or already revoked")
    return {"revoked": True, "token_id": token_id}


# ==================== MCP TRANSPORT (JSON-RPC over HTTP POST) ====================

async def _authenticate_agent(request: Request) -> dict:
    """Bearer agent-token auth with server-side validation (no caching)."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "agent token required (Authorization: Bearer ***")
    raw = auth[7:].strip()

    tok = await bridge_service.validate_mcp_token(raw)
    if tok is None:
        raise HTTPException(401, "agent token invalid, expired, or revoked")

    limit = tok.get("rate_limit", bridge_service.DEFAULT_RATE_LIMIT)
    if not bridge_service.check_rate_limit(tok["token_id"], limit):
        raise HTTPException(
            status_code=429,
            detail={"message": "rate limit exceeded", "retry_after_seconds": int(3600 - (datetime.now(timezone.utc).timestamp() % 3600)) or 3600},
        )

    await bridge_service.record_usage(tok["token_id"])

    await bridge_service.append_agent_audit(
        token_id=tok["token_id"],
        user_id=tok["user_id"],
        action="request.authorized",
        resource=request.url.path,
        request_meta={"method": request.method, "client_ip": request.client.host if request.client else None},
    )

    return tok


# ==================== TOOLS: READ-ONLY CUSTOMER STATE ====================

async def _owned_trust_ids(user_id: str) -> List[tuple]:
    docs = await db["trusts"].find({"user_id": user_id}, {"_id": 0, "trust_id": 1, "name": 1}).to_list(200)
    return [(d.get("trust_id"), d.get("name")) for d in docs]


async def tool_list_deadlines(args: dict, tok: dict) -> dict:
    """Upcoming + overdue compliance deadlines for the caller's trusts."""
    user_id = tok["user_id"]
    trust_id = args.get("trust_id")
    items = await bridge_service.fetch_trust_calendar(tok["user_id"], trust_id)
    return bridge_service.wrap_freshness({
        "deadlines": items,
        "note": "Process data, not legal advice. Mark-filed/completion happens in the app.",
    })


async def tool_list_trusts(args: dict, tok: dict) -> dict:
    """The caller's trusts with basic facts (name, state, grantor, revocability)."""
    items = await bridge_service.fetch_trust_facts(tok["user_id"], None)
    return bridge_service.wrap_freshness({
        "trusts": items,
        "note": "Process data, not legal advice.",
    })


async def tool_get_document_status(args: dict, tok: dict) -> dict:
    """Document/minute generation status for one trust."""
    user_id = tok["user_id"]
    trust_id = args.get("trust_id")
    if not trust_id:
        raise HTTPException(422, "trust_id required")
    owned = await db["trusts"].find_one({"user_id": user_id, "trust_id": trust_id}, {"_id": 0, "name": 1})
    if not owned:
        raise HTTPException(403, "trust not found in your account")
    docs = await db["documents"].find(
        {"user_id": user_id, "trust_id": trust_id},
        {"_id": 0, "document_id": 1, "document_type": 1, "status": 1, "created_at": 1, "generated_at": 1},
    ).sort("created_at", -1).to_list(100)
    return bridge_service.wrap_freshness({
        "trust": owned,
        "documents": docs,
        "note": "Process data, not legal advice. Generation flows live in the app.",
    })


async def tool_get_trust_summary(args: dict, tok: dict) -> dict:
    """One-trust snapshot: key facts + counts (deadlines, docs, beneficiaries)."""
    user_id = tok["user_id"]
    trust_id = args.get("trust_id")
    if not trust_id:
        raise HTTPException(422, "trust_id required")
    trust = await db["trusts"].find_one(
        {"user_id": user_id, "trust_id": trust_id},
        {"_id": 0, "trust_id": 1, "name": 1, "state": 1, "grantor": 1, "revocable": 1},
    )
    if not trust:
        raise HTTPException(403, "trust not found in your account")
    counts = {}
    counts["deadlines_open"] = await db["deadlines"].count_documents(
        {"user_id": user_id, "trust_id": trust_id, "status": {"$nin": ["completed", "waived"]}})
    counts["documents"] = await db["documents"].count_documents(
        {"user_id": user_id, "trust_id": trust_id})
    counts["beneficiaries"] = await db["beneficiaries"].count_documents(
        {"user_id": user_id, "trust_id": trust_id})
    return bridge_service.wrap_freshness({
        "trust": trust,
        "counts": counts,
        "note": "Process data, not legal advice.",
    })


TOOLS = {
    "list_trusts": {
        "description": ("List the user's trusts with basic facts (name, governing state, grantor, "
                        "revocability). Process data, not legal advice."),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "fn": tool_list_trusts,
    },
    "get_trust_summary": {
        "description": ("One-trust snapshot: facts plus open-deadline/document/beneficiary counts. "
                        "Process data, not legal advice."),
        "input_schema": {"type": "object", "required": ["trust_id"],
                         "properties": {"trust_id": {"type": "string"}},
                         "additionalProperties": False},
        "fn": tool_get_trust_summary,
    },
    "list_deadlines": {
        "description": ("Upcoming and overdue compliance deadlines across the user's trusts "
                        "(tax filings, reviews). Read-only: completion/mark-filed stays in the app. "
                        "Process data, not legal advice."),
        "input_schema": {"type": "object",
                         "properties": {"trust_id": {"type": "string"}},
                         "additionalProperties": False},
        "fn": tool_list_deadlines,
    },
    "get_document_status": {
        "description": ("Document and minutes generation status for one trust. Read-only: "
                        "generation/edition stays in the app. Process data, not legal advice."),
        "input_schema": {"type": "object", "required": ["trust_id"],
                         "properties": {"trust_id": {"type": "string"}},
                         "additionalProperties": False},
        "fn": tool_get_document_status,
    },
}


# ==================== JSON-RPC METHODS ====================

async def _rpc_initialize(req: dict, tok: dict) -> dict:
    return {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": MCP_SERVER_NAME, "version": MCP_SERVER_VERSION},
    }


async def _rpc_tools_list(req: dict, tok: dict) -> dict:
    return {"tools": [
        {"name": name,
         "description": spec["description"],
         "inputSchema": spec["input_schema"]}
        for name, spec in TOOLS.items()
    ]}


async def _rpc_tools_call(req: dict, tok: dict) -> dict:
    params = req.get("params") or {}
    name: str = params.get("name") or ""
    args = params.get("arguments") or {}
    spec = TOOLS.get(name)
    if not spec:
        raise HTTPException(404, f"unknown tool: {name}")
    await bridge_service.append_agent_audit(
        token_id=tok["token_id"],
        user_id=tok["user_id"],
        action="tool.called",
        resource=name,
        request_meta={"args_summary": json.dumps(args, default=str)[:500]},
    )
    try:
        result = await spec["fn"](args, tok)
        return {"content": [{"type": "text", "text": json.dumps(result, default=str)}],
                "isError": False}
    except HTTPException as e:
        return {"content": [{"type": "text", "text": json.dumps({"error": e.detail})}],
                "isError": True}


_RPC_METHODS = {
    "initialize": _rpc_initialize,
    "tools/list": _rpc_tools_list,
    "tools/call": _rpc_tools_call,
}


@router.post("")
@router.post("/")
async def mcp_post(request: Request):
    """MCP streamable-HTTP endpoint (JSON-RPC; SSE responses not needed for sync calls)."""
    try:
        tok = await _authenticate_agent(request)
    except HTTPException as e:
        # Auth/rate-limit problems are transport-level. Rate limit still returns
        # a JSON-RPC error object inside the 429 response per council conditions.
        if e.status_code == 429:
            detail = e.detail if isinstance(e.detail, dict) else {"message": str(e.detail)}
            return JSONResponse(
                status_code=429,
                content=_jsonrpc_error(
                    None,
                    -32001,
                    detail.get("message", "rate limit exceeded"),
                    data={"retry_after_seconds": detail.get("retry_after_seconds", 3600)},
                ),
            )
        raise
    try:
        req = await request.json()
    except Exception:
        raise HTTPException(400, "invalid JSON body")
    if req.get("jsonrpc") != "2.0" or not isinstance(req.get("id"), int):
        raise HTTPException(422, "not a JSON-RPC 2.0 request with integer id")
    method = req.get("method")
    handler = _RPC_METHODS.get(method)
    if not handler:
        return _jsonrpc_error(req["id"], -32601, f"method not found: {method}")
    try:
        result = await handler(req, tok)
        return _jsonrpc_result(req["id"], result)
    except HTTPException as e:
        if e.status_code in (401, 403):
            raise  # auth problems are transport-level, not tool-level
        return _jsonrpc_error(req["id"], -32000, str(e.detail))


def _jsonrpc_result(id_: int, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _jsonrpc_error(id_: Optional[int], code: int, message: str, data: Optional[dict] = None) -> dict:
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    out: Dict[str, Any] = {"jsonrpc": "2.0", "error": error}
    if id_ is not None:
        out["id"] = id_
    return out


# Health/metadata for agent setup flows (no secrets):
@router.get("/info")
async def mcp_info():
    return {
        "server": MCP_SERVER_NAME,
        "protocol_version": MCP_PROTOCOL_VERSION,
        "transport": "streamable-http (JSON-RPC POST /api/mcp)",
        "auth": "per-agent bearer token; issue in app under Settings > AI Agents",
        "tools": sorted(TOOLS.keys()),
        "read_only": True,
        "token_lifetime_days": bridge_service.MCP_TOKEN_LIFETIME_DAYS,
        "rate_limit_requests_per_hour": bridge_service.DEFAULT_RATE_LIMIT,
        "write_surface": "not implemented (phase 2, gated on template audit + legal review)",
    }
