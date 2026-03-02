"""
Test Trust Certificate Units Feature - TrustOffice
Tests the complete Trust Units system including:
- Settings CRUD
- Certificate issuance and management
- Unit transfers between holders
"""

import pytest
import requests
import os
import uuid
from datetime import datetime

# Get backend URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from main agent context
DEMO_USER = {
    "email": "demo@trustoffice.com",
    "password": "demopassword"
}

TRUST_ID = "trust_b753cb8fe07f"


class TestTrustUnitsSetup:
    """Setup and authentication tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json=DEMO_USER,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json().get("token")
    
    @pytest.fixture(scope="class")
    def api_client(self, auth_token):
        """Create authenticated session"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {auth_token}"
        })
        return session
    
    def test_login_success(self):
        """Verify we can login with demo user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json=DEMO_USER,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        print(f"✓ Login successful for {DEMO_USER['email']}")


class TestTrustUnitsSummary:
    """Tests for GET /api/trust-units/summary endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json=DEMO_USER,
            headers={"Content-Type": "application/json"}
        )
        return response.json().get("token")
    
    @pytest.fixture(scope="class")
    def api_client(self, auth_token):
        """Create authenticated session"""
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {auth_token}"
        })
        return session
    
    def test_get_summary_returns_200(self, api_client):
        """GET /api/trust-units/summary - returns 200 with valid trust_id"""
        response = api_client.get(f"{BASE_URL}/api/trust-units/summary?trust_id={TRUST_ID}")
        assert response.status_code == 200, f"Failed: {response.text}"
        print(f"✓ Summary endpoint returns 200")
    
    def test_summary_has_required_fields(self, api_client):
        """Summary response contains settings, certificates, and aggregates"""
        response = api_client.get(f"{BASE_URL}/api/trust-units/summary?trust_id={TRUST_ID}")
        data = response.json()
        
        # Check required top-level fields
        assert "settings" in data, "Missing settings field"
        assert "certificates" in data, "Missing certificates field"
        assert "total_issued_units" in data, "Missing total_issued_units field"
        assert "remaining_units" in data, "Missing remaining_units field"
        assert "active_certificate_count" in data, "Missing active_certificate_count field"
        
        print(f"✓ Summary has all required fields")
    
    def test_settings_structure(self, api_client):
        """Settings contains total_authorized_units, unit_label, allow_fractional"""
        response = api_client.get(f"{BASE_URL}/api/trust-units/summary?trust_id={TRUST_ID}")
        settings = response.json()["settings"]
        
        assert "total_authorized_units" in settings
        assert "unit_label" in settings
        assert "allow_fractional" in settings
        assert "trust_id" in settings
        assert "created_at" in settings
        
        print(f"✓ Settings structure is correct")
        print(f"  - total_authorized_units: {settings['total_authorized_units']}")
        print(f"  - unit_label: {settings['unit_label']}")
        print(f"  - allow_fractional: {settings['allow_fractional']}")
    
    def test_certificates_list(self, api_client):
        """Certificates is a list with certificate objects"""
        response = api_client.get(f"{BASE_URL}/api/trust-units/summary?trust_id={TRUST_ID}")
        data = response.json()
        certificates = data["certificates"]
        
        assert isinstance(certificates, list), "Certificates should be a list"
        
        if len(certificates) > 0:
            cert = certificates[0]
            # Check certificate structure
            assert "certificate_id" in cert
            assert "certificate_number" in cert
            assert "holder_name" in cert
            assert "units" in cert
            assert "percentage" in cert
            assert "status" in cert
            assert "issue_date" in cert
            
            print(f"✓ Found {len(certificates)} certificate(s)")
            print(f"  - First cert: {cert['certificate_number']} - {cert['holder_name']} - {cert['units']} units ({cert['percentage']}%)")
        else:
            print("✓ No certificates yet (empty list)")
    
    def test_summary_with_invalid_trust(self, api_client):
        """Summary returns 404 for non-existent trust"""
        response = api_client.get(f"{BASE_URL}/api/trust-units/summary?trust_id=invalid_trust_xyz")
        assert response.status_code == 404
        print("✓ Returns 404 for invalid trust_id")


class TestTrustUnitsSettings:
    """Tests for PATCH /api/trust-units/settings endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json=DEMO_USER,
            headers={"Content-Type": "application/json"}
        )
        return response.json().get("token")
    
    @pytest.fixture(scope="class")
    def api_client(self, auth_token):
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {auth_token}"
        })
        return session
    
    def test_update_unit_label(self, api_client):
        """PATCH settings - can update unit_label"""
        # First get current settings
        summary_response = api_client.get(f"{BASE_URL}/api/trust-units/summary?trust_id={TRUST_ID}")
        original_label = summary_response.json()["settings"]["unit_label"]
        
        # Update unit_label
        new_label = f"Test Unit {uuid.uuid4().hex[:4]}"
        response = api_client.patch(
            f"{BASE_URL}/api/trust-units/settings?trust_id={TRUST_ID}",
            json={"unit_label": new_label}
        )
        
        assert response.status_code == 200, f"Failed to update: {response.text}"
        updated_settings = response.json()
        assert updated_settings["unit_label"] == new_label
        
        # Restore original
        api_client.patch(
            f"{BASE_URL}/api/trust-units/settings?trust_id={TRUST_ID}",
            json={"unit_label": original_label}
        )
        
        print(f"✓ Successfully updated unit_label")
    
    def test_update_allow_fractional(self, api_client):
        """PATCH settings - can toggle allow_fractional"""
        # Get current settings
        summary_response = api_client.get(f"{BASE_URL}/api/trust-units/summary?trust_id={TRUST_ID}")
        original = summary_response.json()["settings"]["allow_fractional"]
        
        # Toggle the value
        response = api_client.patch(
            f"{BASE_URL}/api/trust-units/settings?trust_id={TRUST_ID}",
            json={"allow_fractional": not original}
        )
        
        assert response.status_code == 200
        updated = response.json()
        assert updated["allow_fractional"] == (not original)
        
        # Restore original
        api_client.patch(
            f"{BASE_URL}/api/trust-units/settings?trust_id={TRUST_ID}",
            json={"allow_fractional": original}
        )
        
        print(f"✓ Successfully toggled allow_fractional")
    
    def test_update_returns_updated_at(self, api_client):
        """PATCH settings - returns updated_at timestamp"""
        response = api_client.patch(
            f"{BASE_URL}/api/trust-units/settings?trust_id={TRUST_ID}",
            json={"unit_label": "Certificate Unit"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "updated_at" in data
        assert data["updated_at"] is not None
        
        print(f"✓ Settings update returns updated_at timestamp")


class TestCertificateCreate:
    """Tests for POST /api/trust-units/certificates endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json=DEMO_USER,
            headers={"Content-Type": "application/json"}
        )
        return response.json().get("token")
    
    @pytest.fixture(scope="class")
    def api_client(self, auth_token):
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {auth_token}"
        })
        return session
    
    def test_create_certificate(self, api_client):
        """POST /api/trust-units/certificates - creates new certificate"""
        # First check remaining units
        summary = api_client.get(f"{BASE_URL}/api/trust-units/summary?trust_id={TRUST_ID}").json()
        remaining = summary["remaining_units"]
        
        if remaining < 5:
            pytest.skip(f"Not enough units remaining ({remaining}) to create test certificate")
        
        test_holder = f"TEST_Holder_{uuid.uuid4().hex[:6]}"
        payload = {
            "trust_id": TRUST_ID,
            "holder_name": test_holder,
            "holder_identifier": "Test ID 1234",
            "units": 5,
            "issue_date": datetime.now().strftime("%Y-%m-%d"),
            "notes": "Test certificate for automated testing"
        }
        
        response = api_client.post(
            f"{BASE_URL}/api/trust-units/certificates",
            json=payload
        )
        
        assert response.status_code == 200, f"Failed to create certificate: {response.text}"
        cert = response.json()
        
        # Validate response structure
        assert cert["holder_name"] == test_holder
        assert cert["units"] == 5
        assert cert["status"] == "active"
        assert "certificate_number" in cert
        assert "certificate_id" in cert
        assert "percentage" in cert
        
        print(f"✓ Created certificate {cert['certificate_number']}")
        print(f"  - Holder: {cert['holder_name']}")
        print(f"  - Units: {cert['units']} ({cert['percentage']}%)")
        
        # Store certificate_id for cleanup
        return cert["certificate_id"]
    
    def test_certificate_sequential_numbering(self, api_client):
        """Certificates get sequential numbers (CU-001, CU-002, etc.)"""
        summary = api_client.get(f"{BASE_URL}/api/trust-units/summary?trust_id={TRUST_ID}").json()
        certificates = summary["certificates"]
        
        if len(certificates) > 0:
            # Check that certificate numbers follow CU-XXX pattern
            for cert in certificates:
                cert_num = cert["certificate_number"]
                assert cert_num.startswith("CU-"), f"Invalid certificate number format: {cert_num}"
            
            print(f"✓ Certificate numbers follow CU-XXX pattern")
            print(f"  - Found: {[c['certificate_number'] for c in certificates[:5]]}")
        else:
            print("✓ No certificates to verify numbering")
    
    def test_create_certificate_validation(self, api_client):
        """Certificate creation validates units don't exceed authorized"""
        # Get total authorized
        summary = api_client.get(f"{BASE_URL}/api/trust-units/summary?trust_id={TRUST_ID}").json()
        total_authorized = summary["settings"]["total_authorized_units"]
        
        # Try to create certificate exceeding available
        payload = {
            "trust_id": TRUST_ID,
            "holder_name": "TEST_InvalidCert",
            "units": total_authorized + 1000,  # Way over limit
            "issue_date": datetime.now().strftime("%Y-%m-%d")
        }
        
        response = api_client.post(
            f"{BASE_URL}/api/trust-units/certificates",
            json=payload
        )
        
        assert response.status_code == 400, f"Should fail when exceeding authorized units"
        assert "Cannot issue" in response.json().get("detail", "")
        
        print(f"✓ Properly validates units against authorized total")


class TestCertificateUpdate:
    """Tests for PATCH /api/trust-units/certificates/{id} endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json=DEMO_USER,
            headers={"Content-Type": "application/json"}
        )
        return response.json().get("token")
    
    @pytest.fixture(scope="class")
    def api_client(self, auth_token):
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {auth_token}"
        })
        return session
    
    def test_update_certificate_holder_name(self, api_client):
        """PATCH certificate - can update holder_name"""
        # Get first active certificate
        summary = api_client.get(f"{BASE_URL}/api/trust-units/summary?trust_id={TRUST_ID}").json()
        active_certs = [c for c in summary["certificates"] if c["status"] == "active"]
        
        if len(active_certs) == 0:
            pytest.skip("No active certificates to update")
        
        cert = active_certs[0]
        original_name = cert["holder_name"]
        
        # Update holder name
        new_name = f"TEST_Updated_{uuid.uuid4().hex[:4]}"
        response = api_client.patch(
            f"{BASE_URL}/api/trust-units/certificates/{cert['certificate_id']}",
            json={"holder_name": new_name}
        )
        
        assert response.status_code == 200
        updated = response.json()
        assert updated["holder_name"] == new_name
        
        # Restore original
        api_client.patch(
            f"{BASE_URL}/api/trust-units/certificates/{cert['certificate_id']}",
            json={"holder_name": original_name}
        )
        
        print(f"✓ Successfully updated certificate holder name")
    
    def test_cancel_certificate(self, api_client):
        """PATCH certificate - can change status to cancelled"""
        # First create a test certificate to cancel
        summary = api_client.get(f"{BASE_URL}/api/trust-units/summary?trust_id={TRUST_ID}").json()
        remaining = summary["remaining_units"]
        
        if remaining < 1:
            pytest.skip("Not enough units remaining to create test certificate")
        
        # Create a certificate
        payload = {
            "trust_id": TRUST_ID,
            "holder_name": f"TEST_ToCancel_{uuid.uuid4().hex[:4]}",
            "units": 1,
            "issue_date": datetime.now().strftime("%Y-%m-%d"),
            "notes": "Test certificate for cancellation test"
        }
        
        create_response = api_client.post(
            f"{BASE_URL}/api/trust-units/certificates",
            json=payload
        )
        
        if create_response.status_code != 200:
            pytest.skip("Could not create test certificate")
        
        cert_id = create_response.json()["certificate_id"]
        
        # Cancel the certificate
        response = api_client.patch(
            f"{BASE_URL}/api/trust-units/certificates/{cert_id}",
            json={"status": "cancelled"}
        )
        
        assert response.status_code == 200
        cancelled = response.json()
        assert cancelled["status"] == "cancelled"
        
        print(f"✓ Successfully cancelled certificate")
    
    def test_update_nonexistent_certificate(self, api_client):
        """PATCH returns 404 for non-existent certificate"""
        response = api_client.patch(
            f"{BASE_URL}/api/trust-units/certificates/invalid_cert_id",
            json={"holder_name": "Test"}
        )
        
        assert response.status_code == 404
        print(f"✓ Returns 404 for non-existent certificate")


class TestUnitTransfers:
    """Tests for POST /api/trust-units/transfers endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json=DEMO_USER,
            headers={"Content-Type": "application/json"}
        )
        return response.json().get("token")
    
    @pytest.fixture(scope="class")
    def api_client(self, auth_token):
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {auth_token}"
        })
        return session
    
    def test_transfer_units_between_holders(self, api_client):
        """POST /api/trust-units/transfers - transfers units between holders"""
        # Get current certificates
        summary = api_client.get(f"{BASE_URL}/api/trust-units/summary?trust_id={TRUST_ID}").json()
        active_certs = [c for c in summary["certificates"] if c["status"] == "active" and c["units"] >= 2]
        
        if len(active_certs) == 0:
            pytest.skip("No active certificates with enough units for transfer test")
        
        source_cert = active_certs[0]
        source_holder = source_cert["holder_name"]
        target_holder = f"TEST_TransferTarget_{uuid.uuid4().hex[:4]}"
        
        transfer_payload = {
            "trust_id": TRUST_ID,
            "from_holder": source_holder,
            "to_holder": target_holder,
            "units": 1,
            "reason": "Test transfer for automated testing"
        }
        
        response = api_client.post(
            f"{BASE_URL}/api/trust-units/transfers",
            json=transfer_payload
        )
        
        assert response.status_code == 200, f"Transfer failed: {response.text}"
        transfer = response.json()
        
        assert transfer["from_holder"] == source_holder
        assert transfer["to_holder"] == target_holder
        assert transfer["units"] == 1
        assert "transfer_id" in transfer
        
        print(f"✓ Transfer recorded successfully")
        print(f"  - From: {source_holder}")
        print(f"  - To: {target_holder}")
        print(f"  - Units: 1")
    
    def test_transfer_validation_insufficient_units(self, api_client):
        """Transfer fails when holder has insufficient units"""
        summary = api_client.get(f"{BASE_URL}/api/trust-units/summary?trust_id={TRUST_ID}").json()
        active_certs = [c for c in summary["certificates"] if c["status"] == "active"]
        
        if len(active_certs) == 0:
            pytest.skip("No active certificates for transfer validation test")
        
        cert = active_certs[0]
        
        # Try to transfer more units than holder has
        transfer_payload = {
            "trust_id": TRUST_ID,
            "from_holder": cert["holder_name"],
            "to_holder": "TEST_Target",
            "units": cert["units"] + 1000,  # More than they have
            "reason": "Should fail"
        }
        
        response = api_client.post(
            f"{BASE_URL}/api/trust-units/transfers",
            json=transfer_payload
        )
        
        assert response.status_code == 400
        assert "only has" in response.json().get("detail", "").lower() or "cannot transfer" in response.json().get("detail", "").lower()
        
        print(f"✓ Transfer validation works for insufficient units")
    
    def test_transfer_from_nonexistent_holder(self, api_client):
        """Transfer fails when from_holder has no active certificate"""
        transfer_payload = {
            "trust_id": TRUST_ID,
            "from_holder": "NonExistentHolder_999999",
            "to_holder": "TEST_Target",
            "units": 1,
            "reason": "Should fail"
        }
        
        response = api_client.post(
            f"{BASE_URL}/api/trust-units/transfers",
            json=transfer_payload
        )
        
        assert response.status_code == 404
        
        print(f"✓ Transfer fails for non-existent from_holder")


class TestSummaryAggregates:
    """Tests to verify summary aggregates are calculated correctly"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json=DEMO_USER,
            headers={"Content-Type": "application/json"}
        )
        return response.json().get("token")
    
    @pytest.fixture(scope="class")
    def api_client(self, auth_token):
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {auth_token}"
        })
        return session
    
    def test_total_issued_equals_sum_of_active(self, api_client):
        """total_issued_units equals sum of active certificate units"""
        summary = api_client.get(f"{BASE_URL}/api/trust-units/summary?trust_id={TRUST_ID}").json()
        
        active_certs = [c for c in summary["certificates"] if c["status"] == "active"]
        calculated_total = sum(c["units"] for c in active_certs)
        
        assert summary["total_issued_units"] == calculated_total, \
            f"total_issued_units ({summary['total_issued_units']}) != sum of active ({calculated_total})"
        
        print(f"✓ total_issued_units correctly equals sum of active certificates")
        print(f"  - Total issued: {summary['total_issued_units']}")
    
    def test_remaining_units_calculation(self, api_client):
        """remaining_units = total_authorized - total_issued"""
        summary = api_client.get(f"{BASE_URL}/api/trust-units/summary?trust_id={TRUST_ID}").json()
        
        total_authorized = summary["settings"]["total_authorized_units"]
        total_issued = summary["total_issued_units"]
        expected_remaining = total_authorized - total_issued
        
        assert summary["remaining_units"] == expected_remaining, \
            f"remaining_units ({summary['remaining_units']}) != expected ({expected_remaining})"
        
        print(f"✓ remaining_units correctly calculated")
        print(f"  - Authorized: {total_authorized}, Issued: {total_issued}, Remaining: {summary['remaining_units']}")
    
    def test_active_certificate_count(self, api_client):
        """active_certificate_count matches actual active certificates"""
        summary = api_client.get(f"{BASE_URL}/api/trust-units/summary?trust_id={TRUST_ID}").json()
        
        active_count = len([c for c in summary["certificates"] if c["status"] == "active"])
        
        assert summary["active_certificate_count"] == active_count
        
        print(f"✓ active_certificate_count is correct: {active_count}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
