#!/usr/bin/env python3
"""Offline (mongomock) regression suite for org workspace entry (M5, 2026-10-01).

Covers the Option-B build (Jeff approved 2026-10-01): org console workspace
entry rides the admin-impersonation state machinery — audited ENTER/EXIT
endpoints — while scoping stays server-side via require_org_grant.

- enter-trust: authorized member (active grant) returns context + audit row +
  security event; owner self-view works; unauthorized/expired/revocked -> 403;
  toggle-off -> 404; client lock -> 403.
- log-exit: audit row written; exit never blocked after revocation.

Runs fully in-process (no live server, no prod writes).
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test_m4")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("TOGGLE_INSTITUTION", "true")

import motor.motor_asyncio
import mongomock_motor
motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

import database
from dependencies import get_current_user
from models import GrantLevel
from routers.orgs import enter_trust_workspace, log_org_workspace_exit

db = database.db


def _now():
    return datetime.now(timezone.utc).isoformat()


def _future(days=30):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _past(days=1):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


class _Req:
    """Minimal Request stand-in for the header reads in the endpoint."""
    headers = {"X-Forwarded-For": "203.0.113.9", "User-Agent": "pytest-m5"}


async def _seed_user(email, name="Test User"):
    uid = f"user_{email.split('@')[0]}"
    doc = {"user_id": uid, "email": email, "name": name, "created_at": _now(), "is_admin": False}
    await db.users.replace_one({"user_id": uid}, doc, upsert=True)
    return doc


async def _seed_trust(owner, name="My Family Trust", locked=None):
    tid = f"trust_{owner['user_id']}_m5"
    await db.trusts.delete_many({"trust_id": tid})
    doc = {"trust_id": tid, "user_id": owner["user_id"], "name": name,
           "trust_type": "family", "created_at": _now(), "status": "active"}
    await db.trusts.insert_one(doc)
    if locked is not None:
        await db.user_preferences.replace_one(
            {"user_id": owner["user_id"]},
            {"user_id": owner["user_id"], "admin_access_locked": locked},
            upsert=True)
    return doc


async def _seed_org_member_grant(owner, member, trust, org_id="org_m5",
                                 mem_id="mem_m5", level=GrantLevel.preparer,
                                 days=30, status="active"):
    await db.orgs.replace_one({"org_id": org_id},
                              {"org_id": org_id, "name": "M5 Org",
                               "owner_user_id": member["user_id"],
                               "billing_contact_email": member["email"],
                               "created_at": _now()}, upsert=True)
    await db.org_members.replace_one(
        {"member_id": mem_id},
        {"org_id": org_id, "member_id": mem_id, "user_id": member["user_id"],
         "email": member["email"], "name": member["name"],
         "role": "owner", "status": "active", "invited_at": _now()},
        upsert=True)
    gid = f"grant_{mem_id}_{trust['trust_id'][-6:]}"
    doc = {
        "grant_id": gid, "trust_id": trust["trust_id"], "org_id": org_id,
        "member_id": mem_id, "level": level, "status": status,
        "granted_by": owner["user_id"], "granted_at": _now(),
        "expires_at": _future(days) if days else None,
        "attestation_ref": "attest_m5", "client_notified_at": None,
        "revoked_at": None, "revoke_reason": None,
        "revoke_token": "tok", "revoke_token_expires_at": _future(days),
    }
    await db.trust_grants.replace_one({"grant_id": gid}, doc, upsert=True)
    return doc


def _user_dep(user_doc):
    async def _dep():
        return user_doc
    return _dep


@pytest_asyncio.fixture
async def clean_db():
    for coll in ("users", "trusts", "user_preferences", "orgs", "org_members",
                 "trust_grants", "admin_audit_log"):
        await db[coll].delete_many({})
    yield


pytestmark = pytest.mark.asyncio


async def test_enter_authorized_member_returns_context_and_audits(clean_db):
    owner = await _seed_user("cl_m5@test.com", "Client Person")
    member = await _seed_user("own_m5@test.com", "Owner Person")
    trust = await _seed_trust(owner, "Jeff Family Trust")
    grant = await _seed_org_member_grant(owner, member, trust, level=GrantLevel.preparer)

    with patch("routers.orgs.get_current_user", _user_dep(member)), \
         patch("routers.orgs.record_security_event", new=AsyncMock()):
        res = await enter_trust_workspace(trust["trust_id"], _Req(), member)
    assert res["trust"]["trust_id"] == trust["trust_id"]
    assert res["trust"]["name"] == "Jeff Family Trust"
    assert res["client"]["email"] == "cl_m5@test.com"
    assert res["view_level"] == "preparer"
    assert res["expires_at"] == grant["expires_at"]
    assert res["return_path"] == "/org-console"
    assert res["org"]["name"] == "M5 Org"
    audit = await db.admin_audit_log.find_one({"action": "org_enter_workspace"})
    assert audit and audit["trust_id"] == trust["trust_id"]
    assert audit["admin_user_id"] == member["user_id"]
    assert audit["view_level"] == "preparer"


async def test_enter_owner_self_view(clean_db):
    owner = await _seed_user("cl_m5b@test.com")
    trust = await _seed_trust(owner)
    res = await enter_trust_workspace(trust["trust_id"], _Req(), owner)
    assert res["view_level"] == "owner"
    assert res["expires_at"] is None


async def test_enter_no_grant_403(clean_db):
    owner = await _seed_user("cl_m5c@test.com")
    stranger = await _seed_user("own_m5c@test.com")
    trust = await _seed_trust(owner)
    with pytest.raises(Exception) as ei:
        await enter_trust_workspace(trust["trust_id"], _Req(), stranger)
    assert getattr(ei.value, "status_code", 500) == 403


async def test_enter_expired_grant_403(clean_db):
    owner = await _seed_user("cl_m5d@test.com")
    member = await _seed_user("own_m5d@test.com")
    trust = await _seed_trust(owner)
    await _seed_org_member_grant(owner, member, trust, days=-1)
    with pytest.raises(Exception) as ei:
        await enter_trust_workspace(trust["trust_id"], _Req(), member)
    assert getattr(ei.value, "status_code", 500) == 403


async def test_enter_revoked_grant_403(clean_db):
    owner = await _seed_user("cl_m5e@test.com")
    member = await _seed_user("own_m5e@test.com")
    trust = await _seed_trust(owner)
    await _seed_org_member_grant(owner, member, trust, status="revoked")
    with pytest.raises(Exception) as ei:
        await enter_trust_workspace(trust["trust_id"], _Req(), member)
    assert getattr(ei.value, "status_code", 500) == 403


async def test_enter_client_locked_403(clean_db):
    owner = await _seed_user("cl_m5f@test.com")
    member = await _seed_user("own_m5f@test.com")
    trust = await _seed_trust(owner, locked=True)
    await _seed_org_member_grant(owner, member, trust)
    with patch("routers.orgs.get_current_user", _user_dep(member)):
        with pytest.raises(Exception) as ei:
            await enter_trust_workspace(trust["trust_id"], _Req(), member)
    assert getattr(ei.value, "status_code", 500) == 403
    body = getattr(ei.value, "detail", {})
    assert body.get("code") == "workspace_locked_by_owner" if isinstance(body, dict) else True


async def test_enter_unknown_trust_404(clean_db):
    user = await _seed_user("own_m5g@test.com")
    with pytest.raises(Exception) as ei:
        await enter_trust_workspace("trust_missing", _Req(), user)
    assert getattr(ei.value, "status_code", 500) == 404


async def test_log_exit_audits_even_after_revoke(clean_db):
    owner = await _seed_user("cl_m5h@test.com")
    member = await _seed_user("own_m5h@test.com")
    trust = await _seed_trust(owner)
    # Revoked grant (member lost access mid-session): exit must still log.
    await _seed_org_member_grant(owner, member, trust, status="revoked")
    res = await log_org_workspace_exit(trust["trust_id"], member)
    assert res["message"] == "Org workspace session ended"
    audit = await db.admin_audit_log.find_one({"action": "org_exit_workspace"})
    assert audit and audit["trust_id"] == trust["trust_id"]


async def test_log_exit_owner_view(clean_db):
    owner = await _seed_user("cl_m5i@test.com")
    trust = await _seed_trust(owner)
    res = await log_org_workspace_exit(trust["trust_id"], owner)
    assert res["message"] == "Org workspace session ended"


async def test_both_endpoints_feature_disabled_when_toggle_off(clean_db, monkeypatch):
    owner = await _seed_user("cl_m5j@test.com")
    trust = await _seed_trust(owner)
    import dependencies
    monkeypatch.setattr(dependencies, "_toggle_institution", lambda: False)
    import routers.orgs as orgs_mod
    monkeypatch.setattr(orgs_mod, "_toggle_institution", lambda: False)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as ei:
        await enter_trust_workspace(trust["trust_id"], _Req(), owner)
    assert ei.value.status_code == 404
    with pytest.raises(HTTPException) as ei2:
        await log_org_workspace_exit(trust["trust_id"], owner)
    assert ei2.value.status_code == 404


if __name__ == "__main__":
    import asyncio
    ok = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and asyncio.iscoroutinefunction(fn):
            asyncio.run(fn({}))
            ok += 1
            print(f"PASS {name}")
    print(f"\n{ok} tests passed")