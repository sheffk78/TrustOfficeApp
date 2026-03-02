"""
Test suite for POST /api/trust-units/bootstrap-from-minutes/{minutes_id} endpoint

This endpoint creates Trust Unit Certificates from a 'Designation of Beneficiaries' minutes record.
Features:
- Reads template_data.total_units and beneficiaries from minutes
- Creates trust_units_settings if needed with total_authorized = template_data.total_units
- Creates certificate for each beneficiary with sequential numbering
- Uses meeting_date as issue_date
- Validates wrong template type returns 400
- Validates sum of units doesn't exceed total_authorized
- Prevents duplicate creation (returns error on second call)
"""

import pytest
import requests
import os
import uuid
from datetime import datetime

# Get base URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://trustoffice-preview-1.preview.emergentagent.com').rstrip('/')

# Test credentials
TEST_EMAIL = "demo@trustoffice.com"
TEST_PASSWORD = "demopassword"
TEST_TRUST_ID = "trust_b753cb8fe07f"

# Non-designation minutes for wrong template type test (disposition_of_asset)
NON_DESIGNATION_MINUTES_ID = "min_08c63adff72e"

# Already bootstrapped minutes (should return duplicate error)
# Using the minutes we bootstrapped in manual testing: min_34f729dfe9ec
ALREADY_BOOTSTRAPPED_MINUTES_ID = "min_34f729dfe9ec"


class TestBootstrapFromMinutesEndpoint:
    """Tests for POST /api/trust-units/bootstrap-from-minutes/{minutes_id}"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Authenticate
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        
        if response.status_code == 200:
            token = response.json().get("token")
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        else:
            pytest.skip("Authentication failed - skipping tests")
    
    def test_wrong_template_type_returns_400(self):
        """Test that non-designation minutes returns 400 error"""
        response = self.session.post(
            f"{BASE_URL}/api/trust-units/bootstrap-from-minutes/{NON_DESIGNATION_MINUTES_ID}"
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}. Response: {response.text}"
        data = response.json()
        assert "detail" in data
        # Should indicate wrong template type
        assert "designation" in data["detail"].lower() or "template" in data["detail"].lower()
        print(f"✓ Wrong template type correctly returns 400: {data['detail']}")
    
    def test_duplicate_creation_returns_400(self):
        """Test that calling bootstrap twice on same minutes returns error"""
        response = self.session.post(
            f"{BASE_URL}/api/trust-units/bootstrap-from-minutes/{ALREADY_BOOTSTRAPPED_MINUTES_ID}"
        )
        
        assert response.status_code == 400, f"Expected 400 for duplicate, got {response.status_code}. Response: {response.text}"
        data = response.json()
        assert "detail" in data
        # Should mention already created or duplicate
        assert "already" in data["detail"].lower() or "duplicate" in data["detail"].lower() or "once" in data["detail"].lower()
        print(f"✓ Duplicate creation correctly returns 400: {data['detail']}")
    
    def test_nonexistent_minutes_returns_404(self):
        """Test that non-existent minutes_id returns 404"""
        fake_minutes_id = f"min_{uuid.uuid4().hex[:12]}"
        response = self.session.post(
            f"{BASE_URL}/api/trust-units/bootstrap-from-minutes/{fake_minutes_id}"
        )
        
        assert response.status_code == 404, f"Expected 404 for non-existent minutes, got {response.status_code}"
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()
        print(f"✓ Non-existent minutes correctly returns 404: {data['detail']}")
    
    def test_successful_bootstrap_with_fresh_minutes(self):
        """
        Test successful bootstrap from a fresh designation_of_beneficiaries minutes.
        
        Steps:
        1. Create a new designation_of_beneficiaries minutes with beneficiaries
        2. Call bootstrap endpoint
        3. Verify response contains expected fields
        4. Verify certificates were created
        """
        # First check current units state to determine available units
        summary_response = self.session.get(
            f"{BASE_URL}/api/trust-units/summary",
            params={"trust_id": TEST_TRUST_ID}
        )
        
        if summary_response.status_code != 200:
            pytest.skip(f"Could not get units summary: {summary_response.status_code}")
        
        summary = summary_response.json()
        remaining_units = summary.get("remaining_units", 0)
        
        # Skip if not enough remaining units
        if remaining_units < 6:
            pytest.skip(f"Not enough remaining units ({remaining_units}). Need at least 6 units.")
        
        # Step 1: Create a fresh designation_of_beneficiaries minutes with units fitting remaining
        unique_suffix = uuid.uuid4().hex[:6]
        meeting_date = datetime.now().strftime("%Y-%m-%d")
        
        # Use smaller units to fit within remaining
        unit_a = min(5, int(remaining_units / 3))
        unit_b = min(3, int(remaining_units / 3))
        
        if unit_a <= 0 or unit_b <= 0:
            pytest.skip(f"Not enough units to create meaningful test")
        
        minutes_payload = {
            "trust_id": TEST_TRUST_ID,
            "template_type": "designation_of_beneficiaries",
            "template_data": {
                "minute_number": f"TEST-{unique_suffix}",
                "meeting_date": meeting_date,
                "meeting_time": "10:00 AM",
                "meeting_location": "Test Location",
                "meeting_type": "unanimous_written_consent",
                "trustees_present": ["Test Trustee"],
                "total_units": 100,  # Total units in designation
                "beneficiaries": [
                    {"name": f"Test Beneficiary A {unique_suffix}", "units": unit_a, "relationship": "child"},
                    {"name": f"Test Beneficiary B {unique_suffix}", "units": unit_b, "relationship": "spouse"}
                ]
            }
        }
        
        # Create minutes
        create_response = self.session.post(
            f"{BASE_URL}/api/minutes-templates",
            json=minutes_payload
        )
        
        if create_response.status_code not in [200, 201]:
            pytest.skip(f"Could not create test minutes: {create_response.status_code} - {create_response.text}")
        
        new_minutes = create_response.json()
        new_minutes_id = new_minutes["minutes_id"]
        print(f"✓ Created test minutes: {new_minutes_id}")
        
        # Step 2: Call bootstrap endpoint
        bootstrap_response = self.session.post(
            f"{BASE_URL}/api/trust-units/bootstrap-from-minutes/{new_minutes_id}"
        )
        
        # Step 3: Verify success response
        assert bootstrap_response.status_code == 200, f"Expected 200, got {bootstrap_response.status_code}. Response: {bootstrap_response.text}"
        
        data = bootstrap_response.json()
        
        # Verify response structure
        assert data.get("success") == True, "Expected success=true"
        assert "message" in data, "Expected message field"
        assert data.get("minutes_id") == new_minutes_id, f"Expected minutes_id={new_minutes_id}"
        assert data.get("trust_id") == TEST_TRUST_ID, f"Expected trust_id={TEST_TRUST_ID}"
        assert "total_authorized_units" in data, "Expected total_authorized_units field"
        assert "certificates_created" in data, "Expected certificates_created field"
        assert "certificates" in data, "Expected certificates array"
        assert "total_issued_units" in data, "Expected total_issued_units field"
        assert "remaining_units" in data, "Expected remaining_units field"
        
        print(f"✓ Response structure validated")
        print(f"  - success: {data['success']}")
        print(f"  - message: {data['message']}")
        print(f"  - minutes_id: {data['minutes_id']}")
        print(f"  - trust_id: {data['trust_id']}")
        print(f"  - total_authorized_units: {data['total_authorized_units']}")
        print(f"  - certificates_created: {data['certificates_created']}")
        print(f"  - total_issued_units: {data['total_issued_units']}")
        print(f"  - remaining_units: {data['remaining_units']}")
        
        # Verify 2 certificates created for 2 beneficiaries
        assert data["certificates_created"] == 2, f"Expected 2 certificates, got {data['certificates_created']}"
        assert len(data["certificates"]) == 2, f"Expected 2 certificates in array, got {len(data['certificates'])}"
        
        # Verify total_issued_units matches sum of beneficiary units
        expected_total = unit_a + unit_b
        assert data["total_issued_units"] == expected_total, f"Expected total_issued_units={expected_total}, got {data['total_issued_units']}"
        
        print(f"✓ Certificates count validated: {data['certificates_created']}")
        
        # Verify each certificate has required fields
        for cert in data["certificates"]:
            assert "certificate_id" in cert, "Certificate missing certificate_id"
            assert "holder_name" in cert, "Certificate missing holder_name"
            assert "units" in cert, "Certificate missing units"
            assert "certificate_number" in cert, "Certificate missing certificate_number"
            assert "status" in cert, "Certificate missing status"
            assert "issue_date" in cert, "Certificate missing issue_date"
            assert "percentage" in cert, "Certificate missing percentage"
            
            # Verify issue_date matches meeting_date
            assert cert["issue_date"] == meeting_date, f"Expected issue_date={meeting_date}, got {cert['issue_date']}"
            
            # Verify status is active
            assert cert["status"] == "active", f"Expected status=active, got {cert['status']}"
            
            # Verify certificate_number format (CU-XXX)
            assert cert["certificate_number"].startswith("CU-"), f"Expected certificate_number to start with CU-, got {cert['certificate_number']}"
        
        print(f"✓ All certificate fields validated")
        print(f"  - Certificate numbers: {[c['certificate_number'] for c in data['certificates']]}")
        print(f"  - Holders: {[c['holder_name'] for c in data['certificates']]}")
        print(f"  - Units: {[c['units'] for c in data['certificates']]}")
        
        # Step 4: Verify calling again returns duplicate error
        duplicate_response = self.session.post(
            f"{BASE_URL}/api/trust-units/bootstrap-from-minutes/{new_minutes_id}"
        )
        
        assert duplicate_response.status_code == 400, f"Expected 400 for duplicate call, got {duplicate_response.status_code}"
        dup_data = duplicate_response.json()
        assert "already" in dup_data["detail"].lower() or "once" in dup_data["detail"].lower()
        print(f"✓ Duplicate call correctly rejected: {dup_data['detail']}")
        
        # Cleanup: Note - in production we would clean up test data
        print(f"\n✓ TEST PASSED: Bootstrap from minutes successful")
        print(f"  Created minutes_id: {new_minutes_id}")
        print(f"  Created {data['certificates_created']} certificates")
        
        return data


class TestBootstrapEdgeCases:
    """Edge case tests for bootstrap-from-minutes endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Authenticate
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        
        if response.status_code == 200:
            token = response.json().get("token")
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        else:
            pytest.skip("Authentication failed - skipping tests")
    
    def test_bootstrap_with_empty_beneficiaries_returns_400(self):
        """Test that minutes with no beneficiaries returns 400"""
        unique_suffix = uuid.uuid4().hex[:6]
        meeting_date = datetime.now().strftime("%Y-%m-%d")
        
        # Create minutes with empty beneficiaries
        minutes_payload = {
            "trust_id": TEST_TRUST_ID,
            "template_type": "designation_of_beneficiaries",
            "template_data": {
                "minute_number": f"EMPTY-{unique_suffix}",
                "meeting_date": meeting_date,
                "trustees_present": ["Test Trustee"],
                "total_units": 100,
                "beneficiaries": []  # Empty array
            }
        }
        
        create_response = self.session.post(
            f"{BASE_URL}/api/minutes-templates",
            json=minutes_payload
        )
        
        if create_response.status_code not in [200, 201]:
            pytest.skip(f"Could not create test minutes: {create_response.status_code}")
        
        minutes_id = create_response.json()["minutes_id"]
        
        # Try to bootstrap
        bootstrap_response = self.session.post(
            f"{BASE_URL}/api/trust-units/bootstrap-from-minutes/{minutes_id}"
        )
        
        assert bootstrap_response.status_code == 400, f"Expected 400 for empty beneficiaries, got {bootstrap_response.status_code}"
        data = bootstrap_response.json()
        assert "beneficiar" in data["detail"].lower()
        print(f"✓ Empty beneficiaries correctly returns 400: {data['detail']}")
    
    def test_bootstrap_with_zero_units_beneficiary_skipped(self):
        """Test that beneficiaries with zero units are skipped"""
        # First check current units state to determine available units
        summary_response = self.session.get(
            f"{BASE_URL}/api/trust-units/summary",
            params={"trust_id": TEST_TRUST_ID}
        )
        
        if summary_response.status_code != 200:
            pytest.skip(f"Could not get units summary: {summary_response.status_code}")
        
        summary = summary_response.json()
        remaining_units = summary.get("remaining_units", 0)
        
        # Skip if not enough remaining units
        if remaining_units < 3:
            pytest.skip(f"Not enough remaining units ({remaining_units}). Need at least 3 units.")
        
        unique_suffix = uuid.uuid4().hex[:6]
        meeting_date = datetime.now().strftime("%Y-%m-%d")
        
        # Use a small number of units
        valid_units = min(3, int(remaining_units))
        
        # Create minutes with one valid and one zero-unit beneficiary
        minutes_payload = {
            "trust_id": TEST_TRUST_ID,
            "template_type": "designation_of_beneficiaries",
            "template_data": {
                "minute_number": f"ZERO-{unique_suffix}",
                "meeting_date": meeting_date,
                "trustees_present": ["Test Trustee"],
                "total_units": 100,
                "beneficiaries": [
                    {"name": f"Valid Beneficiary {unique_suffix}", "units": valid_units},
                    {"name": f"Zero Units Beneficiary {unique_suffix}", "units": 0}  # Should be skipped
                ]
            }
        }
        
        create_response = self.session.post(
            f"{BASE_URL}/api/minutes-templates",
            json=minutes_payload
        )
        
        if create_response.status_code not in [200, 201]:
            pytest.skip(f"Could not create test minutes: {create_response.status_code}")
        
        minutes_id = create_response.json()["minutes_id"]
        
        # Bootstrap
        bootstrap_response = self.session.post(
            f"{BASE_URL}/api/trust-units/bootstrap-from-minutes/{minutes_id}"
        )
        
        assert bootstrap_response.status_code == 200, f"Expected 200, got {bootstrap_response.status_code}"
        data = bootstrap_response.json()
        
        # Should only create 1 certificate (the valid one, not the zero-unit one)
        assert data["certificates_created"] == 1, f"Expected 1 certificate, got {data['certificates_created']}"
        assert data["total_issued_units"] == valid_units, f"Expected {valid_units} units, got {data['total_issued_units']}"
        print(f"✓ Zero-unit beneficiary correctly skipped: {data['certificates_created']} certificate(s) created")


class TestBootstrapResponseFields:
    """Verify all response fields are correct per requirements"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Authenticate
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        
        if response.status_code == 200:
            token = response.json().get("token")
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        else:
            pytest.skip("Authentication failed - skipping tests")
    
    def test_response_contains_all_required_fields(self):
        """Verify response contains: success, message, trust_id, total_authorized_units, 
        certificates_created, certificates array, total_issued_units, remaining_units"""
        
        # First check current units state to determine available units
        summary_response = self.session.get(
            f"{BASE_URL}/api/trust-units/summary",
            params={"trust_id": TEST_TRUST_ID}
        )
        
        if summary_response.status_code != 200:
            pytest.skip(f"Could not get units summary: {summary_response.status_code}")
        
        summary = summary_response.json()
        remaining_units = summary.get("remaining_units", 0)
        
        # Skip if not enough remaining units
        if remaining_units < 2:
            pytest.skip(f"Not enough remaining units ({remaining_units}). Need at least 2 units.")
        
        unique_suffix = uuid.uuid4().hex[:6]
        meeting_date = datetime.now().strftime("%Y-%m-%d")
        
        # Use a small number of units
        valid_units = min(2, int(remaining_units))
        
        # Create a fresh minutes
        minutes_payload = {
            "trust_id": TEST_TRUST_ID,
            "template_type": "designation_of_beneficiaries",
            "template_data": {
                "minute_number": f"FIELDS-{unique_suffix}",
                "meeting_date": meeting_date,
                "trustees_present": ["Test Trustee"],
                "total_units": 100,
                "beneficiaries": [
                    {"name": f"Field Test Beneficiary {unique_suffix}", "units": valid_units}
                ]
            }
        }
        
        create_response = self.session.post(
            f"{BASE_URL}/api/minutes-templates",
            json=minutes_payload
        )
        
        if create_response.status_code not in [200, 201]:
            pytest.skip(f"Could not create test minutes: {create_response.status_code}")
        
        minutes_id = create_response.json()["minutes_id"]
        
        # Bootstrap
        bootstrap_response = self.session.post(
            f"{BASE_URL}/api/trust-units/bootstrap-from-minutes/{minutes_id}"
        )
        
        assert bootstrap_response.status_code == 200
        data = bootstrap_response.json()
        
        # Verify all required fields
        required_fields = [
            "success",
            "message", 
            "minutes_id",
            "trust_id",
            "total_authorized_units",
            "certificates_created",
            "certificates",
            "total_issued_units",
            "remaining_units"
        ]
        
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
            print(f"✓ Field present: {field} = {data[field]}")
        
        # Verify types
        assert isinstance(data["success"], bool), "success should be boolean"
        assert isinstance(data["message"], str), "message should be string"
        assert isinstance(data["minutes_id"], str), "minutes_id should be string"
        assert isinstance(data["trust_id"], str), "trust_id should be string"
        assert isinstance(data["total_authorized_units"], (int, float)), "total_authorized_units should be number"
        assert isinstance(data["certificates_created"], int), "certificates_created should be int"
        assert isinstance(data["certificates"], list), "certificates should be list"
        assert isinstance(data["total_issued_units"], (int, float)), "total_issued_units should be number"
        assert isinstance(data["remaining_units"], (int, float)), "remaining_units should be number"
        
        print(f"\n✓ All required fields present and correctly typed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
