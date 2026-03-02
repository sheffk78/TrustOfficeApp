"""
Test file for P2 Feature Gating - Premium Feature Restrictions

Tests the following feature gates:
1. MULTIPLE_TRUSTS - Trial users blocked from creating 2nd+ trust (402)
2. GOVERNANCE_HISTORY - Trial users blocked from /api/governance/{trust_id}/history (402)
3. TRUST_UNITS - Trial users blocked from /api/trust-units/* endpoints (402)
4. BENEFICIARY_DASHBOARD - Trial users blocked from /api/beneficiaries/dashboard (402)

Regression tests:
- Trial users can still access core features (trusts list, single trust, entities, tasks, minutes, distributions)
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Demo user credentials (on trial plan)
DEMO_EMAIL = "demo@trustoffice.com"
DEMO_PASSWORD = "demopassword"
TRUST_ID = "trust_b753cb8fe07f"


class TestMultipleTrustsGate:
    """Test MULTIPLE_TRUSTS feature gate - Trial users limited to 1 trust"""
    
    @pytest.fixture(scope='class')
    def auth_token(self):
        """Login and get auth token for demo user (trial plan)"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEMO_EMAIL,
            "password": DEMO_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")
    
    def test_trial_user_can_view_trusts_list(self, auth_token):
        """Trial users CAN view their trusts list (core feature)"""
        response = requests.get(
            f"{BASE_URL}/api/trusts",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list of trusts"
        print(f"PASS: Trial user can view trusts list ({len(data)} trusts)")
    
    def test_trial_user_can_view_single_trust(self, auth_token):
        """Trial users CAN view their single trust (core feature)"""
        response = requests.get(
            f"{BASE_URL}/api/trusts/{TRUST_ID}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("trust_id") == TRUST_ID, "Response should have correct trust_id"
        print(f"PASS: Trial user can view single trust: {data.get('name')}")
    
    def test_trial_user_blocked_from_creating_second_trust(self, auth_token):
        """Trial users should get 402 when trying to create 2nd trust"""
        # Demo user already has 1 trust, so creating another should be blocked
        response = requests.post(
            f"{BASE_URL}/api/trusts",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "name": "TEST_Second Trust - Should Fail",
                "trust_type": "family",
                "jurisdiction": "Test Jurisdiction"
            }
        )
        assert response.status_code == 402, f"Expected 402 Payment Required, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data, "Error response should have detail"
        assert "paid subscription" in data["detail"].lower() or "trial" in data["detail"].lower(), \
            f"Error should mention subscription requirement: {data['detail']}"
        
        print(f"PASS: Trial user blocked from creating 2nd trust (402)")
        print(f"  - Error message: {data['detail']}")


class TestGovernanceHistoryGate:
    """Test GOVERNANCE_HISTORY feature gate - Trial users blocked from history"""
    
    @pytest.fixture(scope='class')
    def auth_token(self):
        """Login and get auth token for demo user (trial plan)"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEMO_EMAIL,
            "password": DEMO_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")
    
    def test_trial_user_can_access_governance_health(self, auth_token):
        """Trial users CAN access governance health score (core feature)"""
        response = requests.get(
            f"{BASE_URL}/api/governance/{TRUST_ID}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "total_score" in data, "Response should have total_score"
        assert "criteria" in data, "Response should have criteria"
        print(f"PASS: Trial user can access governance health score: {data.get('total_score')}")
    
    def test_trial_user_blocked_from_governance_history(self, auth_token):
        """Trial users should get 402 when accessing governance history"""
        response = requests.get(
            f"{BASE_URL}/api/governance/{TRUST_ID}/history",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 402, f"Expected 402 Payment Required, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data, "Error response should have detail"
        assert "paid subscription" in data["detail"].lower() or "upgrade" in data["detail"].lower(), \
            f"Error should mention subscription requirement: {data['detail']}"
        
        print(f"PASS: Trial user blocked from governance history (402)")
        print(f"  - Error message: {data['detail']}")
    
    def test_governance_history_with_days_param(self, auth_token):
        """Trial users blocked from governance history even with days parameter"""
        response = requests.get(
            f"{BASE_URL}/api/governance/{TRUST_ID}/history?days=7",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 402, f"Expected 402 with days param, got {response.status_code}: {response.text}"
        print("PASS: Trial user blocked from governance history with days param (402)")


class TestTrustUnitsGate:
    """Test TRUST_UNITS feature gate - Trial users blocked from trust unit endpoints"""
    
    @pytest.fixture(scope='class')
    def auth_token(self):
        """Login and get auth token for demo user (trial plan)"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEMO_EMAIL,
            "password": DEMO_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")
    
    def test_trial_user_blocked_from_trust_units_summary(self, auth_token):
        """Trial users should get 402 when accessing trust units summary"""
        response = requests.get(
            f"{BASE_URL}/api/trust-units/summary?trust_id={TRUST_ID}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 402, f"Expected 402 Payment Required, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data, "Error response should have detail"
        print(f"PASS: Trial user blocked from trust units summary (402)")
        print(f"  - Error message: {data['detail']}")
    
    def test_trial_user_blocked_from_trust_units_certificates(self, auth_token):
        """Trial users should get 402 when listing trust unit certificates"""
        response = requests.get(
            f"{BASE_URL}/api/trust-units/certificates?trust_id={TRUST_ID}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 402, f"Expected 402 Payment Required, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data, "Error response should have detail"
        print(f"PASS: Trial user blocked from trust unit certificates (402)")
    
    def test_trust_units_summary_requires_auth(self):
        """Trust units summary should still require authentication first"""
        response = requests.get(f"{BASE_URL}/api/trust-units/summary?trust_id={TRUST_ID}")
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("PASS: Trust units summary requires authentication (401)")


class TestBeneficiaryDashboardGate:
    """Test BENEFICIARY_DASHBOARD feature gate - Trial users blocked from dashboard"""
    
    @pytest.fixture(scope='class')
    def auth_token(self):
        """Login and get auth token for demo user (trial plan)"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEMO_EMAIL,
            "password": DEMO_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")
    
    def test_trial_user_blocked_from_beneficiary_dashboard(self, auth_token):
        """Trial users should get 402 when accessing beneficiary dashboard"""
        response = requests.get(
            f"{BASE_URL}/api/beneficiaries/dashboard",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 402, f"Expected 402 Payment Required, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data, "Error response should have detail"
        print(f"PASS: Trial user blocked from beneficiary dashboard (402)")
        print(f"  - Error message: {data['detail']}")
    
    def test_trial_user_blocked_from_beneficiary_dashboard_with_trust_id(self, auth_token):
        """Trial users blocked from beneficiary dashboard even with trust_id param"""
        response = requests.get(
            f"{BASE_URL}/api/beneficiaries/dashboard?trust_id={TRUST_ID}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 402, f"Expected 402 with trust_id param, got {response.status_code}: {response.text}"
        print("PASS: Trial user blocked from beneficiary dashboard with trust_id param (402)")
    
    def test_beneficiary_dashboard_requires_auth(self):
        """Beneficiary dashboard should still require authentication first"""
        response = requests.get(f"{BASE_URL}/api/beneficiaries/dashboard")
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("PASS: Beneficiary dashboard requires authentication (401)")


class TestTrialUserCoreFeatures:
    """Regression tests - Trial users can still access core features"""
    
    @pytest.fixture(scope='class')
    def auth_token(self):
        """Login and get auth token for demo user (trial plan)"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEMO_EMAIL,
            "password": DEMO_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")
    
    def test_trial_user_can_access_entities(self, auth_token):
        """Trial users can access entities list (core feature)"""
        response = requests.get(
            f"{BASE_URL}/api/entities?trust_id={TRUST_ID}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Trial user can access entities list")
    
    def test_trial_user_can_access_tasks(self, auth_token):
        """Trial users can access tasks list (core feature)"""
        response = requests.get(
            f"{BASE_URL}/api/tasks?trust_id={TRUST_ID}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Trial user can access tasks list")
    
    def test_trial_user_can_access_minutes(self, auth_token):
        """Trial users can access minutes list (core feature)"""
        response = requests.get(
            f"{BASE_URL}/api/minutes?trust_id={TRUST_ID}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Trial user can access minutes list")
    
    def test_trial_user_can_access_distributions(self, auth_token):
        """Trial users can access distributions list (core feature)"""
        response = requests.get(
            f"{BASE_URL}/api/distributions?trust_id={TRUST_ID}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Trial user can access distributions list")
    
    def test_trial_user_can_access_dashboard(self, auth_token):
        """Trial users can access main dashboard (core feature)"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "trust_id" in data, "Dashboard should have trust_id"
        assert "health_score" in data, "Dashboard should have health_score"
        print(f"PASS: Trial user can access dashboard (trust: {data.get('trust_name')})")
    
    def test_trial_user_can_access_onboarding(self, auth_token):
        """Trial users can access onboarding state (core feature)"""
        response = requests.get(
            f"{BASE_URL}/api/onboarding",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Trial user can access onboarding state")


class TestFeatureFlagsEndpoint:
    """Test /api/subscription/features returns correct premium feature flags"""
    
    @pytest.fixture(scope='class')
    def auth_token(self):
        """Login and get auth token for demo user (trial plan)"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEMO_EMAIL,
            "password": DEMO_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")
    
    def test_new_premium_features_are_false_for_trial(self, auth_token):
        """Test that new P2 premium features are False for trial users"""
        response = requests.get(
            f"{BASE_URL}/api/subscription/features",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        features = data.get("features", {})
        
        # New P2 premium features should all be False
        p2_features = ["multiple_trusts", "governance_history", "trust_units", "beneficiary_dashboard"]
        for feature in p2_features:
            assert features.get(feature) == False, f"Feature {feature} should be False for trial users, got {features.get(feature)}"
        
        print("PASS: All P2 premium features are False for trial user:")
        print(f"  - multiple_trusts: {features.get('multiple_trusts')}")
        print(f"  - governance_history: {features.get('governance_history')}")
        print(f"  - trust_units: {features.get('trust_units')}")
        print(f"  - beneficiary_dashboard: {features.get('beneficiary_dashboard')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
