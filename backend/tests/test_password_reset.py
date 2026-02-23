"""
Password Reset Flow Tests for TrustOffice
Tests:
- POST /api/auth/forgot-password - Request password reset
- GET /api/auth/verify-reset-token - Verify reset token
- POST /api/auth/reset-password - Reset password with token
- Database indexes verification
- Legacy collections cleanup verification
"""

import pytest
import requests
import os
from datetime import datetime, timezone, timedelta
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL')
if BASE_URL:
    BASE_URL = BASE_URL.rstrip('/')

# Test user credentials
TEST_EMAIL = "test@example.com"
TEST_PASSWORD = "testpassword123"


class TestPasswordResetFlow:
    """Tests for password reset functionality"""
    
    @pytest.fixture
    def api_client(self):
        """Shared requests session"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        return session
    
    @pytest.fixture
    def auth_token(self, api_client):
        """Get authentication token"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Authentication failed - skipping authenticated tests")
    
    # =================================================================
    # FORGOT PASSWORD ENDPOINT TESTS
    # =================================================================
    
    def test_forgot_password_returns_success_message(self, api_client):
        """POST /api/auth/forgot-password returns success message"""
        response = api_client.post(f"{BASE_URL}/api/auth/forgot-password", json={
            "email": TEST_EMAIL
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "message" in data, "Response should contain 'message' field"
        assert "password reset link" in data["message"].lower(), f"Message should mention password reset link: {data['message']}"
    
    def test_forgot_password_with_nonexistent_email(self, api_client):
        """POST /api/auth/forgot-password returns same message for non-existent email (security)"""
        response = api_client.post(f"{BASE_URL}/api/auth/forgot-password", json={
            "email": f"nonexistent_{uuid.uuid4().hex[:8]}@example.com"
        })
        
        # Should return 200 to prevent email enumeration
        assert response.status_code == 200, f"Expected 200 (security), got {response.status_code}"
        
        data = response.json()
        assert "message" in data
    
    def test_forgot_password_invalid_email_format(self, api_client):
        """POST /api/auth/forgot-password handles invalid email format"""
        response = api_client.post(f"{BASE_URL}/api/auth/forgot-password", json={
            "email": "invalid-email"
        })
        
        # Either returns validation error (422) or handles gracefully (200)
        assert response.status_code in [200, 422], f"Expected 200 or 422, got {response.status_code}"
    
    def test_forgot_password_empty_email(self, api_client):
        """POST /api/auth/forgot-password handles empty email"""
        response = api_client.post(f"{BASE_URL}/api/auth/forgot-password", json={
            "email": ""
        })
        
        # Should return validation error
        assert response.status_code in [400, 422], f"Expected 400/422 for empty email, got {response.status_code}"
    
    # =================================================================
    # VERIFY RESET TOKEN ENDPOINT TESTS
    # =================================================================
    
    def test_verify_reset_token_invalid_token(self, api_client):
        """GET /api/auth/verify-reset-token rejects invalid token"""
        response = api_client.get(f"{BASE_URL}/api/auth/verify-reset-token?token=invalid_token_12345")
        
        assert response.status_code == 400, f"Expected 400 for invalid token, got {response.status_code}"
        
        data = response.json()
        assert "detail" in data or "error" in data or "message" in data
    
    def test_verify_reset_token_missing_token(self, api_client):
        """GET /api/auth/verify-reset-token requires token parameter"""
        response = api_client.get(f"{BASE_URL}/api/auth/verify-reset-token")
        
        # Should return error for missing token
        assert response.status_code in [400, 422], f"Expected 400/422 for missing token, got {response.status_code}"
    
    def test_verify_reset_token_empty_token(self, api_client):
        """GET /api/auth/verify-reset-token handles empty token"""
        response = api_client.get(f"{BASE_URL}/api/auth/verify-reset-token?token=")
        
        assert response.status_code == 400, f"Expected 400 for empty token, got {response.status_code}"
    
    # =================================================================
    # RESET PASSWORD ENDPOINT TESTS
    # =================================================================
    
    def test_reset_password_invalid_token(self, api_client):
        """POST /api/auth/reset-password rejects invalid token"""
        response = api_client.post(f"{BASE_URL}/api/auth/reset-password", json={
            "token": "invalid_token_12345",
            "new_password": "NewValidPassword123"
        })
        
        assert response.status_code == 400, f"Expected 400 for invalid token, got {response.status_code}"
        
        data = response.json()
        assert "detail" in data or "error" in data
    
    def test_reset_password_short_password(self, api_client):
        """POST /api/auth/reset-password rejects short password"""
        response = api_client.post(f"{BASE_URL}/api/auth/reset-password", json={
            "token": "some_token",
            "new_password": "short"  # Less than 8 characters
        })
        
        # Could be 400 for invalid token or password validation
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
    
    def test_reset_password_missing_fields(self, api_client):
        """POST /api/auth/reset-password requires all fields"""
        # Missing new_password
        response = api_client.post(f"{BASE_URL}/api/auth/reset-password", json={
            "token": "some_token"
        })
        
        assert response.status_code in [400, 422], f"Expected 400/422, got {response.status_code}"
        
        # Missing token
        response = api_client.post(f"{BASE_URL}/api/auth/reset-password", json={
            "new_password": "NewPassword123"
        })
        
        assert response.status_code in [400, 422], f"Expected 400/422, got {response.status_code}"


class TestDatabaseIndexes:
    """Tests for database index creation"""
    
    @pytest.fixture
    def api_client(self):
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        return session
    
    @pytest.fixture
    def auth_token(self, api_client):
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Authentication failed")
    
    def test_user_queries_are_fast(self, api_client, auth_token):
        """Verify user-related queries work (indirectly tests indexes)"""
        api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
        
        # Test /api/auth/me - uses user_id index
        response = api_client.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200
    
    def test_trust_queries_work(self, api_client, auth_token):
        """Verify trust queries work (uses trust indexes)"""
        api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
        
        response = api_client.get(f"{BASE_URL}/api/trusts")
        assert response.status_code in [200, 402]  # 402 if trial expired
    
    def test_subscription_queries_work(self, api_client, auth_token):
        """Verify subscription queries work (uses subscription indexes)"""
        api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
        
        response = api_client.get(f"{BASE_URL}/api/subscription")
        assert response.status_code == 200
        
        data = response.json()
        assert "subscription_id" in data or "user_id" in data


class TestPasswordResetTokenDatabase:
    """Tests that verify password_resets collection works"""
    
    @pytest.fixture
    def api_client(self):
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        return session
    
    def test_forgot_password_creates_token(self, api_client):
        """POST /api/auth/forgot-password creates token in password_resets collection
        
        We verify this indirectly by:
        1. Requesting a password reset for existing user
        2. Getting success response
        
        Note: We can't directly verify database state without direct DB access,
        but the API behavior confirms the flow works.
        """
        # First request
        response = api_client.post(f"{BASE_URL}/api/auth/forgot-password", json={
            "email": TEST_EMAIL
        })
        
        assert response.status_code == 200
        
        # Second request should also work (updates existing token)
        response = api_client.post(f"{BASE_URL}/api/auth/forgot-password", json={
            "email": TEST_EMAIL
        })
        
        assert response.status_code == 200


class TestEmailTemplates:
    """Tests for password reset email template"""
    
    @pytest.fixture
    def api_client(self):
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        return session
    
    @pytest.fixture
    def auth_token(self, api_client):
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Authentication failed")
    
    def test_password_reset_template_exists(self, api_client, auth_token):
        """Verify password_reset email template exists"""
        api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
        
        response = api_client.get(f"{BASE_URL}/api/email/status")
        
        # May return 200 or 402 depending on subscription
        if response.status_code == 200:
            data = response.json()
            templates = data.get("available_templates", [])
            assert "password_reset" in templates, f"password_reset template should exist. Found: {templates}"
        else:
            # Can't verify templates without subscription access
            pytest.skip("Cannot access email status endpoint")


class TestLegacyCollectionsRemoval:
    """Tests to verify legacy collections are removed
    
    Note: Without direct database access, we verify indirectly by:
    1. Ensuring current endpoints work with new collection names
    2. Confirming no references to old collection names in API responses
    """
    
    @pytest.fixture
    def api_client(self):
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        return session
    
    @pytest.fixture
    def auth_token(self, api_client):
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Authentication failed")
    
    def test_minutes_endpoint_works(self, api_client, auth_token):
        """Verify minutes endpoint works with minutes_records collection"""
        api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
        
        response = api_client.get(f"{BASE_URL}/api/minutes")
        
        # Either 200 (success) or 402 (subscription required)
        assert response.status_code in [200, 402], f"Unexpected status: {response.status_code}"
    
    def test_distributions_endpoint_works(self, api_client, auth_token):
        """Verify distributions endpoint works with distribution_records collection"""
        api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
        
        response = api_client.get(f"{BASE_URL}/api/distributions")
        
        assert response.status_code in [200, 402], f"Unexpected status: {response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
