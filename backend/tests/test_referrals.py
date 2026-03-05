"""
Test Referral System Endpoints
- GET /api/referrals/my-code - Get user's unique referral code
- GET /api/referrals/stats - Get referral statistics
- GET /api/referrals/validate/{code} - Validate referral code (public endpoint)
- POST /api/auth/register with referral_code - Registration with referral tracking
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestReferralEndpoints:
    """Test referral system endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login with demo user and get token"""
        # Login with demo credentials
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@trustoffice.com",
            "password": "demopassword"
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        
        login_data = login_response.json()
        self.token = login_data.get("token")
        self.user = login_data.get("user")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        yield
    
    def test_get_my_referral_code(self):
        """Test GET /api/referrals/my-code returns user's unique referral code and link"""
        response = requests.get(f"{BASE_URL}/api/referrals/my-code", headers=self.headers)
        
        # Status code assertion
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Data assertions
        data = response.json()
        assert "referral_code" in data, "Missing referral_code in response"
        assert "referral_link" in data, "Missing referral_link in response"
        assert "created_at" in data, "Missing created_at in response"
        
        # Validate referral code format (should be alphanumeric)
        assert data["referral_code"].isalnum(), "Referral code should be alphanumeric"
        assert len(data["referral_code"]) == 8, "Referral code should be 8 characters"
        
        # Validate referral link contains the code
        assert data["referral_code"] in data["referral_link"], "Referral link should contain the code"
        assert "?ref=" in data["referral_link"], "Referral link should have ?ref= parameter"
        print(f"SUCCESS: Got referral code {data['referral_code']}")
    
    def test_get_referral_stats(self):
        """Test GET /api/referrals/stats returns referral statistics"""
        response = requests.get(f"{BASE_URL}/api/referrals/stats", headers=self.headers)
        
        # Status code assertion
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Data assertions
        data = response.json()
        assert "referral_code" in data, "Missing referral_code in response"
        assert "referral_link" in data, "Missing referral_link in response"
        assert "total_referred" in data, "Missing total_referred in response"
        assert "pending_referrals" in data, "Missing pending_referrals in response"
        assert "successful_conversions" in data, "Missing successful_conversions in response"
        assert "rewards_earned" in data, "Missing rewards_earned in response"
        assert "referrals" in data, "Missing referrals array in response"
        
        # Validate data types
        assert isinstance(data["total_referred"], int), "total_referred should be integer"
        assert isinstance(data["pending_referrals"], int), "pending_referrals should be integer"
        assert isinstance(data["successful_conversions"], int), "successful_conversions should be integer"
        assert isinstance(data["rewards_earned"], int), "rewards_earned should be integer"
        assert isinstance(data["referrals"], list), "referrals should be a list"
        print(f"SUCCESS: Got referral stats - total_referred: {data['total_referred']}")
    
    def test_validate_referral_code_valid(self):
        """Test GET /api/referrals/validate/{code} for valid code (public endpoint - no auth)"""
        # First get the referral code for the demo user
        code_response = requests.get(f"{BASE_URL}/api/referrals/my-code", headers=self.headers)
        assert code_response.status_code == 200
        code = code_response.json()["referral_code"]
        
        # Validate the code (no auth header - public endpoint)
        response = requests.get(f"{BASE_URL}/api/referrals/validate/{code}")
        
        # Status code assertion
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Data assertions
        data = response.json()
        assert data.get("valid") == True, "Valid code should return valid: true"
        assert "referrer_name" in data, "Missing referrer_name for valid code"
        assert "discount_percent" in data, "Missing discount_percent"
        assert "message" in data, "Missing message"
        
        # Validate discount is 50%
        assert data["discount_percent"] == 50, "Discount should be 50%"
        print(f"SUCCESS: Validated code {code}, referrer: {data['referrer_name']}")
    
    def test_validate_referral_code_invalid(self):
        """Test GET /api/referrals/validate/{code} for invalid code (public endpoint - no auth)"""
        # Test with invalid code (no auth header - public endpoint)
        response = requests.get(f"{BASE_URL}/api/referrals/validate/INVALIDCODE123")
        
        # Status code assertion
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Data assertions
        data = response.json()
        assert data.get("valid") == False, "Invalid code should return valid: false"
        assert "message" in data, "Missing message for invalid code"
        assert data["message"] == "Invalid referral code", "Wrong message for invalid code"
        print("SUCCESS: Invalid code correctly rejected")
    
    def test_validate_referral_code_case_insensitive(self):
        """Test that referral code validation is case-insensitive"""
        # First get the referral code for the demo user
        code_response = requests.get(f"{BASE_URL}/api/referrals/my-code", headers=self.headers)
        assert code_response.status_code == 200
        code = code_response.json()["referral_code"]
        
        # Validate with lowercase version (no auth header - public endpoint)
        response = requests.get(f"{BASE_URL}/api/referrals/validate/{code.lower()}")
        
        # Status code assertion
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Data assertions
        data = response.json()
        assert data.get("valid") == True, "Lowercase code should still be valid"
        print(f"SUCCESS: Case-insensitive validation works for {code.lower()}")


class TestRegistrationWithReferral:
    """Test registration flow with referral codes"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get referrer's token and code"""
        # Login with demo credentials (referrer)
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@trustoffice.com",
            "password": "demopassword"
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        
        login_data = login_response.json()
        self.referrer_token = login_data.get("token")
        self.referrer_headers = {
            "Authorization": f"Bearer {self.referrer_token}",
            "Content-Type": "application/json"
        }
        
        # Get referrer's code
        code_response = requests.get(
            f"{BASE_URL}/api/referrals/my-code",
            headers=self.referrer_headers
        )
        assert code_response.status_code == 200
        self.referral_code = code_response.json()["referral_code"]
        yield
    
    def test_register_with_valid_referral_code(self):
        """Test registration with a valid referral code"""
        timestamp = int(time.time())
        test_email = f"TEST_referral_user_{timestamp}@test.com"
        
        # Register new user with referral code
        response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_email,
            "password": "TestPassword1",
            "name": f"Test Referred User {timestamp}",
            "referral_code": self.referral_code
        })
        
        # Status code assertion
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Data assertions
        data = response.json()
        assert "user_id" in data, "Missing user_id in response"
        # Email domain is lowercased but local part may preserve case
        assert data["email"].lower() == test_email.lower(), "Email should match (case insensitive)"
        
        print(f"SUCCESS: Registered user with referral code: {data['user_id']}")
        
        # Verify referral was tracked - check referrer's stats
        stats_response = requests.get(
            f"{BASE_URL}/api/referrals/stats",
            headers=self.referrer_headers
        )
        assert stats_response.status_code == 200
        stats = stats_response.json()
        
        # Should have at least 1 referred (may have more from previous tests)
        assert stats["total_referred"] >= 1, "Should have at least 1 referral"
        assert stats["pending_referrals"] >= 1, "Should have at least 1 pending referral"
        print(f"SUCCESS: Referral tracked - Total referred: {stats['total_referred']}")
    
    def test_register_with_invalid_referral_code(self):
        """Test registration with an invalid referral code still succeeds (code is optional)"""
        timestamp = int(time.time())
        test_email = f"TEST_invalid_ref_{timestamp}@test.com"
        
        # Register new user with invalid referral code
        response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_email,
            "password": "TestPassword1",
            "name": f"Test Invalid Ref User {timestamp}",
            "referral_code": "INVALID123"
        })
        
        # Status code assertion - registration should still succeed
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Data assertions
        data = response.json()
        assert "user_id" in data, "Missing user_id in response"
        print("SUCCESS: Registration with invalid referral code succeeded (code is optional)")
    
    def test_register_without_referral_code(self):
        """Test registration without a referral code works normally"""
        timestamp = int(time.time())
        test_email = f"TEST_no_ref_{timestamp}@test.com"
        
        # Register new user without referral code
        response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_email,
            "password": "TestPassword1",
            "name": f"Test No Ref User {timestamp}"
        })
        
        # Status code assertion
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Data assertions
        data = response.json()
        assert "user_id" in data, "Missing user_id in response"
        print("SUCCESS: Registration without referral code works normally")


class TestReferralUnauthorized:
    """Test referral endpoints without authentication"""
    
    def test_my_code_requires_auth(self):
        """Test GET /api/referrals/my-code requires authentication"""
        response = requests.get(f"{BASE_URL}/api/referrals/my-code")
        
        # Should return 401 or 403
        assert response.status_code in [401, 403], f"Expected 401 or 403, got {response.status_code}"
        print("SUCCESS: /referrals/my-code correctly requires authentication")
    
    def test_stats_requires_auth(self):
        """Test GET /api/referrals/stats requires authentication"""
        response = requests.get(f"{BASE_URL}/api/referrals/stats")
        
        # Should return 401 or 403
        assert response.status_code in [401, 403], f"Expected 401 or 403, got {response.status_code}"
        print("SUCCESS: /referrals/stats correctly requires authentication")
    
    def test_validate_is_public(self):
        """Test GET /api/referrals/validate/{code} is publicly accessible"""
        response = requests.get(f"{BASE_URL}/api/referrals/validate/ANYCODE")
        
        # Should return 200 even without auth
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("SUCCESS: /referrals/validate is correctly public")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
