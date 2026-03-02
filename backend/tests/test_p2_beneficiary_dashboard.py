"""
Tests for P2 Features:
1. GET /api/dashboard with optional trust_id query param
2. GET /api/beneficiaries/dashboard endpoint
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestDashboardTrustIdParam:
    """Test GET /api/dashboard with optional trust_id query parameter"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get token for authenticated tests"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@trustoffice.com",
            "password": "demopassword"
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.token = login_response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Get user's trusts
        trusts_response = requests.get(f"{BASE_URL}/api/trusts", headers=self.headers)
        assert trusts_response.status_code == 200
        self.trusts = trusts_response.json()
        assert len(self.trusts) > 0, "Demo user should have at least one trust"
    
    def test_dashboard_without_trust_id(self):
        """GET /api/dashboard without trust_id returns most recent trust's dashboard"""
        response = requests.get(f"{BASE_URL}/api/dashboard", headers=self.headers)
        assert response.status_code == 200, f"Dashboard failed: {response.text}"
        
        data = response.json()
        assert "trust_id" in data
        assert "trust_name" in data
        assert "health_score" in data
        assert "onboarding_state" in data
        assert "recent_activity" in data
        assert "stats" in data
        assert "governance_insights" in data
        print(f"Dashboard without trust_id returned trust: {data['trust_name']}")
    
    def test_dashboard_with_valid_trust_id(self):
        """GET /api/dashboard with valid trust_id returns specific trust's dashboard"""
        # Use the known test trust_id
        test_trust_id = "trust_b753cb8fe07f"
        
        # First verify this trust exists for the user
        trust_exists = any(t["trust_id"] == test_trust_id for t in self.trusts)
        
        if not trust_exists:
            # Use first available trust
            test_trust_id = self.trusts[0]["trust_id"]
        
        response = requests.get(
            f"{BASE_URL}/api/dashboard?trust_id={test_trust_id}", 
            headers=self.headers
        )
        assert response.status_code == 200, f"Dashboard with trust_id failed: {response.text}"
        
        data = response.json()
        assert data["trust_id"] == test_trust_id
        print(f"Dashboard with trust_id={test_trust_id} returned trust: {data['trust_name']}")
    
    def test_dashboard_with_invalid_trust_id(self):
        """GET /api/dashboard with invalid trust_id returns 404"""
        invalid_trust_id = "trust_nonexistent_id_12345"
        
        response = requests.get(
            f"{BASE_URL}/api/dashboard?trust_id={invalid_trust_id}", 
            headers=self.headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data
        print(f"Dashboard with invalid trust_id correctly returned 404: {data['detail']}")
    
    def test_dashboard_with_other_users_trust_id(self):
        """GET /api/dashboard with another user's trust_id returns 404 (access denied)"""
        # This trust_id doesn't belong to demo user
        other_trust_id = "trust_other_user_xyz123"
        
        response = requests.get(
            f"{BASE_URL}/api/dashboard?trust_id={other_trust_id}", 
            headers=self.headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("Dashboard correctly prevents access to other user's trust")


class TestBeneficiaryDashboard:
    """Test GET /api/beneficiaries/dashboard endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get token for authenticated tests"""
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@trustoffice.com",
            "password": "demopassword"
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.token = login_response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Get user's trusts
        trusts_response = requests.get(f"{BASE_URL}/api/trusts", headers=self.headers)
        assert trusts_response.status_code == 200
        self.trusts = trusts_response.json()
    
    def test_beneficiaries_dashboard_without_trust_id(self):
        """GET /api/beneficiaries/dashboard returns data for most recent trust"""
        response = requests.get(
            f"{BASE_URL}/api/beneficiaries/dashboard", 
            headers=self.headers
        )
        assert response.status_code == 200, f"Beneficiary dashboard failed: {response.text}"
        
        data = response.json()
        # Validate BeneficiaryDashboardResponse structure
        assert "trust_id" in data
        assert "trust_name" in data
        assert "total_authorized_units" in data
        assert "total_issued_units" in data
        assert "remaining_units" in data
        assert "unit_label" in data
        assert "active_certificate_count" in data
        assert "beneficiaries" in data
        assert "recent_transfers" in data
        
        assert isinstance(data["beneficiaries"], list)
        assert isinstance(data["recent_transfers"], list)
        
        print(f"Beneficiary dashboard: {data['trust_name']}")
        print(f"  - Total authorized: {data['total_authorized_units']}")
        print(f"  - Total issued: {data['total_issued_units']}")
        print(f"  - Remaining: {data['remaining_units']}")
        print(f"  - Beneficiaries count: {len(data['beneficiaries'])}")
        print(f"  - Active certificates: {data['active_certificate_count']}")
    
    def test_beneficiaries_dashboard_with_trust_id(self):
        """GET /api/beneficiaries/dashboard with trust_id returns specific trust data"""
        test_trust_id = "trust_b753cb8fe07f"
        
        # Check if trust exists
        trust_exists = any(t["trust_id"] == test_trust_id for t in self.trusts)
        if not trust_exists and len(self.trusts) > 0:
            test_trust_id = self.trusts[0]["trust_id"]
        
        response = requests.get(
            f"{BASE_URL}/api/beneficiaries/dashboard?trust_id={test_trust_id}", 
            headers=self.headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert data["trust_id"] == test_trust_id
        print(f"Beneficiary dashboard for {test_trust_id}: {len(data['beneficiaries'])} beneficiaries")
    
    def test_beneficiaries_dashboard_with_invalid_trust_id(self):
        """GET /api/beneficiaries/dashboard with invalid trust_id returns 404"""
        invalid_trust_id = "trust_invalid_xyz999"
        
        response = requests.get(
            f"{BASE_URL}/api/beneficiaries/dashboard?trust_id={invalid_trust_id}", 
            headers=self.headers
        )
        assert response.status_code == 404
        print("Beneficiary dashboard correctly returns 404 for invalid trust_id")
    
    def test_beneficiary_allocation_structure(self):
        """Verify BeneficiaryAllocation structure in response"""
        response = requests.get(
            f"{BASE_URL}/api/beneficiaries/dashboard", 
            headers=self.headers
        )
        assert response.status_code == 200
        
        data = response.json()
        
        if len(data["beneficiaries"]) > 0:
            # Check first beneficiary structure
            ben = data["beneficiaries"][0]
            assert "holder_name" in ben
            assert "total_units" in ben
            assert "percentage" in ben
            assert "certificate_count" in ben
            assert "certificates" in ben
            
            # Certificates should be a list
            assert isinstance(ben["certificates"], list)
            
            # If there are certificates, check certificate structure
            if len(ben["certificates"]) > 0:
                cert = ben["certificates"][0]
                assert "certificate_id" in cert
                assert "certificate_number" in cert
                assert "units" in cert
                assert "issue_date" in cert
                print(f"Verified beneficiary '{ben['holder_name']}' with {ben['certificate_count']} certificates")
        else:
            print("No beneficiaries to verify structure (trust has no certificates)")
    
    def test_recent_transfers_structure(self):
        """Verify recent_transfers structure in response"""
        response = requests.get(
            f"{BASE_URL}/api/beneficiaries/dashboard", 
            headers=self.headers
        )
        assert response.status_code == 200
        
        data = response.json()
        
        if len(data["recent_transfers"]) > 0:
            transfer = data["recent_transfers"][0]
            assert "transfer_id" in transfer
            assert "trust_id" in transfer
            assert "to_holder" in transfer
            assert "units" in transfer
            assert "reason" in transfer
            assert "created_at" in transfer
            # from_holder can be None for initial issuance
            assert "from_holder" in transfer
            print(f"Verified transfer structure: {transfer['units']} units to {transfer['to_holder']}")
        else:
            print("No recent transfers to verify (trust has no transfer history)")
    
    def test_beneficiaries_sorted_by_units_descending(self):
        """Verify beneficiaries are sorted by total_units descending"""
        response = requests.get(
            f"{BASE_URL}/api/beneficiaries/dashboard", 
            headers=self.headers
        )
        assert response.status_code == 200
        
        data = response.json()
        beneficiaries = data["beneficiaries"]
        
        if len(beneficiaries) > 1:
            for i in range(len(beneficiaries) - 1):
                assert beneficiaries[i]["total_units"] >= beneficiaries[i + 1]["total_units"], \
                    f"Beneficiaries not sorted: {beneficiaries[i]['total_units']} < {beneficiaries[i + 1]['total_units']}"
            print(f"Verified {len(beneficiaries)} beneficiaries are sorted by units (descending)")
        else:
            print("Not enough beneficiaries to verify sorting")
    
    def test_remaining_units_calculation(self):
        """Verify remaining_units = total_authorized - total_issued"""
        response = requests.get(
            f"{BASE_URL}/api/beneficiaries/dashboard", 
            headers=self.headers
        )
        assert response.status_code == 200
        
        data = response.json()
        expected_remaining = data["total_authorized_units"] - data["total_issued_units"]
        assert data["remaining_units"] == expected_remaining, \
            f"Remaining units mismatch: {data['remaining_units']} != {expected_remaining}"
        print(f"Verified: {data['total_authorized_units']} - {data['total_issued_units']} = {data['remaining_units']}")


class TestBeneficiaryDashboardUnauthenticated:
    """Test authentication requirements"""
    
    def test_dashboard_requires_auth(self):
        """GET /api/dashboard without auth returns 401"""
        response = requests.get(f"{BASE_URL}/api/dashboard")
        assert response.status_code == 401
        print("Dashboard endpoint correctly requires authentication")
    
    def test_beneficiaries_dashboard_requires_auth(self):
        """GET /api/beneficiaries/dashboard without auth returns 401"""
        response = requests.get(f"{BASE_URL}/api/beneficiaries/dashboard")
        assert response.status_code == 401
        print("Beneficiaries dashboard endpoint correctly requires authentication")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
