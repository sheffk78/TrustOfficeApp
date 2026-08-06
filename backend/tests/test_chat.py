# Smoke tests for chat router (routers/chat.py)
# Endpoints mounted at /api/ai/chat/* — auth required.
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
    """Module health: chat router imports successfully."""
    bd = os.path.join(os.path.dirname(__file__), "..")
    if bd not in sys.path:
        sys.path.insert(0, os.path.abspath(bd))
    import routers.chat  # noqa: F401


def test_get_status(session):
    """GET /api/ai/chat/status — should return 200."""
    r = session.get(f"{BASE_URL}/api/ai/chat/status")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"


def test_get_conversations(session):
    """GET /api/ai/chat/conversations — should return 200."""
    r = session.get(f"{BASE_URL}/api/ai/chat/conversations")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"


def test_post_chat_empty_body(session):
    """POST /api/ai/chat with empty body — should 422 (validation)."""
    r = session.post(f"{BASE_URL}/api/ai/chat", json={})
    assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"


def test_post_chat_with_message(session):
    """POST /api/ai/chat with a message — should 200 (AI may fail upstream, that's ok)."""
    r = session.post(f"{BASE_URL}/api/ai/chat", json={"message": "hello"})
    assert r.status_code < 500, f"Server error {r.status_code}: {r.text}"


def test_post_stream_empty_body(session):
    """POST /api/ai/chat/stream with empty body — should 422."""
    r = session.post(f"{BASE_URL}/api/ai/chat/stream", json={})
    assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"


def test_unauthenticated_chat_blocked():
    """GET /api/ai/chat/conversations without token — should 401/403."""
    if not BASE_URL:
        pytest.skip("No REACT_APP_BACKEND_URL set — no live server")
    r = requests.get(f"{BASE_URL}/api/ai/chat/conversations")
    assert r.status_code in (401, 403, 404), f"Unexpected {r.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])