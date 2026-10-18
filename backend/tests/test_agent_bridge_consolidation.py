# Cross-surface agent-bridge consolidation tests.
# Verifies that /api/mcp (self-serve, live production surface) and /api/bridge
# (admin-issued council-hardened surface) enforce the same token lifecycle
# rules: 90-day expiry, SHA-256 at rest, 60 req/h rate limit, instant revocation.
# Also verifies bridge_mcp_server.py maps its 4 tools onto the hardened /api/bridge
# endpoints.
import asyncio
import json
import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "to-agent-bridge-consolidation-test")
os.environ.setdefault("JWT_SECRET", "test-secret-agent-bridge")
os.environ.setdefault("INTERNAL_API_KEY", "test-internal-key")
os.environ.setdefault("CORS_ORIGINS", "https://app.trustoffice.app")

from server import app  # noqa: E402
import database as _dbmod  # noqa: E402
import services.bridge_service as bridge_service  # noqa: E402
from dependencies import create_jwt_token, hash_password  # noqa: E402


def db():
    return _dbmod.db


def _uid(tag):
    return f"abt-{tag}-{uuid.uuid4().hex[:8]}"


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture(autouse=True, loop_scope="module")
async def _fresh_db():
    import server as _srv
    import dependencies as _deps
    import routers.mcp_bridge as _mcp
    import routers.bridge as _bridge
    import routers.admin as _tadmin
    old_client, old_db = _dbmod.client, _dbmod.db
    old_srv_client, old_srv_db = _srv.client, _srv.db
    old_deps_db = _deps.db
    old_mcp_db = _mcp.db
    old_bridge_db = _bridge.db
    old_tadmin_db = _tadmin.db
    old_bridge_svc_db = bridge_service.db
    import motor.motor_asyncio as ma
    client = ma.AsyncIOMotorClient(
        os.environ["MONGO_URL"], serverSelectionTimeoutMS=5000, maxPoolSize=20,
    )
    _dbmod.client = client
    _dbmod.db = client[os.environ["DB_NAME"]]
    _srv.client = client
    _srv.db = _dbmod.db
    _deps.db = _dbmod.db
    _mcp.db = _dbmod.db
    _bridge.db = _dbmod.db
    _tadmin.db = _dbmod.db
    bridge_service.db = _dbmod.db
    await _dbmod.db.drop_collection("agent_tokens")
    await _dbmod.db.drop_collection("agent_audit_log")
    await _dbmod.db.drop_collection("bridge_audit")
    await _dbmod.db.drop_collection("users")
    await _dbmod.db.drop_collection("subscriptions")
    await _dbmod.db.drop_collection("trusts")
    await _dbmod.db.drop_collection("documents")
    await _dbmod.db.drop_collection("beneficiaries")
    await _dbmod.db.drop_collection("deadlines")
    yield
    _dbmod.client, _dbmod.db = old_client, old_db
    _srv.client, _srv.db = old_srv_client, old_srv_db
    _deps.db = old_deps_db
    _mcp.db = old_mcp_db
    _bridge.db = old_bridge_db
    _tadmin.db = old_tadmin_db
    bridge_service.db = old_bridge_svc_db
    client.close()


async def _bootstrap_user(user_id, admin=False):
    from server import get_subscription_state
    pwd = hash_password("Password123!")
    await db()["users"].insert_one({
        "user_id": user_id,
        "email": f"{user_id}@test.local",
        "name": user_id,
        "password_hash": pwd,
        "role": "admin" if admin else "customer",
        "email_verified": True,
        "is_admin": admin,
    })
    if not admin:
        await db()["subscriptions"].insert_one({
            "user_id": user_id,
            "plan_type": "trustee",
            "status": "active",
            "current_period_end": "2027-01-01T00:00:00+00:00",
        })
        state = await get_subscription_state(user_id)
        assert state.is_active


def _jwt(user_id):
    return create_jwt_token(user_id, f"{user_id}@test.local")


async def _issue_mcp_token(user_id):
    async with await _client() as c:
        r = await c.post("/api/mcp/tokens", json={"agent_name": "cross-test"},
                         headers={"Authorization": f"Bearer {_jwt(user_id)}"})
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["token_id"], r.json()


async def _issue_bridge_token(admin_id, customer_id):
    async with await _client() as c:
        r = await c.post("/api/bridge/admin/tokens", json={
            "customer_id": customer_id,
            "scopes": ["read"],
        }, headers={"Authorization": f"Bearer {_jwt(admin_id)}"})
    assert r.status_code == 201, r.text
    return r.json()["token"], r.json()["token_id"], r.json()


@pytest.mark.asyncio(loop_scope="module")
async def test_mcp_token_has_council_conditions():
    uid = _uid("mcp")
    await _bootstrap_user(uid)
    token, token_id, body = await _issue_mcp_token(uid)
    assert token.startswith("toag_")
    stored = await db()["agent_tokens"].find_one({"token_id": token_id})
    assert stored["status"] == "active"
    assert stored["token_hash"] and "toag_" not in stored["token_hash"]
    assert stored["rate_limit"] == 60
    assert body["rate_limit"] == 60
    assert body["expires_at"]
    expires = stored["expires_at"]
    if isinstance(expires, str):
        expires = datetime.fromisoformat(expires.replace("Z", "+00:00"))
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    assert (expires - datetime.now(timezone.utc)).days >= 89


@pytest.mark.asyncio(loop_scope="module")
async def test_bridge_token_has_council_conditions():
    admin_id = _uid("admin")
    cust_id = _uid("cust")
    await _bootstrap_user(admin_id, admin=True)
    await _bootstrap_user(cust_id)
    token, token_id, body = await _issue_bridge_token(admin_id, cust_id)
    assert token.startswith("tob_")
    stored = await db()["agent_tokens"].find_one({"token_id": token_id})
    assert stored["status"] == "active"
    assert stored["token_hash"] and "tob_" not in stored["token_hash"]
    assert stored["rate_limit"] == 60
    assert body["rate_limit"] == 60
    assert body["expires_at"]
    expires = stored["expires_at"]
    if isinstance(expires, str):
        expires = datetime.fromisoformat(expires.replace("Z", "+00:00"))
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    assert (expires - datetime.now(timezone.utc)).days >= 89


@pytest.mark.asyncio(loop_scope="module")
async def test_revoke_makes_token_dead_on_both_surfaces():
    uid = _uid("rev-mcp")
    await _bootstrap_user(uid)
    mtok, mtid, _ = await _issue_mcp_token(uid)
    admin_id = _uid("rev-admin")
    await _bootstrap_user(admin_id, admin=True)
    btok, btid, _ = await _issue_bridge_token(admin_id, uid)
    async with await _client() as c:
        # revoke MCP token
        r = await c.delete(f"/api/mcp/tokens/{mtid}", headers={"Authorization": f"Bearer {_jwt(uid)}"})
        assert r.status_code == 200
        r = await c.post("/api/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                         headers={"Authorization": f"Bearer {mtok}"})
        assert r.status_code == 401
        # revoke bridge token
        r = await c.post(f"/api/bridge/admin/tokens/{btid}/revoke",
                         json={"reason": "test"},
                         headers={"Authorization": f"Bearer {_jwt(admin_id)}"})
        assert r.status_code == 200
        r = await c.get("/api/bridge/trust-calendar", headers={"X-Agent-Token": btok})
        assert r.status_code == 401


@pytest.mark.asyncio(loop_scope="module")
async def test_expired_tokens_rejected():
    uid = _uid("exp")
    await _bootstrap_user(uid)
    # Directly insert an expired MCP token
    raw = bridge_service.MCP_TOKEN_PREFIX + bridge_service.secrets.token_urlsafe(bridge_service.MCP_TOKEN_RANDOM_BYTES)
    token_id = f"mtok_{uuid.uuid4().hex[:12]}"
    await db()["agent_tokens"].insert_one({
        "token_id": token_id,
        "user_id": uid,
        "customer_id": uid,
        "agent_name": "expired",
        "token_hash": bridge_service._hash_token(raw),
        "token_hint": raw[-6:],
        "scope": ["read"],
        "scopes": ["read"],
        "status": "active",
        "created_at": datetime.now(timezone.utc) - timedelta(days=100),
        "expires_at": datetime.now(timezone.utc) - timedelta(days=10),
        "rate_limit": 60,
        "call_count": 0,
    })
    async with await _client() as c:
        r = await c.post("/api/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                         headers={"Authorization": f"Bearer {raw}"})
        assert r.status_code == 401


@pytest.mark.asyncio(loop_scope="module")
async def test_rate_limit_60_per_hour_on_mcp():
    uid = _uid("rl-mcp")
    await _bootstrap_user(uid)
    token, token_id, _ = await _issue_mcp_token(uid)
    bridge_service.reset_rate_limit(token_id)
    async with await _client() as c:
        for i in range(60):
            r = await c.post("/api/mcp", json={"jsonrpc": "2.0", "id": i, "method": "tools/list"},
                             headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 200, f"call {i} failed"
        r = await c.post("/api/mcp", json={"jsonrpc": "2.0", "id": 60, "method": "tools/list"},
                         headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 429
        body = r.json()
        assert body.get("error")
        assert body["error"]["code"] == -32001
        assert "rate limit" in body["error"]["message"].lower()


@pytest.mark.asyncio(loop_scope="module")
async def test_rate_limit_60_per_hour_on_bridge():
    uid = _uid("rl-br")
    await _bootstrap_user(uid)
    admin_id = _uid("rl-admin")
    await _bootstrap_user(admin_id, admin=True)
    token, token_id, _ = await _issue_bridge_token(admin_id, uid)
    bridge_service.reset_rate_limit(token_id)
    async with await _client() as c:
        for i in range(60):
            r = await c.get("/api/bridge/trust-calendar", headers={"X-Agent-Token": token})
            assert r.status_code == 200, f"call {i} failed"
        r = await c.get("/api/bridge/trust-calendar", headers={"X-Agent-Token": token})
        assert r.status_code == 429
        assert "rate limit" in r.json().get("detail", "").lower()


@pytest.mark.asyncio(loop_scope="module")
async def test_both_surfaces_share_agent_audit_hash_chain():
    uid = _uid("chain")
    await _bootstrap_user(uid)
    await _issue_mcp_token(uid)
    admin_id = _uid("chain-admin")
    await _bootstrap_user(admin_id, admin=True)
    await _issue_bridge_token(admin_id, uid)
    errors = await bridge_service.verify_agent_audit_chain()
    assert not errors, errors


# ==================== bridge_mcp_server.py tool mapping ====================

class FakeBridgeClient:
    """Records the endpoint + arguments chosen by bridge_mcp_server.py dispatch."""
    def __init__(self):
        self.calls = []

    def _request(self, method, path, body=None):
        self.calls.append((method, path, body))
        return {"ok": True}

    def get_trust_calendar(self, trust_id=None):
        q = f"?trust_id={trust_id}" if trust_id else ""
        return self._request("GET", f"/trust-calendar{q}")

    def get_trust_facts(self, trust_id=None):
        q = f"?trust_id={trust_id}" if trust_id else ""
        return self._request("GET", f"/trust-facts{q}")

    def get_document_status(self, trust_id=None):
        q = f"?trust_id={trust_id}" if trust_id else ""
        return self._request("GET", f"/document-status{q}")

    def validate_document(self, trust_id, document_id, draft_reference=None):
        payload = {"trust_id": trust_id, "document_id": document_id}
        if draft_reference:
            payload["draft_reference"] = draft_reference
        return self._request("POST", "/validate-document", json.dumps(payload).encode("utf-8"))


def test_bridge_mcp_server_maps_four_tools():
    import bridge_mcp_server as srv
    client = FakeBridgeClient()
    # 4 tools resolve to the correct /api/bridge HTTP calls
    srv._dispatch(client, "get_trust_calendar", {"trust_id": "t1"})
    srv._dispatch(client, "get_trust_facts", {})
    srv._dispatch(client, "get_document_status", {"trust_id": "t2"})
    srv._dispatch(client, "validate_document", {"trust_id": "t3", "document_id": "d1", "draft_reference": "ref"})
    assert len(client.calls) == 4
    assert client.calls[0] == ("GET", "/trust-calendar?trust_id=t1", None)
    assert client.calls[1] == ("GET", "/trust-facts", None)
    assert client.calls[2] == ("GET", "/document-status?trust_id=t2", None)
    assert client.calls[3] == ("POST", "/validate-document", b'{"trust_id": "t3", "document_id": "d1", "draft_reference": "ref"}')


def test_bridge_mcp_server_unknown_tool_raises():
    import bridge_mcp_server as srv
    with pytest.raises(ValueError, match="unknown tool"):
        srv._dispatch(FakeBridgeClient(), "write_trust", {})
