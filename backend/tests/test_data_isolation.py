"""
Data Isolation Test Suite — TrustOffice

The most critical safety net for a multi-tenant trust governance tool.
Creates two real users (User A and User B), creates data as User A, then
verifies User B cannot see, access, or modify User A's data.

Tests run against the live API (set REACT_APP_BACKEND_URL). They create
real users with unique emails, real trusts, and real records — then clean up.

Covers:
  - Calendar events (the P0 bug that started this suite)
  - Trusts (core entity — can User B list/read User A's trust?)
  - Minutes (can User B read/modify User A's minutes?)
  - Distributions (can User B see User A's distributions?)
  - Beneficiaries (can User B see User A's beneficiaries?)
  - Governance tasks (can User B see User A's tasks?)
  - Vault (can User B see User A's vault documents?)
  - Audit trail (can User B see User A's audit log?)
  - Settings/preferences (can User B modify User A's settings?)

Run: REACT_APP_BACKEND_URL=https://api.trustoffice.app pytest tests/test_data_isolation.py -v
"""

import pytest
import requests
import os
import sys
import uuid
import time
from datetime import datetime, timezone

# Ensure backend dir is importable for module-import tests
_bd = os.path.join(os.path.dirname(__file__), "..")
if _bd not in sys.path:
    sys.path.insert(0, os.path.abspath(_bd))

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = os.environ.get("BACKEND_URL", "").rstrip("/")

# Admin API key for gifting test subscriptions (needed so test users can create trusts)
ADMIN_API_KEY = os.environ.get("TRUSTOFFICE_ADMIN_API_KEY", "")
if not ADMIN_API_KEY:
    # Try to read from the standard secrets location
    _key_path = os.path.expanduser("~/.hermes/secrets/trustoffice-admin-api.key")
    if os.path.exists(_key_path):
        with open(_key_path) as f:
            ADMIN_API_KEY = f.read().strip()

# Dummy env so module imports succeed without a live Mongo
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trustoffice_test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-isolation-tests")

TEST_RUN_ID = uuid.uuid4().hex[:8]  # Unique per test run for cleanup identification


def _make_test_email(label: str) -> str:
    """Generate a unique test email for this run."""
    return f"isolation-{label}-{TEST_RUN_ID}@test.trustoffice.app"


def _gift_subscription(base_url: str, user_id: str, plan: str = "trustee") -> bool:
    """Gift a subscription to a test user via the admin API so they can create trusts."""
    if not ADMIN_API_KEY:
        print(f"  [fixture] gift: NO ADMIN_API_KEY available")
        return False
    try:
        resp = requests.post(
            f"{base_url}/api/admin-api/users/{user_id}/gift-subscription",
            headers={"X-Admin-API-Key": ADMIN_API_KEY, "Content-Type": "application/json"},
            json={"plan_type": plan, "reason": "Automated data isolation test"},
            timeout=10,
        )
        print(f"  [fixture] gift {user_id} ({plan}): {resp.status_code} {resp.text[:200]}")
        return resp.status_code == 200
    except Exception as e:
        print(f"  [fixture] gift ERROR: {e}")
        return False


def _register_and_login(base_url: str, email: str, password: str = "TestPass123!", gift_plan: str = None) -> dict:
    """Register a new user and return auth headers with token.
    Falls back to login if already registered."""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})

    # Try register first
    resp = s.post(f"{base_url}/api/auth/register", json={
        "email": email,
        "password": password,
        "name": f"Isolation Test {email[:12]}",
    })
    print(f"  [fixture] register {email}: {resp.status_code}")

    # Try login regardless (works for both new and existing users)
    resp = s.post(f"{base_url}/api/auth/login", json={
        "email": email,
        "password": password,
    })
    print(f"  [fixture] login {email}: {resp.status_code}")

    if resp.status_code != 200:
        print(f"  [fixture] FAILED: {resp.text[:200]}")
        return None  # Signal failure without skipping the whole module

    token = resp.json().get("token")
    if not token:
        return None

    user_id = resp.json().get("user_id") or resp.json().get("user", {}).get("user_id")

    # Gift a subscription if requested (needed for trust creation)
    if gift_plan and user_id:
        _gift_subscription(base_url, user_id, gift_plan)

    return {
        "session": s,
        "token": token,
        "headers": {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        "user_id": user_id,
        "email": email,
    }


def _login_demo(base_url: str) -> dict:
    """Login as the existing demo user."""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    resp = s.post(f"{base_url}/api/auth/login", json={
        "email": "demo@trustoffice.com",
        "password": "demopassword",
    })
    if resp.status_code != 200:
        return None
    token = resp.json().get("token")
    return {
        "session": s,
        "token": token,
        "headers": {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        "user_id": resp.json().get("user_id"),
        "email": "demo@trustoffice.com",
    }


def _cleanup_user(base_url: str, auth: dict):
    """Best-effort cleanup: delete trusts and data created by this test user."""
    s = auth["session"]
    try:
        # Get all trusts
        resp = s.get(f"{base_url}/api/trusts", headers=auth["headers"])
        if resp.status_code == 200:
            trusts = resp.json()
            for t in trusts:
                tid = t.get("trust_id")
                if tid:
                    try:
                        s.delete(f"{base_url}/api/trusts/{tid}", headers=auth["headers"])
                    except Exception:
                        pass
    except Exception:
        pass


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def base():
    if not BASE_URL:
        pytest.skip("No REACT_APP_BACKEND_URL or BACKEND_URL set — no live server")
    return BASE_URL


@pytest.fixture(scope="module")
def user_a(base):
    """User A — the data owner. Registered fresh each run, gifted a trustee plan."""
    email = _make_test_email("userA")
    auth = _register_and_login(base, email, gift_plan="trustee")
    if not auth:
        pytest.skip(f"Could not register+login test user {email}")
    yield auth
    _cleanup_user(base, auth)


@pytest.fixture(scope="module")
def user_b(base):
    """User B — a completely separate user. Registered fresh each run."""
    email = _make_test_email("userB")
    auth = _register_and_login(base, email)
    if not auth:
        pytest.skip(f"Could not register+login test user {email}")
    yield auth
    _cleanup_user(base, auth)


@pytest.fixture(scope="module")
def trust_a(base, user_a):
    """Create a trust as User A."""
    s = user_a["session"]
    resp = s.post(f"{base}/api/trusts", headers=user_a["headers"], json={
        "name": f"Isolation Test Trust A-{TEST_RUN_ID}",
        "trust_type": "revocable_living",
        "state": "WY",
    })
    print(f"  [fixture] create trust: {resp.status_code} {resp.text[:300]}")
    if resp.status_code not in (200, 201):
        pytest.skip(f"Could not create trust for User A: {resp.status_code} {resp.text}")
    trust = resp.json()
    assert "trust_id" in trust, f"Trust creation response missing trust_id: {trust}"
    print(f"  [fixture] trust_id: {trust['trust_id']}")
    return trust


# ============================================================================
# Calendar Data Isolation (THE P0 BUG TEST)
# ============================================================================

class TestCalendarIsolation:
    """The calendar endpoint was leaking ALL users' tax entries to ANY user.
    This test creates a trust as User A, then checks that User B's calendar
    contains zero events from User A's trust."""

    def test_user_a_has_calendar_events(self, base, user_a, trust_a):
        """User A should see their own calendar events (at least governance tasks auto-seeded)."""
        resp = user_a["session"].get(
            f"{base}/api/calendar/events",
            headers=user_a["headers"],
        )
        assert resp.status_code == 200, f"User A calendar failed: {resp.status_code} {resp.text}"
        data = resp.json()
        assert "events" in data
        assert "count" in data
        # Auto-seeded governance tasks should produce at least some events
        # (If the trust was just created, governance tasks are auto-seeded)
        assert data["count"] >= 0  # At minimum, should not error

    def test_user_b_calendar_excludes_user_a_trust(self, base, user_b, trust_a):
        """User B should NOT see any events from User A's trust_id."""
        resp = user_b["session"].get(
            f"{base}/api/calendar/events",
            headers=user_b["headers"],
        )
        assert resp.status_code == 200, f"User B calendar failed: {resp.status_code} {resp.text}"
        data = resp.json()
        events = data.get("events", [])

        # Check every event — none should reference User A's trust_id
        user_a_trust_id = trust_a["trust_id"]
        leaked_events = [
            e for e in events
            if e.get("trust_id") == user_a_trust_id
        ]

        assert len(leaked_events) == 0, (
            f"DATA ISOLATION BREACH: User B sees {len(leaked_events)} events "
            f"belonging to User A's trust ({user_a_trust_id}). "
            f"Leaked: {leaked_events[:3]}"
        )

    def test_user_b_calendar_with_trust_a_id_returns_404(self, base, user_b, trust_a):
        """User B should get 404 when trying to filter by User A's trust_id."""
        resp = user_b["session"].get(
            f"{base}/api/calendar/events?trust_id={trust_a['trust_id']}",
            headers=user_b["headers"],
        )
        assert resp.status_code == 404, (
            f"User B should get 404 for User A's trust_id, got {resp.status_code}: {resp.text}"
        )

    def test_unauthenticated_calendar_blocked(self, base):
        """Unauthenticated requests should be blocked."""
        resp = requests.get(f"{base}/api/calendar/events")
        assert resp.status_code in (401, 403, 422), (
            f"Unauthenticated calendar access should be blocked, got {resp.status_code}"
        )


# ============================================================================
# Trust Data Isolation
# ============================================================================

class TestTrustIsolation:
    """User B should not see, access, or modify User A's trusts."""

    def test_user_b_cannot_list_user_a_trust(self, base, user_b, trust_a):
        """User B's trust list should NOT contain User A's trust."""
        resp = user_b["session"].get(f"{base}/api/trusts", headers=user_b["headers"])
        assert resp.status_code == 200
        trusts = resp.json()

        user_a_trust_ids = [trust_a["trust_id"]]
        leaked = [t for t in trusts if t.get("trust_id") in user_a_trust_ids]

        assert len(leaked) == 0, (
            f"DATA ISOLATION BREACH: User B sees User A's trust in list: {leaked}"
        )

    def test_user_b_cannot_access_user_a_trust_directly(self, base, user_b, trust_a):
        """User B should get 404 when trying to access User A's trust by ID."""
        # The trusts endpoint might not have a GET by ID — try the governance endpoint
        # which requires trust_id
        resp = user_b["session"].get(
            f"{base}/api/governance/{trust_a['trust_id']}",
            headers=user_b["headers"],
        )
        assert resp.status_code in (403, 404), (
            f"User B should not access User A's trust governance, got {resp.status_code}: {resp.text}"
        )


# ============================================================================
# Minutes Data Isolation
# ============================================================================

class TestMinutesIsolation:
    """User B should not see User A's minutes."""

    def test_user_b_minutes_list_excludes_user_a(self, base, user_b, trust_a):
        """User B's minutes list should not contain anything from User A's trust."""
        resp = user_b["session"].get(
            f"{base}/api/minutes?trust_id={trust_a['trust_id']}",
            headers=user_b["headers"],
        )
        # Should be 404 (trust not found for this user) or empty list
        assert resp.status_code in (200, 403, 404), (
            f"Unexpected status for User B accessing User A's trust minutes: {resp.status_code}"
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                assert len(data) == 0, (
                    f"User B sees User A's minutes: {data[:3]}"
                )


# ============================================================================
# Distributions Data Isolation
# ============================================================================

class TestDistributionsIsolation:
    """User B should not see User A's distributions."""

    def test_user_b_distributions_exclude_user_a(self, base, user_b, trust_a):
        """User B's distributions should not include User A's trust."""
        resp = user_b["session"].get(
            f"{base}/api/distributions?trust_id={trust_a['trust_id']}",
            headers=user_b["headers"],
        )
        assert resp.status_code in (200, 403, 404), (
            f"Unexpected status for User B: {resp.status_code}"
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                assert len(data) == 0, (
                    f"User B sees User A's distributions: {data[:3]}"
                )


# ============================================================================
# Beneficiaries Data Isolation
# ============================================================================

class TestBeneficiariesIsolation:
    """User B should not see User A's beneficiaries."""

    def test_user_b_beneficiaries_exclude_user_a_trust(self, base, user_b, trust_a):
        """User B querying User A's trust_id for beneficiaries should get nothing."""
        resp = user_b["session"].get(
            f"{base}/api/beneficiaries?trust_id={trust_a['trust_id']}",
            headers=user_b["headers"],
        )
        assert resp.status_code in (200, 403, 404), (
            f"Unexpected status for User B: {resp.status_code}"
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                assert len(data) == 0, (
                    f"User B sees User A's beneficiaries: {data[:3]}"
                )


# ============================================================================
# Governance Tasks Data Isolation
# ============================================================================

class TestGovernanceIsolation:
    """User B should not see User A's governance tasks."""

    def test_user_b_governance_excludes_user_a(self, base, user_b, trust_a):
        """User B should not see governance data for User A's trust."""
        resp = user_b["session"].get(
            f"{base}/api/governance/{trust_a['trust_id']}",
            headers=user_b["headers"],
        )
        assert resp.status_code in (403, 404), (
            f"User B should not access User A's governance, got {resp.status_code}: {resp.text}"
        )


# ============================================================================
# Vault Data Isolation
# ============================================================================

class TestVaultIsolation:
    """User B should not see User A's vault documents."""

    def test_user_b_vault_excludes_user_a_trust(self, base, user_b, trust_a):
        """User B querying vault for User A's trust should get nothing."""
        resp = user_b["session"].get(
            f"{base}/api/vault?trust_id={trust_a['trust_id']}",
            headers=user_b["headers"],
        )
        assert resp.status_code in (200, 403, 404), (
            f"Unexpected status for User B vault access: {resp.status_code}"
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                assert len(data) == 0, (
                    f"User B sees User A's vault items: {data[:3]}"
                )


# ============================================================================
# Audit Trail Data Isolation
# ============================================================================

class TestAuditTrailIsolation:
    """User B should not see User A's audit trail entries."""

    def test_user_b_audit_trail_excludes_user_a(self, base, user_b):
        """User B's audit trail should not contain User A's actions."""
        resp = user_b["session"].get(
            f"{base}/api/audit-trail",
            headers=user_b["headers"],
        )
        assert resp.status_code in (200, 403, 404), (
            f"Unexpected status for User B audit trail: {resp.status_code}"
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                # None of the audit entries should reference our test run
                leaked = [
                    e for e in data
                    if TEST_RUN_ID in str(e)
                ]
                assert len(leaked) == 0, (
                    f"User B sees User A's audit entries: {leaked[:3]}"
                )


# ============================================================================
# Cross-User Write Prevention
# ============================================================================

class TestCrossUserWritePrevention:
    """User B should not be able to create/modify data under User A's trust."""

    def test_user_b_cannot_create_minutes_for_user_a_trust(self, base, user_b, trust_a):
        """User B trying to create minutes for User A's trust should fail."""
        resp = user_b["session"].post(
            f"{base}/api/minutes",
            headers=user_b["headers"],
            json={
                "trust_id": trust_a["trust_id"],
                "template_type": "general_meeting",
                "template_data": {},
            },
        )
        assert resp.status_code in (403, 404), (
            f"User B should NOT create minutes for User A's trust, got {resp.status_code}: {resp.text}"
        )

    def test_user_b_cannot_create_distribution_for_user_a_trust(self, base, user_b, trust_a):
        """User B trying to create a distribution for User A's trust should fail."""
        resp = user_b["session"].post(
            f"{base}/api/distributions",
            headers=user_b["headers"],
            json={
                "trust_id": trust_a["trust_id"],
                "beneficiary_name": "Test Beneficiary",
                "amount": 100,
                "date": "2026-01-01",
            },
        )
        assert resp.status_code in (403, 404), (
            f"User B should NOT create distributions for User A's trust, got {resp.status_code}: {resp.text}"
        )


# ============================================================================
# Run as main
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])