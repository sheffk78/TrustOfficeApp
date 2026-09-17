"""
State deep-knowledge router tests (2026-09-16).

Verifies the endpoint that surfaces the 10 per-state deep guides
(backend/KNOWLEDGE/18-state-compliance-<state>.md):

1. GET /api/state-compliance/deep-knowledge returns one entry per guide
   (10 states), sorted by state_name, with id/state_code/state_name/title/summary.
2. GET /api/state-compliance/deep-knowledge/{state_code} returns the full
   markdown (title 'Trust Compliance: <State>', body contains 'Trust Compliance:').
3. Detail for a state without a guide -> 404.
4. Unauthenticated requests are rejected (401/403).

Pure in-process: a minimal FastAPI app mounts only this router; auth is
exercised via the real dependency (no override) for the 401 case and via
app.dependency_overrides for the authenticated cases (mirrors
test_tenant_isolation.py).
"""
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-state-deep-knowledge-tests")

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import dependencies  # noqa: E402
import routers.state_deep_knowledge as sdk  # noqa: E402

USER = {"user_id": "user_1", "email": "test@trustoffice.app", "is_admin": False}


@pytest.fixture(scope="module")
def app():
    a = FastAPI()
    a.include_router(sdk.router, prefix="/api")
    return a


@pytest.fixture(scope="module")
def authed_client(app):
    def fake_current():
        return USER

    app.dependency_overrides[dependencies.get_current_user] = fake_current
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def unauthed_client(app):
    c = TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.pop(dependencies.get_current_user, None)
    return c


class TestListDeepKnowledge:
    def test_returns_10_entries_sorted_by_state_name(self, authed_client):
        r = authed_client.get("/api/state-compliance/deep-knowledge")
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 10

        names = [i["state_name"] for i in items]
        assert names == sorted(names)

        expected_codes = {"AZ", "CA", "DE", "FL", "IL", "NV", "NY", "SD", "TX", "WA"}
        assert {i["state_code"] for i in items} == expected_codes

        for item in items:
            assert item["id"].startswith("18-state-compliance-")
            assert item["title"].startswith("Trust Compliance:")
            assert len(item["summary"]) <= 300 and item["summary"]

    def test_every_state_has_trust_compliance_title(self, authed_client):
        items = authed_client.get("/api/state-compliance/deep-knowledge").json()
        by_code = {i["state_code"]: i for i in items}
        assert by_code["CA"]["title"] == "Trust Compliance: California"
        assert by_code["NY"]["title"] == "Trust Compliance: New York"
        assert by_code["SD"]["state_name"] == "South Dakota"


class TestDeepKnowledgeDetail:
    def test_detail_returns_full_markdown(self, authed_client):
        r = authed_client.get("/api/state-compliance/deep-knowledge/CA")
        assert r.status_code == 200
        body = r.json()
        assert body["state_code"] == "CA"
        assert body["state_name"] == "California"
        assert body["title"] == "Trust Compliance: California"
        assert "Trust Compliance:" in body["markdown"]
        assert "## State Income Tax on Trusts" in body["markdown"]

    def test_detail_is_case_insensitive(self, authed_client):
        r = authed_client.get("/api/state-compliance/deep-knowledge/ny")
        assert r.status_code == 200
        assert r.json()["state_code"] == "NY"

    def test_detail_404_for_uncovered_state(self, authed_client):
        r = authed_client.get("/api/state-compliance/deep-knowledge/XX")
        assert r.status_code == 404

        # A real state code that simply has no deep guide yet
        r2 = authed_client.get("/api/state-compliance/deep-knowledge/AL")
        assert r2.status_code == 404


class TestAuthRequired:
    def test_unauthenticated_list_rejected(self, app, unauthed_client):
        r = unauthed_client.get("/api/state-compliance/deep-knowledge")
        assert r.status_code in (401, 403)

    def test_unauthenticated_detail_rejected(self, unauthed_client):
        r = unauthed_client.get("/api/state-compliance/deep-knowledge/CA")
        assert r.status_code in (401, 403)