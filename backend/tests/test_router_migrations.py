# Test Suite for Router Migrations: schedule_a, compensation, subscriptions
# Tests all migrated endpoints to ensure they return correct data

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')

# Test credentials
TEST_EMAIL = "demo@trustoffice.com"
TEST_PASSWORD = "demopassword"
TEST_TRUST_ID = "trust_b753cb8fe07f"


class TestAuthentication:
    """Auth helper - login to get token"""
    
    def test_login_works(self):
        """Verify demo user can login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data
        print(f"Login successful, token obtained")


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


# ==================== SCHEDULE A ROUTER TESTS ====================

class TestScheduleARouter:
    """Test Schedule A endpoints migrated to routers/schedule_a.py"""
    
    def test_get_schedule_a_items_requires_auth(self):
        """GET /api/schedule-a requires authentication"""
        response = requests.get(f"{BASE_URL}/api/schedule-a?trust_id={TEST_TRUST_ID}")
        assert response.status_code == 401
    
    def test_get_schedule_a_items_returns_list(self, auth_headers):
        """GET /api/schedule-a returns a list of assets"""
        response = requests.get(
            f"{BASE_URL}/api/schedule-a?trust_id={TEST_TRUST_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"GET /api/schedule-a returned {len(data)} items")
    
    def test_get_schedule_a_item_not_found(self, auth_headers):
        """GET /api/schedule-a/{item_id} returns 404 for invalid ID"""
        response = requests.get(
            f"{BASE_URL}/api/schedule-a/invalid_item_id",
            headers=auth_headers
        )
        assert response.status_code == 404
    
    def test_get_schedule_a_summary(self, auth_headers):
        """GET /api/schedule-a/summary/{trust_id} returns summary with categories"""
        response = requests.get(
            f"{BASE_URL}/api/schedule-a/summary/{TEST_TRUST_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "trust_id" in data
        assert "categories" in data
        assert "total_items" in data
        assert "total_value" in data
        print(f"Schedule A summary: {data['total_items']} items, total value: ${data['total_value']}")
    
    def test_get_schedule_a_summary_invalid_trust(self, auth_headers):
        """GET /api/schedule-a/summary/{trust_id} returns 404 for invalid trust"""
        response = requests.get(
            f"{BASE_URL}/api/schedule-a/summary/invalid_trust_id",
            headers=auth_headers
        )
        assert response.status_code == 404
    
    def test_create_schedule_a_item(self, auth_headers):
        """POST /api/schedule-a creates a new asset"""
        create_data = {
            "trust_id": TEST_TRUST_ID,
            "category": "other_property",
            "description": "TEST_Asset for testing",
            "identifier": "TEST-001",
            "location": "Test Location",
            "approximate_value": 1000.00,
            "date_conveyed": "2024-01-01",
            "notes": "Created by pytest"
        }
        response = requests.post(
            f"{BASE_URL}/api/schedule-a",
            headers=auth_headers,
            json=create_data
        )
        assert response.status_code == 200
        data = response.json()
        assert "item_id" in data
        assert data["description"] == create_data["description"]
        assert data["category"] == "other_property"
        assert data["status"] == "active"
        print(f"Created asset with ID: {data['item_id']}")
        
        # Clean up - delete the created asset
        item_id = data["item_id"]
        delete_response = requests.delete(
            f"{BASE_URL}/api/schedule-a/{item_id}",
            headers=auth_headers
        )
        assert delete_response.status_code == 200
        print(f"Cleaned up test asset: {item_id}")
    
    def test_create_and_get_schedule_a_item(self, auth_headers):
        """POST then GET to verify persistence"""
        # Create asset
        create_data = {
            "trust_id": TEST_TRUST_ID,
            "category": "financial_accounts",
            "description": "TEST_Bank Account",
            "identifier": "TEST-ACC-123",
            "location": "Bank of Test",
            "approximate_value": 5000.00,
            "date_conveyed": "2024-01-15",
            "notes": "Persistence test"
        }
        create_response = requests.post(
            f"{BASE_URL}/api/schedule-a",
            headers=auth_headers,
            json=create_data
        )
        assert create_response.status_code == 200
        item_id = create_response.json()["item_id"]
        
        # GET to verify persistence
        get_response = requests.get(
            f"{BASE_URL}/api/schedule-a/{item_id}",
            headers=auth_headers
        )
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["description"] == create_data["description"]
        assert data["identifier"] == create_data["identifier"]
        assert data["approximate_value"] == create_data["approximate_value"]
        print(f"Verified persistence for asset: {item_id}")
        
        # Clean up
        requests.delete(f"{BASE_URL}/api/schedule-a/{item_id}", headers=auth_headers)
    
    def test_update_schedule_a_item(self, auth_headers):
        """PUT /api/schedule-a/{item_id} updates asset"""
        # Create asset first
        create_data = {
            "trust_id": TEST_TRUST_ID,
            "category": "personal_property",
            "description": "TEST_Original Description",
            "identifier": "TEST-UPDATE-001",
            "location": "Original Location",
            "approximate_value": 1500.00,
            "date_conveyed": "2024-02-01",
            "notes": "Before update"
        }
        create_response = requests.post(
            f"{BASE_URL}/api/schedule-a",
            headers=auth_headers,
            json=create_data
        )
        item_id = create_response.json()["item_id"]
        
        # Update the asset
        update_data = {
            "description": "TEST_Updated Description",
            "approximate_value": 2500.00,
            "notes": "After update by pytest"
        }
        update_response = requests.put(
            f"{BASE_URL}/api/schedule-a/{item_id}",
            headers=auth_headers,
            json=update_data
        )
        assert update_response.status_code == 200
        data = update_response.json()
        assert data["description"] == update_data["description"]
        assert data["approximate_value"] == update_data["approximate_value"]
        assert data["updated_at"] is not None
        print(f"Updated asset: {item_id}")
        
        # Verify update persisted
        get_response = requests.get(f"{BASE_URL}/api/schedule-a/{item_id}", headers=auth_headers)
        assert get_response.json()["description"] == update_data["description"]
        
        # Clean up
        requests.delete(f"{BASE_URL}/api/schedule-a/{item_id}", headers=auth_headers)
    
    def test_delete_schedule_a_item(self, auth_headers):
        """DELETE /api/schedule-a/{item_id} removes asset"""
        # Create asset first
        create_response = requests.post(
            f"{BASE_URL}/api/schedule-a",
            headers=auth_headers,
            json={
                "trust_id": TEST_TRUST_ID,
                "category": "other_property",
                "description": "TEST_To be deleted",
                "identifier": "TEST-DEL-001",
                "date_conveyed": "2024-03-01"
            }
        )
        item_id = create_response.json()["item_id"]
        
        # Delete the asset
        delete_response = requests.delete(
            f"{BASE_URL}/api/schedule-a/{item_id}",
            headers=auth_headers
        )
        assert delete_response.status_code == 200
        assert delete_response.json()["message"] == "Asset deleted"
        
        # Verify deletion
        get_response = requests.get(f"{BASE_URL}/api/schedule-a/{item_id}", headers=auth_headers)
        assert get_response.status_code == 404
        print(f"Verified deletion of asset: {item_id}")
    
    def test_delete_schedule_a_item_not_found(self, auth_headers):
        """DELETE /api/schedule-a/{item_id} returns 404 for invalid ID"""
        response = requests.delete(
            f"{BASE_URL}/api/schedule-a/invalid_item_id",
            headers=auth_headers
        )
        assert response.status_code == 404


# ==================== COMPENSATION ROUTER TESTS ====================

class TestCompensationRouter:
    """Test Compensation endpoints migrated to routers/compensation.py"""
    
    def test_get_compensation_plans_requires_auth(self):
        """GET /api/compensation-plans requires authentication"""
        response = requests.get(f"{BASE_URL}/api/compensation-plans?trust_id={TEST_TRUST_ID}")
        assert response.status_code == 401
    
    def test_get_compensation_plans_returns_list(self, auth_headers):
        """GET /api/compensation-plans returns a list of plans"""
        response = requests.get(
            f"{BASE_URL}/api/compensation-plans?trust_id={TEST_TRUST_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"GET /api/compensation-plans returned {len(data)} plans")
    
    def test_create_compensation_plan(self, auth_headers):
        """POST /api/compensation-plans creates a new plan"""
        create_data = {
            "trust_id": TEST_TRUST_ID,
            "trustee_name": "TEST_Trustee",
            "role": "Co-Trustee",
            "annual_amount": 10000.00,
            "annual_approved_amount": 10000.00,
            "fee_type": "fixed",
            "effective_date": "2024-01-01",
            "notes": "Created by pytest"
        }
        response = requests.post(
            f"{BASE_URL}/api/compensation-plans",
            headers=auth_headers,
            json=create_data
        )
        assert response.status_code == 200
        data = response.json()
        assert "plan_id" in data
        assert data["trustee_name"] == create_data["trustee_name"]
        assert data["effective_date"] == create_data["effective_date"]
        print(f"Created compensation plan: {data['plan_id']}")
    
    def test_create_compensation_plan_invalid_trust(self, auth_headers):
        """POST /api/compensation-plans returns 404 for invalid trust"""
        response = requests.post(
            f"{BASE_URL}/api/compensation-plans",
            headers=auth_headers,
            json={
                "trust_id": "invalid_trust_id",
                "trustee_name": "TEST",
                "annual_amount": 1000.00,
                "effective_date": "2024-01-01"
            }
        )
        assert response.status_code == 404
    
    def test_get_compensation_payments_requires_auth(self):
        """GET /api/compensation-payments requires authentication"""
        response = requests.get(f"{BASE_URL}/api/compensation-payments?trust_id={TEST_TRUST_ID}")
        assert response.status_code == 401
    
    def test_get_compensation_payments_returns_list(self, auth_headers):
        """GET /api/compensation-payments returns a list of payments"""
        response = requests.get(
            f"{BASE_URL}/api/compensation-payments?trust_id={TEST_TRUST_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"GET /api/compensation-payments returned {len(data)} payments")
    
    def test_create_compensation_payment(self, auth_headers):
        """POST /api/compensation-payments creates a new payment"""
        create_data = {
            "trust_id": TEST_TRUST_ID,
            "amount": 500.00,
            "date": "2024-06-01",
            "classification_text": "TEST_Quarterly payment"
        }
        response = requests.post(
            f"{BASE_URL}/api/compensation-payments",
            headers=auth_headers,
            json=create_data
        )
        assert response.status_code == 200
        data = response.json()
        assert "payment_id" in data
        assert data["amount"] == create_data["amount"]
        assert data["date"] == create_data["date"]
        assert "exceeds_plan_flag" in data
        print(f"Created compensation payment: {data['payment_id']}, exceeds_plan: {data['exceeds_plan_flag']}")
        
        # Clean up
        payment_id = data["payment_id"]
        requests.delete(f"{BASE_URL}/api/compensation-payments/{payment_id}", headers=auth_headers)
    
    def test_get_compensation_ytd(self, auth_headers):
        """GET /api/compensation-ytd returns YTD totals"""
        response = requests.get(
            f"{BASE_URL}/api/compensation-ytd?trust_id={TEST_TRUST_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "ytd_total" in data
        assert "annual_approved" in data
        assert "exceeds_plan" in data
        assert "remaining" in data
        print(f"YTD compensation: ${data['ytd_total']}, approved: ${data['annual_approved']}, remaining: ${data['remaining']}")
    
    def test_delete_compensation_payment(self, auth_headers):
        """DELETE /api/compensation-payments/{id} removes payment"""
        # Create payment first
        create_response = requests.post(
            f"{BASE_URL}/api/compensation-payments",
            headers=auth_headers,
            json={
                "trust_id": TEST_TRUST_ID,
                "amount": 100.00,
                "date": "2024-06-15",
                "classification_text": "TEST_To be deleted"
            }
        )
        payment_id = create_response.json()["payment_id"]
        
        # Delete payment
        delete_response = requests.delete(
            f"{BASE_URL}/api/compensation-payments/{payment_id}",
            headers=auth_headers
        )
        assert delete_response.status_code == 200
        assert delete_response.json()["message"] == "Payment deleted"
        print(f"Deleted compensation payment: {payment_id}")
    
    def test_delete_compensation_payment_not_found(self, auth_headers):
        """DELETE /api/compensation-payments/{id} returns 404 for invalid ID"""
        response = requests.delete(
            f"{BASE_URL}/api/compensation-payments/invalid_payment_id",
            headers=auth_headers
        )
        assert response.status_code == 404


# ==================== SUBSCRIPTION ROUTER TESTS ====================

class TestSubscriptionRouter:
    """Test Subscription endpoints migrated to routers/subscriptions.py"""
    
    def test_get_subscription_requires_auth(self):
        """GET /api/subscription requires authentication"""
        response = requests.get(f"{BASE_URL}/api/subscription")
        assert response.status_code == 401
    
    def test_get_subscription_returns_details(self, auth_headers):
        """GET /api/subscription returns subscription details"""
        response = requests.get(
            f"{BASE_URL}/api/subscription",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "subscription_id" in data
        assert "user_id" in data
        assert "plan_type" in data
        assert "status" in data
        assert "is_active" in data
        print(f"Subscription: plan={data['plan_type']}, status={data['status']}, active={data['is_active']}")
    
    def test_get_subscription_state(self, auth_headers):
        """GET /api/subscription/state returns normalized state"""
        response = requests.get(
            f"{BASE_URL}/api/subscription/state",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        # Verify all expected fields are present
        expected_fields = [
            "user_id", "plan_type", "status", "is_trial", 
            "is_active", "is_read_only"
        ]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
        print(f"Subscription state: is_trial={data['is_trial']}, is_active={data['is_active']}, is_read_only={data['is_read_only']}")
    
    def test_get_subscription_features(self, auth_headers):
        """GET /api/subscription/features returns feature flags"""
        response = requests.get(
            f"{BASE_URL}/api/subscription/features",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "plan_type" in data
        assert "is_active" in data
        assert "is_trial" in data
        assert "features" in data
        
        features = data["features"]
        # Check core features exist
        assert "minutes_basic" in features
        assert "distributions_basic" in features
        assert "governance_basic" in features
        assert "single_trust" in features
        # Check premium features exist
        assert "csv_export" in features
        assert "pdf_no_watermark" in features
        print(f"Features: plan={data['plan_type']}, {len(features)} feature flags returned")
    
    def test_create_checkout_requires_auth(self):
        """POST /api/subscription/create-checkout requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/subscription/create-checkout",
            json={
                "plan_type": "monthly",
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel"
            }
        )
        assert response.status_code == 401
    
    def test_create_checkout_invalid_plan_type(self, auth_headers):
        """POST /api/subscription/create-checkout rejects invalid plan type"""
        response = requests.post(
            f"{BASE_URL}/api/subscription/create-checkout",
            headers=auth_headers,
            json={
                "plan_type": "invalid_plan",
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel"
            }
        )
        assert response.status_code == 400
        assert "Invalid plan type" in response.json().get("detail", "")
    
    def test_create_portal_requires_auth(self):
        """POST /api/subscription/create-portal requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/subscription/create-portal",
            json={"return_url": "https://example.com/return"}
        )
        assert response.status_code == 401


# ==================== CROSS-ROUTER INTEGRATION TESTS ====================

class TestRouterIntegration:
    """Integration tests across all migrated routers"""
    
    def test_all_routers_respond(self, auth_headers):
        """Verify all router endpoints are accessible"""
        # Schedule A
        schedule_a_response = requests.get(
            f"{BASE_URL}/api/schedule-a?trust_id={TEST_TRUST_ID}",
            headers=auth_headers
        )
        assert schedule_a_response.status_code == 200
        
        # Compensation
        comp_plans_response = requests.get(
            f"{BASE_URL}/api/compensation-plans?trust_id={TEST_TRUST_ID}",
            headers=auth_headers
        )
        assert comp_plans_response.status_code == 200
        
        comp_payments_response = requests.get(
            f"{BASE_URL}/api/compensation-payments?trust_id={TEST_TRUST_ID}",
            headers=auth_headers
        )
        assert comp_payments_response.status_code == 200
        
        comp_ytd_response = requests.get(
            f"{BASE_URL}/api/compensation-ytd?trust_id={TEST_TRUST_ID}",
            headers=auth_headers
        )
        assert comp_ytd_response.status_code == 200
        
        # Subscription
        sub_response = requests.get(
            f"{BASE_URL}/api/subscription",
            headers=auth_headers
        )
        assert sub_response.status_code == 200
        
        sub_state_response = requests.get(
            f"{BASE_URL}/api/subscription/state",
            headers=auth_headers
        )
        assert sub_state_response.status_code == 200
        
        sub_features_response = requests.get(
            f"{BASE_URL}/api/subscription/features",
            headers=auth_headers
        )
        assert sub_features_response.status_code == 200
        
        print("All router endpoints responding correctly")
    
    def test_schedule_a_summary_matches_list(self, auth_headers):
        """Verify Schedule A summary counts match list"""
        # Get list
        list_response = requests.get(
            f"{BASE_URL}/api/schedule-a?trust_id={TEST_TRUST_ID}&status=all",
            headers=auth_headers
        )
        items = list_response.json()
        
        # Get summary
        summary_response = requests.get(
            f"{BASE_URL}/api/schedule-a/summary/{TEST_TRUST_ID}",
            headers=auth_headers
        )
        summary = summary_response.json()
        
        assert summary["total_items"] == len(items), \
            f"Summary total_items ({summary['total_items']}) != list length ({len(items)})"
        print(f"Schedule A summary matches list: {len(items)} items")
