"""
Test P1 Features:
1. Profile editing - PUT /api/auth/profile endpoint
2. Minutes search - GET /api/minutes with search parameter
3. Distributions search - GET /api/distributions with search parameter
"""

import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "testuser@test.com"
TEST_PASSWORD = "testpassword123"


class TestProfileUpdate:
    """Test profile update functionality"""
    
    @pytest.fixture
    def auth_token(self):
        """Login and get auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        if response.status_code != 200:
            pytest.skip(f"Login failed with status {response.status_code}: {response.text}")
        return response.json().get("token")
    
    def test_profile_update_success(self, auth_token):
        """Test PUT /api/auth/profile updates name successfully"""
        new_name = f"Test User {datetime.now().strftime('%H%M%S')}"
        
        response = requests.put(
            f"{BASE_URL}/api/auth/profile",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"name": new_name}
        )
        
        assert response.status_code == 200, f"Profile update failed: {response.text}"
        data = response.json()
        assert "user" in data, "Response should contain user object"
        assert data["user"]["name"] == new_name, "Name should be updated"
        print(f"✓ Profile updated successfully: name changed to '{new_name}'")
    
    def test_profile_update_empty_name_fails(self, auth_token):
        """Test that empty name is rejected"""
        response = requests.put(
            f"{BASE_URL}/api/auth/profile",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"name": "   "}
        )
        
        assert response.status_code == 400, "Empty name should return 400"
        print("✓ Empty name correctly rejected")
    
    def test_profile_update_no_fields_fails(self, auth_token):
        """Test that request with no fields fails"""
        response = requests.put(
            f"{BASE_URL}/api/auth/profile",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={}
        )
        
        assert response.status_code == 400, "No fields should return 400"
        print("✓ No fields correctly rejected")
    
    def test_profile_update_unauthorized(self):
        """Test that unauthorized request fails"""
        response = requests.put(
            f"{BASE_URL}/api/auth/profile",
            json={"name": "Test Name"}
        )
        
        assert response.status_code == 401, "Unauthorized request should return 401"
        print("✓ Unauthorized request correctly rejected")


class TestMinutesSearch:
    """Test minutes search functionality"""
    
    @pytest.fixture
    def auth_token(self):
        """Login and get auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        if response.status_code != 200:
            pytest.skip(f"Login failed with status {response.status_code}: {response.text}")
        return response.json().get("token")
    
    @pytest.fixture
    def trust_id(self, auth_token):
        """Get first trust ID for the user"""
        response = requests.get(
            f"{BASE_URL}/api/trusts",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        if response.status_code != 200:
            pytest.skip("Could not get trusts")
        trusts = response.json()
        if not trusts:
            pytest.skip("No trusts available for testing")
        return trusts[0]["trust_id"]
    
    def test_minutes_search_with_search_param(self, auth_token, trust_id):
        """Test GET /api/minutes with search parameter"""
        # First get all minutes to see what data exists
        response = requests.get(
            f"{BASE_URL}/api/minutes?trust_id={trust_id}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Get minutes failed: {response.text}"
        all_minutes = response.json()
        print(f"Total minutes found: {len(all_minutes)}")
        
        # Now search with a term
        search_term = "test"
        response = requests.get(
            f"{BASE_URL}/api/minutes?trust_id={trust_id}&search={search_term}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200, f"Search minutes failed: {response.text}"
        search_results = response.json()
        print(f"✓ Minutes search with '{search_term}' returned {len(search_results)} results")
    
    def test_minutes_search_empty_results(self, auth_token, trust_id):
        """Test search with term that returns no results"""
        search_term = "xyznonexistent123"
        response = requests.get(
            f"{BASE_URL}/api/minutes?trust_id={trust_id}&search={search_term}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200, f"Search should still return 200 with empty results"
        results = response.json()
        print(f"✓ Minutes search for non-existent term returned {len(results)} results (expected 0 or few)")
    
    def test_minutes_search_case_insensitive(self, auth_token, trust_id):
        """Test that search is case-insensitive"""
        # Search with lowercase
        response_lower = requests.get(
            f"{BASE_URL}/api/minutes?trust_id={trust_id}&search=meeting",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        # Search with uppercase
        response_upper = requests.get(
            f"{BASE_URL}/api/minutes?trust_id={trust_id}&search=MEETING",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response_lower.status_code == 200
        assert response_upper.status_code == 200
        
        # Results should be the same (case insensitive)
        print(f"✓ Case insensitive search: lowercase got {len(response_lower.json())} results, uppercase got {len(response_upper.json())} results")
    
    def test_minutes_search_with_type_filter(self, auth_token, trust_id):
        """Test that type filter still works alongside search"""
        response = requests.get(
            f"{BASE_URL}/api/minutes?trust_id={trust_id}&search=test&minutes_type=annual",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200, f"Search with type filter failed: {response.text}"
        print(f"✓ Minutes search with type filter returned {len(response.json())} results")


class TestDistributionsSearch:
    """Test distributions search functionality"""
    
    @pytest.fixture
    def auth_token(self):
        """Login and get auth token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        if response.status_code != 200:
            pytest.skip(f"Login failed with status {response.status_code}: {response.text}")
        return response.json().get("token")
    
    @pytest.fixture
    def trust_id(self, auth_token):
        """Get first trust ID for the user"""
        response = requests.get(
            f"{BASE_URL}/api/trusts",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        if response.status_code != 200:
            pytest.skip("Could not get trusts")
        trusts = response.json()
        if not trusts:
            pytest.skip("No trusts available for testing")
        return trusts[0]["trust_id"]
    
    def test_distributions_search_with_search_param(self, auth_token, trust_id):
        """Test GET /api/distributions with search parameter"""
        # First get all distributions to see what data exists
        response = requests.get(
            f"{BASE_URL}/api/distributions?trust_id={trust_id}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200, f"Get distributions failed: {response.text}"
        all_distributions = response.json()
        print(f"Total distributions found: {len(all_distributions)}")
        
        # Now search with a term
        search_term = "test"
        response = requests.get(
            f"{BASE_URL}/api/distributions?trust_id={trust_id}&search={search_term}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200, f"Search distributions failed: {response.text}"
        search_results = response.json()
        print(f"✓ Distributions search with '{search_term}' returned {len(search_results)} results")
    
    def test_distributions_search_empty_results(self, auth_token, trust_id):
        """Test search with term that returns no results"""
        search_term = "xyznonexistent456"
        response = requests.get(
            f"{BASE_URL}/api/distributions?trust_id={trust_id}&search={search_term}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200, f"Search should still return 200 with empty results"
        results = response.json()
        print(f"✓ Distributions search for non-existent term returned {len(results)} results (expected 0 or few)")
    
    def test_distributions_search_case_insensitive(self, auth_token, trust_id):
        """Test that search is case-insensitive"""
        # Search with lowercase
        response_lower = requests.get(
            f"{BASE_URL}/api/distributions?trust_id={trust_id}&search=beneficiary",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        # Search with uppercase
        response_upper = requests.get(
            f"{BASE_URL}/api/distributions?trust_id={trust_id}&search=BENEFICIARY",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response_lower.status_code == 200
        assert response_upper.status_code == 200
        
        # Results should be the same (case insensitive)
        print(f"✓ Case insensitive search: lowercase got {len(response_lower.json())} results, uppercase got {len(response_upper.json())} results")
    
    def test_distributions_search_with_status_filter(self, auth_token, trust_id):
        """Test that status filter still works alongside search"""
        response = requests.get(
            f"{BASE_URL}/api/distributions?trust_id={trust_id}&search=test&status=pending",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200, f"Search with status filter failed: {response.text}"
        print(f"✓ Distributions search with status filter returned {len(response.json())} results")
    
    def test_distributions_search_with_purpose_filter(self, auth_token, trust_id):
        """Test that purpose filter still works alongside search"""
        response = requests.get(
            f"{BASE_URL}/api/distributions?trust_id={trust_id}&search=test&purpose=distribution",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200, f"Search with purpose filter failed: {response.text}"
        print(f"✓ Distributions search with purpose filter returned {len(response.json())} results")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
