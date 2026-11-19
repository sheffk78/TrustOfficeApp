"""Bland.ai call-completed webhook receiver tests (batch-mode lane).

Covers routers/bland_webhook.py mounted at /api/service/bland/webhook:
  - secret gating: BLAND_WEBHOOK_SECRET unset -> 503; missing/wrong header -> 401
  - deterministic mapping onto _apply_call_outcome (same path as
    POST /{lead_id}/call-outcome — incl. last_ai_call_at/ai_call_attempts)
  - unmapped dispositions / missing lead ref / unknown lead -> 202 stored,
    full raw payload always persisted to bland_webhook_events
  - malformed bodies -> 400 but still persisted; never 500
  - X-Webhook-Idempotency-Key retry dedupe (applied outcomes not re-applied)

Same transport-stubbing matrix as test_bland_leads_service.py:
mongomock_motor shim, router on a minimal FastAPI app, TestClient.
Payload shapes follow https://docs.bland.ai/tutorials/post-call-webhooks and
https://docs.bland.ai/agents/dispositions#read-the-results.
"""
import os
import sys
from datetime import datetime, timezone

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test_bland_webhook")
os.environ.setdefault("JWT_SECRET", "test-secret-bland-webhook")
os.environ.setdefault("TRUSTOFFICE_LEADS_SERVICE_KEY", "test-service-key-1234")

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

db = database.db

SECRET = "bland-webhook-secret-test"
SECRET_HEADER = {"X-Webhook-Secret": SECRET}
IDEMPOTENCY_HEADER = {"X-Webhook-Idempotency-Key": "evt-dup-1"}
WEBHOOK_URL = "/api/service/bland/webhook"


def _lead(lead_id: str, stage: str = "new"):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "lead_id": lead_id,
        "name": "Test Lead",
        "email": f"{lead_id}@example.com",
        "phone": "+12015550123",
        "stage": stage,
        "source": "unit-test",
        "created_at": now,
        "updated_at": now,
        "notes": 0,
    }


# Doc-faithful shape: agent calls carry agent_dispositions (dispositions doc,
# "Read the results"); metadata echoes the dispatcher's lead_id (Send Call
# accepts request_data/metadata/external_id — webhooks carry them back).
BOOKED_PAYLOAD = {
    "call_id": "12345678-1234-1234-1234-123456789012",
    "c_id": "12345678-1234-1234-1234-123456789012",
    "status": "completed",
    "completed": True,
    "call_length": 0.25,  # minutes per docs — 0.25*60 == 15s
    "answered_by": "human",
    "queue_status": "complete",
    "to": "+12015550123",
    "from": "+15550000000",
    "summary": "Consult booked for Tuesday morning",
    "metadata": {"call_purpose": "governance-consult", "environment": "production",
                 "lead_id": "lead_q"},
    "agent_dispositions": [
        {
            "disposition_key": "booking_outcome",
            "name": "Booking outcome",
            "status": "complete",
            "values": [
                {"key": "booked", "state": "produced", "value": True},
                {"key": "plan", "state": "produced", "value": "annual"},
            ],
            "evidence": [
                {"source": "transcript", "speaker": "customer",
                 "start_ms": 44120, "end_ms": 47890,
                 "text": "Yeah, let's go with the Tuesday consult."}
            ],
        }
    ],
}

# V1 pathway calls carry disposition_tag with values like "COMPLETED_ACTION"
# (post-call webhook doc) — NOT in our disposition vocabulary -> stored only.
UNMAPPED_PAYLOAD = {
    "call_id": "abc",
    "pathway_id": "pw-1",
    "call_length": 0.183333,
    "corrected_duration": "11",
    "queue_status": "complete",
    "disposition_tag": "COMPLETED_ACTION",
    "metadata": {"lead_id": "lead_q"},
}


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    for coll in ("leads", "lead_activities", "bland_webhook_events"):
        await db[coll].delete_many({})
    yield
    for coll in ("leads", "lead_activities", "bland_webhook_events"):
        await db[coll].delete_many({})


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(bland_webhook.router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def secret_on(monkeypatch):
    monkeypatch.setenv("BLAND_WEBHOOK_SECRET", SECRET)


# ==================== SECRET GATING ====================

class TestSecretGating:
    @pytest.mark.asyncio
    async def test_unset_secret_returns_503_and_never_opens(self, client, monkeypatch):
        monkeypatch.delenv("BLAND_WEBHOOK_SECRET", raising=False)
        r = client.post(WEBHOOK_URL, headers=SECRET_HEADER, json={"x": 1})
        assert r.status_code == 503, r.text
        assert r.json()["detail"] == "webhook not configured"
        # no auth path — nothing persisted, nothing mapped
        assert await db.bland_webhook_events.count_documents({}) == 0

    @pytest.mark.asyncio
    async def test_missing_secret_header_401(self, client, secret_on):
        r = client.post(WEBHOOK_URL, json={"x": 1})
        assert r.status_code == 401, r.text

    @pytest.mark.asyncio
    async def test_wrong_secret_401(self, client, secret_on):
        r = client.post(
            WEBHOOK_URL, headers={"X-Webhook-Secret": "nope"}, json={"x": 1}
        )
        assert r.status_code == 401, r.text
        assert await db.bland_webhook_events.count_documents({}) == 0

    @pytest.mark.asyncio
    async def test_correct_secret_proceeds(self, client, secret_on):
        r = client.post(WEBHOOK_URL, headers=SECRET_HEADER, json={})
        # valid auth + empty payload => stored-unmapped, not an auth failure
        assert r.status_code == 202, r.text
        assert r.json()["status"] == "stored_unmapped"


# ==================== MAPPED HAPPY PATH ====================

class TestMappedOutcome:
    @pytest.mark.asyncio
    async def test_booked_disposition_applies_call_outcome_logic(self, client, secret_on):
        await db.leads.insert_one(_lead("lead_q", stage="new"))
        r = client.post(WEBHOOK_URL, headers=SECRET_HEADER, json=BOOKED_PAYLOAD)
        assert r.status_code == 200, r.text
        assert r.json()["received"] is True
        assert r.json()["lead_id"] == "lead_q"
        assert r.json()["disposition"] == "booked"
        assert r.json()["stage"] == "engaged"

        lead = await db.leads.find_one({"lead_id": "lead_q"})
        assert lead["stage"] == "engaged"
        # EXACT same logic as /{lead_id}/call-outcome — cooldown stamp included
        assert lead["last_ai_call_at"].endswith("+00:00")
        assert lead["ai_call_attempts"] == 1
        # call_length 0.25 min -> 15s in the activity line
        acts = await db.lead_activities.find({"lead_id": "lead_q"}).to_list(None)
        assert any(
            a["action_type"] == "manual"
            and "AI call via Bland: booked — Consult booked for Tuesday morning (15s)"
            in (a["content"] or "")
            for a in acts
        ), [a["content"] for a in acts]

        event = await db.bland_webhook_events.find_one({})
        assert event["payload"] == BOOKED_PAYLOAD  # FULL raw payload persisted
        assert event["parse_error"] is False
        assert event["received_at"].endswith("+00:00")
        assert len(event["user_agent"]) <= 120
        assert event["mapping"]["applied"] is True
        assert event["mapping"]["disposition"] == "booked"
        assert event["mapping"]["stage"] == "engaged"

    @pytest.mark.asyncio
    async def test_user_agent_header_truncated(self, client, secret_on):
        await db.leads.insert_one(_lead("lead_q"))
        r = client.post(
            WEBHOOK_URL,
            headers={**SECRET_HEADER, "user-agent": "U" * 500},
            json={"disposition": "voicemail", "metadata": {"lead_id": "lead_q"}},
        )
        assert r.status_code == 200, r.text
        event = await db.bland_webhook_events.find_one({})
        assert len(event["user_agent"]) == 120

    @pytest.mark.asyncio
    async def test_opt_out_via_agent_dispositions(self, client, secret_on):
        await db.leads.insert_one(_lead("lead_q", stage="warm"))
        payload = {
            "metadata": {"lead_id": "lead_q"},
            "agent_dispositions": [
                {"disposition_key": "dnc",
                 "values": [{"key": "opt_out", "state": "produced",
                             "value": True}]}
            ],
        }
        r = client.post(WEBHOOK_URL, headers=SECRET_HEADER, json=payload)
        assert r.status_code == 200, r.text
        assert r.json()["disposition"] == "opt_out"
        lead = await db.leads.find_one({"lead_id": "lead_q"})
        assert lead["stage"] == "do_not_call"


# ==================== STORED-ONLY PATHS (202) ====================

class TestStoredUnmapped:
    @pytest.mark.asyncio
    async def test_unmapped_disposition_stored_202(self, client, secret_on):
        await db.leads.insert_one(_lead("lead_q"))
        r = client.post(WEBHOOK_URL, headers=SECRET_HEADER, json=UNMAPPED_PAYLOAD)
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["status"] == "stored_unmapped"
        assert body["reason"] == "disposition_unmapped"
        assert body["disposition_raw"] == "COMPLETED_ACTION"
        # lead untouched
        lead = await db.leads.find_one({"lead_id": "lead_q"})
        assert lead["stage"] == "new"
        assert "ai_call_attempts" not in lead
        assert "last_ai_call_at" not in lead
        event = await db.bland_webhook_events.find_one({})
        assert event["mapping"]["applied"] is False
        assert event["mapping"]["disposition_raw"] == "COMPLETED_ACTION"

    @pytest.mark.asyncio
    async def test_mapped_disposition_without_lead_ref_stored(self, client, secret_on):
        r = client.post(
            WEBHOOK_URL,
            headers=SECRET_HEADER,
            json={"status": "completed", "disposition": "interested",
                  "summary": "no lead echo"},
        )
        assert r.status_code == 202, r.text
        assert r.json()["reason"] == "no_lead_ref"

    @pytest.mark.asyncio
    async def test_unknown_lead_id_stored(self, client, secret_on):
        r = client.post(
            WEBHOOK_URL,
            headers=SECRET_HEADER,
            json={"disposition": "interested", "metadata": {"lead_id": "nope-123"}},
        )
        assert r.status_code == 202, r.text
        assert r.json()["reason"] == "lead_not_found"

    @pytest.mark.asyncio
    async def test_external_id_echo_resolves_lead(self, client, secret_on):
        """Dispatcher may echo the ref as external_id (Send Call param)."""
        await db.leads.insert_one(_lead("lead_q"))
        r = client.post(
            WEBHOOK_URL,
            headers=SECRET_HEADER,
            json={"external_id": "lead_q", "disposition": "no_answer"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["disposition"] == "no_answer"
        lead = await db.leads.find_one({"lead_id": "lead_q"})
        assert lead["ai_call_attempts"] == 1

    @pytest.mark.asyncio
    async def test_summary_falls_back_to_transcript_tail(self, client, secret_on):
        await db.leads.insert_one(_lead("lead_q"))
        payload = {
            "external_id": "lead_q", "disposition": "interested",
            "concatenated_transcript": "Agent: Hello... " + "filler " * 60
                                       + "Customer: sounds good",
        }
        r = client.post(WEBHOOK_URL, headers=SECRET_HEADER, json=payload)
        assert r.status_code == 200, r.text
        acts = await db.lead_activities.find({"lead_id": "lead_q"}).to_list(None)
        assert any("Transcript tail:" in (a["content"] or "") for a in acts)


# ==================== GARBAGE HANDLING ====================

class TestMalformedBodies:
    @pytest.mark.asyncio
    async def test_unparsable_body_400_but_persisted(self, client, secret_on):
        r = client.post(WEBHOOK_URL, headers=SECRET_HEADER,
                        content=b"\x00\x01{not json at all")
        assert r.status_code == 400, r.text
        assert r.json()["status"] == "invalid_payload"
        event = await db.bland_webhook_events.find_one({})
        assert event["parse_error"] is True
        assert "{not json at all" in event["raw_body"]

    @pytest.mark.asyncio
    async def test_non_object_json_400_but_persisted(self, client, secret_on):
        r = client.post(WEBHOOK_URL, headers=SECRET_HEADER, content=b"[1, 2, 3]")
        assert r.status_code == 400, r.text
        event = await db.bland_webhook_events.find_one({})
        assert event["parse_error"] is True
        assert event["raw_body"] == "[1, 2, 3]"

    @pytest.mark.asyncio
    async def test_empty_body_400(self, client, secret_on):
        r = client.post(WEBHOOK_URL, headers=SECRET_HEADER, content=b"")
        assert r.status_code == 400, r.text
        assert await db.bland_webhook_events.count_documents({}) == 1


# ==================== RETRY / IDEMPOTENCY ====================

class TestIdempotencyDedupe:
    @pytest.mark.asyncio
    async def test_retried_event_not_reapplied(self, client, secret_on):
        await db.leads.insert_one(_lead("lead_q"))
        first = client.post(
            WEBHOOK_URL, headers={**SECRET_HEADER, **IDEMPOTENCY_HEADER},
            json=BOOKED_PAYLOAD,
        )
        assert first.status_code == 200, first.text
        assert first.json()["received"] is True
        again = client.post(
            WEBHOOK_URL, headers={**SECRET_HEADER, **IDEMPOTENCY_HEADER},
            json=BOOKED_PAYLOAD,
        )
        assert again.status_code == 200, again.text
        assert again.json()["status"] == "already_applied"
        # applied exactly once — attempts must not double-count
        lead = await db.leads.find_one({"lead_id": "lead_q"})
        assert lead["ai_call_attempts"] == 1
        docs = await db.bland_webhook_events.find({}).to_list(None)
        assert len(docs) == 2
        assert any(d.get("mapping", {}).get("duplicate") is True for d in docs)
        assert all(d["idempotency_key"] == "evt-dup-1" for d in docs)
