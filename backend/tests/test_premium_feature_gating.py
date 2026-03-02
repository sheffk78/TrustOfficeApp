"""
Test file for Premium Feature Gating (P2 implementation).

Tests that trial users are properly blocked from premium features:
- GET /api/subscription/features returns correct feature flags by plan type
- Trial users: csv_export, benevolence_mode, trust_units = false
- Export endpoints return 402 for trial users with proper headers
- Paid users (monthly/annual) have full access to premium features

Feature Flags:
- Core (trial + paid): minutes_basic, distributions_basic, governance_basic, single_trust
- Premium (paid only): pdf_no_watermark, csv_export, multiple_trusts, benevolence_mode,
                        beneficiary_dashboard, trust_units, governance_history, advanced_templates
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Demo user credentials (on trial plan)
DEMO_EMAIL = "demo@trustoffice.com"
DEMO_PASSWORD = "demopassword"
TRUST_ID = "trust_b753cb8fe07f"


class TestSubscriptionFeatures:
    """Test GET /api/subscription/features endpoint"""
    
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
    
    def test_subscription_features_requires_auth(self):
        """Test that subscription features endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/subscription/features")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: GET /api/subscription/features requires authentication (401)")
    
    def test_subscription_features_returns_correct_structure(self, auth_token):
        """Test that subscription features returns correct response structure"""
        response = requests.get(
            f"{BASE_URL}/api/subscription/features",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        
        # Validate required fields
        assert "plan_type" in data, "Response should have plan_type"
        assert "is_active" in data, "Response should have is_active"
        assert "is_trial" in data, "Response should have is_trial"
        assert "features" in data, "Response should have features dict"
        
        print(f"PASS: GET /api/subscription/features returns correct structure")
        print(f"  - plan_type: {data['plan_type']}")
        print(f"  - is_active: {data['is_active']}")
        print(f"  - is_trial: {data['is_trial']}")
    
    def test_trial_user_has_correct_feature_flags(self, auth_token):
        """Test that trial users have correct feature flags (core=true, premium=false)"""
        response = requests.get(
            f"{BASE_URL}/api/subscription/features",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        features = data.get("features", {})
        
        # Core features should be TRUE for trial users
        core_features = ["minutes_basic", "distributions_basic", "governance_basic", "single_trust"]
        for feature in core_features:
            assert features.get(feature) == True, f"Core feature {feature} should be True for trial users"
        
        # Premium features should be FALSE for trial users
        premium_features = ["csv_export", "benevolence_mode", "trust_units", 
                          "pdf_no_watermark", "multiple_trusts", "beneficiary_dashboard",
                          "governance_history", "advanced_templates"]
        for feature in premium_features:
            assert features.get(feature) == False, f"Premium feature {feature} should be False for trial users, got {features.get(feature)}"
        
        print("PASS: Trial user has correct feature flags:")
        print(f"  - Core features (True): {core_features}")
        print(f"  - Premium features (False): {premium_features}")
    
    def test_trial_user_csv_export_is_false(self, auth_token):
        """Verify csv_export is specifically false for trial users"""
        response = requests.get(
            f"{BASE_URL}/api/subscription/features",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        data = response.json()
        features = data.get("features", {})
        
        assert features.get("csv_export") == False, f"csv_export should be False for trial users, got {features.get('csv_export')}"
        print("PASS: csv_export = False for trial user")
    
    def test_trial_user_benevolence_mode_is_false(self, auth_token):
        """Verify benevolence_mode is specifically false for trial users"""
        response = requests.get(
            f"{BASE_URL}/api/subscription/features",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        data = response.json()
        features = data.get("features", {})
        
        assert features.get("benevolence_mode") == False, f"benevolence_mode should be False for trial users, got {features.get('benevolence_mode')}"
        print("PASS: benevolence_mode = False for trial user")
    
    def test_trial_user_trust_units_is_false(self, auth_token):
        """Verify trust_units is specifically false for trial users"""
        response = requests.get(
            f"{BASE_URL}/api/subscription/features",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        data = response.json()
        features = data.get("features", {})
        
        assert features.get("trust_units") == False, f"trust_units should be False for trial users, got {features.get('trust_units')}"
        print("PASS: trust_units = False for trial user")


class TestExportFeatureGating:
    """Test that export endpoints return 402 for trial users"""
    
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
    
    def test_export_minutes_returns_402_for_trial(self, auth_token):
        """Test GET /api/export/minutes returns 402 for trial users"""
        response = requests.get(
            f"{BASE_URL}/api/export/minutes",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 402, f"Expected 402 for trial user, got {response.status_code}"
        
        # Check error message
        data = response.json()
        assert "detail" in data, "Error response should have detail"
        assert "paid subscription" in data["detail"].lower() or "premium" in data["detail"].lower(), \
            f"Error message should mention premium/paid subscription: {data['detail']}"
        
        # Check custom headers
        assert "X-Required-Feature" in response.headers, "Response should have X-Required-Feature header"
        assert "X-Current-Plan" in response.headers, "Response should have X-Current-Plan header"
        assert response.headers.get("X-Required-Feature") == "csv_export", \
            f"X-Required-Feature should be 'csv_export', got {response.headers.get('X-Required-Feature')}"
        assert response.headers.get("X-Current-Plan") == "trial", \
            f"X-Current-Plan should be 'trial', got {response.headers.get('X-Current-Plan')}"
        
        print("PASS: GET /api/export/minutes returns 402 for trial users")
        print(f"  - X-Required-Feature: {response.headers.get('X-Required-Feature')}")
        print(f"  - X-Current-Plan: {response.headers.get('X-Current-Plan')}")
    
    def test_export_distributions_returns_402_for_trial(self, auth_token):
        """Test GET /api/export/distributions returns 402 for trial users"""
        response = requests.get(
            f"{BASE_URL}/api/export/distributions",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 402, f"Expected 402 for trial user, got {response.status_code}"
        
        # Check custom headers
        assert "X-Required-Feature" in response.headers, "Response should have X-Required-Feature header"
        assert response.headers.get("X-Required-Feature") == "csv_export", \
            f"X-Required-Feature should be 'csv_export', got {response.headers.get('X-Required-Feature')}"
        assert response.headers.get("X-Current-Plan") == "trial", \
            f"X-Current-Plan should be 'trial', got {response.headers.get('X-Current-Plan')}"
        
        print("PASS: GET /api/export/distributions returns 402 for trial users")
        print(f"  - X-Required-Feature: {response.headers.get('X-Required-Feature')}")
        print(f"  - X-Current-Plan: {response.headers.get('X-Current-Plan')}")
    
    def test_export_compensation_returns_402_for_trial(self, auth_token):
        """Test GET /api/export/compensation returns 402 for trial users"""
        response = requests.get(
            f"{BASE_URL}/api/export/compensation",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 402, f"Expected 402 for trial user, got {response.status_code}"
        
        # Check custom headers
        assert "X-Required-Feature" in response.headers, "Response should have X-Required-Feature header"
        assert response.headers.get("X-Required-Feature") == "csv_export", \
            f"X-Required-Feature should be 'csv_export', got {response.headers.get('X-Required-Feature')}"
        assert response.headers.get("X-Current-Plan") == "trial", \
            f"X-Current-Plan should be 'trial', got {response.headers.get('X-Current-Plan')}"
        
        print("PASS: GET /api/export/compensation returns 402 for trial users")
        print(f"  - X-Required-Feature: {response.headers.get('X-Required-Feature')}")
        print(f"  - X-Current-Plan: {response.headers.get('X-Current-Plan')}")
    
    def test_export_tasks_returns_402_for_trial(self, auth_token):
        """Test GET /api/export/tasks returns 402 for trial users"""
        response = requests.get(
            f"{BASE_URL}/api/export/tasks",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 402, f"Expected 402 for trial user, got {response.status_code}"
        
        # Check custom headers
        assert "X-Required-Feature" in response.headers, "Response should have X-Required-Feature header"
        assert response.headers.get("X-Required-Feature") == "csv_export", \
            f"X-Required-Feature should be 'csv_export', got {response.headers.get('X-Required-Feature')}"
        assert response.headers.get("X-Current-Plan") == "trial", \
            f"X-Current-Plan should be 'trial', got {response.headers.get('X-Current-Plan')}"
        
        print("PASS: GET /api/export/tasks returns 402 for trial users")
        print(f"  - X-Required-Feature: {response.headers.get('X-Required-Feature')}")
        print(f"  - X-Current-Plan: {response.headers.get('X-Current-Plan')}")


class TestExportAuthentication:
    """Test that export endpoints still require authentication"""
    
    def test_export_minutes_requires_auth(self):
        """Test GET /api/export/minutes requires authentication"""
        response = requests.get(f"{BASE_URL}/api/export/minutes")
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("PASS: GET /api/export/minutes requires authentication (401)")
    
    def test_export_distributions_requires_auth(self):
        """Test GET /api/export/distributions requires authentication"""
        response = requests.get(f"{BASE_URL}/api/export/distributions")
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("PASS: GET /api/export/distributions requires authentication (401)")
    
    def test_export_compensation_requires_auth(self):
        """Test GET /api/export/compensation requires authentication"""
        response = requests.get(f"{BASE_URL}/api/export/compensation")
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("PASS: GET /api/export/compensation requires authentication (401)")
    
    def test_export_tasks_requires_auth(self):
        """Test GET /api/export/tasks requires authentication"""
        response = requests.get(f"{BASE_URL}/api/export/tasks")
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print("PASS: GET /api/export/tasks requires authentication (401)")


class TestPlanFeaturesConfiguration:
    """Test that PLAN_FEATURES dict is correctly configured"""
    
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
    
    def test_trial_plan_has_only_core_features(self, auth_token):
        """Test that trial plan has only core features enabled"""
        response = requests.get(
            f"{BASE_URL}/api/subscription/features",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        data = response.json()
        features = data.get("features", {})
        
        # Count enabled features
        enabled_count = sum(1 for v in features.values() if v == True)
        core_count = 4  # minutes_basic, distributions_basic, governance_basic, single_trust
        
        # Trial should have exactly 4 core features enabled
        assert enabled_count == core_count, f"Trial plan should have {core_count} features enabled, got {enabled_count}"
        
        print(f"PASS: Trial plan has exactly {core_count} core features enabled")
        
        # List enabled features
        enabled_features = [k for k, v in features.items() if v == True]
        print(f"  - Enabled features: {enabled_features}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
