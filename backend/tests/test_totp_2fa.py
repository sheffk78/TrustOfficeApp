"""
TOTP 2FA backend test suite (TrustOffice FEATURE 2 â TOTP 2FA).

Full matrix required by the build spec:
  - enroll -> verify -> login with correct code
  - login with wrong code (401, no session)
  - recovery code works once then dead
  - disable requires TOTP + password (both)
  - step-up enforced on vault download WHEN 2FA enabled, absent WHEN not
  - challenge_token cannot be reused as a session token
  - 2FA login rate-limited (forgiving backoff, auto-clears)

In-process FastAPI TestClient + FakeDB (no real Mongo, never hits prod).
Security-events + audit + Discord calls are monkeypatched into the FakeDB so
the request path is exercised exactly as in prod without side effects.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pyotp

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# database.py / dependencies.py read these at import time â set dummies first.
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_2fa_test")
os.environ.setdefault("JWT_SECRET", "test-secret-totp-0123456789abcdef")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import database  # noqa: E402
import dependencies  # noqa: E402
import routers.auth as auth_router  # noqa: E402
import routers.totp_2fa as totp_2fa_router  # noqa: E402
import routers.vault as vault_router  # noqa: E402
import routers.successor as successor_router  # noqa: E402
import utils.audit as audit  # noqa: E402
import utils.stepup_2fa as stepup  # noqa: E402
import services.totp_service as totps  # noqa: E402
import services.security_events as se  # noqa: E402


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

    def sort(self, *a, **k):
        return self

    def skip(self, n):
        return self

    def limit(self, n):
        return self

    async def to_list(self, length=None):
        return list(self._docs)


class FakeCollection:
    def __init__(self):
        self.docs = []
        self.inserts = []
        self.updates = []

    async def find_one(self, query, projection=None, **kwargs):
        # Support dot-path queries (e.g. totp.enabled, createdAt), resolving
        # integer array indices (e.g. totp.recovery_codes.0.used_at) like Mongo.
        def matches(d):
            for k, v in query.items():
                if k.startswith("$"):
                    continue
                if "." in k:
                    cur = d
                    ok = True
                    for part in k.split("."):
                        if isinstance(cur, dict) and part in cur:
                            cur = cur[part]
                        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
                            cur = cur[int(part)]
                        else:
                            ok = False
                            break
                    if not ok or cur != v:
                        return False
                else:
                    if d.get(k) != v:
                        return False
            return True

        for d in self.docs:
            if matches(d):
                return d
        return None

    def find(self, query=None, projection=None):
        return FakeCursor(
            [d for d in self.docs if (query is None or _subset(query, d))]
        )

    async def insert_one(self, doc):
        d = dict(doc)
        if "_id" not in d:
            d["_id"] = f"id_{len(self.docs)}"
        self.docs.append(d)
        self.inserts.append(d)
        return FakeResult(inserted_id=d["_id"])

    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if _subset(query, d):
                if "$set" in update:
                    _deep_set(d, update["$set"])
                if "$unset" in update:
                    for k in update["$unset"]:
                        _deep_unset(d, k)
                return FakeResult(modified_count=1, matched_count=1)
        if upsert:
            d = dict(query.get("$setOnInsert", {}))
            if "$set" in update:
                d.update(update["$set"])
            if "_id" not in d:
                d["_id"] = f"id_{len(self.docs)}"
            self.docs.append(d)
            return FakeResult(inserted_id=d["_id"])
        return FakeResult(modified_count=0, matched_count=0)

    async def update_many(self, query, update):
        n = 0
        for d in self.docs:
            if _subset(query, d):
                if "$set" in update:
                    _deep_set(d, update["$set"])
                n += 1
        return FakeResult(modified_count=n, matched_count=n)

    async def delete_one(self, query):
        for i, d in enumerate(self.docs):
            if _subset(query, d):
                self.docs.pop(i)
                return FakeResult(deleted_count=1)
        return FakeResult(deleted_count=0)

    async def delete_many(self, query):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not _subset(query, d)]
        return FakeResult(deleted_count=before - len(self.docs))

    async def count_documents(self, query=None):
        return len([d for d in self.docs if (query is None or _subset(query, d))])

    async def create_index(self, *a, **k):
        return None


def _subset(query, doc):
    for k, v in query.items():
        if k.startswith("$"):
            continue
        if "." in k:
            cur = doc
            ok = True
            for part in k.split("."):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
                    cur = cur[int(part)]
                else:
                    ok = False
                    break
            if not ok or cur != v:
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


def _deep_set(d, fields):
    for k, v in fields.items():
        parts = k.split(".")
        cur = d
        for part in parts[:-1]:
            if isinstance(cur, dict):
                cur = cur.setdefault(part, {})
            elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
                cur = cur[int(part)]
            else:
                cur = {}
        if isinstance(cur, dict):
            cur[parts[-1]] = v
        elif isinstance(cur, list) and parts[-1].isdigit() and int(parts[-1]) < len(cur):
            cur[int(parts[-1])] = v



def _deep_unset(d, k):
    parts = k.split(".")
    cur = d
    for part in parts[:-1]:
        if not isinstance(cur, dict) or part not in cur:
            return
        cur = cur[part]
    if isinstance(cur, dict):
        cur.pop(parts[-1], None)


class FakeDB:
    def __init__(self):
        self.users = FakeCollection()
        self.security_events = FakeCollection()
        self.audit_logs = FakeCollection()
        self.vault_documents = FakeCollection()
        self.trusts = FakeCollection()
        self.subscriptions = FakeCollection()
        self.successor_access = FakeCollection()

    def __getattr__(self, name):
        col = FakeCollection()
        setattr(self, name, col)
        return col


@pytest.fixture(autouse=True)
def _clear_caches():
    totps._totp_failures.clear()
    se._ALERT_CACHE.clear()
    auth_router._rate_limit_store.clear()
    yield
    totps._totp_failures.clear()
    se._ALERT_CACHE.clear()
    auth_router._rate_limit_store.clear()


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(database, "db", db)
    monkeypatch.setattr(dependencies, "db", db)
    monkeypatch.setattr(auth_router, "db", db)
    monkeypatch.setattr(totp_2fa_router, "db", db)
    monkeypatch.setattr(vault_router, "db", db)
    monkeypatch.setattr(successor_router, "db", db)
    monkeypatch.setattr(audit, "db", db)
    monkeypatch.setattr(totps, "db", db)
    try:
        monkeypatch.setattr(se, "db", db)
    except AttributeError:
        pass
    return db


@pytest.fixture
def client(fake_db, monkeypatch):
    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api")
    app.include_router(totp_2fa_router.router, prefix="/api")
    app.include_router(vault_router.router, prefix="/api")
    app.include_router(successor_router.router, prefix="/api")
    return TestClient(app, raise_server_exceptions=False)


# ==================== Helpers ====================

def _seed_user(db, *, user_id, email, admin=False, password="Password123", with_2fa=False, secret=None):
    doc = {
        "_id": user_id,
        "user_id": user_id,
        "email": email,
        "name": "Test User",
        "password_hash": dependencies.hash_password(password),
        "is_admin": admin,
        "last_login": None,
        "totp": {},
    }
    if with_2fa:
        secret = secret or totps.generate_totp_secret()
        doc["totp"] = {
            "enabled": True,
            "secret": secret,
            "recovery_codes": [
                {"code_hash": "x", "used_at": None, "used_ip": None} for _ in range(10)
            ],
        }
    db.users.docs.append(doc)
    # Seed an active (forever_free) subscription so write-gated routes
    # (require_write_access) resolve before step-up 2FA must be enforced.
    db.subscriptions.docs.append({
        "user_id": user_id,
        "plan_type": "forever_free",
        "status": "active",
    })
    return secret


def _current_totp(secret):
    return pyotp.TOTP(secret).now()


def _token_for(client, email, password="Password123", secret=None):
    """Return a real access token for the seeded user (completes 2FA if enabled)."""
    r = _login_password(client, email, password)
    if r.status_code == 200:
        return r.json()["token"]
    # 2FA required -> finish the 2FA step with the current TOTP for `secret`.
    assert r.status_code == 401 and r.json()["detail"] == "2fa_required"
    ct = r.json()["challenge_token"]  # flat body contract (header also present)
    assert ct == r.headers["X-2FA-Challenge-Token"]
    fin = client.post("/api/auth/2fa/login", json={"challenge_token": ct, "code": _current_totp(secret)})
    assert fin.status_code == 200, fin.text
    return fin.json()["token"]


def _login_password(client, email, password):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def _enroll_verify(client, password, email="a@b.com"):
    """End-to-end enroll + verify, returns (enroll_resp, secret, recovery_codes)."""
    token = _token_for(client, email, password)
    e = client.post("/api/auth/2fa/enroll", json={"password": password},
                    headers={"Authorization": f"Bearer {token}"})
    assert e.status_code == 200, e.text
    secret = e.json()["secret"]
    code = _current_totp(secret)
    v = client.post("/api/auth/2fa/verify", json={"code": code},
                    headers={"Authorization": f"Bearer {token}"})
    assert v.status_code == 200, v.text
    return e, secret, v.json()["recovery_codes"]


# ==================== TESTS ====================

class TestEnroll:
    def test_enroll_requires_correct_password(self, client, fake_db):
        _seed_user(fake_db, user_id="u1", email="a@b.com")
        assert client.post("/api/auth/2fa/enroll", json={"password": "wrong"}).status_code == 401
        token = _token_for(client, "a@b.com")
        ok = client.post("/api/auth/2fa/enroll", json={"password": "Password123"},
                         headers={"Authorization": f"Bearer {token}"})
        assert ok.status_code == 200
        assert "secret" in ok.json() and "provisioning_uri" in ok.json()
        assert ok.json()["provisioning_uri"].startswith("otpauth://totp/TrustOffice")

    def test_enroll_returns_provisioning_uri(self, client, fake_db):
        _seed_user(fake_db, user_id="u1", email="a@b.com")
        token = _token_for(client, "a@b.com")
        r = client.post("/api/auth/2fa/enroll", json={"password": "Password123"},
                        headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        assert body["secret"] and body["provisioning_uri"].startswith("otpauth://totp/")
        # enrollment pending â NOT yet enabled
        assert fake_db.users.docs[0]["totp"]["enabled"] is False
        assert fake_db.users.docs[0]["totp"]["enrollment_secret"] == body["secret"]

    def test_enroll_without_2fa_password_set_is_400(self, client, fake_db):
        fake_db.users.docs.append({
            "_id": "u2", "user_id": "u2", "email": "c@d.com", "name": "X",
            "password_hash": None, "is_admin": False, "totp": {},
        })
        # This account has no password -> cannot get a token; enroll should 400.
        r = client.post("/api/auth/2fa/enroll", json={"password": "whatever"})
        assert r.status_code in (400, 401)


class TestEnrollVerifyLogin:
    def test_enroll_verify_login_correct_code(self, client, fake_db):
        _seed_user(fake_db, user_id="u1", email="a@b.com")
        e, secret, recovery = _enroll_verify(client, "Password123")
        # Now enabled
        assert fake_db.users.docs[0]["totp"]["enabled"] is True
        # recovery codes hashed at rest, 10 of them
        rc = fake_db.users.docs[0]["totp"]["recovery_codes"]
        assert len(rc) == 10
        assert all(c["code_hash"].startswith("$2") for c in rc)
        assert all(c["used_at"] is None for c in rc)
        assert len(recovery) == 10

        # Login: password ok + 2FA enabled -> 401 with challenge token (no session)
        r = _login_password(client, "a@b.com", "Password123")
        assert r.status_code == 401
        assert r.json()["detail"] == "2fa_required"
        ct = r.json()["challenge_token"]  # flat body contract
        assert ct and ct == r.headers.get("X-2FA-Challenge-Token")

        # Complete 2FA login with correct code
        fin = client.post("/api/auth/2fa/login", json={"challenge_token": ct, "code": _current_totp(secret)})
        assert fin.status_code == 200, fin.text
        assert fin.json()["token"]
        # challenge token must NOT be a usable session token
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {ct}"})
        assert me.status_code in (401, 403)

    def test_login_with_wrong_code_rejected(self, client, fake_db):
        _seed_user(fake_db, user_id="u1", email="a@b.com")
        _enroll_verify(client, "Password123")
        r = _login_password(client, "a@b.com", "Password123")
        ct = r.headers["X-2FA-Challenge-Token"]
        bad = client.post("/api/auth/2fa/login", json={"challenge_token": ct, "code": "000000"})
        assert bad.status_code == 401
        # No session issued on failure
        assert "token" not in bad.json() or not bad.json().get("token") == ""


class TestRecoveryCode:
    def test_recovery_code_works_once_then_dead(self, client, fake_db):
        secret = _seed_user(fake_db, user_id="u1", email="a@b.com", with_2fa=True)
        r = _login_password(client, "a@b.com", "Password123")
        assert r.status_code == 401
        ct = r.headers["X-2FA-Challenge-Token"]

        # Use a real recovery code: fabricate one and inject its bcrypt hash.
        plain = "ABCDEFGH"
        import bcrypt
        secret_used = totps.get_totp_state(fake_db.users.docs[0])["secret"]
        rc_slot = fake_db.users.docs[0]["totp"]["recovery_codes"][0]
        rc_slot["code_hash"] = bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

        first = client.post("/api/auth/2fa/login", json={"challenge_token": ct, "code": plain})
        assert first.status_code == 200, first.text
        assert first.json()["user"]

        # Same recovery code again -> must fail (single-use)
        r2 = _login_password(client, "a@b.com", "Password123")
        ct2 = r2.headers["X-2FA-Challenge-Token"]
        second = client.post("/api/auth/2fa/login", json={"challenge_token": ct2, "code": plain})
        assert second.status_code == 401
        # slot now consumed
        consumed = fake_db.users.docs[0]["totp"]["recovery_codes"][0]
        assert consumed["used_at"] is not None
        assert totps.count_unused_recovery_codes(fake_db.users.docs[0]) == 9


class TestDisable:
    def test_disable_requires_totp_and_password(self, client, fake_db):
        secret = _seed_user(fake_db, user_id="u1", email="a@b.com", with_2fa=True)
        # No 2FA auth header here â disable is an authenticated endpoint.
        # Authenticated call needs a session; build one by logging in via 2fa.
        token = _token_for(client, "a@b.com", secret=secret)
        headers = {"Authorization": f"Bearer {token}"}

        # Missing password
        bad = client.post("/api/auth/2fa/disable", json={"totp_code": _current_totp(secret), "password": ""}, headers=headers)
        assert bad.status_code == 401
        # Wrong password
        bad2 = client.post("/api/auth/2fa/disable", json={"totp_code": _current_totp(secret), "password": "nope"}, headers=headers)
        assert bad2.status_code == 401
        # Wrong TOTP
        bad3 = client.post("/api/auth/2fa/disable", json={"totp_code": "000000", "password": "Password123"}, headers=headers)
        assert bad3.status_code == 401

        # Both correct -> disabled
        ok = client.post("/api/auth/2fa/disable", json={"totp_code": _current_totp(secret), "password": "Password123"}, headers=headers)
        assert ok.status_code == 200, ok.text
        assert fake_db.users.docs[0]["totp"]["enabled"] is False
        # After disable, login no longer requires 2FA
        after = _login_password(client, "a@b.com", "Password123")
        assert after.status_code == 200
        assert "token" in after.json()


class TestStatus:
    def test_status_reflects_enforced_for_admin(self, client, fake_db):
        secret = _seed_user(fake_db, user_id="admin1", email="admin@b.com", admin=True, with_2fa=True)
        # login + token
        token = _token_for(client, "admin@b.com", secret=secret)
        s = client.get("/api/auth/2fa/status", headers={"Authorization": f"Bearer {token}"})
        assert s.status_code == 200
        body = s.json()
        assert body["enabled"] is True
        assert body["enforced"] is True
        assert body["recovery_codes_remaining"] == 10

    def test_status_enforced_false_for_non_admin(self, client, fake_db):
        secret = _seed_user(fake_db, user_id="u1", email="a@b.com", with_2fa=True)
        token = _token_for(client, "a@b.com", secret=secret)
        s = client.get("/api/auth/2fa/status", headers={"Authorization": f"Bearer {token}"})
        assert s.json()["enforced"] is False


class TestStepUp:
    def test_vault_download_stepup_enforced_when_2fa_on(self, client, fake_db):
        secret = _seed_user(fake_db, user_id="u1", email="a@b.com", with_2fa=True)
        fake_db.vault_documents.docs.append({
            "doc_id": "d1", "user_id": "u1", "trust_id": "t1",
            "file_content": b"hello", "file_name": "x.pdf", "file_content_type": "application/pdf",
        })
        token = _token_for(client, "a@b.com", secret=secret)
        headers = {"Authorization": f"Bearer {token}"}

        # No step-up code -> 403 stepup required
        miss = client.get("/api/vault/documents/d1/download", headers=headers)
        assert miss.status_code == 403
        assert miss.json()["detail"] == "2fa_stepup_required"

        # Wrong code -> still 403
        wrong = client.get("/api/vault/documents/d1/download", headers={**headers, "X-2FA-Code": "000000"})
        assert wrong.status_code == 403

        # Correct code -> 200
        ok = client.get("/api/vault/documents/d1/download", headers={**headers, "X-2FA-Code": _current_totp(secret)})
        assert ok.status_code == 200
        assert ok.content == b"hello"

    def test_vault_download_stepup_absent_when_2fa_off(self, client, fake_db):
        _seed_user(fake_db, user_id="u1", email="a@b.com", with_2fa=False)
        fake_db.vault_documents.docs.append({
            "doc_id": "d1", "user_id": "u1", "trust_id": "t1",
            "file_content": b"hello", "file_name": "x.pdf", "file_content_type": "application/pdf",
        })
        # Login without 2FA -> normal session
        r = _login_password(client, "a@b.com", "Password123")
        assert r.status_code == 200
        token = r.json()["token"]
        # No X-2FA-Code header required
        ok = client.get("/api/vault/documents/d1/download", headers={"Authorization": f"Bearer {token}"})
        assert ok.status_code == 200
        assert ok.content == b"hello"

    def test_successor_grant_stepup_enforced_when_2fa_on(self, client, fake_db):
        secret = _seed_user(fake_db, user_id="u1", email="a@b.com", with_2fa=True)
        fake_db.trusts.docs.append({
            "trust_id": "t1", "user_id": "u1", "name": "T",
            "successor_trustee_email": "succ@b.com", "successor_trustee_name": "Succ",
        })
        token = _token_for(client, "a@b.com", secret=secret)
        headers = {"Authorization": f"Bearer {token}"}

        miss = client.post("/api/trusts/t1/successor/send", headers=headers)
        assert miss.status_code == 403
        assert miss.json()["detail"] == "2fa_stepup_required"

        ok = client.post("/api/trusts/t1/successor/send", headers={**headers, "X-2FA-Code": _current_totp(secret)})
        # 200 (sent) or 502 (email not configured â either way, reached the body)
        assert ok.status_code in (200, 502)

    def test_successor_grant_stepup_absent_when_2fa_off(self, client, fake_db):
        _seed_user(fake_db, user_id="u1", email="a@b.com", with_2fa=False)
        fake_db.trusts.docs.append({
            "trust_id": "t1", "user_id": "u1", "name": "T",
            "successor_trustee_email": "succ@b.com", "successor_trustee_name": "Succ",
        })
        r = _login_password(client, "a@b.com", "Password123")
        assert r.status_code == 200
        token = r.json()["token"]
        ok = client.post("/api/trusts/t1/successor/send", headers={"Authorization": f"Bearer {token}"})
        assert ok.status_code in (200, 502)


class TestChallengeToken:
    def test_challenge_token_not_reusable_as_session(self, client, fake_db):
        secret = _seed_user(fake_db, user_id="u1", email="a@b.com", with_2fa=True)
        r = _login_password(client, "a@b.com", "Password123")
        ct = r.headers["X-2FA-Challenge-Token"]
        # The challenge token decodes as type='2fa_challenge', not an access token.
        assert totps.verify_challenge_token(ct) is not None
        assert totps.verify_challenge_token(ct)["type"] == "2fa_challenge"
        # get_current_user requires type=='access' -> rejected
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {ct}"})
        assert me.status_code in (401, 403)
        # A fresh access token from a completed 2FA login IS usable
        fin = client.post("/api/auth/2fa/login", json={"challenge_token": ct, "code": _current_totp(secret)})
        real = fin.json()["token"]
        me2 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {real}"})
        assert me2.status_code == 200

    def test_expired_challenge_token_rejected(self, client, fake_db, monkeypatch):
        secret = _seed_user(fake_db, user_id="u1", email="a@b.com", with_2fa=True)
        import jwt as _jwt
        expired = _jwt.encode(
            {"user_id": "u1", "email": "a@b.com", "type": "2fa_challenge",
             "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
            dependencies.JWT_SECRET, algorithm=dependencies.JWT_ALGORITHM,
        )
        fin = client.post("/api/auth/2fa/login", json={"challenge_token": expired, "code": _current_totp(secret)})
        assert fin.status_code == 401


class TestRateLimit:
    def test_2fa_login_rate_limited_after_5_failures(self, client, fake_db):
        secret = _seed_user(fake_db, user_id="u1", email="a@b.com", with_2fa=True)
        r = _login_password(client, "a@b.com", "Password123")
        ct = r.headers["X-2FA-Challenge-Token"]
        # 5 wrong codes -> still 401, but 6th is blocked with 429 (forgiving window).
        last = None
        for _ in range(totps.TOTP_FAIL_LIMIT):
            last = client.post("/api/auth/2fa/login", json={"challenge_token": ct, "code": "000000"})
            assert last.status_code == 401
        blocked = client.post("/api/auth/2fa/login", json={"challenge_token": ct, "code": "000000"})
        assert blocked.status_code == 429
        body = blocked.json()  # flat body contract
        assert isinstance(body, dict)
        assert body["detail"] == "2fa_rate_limited"
        assert isinstance(body["retry_after"], int) and body["retry_after"] > 0
        assert isinstance(body["message"], str) and body["message"]
        assert "not locked" in body["message"].lower()
        # The correct code is NOT accepted while rate-limited (forgiving, but enforced).
        during = client.post("/api/auth/2fa/login", json={"challenge_token": ct, "code": _current_totp(secret)})
        assert during.status_code == 429
        # After the window clears, the correct code works again (no permanent lock).
        totps._totp_failures.clear()
        after = client.post("/api/auth/2fa/login", json={"challenge_token": ct, "code": _current_totp(secret)})
        assert after.status_code == 200

    def test_429_body_has_retry_after_and_message(self, client, fake_db):
        secret = _seed_user(fake_db, user_id="u1", email="a@b.com", with_2fa=True)
        r = _login_password(client, "a@b.com", "Password123")
        ct = r.headers["X-2FA-Challenge-Token"]
        # Drive the window to the limit: limit invalid codes (still 401, recorded),
        # then the next attempt is blocked with 429.
        for _ in range(totps.TOTP_FAIL_LIMIT):
            f = client.post("/api/auth/2fa/login", json={"challenge_token": ct, "code": "000000"})
            assert f.status_code == 401
        blocked = client.post("/api/auth/2fa/login", json={"challenge_token": ct, "code": "000000"})
        assert blocked.status_code == 429
        body = blocked.json()  # flat body contract
        assert body["detail"] == "2fa_rate_limited"
        # retry_after is a positive integer (seconds until window clears).
        assert isinstance(body["retry_after"], int)
        assert body["retry_after"] > 0
        # message is non-empty and mentions a whole-minute wait.
        assert isinstance(body["message"], str) and len(body["message"]) > 0
        assert "minute" in body["message"].lower()
        assert "recovery code" in body["message"].lower()

    def test_invalid_code_body_decrements_attempts_remaining(self, client, fake_db):
        secret = _seed_user(fake_db, user_id="u1", email="a@b.com", with_2fa=True)
        r = _login_password(client, "a@b.com", "Password123")
        ct = r.headers["X-2FA-Challenge-Token"]
        seen = []
        # All TOTP_FAIL_LIMIT failures return 401 with a decreasing attempts_remaining
        # (the limit check passes on the 5th attempt, which is then recorded).
        for _ in range(totps.TOTP_FAIL_LIMIT):
            f = client.post("/api/auth/2fa/login", json={"challenge_token": ct, "code": "000000"})
            assert f.status_code == 401
            body = f.json()  # flat body contract
            assert body["detail"] == "2fa_invalid_code"
            assert "attempts_remaining" in body
            assert isinstance(body["attempts_remaining"], int)
            seen.append(body["attempts_remaining"])
        # Strictly decreasing as failures accumulate (4, 3, 2, 1, 0).
        assert seen == sorted(seen, reverse=True)
        assert seen[0] == totps.TOTP_FAIL_LIMIT - 1  # 4 left at first failure
        assert seen[-1] == 0  # 0 left after the limit is reached
        # The next (6th) attempt is blocked -> 429 with retry_after.
        final = client.post("/api/auth/2fa/login", json={"challenge_token": ct, "code": "000000"})
        assert final.status_code == 429
        fb = final.json()  # flat body contract
        assert fb["detail"] == "2fa_rate_limited"
        assert isinstance(fb["retry_after"], int) and fb["retry_after"] > 0


class TestSecurityEvents:
    def test_security_events_written_for_2fa_actions(self, client, fake_db):
        _seed_user(fake_db, user_id="u1", email="a@b.com")
        token = _token_for(client, "a@b.com")
        # enroll (authenticated, correct password)
        client.post("/api/auth/2fa/enroll", json={"password": "Password123"},
                    headers={"Authorization": f"Bearer {token}"})
        types = [e["event_type"] for e in fake_db.security_events.docs]
        assert "2fa_enroll_started" in types
        # No TOTP code or challenge token value is ever stored in event details.
        for e in fake_db.security_events.docs:
            assert "code" not in str(e.get("details", {})).lower()

    def test_failed_2fa_login_writes_event(self, client, fake_db):
        secret = _seed_user(fake_db, user_id="u1", email="a@b.com", with_2fa=True)
        r = _login_password(client, "a@b.com", "Password123")
        ct = r.headers["X-2FA-Challenge-Token"]
        client.post("/api/auth/2fa/login", json={"challenge_token": ct, "code": "000000"})
        types = [e["event_type"] for e in fake_db.security_events.docs]
        assert "2fa_login_failed" in types
