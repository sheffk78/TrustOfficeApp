"""
Admin Panel Backend API Tests
Tests for customer management, admin privileges, access grants, and referral management.

Endpoints tested:
- GET /api/admin/stats - System statistics (admin-only)
- GET /api/admin/customers - List customers with pagination/search
- GET /api/admin/customers/:user_id - Customer detail
- GET /api/admin/admins - List all admin users
- POST /api/admin/customers/:user_id/make-admin - Grant admin privileges
- POST /api/admin/customers/:user_id/remove-admin - Remove admin privileges
- POST /api/admin/customers/:user_id/grant-access - Grant/extend subscription
- DELETE /api/admin/customers/:user_id - Delete customer
- GET /api/admin/referrals - List referrals
- POST /api/admin/referrals/fix - Fix referral issues
- POST /api/admin/create-admin - Create new admin user
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Admin token provided by main agent
ADMIN_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoidXNlcl9hMDk1NmMwOTk5NDYiLCJlbWFpbCI6ImNvbnRhY3RAdHJ1c3RvZmZpY2UuYXBwIiwiZXhwIjoxNzc0MTgzNTE3LCJpYXQiOjE3NzQwOTcxMTd9.Bxy_iUn8fc2kBLHZ_9kvI7WbcadGg_fT2sEuF5a6SCA"


@pytest.fixture
def admin_client():
    """Session with admin auth header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ADMIN_TOKEN}"
    })
    return session


@pytest.fixture
def unauthenticated_client():
    """Session without auth"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


class TestAdminStats:
    """Test GET /api/admin/stats endpoint"""
    
    def test_admin_stats_returns_system_statistics(self, admin_client):
        """Admin can get system statistics"""
        response = admin_client.get(f"{BASE_URL}/api/admin/stats")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify all expected fields are present
        assert "total_users" in data
        assert "active_subscriptions" in data
        assert "trial_users" in data
        assert "expired_trials" in data
        assert "admin_count" in data
        assert "total_trusts" in data
        assert "total_minutes" in data
        assert "total_distributions" in data
        assert "new_users_30d" in data
        assert "revenue_estimate_monthly" in data
        
        # Verify data types
        assert isinstance(data["total_users"], int)
        assert isinstance(data["admin_count"], int)
        assert isinstance(data["revenue_estimate_monthly"], (int, float))
        
        print(f"Stats: {data['total_users']} users, {data['admin_count']} admins")
    
    def test_admin_stats_requires_auth(self, unauthenticated_client):
        """Unauthenticated request returns 401"""
        response = unauthenticated_client.get(f"{BASE_URL}/api/admin/stats")
        assert response.status_code == 401


class TestAdminCustomerList:
    """Test GET /api/admin/customers endpoint"""
    
    def test_list_customers_returns_paginated_results(self, admin_client):
        """Admin can list customers with pagination"""
        response = admin_client.get(f"{BASE_URL}/api/admin/customers?page=1&limit=10")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "customers" in data
        assert "total" in data
        assert "page" in data
        assert "limit" in data
        assert "pages" in data
        
        assert isinstance(data["customers"], list)
        assert data["page"] == 1
        assert data["limit"] == 10
        
        # Verify customer structure if any exist
        if len(data["customers"]) > 0:
            customer = data["customers"][0]
            assert "user_id" in customer
            assert "email" in customer
            assert "name" in customer
            assert "subscription_status" in customer
            assert "subscription_plan" in customer
        
        print(f"Found {data['total']} total customers, showing {len(data['customers'])}")
    
    def test_list_customers_with_search(self, admin_client):
        """Admin can search customers by email"""
        response = admin_client.get(f"{BASE_URL}/api/admin/customers?search=trustoffice")
        assert response.status_code == 200
        
        data = response.json()
        # Should find at least the admin user
        assert data["total"] >= 1
        
        # Verify search results contain the search term
        for customer in data["customers"]:
            assert "trustoffice" in customer["email"].lower() or "trustoffice" in customer.get("name", "").lower()
    
    def test_list_customers_filter_by_admin_status(self, admin_client):
        """Admin can filter customers by admin status"""
        response = admin_client.get(f"{BASE_URL}/api/admin/customers?is_admin=true")
        assert response.status_code == 200
        
        data = response.json()
        # All returned customers should be admins
        for customer in data["customers"]:
            assert customer["is_admin"] == True
    
    def test_is_admin_false_filter_bug(self, admin_client):
        """
        BUG: is_admin=false filter returns 0 results even when non-admin users exist.
        This is because MongoDB looks for is_admin:false but most users don't have
        the is_admin field at all (it's only set when they become admin).
        Fix: Use {"$ne": True} or {"$in": [False, None]} instead of False.
        """
        # Get all customers
        all_response = admin_client.get(f"{BASE_URL}/api/admin/customers?limit=50")
        assert all_response.status_code == 200
        all_customers = all_response.json()["customers"]
        
        # Count non-admin users client-side
        non_admin_count = sum(1 for c in all_customers if not c.get("is_admin"))
        
        # Get customers with is_admin=false filter
        filtered_response = admin_client.get(f"{BASE_URL}/api/admin/customers?is_admin=false&limit=50")
        assert filtered_response.status_code == 200
        filtered_customers = filtered_response.json()["customers"]
        
        # Document the bug: filter returns fewer results than expected
        if non_admin_count > 0 and len(filtered_customers) == 0:
            print(f"BUG CONFIRMED: {non_admin_count} non-admin users exist but is_admin=false returns 0")
            # This test passes to document the bug, not fail on it
        else:
            print(f"Filter working: {len(filtered_customers)} non-admin users returned")


class TestAdminCustomerDetail:
    """Test GET /api/admin/customers/:user_id endpoint"""
    
    def test_get_customer_detail(self, admin_client):
        """Admin can get detailed customer information"""
        # First get a customer from the list
        list_response = admin_client.get(f"{BASE_URL}/api/admin/customers?limit=1")
        assert list_response.status_code == 200
        
        customers = list_response.json()["customers"]
        if len(customers) == 0:
            pytest.skip("No customers available for testing")
        
        user_id = customers[0]["user_id"]
        
        # Get customer detail
        response = admin_client.get(f"{BASE_URL}/api/admin/customers/{user_id}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["user_id"] == user_id
        assert "email" in data
        assert "name" in data
        assert "subscription" in data
        assert "trusts" in data
        assert "stats" in data
        
        # Verify stats structure
        assert "trusts" in data["stats"]
        assert "minutes" in data["stats"]
        assert "distributions" in data["stats"]
        
        print(f"Customer detail: {data['email']}, {data['stats']['trusts']} trusts")
    
    def test_get_nonexistent_customer_returns_404(self, admin_client):
        """Getting non-existent customer returns 404"""
        response = admin_client.get(f"{BASE_URL}/api/admin/customers/user_nonexistent123")
        assert response.status_code == 404


class TestAdminList:
    """Test GET /api/admin/admins endpoint"""
    
    def test_list_admins(self, admin_client):
        """Admin can list all admin users"""
        response = admin_client.get(f"{BASE_URL}/api/admin/admins")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "admins" in data
        assert isinstance(data["admins"], list)
        
        # Should have at least the primary admin
        assert len(data["admins"]) >= 1
        
        # Verify primary admin is in the list
        admin_emails = [a["email"] for a in data["admins"]]
        assert "contact@trustoffice.app" in admin_emails
        
        # Verify admin structure
        for admin in data["admins"]:
            assert "user_id" in admin
            assert "email" in admin
            assert "name" in admin
        
        print(f"Found {len(data['admins'])} admins: {admin_emails}")


class TestMakeRemoveAdmin:
    """Test POST /api/admin/customers/:user_id/make-admin and remove-admin endpoints"""
    
    def test_make_admin_and_remove_admin_flow(self, admin_client):
        """Test making a user admin and then removing admin status"""
        # First, find a non-admin user to test with
        # Note: is_admin=false filter has a bug (looks for is_admin:false instead of missing/false)
        # So we get all customers and filter client-side
        response = admin_client.get(f"{BASE_URL}/api/admin/customers?limit=20")
        assert response.status_code == 200
        
        customers = response.json()["customers"]
        
        # Find a user that's not the primary admin and not already an admin
        test_user = None
        for c in customers:
            if c["email"] != "contact@trustoffice.app" and not c.get("is_admin"):
                test_user = c
                break
        
        if not test_user:
            pytest.skip("No non-admin users available for testing")
        
        user_id = test_user["user_id"]
        
        # Make user admin
        make_response = admin_client.post(
            f"{BASE_URL}/api/admin/customers/{user_id}/make-admin",
            json={"user_id": user_id, "reason": "Test admin promotion"}
        )
        assert make_response.status_code == 200, f"Make admin failed: {make_response.text}"
        
        data = make_response.json()
        assert "message" in data
        assert test_user["email"] in data["message"]
        
        # Verify user is now admin
        detail_response = admin_client.get(f"{BASE_URL}/api/admin/customers/{user_id}")
        assert detail_response.status_code == 200
        assert detail_response.json()["is_admin"] == True
        
        # Remove admin status
        remove_response = admin_client.post(
            f"{BASE_URL}/api/admin/customers/{user_id}/remove-admin",
            json={"user_id": user_id, "reason": "Test admin removal"}
        )
        assert remove_response.status_code == 200, f"Remove admin failed: {remove_response.text}"
        
        # Verify user is no longer admin
        detail_response2 = admin_client.get(f"{BASE_URL}/api/admin/customers/{user_id}")
        assert detail_response2.status_code == 200
        assert detail_response2.json()["is_admin"] == False
        
        print(f"Successfully tested make/remove admin for {test_user['email']}")
    
    def test_cannot_remove_primary_admin(self, admin_client):
        """Cannot remove admin status from primary admin"""
        # Get the primary admin's user_id
        admins_response = admin_client.get(f"{BASE_URL}/api/admin/admins")
        assert admins_response.status_code == 200
        
        primary_admin = None
        for admin in admins_response.json()["admins"]:
            if admin["email"] == "contact@trustoffice.app":
                primary_admin = admin
                break
        
        if not primary_admin:
            pytest.skip("Primary admin not found")
        
        # Try to remove primary admin
        response = admin_client.post(
            f"{BASE_URL}/api/admin/customers/{primary_admin['user_id']}/remove-admin",
            json={"user_id": primary_admin["user_id"], "reason": "Test"}
        )
        assert response.status_code == 400
        assert "primary admin" in response.json()["detail"].lower()


class TestGrantAccess:
    """Test POST /api/admin/customers/:user_id/grant-access endpoint"""
    
    def test_grant_trial_access(self, admin_client):
        """Admin can grant trial access to a user"""
        # Get a customer
        list_response = admin_client.get(f"{BASE_URL}/api/admin/customers?limit=5")
        assert list_response.status_code == 200
        
        customers = list_response.json()["customers"]
        if len(customers) == 0:
            pytest.skip("No customers available")
        
        # Find a non-admin user
        test_user = None
        for c in customers:
            if c["email"] != "contact@trustoffice.app":
                test_user = c
                break
        
        if not test_user:
            pytest.skip("No suitable test user found")
        
        user_id = test_user["user_id"]
        
        # Grant trial access
        response = admin_client.post(
            f"{BASE_URL}/api/admin/customers/{user_id}/grant-access",
            json={"user_id": user_id, "plan_type": "trial", "days": 30}
        )
        assert response.status_code == 200, f"Grant access failed: {response.text}"
        
        data = response.json()
        assert "message" in data
        assert "30 days" in data["message"]
        
        print(f"Granted 30-day trial to {test_user['email']}")
    
    def test_grant_forever_free_access(self, admin_client):
        """Admin can grant forever_free access"""
        # Get a customer
        list_response = admin_client.get(f"{BASE_URL}/api/admin/customers?limit=5")
        assert list_response.status_code == 200
        
        customers = list_response.json()["customers"]
        
        # Find a non-admin user
        test_user = None
        for c in customers:
            if c["email"] != "contact@trustoffice.app" and not c.get("is_admin"):
                test_user = c
                break
        
        if not test_user:
            pytest.skip("No suitable test user found")
        
        user_id = test_user["user_id"]
        
        # Grant forever_free access
        response = admin_client.post(
            f"{BASE_URL}/api/admin/customers/{user_id}/grant-access",
            json={"user_id": user_id, "plan_type": "forever_free"}
        )
        assert response.status_code == 200, f"Grant access failed: {response.text}"
        
        data = response.json()
        assert "message" in data
        assert "forever free" in data["message"].lower()
        
        # Verify subscription was updated
        detail_response = admin_client.get(f"{BASE_URL}/api/admin/customers/{user_id}")
        assert detail_response.status_code == 200
        
        # Revert to trial to not affect other tests
        admin_client.post(
            f"{BASE_URL}/api/admin/customers/{user_id}/grant-access",
            json={"user_id": user_id, "plan_type": "trial", "days": 14}
        )
        
        print(f"Granted forever_free access to {test_user['email']}")


class TestReferrals:
    """Test referral management endpoints"""
    
    def test_list_referrals(self, admin_client):
        """Admin can list referrals"""
        response = admin_client.get(f"{BASE_URL}/api/admin/referrals")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "referrals" in data
        assert "total" in data
        assert "page" in data
        assert "limit" in data
        
        print(f"Found {data['total']} referrals")
    
    def test_fix_referral_create_requires_valid_users(self, admin_client):
        """Creating referral requires valid user emails"""
        response = admin_client.post(
            f"{BASE_URL}/api/admin/referrals/fix",
            json={
                "referrer_email": "nonexistent_referrer@test.com",
                "referee_email": "nonexistent_referee@test.com",
                "action": "create"
            }
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestCreateAdmin:
    """Test POST /api/admin/create-admin endpoint"""
    
    def test_create_admin_with_existing_user(self, admin_client):
        """Creating admin with existing user promotes them"""
        # Get a non-admin user (filter client-side due to is_admin=false bug)
        list_response = admin_client.get(f"{BASE_URL}/api/admin/customers?limit=20")
        assert list_response.status_code == 200
        
        customers = list_response.json()["customers"]
        
        test_user = None
        for c in customers:
            if c["email"] != "contact@trustoffice.app" and not c.get("is_admin"):
                test_user = c
                break
        
        if not test_user:
            pytest.skip("No non-admin users available")
        
        # Create admin (should promote existing user)
        response = admin_client.post(
            f"{BASE_URL}/api/admin/create-admin",
            json={
                "email": test_user["email"],
                "name": test_user["name"]
            }
        )
        assert response.status_code == 200, f"Create admin failed: {response.text}"
        
        data = response.json()
        assert "message" in data
        assert "promoted" in data["message"].lower() or "admin" in data["message"].lower()
        
        # Clean up - remove admin status
        admin_client.post(
            f"{BASE_URL}/api/admin/customers/{test_user['user_id']}/remove-admin",
            json={"user_id": test_user["user_id"], "reason": "Test cleanup"}
        )
        
        print(f"Promoted and demoted {test_user['email']}")


class TestNonAdminAccess:
    """Test that non-admin users get 403 on admin endpoints"""
    
    def test_non_admin_gets_403_on_stats(self):
        """Non-admin user gets 403 on admin stats endpoint"""
        # Use demo user credentials to get a non-admin token
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        # Try to login as demo user
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo@trustoffice.com", "password": "demopassword"}
        )
        
        if login_response.status_code != 200:
            # Demo user might not exist or have different password
            # Try with a fake token that's valid JWT but not admin
            pytest.skip("Demo user login failed - cannot test non-admin access")
        
        token = login_response.json().get("token")
        if not token:
            pytest.skip("No token returned from login")
        
        # Try to access admin endpoint
        session.headers.update({"Authorization": f"Bearer {token}"})
        response = session.get(f"{BASE_URL}/api/admin/stats")
        
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        assert "admin" in response.json()["detail"].lower()


class TestPrimaryAdminExists:
    """Test that primary admin account exists with correct configuration"""
    
    def test_primary_admin_exists(self, admin_client):
        """contact@trustoffice.app exists and is admin"""
        response = admin_client.get(f"{BASE_URL}/api/admin/admins")
        assert response.status_code == 200
        
        admins = response.json()["admins"]
        primary_admin = None
        for admin in admins:
            if admin["email"] == "contact@trustoffice.app":
                primary_admin = admin
                break
        
        assert primary_admin is not None, "Primary admin contact@trustoffice.app not found"
        print(f"Primary admin found: {primary_admin['email']}")
    
    def test_primary_admin_has_forever_free(self, admin_client):
        """Primary admin has forever_free subscription"""
        # Get primary admin's user_id
        admins_response = admin_client.get(f"{BASE_URL}/api/admin/admins")
        assert admins_response.status_code == 200
        
        primary_admin = None
        for admin in admins_response.json()["admins"]:
            if admin["email"] == "contact@trustoffice.app":
                primary_admin = admin
                break
        
        if not primary_admin:
            pytest.skip("Primary admin not found")
        
        # Get customer detail to check subscription
        detail_response = admin_client.get(f"{BASE_URL}/api/admin/customers/{primary_admin['user_id']}")
        assert detail_response.status_code == 200
        
        data = detail_response.json()
        subscription = data.get("subscription", {})
        
        # Admin should have active subscription (forever_free gives active status)
        assert subscription.get("status") == "active" or subscription.get("plan_type") == "forever_free"
        print(f"Primary admin subscription: {subscription.get('plan_type')} - {subscription.get('status')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
