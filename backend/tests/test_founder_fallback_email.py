"""Founder fallback email tests (TrustOffice × Bland lane, 2026-11-18).

Covers the instant founder fallback email wired in routers/leads_service.py
via the shared _apply_call_outcome path (POST /{lead_id}/call-outcome AND the
Bland webhook receiver's mapped path):

  - trigger matrix: callback_requested -> sends; booked WITHOUT booking_ref ->
    sends; booked WITH booking_ref -> no send (booking app auto-notifies
    direct bookings); interested -> no send
  - anti-spam dedupe: max 1 per lead per 6h via the `fallback_email_sent`
    activity marker; expired markers let a new trigger send again
  - provider failure -> HTTP 200 intact, `fallback_email_failed` marker, no
    `fallback_email_sent` marker (never-configured provider behaves the same)
  - summary slot extraction (_extract_slot) + "Reported agreed slot:" surfacing
  - email contents: subject [AI CALL] <name> — <disposition>, lead fields,
    FULL summary, lead_id, confirm/hold slots URL
  - kill switch: TRUSTOFFICE_FALLBACK_EMAIL="" disables the feature

Same transport-stubbing matrix as test_bland_leads_service.py:
mongomock_motor shim, router on a minimal FastAPI app, TestClient. The
Postmark client singleton's send_email is monkeypatched per test — no
network, and NO real recipient is ever used (tests set
TRUSTOFFICE_FALLBACK_EMAIL=founder-test@example.com; empty = kill switch).
"""
import os
import sys
from datetime import datetime, timedelta, timezone

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test_fallback_email")
os.environ.setdefault("JWT_SECRET", "test-secret-fallback-email")
os.environ.setdefault("TRUSTOFFICE_LEADS_SERVICE_KEY", "test-service-key-1234")
# Kill switch OFF in this module's scope: every test monkeypatches the
# recipient explicitly, so nothing inherited from other test modules leaks
# here and nothing here leaks into other modules (monkeypatch restores).
os.environ.setdefault("TRUSTOFFICE_FALLBACK_EMAIL", "")

import motor.motor_asyncio
import mongomock_motor

motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

import database
import routers.bland_webhook as bland_webhook
import routers.leads_service as leads_service

SERVICE_KEY = "test-service-key-1234"
AUTH = {"X-Service-Key": SERVICE_KEY}
TEST_RECIPIENT = "founder-test@example.com"
SLOTS_URL = (
    "https://booking-trustoffice-production.up.railway.app/slots?days=14"
)
WEBHOOK_URL = "/api/service/bland/webhook"
SECRET = "bland-webhook-secret-test"

db = database.db


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    """Fresh collections around every test."""
    for coll in ("leads", "lead_activities", "bland_webhook_events"):
        await db[coll].delete_many({})
    yield
    for coll in ("leads", "lead_activities", "bland_webhook_events"):
        await db[coll].delete_many({})


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(leads_service.router, prefix="/api")
    return TestClient(app)


@pytest.fixture(autouse=True)
def recipient_on(monkeypatch):
    """Test recipient for every test — never the real founder address."""
    monkeypatch.setenv("TRUSTOFFICE_FALLBACK_EMAIL", TEST_RECIPIENT)


@pytest.fixture
def sender(monkeypatch):
    """Patch the Postmark singleton's send_email; records every call."""
    calls = []

    async def fake_send(**kwargs):
        calls.append(kwargs)
        return {"status": "sent", "message_id": f"pm_test_{len(calls)}"}

    monkeypatch.setattr(leads_service._email_service, "send_email", fake_send)
    return calls


async def _seed(stage="new", **overrides):
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "lead_id": "lead_q",
        "name": "Norm Test",
        "email": "norm@example.com",
        "phone": "+15551230000",
        "stage": stage,
        "source": "unit-test",
        "created_at": now,
        "updated_at": now,
        "notes": 0,
    }
    doc.update(overrides)
    await db.leads.insert_one(doc)


def _outcome_url(lead_id="lead_q"):
    return f"/api/service/leads/{lead_id}/call-outcome"


async def _activities(action_type=None, lead_id="lead_q"):
    query = {"lead_id": lead_id}
    if action_type:
        query["action_type"] = action_type
    return await db.lead_activities.find(query).to_list(None)


# ==================== TRIGGER MATRIX (call-outcome endpoint) ====================


class TestTriggerMatrix:
    @pytest.mark.asyncio
    async def test_callback_requested_sends(self, client, sender):
        await _seed(stage="new")
        r = client.post(
            _outcome_url(),
            headers=AUTH,
            json={
                "disposition": "callback_requested",
                "summary": "Asked us to call back tomorrow at 3pm",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["stage"] == "new"  # stage unchanged
        assert len(sender) == 1
        sent = sender[0]
        assert sent["to_email"] == TEST_RECIPIENT
        assert sent["subject"] == "[AI CALL] Norm Test — callback_requested"
        assert sent["tag"] == "ai-call-fallback"
        assert sent["metadata"]["lead_id"] == "lead_q"
        markers = await _activities("fallback_email_sent")
        assert len(markers) == 1
        assert "callback_requested" in markers[0]["content"]

    @pytest.mark.asyncio
    async def test_booked_without_ref_sends(self, client, sender):
        await _seed(stage="warm")
        r = client.post(
            _outcome_url(),
            headers=AUTH,
            json={"disposition": "booked", "summary": "booked, ref pending"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["stage"] == "engaged"
        assert len(sender) == 1
        markers = await _activities("fallback_email_sent")
        assert len(markers) == 1

    @pytest.mark.asyncio
    async def test_booked_with_ref_does_not_send(self, client, sender):
        await _seed(stage="new")
        r = client.post(
            _outcome_url(),
            headers=AUTH,
            json={
                "disposition": "booked",
                "summary": "confirmed",
                "booking_ref": "hold_abc123",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["stage"] == "engaged"
        assert sender == []
        assert await _activities("fallback_email_sent") == []
        assert await _activities("fallback_email_failed") == []

    @pytest.mark.asyncio
    async def test_interested_does_not_send(self, client, sender):
        await _seed(stage="new")
        r = client.post(
            _outcome_url(),
            headers=AUTH,
            json={"disposition": "interested", "summary": "curious"},
        )
        assert r.status_code == 200, r.text
        assert sender == []
        assert await _activities("fallback_email_sent") == []

    @pytest.mark.asyncio
    async def test_not_interested_opt_out_do_not_send(self, client, sender):
        await _seed(stage="new")
        for disposition in ("not_interested", "opt_out"):
            sender.clear()
            r = client.post(
                _outcome_url(),
                headers=AUTH,
                json={"disposition": disposition},
            )
            assert r.status_code == 200, r.text
            assert sender == []
        assert await _activities("fallback_email_sent") == []


# ==================== EMAIL CONTENTS ====================


class TestEmailContents:
    @pytest.mark.asyncio
    async def test_body_has_lead_fields_summary_slot_and_cta(
        self, client, sender
    ):
        await _seed(stage="warm")
        summary = (
            "Norm agreed to a governance consult on Tuesday, November 24 at "
            "2:00 PM. Direct booking failed so no reference was issued."
        )
        r = client.post(
            _outcome_url(),
            headers=AUTH,
            json={"disposition": "callback_requested", "summary": summary},
        )
        assert r.status_code == 200, r.text
        assert len(sender) == 1
        sent = sender[0]
        # Slot surfaced prominently in both bodies
        assert "Reported agreed slot: Tuesday, November 24 at 2:00 PM" in (
            sent["text_body"]
        )
        assert "Reported agreed slot: Tuesday, November 24 at 2:00 PM" in (
            sent["html_body"]
        )
        # Lead identity + FULL summary + lead_id + CTA
        assert "Norm Test" in sent["text_body"]
        assert "norm@example.com" in sent["text_body"]
        assert "+15551230000" in sent["text_body"]
        assert "warm" in sent["text_body"]
        assert "lead_id: lead_q" in sent["text_body"]
        assert summary in sent["text_body"]  # FULL summary, uncut
        assert f"Confirm/hold the slot now: {SLOTS_URL}" in sent["text_body"]
        assert f'<a href="{SLOTS_URL}">' in sent["html_body"]
        # HTML escapes the raw summary
        assert "Norm agreed" in sent["html_body"]

    @pytest.mark.asyncio
    async def test_no_slot_line_when_summary_has_no_slot(
        self, client, sender
    ):
        await _seed()
        r = client.post(
            _outcome_url(),
            headers=AUTH,
            json={
                "disposition": "callback_requested",
                "summary": "Wants a call back sometime next week",
            },
        )
        assert r.status_code == 200, r.text
        assert len(sender) == 1
        assert "Reported agreed slot:" not in sender[0]["text_body"]
        assert "Reported agreed slot:" not in sender[0]["html_body"]


# ==================== ANTI-SPAM DEDUPE (6h window) ====================


class TestDedupe:
    @pytest.mark.asyncio
    async def test_second_trigger_within_window_suppressed(
        self, client, sender
    ):
        await _seed()
        for _ in range(2):
            r = client.post(
                _outcome_url(),
                headers=AUTH,
                json={"disposition": "callback_requested", "summary": "s"},
            )
            assert r.status_code == 200, r.text
        assert len(sender) == 1  # 1 sent, 1 suppressed
        sent_markers = await _activities("fallback_email_sent")
        assert len(sent_markers) == 1

    @pytest.mark.asyncio
    async def test_recent_marker_blocks_but_expired_marker_allows(
        self, client, sender
    ):
        await _seed()
        for age_hours, expect_send in ((5, False), (7, True)):
            sender.clear()
            await db.lead_activities.delete_many({})
            await db.lead_activities.insert_one(
                {
                    "activity_id": f"act_seed_{age_hours}",
                    "lead_id": "lead_q",
                    "action_type": "fallback_email_sent",
                    "content": "prior send",
                    "created_at": datetime.now(timezone.utc)
                    - timedelta(hours=age_hours),
                }
            )
            r = client.post(
                _outcome_url(),
                headers=AUTH,
                json={"disposition": "callback_requested", "summary": "s"},
            )
            assert r.status_code == 200, r.text
            assert len(sender) == (1 if expect_send else 0), (
                f"marker age {age_hours}h: send={len(sender)}"
            )

    @pytest.mark.asyncio
    async def test_window_is_6_hours(self):
        assert leads_service.FALLBACK_EMAIL_DEDUPE_HOURS == 6


# ==================== PROVIDER FAILURE / RESPONSE SAFETY ====================


class TestSendFailure:
    @pytest.mark.asyncio
    async def test_provider_failure_keeps_200_and_marks_failed(
        self, client, monkeypatch
    ):
        async def failing_send(**kwargs):
            return {"status": "failed", "error": "postmark: 503 upstream"}

        monkeypatch.setattr(
            leads_service._email_service, "send_email", failing_send
        )
        await _seed(stage="warm")
        r = client.post(
            _outcome_url(),
            headers=AUTH,
            json={
                "disposition": "booked",
                "summary": "claimed booked but app errored",
            },
        )
        assert r.status_code == 200, r.text  # response intact
        assert r.json()["stage"] == "engaged"  # outcome write unaffected
        failed = await _activities("fallback_email_failed")
        assert len(failed) == 1
        assert "503 upstream" in failed[0]["content"]
        assert await _activities("fallback_email_sent") == []

    @pytest.mark.asyncio
    async def test_unconfigured_provider_also_marks_failed(
        self, client, monkeypatch
    ):
        """not_configured is a non-sent status -> failure marker (retryable)."""
        monkeypatch.setattr(
            leads_service._email_service, "server_token", "", raising=False
        )
        monkeypatch.delenv("POSTMARK_SERVER_TOKEN", raising=False)
        await _seed()
        r = client.post(
            _outcome_url(),
            headers=AUTH,
            json={"disposition": "callback_requested", "summary": "s"},
        )
        assert r.status_code == 200, r.text
        failed = await _activities("fallback_email_failed")
        assert len(failed) == 1
        assert "not_configured" in failed[0]["content"]

    @pytest.mark.asyncio
    async def test_sender_exception_keep_200_and_failed_marker(
        self, client, monkeypatch
    ):
        async def exploding_send(**kwargs):
            raise RuntimeError("postmark client exploded")

        monkeypatch.setattr(
            leads_service._email_service, "send_email", exploding_send
        )
        await _seed()
        r = client.post(
            _outcome_url(),
            headers=AUTH,
            json={"disposition": "callback_requested", "summary": "s"},
        )
        assert r.status_code == 200, r.text
        failed = await _activities("fallback_email_failed")
        assert len(failed) == 1
        assert "pipeline error" in failed[0]["content"].lower()


# ==================== KILL SWITCH ====================


class TestKillSwitch:
    @pytest.mark.asyncio
    async def test_empty_recipient_disables_feature(self, client, sender,
                                                    monkeypatch):
        monkeypatch.setenv("TRUSTOFFICE_FALLBACK_EMAIL", "")
        await _seed()
        r = client.post(
            _outcome_url(),
            headers=AUTH,
            json={"disposition": "callback_requested", "summary": "s"},
        )
        assert r.status_code == 200, r.text
        assert sender == []
        assert await _activities("fallback_email_sent") == []
        assert await _activities("fallback_email_failed") == []


# ==================== SLOT EXTRACTION (pure) ====================


class TestExtractSlot:
    @pytest.mark.parametrize(
        "summary,expected",
        [
            (
                "Consult booked for Tuesday, November 24 at 2:00 PM by all",
                "Tuesday, November 24 at 2:00 PM",
            ),
            # Day-only or time-only chunks never qualify (a slot is date+time)
            ("Call Tuesday morning", None),
            ("She mentioned 2 PM", None),
            ("works", None),
            ("", None),
            (None, None),
            ("She said 14:00 on 11/24 works", "14:00 on 11/24"),
            ("follow up tomorrow at 10am", "tomorrow at 10am"),
            # "3:25 minutes" is a duration, not a clock time
            ("spoke Tuesday, then talked 3:25 minutes", None),
            ("no slot discussed, follow up by email", None),
        ],
    )
    def test_cases(self, summary, expected):
        assert leads_service._extract_slot(summary) == expected


# ==================== WEBHOOK PATH (shared helper parity) ====================


class TestWebhookPath:
    @pytest.fixture
    def webhook_client(self):
        app = FastAPI()
        app.include_router(bland_webhook.router, prefix="/api")
        return TestClient(app)

    def _payload(self, disposition: str, summary: str):
        return {
            "call_id": "12345678-1234-1234-1234-123456789012",
            "status": "completed",
            "completed": True,
            "call_length": 0.18,
            "answered_by": "human",
            "queue_status": "complete",
            "summary": summary,
            "metadata": {"lead_id": "lead_q"},
            "disposition_tag": disposition,
        }

    @pytest.mark.asyncio
    async def test_webhook_callback_requested_triggers_fallback(
        self, webhook_client, sender, monkeypatch
    ):
        monkeypatch.setenv("BLAND_WEBHOOK_SECRET", SECRET)
        await _seed(stage="new")
        r = webhook_client.post(
            WEBHOOK_URL,
            headers={"X-Webhook-Secret": SECRET},
            json=self._payload("Callback Requested", "call back tuesday 2 pm"),
        )
        assert r.status_code == 200, r.text
        assert r.json()["disposition"] == "callback_requested"
        assert len(sender) == 1
        assert sender[0]["subject"] == "[AI CALL] Norm Test — callback_requested"
        assert "Reported agreed slot: tuesday 2 pm" in sender[0]["text_body"]
        markers = await _activities("fallback_email_sent")
        assert len(markers) == 1

    @pytest.mark.asyncio
    async def test_webhook_booked_triggers_fallback(self, webhook_client,
                                                    sender, monkeypatch):
        monkeypatch.setenv("BLAND_WEBHOOK_SECRET", SECRET)
        await _seed(stage="new")
        r = webhook_client.post(
            WEBHOOK_URL,
            headers={"X-Webhook-Secret": SECRET},
            json=self._payload("Booked", "she confirmed but app had an error"),
        )
        assert r.status_code == 200, r.text
        assert r.json()["disposition"] == "booked"
        assert len(sender) == 1
        assert "booked" in sender[0]["subject"]
        markers = await _activities("fallback_email_sent")
        assert len(markers) == 1

    @pytest.mark.asyncio
    async def test_webhook_interested_does_not_send(self, webhook_client,
                                                    sender, monkeypatch):
        monkeypatch.setenv("BLAND_WEBHOOK_SECRET", SECRET)
        await _seed(stage="new")
        r = webhook_client.post(
            WEBHOOK_URL,
            headers={"X-Webhook-Secret": SECRET},
            json=self._payload("Interested", "wants more info"),
        )
        assert r.status_code == 200, r.text
        assert sender == []
        assert await _activities("fallback_email_sent") == []
