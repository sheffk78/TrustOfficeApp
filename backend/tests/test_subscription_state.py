"""
Test suite for subscription state management and read-only mode for expired subscriptions.

Tests:
1. GET /api/subscription/state - returns correct SubscriptionState object
2. GET /api/dashboard - includes subscription field with is_active, is_read_only, etc.
3. Active subscription allows all CRUD operations
4. Expired subscription blocks write operations with 403
5. Expired subscription allows read operations (GET)
6. Error message for blocked writes includes 'subscription is inactive' text
"""
import pytest
import requests
import os
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')

# Test credentials from context
TEST_EMAIL = "demo@trustoffice.com"
TEST_PASSWORD = "demopassword"
TEST_TRUST_ID = "trust_b753cb8fe07f"


class TestSubscriptionStateEndpoint:
    """Tests for GET /api/subscription/state endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self, authenticated_client):
        self.client = authenticated_client
        self.token = authenticated_client.headers.get("Authorization", "").replace("Bearer ", "")
    
    def test_subscription_state_endpoint_returns_200(self, authenticated_client):
        """GET /api/subscription/state should return 200 for authenticated user"""
        response = authenticated_client.get(f"{BASE_URL}/api/subscription/state")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ GET /api/subscription/state returns 200")
    
    def test_subscription_state_has_required_fields(self, authenticated_client):
        """GET /api/subscription/state should return SubscriptionState object with all required fields"""
        response = authenticated_client.get(f"{BASE_URL}/api/subscription/state")
        assert response.status_code == 200
        
        data = response.json()
        
        # Check all required fields in SubscriptionState
        required_fields = [
            "user_id",
            "plan_type",
            "status",
            "is_trial",
            "is_active",
            "is_read_only",
            "trial_days_remaining"
        ]
        
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        # Validate field types
        assert isinstance(data["user_id"], str), "user_id should be string"
        assert isinstance(data["plan_type"], str), "plan_type should be string"
        assert isinstance(data["status"], str), "status should be string"
        assert isinstance(data["is_trial"], bool), "is_trial should be boolean"
        assert isinstance(data["is_active"], bool), "is_active should be boolean"
        assert isinstance(data["is_read_only"], bool), "is_read_only should be boolean"
        # trial_days_remaining can be int or None
        assert data["trial_days_remaining"] is None or isinstance(data["trial_days_remaining"], int), \
            "trial_days_remaining should be int or null"
        
        print(f"✓ SubscriptionState has all required fields")
        print(f"  - is_active: {data['is_active']}")
        print(f"  - is_read_only: {data['is_read_only']}")
        print(f"  - is_trial: {data['is_trial']}")
        print(f"  - status: {data['status']}")
        print(f"  - trial_days_remaining: {data['trial_days_remaining']}")
    
    def test_subscription_state_plan_type_valid(self, authenticated_client):
        """plan_type should be one of: trial, monthly, annual"""
        response = authenticated_client.get(f"{BASE_URL}/api/subscription/state")
        assert response.status_code == 200
        
        data = response.json()
        valid_plan_types = ["trial", "monthly", "annual"]
        assert data["plan_type"] in valid_plan_types, \
            f"Invalid plan_type: {data['plan_type']}. Expected one of: {valid_plan_types}"
        
        print(f"✓ plan_type is valid: {data['plan_type']}")
    
    def test_subscription_state_status_valid(self, authenticated_client):
        """status should be one of: trialing, active, past_due, canceled, expired"""
        response = authenticated_client.get(f"{BASE_URL}/api/subscription/state")
        assert response.status_code == 200
        
        data = response.json()
        valid_statuses = ["trialing", "active", "past_due", "canceled", "expired"]
        assert data["status"] in valid_statuses, \
            f"Invalid status: {data['status']}. Expected one of: {valid_statuses}"
        
        print(f"✓ status is valid: {data['status']}")


class TestDashboardSubscriptionField:
    """Tests for subscription field in GET /api/dashboard"""
    
    def test_dashboard_includes_subscription_field(self, authenticated_client):
        """GET /api/dashboard should include subscription field with state info"""
        response = authenticated_client.get(f"{BASE_URL}/api/dashboard?trust_id={TEST_TRUST_ID}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "subscription" in data, "Dashboard response missing 'subscription' field"
        
        subscription = data["subscription"]
        
        # Check required subscription fields
        required_fields = ["plan_type", "status", "is_trial", "is_active", "is_read_only"]
        for field in required_fields:
            assert field in subscription, f"Subscription missing field: {field}"
        
        # Validate types
        assert isinstance(subscription["plan_type"], str), "plan_type should be string"
        assert isinstance(subscription["status"], str), "status should be string"
        assert isinstance(subscription["is_trial"], bool), "is_trial should be boolean"
        assert isinstance(subscription["is_active"], bool), "is_active should be boolean"
        assert isinstance(subscription["is_read_only"], bool), "is_read_only should be boolean"
        
        print(f"✓ Dashboard includes subscription field with all required data")
        print(f"  - plan_type: {subscription['plan_type']}")
        print(f"  - status: {subscription['status']}")
        print(f"  - is_active: {subscription['is_active']}")
        print(f"  - is_read_only: {subscription['is_read_only']}")


class TestActiveSubscriptionCRUD:
    """Tests that active subscription allows all CRUD operations"""
    
    def test_get_request_allowed_with_active_subscription(self, authenticated_client):
        """GET requests should be allowed with active subscription"""
        response = authenticated_client.get(f"{BASE_URL}/api/trusts")
        assert response.status_code == 200, f"GET /trusts failed: {response.text}"
        print("✓ GET request allowed with active subscription")
    
    def test_post_request_allowed_with_active_subscription(self, authenticated_client):
        """POST requests should be allowed with active subscription"""
        # First check if subscription is active
        state_response = authenticated_client.get(f"{BASE_URL}/api/subscription/state")
        state = state_response.json()
        
        if not state["is_active"]:
            pytest.skip("Subscription is not active - skipping active subscription CRUD test")
        
        # Try to create a governance task (POST operation) using correct endpoint
        task_data = {
            "trust_id": TEST_TRUST_ID,
            "task_type": "custom",
            "due_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "description": "TEST_subscription_test_task"
        }
        response = authenticated_client.post(f"{BASE_URL}/api/tasks", json=task_data)
        
        # Should succeed with active subscription
        assert response.status_code in [200, 201], f"POST failed: {response.status_code} {response.text}"
        print("✓ POST request allowed with active subscription")
        
        # Clean up
        if response.status_code in [200, 201]:
            task_id = response.json().get("task_id")
            if task_id:
                authenticated_client.delete(f"{BASE_URL}/api/tasks/{task_id}")
    
    def test_put_request_allowed_with_active_subscription(self, authenticated_client):
        """PUT/PATCH requests should be allowed with active subscription"""
        # First check if subscription is active
        state_response = authenticated_client.get(f"{BASE_URL}/api/subscription/state")
        state = state_response.json()
        
        if not state["is_active"]:
            pytest.skip("Subscription is not active - skipping active subscription CRUD test")
        
        # Get the trust to update
        response = authenticated_client.get(f"{BASE_URL}/api/trusts/{TEST_TRUST_ID}")
        if response.status_code != 200:
            pytest.skip("Trust not found")
        
        trust = response.json()
        original_jurisdiction = trust.get("jurisdiction", "")
        
        # Try to update the trust
        update_data = {"jurisdiction": "Test Jurisdiction Updated"}
        response = authenticated_client.put(f"{BASE_URL}/api/trusts/{TEST_TRUST_ID}", json=update_data)
        
        assert response.status_code == 200, f"PUT failed: {response.status_code} {response.text}"
        print("✓ PUT request allowed with active subscription")
        
        # Restore original value
        authenticated_client.put(f"{BASE_URL}/api/trusts/{TEST_TRUST_ID}", json={"jurisdiction": original_jurisdiction})


class TestExpiredSubscriptionReadOnly:
    """Tests for read-only mode with expired subscription.
    
    To test expired subscription:
    1. Set trial_end_date to a past date in MongoDB
    2. Run tests
    3. Restore original trial_end_date
    """
    
    @pytest.fixture
    def expired_subscription_client(self, api_client, mongo_client):
        """
        Create a client with expired subscription by temporarily modifying trial_end_date.
        
        This fixture:
        1. Authenticates the user
        2. Saves the original subscription data
        3. Sets trial_end_date to past date
        4. Yields the authenticated client
        5. Restores original subscription data
        """
        # Authenticate
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        
        if response.status_code != 200:
            pytest.skip(f"Login failed: {response.text}")
        
        token = response.json()["token"]
        api_client.headers.update({"Authorization": f"Bearer {token}"})
        
        # Get user_id from subscription state
        state_response = api_client.get(f"{BASE_URL}/api/subscription/state")
        user_id = state_response.json()["user_id"]
        
        # Get MongoDB connection
        db = mongo_client
        
        # Save original subscription data
        original_sub = db.subscriptions.find_one({"user_id": user_id})
        
        if not original_sub:
            pytest.skip("No subscription found for user")
        
        original_data = {
            "trial_end_date": original_sub.get("trial_end_date"),
            "status": original_sub.get("status")
        }
        
        # Set trial_end_date to past (7 days ago) to simulate expired subscription
        expired_date = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        db.subscriptions.update_one(
            {"user_id": user_id},
            {"$set": {
                "trial_end_date": expired_date,
                "status": "trialing"  # Keep as trialing, but with past date
            }}
        )
        
        yield api_client
        
        # Restore original subscription data
        db.subscriptions.update_one(
            {"user_id": user_id},
            {"$set": original_data}
        )
    
    def test_expired_subscription_blocks_post_with_403(self, expired_subscription_client):
        """POST requests should return 403 when subscription is expired"""
        # First verify subscription is read-only
        state_response = expired_subscription_client.get(f"{BASE_URL}/api/subscription/state")
        state = state_response.json()
        
        assert state["is_read_only"] == True, f"Expected is_read_only=True, got {state['is_read_only']}"
        assert state["is_active"] == False, f"Expected is_active=False, got {state['is_active']}"
        
        # Try to create a task (POST operation) - should be blocked
        task_data = {
            "trust_id": TEST_TRUST_ID,
            "task_type": "custom",
            "due_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "description": "TEST_expired_subscription_task"
        }
        response = expired_subscription_client.post(f"{BASE_URL}/api/governance-tasks", json=task_data)
        
        assert response.status_code == 403, \
            f"Expected 403 for POST with expired subscription, got {response.status_code}: {response.text}"
        print("✓ POST blocked with 403 for expired subscription")
    
    def test_expired_subscription_blocks_put_with_403(self, expired_subscription_client):
        """PUT requests should return 403 when subscription is expired"""
        # Verify subscription is read-only
        state_response = expired_subscription_client.get(f"{BASE_URL}/api/subscription/state")
        state = state_response.json()
        
        assert state["is_read_only"] == True
        
        # Try to update trust (PUT operation) - should be blocked
        update_data = {"jurisdiction": "Test Jurisdiction Blocked"}
        response = expired_subscription_client.put(f"{BASE_URL}/api/trusts/{TEST_TRUST_ID}", json=update_data)
        
        assert response.status_code == 403, \
            f"Expected 403 for PUT with expired subscription, got {response.status_code}: {response.text}"
        print("✓ PUT blocked with 403 for expired subscription")
    
    def test_expired_subscription_blocks_delete_with_403(self, expired_subscription_client):
        """DELETE requests should return 403 when subscription is expired"""
        # Verify subscription is read-only
        state_response = expired_subscription_client.get(f"{BASE_URL}/api/subscription/state")
        state = state_response.json()
        
        assert state["is_read_only"] == True
        
        # Try to delete a task (DELETE operation) - should be blocked
        # Use a non-existent task ID to avoid actually deleting anything
        response = expired_subscription_client.delete(f"{BASE_URL}/api/governance-tasks/task_nonexistent123")
        
        # Should return 403 before checking if task exists
        assert response.status_code == 403, \
            f"Expected 403 for DELETE with expired subscription, got {response.status_code}: {response.text}"
        print("✓ DELETE blocked with 403 for expired subscription")
    
    def test_expired_subscription_allows_get_requests(self, expired_subscription_client):
        """GET requests should be allowed even with expired subscription"""
        # Verify subscription is read-only
        state_response = expired_subscription_client.get(f"{BASE_URL}/api/subscription/state")
        state = state_response.json()
        
        assert state["is_read_only"] == True
        assert state["is_active"] == False
        
        # GET trusts should still work
        response = expired_subscription_client.get(f"{BASE_URL}/api/trusts")
        assert response.status_code == 200, \
            f"GET /trusts should work with expired subscription, got {response.status_code}: {response.text}"
        
        # GET specific trust should still work
        response = expired_subscription_client.get(f"{BASE_URL}/api/trusts/{TEST_TRUST_ID}")
        assert response.status_code == 200, \
            f"GET /trusts/{{id}} should work with expired subscription, got {response.status_code}: {response.text}"
        
        # GET dashboard should still work
        response = expired_subscription_client.get(f"{BASE_URL}/api/dashboard?trust_id={TEST_TRUST_ID}")
        assert response.status_code == 200, \
            f"GET /dashboard should work with expired subscription, got {response.status_code}: {response.text}"
        
        print("✓ GET requests allowed with expired subscription (read-only mode)")
    
    def test_expired_subscription_error_message_contains_inactive_text(self, expired_subscription_client):
        """Error message for blocked writes should include 'subscription is inactive' text"""
        # Verify subscription is read-only
        state_response = expired_subscription_client.get(f"{BASE_URL}/api/subscription/state")
        state = state_response.json()
        
        assert state["is_read_only"] == True
        
        # Try a write operation to get the error message
        task_data = {
            "trust_id": TEST_TRUST_ID,
            "task_type": "custom",
            "due_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "description": "TEST_error_message_task"
        }
        response = expired_subscription_client.post(f"{BASE_URL}/api/governance-tasks", json=task_data)
        
        assert response.status_code == 403
        
        error_data = response.json()
        error_detail = error_data.get("detail", "")
        
        # Check that error message contains expected text
        assert "subscription is inactive" in error_detail.lower() or "inactive" in error_detail.lower(), \
            f"Error message should mention 'subscription is inactive'. Got: {error_detail}"
        
        print(f"✓ Error message contains expected text: '{error_detail}'")
    
    def test_expired_subscription_error_includes_subscription_status(self, expired_subscription_client):
        """Error response should include subscription_status and is_read_only fields"""
        # Verify subscription is read-only
        state_response = expired_subscription_client.get(f"{BASE_URL}/api/subscription/state")
        state = state_response.json()
        
        assert state["is_read_only"] == True
        
        # Try a write operation
        task_data = {
            "trust_id": TEST_TRUST_ID,
            "task_type": "custom",
            "due_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "description": "TEST_error_fields_task"
        }
        response = expired_subscription_client.post(f"{BASE_URL}/api/governance-tasks", json=task_data)
        
        assert response.status_code == 403
        
        error_data = response.json()
        
        # Check for subscription status fields in error response
        assert "subscription_status" in error_data or "status" in error_data, \
            f"Error response should include subscription_status. Got: {error_data}"
        assert "is_read_only" in error_data, \
            f"Error response should include is_read_only. Got: {error_data}"
        
        print(f"✓ Error response includes subscription status fields")


class TestSubscriptionExemptPaths:
    """Tests that certain paths are exempt from subscription checks"""
    
    def test_auth_endpoints_exempt_from_subscription_check(self, api_client):
        """Auth endpoints should work regardless of subscription status"""
        # Login should always work
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        print("✓ /api/auth/login exempt from subscription check")
    
    def test_subscription_endpoints_exempt_from_subscription_check(self, authenticated_client):
        """Subscription management endpoints should work even with expired subscription"""
        # These endpoints should be accessible for managing subscription
        # GET subscription should work
        response = authenticated_client.get(f"{BASE_URL}/api/subscription")
        assert response.status_code == 200, f"GET /subscription failed: {response.text}"
        print("✓ /api/subscription endpoint accessible")
        
        # GET subscription/state should work
        response = authenticated_client.get(f"{BASE_URL}/api/subscription/state")
        assert response.status_code == 200, f"GET /subscription/state failed: {response.text}"
        print("✓ /api/subscription/state endpoint accessible")


# ==================== FIXTURES ====================

@pytest.fixture
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture
def authenticated_client(api_client):
    """Session with auth token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.text}")
    
    token = response.json()["token"]
    api_client.headers.update({"Authorization": f"Bearer {token}"})
    return api_client


@pytest.fixture
def mongo_client():
    """Direct MongoDB connection for test setup/teardown"""
    from pymongo import MongoClient
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'trustoffice')
    
    client = MongoClient(mongo_url)
    db = client[db_name]
    yield db
    client.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
