# Test Suite for Server.py Cleanup - Migrated Routers
# Tests for: email.py, background_jobs.py, categories.py, beneficiaries.py, demo.py
# Plus regression tests for dashboard, trusts, distributions after refactoring

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')

# Test credentials
TEST_EMAIL = "demo@trustoffice.com"
TEST_PASSWORD = "demopassword"


@pytest.fixture(scope="module")
def auth_token():
    """Get auth token for tests"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Authentication failed")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get auth headers for tests"""
    return {"Authorization": f"Bearer {auth_token}"}


# ==================== AUTH ROUTER (Regression) ====================

class TestAuthRouterRegression:
    """Regression tests for auth endpoints after server.py refactoring"""
    
    def test_login_works(self):
        """POST /api/auth/login works after refactoring"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == TEST_EMAIL
        print("✓ Login works correctly")
    
    def test_get_me(self, auth_headers):
        """GET /api/auth/me works after refactoring"""
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "user_id" in data
        assert "email" in data
        assert data["email"] == TEST_EMAIL
        print(f"✓ GET /api/auth/me returned user: {data['email']}")


# ==================== CATEGORIES ROUTER (New Migration) ====================

class TestCategoriesRouter:
    """Test Categories endpoint migrated to routers/categories.py"""
    
    def test_get_categories_no_auth_required(self):
        """GET /api/categories does not require authentication"""
        response = requests.get(f"{BASE_URL}/api/categories")
        assert response.status_code == 200
        print("✓ Categories accessible without auth")
    
    def test_get_categories_returns_enums(self):
        """GET /api/categories returns enum values for forms"""
        response = requests.get(f"{BASE_URL}/api/categories")
        assert response.status_code == 200
        data = response.json()
        
        # Verify all expected enum categories exist
        assert "purpose_classifications" in data
        assert "task_types" in data
        assert "minutes_types" in data
        assert "entity_types" in data
        assert "relationship_types" in data
        
        # Verify content
        assert "distribution" in data["purpose_classifications"]
        assert "annual_review" in data["task_types"]
        assert "quarterly" in data["minutes_types"]
        assert "Trust" in data["entity_types"]
        assert "owns" in data["relationship_types"]
        
        print(f"✓ Categories returned: {len(data)} categories")
        print(f"  - purpose_classifications: {data['purpose_classifications']}")
        print(f"  - task_types: {data['task_types']}")


# ==================== EMAIL ROUTER (New Migration) ====================

class TestEmailRouter:
    """Test Email endpoints migrated to routers/email.py"""
    
    def test_get_email_status_requires_auth(self):
        """GET /api/email/status requires authentication"""
        response = requests.get(f"{BASE_URL}/api/email/status")
        assert response.status_code == 401
    
    def test_get_email_status_returns_config(self, auth_headers):
        """GET /api/email/status returns email service configuration"""
        response = requests.get(f"{BASE_URL}/api/email/status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "configured" in data
        assert "from_email" in data
        assert "from_name" in data
        assert "available_templates" in data
        
        # Verify email is configured
        assert data["configured"] == True
        assert data["from_name"] == "TrustOffice"
        
        # Verify templates list
        templates = data["available_templates"]
        assert "welcome" in templates
        assert "task_reminder" in templates
        assert "task_overdue" in templates
        assert "password_reset" in templates
        
        print(f"✓ Email status: configured={data['configured']}, templates={len(templates)}")


# ==================== BACKGROUND JOBS ROUTER (New Migration) ====================

class TestBackgroundJobsRouter:
    """Test Background Jobs endpoints migrated to routers/background_jobs.py"""
    
    def test_get_background_jobs_status_requires_auth(self):
        """GET /api/background-jobs/status requires authentication"""
        response = requests.get(f"{BASE_URL}/api/background-jobs/status")
        assert response.status_code == 401
    
    def test_get_background_jobs_status(self, auth_headers):
        """GET /api/background-jobs/status returns scheduler status"""
        response = requests.get(f"{BASE_URL}/api/background-jobs/status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "running" in data
        assert "jobs" in data
        assert "scheduler_active" in data
        
        # Verify scheduler is running
        assert data["running"] == True
        assert data["scheduler_active"] == True
        
        # Verify jobs list
        jobs = data["jobs"]
        assert len(jobs) >= 3
        
        # Check specific jobs exist
        job_ids = [j["id"] for j in jobs]
        assert "task_status_update" in job_ids
        assert "daily_reminders" in job_ids
        assert "daily_health_snapshots" in job_ids
        
        print(f"✓ Background jobs: running={data['running']}, jobs={len(jobs)}")
        for job in jobs:
            print(f"  - {job['id']}: {job['name']}")


# ==================== BENEFICIARIES ROUTER (New Migration) ====================

class TestBeneficiariesRouter:
    """Test Beneficiaries dashboard migrated to routers/beneficiaries.py"""
    
    def test_get_beneficiary_dashboard_requires_auth(self):
        """GET /api/beneficiaries/dashboard requires authentication"""
        response = requests.get(f"{BASE_URL}/api/beneficiaries/dashboard")
        assert response.status_code == 401
    
    def test_get_beneficiary_dashboard_returns_402_for_trial(self, auth_headers):
        """GET /api/beneficiaries/dashboard returns 402 for trial users"""
        response = requests.get(f"{BASE_URL}/api/beneficiaries/dashboard", headers=auth_headers)
        # 402 = Payment Required - premium feature not available for trial
        assert response.status_code == 402
        data = response.json()
        assert "detail" in data
        assert "beneficiary_dashboard" in data["detail"].lower() or "subscription" in data["detail"].lower()
        print(f"✓ Beneficiaries dashboard correctly gated: {response.status_code}")


# ==================== DEMO ROUTER (New Migration) ====================

class TestDemoRouter:
    """Test Demo seed endpoint migrated to routers/demo.py"""
    
    def test_seed_demo_data_requires_auth(self):
        """POST /api/demo/seed requires authentication"""
        response = requests.post(f"{BASE_URL}/api/demo/seed")
        assert response.status_code == 401
    
    def test_seed_demo_data_returns_already_has_trusts(self, auth_headers):
        """POST /api/demo/seed returns seeded=false if user has trusts"""
        response = requests.post(f"{BASE_URL}/api/demo/seed", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Demo user already has trusts, so should not seed again
        assert "seeded" in data
        assert data["seeded"] == False
        assert "message" in data
        assert "already" in data["message"].lower()
        
        print(f"✓ Demo seed: seeded={data['seeded']}, message={data['message']}")


# ==================== DASHBOARD ROUTER (Regression) ====================

class TestDashboardRegression:
    """Regression tests for dashboard after server.py refactoring"""
    
    def test_get_dashboard(self, auth_headers):
        """GET /api/dashboard works after refactoring"""
        # Get a trust ID first
        trusts_response = requests.get(f"{BASE_URL}/api/trusts", headers=auth_headers)
        trusts = trusts_response.json()
        trust_id = trusts[0]["trust_id"] if trusts else None
        
        if not trust_id:
            pytest.skip("No trusts available")
        
        response = requests.get(f"{BASE_URL}/api/dashboard?trust_id={trust_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify dashboard structure
        assert "trust_id" in data
        assert "trust_name" in data
        assert "health_score" in data
        assert "recent_activity" in data
        assert "stats" in data
        assert "subscription" in data
        
        print(f"✓ Dashboard for {data['trust_name']}: score={data['health_score']['total_score']}")


# ==================== TRUSTS ROUTER (Regression) ====================

class TestTrustsRegression:
    """Regression tests for trusts endpoint after server.py refactoring"""
    
    def test_get_trusts(self, auth_headers):
        """GET /api/trusts works after refactoring"""
        response = requests.get(f"{BASE_URL}/api/trusts", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        assert len(data) >= 1  # Demo user has trusts
        
        # Verify trust structure
        trust = data[0]
        assert "trust_id" in trust
        assert "name" in trust
        assert "trust_type" in trust
        assert "jurisdiction" in trust
        assert "governance_score" in trust
        
        print(f"✓ Trusts returned: {len(data)} trusts")
        for t in data:
            print(f"  - {t['name']} ({t['trust_id']})")


# ==================== DISTRIBUTIONS ROUTER (Regression) ====================

class TestDistributionsRegression:
    """Regression tests for distributions endpoint after server.py refactoring"""
    
    def test_get_distributions(self, auth_headers):
        """GET /api/distributions works after refactoring"""
        # Get a trust ID first
        trusts_response = requests.get(f"{BASE_URL}/api/trusts", headers=auth_headers)
        trusts = trusts_response.json()
        trust_id = trusts[0]["trust_id"] if trusts else None
        
        if not trust_id:
            pytest.skip("No trusts available")
        
        response = requests.get(f"{BASE_URL}/api/distributions?trust_id={trust_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        
        # If there are distributions, verify structure
        if data:
            dist = data[0]
            assert "distribution_id" in dist
            assert "beneficiary_name" in dist
            assert "amount" in dist
            assert "date" in dist
            print(f"✓ Distributions returned: {len(data)} records")
        else:
            print("✓ Distributions endpoint works (0 records)")


# ==================== ALL ROUTERS INTEGRATION TEST ====================

class TestAllRoutersIntegration:
    """Integration tests to verify all 19 routers are properly registered"""
    
    def test_all_migrated_routers_accessible(self, auth_headers):
        """Verify all newly migrated router endpoints are accessible"""
        endpoints = [
            ("/api/categories", "GET", False),
            ("/api/email/status", "GET", True),
            ("/api/background-jobs/status", "GET", True),
            ("/api/beneficiaries/dashboard", "GET", True),  # Returns 402 but is accessible
            ("/api/demo/seed", "POST", True),
        ]
        
        results = []
        for path, method, needs_auth in endpoints:
            headers = auth_headers if needs_auth else {}
            
            if method == "GET":
                response = requests.get(f"{BASE_URL}{path}", headers=headers)
            else:
                response = requests.post(f"{BASE_URL}{path}", headers=headers)
            
            # 200, 402 (payment required), 403 are all valid "accessible" responses
            is_accessible = response.status_code in [200, 402]
            results.append({
                "path": path,
                "method": method,
                "status": response.status_code,
                "accessible": is_accessible
            })
            
            if not is_accessible:
                print(f"  ✗ {method} {path} returned {response.status_code}")
        
        # All endpoints should be accessible
        all_accessible = all(r["accessible"] for r in results)
        assert all_accessible, f"Some endpoints not accessible: {[r for r in results if not r['accessible']]}"
        
        print("✓ All migrated routers accessible:")
        for r in results:
            print(f"  - {r['method']} {r['path']}: {r['status']}")
    
    def test_core_routers_still_work(self, auth_headers):
        """Verify core routers (trusts, distributions, dashboard) still work"""
        # Get trust ID
        trusts_response = requests.get(f"{BASE_URL}/api/trusts", headers=auth_headers)
        assert trusts_response.status_code == 200
        trusts = trusts_response.json()
        trust_id = trusts[0]["trust_id"]
        
        # Test dashboard
        dashboard_response = requests.get(f"{BASE_URL}/api/dashboard?trust_id={trust_id}", headers=auth_headers)
        assert dashboard_response.status_code == 200
        
        # Test distributions
        dist_response = requests.get(f"{BASE_URL}/api/distributions?trust_id={trust_id}", headers=auth_headers)
        assert dist_response.status_code == 200
        
        # Test tasks
        tasks_response = requests.get(f"{BASE_URL}/api/tasks?trust_id={trust_id}", headers=auth_headers)
        assert tasks_response.status_code == 200
        
        # Test minutes
        minutes_response = requests.get(f"{BASE_URL}/api/minutes?trust_id={trust_id}", headers=auth_headers)
        assert minutes_response.status_code == 200
        
        # Test subscription
        sub_response = requests.get(f"{BASE_URL}/api/subscription", headers=auth_headers)
        assert sub_response.status_code == 200
        
        print("✓ All core routers working correctly")
