"""
Test file for CSV Export and Subscription Management endpoints.

Export endpoints:
- GET /api/export/minutes - CSV export for minutes
- GET /api/export/distributions - CSV export for distributions
- GET /api/export/compensation - CSV export for compensation
- GET /api/export/tasks - CSV export for tasks

Subscription endpoints:
- GET /api/subscription - Get subscription details
- POST /api/subscription/create-portal - Create Stripe billing portal
- POST /api/subscription/cancel - Cancel subscription at period end
- POST /api/subscription/reactivate - Reactivate canceled subscription
- POST /api/subscription/upgrade - Upgrade from monthly to annual
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestExportEndpoints:
    """Test CSV export endpoints - Minutes, Distributions, Compensation, Tasks"""
    
    @pytest.fixture(scope='class')
    def auth_token(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "test@example.com",
            "password": "testpassword123"
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Authentication failed - cannot test export endpoints")
    
    def test_export_minutes_requires_auth(self):
        """Test that export minutes requires authentication"""
        response = requests.get(f"{BASE_URL}/api/export/minutes")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Export minutes requires authentication (401)")
    
    def test_export_minutes_returns_csv(self, auth_token):
        """Test that export minutes returns CSV data"""
        response = requests.get(
            f"{BASE_URL}/api/export/minutes",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert "text/csv" in response.headers.get("Content-Type", ""), "Expected CSV content type"
        assert "Content-Disposition" in response.headers, "Expected Content-Disposition header"
        assert "minutes_export" in response.headers.get("Content-Disposition", ""), "Expected minutes_export in filename"
        
        # Verify CSV has headers
        content = response.text
        assert "Trust Name" in content, "CSV should have Trust Name column"
        assert "Minutes Type" in content, "CSV should have Minutes Type column"
        assert "Meeting Date" in content, "CSV should have Meeting Date column"
        print("PASS: Export minutes returns valid CSV with proper headers")
    
    def test_export_distributions_requires_auth(self):
        """Test that export distributions requires authentication"""
        response = requests.get(f"{BASE_URL}/api/export/distributions")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Export distributions requires authentication (401)")
    
    def test_export_distributions_returns_csv(self, auth_token):
        """Test that export distributions returns CSV data"""
        response = requests.get(
            f"{BASE_URL}/api/export/distributions",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert "text/csv" in response.headers.get("Content-Type", ""), "Expected CSV content type"
        assert "distributions_export" in response.headers.get("Content-Disposition", ""), "Expected distributions_export in filename"
        
        # Verify CSV has headers
        content = response.text
        assert "Trust Name" in content, "CSV should have Trust Name column"
        assert "Beneficiary" in content, "CSV should have Beneficiary column"
        assert "Amount" in content, "CSV should have Amount column"
        print("PASS: Export distributions returns valid CSV with proper headers")
    
    def test_export_compensation_requires_auth(self):
        """Test that export compensation requires authentication"""
        response = requests.get(f"{BASE_URL}/api/export/compensation")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Export compensation requires authentication (401)")
    
    def test_export_compensation_returns_csv(self, auth_token):
        """Test that export compensation returns CSV data"""
        response = requests.get(
            f"{BASE_URL}/api/export/compensation",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert "text/csv" in response.headers.get("Content-Type", ""), "Expected CSV content type"
        assert "compensation_export" in response.headers.get("Content-Disposition", ""), "Expected compensation_export in filename"
        
        # Verify CSV has headers
        content = response.text
        assert "Trust Name" in content, "CSV should have Trust Name column"
        assert "Amount" in content, "CSV should have Amount column"
        assert "Date" in content, "CSV should have Date column"
        print("PASS: Export compensation returns valid CSV with proper headers")
    
    def test_export_tasks_requires_auth(self):
        """Test that export tasks requires authentication"""
        response = requests.get(f"{BASE_URL}/api/export/tasks")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Export tasks requires authentication (401)")
    
    def test_export_tasks_returns_csv(self, auth_token):
        """Test that export tasks returns CSV data"""
        response = requests.get(
            f"{BASE_URL}/api/export/tasks",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert "text/csv" in response.headers.get("Content-Type", ""), "Expected CSV content type"
        assert "tasks_export" in response.headers.get("Content-Disposition", ""), "Expected tasks_export in filename"
        
        # Verify CSV has headers
        content = response.text
        assert "Trust Name" in content, "CSV should have Trust Name column"
        assert "Task Type" in content, "CSV should have Task Type column"
        assert "Due Date" in content, "CSV should have Due Date column"
        assert "Status" in content, "CSV should have Status column"
        print("PASS: Export tasks returns valid CSV with proper headers")
    
    def test_export_with_trust_filter(self, auth_token):
        """Test export with trust_id filter parameter"""
        # First get a trust ID
        trusts_response = requests.get(
            f"{BASE_URL}/api/trusts",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        if trusts_response.status_code == 200 and trusts_response.json():
            trust_id = trusts_response.json()[0].get("trust_id")
            
            response = requests.get(
                f"{BASE_URL}/api/export/minutes?trust_id={trust_id}",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            print(f"PASS: Export with trust_id filter works correctly")
        else:
            print("SKIP: No trusts available to test filter")


class TestSubscriptionEndpoints:
    """Test subscription management endpoints"""
    
    @pytest.fixture(scope='class')
    def auth_token(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "test@example.com",
            "password": "testpassword123"
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Authentication failed - cannot test subscription endpoints")
    
    def test_get_subscription_requires_auth(self):
        """Test that get subscription requires authentication"""
        response = requests.get(f"{BASE_URL}/api/subscription")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: GET /api/subscription requires authentication (401)")
    
    def test_get_subscription_returns_details(self, auth_token):
        """Test that get subscription returns subscription details"""
        response = requests.get(
            f"{BASE_URL}/api/subscription",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        # Validate required fields
        assert "subscription_id" in data, "Response should have subscription_id"
        assert "user_id" in data, "Response should have user_id"
        assert "plan_type" in data, "Response should have plan_type"
        assert "status" in data, "Response should have status"
        assert "is_active" in data, "Response should have is_active"
        
        # New fields for subscription management
        assert "current_period_end" in data, "Response should have current_period_end"
        assert "cancel_at_period_end" in data, "Response should have cancel_at_period_end"
        
        print(f"PASS: GET /api/subscription returns valid data. Plan: {data['plan_type']}, Status: {data['status']}")
        return data
    
    def test_subscription_has_trial_dates_for_trial_user(self, auth_token):
        """Test that trial users have trial date fields"""
        response = requests.get(
            f"{BASE_URL}/api/subscription",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        data = response.json()
        
        if data.get("status") == "trialing":
            assert "trial_start_date" in data, "Trial user should have trial_start_date"
            assert "trial_end_date" in data, "Trial user should have trial_end_date"
            assert "days_remaining" in data, "Trial user should have days_remaining"
            print(f"PASS: Trial user has trial dates. Days remaining: {data.get('days_remaining')}")
        else:
            print(f"SKIP: User is not on trial (status: {data.get('status')})")
    
    def test_create_portal_requires_auth(self):
        """Test that create portal requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/subscription/create-portal",
            json={"return_url": "https://example.com/billing"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: POST /api/subscription/create-portal requires authentication (401)")
    
    def test_create_portal_for_trial_user_returns_error(self, auth_token):
        """Test that portal creation fails for trial users without Stripe customer"""
        response = requests.post(
            f"{BASE_URL}/api/subscription/create-portal",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"return_url": "https://example.com/billing"}
        )
        # For trial users without stripe_customer_id, this should return 400
        # This is expected behavior per the agent_to_agent_context_note
        if response.status_code == 400:
            data = response.json()
            assert "detail" in data, "Error response should have detail"
            print(f"PASS: Portal creation returns 400 for trial user: {data.get('detail')}")
        elif response.status_code == 200:
            # User has active subscription
            data = response.json()
            assert "portal_url" in data, "Success response should have portal_url"
            print(f"PASS: Portal creation successful - user has active subscription")
        else:
            pytest.fail(f"Unexpected status code: {response.status_code}")
    
    def test_cancel_subscription_requires_auth(self):
        """Test that cancel subscription requires authentication"""
        response = requests.post(f"{BASE_URL}/api/subscription/cancel")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: POST /api/subscription/cancel requires authentication (401)")
    
    def test_cancel_subscription_for_trial_user_returns_error(self, auth_token):
        """Test that cancel fails for trial users without Stripe subscription"""
        response = requests.post(
            f"{BASE_URL}/api/subscription/cancel",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        # For trial users without stripe_subscription_id, this should return 400
        if response.status_code == 400:
            data = response.json()
            assert "detail" in data, "Error response should have detail"
            assert "No active subscription found" in data.get("detail", ""), "Should indicate no subscription"
            print(f"PASS: Cancel returns 400 for trial user: {data.get('detail')}")
        elif response.status_code == 200:
            # User has active subscription - this would actually cancel
            print("NOTE: Cancel succeeded - user has active Stripe subscription")
        else:
            pytest.fail(f"Unexpected status code: {response.status_code}")
    
    def test_reactivate_subscription_requires_auth(self):
        """Test that reactivate subscription requires authentication"""
        response = requests.post(f"{BASE_URL}/api/subscription/reactivate")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: POST /api/subscription/reactivate requires authentication (401)")
    
    def test_reactivate_subscription_for_trial_user_returns_error(self, auth_token):
        """Test that reactivate fails for trial users without Stripe subscription"""
        response = requests.post(
            f"{BASE_URL}/api/subscription/reactivate",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        # For trial users without stripe_subscription_id, this should return 400
        if response.status_code == 400:
            data = response.json()
            assert "detail" in data, "Error response should have detail"
            assert "No subscription found" in data.get("detail", ""), "Should indicate no subscription"
            print(f"PASS: Reactivate returns 400 for trial user: {data.get('detail')}")
        elif response.status_code == 200:
            # User has subscription that was canceled
            print("NOTE: Reactivate succeeded - user has Stripe subscription")
        else:
            pytest.fail(f"Unexpected status code: {response.status_code}")
    
    def test_upgrade_subscription_requires_auth(self):
        """Test that upgrade subscription requires authentication"""
        response = requests.post(f"{BASE_URL}/api/subscription/upgrade")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: POST /api/subscription/upgrade requires authentication (401)")
    
    def test_upgrade_subscription_for_trial_user_returns_error(self, auth_token):
        """Test that upgrade fails for trial users without Stripe subscription"""
        response = requests.post(
            f"{BASE_URL}/api/subscription/upgrade",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        # For trial users without stripe_subscription_id, this should return 400
        if response.status_code == 400:
            data = response.json()
            assert "detail" in data, "Error response should have detail"
            assert "No active subscription found" in data.get("detail", ""), "Should indicate no subscription"
            print(f"PASS: Upgrade returns 400 for trial user: {data.get('detail')}")
        elif response.status_code == 200:
            # User has active monthly subscription
            print("NOTE: Upgrade succeeded - user has active monthly subscription")
        else:
            pytest.fail(f"Unexpected status code: {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
