"""2026-10-23 fix bundle: contact-form -> lead wiring, alert resilience,
demand-based pipeline monitor.

Covers the three defects found in the 2026-10-23 lead-flow audit:

  1. Alert resilience: notify_pipeline_alert / notify_alert must (a) log at
     ERROR and return success=False loudly when no webhook is configured or
     the POST fails, and (b) fall back to the hard-coded alert webhook
     instead of dropping the alert. Plus a startup assertion in the app
     factory that shouts if both alert env vars are missing.

  2. Contact form wiring: routers/contact.py submit_contact_form must
     upsert into db.leads (source='contact-page', duplicate-check on email),
     call notify_new_lead + create_notification(type='new_lead'), send the
     email rail to kenneth@agentictrust.app, and store lead_id back on the
     submission doc.

  3. Pipeline monitor: the throughput floor must be measured against DEMAND
     (sends that were due in the window) rather than a flat 10% of the
     eligible cohort, so a quiet day is not a false RED while a genuinely
     stuck drip still goes RED.

Uses an in-memory mongomock_motor shim exposing the motor-style async API.
No real DB or network is touched: Discord and email sends are mocked.
"""
import logging
import os
import sys
import types
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_database")
os.environ.setdefault("JWT_SECRET", "test-secret-for-tests")

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import mongomock_motor

import discord_service as discord_module
import leads_monitor
import routers.contact as contact_module


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def db():
    client = mongomock_motor.AsyncMongoMockClient()
    return client["test_database"]


@pytest.fixture(autouse=True)
def mock_outbound(monkeypatch):
    """Every outbound rail is mocked - nothing leaves the process."""
    discord_calls = []

    async def _notify_new_lead(**kwargs):
        discord_calls.append(kwargs)
        return {"success": True}

    async def _create_notification(**kwargs):
        discord_calls.append({"notification": kwargs})
        return {"notification_id": "notif_test"}

    sent_emails = []

    async def _send_email(**kwargs):
        sent_emails.append(kwargs)
        return {"status": "sent", "message_id": "test-msg-id"}

    monkeypatch.setattr(contact_module, "notify_new_lead", _notify_new_lead)
    monkeypatch.setattr(contact_module, "create_notification", _create_notification)
    monkeypatch.setattr(contact_module.email_service, "send_email", _send_email)
    # is_configured is a read-only property on EmailService - patch the
    # underlying token so the property reports True.
    monkeypatch.setattr(contact_module.email_service, "server_token", "test-token")

    return {"discord": discord_calls, "emails": sent_emails}


class _FakeRequest:
    def __init__(self, ip="10.0.0.1"):
        self.client = types.SimpleNamespace(host=ip)
        self.headers = {"User-Agent": "pytest"}


# --------------------------------------------------------------------------- #
# 1. Alert resilience
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_pipeline_alert_falls_back_when_primary_unset(monkeypatch):
    """An unconfigured primary alert webhook must NOT drop the alert."""
    monkeypatch.setattr(discord_module, "DISCORD_TRUSTOFFICE_MAIN_WEBHOOK_URL", None)
    monkeypatch.setattr(discord_module, "DISCORD_ALERT_FALLBACK_WEBHOOK_URL", "https://fallback.example/webhook")

    posted = {}

    async def _fake_send(webhook_url, content, **kwargs):
        posted["url"] = webhook_url
        return {"success": True}

    monkeypatch.setattr(discord_module, "send_discord_message", _fake_send)

    res = await discord_module.notify_pipeline_alert(
        title="RED", message="boom", details={"a": 1}, alert_level="red"
    )
    assert res["success"] is True
    assert posted["url"] == "https://fallback.example/webhook"


@pytest.mark.asyncio
async def test_pipeline_alert_uses_primary_when_set(monkeypatch):
    monkeypatch.setattr(discord_module, "DISCORD_TRUSTOFFICE_MAIN_WEBHOOK_URL", "https://primary.example/webhook")
    monkeypatch.setattr(discord_module, "DISCORD_ALERT_FALLBACK_WEBHOOK_URL", "https://fallback.example/webhook")

    posted = {}

    async def _fake_send(webhook_url, content, **kwargs):
        posted["url"] = webhook_url
        return {"success": True}

    monkeypatch.setattr(discord_module, "send_discord_message", _fake_send)

    await discord_module.notify_pipeline_alert(title="RED", message="boom")
    assert posted["url"] == "https://primary.example/webhook"


@pytest.mark.asyncio
async def test_pipeline_alert_logs_error_when_nothing_configured(monkeypatch, caplog):
    """With no webhook at all, the notifier must shout at ERROR level."""
    monkeypatch.setattr(discord_module, "DISCORD_TRUSTOFFICE_MAIN_WEBHOOK_URL", None)
    monkeypatch.setattr(discord_module, "DISCORD_ALERT_FALLBACK_WEBHOOK_URL", None)

    with caplog.at_level(logging.ERROR):
        res = await discord_module.notify_pipeline_alert(title="RED", message="boom")

    assert res["success"] is False
    assert res.get("dropped") is True
    assert any(r.levelno >= logging.ERROR for r in caplog.records)
    assert any("RED ALERT" in r.message or "NOT SENT" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_pipeline_alert_logs_error_on_delivery_failure(monkeypatch, caplog):
    """A failed POST must be logged at ERROR, not swallowed."""
    monkeypatch.setattr(discord_module, "DISCORD_TRUSTOFFICE_MAIN_WEBHOOK_URL", "https://primary.example/webhook")

    async def _fake_send(webhook_url, content, **kwargs):
        return {"success": False, "error": "500 boom"}

    monkeypatch.setattr(discord_module, "send_discord_message", _fake_send)

    with caplog.at_level(logging.ERROR):
        res = await discord_module.notify_pipeline_alert(title="RED", message="boom")

    assert res["success"] is False
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


@pytest.mark.asyncio
async def test_notify_alert_falls_back_and_reports_failure(monkeypatch, caplog):
    monkeypatch.setattr(discord_module, "DISCORD_ALERTS_WEBHOOK_URL", None)
    monkeypatch.setattr(discord_module, "DISCORD_LEADS_WEBHOOK_URL", None)
    monkeypatch.setattr(discord_module, "DISCORD_ALERT_FALLBACK_WEBHOOK_URL", "https://fallback.example/webhook")

    posted = {}

    async def _fake_send(webhook_url, content, **kwargs):
        posted["url"] = webhook_url
        return {"success": True}

    monkeypatch.setattr(discord_module, "send_discord_message", _fake_send)

    with caplog.at_level(logging.ERROR):
        res = await discord_module.notify_alert(title="ALERT", message="boom")

    assert res["success"] is True
    assert posted["url"] == "https://fallback.example/webhook"
    # The fallback use itself is an ERROR-level event - it means an env var
    # is missing on the service and someone must fix it.
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


def test_missing_alert_webhook_env_reports_both(monkeypatch):
    monkeypatch.setattr(discord_module, "DISCORD_TRUSTOFFICE_MAIN_WEBHOOK_URL", None)
    monkeypatch.setattr(discord_module, "DISCORD_ALERTS_WEBHOOK_URL", None)
    missing = discord_module.missing_alert_webhook_env()
    assert "DISCORD_TRUSTOFFICE_MAIN_WEBHOOK_URL" in missing
    assert "DISCORD_ALERTS_WEBHOOK_URL" in missing

    monkeypatch.setattr(discord_module, "DISCORD_TRUSTOFFICE_MAIN_WEBHOOK_URL", "https://x")
    monkeypatch.setattr(discord_module, "DISCORD_ALERTS_WEBHOOK_URL", "https://y")
    assert discord_module.missing_alert_webhook_env() == []


# --------------------------------------------------------------------------- #
# 2. Contact form -> lead wiring
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_contact_form_creates_lead_and_notifies(db, mock_outbound, monkeypatch):
    monkeypatch.setattr(contact_module, "db", db)

    result = await contact_module.submit_contact_form(
        contact_module.ContactSubmission(
            name="Kit Probe",
            email="kit-contact-fix-probe@trustoffice.app",
            message="This is a probe message long enough to pass validation.",
        ),
        _FakeRequest(),
    )

    assert result["success"] is True
    lead_id = result["lead_id"]
    assert lead_id

    # Lead exists with the right shape.
    lead = await db.leads.find_one({"email": "kit-contact-fix-probe@trustoffice.app"})
    assert lead is not None
    assert lead["lead_id"] == lead_id
    assert lead["source"] == "contact-page"
    assert lead["origin_source"] == "contact-page"
    assert lead["stage"] == "new"
    assert lead["nurture_step_sent"] == 0

    # Submission doc keeps the message and carries the lead back-reference.
    sub = await db.contact_submissions.find_one({"submission_id": result["submission_id"]})
    assert sub is not None
    assert sub["lead_id"] == lead_id
    assert "probe message" in sub["message"]

    # Discord new-lead notification fired.
    lead_calls = [c for c in mock_outbound["discord"] if "email" in c]
    assert lead_calls, "notify_new_lead was not called"
    assert lead_calls[0]["source"] == "contact-page"
    assert lead_calls[0]["email"] == "kit-contact-fix-probe@trustoffice.app"

    # In-app notification fired.
    notif_calls = [c for c in mock_outbound["discord"] if "notification" in c]
    assert notif_calls, "create_notification was not called"
    assert notif_calls[0]["notification"]["type"] == "new_lead"
    assert notif_calls[0]["notification"]["lead_id"] == lead_id

    # Email rail fired to the human-facing address.
    assert mock_outbound["emails"], "no email was sent"
    new_lead_mail = [
        e for e in mock_outbound["emails"]
        if e.get("to_email") == "kenneth@agentictrust.app"
    ]
    assert new_lead_mail, "no new-lead email to kenneth@agentictrust.app"
    assert new_lead_mail[0]["subject"] == "New TrustOffice lead: Kit Probe"


@pytest.mark.asyncio
async def test_contact_form_duplicate_email_updates_existing_lead(db, mock_outbound, monkeypatch):
    """Duplicate check on email: second submission reuses the same lead."""
    monkeypatch.setattr(contact_module, "db", db)

    payload = dict(
        name="Kit Probe",
        email="kit-contact-fix-probe@trustoffice.app",
        message="First message long enough to pass validation rules.",
    )
    first = await contact_module.submit_contact_form(
        contact_module.ContactSubmission(**payload), _FakeRequest()
    )
    second = await contact_module.submit_contact_form(
        contact_module.ContactSubmission(**payload), _FakeRequest()
    )

    assert first["lead_id"] == second["lead_id"]
    assert await db.leads.count_documents({"email": payload["email"]}) == 1

    # The second submission still records its own message and lead link.
    sub = await db.contact_submissions.find_one({"submission_id": second["submission_id"]})
    assert sub["lead_id"] == first["lead_id"]

    # The duplicate must not re-fire the new-lead fan-out.
    lead_calls = [c for c in mock_outbound["discord"] if "email" in c]
    assert len(lead_calls) == 1


# --------------------------------------------------------------------------- #
# 3. Demand-based pipeline monitor
# --------------------------------------------------------------------------- #
def _lead(lead_id, step, anchor_hours_ago, **over):
    """A cohort lead anchored `anchor_hours_ago` hours in the past.

    The drip schedule anchors on the step-1 timestamp, so the next step's
    due time is anchor + N days. Hours give the test the precision it needs
    to place a due time inside or outside the trailing 24h window.
    """
    anchor = datetime.now(timezone.utc) - timedelta(hours=anchor_hours_ago)
    doc = {
        "lead_id": lead_id,
        "email": f"{lead_id}@example.com",
        "name": "Lead",
        "stage": "new",
        "nurture_step_sent": step,
        "nurture_step1_sent_at": anchor.isoformat(),
        "created_at": anchor.isoformat(),
    }
    doc.update(over)
    return doc


@pytest.mark.asyncio
async def test_monitor_quiet_day_is_not_red(db, monkeypatch):
    """Cohort of 130 leads, nothing due in the window -> NOT a failure.

    This is the false-RED that has been firing in production: 7 sends/24h
    against a flat floor of 13 while zero sends were actually due.
    """
    calls = []

    async def _notify(**kwargs):
        calls.append(kwargs)
        return {"success": True}

    # 130 leads, all anchored so their next step is far in the future.
    for i in range(130):
        await db.leads.insert_one(_lead(f"Q{i}", 7, 24))
    # One recent nurture send so assert-1 has a non-zero baseline.
    await db.lead_activities.insert_one({
        "activity_id": "act1",
        "lead_id": "Q0",
        "action_type": "email",
        "content": "Sent nurture email 7/12 via MailerCloud",
        "created_at": datetime.now(timezone.utc),
    })

    result = await leads_monitor.check_leads_pipeline_health(db, notify=_notify)

    assert result["all_ok"] is True, result["failures"]
    assert result["eligible_cohort"] == 130
    assert result["sends_due_in_window"] == 0
    assert not calls, "a quiet day must not page anyone"


@pytest.mark.asyncio
async def test_monitor_red_when_due_sends_do_not_go_out(db, monkeypatch):
    """A due send that never goes out is a real failure -> RED."""
    calls = []

    async def _notify(**kwargs):
        calls.append(kwargs)
        return {"success": True}

    # Step 2 fires on day 3 after the anchor: anchor 5 days ago -> due now.
    for i in range(5):
        await db.leads.insert_one(_lead(f"D{i}", 1, 76))

    result = await leads_monitor.check_leads_pipeline_health(db, notify=_notify)

    assert result["all_ok"] is False
    assert result["sends_due_in_window"] == 5
    assert result["sends_last_24h"] == 0
    assert len(calls) == 1
    assert calls[0]["alert_level"] == "red"


@pytest.mark.asyncio
async def test_monitor_red_when_due_sends_are_overdue(db, monkeypatch):
    """A send due well past the grace window and never sent -> RED."""
    calls = []

    async def _notify(**kwargs):
        calls.append(kwargs)
        return {"success": True}

    # Step 2 due on day 3; anchor 10 days ago -> due 7 days ago, long past
    # the 12h grace window, and no send ever happened.
    await db.leads.insert_one(_lead("OV", 1, 240))

    result = await leads_monitor.check_leads_pipeline_health(db, notify=_notify)

    assert result["all_ok"] is False
    assert result["sends_overdue"] == 1
    assert any("overdue" in f.lower() or "not sent" in f.lower() for f in result["failures"])
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_monitor_logs_error_level_on_red(db, caplog):
    """The monitor itself must log the failure at ERROR, not INFO."""
    async def _notify(**kwargs):
        return {"success": True}

    await db.leads.insert_one(_lead("LG", 1, 240))

    with caplog.at_level(logging.ERROR):
        result = await leads_monitor.check_leads_pipeline_health(db, notify=_notify)

    assert result["all_ok"] is False
    assert any(r.levelno >= logging.ERROR for r in caplog.records)
    assert any("RED" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_monitor_reports_undelivered_alert(db, caplog):
    """A notifier that did not report success is itself a monitor failure."""
    async def _notify(**kwargs):
        return {"success": False, "error": "webhook not configured"}

    await db.leads.insert_one(_lead("UD", 1, 240))

    with caplog.at_level(logging.ERROR):
        result = await leads_monitor.check_leads_pipeline_health(db, notify=_notify)

    assert result["all_ok"] is False
    assert any("NOT DELIVERED" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_monitor_survives_notifier_exception(db, caplog):
    async def _notify(**kwargs):
        raise RuntimeError("network down")

    await db.leads.insert_one(_lead("EX", 1, 240))

    with caplog.at_level(logging.ERROR):
        result = await leads_monitor.check_leads_pipeline_health(db, notify=_notify)

    # The monitor must not crash, and must record the failure loudly.
    assert result["all_ok"] is False
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


# --------------------------------------------------------------------------- #
# 4. Confirm-before-alert (two-strike rule, 2026-10-28)
#
# Production evidence: at 2026-10-29T00:52:17Z the monitor paged RED claiming
# "8 sends/24h < floor 30" while the drip batch satisfying the floor committed
# its 30 activity rows at 00:52:16.924Z — the monitor read a torn snapshot
# 0.9s ahead of the batch. A single RED snapshot is not evidence; two
# consecutive REDs (the re-check settling after the batch) are.
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def zero_recheck(monkeypatch):
    """Make the two-strike re-check instant in tests."""
    monkeypatch.setattr(leads_monitor, "_recheck_delay", lambda result: 0.0)


@pytest.mark.asyncio
async def test_monitor_race_resolves_before_second_strike(db, caplog):
    """The 00:52Z production race: snapshot #1 fails, the drip batch commits,
    snapshot #2 is green -> NO Discord page. The RED must never leave the box."""
    calls = []

    async def _notify(**kwargs):
        calls.append(kwargs)
        return {"success": True}

    # 5 leads due right now (anchor 5 days ago, step 2 due on day 3)...
    for i in range(5):
        await db.leads.insert_one(_lead(f"R{i}", 1, 76))
    # ...and exactly the torn state the monitor saw mid-drip: sends not yet counted.
    with caplog.at_level(logging.WARNING):
        # Simulate the drip committing BETWEEN the two snapshots: the shared db
        # object's leads collection returns fresh docs after the wrapper runs.
        original = leads_monitor._run_asserts
        first_done = []

        async def _run_asserts_with_commit(db_arg, notify=None):
            if not first_done:
                first_done.append(True)
                return await original(db_arg, notify=notify)
            # Commit the drip batch BEFORE the confirming snapshot so snapshot
            # #2 observes post-batch state (sends counted, steps advanced).
            for i in range(5):
                await db_arg.leads.update_one(
                    {"lead_id": f"R{i}"},
                    {"$set": {"nurture_step_sent": 2}},
                )
                await db_arg.lead_activities.insert_one({
                    "activity_id": f"race{i}",
                    "lead_id": f"R{i}",
                    "action_type": "email",
                    "content": "Sent nurture email 2/12 via MailerCloud",
                    "created_at": datetime.now(timezone.utc),
                })
            return await original(db_arg, notify=notify)

        leads_monitor._run_asserts = _run_asserts_with_commit
        try:
            result = await leads_monitor.check_leads_pipeline_health(db, notify=_notify)
        finally:
            leads_monitor._run_asserts = original

    assert calls == [], "a race-resolved RED must never page Discord"
    assert result["all_ok"] is True
    assert any("RESOLVED between snapshots" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_monitor_pages_only_after_two_consecutive_reds(db, caplog):
    """A real stall fails BOTH snapshots -> exactly one RED page, after re-check."""
    calls = []

    async def _notify(**kwargs):
        calls.append(kwargs)
        return {"success": True}

    # Step 2 due on day 3; anchor 5 days ago -> due now; nothing ever sends.
    for i in range(5):
        await db.leads.insert_one(_lead(f"S{i}", 1, 76))

    with caplog.at_level(logging.ERROR):
        result = await leads_monitor.check_leads_pipeline_health(db, notify=_notify)

    assert result["all_ok"] is False
    assert len(calls) == 1, "one confirmed RED -> exactly one page"
    assert calls[0]["alert_level"] == "red"
    assert any("snapshot #1" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_monitor_single_snapshot_green_never_rechecks(db, caplog):
    """Healthy pipeline: one snapshot, green, no re-check, no page."""
    calls = []

    async def _notify(**kwargs):
        calls.append(kwargs)
        return {"success": True}

    await db.leads.insert_one(_lead("G1", 7, 24))
    await db.lead_activities.insert_one({
        "activity_id": "g1",
        "lead_id": "G1",
        "action_type": "email",
        "content": "Sent nurture email 7/12 via MailerCloud",
        "created_at": datetime.now(timezone.utc),
    })

    with caplog.at_level(logging.INFO):
        result = await leads_monitor.check_leads_pipeline_health(db, notify=_notify)

    assert result["all_ok"] is True
    assert not calls
    assert not any("snapshot #1" in r.message for r in caplog.records)
