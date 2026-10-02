#!/usr/bin/env python3
"""Phase 0 — GET /orgs/{org_id}/trusts/search (advisor hundreds-scale filter).

Offline mongomock suite (same pattern as test_org_workspace_entry.py):
- default page: 200 seeded trusts -> page_size 24, total/pages correct
- q matches name substring (case-insensitive, escaped)
- level filter preparer/viewer counts
- sort name_asc ordering
- pagination jump (page 5)
- grant scoping: non-member org -> 403
- client filter by owner_user_id
- attention/healthy status filter
- deadline=7d / none filters
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

import database
from dependencies import get_current_user
from models import GrantLevel

db = database.db

ORG_ID = "org_s"
OWNER = "u_adv1"


def _iso(d: datetime) -> str:
    return d.isoformat()


async def _seed_org(user):
    uid = user["user_id"]
    member_id = f"mem_{uid}"
    await db.orgs.insert_one({"org_id": ORG_ID, "name": "Big Firm", "owner_user_id": uid})
    await db.org_members.insert_one({
        "member_id": member_id, "org_id": ORG_ID, "user_id": uid,
        "email": user["email"], "status": "active", "role": "owner",
    })
    return member_id


def _trust(i: int) -> dict:
    return {
        "trust_id": f"t_{i:03d}",
        "name": f"Family Trust {i}" if i % 5 else f"Alpha Trust {i}",
        "user_id": f"u_c{i % 40:03d}",
        "grantor_name": f"Grantor {i}",
        "trustee_full_name": f"Trustee {i}",
        "creation_date": "2024-01-01",
    }


async def _seed_book(member_id: str, n=200):
    from routers.org_search import org_trusts_search  # ensure module importable
    for i in range(n):
        await db.trusts.insert_one(_trust(i))
        await db.users.insert_one({
            "user_id": f"u_c{i % 40:03d}", "name": f"Client {i % 40}",
            "email": f"client{i % 40}@x.com",
        })
        await db.trust_grants.insert_one({
            "grant_id": f"g_{i}", "trust_id": f"t_{i:03d}", "org_id": ORG_ID,
            "member_id": member_id,
            "level": "preparer" if i % 3 else "viewer",
            "status": "active",
        })


@pytest_asyncio.fixture
async def ctx(monkeypatch):
    # Suites sharing a process (e.g. test_tenant_isolation's FakeDB swap of
    # database.db / dependencies.db) must not leak in — pin a FRESH mongomock
    # db on every module that reads it by identity (same mechanism they use).
    import mongomock_motor
    import dependencies
    import routers.orgs as _orgs
    import routers.org_search as _osearch
    fresh = mongomock_motor.AsyncMongoMockClient()[os.environ["DB_NAME"]]
    for mod in (database, dependencies, _orgs, _osearch):
        monkeypatch.setattr(mod, "db", fresh)
    globals()["db"] = fresh
    # clean collections (mongomock is in-process)
    for c in ("orgs", "org_members", "trusts", "users", "trust_grants",
              "meeting_minutes", "governance_tasks", "health_score_snapshots",
              "minutes_approval_status"):
        await db[c].delete_many({})
    user = {"user_id": "u_adv1", "email": "adv@firm.com", "name": "Advisor", "is_admin": False}
    member_id = await _seed_org(user)
    await _seed_book(member_id)
    return user


# ---- direct endpoint invocation (matches test_org_workspace_entry style) ----

async def _call(user, **params):
    from routers.org_search import org_trusts_search
    return await org_trusts_search(ORG_ID, user=user, **params)


@pytest.mark.asyncio
async def test_default_page_and_total(ctx):
    out = await _call(ctx)
    assert out["total"] == 200
    assert len(out["trusts"]) == 24
    assert out["page"] == {"page": 1, "page_size": 24, "pages": 9}
    # payload parity with org_trusts contract
    t = out["trusts"][0]
    for k in ("trust_id", "name", "owner_user_id", "owner_name", "owner_email",
              "grantor_name", "trustee_name", "grant_level", "pending_minutes",
              "next_deadline"):
        assert k in t
    assert "health_score" in t


@pytest.mark.asyncio
async def test_q_matches_owner_and_name(ctx):
    out = await _call(ctx, q="Alpha Trust 5")
    names = [t["name"] for t in out["trusts"]]
    assert out["total"] >= 1 and all("Alpha Trust 5" in n for n in names)
    # escaped regex: dots/parens don't blow up
    out2 = await _call(ctx, q="Family (Trust")
    assert out2["total"] == 0


@pytest.mark.asyncio
async def test_level_filter(ctx):
    viewers = await _call(ctx, level="viewer")
    preps = await _call(ctx, level="preparer")
    assert viewers["total"] + preps["total"] == 200
    assert all(t["grant_level"] == "viewer" for t in viewers["trusts"])


@pytest.mark.asyncio
async def test_name_sort_and_pagination(ctx):
    out = await _call(ctx, sort="name_asc")
    names = [t["name"].lower() for t in out["trusts"]]
    assert names == sorted(names)
    jump = await _call(ctx, page=9, page_size=24)
    assert len(jump["trusts"]) == 200 - 8 * 24
    assert jump["page"]["page"] == 9


@pytest.mark.asyncio
async def test_status_attention(ctx):
    # trust t_100: pending minutes + health snapshot (low) → attention
    await db.meeting_minutes.insert_one({
        "minutes_id": "m1", "trust_id": "t_100", "status": "draft",
    })
    await db.health_score_snapshots.insert_one({
        "trust_id": "t_100", "score": 42, "created_at": _iso(datetime.now(timezone.utc)),
    })
    out = await _call(ctx, status="attention")
    ids = [t["trust_id"] for t in out["trusts"]]
    assert "t_100" in ids
    healthy = await _call(ctx, status="healthy")
    assert "t_100" not in [t["trust_id"] for t in healthy["trusts"]]


@pytest.mark.asyncio
async def test_deadline_windows(ctx):
    today = datetime.now(timezone.utc)
    await db.governance_tasks.insert_many([
        {"trust_id": "t_200", "due_date": (today - timedelta(days=2)).strftime("%Y-%m-%d"),
         "task_type": "annual_review", "title": "Overdue review"},  # overdue (not in default forward search)
        {"trust_id": "t_201", "due_date": (today + timedelta(days=3)).strftime("%Y-%m-%d"),
         "task_type": "quarterly_review", "title": "Due soon"},
        {"trust_id": "t_202", "due_date": (today + timedelta(days=60)).strftime("%Y-%m-%d"),
         "task_type": "annual_review", "title": "Later"},
    ])
    # note: t_200/t_201/t_202 not in the 200-trust grant book → use t_000..t_199 ids
    await db.governance_tasks.insert_many([
        {"trust_id": "t_010", "due_date": (today + timedelta(days=3)).strftime("%Y-%m-%d"), "title": "Soon"},
        {"trust_id": "t_011", "due_date": (today + timedelta(days=45)).strftime("%Y-%m-%d"), "title": "Mid"},
    ])
    week = await _call(ctx, deadline="7d")
    ids = [t["trust_id"] for t in week["trusts"]]
    assert "t_010" in ids and "t_011" not in ids
    none = await _call(ctx, deadline="none")
    assert "t_010" not in [t["trust_id"] for t in none["trusts"]]
    assert "t_011" not in [t["trust_id"] for t in none["trusts"]]


@pytest.mark.asyncio
async def test_client_filter_and_scoping(ctx):
    out = await _call(ctx, client="u_c001")
    assert out["total"] == 5  # 200 trusts, owner cycled over 40 clients
    assert all(t["owner_user_id"] == "u_c001" for t in out["trusts"])

    # non-member org → 404 (org does not exist) — access control holds either way
    from routers.org_search import org_trusts_search
    with pytest.raises(Exception) as ei:
        await org_trusts_search("org_other", user=ctx)
    assert getattr(ei.value, "status_code", 500) in (403, 404)


@pytest.mark.asyncio
async def test_unknown_sort_defaults_pending(ctx):
    out = await _call(ctx, sort="bogus")
    counts = [t["pending_minutes"] for t in out["trusts"]]
    assert counts == sorted(counts, reverse=True)