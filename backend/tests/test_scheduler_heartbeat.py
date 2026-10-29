"""Tests for the scheduler heartbeat monitor (2026-10-28).

Production evidence for why this exists: on 2026-10-28 no background job ran
between ~09:10Z and ~18:10Z (deploy churn / restart gap). The outage silently
missed a booking-reminder window, and no monitor noticed because every monitor
is itself a scheduled job — dead jobs can't report their own death.

These tests use the same mongomock shim as the other funnel tests.
"""
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

# routers.leads / database.py read MONGO_URL at import time.
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_database")
os.environ.setdefault("JWT_SECRET", "test-secret-for-tests")

from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import heartbeat_monitor as hb
import discord_service as discord_module
from background_tasks import BackgroundTaskRunner


# --------------------------------------------------------------------------- #
# Async mongomock shim (motor-style API over sync mongomock)
# --------------------------------------------------------------------------- #
class _AsyncCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._cursor)
        except StopIteration:
            raise StopAsyncIteration

    async def to_list(self, length=None):
        return list(self._cursor)


class _AsyncCollection:
    def __init__(self, coll):
        self._coll = coll

    def find(self, *a, **k):
        return _AsyncCursor(self._coll.find(*a, **k))

    async def find_one(self, *a, **k):
        return self._coll.find_one(*a, **k)

    async def count_documents(self, *a, **k):
        return self._coll.count_documents(*a, **k)

    async def update_one(self, *a, **k):
        return self._coll.update_one(*a, **k)

    async def insert_one(self, doc, *a, **k):
        return self._coll.insert_one(doc, *a, **k)


class _AsyncDB:
    def __init__(self, client_db):
        self._db = client_db
        self._cols = {}

    def __getattr__(self, name):
        if name.startswith("_"):
            return object.__getattribute__(self, name)
        if name not in self._cols:
            self._cols[name] = _AsyncCollection(self._db[name])
        return self._cols[name]


@pytest.fixture
def db():
    import mongomock
    return _AsyncDB(mongomock.MongoClient()["hb_test"])


@pytest.fixture(autouse=True)
def capture_pipeline_alert(monkeypatch):
    calls = []

    async def _alert(**kwargs):
        calls.append(kwargs)
        return {"success": True}

    monkeypatch.setattr(discord_module, "notify_pipeline_alert", _alert)
    yield calls


def _stamp_hours_ago(db, job, hours_ago, field="last_run_at"):
    at = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    doc = {field: at, "job_name": job}
    return db.schedule_heartbeats.insert_one(doc)


# --------------------------------------------------------------------------- #
# stamping
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_stamp_heartbeat_upserts(db):
    r1 = await hb.stamp_heartbeat(db, "nurture_drip")
    assert r1["ok"] is True
    doc = await db.schedule_heartbeats.find_one({"job_name": "nurture_drip"})
    assert doc is not None
    assert isinstance(doc["last_run_at"], datetime)
    # Second stamp overwrites (upsert, not insert -> single doc).
    await hb.stamp_heartbeat(db, "nurture_drip")
    count = await db.schedule_heartbeats.count_documents({"job_name": "nurture_drip"})
    assert count == 1


@pytest.mark.asyncio
async def test_stamp_never_raises(db):
    class ExplodingDB:
        def __getattr__(self, name):
            raise RuntimeError("db down")

    r = await hb.stamp_heartbeat(ExplodingDB(), "nurture_drip")
    assert r["ok"] is False  # swallowed, job continues


# --------------------------------------------------------------------------- #
# stall detection
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_all_jobs_fresh_is_green(db, capture_pipeline_alert):
    for job in ("nurture_drip", "booking_reminders", "leads_pipeline_health"):
        await _stamp_hours_ago(db, job, hours_ago=2)
    result = await hb.check_scheduler_heartbeats(db)
    assert result["all_ok"] is True, result["failures"]
    assert result["stale_jobs"] == []
    assert capture_pipeline_alert == []


@pytest.mark.asyncio
async def test_stale_drip_pages_red(db, capture_pipeline_alert):
    # Drip runs every 6h; 14h of silence = 2+ missed cycles -> RED.
    # Reminders + monitor stamped fresh so only the drip is stale.
    await _stamp_hours_ago(db, "nurture_drip", hours_ago=14)
    await _stamp_hours_ago(db, "booking_reminders", hours_ago=1)
    await _stamp_hours_ago(db, "leads_pipeline_health", hours_ago=1)
    result = await hb.check_scheduler_heartbeats(db)
    assert result["all_ok"] is False
    assert result["stale_jobs"] == ["nurture_drip"]
    assert "nurture_drip" in result["failures"][0]


@pytest.mark.asyncio
async def test_stale_reminder_pages_red(db, capture_pipeline_alert):
    # Reminders run hourly; >3h silence means the job stopped.
    await _stamp_hours_ago(db, "nurture_drip", hours_ago=2)
    await _stamp_hours_ago(db, "booking_reminders", hours_ago=5)
    result = await hb.check_scheduler_heartbeats(db)
    assert result["all_ok"] is False
    assert "booking_reminders" in result["stale_jobs"]


@pytest.mark.asyncio
async def test_never_stamped_job_fails(db, capture_pipeline_alert):
    # Two jobs stamped, one never: the missing one is the failure.
    await _stamp_hours_ago(db, "nurture_drip", hours_ago=1)
    await _stamp_hours_ago(db, "booking_reminders", hours_ago=1)
    result = await hb.check_scheduler_heartbeats(db)
    assert result["all_ok"] is False
    assert result["stale_jobs"] == ["leads_pipeline_health"]


@pytest.mark.asyncio
async def test_string_timestamps_accepted(db, capture_pipeline_alert):
    """Prod Mongo may hold ISO strings during the type migration."""
    at = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    await db.schedule_heartbeats.insert_one({"job_name": "nurture_drip", "last_run_at": at})
    await _stamp_hours_ago(db, "booking_reminders", hours_ago=1)
    await _stamp_hours_ago(db, "leads_pipeline_health", hours_ago=1)
    result = await hb.check_scheduler_heartbeats(db)
    assert result["all_ok"] is True, result["failures"]


# --------------------------------------------------------------------------- #
# wired runner (background_tasks)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_runner_heartbeat_health_pages_on_stall(db, capture_pipeline_alert):
    r = BackgroundTaskRunner()
    r.db = db
    # Fresh reminders+monitor, dead drip.
    await _stamp_hours_ago(db, "nurture_drip", hours_ago=20)
    await _stamp_hours_ago(db, "booking_reminders", hours_ago=1)
    await _stamp_hours_ago(db, "leads_pipeline_health", hours_ago=1)
    result = await r.check_scheduler_heartbeat_health()
    assert result["all_ok"] is False
    assert len(capture_pipeline_alert) == 1
    assert "nurture_drip" in capture_pipeline_alert[0]["message"]
    # Self-stamps written.
    me = await db.schedule_heartbeats.find_one({"job_name": "scheduler_heartbeat_check"})
    assert me is not None and me.get("last_done_at") is not None


@pytest.mark.asyncio
async def test_runner_heartbeat_health_quiet_when_green(db, capture_pipeline_alert):
    r = BackgroundTaskRunner()
    r.db = db
    for job in ("nurture_drip", "booking_reminders", "leads_pipeline_health"):
        await _stamp_hours_ago(db, job, hours_ago=2)
    result = await r.check_scheduler_heartbeat_health()
    assert result["all_ok"] is True
    assert capture_pipeline_alert == []