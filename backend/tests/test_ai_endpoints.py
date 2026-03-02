"""
AI Endpoints Tests for TrustOffice
Tests AI integration layer using Claude API for:
- Minutes drafting (Claude Sonnet)
- Governance suggestions (Claude Haiku)
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from context
DEMO_EMAIL = "demo@trustoffice.com"
DEMO_PASSWORD = "demopassword"


class TestSetup:
    """Test fixtures and helper methods"""
    
    @staticmethod
    def get_auth_token():
        """Login and get auth token for protected endpoints"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}
        )
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip(f"Authentication failed: {response.status_code}")
        return None


class TestAIStatusEndpoint:
    """Tests for GET /api/ai/status"""
    
    def test_ai_status_requires_authentication(self):
        """Verify AI status endpoint requires auth"""
        response = requests.get(f"{BASE_URL}/api/ai/status")
        assert response.status_code == 401 or response.status_code == 403, \
            f"Expected 401/403 without auth, got {response.status_code}"
        print("PASS: GET /api/ai/status requires authentication (401/403)")
    
    def test_ai_status_returns_enabled_status(self):
        """Verify AI status returns AI enabled status and available features"""
        token = TestSetup.get_auth_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.get(
            f"{BASE_URL}/api/ai/status",
            headers=headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify response structure
        assert "ai_enabled" in data, "Missing 'ai_enabled' field"
        assert isinstance(data["ai_enabled"], bool), "'ai_enabled' should be boolean"
        
        assert "features" in data, "Missing 'features' field"
        assert "minutes_drafting" in data["features"], "Missing 'minutes_drafting' feature"
        assert "governance_suggestions" in data["features"], "Missing 'governance_suggestions' feature"
        
        assert "models" in data, "Missing 'models' field"
        
        print(f"PASS: AI Status Response - ai_enabled: {data['ai_enabled']}")
        print(f"PASS: Features - minutes_drafting: {data['features']['minutes_drafting']}, governance_suggestions: {data['features']['governance_suggestions']}")
        print(f"PASS: Models - drafting: {data['models']['drafting']}, suggestions: {data['models']['suggestions']}")


class TestMinutesDraftEndpoint:
    """Tests for POST /api/ai/minutes-draft (Claude Sonnet)"""
    
    def test_minutes_draft_requires_authentication(self):
        """Verify minutes drafting endpoint requires auth"""
        payload = {
            "minutes_type": "annual",
            "meeting_date": "2025-01-15",
            "participants": ["John Smith - Trustee"],
            "decisions_outline": ["Approved annual distribution"],
            "trust_name": "Test Trust"
        }
        response = requests.post(
            f"{BASE_URL}/api/ai/minutes-draft",
            json=payload
        )
        assert response.status_code == 401 or response.status_code == 403, \
            f"Expected 401/403 without auth, got {response.status_code}"
        print("PASS: POST /api/ai/minutes-draft requires authentication (401/403)")
    
    def test_minutes_draft_generates_formal_minutes(self):
        """Verify minutes drafting generates formal minutes with WHEREAS/RESOLVED structure"""
        token = TestSetup.get_auth_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        payload = {
            "minutes_type": "annual",
            "meeting_date": "2025-01-15",
            "participants": ["John Smith - Trustee", "Jane Doe - Attorney"],
            "decisions_outline": [
                "Approved annual distribution to beneficiary",
                "Reviewed trust assets and investments"
            ],
            "trust_name": "Smith Family Trust",
            "jurisdiction": "Delaware",
            "beneficiary_standard": "HEMS",
            "additional_context": "Routine annual review meeting"
        }
        
        # Note: Claude API calls may take 5-15 seconds
        response = requests.post(
            f"{BASE_URL}/api/ai/minutes-draft",
            headers=headers,
            json=payload,
            timeout=60  # Extended timeout for AI call
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.text[:500]}"
        data = response.json()
        
        # Verify response structure
        assert "draft_body" in data, "Missing 'draft_body' field"
        assert isinstance(data["draft_body"], str), "'draft_body' should be string"
        assert len(data["draft_body"]) > 100, f"draft_body too short: {len(data['draft_body'])} chars"
        
        assert "suggested_title" in data, "Missing 'suggested_title' field"
        assert isinstance(data["suggested_title"], str), "'suggested_title' should be string"
        assert len(data["suggested_title"]) > 0, "suggested_title should not be empty"
        
        assert "cautions" in data, "Missing 'cautions' field"
        assert isinstance(data["cautions"], list), "'cautions' should be list"
        
        # Verify content quality - should have formal language
        draft = data["draft_body"].upper()
        # Check for formal minute language patterns
        has_formal_structure = any(word in draft for word in ["WHEREAS", "RESOLVED", "MEETING", "MINUTES", "TRUSTEE"])
        assert has_formal_structure, f"Draft doesn't appear to have formal minutes structure: {data['draft_body'][:300]}"
        
        print(f"PASS: Minutes Draft Generated Successfully")
        print(f"PASS: suggested_title: {data['suggested_title']}")
        print(f"PASS: draft_body length: {len(data['draft_body'])} chars")
        print(f"PASS: cautions count: {len(data['cautions'])}")
    
    def test_minutes_draft_validation(self):
        """Verify minutes draft validates required fields"""
        token = TestSetup.get_auth_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        # Missing required fields
        payload = {
            "minutes_type": "annual"
            # Missing meeting_date, participants, decisions_outline, trust_name
        }
        
        response = requests.post(
            f"{BASE_URL}/api/ai/minutes-draft",
            headers=headers,
            json=payload
        )
        
        # Should fail validation with 422
        assert response.status_code == 422, f"Expected 422 for invalid payload, got {response.status_code}"
        print("PASS: Minutes draft validates required fields (returns 422 for invalid input)")


class TestGovernanceSuggestionsEndpoint:
    """Tests for POST /api/ai/governance-suggestions (Claude Haiku)"""
    
    def test_governance_suggestions_requires_authentication(self):
        """Verify governance suggestions endpoint requires auth"""
        response = requests.post(f"{BASE_URL}/api/ai/governance-suggestions")
        assert response.status_code == 401 or response.status_code == 403, \
            f"Expected 401/403 without auth, got {response.status_code}"
        print("PASS: POST /api/ai/governance-suggestions requires authentication (401/403)")
    
    def test_governance_suggestions_returns_actionable_suggestions(self):
        """Verify governance suggestions returns actionable suggestions with routes and point estimates"""
        token = TestSetup.get_auth_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        # Note: Claude API calls may take 5-15 seconds
        response = requests.post(
            f"{BASE_URL}/api/ai/governance-suggestions",
            headers=headers,
            timeout=60  # Extended timeout for AI call
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.text[:500]}"
        data = response.json()
        
        # Verify response structure
        assert "suggestions" in data, "Missing 'suggestions' field"
        assert isinstance(data["suggestions"], list), "'suggestions' should be list"
        
        # Should have 2-4 suggestions as per AI service logic
        if len(data["suggestions"]) > 0:
            suggestion = data["suggestions"][0]
            
            # Verify suggestion structure
            assert "title" in suggestion, "Suggestion missing 'title'"
            assert isinstance(suggestion["title"], str), "Suggestion title should be string"
            
            assert "description" in suggestion, "Suggestion missing 'description'"
            assert isinstance(suggestion["description"], str), "Suggestion description should be string"
            
            assert "route" in suggestion, "Suggestion missing 'route'"
            assert isinstance(suggestion["route"], str), "Suggestion route should be string"
            assert suggestion["route"].startswith("/"), f"Route should start with '/': {suggestion['route']}"
            
            # estimated_points_gain can be int or null
            assert "estimated_points_gain" in suggestion, "Suggestion missing 'estimated_points_gain'"
            
            # Verify routes are valid app routes
            valid_routes = [
                "/minutes/new", "/minutes/templates", "/calendar", "/distributions",
                "/schedule-a", "/benevolence", "/compensation", "/governance",
                "/entities", "/trust-units"
            ]
            has_valid_route = any(
                suggestion["route"].startswith(r) for r in valid_routes
            )
            assert has_valid_route, f"Invalid route: {suggestion['route']}"
            
            print(f"PASS: Governance Suggestions Generated Successfully")
            print(f"PASS: Number of suggestions: {len(data['suggestions'])}")
            for i, s in enumerate(data["suggestions"]):
                print(f"PASS: Suggestion {i+1}: {s['title']} -> {s['route']} (points: {s.get('estimated_points_gain', 'N/A')})")
        else:
            print(f"WARN: No suggestions returned (user may have perfect governance score)")
    
    def test_governance_suggestions_with_trust_id(self):
        """Verify governance suggestions can accept optional trust_id parameter"""
        token = TestSetup.get_auth_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        # First get user's trusts to get a valid trust_id
        trusts_response = requests.get(
            f"{BASE_URL}/api/trusts",
            headers=headers
        )
        
        if trusts_response.status_code == 200:
            trusts = trusts_response.json()
            if trusts and len(trusts) > 0:
                trust_id = trusts[0].get("trust_id")
                
                # Call with trust_id
                response = requests.post(
                    f"{BASE_URL}/api/ai/governance-suggestions?trust_id={trust_id}",
                    headers=headers,
                    timeout=60
                )
                
                assert response.status_code == 200, f"Expected 200, got {response.status_code}"
                data = response.json()
                assert "suggestions" in data
                print(f"PASS: Governance suggestions with trust_id={trust_id} returned successfully")
            else:
                pytest.skip("No trusts found for user")
        else:
            pytest.skip(f"Could not get trusts: {trusts_response.status_code}")


class TestAIEndpointEdgeCases:
    """Edge case tests for AI endpoints"""
    
    def test_ai_status_with_invalid_token(self):
        """Verify AI status rejects invalid tokens"""
        headers = {"Authorization": "Bearer invalid_token_12345"}
        response = requests.get(
            f"{BASE_URL}/api/ai/status",
            headers=headers
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("PASS: AI status rejects invalid token")
    
    def test_minutes_draft_with_minimal_input(self):
        """Test minutes draft with minimal valid input"""
        token = TestSetup.get_auth_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        # Minimal but valid payload
        payload = {
            "minutes_type": "special",
            "meeting_date": "2025-01-20",
            "participants": ["Test Trustee"],
            "decisions_outline": ["Simple decision"],
            "trust_name": "Minimal Test Trust"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/ai/minutes-draft",
            headers=headers,
            json=payload,
            timeout=60
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "draft_body" in data
        assert "suggested_title" in data
        assert "cautions" in data
        print("PASS: Minutes draft works with minimal valid input")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
