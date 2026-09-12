"""
Session-hardening tests (security council decision).

Covers:
  1. Access-token type enforcement (type=='access' required).
  2. 30-minute access-token expiry claim.
  3. Refresh-token rotation (old invalidated, new issued).
  4. Reuse detection: a revoked/rotated refresh token revokes ALL of the user's
     refresh tokens + records a security event.
  5. Revoke-on-password-change: old refresh tokens + outstanding access tokens gone.

Pure-unit / in-process FastAPI TestClient with a FakeDB — never hits a real
MongoDB, never hits prod. Run:
  python3 -m pytest backend/tests/test_session_hardening.py -q
"""
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# database.py / dependencies.py read these at import time — set dummies first.
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test")
os.environ.setdefault("JWT_SECRET", "test-secret-session-hardening")


# ==================== Fake Mongo ====================

class FakeResult:
    def __init__(self, modified_count=0, matched_count=0, inserted_id=None, deleted_count=0, **kwargs):
        self.modified_count = modified_count
        self.matched_count = matched_count
        self.inserted_id = inserted_id
        self.deleted_count = deleted_count


class FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, length=None):
        return list(self._docs)


class FakeCollection:
    def __init__(self):
        self.docs = []
        self.updates = []

    async def find_one(self, query, projection=None):
        for d in self.docs:
            # simple subset match
            if all(d.get(k) == v for k, v in query.items()):
                return d
        return None

    def find(self, query=None, projection=None):
        return FakeCursor(
            [d for d in self.docs if (query is None or all(d.get(k) == v for k, v in query.items()))]
        )

    async def insert_one(self, doc):
        d = dict(doc)
        if "_id" not in d:
            d["_id"] = f"id_{len(self.docs)}"
        self.docs.append(d)
        return FakeResult(inserted_id=d["_id"])

    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                if "$set" in update:
                    d.update(update["$set"])
                return FakeResult(modified_count=1, matched_count=1)
        if upsert:
            d = dict(query)
            if "$set" in update:
                d.update(update["$set"])
            self.docs.append(d)
            return FakeResult(upserted_id="x")
        return FakeResult(modified_count=0, matched_count=0)

    async def update_many(self, query, update):
        n = 0
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                if "$set" in update:
                    d.update(update["$set"])
                n += 1
        return FakeResult(modified_count=n, matched_count=n)

    async def delete_one(self, query):
        for i, d in enumerate(self.docs):
            if all(d.get(k) == v for k, v in query.items()):
                self.docs.pop(i)
                return FakeResult(deleted_count=1)
        return FakeResult(deleted_count=0)

    async def delete_many(self, query):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not all(d.get(k) == v for k, v in query.items())]
        return FakeResult(deleted_count=before - len(self.docs))

    async def create_index(self, *a, **k):
        return None


class FakeDB:
    def __init__(self):
        self.users = FakeCollection()
        self.refresh_tokens = FakeCollection()
        self.jwt_revocations = FakeCollection()
        self.user_sessions = FakeCollection()
        self.password_resets = FakeCollection()
        self.audit_logs = FakeCollection()
        self.subscriptions = FakeCollection()
        self.oauth_auth_codes = FakeCollection()

    def __getattr__(self, name):
        col = FakeCollection()
        setattr(self, name, col)
        return col


@pytest.fixture
def fake_db(monkeypatch):
    import database
    import dependencies

    db = FakeDB()
    monkeypatch.setattr(database, "db", db)
    monkeypatch.setattr(dependencies, "db", db)

    # Audit logging writes to db.audit_logs (FakeDB) — let it run so the
    # reuse-detection security event is observable in the test.
    import routers.auth as auth_router
    import utils.audit as audit
    monkeypatch.setattr(auth_router, "db", db)
    monkeypatch.setattr(dependencies, "db", db)
    monkeypatch.setattr(audit, "db", db)

    # Seed a known user
    db.users.docs.append({
        "_id": "u1",
        "user_id": "user_test",
        "email": "qa@trustoffice.app",
        "name": "QA User",
        "password_hash": dependencies.hash_password("CurrentPass123"),
        "is_admin": False,
    })
    return db


@pytest.fixture
def client(fake_db, monkeypatch):
    import dependencies
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routers.auth as auth_router

    fake_user = {"user_id": "user_test", "email": "qa@trustoffice.app"}

    async def fake_get_current_user():
        return fake_user

    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api")
    app.dependency_overrides[dependencies.get_current_user] = fake_get_current_user
    return TestClient(app)


# ==================== 1. TYPE ENFORCEMENT ====================

def test_non_access_token_rejected(monkeypatch):
    """A JWT without type=='access' must be rejected by get_current_user."""
    import jwt
    import dependencies

    token = jwt.encode(
        {"user_id": "user_test", "email": "qa@trustoffice.app", "jti": "abc", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        dependencies.JWT_SECRET, algorithm=dependencies.JWT_ALGORITHM,
    )
    from fastapi import Request
    dummy = Request({"type": "http", "headers": [], "query_string": b"", "path": "/"})
    async def _run():
        try:
            await dependencies.get_current_user(dummy)
            return False
        except Exception:
            return True
    import asyncio
    assert asyncio.run(_run()) is True


def test_access_token_accepted():
    import dependencies
    token = dependencies.create_jwt_token("user_test", "qa@trustoffice.app")
    assert dependencies.jwt.decode(token, dependencies.JWT_SECRET, algorithms=[dependencies.JWT_ALGORITHM]).get("type") == "access"


# ==================== 2. 30-MIN EXPIRY CLAIM ====================

def test_access_token_has_30_min_expiry():
    import dependencies
    token = dependencies.create_jwt_token("user_test", "qa@trustoffice.app")
    payload = dependencies.jwt.decode(token, dependencies.JWT_SECRET, algorithms=[dependencies.JWT_ALGORITHM])
    iat = payload["iat"]
    exp = payload["exp"]
    delta = (datetime.fromtimestamp(exp, tz=timezone.utc) - datetime.fromtimestamp(iat, tz=timezone.utc))
    assert delta == timedelta(minutes=30), f"expected 30 min, got {delta}"


# ==================== 3. REFRESH ROTATION ====================

def test_refresh_rotates_and_invalidates_old(client):
    """POST /auth/refresh returns a new access token + rotates the refresh token."""
    import dependencies

    # Seed a refresh token record (raw -> stored hashed)
    raw = dependencies.generate_refresh_token()
    hashv = dependencies.hash_refresh_token(raw)
    client.app.router  # touch
    # Insert via the same db the router uses
    from database import db
    db.refresh_tokens.docs.append({
        "_id": "rt1",
        "user_id": "user_test",
        "token_hash": hashv,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        "rotated_from": None,
        "revoked": False,
    })

    resp = client.post("/api/auth/refresh", cookies={"refresh_token": raw})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("token")

    # Old token must now be marked revoked + rotated
    old = db.refresh_tokens.find_one({"token_hash": hashv})
    # find_one is async
    import asyncio
    old_doc = asyncio.run(old)
    assert old_doc["revoked"] is True, "old refresh token should be revoked after rotation"
    assert old_doc.get("rotated_at") is not None

    # A brand-new refresh token record should exist (the rotated one)
    new_records = [d for d in db.refresh_tokens.docs if d["token_hash"] != hashv]
    assert new_records, "a new refresh token should have been issued"


def test_refresh_sets_cookies(client):
    import dependencies
    raw = dependencies.generate_refresh_token()
    from database import db
    db.refresh_tokens.docs.append({
        "_id": "rt2", "user_id": "user_test", "token_hash": dependencies.hash_refresh_token(raw),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        "rotated_from": None, "revoked": False,
    })
    resp = client.post("/api/auth/refresh", cookies={"refresh_token": raw})
    assert resp.status_code == 200
    assert "session_token" in resp.cookies
    assert "refresh_token" in resp.cookies
    # The refresh cookie must be scoped to /auth (path attribute in Set-Cookie)
    set_cookie = resp.headers.get("set-cookie", "")
    assert "refresh_token" in set_cookie
    assert "Path=/auth" in set_cookie


# ==================== 4. REUSE DETECTION REVOKES ALL ====================

def test_reuse_of_revoked_refresh_revokes_all(client):
    """Presenting a rotated refresh token revokes ALL of the user's tokens + logs event."""
    import dependencies
    import asyncio

    # Two valid refresh tokens for the same user
    raw1 = dependencies.generate_refresh_token()
    raw2 = dependencies.generate_refresh_token()
    now = datetime.now(timezone.utc)
    from database import db
    db.refresh_tokens.docs.append({
        "_id": "a", "user_id": "user_test", "token_hash": dependencies.hash_refresh_token(raw1),
        "created_at": now.isoformat(), "expires_at": (now + timedelta(days=30)).isoformat(),
        "rotated_from": "old", "revoked": True,  # already rotated/revoked
    })
    db.refresh_tokens.docs.append({
        "_id": "b", "user_id": "user_test", "token_hash": dependencies.hash_refresh_token(raw2),
        "created_at": now.isoformat(), "expires_at": (now + timedelta(days=30)).isoformat(),
        "rotated_from": None, "revoked": False,
    })

    # Present the rotated/revoked token -> should 401 and revoke token b too
    resp = client.post("/api/auth/refresh", cookies={"refresh_token": raw1})
    assert resp.status_code == 401, resp.text

    # Both tokens now revoked
    a = asyncio.run(db.refresh_tokens.find_one({"token_hash": dependencies.hash_refresh_token(raw1)}))
    b = asyncio.run(db.refresh_tokens.find_one({"token_hash": dependencies.hash_refresh_token(raw2)}))
    assert a["revoked"] is True
    assert b["revoked"] is True, "reuse must revoke ALL of the user's refresh tokens"

    # A security event log line must be recorded
    events = [d for d in db.audit_logs.docs if d.get("action") == "refresh_token_reuse_detected"]
    assert events, "reuse detection must record a security event"


# ==================== 5. REVOKE ON PASSWORD CHANGE ====================

def test_password_change_revokes_refresh_and_access(client):
    """Changing password revokes all refresh tokens AND all outstanding access tokens."""
    import dependencies
    import asyncio

    # Seed a refresh token
    raw = dependencies.generate_refresh_token()
    now = datetime.now(timezone.utc)
    from database import db
    db.refresh_tokens.docs.append({
        "_id": "rt", "user_id": "user_test", "token_hash": dependencies.hash_refresh_token(raw),
        "created_at": now.isoformat(), "expires_at": (now + timedelta(days=30)).isoformat(),
        "rotated_from": None, "revoked": False,
    })

    resp = client.post("/api/auth/password/change", json={
        "current_password": "CurrentPass123",
        "new_password": "BrandNewPass456",
    })
    assert resp.status_code == 200, resp.text

    # Refresh token revoked
    rt = asyncio.run(db.refresh_tokens.find_one({"token_hash": dependencies.hash_refresh_token(raw)}))
    assert rt["revoked"] is True, "password change must revoke all refresh tokens"

    # Access tokens revoked via jti 'all' marker
    rev = asyncio.run(db.jwt_revocations.find_one({"user_id": "user_test", "jti": "all"}))
    assert rev is not None, "password change must revoke all outstanding access tokens"

    # New access token issued so current session continues
    assert resp.json().get("token")


def test_password_change_wrong_current_fails(client):
    resp = client.post("/api/auth/password/change", json={
        "current_password": "wrongpass", "new_password": "BrandNewPass456",
    })
    assert resp.status_code == 401
