#!/usr/bin/env python3
"""Org-console demo-readiness guards (2026-10-02 regression suite).

Covers the four backend fixes from the 2026-10-01 org-console QA:
  1. BUG-14 (MED): owner could suspend/demote their OWN row via PATCH
     /orgs/{org_id}/members/{member_id} — owner-only routes then 403 and the
     console is locked until a DB restore. Now: 409 owner_row_immutable.
  2. LOW-c: duplicate invites for the same email inserted a second 'invited'
     row (and the login accept path blanket-reactivated any invited row for
     the caller). Now: 409 invite_already_exists while invited/active exists
     (suspended stays re-invitable), and accepting an invite while the email
     ALREADY holds an active row rolls back + 409 member_already_active.
  3. LOW-a: fractional-day expiry truncation — (x - now).days floors, so
     365d 9h passed the 365-day cap. Now capped with a real timedelta compare.
  4. Invite role was a dead control: route hardcoded 'member' while the UI
     sent the selected role. Now honored (member|admin, else 422 invalid_role).

Direct-call style (functions invoked with user=..., no live API), mongomock
backend, self-contained env so it runs green in isolation or full-suite.
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test_org_guards")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-org-guards")
os.environ.setdefault("TOGGLE_INSTITUTION", "true")

import motor.motor_asyncio
import mongomock_motor
motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException

import database
from routers import orgs as orgs_mod

db = database.db


def _now():
    return datetime.now(timezone.utc).isoformat()


@pytest_asyncio.fixture
async def org():
    for coll in ("users", "orgs", "org_members"):
        await db[coll].delete_many({})

    owner_user_id = "u_owner"
    org_id = "org_guards"
    await db.orgs.insert_one({
        "org_id": org_id, "name": "Guard Org",
        "owner_user_id": owner_user_id, "created_at": _now()})
    member_id = "mem_owner_row"
    await db.org_members.insert_one({
        "member_id": member_id, "org_id": org_id, "user_id": owner_user_id,
        "email": "owner@t.test", "name": "Owner", "role": "owner",
        "status": "active", "invited_at": _now(), "invited_by": owner_user_id,
        "joined_at": _now()})
    return {"org_id": org_id, "owner_user_id": owner_user_id,
            "member_id": member_id}


async def _seed_member(org_id, uid, email, member_id, role="member",
                       status="active"):
    await db.org_members.insert_one({
        "member_id": member_id, "org_id": org_id, "user_id": uid,
        "email": email, "name": uid, "role": role, "status": status,
        "invited_at": _now(), "invited_by": "u_owner"})
    return member_id


class TestOwnerRowGuard:
    @pytest.mark.asyncio
    async def test_owner_cannot_suspend_own_row(self, org):
        with pytest.raises(HTTPException) as exc:
            await orgs_mod.update_org_member(
                org["org_id"], org["member_id"], {"status": "suspended"},
                user={"user_id": org["owner_user_id"], "email": "owner@t.test"})
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "owner_row_immutable"
        # row untouched — owner still owner + active
        row = await db.org_members.find_one(
            {"member_id": org["member_id"]}, {"_id": 0})
        assert row["role"] == "owner" and row["status"] == "active"

    @pytest.mark.asyncio
    async def test_owner_cannot_demote_own_role(self, org):
        with pytest.raises(HTTPException) as exc:
            await orgs_mod.update_org_member(
                org["org_id"], org["member_id"], {"role": "member"},
                user={"user_id": org["owner_user_id"], "email": "owner@t.test"})
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_owner_still_manages_member_rows(self, org):
        """Guard is narrow: normal member rows stay manageable."""
        mid = await _seed_member(
            org["org_id"], "u_member", "m1@t.test", "mem_m1", role="member")
        out = await orgs_mod.update_org_member(
            org["org_id"], mid, {"role": "admin"},
            user={"user_id": org["owner_user_id"], "email": "owner@t.test"})
        assert out["updated"] == {"role": "admin"}
        row = await db.org_members.find_one({"member_id": mid}, {"_id": 0})
        assert row["role"] == "admin"


class TestDuplicateInviteGuard:
    @pytest.mark.asyncio
    async def test_second_invite_while_invited_409(self, org):
        await _seed_member(org["org_id"], None, "new@t.test", "mem_inv1",
                           status="invited")
        with pytest.raises(HTTPException) as exc:
            await orgs_mod.invite_org_member(
                org["org_id"], {"email": "new@t.test"},
                user={"user_id": org["owner_user_id"], "email": "owner@t.test"})
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "invite_already_exists"
        # still exactly one row for that email
        n = await db.org_members.count_documents(
            {"org_id": org["org_id"], "email": "new@t.test"})
        assert n == 1

    @pytest.mark.asyncio
    async def test_invite_case_insensitive(self, org):
        await orgs_mod.invite_org_member(
            org["org_id"], {"email": "Case@t.test"},
            user={"user_id": org["owner_user_id"], "email": "owner@t.test"})
        with pytest.raises(HTTPException) as exc:
            await orgs_mod.invite_org_member(
                org["org_id"], {"email": "case@T.test"},
                user={"user_id": org["owner_user_id"], "email": "owner@t.test"})
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_suspended_row_stays_re_invitable(self, org):
        await _seed_member(org["org_id"], "u_old", "susp@t.test", "mem_susp",
                           status="suspended")
        out = await orgs_mod.invite_org_member(
            org["org_id"], {"email": "susp@t.test"},
            user={"user_id": org["owner_user_id"], "email": "owner@t.test"})
        assert out["member_id"] != "mem_susp"

    @pytest.mark.asyncio
    async def test_accept_with_existing_active_row_conflicts(self, org):
        """Legacy dup (pre-guard-era data): an active row AND a fresh invite
        for the same email. Accepting must NOT produce two live rows — roll
        back + 409. (The invite route itself now refuses to create this
        state, so the invite row is seeded directly to simulate old data.)"""
        # active row predates the invite (pre-guard-era duplicate)
        await _seed_member(org["org_id"], "u_dupe", "dupe@t.test",
                           "mem_active_row")
        token = "legacy-token-dupe-accept"
        await db.org_members.insert_one({
            "member_id": "mem_dupe_fresh", "org_id": org["org_id"],
            "user_id": None, "email": "dupe@t.test", "name": "dupe",
            "role": "member", "status": "invited", "invited_at": _now(),
            "invited_by": org["owner_user_id"],
            "invite_token": token,
            "invite_expires_at": (datetime.now(timezone.utc)
                                  + timedelta(hours=72)).isoformat()})
        with pytest.raises(HTTPException) as exc:
            await orgs_mod.accept_org_invite(
                token,
                user={"user_id": "u_dupe", "email": "dupe@t.test"})
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "member_already_active"
        # fresh row rolled back to invited / unclaimed
        rolled = await db.org_members.find_one(
            {"member_id": "mem_dupe_fresh"}, {"_id": 0})
        assert rolled["status"] == "invited" and rolled["user_id"] is None
        # original active row untouched
        orig = await db.org_members.find_one(
            {"member_id": "mem_active_row"}, {"_id": 0})
        assert orig["status"] == "active"

    @pytest.mark.asyncio
    async def test_invite_blocked_when_active_row_exists(self, org):
        """The invite route itself now refuses when the email already holds
        an ACTIVE row (this state can no longer be created through the API)."""
        await _seed_member(org["org_id"], "u_live", "live@t.test",
                           "mem_live", status="active")
        with pytest.raises(HTTPException) as exc:
            await orgs_mod.invite_org_member(
                org["org_id"], {"email": "live@t.test"},
                user={"user_id": org["owner_user_id"], "email": "owner@t.test"})
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "invite_already_exists"
        assert "already a member" in exc.value.detail["message"]


class TestInviteRoleHonor:
    @pytest.mark.asyncio
    async def test_invite_role_admin_persists(self, org):
        out = await orgs_mod.invite_org_member(
            org["org_id"], {"email": "admin1@t.test", "role": "admin"},
            user={"user_id": org["owner_user_id"], "email": "owner@t.test"})
        row = await db.org_members.find_one(
            {"member_id": out["member_id"]}, {"_id": 0})
        assert row["role"] == "admin"

    @pytest.mark.asyncio
    async def test_invite_role_invalid_422(self, org):
        with pytest.raises(HTTPException) as exc:
            await orgs_mod.invite_org_member(
                org["org_id"], {"email": "boss@t.test", "role": "owner"},
                user={"user_id": org["owner_user_id"], "email": "owner@t.test"})
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "invalid_role"

    @pytest.mark.asyncio
    async def test_invite_default_role_member(self, org):
        out = await orgs_mod.invite_org_member(
            org["org_id"], {"email": "plain@t.test"},
            user={"user_id": org["owner_user_id"], "email": "owner@t.test"})
        row = await db.org_members.find_one(
            {"member_id": out["member_id"]}, {"_id": 0})
        assert row["role"] == "member"


async def _seed_grant_fixtures(expires_at):
    """Minimal owner/trust/org fixtures for grant_trust_access expiry checks."""
    for coll in ("users", "trusts", "orgs", "org_members", "trust_grants"):
        await db[coll].delete_many({})
    owner = {"user_id": "u_owner2", "email": "o2@t.test", "name": "Owner2"}
    await db.users.insert_one({**owner, "created_at": _now(), "is_admin": False})
    await db.trusts.insert_one({
        "trust_id": "t_exp", "user_id": owner["user_id"], "name": "Expiry",
        "trust_type": "family", "created_at": _now(), "status": "active"})
    await db.orgs.insert_one({
        "org_id": "org_exp", "name": "Exp Org",
        "owner_user_id": owner["user_id"], "created_at": _now()})
    await db.org_members.insert_one({
        "member_id": "mem_exp", "org_id": "org_exp", "user_id": "u_member2",
        "email": "m2@t.test", "name": "m2", "role": "member",
        "status": "active", "invited_at": _now(), "invited_by": owner["user_id"]})
    from models import TrustGrantCreate, GrantLevel
    body = TrustGrantCreate(
        org_id="org_exp", member_id="mem_exp", level=GrantLevel.viewer,
        expires_at=expires_at, attested_delegation=True,
        attestation_ref="exp-test")
    return owner, body


class TestGrantExpiryFractionalDay:
    @pytest.mark.asyncio
    async def test_365d_9h_rejected(self):
        exp = (datetime.now(timezone.utc) + timedelta(days=365, hours=9)).isoformat()
        owner, body = await _seed_grant_fixtures(exp)
        with pytest.raises(HTTPException) as exc:
            await orgs_mod.grant_trust_access(
                "t_exp", body, user={**owner, "name": "Owner2"})
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "expiry_exceeds_365_days"

    @pytest.mark.asyncio
    async def test_exact_365d_accepted(self):
        exp = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
        owner, body = await _seed_grant_fixtures(exp)
        grant = await orgs_mod.grant_trust_access(
            "t_exp", body, user={**owner, "name": "Owner2"})
        assert grant.status == "active"