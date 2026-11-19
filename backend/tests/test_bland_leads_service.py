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


def _lead(
    lead_id,
    *,
    stage="new",
    # Default phone must be call-eligible: ≥10 CONSECUTIVE digits in the raw
    # stored string (no separators) so legacy queue tests pass the queue's
    # dialable-number regex.
    phone="5550001000",
    created_at=None,
    **extra,
):
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

    # ---- phone normalization (Meta 'p:' backfill quirk + masked junk) ----

    @pytest.mark.asyncio
    async def test_queue_normalizes_p_prefixed_phone(self, client):
        # Meta ad-export backfill stores phones like 'p:+1201…' — the view
        # must strip the prefix so Bland dials a real number.
        await _seed(phone="p:+1202987655")
        r = client.get(QUEUE_URL, headers=AUTH)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["count"] == 1
        assert body["leads"][0]["phone"] == "+1202987655"

    @pytest.mark.asyncio
    async def test_queue_excludes_masked_asterisk_phones(self, client):
        # Masked CRM junk ('+184****4495') has no 10-digit run — never queued.
        await _seed(phone="+184****4495")
        r = client.get(QUEUE_URL, headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body["leads"] == [] and body["count"] == 0

    @pytest.mark.asyncio
    async def test_queue_plain_stored_phone_unchanged(self, client):
        await _seed(phone="8128015542")
        r = client.get(QUEUE_URL, headers=AUTH)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["count"] == 1
        assert body["leads"][0]["phone"] == "8128015542"


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


# ==================== BATCH-MODE GUARD: cooldown + claim ====================

CLAIM_URL = "/api/service/leads/{lead_id}/claim"


def _claim_url(lead_id: str) -> str:
    return CLAIM_URL.format(lead_id=lead_id)


class TestCallOutcomeCooldownStamp:
    """POST /{id}/call-outcome stamps last_ai_call_at + ai_call_attempts."""

    @pytest.mark.asyncio
    async def test_call_outcome_stamps_cooldown_fields(self, client):
        await db.leads.insert_one(_lead("lead_q", stage="new"))
        r = client.post(
            f"/api/service/leads/lead_q/call-outcome",
            headers=AUTH,
            json={"disposition": "interested", "summary": "warm signal"},
        )
        assert r.status_code == 200, r.text
        lead = await db.leads.find_one({"lead_id": "lead_q"})
        # ISO-aware-UTC string, lexicographically comparable in the queue query
        assert isinstance(lead.get("last_ai_call_at"), str)
        assert lead["last_ai_call_at"].endswith("+00:00")
        assert lead.get("ai_call_attempts") == 1
        # second call increments the counter
        client.post(
            f"/api/service/leads/lead_q/call-outcome",
            headers=AUTH,
            json={"disposition": "voicemail"},
        )
        lead = await db.leads.find_one({"lead_id": "lead_q"})
        assert lead["ai_call_attempts"] == 2

    @pytest.mark.asyncio
    async def test_booking_by_email_does_not_stamp_cooldown(self, client):
        """Booking callbacks are not AI calls — no cooldown stamp (additive-only)."""
        await db.leads.insert_one(
            _lead("lead_q", stage="new", email="fixture@example.com")
        )
        r = client.post(
            "/api/service/leads/by-email/fixture@example.com/booking",
            headers=AUTH,
            json={"status": "booked", "booking_ref": "hold_x"},
        )
        assert r.status_code == 200, r.text
        lead = await db.leads.find_one({"lead_id": "lead_q"})
        assert "last_ai_call_at" not in lead
        assert "ai_call_attempts" not in lead


class TestQueueCooldown:
    """GET /queue excludes leads inside the retry-cooldown window."""

    @pytest.mark.asyncio
    async def test_fresh_lead_in_queue_then_excluded_after_outcome(self, client):
        await db.leads.insert_one(_lead("lead_a", stage="new"))
        r = client.get("/api/service/leads/queue?limit=25", headers=AUTH)
        assert r.status_code == 200, r.text
        body = r.json()
        assert [l["lead_id"] for l in body["leads"]] == ["lead_a"]
        assert body["count"] == 1
        assert body["cooldown"] == 0
        assert body["claimed"] == 0
        assert set(body) == {"leads", "count", "cooldown", "claimed", "asOf"}

        r = client.post(
            "/api/service/leads/lead_a/call-outcome",
            headers=AUTH,
            json={"disposition": "interested", "summary": "TEST — cooldown plumbing write"},
        )
        assert r.status_code == 200, r.text
        body = client.get("/api/service/leads/queue?limit=25", headers=AUTH).json()
        # the called lead is gone from the result set, but still accounted for
        assert [l["lead_id"] for l in body["leads"]] == []
        assert body["count"] == 0
        assert body["cooldown"] == 1
        # total ledger stays accurate: count + cooldown == call-eligible
        assert body["count"] + body["cooldown"] == 1

    @pytest.mark.asyncio
    async def test_cooldown_expiry_returns_lead_to_queue(self, client):
        await db.leads.insert_one(_lead("lead_a", stage="new"))
        client.post(
            "/api/service/leads/lead_a/call-outcome",
            headers=AUTH,
            json={"disposition": "interested", "summary": "TEST — cooldown plumbing write"},
        )
        # backdate the stamp past the default 24h window
        stale_iso = (
            datetime.now(timezone.utc) - timedelta(hours=25)
        ).isoformat()
        await db.leads.update_one(
            {"lead_id": "lead_a"}, {"$set": {"last_ai_call_at": stale_iso}}
        )
        body = client.get("/api/service/leads/queue?limit=25", headers=AUTH).json()
        assert [l["lead_id"] for l in body["leads"]] == ["lead_a"]
        assert body["count"] == 1
        assert body["cooldown"] == 0

    @pytest.mark.asyncio
    async def test_cooldown_env_override_zero_disables_exclusion(self, client, monkeypatch):
        monkeypatch.setenv("BLAND_RETRY_COOLDOWN_HOURS", "0")
        await db.leads.insert_one(_lead("lead_a", stage="new"))
        client.post(
            "/api/service/leads/lead_a/call-outcome",
            headers=AUTH,
            json={"disposition": "interested"},
        )
        body = client.get("/api/service/leads/queue?limit=25", headers=AUTH).json()
        # 0h window → the just-called lead is immediately callable again
        assert [l["lead_id"] for l in body["leads"]] == ["lead_a"]
        assert body["cooldown"] == 0

    @pytest.mark.asyncio
    async def test_queue_meta_counts_across_cooldown_and_claim(self, client):
        """cooldown + claimed metas count correctly TOGETHER (independent sets)."""
        await db.leads.insert_many([
            _lead("lead_a", stage="new"),   # goes into cooldown
            _lead("lead_b", stage="new"),   # gets claimed (stays visible)
            _lead("lead_c", stage="new"),   # untouched
        ])
        client.post(
            "/api/service/leads/lead_a/call-outcome",
            headers=AUTH,
            json={"disposition": "interested"},
        )
        assert client.post(
            _claim_url("lead_b"), headers=AUTH, json={"claimed_by": "bland-worker-1"}
        ).status_code == 200
        body = client.get("/api/service/leads/queue?limit=25", headers=AUTH).json()
        ids = {l["lead_id"] for l in body["leads"]}
        # claimed lead_b stays visible; cooldown lead_a is excluded
        assert ids == {"lead_b", "lead_c"}
        assert body["count"] == 2
        assert body["cooldown"] == 1
        assert body["claimed"] == 1


class TestClaimFlow:
    """POST/DELETE /{id}/claim — TTLs, conflicts, releases, queue visibility."""

    @pytest.mark.asyncio
    async def test_claim_sets_fields_default_ttl_20(self, client):
        lead = _lead("lead_q", stage="new")
        await db.leads.insert_one(lead)
        r = client.post(
            _claim_url("lead_q"), headers=AUTH, json={"claimed_by": "bland-worker-1"}
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        assert body["claimed_until"].endswith("+00:00")
        until = datetime.fromisoformat(body["claimed_until"])
        # default TTL is 20 minutes
        assert 19 <= (until - datetime.now(timezone.utc)).total_seconds() / 60 <= 21
        doc = await db.leads.find_one({"lead_id": "lead_q"})
        assert doc["claim"]["claimed_by"] == "bland-worker-1"
        assert doc["claim"]["claimed_until"] == body["claimed_until"]
        assert doc["claim"]["claimed_at"].endswith("+00:00")

    @pytest.mark.asyncio
    async def test_claim_conflict_409_with_unexpired_claim(self, client):
        await db.leads.insert_one(_lead("lead_q", stage="new"))
        client.post(_claim_url("lead_q"), headers=AUTH, json={"claimed_by": "w1"})
        r = client.post(
            _claim_url("lead_q"), headers=AUTH, json={"claimed_by": "bland-worker-2"}
        )
        assert r.status_code == 409, r.text
        assert r.json()["detail"] == "already_claimed"
        assert r.json()["claimed_until"].endswith("+00:00")
        assert r.json()["claimed_by"] == "w1"

    @pytest.mark.asyncio
    async def test_same_claimer_refreshes_claim(self, client):
        await db.leads.insert_one(_lead("lead_q", stage="new"))
        client.post(_claim_url("lead_q"), headers=AUTH, json={"claimed_by": "w1"})
        r = client.post(
            _claim_url("lead_q"), headers=AUTH, json={"claimed_by": "w1", "ttl_minutes": 60}
        )
        assert r.status_code == 200, r.text
        assert r.json()["success"] is True
        assert r.json()["ttl_minutes"] == 60
        until = datetime.fromisoformat(r.json()["claimed_until"])
        assert 59 <= (until - datetime.now(timezone.utc)).total_seconds() / 60 <= 61

    @pytest.mark.asyncio
    async def test_claim_ttl_bounds_validated(self, client):
        await db.leads.insert_one(_lead("lead_q", stage="new"))
        r = client.post(
            _claim_url("lead_q"), headers=AUTH, json={"claimed_by": "w1", "ttl_minutes": 61}
        )
        assert r.status_code == 422
        r = client.post(
            _claim_url("lead_q"), headers=AUTH, json={"claimed_by": "w1", "ttl_minutes": 0}
        )
        assert r.status_code == 422
        r = client.post(_claim_url("lead_q"), headers=AUTH, json={"claimed_by": ""})
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_delete_claim_releases(self, client):
        await db.leads.insert_one(_lead("lead_q", stage="new"))
        client.post(_claim_url("lead_q"), headers=AUTH, json={"claimed_by": "w1"})
        r = client.delete(_claim_url("lead_q"), headers=AUTH)
        assert r.status_code == 200, r.text
        assert r.json()["success"] is True
        doc = await db.leads.find_one({"lead_id": "lead_q"})
        assert "claim" not in (doc or {})
        # different claimant can take it immediately after release
        r = client.post(
            _claim_url("lead_q"), headers=AUTH, json={"claimed_by": "bland-worker-2"}
        )
        assert r.status_code == 200, r.text

    @pytest.mark.asyncio
    async def test_release_is_idempotent_on_unclaimed_lead(self, client):
        await db.leads.insert_one(_lead("lead_q", stage="new"))
        r = client.delete(_claim_url("lead_q"), headers=AUTH)
        assert r.status_code == 200, r.text

    @pytest.mark.asyncio
    async def test_expired_claim_is_auto_released(self, client):
        """Expired claims are ignored by the 409 check — TTL auto-release."""
        await db.leads.insert_one(_lead("lead_q", stage="new"))
        client.post(_claim_url("lead_q"), headers=AUTH, json={"claimed_by": "w1", "ttl_minutes": 60})
        past_iso = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        await db.leads.update_one(
            {"lead_id": "lead_q"},
            {"$set": {"claim": {"claimed_by": "w1", "claimed_until": past_iso,
                                "claimed_at": past_iso}}},
        )
        r = client.post(
            _claim_url("lead_q"), headers=AUTH, json={"claimed_by": "bland-worker-2"}
        )
        assert r.status_code == 200, r.text  # stale w1 claim does NOT block w2

    @pytest.mark.asyncio
    async def test_claim_unknown_lead_404(self, client):
        assert client.post(
            _claim_url("lead_missing"), headers=AUTH, json={"claimed_by": "w1"}
        ).status_code == 404
        assert client.delete(_claim_url("lead_missing"), headers=AUTH).status_code == 404

    @pytest.mark.asyncio
    async def test_claim_requires_auth(self, client):
        assert client.post(
            _claim_url("lead_q"), json={"claimed_by": "w1"}
        ).status_code == 401
        assert client.delete(_claim_url("lead_q")).status_code == 401

    @pytest.mark.asyncio
    async def test_queue_additive_claim_fields_on_lead_objects(self, client):
        """Claimed leads stay in the queue payload (worker skips them itself)."""
        base_fields = {"lead_id", "name", "phone", "stage", "created_at", "updated_at",
                       "email", "source", "notes"}
        await db.leads.insert_one(_lead("lead_q", stage="new"))
        unclaimed = client.get("/api/service/leads/queue?limit=25", headers=AUTH).json()
        assert set(unclaimed["leads"][0]) == base_fields  # shape unchanged

        client.post(_claim_url("lead_q"), headers=AUTH, json={"claimed_by": "w1", "ttl_minutes": 30})
        body = client.get("/api/service/leads/queue?limit=25", headers=AUTH).json()
        lead = body["leads"][0]
        # claimed lead still present, additive fields only
        assert lead["lead_id"] == "lead_q"
        assert set(lead) == base_fields | {"claimed_by", "claimed_until"}
        assert lead["claimed_by"] == "w1"
        assert lead["claimed_until"].endswith("+00:00")
        assert body["claimed"] == 1

        client.delete(_claim_url("lead_q"), headers=AUTH)
        body = client.get("/api/service/leads/queue?limit=25", headers=AUTH).json()
        assert set(body["leads"][0]) == base_fields  # fields drop on release
        assert body["claimed"] == 0

    @pytest.mark.asyncio
    async def test_expired_claim_hidden_from_queue_annotation(self, client):
        """A backdated (expired) claim must not annotate the lead or the meta."""
        await db.leads.insert_one(_lead("lead_q", stage="new"))
        client.post(_claim_url("lead_q"), headers=AUTH, json={"claimed_by": "w1"})
        past_iso = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        await db.leads.update_one(
            {"lead_id": "lead_q"},
            {"$set": {"claim": {"claimed_by": "w1", "claimed_until": past_iso,
                                "claimed_at": past_iso}}},
        )
        body = client.get("/api/service/leads/queue?limit=25", headers=AUTH).json()
        lead = body["leads"][0]
        assert "claimed_by" not in lead and "claimed_until" not in lead
        assert body["claimed"] == 0
