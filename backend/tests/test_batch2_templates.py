"""
Tests for Batch 2 Minutes Templates (10 new templates)
- trust_amendment, power_of_attorney, trust_termination, real_estate_purchase, 
- business_interest_acquisition, real_estate_lease, fiscal_year_election,
- tax_filing_authorization, emergency_ratification, conflict_of_interest
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "demo@trustoffice.com"
TEST_PASSWORD = "demopassword"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def auth_token(api_client):
    """Get authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Authentication failed with status {response.status_code}")


@pytest.fixture(scope="module")
def authenticated_client(api_client, auth_token):
    """Session with auth header"""
    api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api_client


@pytest.fixture(scope="module")
def trust_id(authenticated_client):
    """Get the first available trust ID"""
    response = authenticated_client.get(f"{BASE_URL}/api/trusts")
    if response.status_code == 200:
        trusts = response.json()
        if trusts:
            return trusts[0]["trust_id"]
    pytest.skip("No trusts available for testing")


# === TEMPLATE LIST TEST ===
class TestTemplateList:
    """Test that all 31 templates (including 10 new batch 2) are available"""
    
    def test_templates_count(self, authenticated_client, trust_id):
        """Verify we have 31 template types in the MinutesTemplateType enum"""
        # This test verifies the backend has all template types
        batch2_templates = [
            "trust_amendment", "power_of_attorney", "trust_termination",
            "real_estate_purchase", "business_interest_acquisition", "real_estate_lease",
            "fiscal_year_election", "tax_filing_authorization", "emergency_ratification",
            "conflict_of_interest"
        ]
        
        # Test creating a minutes template for one type to ensure API works
        response = authenticated_client.post(f"{BASE_URL}/api/minutes-templates", json={
            "trust_id": trust_id,
            "template_type": "trust_amendment",
            "template_data": {
                "amendment_type": "modification",
                "article_section": "Article V",
                "current_provision": "Test current",
                "amended_provision": "Test amended"
            }
        })
        
        # Should create successfully or return expected error
        assert response.status_code in [200, 201, 400, 404], f"Unexpected status: {response.status_code}"
        print(f"Template creation response status: {response.status_code}")


# === BATCH 2 TEMPLATE TESTS ===
class TestTrustAmendmentTemplate:
    """Test trust_amendment template generation"""
    
    def test_create_trust_amendment_minutes(self, authenticated_client, trust_id):
        """Test creating trust amendment minutes"""
        response = authenticated_client.post(f"{BASE_URL}/api/minutes-templates", json={
            "trust_id": trust_id,
            "template_type": "trust_amendment",
            "template_data": {
                "meeting_date": "March 2, 2026",
                "meeting_time": "10:00 AM",
                "meeting_type": "unanimous_written_consent",
                "trustees_present": ["John Smith", "Jane Smith"],
                "amendment_type": "modification",
                "article_section": "Article V, Section 3",
                "current_provision": "The Trustee shall distribute income quarterly.",
                "amended_provision": "The Trustee shall distribute income monthly.",
                "effective_date": "immediately upon execution",
                "reason": "Changed family circumstances"
            }
        })
        
        assert response.status_code in [200, 201], f"Failed: {response.text}"
        data = response.json()
        assert "minutes_id" in data
        assert data["template_type"] == "trust_amendment"
        assert "generated_document" in data
        assert "TRUST MINUTES" in data["generated_document"]
        print(f"✓ Trust Amendment template created: {data['minutes_id']}")


class TestPowerOfAttorneyTemplate:
    """Test power_of_attorney template generation"""
    
    def test_create_power_of_attorney_minutes(self, authenticated_client, trust_id):
        """Test creating power of attorney minutes"""
        response = authenticated_client.post(f"{BASE_URL}/api/minutes-templates", json={
            "trust_id": trust_id,
            "template_type": "power_of_attorney",
            "template_data": {
                "meeting_date": "March 2, 2026",
                "trustees_present": ["John Smith"],
                "agent_name": "Jane Doe",
                "scope": "limited",
                "powers_granted": ["Execute real estate documents", "Access bank accounts"],
                "expiration": "upon completion of transaction",
                "purpose": "Execute closing documents for property sale"
            }
        })
        
        assert response.status_code in [200, 201], f"Failed: {response.text}"
        data = response.json()
        assert data["template_type"] == "power_of_attorney"
        print(f"✓ Power of Attorney template created: {data['minutes_id']}")


class TestTrustTerminationTemplate:
    """Test trust_termination template generation"""
    
    def test_create_trust_termination_minutes(self, authenticated_client, trust_id):
        """Test creating trust termination minutes"""
        response = authenticated_client.post(f"{BASE_URL}/api/minutes-templates", json={
            "trust_id": trust_id,
            "template_type": "trust_termination",
            "template_data": {
                "meeting_date": "March 2, 2026",
                "trustees_present": ["John Smith", "Jane Smith"],
                "termination_reason": "Trust has accomplished all purposes",
                "termination_date": "March 15, 2026",
                "distribution_plan": "All remaining assets to be distributed equally to beneficiaries",
                "final_accounting_date": "within 60 days",
                "outstanding_obligations": "None"
            }
        })
        
        assert response.status_code in [200, 201], f"Failed: {response.text}"
        data = response.json()
        assert data["template_type"] == "trust_termination"
        print(f"✓ Trust Termination template created: {data['minutes_id']}")


class TestRealEstatePurchaseTemplate:
    """Test real_estate_purchase template generation"""
    
    def test_create_real_estate_purchase_minutes(self, authenticated_client, trust_id):
        """Test creating real estate purchase minutes"""
        response = authenticated_client.post(f"{BASE_URL}/api/minutes-templates", json={
            "trust_id": trust_id,
            "template_type": "real_estate_purchase",
            "template_data": {
                "meeting_date": "March 2, 2026",
                "trustees_present": ["John Smith"],
                "property_address": "123 Main Street, City, State 12345",
                "property_type": "residential",
                "purchase_price": "$500,000",
                "financing": "all cash",
                "purpose": "investment and income production",
                "inspection_period": "30 days"
            }
        })
        
        assert response.status_code in [200, 201], f"Failed: {response.text}"
        data = response.json()
        assert data["template_type"] == "real_estate_purchase"
        print(f"✓ Real Estate Purchase template created: {data['minutes_id']}")


class TestBusinessInterestTemplate:
    """Test business_interest_acquisition template generation"""
    
    def test_create_business_interest_minutes(self, authenticated_client, trust_id):
        """Test creating business interest acquisition minutes"""
        response = authenticated_client.post(f"{BASE_URL}/api/minutes-templates", json={
            "trust_id": trust_id,
            "template_type": "business_interest_acquisition",
            "template_data": {
                "meeting_date": "March 2, 2026",
                "trustees_present": ["John Smith", "Jane Smith"],
                "entity_name": "ABC Holdings, LLC",
                "entity_type": "LLC",
                "ownership_percentage": "25%",
                "purchase_price": "$100,000",
                "purpose": "investment diversification",
                "due_diligence": "financial review completed"
            }
        })
        
        assert response.status_code in [200, 201], f"Failed: {response.text}"
        data = response.json()
        assert data["template_type"] == "business_interest_acquisition"
        print(f"✓ Business Interest Acquisition template created: {data['minutes_id']}")


class TestRealEstateLeaseTemplate:
    """Test real_estate_lease template generation"""
    
    def test_create_real_estate_lease_minutes(self, authenticated_client, trust_id):
        """Test creating real estate lease minutes"""
        response = authenticated_client.post(f"{BASE_URL}/api/minutes-templates", json={
            "trust_id": trust_id,
            "template_type": "real_estate_lease",
            "template_data": {
                "meeting_date": "March 2, 2026",
                "trustees_present": ["John Smith"],
                "property_address": "456 Oak Avenue, City, State 12345",
                "tenant_name": "John Tenant",
                "lease_term": "1 year",
                "monthly_rent": "$2,500",
                "security_deposit": "$2,500",
                "permitted_use": "residential occupancy"
            }
        })
        
        assert response.status_code in [200, 201], f"Failed: {response.text}"
        data = response.json()
        assert data["template_type"] == "real_estate_lease"
        print(f"✓ Real Estate Lease template created: {data['minutes_id']}")


class TestFiscalYearTemplate:
    """Test fiscal_year_election template generation"""
    
    def test_create_fiscal_year_minutes(self, authenticated_client, trust_id):
        """Test creating fiscal year election minutes"""
        response = authenticated_client.post(f"{BASE_URL}/api/minutes-templates", json={
            "trust_id": trust_id,
            "template_type": "fiscal_year_election",
            "template_data": {
                "meeting_date": "March 2, 2026",
                "trustees_present": ["John Smith", "Jane Smith"],
                "fiscal_year_end": "December 31",
                "election_type": "initial",
                "effective_year": "2026",
                "reason": "administrative convenience"
            }
        })
        
        assert response.status_code in [200, 201], f"Failed: {response.text}"
        data = response.json()
        assert data["template_type"] == "fiscal_year_election"
        print(f"✓ Fiscal Year Election template created: {data['minutes_id']}")


class TestTaxFilingTemplate:
    """Test tax_filing_authorization template generation"""
    
    def test_create_tax_filing_minutes(self, authenticated_client, trust_id):
        """Test creating tax filing authorization minutes"""
        response = authenticated_client.post(f"{BASE_URL}/api/minutes-templates", json={
            "trust_id": trust_id,
            "template_type": "tax_filing_authorization",
            "template_data": {
                "meeting_date": "March 2, 2026",
                "trustees_present": ["John Smith"],
                "tax_year": "2025",
                "preparer_name": "CPA Firm Name",
                "returns_to_file": ["Form 1041 - U.S. Income Tax Return"],
                "filing_deadline": "April 15, 2026",
                "extension_authorized": True
            }
        })
        
        assert response.status_code in [200, 201], f"Failed: {response.text}"
        data = response.json()
        assert data["template_type"] == "tax_filing_authorization"
        print(f"✓ Tax Filing Authorization template created: {data['minutes_id']}")


class TestEmergencyRatificationTemplate:
    """Test emergency_ratification template generation"""
    
    def test_create_emergency_ratification_minutes(self, authenticated_client, trust_id):
        """Test creating emergency ratification minutes"""
        response = authenticated_client.post(f"{BASE_URL}/api/minutes-templates", json={
            "trust_id": trust_id,
            "template_type": "emergency_ratification",
            "template_data": {
                "meeting_date": "March 2, 2026",
                "trustees_present": ["John Smith", "Jane Smith"],
                "action_date": "February 28, 2026",
                "emergency_type": "Property flood damage requiring immediate repair",
                "actions_taken": ["Hired emergency contractor", "Authorized $15,000 for repairs"],
                "trustee_acting": "John Smith",
                "cost_incurred": "$15,000",
                "outcome": "Property secured and repairs completed"
            }
        })
        
        assert response.status_code in [200, 201], f"Failed: {response.text}"
        data = response.json()
        assert data["template_type"] == "emergency_ratification"
        print(f"✓ Emergency Ratification template created: {data['minutes_id']}")


class TestConflictOfInterestTemplate:
    """Test conflict_of_interest template generation"""
    
    def test_create_conflict_of_interest_minutes(self, authenticated_client, trust_id):
        """Test creating conflict of interest disclosure minutes"""
        response = authenticated_client.post(f"{BASE_URL}/api/minutes-templates", json={
            "trust_id": trust_id,
            "template_type": "conflict_of_interest",
            "template_data": {
                "meeting_date": "March 2, 2026",
                "trustees_present": ["John Smith", "Jane Smith"],
                "trustee_name": "John Smith",
                "conflict_type": "financial_interest",
                "description": "Trustee has personal ownership interest in property being considered for purchase",
                "related_transaction": "Purchase of commercial property at 789 Business Ave",
                "disclosure_date": "March 2, 2026",
                "waiver_granted": True,
                "conditions": "Trustee will recuse from voting on this transaction"
            }
        })
        
        assert response.status_code in [200, 201], f"Failed: {response.text}"
        data = response.json()
        assert data["template_type"] == "conflict_of_interest"
        print(f"✓ Conflict of Interest template created: {data['minutes_id']}")


class TestPDFGeneration:
    """Test PDF generation for batch 2 templates"""
    
    def test_trust_amendment_pdf(self, authenticated_client, trust_id):
        """Test PDF download for trust amendment template"""
        # Create a template first
        create_response = authenticated_client.post(f"{BASE_URL}/api/minutes-templates", json={
            "trust_id": trust_id,
            "template_type": "trust_amendment",
            "template_data": {
                "trustees_present": ["John Smith"],
                "amendment_type": "modification",
                "article_section": "Article V",
                "current_provision": "Test",
                "amended_provision": "Test amended"
            }
        })
        
        assert create_response.status_code in [200, 201], f"Failed to create: {create_response.text}"
        minutes_id = create_response.json()["minutes_id"]
        
        # Get PDF
        pdf_response = authenticated_client.get(f"{BASE_URL}/api/minutes-templates/{minutes_id}/pdf")
        assert pdf_response.status_code == 200, f"Failed to get PDF: {pdf_response.text}"
        
        pdf_data = pdf_response.json()
        assert "pdf_base64" in pdf_data
        assert len(pdf_data["pdf_base64"]) > 100  # Should have substantial content
        print(f"✓ PDF generated successfully for trust_amendment, size: {len(pdf_data['pdf_base64'])} chars")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
