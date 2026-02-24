"""
Test Benevolence Mode Feature - Backend API Tests
Tests the benevolence toggle in trust settings, benevolence CRUD endpoints,
summary endpoint, and template-options filtering based on benevolence_enabled flag.
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "test@trustoffice.com"
TEST_PASSWORD = "testpassword123"
TRUST_ID_WITH_BENEVOLENCE = "trust_f8896488ce03"  # Smith Family Trust with benevolence_enabled=true

class TestBenevolenceFeature:
    """Test suite for Benevolence Mode feature"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token before each test"""
        self.session = requests.Session()
        response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        if response.status_code == 200:
            token = response.json().get("token")
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        else:
            pytest.skip(f"Login failed: {response.status_code} - {response.text}")
    
    # ----- Trust Settings Benevolence Toggle Tests -----
    
    def test_get_trust_shows_benevolence_enabled(self):
        """Test that GET /trusts/{trust_id} returns benevolence_enabled field"""
        response = self.session.get(f"{BASE_URL}/api/trusts/{TRUST_ID_WITH_BENEVOLENCE}")
        assert response.status_code == 200
        data = response.json()
        assert "benevolence_enabled" in data
        print(f"Trust benevolence_enabled: {data.get('benevolence_enabled')}")
    
    def test_update_trust_benevolence_toggle(self):
        """Test that PUT /trusts/{trust_id} can update benevolence_enabled"""
        # First get current state
        get_response = self.session.get(f"{BASE_URL}/api/trusts/{TRUST_ID_WITH_BENEVOLENCE}")
        assert get_response.status_code == 200
        current_state = get_response.json().get("benevolence_enabled", False)
        
        # Toggle to opposite state
        new_state = not current_state
        update_response = self.session.put(
            f"{BASE_URL}/api/trusts/{TRUST_ID_WITH_BENEVOLENCE}",
            json={"benevolence_enabled": new_state}
        )
        assert update_response.status_code == 200
        updated_data = update_response.json()
        assert updated_data.get("benevolence_enabled") == new_state
        print(f"Successfully toggled benevolence_enabled to {new_state}")
        
        # Restore original state
        restore_response = self.session.put(
            f"{BASE_URL}/api/trusts/{TRUST_ID_WITH_BENEVOLENCE}",
            json={"benevolence_enabled": current_state}
        )
        assert restore_response.status_code == 200
        print(f"Restored benevolence_enabled to {current_state}")
    
    def test_update_trust_tax_status(self):
        """Test that PUT /trusts/{trust_id} can update tax_status"""
        update_response = self.session.put(
            f"{BASE_URL}/api/trusts/{TRUST_ID_WITH_BENEVOLENCE}",
            json={"tax_status": "501c3"}
        )
        assert update_response.status_code == 200
        updated_data = update_response.json()
        assert updated_data.get("tax_status") == "501c3"
        print(f"Tax status updated to: {updated_data.get('tax_status')}")
    
    # ----- Template Options Conditional Display Tests -----
    
    def test_template_options_shows_benevolence_when_enabled(self):
        """Test that GET /template-options includes benevolence_approval when trust has benevolence enabled"""
        # First ensure benevolence is enabled
        self.session.put(
            f"{BASE_URL}/api/trusts/{TRUST_ID_WITH_BENEVOLENCE}",
            json={"benevolence_enabled": True}
        )
        
        # Get templates with trust_id
        response = self.session.get(f"{BASE_URL}/api/template-options?trust_id={TRUST_ID_WITH_BENEVOLENCE}")
        assert response.status_code == 200
        templates = response.json()
        
        template_types = [t.get("type") for t in templates]
        assert "benevolence_approval" in template_types
        print(f"Found benevolence_approval template in options (trust has benevolence enabled)")
    
    def test_template_options_hides_benevolence_when_disabled(self):
        """Test that GET /template-options excludes benevolence_approval when trust has benevolence disabled"""
        # Disable benevolence for this test
        self.session.put(
            f"{BASE_URL}/api/trusts/{TRUST_ID_WITH_BENEVOLENCE}",
            json={"benevolence_enabled": False}
        )
        
        # Get templates with trust_id
        response = self.session.get(f"{BASE_URL}/api/template-options?trust_id={TRUST_ID_WITH_BENEVOLENCE}")
        assert response.status_code == 200
        templates = response.json()
        
        template_types = [t.get("type") for t in templates]
        assert "benevolence_approval" not in template_types
        print(f"Benevolence_approval template correctly hidden (trust has benevolence disabled)")
        
        # Restore benevolence enabled
        self.session.put(
            f"{BASE_URL}/api/trusts/{TRUST_ID_WITH_BENEVOLENCE}",
            json={"benevolence_enabled": True}
        )
    
    # ----- Benevolence Records CRUD Tests -----
    
    def test_get_benevolence_records_success(self):
        """Test GET /benevolence returns records for enabled trust"""
        # Ensure benevolence is enabled
        self.session.put(
            f"{BASE_URL}/api/trusts/{TRUST_ID_WITH_BENEVOLENCE}",
            json={"benevolence_enabled": True}
        )
        
        response = self.session.get(f"{BASE_URL}/api/benevolence?trust_id={TRUST_ID_WITH_BENEVOLENCE}")
        assert response.status_code == 200
        records = response.json()
        assert isinstance(records, list)
        print(f"GET /benevolence returned {len(records)} records")
    
    def test_create_benevolence_record_success(self):
        """Test POST /benevolence creates a new record"""
        # Ensure benevolence is enabled
        self.session.put(
            f"{BASE_URL}/api/trusts/{TRUST_ID_WITH_BENEVOLENCE}",
            json={"benevolence_enabled": True}
        )
        
        payload = {
            "trust_id": TRUST_ID_WITH_BENEVOLENCE,
            "beneficiary_name": "TEST_John Doe",
            "beneficiary_type": "individual",
            "purpose": "medical",
            "purpose_description": "Medical expenses for surgery",
            "amount": 500.00,
            "date": "2026-01-20",
            "approved_by": ["Trustee A", "Trustee B"],
            "approval_method": "unanimous",
            "notes": "Test benevolence record",
            "status": "approved"
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/benevolence",
            json=payload
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "record_id" in data
        assert data["beneficiary_name"] == "TEST_John Doe"
        assert data["amount"] == 500.00
        assert data["purpose"] == "medical"
        assert data["status"] == "approved"
        
        print(f"Created benevolence record: {data['record_id']}")
        
        # Cleanup - delete the test record
        delete_response = self.session.delete(f"{BASE_URL}/api/benevolence/{data['record_id']}")
        assert delete_response.status_code == 200
        print(f"Cleaned up test record {data['record_id']}")
    
    def test_create_benevolence_fails_when_disabled(self):
        """Test POST /benevolence fails when benevolence is not enabled"""
        # First disable benevolence
        self.session.put(
            f"{BASE_URL}/api/trusts/{TRUST_ID_WITH_BENEVOLENCE}",
            json={"benevolence_enabled": False}
        )
        
        payload = {
            "trust_id": TRUST_ID_WITH_BENEVOLENCE,
            "beneficiary_name": "TEST_Jane Doe",
            "beneficiary_type": "individual",
            "purpose": "housing",
            "purpose_description": "Housing assistance",
            "amount": 300.00,
            "date": "2026-01-20",
            "approved_by": ["Trustee A"],
            "approval_method": "single_trustee",
            "notes": "",
            "status": "approved"
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/benevolence",
            json=payload
        )
        assert response.status_code == 400
        error_data = response.json()
        assert "not enabled" in error_data.get("detail", "").lower()
        print(f"Correctly rejected: {error_data.get('detail')}")
        
        # Restore benevolence enabled
        self.session.put(
            f"{BASE_URL}/api/trusts/{TRUST_ID_WITH_BENEVOLENCE}",
            json={"benevolence_enabled": True}
        )
    
    def test_get_benevolence_with_filters(self):
        """Test GET /benevolence with filter parameters"""
        # Ensure benevolence is enabled
        self.session.put(
            f"{BASE_URL}/api/trusts/{TRUST_ID_WITH_BENEVOLENCE}",
            json={"benevolence_enabled": True}
        )
        
        # Test with purpose filter
        response = self.session.get(
            f"{BASE_URL}/api/benevolence?trust_id={TRUST_ID_WITH_BENEVOLENCE}&purpose=medical"
        )
        assert response.status_code == 200
        print("Filter by purpose=medical succeeded")
        
        # Test with status filter
        response = self.session.get(
            f"{BASE_URL}/api/benevolence?trust_id={TRUST_ID_WITH_BENEVOLENCE}&status=approved"
        )
        assert response.status_code == 200
        print("Filter by status=approved succeeded")
    
    # ----- Benevolence Summary Tests -----
    
    def test_get_benevolence_summary(self):
        """Test GET /benevolence/summary/{trust_id} returns summary data"""
        # Ensure benevolence is enabled
        self.session.put(
            f"{BASE_URL}/api/trusts/{TRUST_ID_WITH_BENEVOLENCE}",
            json={"benevolence_enabled": True}
        )
        
        response = self.session.get(f"{BASE_URL}/api/benevolence/summary/{TRUST_ID_WITH_BENEVOLENCE}")
        assert response.status_code == 200
        data = response.json()
        
        # Check summary structure
        assert "total_amount" in data
        assert "total_count" in data
        assert "by_purpose" in data
        print(f"Summary: total_count={data['total_count']}, total_amount={data['total_amount']}")
        print(f"By purpose: {data['by_purpose']}")
    
    def test_get_benevolence_summary_invalid_trust(self):
        """Test GET /benevolence/summary returns 404 for invalid trust"""
        response = self.session.get(f"{BASE_URL}/api/benevolence/summary/invalid_trust_id")
        assert response.status_code == 404
        print("Correctly returned 404 for invalid trust_id")
    
    # ----- Full CRUD Flow Test -----
    
    def test_benevolence_full_crud_flow(self):
        """Test complete Create, Read, Update, Delete flow for benevolence record"""
        # Ensure benevolence is enabled
        self.session.put(
            f"{BASE_URL}/api/trusts/{TRUST_ID_WITH_BENEVOLENCE}",
            json={"benevolence_enabled": True}
        )
        
        # CREATE
        create_payload = {
            "trust_id": TRUST_ID_WITH_BENEVOLENCE,
            "beneficiary_name": "TEST_CRUD_Person",
            "beneficiary_type": "individual",
            "purpose": "education",
            "purpose_description": "Educational scholarship",
            "amount": 1000.00,
            "date": "2026-01-21",
            "approved_by": ["Board"],
            "approval_method": "unanimous",
            "notes": "Full CRUD test",
            "status": "approved"
        }
        
        create_response = self.session.post(f"{BASE_URL}/api/benevolence", json=create_payload)
        assert create_response.status_code == 200
        record = create_response.json()
        record_id = record["record_id"]
        print(f"CREATE: {record_id}")
        
        # READ
        get_response = self.session.get(f"{BASE_URL}/api/benevolence/{record_id}")
        assert get_response.status_code == 200
        fetched = get_response.json()
        assert fetched["beneficiary_name"] == "TEST_CRUD_Person"
        assert fetched["amount"] == 1000.00
        print(f"READ: Verified record {record_id}")
        
        # UPDATE
        update_payload = {
            "amount": 1500.00,
            "status": "disbursed",
            "notes": "Updated - disbursed"
        }
        update_response = self.session.put(f"{BASE_URL}/api/benevolence/{record_id}", json=update_payload)
        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated["amount"] == 1500.00
        assert updated["status"] == "disbursed"
        print(f"UPDATE: amount=1500, status=disbursed")
        
        # VERIFY UPDATE persisted
        verify_response = self.session.get(f"{BASE_URL}/api/benevolence/{record_id}")
        assert verify_response.status_code == 200
        verified = verify_response.json()
        assert verified["amount"] == 1500.00
        assert verified["status"] == "disbursed"
        print("UPDATE VERIFIED: Changes persisted in database")
        
        # DELETE
        delete_response = self.session.delete(f"{BASE_URL}/api/benevolence/{record_id}")
        assert delete_response.status_code == 200
        print(f"DELETE: {record_id}")
        
        # VERIFY DELETE
        verify_delete = self.session.get(f"{BASE_URL}/api/benevolence/{record_id}")
        assert verify_delete.status_code == 404
        print("DELETE VERIFIED: Record no longer exists")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
