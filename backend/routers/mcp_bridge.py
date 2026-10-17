# MCP Bridge — read-only customer-state surface for external AI agents.
# (Option A: Platform + Agent Bridge — 2026-10-18 council decision.)
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
#   scope; independently revocable. A leaked agent token is not an account
#   takeover — it cannot read anything its user cannot, and it can be killed
#   without touching the user's sessions.
# - Every tool call lands in `agent_audit_log` (who, which tool, which trust,
#   when, args summary). The audit chain is the moat — records, not chat.
# - The MCP payload is hand-rolled JSON-RPC because the mcp/fastmcp SDKs
#   conflict with the backend pin (fastmcp 4.x needs starlette>=1.0; server.py
#   uses Router(on_startup=...) which starlette 1.x removed — verified
#   2026-10-18 in the test venv). No new dependencies.
#
# UPL posture: every tool returns process/record data, never legal advice;
# tool descriptions say so explicitly.

import json
import logging
import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from database import db
from dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp_bridge"])

MCP_PROTOCOL_VERSION = "2025-06-18"
MCP_SERVER_NAME = "trustoffice"
MCP_SERVER_VERSION = "0.1.0"

AGENT_TOKEN_PREFIX = "toag_"



# ==================== AGENT TOKEN ADMIN (human-facing, JWT-authed) ====================

class AgentTokenCreate(BaseModel):
    agent_name: str


def _token_collection():
    return db["agent_tokens"]


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
    raw = AGENT_TOKEN_PREFIX + secrets.token_urlsafe(32)
    doc = {
        "token_id": str(uuid.uuid4()),
        "user_id": user["user_id"],
        "agent_name": name,
        "token_hash": _hash_token(raw),
        "token_hint": raw[-6:],
        "scope": ["read"],
        "created_at": datetime.now(timezone.utc),
        "revoked_at": None,
        "last_used_at": None,
        "call_count": 0,
    }
    await _token_collection().insert_one(doc)
    return {
        "token": raw,  # shown once, never stored in plaintext
        "token_id": doc["token_id"],
        "agent_name": name,
        "scope": doc["scope"],
        "note": "Store this token in your agent's secret store now. It is shown only once.",
    }


@router.get("/tokens")
async def list_agent_tokens(user: dict = Depends(get_current_user)):
    docs = await _token_collection().find(
        {"user_id": user["user_id"], "revoked_at": None},
        {"_id": 0, "token_id": 1, "agent_name": 1, "token_hint": 1, "scope": 1,
         "created_at": 1, "last_used_at": 1, "call_count": 1},
    ).to_list(100)
    return {"tokens": docs}


@router.delete("/tokens/{token_id}")
async def revoke_agent_token(token_id: str, user: dict = Depends(get_current_user)):
    r = await _token_collection().update_one(
        {"token_id": token_id, "user_id": user["user_id"], "revoked_at": None},
        {"$set": {"revoked_at": datetime.now(timezone.utc)}},
    )
    if r.matched_count == 0:
        raise HTTPException(404, "token not found or already revoked")
    return {"revoked": True, "token_id": token_id}


# ==================== MCP TRANSPORT (JSON-RPC over HTTP POST) ====================

async def _authenticate_agent(request: Request) -> dict:
    """Bearer agent-token auth. Returns the token doc (with user_id)."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "agent token required (Authorization: Bearer <agent-token>)")
    raw = auth[7:].strip()
    if not raw.startswith(AGENT_TOKEN_PREFIX):
        raise HTTPException(401, "invalid agent token format")
    tok = await _token_collection().find_one({"token_hash": _hash_token(raw)})
    if not tok or tok.get("revoked_at"):
        raise HTTPException(401, "agent token invalid or revoked")
    await _token_collection().update_one(
        {"token_id": tok["token_id"]},
        {"$set": {"last_used_at": datetime.now(timezone.utc)}, "$inc": {"call_count": 1}},
    )
    return tok


def _hash_token(raw: str) -> str:
    import hashlib
    return hashlib.sha256(raw.encode()).hexdigest()



async def _audit(tok: dict, tool: str, args: dict):
    await db["agent_audit_log"].insert_one({
        "token_id": tok["token_id"],
        "agent_name": tok.get("agent_name"),
        "user_id": tok["user_id"],
        "tool": tool,
        "args_summary": json.dumps(args, default=str)[:500],
        "at": datetime.now(timezone.utc),
    })



# ==================== TOOLS: READ-ONLY CUSTOMER STATE ====================

async def _owned_trust_ids(user_id: str) -> List[tuple]:
    docs = await db["trusts"].find({"user_id": user_id}, {"_id": 0, "trust_id": 1, "name": 1}).to_list(200)
    return [(d.get("trust_id"), d.get("name")) for d in docs]


async def tool_list_deadlines(args: dict, tok: dict) -> dict:
    """Upcoming + overdue compliance deadlines for the caller's trusts."""
    user_id = tok["user_id"]
    trust_id = args.get("trust_id")
    query: Dict[str, Any] = {"user_id": user_id}
    if trust_id:
        query["trust_id"] = trust_id
    docs = await db["deadlines"].find(
        query,
        {"_id": 0, "trust_id": 1, "title": 1, "category": 1, "due_date": 1,
         "status": 1, "priority": 1, "is_statutory": 1},
    ).sort("due_date", 1).to_list(100)
    return {
        "deadlines": docs,
        "note": "Process data, not legal advice. Mark-filed/completion happens in the app.",
    }


async def tool_list_trusts(args: dict, tok: dict) -> dict:
    """The caller's trusts with basic facts (name, state, grantor, revocability)."""
    user_id = tok["user_id"]
    docs = await db["trusts"].find(
        {"user_id": user_id},
        {"_id": 0, "trust_id": 1, "name": 1, "state": 1, "grantor": 1,
         "revocable": 1, "created_at": 1},
    ).to_list(100)
    return {"trusts": docs, "note": "Process data, not legal advice."}


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
    return {
        "trust": owned,
        "documents": docs,
        "note": "Process data, not legal advice. Generation flows live in the app.",
    }


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
    return {"trust": trust, "counts": counts, "note": "Process data, not legal advice."}


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
    await _audit(tok, name or "unknown", args)
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
    tok = await _authenticate_agent(request)
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


def _jsonrpc_error(id_: int, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}



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
        "write_surface": "not implemented (phase 2, gated on template audit + legal review)",
    }