# Smoke tests for external router (routers/external.py)
# Endpoints mounted at /api/external/* — partner API (Bearer API key auth).
# These tests SKIP gracefully when no live server is available.

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
# Optional partner API key — if unset, endpoints will 401 (still a valid smoke signal)
EXTERNAL_API_KEY = os.environ.get("EXTERNAL_API_KEY", "")


@pytest.fixture(scope="module")
def session():
    if not BASE_URL:
        pytest.skip("No REACT_APP_BACKEND_URL set — no live server")
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    if EXTERNAL_API_KEY:
        s.headers.update({"Authorization": f"Bearer {EXTERNAL_API_KEY}"})
    return s


def test_module_imports():
    """Module health: external router imports successfully."""
    import routers.external  # noqa: F401


def test_provision_trustoffice_requires_auth(session):
    """POST /api/external/provision-trustoffice without valid key — should 401."""
    if EXTERNAL_API_KEY:
        pytest.skip("API key configured — auth test would mutate state")
    r = session.post(f"{BASE_URL}/api/external/provision-trustoffice", json={})
    assert r.status_code in (401, 422), f"Unexpected {r.status_code}: {r.text}"


def test_provision_dry_run_requires_auth(session):
    """POST /api/external/provision-trustoffice/dry-run without valid key — should 401."""
    # dry-run does not persist, but still requires auth
    if EXTERNAL_API_KEY:
        r = session.post(f"{BASE_URL}/api/external/provision-trustoffice/dry-run", json={})
        assert r.status_code in (200, 400, 422), f"Unexpected {r.status_code}: {r.text}"
    else:
        r = session.post(f"{BASE_URL}/api/external/provision-trustoffice/dry-run", json={})
        assert r.status_code in (401, 422), f"Unexpected {r.status_code}: {r.text}"


def test_status_requires_auth(session):
    """GET /api/external/provision-trustoffice/status without valid key — should 401."""
    r = session.get(f"{BASE_URL}/api/external/provision-trustoffice/status")
    assert r.status_code in (401, 404, 422), f"Unexpected {r.status_code}: {r.text}"


def test_lookup_user_requires_auth(session):
    """GET /api/external/lookup-user without valid key — should 401."""
    if EXTERNAL_API_KEY:
        r = session.get(f"{BASE_URL}/api/external/lookup-user?email=test@example.com")
        assert r.status_code in (200, 404), f"Unexpected {r.status_code}: {r.text}"
    else:
        r = session.get(f"{BASE_URL}/api/external/lookup-user?email=test@example.com")
        assert r.status_code in (401, 422), f"Unexpected {r.status_code}: {r.text}"


def test_link_trust_requires_auth(session):
    """POST /api/external/link-trust without valid key — should 401."""
    if EXTERNAL_API_KEY:
        pytest.skip("API key configured — link-trust test would mutate state")
    r = session.post(f"{BASE_URL}/api/external/link-trust", json={})
    assert r.status_code in (401, 422), f"Unexpected {r.status_code}: {r.text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])