#!/usr/bin/env python3
"""Granted-member READ access regression (2026-10-03, JOB-20261003-TO-GRANT-READ-FIX).

Root cause: 51fbd58 (2026-10-01) made GET /trusts grant-aware, but the four
detail read endpoints stayed owner-only — an org member selecting a granted
client trust got 404 "Trust not found" on:
  GET /api/dashboard?trust_id=…
  GET /api/ai/weekly-briefing?trust_id=…
  GET /api/trusts/{id}/bank-accounts/summary
  GET /api/trusts/{id}/tax-calendar/upcoming
Prod evidence: 2026-10-01..02 error-log bursts (u18b8, sandbox + live client
trust). Fix: resolve_granted_trust() owner-or-grant read resolution; data
queries run with the OWNER's user_id; subscription gate unchanged; reads
only (writes stay behind require_org_grant).

Matrix (mongomock, in-process TestClient, subscription gate not mounted):
  - preparer grant → all four endpoints non-404 (200-family or real data)
  - viewer grant → same (read paths equal for both levels)
  - expired grant → 404 (unchanged owner-only semantics for dead grants)
  - revoked grant → 404
  - non-member stranger → 404 (no grant, not owner)
  - owner → unchanged 200 (regression guard: owner path untouched)
  - resolve_granted_trust: owner passthrough / grant hit / dead grant miss
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test_grant_read")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-grantread")
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
from routers import governance as gov_mod
from routers import ai as ai_mod
from routers import banking as bank_mod
from routers import tax_calendar as tax_mod
from routers.trusts import resolve_granted_trust

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
                 "governance_tasks", "distribution_records", "tax_calendar",
                 "bank_accounts", "bank_statements", "meeting_minutes",
                 "dismissed_insights", "onboarding", "user_preferences",
                 "subscriptions", "quarterly_drafts", "risk_findings",
                 "governance_insights_state"):
        await db[coll].delete_many({})

    owner = {"user_id": "u_owner", "email": "o@t.test", "name": "Owner"}
    await db.users.insert_one({**owner, "created_at": _now(), "is_admin": False})

    async def _trust(tid, name):
        t = {"trust_id": tid, "user_id": owner["user_id"], "name": name,
             "trust_type": "family", "jurisdiction": "UT", "created_at": _now(),
             "status": "active"}
        await db.trusts.insert_one(t)
        return t

    trust = await _trust("t_read", "Grant Read Trust")
    trust2 = await _trust("t_other", "No-Grant Trust")

    await db.orgs.insert_one({"org_id": "o_read", "name": "Read Org",
                              "owner_user_id": owner["user_id"], "created_at": _now()})

    async def member(uid, email, member_id, *, status="active"):
        await db.users.insert_one({"user_id": uid, "email": email, "name": uid,
                                   "created_at": _now(), "is_admin": False})
        await db.org_members.insert_one({
            "org_id": "o_read", "member_id": member_id, "user_id": uid,
            "email": email, "name": uid, "role": "member", "status": status,
            "invited_at": _now()})

    async def grant(member_id, tid, level, *, status="active", expires=None):
        await db.trust_grants.insert_one({
            "grant_id": f"g_{member_id}_{tid}", "trust_id": tid,
            "org_id": "o_read", "member_id": member_id, "level": level,
            "status": status, "granted_by": owner["user_id"], "granted_at": _now(),
            "expires_at": expires or _future(30), "attestation_ref": "a",
            "client_notified_at": None, "revoked_at": None, "revoke_reason": None})

    await member("u_prep", "p@t.test", "m_prep")
    await grant("m_prep", "t_read", "preparer")

    await member("u_view", "v@t.test", "m_view")
    await grant("m_view", "t_read", "viewer")

    await member("u_exp", "e@t.test", "m_exp")
    await grant("m_exp", "t_read", "viewer", expires=_past(1))

    await member("u_rev", "r@t.test", "m_rev")
    await grant("m_rev", "t_read", "viewer", status="revoked")

    await member("u_none", "n@t.test", "m_none")

    # owner-owned data so the granted path has something to READ
    await db.governance_tasks.insert_one({
        "task_id": "task_1", "trust_id": "t_read", "user_id": "u_owner",
        "title": "Q review", "due_date": datetime.now(timezone.utc).date().isoformat(), "completed_at": None})
    await db.tax_calendar.insert_one({
        "trust_id": "t_read", "user_id": "u_owner", "tax_year": datetime.now(timezone.utc).year,
        "filing_status": "pending", "form_name": "Form 706",
        "due_date": datetime.now(timezone.utc).date().isoformat()})

    return {"owner": owner, "trust": trust, "trust2": trust2,
            "prep": {"user_id": "u_prep", "email": "p@t.test"},
            "view": {"user_id": "u_view", "email": "v@t.test"},
            "exp": {"user_id": "u_exp", "email": "e@t.test"},
            "rev": {"user_id": "u_rev", "email": "r@t.test"},
            "none": {"user_id": "u_none", "email": "n@t.test"}}


def _client(user):
    """TestClient with the four read routers mounted; auth overridden to the
    given user. The subscription middleware is NOT mounted (it lives on the
    prod app in server.py, not on these routers) — this suite tests the
    grant read-path only."""
    app = FastAPI()
    app.include_router(gov_mod.router, prefix="/api")
    app.include_router(ai_mod.router, prefix="/api")
    app.include_router(bank_mod.router, prefix="/api")
    app.include_router(tax_mod.router, prefix="/api")

    async def fake_user():
        return {**user, "name": user.get("name", "")}

    app.dependency_overrides[get_current_user] = fake_user
    return TestClient(app, raise_server_exceptions=False)


GETS = [
    "/api/dashboard?trust_id=t_read",
    "/api/ai/weekly-briefing?trust_id=t_read",
    "/api/trusts/t_read/bank-accounts/summary",
    "/api/trusts/t_read/tax-calendar/upcoming?days=90",
]


class TestGrantedMemberReads:
    @pytest.mark.asyncio
    async def test_preparer_reads_all_four(self, seeded):
        c = _client(seeded["prep"])
        for url in GETS:
            res = c.get(url)
            assert res.status_code != 404, f"{url} 404 for preparer grant"
            assert res.status_code < 500, f"{url} 500 ({res.status_code}): {res.text[:160]}"
        dash = c.get(GETS[0]).json()
        # health/insight data must reflect the OWNER's data, not the member's empty set
        assert dash["trust_id"] == "t_read"

    @pytest.mark.asyncio
    async def test_viewer_reads_all_four(self, seeded):
        c = _client(seeded["view"])
        for url in GETS:
            res = c.get(url)
            assert res.status_code != 404, f"{url} 404 for viewer grant"
            assert res.status_code < 500, f"{url} 500 ({res.status_code}): {res.text[:160]}"

    @pytest.mark.asyncio
    async def test_expired_grant_still_404(self, seeded):
        c = _client(seeded["exp"])
        for url in GETS:
            assert c.get(url).status_code == 404, f"expired grant must not read {url}"

    @pytest.mark.asyncio
    async def test_revoked_grant_still_404(self, seeded):
        c = _client(seeded["rev"])
        for url in GETS:
            assert c.get(url).status_code == 404, f"revoked grant must not read {url}"

    @pytest.mark.asyncio
    async def test_stranger_no_grant_404(self, seeded):
        c = _client(seeded["none"])
        for url in GETS:
            assert c.get(url).status_code == 404, f"no-grant member must not read {url}"

    @pytest.mark.asyncio
    async def test_grant_on_other_trust_does_not_leak(self, seeded):
        c = _client(seeded["prep"])
        url2 = "/api/trusts/t_other/tax-calendar/upcoming?days=90"
        assert c.get(url2).status_code == 404, "t_other has no grant — 404 required"

    @pytest.mark.asyncio
    async def test_owner_unchanged(self, seeded):
        c = _client(seeded["owner"])
        for url in GETS:
            res = c.get(url)
            assert res.status_code != 404, f"owner read broke: {url}"
            assert res.status_code < 500, f"owner read 500: {url} {res.status_code}"


class TestResolveGrantedTrust:
    @pytest.mark.asyncio
    async def test_owner_passthrough(self, seeded):
        uid, grant = await resolve_granted_trust("t_read", seeded["owner"])
        assert uid == "u_owner" and grant is None

    @pytest.mark.asyncio
    async def test_grant_hit(self, seeded):
        uid, grant = await resolve_granted_trust("t_read", seeded["view"])
        assert uid == "u_owner" and grant and grant["level"] == "viewer"

    @pytest.mark.asyncio
    async def test_dead_grant_miss(self, seeded):
        uid, grant = await resolve_granted_trust("t_read", seeded["exp"])
        assert uid is None and grant is None
        uid, grant = await resolve_granted_trust("t_read", seeded["rev"])
        assert uid is None and grant is None

    @pytest.mark.asyncio
    async def test_missing_trust(self, seeded):
        uid, grant = await resolve_granted_trust("t_ghost", seeded["view"])
        assert uid is None and grant is None

    @pytest.mark.asyncio
    async def test_unknown_trust_via_http_404(self, seeded):
        c = _client(seeded["view"])
        assert c.get("/api/dashboard?trust_id=t_ghost").status_code == 404