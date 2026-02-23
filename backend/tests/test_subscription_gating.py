"""
Test subscription gating feature:
- Expired trial users get 402 on protected routes
- Expired users can access auth/* and subscription/* endpoints
- Active trial users can access all pages normally
"""
import pytest
import requests
import os
from datetime import datetime, timedelta, timezone

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')

class TestSubscriptionGating:
    """Test subscription gating middleware behavior"""
    
    # Test credentials
    ACTIVE_USER_EMAIL = "test@example.com"
    ACTIVE_USER_PASSWORD = "testpassword123"
    EXPIRED_USER_EMAIL = "expired@test.com"
    EXPIRED_USER_PASSWORD = "testpass123"
    
    @pytest.fixture
    def active_user_token(self):
        """Get token for active trial user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": self.ACTIVE_USER_EMAIL, "password": self.ACTIVE_USER_PASSWORD}
        )
        assert response.status_code == 200, f"Active user login failed: {response.text}"
        return response.json().get("token")
    
    @pytest.fixture
    def expired_user_token(self):
        """Get token for expired trial user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": self.EXPIRED_USER_EMAIL, "password": self.EXPIRED_USER_PASSWORD}
        )
        assert response.status_code == 200, f"Expired user login failed: {response.text}"
        return response.json().get("token")
    
    # ============== EXPIRED USER TESTS ==============
    
    def test_expired_user_can_login(self):
        """Expired user should be able to login"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": self.EXPIRED_USER_EMAIL, "password": self.EXPIRED_USER_PASSWORD}
        )
        assert response.status_code == 200, f"Login should work: {response.text}"
        data = response.json()
        assert "token" in data
        assert "user" in data
        print(f"✅ Expired user can login successfully")
    
    def test_expired_user_can_access_auth_me(self, expired_user_token):
        """Expired user should access /api/auth/me"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {expired_user_token}"}
        )
        assert response.status_code == 200, f"Auth/me should be accessible: {response.text}"
        print(f"✅ Expired user can access /api/auth/me")
    
    def test_expired_user_can_access_subscription(self, expired_user_token):
        """Expired user should access /api/subscription endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/subscription",
            headers={"Authorization": f"Bearer {expired_user_token}"}
        )
        assert response.status_code == 200, f"Subscription should be accessible: {response.text}"
        data = response.json()
        # Verify it shows expired state
        assert data.get("is_active") == False, "Should show inactive subscription"
        print(f"✅ Expired user can access /api/subscription (shows inactive)")
        print(f"   Subscription data: status={data.get('status')}, is_active={data.get('is_active')}")
    
    def test_expired_user_can_access_subscription_create_checkout(self, expired_user_token):
        """Expired user should access /api/subscription/create-checkout"""
        response = requests.post(
            f"{BASE_URL}/api/subscription/create-checkout",
            headers={"Authorization": f"Bearer {expired_user_token}"},
            json={
                "plan_type": "monthly",
                "success_url": f"{BASE_URL}/settings/billing?success=true",
                "cancel_url": f"{BASE_URL}/settings/billing?canceled=true"
            }
        )
        # Should return checkout_url (200) or error but NOT 402
        assert response.status_code != 402, f"Should not return 402 for checkout endpoint"
        print(f"✅ Expired user can access /api/subscription/create-checkout (status: {response.status_code})")
    
    def test_expired_user_can_access_categories(self, expired_user_token):
        """Expired user should access /api/categories (exempt route)"""
        response = requests.get(
            f"{BASE_URL}/api/categories",
            headers={"Authorization": f"Bearer {expired_user_token}"}
        )
        assert response.status_code == 200, f"Categories should be accessible: {response.text}"
        print(f"✅ Expired user can access /api/categories")
    
    def test_expired_user_blocked_from_trusts(self, expired_user_token):
        """Expired user should get 402 on /api/trusts"""
        response = requests.get(
            f"{BASE_URL}/api/trusts",
            headers={"Authorization": f"Bearer {expired_user_token}"}
        )
        assert response.status_code == 402, f"Should return 402, got {response.status_code}: {response.text}"
        data = response.json()
        assert "detail" in data
        assert "expired" in data.get("detail", "").lower() or "inactive" in data.get("detail", "").lower()
        print(f"✅ Expired user gets 402 on /api/trusts: {data.get('detail')}")
    
    def test_expired_user_blocked_from_entities(self, expired_user_token):
        """Expired user should get 402 on /api/entities"""
        response = requests.get(
            f"{BASE_URL}/api/entities?trust_id=test",
            headers={"Authorization": f"Bearer {expired_user_token}"}
        )
        assert response.status_code == 402, f"Should return 402, got {response.status_code}"
        print(f"✅ Expired user gets 402 on /api/entities")
    
    def test_expired_user_blocked_from_minutes(self, expired_user_token):
        """Expired user should get 402 on /api/minutes"""
        response = requests.get(
            f"{BASE_URL}/api/minutes",
            headers={"Authorization": f"Bearer {expired_user_token}"}
        )
        assert response.status_code == 402, f"Should return 402, got {response.status_code}"
        print(f"✅ Expired user gets 402 on /api/minutes")
    
    def test_expired_user_blocked_from_distributions(self, expired_user_token):
        """Expired user should get 402 on /api/distributions"""
        response = requests.get(
            f"{BASE_URL}/api/distributions",
            headers={"Authorization": f"Bearer {expired_user_token}"}
        )
        assert response.status_code == 402, f"Should return 402, got {response.status_code}"
        print(f"✅ Expired user gets 402 on /api/distributions")
    
    def test_expired_user_blocked_from_tasks(self, expired_user_token):
        """Expired user should get 402 on /api/tasks"""
        response = requests.get(
            f"{BASE_URL}/api/tasks",
            headers={"Authorization": f"Bearer {expired_user_token}"}
        )
        assert response.status_code == 402, f"Should return 402, got {response.status_code}"
        print(f"✅ Expired user gets 402 on /api/tasks")
    
    def test_expired_user_blocked_from_activity(self, expired_user_token):
        """Expired user should get 402 on /api/activity"""
        response = requests.get(
            f"{BASE_URL}/api/activity",
            headers={"Authorization": f"Bearer {expired_user_token}"}
        )
        assert response.status_code == 402, f"Should return 402, got {response.status_code}"
        print(f"✅ Expired user gets 402 on /api/activity")
    
    # ============== ACTIVE USER TESTS ==============
    
    def test_active_user_can_access_trusts(self, active_user_token):
        """Active trial user should access /api/trusts"""
        response = requests.get(
            f"{BASE_URL}/api/trusts",
            headers={"Authorization": f"Bearer {active_user_token}"}
        )
        assert response.status_code == 200, f"Active user should access trusts: {response.text}"
        print(f"✅ Active user can access /api/trusts")
    
    def test_active_user_can_access_subscription(self, active_user_token):
        """Active trial user should access /api/subscription"""
        response = requests.get(
            f"{BASE_URL}/api/subscription",
            headers={"Authorization": f"Bearer {active_user_token}"}
        )
        assert response.status_code == 200, f"Active user should access subscription: {response.text}"
        data = response.json()
        assert data.get("is_active") == True, "Should show active subscription"
        print(f"✅ Active user can access /api/subscription (is_active: True)")
    
    def test_active_user_can_access_minutes(self, active_user_token):
        """Active trial user should access /api/minutes"""
        response = requests.get(
            f"{BASE_URL}/api/minutes",
            headers={"Authorization": f"Bearer {active_user_token}"}
        )
        assert response.status_code == 200, f"Active user should access minutes: {response.text}"
        print(f"✅ Active user can access /api/minutes")
    
    def test_active_user_can_access_distributions(self, active_user_token):
        """Active trial user should access /api/distributions"""
        response = requests.get(
            f"{BASE_URL}/api/distributions",
            headers={"Authorization": f"Bearer {active_user_token}"}
        )
        assert response.status_code == 200, f"Active user should access distributions: {response.text}"
        print(f"✅ Active user can access /api/distributions")
    
    def test_active_user_can_access_tasks(self, active_user_token):
        """Active trial user should access /api/tasks"""
        response = requests.get(
            f"{BASE_URL}/api/tasks",
            headers={"Authorization": f"Bearer {active_user_token}"}
        )
        assert response.status_code == 200, f"Active user should access tasks: {response.text}"
        print(f"✅ Active user can access /api/tasks")


class TestMiddlewareExemptPaths:
    """Test that exempt paths work correctly"""
    
    EXEMPT_PATHS = [
        "/api/auth/login",
        "/api/auth/register", 
        "/api/auth/logout",
        "/api/auth/session",
        "/api/auth/me",
        "/api/subscription",
        "/api/subscription/create-checkout",
        "/api/subscription/verify-payment",
        "/api/subscription/create-portal",
        "/api/subscription/cancel",
        "/api/subscription/reactivate",
        "/api/subscription/upgrade",
        "/api/categories",
    ]
    
    def test_unauthenticated_access_to_categories(self):
        """Categories should be accessible without auth"""
        response = requests.get(f"{BASE_URL}/api/categories")
        assert response.status_code == 200, f"Categories should be public: {response.text}"
        print(f"✅ /api/categories is publicly accessible")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
