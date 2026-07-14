# Test Audit Defense PDF Export - Phase 2D
# Tests the court-ready PDF generation endpoint for structural separation evidence

import pytest
import requests
import os
import io

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "contact@trustoffice.app"
ADMIN_PASSWORD = "TrustAdmin2026!"
TRUST_ID = "trust_2097657c7e1d"  # Smith Family Trust


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Authentication failed - skipping tests")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Return headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}"}


class TestAuditDefensePDFEndpoint:
    """Tests for GET /api/exports/audit-defense/{trust_id}"""

    def test_pdf_endpoint_returns_200(self, auth_headers):
        """Test that endpoint returns 200 for valid trust"""
        response = requests.get(
            f"{BASE_URL}/api/exports/audit-defense/{TRUST_ID}?days=365",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✓ PDF endpoint returns 200 for valid trust")

    def test_pdf_content_type(self, auth_headers):
        """Test that response has correct content type"""
        response = requests.get(
            f"{BASE_URL}/api/exports/audit-defense/{TRUST_ID}?days=365",
            headers=auth_headers
        )
        assert response.status_code == 200
        content_type = response.headers.get("Content-Type", "")
        assert "application/pdf" in content_type, f"Expected application/pdf, got {content_type}"
        print("✓ Response has correct content type: application/pdf")

    def test_pdf_content_disposition(self, auth_headers):
        """Test that response has attachment header for download"""
        response = requests.get(
            f"{BASE_URL}/api/exports/audit-defense/{TRUST_ID}?days=365",
            headers=auth_headers
        )
        assert response.status_code == 200
        content_disp = response.headers.get("Content-Disposition", "")
        assert "attachment" in content_disp, f"Expected attachment header, got {content_disp}"
        assert "audit_defense_" in content_disp, f"Expected filename with audit_defense_, got {content_disp}"
        assert ".pdf" in content_disp, f"Expected .pdf extension, got {content_disp}"
        print(f"✓ Content-Disposition header correct: {content_disp}")

    def test_pdf_is_valid(self, auth_headers):
        """Test that response is a valid PDF file"""
        response = requests.get(
            f"{BASE_URL}/api/exports/audit-defense/{TRUST_ID}?days=365",
            headers=auth_headers
        )
        assert response.status_code == 200
        # PDF files start with %PDF
        assert response.content[:4] == b'%PDF', "Response is not a valid PDF file"
        print("✓ Response is a valid PDF file (starts with %PDF)")

    def test_pdf_has_content(self, auth_headers):
        """Test that PDF has reasonable size (not empty)"""
        response = requests.get(
            f"{BASE_URL}/api/exports/audit-defense/{TRUST_ID}?days=365",
            headers=auth_headers
        )
        assert response.status_code == 200
        # PDF should be at least 5KB for a report with data
        assert len(response.content) > 5000, f"PDF too small: {len(response.content)} bytes"
        print(f"✓ PDF has content: {len(response.content)} bytes")

    def test_404_for_nonexistent_trust(self, auth_headers):
        """Test that endpoint returns 404 for non-existent trust"""
        response = requests.get(
            f"{BASE_URL}/api/exports/audit-defense/trust_nonexistent?days=365",
            headers=auth_headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()
        print("✓ Returns 404 for non-existent trust")

    def test_401_without_auth(self):
        """Test that endpoint requires authentication"""
        response = requests.get(
            f"{BASE_URL}/api/exports/audit-defense/{TRUST_ID}?days=365"
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Returns 401 without authentication")

    def test_days_parameter_works(self, auth_headers):
        """Test that days parameter is accepted"""
        # Test with different days values
        for days in [30, 90, 365]:
            response = requests.get(
                f"{BASE_URL}/api/exports/audit-defense/{TRUST_ID}?days={days}",
                headers=auth_headers
            )
            assert response.status_code == 200, f"Failed for days={days}"
        print("✓ Days parameter works for 30, 90, 365")


class TestAuditDefensePDFContent:
    """Tests for PDF content verification using pdfplumber"""

    @pytest.fixture(scope="class")
    def pdf_content(self, auth_headers):
        """Download PDF and extract text content"""
        try:
            import pdfplumber
        except ImportError:
            pytest.skip("pdfplumber not installed")
        
        response = requests.get(
            f"{BASE_URL}/api/exports/audit-defense/{TRUST_ID}?days=365",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        pdf_bytes = io.BytesIO(response.content)
        with pdfplumber.open(pdf_bytes) as pdf:
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text() or ""
                full_text += text + "\n"
            return {"text": full_text, "page_count": len(pdf.pages)}

    def test_pdf_has_title(self, pdf_content):
        """Test that PDF contains the title"""
        assert "AUDIT DEFENSE REPORT" in pdf_content["text"]
        print("✓ PDF contains title: AUDIT DEFENSE REPORT")

    def test_pdf_has_entity_structure_section(self, pdf_content):
        """Test that PDF contains entity structure section"""
        assert "1. ENTITY STRUCTURE" in pdf_content["text"]
        print("✓ PDF contains Section 1: ENTITY STRUCTURE")

    def test_pdf_has_transaction_summary_section(self, pdf_content):
        """Test that PDF contains transaction summary section"""
        assert "2. TRANSACTION SUMMARY BY ENTITY" in pdf_content["text"]
        print("✓ PDF contains Section 2: TRANSACTION SUMMARY BY ENTITY")

    def test_pdf_has_inter_entity_transfer_section(self, pdf_content):
        """Test that PDF contains inter-entity transfer log"""
        assert "3. INTER-ENTITY TRANSFER LOG" in pdf_content["text"]
        print("✓ PDF contains Section 3: INTER-ENTITY TRANSFER LOG")

    def test_pdf_has_separation_alerts_section(self, pdf_content):
        """Test that PDF contains separation alerts section"""
        assert "4. SEPARATION ALERTS" in pdf_content["text"]
        print("✓ PDF contains Section 4: SEPARATION ALERTS")

    def test_pdf_has_governance_actions_section(self, pdf_content):
        """Test that PDF contains governance actions section"""
        assert "5. LINKED GOVERNANCE ACTIONS" in pdf_content["text"]
        print("✓ PDF contains Section 5: LINKED GOVERNANCE ACTIONS")

    def test_pdf_has_health_score_section(self, pdf_content):
        """Test that PDF contains health score history section"""
        assert "6. GOVERNANCE HEALTH SCORE HISTORY" in pdf_content["text"]
        print("✓ PDF contains Section 6: GOVERNANCE HEALTH SCORE HISTORY")

    def test_pdf_has_confidentiality_notice(self, pdf_content):
        """Test that PDF contains confidentiality notice"""
        assert "CONFIDENTIAL" in pdf_content["text"]
        print("✓ PDF contains CONFIDENTIAL notice")

    def test_pdf_has_trust_name(self, pdf_content):
        """Test that PDF contains the trust name"""
        assert "Smith Family Trust" in pdf_content["text"]
        print("✓ PDF contains trust name: Smith Family Trust")

    def test_pdf_has_entities(self, pdf_content):
        """Test that PDF contains entity data"""
        # Check for entity names from Smith Family Trust
        assert "Smith Holdings LLC" in pdf_content["text"]
        print("✓ PDF contains entity data (Smith Holdings LLC)")

    def test_pdf_has_multiple_pages(self, pdf_content):
        """Test that PDF has multiple pages (comprehensive report)"""
        assert pdf_content["page_count"] >= 3, f"Expected at least 3 pages, got {pdf_content['page_count']}"
        print(f"✓ PDF has {pdf_content['page_count']} pages")

    def test_pdf_has_period_covered(self, pdf_content):
        """Test that PDF contains period covered"""
        assert "Period Covered:" in pdf_content["text"]
        print("✓ PDF contains Period Covered")

    def test_pdf_has_ein_data(self, pdf_content):
        """Test that PDF contains EIN data"""
        # Smith Family Trust has EIN 12-3456789
        assert "12-3456789" in pdf_content["text"] or "EIN" in pdf_content["text"]
        print("✓ PDF contains EIN data")

    def test_pdf_has_alert_counts(self, pdf_content):
        """Test that PDF contains alert counts"""
        assert "Active Alerts:" in pdf_content["text"]
        print("✓ PDF contains alert counts")

    def test_pdf_has_minutes_records(self, pdf_content):
        """Test that PDF contains minutes records section"""
        assert "Minutes Records" in pdf_content["text"]
        print("✓ PDF contains Minutes Records")

    def test_pdf_has_distribution_authorizations(self, pdf_content):
        """Test that PDF contains distribution authorizations"""
        assert "Distribution Authorizations" in pdf_content["text"]
        print("✓ PDF contains Distribution Authorizations")

    def test_pdf_has_compensation_payments(self, pdf_content):
        """Test that PDF contains compensation payments"""
        assert "Compensation Payments" in pdf_content["text"]
        print("✓ PDF contains Compensation Payments")
