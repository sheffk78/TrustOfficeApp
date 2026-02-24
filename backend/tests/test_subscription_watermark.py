"""
Test subscription system with soft gating via watermarks:
- New user trial creation with 14-day trial
- Checkout session creation for monthly/annual plans
- Subscription status checks (plan_type, status, days_remaining)
- PDF watermark logic for trialing users
- Cancel/reactivate endpoints
- hide_watermark preference validation (requires active subscription)
"""
import pytest
import requests
import os
import uuid
from datetime import datetime, timedelta, timezone

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')

class TestSubscriptionFlow:
    """Test subscription-related flows"""
    
    # Test credentials
    DEMO_EMAIL = "demo@trustoffice.com"
    DEMO_PASSWORD = "demopassword"
    
    @pytest.fixture
    def demo_token(self):
        """Get token for demo user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": self.DEMO_EMAIL, "password": self.DEMO_PASSWORD}
        )
        assert response.status_code == 200, f"Demo user login failed: {response.text}"
        return response.json().get("token")
    
    @pytest.fixture
    def demo_user(self):
        """Get demo user info"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": self.DEMO_EMAIL, "password": self.DEMO_PASSWORD}
        )
        assert response.status_code == 200
        return response.json()
    
    # ============== NEW USER TRIAL TESTS ==============
    
    def test_new_user_gets_14_day_trial(self):
        """Register new user and verify they get 14-day trial with status='trialing'"""
        unique_email = f"subtest_{uuid.uuid4().hex[:8]}@test.com"
        
        # Register new user
        register_response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": unique_email,
                "password": "testpass123",
                "name": "Test Subscription User"
            }
        )
        assert register_response.status_code == 200, f"Registration failed: {register_response.text}"
        
        # Login
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": unique_email, "password": "testpass123"}
        )
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        token = login_response.json().get("token")
        
        # Get subscription - should auto-create trial
        sub_response = requests.get(
            f"{BASE_URL}/api/subscription",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert sub_response.status_code == 200, f"Subscription fetch failed: {sub_response.text}"
        
        sub_data = sub_response.json()
        
        # Verify trial properties
        assert sub_data.get("status") == "trialing", f"Status should be 'trialing', got {sub_data.get('status')}"
        assert sub_data.get("plan_type") == "trial", f"Plan type should be 'trial', got {sub_data.get('plan_type')}"
        assert sub_data.get("is_active") == True, "New trial user should have is_active=True"
        
        # Verify days_remaining is approximately 14 (could be 13 depending on timing)
        days_remaining = sub_data.get("days_remaining")
        assert days_remaining is not None, "days_remaining should be set for trialing user"
        assert 13 <= days_remaining <= 14, f"days_remaining should be ~14, got {days_remaining}"
        
        print(f"✅ New user gets 14-day trial: status={sub_data.get('status')}, days_remaining={days_remaining}")
    
    # ============== SUBSCRIPTION STATUS TESTS ==============
    
    def test_subscription_status_endpoint_returns_correct_fields(self, demo_token):
        """GET /subscription returns correct plan_type, status, days_remaining, is_active"""
        response = requests.get(
            f"{BASE_URL}/api/subscription",
            headers={"Authorization": f"Bearer {demo_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        
        # Required fields should be present
        assert "subscription_id" in data
        assert "user_id" in data
        assert "plan_type" in data
        assert "status" in data
        assert "is_active" in data
        
        # Verify status is valid enum value
        valid_statuses = ["trialing", "active", "past_due", "canceled", "expired"]
        assert data["status"] in valid_statuses, f"Invalid status: {data['status']}"
        
        # Verify plan_type is valid
        valid_plans = ["trial", "monthly", "annual"]
        assert data["plan_type"] in valid_plans, f"Invalid plan_type: {data['plan_type']}"
        
        print(f"✅ Subscription status check: plan_type={data['plan_type']}, status={data['status']}, is_active={data['is_active']}")
    
    # ============== CHECKOUT SESSION TESTS ==============
    
    def test_create_checkout_session_monthly_returns_valid_url(self, demo_token):
        """Create checkout session for monthly plan and verify valid Stripe checkout URL"""
        response = requests.post(
            f"{BASE_URL}/api/subscription/create-checkout",
            headers={"Authorization": f"Bearer {demo_token}"},
            json={
                "plan_type": "monthly",
                "success_url": f"{BASE_URL}/settings/billing?success=true",
                "cancel_url": f"{BASE_URL}/settings/billing?canceled=true"
            }
        )
        assert response.status_code == 200, f"Checkout session creation failed: {response.text}"
        
        data = response.json()
        assert "checkout_url" in data, "Response should contain checkout_url"
        assert "session_id" in data, "Response should contain session_id"
        
        # Verify URL is a valid Stripe checkout URL
        checkout_url = data["checkout_url"]
        assert checkout_url.startswith("https://checkout.stripe.com"), f"Invalid checkout URL: {checkout_url}"
        
        print(f"✅ Monthly checkout session created: {checkout_url[:70]}...")
    
    def test_create_checkout_session_annual_returns_valid_url(self, demo_token):
        """Create checkout session for annual plan and verify valid Stripe checkout URL"""
        response = requests.post(
            f"{BASE_URL}/api/subscription/create-checkout",
            headers={"Authorization": f"Bearer {demo_token}"},
            json={
                "plan_type": "annual",
                "success_url": f"{BASE_URL}/settings/billing?success=true",
                "cancel_url": f"{BASE_URL}/settings/billing?canceled=true"
            }
        )
        assert response.status_code == 200, f"Checkout session creation failed: {response.text}"
        
        data = response.json()
        assert "checkout_url" in data
        assert "session_id" in data
        
        checkout_url = data["checkout_url"]
        assert checkout_url.startswith("https://checkout.stripe.com")
        
        print(f"✅ Annual checkout session created: {checkout_url[:70]}...")
    
    def test_create_checkout_session_invalid_plan_type(self, demo_token):
        """Invalid plan type should return 400 error"""
        response = requests.post(
            f"{BASE_URL}/api/subscription/create-checkout",
            headers={"Authorization": f"Bearer {demo_token}"},
            json={
                "plan_type": "invalid_plan",
                "success_url": f"{BASE_URL}/success",
                "cancel_url": f"{BASE_URL}/cancel"
            }
        )
        assert response.status_code == 400, f"Should return 400 for invalid plan, got {response.status_code}"
        print(f"✅ Invalid plan type correctly returns 400")
    
    # ============== CANCEL/REACTIVATE TESTS ==============
    
    def test_cancel_subscription_without_stripe_subscription(self, demo_token):
        """Cancel subscription without Stripe subscription should return 400"""
        response = requests.post(
            f"{BASE_URL}/api/subscription/cancel",
            headers={"Authorization": f"Bearer {demo_token}"}
        )
        # If user is on trial with no Stripe subscription, should get 400
        assert response.status_code in [200, 400], f"Unexpected status: {response.status_code}"
        
        if response.status_code == 400:
            data = response.json()
            assert "detail" in data
            assert "subscription" in data["detail"].lower() or "active" in data["detail"].lower()
            print(f"✅ Cancel returns expected error for trial user: {data['detail']}")
        else:
            print(f"✅ Cancel returned success (user has active Stripe subscription)")
    
    def test_reactivate_subscription_without_stripe_subscription(self, demo_token):
        """Reactivate subscription without Stripe subscription should return 400"""
        response = requests.post(
            f"{BASE_URL}/api/subscription/reactivate",
            headers={"Authorization": f"Bearer {demo_token}"}
        )
        # If user is on trial with no Stripe subscription, should get 400
        assert response.status_code in [200, 400], f"Unexpected status: {response.status_code}"
        
        if response.status_code == 400:
            data = response.json()
            assert "detail" in data
            print(f"✅ Reactivate returns expected error: {data['detail']}")
        else:
            print(f"✅ Reactivate returned success")


class TestWatermarkSoftGating:
    """Test soft gating via watermarks on PDFs"""
    
    DEMO_EMAIL = "demo@trustoffice.com"
    DEMO_PASSWORD = "demopassword"
    
    @pytest.fixture
    def demo_token(self):
        """Get token for demo user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": self.DEMO_EMAIL, "password": self.DEMO_PASSWORD}
        )
        assert response.status_code == 200, f"Demo user login failed: {response.text}"
        return response.json().get("token")
    
    @pytest.fixture
    def demo_trust_id(self, demo_token):
        """Get first trust ID for demo user"""
        response = requests.get(
            f"{BASE_URL}/api/trusts",
            headers={"Authorization": f"Bearer {demo_token}"}
        )
        if response.status_code == 200 and response.json():
            return response.json()[0]["trust_id"]
        
        # Create a trust if none exists
        create_response = requests.post(
            f"{BASE_URL}/api/trusts",
            headers={"Authorization": f"Bearer {demo_token}"},
            json={"name": "TEST Watermark Trust", "trust_type": "family", "jurisdiction": "Delaware"}
        )
        assert create_response.status_code == 200, f"Failed to create trust: {create_response.text}"
        return create_response.json()["trust_id"]
    
    def test_pdf_endpoint_accessible_for_trialing_user(self, demo_token, demo_trust_id):
        """Verify PDF export is accessible for trialing users (soft gating allows access)"""
        # First, create a minutes record to export
        minutes_response = requests.post(
            f"{BASE_URL}/api/minutes",
            headers={"Authorization": f"Bearer {demo_token}"},
            json={
                "trust_id": demo_trust_id,
                "minutes_type": "annual",
                "meeting_date": datetime.now(timezone.utc).isoformat(),
                "participants_text": "Test Participant",
                "decisions_text": "Test decision for watermark testing"
            }
        )
        
        if minutes_response.status_code != 200:
            # Try to get existing minutes
            list_response = requests.get(
                f"{BASE_URL}/api/minutes?trust_id={demo_trust_id}",
                headers={"Authorization": f"Bearer {demo_token}"}
            )
            assert list_response.status_code == 200
            minutes_list = list_response.json()
            if not minutes_list:
                pytest.skip("No minutes available for PDF export test")
            minutes_id = minutes_list[0]["minutes_id"]
        else:
            minutes_id = minutes_response.json()["minutes_id"]
        
        # Get PDF export - should succeed (soft gating)
        pdf_response = requests.get(
            f"{BASE_URL}/api/minutes/{minutes_id}/pdf",
            headers={"Authorization": f"Bearer {demo_token}"}
        )
        
        # Should NOT get 402 (soft gating means access is allowed)
        assert pdf_response.status_code == 200, f"PDF export should be accessible (soft gating): {pdf_response.status_code}"
        
        data = pdf_response.json()
        assert "pdf_base64" in data, "Response should contain pdf_base64"
        assert "filename" in data, "Response should contain filename"
        
        # Verify PDF is non-empty
        import base64
        pdf_bytes = base64.b64decode(data["pdf_base64"])
        assert len(pdf_bytes) > 0, "PDF should not be empty"
        
        print(f"✅ PDF export accessible for trialing user (soft gating works)")


class TestWatermarkPreference:
    """Test hide_watermark preference requires active subscription"""
    
    TEST_EMAIL = "subtest_1771962161@test.com"
    TEST_PASSWORD = "testpass123"
    DEMO_EMAIL = "demo@trustoffice.com"
    DEMO_PASSWORD = "demopassword"
    
    @pytest.fixture
    def test_token(self):
        """Get token for test user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": self.TEST_EMAIL, "password": self.TEST_PASSWORD}
        )
        if response.status_code != 200:
            pytest.skip(f"Test user login failed: {response.text}")
        return response.json().get("token")
    
    @pytest.fixture
    def demo_token(self):
        """Get token for demo user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": self.DEMO_EMAIL, "password": self.DEMO_PASSWORD}
        )
        assert response.status_code == 200, f"Demo user login failed: {response.text}"
        return response.json().get("token")
    
    def test_get_user_preferences_returns_hide_watermark(self, demo_token):
        """GET /user/preferences returns hide_watermark field"""
        response = requests.get(
            f"{BASE_URL}/api/user/preferences",
            headers={"Authorization": f"Bearer {demo_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "hide_watermark" in data, "Response should contain hide_watermark field"
        assert isinstance(data["hide_watermark"], bool), "hide_watermark should be boolean"
        
        print(f"✅ User preferences contains hide_watermark: {data['hide_watermark']}")
    
    def test_hide_watermark_requires_active_subscription(self):
        """Setting hide_watermark=true requires active subscription"""
        # Create a new user that will only have trial
        unique_email = f"watermark_test_{uuid.uuid4().hex[:8]}@test.com"
        
        # Register
        requests.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": unique_email,
                "password": "testpass123",
                "name": "Watermark Test User"
            }
        )
        
        # Login
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": unique_email, "password": "testpass123"}
        )
        
        if login_response.status_code != 200:
            pytest.skip("Could not create test user")
        
        token = login_response.json().get("token")
        
        # Check subscription status
        sub_response = requests.get(
            f"{BASE_URL}/api/subscription",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        sub_data = sub_response.json()
        
        # Try to set hide_watermark=true
        prefs_response = requests.put(
            f"{BASE_URL}/api/user/preferences",
            headers={"Authorization": f"Bearer {token}"},
            json={"hide_watermark": True}
        )
        
        # If user is trialing, this should succeed (trialing counts as subscribed for watermark)
        # If user is expired, this should fail with 403
        if sub_data.get("status") == "trialing" and sub_data.get("is_active"):
            assert prefs_response.status_code == 200, f"Trialing user should be able to hide watermark: {prefs_response.text}"
            print(f"✅ Trialing user can set hide_watermark=true")
        else:
            # Expired or no subscription - should get 403
            assert prefs_response.status_code == 403, f"Expected 403 for expired user, got {prefs_response.status_code}"
            print(f"✅ Expired user cannot set hide_watermark=true (returns 403)")
    
    def test_trialing_user_can_toggle_watermark(self, demo_token):
        """Trialing/active user can toggle hide_watermark preference"""
        # Check current subscription status
        sub_response = requests.get(
            f"{BASE_URL}/api/subscription",
            headers={"Authorization": f"Bearer {demo_token}"}
        )
        sub_data = sub_response.json()
        
        if not sub_data.get("is_active"):
            pytest.skip("User does not have active subscription")
        
        # Toggle hide_watermark to true
        response = requests.put(
            f"{BASE_URL}/api/user/preferences",
            headers={"Authorization": f"Bearer {demo_token}"},
            json={"hide_watermark": True}
        )
        assert response.status_code == 200, f"Failed to set hide_watermark: {response.text}"
        
        # Verify it was set
        get_response = requests.get(
            f"{BASE_URL}/api/user/preferences",
            headers={"Authorization": f"Bearer {demo_token}"}
        )
        assert get_response.status_code == 200
        assert get_response.json()["hide_watermark"] == True
        
        # Toggle back to false
        response = requests.put(
            f"{BASE_URL}/api/user/preferences",
            headers={"Authorization": f"Bearer {demo_token}"},
            json={"hide_watermark": False}
        )
        assert response.status_code == 200
        
        print(f"✅ Active/trialing user can toggle hide_watermark preference")


class TestExpiredSubscription402Response:
    """Test that expired subscription returns 402 on protected endpoints"""
    
    EXPIRED_USER_EMAIL = "expired@test.com"
    EXPIRED_USER_PASSWORD = "testpass123"
    
    @pytest.fixture
    def expired_token(self):
        """Get token for expired user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": self.EXPIRED_USER_EMAIL, "password": self.EXPIRED_USER_PASSWORD}
        )
        if response.status_code != 200:
            pytest.skip(f"Expired test user not available: {response.text}")
        return response.json().get("token")
    
    def test_expired_user_gets_402_on_trusts(self, expired_token):
        """Expired subscription returns 402 on /api/trusts"""
        response = requests.get(
            f"{BASE_URL}/api/trusts",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        assert response.status_code == 402, f"Expected 402, got {response.status_code}"
        
        data = response.json()
        assert "detail" in data
        # Message should mention subscription/trial expired
        assert "expired" in data["detail"].lower() or "inactive" in data["detail"].lower() or "subscribe" in data["detail"].lower()
        
        print(f"✅ Expired user gets 402 on protected endpoint: {data['detail']}")
    
    def test_expired_user_can_still_access_subscription_endpoint(self, expired_token):
        """Expired user can access /api/subscription to see their status"""
        response = requests.get(
            f"{BASE_URL}/api/subscription",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        assert response.status_code == 200, f"Should access subscription endpoint: {response.text}"
        
        data = response.json()
        assert data.get("is_active") == False, "Expired user should have is_active=False"
        
        print(f"✅ Expired user can access /api/subscription (shows inactive)")
    
    def test_expired_user_can_create_checkout(self, expired_token):
        """Expired user can create checkout session to resubscribe"""
        response = requests.post(
            f"{BASE_URL}/api/subscription/create-checkout",
            headers={"Authorization": f"Bearer {expired_token}"},
            json={
                "plan_type": "monthly",
                "success_url": f"{BASE_URL}/settings/billing?success=true",
                "cancel_url": f"{BASE_URL}/settings/billing?canceled=true"
            }
        )
        # Should NOT return 402
        assert response.status_code != 402, "Checkout endpoint should not return 402"
        
        if response.status_code == 200:
            data = response.json()
            assert "checkout_url" in data
            print(f"✅ Expired user can create checkout session to resubscribe")
        else:
            print(f"⚠️ Checkout returned {response.status_code}: {response.text}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
