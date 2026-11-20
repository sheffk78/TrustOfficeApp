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
    for coll in ("leads", "lead_activities", "bland_call_log", "bland_aged_budget"):
        await db[coll].delete_many({})
    yield
    for coll in ("leads", "lead_activities", "bland_call_log", "bland_aged_budget"):
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


# ---------------------------------------------------------------------------
# tier=aged through the REAL capped queue (no _queue_fn fake). The dispatcher
# side stays dumb: it dispatches what the queue hands back, so the daily cap
# must come from the bland_aged_budget ledger inside get_calling_queue. Bland
# traffic is the injected fake session; BLAND_DISPATCH_ENABLED stays off in
# the environment for any run_once-style path.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aged_poll_through_capped_queue_never_exceeds_ledger(
    reset_env, clean_db, monkeypatch
):
    _enable(monkeypatch)  # call window open; Bland client = fake session
    monkeypatch.setattr(disp, "_HAS_TIER", True)
    monkeypatch.setenv("BLAND_AGED_DAILY_CAP", "10")
    now = datetime.now(timezone.utc)
    # 12 aged leads (older than the default 7d fresh window); AGED0 newest.
    for i in range(12):
        await db.leads.insert_one(
            _lead(
                f"AGED{i}",
                phone="5550001000",
                created_at=now - timedelta(hours=169 + i),
            )
        )
    budget = db.bland_aged_budget
    await budget.delete_many({})

    # Poll 1: cap 10 -> exactly 10 dispatches, ledger == dispatched set.
    caller = disp.BlandCaller(session=FakeSession([FakeResp(200)] * 12))
    summary = await disp._poll_aged(caller)
    assert summary["aged_called"] == 10
    assert len(caller.session.calls) == 10
    submitted = {c[1]["json"]["external_id"] for c in caller.session.calls}
    ledger = await budget.find_one({})
    assert ledger is not None
    assert ledger["day"] == now.strftime("%Y-%m-%d")
    assert len(set(ledger["lead_ids"])) == 10
    assert submitted == set(ledger["lead_ids"])

    # Poll 2 same day: budget spent; the queue hands back the already-
    # emitted set idempotently (same 10 leads, never the 2 behind-cap ones).
    # The dispatcher re-claims its own claims by design (conflict only fires
    # for a DIFFERENT claimant), so it re-submits the same unique set --
    # ledger stays at exactly 10 unique leads across the whole day.
    caller2 = disp.BlandCaller(
        session=FakeSession([FakeResp(200)] * 12)
    )
    summary2 = await disp._poll_aged(caller2)
    submitted2 = {c[1]["json"]["external_id"] for c in caller2.session.calls}
    assert submitted2 == set(ledger["lead_ids"])  # no cap-overrun emission
    assert summary2["aged_called"] == len(submitted2)
    assert "AGED10" not in submitted2 and "AGED11" not in submitted2
    ledger2 = await budget.find_one({})
    assert set(ledger2["lead_ids"]) == set(ledger["lead_ids"])
    await budget.delete_many({})


# ===========================================================================
# 2026-11-20 zero-dial regression: tier created_at date-vs-string mismatch
# ---------------------------------------------------------------------------
# Commits 635a15c filtered the tier=fresh / tier=aged lanes on created_at
# against a bare ISO STRING. Production leads store created_at as a BSON
# datetime, and MongoDB type ordering makes date-vs-string comparisons match
# NOTHING, so both tier polls returned zero leads forever while the legacy
# no-param /queue (no created_at filter) still showed the full pool. The
# dispatcher kept ticking silently: zero claims, zero bland_call_log rows,
# zero dials, no errors (dials stopped 2026-11-19 01:17 UTC once the tier
# lane went live).
#
# Why the suite above missed it: the _lead() helper stores created_at as
# now.isoformat() --- a STRING --- so every pre-existing test exercised only
# the string-vs-string branch that always worked. The fix matches either
# storage form via $or; these tests pin both the clause shape and an
# end-to-end dispatch with a DATETIME-typed created_at lead.
# ===========================================================================


def _mtime(doc_value, comparator, op):
    """Mongo type-ordered comparison for one field condition.

    date~date and string~string compare normally; ANY cross-type comparison
    (the bug shape: BSON datetime field vs ISO string comparator) matches
    nothing, and a missing field matches neither $or branch.
    """
    if doc_value is None or op not in ("$gte", "$lt"):
        return False
    if isinstance(doc_value, datetime) and isinstance(comparator, datetime):
        left = doc_value if doc_value.tzinfo else doc_value.replace(tzinfo=timezone.utc)
        return left >= comparator if op == "$gte" else left < comparator
    if isinstance(doc_value, str) and isinstance(comparator, str):
        return doc_value >= comparator if op == "$gte" else doc_value < comparator
    return False


def _matches(doc, clause):
    """Evaluate {'$or': [{'created_at': {op: val}}, ...]}."""
    for branch in clause.get("$or", []):
        for op, val in branch.get("created_at", {}).items():
            if _mtime(doc.get("created_at"), val, op):
                return True
    return False


@pytest.mark.asyncio
async def test_tier_clauses_pin_datetime_and_string_comparisors(clean_db):
    cutoff = datetime.now(timezone.utc).isoformat()
    fresh = leads_service._created_at_gte_clause(cutoff)
    aged = leads_service._created_at_lt_clause(cutoff)
    fresh_vals = [b["created_at"]["$gte"] for b in fresh["$or"]]
    aged_vals = [b["created_at"]["$lt"] for b in aged["$or"]]
    for vals, op in ((fresh_vals, "$gte"), (aged_vals, "$lt")):
        assert any(isinstance(v, datetime) and v.tzinfo for v in vals), op
        assert any(isinstance(v, str) for v in vals), op


@pytest.mark.asyncio
async def test_old_string_clause_misses_datetime_doc_fix_matches(clean_db):
    """THE regression, pinned: the pre-fix bare-string $gte clause is blind
    to a BSON-datetime created_at; the fixed $or clause sees it."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=168)).isoformat()
    doc_dt = {"created_at": datetime.now(timezone.utc) - timedelta(hours=24)}
    doc_str = {"created_at": cutoff}
    old_clause = {"created_at": {"$gte": cutoff}}  # pre-fix shape (635a15c)
    assert not _mtime(doc_dt["created_at"], cutoff, "$gte"), (
        "old string clause must MISS a datetime-typed created_at (the bug)"
    )
    assert _mtime(doc_str["created_at"], cutoff, "$gte")
    fixed = leads_service._created_at_gte_clause(cutoff)
    assert _matches(doc_dt, fixed)
    assert _matches(doc_str, fixed)


@pytest.mark.asyncio
async def test_fresh_aged_partition_datetime_typed_leads(clean_db):
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=168)).isoformat()
    fresh = leads_service._created_at_gte_clause(cutoff)
    aged = leads_service._created_at_lt_clause(cutoff)
    new_lead = {"created_at": now - timedelta(hours=1)}     # hot inbound
    old_lead = {"created_at": now - timedelta(hours=400)}   # drip lane
    assert _matches(new_lead, fresh) and not _matches(new_lead, aged)
    assert _matches(old_lead, aged) and not _matches(old_lead, fresh)
    assert not _matches({}, fresh) and not _matches({}, aged)  # no widening


@pytest.mark.asyncio
async def test_fresh_poll_dispatches_datetime_created_at_lead(clean_db, reset_env, monkeypatch):
    """End-to-end through the REAL tier queue: a lead whose created_at is
    stored as a BSON datetime (production storage form) must be dispatched,
    claimed and audit-logged by tier=fresh. Before the fix the tier query
    match nothing and the poll returned zero leads (silent outage)."""
    _enable(monkeypatch)
    monkeypatch.setenv("BLAND_FRESH_ENABLED", "true")
    monkeypatch.setattr(disp, "_HAS_TIER", True)

    now = datetime.now(timezone.utc)
    await db.leads.insert_one({
        "lead_id": "DTC1",
        "name": "Datetime Lead",
        "email": "dtc1@example.com",
        "phone": "5550001000",  # >= 10 digits -> dialable regex
        "stage": "new",
        "source": "unit-test",
        "created_at": now - timedelta(hours=2),   # BSON datetime, NOT isoformat
        "updated_at": (now - timedelta(hours=2)).isoformat(),
        "notes": "",
    })

    caller = disp.BlandCaller(session=FakeSession([FakeResp(200)]))
    summary = await disp.tick(caller)

    assert summary["fresh_called"] == 1, "datetime-typed lead must be visible to tier=fresh"
    assert len(caller.session.calls) == 1
    assert caller.session.calls[0][1]["json"]["external_id"] == "DTC1"
    doc = await db.leads.find_one({"lead_id": "DTC1"})
    assert doc["claim"]["claimed_by"] == disp.CLAIMED_BY
    logs = await db.bland_call_log.find().to_list(None)
    assert len(logs) == 1 and logs[0]["ok"] is True


@pytest.mark.asyncio
async def test_aged_poll_dispatches_datetime_created_at_lead(clean_db, reset_env, monkeypatch):
    """Same as above through the REAL capped aged queue: an old lead with a
    BSON-datetime created_at must surface in tier=aged (pre-fix: aged_query
    matched nothing -> aged dispatches stayed at zero)."""
    _enable(monkeypatch)
    monkeypatch.setenv("BLAND_AGED_ENABLED", "true")
    monkeypatch.setattr(disp, "_HAS_TIER", True)
    monkeypatch.setenv("BLAND_AGED_DAILY_CAP", "10")

    now = datetime.now(timezone.utc)
    await db.leads.insert_one({
        "lead_id": "DTA1",
        "name": "Old Datetime Lead",
        "email": "dta1@example.com",
        "phone": "5550001000",
        "stage": "new",
        "source": "unit-test",
        "created_at": now - timedelta(hours=400),  # well outside fresh window
        "updated_at": (now - timedelta(hours=400)).isoformat(),
        "notes": "",
    })
    await db.bland_aged_budget.delete_many({})

    summary = await disp._poll_aged(disp.BlandCaller(session=FakeSession([FakeResp(200)])))

    assert summary["aged_called"] == 1, "datetime-typed lead must be visible to tier=aged"
    budget = await db.bland_aged_budget.find_one({})
    assert budget is not None and budget["lead_ids"] == ["DTA1"]


@pytest.mark.asyncio
async def test_call_window_boundary_and_dst_wall_time_math(reset_env):
    """Pins the exonerated timezone suspect: window gates on Denver wall
    time (zoneinfo-aware), start inclusive, end exclusive, DST-safe. The
    caller must pass an already-Denver-converted datetime (as tick() does
    via .astimezone(DENVER)); a raw datetime.timezone.utc-aware datetime
    raises on naive/aware time comparison by design."""
    f = disp._call_window_open
    d = disp.DENVER

    def denver(y, m, day, hh, mm):
        return datetime(y, m, day, hh, mm, tzinfo=timezone.utc).astimezone(d)

    assert f(denver(2026, 11, 20, 16, 0))   # 09:00 MST, window start inclusive
    assert f(denver(2026, 11, 20, 16, 5))   # 09:05 MT
    assert f(denver(2026, 11, 20, 22, 0))   # 15:00 MT, mid-window
    assert f(denver(2026, 11, 21, 2, 29))   # 19:29 MST
    assert not f(denver(2026, 11, 21, 2, 30))   # 19:30 MST, end exclusive
    assert not f(denver(2026, 11, 20, 15, 59))  # 08:59 MST, before start
    assert not f(denver(2026, 11, 20, 13, 0))   # 06:00 MST
    # DST: 09:00 MT is 16:00 UTC in Nov (MST, UTC-7) but 15:00 UTC in Jul (MDT, UTC-6)
    assert not f(denver(2026, 11, 20, 15, 59))
    assert f(denver(2026, 7, 20, 15, 0))    # 09:00 MDT start
    assert not f(denver(2026, 7, 20, 14, 59))
    assert not f(denver(2026, 7, 21, 1, 30))    # 19:30 MDT end exclusive