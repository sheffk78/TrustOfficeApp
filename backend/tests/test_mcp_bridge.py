# MCP bridge tests (JOB-20261018-TO-AGENT-BRIDGE) — in-process, real Mongo.
# Covers: token lifecycle, JSON-RPC protocol shape, auth/revocation scoping,
# per-user data isolation, audit log writes, UPL-note presence.
import json
import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "to-mcp-test")
os.environ.setdefault("JWT_SECRET", "test-secret-mcp")
os.environ.setdefault("CORS_ORIGINS", "https://app.trustoffice.app")

from server import app  # noqa: E402
import database as _dbmod  # noqa: E402
from dependencies import create_jwt_token  # noqa: E402
import services.bridge_service as bridge_service  # noqa: E402


def db():
    """Live rebound database object (fresh Motor client per test)."""
    return _dbmod.db


def create_access_token(user_id: str) -> str:
    return create_jwt_token(user_id, f"{user_id}@test.local")


@pytest_asyncio.fixture(autouse=True)
async def _fresh_motor_connection():
    """Each test gets a fresh Motor client + db object so no loop binding survives
    across tests (pytest-asyncio creates a new loop per test; Motor clients bind
    to the loop they first run on and 'Event loop is closed' otherwise)."""
    import motor.motor_asyncio as ma
    import database as _dbmod
    import server as _srv
    import dependencies as _deps
    import routers.mcp_bridge as _bridge
    import services.bridge_service as _bri_svc
    old_client, old_db = _dbmod.client, _dbmod.db
    old_srv_client, old_srv_db = _srv.client, _srv.db
    old_deps_db = _deps.db
    old_bridge_db = _bridge.db
    old_bridge_svc_db = _bri_svc.db
    client = ma.AsyncIOMotorClient(
        os.environ["MONGO_URL"], serverSelectionTimeoutMS=5000, maxPoolSize=20,
    )
    _dbmod.client = client
    _dbmod.db = client[os.environ["DB_NAME"]]
    # Every module that did `from database import db` holds its OWN name binding
    # to the original db object — rebind the ones this suite exercises, or the
    # first test's loop-bound client leaks into later tests ("Event loop closed").
    _srv.client = client
    _srv.db = _dbmod.db
    _deps.db = _dbmod.db
    _bridge.db = _dbmod.db
    _bri_svc.db = _dbmod.db
    # Drop prior test run collections so the agent_audit_log hash chain migrates
    # from a clean genesis every run (legacy rows are deterministic on first write).
    await _dbmod.db.drop_collection("agent_tokens")
    await _dbmod.db.drop_collection("agent_audit_log")
    await _dbmod.db.drop_collection("users")
    await _dbmod.db.drop_collection("subscriptions")
    await _dbmod.db.drop_collection("trusts")
    await _dbmod.db.drop_collection("documents")
    yield
    _dbmod.client, _dbmod.db = old_client, old_db
    _srv.client, _srv.db = old_srv_client, old_srv_db
    _deps.db = old_deps_db
    _bridge.db = old_bridge_db
    _bri_svc.db = old_bridge_svc_db
    client.close()


def _uid(tag):
    return f"mcpuser-{tag}-{uuid.uuid4().hex[:8]}"


async def _bootstrap_user(user_id):
    from datetime import datetime, timezone
    _db = db()
    await _db["users"].insert_one({
        "user_id": user_id, "email": f"{user_id}@test.local", "name": user_id,
    })
    # Active paid subscription — the MCP token gate (and product gate) requires it
    await _db["subscriptions"].insert_one({
        "user_id": user_id, "plan_type": "trustee", "status": "active",
        "current_period_end": "2027-01-01T00:00:00+00:00",
    })


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_token_lifecycle_and_rpc_flow():
    uid = _uid("flow")
    await _bootstrap_user(uid)
    jwt = create_access_token(uid)
    async with await _client() as c:
        # 1. Issue agent token via JWT
        r = await c.post("/api/mcp/tokens", json={"agent_name": "claude-code"},
                         headers={"Authorization": f"Bearer {jwt}"})
        assert r.status_code == 200, r.text
        tok = r.json()["token"]
        assert tok.startswith("toag_")
        token_id = r.json()["token_id"]
        # plaintext token must NOT be stored
        stored = await db()["agent_tokens"].find_one({"token_id": token_id})
        assert stored["token_hash"] and "toag_" not in stored["token_hash"]
        assert stored["status"] == "active"
        assert stored["rate_limit"] == 60
        from datetime import datetime, timezone
        expires = stored["expires_at"]
        if isinstance(expires, str):
            expires = datetime.fromisoformat(expires.replace("Z", "+00:00"))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        assert (expires - datetime.now(timezone.utc)).days >= 89
        # hash-chained audit row for token issuance
        audit = await db()["agent_audit_log"].find_one({"action": "token.issued", "token_id": token_id})
        assert audit and audit.get("entry_hash") and audit.get("prev_hash")

        # 2. initialize handshake
        r = await c.post("/api/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
        body = r.json()
        assert body["result"]["serverInfo"]["name"] == "trustoffice"
        assert body["result"]["protocolVersion"] == "2025-06-18"

        # 3. tools/list — all four read-only tools present with UPL note
        r = await c.post("/api/mcp", json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers={"Authorization": f"Bearer {tok}"})
        tools = r.json()["result"]["tools"]
        names = {t["name"] for t in tools}
        assert {"list_trusts", "get_trust_summary", "list_deadlines", "get_document_status"} <= names
        assert all("not legal advice" in t["description"] for t in tools)
        assert all(t["inputSchema"].get("additionalProperties") is False for t in tools)

        # 4. tools/call list_trusts (user has none yet — empty result, no error)
        r = await c.post("/api/mcp", json={
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "list_trusts", "arguments": {}}},
            headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
        assert r.json()["result"]["isError"] is False
        result_payload = json.loads(r.json()["result"]["content"][0]["text"])
        assert "as_of" in result_payload
        assert "valid_until" in result_payload
        assert "note" in result_payload

        # 4b. hash-chained audit integrity for this token's trail
        errors = await bridge_service.verify_agent_audit_chain()
        assert not errors, errors

        # 5. audit log row written per tools/call (only tools/call calls are audited)
        rows = await db()["agent_audit_log"].count_documents({"user_id": uid})
        assert rows >= 1

        # 6. revoke → token dies
        r = await c.delete(f"/api/mcp/tokens/{token_id}", headers={"Authorization": f"Bearer {jwt}"})
        assert r.status_code == 200
        r = await c.post("/api/mcp", json={
            "jsonrpc": "2.0", "id": 9, "method": "tools/list", "params": {}},
            headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_agent_token_cannot_authenticate_as_user_api():
    """Key isolation property: agent token ≠ user JWT. It must fail on /api/auth/me."""
    uid = _uid("isolation")
    await _bootstrap_user(uid)
    jwt = create_access_token(uid)
    async with await _client() as c:
        r = await c.post("/api/mcp/tokens", json={"agent_name": "hermes"},
                         headers={"Authorization": f"Bearer {jwt}"})
        tok = r.json()["token"]
        # agent token presented to a normal user endpoint must be rejected
        r = await c.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_data_isolation_between_users():
    """Trusts of other users are invisible to the agent token (scoped reads)."""
    u1, u2 = _uid("iso1"), _uid("iso2")
    await _bootstrap_user(u1)
    await _bootstrap_user(u2)
    await db()["trusts"].insert_one({
        "trust_id": f"trust_{uuid.uuid4().hex[:10]}", "user_id": u2, "name": "Not Yours Trust",
    })
    jwt1 = create_access_token(u1)
    async with await _client() as c:
        r = await c.post("/api/mcp/tokens", json={"agent_name": "probe"},
                         headers={"Authorization": f"Bearer {jwt1}"})
        tok = r.json()["token"]
        r = await c.post("/api/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "list_trusts", "arguments": {}}},
            headers={"Authorization": f"Bearer {tok}"})
        text = r.json()["result"]["content"][0]["text"]
        assert "Not Yours Trust" not in text


@pytest.mark.asyncio
async def test_bad_requests_shape():
    uid = _uid("shape")
    await _bootstrap_user(uid)
    jwt = create_access_token(uid)
    async with await _client() as c:
        r = await c.post("/api/mcp/tokens", json={"agent_name": "x"},
                         headers={"Authorization": f"Bearer {jwt}"})
        tok = r.json()["token"]
        # missing auth
        r = await c.post("/api/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert r.status_code == 401
        # unknown method
        r = await c.post("/api/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "resources/list"},
                         headers={"Authorization": f"Bearer {tok}"})
        assert r.json()["error"]["code"] == -32601
        # unknown tool: in-band JSON-RPC error (tool-level errors ride the 200),
        # and its error message must not hint at any write surface
        r = await c.post("/api/mcp", json={
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "write_trust", "arguments": {}}},
            headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
        assert r.json()["error"]["message"] == "unknown tool: write_trust"