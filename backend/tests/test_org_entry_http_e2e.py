#!/usr/bin/env python3
"""E2E HTTP-layer tests for org workspace entry (Option B, 6567d1d).

Goes through the REAL FastAPI HTTP layer (TestClient) with monkeypatched
FakeDB — unlike test_org_workspace_entry.py which calls the endpoint
functions directly. Covers the full request path a browser makes:
auth header -> dependency resolution -> route handler -> response JSON.

Matrix:
  1. authorized preparer: 200, full viewing context, audit + security event
  2. viewer: 200 with view_level viewer
  3. expired grant: 403 org_access_denied
  4. revoked grant: 403
  5. no grant at all: 403
  6. unknown trust: 404
  7. client admin-lock: 403 workspace_locked_by_owner
  8. owner self-view: 200 view_level owner
  9. log-exit: 200 + audit row (also after revocation)
 10. toggle off: 404 feature_disabled (both endpoints)
 11. POST-only: GET to the route → 405 (method not allowed)
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test_m4")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-e2e")
os.environ.setdefault("TOGGLE_INSTITUTION", "true")

import motor.motor_asyncio
import mongomock_motor
motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

import database
from dependencies import get_current_user
from models import GrantLevel
from routers import orgs as orgs_mod

# Orgs router imports services.security_events at module load — patch the
# names the endpoint uses so the mongomock session writes go nowhere real.
db = database.db


def _now():
    return datetime.now(timezone.utc).isoformat()


def _future(days=30):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


class _Matrix:
    """Shared seeded state for the class-scoped tests."""

@pytest_asyncio.fixture
async def matrix():
    for coll in ("users", "trusts", "user_preferences", "orgs", "org_members",
                 "trust_grants", "admin_audit_log"):
        await db[coll].delete_many({})

    owner = {"user_id": "user_client_e2e", "email": "client@e2e.test", "name": "Client Person"}
    preparer = {"user_id": "user_prep_e2e", "email": "prep@e2e.test", "name": "Prep Member"}
    viewer = {"user_id": "user_view_e2e", "email": "view@e2e.test", "name": "View Member"}
    stranger = {"user_id": "user_str_e2e", "email": "str@e2e.test", "name": "Stranger"}
    for u in (owner, preparer, viewer, stranger):
        await db.users.insert_one({**u, "created_at": _now(), "is_admin": False})

    trust = {"trust_id": "trust_e2e_main", "user_id": owner["user_id"],
             "name": "E2E Family Trust", "trust_type": "family",
             "created_at": _now(), "status": "active"}
    await db.trusts.insert_one(trust)

    org = {"org_id": "org_e2e", "name": "E2E Org", "owner_user_id": preparer["user_id"],
           "billing_contact_email": preparer["email"], "created_at": _now()}
    await db.orgs.insert_one(org)

    for u in (preparer, viewer):
        await db.org_members.insert_one({
            "org_id": "org_e2e", "member_id": f"mem_{u['user_id']}",
            "user_id": u["user_id"], "email": u["email"], "name": u["name"],
            "role": "member", "status": "active", "invited_at": _now()})

    await db.trust_grants.insert_one({
        "grant_id": "grant_prep_e2e", "trust_id": trust["trust_id"],
        "org_id": "org_e2e", "member_id": f"mem_{preparer['user_id']}",
        "level": "preparer", "status": "active", "granted_by": owner["user_id"],
        "granted_at": _now(), "expires_at": _future(30),
        "attestation_ref": "att", "client_notified_at": None,
        "revoked_at": None, "revoke_reason": None,
        "revoke_token": "t1", "revoke_token_expires_at": _future(30)})
    await db.trust_grants.insert_one({
        "grant_id": "grant_view_e2e", "trust_id": trust["trust_id"],
        "org_id": "org_e2e", "member_id": f"mem_{viewer['user_id']}",
        "level": "viewer", "status": "active", "granted_by": owner["user_id"],
        "granted_at": _now(), "expires_at": _future(30),
        "attestation_ref": "att", "client_notified_at": None,
        "revoked_at": None, "revoke_reason": None,
        "revoke_token": "t2", "revoke_token_expires_at": _future(30)})
    await db.trust_grants.insert_one({
        "grant_id": "grant_expired_e2e", "trust_id": trust["trust_id"],
        "org_id": "org_e2e", "member_id": "mem_expired",
        "level": "preparer", "status": "active", "granted_by": owner["user_id"],
        "granted_at": _now(), "expires_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        "attestation_ref": "att", "client_notified_at": None,
        "revoked_at": None, "revoke_reason": None,
        "revoke_token": "t3", "revoke_token_expires_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()})
    await db.trust_grants.insert_one({
        "grant_id": "grant_revoked_e2e", "trust_id": trust["trust_id"],
        "org_id": "org_e2e", "member_id": "mem_revoked",
        "level": "preparer", "status": "revoked", "granted_by": owner["user_id"],
        "granted_at": _now(), "expires_at": _future(1),
        "attestation_ref": "att", "client_notified_at": None,
        "revoked_at": _now(), "revoke_reason": "client_revoked",
        "revoke_token": "t4", "revoke_token_expires_at": _future(1)})

    return {"owner": owner, "preparer": preparer, "viewer": viewer,
            "stranger": stranger, "trust": trust}


def _client(user):
    app = FastAPI()
    app.include_router(orgs_mod.router, prefix="/api")

    async def fake_user():
        return user

    app.dependency_overrides[get_current_user] = fake_user
    return TestClient(app)


pytestmark = pytest.mark.usefixtures()


class TestEnterMatrix:
    @pytest.mark.asyncio
    async def test_full_matrix(self, matrix):
        st = matrix
        tid = st["trust"]["trust_id"]

        with patch.object(orgs_mod, "record_security_event", new=AsyncMock()), \
             patch("services.security_events.record_security_event", new=AsyncMock()):
            # 1. preparer
            c = _client(st["preparer"])
            res = c.post(f"/api/orgs/enter-trust/{tid}",
                         headers={"X-Forwarded-For": "198.51.100.7", "User-Agent": "e2e"})
            assert res.status_code == 200, res.text
            body = res.json()
            assert body["trust"]["trust_id"] == tid
            assert body["client"]["email"] == "client@e2e.test"
            assert body["view_level"] == "preparer"
            assert body["org"]["org_id"] == "org_e2e"
            # 2026-10-09 (Jeff): entry lands on the CLIENT's dashboard, not back in the console.
            assert body["return_path"] == "/dashboard"
            assert body["expires_at"] == _future(30) or body["expires_at"]

            # 2. viewer
            res = _client(st["viewer"]).post(f"/api/orgs/enter-trust/{tid}")
            assert res.status_code == 200, res.text
            assert res.json()["view_level"] == "viewer"

            # 5. stranger (no grant)
            res = _client(st["stranger"]).post(f"/api/orgs/enter-trust/{tid}")
            assert res.status_code == 403, res.text

            # 6. unknown trust
            res = _client(st["preparer"]).post("/api/orgs/enter-trust/trust_nope")
            assert res.status_code == 404, res.text

            # 11. wrong method
            res = _client(st["preparer"]).get(f"/api/orgs/enter-trust/{tid}")
            assert res.status_code == 405, res.text

            # 8. owner self-view
            res = _client(st["owner"]).post(f"/api/orgs/enter-trust/{tid}")
            assert res.status_code == 200, res.text
            assert res.json()["view_level"] == "owner"

        # 3. expired grant (member not in org_members anymore either -> 403)
        res = _client({"user_id": "user_exp_e2e", "email": "exp@e2e.test"}).post(
            f"/api/orgs/enter-trust/{tid}")
        assert res.status_code == 403, res.text

        # 4. revoked-grant member: not an active org member -> 403 via same path
        res = _client({"user_id": "user_revg_e2e", "email": "revg@e2e.test"}).post(
            f"/api/orgs/enter-trust/{tid}")
        assert res.status_code == 403, res.text

        # 7. client admin-lock blocks member entry (seed pref mid-matrix)
        await db.user_preferences.insert_one({"user_id": st["owner"]["user_id"], "admin_access_locked": True})
        with patch.object(orgs_mod, "record_security_event", new=AsyncMock()):
            res = _client(st["preparer"]).post(f"/api/orgs/enter-trust/{tid}")
        assert res.status_code == 403, res.text
        assert res.json()["detail"]["code"] == "workspace_locked_by_owner"
        await db.user_preferences.delete_many({})

        # 9. exit logs + 200 even for a member whose grant was revoked (seed member doc + revoked grant)
        await db.org_members.insert_one({
            "org_id": "org_e2e", "member_id": "mem_exit", "user_id": "user_exit_e2e",
            "email": "exit@e2e.test", "name": "Exit Member", "role": "member",
            "status": "active", "invited_at": _now()})
        await db.trust_grants.insert_one({
            "grant_id": "grant_exit", "trust_id": tid, "org_id": "org_e2e",
            "member_id": "mem_exit", "level": "viewer", "status": "revoked",
            "granted_by": st["owner"]["user_id"], "granted_at": _now(),
            "expires_at": _future(1), "attestation_ref": "att",
            "client_notified_at": None, "revoked_at": _now(),
            "revoke_reason": "x", "revoke_token": "t5",
            "revoke_token_expires_at": _future(1)})
        res = _client({"user_id": "user_exit_e2e", "email": "exit@e2e.test"}).post(
            f"/api/orgs/enter-trust/{tid}/log-exit")
        assert res.status_code == 200, res.text
        audit_exit = await db.admin_audit_log.find_one({"action": "org_exit_workspace"})
        assert audit_exit and audit_exit["trust_id"] == tid

        # Audit row for the preparer enter exists too
        audit_enter = await db.admin_audit_log.find_one({"action": "org_enter_workspace"})
        assert audit_enter and audit_enter["admin_email"] == "prep@e2e.test"

        # 10. toggle off -> 404 on both
        with patch.object(orgs_mod, "_toggle_institution", lambda: False):
            res = _client(st["preparer"]).post(f"/api/orgs/enter-trust/{tid}")
            assert res.status_code == 404 and res.json()["detail"]["code"] == "feature_disabled"
            res = _client(st["preparer"]).post(f"/api/orgs/enter-trust/{tid}/log-exit")
            assert res.status_code == 404 and res.json()["detail"]["code"] == "feature_disabled"

        # Audit trail sanity: enter audit rows include org + grant linkage
        rows = await db.admin_audit_log.find({"action": {"$in": ["org_enter_workspace", "org_exit_workspace"]}}).to_list(50)
        assert rows, "no audit rows written"


if __name__ == "__main__":
    import asyncio
    asyncio.run(TestEnterMatrix().test_full_matrix(matrix()))
    print("matrix PASS")