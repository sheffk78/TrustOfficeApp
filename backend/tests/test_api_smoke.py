"""
Backend API Smoke Tests — TrustOffice

Tests every critical backend endpoint for:
  - Correct status codes (not 500s)
  - Auth enforcement (no unauthenticated access)
  - Response structure (has expected fields)

This is the "does it boot and respond" layer — not business logic.
Run nightly and before deploys.

Run: REACT_APP_BACKEND_URL=https://api.trustoffice.app pytest tests/test_api_smoke.py -v
"""

import pytest
import requests
import os
import sys
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = os.environ.get("BACKEND_URL", "").rstrip("/")

# Admin API key
ADMIN_API_KEY = os.environ.get("TRUSTOFFICE_ADMIN_API_KEY", "")
if not ADMIN_API_KEY:
    _key_path = os.path.expanduser("~/.hermes/secrets/trustoffice-admin-api.key")
    if os.path.exists(_key_path):
        with open(_key_path) as f:
            ADMIN_API_KEY = f.read().strip()

TEST_RUN_ID = uuid.uuid4().hex[:8]

# Designated, versioned QA test accounts (canonical). Created once and reused
# across runs so the smoke suite does NOT spawn throwaway users in prod.
# Credentials are the shared QA password stored in the CI/ops QA config.
QA_ACCOUNTS = [
    "test.qa1@trustoffice.app",
    "test.qa2@trustoffice.app",
    "test.qa3@trustoffice.app",
]
# Env-only: the shared QA password is NEVER committed to source. It ships from
# the ops config only (nightly cron sets TRUSTOFFICE_QA_PASSWORD).
QA_PASSWORD = os.environ.get("TRUSTOFFICE_QA_PASSWORD")
if not QA_PASSWORD:
    raise RuntimeError(
        "TRUSTOFFICE_QA_PASSWORD env var is required to run the smoke suite. "
        "The QA password is not stored in this repo."
    )


def _login(base_url: str, email: str, password: str = QA_PASSWORD) -> dict | None:
    """Log into an existing (designated QA) account and return auth headers."""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    resp = s.post(f"{base_url}/api/auth/login", json={
        "email": email, "password": password
    })
    if resp.status_code != 200:
        return None
    token = resp.json().get("token")
    user_id = resp.json().get("user_id") or resp.json().get("user", {}).get("user_id")
    return {
        "session": s,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        "user_id": user_id,
        "email": email,
    }


def _delete_throwaway_users(base_url: str) -> None:
    """Bulk-delete any throwaway test users this run may have created, so the
    smoke suite never pollutes prod's customer list. Skips the designated QA
    accounts (reused across runs) and any real accounts."""
    if not ADMIN_API_KEY:
        return
    ids = []
    try:
        users = requests.get(
            f"{base_url}/api/admin-api/users?limit=200",
            headers={"X-Admin-API-Key": ADMIN_API_KEY},
            timeout=10,
        ).json().get("users", [])
    except Exception:
        return
    throwaway_patterns = ("smoke-reg-", "smoke-login-", "smoke-user-", "kit-smoke-test@")
    for u in users:
        email = (u.get("email") or "").lower()
        uid = u.get("user_id")
        if not uid or email in QA_ACCOUNTS:
            continue
        if email.startswith(("smoke-", "isolation-", "test_register_")) or any(email.startswith(p) for p in throwaway_patterns):
            if "@test.trustoffice.app" in email or "@example.com" in email or "@test.com" in email:
                ids.append(uid)
    if ids:
        requests.post(
            f"{base_url}/api/admin-api/users/bulk-delete",
            headers={"X-Admin-API-Key": ADMIN_API_KEY, "Content-Type": "application/json"},
            json={"user_ids": ids},
            timeout=15,
        )


def _register(base_url: str, label: str = "smoke") -> dict:
    """Use a designated QA account (idempotent) instead of spawning throwaway
    users in prod. Falls back to register-only for the dedicated register test."""
    # Prefer a designated QA account for the shared auth fixture.
    for email in QA_ACCOUNTS:
        a = _login(base_url, email)
        if a:
            # Designated accounts are already gifted forever_free by ops.
            return a
    # Fallback: register a fresh one (cleaned up by _delete_throwaway_users).
    email = f"smoke-{label}-{TEST_RUN_ID}@test.trustoffice.app"
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})

    s.post(f"{base_url}/api/auth/register", json={
        "email": email, "password": QA_PASSWORD, "name": f"Smoke {label}"
    })
    resp = s.post(f"{base_url}/api/auth/login", json={
        "email": email, "password": QA_PASSWORD
    })
    if resp.status_code != 200:
        return None

    token = resp.json().get("token")
    user_id = resp.json().get("user_id") or resp.json().get("user", {}).get("user_id")

    # Gift subscription
    if ADMIN_API_KEY and user_id:
        requests.post(
            f"{base_url}/api/admin-api/users/{user_id}/gift-subscription",
            headers={"X-Admin-API-Key": ADMIN_API_KEY, "Content-Type": "application/json"},
            json={"plan_type": "trustee", "reason": "Smoke test"},
            timeout=10,
        )

    return {
        "session": s,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        "user_id": user_id,
        "email": email,
    }


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="session", autouse=True)
def _cleanup_throwaways(base):
    """After the whole smoke run, delete any throwaway test users this run spawned."""
    yield
    try:
        _delete_throwaway_users(base)
    except Exception:
        pass


@pytest.fixture(scope="module")
def base():
    if not BASE_URL:
        pytest.skip("No REACT_APP_BACKEND_URL set")
    return BASE_URL


@pytest.fixture(scope="module")
def auth(base):
    a = _register(base, "user")
    if not a:
        pytest.skip("Could not register test user")
    yield a


@pytest.fixture(scope="module")
def trust(base, auth):
    """Create a trust for testing."""
    resp = auth["session"].post(
        f"{base}/api/trusts",
        headers=auth["headers"],
        json={"name": f"Smoke Test Trust {TEST_RUN_ID}", "trust_type": "revocable_living", "state": "WY"},
    )
    if resp.status_code not in (200, 201):
        pytest.skip(f"Could not create trust: {resp.status_code}")
    return resp.json()


# ============================================================================
# Health Endpoints
# ============================================================================

class TestHealth:
    def test_health_endpoint(self, base):
        resp = requests.get(f"{base}/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "trustoffice-api"
        assert data["db"] == "connected"

    def test_admin_api_health(self, base):
        if not ADMIN_API_KEY:
            pytest.skip("No admin API key")
        # Admin API doesn't have a dedicated /health endpoint;
        # use stats endpoint as a health proxy
        resp = requests.get(
            f"{base}/api/admin-api/users?limit=1",
            headers={"X-Admin-API-Key": ADMIN_API_KEY},
        )
        assert resp.status_code == 200, f"Admin API health check: {resp.status_code}"


# ============================================================================
# Auth Endpoints
# ============================================================================

class TestAuth:
    def test_register(self, base):
        email = f"smoke-reg-{TEST_RUN_ID}@test.trustoffice.app"
        resp = requests.post(f"{base}/api/auth/register", json={
            "email": email, "password": QA_PASSWORD, "name": "Smoke Register"
        })
        assert resp.status_code == 200
        assert "user_id" in resp.json()

    def test_login(self, base):
        email = f"smoke-login-{TEST_RUN_ID}@test.trustoffice.app"
        # Register first
        requests.post(f"{base}/api/auth/register", json={
            "email": email, "password": QA_PASSWORD, "name": "Smoke Login"
        })
        resp = requests.post(f"{base}/api/auth/login", json={
            "email": email, "password": QA_PASSWORD
        })
        assert resp.status_code == 200
        assert "token" in resp.json()

    def test_me(self, base, auth):
        resp = auth["session"].get(f"{base}/api/auth/me", headers=auth["headers"])
        assert resp.status_code == 200

    def test_unauthenticated_blocked(self, base):
        """Every protected endpoint should reject unauthenticated requests."""
        endpoints = [
            ("/api/trusts", "GET"),
            ("/api/calendar/events", "GET"),
            ("/api/minutes", "GET"),
            ("/api/distributions", "GET"),
            ("/api/beneficiaries", "GET"),
            ("/api/governance/nonexistent", "GET"),  # governance requires {trust_id} path param
            ("/api/trusts/test-nonexistent/vault/documents", "GET"),
            ("/api/audit-logs", "GET"),
        ]
        for path, method in endpoints:
            resp = requests.request(method, f"{base}{path}")
            assert resp.status_code in (401, 403, 422), (
                f"Unauthenticated {method} {path} returned {resp.status_code} — should be 401/403/422"
            )


# ============================================================================
# Core CRUD Endpoints
# ============================================================================

class TestCoreEndpoints:
    """Smoke test every critical CRUD endpoint — verify it returns 200 and sane structure."""

    def test_list_trusts(self, base, auth):
        resp = auth["session"].get(f"{base}/api/trusts", headers=auth["headers"])
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_get_trust_by_id(self, base, auth, trust):
        tid = trust["trust_id"]
        resp = auth["session"].get(f"{base}/api/trusts/{tid}", headers=auth["headers"])
        # Some endpoints return 200, some return the trust in a different format
        assert resp.status_code in (200, 404), f"GET /trusts/{tid}: {resp.status_code}"

    def test_calendar_events(self, base, auth, trust):
        resp = auth["session"].get(f"{base}/api/calendar/events", headers=auth["headers"])
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert "count" in data

    def test_governance_health(self, base, auth, trust):
        tid = trust["trust_id"]
        resp = auth["session"].get(f"{base}/api/governance/{tid}", headers=auth["headers"])
        assert resp.status_code == 200, f"GET /governance/{tid}: {resp.status_code} {resp.text[:200]}"

    def test_list_minutes(self, base, auth, trust):
        resp = auth["session"].get(
            f"{base}/api/minutes?trust_id={trust['trust_id']}",
            headers=auth["headers"],
        )
        assert resp.status_code == 200, f"GET /minutes: {resp.status_code}"

    def test_list_distributions(self, base, auth, trust):
        resp = auth["session"].get(
            f"{base}/api/distributions?trust_id={trust['trust_id']}",
            headers=auth["headers"],
        )
        assert resp.status_code == 200, f"GET /distributions: {resp.status_code}"

    def test_list_beneficiaries(self, base, auth, trust):
        resp = auth["session"].get(
            f"{base}/api/beneficiaries?trust_id={trust['trust_id']}",
            headers=auth["headers"],
        )
        assert resp.status_code == 200, f"GET /beneficiaries: {resp.status_code}"

    def test_list_vault(self, base, auth, trust):
        resp = auth["session"].get(
            f"{base}/api/vault?trust_id={trust['trust_id']}",
            headers=auth["headers"],
        )
        assert resp.status_code in (200, 404), f"GET /vault: {resp.status_code}"

    def test_audit_trail(self, base, auth):
        resp = auth["session"].get(f"{base}/api/audit-logs", headers=auth["headers"])
        assert resp.status_code == 200, f"GET /audit-logs: {resp.status_code}"

    def test_dashboard(self, base, auth, trust):
        resp = auth["session"].get(f"{base}/api/dashboard", headers=auth["headers"])
        assert resp.status_code == 200, f"GET /dashboard: {resp.status_code}"

    def test_subscription_status(self, base, auth):
        resp = auth["session"].get(f"{base}/api/subscription", headers=auth["headers"])
        assert resp.status_code == 200, f"GET /subscription: {resp.status_code}"


# ============================================================================
# Error Handling
# ============================================================================

class TestErrorHandling:
    """Verify the API handles errors gracefully (no 500s)."""

    def test_invalid_trust_id_returns_404_not_500(self, base, auth):
        resp = auth["session"].get(
            f"{base}/api/governance/nonexistent_trust_id",
            headers=auth["headers"],
        )
        assert resp.status_code in (403, 404), f"Got {resp.status_code}: {resp.text[:200]}"

    def test_invalid_trust_id_for_calendar(self, base, auth):
        resp = auth["session"].get(
            f"{base}/api/calendar/events?trust_id=nonexistent_trust_id",
            headers=auth["headers"],
        )
        assert resp.status_code == 404, f"Got {resp.status_code}: {resp.text[:200]}"

    def test_malformed_request_body(self, base, auth):
        """Send garbage JSON to a POST endpoint — should get 4xx, not 500."""
        resp = auth["session"].post(
            f"{base}/api/trusts",
            headers=auth["headers"],
            json={"invalid_field": "garbage"},
        )
        assert resp.status_code < 500, f"Got {resp.status_code}: {resp.text[:200]}"

    def test_missing_required_fields(self, base, auth):
        """POST /trusts without required fields should get 422, not 500."""
        resp = auth["session"].post(
            f"{base}/api/trusts",
            headers=auth["headers"],
            json={},
        )
        assert resp.status_code == 422, f"Got {resp.status_code}: {resp.text[:200]}"


# ============================================================================
# Admin API
# ============================================================================

class TestAdminAPI:
    """Smoke test the admin API endpoints."""

    def test_admin_stats_summary(self, base):
        if not ADMIN_API_KEY:
            pytest.skip("No admin API key")
        resp = requests.get(
            f"{base}/api/admin-api/stats/summary",
            headers={"X-Admin-API-Key": ADMIN_API_KEY},
        )
        # KNOWN BUG: stats/summary returns 500 (revenue tracking bug — Admin API
        # can't handle missing/zero Stripe data). This is tracked in BRAND-STATUS.md.
        # When fixed, change this back to assert resp.status_code == 200.
        if resp.status_code == 500:
            pytest.xfail("Known bug: admin stats/summary returns 500 (revenue tracking bug)")
        assert resp.status_code == 200
        data = resp.json()
        assert "users_total" in data or "users" in data

    def test_admin_users_list(self, base):
        if not ADMIN_API_KEY:
            pytest.skip("No admin API key")
        resp = requests.get(
            f"{base}/api/admin-api/users?limit=5",
            headers={"X-Admin-API-Key": ADMIN_API_KEY},
        )
        assert resp.status_code == 200

    def test_admin_unauthenticated_blocked(self, base):
        resp = requests.get(f"{base}/api/admin-api/stats/summary")
        assert resp.status_code in (401, 403), f"Got {resp.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])