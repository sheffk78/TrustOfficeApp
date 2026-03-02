# Test suite for Guided Minutes API endpoints
# Tests the 4-step wizard flow: context, draft generation, and save

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "demo@trustoffice.com"
TEST_PASSWORD = "demopassword"


class TestGuidedMinutesAPI:
    """Test suite for /api/guided-minutes endpoints"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup auth token and trust_id for all tests"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Authenticate
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        
        if login_response.status_code != 200:
            pytest.skip("Authentication failed - cannot test guided minutes")
        
        login_data = login_response.json()
        self.token = login_data.get("token")  # API returns 'token' not 'access_token'
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        # Get trust_id from user's trusts
        trusts_response = self.session.get(f"{BASE_URL}/api/trusts")
        if trusts_response.status_code == 200:
            trusts = trusts_response.json()
            if trusts:
                self.trust_id = trusts[0].get("trust_id")
            else:
                pytest.skip("No trusts available for testing")
        else:
            pytest.skip("Could not fetch trusts")

    def test_get_guided_minutes_context(self):
        """Test GET /api/guided-minutes/context returns trust context"""
        response = self.session.get(
            f"{BASE_URL}/api/guided-minutes/context",
            params={"trust_id": self.trust_id}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Validate required fields
        assert "trust_id" in data, "Missing trust_id in response"
        assert "trust_name" in data, "Missing trust_name in response"
        assert "trustees" in data, "Missing trustees list in response"
        assert isinstance(data["trustees"], list), "trustees should be a list"
        
        print(f"Context returned: trust_name={data.get('trust_name')}, trustees count={len(data.get('trustees', []))}")

    def test_get_guided_minutes_context_without_trust_id(self):
        """Test GET /api/guided-minutes/context returns default trust when trust_id not provided"""
        response = self.session.get(f"{BASE_URL}/api/guided-minutes/context")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "trust_id" in data, "Missing trust_id in response"
        assert "trust_name" in data, "Missing trust_name in response"

    def test_create_guided_minutes_draft(self):
        """Test POST /api/guided-minutes/draft generates AI draft"""
        # AI generation may take 5-15 seconds, so we use a longer timeout
        payload = {
            "trust_id": self.trust_id,
            "minutes_type": "quarterly",
            "meeting_date": "2025-01-15",
            "participants": ["John Trustee", "Jane Trustee"],
            "agenda_items": ["Review of Q4 finances", "Discussion of upcoming distributions"],
            "key_decisions": ["Approved distribution of $10,000 to beneficiary"]
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/guided-minutes/draft",
            json=payload,
            timeout=60  # AI generation can take time
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Validate response structure
        assert "suggested_title" in data, "Missing suggested_title in response"
        assert "draft_body" in data, "Missing draft_body in response"
        assert "cautions" in data, "Missing cautions in response"
        assert "minutes_type" in data, "Missing minutes_type in response"
        assert "meeting_date" in data, "Missing meeting_date in response"
        assert "participants_text" in data, "Missing participants_text in response"
        
        # Validate content
        assert len(data["draft_body"]) > 100, "Draft body seems too short"
        assert isinstance(data["cautions"], list), "cautions should be a list"
        assert data["minutes_type"] == "quarterly"
        assert data["meeting_date"] == "2025-01-15"
        
        print(f"Draft generated: title='{data['suggested_title'][:50]}...'")
        print(f"Draft body length: {len(data['draft_body'])} chars")
        print(f"Cautions: {len(data['cautions'])} warnings")
        
        # Store for save test
        self.draft_response = data

    def test_create_guided_minutes_draft_annual(self):
        """Test annual meeting type draft generation"""
        payload = {
            "trust_id": self.trust_id,
            "minutes_type": "annual",
            "meeting_date": "2025-01-10",
            "participants": ["Test Trustee"],
            "agenda_items": ["Annual review"],
            "key_decisions": ["Confirmed annual compliance"]
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/guided-minutes/draft",
            json=payload,
            timeout=60
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["minutes_type"] == "annual"

    def test_create_guided_minutes_draft_general(self):
        """Test general meeting type draft generation"""
        payload = {
            "trust_id": self.trust_id,
            "minutes_type": "general",
            "meeting_date": "2025-01-12",
            "participants": ["Test Trustee"],
            "agenda_items": ["Special matter"],
            "key_decisions": ["Approved special request"]
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/guided-minutes/draft",
            json=payload,
            timeout=60
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["minutes_type"] == "general"

    def test_save_guided_minutes(self):
        """Test POST /api/guided-minutes/save saves minutes record"""
        payload = {
            "trust_id": self.trust_id,
            "minutes_type": "quarterly",
            "meeting_date": "2025-01-15",
            "participants_text": "John Trustee, Jane Trustee",
            "decisions_text": "TEST_GuidedMinutes: Test meeting minutes content for automated testing. WHEREAS the trustees met to discuss important matters, RESOLVED that the test passed successfully."
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/guided-minutes/save",
            json=payload,
            timeout=30
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Validate saved record structure
        assert "minutes_id" in data, "Missing minutes_id in response"
        assert "trust_id" in data, "Missing trust_id in response"
        assert "minutes_type" in data, "Missing minutes_type in response"
        assert "meeting_date" in data, "Missing meeting_date in response"
        assert "decisions_text" in data, "Missing decisions_text in response"
        assert "created_at" in data, "Missing created_at in response"
        
        # Validate content
        assert data["trust_id"] == self.trust_id
        assert data["minutes_type"] == "quarterly"
        assert "TEST_GuidedMinutes" in data["decisions_text"]
        
        print(f"Minutes saved: minutes_id={data['minutes_id']}")
        
        # Verify persistence by fetching the saved record
        saved_minutes_id = data["minutes_id"]
        verify_response = self.session.get(f"{BASE_URL}/api/minutes/{saved_minutes_id}")
        assert verify_response.status_code == 200, f"Failed to verify saved minutes: {verify_response.status_code}"

    def test_context_invalid_trust_returns_404(self):
        """Test that invalid trust_id returns 404"""
        response = self.session.get(
            f"{BASE_URL}/api/guided-minutes/context",
            params={"trust_id": "nonexistent_trust_12345"}
        )
        
        # Should return 404 Not Found
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"

    def test_draft_missing_required_fields(self):
        """Test draft generation with missing required fields returns 422"""
        payload = {
            "trust_id": self.trust_id,
            # Missing minutes_type, meeting_date, participants
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/guided-minutes/draft",
            json=payload
        )
        
        # Should return 422 Unprocessable Entity for validation error
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"

    def test_save_missing_required_fields(self):
        """Test save with missing required fields returns 422"""
        payload = {
            "trust_id": self.trust_id,
            # Missing other required fields
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/guided-minutes/save",
            json=payload
        )
        
        # Should return 422 Unprocessable Entity for validation error
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"

    def test_context_without_auth_returns_401(self):
        """Test that unauthenticated request returns 401"""
        session_no_auth = requests.Session()
        response = session_no_auth.get(f"{BASE_URL}/api/guided-minutes/context")
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
