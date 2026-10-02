"""Phase 1 — org overview + review queue (mongomock, mirrors test_org_trusts_search)."""
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

db = database.db

ORG_ID = "org_q"


async def _seed(member_level="preparer", health=72, pending=0):
    user = {"user_id": "u_adv", "email": "adv@firm.com", "name": "Advisor", "is_admin": False}
    member_id = "mem_adv"
    await db.orgs.insert_one({"org_id": ORG_ID, "name": "Firm"})
    await db.org_members.insert_one({
        "member_id": member_id, "org_id": ORG_ID, "user_id": user["user_id"],
        "email": user["email"], "status": "active", "role": "owner",
    })
    await db.trusts.insert_one({
        "trust_id": "t_a", "name": "Trust A", "user_id": "u_owner_a",
        "grantor_name": "G", "trustee_full_name": "T", "creation_date": "2024-01-01",
    })
    await db.users.insert_one({"user_id": "u_owner_a", "name": "Owner A", "email": "a@x.com"})
    await db.trust_grants.insert_one({
        "grant_id": "g_a", "trust_id": "t_a", "org_id": ORG_ID,
        "member_id": member_id, "level": member_level, "status": "active",
    })
    if pending:
        await db.meeting_minutes.insert_one({"minutes_id": "mm1", "trust_id": "t_a", "status": "draft"})
    if health is not None:
        await db.health_score_snapshots.insert_one({
            "trust_id": "t_a", "score": health, "created_at": datetime.now(timezone.utc).isoformat(),
        })
    return user


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


@pytest.mark.asyncio
async def test_overview_rollup(ctx):
    user = await _seed(health=72, pending=2)
    today = datetime.now(timezone.utc).date()
    await db.governance_tasks.insert_one({
        "task_id": "task_1", "trust_id": "t_a", "user_id": "u_owner_a",
        "task_type": "quarterly_review",
        "due_date": (today + timedelta(days=3)).strftime("%Y-%m-%d"),
        "description": "Q review", "completed_at": None, "created_at": "2026-01-01",
    })
    out = await _oq.org_overview(ORG_ID, user=user)
    assert out["portfolio"]["trust_count"] == 1
    assert out["portfolio"]["average_health"] == 72.0
    assert out["portfolio"]["pending_minutes_total"] == 1  # one draft minute seeded
    assert out["portfolio"]["due_week"] == 1
    row = out["trusts"][0]
    assert row["health_chip"] == "watch"  # 60 <= 72 < 80
    assert row["next_deadline"] is not None


@pytest.mark.asyncio
async def test_queue_urgency_order_and_counts(ctx):
    user = await _seed()
    today = datetime.now(timezone.utc)
    await db.governance_tasks.insert_many([
        {"task_id": "tk_over", "trust_id": "t_a", "user_id": "u_owner_a", "task_type": "annual_review",
         "due_date": (today - timedelta(days=3)).strftime("%Y-%m-%d"), "completed_at": None, "description": "Overdue", "created_at": "2026-01-01"},
        {"task_id": "tk_week", "trust_id": "t_a", "user_id": "u_owner_a", "task_type": "quarterly_review",
         "due_date": (today + timedelta(days=5)).strftime("%Y-%m-%d"), "completed_at": None, "description": "This week", "created_at": "2026-01-01"},
        {"task_id": "tk_later", "trust_id": "t_a", "user_id": "u_owner_a", "task_type": "custom",
         "due_date": (today + timedelta(days=70)).strftime("%Y-%m-%d"), "completed_at": None, "description": "Later", "created_at": "2026-01-01"},
    ])
    out = await _oq.org_queue(org_id=ORG_ID, user=user)
    urgencies = [i["urgency"] for i in out["items"]]
    assert urgencies == ["overdue", "due_week", "later"]
    assert out["counts"] == {"overdue": 1, "due_week": 1, "later": 1}
    assert out["items"][0]["trust_name"] == "Trust A"


@pytest.mark.asyncio
async def test_queue_complete_on_behalf_recurrence_and_dedupe(ctx):
    user = await _seed(member_level="preparer")
    today = datetime.now(timezone.utc)
    task = {
        "task_id": "tk_rec", "trust_id": "t_a", "user_id": "u_owner_a",
        "task_type": "quarterly_review",
        "due_date": (today - timedelta(days=1)).strftime("%Y-%m-%d"),
        "completed_at": None, "description": "Q", "checklist_items": [], "created_at": "2026-01-01",
    }
    await db.governance_tasks.insert_one(dict(task))  # copy: mongomock stamps _id in place
    out = await _oq.org_queue_complete("tk_rec", user=user)
    assert out["status"] == "completed" and out["completed_via"] == "org_queue"
    # next cycle spawned (90d from original due)
    nxt = await db.governance_tasks.find_one({"created_via": "org_queue_recurrence"})
    assert nxt is not None
    original_due = task["due_date"]
    from datetime import datetime as dt
    expected = (dt.fromisoformat(original_due) + timedelta(days=90)).isoformat()
    assert nxt["due_date"] == expected
    # attribution stamped on completed task
    done = await db.governance_tasks.find_one({"task_id": "tk_rec"})
    assert done["completed_via"] == "org_queue" and done["completed_by_member_id"] == "mem_adv"
    # activity entry
    act = await db.org_activity.find_one({"action": "queue_task_completed"})
    assert act is not None
    # IDEMPOTENCE/DEDUPE: completing a fresh identical task now spawns NO second cycle
    task2 = dict(task, task_id="tk_rec2")
    task2.pop("_id", None)
    await db.governance_tasks.insert_one(task2)
    out2 = await _oq.org_queue_complete("tk_rec2", user=user)
    cycles = [d async for d in db.governance_tasks.find({"created_via": "org_queue_recurrence"})]
    assert len(cycles) == 1  # dedupe guard held


@pytest.mark.asyncio
async def test_viewer_grant_cannot_complete(ctx):
    user = await _seed(member_level="viewer")
    await db.governance_tasks.insert_one({
        "task_id": "tk_v", "trust_id": "t_a", "user_id": "u_owner_a",
        "task_type": "custom", "due_date": "2026-01-01", "completed_at": None, "created_at": "2026-01-01",
    })
    with pytest.raises(Exception) as ei:
        await _oq.org_queue_complete("tk_v", user=user)
    assert ei.value.status_code == 403


@pytest.mark.asyncio
async def test_toggle_off_404(ctx, monkeypatch):
    monkeypatch.setattr(_oq, "_toggle_institution", lambda: False)
    user = {"user_id": "u_adv", "email": "adv@firm.com"}
    with pytest.raises(Exception) as ei:
        await _oq.org_overview(ORG_ID, user=user)
    assert ei.value.status_code == 404
