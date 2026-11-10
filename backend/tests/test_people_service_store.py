"""Tests for the P4 person notes/tasks store (routers/people_service.py).

The OS people-card writes now land SERVER-SIDE here (people_notes /
people_tasks collections, keyed by the person id EXACTLY as sent) instead of
only in the OS host's Mac-local crm.db. Bare-id lead notes additionally
side-log into the legacy lead_activities 'manual' stream.

Same harness as test_leads_service.py: mongomock-patched motor, the router
mounted on a minimal FastAPI app, TestClient drives it.
"""
import os
import sys
from datetime import datetime, timezone, timedelta

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test_people_service_store")
os.environ.setdefault("JWT_SECRET", "test-secret-people-service")
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
import routers.people_service as people_service

SERVICE_KEY = os.environ["TRUSTOFFICE_LEADS_SERVICE_KEY"]
AUTH = {"X-Service-Key": SERVICE_KEY}

db = database.db

STORE_COLS = ("people_notes", "people_tasks", "leads", "lead_activities")


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    """Fresh store collections around every test."""
    for coll in STORE_COLS:
        await db[coll].delete_many({})
    yield
    for coll in STORE_COLS:
        await db[coll].delete_many({})


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(people_service.router, prefix="/api")
    return TestClient(app)


async def _seed_lead(lead_id="lead_5a66201222c5", name="Robert Kight"):
    now = datetime.now(timezone.utc)
    await db.leads.insert_one(
        {
            "lead_id": lead_id,
            "name": name,
            "email": "robert@example.com",
            "stage": "new",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "notes": "",
        }
    )


# ==================== auth ====================


class TestStoreAuth:
    def test_note_post_missing_key_401(self, client):
        r = client.post("/api/service/people/lead:lead_x/note", json={"text": "hi"})
        assert r.status_code == 401
        assert "Missing service key" in r.json()["detail"]

    def test_task_post_wrong_key_401(self, client):
        r = client.post(
            "/api/service/people/lead:lead_x/task",
            json={"title": "t"},
            headers={"X-Service-Key": "nope"},
        )
        assert r.status_code == 401

    def test_task_status_missing_key_401(self, client):
        r = client.post(
            "/api/service/people/lead:lead_x/task-status",
            json={"task_id": "pt_x", "status": "done"},
        )
        assert r.status_code == 401

    def test_service_not_configured_503(self, client, monkeypatch):
        monkeypatch.delenv("TRUSTOFFICE_LEADS_SERVICE_KEY", raising=False)
        r = client.get("/api/service/people/lead:lead_x/notes", headers=AUTH)
        assert r.status_code == 503


# ==================== GET notes/tasks (empty stores) ====================


class TestStoreReadsEmpty:
    def test_notes_empty_is_200_empty_list(self, client):
        r = client.get("/api/service/people/lead:lead_unknown/notes", headers=AUTH)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["notes"] == []
        assert body["person_id"] == "lead:lead_unknown"
        assert "as_of" in body

    def test_tasks_empty_is_200_empty_list(self, client):
        r = client.get("/api/service/people/purchaser:a@b.com/tasks", headers=AUTH)
        assert r.status_code == 200, r.text
        assert r.json()["tasks"] == []


# ==================== POST note (append + wire shapes) ====================


class TestPersonNote:
    def test_note_append_returns_wire_shape(self, client):
        r = client.post(
            "/api/service/people/purchaser:alice@example.com/note",
            json={"text": "Called Robert, follow up Monday."},
            headers=AUTH,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        note = body["note"]
        assert note["id"].startswith("pn_")
        assert note["text"] == "Called Robert, follow up Monday."
        assert note["at"]  # ISO stamp present

    @pytest.mark.asyncio
    async def test_note_persists_exact_person_id_including_colon(self, client):
        r = client.post(
            "/api/service/people/lead:lead_5a66201222c5/note",
            json={"text": "wants a trustee review"},
            headers=AUTH,
        )
        assert r.status_code == 200, r.text
        stored = [d async for d in db.people_notes.find({})]
        assert len(stored) == 1
        # EXACT id as sent — colon intact, no de-dup rewriting
        assert stored[0]["person_id"] == "lead:lead_5a66201222c5"
        # readable back through the store GET
        got = client.get(
            "/api/service/people/lead:lead_5a66201222c5/notes", headers=AUTH
        )
        assert got.status_code == 200
        rows = got.json()["notes"]
        assert len(rows) == 1
        assert rows[0]["text"] == "wants a trustee review"
        assert rows[0]["id"] == r.json()["note"]["id"]

    def test_note_validation_too_long(self, client):
        r = client.post(
            "/api/service/people/lead:lead_x/note",
            json={"text": "y" * 2001},
            headers=AUTH,
        )
        assert r.status_code == 400

    def test_note_validation_empty(self, client):
        r = client.post(
            "/api/service/people/lead:lead_x/note", json={"text": "  "}, headers=AUTH
        )
        assert r.status_code == 400


# ==================== POST task ====================


class TestPersonTask:
    def test_task_add_returns_open_task(self, client):
        r = client.post(
            "/api/service/people/purchaser:carol@example.com/task",
            json={"title": "Send the contract", "status": "open"},
            headers=AUTH,
        )
        assert r.status_code == 200, r.text
        task = r.json()["task"]
        assert task["id"].startswith("pt_")
        assert task["title"] == "Send the contract"
        assert task["status"] == "open"
        assert task["at"]

        got = client.get(
            "/api/service/people/purchaser:carol@example.com/tasks", headers=AUTH
        )
        rows = got.json()["tasks"]
        assert len(rows) == 1 and rows[0]["id"] == task["id"]

    def test_task_status_rejects_unknown_enum(self, client):
        r = client.post(
            "/api/service/people/lead:lead_x/task",
            json={"title": "x", "status": "banana"},
            headers=AUTH,
        )
        assert r.status_code == 400

    def test_task_title_limits(self, client):
        r = client.post(
            "/api/service/people/lead:lead_x/task",
            json={"title": "z" * 301},
            headers=AUTH,
        )
        assert r.status_code == 400


# ==================== POST task-status (flip + 404) ====================


class TestTaskStatus:
    def _add_task(self, client, person="purchaser:flip@example.com"):
        r = client.post(
            f"/api/service/people/{person}/task",
            json={"title": "Follow up", "status": "open"},
            headers=AUTH,
        )
        return r.json()["task"]["id"]

    @pytest.mark.asyncio
    async def test_flip_open_to_done(self, client):
        task_id = self._add_task(client)
        r = client.post(
            "/api/service/people/purchaser:flip@example.com/task-status",
            json={"task_id": task_id, "status": "done"},
            headers=AUTH,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "done"
        rows = [d async for d in db.people_tasks.find({"task_id": task_id})]
        assert rows[0]["status"] == "done"

    def test_flip_unknown_task_is_404(self, client):
        r = client.post(
            "/api/service/people/purchaser:flip@example.com/task-status",
            json={"task_id": "pt_does_not_exist", "status": "done"},
            headers=AUTH,
        )
        assert r.status_code == 404

    def test_flip_wrong_person_is_404(self, client):
        task_id = self._add_task(client)
        r = client.post(
            "/api/service/people/purchaser:other@example.com/task-status",
            json={"task_id": task_id, "status": "done"},
            headers=AUTH,
        )
        assert r.status_code == 404


# ==================== bare-id lead-activity side-log ====================


class TestLeadSideLog:
    async def _activity_count(self, lead_id):
        return await db.lead_activities.count_documents({"lead_id": lead_id})

    @pytest.mark.asyncio
    async def test_colon_id_also_side_logs_bare_activity(self, client):
        await _seed_lead("lead_5a66201222c5")
        r = client.post(
            "/api/service/people/lead:lead_5a66201222c5/note",
            json={"text": "Called, promised to email the docs"},
            headers=AUTH,
        )
        assert r.status_code == 200, r.text
        assert r.json()["side_logged"] is True
        # side-log row: SAME _log_activity path, BARE id
        rows = [d async for d in db.lead_activities.find({"lead_id": "lead_5a66201222c5"})]
        assert len(rows) == 1
        assert rows[0]["action_type"] == "manual"
        assert "promised to email the docs" in rows[0]["content"]
        # the store row still carries the EXACT colon id
        store_rows = [d async for d in db.people_notes.find({})]
        assert store_rows[0]["person_id"] == "lead:lead_5a66201222c5"

    @pytest.mark.asyncio
    async def test_side_log_dedupes_after_first_row(self, client):
        await _seed_lead("lead_5a66201222c5")
        for _ in range(2):
            r = client.post(
                "/api/service/people/lead:lead_5a66201222c5/note",
                json={"text": "second note only in the store"},
                headers=AUTH,
            )
            assert r.status_code == 200
        # one side-log row total; two store rows
        assert await self._activity_count("lead_5a66201222c5") == 1
        assert await db.people_notes.count_documents(
            {"person_id": "lead:lead_5a66201222c5"}
        ) == 2

    @pytest.mark.asyncio
    async def test_unknown_lead_still_stores_without_side_log(self, client):
        r = client.post(
            "/api/service/people/lead:lead_missing/note",
            json={"text": "note for a lead that vanished"},
            headers=AUTH,
        )
        assert r.status_code == 200, r.text
        assert r.json()["side_logged"] is False
        assert (
            await db.people_notes.count_documents({"person_id": "lead:lead_missing"})
            == 1
        )
        assert await db.lead_activities.count_documents({}) == 0

    @pytest.mark.asyncio
    async def test_purchaser_note_never_side_logs(self, client):
        r = client.post(
            "/api/service/people/purchaser:alice@example.com/note",
            json={"text": "purchaser note"},
            headers=AUTH,
        )
        assert r.status_code == 200
        assert r.json()["side_logged"] is False
        assert await db.lead_activities.count_documents({}) == 0


# ==================== detail carries notes + tasks ====================


class TestDetailCarriesStore:
    @pytest.mark.asyncio
    async def test_detail_returns_store_notes_and_tasks(self, client):
        await _seed_lead("lead_detail1")
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=1)
        await db.people_notes.insert_one(
            {
                "note_id": "pn_old",
                "person_id": "lead:lead_detail1",
                "text": "older note",
                "at": old,
            }
        )
        await db.people_notes.insert_one(
            {
                "note_id": "pn_new",
                "person_id": "lead:lead_detail1",
                "text": "newer note",
                "at": now,
            }
        )
        await db.people_tasks.insert_one(
            {
                "task_id": "pt_1",
                "person_id": "lead:lead_detail1",
                "title": "Call Robert",
                "status": "open",
                "at": now,
            }
        )
        # a note for a DIFFERENT person must not leak in
        await db.people_notes.insert_one(
            {
                "note_id": "pn_other",
                "person_id": "lead:lead_other",
                "text": "someone else's note",
                "at": now,
            }
        )
        r = client.get("/api/service/people/lead:lead_detail1/detail", headers=AUTH)
        assert r.status_code == 200, r.text
        body = r.json()
        notes = body["notes"]
        assert [n["id"] for n in notes] == ["pn_new", "pn_old"]  # newest first
        assert notes[0]["text"] == "newer note"
        assert "pn_other" not in [n["id"] for n in notes]
        tasks = body["tasks"]
        assert len(tasks) == 1
        assert tasks[0]["id"] == "pt_1"
        assert tasks[0]["status"] == "open"

    @pytest.mark.asyncio
    async def test_detail_empty_stores_give_empty_lists(self, client):
        r = client.get("/api/service/people/purchaser:ghost@b.com/detail", headers=AUTH)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["notes"] == []
        assert body["tasks"] == []
