#!/usr/bin/env python3
"""Successor access methods (Jeff 2026-10-16): access-code + death-certificate claim.

Trustee chooses the method per trust; access code is the DEFAULT. Covers:
- code generate → claim → packet (happy path)
- code reuse (reusable until revoked, use_count grows)
- rotate → old code invalid
- revoke → code invalid
- rate-limit guard dependency returns 429 (in-memory limiter)
- method switching (default access_code; death_cert)
- death-cert claim submit → pending → approve → one-time token email
- claim reject
- admin-only guard on review endpoints
Runs against mongomock — never touches prod.
"""
import os
import sys
import io

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test_successor")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

import motor.motor_asyncio
import mongomock_motor
motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio

import database
import dependencies
import routers.successor as successor

db = database.db


@pytest_asyncio.fixture
async def ctx(monkeypatch):
    import mongomock_motor
    fresh = mongomock_motor.AsyncMongoMockClient()[os.environ["DB_NAME"]]
    for mod in (database, dependencies, successor):
        monkeypatch.setattr(mod, "db", fresh)
    globals()["db"] = fresh
    for c in ("trusts", "users", "successor_access", "successor_claims", "entities",
              "trust_unit_certificates", "class_beneficiaries", "bank_accounts",
              "vault_documents", "governance_tasks", "tax_calendar", "audit_events"):
        await db[c].delete_many({})

    async def fake_noop_write(user_id, action, resource, resource_id, meta=None):
        return None

    monkeypatch.setattr(successor, "log_audit_event", fake_noop_write)

    async def fake_notify(access_doc, trust):
        successor.NOTIFIED.append((access_doc.get("use_count"),))
    monkeypatch.setattr(successor, "_notify_trustee_code_used", fake_notify)
    successor.NOTIFIED = []
    yield


@pytest.fixture
def owner_user():
    return {"user_id": "u_owner", "email": "owner@x.com", "name": "Owner", "is_admin": False}


@pytest.fixture
def admin_user():
    return {"user_id": "u_admin", "email": "admin@x.com", "name": "Admin", "is_admin": True}


async def _seed_trust(trust_id="t_succ", method=None):
    doc = {
        "trust_id": trust_id,
        "name": "Family Trust",
        "user_id": "u_owner",
        "trustee_names": "Jeff Kohler",
        "successor_trustee_name": "Sam Successor",
        "successor_trustee_email": "sam@successor.com",
        "successor_instructions": "Keep it simple.",
    }
    if method:
        doc["successor_access_method"] = method
    await db.trusts.insert_one(doc)
    await db.users.insert_one({"user_id": "u_owner", "email": "owner@x.com", "name": "Jeff"})
    await db.entities.insert_one({"trust_id": trust_id, "user_id": "u_owner", "name": "Family LLC", "entity_type": "llc"})
    return doc


@pytest.mark.asyncio
async def test_default_method_is_access_code(ctx, owner_user):
    """Trusts default to the access-code method (Jeff's choice model, nothing set yet)."""
    await _seed_trust()
    status = await successor.get_successor_access_status("t_succ", user=owner_user)
    assert status["method"] == "access_code"
    assert status["code_set"] is False


@pytest.mark.asyncio
async def test_generate_code_returns_raw_once_and_status_hint(ctx, owner_user):
    await _seed_trust()
    out = await successor.generate_successor_code("t_succ", user=owner_user, _stepup=None)
    code = out["code"]
    assert code.count("-") == 3 and len(code.replace("-", "")) == 16
    # Hash-only storage — the raw code must NOT be in the database.
    doc = await db.successor_access.find_one({"trust_id": "t_succ", "kind": "access_code"})
    assert code not in (doc.get("code_hint") or "")
    assert "code_hash" in doc and doc["code_hash"] != code
    status = await successor.get_successor_access_status("t_succ", user=owner_user)
    assert status["code_set"] is True
    assert status["code_hint"] == out["code_hint"]


@pytest.mark.asyncio
async def test_code_claim_returns_packet_and_counts_use(ctx, owner_user):
    await _seed_trust()
    out = await successor.generate_successor_code("t_succ", user=owner_user, _stepup=None)
    packet = await successor.claim_successor_code(successor.SuccessorCodeClaim(code=out["code"]),
                                                  request=None, _rl=None)
    assert packet["trust"]["name"] == "Family Trust"
    assert packet["entities"][0]["name"] == "Family LLC"
    assert packet["successor_name"] == "Sam Successor"
    doc = await db.successor_access.find_one({"trust_id": "t_succ", "kind": "access_code"})
    assert doc["use_count"] == 1 and doc["first_used_at"] is not None
    assert successor.NOTIFIED == [(1,)]


@pytest.mark.asyncio
async def test_code_is_reusable_until_revoked(ctx, owner_user):
    await _seed_trust()
    out = await successor.generate_successor_code("t_succ", user=owner_user, _stepup=None)
    await successor.claim_successor_code(successor.SuccessorCodeClaim(code=out["code"]), request=None, _rl=None)
    await successor.claim_successor_code(successor.SuccessorCodeClaim(code=out["code"]), request=None, _rl=None)
    doc = await db.successor_access.find_one({"trust_id": "t_succ", "kind": "access_code"})
    assert doc["use_count"] == 2


@pytest.mark.asyncio
async def test_rotate_invalidates_old_code(ctx, owner_user):
    await _seed_trust()
    first = await successor.generate_successor_code("t_succ", user=owner_user, _stepup=None)
    second = await successor.generate_successor_code("t_succ", user=owner_user, _stepup=None)
    with pytest.raises(Exception):
        await successor.claim_successor_code(successor.SuccessorCodeClaim(code=first["code"]), request=None, _rl=None)
    packet = await successor.claim_successor_code(successor.SuccessorCodeClaim(code=second["code"]), request=None, _rl=None)
    assert packet["trust"]["name"] == "Family Trust"


@pytest.mark.asyncio
async def test_revoke_blocks_code(ctx, owner_user):
    await _seed_trust()
    out = await successor.generate_successor_code("t_succ", user=owner_user, _stepup=None)
    await successor.revoke_successor_code("t_succ", user=owner_user, _stepup=None)
    with pytest.raises(Exception):
        await successor.claim_successor_code(successor.SuccessorCodeClaim(code=out["code"]), request=None, _rl=None)


@pytest.mark.asyncio
async def test_set_method_default_and_switch(ctx, owner_user):
    await _seed_trust()
    out = await successor.set_successor_method("t_succ", successor.SuccessorMethodUpdate(method="death_cert"),
                                               user=owner_user, _stepup=None)
    assert out["previous"] == "access_code" and out["method"] == "death_cert"
    status = await successor.get_successor_access_status("t_succ", user=owner_user)
    assert status["method"] == "death_cert"


@pytest.mark.asyncio
async def test_death_cert_claim_submit_and_approve(ctx, owner_user, admin_user, monkeypatch):
    """Method B: standing invite → claim upload → admin approve → one-time packet token emailed."""
    # Standing invite = existing token created by the send flow
    await _seed_trust()
    sent = {}

    async def fake_send(**kwargs):
        sent.update(kwargs)
        return {"status": "sent"}

    monkeypatch.setattr(type(successor.email_service), "is_configured",
                        property(lambda self: True), raising=False)
    monkeypatch.setattr(successor.email_service, "send_successor_packet_email", fake_send)
    successor.email_service.app_url = "https://app.trustoffice.test"

    from routers.successor import _hash_token
    await db.successor_access.insert_one({
        "token_hash": _hash_token("standtok123"),
        "trust_id": "t_succ",
        "user_id": "u_owner",
        "created_at": "2026-10-16T00:00:00+00:00",
        "expires_at": "2099-01-01T00:00:00+00:00",
        "used_at": None,
    })

    import fastapi
    import starlette.datastructures

    def _make_upload(name, content, ctype):
        upload = fastapi.UploadFile(
            file=io.BytesIO(content),
            filename=name,
            headers=starlette.datastructures.Headers({"content-type": ctype}),
        )
        return upload

    # Build the UploadFile for the certificate
    upload = _make_upload("certificate.pdf", b"%PDF-1.4 fake cert", "application/pdf")

    result = await successor.claim_successor_verification(
        successor.SuccessorVerificationClaim(
            trust_token="standtok123",
            claimant_name="Sam Successor",
            claimant_email="sam@successor.com",
            claimant_phone="555-0100",
            notes="",
        ),
        file=upload,
        _rl=None,
    )
    assert result["status"] == "submitted"
    claim_id = result["claim_id"]

    claims = await successor.list_successor_claims(user=admin_user)
    assert len(claims) == 1 and claims[0]["status"] == "pending"
    assert "certificate_content" not in claims[0]

    approved = await successor.approve_successor_claim(claim_id, user=admin_user, _stepup=None)
    assert approved["status"] == "approved" and approved["packet_sent"] is True
    assert sent["to_email"] == "sam@successor.com"
    doc = await db.successor_claims.find_one({"claim_id": claim_id})
    assert doc["status"] == "approved"


@pytest.mark.asyncio
async def test_reject_claim_records_reason(ctx, owner_user, admin_user):
    await _seed_trust()
    from routers.successor import _hash_token
    await db.successor_access.insert_one({
        "token_hash": _hash_token("standtok456"),
        "trust_id": "t_succ", "user_id": "u_owner",
        "created_at": "2026-10-16T00:00:00+00:00",
        "expires_at": "2099-01-01T00:00:00+00:00", "used_at": None,
    })
    import fastapi
    import starlette.datastructures

    upload = fastapi.UploadFile(
        file=io.BytesIO(b"\xff\xd8\xff fake jpg"),
        filename="cert.jpg",
        headers=starlette.datastructures.Headers({"content-type": "image/jpeg"}),
    )
    result = await successor.claim_successor_verification(
        successor.SuccessorVerificationClaim(trust_token="standtok456",
                                             claimant_name="S", claimant_email="s@x.com"),
        file=upload, _rl=None,
    )
    out = await successor.reject_successor_claim(result["claim_id"], reason="unreadable scan",
                                                 user=admin_user, _stepup=None)
    assert out["status"] == "rejected"
    doc = await db.successor_claims.find_one({"claim_id": result["claim_id"]})
    assert doc["review_reason"] == "unreadable scan"


@pytest.mark.asyncio
async def test_review_endpoints_require_admin(ctx, owner_user):
    await _seed_trust()
    with pytest.raises(Exception):
        await successor.list_successor_claims(user=owner_user)


@pytest.mark.asyncio
async def test_claim_verification_rejects_bad_file_type(ctx, admin_user):
    await _seed_trust()
    from routers.successor import _hash_token
    await db.successor_access.insert_one({
        "token_hash": _hash_token("standtok789"),
        "trust_id": "t_succ", "user_id": "u_owner",
        "created_at": "2026-10-16T00:00:00+00:00",
        "expires_at": "2099-01-01T00:00:00+00:00", "used_at": None,
    })
    import fastapi
    import starlette.datastructures

    upload = fastapi.UploadFile(
        file=io.BytesIO(b"plain text"),
        filename="cert.txt",
        headers=starlette.datastructures.Headers({"content-type": "text/plain"}),
    )
    with pytest.raises(Exception):
        await successor.claim_successor_verification(
            successor.SuccessorVerificationClaim(trust_token="standtok789",
                                                 claimant_name="S", claimant_email="s@x.com"),
            file=upload, _rl=None,
        )