"""Service-errors lane tests: POST /api/service/errors/resolve-disconnects.

Covers the 2026-11-17 false-alarm sweep endpoint in routers/service_errors.py:
  - 401 without the X-Service-Key header
  - resolves only matching (disconnect message + older than 1h) rows
  - leaves every other unresolved row untouched
  - remaining_unresolved response shape (error_id/url/error_type/timestamp/
    truncated_message@120, capped at 20)

Same transport-stubbing matrix as test_bland_leads_service.py: mongomock_motor
shim, router mounted on a minimal FastAPI app, TestClient.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test_service_errors")
os.environ.setdefault("JWT_SECRET", "test-secret-service-errors")
os.environ.setdefault("TRUSTOFFICE_LEADS_SERVICE_KEY", "test-service-key-1234")

# Reuse the exact same shim pattern as test_bland_leads_service.py — capture
# the real motor BEFORE any module under test runs, then patch.
import motor.motor_asyncio
import mongomock_motor

motor.motor_asyncio.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

import database
import routers.service_errors as service_errors

SERVICE_KEY = "test-service-key-1234"
AUTH = {"X-Service-Key": SERVICE_KEY}
URL = "/api/service/errors/resolve-disconnects"

db = database.db

NOW = datetime.now(timezone.utc)
STALE = (NOW - timedelta(hours=2)).isoformat()
FRESH = (NOW - timedelta(minutes=5)).isoformat()


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    await db.error_logs.delete_many({})
    yield
    await db.error_logs.delete_many({})


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(service_errors.router, prefix="/api")
    return TestClient(app)


def _err(error_id, *, message="No response returned.", timestamp=STALE,
         error_type="RuntimeError", resolved=False, **extra):
    doc = {
        "error_id": error_id,
        "timestamp": timestamp,
        "error_type": error_type,
        "error_message": message,
        "url": "/docker-compose.prod.yml",
        "resolved": resolved,
    }
    doc.update(extra)
    return doc


class TestAuth:
    def test_401_without_key(self, client):
        r = client.post(URL)
        assert r.status_code == 401

    def test_401_with_wrong_key(self, client):
        r = client.post(URL, headers={"X-Service-Key": "nope"})
        assert r.status_code == 401


class TestResolveDisconnects:
    @pytest.mark.asyncio
    async def test_resolves_only_matching_and_stale_rows(self, client):
        # two stale matching rows (exact + case-insensitive fragment)
        await db.error_logs.insert_one(_err("err_stale_match"))
        await db.error_logs.insert_one(_err("err_stale_match_case", message="...NO RESPONSE RETURNED..."))
        # fresh disconnect (inside the 1h window) must NOT be swept
        await db.error_logs.insert_one(_err("err_fresh_match", timestamp=FRESH))
        # already-resolved disconnect must not be re-touched
        await db.error_logs.insert_one(_err("err_already", resolved=True))
        # other unresolved errors must be untouched
        await db.error_logs.insert_one(_err("err_other_msg", message="Database timeout"))
        # different error_type but same message -> message-based filter
        # still sweeps it (contract: filter is message + age only)
        await db.error_logs.insert_one(_err("err_other_type", message="No response returned.", error_type="ValueError"))

        r = client.post(URL, headers=AUTH)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        assert body["resolved_count"] == 3
        assert body["updated"] == 3

        swept_ids = ["err_stale_match", "err_stale_match_case", "err_other_type"]
        swept = await db.error_logs.find({"error_id": {"$in": swept_ids}}).to_list(None)
        assert len(swept) == 3
        for doc in swept:
            assert doc["resolved"] is True
            assert doc["resolved_note"] == service_errors.SWEEP_NOTE
            assert doc.get("resolved_at")

        untouched = await db.error_logs.find(
            {"error_id": {"$in": ["err_fresh_match", "err_already", "err_other_msg"]}}
        ).to_list(None)
        by_id = {row["error_id"]: row for row in untouched}
        assert by_id["err_fresh_match"]["resolved"] is False
        assert "resolved_note" not in by_id["err_fresh_match"]
        assert by_id["err_already"]["resolved"] is True
        assert "resolved_note" not in by_id["err_already"]
        assert by_id["err_other_msg"]["resolved"] is False
        assert "resolved_note" not in by_id["err_other_msg"]

    @pytest.mark.asyncio
    async def test_other_unresolved_rows_left_untouched(self, client):
        await db.error_logs.insert_one(_err("err_stale_match"))
        await db.error_logs.insert_one(_err("err_db", message="Connection refused", error_type="ConnectionError"))
        await db.error_logs.insert_one(_err("err_auth", message="Not authenticated", error_type="auth_check"))

        r = client.post(URL, headers=AUTH)
        assert r.status_code == 200
        assert r.json()["resolved_count"] == 1

        db_row = await db.error_logs.find_one({"error_id": "err_db"})
        assert db_row["resolved"] is False
        assert set(db_row) >= {"resolved", "error_id"}
        assert "resolved_note" not in db_row
        auth_row = await db.error_logs.find_one({"error_id": "err_auth"})
        assert auth_row["resolved"] is False
        assert "resolved_note" not in auth_row

    @pytest.mark.asyncio
    async def test_remaining_unresolved_shape(self, client):
        await db.error_logs.insert_one(_err("err_stale_match"))
        long_msg = "x" * 300
        for i in range(3):
            await db.error_logs.insert_one(
                _err(f"err_left{i}", message=long_msg, error_type="DbError", timestamp=FRESH)
            )

        r = client.post(URL, headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        remaining = body["remaining_unresolved"]
        assert len(remaining) == 3
        assert body["resolved_count"] == 1
        for row in remaining:
            assert set(row) == {"error_id", "url", "error_type", "timestamp", "truncated_message"}
            assert row["truncated_message"] == "x" * 120
            assert row["url"] == "/docker-compose.prod.yml"

    @pytest.mark.asyncio
    async def test_remaining_capped_at_20(self, client):
        for i in range(25):
            await db.error_logs.insert_one(
                _err(f"err_many{i}", message="Timeout waiting for lock", timestamp=STALE)
            )
        r = client.post(URL, headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body["resolved_count"] == 0  # no disconnect messages
        assert len(body["remaining_unresolved"]) == 20

    @pytest.mark.asyncio
    async def test_empty_store(self, client):
        r = client.post(URL, headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body == {"success": True, "resolved_count": 0, "updated": 0, "remaining_unresolved": []}


# ==================== CHANGE 1: error_alerting auto-resolve at insert ====================

class TestAlertingAutoResolve:
    @pytest.mark.asyncio
    async def test_base_mw_disconnect_stored_resolved_at_insert(self, clean_db):
        """report_error() must store the benign disconnect class as already
        resolved (with note + timestamp) so it never enters the feed."""
        import error_alerting
        await db.error_logs.delete_many({})
        await error_alerting.report_error(
            source="server",
            error_type="RuntimeError",
            error_message='RuntimeError("No response returned.")',
        )
        doc = await db.error_logs.find_one({})
        assert doc is not None
        assert doc["resolved"] is True
        assert doc["resolved_note"].startswith("Auto-resolved at insert:")
        assert doc.get("resolved_at")

    @pytest.mark.asyncio
    async def test_other_errors_still_unresolved(self, clean_db):
        import error_alerting
        await db.error_logs.delete_many({})
        await error_alerting.report_error(
            source="server",
            error_type="ConnectionError",
            error_message="Mongo connection refused",
        )
        doc = await db.error_logs.find_one({})
        assert doc is not None
        assert doc["resolved"] is False
        assert "resolved_note" not in doc
