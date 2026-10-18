#!/usr/bin/env python3
"""
TrustOffice Agent Bridge — thin MCP stdio server.

Exposes read-only bridge tools to external customer agents over the Model Context
Protocol (MCP) using a minimal, stdlib-only JSON-RPC stdio loop. No heavy MCP SDK
dependencies are required.

Tools:
  - get_trust_calendar
  - get_trust_facts
  - get_document_status
  - validate_document

Environment:
  BRIDGE_BASE_URL  Base URL of the TrustOffice bridge API (e.g. https://api.trustoffice.app/api/bridge)
  BRIDGE_TOKEN     Opaque agent token issued via POST /api/bridge/admin/tokens

Run:
  BRIDGE_BASE_URL=http://localhost:8000/api/bridge BRIDGE_TOKEN=tob_... python backend/bridge_mcp_server.py
"""

import json
import logging
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("bridge_mcp")


class BridgeClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _request(self, method: str, path: str, body: Optional[bytes] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {
            "X-Agent-Token": self.token,
            "Accept": "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, method=method, headers=headers, data=body)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(text)
            except Exception:
                detail = {"detail": text}
            raise BridgeAPIError(exc.code, detail) from exc

    def get_trust_calendar(self, trust_id: Optional[str] = None) -> Dict[str, Any]:
        q = f"?trust_id={trust_id}" if trust_id else ""
        return self._request("GET", f"/trust-calendar{q}")

    def get_trust_facts(self, trust_id: Optional[str] = None) -> Dict[str, Any]:
        q = f"?trust_id={trust_id}" if trust_id else ""
        return self._request("GET", f"/trust-facts{q}")

    def get_document_status(self, trust_id: Optional[str] = None) -> Dict[str, Any]:
        q = f"?trust_id={trust_id}" if trust_id else ""
        return self._request("GET", f"/document-status{q}")

    def validate_document(self, trust_id: str, document_id: str, draft_reference: Optional[str] = None) -> Dict[str, Any]:
        payload = {"trust_id": trust_id, "document_id": document_id}
        if draft_reference:
            payload["draft_reference"] = draft_reference
        return self._request("POST", "/validate-document", json.dumps(payload).encode("utf-8"))


class BridgeAPIError(Exception):
    def __init__(self, status: int, detail: Any):
        self.status = status
        self.detail = detail
        super().__init__(f"Bridge API {status}: {detail}")


TOOLS: List[Dict[str, Any]] = [
    {
        "name": "get_trust_calendar",
        "description": "Read-only: upcoming/overdue trust deadlines and obligations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "trust_id": {"type": "string", "description": "Optional trust ID. If omitted, returns deadlines across all customer trusts."},
            },
        },
    },
    {
        "name": "get_trust_facts",
        "description": "Read-only: trust name, type, jurisdiction, grantor, revocability, formation date. Excludes SSN, asset values, and beneficiary contact info.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "trust_id": {"type": "string", "description": "Optional trust ID. If omitted, returns all customer trusts."},
            },
        },
    },
    {
        "name": "get_document_status",
        "description": "Read-only: vault document and minutes status list. No file content is returned.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "trust_id": {"type": "string", "description": "Optional trust ID. If omitted, returns documents across all customer trusts."},
            },
        },
    },
    {
        "name": "validate_document",
        "description": "Generic-verdict validation: returns only PASS / FAIL_COMPLETENESS / FAIL_FORMAT / FAIL_CONSISTENCY plus a draft reference. No rulebook detail.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "trust_id": {"type": "string"},
                "document_id": {"type": "string"},
                "draft_reference": {"type": "string", "description": "Optional draft reference to echo back."},
            },
            "required": ["trust_id", "document_id"],
        },
    },
]


def _dispatch(client: BridgeClient, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    if name == "get_trust_calendar":
        return client.get_trust_calendar(args.get("trust_id"))
    if name == "get_trust_facts":
        return client.get_trust_facts(args.get("trust_id"))
    if name == "get_document_status":
        return client.get_document_status(args.get("trust_id"))
    if name == "validate_document":
        return client.validate_document(
            args["trust_id"],
            args["document_id"],
            args.get("draft_reference"),
        )
    raise ValueError(f"unknown tool: {name}")


def _result(content: Any) -> List[Dict[str, Any]]:
    return [{"type": "text", "text": json.dumps(content, indent=2)}]


def _error_content(code: int, message: str, data: Optional[Any] = None) -> Dict[str, Any]:
    out = {"code": code, "message": message}
    if data is not None:
        out["data"] = data
    return out


def _send(obj: Dict[str, Any]) -> None:
    text = json.dumps(obj) + "\n"
    sys.stdout.write(text)
    sys.stdout.flush()


def run_server(client: BridgeClient) -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            _send({"jsonrpc": "2.0", "id": None, "error": _error_content(-32700, "Parse error")})
            continue

        msg_id = msg.get("id")
        method = msg.get("method")

        if method == "initialize":
            _send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "trustoffice-agent-bridge", "version": "1.0.0"},
                    "capabilities": {"tools": {}},
                },
            })
            continue

        if method == "notifications/initialized" or method == "initialized":
            continue

        if method == "tools/list":
            _send({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}})
            continue

        if method == "tools/call":
            params = msg.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})
            try:
                result = _dispatch(client, name, args)
                _send({"jsonrpc": "2.0", "id": msg_id, "result": {"content": _result(result), "isError": False}})
            except BridgeAPIError as exc:
                _send({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": _result({"error": exc.detail, "status": exc.status}),
                        "isError": True,
                    },
                })
            except Exception as exc:
                logger.exception("tool dispatch failed")
                _send({"jsonrpc": "2.0", "id": msg_id, "error": _error_content(-32603, str(exc))})
            continue

        if msg_id is not None:
            _send({"jsonrpc": "2.0", "id": msg_id, "error": _error_content(-32601, f"Method not found: {method}")})


def main() -> None:
    base_url = os.environ.get("BRIDGE_BASE_URL", "http://localhost:8000/api/bridge")
    token = os.environ.get("BRIDGE_TOKEN")
    if not token:
        logger.error("BRIDGE_TOKEN environment variable is required")
        sys.exit(1)
    client = BridgeClient(base_url, token)
    run_server(client)


if __name__ == "__main__":
    main()
