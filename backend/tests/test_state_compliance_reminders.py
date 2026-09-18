"""
Tests for TrustOffice State Compliance Phase A (2026-09-17):
closing the notification loop for state-compliance deadlines.

Covers:
  (a) upcoming notice deadline fires within 30d and marks sent
  (b) no duplicate on second run (same threshold)
  (c) 'null' string sentinel + null fields are skipped
  (d) overdue fires once (no daily repeat)
  (e) accounting deadline fires (act = 'annual accounting')
  (f) health monitor RED-alerts when due-within-14d exists but zero sends in
      24h, and stays quiet when a send happened / email unconfigured
  (g) email-not-configured skip
  (h) the daily job still returns a sane value and the task-deadline path is
      unaffected

Uses an in-memory mongomock shim exposing the motor-style async API (copied from
test_lead_pipeline_fixes.py) so no real DB or network is touched. All email
sends are mocked.
"""
import asyncio
import logging
import os

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_database")
os.environ.setdefault("JWT_SECRET", "test-secret-for-tests")

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock

import mongomock
import pytest

from background_tasks import BackgroundTaskRunner
import email_service as email_service_module
import discord_service as discord_module
import compliance_monitor
from email_templates import render_template


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
@pytest.fixture
def db():
    return make_async_db()


@pytest.fixture
def runner(db):
    r = BackgroundTaskRunner()
    r.db = db
    return r


@pytest.fixture(autouse=True)
def mock_services():
    # Email service: configured + every send succeeds.
    email_service_module.email_service.server_token = "test-token"
    email_service_module.email_service.send_templated_email = AsyncMock(
        return_value={"status": "sent", "message_id": "test-123"}
    )
    # Discord RED alert capture (monitor late-imports from discord_service).
    discord_module.notify_pipeline_alert = AsyncMock(return_value={"success": True})
    yield


async def _seed_trust_user(db, trust_id="T1", user_id="U1", state_code="CA",
                           state_name="California"):
    await asyncio.gather(
        db.trusts.insert_one({
            "trust_id": trust_id, "user_id": user_id,
            "trust_name": "Demo Trust", "state_code": state_code,
            "state_name": state_name,
        }),
        db.users.insert_one({
            "user_id": user_id, "email": "owner@example.com", "name": "Owner",
        }),
    )


def _today():
    return datetime.now(timezone.utc).date()


def _mk_compliance(trust_id="T1", state_code="CA", notice_next_due=None,
                   accounting_next_due=None, compliance_reminder_sent=None):
    doc = {
        "trust_id": trust_id, "state_code": state_code,
        "notice_next_due": notice_next_due,
        "accounting_next_due": accounting_next_due,
    }
    if compliance_reminder_sent is not None:
        doc["compliance_reminder_sent"] = compliance_reminder_sent
    return doc


# --------------------------------------------------------------------------- #
# (a) upcoming notice deadline fires within 30d and marks sent
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_upcoming_notice_fires_and_marks(runner, db):
    await _seed_trust_user(db)
    due = (_today() + timedelta(days=10)).isoformat()
    await db.trust_state_compliance.insert_one(_mk_compliance(notice_next_due=due))

    sent = await runner.send_compliance_deadline_reminders()

    assert sent == 1
    email_service_module.email_service.send_templated_email.assert_called_once()
    call = email_service_module.email_service.send_templated_email.call_args
    assert call.kwargs["template_name"] == "compliance_deadline_reminder"
    assert call.kwargs["tag"] == "compliance_reminder"
    td = call.kwargs["template_data"]
    assert td["act"] == "beneficiary notice"
    assert td["is_overdue"] is False
    assert td["days_remaining"] == 10

    rec = await db.trust_state_compliance.find_one({"trust_id": "T1", "state_code": "CA"})
    assert "upcoming" in (rec.get("compliance_reminder_sent") or {}).get("notice", [])


# --------------------------------------------------------------------------- #
# (b) no duplicate on second run (same threshold)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_no_duplicate_second_run(runner, db):
    await _seed_trust_user(db)
    due = (_today() + timedelta(days=10)).isoformat()
    await db.trust_state_compliance.insert_one(_mk_compliance(notice_next_due=due))

    s1 = await runner.send_compliance_deadline_reminders()
    s2 = await runner.send_compliance_deadline_reminders()

    assert s1 == 1 and s2 == 0
    assert email_service_module.email_service.send_templated_email.call_count == 1


# --------------------------------------------------------------------------- #
# (c) 'null' string sentinel + null fields are skipped
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_null_sentinel_and_null_skipped(runner, db):
    await _seed_trust_user(db)
    await db.trust_state_compliance.insert_one(
        _mk_compliance(notice_next_due="null", accounting_next_due=None)
    )

    sent = await runner.send_compliance_deadline_reminders()

    assert sent == 0
    assert email_service_module.email_service.send_templated_email.call_count == 0


# --------------------------------------------------------------------------- #
# (d) overdue fires once (no daily repeat)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_overdue_fires_once(runner, db):
    await _seed_trust_user(db)
    due = (_today() - timedelta(days=5)).isoformat()
    await db.trust_state_compliance.insert_one(_mk_compliance(notice_next_due=due))

    s1 = await runner.send_compliance_deadline_reminders()
    s2 = await runner.send_compliance_deadline_reminders()

    assert s1 == 1 and s2 == 0
    call = email_service_module.email_service.send_templated_email.call_args
    td = call.kwargs["template_data"]
    assert td["is_overdue"] is True
    assert td["days_overdue"] == 5

    rec = await db.trust_state_compliance.find_one({"trust_id": "T1", "state_code": "CA"})
    assert "overdue" in (rec.get("compliance_reminder_sent") or {}).get("notice", [])


# --------------------------------------------------------------------------- #
# (e) accounting deadline fires (act = 'annual accounting')
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_accounting_fires(runner, db):
    await _seed_trust_user(db)
    due = (_today() + timedelta(days=3)).isoformat()
    await db.trust_state_compliance.insert_one(_mk_compliance(accounting_next_due=due))

    sent = await runner.send_compliance_deadline_reminders()

    assert sent == 1
    call = email_service_module.email_service.send_templated_email.call_args
    td = call.kwargs["template_data"]
    assert td["act"] == "annual accounting"
    rec = await db.trust_state_compliance.find_one({"trust_id": "T1", "state_code": "CA"})
    assert "upcoming" in (rec.get("compliance_reminder_sent") or {}).get("accounting", [])


# --------------------------------------------------------------------------- #
# (f) health monitor RED-alerts when stalled; quiet when send happened; quiet
#     when email unconfigured
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_monitor_red_alert_when_stalled(db):
    spy = AsyncMock()
    await db.trust_state_compliance.insert_one(
        _mk_compliance(notice_next_due=(_today() + timedelta(days=5)).isoformat())
    )
    res = await compliance_monitor.check_compliance_reminder_health(
        db, notify=spy, email_configured=True
    )
    assert res["all_ok"] is False
    assert res["at_risk_count"] == 1
    spy.assert_called_once()
    kwargs = spy.call_args.kwargs
    assert kwargs.get("alert_level") == "red"
    assert "stalled" in kwargs.get("title", "").lower()


@pytest.mark.asyncio
async def test_monitor_quiet_when_send_happened(db):
    spy = AsyncMock()
    await db.trust_state_compliance.insert_one(
        _mk_compliance(notice_next_due=(_today() + timedelta(days=5)).isoformat())
    )
    await db.audit_logs.insert_one({
        "action": "compliance_reminder_sent",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    res = await compliance_monitor.check_compliance_reminder_health(
        db, notify=spy, email_configured=True
    )
    assert res["all_ok"] is True
    spy.assert_not_called()


@pytest.mark.asyncio
async def test_monitor_quiet_when_email_unconfigured(db):
    spy = AsyncMock()
    await db.trust_state_compliance.insert_one(
        _mk_compliance(notice_next_due=(_today() + timedelta(days=5)).isoformat())
    )
    res = await compliance_monitor.check_compliance_reminder_health(
        db, notify=spy, email_configured=False
    )
    assert res["all_ok"] is True
    spy.assert_not_called()


# --------------------------------------------------------------------------- #
# (g) email-not-configured skip
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_email_not_configured_skips(runner, db):
    email_service_module.email_service.server_token = ""
    try:
        await _seed_trust_user(db)
        due = (_today() + timedelta(days=5)).isoformat()
        await db.trust_state_compliance.insert_one(_mk_compliance(notice_next_due=due))

        sent = await runner.send_compliance_deadline_reminders()

        assert sent == 0
        assert email_service_module.email_service.send_templated_email.call_count == 0
    finally:
        email_service_module.email_service.server_token = "test-token"


# --------------------------------------------------------------------------- #
# (h) daily job returns a sane value + task-deadline path unaffected
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_daily_job_returns_breakdown_and_task_path(runner, db):
    await _seed_trust_user(db)
    due = (_today() + timedelta(days=5)).isoformat()
    await db.deadlines.insert_one({
        "deadline_id": "D1", "trust_id": "T1", "user_id": "U1",
        "title": "Tax filing", "due_date": due, "reminder_days_before": [5],
        "reminder_sent_days": [], "status": "pending", "category": "other",
    })
    await db.trust_state_compliance.insert_one(
        _mk_compliance(notice_next_due=(_today() + timedelta(days=2)).isoformat())
    )

    result = await runner.send_deadline_reminders()

    assert isinstance(result, dict)
    assert "task_deadlines" in result and "compliance" in result
    assert result["task_deadlines"] == 1  # one task deadline fired
    assert result["compliance"] == 1      # one compliance reminder fired


# --------------------------------------------------------------------------- #
# Template renders without error (catches f-string / lambda mistakes)
# --------------------------------------------------------------------------- #
def test_compliance_template_renders():
    data = {
        "user_name": "Owner", "trust_name": "Demo Trust",
        "state_code": "CA", "state_name": "California",
        "act": "beneficiary notice", "due_date": "2026-10-01",
        "is_overdue": False, "days_remaining": 10,
        "app_url": "https://trustoffice.app",
    }
    rendered = render_template("compliance_deadline_reminder", data)
    assert "beneficiary notice" in rendered["subject"].lower()
    assert "https://trustoffice.app/governance?tab=state" in rendered["html"]
    assert "governance?tab=state" in rendered["text"]

    overdue = dict(data, is_overdue=True, days_remaining=None, days_overdue=5)
    rendered2 = render_template("compliance_deadline_reminder", overdue)
    assert "overdue" in rendered2["subject"].lower()
    assert "lowers" in rendered2["html"].lower()
