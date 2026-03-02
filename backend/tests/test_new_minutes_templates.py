"""
Test cases for the 10 new minutes templates:
- investment_policy
- loan_authorization
- insurance_authorization
- annual_review
- quarterly_review
- trustee_compensation
- trustee_resignation
- beneficiary_request_denial
- hems_distribution
- beneficiary_loan
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "demo@trustoffice.com"
TEST_PASSWORD = "demopassword"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["token"]


@pytest.fixture(scope="module")
def trust_id(auth_token):
    """Get a trust ID for testing"""
    response = requests.get(
        f"{BASE_URL}/api/trusts",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    trusts = response.json()
    assert len(trusts) > 0, "No trusts found for test user"
    return trusts[0]["trust_id"]


class TestTemplateOptions:
    """Test that all new templates appear in template options"""
    
    def test_template_options_returns_all_templates(self, auth_token):
        """Verify all 20+ templates are listed"""
        response = requests.get(
            f"{BASE_URL}/api/template-options",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        templates = response.json()
        
        # Check for the 10 new templates
        new_template_types = [
            "investment_policy", "loan_authorization", "insurance_authorization",
            "annual_review", "quarterly_review", "trustee_compensation",
            "trustee_resignation", "beneficiary_request_denial", 
            "hems_distribution", "beneficiary_loan"
        ]
        
        template_types_found = [t["type"] for t in templates]
        
        for template_type in new_template_types:
            assert template_type in template_types_found, f"Template {template_type} not found in options"
        
        print(f"✓ All 10 new templates found in template options")


class TestInvestmentPolicyTemplate:
    """Test investment_policy template generation"""
    
    def test_generate_investment_policy(self, auth_token, trust_id):
        """Test investment policy template generation"""
        template_data = {
            "minute_number": "2026-TEST-001",
            "meeting_date": "January 30, 2026",
            "meeting_time": "10:00 AM",
            "meeting_type": "unanimous_written_consent",
            "trustees_present": ["John Smith", "Jane Doe"],
            "trust_indenture_date": "January 1, 2020",
            "policy_type": "adopt",
            "risk_tolerance": "moderate",
            "asset_allocation": [
                {"asset_class": "Fixed Income", "percentage": 50},
                {"asset_class": "Equities", "percentage": 40},
                {"asset_class": "Cash", "percentage": 10}
            ],
            "investment_restrictions": ["No speculative trading", "No margin accounts"],
            "review_frequency": "annually"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/minutes-templates",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json={
                "trust_id": trust_id,
                "template_type": "investment_policy",
                "template_data": template_data
            }
        )
        
        assert response.status_code == 200, f"Failed: {response.text}"
        result = response.json()
        assert "minutes_id" in result
        assert "generated_document" in result
        assert "Investment Policy" in result["generated_document"]
        assert "RISK TOLERANCE: Moderate" in result["generated_document"]
        print(f"✓ Investment policy template generated: {result['minutes_id']}")
        return result["minutes_id"]


class TestLoanAuthorizationTemplate:
    """Test loan_authorization template generation"""
    
    def test_generate_loan_authorization_making(self, auth_token, trust_id):
        """Test loan authorization (making loan) template"""
        template_data = {
            "minute_number": "2026-TEST-002",
            "meeting_date": "January 30, 2026",
            "meeting_time": "10:00 AM",
            "meeting_type": "unanimous_written_consent",
            "trustees_present": ["John Smith"],
            "trust_indenture_date": "January 1, 2020",
            "loan_direction": "making",
            "borrower_name": "ABC Corporation",
            "loan_amount": 50000,
            "interest_rate": "AFR",
            "term_months": 60,
            "loan_purpose": "Business expansion",
            "collateral_description": "Promissory note"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/minutes-templates",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json={
                "trust_id": trust_id,
                "template_type": "loan_authorization",
                "template_data": template_data
            }
        )
        
        assert response.status_code == 200, f"Failed: {response.text}"
        result = response.json()
        assert "Authorization of Loan from Trust" in result["generated_document"]
        assert "ABC Corporation" in result["generated_document"]
        assert "$50,000.00" in result["generated_document"]
        print(f"✓ Loan authorization (making) template generated: {result['minutes_id']}")


class TestInsuranceAuthorizationTemplate:
    """Test insurance_authorization template generation"""
    
    def test_generate_insurance_authorization(self, auth_token, trust_id):
        """Test insurance authorization template"""
        template_data = {
            "minute_number": "2026-TEST-003",
            "meeting_date": "January 30, 2026",
            "meeting_time": "10:00 AM",
            "meeting_type": "unanimous_written_consent",
            "trustees_present": ["John Smith"],
            "trust_indenture_date": "January 1, 2020",
            "insurance_type": "property",
            "policy_action": "obtain",
            "insurer_name": "ABC Insurance Company",
            "coverage_amount": 500000,
            "premium_amount": 2500,
            "coverage_description": "Full property coverage for trust assets"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/minutes-templates",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json={
                "trust_id": trust_id,
                "template_type": "insurance_authorization",
                "template_data": template_data
            }
        )
        
        assert response.status_code == 200, f"Failed: {response.text}"
        result = response.json()
        assert "Insurance Policy Authorization" in result["generated_document"]
        assert "ABC Insurance Company" in result["generated_document"]
        assert "$500,000.00" in result["generated_document"]
        print(f"✓ Insurance authorization template generated: {result['minutes_id']}")


class TestAnnualReviewTemplate:
    """Test annual_review template generation"""
    
    def test_generate_annual_review(self, auth_token, trust_id):
        """Test annual review template"""
        template_data = {
            "minute_number": "2026-TEST-004",
            "meeting_date": "January 30, 2026",
            "meeting_time": "10:00 AM",
            "meeting_type": "in_person",
            "meeting_location": "123 Main St, City, State",
            "trustees_present": ["John Smith", "Jane Doe"],
            "trust_indenture_date": "January 1, 2020",
            "fiscal_year": "2025",
            "total_assets": 1000000,
            "total_income": 50000,
            "total_expenses": 15000,
            "total_distributions": 25000,
            "investment_return": "8.5%",
            "key_accomplishments": ["Completed property acquisition", "Updated beneficiary records"],
            "upcoming_priorities": ["Review investment policy", "Annual trustee meeting"],
            "governance_items": ["All trustees in good standing", "Insurance renewed"]
        }
        
        response = requests.post(
            f"{BASE_URL}/api/minutes-templates",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json={
                "trust_id": trust_id,
                "template_type": "annual_review",
                "template_data": template_data
            }
        )
        
        assert response.status_code == 200, f"Failed: {response.text}"
        result = response.json()
        assert "Annual Review" in result["generated_document"]
        assert "FISCAL YEAR 2025" in result["generated_document"]
        assert "$1,000,000.00" in result["generated_document"]
        print(f"✓ Annual review template generated: {result['minutes_id']}")


class TestQuarterlyReviewTemplate:
    """Test quarterly_review template generation"""
    
    def test_generate_quarterly_review(self, auth_token, trust_id):
        """Test quarterly review template"""
        template_data = {
            "minute_number": "2026-TEST-005",
            "meeting_date": "January 30, 2026",
            "meeting_time": "10:00 AM",
            "meeting_type": "video_conference",
            "trustees_present": ["John Smith"],
            "trust_indenture_date": "January 1, 2020",
            "quarter": "Q4",
            "year": "2025",
            "beginning_balance": 950000,
            "ending_balance": 1000000,
            "income_received": 75000,
            "expenses_paid": 20000,
            "distributions_made": 5000,
            "discussion_items": ["Investment performance review", "Upcoming distributions"],
            "action_items": ["Schedule annual meeting", "Update Schedule A"]
        }
        
        response = requests.post(
            f"{BASE_URL}/api/minutes-templates",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json={
                "trust_id": trust_id,
                "template_type": "quarterly_review",
                "template_data": template_data
            }
        )
        
        assert response.status_code == 200, f"Failed: {response.text}"
        result = response.json()
        assert "Quarterly Review" in result["generated_document"]
        assert "Q4 2025" in result["generated_document"]
        print(f"✓ Quarterly review template generated: {result['minutes_id']}")


class TestTrusteeCompensationTemplate:
    """Test trustee_compensation template generation"""
    
    def test_generate_trustee_compensation(self, auth_token, trust_id):
        """Test trustee compensation template"""
        template_data = {
            "minute_number": "2026-TEST-006",
            "meeting_date": "January 30, 2026",
            "meeting_time": "10:00 AM",
            "meeting_type": "unanimous_written_consent",
            "trustees_present": ["John Smith", "Jane Doe"],
            "trust_indenture_date": "January 1, 2020",
            "trustee_name": "John Smith",
            "compensation_type": "annual",
            "compensation_amount": 5000,
            "effective_date": "February 1, 2026",
            "compensation_basis": "Administrative services and fiduciary oversight",
            "duties_description": "Trust administration, investment oversight, beneficiary communications",
            "all_trustees": False
        }
        
        response = requests.post(
            f"{BASE_URL}/api/minutes-templates",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json={
                "trust_id": trust_id,
                "template_type": "trustee_compensation",
                "template_data": template_data
            }
        )
        
        assert response.status_code == 200, f"Failed: {response.text}"
        result = response.json()
        assert "Trustee Compensation Approval" in result["generated_document"]
        assert "John Smith" in result["generated_document"]
        assert "$5,000.00 per year" in result["generated_document"]
        print(f"✓ Trustee compensation template generated: {result['minutes_id']}")


class TestTrusteeResignationTemplate:
    """Test trustee_resignation template generation"""
    
    def test_generate_trustee_resignation(self, auth_token, trust_id):
        """Test trustee resignation template"""
        template_data = {
            "minute_number": "2026-TEST-007",
            "meeting_date": "January 30, 2026",
            "meeting_time": "10:00 AM",
            "meeting_type": "unanimous_written_consent",
            "trustees_present": ["Jane Doe"],
            "trust_indenture_date": "January 1, 2020",
            "departing_trustee_name": "Robert Wilson",
            "departure_type": "resignation",
            "departure_reason": "Personal relocation",
            "effective_date": "March 1, 2026",
            "remaining_trustees": ["Jane Doe", "Michael Brown"],
            "successor_appointed": False
        }
        
        response = requests.post(
            f"{BASE_URL}/api/minutes-templates",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json={
                "trust_id": trust_id,
                "template_type": "trustee_resignation",
                "template_data": template_data
            }
        )
        
        assert response.status_code == 200, f"Failed: {response.text}"
        result = response.json()
        assert "Trustee Resignation" in result["generated_document"]
        assert "Robert Wilson" in result["generated_document"]
        assert "tendered their resignation" in result["generated_document"]
        print(f"✓ Trustee resignation template generated: {result['minutes_id']}")


class TestBeneficiaryRequestDenialTemplate:
    """Test beneficiary_request_denial template generation"""
    
    def test_generate_beneficiary_denial(self, auth_token, trust_id):
        """Test beneficiary request denial template"""
        template_data = {
            "minute_number": "2026-TEST-008",
            "meeting_date": "January 30, 2026",
            "meeting_time": "10:00 AM",
            "meeting_type": "unanimous_written_consent",
            "trustees_present": ["John Smith"],
            "trust_indenture_date": "January 1, 2020",
            "beneficiary_name": "Sarah Johnson",
            "request_type": "distribution",
            "request_amount": 25000,
            "request_purpose": "Vacation expenses",
            "request_date": "January 15, 2026",
            "denial_reasons": [
                "Request does not meet HEMS distribution standards",
                "Vacation expenses are not covered under trust provisions"
            ],
            "alternative_offered": "Consider applying for educational or medical expense distribution"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/minutes-templates",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json={
                "trust_id": trust_id,
                "template_type": "beneficiary_request_denial",
                "template_data": template_data
            }
        )
        
        assert response.status_code == 200, f"Failed: {response.text}"
        result = response.json()
        assert "Denial of Beneficiary Request" in result["generated_document"]
        assert "Sarah Johnson" in result["generated_document"]
        assert "$25,000.00" in result["generated_document"]
        print(f"✓ Beneficiary request denial template generated: {result['minutes_id']}")


class TestHEMSDistributionTemplate:
    """Test hems_distribution template generation"""
    
    def test_generate_hems_distribution(self, auth_token, trust_id):
        """Test HEMS distribution template"""
        template_data = {
            "minute_number": "2026-TEST-009",
            "meeting_date": "January 30, 2026",
            "meeting_time": "10:00 AM",
            "meeting_type": "unanimous_written_consent",
            "trustees_present": ["John Smith"],
            "trust_indenture_date": "January 1, 2020",
            "beneficiary_name": "Emily Johnson",
            "hems_category": "education",
            "distribution_amount": 15000,
            "specific_purpose": "College tuition payment for Spring 2026 semester",
            "supporting_documentation": ["University invoice", "Enrollment verification"],
            "recurring": True,
            "recurring_frequency": "quarterly"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/minutes-templates",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json={
                "trust_id": trust_id,
                "template_type": "hems_distribution",
                "template_data": template_data
            }
        )
        
        assert response.status_code == 200, f"Failed: {response.text}"
        result = response.json()
        assert "HEMS Distribution" in result["generated_document"]
        assert "Emily Johnson" in result["generated_document"]
        assert "Education" in result["generated_document"] or "EDUCATION" in result["generated_document"]
        print(f"✓ HEMS distribution template generated: {result['minutes_id']}")


class TestBeneficiaryLoanTemplate:
    """Test beneficiary_loan template generation"""
    
    def test_generate_beneficiary_loan(self, auth_token, trust_id):
        """Test beneficiary loan template"""
        template_data = {
            "minute_number": "2026-TEST-010",
            "meeting_date": "January 30, 2026",
            "meeting_time": "10:00 AM",
            "meeting_type": "unanimous_written_consent",
            "trustees_present": ["John Smith"],
            "trust_indenture_date": "January 1, 2020",
            "beneficiary_name": "David Johnson",
            "loan_amount": 75000,
            "interest_rate": "AFR (Applicable Federal Rate)",
            "term_months": 120,
            "loan_purpose": "Down payment for primary residence",
            "collateral_description": "Promissory note secured by beneficial interest",
            "repayment_terms": "monthly installments"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/minutes-templates",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json={
                "trust_id": trust_id,
                "template_type": "beneficiary_loan",
                "template_data": template_data
            }
        )
        
        assert response.status_code == 200, f"Failed: {response.text}"
        result = response.json()
        assert "Loan to Beneficiary" in result["generated_document"]
        assert "David Johnson" in result["generated_document"]
        assert "$75,000.00" in result["generated_document"]
        print(f"✓ Beneficiary loan template generated: {result['minutes_id']}")


class TestPDFGeneration:
    """Test PDF generation for new templates"""
    
    def test_investment_policy_pdf_generation(self, auth_token, trust_id):
        """Test PDF generation for investment policy"""
        # First create a template
        template_data = {
            "minute_number": "2026-PDF-001",
            "meeting_date": "January 30, 2026",
            "meeting_time": "10:00 AM",
            "meeting_type": "unanimous_written_consent",
            "trustees_present": ["John Smith"],
            "trust_indenture_date": "January 1, 2020",
            "policy_type": "adopt",
            "risk_tolerance": "conservative",
            "review_frequency": "quarterly"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/minutes-templates",
            headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
            json={
                "trust_id": trust_id,
                "template_type": "investment_policy",
                "template_data": template_data
            }
        )
        
        assert response.status_code == 200
        minutes_id = response.json()["minutes_id"]
        
        # Now get PDF
        pdf_response = requests.get(
            f"{BASE_URL}/api/minutes-templates/{minutes_id}/pdf",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert pdf_response.status_code == 200
        pdf_data = pdf_response.json()
        assert "pdf_base64" in pdf_data
        assert "filename" in pdf_data
        assert len(pdf_data["pdf_base64"]) > 100  # PDF content exists
        print(f"✓ PDF generated for investment policy template: {pdf_data['filename']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
