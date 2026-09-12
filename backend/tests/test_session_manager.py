"""
Session/device manager tests (FEATURE 5 item 2).

Covers:
  1. A session record is written on login (jti + device label + ip + timestamps).
  2. GET /auth/sessions lists only the requesting user's own sessions (tenant
     isolation: user A never sees user B's sessions).
  3. DELETE /auth/sessions/<jti> revokes a single other session and rejects the
     caller's own current session with 400.
  4. POST /auth/sessions/revoke-all revokes every other session and leaves the
     current session alive, returning the revoked count.
  5. last_seen_at updates on authenticated requests (throttled touch hook).

Pure-unit / in-process FastAPI TestClient with a FakeDB that supports the query
operators our session helpers use ($gt, $ne, $set, $setOnInsert, upsert).
Never hits a real MongoDB or prod. Run:
  python3 -m pytest backend/tests/test_session_manager.py -q
"""
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# database.py / dependencies.py read these at import time - set dummies first.
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test")
os.environ.setdefault("JWT_SECRET", "test-secret-session-manager")


# ==================== Fake Mongo (operators our helpers use) ====================

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


def _matches(doc, query):
    """Subset match supporting $gt / $ne operators."""
    for k, v in query.items():
        doc_v = doc.get(k)
        if isinstance(v, dict):
            if "$gt" in v and not (doc_v is not None and doc_v > v["$gt"]):
                return False
            if "$ne" in v and doc_v == v["$ne"]:
                return False
        else:
            if doc_v != v:
                return False
    return True


class FakeCollection:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, projection=None):
        for d in self.docs:
            if _matches(d, query):
                return d
        return None

    def find(self, query=None, projection=None):
        return FakeCursor([d for d in self.docs if (query is None or _matches(d, query))])

    async def insert_one(self, doc):
        d = dict(doc)
        if "_id" not in d:
            d["_id"] = f"id_{len(self.docs)}"
        self.docs.append(d)
        return FakeResult(inserted_id=d["_id"])

    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if _matches(d, query):
                if "$set" in update:
                    d.update(update["$set"])
                if "$setOnInsert" in update:
                    for kk, vv in update["$setOnInsert"].items():
                        d.setdefault(kk, vv)
                return FakeResult(modified_count=1, matched_count=1)
        if upsert:
            d = dict(query)
            if "$set" in update:
                d.update(update["$set"])
            if "$setOnInsert" in update:
                d.update(update["$setOnInsert"])
            self.docs.append(d)
            return FakeResult(upserted_id="x")
        return FakeResult(modified_count=0, matched_count=0)

    async def update_many(self, query, update):
        n = 0
        for d in self.docs:
            if _matches(d, query):
                if "$set" in update:
                    d.update(update["$set"])
                n += 1
        return FakeResult(modified_count=n, matched_count=n)

    async def delete_one(self, query):
        for i, d in enumerate(self.docs):
            if _matches(d, query):
                self.docs.pop(i)
                return FakeResult(deleted_count=1)
        return FakeResult(deleted_count=0)

    async def delete_many(self, query):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not _matches(d, query)]
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
        self.security_events = FakeCollection()

    def __getattr__(self, name):
        col = FakeCollection()
        setattr(self, name, col)
        return col


@pytest.fixture
def fake_db(monkeypatch):
    import database
    import dependencies
    import routers.auth as auth_router
    import utils.audit as audit

    db = FakeDB()
    monkeypatch.setattr(database, "db", db)
    monkeypatch.setattr(dependencies, "db", db)
    monkeypatch.setattr(auth_router, "db", db)
    monkeypatch.setattr(audit, "db", db)

    # Seed two known users (tenant isolation test).
    db.users.docs.append({
        "_id": "uA", "user_id": "user_a", "email": "a@trustoffice.app",
        "name": "User A", "password_hash": dependencies.hash_password("CurrentPass123"),
        "is_admin": False,
    })
    db.users.docs.append({
        "_id": "uB", "user_id": "user_b", "email": "b@trustoffice.app",
        "name": "User B", "password_hash": dependencies.hash_password("CurrentPass123"),
        "is_admin": False,
    })
    return db


def _make_client(fake_db, user_id, email):
    import dependencies
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routers.auth as auth_router

    async def fake_get_current_user():
        return {"user_id": user_id, "email": email}

    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api")
    app.dependency_overrides[dependencies.get_current_user] = fake_get_current_user
    return TestClient(app)


@pytest.fixture
def client_a(fake_db):
    return _make_client(fake_db, "user_a", "a@trustoffice.app")


@pytest.fixture
def client_b(fake_db):
    return _make_client(fake_db, "user_b", "b@trustoffice.app")


# ==================== 1. Session recorded at login ====================

def test_login_records_session(client_a, fake_db):
    """POST /auth/login upserts a user_sessions record keyed by the token jti."""
    import asyncio
    resp = client_a.post(
        "/api/auth/login",
        json={"email": "a@trustoffice.app", "password": "CurrentPass123"},
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0 Safari/537.36"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    token = body.get("token")
    assert token

    # Decode jti from the issued token.
    import jwt
    import dependencies
    payload = jwt.decode(token, dependencies.JWT_SECRET, algorithms=[dependencies.JWT_ALGORITHM])
    jti = payload["jti"]

    sess = asyncio.run(fake_db.user_sessions.find_one({"user_id": "user_a", "jti": jti}))
    assert sess is not None, "login must record a session"
    assert sess["revoked"] is False
    assert sess["device_label"] == "Chrome on macOS"
    assert sess.get("ip") is not None
    assert "created_at" in sess and "last_seen_at" in sess


# ==================== 2. Tenant isolation ====================

def test_list_shows_only_own_sessions(client_a, client_b, fake_db):
    """User A's session list never contains user B's sessions."""
    import asyncio
    # Seed sessions directly for both users.
    now = datetime.now(timezone.utc)
    fake_db.user_sessions.docs.append({
        "user_id": "user_a", "jti": "jti_a1", "device_label": "Chrome on macOS",
        "ip": "1.1.1.1", "created_at": now.isoformat(), "last_seen_at": now.isoformat(),
        "expires_at": (now + timedelta(days=30)).isoformat(), "revoked": False,
    })
    fake_db.user_sessions.docs.append({
        "user_id": "user_b", "jti": "jti_b1", "device_label": "Firefox on Windows",
        "ip": "2.2.2.2", "created_at": now.isoformat(), "last_seen_at": now.isoformat(),
        "expires_at": (now + timedelta(days=30)).isoformat(), "revoked": False,
    })

    resp_a = client_a.get("/api/auth/sessions")
    assert resp_a.status_code == 200, resp_a.text
    jtis_a = {s["jti"] for s in resp_a.json()["sessions"]}
    assert "jti_a1" in jtis_a
    assert "jti_b1" not in jtis_a, "user A must not see user B sessions"

    resp_b = client_b.get("/api/auth/sessions")
    assert resp_b.status_code == 200
    jtis_b = {s["jti"] for s in resp_b.json()["sessions"]}
    assert "jti_b1" in jtis_b
    assert "jti_a1" not in jtis_b


def test_current_session_flagged(client_a, fake_db):
    """The session whose jti matches the request token is marked is_current."""
    import asyncio
    # Make client_a's current jti known by recording a session for it.
    now = datetime.now(timezone.utc)
    current_jti = "jti_current_a"
    fake_db.user_sessions.docs.append({
        "user_id": "user_a", "jti": current_jti, "device_label": "Chrome on macOS",
        "ip": "1.1.1.1", "created_at": now.isoformat(), "last_seen_at": now.isoformat(),
        "expires_at": (now + timedelta(days=30)).isoformat(), "revoked": False,
    })
    fake_db.user_sessions.docs.append({
        "user_id": "user_a", "jti": "jti_other_a", "device_label": "Safari on iOS",
        "ip": "1.1.1.2", "created_at": now.isoformat(), "last_seen_at": now.isoformat(),
        "expires_at": (now + timedelta(days=30)).isoformat(), "revoked": False,
    })

    # Force the fake current-user's jti by monkeypatching the client's token path:
    # we instead verify the helper directly, since the TestClient uses the override.
    from dependencies import get_active_sessions
    sessions = asyncio.run(get_active_sessions("user_a", current_jti))
    by_jti = {s["jti"]: s for s in sessions}
    assert by_jti[current_jti]["is_current"] is True
    assert by_jti["jti_other_a"]["is_current"] is False


# ==================== 3. Single revoke ====================

def test_revoke_single_other_session(client_a, fake_db):
    """DELETE /auth/sessions/<jti> revokes a different session (200)."""
    import asyncio
    now = datetime.now(timezone.utc)
    fake_db.user_sessions.docs.append({
        "user_id": "user_a", "jti": "jti_victim", "device_label": "Firefox on Windows",
        "ip": "2.2.2.2", "created_at": now.isoformat(), "last_seen_at": now.isoformat(),
        "expires_at": (now + timedelta(days=30)).isoformat(), "revoked": False,
    })
    resp = client_a.delete("/api/auth/sessions/jti_victim")
    assert resp.status_code == 200, resp.text
    sess = asyncio.run(fake_db.user_sessions.find_one({"user_id": "user_a", "jti": "jti_victim"}))
    assert sess["revoked"] is True
    # Outstanding access token invalidated via jwt_revocations.
    rev = asyncio.run(fake_db.jwt_revocations.find_one({"user_id": "user_a", "jti": "jti_victim"}))
    assert rev is not None


def test_revoke_own_current_session_rejected(client_a, fake_db):
    """DELETE targeting the caller's own session returns 400."""
    # We cannot easily know client_a's real current jti (override skips token),
    # so exercise the endpoint's own-jti guard through the helper path:
    # set the current-user override to a known jti via a custom client.
    import dependencies
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routers.auth as auth_router

    current_jti = "jti_self"

    async def fake_user():
        return {"user_id": "user_a", "email": "a@trustoffice.app"}

    # Patch _current_jti indirectly: the endpoint reads the token via _extract_token.
    # Simulate by injecting a Bearer token whose jti == current_jti.
    token = dependencies.create_jwt_token("user_a", "a@trustoffice.app")
    # Overwrite the jti by encoding one manually.
    import jwt
    payload = jwt.decode(token, dependencies.JWT_SECRET, algorithms=[dependencies.JWT_ALGORITHM])
    payload["jti"] = current_jti
    token = jwt.encode(payload, dependencies.JWT_SECRET, algorithm=dependencies.JWT_ALGORITHM)

    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api")
    app.dependency_overrides[dependencies.get_current_user] = fake_user
    c = TestClient(app)
    resp = c.delete("/api/auth/sessions/jti_self", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 400, resp.text
    assert "current" in resp.json()["detail"].lower()


def test_revoke_unknown_session_404(client_a, fake_db):
    resp = client_a.delete("/api/auth/sessions/does_not_exist")
    assert resp.status_code == 404


# ==================== 4. Revoke all ====================

def test_revoke_all_leaves_current_alive(client_a, fake_db):
    """POST /auth/sessions/revoke-all revokes others, keeps current, returns count."""
    import asyncio
    now = datetime.now(timezone.utc)
    fake_db.user_sessions.docs.append({
        "user_id": "user_a", "jti": "jti_keep", "device_label": "Chrome on macOS",
        "ip": "1.1.1.1", "created_at": now.isoformat(), "last_seen_at": now.isoformat(),
        "expires_at": (now + timedelta(days=30)).isoformat(), "revoked": False,
    })
    fake_db.user_sessions.docs.append({
        "user_id": "user_a", "jti": "jti_drop1", "device_label": "Firefox on Windows",
        "ip": "2.2.2.2", "created_at": now.isoformat(), "last_seen_at": now.isoformat(),
        "expires_at": (now + timedelta(days=30)).isoformat(), "revoked": False,
    })
    fake_db.user_sessions.docs.append({
        "user_id": "user_a", "jti": "jti_drop2", "device_label": "Safari on iOS",
        "ip": "3.3.3.3", "created_at": now.isoformat(), "last_seen_at": now.isoformat(),
        "expires_at": (now + timedelta(days=30)).isoformat(), "revoked": False,
    })

    import dependencies
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routers.auth as auth_router
    import jwt

    token = dependencies.create_jwt_token("user_a", "a@trustoffice.app")
    payload = jwt.decode(token, dependencies.JWT_SECRET, algorithms=[dependencies.JWT_ALGORITHM])
    payload["jti"] = "jti_keep"
    token = jwt.encode(payload, dependencies.JWT_SECRET, algorithm=dependencies.JWT_ALGORITHM)

    async def fake_user():
        return {"user_id": "user_a", "email": "a@trustoffice.app"}

    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api")
    app.dependency_overrides[dependencies.get_current_user] = fake_user
    c = TestClient(app)
    resp = c.post("/api/auth/sessions/revoke-all", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["revoked_count"] == 2, body

    # Current session still alive.
    keep = asyncio.run(fake_db.user_sessions.find_one({"user_id": "user_a", "jti": "jti_keep"}))
    assert keep["revoked"] is False
    # Others revoked.
    drop1 = asyncio.run(fake_db.user_sessions.find_one({"user_id": "user_a", "jti": "jti_drop1"}))
    drop2 = asyncio.run(fake_db.user_sessions.find_one({"user_id": "user_a", "jti": "jti_drop2"}))
    assert drop1["revoked"] is True
    assert drop2["revoked"] is True


# ==================== 5. last_seen updates (throttled) ====================

def test_touch_session_updates_last_seen(fake_db):
    import asyncio
    from dependencies import touch_session
    now = datetime.now(timezone.utc)
    fake_db.user_sessions.docs.append({
        "user_id": "user_a", "jti": "jti_touch", "device_label": "Chrome on macOS",
        "ip": "1.1.1.1", "created_at": now.isoformat(),
        "last_seen_at": (now - timedelta(hours=2)).isoformat(),
        "expires_at": (now + timedelta(days=30)).isoformat(), "revoked": False,
    })
    from fastapi import Request
    dummy = Request({"type": "http", "headers": [], "query_string": b"", "path": "/", "client": ("1.1.1.1", 1234)})

    asyncio.run(touch_session("user_a", "jti_touch", dummy))
    after = asyncio.run(fake_db.user_sessions.find_one({"user_id": "user_a", "jti": "jti_touch"}))
    assert after["last_seen_at"] > (now - timedelta(hours=1)).isoformat()

    # Second immediate touch is throttled (no new write within 5 min window).
    first_ts = after["last_seen_at"]
    asyncio.run(touch_session("user_a", "jti_touch", dummy))
    after2 = asyncio.run(fake_db.user_sessions.find_one({"user_id": "user_a", "jti": "jti_touch"}))
    assert after2["last_seen_at"] == first_ts, "touch must be throttled to 1 write / 5 min"


def test_heartbeat_middleware_updates_last_seen(fake_db, client_a):
    """The SessionHeartbeatMiddleware bumps last_seen_at on an authenticated call."""
    import asyncio
    import dependencies
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routers.auth as auth_router
    import jwt

    now = datetime.now(timezone.utc)
    token = dependencies.create_jwt_token("user_a", "a@trustoffice.app")
    payload = jwt.decode(token, dependencies.JWT_SECRET, algorithms=[dependencies.JWT_ALGORITHM])
    current_jti = payload["jti"]
    fake_db.user_sessions.docs.append({
        "user_id": "user_a", "jti": current_jti, "device_label": "Chrome on macOS",
        "ip": "1.1.1.1", "created_at": now.isoformat(),
        "last_seen_at": (now - timedelta(hours=1)).isoformat(),
        "expires_at": (now + timedelta(days=30)).isoformat(), "revoked": False,
    })

    async def fake_user():
        return {"user_id": "user_a", "email": "a@trustoffice.app"}

    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api")
    app.dependency_overrides[dependencies.get_current_user] = fake_user
    c = TestClient(app)
    # Any authenticated call triggers the heartbeat middleware.
    c.get("/api/auth/sessions", headers={"Authorization": f"Bearer {token}"})

    after = asyncio.run(fake_db.user_sessions.find_one({"user_id": "user_a", "jti": current_jti}))
    assert after["last_seen_at"] > (now - timedelta(minutes=10)).isoformat()
