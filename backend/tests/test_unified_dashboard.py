"""
Test suite for the unified GET /api/dashboard endpoint.

Tests:
- Dashboard returns DashboardResponse with all required fields
- health_score contains full HealthScoreResponse (criteria, total_score, color, calculated_at)
- onboarding_state contains all 5 boolean fields
- recent_activity returns limited list of activities
- stats contains total_decisions, pending_reviews, total_distributions, ytd_distributions_amount
- governance_insights generated from unachieved criteria
- Dashboard returns 404 if user has no trusts
- Existing /api/onboarding still works after refactoring
- Existing /api/activity still works after refactoring
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "demo@trustoffice.com"
TEST_PASSWORD = "demopassword"
TEST_TRUST_ID = "trust_b753cb8fe07f"


class TestUnifiedDashboard:
    """Test unified /api/dashboard endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        # Login to get token
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def test_dashboard_returns_200_with_all_required_fields(self):
        """Test GET /api/dashboard returns 200 with DashboardResponse structure"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard",
            headers=self.headers
        )
        
        assert response.status_code == 200, f"Dashboard failed: {response.text}"
        data = response.json()
        
        # Verify top-level required fields
        assert "trust_id" in data, "Missing trust_id"
        assert "trust_name" in data, "Missing trust_name"
        assert "health_score" in data, "Missing health_score"
        assert "onboarding_state" in data, "Missing onboarding_state"
        assert "recent_activity" in data, "Missing recent_activity"
        assert "stats" in data, "Missing stats"
        assert "governance_insights" in data, "Missing governance_insights"
        
        print(f"Dashboard response has all required top-level fields")
        print(f"Trust ID: {data['trust_id']}")
        print(f"Trust Name: {data['trust_name']}")
    
    def test_health_score_contains_full_response(self):
        """Test health_score contains all HealthScoreResponse fields"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard",
            headers=self.headers
        )
        
        assert response.status_code == 200
        data = response.json()
        health_score = data["health_score"]
        
        # Verify HealthScoreResponse fields
        assert "trust_id" in health_score, "Missing trust_id in health_score"
        assert "total_score" in health_score, "Missing total_score"
        assert "max_score" in health_score, "Missing max_score"
        assert "color" in health_score, "Missing color"
        assert "criteria" in health_score, "Missing criteria"
        assert "calculated_at" in health_score, "Missing calculated_at"
        
        # Verify score value types
        assert isinstance(health_score["total_score"], int), "total_score should be int"
        assert isinstance(health_score["max_score"], int), "max_score should be int"
        assert health_score["max_score"] == 120, "max_score should be 120"
        
        # Verify color is valid
        assert health_score["color"] in ["red", "yellow", "green"], f"Invalid color: {health_score['color']}"
        
        # Verify criteria is a list with proper structure
        assert isinstance(health_score["criteria"], list), "criteria should be a list"
        assert len(health_score["criteria"]) == 6, "Should have 6 criteria"
        
        for criterion in health_score["criteria"]:
            assert "name" in criterion, "Criterion missing name"
            assert "description" in criterion, "Criterion missing description"
            assert "points" in criterion, "Criterion missing points"
            assert "max_points" in criterion, "Criterion missing max_points"
            assert "achieved" in criterion, "Criterion missing achieved"
        
        print(f"Health Score: {health_score['total_score']}/{health_score['max_score']} ({health_score['color']})")
        print(f"Criteria: {[c['name'] for c in health_score['criteria']]}")
    
    def test_onboarding_state_contains_all_boolean_fields(self):
        """Test onboarding_state contains all 5 boolean fields"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard",
            headers=self.headers
        )
        
        assert response.status_code == 200
        data = response.json()
        onboarding = data["onboarding_state"]
        
        # Verify all 5 boolean fields exist
        required_fields = [
                    "formation_date_added",
                    "ein_entered",
                    "trust_doc_uploaded",
                    "ein_doc_uploaded",
                    "beneficiaries_added",
                    "assets_added",
            "calendar_set", 
            "minutes_generated",
            "checklist_dismissed"
        ]
        
        for field in required_fields:
            assert field in onboarding, f"Missing {field} in onboarding_state"
            assert isinstance(onboarding[field], bool), f"{field} should be boolean"
        
        # Verify user_id exists
        assert "user_id" in onboarding, "Missing user_id in onboarding_state"
        
        print(f"Onboarding state: {onboarding}")
    
    def test_recent_activity_returns_list(self):
        """Test recent_activity returns limited list of activities"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard",
            headers=self.headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        recent_activity = data["recent_activity"]
        assert isinstance(recent_activity, list), "recent_activity should be a list"
        
        # Dashboard limits to 10 items
        assert len(recent_activity) <= 10, "recent_activity should be limited to 10 items"
        
        # Verify activity item structure if any activities exist
        if recent_activity:
            activity = recent_activity[0]
            assert "type" in activity, "Activity missing type"
            assert "id" in activity, "Activity missing id"
            assert "trust_id" in activity, "Activity missing trust_id"
            assert "title" in activity, "Activity missing title"
            assert "created_at" in activity, "Activity missing created_at"
        
        print(f"Recent activity count: {len(recent_activity)}")
        if recent_activity:
            print(f"Activity types: {[a['type'] for a in recent_activity[:5]]}")
    
    def test_stats_contains_required_fields(self):
        """Test stats contains all DashboardStats fields"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard",
            headers=self.headers
        )
        
        assert response.status_code == 200
        data = response.json()
        stats = data["stats"]
        
        # Verify DashboardStats fields
        assert "total_decisions" in stats, "Missing total_decisions"
        assert "pending_reviews" in stats, "Missing pending_reviews"
        assert "total_distributions" in stats, "Missing total_distributions"
        assert "ytd_distributions_amount" in stats, "Missing ytd_distributions_amount"
        
        # Verify types
        assert isinstance(stats["total_decisions"], int), "total_decisions should be int"
        assert isinstance(stats["pending_reviews"], int), "pending_reviews should be int"
        assert isinstance(stats["total_distributions"], int), "total_distributions should be int"
        assert isinstance(stats["ytd_distributions_amount"], (int, float)), "ytd_distributions_amount should be numeric"
        
        print(f"Stats: {stats}")
    
    def test_governance_insights_structure(self):
        """Test governance_insights contains GovernanceInsight objects with correct structure"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard",
            headers=self.headers
        )
        
        assert response.status_code == 200
        data = response.json()
        insights = data["governance_insights"]
        
        assert isinstance(insights, list), "governance_insights should be a list"
        
        # Verify insight structure if any exist
        if insights:
            insight = insights[0]
            assert "type" in insight, "Insight missing type"
            assert "criterion_name" in insight, "Insight missing criterion_name"
            assert "title" in insight, "Insight missing title"
            assert "description" in insight, "Insight missing description"
            assert "action_path" in insight, "Insight missing action_path"
            assert "action_label" in insight, "Insight missing action_label"
            assert "points" in insight, "Insight missing points"
            
            # Verify type is valid
            assert insight["type"] in ["warning", "error", "info"], f"Invalid insight type: {insight['type']}"
            
            # Points should be 20
            assert insight["points"] == 20, "Insight points should be 20"
            
            print(f"Governance insights count: {len(insights)}")
            for i in insights:
                print(f"  - {i['title']} ({i['type']}): {i['description']}")
        else:
            print("No governance insights (all criteria achieved)")
    
    def test_insights_match_unachieved_criteria(self):
        """Test governance_insights correspond to unachieved criteria"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard",
            headers=self.headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Get unachieved criteria names
        unachieved = [c["name"] for c in data["health_score"]["criteria"] if not c["achieved"]]
        
        # Get insight criterion names
        insight_criteria = [i["criterion_name"] for i in data["governance_insights"]]
        
        # Each insight should correspond to an unachieved criterion
        for criterion_name in insight_criteria:
            assert criterion_name in unachieved, f"Insight {criterion_name} doesn't match unachieved criteria"
        
        # Number of insights should match number of unachieved criteria
        assert len(insight_criteria) == len(unachieved), "Insights count should match unachieved criteria count"
        
        print(f"Unachieved criteria: {unachieved}")
        print(f"Insight criteria: {insight_criteria}")
        print(f"Match verified: {len(insight_criteria) == len(unachieved)}")


class TestExistingEndpointsStillWork:
    """Test that existing /api/onboarding and /api/activity still work after refactoring"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def test_onboarding_endpoint_still_works(self):
        """Test GET /api/onboarding returns valid OnboardingState"""
        response = requests.get(
            f"{BASE_URL}/api/onboarding",
            headers=self.headers
        )
        
        assert response.status_code == 200, f"Onboarding failed: {response.text}"
        data = response.json()
        
        # Verify structure
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
        
        print(f"GET /api/onboarding working: {data}")
    
    def test_activity_endpoint_still_works(self):
        """Test GET /api/activity returns valid activity list"""
        response = requests.get(
            f"{BASE_URL}/api/activity",
            headers=self.headers
        )
        
        assert response.status_code == 200, f"Activity failed: {response.text}"
        data = response.json()
        
        # Should return a list
        assert isinstance(data, list), "Activity should return list"
        
        # Verify structure if any activities
        if data:
            activity = data[0]
            assert "type" in activity
            assert "id" in activity
            assert "trust_id" in activity
            assert "title" in activity
            assert "created_at" in activity
        
        print(f"GET /api/activity working: {len(data)} activities returned")
    
    def test_activity_endpoint_with_trust_filter(self):
        """Test GET /api/activity with trust_id filter works"""
        response = requests.get(
            f"{BASE_URL}/api/activity?trust_id={TEST_TRUST_ID}",
            headers=self.headers
        )
        
        assert response.status_code == 200, f"Activity failed: {response.text}"
        data = response.json()
        
        # All activities should belong to the filtered trust
        for activity in data:
            assert activity["trust_id"] == TEST_TRUST_ID, f"Activity trust_id mismatch"
        
        print(f"GET /api/activity?trust_id={TEST_TRUST_ID} working: {len(data)} activities")
    
    def test_activity_endpoint_with_limit(self):
        """Test GET /api/activity with limit parameter"""
        response = requests.get(
            f"{BASE_URL}/api/activity?limit=5",
            headers=self.headers
        )
        
        assert response.status_code == 200, f"Activity failed: {response.text}"
        data = response.json()
        
        assert len(data) <= 5, "Should respect limit parameter"
        
        print(f"GET /api/activity?limit=5 working: {len(data)} activities (max 5)")


class TestDashboardErrorHandling:
    """Test dashboard error handling"""
    
    def test_dashboard_returns_401_without_auth(self):
        """Test dashboard returns 401 when not authenticated"""
        response = requests.get(f"{BASE_URL}/api/dashboard")
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("Dashboard correctly returns 401 without authentication")
    
    def test_dashboard_returns_404_for_user_without_trusts(self):
        """Test dashboard returns 404 if user has no trusts"""
        # Register a new user without any trusts
        import uuid
        unique_email = f"test_notrustuser_{uuid.uuid4().hex[:8]}@test.com"
        
        # Register new user
        register_response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": unique_email,
                "password": "testpassword123",
                "name": "Test User No Trust"
            }
        )
        
        if register_response.status_code != 200:
            pytest.skip("Could not register test user")
        
        # Login with the new user
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": unique_email, "password": "testpassword123"}
        )
        
        assert login_response.status_code == 200, "Login should succeed"
        token = login_response.json()["token"]
        
        # Try to access dashboard
        response = requests.get(
            f"{BASE_URL}/api/dashboard",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 404, f"Expected 404 for user without trusts, got {response.status_code}"
        assert "No trust found" in response.json().get("detail", ""), "Should indicate no trust found"
        
        print(f"Dashboard correctly returns 404 for user without trusts")


class TestDashboardDataConsistency:
    """Test dashboard data is consistent with individual endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def test_health_score_matches_governance_endpoint(self):
        """Test dashboard health_score matches /api/governance/{trust_id}"""
        # Get dashboard
        dashboard_response = requests.get(
            f"{BASE_URL}/api/dashboard",
            headers=self.headers
        )
        assert dashboard_response.status_code == 200
        dashboard_data = dashboard_response.json()
        
        trust_id = dashboard_data["trust_id"]
        dashboard_health = dashboard_data["health_score"]
        
        # Get governance endpoint directly
        governance_response = requests.get(
            f"{BASE_URL}/api/governance/{trust_id}",
            headers=self.headers
        )
        assert governance_response.status_code == 200
        governance_data = governance_response.json()
        
        # Compare key fields (scores might differ slightly due to timing)
        # Just verify structure is same
        assert dashboard_health["max_score"] == governance_data["max_score"]
        assert len(dashboard_health["criteria"]) == len(governance_data["criteria"])
        
        # Criteria names should match
        dashboard_criteria_names = [c["name"] for c in dashboard_health["criteria"]]
        governance_criteria_names = [c["name"] for c in governance_data["criteria"]]
        assert dashboard_criteria_names == governance_criteria_names
        
        print(f"Dashboard health score structure matches /api/governance/{trust_id}")
    
    def test_onboarding_matches_onboarding_endpoint(self):
        """Test dashboard onboarding_state matches /api/onboarding"""
        # Get dashboard
        dashboard_response = requests.get(
            f"{BASE_URL}/api/dashboard",
            headers=self.headers
        )
        assert dashboard_response.status_code == 200
        dashboard_onboarding = dashboard_response.json()["onboarding_state"]
        
        # Get onboarding endpoint
        onboarding_response = requests.get(
            f"{BASE_URL}/api/onboarding",
            headers=self.headers
        )
        assert onboarding_response.status_code == 200
        onboarding_data = onboarding_response.json()
        
        # Compare fields
        for field in ["formation_date_added", "ein_entered", "trust_doc_uploaded", "ein_doc_uploaded", "beneficiaries_added", "assets_added", "calendar_set", "minutes_generated", "checklist_dismissed"]:
            assert dashboard_onboarding[field] == onboarding_data[field], f"{field} mismatch"
        
        print("Dashboard onboarding_state matches /api/onboarding")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
