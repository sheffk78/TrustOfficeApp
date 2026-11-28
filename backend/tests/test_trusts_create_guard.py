"""Offline unit test for POST /api/trusts empty-name guard.

Runs the trusts router directly via FastAPI TestClient, stubbing auth and DB.
"""
import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test")
os.environ.setdefault("JWT_SECRET", "test-secret-not-used-in-unit-tests")


class FakeCollection:
    async def count_documents(self, *a, **k):
        return 0
    async def insert_one(self, *a, **k):
        return type("InsertResult", (), {"inserted_id": "dummy"})()
    async def update_one(self, *a, **k):
        return None
    async def find_one(self, *a, **k):
        return None
    async def delete_one(self, *a, **k):
        return None


class FakeDB:
    def __init__(self):
        self.trusts = FakeCollection()
        self.users = FakeCollection()
        self.subscriptions = FakeCollection()
        self.entities = FakeCollection()
        self.governance_tasks = FakeCollection()
        self.tax_calendar = FakeCollection()
        self.health_score_snapshots = FakeCollection()
        self.trust_state_compliance = FakeCollection()

    def __getattr__(self, name):
        col = FakeCollection()
        setattr(self, name, col)
        return col


@pytest.fixture
def fake_db(monkeypatch):
    import database
    import routers.trusts as trusts_router

    db = FakeDB()
    # trusts.py does `from database import db` — patch the name the router bound.
    monkeypatch.setattr(trusts_router, "db", db)
    monkeypatch.setattr(database, "db", db)
    return db


@pytest.fixture
def client(fake_db, monkeypatch):
    import dependencies
    import routers.trusts as trusts_router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    async def fake_get_current_user():
        return {"user_id": "test_user_1", "email": "qa@trustoffice.app"}

    async def fake_get_subscription_state(user_id):
        return type("SubState", (), {
            "plan_type": "free",
            "legacy_trust_limit": None,
            "is_active": True,
            "is_read_only": False,
            "status": "active",
        })()

    async def fake_check_feature_access(user_id, feature, **kwargs):
        return True

    monkeypatch.setattr(dependencies, "get_subscription_state", fake_get_subscription_state)
    monkeypatch.setattr(dependencies, "check_feature_access", fake_check_feature_access)

    # Silence downstream helpers that touch the stub DB in ways we don't need.
    import services.trust_archive as trust_archive
    monkeypatch.setattr(trust_archive, "apply_archive_guard", lambda app: 0)

    test_app = FastAPI()
    test_app.include_router(trusts_router.router, prefix="/api")
    test_app.dependency_overrides[dependencies.get_current_user] = fake_get_current_user

    return TestClient(test_app)


def test_create_trust_missing_name_returns_readable_422(client):
    resp = client.post("/api/trusts", json={})
    assert resp.status_code == 422
    # Pydantic validation runs before the route body; the missing-field
    # contract is FastAPI's standard "Field required" response.
    detail = resp.json().get("detail", "")
    assert any("Field required" in str(err.get("msg", "")) for err in detail)


def test_create_trust_empty_name_returns_readable_422(client):
    resp = client.post("/api/trusts", json={"name": "", "trust_type": "family", "jurisdiction": "DE"})
    assert resp.status_code == 422
    assert "Trust name is required" in resp.json().get("detail", "")
