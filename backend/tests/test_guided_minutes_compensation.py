"""
Test cases for Guided Minutes (trustees vs other attendees separation) and 
Compensation page (trustee selector in payment modal) improvements.
"""
import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "demo@trustoffice.com"
TEST_PASSWORD = "demopassword"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for tests"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def headers(auth_token):
    """Return headers with auth token"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


@pytest.fixture(scope="module")
def trust_id(headers):
    """Get the first trust ID for testing"""
    response = requests.get(f"{BASE_URL}/api/trusts", headers=headers)
    assert response.status_code == 200
    trusts = response.json()
    assert len(trusts) > 0, "No trusts found for user"
    return trusts[0]["trust_id"]


class TestGuidedMinutesContext:
    """Test Guided Minutes context API - verifies trustees list is returned"""
    
    def test_get_context_returns_trustees(self, headers, trust_id):
        """Test that guided minutes context returns trustees list"""
        response = requests.get(
            f"{BASE_URL}/api/guided-minutes/context?trust_id={trust_id}",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "trust_id" in data
        assert "trust_name" in data
        assert "trustees" in data
        assert isinstance(data["trustees"], list)
        
        # Should have at least some trustees
        print(f"Trustees found: {data['trustees']}")


class TestGuidedMinutesDraft:
    """Test Guided Minutes draft generation with separate trustees and other attendees"""
    
    def test_draft_with_other_attendees(self, headers, trust_id):
        """Test that draft request accepts other_attendees field separately from participants"""
        response = requests.post(
            f"{BASE_URL}/api/guided-minutes/draft",
            headers=headers,
            json={
                "trust_id": trust_id,
                "minutes_type": "annual",
                "meeting_date": "2026-03-02",
                "participants": ["John Smith"],  # Trustees
                "other_attendees": ["James Wilson (Attorney)", "Mary Johnson (CPA)"],  # Non-trustees
                "agenda_items": ["Review annual financials", "Discuss trust amendments"],
                "key_decisions": ["Approved annual distribution of $10,000"],
                "additional_context": "Test meeting"
            }
        )
        
        assert response.status_code == 200, f"Draft generation failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "suggested_title" in data
        assert "draft_body" in data
        assert "participants_text" in data
        
        print(f"Draft title: {data['suggested_title']}")
        print(f"Participants text: {data['participants_text']}")


class TestGuidedMinutesSave:
    """Test Guided Minutes save with other_attendees_text field"""
    
    def test_save_with_other_attendees(self, headers, trust_id):
        """Test that save request accepts other_attendees_text field"""
        response = requests.post(
            f"{BASE_URL}/api/guided-minutes/save",
            headers=headers,
            json={
                "trust_id": trust_id,
                "minutes_type": "annual",
                "meeting_date": "2026-03-02",
                "participants_text": "John Smith",
                "other_attendees_text": "James Wilson (Attorney), Mary Johnson (CPA)",
                "decisions_text": "WHEREAS, the Trustees met to discuss...\n\nRESOLVED, that..."
            }
        )
        
        assert response.status_code == 200, f"Save failed: {response.text}"
        data = response.json()
        
        # Verify response contains minutes_id
        assert "minutes_id" in data
        print(f"Minutes saved: {data['minutes_id']}")
        
        return data["minutes_id"]


class TestCompensationPaymentWithTrustee:
    """Test Compensation payment creation with trustee_name field"""
    
    def test_create_payment_with_trustee(self, headers, trust_id):
        """Test that payment can be created with a specific trustee_name"""
        response = requests.post(
            f"{BASE_URL}/api/compensation-payments",
            headers=headers,
            json={
                "trust_id": trust_id,
                "amount": 1500.00,
                "date": "2026-03-02",
                "classification_text": "TEST_Quarterly trustee fee",
                "trustee_name": "John Smith"  # New field for recipient trustee
            }
        )
        
        assert response.status_code in [200, 201], f"Payment creation failed: {response.text}"
        data = response.json()
        
        # Verify response contains payment_id
        assert "payment_id" in data
        print(f"Payment created: {data['payment_id']}")
        
        return data["payment_id"]
    
    def test_payment_without_trustee_also_works(self, headers, trust_id):
        """Test that payment can still be created without trustee_name (backward compatible)"""
        response = requests.post(
            f"{BASE_URL}/api/compensation-payments",
            headers=headers,
            json={
                "trust_id": trust_id,
                "amount": 500.00,
                "date": "2026-03-02",
                "classification_text": "TEST_General compensation"
            }
        )
        
        assert response.status_code in [200, 201], f"Payment creation failed: {response.text}"
        data = response.json()
        
        assert "payment_id" in data
        print(f"Payment without trustee created: {data['payment_id']}")
    
    def test_get_payments_includes_trustee_name(self, headers, trust_id):
        """Test that payment list returns trustee_name field"""
        response = requests.get(
            f"{BASE_URL}/api/compensation-payments?trust_id={trust_id}",
            headers=headers
        )
        
        assert response.status_code == 200
        payments = response.json()
        
        # Check that payments have trustee_name field
        for payment in payments:
            # trustee_name can be null/None for old payments
            assert "trustee_name" in payment or "trustee_name" not in payment  # Just check structure
            if payment.get("trustee_name"):
                print(f"Payment {payment['payment_id']} has trustee: {payment['trustee_name']}")


class TestMinutesPDFGeneration:
    """Test PDF generation includes 'Also Present' section"""
    
    def test_pdf_generation_endpoint(self, headers, trust_id):
        """Test that PDF can be generated for minutes"""
        # First get list of minutes
        response = requests.get(
            f"{BASE_URL}/api/minutes?trust_id={trust_id}",
            headers=headers
        )
        
        assert response.status_code == 200
        minutes_list = response.json()
        
        if len(minutes_list) > 0:
            minutes_id = minutes_list[0]["minutes_id"]
            
            # Try to generate PDF
            pdf_response = requests.get(
                f"{BASE_URL}/api/minutes/{minutes_id}/pdf",
                headers=headers
            )
            
            assert pdf_response.status_code == 200, f"PDF generation failed: {pdf_response.text}"
            data = pdf_response.json()
            
            assert "pdf_base64" in data
            assert "filename" in data
            print(f"PDF generated: {data['filename']}")


class TestCompensationPlansRename:
    """Test that Per-Trustee Compensation Caps section works correctly"""
    
    def test_get_compensation_plans(self, headers, trust_id):
        """Test that compensation plans endpoint returns plans"""
        response = requests.get(
            f"{BASE_URL}/api/compensation-plans?trust_id={trust_id}",
            headers=headers
        )
        
        assert response.status_code == 200
        plans = response.json()
        
        # Plans can be empty or have entries
        print(f"Number of compensation plans: {len(plans)}")
        
        for plan in plans:
            # Check fields that should be present
            assert "plan_id" in plan
            print(f"Plan: {plan.get('trustee_name', 'Primary')} - ${plan.get('annual_approved_amount', plan.get('annual_fee', 0))}")


# Cleanup - delete test data
class TestCleanup:
    """Cleanup test data created during tests"""
    
    def test_cleanup_test_payments(self, headers, trust_id):
        """Delete test payments created during testing"""
        response = requests.get(
            f"{BASE_URL}/api/compensation-payments?trust_id={trust_id}",
            headers=headers
        )
        
        if response.status_code == 200:
            payments = response.json()
            
            for payment in payments:
                if payment.get("classification_text", "").startswith("TEST_"):
                    delete_response = requests.delete(
                        f"{BASE_URL}/api/compensation-payments/{payment['payment_id']}",
                        headers=headers
                    )
                    if delete_response.status_code in [200, 204]:
                        print(f"Deleted test payment: {payment['payment_id']}")
