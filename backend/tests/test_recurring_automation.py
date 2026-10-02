#!/usr/bin/env python3
"""Phase 2 — recurring automation engine + firm calendar (mongomock)."""
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
import dependencies
import routers.orgs as _orgs
import routers.org_queue as _oq
import services.recurring_automation as ra

db = database.db


def _iso(days):
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d")


@pytest_asyncio.fixture
async def ctx(monkeypatch):
    import mongomock_motor
    fresh = mongomock_motor.AsyncMongoMockClient()[os.environ["DB_NAME"]]
    for mod in (database, dependencies, _orgs, _oq):
        monkeypatch.setattr(mod, "db", fresh)
    globals()["db"] = fresh
    for c in ("orgs", "org_members", "trusts", "users", "trust_grants",
              "meeting_minutes", "governance_tasks", "health_score_snapshots",
              "minutes_approval_status", "org_activity"):
        await db[c].delete_many({})
    yield


@pytest.fixture
def user():
    return {"user_id": "u_adv", "email": "adv@firm.com", "name": "Advisor", "is_admin": False}


@pytest.mark.asyncio
async def test_materialization_creates_next_cycle_in_window(ctx):
    await db.governance_tasks.insert_one({
        "task_id": "t1", "trust_id": "trust_1", "user_id": "u_owner",
        "task_type": "quarterly_review", "due_date": _iso(4),  # next cycle (90d) outside window -> later pass, use annual small case:
    })
    # cycle fits window: set annual_review due 340d ago -> next due in 25d (inside 30d window)
    await db.governance_tasks.insert_one({
        "task_id": "t2", "trust_id": "trust_2", "user_id": "u_owner",
        "task_type": "annual_review", "due_date": _iso(-340),
        "completed_at": "2026-01-01T00:00:00+00:00",
    })
    out = await ra.materialize_recurring(db)
    assert out["dry_run"] is False
    assert len(out["created"]) == 1
    nxt = await db.governance_tasks.find_one({"created_via": "recurring_automation"})
    assert nxt["trust_id"] == "trust_2"
    expected_due = (datetime.now(timezone.utc) + timedelta(days=25)).strftime("%Y-%m-%d")
    assert nxt["due_date"] == expected_due
    assert nxt["created_via"] == "recurring_automation"
    # source task stamped materialized
    src = await db.governance_tasks.find_one({"task_id": "t2"})
    assert src["materialized"] is True


@pytest.mark.asyncio
async def test_materialization_dry_run(ctx):
    await db.governance_tasks.insert_one({
        "task_id": "t1", "trust_id": "trust_1", "user_id": "u_owner",
        "task_type": "quarterly_review", "due_date": _iso(-60),
        "completed_at": "2026-01-01T00:00:00+00:00",
    })
    out = await ra.materialize_recurring(db, dry_run=True)
    assert len(out["created"]) == 1 and out["dry_run"] is True
    assert await db.governance_tasks.count_documents({"created_via": "recurring_automation"}) == 0


@pytest.mark.asyncio
async def test_materialization_dedupe_on_rerun_and_successor(ctx):
    await db.governance_tasks.insert_one({
        "task_id": "t1", "trust_id": "trust_1", "user_id": "u_owner",
        "task_type": "quarterly_review", "due_date": _iso(-60),
        "completed_at": "2026-01-01T00:00:00+00:00",
    })
    await ra.materialize_recurring(db)
    n1 = await db.governance_tasks.count_documents({"created_via": "recurring_automation"})
    await ra.materialize_recurring(db)
    n2 = await db.governance_tasks.count_documents({"created_via": "recurring_automation"})
    assert n1 == 1 and n2 == 1  # idempotent
    # successor exists -> source marked materialized, no NEW duplicate
    await ra.materialize_recurring(db)
    assert await db.governance_tasks.count_documents({"created_via": "recurring_automation"}) == 1


@pytest.mark.asyncio
async def test_firm_calendar_buckets_and_automated_flag(ctx, user):
    member_id = "mem_adv"
    await db.orgs.insert_one({"org_id": "org_q", "name": "Firm"})
    await db.org_members.insert_one({"member_id": member_id, "org_id": "org_q", "user_id": "u_adv", "email": user["email"], "status": "active", "role": "owner"})
    await db.trusts.insert_one({"trust_id": "trust_1", "name": "Trust One", "user_id": "u_owner", "trustee_full_name": "T", "grantor_name": "G"})
    await db.users.insert_one({"user_id": "u_owner", "name": "Owner One", "email": "o1@x.com"})
    await db.trust_grants.insert_one({"grant_id": "g1", "trust_id": "trust_1", "org_id": "org_q", "member_id": member_id, "level": "preparer", "status": "active"})
    await db.governance_tasks.insert_many([
        {"task_id": "a1", "trust_id": "trust_1", "user_id": "u_owner", "task_type": "quarterly_review", "due_date": _iso(3), "description": "Q review", "created_at": "2026-01-01"},
        {"task_id": "a2", "trust_id": "trust_1", "user_id": "u_owner", "task_type": "custom", "due_date": _iso(3), "description": "Read ledger", "created_at": "2026-01-01"},
    ])
    out = await _oq.org_firm_calendar("org_q", user=user)
    assert out["counts"]["total"] == 2
    assert len(out["weeks"]) >= 1
    items = out["weeks"][0]["items"]
    titles = [i["title"] for i in items]
    assert "Q review" in titles and "Read ledger" in titles
    assert all(i["automated"] is False for i in items)


@pytest.mark.asyncio
async def test_firm_calendar_scopes_to_grants(ctx, user):
    # no member for user -> 403
    with pytest.raises(Exception) as ei:
        await _oq.org_firm_calendar("org_none", user=user)
    assert ei.value.status_code in (403, 404)
