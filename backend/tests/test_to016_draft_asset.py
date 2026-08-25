"""
TO-016: Draft Schedule A asset automation from minutes.

Tests the full flow:
1. Create minutes from initial_trustee_meeting template with bank account info
2. Finalize the minutes → draft Schedule A asset auto-created
3. Verify draft asset appears in GET /schedule-a?status=active (the fix)
4. Confirm the draft asset → becomes active
5. Verify duplicate prevention — re-finalize does not create second draft
6. Verify minutes without bank info → no draft asset created
7. Verify response includes draft_asset_created flag

Live HTTP tests against deployed backend. Skips gracefully without REACT_APP_BACKEND_URL.
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
DEMO_EMAIL = "demo@trustoffice.com"
DEMO_PASSWORD = "demopassword"
TRUST_ID = "trust_b753cb8fe07f"

# database.py reads MONGO_URL/DB_NAME at import time; set dummies so module
# imports work without a live Mongo.
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


# ==================== Helper: create & finalize minutes ====================

def _create_bank_account_minutes(session, unique_suffix, bank_name="Test Bank", account_number="1234567890", initial_deposit="5000"):
    """Create a minutes template with bank account info. Returns minutes_id."""
    payload = {
        "trust_id": TRUST_ID,
        "template_type": "initial_trustee_meeting",
        "template_data": {
            "meeting_date": "2025-01-15",
            "trustees_present": [f"TEST_Trustee_{unique_suffix}"],
            "bank_name": bank_name,
            "account_number": account_number,
            "account_type": "checking",
            "initial_deposit": initial_deposit,
        }
    }
    r = session.post(f"{BASE_URL}/api/minutes-templates", json=payload)
    assert r.status_code == 200, f"Create minutes failed: {r.text}"
    return r.json()["minutes_id"]


def _finalize_minutes(session, minutes_id):
    """Finalize minutes via PUT. Returns response JSON."""
    r = session.put(f"{BASE_URL}/api/minutes/{minutes_id}", json={"status": "finalized"})
    assert r.status_code == 200, f"Finalize failed: {r.text}"
    return r.json()


def _get_schedule_a_active(session):
    """Get active Schedule A items (should include drafts per TO-016 fix)."""
    r = session.get(f"{BASE_URL}/api/schedule-a?trust_id={TRUST_ID}&status=active")
    assert r.status_code == 200, f"GET schedule-a failed: {r.text}"
    return r.json()


def _cleanup_asset(session, item_id):
    """Delete a Schedule A item (best-effort)."""
    if item_id:
        session.delete(f"{BASE_URL}/api/schedule-a/{item_id}")


# ==================== Tests ====================

class TestTO016DraftAssetFromMinutes:
    """TO-016: Auto-create draft Schedule A asset from finalized minutes with bank info."""

    def test_module_imports(self):
        """Routers import successfully (smoke)."""
        import sys
        bd = os.path.join(os.path.dirname(__file__), "..")
        if bd not in sys.path:
            sys.path.insert(0, os.path.abspath(bd))
        import routers.minutes  # noqa: F401
        import routers.schedule_a  # noqa: F401

    def test_finalize_minutes_with_bank_info_creates_draft_asset(self, session):
        """Finalizing minutes with bank_name + account_number auto-creates a draft Schedule A asset
        AND a real bank_account record."""
        uid = uuid.uuid4().hex[:8]
        minutes_id = _create_bank_account_minutes(session, uid, bank_name=f"TestBank_{uid}")

        data = _finalize_minutes(session, minutes_id)

        # Response should signal draft asset creation
        assert "draft_asset_created" in data, f"Missing draft_asset_created in response: {data}"
        assert data["draft_asset_created"] is True, f"Expected draft_asset_created=True, got: {data}"
        assert data.get("draft_asset_id"), f"Expected draft_asset_id, got: {data}"

        # Response should also signal bank account creation
        assert data.get("bank_account_created") is True, f"Expected bank_account_created=True, got: {data}"
        assert data.get("bank_account_id"), f"Expected bank_account_id, got: {data}"

        # Verify the bank account appears in the trust's banking list
        r = session.get(f"{BASE_URL}/api/trusts/{TRUST_ID}/bank-accounts")
        assert r.status_code == 200, f"GET bank-accounts failed: {r.text}"
        accounts = r.json()
        bank_acct_id = data.get("bank_account_id")
        matching = [a for a in accounts if a.get("account_id") == bank_acct_id]
        assert len(matching) == 1, f"Bank account {bank_acct_id} not found in trust accounts"
        assert matching[0]["institution_name"] == f"TestBank_{uid}"
        assert matching[0]["last_four"] == "7890"

        # Cleanup
        _cleanup_asset(session, data.get("draft_asset_id"))
        session.delete(f"{BASE_URL}/api/trusts/{TRUST_ID}/bank-accounts/{bank_acct_id}")

    def test_draft_asset_visible_in_active_tab(self, session):
        """Draft assets appear in GET /schedule-a?status=active (the TO-016 status filter fix)."""
        uid = uuid.uuid4().hex[:8]
        minutes_id = _create_bank_account_minutes(session, uid, bank_name=f"VisibleBank_{uid}")

        finalize_data = _finalize_minutes(session, minutes_id)
        draft_id = finalize_data.get("draft_asset_id")
        assert draft_id, "No draft asset created"

        # Fetch active items — drafts should be included
        result = _get_schedule_a_active(session)
        items = result.get("items", result) if isinstance(result, dict) else result

        draft_items = [a for a in items if a.get("status") == "draft" and a.get("item_id") == draft_id]
        assert len(draft_items) == 1, (
            f"Draft asset {draft_id} not found in active tab. "
            f"Total items: {len(items)}, draft items: {len([a for a in items if a.get('status') == 'draft'])}"
        )

        # Verify the draft has correct fields from bank info
        draft = draft_items[0]
        assert draft["category"] == "financial_accounts"
        assert f"VisibleBank_{uid}" in draft["description"]
        assert draft["status"] == "draft"
        # Only last 4 digits of account number should be stored
        assert "7890" in draft.get("identifier", ""), f"Expected last4 in identifier, got: {draft.get('identifier')}"

        _cleanup_asset(session, draft_id)

    def test_confirm_draft_asset_activates_it(self, session):
        """POST /schedule-a/{item_id}/confirm activates a draft asset."""
        uid = uuid.uuid4().hex[:8]
        minutes_id = _create_bank_account_minutes(session, uid, bank_name=f"ConfirmBank_{uid}")

        finalize_data = _finalize_minutes(session, minutes_id)
        draft_id = finalize_data.get("draft_asset_id")
        assert draft_id, "No draft asset created"

        # Confirm the draft
        r = session.post(f"{BASE_URL}/api/schedule-a/{draft_id}/confirm")
        assert r.status_code == 200, f"Confirm failed: {r.text}"
        confirmed = r.json()
        assert confirmed["status"] == "active", f"Expected status=active after confirm, got: {confirmed.get('status')}"

        # Verify it's now active in the list
        result = _get_schedule_a_active(session)
        items = result.get("items", result) if isinstance(result, dict) else result
        active_item = [a for a in items if a.get("item_id") == draft_id]
        assert len(active_item) == 1
        assert active_item[0]["status"] == "active"

        _cleanup_asset(session, draft_id)

    def test_duplicate_finalization_does_not_create_second_draft(self, session):
        """Re-finalizing minutes that already produced a draft does not create a duplicate."""
        uid = uuid.uuid4().hex[:8]
        minutes_id = _create_bank_account_minutes(session, uid, bank_name=f"DupBank_{uid}")

        # First finalization
        first_data = _finalize_minutes(session, minutes_id)
        first_draft_id = first_data.get("draft_asset_id")
        assert first_draft_id, "First finalization should create draft"

        # Try to finalize again — the minutes are already finalized, so this should 403/409
        # but even if it somehow succeeds, no second draft should be created
        r = session.put(f"{BASE_URL}/api/minutes/{minutes_id}", json={"status": "finalized"})
        # Already finalized → should be blocked
        assert r.status_code in (403, 409), f"Expected 403/409 for re-finalize, got {r.status_code}: {r.text}"

        # Verify only one draft exists for this minutes_id
        all_r = session.get(f"{BASE_URL}/api/schedule-a?trust_id={TRUST_ID}&status=all")
        assert all_r.status_code == 200
        all_items = all_r.json().get("items", all_r.json())
        drafts_for_minutes = [
            a for a in all_items
            if a.get("source_minutes_id") == minutes_id and a.get("status") == "draft"
        ]
        assert len(drafts_for_minutes) <= 1, (
            f"Expected at most 1 draft for minutes {minutes_id}, found {len(drafts_for_minutes)}"
        )

        _cleanup_asset(session, first_draft_id)

    def test_minutes_without_bank_info_no_draft_created(self, session):
        """Finalizing minutes without bank_name does not create a draft asset."""
        uid = uuid.uuid4().hex[:8]
        payload = {
            "trust_id": TRUST_ID,
            "template_type": "initial_trustee_meeting",
            "template_data": {
                "meeting_date": "2025-01-15",
                "trustees_present": [f"TEST_Trustee_{uid}"],
                # No bank_name, no account_number
            }
        }
        r = session.post(f"{BASE_URL}/api/minutes-templates", json=payload)
        assert r.status_code == 200, f"Create failed: {r.text}"
        minutes_id = r.json()["minutes_id"]

        data = _finalize_minutes(session, minutes_id)

        # Should NOT have created a draft asset
        assert data.get("draft_asset_created") is False, (
            f"Should not create draft without bank info, got draft_asset_created={data.get('draft_asset_created')}"
        )
        assert data.get("draft_asset_id") is None

    def test_confirm_nonexistent_draft_returns_404(self, session):
        """POST /schedule-a/{invalid_id}/confirm returns 404."""
        r = session.post(f"{BASE_URL}/api/schedule-a/asset_nonexistent_draft/confirm")
        assert r.status_code == 404, f"Expected 404 for nonexistent draft, got {r.status_code}"

    def test_draft_asset_has_audit_trail(self, session):
        """Auto-created draft asset is logged in the audit trail."""
        uid = uuid.uuid4().hex[:8]
        minutes_id = _create_bank_account_minutes(session, uid, bank_name=f"AuditBank_{uid}")

        finalize_data = _finalize_minutes(session, minutes_id)
        draft_id = finalize_data.get("draft_asset_id")
        assert draft_id, "No draft asset created"

        # Check audit trail
        r = session.get(f"{BASE_URL}/api/audit-trail?trust_id={TRUST_ID}&limit=50")
        if r.status_code == 200:
            entries = r.json()
            if isinstance(entries, dict):
                entries = entries.get("items", entries.get("records", []))
            draft_audits = [
                e for e in entries
                if e.get("action") == "draft_asset_from_minutes" and e.get("entity_id") == draft_id
            ]
            assert len(draft_audits) >= 1, (
                f"No audit trail entry found for draft asset {draft_id}. "
                f"Actions present: {[e.get('action') for e in entries[:20]]}"
            )

        _cleanup_asset(session, draft_id)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])