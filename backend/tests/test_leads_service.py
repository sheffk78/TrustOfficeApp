"""Tests for the TrustOffice "leads service" lane (routers/leads_service.py).

Phase 1 OS-overview-card endpoints: scoped key auth (X-Service-Key) + three
read/write routes against the leads + lead_activities collections.

Uses an in-memory mongomock_motor shim (no real DB, no network), mounting the
router directly on a minimal FastAPI app and driving it with TestClient ÃÂ¢ÃÂÃÂ the
same matrix as tests/test_org_entry_http_e2e.py.
"""
import os
import sys
from datetime import datetime, timezone, timedelta

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test_leads_service")
os.environ.setdefault("JWT_SECRET", "test-secret-leads-service")
# Dummy service key for local tests; never a real provisioned key.
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
import routers.leads_service as leads_service

SERVICE_KEY = "test-service-key-1234"
AUTH = {"X-Service-Key": SERVICE_KEY}

db = database.db


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    """Fresh collections around every test."""
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


async def _seed_leads(n=3, with_activities=True):
    """Insert n leads (lead_0 is newest) and 3 activities each."""
    now = datetime.now(timezone.utc)
    for i in range(n):
        lid = f"lead_{i}"
        ts = now - timedelta(hours=i)
        await db.leads.insert_one(
            {
                "lead_id": lid,
                "name": f"Lead {i}",
                "email": f"lead{i}@example.com",
                "phone": f"555-000-{i}",
                "stage": "new",
                "source": "blog-subscribe",
                "created_at": ts.isoformat(),
                "updated_at": ts.isoformat(),
                "notes": "",
            }
        )
        if with_activities:
            for j in range(3):
                # activities 0..2 get progressively newer timestamps
                await db.lead_activities.insert_one(
                    {
                        "activity_id": f"act_{lid}_{j}",
                        "lead_id": lid,
                        "action_type": "note",
                        # >160 chars to verify truncation downstream
                        "content": f"activity {j} for lead {i} " + "y" * 200,
                        "created_at": now - timedelta(minutes=(3 - j) * 10),
                    }
                )


# ==================== auth ====================

class TestAuth:
    def test_missing_key_returns_401(self, client):
        r = client.get("/api/service/leads/latest")
        assert r.status_code == 401
        assert "Missing service key" in r.json()["detail"]

    def test_wrong_key_returns_401(self, client):
        r = client.get(
            "/api/service/leads/latest",
            headers={"X-Service-Key": "definitely-not-it"},
        )
        assert r.status_code == 401
        assert "Invalid service key" in r.json()["detail"]

    def test_service_not_configured_returns_503(self, client, monkeypatch):
        monkeypatch.delenv("TRUSTOFFICE_LEADS_SERVICE_KEY", raising=False)
        r = client.get("/api/service/leads/latest", headers=AUTH)
        assert r.status_code == 503
        assert "not configured" in r.json()["detail"]


# ==================== GET /latest ====================

class TestLatest:
    @pytest.mark.asyncio
    async def test_latest_returns_newest_three_with_activities(self, client):
        await _seed_leads(5)
        r = client.get("/api/service/leads/latest", headers=AUTH)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "asOf" in body
        assert "leads" in body
        leads = body["leads"]
        assert len(leads) == 3
        # newest first: lead_0 is the most recent
        assert [l["lead_id"] for l in leads] == ["lead_0", "lead_1", "lead_2"]
        for lead in leads:
            # projected fields present, no _id
            assert "lead_id" in lead and "_id" not in lead
            assert {"name", "email", "phone", "stage", "source", "created_at",
                    "updated_at", "notes"} <= set(lead.keys())
            # exactly 3 activities, each truncated + iso timestamps
            acts = lead["activities"]
            assert len(acts) == 3
            for a in acts:
                assert set(a.keys()) == {"action_type", "content", "created_at"}
                assert a["content"].startswith("activity")
                assert len(a["content"]) == 160  # truncated to 160 chars
                # iso timestamp parses
                datetime.fromisoformat(a["created_at"])

    @pytest.mark.asyncio
    async def test_latest_empty_when_no_leads(self, client):
        r = client.get("/api/service/leads/latest", headers=AUTH)
        assert r.status_code == 200
        assert r.json()["leads"] == []


# ==================== POST /{lead_id}/note ====================

class TestAddNote:
    @pytest.mark.asyncio
    async def test_note_lands_in_lead_activities(self, client):
        await _seed_leads(1, with_activities=False)
        r = client.post(
            "/api/service/leads/lead_0/note",
            headers=AUTH,
            json={"content": "  spoke with lead, very interested  "},
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"success": True}

        acts = [
            a
            async for a in db.lead_activities.find({"lead_id": "lead_0"})
        ]
        assert len(acts) == 1
        assert acts[0]["action_type"] == "manual"
        assert acts[0]["content"] == "spoke with lead, very interested"  # trimmed

    @pytest.mark.asyncio
    async def test_empty_note_rejected(self, client):
        await _seed_leads(1, with_activities=False)
        r = client.post(
            "/api/service/leads/lead_0/note",
            headers=AUTH,
            json={"content": "   "},
        )
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_unknown_lead_note_returns_404(self, client):
        r = client.post(
            "/api/service/leads/lead_nope/note",
            headers=AUTH,
            json={"content": "hi"},
        )
        assert r.status_code == 404


# ==================== PATCH /{lead_id}/stage ====================

class TestSetStage:
    @pytest.mark.asyncio
    async def test_stage_change_updates_lead_and_logs_activity(self, client):
        await _seed_leads(1, with_activities=False)
        r = client.patch(
            "/api/service/leads/lead_0/stage",
            headers=AUTH,
            json={"stage": "warm"},
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"success": True, "stage": "warm"}

        lead = await db.leads.find_one({"lead_id": "lead_0"})
        assert lead["stage"] == "warm"

        acts = [
            a
            async for a in db.lead_activities.find({"lead_id": "lead_0"})
        ]
        assert len(acts) == 1
        assert acts[0]["action_type"] == "system"
        assert "Stage set to warm from OS overview by Kit" == acts[0]["content"]

    @pytest.mark.asyncio
    async def test_bad_stage_returns_400(self, client):
        await _seed_leads(1, with_activities=False)
        r = client.patch(
            "/api/service/leads/lead_0/stage",
            headers=AUTH,
            json={"stage": "not-a-real-stage"},
        )
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_unknown_lead_stage_returns_404(self, client):
        r = client.patch(
            "/api/service/leads/lead_nope/stage",
            headers=AUTH,
            json={"stage": "warm"},
        )
        assert r.status_code == 404
