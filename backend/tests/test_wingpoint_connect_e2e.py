"""
Connect Flow v2 — END-TO-END verification against the app's REAL database.

Unlike tests/test_wingpoint_connect_flow.py (which uses an in-memory fake),
this exercises the full FastAPI ASGI stack — real routing, real Pydantic
validation, real MongoDB (or the repo's mongomock stand-in), real JWT
issuance, real password hashing.

Isolation: every test uses its own app_id, its own email and its own
forwarded client IP, so the connect rate-limit buckets never collide with
another suite. Cleanup deletes ONLY the documents this module created —
nothing is ever dropped collection-wide (the CI unit run shares one MongoDB
with every other suite).

Read-back goes through the app's own `database.db` handle on the TestClient's
event loop, so the assertions hold whether that handle is a real mongod or
the repo's mongomock stand-in (several sibling suites swap the driver at
module import — see the note in conftest.py about REAL_MOTOR_CLIENT_CLASS).

Run:
  cd backend
  MONGO_URL=mongodb://localhost:27017 DB_NAME=to_connect_e2e \
    JWT_SECRET=e2e-test-secret-key-at-least-32-chars \
    CORS_ORIGINS=https://app.trustoffice.app \
    ../.venv/bin/python -m pytest tests/test_wingpoint_connect_e2e.py -q
"""
import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_connect_e2e")
os.environ.setdefault("JWT_SECRET", "e2e-test-secret-key-at-least-32-chars")
os.environ.setdefault("CORS_ORIGINS", "https://app.trustoffice.app")

REDIRECT_HOST = "wingpointtrust.com"


def _ctx(tag):
    """A connect context unique to one test: own app_id, email, wp_ref."""
    return {
        "wp_ref": f"WP-E2E-{tag}",
        "app_id": f"app_{tag}",
        "email": f"e2e-{tag}@example.com",
        "redirect_url": f"https://{REDIRECT_HOST}/trustoffice/callback?app_id=app_{tag}",
    }


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    import server

    with TestClient(server.app) as c:
        yield c


@pytest.fixture
def ctx():
    """A per-test connect context + the X-Forwarded-For that isolates the
    per-IP rate-limit bucket (the TestClient always reports 'testclient')."""
    tag = uuid.uuid4().hex[:12]
    headers = {"X-Forwarded-For": f"198.51.100.{int(tag[:2], 16) % 250 + 1}"}
    return _ctx(tag), headers


@pytest.fixture
def db_read(client):
    """Read back from the app's own DB handle, on the app's event loop."""
    import database

    def _read(collection, query):
        async def _one():
            return await getattr(database.db, collection).find_one(query)

        return client.portal.call(_one)

    return _read


@pytest.fixture
def db_write(client):
    """Write to the app's own DB handle, on the app's event loop."""
    import database

    def _write(collection, doc):
        async def _one():
            return await getattr(database.db, collection).insert_one(doc)

        return client.portal.call(_one)

    return _write


@pytest.fixture
def db_count(client):
    import database

    def _count(collection, query):
        async def _one():
            return await getattr(database.db, collection).count_documents(query)

        return client.portal.call(_one)

    return _count


@pytest.fixture(autouse=True)
def cleanup(client):
    """Remove only what this module created — never a whole collection."""
    import database

    created = []

    yield created

    async def _purge():
        for email in created:
            for col in ("users", "subscriptions", "wingpoint_connect_codes"):
                try:
                    await getattr(database.db, col).delete_many({"email": email})
                except Exception:
                    pass

    try:
        client.portal.call(_purge)
    except Exception:
        pass


def _seed_user(db_write, email, password_hash=None, **extra):
    doc = {
        "user_id": f"user_{email}",
        "email": email,
        "name": "E2E Member",
        "password_hash": password_hash,
        "created_at": "2026-10-01T00:00:00Z",
    }
    doc.update(extra)
    db_write("users", doc)
    return doc


def test_e2e_branch_a_new_account_signup(client, db_read, db_count, db_write, ctx, cleanup):
    """Branch (a): no account -> prefilled signup -> account created -> 200."""
    body, headers = ctx
    cleanup.append(body["email"])

    r = client.post("/api/wingpoint-connect/resolve", json=body, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "new"

    r = client.post(
        "/api/wingpoint-connect/signup",
        json={**body, "name": "E2E Member", "password": "BrandNewPass1"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["token"]
    assert payload["user"]["email"] == body["email"]

    # The account really landed in the database, bound to the WP ref.
    stored = db_read("users", {"email": body["email"]})
    assert stored is not None, "signup did not persist the user"
    assert stored["wp_ref"] == body["wp_ref"]
    assert stored["source"] == "wingpoint"
    assert stored["password_hash"] != "BrandNewPass1"

    # A second signup for the same email is refused (no duplicate account).
    r2 = client.post(
        "/api/wingpoint-connect/signup",
        json={**body, "name": "E2E Member", "password": "BrandNewPass1"},
        headers=headers,
    )
    assert r2.status_code == 409, r2.text
    assert db_count("users", {"email": body["email"]}) == 1


def test_e2e_branch_b_never_activated_claim(
    client, db_read, db_count, db_write, ctx, cleanup, monkeypatch
):
    """Branch (b): provisioned account with no password -> claim + activate."""
    from dependencies import verify_password
    import routers.wingpoint_connect as wc

    body, headers = ctx
    cleanup.append(body["email"])

    _seed_user(
        db_write,
        body["email"],
        password_hash=None,
        created_via="wingpoint_provision",
        source="wingpoint",
        wp_ref=body["wp_ref"],
    )

    r = client.post("/api/wingpoint-connect/resolve", json=body, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "needs_activation"

    # Capture the emailed code instead of sending mail.
    captured = {}

    async def fake_send(to_email, user_name, code, **_kwargs):
        captured["email"] = to_email
        captured["code"] = code
        return {"status": "sent"}

    monkeypatch.setattr(
        wc.email_service, "send_wingpoint_connect_code_email", fake_send, raising=False
    )

    r = client.post("/api/wingpoint-connect/claim/request-code", json=body, headers=headers)
    assert r.status_code == 200, r.text
    assert captured["email"] == body["email"]
    assert len(captured["code"]) == 6 and captured["code"].isdigit()

    r = client.post(
        "/api/wingpoint-connect/claim/verify",
        json={**body, "code": captured["code"], "new_password": "BrandNewPass1"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["token"]

    # The EXISTING account was activated — still exactly one user.
    assert db_count("users", {"email": body["email"]}) == 1
    stored = db_read("users", {"email": body["email"]})
    assert verify_password("BrandNewPass1", stored["password_hash"])

    # And it now resolves as activated.
    r = client.post("/api/wingpoint-connect/resolve", json=body, headers=headers)
    assert r.json()["state"] == "activated"


def test_e2e_branch_c_activated_login(client, db_read, db_write, ctx, cleanup):
    """Branch (c): account with a password -> prefilled login."""
    from dependencies import hash_password

    body, headers = ctx
    cleanup.append(body["email"])

    _seed_user(db_write, body["email"], password_hash=hash_password("AlreadySet123"))

    r = client.post("/api/wingpoint-connect/resolve", json=body, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "activated"


def test_e2e_scoped_lookup_rejects_missing_context(client, ctx):
    """The lookup is scoped — no generic public email-existence API."""
    body, headers = ctx

    # No wp_ref
    r = client.post(
        "/api/wingpoint-connect/resolve", json={**body, "wp_ref": ""}, headers=headers
    )
    assert r.status_code == 400, r.text

    # No app_id and no app_id inside the redirect
    r = client.post(
        "/api/wingpoint-connect/resolve",
        json={**body, "app_id": "", "redirect_url": f"https://{REDIRECT_HOST}/cb"},
        headers=headers,
    )
    assert r.status_code == 400, r.text

    # Non-WingPoint redirect host
    r = client.post(
        "/api/wingpoint-connect/resolve",
        json={**body, "redirect_url": f"https://evil.example.com/cb?app_id={body['app_id']}"},
        headers=headers,
    )
    assert r.status_code == 400, r.text

    # No redirect at all
    r = client.post(
        "/api/wingpoint-connect/resolve", json={**body, "redirect_url": ""}, headers=headers
    )
    assert r.status_code == 400, r.text


def test_e2e_rate_limit_trips(client, ctx):
    """Repeated resolves from one email are rate limited."""
    body, headers = ctx
    codes = [
        client.post("/api/wingpoint-connect/resolve", json=body, headers=headers).status_code
        for _ in range(8)
    ]
    assert 429 in codes, f"expected a 429 among {codes}"


def test_e2e_no_email_leak_in_response(client, ctx):
    """Prefill is UI-only — the server never reflects the member's email back."""
    body, headers = ctx
    r = client.post("/api/wingpoint-connect/resolve", json=body, headers=headers)
    assert r.status_code == 200
    assert body["email"] not in r.text
    assert "prefill_email" not in r.text
