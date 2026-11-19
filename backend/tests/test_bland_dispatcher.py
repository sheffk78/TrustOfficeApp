"""Kit-owned Bland dispatch controller tests.

mongomock + httpx-free: BlandCaller takes an injectable fake session, so no
real HTTP and no respx dependency. Dispatcher reads all env at request time,
so monkeypatch.setenv/delenv drive every knob.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test_bland_dispatcher")
os.environ.setdefault("JWT_SECRET", "test-secret-dispatcher")

import motor.motor_asyncio
import mongomock_motor

motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio

import database
import routers.bland_dispatcher as disp
import routers.leads_service as leads_service

db = database.db

DENVER = disp.DENVER


def _lead(lead_id, *, stage="new", phone="+15551234567", created_at=None):
    now = created_at or datetime.now(timezone.utc)
    return {
        "lead_id": lead_id,
        "name": f"Lead {lead_id}",
        "email": f"{lead_id}@example.com",
        "phone": phone,
        "stage": stage,
        "source": "unit-test",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "notes": "",
    }


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    for coll in ("leads", "lead_activities", "bland_call_log"):
        await db[coll].delete_many({})
    yield
    for coll in ("leads", "lead_activities", "bland_call_log"):
        await db[coll].delete_many({})


@pytest.fixture
def reset_env(monkeypatch):
    """Reset dispatcher env knobs + aged-run state for each test."""
    monkeypatch.delenv("BLAND_DISPATCH_ENABLED", raising=False)
    monkeypatch.delenv("BLAND_API_KEY", raising=False)
    monkeypatch.delenv("BLAND_FRESH_ENABLED", raising=False)
    monkeypatch.delenv("BLAND_AGED_ENABLED", raising=False)
    monkeypatch.delenv("BLAND_WEBHOOK_SECRET", raising=False)
    monkeypatch.setattr(disp, "_AGED_LAST_RUN", None)
    monkeypatch.setattr(disp, "_HAS_TIER", False)


class FakeResp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def post(self, url, **kw):
        self.calls.append((url, kw))
        return self.responses.pop(0)


def _enable(monkeypatch, key="test-bland-key"):
    monkeypatch.setenv("BLAND_DISPATCH_ENABLED", "true")
    monkeypatch.setenv("BLAND_API_KEY", key)
    monkeypatch.setenv("BLAND_WEBHOOK_SECRET", "webhook-secret")
    # tests may run outside production hours; keep the window open
    monkeypatch.setenv("BLAND_CALL_WINDOW_MT", "00:00-23:59")


# ---------------------------------------------------------------------------
# idle / keyless
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_idle_when_disabled(reset_env, clean_db):
    await db.leads.insert_one(_lead("L1"))
    caller = disp.BlandCaller(session=FakeSession([]))
    summary = await disp.tick(caller)
    assert summary == {
        "fresh_called": 0, "fresh_skipped_window": 0,
        "aged_called": 0, "aged_skipped_window": 0,
    }
    assert caller.session.calls == []
    assert await db.bland_call_log.count_documents({}) == 0


@pytest.mark.asyncio
async def test_idle_when_keyless(reset_env, clean_db, monkeypatch):
    monkeypatch.setenv("BLAND_DISPATCH_ENABLED", "true")
    # BLAND_API_KEY absent
    await db.leads.insert_one(_lead("L1"))
    caller = disp.BlandCaller(session=FakeSession([]))
    summary = await disp.tick(caller)
    assert summary["fresh_called"] == 0
    assert caller.session.calls == []
    assert await db.bland_call_log.count_documents({}) == 0


# ---------------------------------------------------------------------------
# fresh poll: batch max + claim
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fresh_poll_batch_max_and_claim(reset_env, clean_db, monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setenv("BLAND_FRESH_ENABLED", "true")

    # oldest -> newest
    now = datetime.now(timezone.utc)
    await db.leads.insert_many([
        _lead("L1", created_at=now - timedelta(hours=3)),
        _lead("L2", created_at=now - timedelta(hours=2)),
        _lead("L3", created_at=now - timedelta(hours=1)),
    ])

    caller = disp.BlandCaller(session=FakeSession([
        FakeResp(200, {"call_id": "c1"}),
        FakeResp(200, {"call_id": "c2"}),
    ]))
    await disp.tick(caller)

    # batch max default 2 -> exactly 2 calls
    assert len(caller.session.calls) == 2
    # queue returns oldest first; L1, L2 dispatched
    assert caller.session.calls[0][1]["json"]["external_id"] == "L1"
    assert caller.session.calls[1][1]["json"]["external_id"] == "L2"

    # webhook URL carries ?secret=
    assert "?secret=webhook-secret" in caller.session.calls[0][1]["json"]["webhook"]

    # payload exact param names per Bland Send Call docs
    p1 = caller.session.calls[0][1]["json"]
    assert p1["agent_id"] == disp.DEFAULT_AGENT_ID
    assert p1["metadata"]["tier"] == "fresh"
    assert p1["request_data"]["timezone"] == "America/Denver"

    # claims created on dispatched leads
    l1 = await db.leads.find_one({"lead_id": "L1"})
    l2 = await db.leads.find_one({"lead_id": "L2"})
    l3 = await db.leads.find_one({"lead_id": "L3"})
    assert l1["claim"]["claimed_by"] == disp.CLAIMED_BY
    assert l2["claim"]["claimed_by"] == disp.CLAIMED_BY
    assert "claim" not in l3 or not l3["claim"].get("claimed_by")

    # audit log
    logs = await db.bland_call_log.find().to_list(None)
    assert len(logs) == 2
    assert all(log["ok"] for log in logs)
    assert all(log["tier"] == "fresh" for log in logs)
    assert all(log["http"] == 200 for log in logs)


# ---------------------------------------------------------------------------
# fresh: pre-claimed lead is skipped and logged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fresh_preclaimed_lead_skipped_and_logged(reset_env, clean_db, monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setenv("BLAND_FRESH_ENABLED", "true")

    now = datetime.now(timezone.utc)
    await db.leads.insert_many([
        _lead("L1", created_at=now - timedelta(hours=3)),
        _lead("L2", created_at=now - timedelta(hours=2)),
        _lead("L3", created_at=now - timedelta(hours=1)),
    ])

    # pre-claim L1 by another worker
    await db.leads.update_one(
        {"lead_id": "L1"},
        {"$set": {"claim": {"claimed_by": "other-worker", "claimed_until": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}}}
    )

    caller = disp.BlandCaller(session=FakeSession([FakeResp(200)]))
    await disp.tick(caller)

    # batch max default 2: batch = [L1 (pre-claimed -> skipped), L2 -> dispatched]
    assert len(caller.session.calls) == 1
    assert caller.session.calls[0][1]["json"]["external_id"] == "L2"

    # audit log: L1 entry with already_claimed + L2 ok
    logs = await db.bland_call_log.find().to_list(None)
    assert len(logs) == 2
    l1_log = next(l for l in logs if l["lead_id"] == "L1")
    assert l1_log["ok"] is False
    assert l1_log["error_code"] == "already_claimed"


# ---------------------------------------------------------------------------
# Bland 4xx -> logged, lead skipped, loop survives
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bland_4xx_logged_skipped_loop_survives(reset_env, clean_db, monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setenv("BLAND_FRESH_ENABLED", "true")

    now = datetime.now(timezone.utc)
    await db.leads.insert_many([
        _lead("L1", created_at=now - timedelta(hours=3)),
        _lead("L2", created_at=now - timedelta(hours=2)),
    ])

    # first call fails (400), second succeeds
    caller = disp.BlandCaller(session=FakeSession([
        FakeResp(400, {"error": "bad phone"}),
        FakeResp(200, {"call_id": "c2"}),
    ]))
    await disp.tick(caller)

    assert len(caller.session.calls) == 2
    logs = await db.bland_call_log.find().to_list(None)
    assert len(logs) == 2
    l1_log = next(l for l in logs if l["lead_id"] == "L1")
    assert l1_log["ok"] is False
    assert l1_log["http"] == 400
    assert l1_log["error_code"] == "bad phone"
    l2_log = next(l for l in logs if l["lead_id"] == "L2")
    assert l2_log["ok"] is True

    # second tick must not raise (loop survives)
    caller2 = disp.BlandCaller(session=FakeSession([FakeResp(200), FakeResp(200)]))
    summary = await disp.tick(caller2)
    assert summary["fresh_called"] == 2  # same claimer refreshes claim, re-dials


# ---------------------------------------------------------------------------
# aged disabled -> zero older dispatches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aged_disabled_zero_dispatches(reset_env, clean_db, monkeypatch):
    _enable(monkeypatch)
    # BLAND_AGED_ENABLED not set (default false)
    await db.leads.insert_one(_lead("OLD1"))

    caller = disp.BlandCaller(session=FakeSession([FakeResp(200)]))
    await disp.tick(caller)

    assert len(caller.session.calls) == 0
    assert await db.bland_call_log.count_documents({}) == 0


# ---------------------------------------------------------------------------
# aged once per day (with tier support simulated)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aged_once_per_day_with_tier_support(reset_env, clean_db, monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setenv("BLAND_AGED_ENABLED", "true")
    # Simulate tier support (concurrent lane merged) + aged queue
    monkeypatch.setattr(disp, "_HAS_TIER", True)

    aged_leads = [_lead("A1"), _lead("A2")]
    await db.leads.insert_many(aged_leads)
    async def fake_queue(*args, **kw):
        if kw.get("tier") == "aged":
            return {"leads": aged_leads, "count": 2}
        return {"leads": [], "count": 0}

    monkeypatch.setattr(disp, "_queue_fn", fake_queue)

    # day 1 10:00 Denver (MST = UTC-7 -> 17:00Z)
    day1_utc = datetime(2026, 11, 19, 17, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(disp, "_now", lambda: day1_utc)

    caller = disp.BlandCaller(session=FakeSession([FakeResp(200), FakeResp(200)]))
    await disp.tick(caller)

    assert len(caller.session.calls) == 2
    logs = await db.bland_call_log.find().to_list(None)
    assert len(logs) == 2
    assert all(l["tier"] == "aged" for l in logs)

    # second tick same day -> no new calls (aged_last_run == today)
    caller2 = disp.BlandCaller(session=FakeSession([FakeResp(200), FakeResp(200)]))
    await disp.tick(caller2)
    assert len(caller2.session.calls) == 0  # no new calls because aged already ran today

    # next day -> runs again
    day2_utc = datetime(2026, 11, 20, 17, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(disp, "_now", lambda: day2_utc)
    caller3 = disp.BlandCaller(session=FakeSession([FakeResp(200), FakeResp(200)]))
    await disp.tick(caller3)
    assert len(caller3.session.calls) == 2

    # cap is server-side (queue's tier=aged + bland_aged_budget post-merge)
    # dispatcher dispatches what the queue returns; no cap logic duplicated here.


# ---------------------------------------------------------------------------
# call window defers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_window_defers(reset_env, clean_db, monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setenv("BLAND_FRESH_ENABLED", "true")
    # window 03:00-04:00 Denver; now is 10:00 Denver -> outside
    monkeypatch.setenv("BLAND_CALL_WINDOW_MT", "03:00-04:00")
    now_utc = datetime(2026, 11, 19, 17, 0, tzinfo=timezone.utc)  # 10:00 MST
    monkeypatch.setattr(disp, "_now", lambda: now_utc)

    await db.leads.insert_many([_lead("L1"), _lead("L2")])
    caller = disp.BlandCaller(session=FakeSession([FakeResp(200), FakeResp(200)]))
    await disp.tick(caller)

    assert len(caller.session.calls) == 0
    assert await db.bland_call_log.count_documents({}) == 0
    # no claims created
    leads = await db.leads.find().to_list(None)
    for l in leads:
        assert "claim" not in l or not l["claim"].get("claimed_by")