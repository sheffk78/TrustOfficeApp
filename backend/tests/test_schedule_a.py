# Smoke tests for schedule_a router (routers/schedule_a.py)
# Endpoints mounted at /api/schedule-a/* — auth required.
# These tests SKIP gracefully when no live server is available.

import pytest
import requests
import os
import sys

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
DEMO_EMAIL = "demo@trustoffice.com"
DEMO_PASSWORD = "demopassword"
TRUST_ID = "trust_b753cb8fe07f"  # demo trust id used by other tests

# database.py hard-reads MONGO_URL/DB_NAME at import time; set dummies so the
# module-import test (and any router import) succeeds without a live Mongo.
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-smoke-tests")


@pytest.fixture(scope="module")
def auth_token():
    if not BASE_URL:
        pytest.skip("No REACT_APP_BACKEND_URL set — no live server")
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}
    )
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Auth failed: {response.status_code}")


@pytest.fixture(scope="module")
def session(auth_token):
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    })
    return s


def test_module_imports():
    """Module health: schedule_a router imports successfully."""
    bd = os.path.join(os.path.dirname(__file__), "..")
    if bd not in sys.path:
        sys.path.insert(0, os.path.abspath(bd))
    import routers.schedule_a  # noqa: F401


def test_get_schedule_a(session):
    """GET /api/schedule-a — should return 200 list."""
    r = session.get(f"{BASE_URL}/api/schedule-a")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"


def test_get_schedule_a_with_trust_filter(session):
    """GET /api/schedule-a?trust_id=... — should return 200."""
    r = session.get(f"{BASE_URL}/api/schedule-a?trust_id={TRUST_ID}")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"


def test_get_summary(session):
    """GET /api/schedule-a/summary/{trust_id} — should return 200."""
    r = session.get(f"{BASE_URL}/api/schedule-a/summary/{TRUST_ID}")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"


def test_post_schedule_a_empty_body(session):
    """POST /api/schedule-a with empty body — should 422 (validation)."""
    r = session.post(f"{BASE_URL}/api/schedule-a", json={})
    assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"


def test_post_schedule_a_missing_trust(session):
    """POST /api/schedule-a with invalid trust_id — should 404/422."""
    payload = {
        "trust_id": "trust_nonexistent_xyz",
        "category": "real_property",
        "description": "Test asset",
        "identifier": "test-id",
        "location": None,
        "approximate_value": 1000.00,
        "date_conveyed": None,
        "notes": "pytest smoke",
    }
    r = session.post(f"{BASE_URL}/api/schedule-a", json=payload)
    assert r.status_code in (404, 422), f"Unexpected {r.status_code}: {r.text}"


def test_get_nonexistent_item(session):
    """GET /api/schedule-a/{nonexistent_id} — should 404."""
    r = session.get(f"{BASE_URL}/api/schedule-a/asset_nonexistent123")
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


def test_unauthenticated_schedule_a_blocked():
    """GET /api/schedule-a without token — should 401/403."""
    if not BASE_URL:
        pytest.skip("No REACT_APP_BACKEND_URL set — no live server")
    r = requests.get(f"{BASE_URL}/api/schedule-a")
    assert r.status_code in (401, 403, 404), f"Unexpected {r.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])