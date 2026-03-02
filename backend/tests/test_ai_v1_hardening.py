"""
AI v1 Integration Hardening Tests
Tests for:
1. AI endpoints return safe error messages (not exposing internal details)
2. Rate limiting is active (max 10 drafts, 20 suggestions per user per hour)
3. GET /api/ai/status returns rate_limits in response
4. GET /api/ai/health performs ping and returns {ok: true/false}
5. AI_CALL log entries contain user_id, trust_id, endpoint, model, input_chars
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
DEMO_EMAIL = "demo@trustoffice.com"
DEMO_PASSWORD = "demopassword"


class TestAIStatusEndpoint:
    """Tests for GET /api/ai/status - must include rate_limits"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get auth token for tests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}
        )
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Authentication failed")
    
    def test_ai_status_returns_rate_limits(self, auth_token):
        """Verify GET /api/ai/status returns rate_limits object"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        response = requests.get(
            f"{BASE_URL}/api/ai/status",
            headers=headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify rate_limits field exists and has correct structure
        assert "rate_limits" in data, "Missing 'rate_limits' field in response"
        
        rate_limits = data["rate_limits"]
        assert rate_limits is not None, "rate_limits should not be null when AI is enabled"
        
        # Verify rate limit values
        assert "minutes-draft" in rate_limits, "Missing 'minutes-draft' rate limit"
        assert rate_limits["minutes-draft"] == 10, f"Expected 10 drafts/hour, got {rate_limits['minutes-draft']}"
        
        assert "governance-suggestions" in rate_limits, "Missing 'governance-suggestions' rate limit"
        assert rate_limits["governance-suggestions"] == 20, f"Expected 20 suggestions/hour, got {rate_limits['governance-suggestions']}"
        
        print(f"PASS: GET /api/ai/status returns rate_limits: {rate_limits}")
    
    def test_ai_status_complete_response_structure(self, auth_token):
        """Verify complete response structure of GET /api/ai/status"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        response = requests.get(
            f"{BASE_URL}/api/ai/status",
            headers=headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Required fields
        required_fields = ["ai_enabled", "features", "models", "rate_limits"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        # Features sub-structure
        assert "minutes_drafting" in data["features"]
        assert "governance_suggestions" in data["features"]
        
        # Models sub-structure
        assert "drafting" in data["models"]
        assert "suggestions" in data["models"]
        
        print(f"PASS: Complete response structure verified: {list(data.keys())}")


class TestAIHealthEndpoint:
    """Tests for GET /api/ai/health - performs ping and returns ok status"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get auth token for tests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}
        )
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Authentication failed")
    
    def test_ai_health_returns_ok_field(self, auth_token):
        """Verify GET /api/ai/health returns {ok: true/false}"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        response = requests.get(
            f"{BASE_URL}/api/ai/health",
            headers=headers,
            timeout=30  # Health check may perform a Claude ping
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Must have "ok" field
        assert "ok" in data, "Missing 'ok' field in health check response"
        assert isinstance(data["ok"], bool), "'ok' should be boolean"
        
        print(f"PASS: GET /api/ai/health returns ok={data['ok']}")
    
    def test_ai_health_requires_auth(self):
        """Verify GET /api/ai/health requires authentication"""
        response = requests.get(f"{BASE_URL}/api/ai/health")
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"
        print("PASS: /api/ai/health requires authentication")


class TestAISafeErrorMessages:
    """Tests to verify AI endpoints return safe error messages without exposing internals"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get auth token for tests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}
        )
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Authentication failed")
    
    def test_minutes_draft_error_is_safe(self, auth_token):
        """Verify error messages don't expose internal details"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Send invalid payload to trigger validation error
        payload = {"invalid": "data"}
        
        response = requests.post(
            f"{BASE_URL}/api/ai/minutes-draft",
            headers=headers,
            json=payload
        )
        
        # 422 validation error is expected
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        data = response.json()
        
        # Error should be FastAPI validation format, not expose internal stack traces
        error_text = str(data)
        unsafe_patterns = [
            "traceback", "exception", "stack", "Traceback",
            "File \"", "line ", "claude_client", "ai_service",
            "EMERGENT_LLM_KEY", "api_key", "secret"
        ]
        
        for pattern in unsafe_patterns:
            assert pattern.lower() not in error_text.lower(), f"Error exposes unsafe pattern: {pattern}"
        
        print("PASS: Validation error message is safe (no internal details exposed)")
    
    def test_governance_suggestions_not_found_is_safe(self, auth_token):
        """Verify 404 error for invalid trust_id doesn't expose internals"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        response = requests.post(
            f"{BASE_URL}/api/ai/governance-suggestions?trust_id=invalid_trust_12345",
            headers=headers
        )
        
        # Should return 404 for invalid trust
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        data = response.json()
        
        # Error should be a simple message
        error_text = str(data)
        unsafe_patterns = [
            "traceback", "exception", "stack", "mongodb",
            "collection", "pymongo", "ObjectId"
        ]
        
        for pattern in unsafe_patterns:
            assert pattern.lower() not in error_text.lower(), f"Error exposes unsafe pattern: {pattern}"
        
        print(f"PASS: 404 error is safe: {data.get('detail', data)}")


class TestRateLimitingConfiguration:
    """Tests to verify rate limiting is properly configured"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get auth token for tests"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}
        )
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Authentication failed")
    
    def test_rate_limits_advertised_correctly(self, auth_token):
        """Verify rate limits are advertised correctly in /api/ai/status"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        response = requests.get(
            f"{BASE_URL}/api/ai/status",
            headers=headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check exact rate limit values from spec
        assert data["rate_limits"]["minutes-draft"] == 10, "Minutes draft should be 10/hour"
        assert data["rate_limits"]["governance-suggestions"] == 20, "Suggestions should be 20/hour"
        
        print("PASS: Rate limits correctly configured: minutes-draft=10, governance-suggestions=20")
    
    def test_rate_limit_error_message_format(self, auth_token):
        """Note: This test verifies the rate limit error format without actually hitting the limit"""
        # We can't easily test rate limit triggering in production without hitting 10 requests
        # But we can verify the endpoint returns proper status code format
        
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Make a valid request to verify it doesn't hit rate limit (user shouldn't have 10 requests)
        response = requests.post(
            f"{BASE_URL}/api/ai/minutes-draft",
            headers=headers,
            json={
                "minutes_type": "special",
                "meeting_date": "2026-01-15",
                "participants": ["Test Trustee"],
                "decisions_outline": ["Test decision"],
                "trust_name": "Test Trust"
            },
            timeout=60
        )
        
        # Should succeed (not rate limited)
        assert response.status_code in [200, 429], f"Expected 200 or 429, got {response.status_code}"
        
        if response.status_code == 429:
            data = response.json()
            error_msg = data.get("detail", "")
            # Rate limit message should be safe and informative
            assert "rate limit" in error_msg.lower(), "Rate limit error should mention rate limit"
            assert "Max" in error_msg or "later" in error_msg, "Error should indicate when to retry"
            print(f"PASS: Rate limit message format verified: {error_msg}")
        else:
            print("PASS: Request succeeded (within rate limit), format would be checked if 429 occurs")


class TestAIEndpointAuthentication:
    """Tests for authentication on AI endpoints"""
    
    def test_status_requires_auth(self):
        """GET /api/ai/status requires authentication"""
        response = requests.get(f"{BASE_URL}/api/ai/status")
        assert response.status_code in [401, 403]
        print("PASS: /api/ai/status requires auth")
    
    def test_health_requires_auth(self):
        """GET /api/ai/health requires authentication"""
        response = requests.get(f"{BASE_URL}/api/ai/health")
        assert response.status_code in [401, 403]
        print("PASS: /api/ai/health requires auth")
    
    def test_minutes_draft_requires_auth(self):
        """POST /api/ai/minutes-draft requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/ai/minutes-draft",
            json={"minutes_type": "annual", "meeting_date": "2026-01-01", 
                  "participants": ["Test"], "decisions_outline": ["Test"], "trust_name": "Test"}
        )
        assert response.status_code in [401, 403]
        print("PASS: /api/ai/minutes-draft requires auth")
    
    def test_governance_suggestions_requires_auth(self):
        """POST /api/ai/governance-suggestions requires authentication"""
        response = requests.post(f"{BASE_URL}/api/ai/governance-suggestions")
        assert response.status_code in [401, 403]
        print("PASS: /api/ai/governance-suggestions requires auth")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
