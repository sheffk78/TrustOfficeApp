"""
Test Suite: Notification Preferences & Benevolence PDF Export APIs
Testing newly added features from session - Iteration 18
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "test@trustoffice.com"
TEST_PASSWORD = "testpassword123"
TRUST_ID = "trust_f8896488ce03"  # Trust with benevolence_enabled=true


class TestAuth:
    """Authentication helper"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        if response.status_code == 200:
            return response.json().get("token")
        pytest.fail(f"Authentication failed: {response.status_code} - {response.text}")
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Headers with auth token"""
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestNotificationPreferences(TestAuth):
    """Test notification preferences endpoints"""
    
    def test_get_notification_preferences_returns_valid_response(self, auth_headers):
        """GET /api/notifications/preferences returns user preferences with user_id"""
        response = requests.get(f"{BASE_URL}/api/notifications/preferences", headers=auth_headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify user_id is present
        assert "user_id" in data, "Missing user_id field"
        
        # Check that any stored preferences are boolean type
        possible_fields = ["minutes_created", "distribution_created", "distribution_approved", 
                         "task_reminders", "task_overdue", "subscription_updates", "weekly_digest"]
        for field in possible_fields:
            if field in data:
                assert isinstance(data[field], bool), f"{field} should be boolean"
        
        print(f"✓ GET /api/notifications/preferences returned valid response: {data}")
    
    def test_update_notification_preference_single_field(self, auth_headers):
        """PUT /api/notifications/preferences updates specific preference fields"""
        # Toggle weekly_digest
        response = requests.put(
            f"{BASE_URL}/api/notifications/preferences",
            headers=auth_headers,
            json={"weekly_digest": True}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "message" in data, "Missing confirmation message"
        assert data.get("preferences", {}).get("weekly_digest") == True, "weekly_digest was not updated"
        
        print(f"✓ PUT /api/notifications/preferences updated weekly_digest to True")
        
        # Now set it back to False
        response = requests.put(
            f"{BASE_URL}/api/notifications/preferences",
            headers=auth_headers,
            json={"weekly_digest": False}
        )
        assert response.status_code == 200
        print(f"✓ PUT /api/notifications/preferences reset weekly_digest to False")
    
    def test_update_multiple_preferences(self, auth_headers):
        """PUT /api/notifications/preferences can update multiple fields at once"""
        response = requests.put(
            f"{BASE_URL}/api/notifications/preferences",
            headers=auth_headers,
            json={
                "task_reminders": False,
                "task_overdue": False
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        prefs = data.get("preferences", {})
        assert prefs.get("task_reminders") == False
        assert prefs.get("task_overdue") == False
        
        print(f"✓ PUT /api/notifications/preferences updated multiple fields")
        
        # Reset them back
        requests.put(
            f"{BASE_URL}/api/notifications/preferences",
            headers=auth_headers,
            json={"task_reminders": True, "task_overdue": True}
        )
    
    def test_update_preferences_empty_body_fails(self, auth_headers):
        """PUT /api/notifications/preferences returns 400 if no fields to update"""
        response = requests.put(
            f"{BASE_URL}/api/notifications/preferences",
            headers=auth_headers,
            json={}
        )
        
        assert response.status_code == 400, f"Expected 400 for empty update, got {response.status_code}"
        print(f"✓ PUT /api/notifications/preferences correctly returns 400 for empty body")
    
    def test_get_preferences_requires_auth(self):
        """GET /api/notifications/preferences requires authentication"""
        response = requests.get(f"{BASE_URL}/api/notifications/preferences")
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print(f"✓ GET /api/notifications/preferences correctly requires authentication")


class TestBenevolenceExportPDF(TestAuth):
    """Test benevolence PDF export endpoint"""
    
    def test_export_benevolence_pdf_success(self, auth_headers):
        """GET /api/benevolence/export/{trust_id}/pdf generates valid PDF"""
        response = requests.get(
            f"{BASE_URL}/api/benevolence/export/{TRUST_ID}/pdf",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        assert response.headers.get("content-type") == "application/pdf", "Response should be PDF"
        
        # Verify content-disposition header
        content_disp = response.headers.get("content-disposition", "")
        assert "attachment" in content_disp, "Should have attachment disposition"
        assert ".pdf" in content_disp, "Filename should include .pdf"
        
        # Verify PDF content starts with PDF magic bytes
        content = response.content
        assert len(content) > 100, "PDF should have substantial content"
        assert content[:4] == b'%PDF', "Content should start with PDF magic bytes"
        
        print(f"✓ GET /api/benevolence/export/{TRUST_ID}/pdf returned valid PDF ({len(content)} bytes)")
    
    def test_export_benevolence_pdf_with_year_filter(self, auth_headers):
        """GET /api/benevolence/export/{trust_id}/pdf?year=2026 filters by year"""
        current_year = 2026
        response = requests.get(
            f"{BASE_URL}/api/benevolence/export/{TRUST_ID}/pdf?year={current_year}",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        assert response.headers.get("content-type") == "application/pdf"
        
        # Verify filename includes year
        content_disp = response.headers.get("content-disposition", "")
        assert str(current_year) in content_disp or "benevolence_report" in content_disp
        
        print(f"✓ GET /api/benevolence/export/{TRUST_ID}/pdf?year={current_year} returned filtered PDF")
    
    def test_export_pdf_invalid_trust_returns_404(self, auth_headers):
        """GET /api/benevolence/export/{invalid_trust_id}/pdf returns 404"""
        response = requests.get(
            f"{BASE_URL}/api/benevolence/export/trust_invalid123/pdf",
            headers=auth_headers
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print(f"✓ GET /api/benevolence/export/invalid_trust/pdf correctly returns 404")
    
    def test_export_pdf_benevolence_disabled_returns_400(self, auth_headers):
        """GET /api/benevolence/export/{trust_id}/pdf returns 400 if benevolence is not enabled"""
        # First we need to find or create a trust without benevolence enabled
        # Get user trusts
        trusts_response = requests.get(f"{BASE_URL}/api/trusts", headers=auth_headers)
        
        if trusts_response.status_code == 200:
            trusts = trusts_response.json()
            # Find a trust with benevolence_enabled=false
            non_benevolence_trust = None
            for trust in trusts:
                if not trust.get("benevolence_enabled", False) and trust.get("trust_id") != TRUST_ID:
                    non_benevolence_trust = trust
                    break
            
            if non_benevolence_trust:
                trust_id = non_benevolence_trust["trust_id"]
                response = requests.get(
                    f"{BASE_URL}/api/benevolence/export/{trust_id}/pdf",
                    headers=auth_headers
                )
                
                assert response.status_code == 400, f"Expected 400, got {response.status_code}"
                assert "not enabled" in response.json().get("detail", "").lower()
                print(f"✓ GET /api/benevolence/export/{trust_id}/pdf returns 400 when benevolence disabled")
            else:
                # Create a test trust without benevolence
                create_response = requests.post(
                    f"{BASE_URL}/api/trusts",
                    headers=auth_headers,
                    json={"name": "TEST_No_Benevolence_Trust", "trust_type": "family", "jurisdiction": "Test"}
                )
                if create_response.status_code == 200:
                    test_trust = create_response.json()
                    test_trust_id = test_trust["trust_id"]
                    
                    response = requests.get(
                        f"{BASE_URL}/api/benevolence/export/{test_trust_id}/pdf",
                        headers=auth_headers
                    )
                    
                    assert response.status_code == 400, f"Expected 400, got {response.status_code}"
                    print(f"✓ GET /api/benevolence/export/{test_trust_id}/pdf returns 400 when benevolence disabled")
                    
                    # Cleanup - delete test trust
                    requests.delete(f"{BASE_URL}/api/trusts/{test_trust_id}", headers=auth_headers)
                else:
                    pytest.skip("Could not find or create a trust without benevolence to test")
        else:
            pytest.skip("Could not get trusts list to find test trust")
    
    def test_export_pdf_requires_auth(self):
        """GET /api/benevolence/export/{trust_id}/pdf requires authentication"""
        response = requests.get(f"{BASE_URL}/api/benevolence/export/{TRUST_ID}/pdf")
        assert response.status_code == 401, f"Expected 401 without auth, got {response.status_code}"
        print(f"✓ GET /api/benevolence/export/{TRUST_ID}/pdf correctly requires authentication")


class TestIntegration(TestAuth):
    """Integration tests for verifying real-time updates"""
    
    def test_notification_preference_persistence(self, auth_headers):
        """Verify notification preference changes persist correctly"""
        # Get current state
        get_response = requests.get(f"{BASE_URL}/api/notifications/preferences", headers=auth_headers)
        original_prefs = get_response.json()
        
        # Toggle a preference
        new_value = not original_prefs.get("minutes_created", True)
        update_response = requests.put(
            f"{BASE_URL}/api/notifications/preferences",
            headers=auth_headers,
            json={"minutes_created": new_value}
        )
        assert update_response.status_code == 200
        
        # Verify it persisted
        verify_response = requests.get(f"{BASE_URL}/api/notifications/preferences", headers=auth_headers)
        assert verify_response.json().get("minutes_created") == new_value
        
        # Reset to original
        requests.put(
            f"{BASE_URL}/api/notifications/preferences",
            headers=auth_headers,
            json={"minutes_created": original_prefs.get("minutes_created", True)}
        )
        
        print(f"✓ Notification preference changes persist correctly")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
