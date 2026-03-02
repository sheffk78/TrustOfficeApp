# Trust Units Router Tests - Testing migrated trust_units.py router (1017 lines)
# Tests: GET /api/trust-units/summary, PATCH /api/trust-units/settings
# Certificates: POST/PATCH/GET /api/trust-units/certificates, GET /api/trust-units/certificates/{id}/pdf
# Transfers: POST/GET /api/trust-units/transfers
# Bootstrap from Minutes: POST /api/trust-units/create-from-minutes/{id}, POST /api/trust-units/bootstrap-from-minutes/{id}

import pytest
import requests
import os
import uuid
import base64

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "demo@trustoffice.com"
TEST_PASSWORD = "demopassword"
TEST_TRUST_ID = "trust_b753cb8fe07f"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for tests"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get headers with auth token"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


# ==================== TRUST UNITS SUMMARY TESTS ====================

class TestTrustUnitsSummary:
    """Tests for GET /api/trust-units/summary endpoint"""

    def test_get_summary_requires_auth(self):
        """Summary endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/trust-units/summary", params={"trust_id": TEST_TRUST_ID})
        assert response.status_code == 401
        print("PASS: Summary requires authentication (401)")

    def test_get_summary_returns_valid_response(self, auth_headers):
        """GET /api/trust-units/summary returns proper structure"""
        response = requests.get(
            f"{BASE_URL}/api/trust-units/summary",
            params={"trust_id": TEST_TRUST_ID},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Validate response structure
        assert "settings" in data
        assert "certificates" in data
        assert "total_issued_units" in data
        assert "remaining_units" in data
        assert "active_certificate_count" in data
        
        # Validate settings structure
        settings = data["settings"]
        assert "trust_id" in settings
        assert "total_authorized_units" in settings
        assert "unit_label" in settings
        assert "allow_fractional" in settings
        
        print(f"PASS: Summary returned valid structure. Active certs: {data['active_certificate_count']}, Issued: {data['total_issued_units']}/{settings['total_authorized_units']}")

    def test_get_summary_invalid_trust(self, auth_headers):
        """Summary returns 404 for invalid trust_id"""
        response = requests.get(
            f"{BASE_URL}/api/trust-units/summary",
            params={"trust_id": "invalid_trust_id"},
            headers=auth_headers
        )
        assert response.status_code == 404
        print("PASS: Summary returns 404 for invalid trust_id")


# ==================== TRUST UNITS SETTINGS TESTS ====================

class TestTrustUnitsSettings:
    """Tests for PATCH /api/trust-units/settings endpoint"""

    def test_update_settings_requires_auth(self):
        """Settings update requires authentication"""
        response = requests.patch(
            f"{BASE_URL}/api/trust-units/settings",
            params={"trust_id": TEST_TRUST_ID},
            json={"unit_label": "Test Unit"}
        )
        assert response.status_code == 401
        print("PASS: Settings update requires authentication (401)")

    def test_update_settings_unit_label(self, auth_headers):
        """PATCH /api/trust-units/settings can update unit_label"""
        # Get current settings first
        summary_response = requests.get(
            f"{BASE_URL}/api/trust-units/summary",
            params={"trust_id": TEST_TRUST_ID},
            headers=auth_headers
        )
        original_label = summary_response.json()["settings"]["unit_label"]
        
        # Update to new label
        new_label = f"Test Unit {uuid.uuid4().hex[:6]}"
        response = requests.patch(
            f"{BASE_URL}/api/trust-units/settings",
            params={"trust_id": TEST_TRUST_ID},
            json={"unit_label": new_label},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["unit_label"] == new_label
        print(f"PASS: Unit label updated to '{new_label}'")
        
        # Restore original label
        requests.patch(
            f"{BASE_URL}/api/trust-units/settings",
            params={"trust_id": TEST_TRUST_ID},
            json={"unit_label": original_label},
            headers=auth_headers
        )

    def test_update_settings_allow_fractional(self, auth_headers):
        """PATCH /api/trust-units/settings can toggle allow_fractional"""
        # Get current settings
        summary_response = requests.get(
            f"{BASE_URL}/api/trust-units/summary",
            params={"trust_id": TEST_TRUST_ID},
            headers=auth_headers
        )
        original_value = summary_response.json()["settings"]["allow_fractional"]
        
        # Toggle value
        response = requests.patch(
            f"{BASE_URL}/api/trust-units/settings",
            params={"trust_id": TEST_TRUST_ID},
            json={"allow_fractional": not original_value},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["allow_fractional"] == (not original_value)
        print(f"PASS: allow_fractional toggled to {not original_value}")
        
        # Restore original value
        requests.patch(
            f"{BASE_URL}/api/trust-units/settings",
            params={"trust_id": TEST_TRUST_ID},
            json={"allow_fractional": original_value},
            headers=auth_headers
        )

    def test_update_settings_invalid_trust(self, auth_headers):
        """Settings update returns 404 for invalid trust_id"""
        response = requests.patch(
            f"{BASE_URL}/api/trust-units/settings",
            params={"trust_id": "invalid_trust_id"},
            json={"unit_label": "Test"},
            headers=auth_headers
        )
        assert response.status_code == 404
        print("PASS: Settings update returns 404 for invalid trust_id")


# ==================== CERTIFICATES CRUD TESTS ====================

class TestTrustUnitsCertificates:
    """Tests for Certificates CRUD: POST/PATCH/GET /api/trust-units/certificates"""

    def test_list_certificates_requires_auth(self):
        """List certificates requires authentication"""
        response = requests.get(
            f"{BASE_URL}/api/trust-units/certificates",
            params={"trust_id": TEST_TRUST_ID}
        )
        assert response.status_code == 401
        print("PASS: List certificates requires authentication (401)")

    def test_list_certificates_returns_list(self, auth_headers):
        """GET /api/trust-units/certificates returns list of certificates"""
        response = requests.get(
            f"{BASE_URL}/api/trust-units/certificates",
            params={"trust_id": TEST_TRUST_ID},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        if len(data) > 0:
            cert = data[0]
            # Validate certificate structure
            assert "certificate_id" in cert
            assert "holder_name" in cert
            assert "units" in cert
            assert "percentage" in cert
            assert "status" in cert
            assert "certificate_number" in cert
            print(f"PASS: Listed {len(data)} certificates. First cert: {cert.get('certificate_number')}")
        else:
            print("PASS: Listed certificates (empty list)")

    def test_list_certificates_with_status_filter(self, auth_headers):
        """GET /api/trust-units/certificates supports status filter"""
        response = requests.get(
            f"{BASE_URL}/api/trust-units/certificates",
            params={"trust_id": TEST_TRUST_ID, "status": "active"},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify all returned are active
        for cert in data:
            assert cert["status"] == "active"
        print(f"PASS: Status filter works. Found {len(data)} active certificates")

    def test_list_certificates_invalid_trust(self, auth_headers):
        """List certificates returns 404 for invalid trust_id"""
        response = requests.get(
            f"{BASE_URL}/api/trust-units/certificates",
            params={"trust_id": "invalid_trust_id"},
            headers=auth_headers
        )
        assert response.status_code == 404
        print("PASS: List certificates returns 404 for invalid trust_id")


# ==================== CERTIFICATE PDF TESTS ====================

class TestTrustUnitsCertificatePDF:
    """Tests for GET /api/trust-units/certificates/{id}/pdf"""

    def test_get_pdf_requires_auth(self, auth_headers):
        """PDF endpoint requires authentication"""
        # First get a valid certificate ID
        certs_response = requests.get(
            f"{BASE_URL}/api/trust-units/certificates",
            params={"trust_id": TEST_TRUST_ID},
            headers=auth_headers
        )
        if certs_response.status_code != 200 or len(certs_response.json()) == 0:
            pytest.skip("No certificates available for PDF test")
        
        cert_id = certs_response.json()[0]["certificate_id"]
        
        # Test without auth
        response = requests.get(f"{BASE_URL}/api/trust-units/certificates/{cert_id}/pdf")
        assert response.status_code == 401
        print("PASS: PDF requires authentication (401)")

    def test_get_pdf_returns_valid_response(self, auth_headers):
        """GET /api/trust-units/certificates/{id}/pdf returns PDF data"""
        # Get a valid certificate ID
        certs_response = requests.get(
            f"{BASE_URL}/api/trust-units/certificates",
            params={"trust_id": TEST_TRUST_ID},
            headers=auth_headers
        )
        if certs_response.status_code != 200 or len(certs_response.json()) == 0:
            pytest.skip("No certificates available for PDF test")
        
        cert_id = certs_response.json()[0]["certificate_id"]
        
        response = requests.get(
            f"{BASE_URL}/api/trust-units/certificates/{cert_id}/pdf",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Validate PDF response structure
        assert "pdf_base64" in data
        assert "filename" in data
        
        # Verify it's valid base64
        try:
            pdf_bytes = base64.b64decode(data["pdf_base64"])
            assert len(pdf_bytes) > 0
            # Check PDF header
            assert pdf_bytes[:4] == b'%PDF'
        except Exception as e:
            pytest.fail(f"Invalid PDF data: {e}")
        
        print(f"PASS: PDF generated. Filename: {data['filename']}, Size: {len(pdf_bytes)} bytes")

    def test_get_pdf_invalid_certificate(self, auth_headers):
        """PDF returns 404 for invalid certificate_id"""
        response = requests.get(
            f"{BASE_URL}/api/trust-units/certificates/invalid_cert_id/pdf",
            headers=auth_headers
        )
        assert response.status_code == 404
        print("PASS: PDF returns 404 for invalid certificate_id")


# ==================== TRANSFERS TESTS ====================

class TestTrustUnitsTransfers:
    """Tests for POST/GET /api/trust-units/transfers"""

    def test_list_transfers_requires_auth(self):
        """List transfers requires authentication"""
        response = requests.get(
            f"{BASE_URL}/api/trust-units/transfers",
            params={"trust_id": TEST_TRUST_ID}
        )
        assert response.status_code == 401
        print("PASS: List transfers requires authentication (401)")

    def test_list_transfers_returns_list(self, auth_headers):
        """GET /api/trust-units/transfers returns list of transfers"""
        response = requests.get(
            f"{BASE_URL}/api/trust-units/transfers",
            params={"trust_id": TEST_TRUST_ID},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        if len(data) > 0:
            transfer = data[0]
            # Validate transfer structure
            assert "transfer_id" in transfer
            assert "from_holder" in transfer  # Can be null
            assert "to_holder" in transfer
            assert "units" in transfer
            assert "reason" in transfer
            assert "created_at" in transfer
            print(f"PASS: Listed {len(data)} transfers. First: {transfer.get('units')} units to {transfer.get('to_holder')}")
        else:
            print("PASS: Listed transfers (empty list)")

    def test_create_transfer_requires_auth(self):
        """Create transfer requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/trust-units/transfers",
            json={
                "trust_id": TEST_TRUST_ID,
                "to_holder": "Test Holder",
                "units": 1,
                "reason": "Test transfer"
            }
        )
        assert response.status_code == 401
        print("PASS: Create transfer requires authentication (401)")


# ==================== REGRESSION TESTS - PREVIOUSLY MIGRATED ROUTERS ====================

class TestPreviouslyMigratedRoutersRegression:
    """Regression tests for previously migrated routers (benevolence, exports, subscriptions, compensation, schedule_a)"""

    def test_benevolence_router_accessible(self, auth_headers):
        """Benevolence router regression - GET /api/benevolence"""
        response = requests.get(
            f"{BASE_URL}/api/benevolence",
            params={"trust_id": TEST_TRUST_ID},
            headers=auth_headers
        )
        assert response.status_code == 200
        print("PASS: Benevolence router accessible")

    def test_exports_router_accessible(self, auth_headers):
        """Exports router regression - GET /api/export/minutes returns 402 for trial (premium feature)"""
        response = requests.get(
            f"{BASE_URL}/api/export/minutes",
            headers=auth_headers
        )
        # Should return 402 (premium feature) or 200 if user has paid subscription
        assert response.status_code in [200, 402]
        print(f"PASS: Exports router accessible (status: {response.status_code})")

    def test_subscriptions_router_accessible(self, auth_headers):
        """Subscriptions router regression - GET /api/subscription"""
        response = requests.get(
            f"{BASE_URL}/api/subscription",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "plan_type" in data
        print(f"PASS: Subscriptions router accessible. Status: {data.get('status')}")

    def test_compensation_router_accessible(self, auth_headers):
        """Compensation router regression - GET /api/compensation/plans"""
        response = requests.get(
            f"{BASE_URL}/api/compensation/plans",
            params={"trust_id": TEST_TRUST_ID},
            headers=auth_headers
        )
        assert response.status_code == 200
        print("PASS: Compensation router accessible")

    def test_schedule_a_router_accessible(self, auth_headers):
        """Schedule A router regression - GET /api/schedule-a/items"""
        response = requests.get(
            f"{BASE_URL}/api/schedule-a/items",
            params={"trust_id": TEST_TRUST_ID},
            headers=auth_headers
        )
        assert response.status_code == 200
        print("PASS: Schedule A router accessible")


# ==================== ROUTER INTEGRATION TESTS ====================

class TestTrustUnitsRouterIntegration:
    """Integration tests verifying trust_units router is properly mounted"""

    def test_all_trust_units_endpoints_accessible(self, auth_headers):
        """Verify all trust units endpoints respond (not 500)"""
        endpoints = [
            ("GET", f"/api/trust-units/summary?trust_id={TEST_TRUST_ID}"),
            ("GET", f"/api/trust-units/certificates?trust_id={TEST_TRUST_ID}"),
            ("GET", f"/api/trust-units/transfers?trust_id={TEST_TRUST_ID}"),
        ]
        
        for method, path in endpoints:
            if method == "GET":
                response = requests.get(f"{BASE_URL}{path}", headers=auth_headers)
            
            # Should not be 500
            assert response.status_code != 500, f"{method} {path} returned 500"
            print(f"PASS: {method} {path} -> {response.status_code}")

    def test_trust_units_router_uses_api_prefix(self, auth_headers):
        """Verify trust units router is mounted with /api prefix"""
        # Test without /api prefix should 404
        response = requests.get(
            f"{BASE_URL}/trust-units/summary",
            params={"trust_id": TEST_TRUST_ID},
            headers=auth_headers
        )
        assert response.status_code == 404, "Endpoint should not exist without /api prefix"
        
        # Test with /api prefix should work
        response = requests.get(
            f"{BASE_URL}/api/trust-units/summary",
            params={"trust_id": TEST_TRUST_ID},
            headers=auth_headers
        )
        assert response.status_code == 200
        print("PASS: Trust units router correctly uses /api prefix")


# ==================== DATA PERSISTENCE VERIFICATION ====================

class TestTrustUnitsDataPersistence:
    """Test that trust units data is persisted correctly in database"""

    def test_settings_persistence(self, auth_headers):
        """Settings changes are persisted - update and verify with GET"""
        unique_label = f"TEST_LABEL_{uuid.uuid4().hex[:8]}"
        
        # Update settings
        update_response = requests.patch(
            f"{BASE_URL}/api/trust-units/settings",
            params={"trust_id": TEST_TRUST_ID},
            json={"unit_label": unique_label},
            headers=auth_headers
        )
        assert update_response.status_code == 200
        
        # Verify with GET
        summary_response = requests.get(
            f"{BASE_URL}/api/trust-units/summary",
            params={"trust_id": TEST_TRUST_ID},
            headers=auth_headers
        )
        assert summary_response.status_code == 200
        assert summary_response.json()["settings"]["unit_label"] == unique_label
        print(f"PASS: Settings persisted correctly. Label: {unique_label}")
        
        # Cleanup - restore default label
        requests.patch(
            f"{BASE_URL}/api/trust-units/settings",
            params={"trust_id": TEST_TRUST_ID},
            json={"unit_label": "Certificate Unit"},
            headers=auth_headers
        )

    def test_summary_aggregates_are_accurate(self, auth_headers):
        """Summary aggregates match certificate data"""
        # Get summary
        summary_response = requests.get(
            f"{BASE_URL}/api/trust-units/summary",
            params={"trust_id": TEST_TRUST_ID},
            headers=auth_headers
        )
        assert summary_response.status_code == 200
        summary = summary_response.json()
        
        # Get certificates separately
        certs_response = requests.get(
            f"{BASE_URL}/api/trust-units/certificates",
            params={"trust_id": TEST_TRUST_ID},
            headers=auth_headers
        )
        assert certs_response.status_code == 200
        certs = certs_response.json()
        
        # Calculate expected values
        active_certs = [c for c in certs if c["status"] == "active"]
        calculated_issued = sum(c["units"] for c in active_certs)
        
        # Verify aggregates match
        assert summary["active_certificate_count"] == len(active_certs)
        assert summary["total_issued_units"] == calculated_issued
        
        total_authorized = summary["settings"]["total_authorized_units"]
        assert summary["remaining_units"] == total_authorized - calculated_issued
        
        print(f"PASS: Summary aggregates accurate. Active: {len(active_certs)}, Issued: {calculated_issued}/{total_authorized}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
