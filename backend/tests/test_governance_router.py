"""
Test suite for governance router endpoints migrated from server.py to routers/governance.py
Tests: Health score, History, Dashboard, Onboarding, Activity endpoints

Health score criteria (6 criteria, 20 points each = 120 max):
1. Quarterly Minutes - minutes generated this quarter
2. Task Compliance - no overdue tasks
3. Compensation Alignment - YTD ≤ approved annual
4. Distribution Documentation - at least 1 distribution logged
5. Annual Review - annual_review task completed in last 12 months
"""

import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
DEMO_USER = "demo@trustoffice.com"
DEMO_PASSWORD = "demopassword"
TRUST_ID = "trust_b753cb8fe07f"


@pytest.fixture(scope="module")
def auth_session():
    """Login and get authenticated session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": DEMO_USER,
        "password": DEMO_PASSWORD
    })
    
    if response.status_code != 200:
        pytest.skip(f"Could not authenticate: {response.status_code} - {response.text}")
    
    data = response.json()
    token = data.get("token")
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    
    return session


class TestGovernanceHealthScore:
    """Tests for GET /api/governance/{trust_id} - Health score endpoint"""
    
    def test_get_health_score_returns_200(self, auth_session):
        """Test that health score endpoint returns 200 for valid trust"""
        response = auth_session.get(f"{BASE_URL}/api/governance/{TRUST_ID}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ GET /api/governance/{TRUST_ID} returns 200")
    
    def test_health_score_has_required_fields(self, auth_session):
        """Test health score response has all required fields"""
        response = auth_session.get(f"{BASE_URL}/api/governance/{TRUST_ID}")
        assert response.status_code == 200
        
        data = response.json()
        
        # Check required top-level fields
        assert "trust_id" in data, "Missing trust_id"
        assert "total_score" in data, "Missing total_score"
        assert "max_score" in data, "Missing max_score"
        assert "color" in data, "Missing color"
        assert "criteria" in data, "Missing criteria"
        assert "calculated_at" in data, "Missing calculated_at"
        
        print(f"✓ Health score response has all required fields")
    
    def test_health_score_has_5_criteria(self, auth_session):
        """Test that health score returns exactly 5 criteria (20 points each)"""
        response = auth_session.get(f"{BASE_URL}/api/governance/{TRUST_ID}")
        assert response.status_code == 200
        
        data = response.json()
        criteria = data.get("criteria", [])
        
        assert len(criteria) == 5, f"Expected 5 criteria, got {len(criteria)}"
        
        expected_criteria_names = {
            "Quarterly Minutes",
            "Task Compliance",
            "Compensation Alignment",
            "Distribution Documentation",
            "Annual Review"
        }
        
        actual_names = {c.get("name") for c in criteria}
        assert actual_names == expected_criteria_names, f"Expected {expected_criteria_names}, got {actual_names}"
        
        print(f"✓ Health score has 5 criteria: {actual_names}")
    
    def test_health_score_criteria_structure(self, auth_session):
        """Test each criterion has required fields"""
        response = auth_session.get(f"{BASE_URL}/api/governance/{TRUST_ID}")
        assert response.status_code == 200
        
        data = response.json()
        criteria = data.get("criteria", [])
        
        for c in criteria:
            assert "name" in c, f"Criterion missing name: {c}"
            assert "description" in c, f"Criterion missing description: {c}"
            assert "points" in c, f"Criterion missing points: {c}"
            assert "achieved" in c, f"Criterion missing achieved: {c}"
            assert isinstance(c.get("points"), int), f"points should be int: {c}"
            assert isinstance(c.get("achieved"), bool), f"achieved should be bool: {c}"
        
        print(f"✓ All criteria have required fields")
    
    def test_health_score_max_score_is_120(self, auth_session):
        """Test max_score is 120"""
        response = auth_session.get(f"{BASE_URL}/api/governance/{TRUST_ID}")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("max_score") == 120, f"max_score should be 120, got {data.get('max_score')}"
        print(f"✓ max_score is 120")
    
    def test_health_score_color_valid(self, auth_session):
        """Test color is one of red/yellow/green"""
        response = auth_session.get(f"{BASE_URL}/api/governance/{TRUST_ID}")
        assert response.status_code == 200
        
        data = response.json()
        color = data.get("color")
        assert color in ["red", "yellow", "green"], f"Invalid color: {color}"
        print(f"✓ Health score color is valid: {color}")
    
    def test_health_score_invalid_trust_404(self, auth_session):
        """Test that invalid trust_id returns 404"""
        response = auth_session.get(f"{BASE_URL}/api/governance/invalid_trust_12345")
        assert response.status_code == 404, f"Expected 404 for invalid trust, got {response.status_code}"
        print(f"✓ Invalid trust returns 404")


class TestGovernanceHistory:
    """Tests for GET /api/governance/{trust_id}/history - Historical snapshots"""
    
    def test_get_history_returns_200(self, auth_session):
        """Test history endpoint returns 200"""
        response = auth_session.get(f"{BASE_URL}/api/governance/{TRUST_ID}/history")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ GET /api/governance/{TRUST_ID}/history returns 200")
    
    def test_history_has_required_fields(self, auth_session):
        """Test history response structure"""
        response = auth_session.get(f"{BASE_URL}/api/governance/{TRUST_ID}/history")
        assert response.status_code == 200
        
        data = response.json()
        
        assert "trust_id" in data, "Missing trust_id"
        assert "days" in data, "Missing days"
        assert "history" in data, "Missing history"
        assert "current_score" in data, "Missing current_score"
        
        print(f"✓ History response has required fields")
    
    def test_history_with_days_param(self, auth_session):
        """Test history with custom days parameter"""
        response = auth_session.get(f"{BASE_URL}/api/governance/{TRUST_ID}/history?days=7")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("days") == 7, f"Expected days=7, got {data.get('days')}"
        print(f"✓ History respects days parameter")
    
    def test_history_invalid_trust_404(self, auth_session):
        """Test that invalid trust returns 404"""
        response = auth_session.get(f"{BASE_URL}/api/governance/invalid_trust_xyz/history")
        assert response.status_code == 404
        print(f"✓ Invalid trust history returns 404")


class TestDashboard:
    """Tests for GET /api/dashboard - Unified dashboard endpoint"""
    
    def test_get_dashboard_returns_200(self, auth_session):
        """Test dashboard endpoint returns 200"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ GET /api/dashboard returns 200")
    
    def test_dashboard_has_required_fields(self, auth_session):
        """Test dashboard response has all required components"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard")
        assert response.status_code == 200
        
        data = response.json()
        
        # Required top-level fields
        assert "trust_id" in data, "Missing trust_id"
        assert "trust_name" in data, "Missing trust_name"
        assert "health_score" in data, "Missing health_score"
        assert "onboarding_state" in data, "Missing onboarding_state"
        assert "recent_activity" in data, "Missing recent_activity"
        assert "stats" in data, "Missing stats"
        assert "governance_insights" in data, "Missing governance_insights"
        
        print(f"✓ Dashboard has all required fields")
    
    def test_dashboard_health_score_structure(self, auth_session):
        """Test dashboard health_score has proper structure"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard")
        assert response.status_code == 200
        
        data = response.json()
        health_score = data.get("health_score", {})
        
        assert "total_score" in health_score, "health_score missing total_score"
        assert "max_score" in health_score, "health_score missing max_score"
        assert "color" in health_score, "health_score missing color"
        assert "criteria" in health_score, "health_score missing criteria"
        
        print(f"✓ Dashboard health_score structure is valid")
    
    def test_dashboard_stats_structure(self, auth_session):
        """Test dashboard stats has proper structure"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard")
        assert response.status_code == 200
        
        data = response.json()
        stats = data.get("stats", {})
        
        assert "total_decisions" in stats, "stats missing total_decisions"
        assert "pending_reviews" in stats, "stats missing pending_reviews"
        assert "total_distributions" in stats, "stats missing total_distributions"
        assert "ytd_distributions_amount" in stats, "stats missing ytd_distributions_amount"
        
        print(f"✓ Dashboard stats structure is valid")
    
    def test_dashboard_onboarding_state_structure(self, auth_session):
        """Test dashboard onboarding_state has proper structure"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard")
        assert response.status_code == 200
        
        data = response.json()
        onboarding = data.get("onboarding_state", {})
        
        assert "user_id" in onboarding, "onboarding_state missing user_id"
        assert "formation_date_added" in onboarding, "onboarding_state missing formation_date_added"
        assert "ein_entered" in onboarding, "onboarding_state missing ein_entered"
        assert "trust_doc_uploaded" in onboarding, "onboarding_state missing trust_doc_uploaded"
        assert "ein_doc_uploaded" in onboarding, "onboarding_state missing ein_doc_uploaded"
        assert "beneficiaries_added" in onboarding, "onboarding_state missing beneficiaries_added"
        assert "assets_added" in onboarding, "onboarding_state missing assets_added"
        assert "calendar_set" in onboarding, "onboarding_state missing calendar_set"
        assert "minutes_generated" in onboarding, "onboarding_state missing minutes_generated"
        assert "checklist_dismissed" in onboarding, "onboarding_state missing checklist_dismissed"
        
        print(f"✓ Dashboard onboarding_state structure is valid")
    
    def test_dashboard_subscription_state(self, auth_session):
        """Test dashboard includes subscription state for read-only mode awareness"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard")
        assert response.status_code == 200
        
        data = response.json()
        
        # Subscription field is optional but should be present
        if "subscription" in data:
            subscription = data.get("subscription", {})
            assert "plan_type" in subscription, "subscription missing plan_type"
            assert "status" in subscription, "subscription missing status"
            assert "is_trial" in subscription, "subscription missing is_trial"
            assert "is_active" in subscription, "subscription missing is_active"
            assert "is_read_only" in subscription, "subscription missing is_read_only"
            print(f"✓ Dashboard subscription state is valid: {subscription.get('status')}")
        else:
            print("✓ Dashboard subscription field not present (optional)")
    
    def test_dashboard_with_trust_id_param(self, auth_session):
        """Test dashboard with specific trust_id"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard?trust_id={TRUST_ID}")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("trust_id") == TRUST_ID, f"Expected trust_id {TRUST_ID}, got {data.get('trust_id')}"
        print(f"✓ Dashboard respects trust_id parameter")
    
    def test_dashboard_invalid_trust_404(self, auth_session):
        """Test dashboard with invalid trust_id returns 404"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard?trust_id=invalid_trust_xyz")
        assert response.status_code == 404
        print(f"✓ Invalid trust_id returns 404")


class TestOnboarding:
    """Tests for onboarding endpoints: GET, PATCH, POST dismiss"""
    
    def test_get_onboarding_returns_200(self, auth_session):
        """Test GET /api/onboarding returns 200"""
        response = auth_session.get(f"{BASE_URL}/api/onboarding")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ GET /api/onboarding returns 200")
    
    def test_onboarding_has_required_fields(self, auth_session):
        """Test onboarding response structure"""
        response = auth_session.get(f"{BASE_URL}/api/onboarding")
        assert response.status_code == 200
        
        data = response.json()
        
        assert "user_id" in data, "Missing user_id"
        assert "formation_date_added" in data, "Missing formation_date_added"
        assert "ein_entered" in data, "Missing ein_entered"
        assert "trust_doc_uploaded" in data, "Missing trust_doc_uploaded"
        assert "ein_doc_uploaded" in data, "Missing ein_doc_uploaded"
        assert "beneficiaries_added" in data, "Missing beneficiaries_added"
        assert "assets_added" in data, "Missing assets_added"
        assert "calendar_set" in data, "Missing calendar_set"
        assert "minutes_generated" in data, "Missing minutes_generated"
        assert "checklist_dismissed" in data, "Missing checklist_dismissed"
        
        # Check types
        assert isinstance(data.get("formation_date_added"), bool)
        assert isinstance(data.get("ein_entered"), bool)
        assert isinstance(data.get("trust_doc_uploaded"), bool)
        assert isinstance(data.get("ein_doc_uploaded"), bool)
        assert isinstance(data.get("beneficiaries_added"), bool)
        assert isinstance(data.get("assets_added"), bool)
        assert isinstance(data.get("calendar_set"), bool)
        assert isinstance(data.get("minutes_generated"), bool)
        assert isinstance(data.get("checklist_dismissed"), bool)
        
        print(f"✓ Onboarding response has all required fields with correct types")
    
    def test_patch_onboarding_returns_200(self, auth_session):
        """Test PATCH /api/onboarding updates state"""
        # Get current state
        get_response = auth_session.get(f"{BASE_URL}/api/onboarding")
        assert get_response.status_code == 200
        current_state = get_response.json()
        
        # Try to update (toggle a value)
        update_payload = {"formation_date_added": not current_state.get("formation_date_added", False)}
        response = auth_session.patch(f"{BASE_URL}/api/onboarding", json=update_payload)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify update
        data = response.json()
        assert "message" in data, "Response should have message"
        
        # Restore original state
        auth_session.patch(f"{BASE_URL}/api/onboarding", json={"formation_date_added": current_state.get("formation_date_added", False)})
        
        print(f"✓ PATCH /api/onboarding works correctly")
    
    def test_post_onboarding_dismiss(self, auth_session):
        """Test POST /api/onboarding/dismiss"""
        response = auth_session.post(f"{BASE_URL}/api/onboarding/dismiss")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "message" in data, "Response should have message"
        
        print(f"✓ POST /api/onboarding/dismiss returns 200")
    
    def test_onboarding_dismiss_sets_checklist_dismissed(self, auth_session):
        """Verify dismiss actually sets checklist_dismissed to true"""
        # Call dismiss
        auth_session.post(f"{BASE_URL}/api/onboarding/dismiss")
        
        # Check state
        response = auth_session.get(f"{BASE_URL}/api/onboarding")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("checklist_dismissed") == True, "checklist_dismissed should be True after dismiss"
        
        print(f"✓ Dismiss sets checklist_dismissed to True")


class TestActivity:
    """Tests for GET /api/activity - Recent activity timeline"""
    
    def test_get_activity_returns_200(self, auth_session):
        """Test activity endpoint returns 200"""
        response = auth_session.get(f"{BASE_URL}/api/activity")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ GET /api/activity returns 200")
    
    def test_activity_has_activities_array(self, auth_session):
        """Test activity response has activities array"""
        response = auth_session.get(f"{BASE_URL}/api/activity")
        assert response.status_code == 200
        
        data = response.json()
        assert "activities" in data, "Missing activities array"
        assert isinstance(data.get("activities"), list), "activities should be a list"
        
        print(f"✓ Activity response has activities array")
    
    def test_activity_with_trust_id(self, auth_session):
        """Test activity with specific trust_id"""
        response = auth_session.get(f"{BASE_URL}/api/activity?trust_id={TRUST_ID}")
        assert response.status_code == 200
        
        data = response.json()
        assert "activities" in data
        
        print(f"✓ Activity with trust_id works")
    
    def test_activity_with_limit(self, auth_session):
        """Test activity with limit parameter"""
        response = auth_session.get(f"{BASE_URL}/api/activity?limit=5")
        assert response.status_code == 200
        
        data = response.json()
        activities = data.get("activities", [])
        assert len(activities) <= 5, f"Expected max 5 activities, got {len(activities)}"
        
        print(f"✓ Activity respects limit parameter")
    
    def test_activity_items_structure(self, auth_session):
        """Test individual activity items have expected structure"""
        response = auth_session.get(f"{BASE_URL}/api/activity?trust_id={TRUST_ID}")
        assert response.status_code == 200
        
        data = response.json()
        activities = data.get("activities", [])
        
        # Check structure if activities exist
        for activity in activities[:3]:  # Check first 3
            assert "type" in activity, f"Activity missing type: {activity}"
            assert "title" in activity, f"Activity missing title: {activity}"
            assert "created_at" in activity, f"Activity missing created_at: {activity}"
        
        print(f"✓ Activity items have correct structure (checked {min(3, len(activities))} items)")


class TestUnauthorizedAccess:
    """Test that endpoints require authentication"""
    
    def test_governance_requires_auth(self):
        """Test governance endpoint requires auth"""
        response = requests.get(f"{BASE_URL}/api/governance/{TRUST_ID}")
        assert response.status_code == 401, f"Expected 401 for unauthenticated request, got {response.status_code}"
        print(f"✓ GET /api/governance/{TRUST_ID} requires auth")
    
    def test_dashboard_requires_auth(self):
        """Test dashboard endpoint requires auth"""
        response = requests.get(f"{BASE_URL}/api/dashboard")
        assert response.status_code == 401
        print(f"✓ GET /api/dashboard requires auth")
    
    def test_onboarding_requires_auth(self):
        """Test onboarding endpoint requires auth"""
        response = requests.get(f"{BASE_URL}/api/onboarding")
        assert response.status_code == 401
        print(f"✓ GET /api/onboarding requires auth")
    
    def test_activity_requires_auth(self):
        """Test activity endpoint requires auth"""
        response = requests.get(f"{BASE_URL}/api/activity")
        assert response.status_code == 401
        print(f"✓ GET /api/activity requires auth")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
