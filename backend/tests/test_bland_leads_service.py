"""Bland.ai calling-assistant tests for the leads service lane.

Covers the three Bland endpoints added to routers/leads_service.py:
  GET  /api/service/leads/queue            -> paginated calling queue
  GET  /api/service/leads/{lead_id}        -> single lead + <=10 activities
  POST /api/service/leads/{lead_id}/call-outcome -> disposition handling

Same transport-stubbing matrix as test_leads_service.py: mongomock_motor shim,
router mounted on a minimal FastAPI app, TestClient. The do_not_call stage and
STAGE_LABELS wiring in routers/leads.py is asserted here too.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test_leads_service")
os.environ.setdefault("JWT_SECRET", "test-secret-leads-service")
os.environ.setdefault("TRUSTOFFICE_LEADS_SERVICE_KEY", "test-service-key-1234")

# Reuse the exact same shim pattern as test_leads_service.py — capture the
# real motor BEFORE any module under test runs, then patch.
import motor.motor_asyncio
import mongomock_motor

motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

import database
import routers.leads as leads_mod
import routers.leads_service as leads_service

SERVICE_KEY = "test-service-key-1234"
AUTH = {"X-Service-Key": SERVICE_KEY}

db = database.db


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    for coll in ("leads", "lead_activities"):
        await db[coll].delete_many({})
    yield
    for coll in ("leads", "lead_activities"):
        await db[coll].delete_many({})


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(leads_service.router, prefix="/api")
    return TestClient(app)


QUEUE_URL = "/api/service/leads/queue"


def _lead(lead_id, *, stage="new", phone="555-000-1", created_at=None, **extra):
    now = created_at or datetime.now(timezone.utc)
    doc = {
        "lead_id": lead_id,
        "name": "Lead " + lead_id,
        "email": lead_id + "@example.com",
        "phone": phone,
        "stage": stage,
        "source": "blog-subscribe",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "notes": "",
    }
    doc.update(extra)
    return doc


async def _seed(**overrides):
    doc = _lead("lead_q", **overrides)
    await db.leads.insert_one(doc)
    return doc


# ==================== GET /queue ====================

class TestQueue:
    @pytest.mark.asyncio
    async def test_queue_oldest_first_excludes_uncallable(self, client):
        now = datetime.now(timezone.utc)
        # 3 call-eligible leads, oldest first; 5 that must never be called
        await db.leads.insert_one(_lead("lead_old", created_at=now - timedelta(days=3)))
        await db.leads.insert_one(
            _lead("lead_mid", stage="warm", created_at=now - timedelta(days=2))
        )
        await db.leads.insert_one(
            _lead("lead_new", stage="engaged", created_at=now - timedelta(days=1))
        )
        await db.leads.insert_one(
            _lead("lead_dnc", stage="do_not_call", created_at=now - timedelta(hours=10))
        )
        await db.leads.insert_one(
            _lead("lead_lost", stage="lost", created_at=now - timedelta(hours=9))
        )
        await db.leads.insert_one(
            _lead("lead_nophone", phone="", created_at=now - timedelta(hours=8))
        )
        await db.leads.insert_one(dict(_lead("lead_nonephone"), phone=None))
        await db.leads.insert_one(
            _lead("lead_conv", stage="converted", created_at=now - timedelta(hours=5))
        )

        r = client.get(QUEUE_URL, headers=AUTH)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["count"] == 3
        # oldest first (ASC)
        assert [l["lead_id"] for l in body["leads"]] == [
            "lead_old", "lead_mid", "lead_new",
        ]
        for lead in body["leads"]:
            assert "_id" not in lead
            assert set(lead) == {
                "lead_id", "name", "email", "phone", "stage", "source",
                "created_at", "updated_at", "notes",
            }
        assert "asOf" in body
        datetime.fromisoformat(body["asOf"])

    @pytest.mark.asyncio
    async def test_queue_default_limit_10_max_25(self, client):
        now = datetime.now(timezone.utc)
        for i in range(30):
            await db.leads.insert_one(
                _lead(f"lead_{i}", created_at=now - timedelta(minutes=30 - i))
            )
        # default = 10
        r = client.get(QUEUE_URL, headers=AUTH)
        assert r.status_code == 200
        assert len(r.json()["leads"]) == 10
        assert r.json()["count"] == 30

        # explicit 25
        r = client.get(QUEUE_URL + "?limit=25", headers=AUTH)
        assert r.status_code == 200
        assert len(r.json()["leads"]) == 25

        # >25 is rejected (422 from the ge/le constraint)
        r = client.get(QUEUE_URL + "?limit=26", headers=AUTH)
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_queue_pagination_offset(self, client):
        now = datetime.now(timezone.utc)
        for i in range(12):
            await db.leads.insert_one(
                _lead(f"lead_p{i}", created_at=now - timedelta(minutes=12 - i))
            )
        r = client.get(QUEUE_URL + "?limit=5&offset=5", headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 12
        assert [l["lead_id"] for l in body["leads"]] == [
            "lead_p5", "lead_p6", "lead_p7", "lead_p8", "lead_p9",
        ]

    @pytest.mark.asyncio
    async def test_queue_empty(self, client):
        r = client.get(QUEUE_URL, headers=AUTH)
        assert r.status_code == 200
        assert r.json()["leads"] == [] and r.json()["count"] == 0

    @pytest.mark.asyncio
    async def test_queue_requires_auth(self, client):
        r = client.get(QUEUE_URL)
        assert r.status_code == 401


# ==================== GET /{lead_id} ====================

class TestGetLead:
    @pytest.mark.asyncio
    async def test_single_lead_with_up_to_10_activities_newest_first(self, client):
        await _seed(stage="warm")
        now = datetime.now(timezone.utc)
        for i in range(12):
            await db.lead_activities.insert_one(
                {
                    "activity_id": f"act_{i}",
                    "lead_id": "lead_q",
                    "action_type": "note",
                    "content": f"activity {i}",
                    "created_at": now - timedelta(hours=i),
                }
            )
        r = client.get("/api/service/leads/lead_q", headers=AUTH)
        assert r.status_code == 200, r.text
        body = r.json()
        lead = body["lead"]
        assert lead["lead_id"] == "lead_q"
        assert lead["stage"] == "warm"
        for field in ("name", "email", "phone", "source", "created_at", "updated_at", "notes"):
            assert field in lead
        assert "_id" not in lead
        acts = lead["activities"]
        assert len(acts) == 10  # capped at 10
        # newest first: activity 0 is the most recent
        assert acts[0]["content"] == "activity 0"
        assert acts[-1]["content"] == "activity 9"
        for a in acts:
            assert set(a.keys()) == {"action_type", "content", "created_at"}

    @pytest.mark.asyncio
    async def test_unknown_lead_404(self, client):
        r = client.get("/api/service/leads/lead_nope", headers=AUTH)
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_do_not_call_lead_still_resolvable(self, client):
        # Opted-out leads leave the /queue but stay resolvable by id.
        await _seed(stage="do_not_call")
        r = client.get("/api/service/leads/lead_q", headers=AUTH)
        assert r.status_code == 200
        assert r.json()["lead"]["stage"] == "do_not_call"

    @pytest.mark.asyncio
    async def test_get_lead_requires_auth(self, client):
        r = client.get("/api/service/leads/lead_q")
        assert r.status_code == 401


# ==================== POST /{lead_id}/call-outcome ====================

class TestCallOutcome:
    async def _acts(self, lead_id="lead_q"):
        return [a async for a in db.lead_activities.find({"lead_id": lead_id})]

    @pytest.mark.asyncio
    async def test_booked_sets_engaged_and_logs_ref_and_duration(self, client):
        await _seed(stage="new")
        r = client.post(
            "/api/service/leads/lead_q/call-outcome",
            headers=AUTH,
            json={
                "disposition": "booked",
                "summary": "Wants a consultation",
                "booking_ref": "hold_abc123",
                "call_duration_sec": 214,
            },
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"success": True, "lead_id": "lead_q", "stage": "engaged"}
        lead = await db.leads.find_one({"lead_id": "lead_q"})
        assert lead["stage"] == "engaged"

        acts = await self._acts()
        contents = [a["content"] for a in acts]
        assert "AI call via Bland: booked — Wants a consultation (214s)" in contents
        assert "Booking ref: hold_abc123" in contents
        call_act = next(a for a in acts if "AI call via Bland" in a["content"])
        assert call_act["action_type"] == "manual"

    @pytest.mark.asyncio
    async def test_booked_without_ref_logs_no_ref_activity(self, client):
        await _seed(stage="warm")
        r = client.post(
            "/api/service/leads/lead_q/call-outcome",
            headers=AUTH,
            json={"disposition": "booked", "summary": "booked directly"},
        )
        assert r.status_code == 200
        assert r.json()["stage"] == "engaged"
        contents = [a["content"] for a in await self._acts()]
        assert contents == ["AI call via Bland: booked — booked directly"]

    @pytest.mark.asyncio
    async def test_not_interested_sets_lost(self, client):
        await _seed(stage="engaged")
        r = client.post(
            "/api/service/leads/lead_q/call-outcome",
            headers=AUTH,
            json={"disposition": "not_interested", "summary": "no trust interest"},
        )
        assert r.status_code == 200
        assert r.json()["stage"] == "lost"
        lead = await db.leads.find_one({"lead_id": "lead_q"})
        assert lead["stage"] == "lost"

    @pytest.mark.asyncio
    async def test_opt_out_disposition_sets_do_not_call_and_logs(self, client):
        await _seed(stage="engaged")
        r = client.post(
            "/api/service/leads/lead_q/call-outcome",
            headers=AUTH,
            json={"disposition": "opt_out", "summary": "take me off your list"},
        )
        assert r.status_code == 200
        assert r.json()["stage"] == "do_not_call"
        lead = await db.leads.find_one({"lead_id": "lead_q"})
        assert lead["stage"] == "do_not_call"
        acts = await self._acts()
        system_acts = [a for a in acts if a["action_type"] == "system"]
        assert len(system_acts) == 1
        assert system_acts[0]["content"] == (
            "Opt-out recorded from AI call — do not call"
        )

    @pytest.mark.asyncio
    async def test_opt_out_flag_forces_do_not_call_any_disposition(self, client):
        await _seed(stage="new")
        r = client.post(
            "/api/service/leads/lead_q/call-outcome",
            headers=AUTH,
            json={"disposition": "interested", "summary": "ok", "opt_out": True},
        )
        assert r.status_code == 200
        assert r.json()["stage"] == "do_not_call"
        lead = await db.leads.find_one({"lead_id": "lead_q"})
        assert lead["stage"] == "do_not_call"

    @pytest.mark.asyncio
    async def test_neutral_dispositions_leave_stage(self, client):
        for disposition in ("voicemail", "no_answer", "callback_requested", "interested"):
            await db.leads.delete_many({})
            await _seed(stage="warm")
            r = client.post(
                "/api/service/leads/lead_q/call-outcome",
                headers=AUTH,
                json={"disposition": disposition, "summary": "s" * 5},
            )
            assert r.status_code == 200, r.text
            assert r.json()["stage"] == "warm"
            lead = await db.leads.find_one({"lead_id": "lead_q"})
            assert lead["stage"] == "warm"

    @pytest.mark.asyncio
    async def test_minimal_body_disposition_only(self, client):
        await _seed(stage="new")
        r = client.post(
            "/api/service/leads/lead_q/call-outcome",
            headers=AUTH,
            json={"disposition": "no_answer"},
        )
        assert r.status_code == 200
        contents = [a["content"] for a in await self._acts()]
        # no summary -> no trailing separator / no duration suffix
        assert contents == ["AI call via Bland: no_answer"]

    @pytest.mark.asyncio
    async def test_invalid_disposition_400(self, client):
        await _seed()
        r = client.post(
            "/api/service/leads/lead_q/call-outcome",
            headers=AUTH,
            json={"disposition": "hung_up_angry", "summary": "s"},
        )
        assert r.status_code == 400
        assert "Invalid disposition" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_booking_ref_over_200_chars_rejected(self, client):
        await _seed()
        r = client.post(
            "/api/service/leads/lead_q/call-outcome",
            headers=AUTH,
            json={"disposition": "booked", "booking_ref": "x" * 201},
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_unknown_lead_404(self, client):
        r = client.post(
            "/api/service/leads/lead_nope/call-outcome",
            headers=AUTH,
            json={"disposition": "booked"},
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_opt_out_lead_drops_out_of_queue(self, client):
        await _seed(stage="warm")
        before = client.get(QUEUE_URL + "?limit=25", headers=AUTH).json()
        assert before["count"] == 1

        r = client.post(
            "/api/service/leads/lead_q/call-outcome",
            headers=AUTH,
            json={"disposition": "opt_out", "summary": "not now"},
        )
        assert r.status_code == 200

        after = client.get(QUEUE_URL + "?limit=25", headers=AUTH).json()
        assert after["count"] == 0
        assert after["leads"] == []

    @pytest.mark.asyncio
    async def test_requires_auth(self, client):
        r = client.post(
            "/api/service/leads/lead_q/call-outcome",
            json={"disposition": "booked"},
        )
        assert r.status_code == 401


# ==================== do_not_call stage wiring (routers/leads.py) ====================

class TestDoNotCallStageWiring:
    def test_stage_registered(self):
        assert "do_not_call" in leads_mod.LEAD_STAGES
        assert leads_mod.STAGE_LABELS["do_not_call"] == "Do Not Call"

    @pytest.mark.asyncio
    async def test_service_stage_endpoint_allows_do_not_call(self, client):
        await _seed(stage="warm")
        r = client.patch(
            "/api/service/leads/lead_q/stage",
            headers=AUTH,
            json={"stage": "do_not_call"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["stage"] == "do_not_call"
        lead = await db.leads.find_one({"lead_id": "lead_q"})
        assert lead["stage"] == "do_not_call"


# ==================== POST /by-email/{email}/booking ====================

BOOKING_BY_EMAIL_URL = "/api/service/leads/by-email/lead_q@example.com/booking"


class TestBookingByEmail:
    @pytest.mark.asyncio
    async def test_booking_by_email_matched_sets_engaged_and_logs(self, client):
        await _seed(stage="new")
        r = client.post(
            BOOKING_BY_EMAIL_URL,
            headers=AUTH,
            json={
                "status": "booked",
                "when": "2026-10-05T16:00:00+00:00",
                "booking_ref": "hold_abc123",
                "event_type": "governance-consultation",
                "channel": "booking-app",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        assert body["matched"] is True
        assert body["lead_id"] == "lead_q"
        assert body["stage"] == "engaged"

        lead = await db.leads.find_one({"lead_id": "lead_q"})
        assert lead is not None
        assert lead["stage"] == "engaged"

        acts = await db.lead_activities.find({"lead_id": "lead_q"}).to_list(None)
        contents = [a.get("content") for a in acts]
        assert any(
            "Governance consultation BOOKED" in (c or "") and "hold_abc123" in (c or "")
            for c in contents
        )
        assert any(a.get("action_type") == "system" for a in acts)

    @pytest.mark.asyncio
    async def test_booking_by_email_unmatched_returns_matched_false_no_side_effects(self, client):
        r = client.post(
            "/api/service/leads/by-email/lead_nope@example.com/booking",
            headers=AUTH,
            json={"status": "booked", "when": "2026-10-05T16:00:00+00:00", "booking_ref": "hold_x"},
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"success": True, "matched": False}
        # no side effects on a miss
        assert await db.lead_activities.count_documents({}) == 0

    @pytest.mark.asyncio
    async def test_booking_by_email_do_not_call_respected(self, client):
        await _seed(stage="do_not_call")
        r = client.post(
            BOOKING_BY_EMAIL_URL,
            headers=AUTH,
            json={"status": "booked", "when": "2026-10-05T16:00:00+00:00", "booking_ref": "hold_abc123"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        assert body["matched"] is True
        assert body["stage"] == "do_not_call"
        lead = await db.leads.find_one({"lead_id": "lead_q"})
        assert lead is not None
        assert lead["stage"] == "do_not_call"
        acts = await db.lead_activities.find({"lead_id": "lead_q"}).to_list(None)
        assert any("Governance consultation BOOKED" in (a.get("content") or "") for a in acts)

    @pytest.mark.asyncio
    async def test_booking_by_email_case_insensitive_match(self, client):
        await db.leads.insert_one(_lead("lead_mixed", stage="new", email="Mixed.Case@Example.com"))
        r = client.post(
            "/api/service/leads/by-email/mixed.case@example.com/booking",
            headers=AUTH,
            json={"status": "booked", "when": "2026-10-05T16:00:00+00:00", "booking_ref": "hold_m1"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["matched"] is True
        assert r.json()["lead_id"] == "lead_mixed"
        assert r.json()["stage"] == "engaged"

    @pytest.mark.asyncio
    async def test_booking_by_email_requires_auth(self, client):
        r = client.post(BOOKING_BY_EMAIL_URL, json={"status": "booked"})
        assert r.status_code == 401
        assert await db.lead_activities.count_documents({}) == 0
