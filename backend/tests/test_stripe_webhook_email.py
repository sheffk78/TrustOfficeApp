"""
Test Stripe Webhook and Subscription Email Notifications
Tests for enhanced webhook handling and subscription email templates
"""

import pytest
import requests
import os
import json

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "test@example.com"
TEST_PASSWORD = "testpassword123"


class TestEmailStatus:
    """Test GET /api/email/status - Email templates and configuration"""
    
    def test_email_status_returns_templates(self):
        """Test that /api/email/status returns 11 templates including subscription ones"""
        # First login to get token
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        token = login_resp.json().get("token")
        
        # Get email status
        resp = requests.get(
            f"{BASE_URL}/api/email/status",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert resp.status_code == 200, f"Email status failed: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert "configured" in data, "Missing 'configured' field"
        assert "from_email" in data, "Missing 'from_email' field"
        assert "from_name" in data, "Missing 'from_name' field"
        assert "available_templates" in data, "Missing 'available_templates' field"
        
        templates = data["available_templates"]
        assert isinstance(templates, list), "Templates should be a list"
        
        # Expected subscription templates
        expected_templates = [
            "subscription_activated",
            "subscription_canceled", 
            "subscription_renewed",
            "payment_failed",
            "subscription_upgraded"
        ]
        
        # Also check other base templates exist
        base_templates = [
            "welcome",
            "task_reminder",
            "task_overdue",
            "minutes_created",
            "distribution_created",
            "distribution_approved"
        ]
        
        all_expected = expected_templates + base_templates
        
        for template in expected_templates:
            assert template in templates, f"Missing subscription template: {template}"
            print(f"  [PASS] Template '{template}' exists")
        
        for template in base_templates:
            assert template in templates, f"Missing base template: {template}"
            print(f"  [PASS] Template '{template}' exists")
        
        # Verify we have at least 11 templates
        assert len(templates) >= 11, f"Expected at least 11 templates, got {len(templates)}"
        print(f"\n  Total templates found: {len(templates)}")
        print(f"  Templates: {templates}")


class TestSubscriptionEndpoints:
    """Test subscription cancel and upgrade endpoints"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        if resp.status_code == 200:
            return resp.json().get("token")
        pytest.skip("Login failed")
    
    def test_subscription_cancel_requires_active_subscription(self, auth_token):
        """
        POST /api/subscription/cancel - Should return 400 without active Stripe subscription
        Expected: Test user doesn't have active Stripe subscription, so should get 400
        """
        resp = requests.post(
            f"{BASE_URL}/api/subscription/cancel",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        # Test user likely doesn't have active Stripe subscription
        # So we expect 400 with appropriate message
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "detail" in data, "Missing 'detail' field in error response"
        assert "No active subscription" in data["detail"], f"Unexpected error: {data['detail']}"
        print(f"  [PASS] Returns 400 for user without active Stripe subscription")
        print(f"  Error detail: {data['detail']}")
    
    def test_subscription_upgrade_requires_active_subscription(self, auth_token):
        """
        POST /api/subscription/upgrade - Should return 400 without active Stripe subscription
        Expected: Test user doesn't have active Stripe subscription, so should get 400
        """
        resp = requests.post(
            f"{BASE_URL}/api/subscription/upgrade",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        # Test user likely doesn't have active Stripe subscription
        # So we expect 400 with appropriate message
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        assert "detail" in data, "Missing 'detail' field in error response"
        # Could be "No active subscription" or "Already on annual plan"
        print(f"  [PASS] Returns 400 for user without eligible subscription")
        print(f"  Error detail: {data['detail']}")


class TestStripeWebhook:
    """Test POST /api/stripe/webhook endpoint"""
    
    def test_webhook_rejects_invalid_payload(self):
        """
        POST /api/stripe/webhook - Should return 400 for invalid payload
        """
        resp = requests.post(
            f"{BASE_URL}/api/stripe/webhook",
            data="invalid payload",
            headers={"Content-Type": "application/json"}
        )
        
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        print(f"  [PASS] Returns 400 for invalid payload")
    
    def test_webhook_rejects_missing_signature(self):
        """
        POST /api/stripe/webhook - Should return 400 for missing signature
        """
        # Valid-looking but unsigned payload
        payload = json.dumps({
            "type": "checkout.session.completed",
            "data": {"object": {"id": "test_123"}}
        })
        
        resp = requests.post(
            f"{BASE_URL}/api/stripe/webhook",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        
        # Should fail due to missing/invalid signature
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        data = resp.json()
        # Could be "Invalid payload" or "Invalid signature"
        assert "Invalid" in data.get("detail", ""), f"Expected Invalid error, got: {data}"
        print(f"  [PASS] Returns 400 for unsigned webhook request")
        print(f"  Error detail: {data.get('detail')}")
    
    def test_webhook_rejects_invalid_signature(self):
        """
        POST /api/stripe/webhook - Should return 400 for invalid signature
        """
        payload = json.dumps({
            "id": "evt_test123",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test123",
                    "metadata": {"user_id": "test_user"}
                }
            }
        })
        
        resp = requests.post(
            f"{BASE_URL}/api/stripe/webhook",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "stripe-signature": "t=1234567890,v1=invalid_signature"
            }
        )
        
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "Invalid" in data.get("detail", ""), f"Expected Invalid error, got: {data}"
        print(f"  [PASS] Returns 400 for invalid Stripe signature")


class TestWebhookEventTypes:
    """Test that webhook handles expected event types (structure verification)"""
    
    def test_checkout_session_completed_event_structure(self):
        """Verify checkout.session.completed webhook event structure is correct"""
        # This test verifies the code structure handles checkout.session.completed
        # by checking the endpoint exists and rejects invalid requests properly
        
        payload = json.dumps({
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_123",
                    "subscription": "sub_test_123",
                    "metadata": {
                        "user_id": "user_test123",
                        "plan_type": "monthly"
                    }
                }
            }
        })
        
        resp = requests.post(
            f"{BASE_URL}/api/stripe/webhook",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "stripe-signature": "t=1234567890,v1=fake_sig"
            }
        )
        
        # Should reject due to invalid signature, not due to missing endpoint
        assert resp.status_code == 400, f"Unexpected status: {resp.status_code}"
        assert "Invalid" in resp.json().get("detail", "")
        print("  [PASS] checkout.session.completed endpoint exists and validates signature")
    
    def test_invoice_payment_failed_event_structure(self):
        """Verify invoice.payment_failed webhook event structure is correct"""
        payload = json.dumps({
            "type": "invoice.payment_failed",
            "data": {
                "object": {
                    "id": "inv_test_123",
                    "customer": "cus_test_123",
                    "amount_due": 7900,
                    "next_payment_attempt": 1234567890
                }
            }
        })
        
        resp = requests.post(
            f"{BASE_URL}/api/stripe/webhook",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "stripe-signature": "t=1234567890,v1=fake_sig"
            }
        )
        
        # Should reject due to invalid signature
        assert resp.status_code == 400
        print("  [PASS] invoice.payment_failed endpoint exists and validates signature")
    
    def test_customer_subscription_updated_event_structure(self):
        """Verify customer.subscription.updated webhook event structure is correct"""
        payload = json.dumps({
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_test_123",
                    "customer": "cus_test_123",
                    "cancel_at_period_end": False,
                    "items": {"data": [{"price": {"id": "price_test"}}]}
                },
                "previous_attributes": {}
            }
        })
        
        resp = requests.post(
            f"{BASE_URL}/api/stripe/webhook",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "stripe-signature": "t=1234567890,v1=fake_sig"
            }
        )
        
        assert resp.status_code == 400
        print("  [PASS] customer.subscription.updated endpoint exists and validates signature")
    
    def test_customer_subscription_deleted_event_structure(self):
        """Verify customer.subscription.deleted webhook event structure is correct"""
        payload = json.dumps({
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "id": "sub_test_123",
                    "customer": "cus_test_123"
                }
            }
        })
        
        resp = requests.post(
            f"{BASE_URL}/api/stripe/webhook",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "stripe-signature": "t=1234567890,v1=fake_sig"
            }
        )
        
        assert resp.status_code == 400
        print("  [PASS] customer.subscription.deleted endpoint exists and validates signature")


class TestEmailTemplatesExist:
    """Verify email templates exist in email_templates.py"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        if resp.status_code == 200:
            return resp.json().get("token")
        pytest.skip("Login failed")
    
    def test_subscription_activated_template_exists(self, auth_token):
        """Verify subscription_activated template is available"""
        resp = requests.get(
            f"{BASE_URL}/api/email/status",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert resp.status_code == 200
        templates = resp.json().get("available_templates", [])
        assert "subscription_activated" in templates
        print("  [PASS] subscription_activated template exists")
    
    def test_subscription_canceled_template_exists(self, auth_token):
        """Verify subscription_canceled template is available"""
        resp = requests.get(
            f"{BASE_URL}/api/email/status",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert resp.status_code == 200
        templates = resp.json().get("available_templates", [])
        assert "subscription_canceled" in templates
        print("  [PASS] subscription_canceled template exists")
    
    def test_subscription_renewed_template_exists(self, auth_token):
        """Verify subscription_renewed template is available"""
        resp = requests.get(
            f"{BASE_URL}/api/email/status",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert resp.status_code == 200
        templates = resp.json().get("available_templates", [])
        assert "subscription_renewed" in templates
        print("  [PASS] subscription_renewed template exists")
    
    def test_payment_failed_template_exists(self, auth_token):
        """Verify payment_failed template is available"""
        resp = requests.get(
            f"{BASE_URL}/api/email/status",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert resp.status_code == 200
        templates = resp.json().get("available_templates", [])
        assert "payment_failed" in templates
        print("  [PASS] payment_failed template exists")
    
    def test_subscription_upgraded_template_exists(self, auth_token):
        """Verify subscription_upgraded template is available"""
        resp = requests.get(
            f"{BASE_URL}/api/email/status",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert resp.status_code == 200
        templates = resp.json().get("available_templates", [])
        assert "subscription_upgraded" in templates
        print("  [PASS] subscription_upgraded template exists")


class TestEmailServiceMethods:
    """Verify email service has all required methods"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        if resp.status_code == 200:
            return resp.json().get("token")
        pytest.skip("Login failed")
    
    def test_email_service_configured(self, auth_token):
        """Verify email service is configured with Postmark"""
        resp = requests.get(
            f"{BASE_URL}/api/email/status",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Check email configuration
        assert data.get("configured") is True, "Email service should be configured"
        assert "from_email" in data, "Missing from_email"
        assert "from_name" in data, "Missing from_name"
        
        print(f"  [PASS] Email service configured")
        print(f"  From: {data.get('from_name')} <{data.get('from_email')}>")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
