# Test auth router - migrated auth endpoints from server.py
# Tests: registration, login, me, profile update, password reset flow, logout
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuthRouterEndpoints:
    """Test migrated auth router endpoints"""
    
    @pytest.fixture(scope="class")
    def test_user_email(self):
        """Generate unique email for this test run"""
        return f"TEST_auth_router_{uuid.uuid4().hex[:8]}@example.com"
    
    @pytest.fixture(scope="class")
    def test_user_password(self):
        return "testpassword123"
    
    @pytest.fixture(scope="class")
    def registered_user(self, test_user_email, test_user_password):
        """Register a test user and return their token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": test_user_email,
                "password": test_user_password,
                "name": "Test Auth Router User"
            }
        )
        if response.status_code == 200:
            # Login to get token
            login_resp = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={
                    "email": test_user_email,
                    "password": test_user_password
                }
            )
            if login_resp.status_code == 200:
                return login_resp.json()
        return None
    
    # ==================== REGISTRATION TESTS ====================
    
    def test_register_new_user(self):
        """Test POST /api/auth/register with new user"""
        unique_email = f"TEST_register_{uuid.uuid4().hex[:8]}@example.com"
        response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": unique_email,
                "password": "testpassword123",
                "name": "Test Registration User"
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "user_id" in data
        assert data["email"] == unique_email
        assert data["name"] == "Test Registration User"
        assert "created_at" in data
        print(f"PASS: User registration works - user_id: {data['user_id']}")
    
    def test_register_duplicate_email_fails(self, test_user_email, test_user_password, registered_user):
        """Test that registering with duplicate email fails"""
        response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": test_user_email,
                "password": "anotherpassword",
                "name": "Duplicate User"
            }
        )
        
        assert response.status_code == 400, f"Expected 400 for duplicate email, got {response.status_code}"
        data = response.json()
        assert "already registered" in data.get("detail", "").lower()
        print("PASS: Duplicate email registration correctly rejected")
    
    def test_register_invalid_email_format(self):
        """Test that invalid email format is rejected"""
        response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": "not-an-email",
                "password": "testpassword123",
                "name": "Invalid Email User"
            }
        )
        
        # Should get 422 validation error for invalid email format
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print("PASS: Invalid email format correctly rejected with 422")
    
    # ==================== LOGIN TESTS ====================
    
    def test_login_with_valid_credentials(self, test_user_email, test_user_password, registered_user):
        """Test POST /api/auth/login with valid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": test_user_email,
                "password": test_user_password
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "token" in data
        assert isinstance(data["token"], str)
        assert len(data["token"]) > 0
        
        assert "user" in data
        assert data["user"]["email"] == test_user_email
        assert "user_id" in data["user"]
        print(f"PASS: Login works - user_id: {data['user']['user_id']}")
    
    def test_login_with_wrong_password(self, test_user_email, registered_user):
        """Test login fails with wrong password"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": test_user_email,
                "password": "wrongpassword"
            }
        )
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        data = response.json()
        assert "invalid credentials" in data.get("detail", "").lower()
        print("PASS: Wrong password correctly rejected with 401")
    
    def test_login_with_nonexistent_user(self):
        """Test login fails for non-existent user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": f"nonexistent_{uuid.uuid4().hex[:8]}@example.com",
                "password": "anypassword"
            }
        )
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Non-existent user login correctly rejected with 401")
    
    # ==================== ME ENDPOINT TESTS ====================
    
    def test_get_me_with_valid_token(self, registered_user):
        """Test GET /api/auth/me with valid token"""
        assert registered_user is not None, "User registration failed"
        
        token = registered_user["token"]
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "user_id" in data
        assert "email" in data
        assert "name" in data
        assert "created_at" in data
        print(f"PASS: GET /me works - user: {data['email']}")
    
    def test_get_me_without_token(self):
        """Test GET /api/auth/me without token returns 401"""
        response = requests.get(f"{BASE_URL}/api/auth/me")
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: GET /me correctly rejects unauthenticated request")
    
    def test_get_me_with_invalid_token(self):
        """Test GET /api/auth/me with invalid token returns 401"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": "Bearer invalid_token_12345"}
        )
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: GET /me correctly rejects invalid token")
    
    # ==================== PROFILE UPDATE TESTS ====================
    
    def test_update_profile_name(self, registered_user):
        """Test PUT /api/auth/profile updates name"""
        assert registered_user is not None, "User registration failed"
        
        token = registered_user["token"]
        new_name = f"Updated Name {uuid.uuid4().hex[:6]}"
        
        response = requests.put(
            f"{BASE_URL}/api/auth/profile",
            json={"name": new_name},
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "message" in data
        assert "user" in data
        assert data["user"]["name"] == new_name
        print(f"PASS: Profile update works - new name: {new_name}")
    
    def test_update_profile_empty_name_fails(self, registered_user):
        """Test PUT /api/auth/profile rejects empty name"""
        assert registered_user is not None, "User registration failed"
        
        token = registered_user["token"]
        
        response = requests.put(
            f"{BASE_URL}/api/auth/profile",
            json={"name": "   "},  # whitespace only
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("PASS: Empty name profile update correctly rejected")
    
    def test_update_profile_without_token(self):
        """Test PUT /api/auth/profile without token returns 401"""
        response = requests.put(
            f"{BASE_URL}/api/auth/profile",
            json={"name": "New Name"}
        )
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: Profile update correctly rejects unauthenticated request")
    
    # ==================== LOGOUT TESTS ====================
    
    def test_logout_endpoint(self, registered_user):
        """Test POST /api/auth/logout"""
        assert registered_user is not None, "User registration failed"
        
        token = registered_user["token"]
        
        response = requests.post(
            f"{BASE_URL}/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "message" in data
        assert "logged out" in data["message"].lower()
        print("PASS: Logout endpoint works")
    
    def test_logout_without_token(self):
        """Test POST /api/auth/logout without token still returns 200"""
        response = requests.post(f"{BASE_URL}/api/auth/logout")
        
        # Logout should work even without auth (just clears cookies)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Logout without token works (idempotent)")


class TestPasswordResetEndpoints:
    """Test password reset flow endpoints"""
    
    def test_forgot_password_returns_success_for_valid_email(self):
        """Test POST /api/auth/forgot-password returns success message"""
        # First create a user
        unique_email = f"TEST_forgotpw_{uuid.uuid4().hex[:8]}@example.com"
        requests.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": unique_email,
                "password": "testpassword123",
                "name": "Forgot Password Test User"
            }
        )
        
        # Request password reset
        response = requests.post(
            f"{BASE_URL}/api/auth/forgot-password",
            json={"email": unique_email}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "message" in data
        # Message should not reveal whether email exists
        assert "if an account exists" in data["message"].lower()
        print("PASS: Forgot password returns non-revealing success message")
    
    def test_forgot_password_returns_success_for_nonexistent_email(self):
        """Test forgot-password returns same message for non-existent email (security)"""
        response = requests.post(
            f"{BASE_URL}/api/auth/forgot-password",
            json={"email": f"nonexistent_{uuid.uuid4().hex[:8]}@example.com"}
        )
        
        # Should return 200 to prevent email enumeration
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "if an account exists" in data["message"].lower()
        print("PASS: Non-existent email returns same message (security)")
    
    def test_reset_password_with_invalid_token(self):
        """Test POST /api/auth/reset-password with invalid token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/reset-password",
            json={
                "token": "invalid_token_12345",
                "new_password": "newpassword123"
            }
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert "invalid" in data.get("detail", "").lower() or "expired" in data.get("detail", "").lower()
        print("PASS: Invalid reset token correctly rejected")
    
    def test_verify_reset_token_with_invalid_token(self):
        """Test GET /api/auth/verify-reset-token with invalid token"""
        response = requests.get(
            f"{BASE_URL}/api/auth/verify-reset-token?token=invalid_token_12345"
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("PASS: Invalid verify reset token correctly rejected")


class TestDemoUserLogin:
    """Test login with provided demo credentials"""
    
    def test_demo_user_login(self):
        """Test login with demo@trustoffice.com credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "demo@trustoffice.com",
                "password": "demopassword"
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == "demo@trustoffice.com"
        print(f"PASS: Demo user login works - user_id: {data['user']['user_id']}")
        return data
    
    def test_demo_user_me_endpoint(self):
        """Test GET /me with demo user"""
        # First login
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "demo@trustoffice.com",
                "password": "demopassword"
            }
        )
        
        if login_resp.status_code != 200:
            pytest.skip("Demo user login failed")
        
        token = login_resp.json()["token"]
        
        # Then get me
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data["email"] == "demo@trustoffice.com"
        print(f"PASS: Demo user /me works - name: {data['name']}")


class TestRegressionCoreFeatures:
    """Regression tests to verify core features still accessible after auth migration"""
    
    @pytest.fixture
    def demo_token(self):
        """Get demo user token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "demo@trustoffice.com",
                "password": "demopassword"
            }
        )
        if response.status_code == 200:
            return response.json()["token"]
        return None
    
    def test_trusts_endpoint_accessible(self, demo_token):
        """Test GET /api/trusts still works"""
        assert demo_token is not None, "Demo login failed"
        
        response = requests.get(
            f"{BASE_URL}/api/trusts",
            headers={"Authorization": f"Bearer {demo_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Trusts endpoint accessible - {len(data)} trusts found")
    
    def test_entities_endpoint_accessible(self, demo_token):
        """Test GET /api/entities still works"""
        assert demo_token is not None, "Demo login failed"
        
        response = requests.get(
            f"{BASE_URL}/api/entities?trust_id=trust_b753cb8fe07f",
            headers={"Authorization": f"Bearer {demo_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Entities endpoint accessible")
    
    def test_tasks_endpoint_accessible(self, demo_token):
        """Test GET /api/tasks still works"""
        assert demo_token is not None, "Demo login failed"
        
        response = requests.get(
            f"{BASE_URL}/api/tasks?trust_id=trust_b753cb8fe07f",
            headers={"Authorization": f"Bearer {demo_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Tasks endpoint accessible")
    
    def test_minutes_endpoint_accessible(self, demo_token):
        """Test GET /api/minutes still works"""
        assert demo_token is not None, "Demo login failed"
        
        response = requests.get(
            f"{BASE_URL}/api/minutes?trust_id=trust_b753cb8fe07f",
            headers={"Authorization": f"Bearer {demo_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Minutes endpoint accessible")
    
    def test_distributions_endpoint_accessible(self, demo_token):
        """Test GET /api/distributions still works"""
        assert demo_token is not None, "Demo login failed"
        
        response = requests.get(
            f"{BASE_URL}/api/distributions?trust_id=trust_b753cb8fe07f",
            headers={"Authorization": f"Bearer {demo_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: Distributions endpoint accessible")
    
    def test_dashboard_endpoint_accessible(self, demo_token):
        """Test GET /api/dashboard still works"""
        assert demo_token is not None, "Demo login failed"
        
        response = requests.get(
            f"{BASE_URL}/api/dashboard?trust_id=trust_b753cb8fe07f",
            headers={"Authorization": f"Bearer {demo_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "trust_id" in data
        assert "health_score" in data
        print("PASS: Dashboard endpoint accessible")


class TestFeatureGatesStillWork:
    """Verify feature gates still working after auth migration"""
    
    @pytest.fixture
    def demo_token(self):
        """Get demo user token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "demo@trustoffice.com",
                "password": "demopassword"
            }
        )
        if response.status_code == 200:
            return response.json()["token"]
        return None
    
    def test_governance_history_gate(self, demo_token):
        """Test governance history feature gate still works"""
        assert demo_token is not None, "Demo login failed"
        
        response = requests.get(
            f"{BASE_URL}/api/governance/trust_b753cb8fe07f/history",
            headers={"Authorization": f"Bearer {demo_token}"}
        )
        
        # Demo user is trial - should get 402
        assert response.status_code == 402, f"Expected 402 for trial user, got {response.status_code}"
        print("PASS: Governance history feature gate still works")
    
    def test_trust_units_gate(self, demo_token):
        """Test trust units feature gate still works"""
        assert demo_token is not None, "Demo login failed"
        
        response = requests.get(
            f"{BASE_URL}/api/trust-units/summary?trust_id=trust_b753cb8fe07f",
            headers={"Authorization": f"Bearer {demo_token}"}
        )
        
        # Demo user is trial - should get 402
        assert response.status_code == 402, f"Expected 402 for trial user, got {response.status_code}"
        print("PASS: Trust units feature gate still works")
    
    def test_beneficiary_dashboard_gate(self, demo_token):
        """Test beneficiary dashboard feature gate still works"""
        assert demo_token is not None, "Demo login failed"
        
        response = requests.get(
            f"{BASE_URL}/api/beneficiaries/dashboard?trust_id=trust_b753cb8fe07f",
            headers={"Authorization": f"Bearer {demo_token}"}
        )
        
        # Demo user is trial - should get 402
        assert response.status_code == 402, f"Expected 402 for trial user, got {response.status_code}"
        print("PASS: Beneficiary dashboard feature gate still works")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
