"""Tests for the TrustOffice lead-pipeline fixes (2026-09-17 council audit).

Covers all 6 items:
  1. Drip throughput fix (per-run cap + all-due-fire)
  2. Booking reminders (day-before + 1-hour, idempotent)
  3. Post-drip re-engagement
  4. Monitor asserts (nurture + booking-reminder RED alerts)
  5. lead_activities.created_at string -> BSON Date (backfill + read-compat)
  6. Welcome double-send dedupe (Postmark vs MailerCloud step-1)

Uses an in-memory mongomock shim exposing the motor-style async API the code
expects, so no real DB or network is touched. All email sends are mocked.
"""
import logging
import os

# routers.leads / database.py read MONGO_URL at import time.
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_database")
os.environ.setdefault("JWT_SECRET", "test-secret-for-tests")

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock

import mongomock
import pytest

from background_tasks import (
    BackgroundTaskRunner,
    DRIP_MAX_PER_RUN,
    _as_dt,
)
import email_service as email_service_module
import mailercloud_service as mailercloud_module
import discord_service as discord_module
import leads_monitor


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

    async def insert_one(self, doc, *a, **k):
        return self._coll.insert_one(doc, *a, **k)

    async def update_one(self, *a, **k):
        return self._coll.update_one(*a, **k)

    async def delete_one(self, *a, **k):
        return self._coll.delete_one(*a, **k)

    async def count_documents(self, *a, **k):
        return self._coll.count_documents(*a, **k)


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


def make_async_db(db_name="test_database"):
    client = mongomock.MongoClient()
    return _AsyncDB(client[db_name])


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
EMAIL_METHODS = [
    "send_booking_reminder_day_before",
    "send_booking_reminder_1h",
    "send_post_drip_reengagement",
    "send_lead_welcome",
]


@pytest.fixture
def db():
    return make_async_db()


@pytest.fixture
def runner(db):
    r = BackgroundTaskRunner()
    r.db = db
    return r


@pytest.fixture(autouse=True)
def mock_services(monkeypatch):
    # Email service: configured + every send succeeds.
    email_service_module.email_service.server_token = "test-token"  # makes is_configured True
    for meth in EMAIL_METHODS:
        setattr(
            email_service_module.email_service,
            meth,
            AsyncMock(return_value={"success": True}),
        )
    # MailerCloud: configured + every call succeeds.
    mailercloud_module.MAILERCLOUD_API_KEY = "test-key"
    mailercloud_module.send_nurture_email_via_mailercloud = AsyncMock(
        return_value={"success": True}
    )
    mailercloud_module.add_to_lead_list = AsyncMock(return_value={"success": True})
    # Discord RED alert capture (monitor late-imports from discord_service).
    monkeypatch.setattr(
        discord_module,
        "notify_pipeline_alert",
        AsyncMock(return_value={"success": True}),
    )
    yield


def _make_lead(lead_id, **over):
    doc = {
        "lead_id": lead_id,
        "email": f"{lead_id}@example.com",
        "name": "Test Lead",
        "stage": "new",
        "created_at": (datetime.now(timezone.utc) - timedelta(days=30)),
    }
    doc.update(over)
    return doc


# --------------------------------------------------------------------------- #
# Item 1: Drip throughput fix
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_drip_sends_all_due_within_cap(runner, db):
    # 200 catch-up leads (step 0) -> all due; cap should clamp per run.
    for i in range(200):
        await db.leads.insert_one(_make_lead(f"L{i}"))
    n1 = await runner.send_nurture_drip_emails()
    n2 = await runner.send_nurture_drip_emails()
    n3 = await runner.send_nurture_drip_emails()
    assert n1 == DRIP_MAX_PER_RUN
    assert n2 == DRIP_MAX_PER_RUN
    assert n3 == 200 - 2 * DRIP_MAX_PER_RUN
    # All 200 eventually fire across runs.
    total = await db.leads.count_documents({"nurture_step_sent": 1})
    assert total == 200


@pytest.mark.asyncio
async def test_drip_sends_every_due_when_under_cap(runner, db, caplog):
    for i in range(30):
        await db.leads.insert_one(_make_lead(f"M{i}"))
    with caplog.at_level(logging.INFO):
        sent = await runner.send_nurture_drip_emails()
    assert sent == 30
    # Metric log line present.
    assert any("[drip-metric]" in r.message for r in caplog.records)
    # Activity rows written with BSON Date created_at (not string).
    act = await db.lead_activities.find_one({"action_type": "email"})
    assert act is not None
    assert isinstance(act["created_at"], datetime)
    assert not isinstance(act["created_at"], str)


@pytest.mark.asyncio
async def test_drip_excludes_booked_and_converted(runner, db):
    await db.leads.insert_one(_make_lead("B1", booked_call=True,
                                         booked_call_at=datetime.now(timezone.utc)))
    await db.leads.insert_one(_make_lead("B2", stage="converted"))
    sent = await runner.send_nurture_drip_emails()
    assert sent == 0


# --------------------------------------------------------------------------- #
# Item 2: Booking reminders
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_booking_day_before_reminder(runner, db):
    at = datetime.now(timezone.utc) + timedelta(hours=24)
    await db.leads.insert_one(_make_lead("K1", booked_call=True, booked_call_at=at))
    res = await runner.send_booking_reminder_emails()
    assert res == {"day_before": 1, "one_hour": 0}
    lead = await db.leads.find_one({"lead_id": "K1"})
    assert lead["reminder_day_before_sent_at"]
    assert not lead.get("reminder_1h_sent_at")
    # Idempotent: second run sends nothing.
    res2 = await runner.send_booking_reminder_emails()
    assert res2 == {"day_before": 0, "one_hour": 0}


@pytest.mark.asyncio
async def test_booking_1h_reminder(runner, db):
    at = datetime.now(timezone.utc) + timedelta(minutes=60)
    await db.leads.insert_one(_make_lead("K2", booked_call=True, booked_call_at=at))
    res = await runner.send_booking_reminder_emails()
    assert res == {"day_before": 0, "one_hour": 1}
    lead = await db.leads.find_one({"lead_id": "K2"})
    assert lead["reminder_1h_sent_at"]


@pytest.mark.asyncio
async def test_booking_window_boundaries(runner, db):
    # Just inside day-before window (24h, safely > 23h lower bound to avoid
    # clock-skew flakiness at the exact boundary).
    await db.leads.insert_one(_make_lead("K3", booked_call=True,
                                         booked_call_at=datetime.now(timezone.utc) + timedelta(hours=24)))
    # Far future (10d) -> nothing.
    await db.leads.insert_one(_make_lead("K4", booked_call=True,
                                         booked_call_at=datetime.now(timezone.utc) + timedelta(days=10)))
    # Past call -> nothing.
    await db.leads.insert_one(_make_lead("K5", booked_call=True,
                                         booked_call_at=datetime.now(timezone.utc) - timedelta(hours=2)))
    res = await runner.send_booking_reminder_emails()
    assert res == {"day_before": 1, "one_hour": 0}


# --------------------------------------------------------------------------- #
# Item 3: Post-drip re-engagement
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_post_drip_reengagement_sends_and_marks(runner, db):
    for i in range(5):
        await db.leads.insert_one(_make_lead(f"P{i}", nurture_step_sent=12, stage="new"))
    # Excluded: converted, step 11, already re-engaged.
    await db.leads.insert_one(_make_lead("PX", nurture_step_sent=12, stage="converted"))
    await db.leads.insert_one(_make_lead("PY", nurture_step_sent=11, stage="new"))
    await db.leads.insert_one(_make_lead("PZ", nurture_step_sent=12, stage="new",
                                         post_drip_reengaged_at="2026-09-01T00:00:00+00:00"))
    sent = await runner.send_post_drip_reengagement()
    assert sent == 5
    for i in range(5):
        lead = await db.leads.find_one({"lead_id": f"P{i}"})
        assert lead["stage"] == "post_drip"
        assert lead["post_drip_reengaged_at"]
    # Idempotent.
    assert await runner.send_post_drip_reengagement() == 0


# --------------------------------------------------------------------------- #
# Item 4: Monitor asserts
# --------------------------------------------------------------------------- #
def _eligible_lead(lead_id):
    return _make_lead(lead_id, nurture_step_sent=5, stage="new")


@pytest.mark.asyncio
async def test_monitor_pass_when_sends_present(db, monkeypatch):
    for i in range(4):
        await db.leads.insert_one(_eligible_lead(f"E{i}"))
    await db.lead_activities.insert_one({
        "activity_id": "a1",
        "lead_id": "E0",
        "action_type": "email",
        "content": "Sent nurture email 5/12 via MailerCloud",
        "created_at": datetime.now(timezone.utc),
    })
    result = await leads_monitor.check_leads_pipeline_health(db)
    assert result["all_ok"] is True
    discord_module.notify_pipeline_alert.assert_not_called()


@pytest.mark.asyncio
async def test_monitor_red_alert_when_no_sends(db):
    for i in range(4):
        await db.leads.insert_one(_eligible_lead(f"E{i}"))
    result = await leads_monitor.check_leads_pipeline_health(db)
    assert result["all_ok"] is False
    assert any("nurture" in f.lower() for f in result["failures"])
    discord_module.notify_pipeline_alert.assert_called_once()
    kwargs = discord_module.notify_pipeline_alert.call_args.kwargs
    assert kwargs.get("alert_level") == "red"
    assert "RED" in kwargs.get("title", "")


@pytest.mark.asyncio
async def test_monitor_booking_reminder_violation(db):
    # Booked call within 36h, no reminder logged -> violation.
    at = datetime.now(timezone.utc) + timedelta(hours=20)
    await db.leads.insert_one(_make_lead("KX", booked_call=True, booked_call_at=at))
    # No nurture activity, so nurture assert also fails; we only check the
    # booking-reminder violation is reported.
    result = await leads_monitor.check_leads_pipeline_health(db)
    assert any("booking" in f.lower() for f in result["failures"])
    discord_module.notify_pipeline_alert.assert_called_once()


@pytest.mark.asyncio
async def test_monitor_booking_reminder_ok_when_flagged(db):
    at = datetime.now(timezone.utc) + timedelta(hours=20)
    await db.leads.insert_one(_make_lead("KX", booked_call=True, booked_call_at=at,
                                         reminder_day_before_sent_at="2026-09-17T00:00:00+00:00"))
    await db.lead_activities.insert_one({
        "activity_id": "a2",
        "lead_id": "KX",
        "action_type": "email",
        "content": "Sent nurture email 5/12 via MailerCloud",
        "created_at": datetime.now(timezone.utc),
    })
    result = await leads_monitor.check_leads_pipeline_health(db)
    assert result["all_ok"] is True


# --------------------------------------------------------------------------- #
# Item 5: lead_activities.created_at string -> Date
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_backfill_string_created_at_to_date(runner, db):
    for i in range(3):
        await db.lead_activities.insert_one({
            "activity_id": f"old{i}",
            "lead_id": f"L{i}",
            "action_type": "email",
            "content": "legacy",
            "created_at": "2026-09-10T12:00:00+00:00",  # string
        })
    converted = await runner.backfill_lead_activities_dates()
    assert converted >= 3
    for i in range(3):
        doc = await db.lead_activities.find_one({"activity_id": f"old{i}"})
        assert isinstance(doc["created_at"], datetime)
        assert not isinstance(doc["created_at"], str)


@pytest.mark.asyncio
async def test_new_activity_write_is_date(runner, db):
    await runner._log_drip_activity("LT", "email", "x")
    doc = await db.lead_activities.find_one({"lead_id": "LT"})
    assert isinstance(doc["created_at"], datetime)
    assert not isinstance(doc["created_at"], str)


def test_as_dt_read_compat():
    d = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)
    assert _as_dt(d) is d
    assert isinstance(_as_dt("2026-09-10T12:00:00+00:00"), datetime)
    assert _as_dt("not-a-date") is None
    assert _as_dt(None) is None


@pytest.mark.asyncio
async def test_monitor_counts_string_created_at_activities(db):
    await db.leads.insert_one(_eligible_lead("EZ"))
    await db.lead_activities.insert_one({
        "activity_id": "sz",
        "lead_id": "EZ",
        "action_type": "email",
        "content": "Sent nurture email 5/12 via MailerCloud",
        "created_at": datetime.now(timezone.utc).isoformat(),  # legacy string
    })
    result = await leads_monitor.check_leads_pipeline_health(db)
    assert result["all_ok"] is True  # string activity still counted


# --------------------------------------------------------------------------- #
# Item 6: Welcome double-send dedupe
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_welcome_dedupe_prefers_mailercloud(runner, db, monkeypatch):
    from routers.leads import _welcome_with_dedupe

    leads_module_db = db  # module-global db used by _log_activity
    import routers.leads as leads_module
    monkeypatch.setattr(leads_module, "db", leads_module_db)

    await db.leads.insert_one(_make_lead("W1"))
    await _welcome_with_dedupe(db, "w1@example.com", "Test", "W1")

    mailercloud_module.send_nurture_email_via_mailercloud.assert_called_once()
    email_service_module.email_service.send_lead_welcome.assert_not_called()
    lead = await db.leads.find_one({"lead_id": "W1"})
    assert lead["nurture_step_sent"] == 1


@pytest.mark.asyncio
async def test_welcome_dedupe_postmark_fallback_when_mailercloud_fails(runner, db, monkeypatch):
    from routers.leads import _welcome_with_dedupe
    import routers.leads as leads_module
    monkeypatch.setattr(leads_module, "db", db)

    mailercloud_module.send_nurture_email_via_mailercloud = AsyncMock(
        return_value={"success": False, "error": "boom"}
    )
    await db.leads.insert_one(_make_lead("W2"))
    await _welcome_with_dedupe(db, "w2@example.com", "Test", "W2")

    mailercloud_module.send_nurture_email_via_mailercloud.assert_called_once()
    email_service_module.email_service.send_lead_welcome.assert_called_once()


# --------------------------------------------------------------------------- #
# Item 4 (regression): real notify_pipeline_alert must accept alert_level kw.
# The autouse mock_services fixture replaces notify_pipeline_alert with a
# MagicMock (which accepts anything), so it cannot catch a signature mismatch
# in the REAL function. If the real function ever rejects `alert_level`, every
# RED monitor alert would raise TypeError and be swallowed (silent failure).
# We load the real module fresh and out-of-band to lock the contract.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_real_notify_pipeline_alert_accepts_alert_level_kw():
    import importlib.util
    import os

    real_path = os.path.join(os.path.dirname(__file__), "..", "discord_service.py")
    spec = importlib.util.spec_from_file_location("discord_service_real_check", real_path)
    real_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(real_mod)

    # No webhook configured in the test env -> returns gracefully, no network.
    res = await real_mod.notify_pipeline_alert(
        title="Lead pipeline health check FAILED (RED)",
        message="nurture throughput floor missed",
        details={"eligible_cohort": 12, "sends_last_24h": 0},
        alert_level="red",
    )
    assert isinstance(res, dict)
    # And calling without alert_level must still work (backward compatible).
    res2 = await real_mod.notify_pipeline_alert(title="t", message="m")
    assert isinstance(res2, dict)
