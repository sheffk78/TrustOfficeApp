"""
Tests for the jti-keyed user_sessions fallback in get_current_user
(fix-trustoffice-session-kickout-data-loss, 2026-11-01).

Background: password-login sessions are written jti-keyed by
record_session_for_token() (no `session_token` field), so once the 30-min
access JWT expires, _lookup_session_user() never resolves and the user is
kicked to login mid-work (form data loss). get_current_user now falls back
to the user_sessions jti record of the EXPIRED access token — but only
behind the 2026-09-15 hardening gates (council F5):

  T1: jti-keyed session record + expired access token + live refresh chain
      → fallback RESOLVES (the whole point).
  T2: same but session revoked:true → 401 (revoked session never authenticates).
  T3: jti present in jwt_revocations → 401 (token-level revocation).
  T4: no live unrotated refresh record for the user → 401 (dead chain = dead session).
  T5: /auth/refresh honors its rate_limit(30, 60) — 429 beyond the burst budget.

Pure-unit / in-process FastAPI TestClient with a FakeDB — never hits a real
MongoDB, never hits prod. Run:
  python3 -m pytest backend/tests/test_session_jti_fallback.py -q
"""
import asyncio
import os
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# database.py / dependencies.py read these at import time — set dummies first.
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test")
os.environ.setdefault("JWT_SECRET", "test-secret-jti-fallback")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import database  # noqa: E402
import dependencies  # noqa: E402
from routers.auth import router as auth_router  # noqa: E402

# Import the FakeDB infrastructure from the sibling hardening suite (extend,
# don't reinvent) — it matches the collection shapes this fallback uses.
from tests.test_session_hardening import FakeDB, FakeCursor  # noqa: E402

# Some routers chain find().sort(...).to_list(...) (the hardening suite's tests
# never hit those branches, the /auth/refresh path can) — add a no-op sort().
if not hasattr(FakeCursor, "sort"):

    def _sort(self, *args, **kwargs):
        return self

    FakeCursor.sort = _sort


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(database, "db", db)
    monkeypatch.setattr(dependencies, "db", db)
    import routers.auth as auth_router
    import utils.audit as audit
    monkeypatch.setattr(auth_router, "db", db)
    monkeypatch.setattr(audit, "db", db)

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
def app_with_auth(fake_db, monkeypatch):
    """App with the REAL get_current_user wired (no override) + a probe route."""
    app = FastAPI()
    app.include_router(auth_router, prefix="/api")

    from fastapi import Depends

    @app.get("/api/auth/me")
    async def me(user: dict = Depends(dependencies.get_current_user)):
        return {"user_id": user["user_id"], "email": user.get("email")}

    return app


def _expired_access_token(jti, user_id="user_test", email="qa@trustoffice.app"):
    """Build an access token whose exp is in the past but signature is valid."""
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "email": email,
        "type": "access",
        "jti": jti,
        "exp": now - timedelta(minutes=2),  # EXPIRED
        "iat": now - timedelta(minutes=32),
    }
    return dependencies.jwt.encode(payload, dependencies.JWT_SECRET, algorithm=dependencies.JWT_ALGORITHM)


def _seed_live_session(db, jti, user_id="user_test", revoked=False, expired=False):
    """Seed a jti-keyed user_sessions record exactly like record_session_for_token writes."""
    now = datetime.now(timezone.utc)
    expires_at = (now - timedelta(days=1)) if expired else (now + timedelta(days=29))
    db.user_sessions.docs.append({
        "user_id": user_id,
        "jti": jti,
        "device": "pytest",
        "created_at": now.isoformat(),
        "last_seen": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "revoked": revoked,
    })


def _seed_live_refresh_chain(db, user_id="user_test", count=1):
    """Seed live, unrotated refresh-token records (the live-chain gate)."""
    now = datetime.now(timezone.utc)
    for i in range(count):
        db.refresh_tokens.docs.append({
            "_id": f"rt{i}",
            "user_id": user_id,
            "token_hash": dependencies.hash_refresh_token(dependencies.generate_refresh_token()),
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=30)).isoformat(),
            "rotated_from": None,
            "revoked": False,
        })


def _client(app, strict=False):
    return TestClient(app, raise_server_exceptions=strict)


def _get_me(app, token):
    return _client(app).get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        cookies={"session_token": token},
    )


# ==================== T1: fallback RESOLVES ====================

def test_t1_jti_fallback_resolves_with_live_refresh_chain(app_with_auth, fake_db):
    """Box 4 positive: expired access token + jti-keyed session record (not
    revoked, not idle-expired) + live unrotated refresh chain → get_current_user
    resolves the user instead of 401."""
    jti = str(uuid.uuid4())
    token = _expired_access_token(jti)
    # _check_jwt_revocation runs BEFORE the fallback in get_current_user and
    # rejects expired tokens on the primary path unless they're in the grace
    # window; the fallback path is reached because the token carries a valid
    # signature but a past exp. Seed the pieces the gate requires:
    _seed_live_session(fake_db, jti)
    _seed_live_refresh_chain(fake_db)

    resp = _get_me(app_with_auth, token)
    assert resp.status_code == 200, f"T1 fallback must resolve: {resp.status_code} {resp.text}"
    assert resp.json()["user_id"] == "user_test"


def test_t1b_fallback_does_not_extend_session_ttl(app_with_auth, fake_db):
    """The fallback must not touch/extend the sliding idle TTL — record_session
    touch happens only on normal (non-fallback) requests."""
    jti = str(uuid.uuid4())
    token = _expired_access_token(jti)
    _seed_live_session(fake_db, jti)
    _seed_live_refresh_chain(fake_db)

    before = fake_db.user_sessions.docs[0]["expires_at"]
    resp = _get_me(app_with_auth, token)
    assert resp.status_code == 200
    after = fake_db.user_sessions.docs[0]["expires_at"]
    assert before == after, "fallback must never extend the session idle TTL"


# ==================== T2: revoked session → 401 ====================

def test_t2_revoked_session_does_not_authenticate(app_with_auth, fake_db):
    jti = str(uuid.uuid4())
    token = _expired_access_token(jti)
    _seed_live_session(fake_db, jti, revoked=True)
    _seed_live_refresh_chain(fake_db)

    resp = _get_me(app_with_auth, token)
    assert resp.status_code == 401, "revoked session must NOT authenticate via the jti fallback"


# ==================== T3: jti revoked (jwt_revocations) → 401 ====================

def test_t3_jti_in_jwt_revocations_rejected(app_with_auth, fake_db):
    jti = str(uuid.uuid4())
    token = _expired_access_token(jti)
    _seed_live_session(fake_db, jti)
    _seed_live_refresh_chain(fake_db)
    now = datetime.now(timezone.utc)
    fake_db.jwt_revocations.docs.append({
        "jti": jti,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=dependencies.JWT_EXPIRATION_HOURS)).isoformat(),
    })

    resp = _get_me(app_with_auth, token)
    assert resp.status_code == 401, "jti present in jwt_revocations must NOT authenticate"


def test_t3b_user_all_marker_before_iat_rejected(app_with_auth, fake_db):
    """A user-wide 'all' revocation marker minted AFTER the token was issued
    kills the fallback (password change: old tokens are dead)."""
    jti = str(uuid.uuid4())
    token = _expired_access_token(jti)
    iat = dependencies.jwt.decode(
        token, dependencies.JWT_SECRET, algorithms=[dependencies.JWT_ALGORITHM], options={"verify_exp": False}
    )["iat"]
    _seed_live_session(fake_db, jti)
    _seed_live_refresh_chain(fake_db)
    fake_db.jwt_revocations.docs.append({
        "user_id": "user_test",
        "jti": "all",
        "created_at": datetime.fromtimestamp(iat, tz=timezone.utc) + timedelta(minutes=10),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=dependencies.JWT_EXPIRATION_HOURS)).isoformat(),
    })

    resp = _get_me(app_with_auth, token)
    assert resp.status_code == 401, "user 'all' revocation minted after iat must NOT authenticate"


# ==================== T4: no live refresh chain → 401 ====================

def test_t4_no_live_refresh_record_rejected(app_with_auth, fake_db):
    """User has session record but every refresh token is revoked/expired/rotated
    — dead chain = dead session; fallback must NOT authenticate."""
    jti = str(uuid.uuid4())
    token = _expired_access_token(jti)
    _seed_live_session(fake_db, jti)
    # Seed only DEAD refresh records: revoked (a), expired (b), rotated-and-rotated_at-old (c)
    now = datetime.now(timezone.utc)
    fake_db.refresh_tokens.docs.append({
        "_id": "dead-a", "user_id": "user_test",
        "token_hash": dependencies.hash_refresh_token(dependencies.generate_refresh_token()),
        "created_at": now.isoformat(), "expires_at": (now + timedelta(days=30)).isoformat(),
        "rotated_from": None, "revoked": True,
    })
    fake_db.refresh_tokens.docs.append({
        "_id": "dead-b", "user_id": "user_test",
        "token_hash": dependencies.hash_refresh_token(dependencies.generate_refresh_token()),
        "created_at": now.isoformat(), "expires_at": (now - timedelta(days=1)).isoformat(),
        "rotated_from": None, "revoked": False,
    })
    fake_db.refresh_tokens.docs.append({
        "_id": "dead-c", "user_id": "user_test",
        "token_hash": dependencies.hash_refresh_token(dependencies.generate_refresh_token()),
        "created_at": now.isoformat(), "expires_at": (now + timedelta(days=30)).isoformat(),
        "rotated_from": "older", "revoked": False,
        "rotated_at": (now - timedelta(hours=2)).isoformat(),  # rotated long ago
    })

    resp = _get_me(app_with_auth, token)
    assert resp.status_code == 401, "no live unrotated refresh chain → no fallback auth"


def test_t4b_no_session_record_at_all_rejected(app_with_auth, fake_db):
    """No jti-keyed session record (different jti) → plain 401, fallback misses."""
    token = _expired_access_token(str(uuid.uuid4()))
    _seed_live_refresh_chain(fake_db)  # chain exists, but the session doesn't
    resp = _get_me(app_with_auth, token)
    assert resp.status_code == 401


# ==================== T5: /auth/refresh rate limit ====================

def test_t5_refresh_rate_limit_enforced(app_with_auth, fake_db, monkeypatch):
    """/auth/refresh must honor rate_limit(30, 60) — 429 beyond the 31st call
    in one window (multi-tab burst budget = 30)."""
    # RATE_LIMIT_DISABLED would neuter this test — make sure it's unset.
    monkeypatch.delenv("RATE_LIMIT_DISABLED", raising=False)
    import routers.auth as auth_router
    # Isolate the in-memory limiter window for this test. Note: the limiter
    # relies on defaultdict.__missing__ (auto-list per key) — replacing it
    # with a plain dict breaks the endpoint (KeyError → 500); keep the type.
    monkeypatch.setattr(auth_router, "_rate_limit_store", defaultdict(list))

    client = _client(app_with_auth)
    responses = []
    for i in range(31):
        responses.append(client.post("/api/auth/refresh", cookies={"refresh_token": "unknown-cookie"}))

    # All refresh calls 401 (unknown token) — but the 31st must be 429, not 401.
    statuses = [r.status_code for r in responses]
    assert all(s in (401, 429) for s in statuses), statuses
    assert statuses[-1] == 429, f"31st refresh call must be rate-limited, got {statuses[-1]}"
    assert statuses.count(429) >= 1, "at least one call must hit the limiter"
    # 429 body detail mentions Too many requests (shape parity with login's limiter)
    body = responses[-1].json()
    assert "too many requests" in str(body.get("detail", "")).lower()


def test_t5b_refresh_rate_limit_429_is_rate_limit_response(app_with_auth, fake_db, monkeypatch):
    """Sanity check: the limiter kicks in BEFORE the unknown-token 401 path and
    reports the limiter window message, not 'Invalid refresh token'."""
    monkeypatch.delenv("RATE_LIMIT_DISABLED", raising=False)
    import routers.auth as auth_router
    # Keep the defaultdict type — a plain dict breaks the limiter (KeyError → 500).
    monkeypatch.setattr(auth_router, "_rate_limit_store", defaultdict(list))

    client = _client(app_with_auth)
    statuses = []
    for i in range(31):
        statuses.append(client.post("/api/auth/refresh", cookies={"refresh_token": "x"}).status_code)
    assert statuses[:30] == [401] * 30, "first 30 calls pass the limiter and fail on token"
    assert statuses[30] == 429, "call 31 exceeds the 30/60s budget → 429"
    assert statuses == [401] * 30 + [429], f"429 must appear exactly at the boundary: {statuses}"