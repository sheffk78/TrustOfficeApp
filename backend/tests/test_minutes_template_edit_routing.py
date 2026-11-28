"""
Regression: template-created minutes rendered in MinutesDetailPage used to send
edits to PUT /minutes/{id}, which 400s for anything other than finalize.

Tests:
- 400 on PUT /minutes/{template_id} with only content edits, with an actionable
  detail string that points the caller at PUT /minutes-templates/{id}.
- Positive: PUT /minutes/{template_id} with {status: "finalized"} succeeds.

Pure in-process FastAPI + mongomock, no live server.
Run: python -m pytest backend/tests/test_minutes_template_edit_routing.py -q
"""
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test_minutes_routing")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-minutes-routing")

import motor.motor_asyncio
import mongomock_motor
motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient

import database
from dependencies import get_current_user, require_write_access
from routers import minutes as minutes_mod

db = database.db


@pytest_asyncio.fixture
async def seeded_db():
    for coll in ("users", "trusts", "minutes_templates", "minutes_records"):
        await db[coll].delete_many({})

    now = datetime.now(timezone.utc).isoformat()
    await db.users.insert_one({
        "user_id": "u_test",
        "email": "test@example.com",
        "name": "Test User",
        "is_admin": False,
    })
    await db.trusts.insert_one({
        "trust_id": "t_test",
        "user_id": "u_test",
        "name": "Test Trust",
        "created_at": now,
    })
    await db.minutes_templates.insert_one({
        "minutes_id": "min_test_seed",
        "trust_id": "t_test",
        "user_id": "u_test",
        "template_type": "general_meeting",
        "template_data": {
            "meeting_date": "November 27, 2026",
            "trustees_present": ["John Smith"],
        },
        "generated_document": "Generated minutes text",
        "status": "draft",
        "created_at": now,
        "meeting_date": "2026-11-27",
    })
    return {"user_id": "u_test", "minutes_id": "min_test_seed"}


@pytest.fixture
def client(seeded_db):
    app = FastAPI()

    async def fake_user():
        return {"user_id": "u_test", "email": "test@example.com", "is_admin": False}

    app.dependency_overrides[get_current_user] = fake_user
    app.dependency_overrides[require_write_access] = fake_user
    app.include_router(minutes_mod.router, prefix="/api")
    return TestClient(app)


class TestTemplateMinutesEditRouting:
    def test_put_minutes_content_only_returns_400_with_actionable_detail(self, client):
        res = client.put("/api/minutes/min_test_seed", json={"decisions_text": "Updated text"})
        assert res.status_code == 400
        body = res.json()
        assert "PUT /minutes-templates" in body["detail"]
        assert "finalize" in body["detail"].lower()

    def test_put_minutes_finalize_is_accepted(self, client):
        res = client.put("/api/minutes/min_test_seed", json={"status": "finalized"})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["message"] == "Minutes finalized"
        assert body["legacy_path"] is True
