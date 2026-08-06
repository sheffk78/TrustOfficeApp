# Smoke tests for subscriptions router (routers/subscriptions.py)
# Endpoints mounted at /api/subscription/* (+ /api/stripe/webhook).
# These tests SKIP gracefully when no live server is available.

import pytest
import requests
import os
import sys

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
DEMO_EMAIL = "demo@trustoffice.com"
DEMO_PASSWORD = "demopassword"

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
    """Module health: subscriptions router imports successfully."""
    bd = os.path.join(os.path.dirname(__file__), "..")
    if bd not in sys.path:
        sys.path.insert(0, os.path.abspath(bd))
    import routers.subscriptions  # noqa: F401


def test_get_subscription(session):
    """GET /api/subscription — should return 200."""
    r = session.get(f"{BASE_URL}/api/subscription")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"


def test_get_subscription_state(session):
    """GET /api/subscription/state — should return 200."""
    r = session.get(f"{BASE_URL}/api/subscription/state")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"


def test_get_subscription_features(session):
    """GET /api/subscription/features — should return 200."""
    r = session.get(f"{BASE_URL}/api/subscription/features")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"


def test_create_checkout_invalid_body(session):
    """POST /api/subscription/create-checkout with empty body — should 4xx."""
    r = session.post(f"{BASE_URL}/api/subscription/create-checkout", json={})
    assert r.status_code < 500, f"Server error {r.status_code}: {r.text}"


def test_create_portal_invalid_body(session):
    """POST /api/subscription/create-portal with empty body — should 4xx."""
    r = session.post(f"{BASE_URL}/api/subscription/create-portal", json={})
    assert r.status_code < 500, f"Server error {r.status_code}: {r.text}"


def test_cancel_invalid_body(session):
    """POST /api/subscription/cancel with empty body — should 4xx."""
    r = session.post(f"{BASE_URL}/api/subscription/cancel", json={})
    assert r.status_code < 500, f"Server error {r.status_code}: {r.text}"


def test_upgrade_invalid_body(session):
    """POST /api/subscription/upgrade with empty body — should 4xx."""
    r = session.post(f"{BASE_URL}/api/subscription/upgrade", json={})
    assert r.status_code < 500, f"Server error {r.status_code}: {r.text}"


def test_stripe_webhook_invalid_signature():
    """POST /api/stripe/webhook without valid signature — should 400/403."""
    if not BASE_URL:
        pytest.skip("No REACT_APP_BACKEND_URL set — no live server")
    r = requests.post(f"{BASE_URL}/api/stripe/webhook", json={})
    assert r.status_code in (400, 403, 401), f"Unexpected {r.status_code}: {r.text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])