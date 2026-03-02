"""
Tests for minutes router - minutes CRUD, PDF generation, and templates
Migrated from server.py to routers/minutes.py (1243 lines)
"""
import pytest
import requests
import os
import uuid
from datetime import datetime, timezone

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
DEMO_EMAIL = "demo@trustoffice.com"
DEMO_PASSWORD = "demopassword"
TRUST_ID = "trust_b753cb8fe07f"

class TestMinutesRouterSetup:
    """Setup tests - verify auth and router availability"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get auth token for demo user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEMO_EMAIL,
            "password": DEMO_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get auth headers"""
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_login_works(self, auth_token):
        """Verify login works"""
        assert auth_token is not None
        assert len(auth_token) > 0
        print("Login successful - auth token obtained")


class TestMinutesCRUD:
    """Test minutes CRUD operations"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEMO_EMAIL,
            "password": DEMO_PASSWORD
        })
        assert response.status_code == 200
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    def test_get_minutes_returns_200(self, auth_headers):
        """GET /api/minutes returns 200"""
        response = requests.get(f"{BASE_URL}/api/minutes", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"GET /api/minutes - returned {len(data)} records")
    
    def test_get_minutes_with_trust_filter(self, auth_headers):
        """GET /api/minutes?trust_id=xxx works"""
        response = requests.get(
            f"{BASE_URL}/api/minutes?trust_id={TRUST_ID}", 
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # All returned records should match trust_id filter
        for record in data:
            assert record.get("trust_id") == TRUST_ID
        print(f"GET /api/minutes with trust filter - returned {len(data)} records")
    
    def test_get_minutes_with_search(self, auth_headers):
        """GET /api/minutes?search=xxx works"""
        response = requests.get(
            f"{BASE_URL}/api/minutes?search=test", 
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"GET /api/minutes with search - returned {len(data)} records")
    
    def test_get_minutes_with_type_filter(self, auth_headers):
        """GET /api/minutes?minutes_type=xxx works"""
        response = requests.get(
            f"{BASE_URL}/api/minutes?minutes_type=annual", 
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"GET /api/minutes with type filter - returned {len(data)} records")
    
    def test_create_minutes_returns_correct_response(self, auth_headers):
        """POST /api/minutes creates new minutes record"""
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "trust_id": TRUST_ID,
            "minutes_type": "annual",
            "meeting_date": "2025-01-15",
            "participants_text": f"TEST_Trustee1_{unique_id}, TEST_Trustee2_{unique_id}",
            "decisions_text": f"TEST decision text {unique_id} - Annual review completed"
        }
        response = requests.post(
            f"{BASE_URL}/api/minutes", 
            json=payload, 
            headers=auth_headers
        )
        assert response.status_code == 200, f"Create failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "minutes_id" in data
        assert data["trust_id"] == TRUST_ID
        assert data["minutes_type"] == "annual"
        assert data["meeting_date"] == "2025-01-15"
        assert f"TEST_Trustee1_{unique_id}" in data["participants_text"]
        assert f"TEST decision text {unique_id}" in data["decisions_text"]
        assert "created_at" in data
        
        print(f"Created minutes: {data['minutes_id']}")
        return data["minutes_id"]
    
    def test_create_and_get_minutes_persistence(self, auth_headers):
        """POST /api/minutes then GET to verify persistence"""
        unique_id = uuid.uuid4().hex[:8]
        # Create
        payload = {
            "trust_id": TRUST_ID,
            "minutes_type": "quarterly",
            "meeting_date": "2025-01-20",
            "participants_text": f"TEST_persistence_{unique_id}",
            "decisions_text": f"TEST_persistence_decision_{unique_id}"
        }
        create_response = requests.post(
            f"{BASE_URL}/api/minutes", 
            json=payload, 
            headers=auth_headers
        )
        assert create_response.status_code == 200
        created = create_response.json()
        minutes_id = created["minutes_id"]
        
        # Get by ID to verify persistence
        get_response = requests.get(
            f"{BASE_URL}/api/minutes/{minutes_id}", 
            headers=auth_headers
        )
        assert get_response.status_code == 200
        fetched = get_response.json()
        
        assert fetched["minutes_id"] == minutes_id
        assert fetched["trust_id"] == TRUST_ID
        assert f"TEST_persistence_{unique_id}" in fetched["participants_text"]
        
        print(f"Verified minutes persistence for {minutes_id}")
    
    def test_get_minutes_by_id_not_found(self, auth_headers):
        """GET /api/minutes/{id} returns 404 for non-existent"""
        response = requests.get(
            f"{BASE_URL}/api/minutes/nonexistent_minutes_id", 
            headers=auth_headers
        )
        assert response.status_code == 404
        print("GET /api/minutes/{id} - returns 404 for invalid ID")
    
    def test_delete_minutes(self, auth_headers):
        """DELETE /api/minutes/{id} deletes record"""
        # Create a minutes record to delete
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "trust_id": TRUST_ID,
            "minutes_type": "solvency",
            "meeting_date": "2025-01-21",
            "participants_text": f"TEST_delete_{unique_id}",
            "decisions_text": f"TEST_delete_decision_{unique_id}"
        }
        create_response = requests.post(
            f"{BASE_URL}/api/minutes", 
            json=payload, 
            headers=auth_headers
        )
        assert create_response.status_code == 200
        minutes_id = create_response.json()["minutes_id"]
        
        # Delete
        delete_response = requests.delete(
            f"{BASE_URL}/api/minutes/{minutes_id}", 
            headers=auth_headers
        )
        assert delete_response.status_code == 200
        
        # Verify deleted - should return 404
        get_response = requests.get(
            f"{BASE_URL}/api/minutes/{minutes_id}", 
            headers=auth_headers
        )
        assert get_response.status_code == 404
        
        print(f"Successfully deleted minutes {minutes_id}")
    
    def test_delete_minutes_not_found(self, auth_headers):
        """DELETE /api/minutes/{id} returns 404 for non-existent"""
        response = requests.delete(
            f"{BASE_URL}/api/minutes/nonexistent_minutes_id", 
            headers=auth_headers
        )
        assert response.status_code == 404
        print("DELETE /api/minutes/{id} - returns 404 for invalid ID")


class TestMinutesPDF:
    """Test minutes PDF generation"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEMO_EMAIL,
            "password": DEMO_PASSWORD
        })
        assert response.status_code == 200
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    def test_get_minutes_pdf(self, auth_headers):
        """GET /api/minutes/{id}/pdf generates PDF"""
        # First create a minutes record
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "trust_id": TRUST_ID,
            "minutes_type": "distribution",
            "meeting_date": "2025-01-22",
            "participants_text": f"TEST_pdf_{unique_id}",
            "decisions_text": f"TEST_pdf_decision_{unique_id}"
        }
        create_response = requests.post(
            f"{BASE_URL}/api/minutes", 
            json=payload, 
            headers=auth_headers
        )
        assert create_response.status_code == 200
        minutes_id = create_response.json()["minutes_id"]
        
        # Get PDF
        pdf_response = requests.get(
            f"{BASE_URL}/api/minutes/{minutes_id}/pdf", 
            headers=auth_headers
        )
        assert pdf_response.status_code == 200
        data = pdf_response.json()
        
        # Verify PDF response structure
        assert "pdf_base64" in data
        assert "filename" in data
        assert len(data["pdf_base64"]) > 100  # Should have substantial content
        assert minutes_id in data["filename"]
        
        print(f"Successfully generated PDF for minutes {minutes_id}")
    
    def test_get_minutes_pdf_not_found(self, auth_headers):
        """GET /api/minutes/{id}/pdf returns 404 for non-existent"""
        response = requests.get(
            f"{BASE_URL}/api/minutes/nonexistent_minutes_id/pdf", 
            headers=auth_headers
        )
        assert response.status_code == 404
        print("GET /api/minutes/{id}/pdf - returns 404 for invalid ID")


class TestMinutesTemplates:
    """Test minutes templates endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEMO_EMAIL,
            "password": DEMO_PASSWORD
        })
        assert response.status_code == 200
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    def test_get_template_options(self, auth_headers):
        """GET /api/template-options returns available templates"""
        response = requests.get(
            f"{BASE_URL}/api/template-options", 
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        assert len(data) >= 10  # Should have at least 10 template types
        
        # Verify expected templates exist
        template_types = [t["type"] for t in data]
        expected_types = [
            "blank",
            "general_meeting",
            "distribution_to_beneficiaries",
            "acceptance_of_property",
            "disposition_of_asset",
            "appointment_additional_trustee",
            "appointment_successor_trustee",
            "designation_of_beneficiaries",
            "bank_account_authorization",
            "change_of_situs"
        ]
        
        for expected in expected_types:
            assert expected in template_types, f"Missing template type: {expected}"
        
        # Verify template structure
        for template in data:
            assert "type" in template
            assert "name" in template
            assert "description" in template
            assert "icon" in template
        
        print(f"GET /api/template-options - returned {len(data)} templates")
    
    def test_get_template_options_with_trust_filter(self, auth_headers):
        """GET /api/template-options?trust_id=xxx filters benevolence"""
        response = requests.get(
            f"{BASE_URL}/api/template-options?trust_id={TRUST_ID}", 
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"GET /api/template-options with trust_id - returned {len(data)} templates")
    
    def test_get_minutes_templates_list(self, auth_headers):
        """GET /api/minutes-templates returns list"""
        response = requests.get(
            f"{BASE_URL}/api/minutes-templates", 
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"GET /api/minutes-templates - returned {len(data)} template-based minutes")
    
    def test_get_minutes_templates_with_trust_filter(self, auth_headers):
        """GET /api/minutes-templates?trust_id=xxx works"""
        response = requests.get(
            f"{BASE_URL}/api/minutes-templates?trust_id={TRUST_ID}", 
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # All returned should match trust_id
        for record in data:
            assert record.get("trust_id") == TRUST_ID
        print(f"GET /api/minutes-templates with trust filter - returned {len(data)} records")
    
    def test_create_minutes_from_blank_template(self, auth_headers):
        """POST /api/minutes-templates creates from blank template"""
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "trust_id": TRUST_ID,
            "template_type": "blank",
            "template_data": {
                "meeting_date": "2025-01-25",
                "meeting_time": "10:00 AM",
                "meeting_type": "unanimous_written_consent",
                "trustees_present": [f"TEST_Trustee_{unique_id}"]
            }
        }
        response = requests.post(
            f"{BASE_URL}/api/minutes-templates", 
            json=payload, 
            headers=auth_headers
        )
        assert response.status_code == 200, f"Create failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "minutes_id" in data
        assert data["trust_id"] == TRUST_ID
        assert data["template_type"] == "blank"
        assert "generated_document" in data
        assert "original_document" in data
        assert data["status"] == "draft"
        assert "created_at" in data
        
        print(f"Created blank template minutes: {data['minutes_id']}")
        return data["minutes_id"]
    
    def test_create_minutes_from_general_meeting_template(self, auth_headers):
        """POST /api/minutes-templates creates from general_meeting template"""
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "trust_id": TRUST_ID,
            "template_type": "general_meeting",
            "template_data": {
                "minute_number": f"2025-{unique_id}",
                "meeting_date": "2025-01-26",
                "meeting_time": "2:00 PM",
                "meeting_type": "in_person",
                "meeting_location": "Test Location",
                "trustees_present": [f"TEST_Trustee1_{unique_id}", f"TEST_Trustee2_{unique_id}"],
                "trust_indenture_date": "2020-01-01",
                "resolutions": [
                    {
                        "title": f"Test Resolution {unique_id}",
                        "whereas_clauses": ["The trust needs testing"],
                        "resolved_clauses": ["To approve this test resolution"],
                        "vote": "Unanimous approval",
                        "effective_date": "Immediately"
                    }
                ]
            }
        }
        response = requests.post(
            f"{BASE_URL}/api/minutes-templates", 
            json=payload, 
            headers=auth_headers
        )
        assert response.status_code == 200, f"Create failed: {response.text}"
        data = response.json()
        
        assert data["template_type"] == "general_meeting"
        assert "TRUST MINUTES" in data["generated_document"]
        assert f"TEST_Trustee1_{unique_id}" in data["generated_document"]
        
        print(f"Created general_meeting template minutes: {data['minutes_id']}")
    
    def test_create_minutes_from_distribution_template(self, auth_headers):
        """POST /api/minutes-templates creates from distribution template"""
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "trust_id": TRUST_ID,
            "template_type": "distribution_to_beneficiaries",
            "template_data": {
                "meeting_date": "2025-01-27",
                "trustees_present": [f"TEST_Trustee_{unique_id}"],
                "distribution_total": 10000.00,
                "distribution_date": "2025-02-01",
                "distribution_characterization": "income",
                "distribution_items": [
                    {
                        "beneficiary_name": f"TEST_Beneficiary_{unique_id}",
                        "amount": 10000.00,
                        "percentage": 100
                    }
                ]
            }
        }
        response = requests.post(
            f"{BASE_URL}/api/minutes-templates", 
            json=payload, 
            headers=auth_headers
        )
        assert response.status_code == 200, f"Create failed: {response.text}"
        data = response.json()
        
        assert data["template_type"] == "distribution_to_beneficiaries"
        assert "Distribution" in data["generated_document"]
        assert "$10,000.00" in data["generated_document"]
        
        print(f"Created distribution template minutes: {data['minutes_id']}")
    
    def test_create_minutes_from_property_acceptance_template(self, auth_headers):
        """POST /api/minutes-templates creates from acceptance_of_property template"""
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "trust_id": TRUST_ID,
            "template_type": "acceptance_of_property",
            "template_data": {
                "meeting_date": "2025-01-28",
                "trustees_present": [f"TEST_Trustee_{unique_id}"],
                "grantor_name": f"TEST_Grantor_{unique_id}",
                "property_description": f"TEST Property Description {unique_id}",
                "property_value": 50000.00,
                "conveyance_date": "2025-01-28",
                "add_to_schedule_a": False  # Don't actually add to Schedule A for tests
            }
        }
        response = requests.post(
            f"{BASE_URL}/api/minutes-templates", 
            json=payload, 
            headers=auth_headers
        )
        assert response.status_code == 200, f"Create failed: {response.text}"
        data = response.json()
        
        assert data["template_type"] == "acceptance_of_property"
        assert "Acceptance of Additional Property" in data["generated_document"]
        
        print(f"Created property acceptance template minutes: {data['minutes_id']}")
    
    def test_create_minutes_from_asset_disposition_template(self, auth_headers):
        """POST /api/minutes-templates creates from disposition_of_asset template"""
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "trust_id": TRUST_ID,
            "template_type": "disposition_of_asset",
            "template_data": {
                "meeting_date": "2025-01-29",
                "trustees_present": [f"TEST_Trustee_{unique_id}"],
                "disposition_asset_description": f"TEST Asset {unique_id}",
                "disposition_reason": "sale",
                "disposition_date": "2025-02-01",
                "disposition_value": 25000.00,
                "disposition_recipient": f"TEST_Buyer_{unique_id}",
                "update_schedule_a": False  # Don't actually update Schedule A
            }
        }
        response = requests.post(
            f"{BASE_URL}/api/minutes-templates", 
            json=payload, 
            headers=auth_headers
        )
        assert response.status_code == 200, f"Create failed: {response.text}"
        data = response.json()
        
        assert data["template_type"] == "disposition_of_asset"
        assert "Disposition of Trust Asset" in data["generated_document"]
        
        print(f"Created asset disposition template minutes: {data['minutes_id']}")
    
    def test_create_minutes_from_trustee_appointment_template(self, auth_headers):
        """POST /api/minutes-templates creates from trustee appointment template"""
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "trust_id": TRUST_ID,
            "template_type": "appointment_additional_trustee",
            "template_data": {
                "meeting_date": "2025-01-30",
                "trustees_present": [f"TEST_Trustee_{unique_id}"],
                "new_trustee_name": f"TEST_NewTrustee_{unique_id}",
                "new_trustee_gender": "man",
                "signature_requirement": "any_one"
            }
        }
        response = requests.post(
            f"{BASE_URL}/api/minutes-templates", 
            json=payload, 
            headers=auth_headers
        )
        assert response.status_code == 200, f"Create failed: {response.text}"
        data = response.json()
        
        assert data["template_type"] == "appointment_additional_trustee"
        assert "Appointment" in data["generated_document"]
        assert f"TEST_NewTrustee_{unique_id}" in data["generated_document"]
        
        print(f"Created trustee appointment template minutes: {data['minutes_id']}")
    
    def test_create_minutes_from_bank_account_template(self, auth_headers):
        """POST /api/minutes-templates creates from bank_account_authorization template"""
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "trust_id": TRUST_ID,
            "template_type": "bank_account_authorization",
            "template_data": {
                "meeting_date": "2025-01-31",
                "trustees_present": [f"TEST_Trustee_{unique_id}"],
                "bank_name": f"TEST_Bank_{unique_id}",
                "account_type": "checking",
                "purpose": "trust administration",
                "authorized_signers": [f"TEST_Trustee_{unique_id}"],
                "signature_requirement": "any_one"
            }
        }
        response = requests.post(
            f"{BASE_URL}/api/minutes-templates", 
            json=payload, 
            headers=auth_headers
        )
        assert response.status_code == 200, f"Create failed: {response.text}"
        data = response.json()
        
        assert data["template_type"] == "bank_account_authorization"
        assert "Bank Account" in data["generated_document"]
        assert f"TEST_Bank_{unique_id}" in data["generated_document"]
        
        print(f"Created bank account template minutes: {data['minutes_id']}")
    
    def test_get_minutes_template_by_id(self, auth_headers):
        """GET /api/minutes-templates/{id} returns specific template"""
        # First create one
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "trust_id": TRUST_ID,
            "template_type": "blank",
            "template_data": {
                "meeting_date": "2025-02-01",
                "trustees_present": [f"TEST_Trustee_{unique_id}"]
            }
        }
        create_response = requests.post(
            f"{BASE_URL}/api/minutes-templates", 
            json=payload, 
            headers=auth_headers
        )
        assert create_response.status_code == 200
        minutes_id = create_response.json()["minutes_id"]
        
        # Get by ID
        get_response = requests.get(
            f"{BASE_URL}/api/minutes-templates/{minutes_id}", 
            headers=auth_headers
        )
        assert get_response.status_code == 200
        data = get_response.json()
        
        assert data["minutes_id"] == minutes_id
        assert data["trust_id"] == TRUST_ID
        
        print(f"GET /api/minutes-templates/{minutes_id} - success")
    
    def test_get_minutes_template_not_found(self, auth_headers):
        """GET /api/minutes-templates/{id} returns 404 for non-existent"""
        response = requests.get(
            f"{BASE_URL}/api/minutes-templates/nonexistent_id", 
            headers=auth_headers
        )
        assert response.status_code == 404
        print("GET /api/minutes-templates/{id} - returns 404 for invalid ID")
    
    def test_update_minutes_template(self, auth_headers):
        """PUT /api/minutes-templates/{id} updates template"""
        # First create one
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "trust_id": TRUST_ID,
            "template_type": "blank",
            "template_data": {
                "meeting_date": "2025-02-02",
                "trustees_present": [f"TEST_Trustee_{unique_id}"]
            }
        }
        create_response = requests.post(
            f"{BASE_URL}/api/minutes-templates", 
            json=payload, 
            headers=auth_headers
        )
        assert create_response.status_code == 200
        minutes_id = create_response.json()["minutes_id"]
        
        # Update
        update_payload = {
            "generated_document": f"Updated document content {unique_id}",
            "status": "final"
        }
        update_response = requests.put(
            f"{BASE_URL}/api/minutes-templates/{minutes_id}", 
            json=update_payload, 
            headers=auth_headers
        )
        assert update_response.status_code == 200
        data = update_response.json()
        
        assert data["status"] == "final"
        assert f"Updated document content {unique_id}" in data["generated_document"]
        assert data["updated_at"] is not None
        
        print(f"PUT /api/minutes-templates/{minutes_id} - updated successfully")
    
    def test_update_minutes_template_not_found(self, auth_headers):
        """PUT /api/minutes-templates/{id} returns 404 for non-existent"""
        response = requests.put(
            f"{BASE_URL}/api/minutes-templates/nonexistent_id", 
            json={"status": "final"}, 
            headers=auth_headers
        )
        assert response.status_code == 404
        print("PUT /api/minutes-templates/{id} - returns 404 for invalid ID")
    
    def test_delete_minutes_template(self, auth_headers):
        """DELETE /api/minutes-templates/{id} deletes template"""
        # First create one
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "trust_id": TRUST_ID,
            "template_type": "blank",
            "template_data": {
                "meeting_date": "2025-02-03",
                "trustees_present": [f"TEST_delete_{unique_id}"]
            }
        }
        create_response = requests.post(
            f"{BASE_URL}/api/minutes-templates", 
            json=payload, 
            headers=auth_headers
        )
        assert create_response.status_code == 200
        minutes_id = create_response.json()["minutes_id"]
        
        # Delete
        delete_response = requests.delete(
            f"{BASE_URL}/api/minutes-templates/{minutes_id}", 
            headers=auth_headers
        )
        assert delete_response.status_code == 200
        
        # Verify deleted
        get_response = requests.get(
            f"{BASE_URL}/api/minutes-templates/{minutes_id}", 
            headers=auth_headers
        )
        assert get_response.status_code == 404
        
        print(f"DELETE /api/minutes-templates/{minutes_id} - deleted successfully")
    
    def test_delete_minutes_template_not_found(self, auth_headers):
        """DELETE /api/minutes-templates/{id} returns 404 for non-existent"""
        response = requests.delete(
            f"{BASE_URL}/api/minutes-templates/nonexistent_id", 
            headers=auth_headers
        )
        assert response.status_code == 404
        print("DELETE /api/minutes-templates/{id} - returns 404 for invalid ID")
    
    def test_get_minutes_template_pdf(self, auth_headers):
        """GET /api/minutes-templates/{id}/pdf generates PDF"""
        # First create one
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "trust_id": TRUST_ID,
            "template_type": "general_meeting",
            "template_data": {
                "meeting_date": "2025-02-04",
                "trustees_present": [f"TEST_pdf_{unique_id}"],
                "resolutions": [
                    {
                        "title": "Test Resolution",
                        "whereas_clauses": ["Testing PDF generation"],
                        "resolved_clauses": ["Approved"],
                        "vote": "Unanimous"
                    }
                ]
            }
        }
        create_response = requests.post(
            f"{BASE_URL}/api/minutes-templates", 
            json=payload, 
            headers=auth_headers
        )
        assert create_response.status_code == 200
        minutes_id = create_response.json()["minutes_id"]
        
        # Get PDF
        pdf_response = requests.get(
            f"{BASE_URL}/api/minutes-templates/{minutes_id}/pdf", 
            headers=auth_headers
        )
        assert pdf_response.status_code == 200
        data = pdf_response.json()
        
        assert "pdf_base64" in data
        assert "filename" in data
        assert len(data["pdf_base64"]) > 100
        
        print(f"GET /api/minutes-templates/{minutes_id}/pdf - generated successfully")


class TestMinutesAuthentication:
    """Test that all minutes endpoints require authentication"""
    
    def test_get_minutes_requires_auth(self):
        """GET /api/minutes requires authentication"""
        response = requests.get(f"{BASE_URL}/api/minutes")
        assert response.status_code == 401
        print("GET /api/minutes - requires auth (401)")
    
    def test_post_minutes_requires_auth(self):
        """POST /api/minutes requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/minutes", 
            json={"trust_id": TRUST_ID, "minutes_type": "annual", "meeting_date": "2025-01-01", "participants_text": "", "decisions_text": ""}
        )
        assert response.status_code == 401
        print("POST /api/minutes - requires auth (401)")
    
    def test_delete_minutes_requires_auth(self):
        """DELETE /api/minutes/{id} requires authentication"""
        response = requests.delete(f"{BASE_URL}/api/minutes/test_id")
        assert response.status_code == 401
        print("DELETE /api/minutes/{id} - requires auth (401)")
    
    def test_get_minutes_pdf_requires_auth(self):
        """GET /api/minutes/{id}/pdf requires authentication"""
        response = requests.get(f"{BASE_URL}/api/minutes/test_id/pdf")
        assert response.status_code == 401
        print("GET /api/minutes/{id}/pdf - requires auth (401)")
    
    def test_get_minutes_templates_requires_auth(self):
        """GET /api/minutes-templates requires authentication"""
        response = requests.get(f"{BASE_URL}/api/minutes-templates")
        assert response.status_code == 401
        print("GET /api/minutes-templates - requires auth (401)")
    
    def test_post_minutes_templates_requires_auth(self):
        """POST /api/minutes-templates requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/minutes-templates", 
            json={"trust_id": TRUST_ID, "template_type": "blank", "template_data": {}}
        )
        assert response.status_code == 401
        print("POST /api/minutes-templates - requires auth (401)")
    
    def test_get_template_options_requires_auth(self):
        """GET /api/template-options requires authentication"""
        response = requests.get(f"{BASE_URL}/api/template-options")
        assert response.status_code == 401
        print("GET /api/template-options - requires auth (401)")


class TestMinutesInvalidTrust:
    """Test minutes endpoints with invalid trust_id"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEMO_EMAIL,
            "password": DEMO_PASSWORD
        })
        assert response.status_code == 200
        return {"Authorization": f"Bearer {response.json()['token']}"}
    
    def test_create_minutes_invalid_trust(self, auth_headers):
        """POST /api/minutes with invalid trust returns 404"""
        payload = {
            "trust_id": "invalid_trust_id",
            "minutes_type": "annual",
            "meeting_date": "2025-01-01",
            "participants_text": "Test",
            "decisions_text": "Test"
        }
        response = requests.post(
            f"{BASE_URL}/api/minutes", 
            json=payload, 
            headers=auth_headers
        )
        assert response.status_code == 404
        print("POST /api/minutes with invalid trust - returns 404")
    
    def test_create_minutes_template_invalid_trust(self, auth_headers):
        """POST /api/minutes-templates with invalid trust returns 404"""
        payload = {
            "trust_id": "invalid_trust_id",
            "template_type": "blank",
            "template_data": {}
        }
        response = requests.post(
            f"{BASE_URL}/api/minutes-templates", 
            json=payload, 
            headers=auth_headers
        )
        assert response.status_code == 404
        print("POST /api/minutes-templates with invalid trust - returns 404")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
