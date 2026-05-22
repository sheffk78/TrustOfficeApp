"""
Test suite for Minutes Templates and Schedule A features
Tests: Template options, distribution template, trustee appointment template,
       property acceptance auto-add to Schedule A, Schedule A CRUD, PDF download
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test user credentials
TEST_EMAIL = "demo@trustoffice.com"
TEST_PASSWORD = "demo123"
TRUST_ID = "trust_99f798cab238"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for demo user"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Login failed: {response.text}")
    return response.json().get("token")


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Authenticated requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


class TestTemplateOptions:
    """Test GET /api/template-options endpoint"""
    
    def test_get_template_options_returns_6_templates(self, api_client):
        """Verify template options endpoint returns 6 template types"""
        response = api_client.get(f"{BASE_URL}/api/template-options")
        assert response.status_code == 200
        
        templates = response.json()
        assert isinstance(templates, list)
        assert len(templates) == 6, f"Expected 6 templates, got {len(templates)}"
        
        # Verify expected template types
        template_types = [t["type"] for t in templates]
        expected_types = [
            "blank",
            "general_meeting",
            "distribution_to_beneficiaries",
            "acceptance_of_property",
            "appointment_additional_trustee",
            "appointment_successor_trustee"
        ]
        for expected in expected_types:
            assert expected in template_types, f"Missing template type: {expected}"
    
    def test_template_options_have_required_fields(self, api_client):
        """Each template option should have type, name, description, icon"""
        response = api_client.get(f"{BASE_URL}/api/template-options")
        templates = response.json()
        
        required_fields = ["type", "name", "description", "icon"]
        for template in templates:
            for field in required_fields:
                assert field in template, f"Template {template.get('type')} missing field: {field}"


class TestDistributionTemplate:
    """Test distribution_to_beneficiaries template creation"""
    
    def test_create_distribution_template_with_all_fields(self, api_client):
        """Create distribution template with meeting info, distribution details, beneficiaries"""
        payload = {
            "trust_id": TRUST_ID,
            "template_type": "distribution_to_beneficiaries",
            "template_data": {
                "minute_number": f"TEST-{uuid.uuid4().hex[:6]}",
                "meeting_date": "January 25, 2026",
                "meeting_time": "2:00 PM",
                "meeting_type": "unanimous_written_consent",
                "trustees_present": ["Test Trustee 1", "Test Trustee 2"],
                "trust_formation_date": "January 1, 2020",
                "distribution_total": 100000,
                "distribution_items": [
                    {"beneficiary_name": "Beneficiary A", "amount": 60000, "percentage": 60},
                    {"beneficiary_name": "Beneficiary B", "amount": 40000, "percentage": 40}
                ],
                "distribution_date": "February 1, 2026",
                "distribution_characterization": "income"
            }
        }
        
        response = api_client.post(f"{BASE_URL}/api/minutes-templates", json=payload)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert data["template_type"] == "distribution_to_beneficiaries"
        assert data["minutes_id"].startswith("min_")
        assert "generated_document" in data
        
        # Verify WHEREAS/RESOLVED language in generated document
        doc = data["generated_document"]
        assert "WHEREAS" in doc, "Generated document should contain WHEREAS clause"
        assert "RESOLVED" in doc, "Generated document should contain RESOLVED clause"
        assert "Beneficiary A" in doc, "Beneficiary name should appear in document"
        assert "$60,000" in doc or "60,000" in doc, "Distribution amount should appear"


class TestTrusteeAppointmentTemplate:
    """Test trustee appointment templates"""
    
    def test_create_additional_trustee_template_with_required_fields(self, api_client):
        """Create additional trustee template with name, gender, signature requirements"""
        payload = {
            "trust_id": TRUST_ID,
            "template_type": "appointment_additional_trustee",
            "template_data": {
                "minute_number": f"TEST-{uuid.uuid4().hex[:6]}",
                "meeting_date": "January 25, 2026",
                "meeting_time": "10:00 AM",
                "trustees_present": ["Existing Trustee"],
                "trust_formation_date": "January 1, 2020",
                "new_trustee_name": "New Trustee Person",
                "new_trustee_gender": "woman",
                "signature_requirement": "any_two",
                "banking_powers_granted": True,
                "effective_date": "February 1, 2026"
            }
        }
        
        response = api_client.post(f"{BASE_URL}/api/minutes-templates", json=payload)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert data["template_type"] == "appointment_additional_trustee"
        
        # Verify new trustee info in document
        doc = data["generated_document"]
        assert "New Trustee Person" in doc
        assert "WHEREAS" in doc
        assert "RESOLVED" in doc
    
    def test_create_successor_trustee_template(self, api_client):
        """Create successor trustee template with departing trustee info"""
        payload = {
            "trust_id": TRUST_ID,
            "template_type": "appointment_successor_trustee",
            "template_data": {
                "minute_number": f"TEST-{uuid.uuid4().hex[:6]}",
                "meeting_date": "January 25, 2026",
                "trustees_present": ["Current Trustee"],
                "trust_formation_date": "January 1, 2020",
                "new_trustee_name": "Successor Trustee",
                "new_trustee_gender": "man",
                "departing_trustee_name": "Old Trustee",
                "departing_reason": "resigned",
                "signature_requirement": "any_one",
                "banking_powers_granted": True,
                "effective_date": "February 1, 2026"
            }
        }
        
        response = api_client.post(f"{BASE_URL}/api/minutes-templates", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        doc = data["generated_document"]
        assert "Successor Trustee" in doc
        assert "resigned" in doc.lower() or "resignation" in doc.lower()


class TestPropertyAcceptanceAutoAdd:
    """Test property acceptance template auto-adds to Schedule A"""
    
    def test_property_acceptance_auto_adds_to_schedule_a(self, api_client):
        """When add_to_schedule_a=True, asset should be added to Schedule A"""
        unique_desc = f"TEST Property {uuid.uuid4().hex[:8]}"
        
        payload = {
            "trust_id": TRUST_ID,
            "template_type": "acceptance_of_property",
            "template_data": {
                "minute_number": f"TEST-{uuid.uuid4().hex[:6]}",
                "meeting_date": "January 25, 2026",
                "trustees_present": ["Test Trustee"],
                "trust_formation_date": "January 1, 2020",
                "grantor_name": "John Test Grantor",
                "property_description": unique_desc,
                "property_value": 125000,
                "conveyance_date": "January 25, 2026",
                "add_to_schedule_a": True,
                "schedule_a_category": "real_property"
            }
        }
        
        response = api_client.post(f"{BASE_URL}/api/minutes-templates", json=payload)
        assert response.status_code == 200, f"Failed to create template: {response.text}"
        
        # Verify asset was added to Schedule A
        schedule_response = api_client.get(f"{BASE_URL}/api/schedule-a?trust_id={TRUST_ID}")
        assert schedule_response.status_code == 200
        
        assets = schedule_response.json()
        matching_assets = [a for a in assets if a["description"] == unique_desc]
        assert len(matching_assets) >= 1, f"Property '{unique_desc}' should be in Schedule A"
        
        asset = matching_assets[0]
        assert asset["category"] == "real_property"
        assert asset["approximate_value"] == 125000
        
        # Cleanup - delete the test asset
        api_client.delete(f"{BASE_URL}/api/schedule-a/{asset['item_id']}")


class TestScheduleACRUD:
    """Test Schedule A asset management CRUD operations"""
    
    @pytest.fixture
    def test_asset_id(self, api_client):
        """Create a test asset and yield its ID, cleanup after test"""
        payload = {
            "trust_id": TRUST_ID,
            "category": "financial_accounts",
            "description": f"TEST Brokerage Account {uuid.uuid4().hex[:6]}",
            "identifier": "****-9999",
            "location": "Test Bank",
            "approximate_value": 50000,
            "date_conveyed": "2026-01-25",
            "notes": "Test asset for pytest"
        }
        
        response = api_client.post(f"{BASE_URL}/api/schedule-a", json=payload)
        assert response.status_code == 200
        asset = response.json()
        yield asset["item_id"]
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/schedule-a/{asset['item_id']}")
    
    def test_create_schedule_a_asset(self, api_client):
        """Test creating a new Schedule A asset"""
        payload = {
            "trust_id": TRUST_ID,
            "category": "digital_assets",
            "description": f"TEST Bitcoin Holdings {uuid.uuid4().hex[:6]}",
            "identifier": "wallet-xyz",
            "location": "Cold Storage",
            "approximate_value": 25000,
            "date_conveyed": "2026-01-20",
            "notes": "Test crypto asset"
        }
        
        response = api_client.post(f"{BASE_URL}/api/schedule-a", json=payload)
        assert response.status_code == 200
        
        asset = response.json()
        assert asset["item_id"].startswith("asset_")
        assert asset["category"] == "digital_assets"
        assert asset["approximate_value"] == 25000
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/schedule-a/{asset['item_id']}")
    
    def test_get_schedule_a_assets(self, api_client):
        """Test retrieving Schedule A assets for a trust"""
        response = api_client.get(f"{BASE_URL}/api/schedule-a?trust_id={TRUST_ID}")
        assert response.status_code == 200
        
        assets = response.json()
        assert isinstance(assets, list)
        # Should have at least some assets from demo data
        assert len(assets) >= 1
    
    def test_update_schedule_a_asset(self, api_client, test_asset_id):
        """Test updating a Schedule A asset"""
        update_payload = {
            "description": "UPDATED Test Brokerage Account",
            "approximate_value": 75000
        }
        
        response = api_client.put(f"{BASE_URL}/api/schedule-a/{test_asset_id}", json=update_payload)
        assert response.status_code == 200
        
        updated = response.json()
        assert updated["description"] == "UPDATED Test Brokerage Account"
        assert updated["approximate_value"] == 75000
        assert updated["updated_at"] is not None
    
    def test_delete_schedule_a_asset(self, api_client):
        """Test deleting a Schedule A asset"""
        # Create asset to delete
        payload = {
            "trust_id": TRUST_ID,
            "category": "other_property",
            "description": f"TO DELETE Asset {uuid.uuid4().hex[:6]}",
            "date_conveyed": "2026-01-25"
        }
        
        create_response = api_client.post(f"{BASE_URL}/api/schedule-a", json=payload)
        assert create_response.status_code == 200
        asset_id = create_response.json()["item_id"]
        
        # Delete the asset
        delete_response = api_client.delete(f"{BASE_URL}/api/schedule-a/{asset_id}")
        assert delete_response.status_code == 200
        
        # Verify deletion
        get_response = api_client.get(f"{BASE_URL}/api/schedule-a/{asset_id}")
        assert get_response.status_code == 404
    
    def test_schedule_a_summary_with_totals(self, api_client):
        """Test Schedule A summary endpoint returns category totals"""
        response = api_client.get(f"{BASE_URL}/api/schedule-a/summary/{TRUST_ID}")
        assert response.status_code == 200
        
        summary = response.json()
        assert "total_items" in summary
        assert "total_value" in summary
        assert "categories" in summary
        assert summary["trust_id"] == TRUST_ID


class TestMinutesDocumentGeneration:
    """Test that generated minutes contain proper legal language"""
    
    def test_generated_document_has_whereas_resolved(self, api_client):
        """All templates should generate documents with WHEREAS/RESOLVED language"""
        payload = {
            "trust_id": TRUST_ID,
            "template_type": "general_meeting",
            "template_data": {
                "minute_number": f"TEST-{uuid.uuid4().hex[:6]}",
                "meeting_date": "January 25, 2026",
                "trustees_present": ["Test Trustee"],
                "trust_formation_date": "January 1, 2020",
                "resolutions": [
                    {
                        "title": "Test Resolution",
                        "whereas_clauses": ["The trust needs to test something"],
                        "resolved_clauses": ["The test shall pass"]
                    }
                ]
            }
        }
        
        response = api_client.post(f"{BASE_URL}/api/minutes-templates", json=payload)
        assert response.status_code == 200
        
        doc = response.json()["generated_document"]
        assert "WHEREAS" in doc
        assert "RESOLVED" in doc or "BE IT RESOLVED" in doc


class TestMinutesPreviewEdit:
    """Test minutes preview and edit functionality"""
    
    def test_update_minutes_document(self, api_client):
        """Test that minutes preview can be edited before saving"""
        # Create a template
        payload = {
            "trust_id": TRUST_ID,
            "template_type": "general_meeting",
            "template_data": {
                "minute_number": f"TEST-{uuid.uuid4().hex[:6]}",
                "meeting_date": "January 25, 2026",
                "trustees_present": ["Test Trustee"],
                "trust_formation_date": "January 1, 2020"
            }
        }
        
        create_response = api_client.post(f"{BASE_URL}/api/minutes-templates", json=payload)
        assert create_response.status_code == 200
        minutes_id = create_response.json()["minutes_id"]
        
        # Update the document
        edited_doc = "EDITED DOCUMENT CONTENT - This is a test edit"
        update_payload = {
            "generated_document": edited_doc,
            "status": "final"
        }
        
        update_response = api_client.put(f"{BASE_URL}/api/minutes-templates/{minutes_id}", json=update_payload)
        assert update_response.status_code == 200
        
        updated = update_response.json()
        assert updated["generated_document"] == edited_doc
        assert updated["status"] == "final"
        assert updated["original_document"] != edited_doc  # Original preserved
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/minutes-templates/{minutes_id}")


class TestPDFDownload:
    """Test PDF download functionality for minutes"""
    
    def test_pdf_download_returns_base64(self, api_client):
        """Test PDF download endpoint returns base64 encoded PDF"""
        # Create a template first
        payload = {
            "trust_id": TRUST_ID,
            "template_type": "general_meeting",
            "template_data": {
                "minute_number": f"PDF-TEST-{uuid.uuid4().hex[:6]}",
                "meeting_date": "January 25, 2026",
                "trustees_present": ["Test Trustee"],
                "trust_formation_date": "January 1, 2020"
            }
        }
        
        create_response = api_client.post(f"{BASE_URL}/api/minutes-templates", json=payload)
        assert create_response.status_code == 200
        minutes_id = create_response.json()["minutes_id"]
        
        # Get PDF
        pdf_response = api_client.get(f"{BASE_URL}/api/minutes-templates/{minutes_id}/pdf")
        assert pdf_response.status_code == 200
        
        pdf_data = pdf_response.json()
        assert "pdf_base64" in pdf_data
        assert "filename" in pdf_data
        assert pdf_data["filename"].endswith(".pdf")
        assert len(pdf_data["pdf_base64"]) > 100  # PDF should have content
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/minutes-templates/{minutes_id}")
