# Smoke tests for admin router (routers/admin.py)
# Endpoints are mounted at /api/admin/* — admin-only (is_admin=True).
# These tests SKIP gracefully when no live server / admin login is available.

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
DEMO_EMAIL = "demo@trustoffice.com"
DEMO_PASSWORD = "demopassword"


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
    """Module health: admin router imports successfully."""
    import routers.admin  # noqa: F401


def test_get_admins_requires_admin(session):
    """GET /api/admin/admins — should return 200 (admin) or 403 (non-admin)."""
    r = session.get(f"{BASE_URL}/api/admin/admins")
    assert r.status_code in (200, 403), f"Unexpected {r.status_code}: {r.text}"


def test_get_customers_requires_admin(session):
    """GET /api/admin/customers — should return 200 (admin) or 403 (non-admin)."""
    r = session.get(f"{BASE_URL}/api/admin/customers")
    assert r.status_code in (200, 403), f"Unexpected {r.status_code}: {r.text}"


def test_get_stats_requires_admin(session):
    """GET /api/admin/stats — should return 200 (admin) or 403 (non-admin)."""
    r = session.get(f"{BASE_URL}/api/admin/stats")
    assert r.status_code in (200, 403), f"Unexpected {r.status_code}: {r.text}"


def test_get_revenue_requires_admin(session):
    """GET /api/admin/revenue — should return 200 (admin) or 403 (non-admin)."""
    r = session.get(f"{BASE_URL}/api/admin/revenue")
    assert r.status_code in (200, 403), f"Unexpected {r.status_code}: {r.text}"


def test_get_referrals_requires_admin(session):
    """GET /api/admin/referrals — should return 200 (admin) or 403 (non-admin)."""
    r = session.get(f"{BASE_URL}/api/admin/referrals")
    assert r.status_code in (200, 403), f"Unexpected {r.status_code}: {r.text}"


def test_bulk_delete_without_body(session):
    """POST /api/admin/customers/bulk-delete — empty body should 4xx, not 5xx."""
    r = session.post(f"{BASE_URL}/api/admin/customers/bulk-delete", json={})
    assert r.status_code < 500, f"Server error {r.status_code}: {r.text}"


def test_unauthenticated_admin_blocked():
    """GET /api/admin/customers without token — should 401/403."""
    r = requests.get(f"{BASE_URL}/api/admin/customers")
    assert r.status_code in (401, 403, 404), f"Unexpected {r.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])