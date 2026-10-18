"""
Agent Bridge v1 tests.

Pure-unit / in-process FastAPI tests using a FakeDB — no real MongoDB required.
Run:
  python3 -m pytest backend/tests/test_bridge.py -q
"""
import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test_bridge")
os.environ.setdefault("JWT_SECRET", "test-secret-bridge")

import database  # noqa: E402
import dependencies  # noqa: E402
import services.bridge_service as bridge_service  # noqa: E402


class FakeResult:
    def __init__(
        self,
        modified_count: int = 0,
        matched_count: int = 0,
        inserted_id: Optional[str] = None,
        deleted_count: int = 0,
    ):
        self.modified_count = modified_count
        self.matched_count = matched_count
        self.inserted_id = inserted_id
        self.deleted_count = deleted_count


class FakeCursor:
    def __init__(self, docs: List[Dict[str, Any]]):
        self._docs = docs

    def sort(self, *args, **kwargs) -> "FakeCursor":
        # Minimal sort: handle single (field, direction) only.
        if len(args) == 2 and isinstance(args[1], int):
            field, direction = args
            reverse = direction == -1
            self._docs = sorted(
                self._docs,
                key=lambda d: d.get(field) or "",
                reverse=reverse,
            )
        return self

    async def to_list(self, length: Optional[int] = None):
        out = list(self._docs)
        if length is not None:
            out = out[:length]
        return out


class FakeCollection:
    def __init__(self):
        self.docs: List[Dict[str, Any]] = []
        self.last_query: Optional[Dict[str, Any]] = None

    def _matches(self, doc: Dict[str, Any], query: Dict[str, Any]) -> bool:
        for k, v in query.items():
            if k == "_id":
                if doc.get("_id") != v:
                    return False
                continue
            # Top-level equality only (sufficient for bridge tests).
            if isinstance(v, dict):
                # Tiny support for $in, $type
                if "$in" in v:
                    if doc.get(k) not in v["$in"]:
                        return False
                    continue
                if "$type" in v:
                    continue  # ignore for tests
                return False
            if doc.get(k) != v:
                return False
        return True

    async def find_one(
        self,
        query: Optional[Dict[str, Any]] = None,
        projection: Optional[Dict[str, Any]] = None,
        sort: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        query = query or {}
        docs = [d for d in self.docs if self._matches(d, query)]
        if sort:
            # Minimal support for [(field, direction)] or {field: direction}
            if isinstance(sort, dict):
                sort = list(sort.items())
            if sort:
                field, direction = sort[0]
                reverse = direction == -1
                docs = sorted(docs, key=lambda d: d.get(field) or "", reverse=reverse)
        return dict(docs[0]) if docs else None

    def find(
        self,
        query: Optional[Dict[str, Any]] = None,
        projection: Optional[Dict[str, Any]] = None,
        sort: Optional[Any] = None,
    ) -> FakeCursor:
        self.last_query = query
        query = query or {}
        docs = [d for d in self.docs if self._matches(d, query)]
        return FakeCursor(docs)

    async def insert_one(self, doc: Dict[str, Any]) -> FakeResult:
        d = dict(doc)
        if "_id" not in d:
            d["_id"] = f"id_{len(self.docs)}"
        self.docs.append(d)
        return FakeResult(inserted_id=d["_id"])

    async def update_one(
        self,
        query: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
    ) -> FakeResult:
        for i, d in enumerate(self.docs):
            if self._matches(d, query):
                if "$set" in update:
                    self.docs[i].update(update["$set"])
                if "$inc" in update:
                    for k, v in update["$inc"].items():
                        self.docs[i][k] = self.docs[i].get(k, 0) + v
                return FakeResult(modified_count=1, matched_count=1)
        if upsert:
            d = dict(query)
            if "$set" in update:
                d.update(update["$set"])
            self.docs.append(d)
            return FakeResult(modified_count=1, matched_count=1)
        return FakeResult(modified_count=0, matched_count=0)

    async def update_many(self, query: Dict[str, Any], update: Dict[str, Any]) -> FakeResult:
        n = 0
        for i, d in enumerate(self.docs):
            if self._matches(d, query):
                if "$set" in update:
                    self.docs[i].update(update["$set"])
                n += 1
        return FakeResult(modified_count=n, matched_count=n)

    async def delete_one(self, query: Dict[str, Any]) -> FakeResult:
        for i, d in enumerate(self.docs):
            if self._matches(d, query):
                self.docs.pop(i)
                return FakeResult(deleted_count=1)
        return FakeResult(deleted_count=0)

    async def delete_many(self, query: Dict[str, Any]) -> FakeResult:
        before = len(self.docs)
        self.docs = [d for d in self.docs if not self._matches(d, query)]
        return FakeResult(deleted_count=before - len(self.docs))

    async def count_documents(self, query: Optional[Dict[str, Any]] = None) -> int:
        query = query or {}
        return sum(1 for d in self.docs if self._matches(d, query))

    async def create_index(self, *args, **kwargs) -> None:
        return None

    async def distinct(self, field: str, query: Optional[Dict[str, Any]] = None):
        query = query or {}
        return list({d.get(field) for d in self.docs if self._matches(d, query) if field in d})


class FakeDB:
    def __init__(self):
        self.agent_tokens = FakeCollection()
        self.bridge_audit = FakeCollection()
        self.trusts = FakeCollection()
        self.deadlines = FakeCollection()
        self.vault_documents = FakeCollection()
        self.minutes_records = FakeCollection()
        self.users = FakeCollection()
        self.subscriptions = FakeCollection()

    def __getattr__(self, name: str) -> FakeCollection:
        col = FakeCollection()
        setattr(self, name, col)
        return col


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(database, "db", db)
    monkeypatch.setattr(dependencies, "db", db)
    monkeypatch.setattr(bridge_service, "db", db)
    import routers.bridge as bridge_router
    monkeypatch.setattr(bridge_router, "db", db)
    return db


@pytest.fixture
def client(fake_db, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.bridge import router as bridge_router, require_admin

    admin_user = {"user_id": "admin_test", "email": "admin@trustoffice.app", "is_admin": True}

    app = FastAPI()
    app.include_router(bridge_router, prefix="/api")
    app.dependency_overrides[require_admin] = lambda: admin_user

    # Reset in-memory rate limit state between tests.
    bridge_service.reset_rate_limit()

    return TestClient(app)


def _issue_token_sync(
    client,
    customer_id: str,
    scopes: Optional[List[str]] = None,
    rate_limit: Optional[int] = None,
):
    payload = {"customer_id": customer_id, "scopes": scopes or ["read"]}
    if rate_limit is not None:
        payload["rate_limit"] = rate_limit
    resp = client.post("/api/bridge/admin/tokens", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["token"].startswith("tob_")
    assert len(data["token"]) == len("tob_") + 32
    return data


# ==================== TOKEN LIFECYCLE ====================

def test_token_format_and_hashed_at_rest(fake_db, client):
    data = _issue_token_sync(client, customer_id="cust_1")
    token_id = data["token_id"]
    stored = next((d for d in fake_db.agent_tokens.docs if d["token_id"] == token_id), None)
    assert stored is not None
    assert "tob_" not in stored["token_hash"]
    assert stored["token_hash"] == bridge_service._hash_token(data["token"])


def test_use_token_then_revoke_then_401(fake_db, client):
    data = _issue_token_sync(client, customer_id="cust_1")
    token = data["token"]

    resp = client.get("/api/bridge/trust-facts", headers={"X-Agent-Token": token})
    assert resp.status_code == 200

    # Revoke
    r = client.post(f"/api/bridge/admin/tokens/{data['token_id']}/revoke", json={"reason": "compromised"})
    assert r.status_code == 200
    assert r.json()["revoked"] is True

    # Same token must now be rejected immediately.
    resp = client.get("/api/bridge/trust-facts", headers={"X-Agent-Token": token})
    assert resp.status_code == 401


def test_expired_token_rejected(fake_db, client, monkeypatch):
    data = _issue_token_sync(client, customer_id="cust_1")
    token = data["token"]

    # Simulate time jumping past expiry.
    real_now = bridge_service._now_dt
    future = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00")) + timedelta(days=1)

    def fake_now():
        return future

    monkeypatch.setattr(bridge_service, "_now_dt", fake_now)
    resp = client.get("/api/bridge/trust-facts", headers={"X-Agent-Token": token})
    assert resp.status_code == 401

    monkeypatch.setattr(bridge_service, "_now_dt", real_now)


def test_scope_denied(fake_db, client):
    data = _issue_token_sync(client, customer_id="cust_1", scopes=["other"])
    resp = client.get("/api/bridge/trust-facts", headers={"X-Agent-Token": data["token"]})
    assert resp.status_code == 403
    assert "scope" in resp.json()["detail"].lower()


def test_no_admin_key_on_bridge_endpoint(fake_db, client):
    """Bridge routes never accept admin JWTs; they require X-Agent-Token."""
    # Issue a valid user/admin JWT — the bridge must reject it.
    jwt = dependencies.create_jwt_token("admin_test", "admin@trustoffice.app")
    resp = client.get("/api/bridge/trust-facts", headers={"Authorization": f"Bearer {jwt}"})
    # Admin JWT is not a valid tob_* token -> 401.
    assert resp.status_code == 401


# ==================== RATE LIMITING ====================

def test_rate_limit(fake_db, client):
    data = _issue_token_sync(client, customer_id="cust_1", rate_limit=2)
    token = data["token"]
    # First two requests succeed.
    assert client.get("/api/bridge/trust-facts", headers={"X-Agent-Token": token}).status_code == 200
    assert client.get("/api/bridge/trust-facts", headers={"X-Agent-Token": token}).status_code == 200
    # Third request is blocked for an hour.
    resp = client.get("/api/bridge/trust-facts", headers={"X-Agent-Token": token})
    assert resp.status_code == 429


# ==================== TENANT ISOLATION ====================

def test_tenant_isolation(fake_db, client):
    # Seed trusts for two customers.
    fake_db.trusts.docs.append({
        "_id": "t1", "trust_id": "trust_a", "user_id": "cust_a",
        "name": "A Trust", "state": "CO", "type": "revocable_living",
        "grantor": "Alice", "revocable": True,
        "formation_date": "2020-01-01T00:00:00+00:00",
        "created_at": "2020-01-01T00:00:00+00:00",
        "updated_at": "2024-01-01T00:00:00+00:00",
    })
    fake_db.trusts.docs.append({
        "_id": "t2", "trust_id": "trust_b", "user_id": "cust_b",
        "name": "B Trust", "state": "UT", "type": "irrevocable",
        "grantor": "Bob", "revocable": False,
        "formation_date": "2021-01-01T00:00:00+00:00",
        "created_at": "2021-01-01T00:00:00+00:00",
        "updated_at": "2024-01-01T00:00:00+00:00",
    })

    data = _issue_token_sync(client, customer_id="cust_a")
    token = data["token"]

    resp = client.get("/api/bridge/trust-facts", headers={"X-Agent-Token": token})
    assert resp.status_code == 200
    names = {t.get("name") for t in resp.json()["trusts"]}
    assert "A Trust" in names
    assert "B Trust" not in names

    # Explicitly querying cust_b's trust_id yields nothing.
    resp2 = client.get("/api/bridge/trust-facts?trust_id=trust_b", headers={"X-Agent-Token": token})
    assert resp2.status_code == 200
    assert resp2.json()["trusts"] == []


# ==================== READ-ONLY + WHITELIST ====================

def test_trust_facts_excludes_sensitive_fields(fake_db, client):
    fake_db.trusts.docs.append({
        "_id": "t1", "trust_id": "trust_1", "user_id": "cust_1",
        "name": "Family Trust", "state": "CA", "type": "revocable_living",
        "grantor": "Jane", "revocable": True,
        "formation_date": "2019-06-01T00:00:00+00:00",
        "created_at": "2019-06-01T00:00:00+00:00", "updated_at": "2024-06-01T00:00:00+00:00",
        # Sensitive fields that must not leak over the bridge
        "ssn": "123-45-6789",
        "asset_value": 1234567,
        "beneficiary_email": "ben@test.com",
        "beneficiary_phone": "555-555-5555",
    })
    data = _issue_token_sync(client, customer_id="cust_1")
    token = data["token"]
    resp = client.get("/api/bridge/trust-facts?trust_id=trust_1", headers={"X-Agent-Token": token})
    assert resp.status_code == 200
    item = resp.json()["trusts"][0]
    assert item["name"] == "Family Trust"
    assert "ssn" not in item
    assert "asset_value" not in item
    assert "beneficiary_email" not in item
    assert "beneficiary_phone" not in item


def test_response_has_as_of_and_valid_until(fake_db, client):
    data = _issue_token_sync(client, customer_id="cust_1")
    resp = client.get("/api/bridge/trust-facts", headers={"X-Agent-Token": data["token"]})
    assert resp.status_code == 200
    body = resp.json()
    assert "as_of" in body
    assert "valid_until" in body
    assert body["valid_until"] > body["as_of"]


# ==================== AUDIT CHAIN ====================

def test_audit_chain_verify_and_tamper_detection(fake_db, client):
    data = _issue_token_sync(client, customer_id="cust_1")
    token = data["token"]

    # Generate some audit entries.
    client.get("/api/bridge/trust-facts", headers={"X-Agent-Token": token})
    client.get("/api/bridge/document-status", headers={"X-Agent-Token": token})

    verify = client.get("/api/bridge/audit/verify", headers={"X-Agent-Token": token})
    assert verify.status_code == 200
    assert verify.json()["verified"] is True
    assert verify.json()["errors"] == []

    # Tamper with a bridge_audit entry.
    entry = fake_db.bridge_audit.docs[0]
    entry["action"] = "tampered"

    verify2 = client.get("/api/bridge/audit/verify", headers={"X-Agent-Token": token})
    assert verify2.status_code == 200
    assert verify2.json()["verified"] is False
    assert any("tampered" in e.lower() or "mismatch" in e.lower() for e in verify2.json()["errors"])


# ==================== GENERIC VERDICT ENVELOPE ====================

def test_verdict_envelope_shape(fake_db, client):
    fake_db.trusts.docs.append({
        "_id": "t1", "trust_id": "trust_v", "user_id": "cust_1",
        "name": "Verdict Trust", "state": "CO", "type": "revocable_living",
        "grantor": "Grant", "revocable": True,
        "formation_date": "2020-01-01T00:00:00+00:00",
        "created_at": "2020-01-01T00:00:00+00:00", "updated_at": "2024-01-01T00:00:00+00:00",
    })
    fake_db.vault_documents.docs.append({
        "_id": "d1", "doc_id": "doc_complete", "trust_id": "trust_v", "user_id": "cust_1",
        "name": "Complete Doc", "mime_type": "text/plain",
        "file_content": b"some content",
        "created_at": "2024-01-01T00:00:00+00:00", "updated_at": "2024-01-01T00:00:00+00:00",
    })
    fake_db.vault_documents.docs.append({
        "_id": "d2", "doc_id": "doc_format", "trust_id": "trust_v", "user_id": "cust_1",
        "name": "Format Doc", "mime_type": "application/pdf",
        # No file_content -> format failure in stub.
        "created_at": "2024-01-01T00:00:00+00:00", "updated_at": "2024-01-01T00:00:00+00:00",
    })

    data = _issue_token_sync(client, customer_id="cust_1")
    token = data["token"]

    # PASS
    r = client.post(
        "/api/bridge/validate-document",
        json={"trust_id": "trust_v", "document_id": "doc_complete", "draft_reference": "draft-001"},
        headers={"X-Agent-Token": token},
    )
    assert r.status_code == 200
    val = r.json()["validation"]
    assert val["verdict"] == "PASS"
    assert val["draft_reference"] == "draft-001"
    assert set(val.keys()) == {"verdict", "draft_reference"}

    # FAIL_FORMAT (no rule detail)
    r2 = client.post(
        "/api/bridge/validate-document",
        json={"trust_id": "trust_v", "document_id": "doc_format"},
        headers={"X-Agent-Token": token},
    )
    assert r2.json()["validation"]["verdict"] == "FAIL_FORMAT"
    assert "rule" not in r2.json()["validation"]
    assert "detail" not in r2.json()["validation"]

    # FAIL_COMPLETENESS for missing document
    r3 = client.post(
        "/api/bridge/validate-document",
        json={"trust_id": "trust_v", "document_id": "doc_missing", "draft_reference": "draft-003"},
        headers={"X-Agent-Token": token},
    )
    assert r3.status_code == 200
    assert r3.json()["validation"]["verdict"] == "FAIL_COMPLETENESS"


# ==================== ADMIN ENDPOINTS / REVOCATION IMMEDIATE ====================

def test_revoke_token_effective_immediately(fake_db, client):
    data = _issue_token_sync(client, customer_id="cust_1")
    token_id = data["token_id"]
    token = data["token"]

    # Concurrent-ish: start a request then revoke mid-flight is hard to test in-proc,
    # so we verify the stored record is revoked and the next request fails.
    r = client.post(f"/api/bridge/admin/tokens/{token_id}/revoke", json={"reason": "test revoke"})
    assert r.status_code == 200

    stored = next((d for d in fake_db.agent_tokens.docs if d["token_id"] == token_id), None)
    assert stored["status"] == "revoked"
    assert stored["revoked_reason"] == "test revoke"

    resp = client.get("/api/bridge/trust-facts", headers={"X-Agent-Token": token})
    assert resp.status_code == 401


# ==================== 90-DAY EXPIRY ====================

def test_token_expiry_is_90_days(fake_db, client):
    data = _issue_token_sync(client, customer_id="cust_1")
    created = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00")) - timedelta(days=90)
    now = datetime.now(timezone.utc)
    assert abs((now - created).total_seconds()) < 5
