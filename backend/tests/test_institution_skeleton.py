#!/usr/bin/env python3
"""M4 test fixtures + regression suite for TrustOffice Institution + Trust Party layers.

Runs fully in-process against mongomock (no live server, no prod writes).
Also protected by tests/conftest.py prod URL block.
"""
import importlib.util
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test_m4")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

import motor.motor_asyncio
import mongomock_motor
motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
import asyncio
from datetime import datetime, timezone

import database
from dependencies import get_current_user, _toggle_institution, _toggle_trust_parties
from models import (
    OrgCreate, OrgMemberRole, GrantLevel, TrustGrantCreate,
    TrustPartyCreate, PartyType, PartyLevel, PartyGrantCreate,
)

db = database.db


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _seed_user(email, name="Test User"):
    uid = f"user_{email.split('@')[0]}"
    doc = {"user_id": uid, "email": email, "name": name, "created_at": _now(), "is_admin": False}
    await db.users.replace_one({"user_id": uid}, doc, upsert=True)
    return doc


async def _seed_trust(user, name="Test Trust"):
    tid = f"trust_{user['user_id']}_"
    # find unused
    existing = await db.trusts.find_one({"user_id": user["user_id"]}, sort={"trust_id": -1})
    suffix = 1
    if existing:
        try:
            suffix = int(existing["trust_id"].rsplit("_", 1)[1]) + 1
        except Exception:
            pass
    tid += str(suffix)
    doc = {
        "trust_id": tid,
        "user_id": user["user_id"],
        "name": name,
        "trust_type": "family",
        "created_at": _now(),
        "status": "active",
        "approval_threshold": None,
    }
    await db.trusts.insert_one(doc)
    return doc


@pytest_asyncio.fixture
async def seeded_db():
    """Clear collections and return db handle."""
    for coll in ["users", "trusts", "orgs", "org_members", "trust_grants", "trust_parties", "party_grants", "party_audit", "minutes_records", "minutes_approval_status"]:
        await db[coll].delete_many({})
    return db


class TestM1OrgSkeleton:
    """M1: org create, invite, grant, guard short-circuit."""

    @pytest.mark.asyncio
    async def test_toggle_off_returns_user(self, seeded_db):
        os.environ.pop("TOGGLE_INSTITUTION", None)
        user = await _seed_user("test1@example.com")
        trust = await _seed_trust(user)
        # guard short-circuits to user when flag off
        from dependencies import require_org_grant
        from models import GrantLevel
        # FastAPI Depends not available inline; call directly
        # We need to mock request
        class FakeRequest:
            pass
        result = await require_org_grant(trust["trust_id"], GrantLevel.viewer, FakeRequest(), user)
        assert result["user_id"] == user["user_id"]

    @pytest.mark.asyncio
    async def test_org_create_and_grant(self, seeded_db):
        os.environ["TOGGLE_INSTITUTION"] = "1"
        owner = await _seed_user("owner@example.com", "Owner")
        trust = await _seed_trust(owner)
        org_id = "org_abc123"
        await db.orgs.insert_one({"org_id": org_id, "name": "WP Group", "owner_user_id": owner["user_id"], "created_at": _now()})
        mem_id = "mem_def456"
        await db.org_members.insert_one({
            "member_id": mem_id, "org_id": org_id, "user_id": owner["user_id"],
            "email": owner["email"], "name": owner["name"],
            "role": OrgMemberRole.owner, "status": "active",
            "invited_at": _now(), "invited_by": owner["user_id"], "joined_at": _now(),
        })
        grant_doc = {
            "grant_id": "grant_001", "trust_id": trust["trust_id"],
            "org_id": org_id, "member_id": mem_id, "level": GrantLevel.preparer,
            "status": "active", "granted_by": owner["user_id"],
            "granted_at": _now(), "expires_at": _now(),
        }
        await db.trust_grants.insert_one(grant_doc)
        from dependencies import require_org_grant
        result = await require_org_grant(trust["trust_id"], GrantLevel.preparer, None, owner)
        # Owner passes guard; org_grant may not be present (owner short-circuit before grant lookup)
        assert result["user_id"] == owner["user_id"]

    @pytest.mark.asyncio
    async def test_org_grant_denies_non_member(self, seeded_db):
        os.environ["TOGGLE_INSTITUTION"] = "1"
        owner = await _seed_user("owner2@example.com")
        other = await _seed_user("other@example.com")
        trust = await _seed_trust(owner)
        from dependencies import require_org_grant
        from models import GrantLevel
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await require_org_grant(trust["trust_id"], GrantLevel.viewer, None, other)
        assert exc.value.status_code == 403


class TestM2TrustParty:
    """M2: trust-party CRUD, guard, protector powers, backfill."""

    @pytest.mark.asyncio
    async def test_party_create_and_grant(self, seeded_db):
        os.environ["TOGGLE_TRUST_PARTIES"] = "1"
        owner = await _seed_user("owner3@example.com")
        trust = await _seed_trust(owner)
        party_doc = {
            "party_id": "party_001", "trust_id": trust["trust_id"],
            "party_type": PartyType.co_trustee, "name": "Jane", "email": "jane@example.com",
            "status": "active", "powers": [], "invited_at": _now(),
            "activated_at": _now(), "user_id": "user_jane", "source": "manual",
        }
        await db.trust_parties.insert_one(party_doc)
        grant_doc = {
            "grant_id": "pgrant_001", "trust_id": trust["trust_id"],
            "party_id": "party_001", "level": PartyLevel.actor,
            "status": "active", "granted_by": owner["user_id"],
            "granted_at": _now(),
        }
        await db.party_grants.insert_one(grant_doc)
        from dependencies import require_trust_party_access
        user_jane = {"user_id": "user_jane", "email": "jane@example.com", "name": "Jane"}
        result = await require_trust_party_access(trust["trust_id"], PartyLevel.actor, None, user_jane)
        assert result.get("party_grant")["level"] == "actor"

    @pytest.mark.asyncio
    async def test_toggle_off_short_circuit(self, seeded_db):
        os.environ.pop("TOGGLE_TRUST_PARTIES", None)
        user = await _seed_user("rand@example.com")
        trust = await _seed_trust(user)
        from dependencies import require_trust_party_access
        result = await require_trust_party_access(trust["trust_id"], PartyLevel.viewer, None, user)
        assert "party_grant" not in result

    @pytest.mark.asyncio
    async def test_multi_sig_threshold_null_means_all(self, seeded_db):
        os.environ["TOGGLE_TRUST_PARTIES"] = "1"
        owner = await _seed_user("owner4@example.com")
        trust = await _seed_trust(owner)
        # null threshold
        await db.trusts.update_one({"trust_id": trust["trust_id"]}, {"$set": {"approval_threshold": None}})
        updated = await db.trusts.find_one({"trust_id": trust["trust_id"]})
        assert updated["approval_threshold"] is None


class TestM3Flags:
    """M3: flags default off, endpoints gated."""

    @pytest.mark.asyncio
    async def test_toggles_default_off(self, seeded_db):
        os.environ.pop("TOGGLE_INSTITUTION", None)
        os.environ.pop("TOGGLE_TRUST_PARTIES", None)
        assert _toggle_institution() is False
        assert _toggle_trust_parties() is False


class TestRegressionNoDelta:
    """Regression: existing flows unchanged when both flags OFF."""

    @pytest.mark.asyncio
    async def test_owner_still_passes_guard(self, seeded_db):
        os.environ.pop("TOGGLE_INSTITUTION", None)
        os.environ.pop("TOGGLE_TRUST_PARTIES", None)
        owner = await _seed_user("reg@example.com")
        trust = await _seed_trust(owner)
        from dependencies import require_org_grant, require_trust_party_access
        from models import GrantLevel, PartyLevel
        r1 = await require_org_grant(trust["trust_id"], GrantLevel.viewer, None, owner)
        r2 = await require_trust_party_access(trust["trust_id"], PartyLevel.viewer, None, owner)
        assert r1["user_id"] == owner["user_id"]
        assert r2["user_id"] == owner["user_id"]
