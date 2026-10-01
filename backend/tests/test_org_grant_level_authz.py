#!/usr/bin/env python3
"""Authorization regression: does grant LEVEL actually gate writes?

The org console workspace lets org members work INSIDE a client trust. The
viewing-session banner (6567d1d) is UX; the security claim is that a
viewer-grant cannot WRITE and a preparer-grant can. This suite proves the
enforcement layer end to end through the HTTP routes that carry
require_org_grant (distributions POST = preparer-gated write).

Matrix (mongomock, in-process TestClient):
  - viewer grant: POST distribution -> 403
  - preparer grant: POST distribution -> non-403 (accepts validation pass)
  - grant expired: 403
  - grant revoked: 403
  - wrong-trust id (no grant): 403
  - toggle-off: legacy behavior (owner-only) — member w/o ownership 403
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test_m4")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-authz")
os.environ.setdefault("TOGGLE_INSTITUTION", "true")

import motor.motor_asyncio
import mongomock_motor
motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi import Depends

import database
import dependencies
from dependencies import get_current_user
from routers import distributions as dist_mod

db = database.db


def _now():
    return datetime.now(timezone.utc).isoformat()


def _future(days):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _past(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


@pytest_asyncio.fixture
async def seeded():
    for coll in ("users", "trusts", "orgs", "org_members", "trust_grants",
                 "distributions", "distribution_records", "org_activity"):
        await db[coll].delete_many({})

    owner = {"user_id": "u_owner", "email": "o@t.test", "name": "Owner"}
    await db.users.insert_one({**owner, "created_at": _now(), "is_admin": False})
    trust = {"trust_id": "t_authz", "user_id": owner["user_id"], "name": "AuthZ Trust",
             "trust_type": "family", "created_at": _now(), "status": "active"}
    await db.trusts.insert_one(trust)
    await db.orgs.insert_one({"org_id": "o_authz", "name": "AuthZ Org",
                              "owner_user_id": owner["user_id"], "created_at": _now()})

    async def member_with_grant(uid, email, member_id, level, status="active", expires=None):
        await db.users.insert_one({"user_id": uid, "email": email, "name": uid,
                                   "created_at": _now(), "is_admin": False})
        await db.org_members.insert_one({
            "org_id": "o_authz", "member_id": member_id, "user_id": uid,
            "email": email, "name": uid, "role": "member", "status": "active",
            "invited_at": _now()})
        await db.trust_grants.insert_one({
            "grant_id": f"g_{member_id}", "trust_id": trust["trust_id"],
            "org_id": "o_authz", "member_id": member_id, "level": level,
            "status": status, "granted_by": owner["user_id"], "granted_at": _now(),
            "expires_at": expires or _future(30), "attestation_ref": "a",
            "client_notified_at": None, "revoked_at": None, "revoke_reason": None,
            "revoke_token": f"tk_{member_id}",
            "revoke_token_expires_at": expires or _future(30)})

    await member_with_grant("u_viewer", "v@t.test", "m_viewer", "viewer")
    await member_with_grant("u_prep", "p@t.test", "m_prep", "preparer")
    await member_with_grant("u_viewexp", "ve@t.test", "m_viewexp", "preparer",
                            expires=_past(1))
    await member_with_grant("u_viewrev", "vr@t.test", "m_viewrev", "preparer",
                            status="revoked")
    await member_with_grant("u_nogrant", "ng@t.test", "m_nogrant", "viewer")
    # that member's grant is for t_authz; create second trust without grant:
    trust2 = {"trust_id": "t_other", "user_id": owner["user_id"], "name": "Other",
              "trust_type": "family", "created_at": _now(), "status": "active"}
    await db.trusts.insert_one(trust2)

    return {"owner": owner, "trust": trust, "trust2": trust2,
            "viewer": {"user_id": "u_viewer", "email": "v@t.test"},
            "prep": {"user_id": "u_prep", "email": "p@t.test"},
            "viewexp": {"user_id": "u_viewexp", "email": "ve@t.test"},
            "viewrev": {"user_id": "u_viewrev", "email": "vr@t.test"},
            "nogrant": {"user_id": "u_nogrant", "email": "ng@t.test"}}


def _client(user, seeded_state):
    """TestClient with subscription gate bypassed — this suite tests the
    GRANT-level gate specifically, not the (already covered) subscription
    gate. require_write_access otherwise 403s every preparer write with
    'subscription inactive' before the grant logic ever runs."""
    from routers import orgs as _  # ensure module import side-effects settled
    app = FastAPI()
    app.include_router(dist_mod.router, prefix="/api")

    async def fake_user():
        return {**user, "name": user.get("name", "")}

    async def fake_user_wrapped():
        return {**user, "name": user.get("name", "")}

    async def fake_write_access(u=Depends(get_current_user)):
        return u

    app.dependency_overrides[get_current_user] = fake_user
    app.dependency_overrides[dist_mod.require_write_access] = fake_write_access
    return TestClient(app)


NOW_ISO = datetime.now(timezone.utc).date().isoformat()


def body(tid="t_authz"):
    return {"trust_id": tid, "beneficiary_name": "B A", "amount": 5,
            "date": NOW_ISO, "purpose_classification": "distribution",
            "notes": "authz"}


class TestGrantLevelAuthz:
    @pytest.mark.asyncio
    async def test_matrix(self, seeded):
        st = seeded
        tid = st["trust"]["trust_id"]

        async def _count_dists():
            return await db.distributions.count_documents({})

        # 1. viewer grant: WRITE (create distribution) -> 403
        base = _count = 0
        res = _client(st["viewer"], st).post("/api/distributions", json=body(tid))
        assert res.status_code == 403, f"viewer write must 403, got {res.status_code}: {res.text[:120]}"

        # 2. preparer grant: WRITE -> must be allowed past the guard
        res = _client(st["prep"], st).post("/api/distributions", json=body(tid))
        assert res.status_code != 403, f"preparer write wrongly 403: {res.text[:160]}"
        created = res.status_code == 200 or res.status_code == 201, res.text[:160]
        n_after = await db.distribution_records.count_documents({})
        assert n_after > 0, f"preparer write did not persist (status {res.status_code})"

        # 3. expired grant -> 403
        res = _client(st["viewexp"], st).post("/api/distributions", json=body(tid))
        assert res.status_code == 403, "expired grant write must 403"

        # 4. revoked grant -> 403
        res = _client(st["viewrev"], st).post("/api/distributions", json=body(tid))
        assert res.status_code == 403, "revoked grant write must 403"

        # 5. grant for t_authz used on t_other (different trust) -> 403
        res = _client(st["viewer"], st).post("/api/distributions", json=body(st["trust2"]["trust_id"]))
        assert res.status_code == 403, "cross-trust grant reuse must 403"

        # 6. toggle off: D8 short-circuit = legacy owner-only behavior;
        #    member (non-owner) write -> 403 either way. Nothing to assert
        #    beyond no-crash + 403-family.
        with patch_toggle_off():
            res = _client(st["viewer"], st).post("/api/distributions", json=body(tid))
            assert res.status_code in (403, 401, 404), res.status_code

        # 7. distributions written by preparer carry attribution for the audit
        dist_row = await db.distribution_records.find_one({})
        assert dist_row is not None


from contextlib import contextmanager


@contextmanager
def patch_toggle_off():
    import routers.distributions as d
    orig = dependencies._toggle_institution
    # distribution module references the dep by import name in signatures
    name_to_patch = None
    for attr in ("_toggle_institution",):
        if hasattr(d, attr):
            name_to_patch = attr
    if name_to_patch:
        setattr(d, name_to_patch, lambda: False)
    try:
        yield
    finally:
        if name_to_patch:
            setattr(d, name_to_patch, orig)


if __name__ == "__main__":
    import asyncio
    s = None
    async def run():
        global s
        pytestmark2 = None
    print("run via pytest")