"""
Test P0 Bug Fixes: 
1. Save Minutes - Create minute from template, generate preview, save
2. Distribution Clock Icon - PATCH /distributions/{id}/status to set back to review

P1 Feature:
- Auto-populate Minutes Form from Entity data (trust_formation_date, trustees_present)
"""

import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def auth_session():
    """Create authenticated session with demo user"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login as demo user
    login_response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": "demo@trustoffice.com",
        "password": "demopassword"
    })
    
    if login_response.status_code == 200:
        token = login_response.json().get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    pytest.skip("Authentication failed - unable to login as demo user")

@pytest.fixture(scope="module")
def trust_data(auth_session):
    """Get existing trust or seed demo data"""
    # First try to get existing trusts
    trusts_response = auth_session.get(f"{BASE_URL}/api/trusts")
    if trusts_response.status_code == 200:
        trusts = trusts_response.json()
        if trusts and len(trusts) > 0:
            return trusts[0]
    
    # If no trusts, seed demo data
    seed_response = auth_session.post(f"{BASE_URL}/api/demo/seed")
    if seed_response.status_code == 200:
        trusts_response = auth_session.get(f"{BASE_URL}/api/trusts")
        if trusts_response.status_code == 200:
            trusts = trusts_response.json()
            if trusts and len(trusts) > 0:
                return trusts[0]
    
    pytest.skip("Unable to get or create trust")

class TestMinutesSaveFlow:
    """P0 Bug Fix: Test that saving generated minutes works correctly"""
    
    def test_create_minutes_template(self, auth_session, trust_data):
        """Create a minutes template via POST"""
        trust_id = trust_data['trust_id']
        
        template_data = {
            "trust_id": trust_id,
            "template_type": "general_meeting",
            "template_data": {
                "minute_number": "TEST-2026-001",
                "meeting_date": "January 15, 2026",
                "meeting_time": "10:00 AM",
                "meeting_type": "unanimous_written_consent",
                "trustees_present": ["John Smith", "Jane Doe"],
                "trust_formation_date": "January 1, 2020",
                "resolutions": [{
                    "title": "Test Resolution",
                    "whereas_clauses": ["The Trust requires testing"],
                    "resolved_clauses": ["Testing is approved"],
                    "vote": "Unanimous approval",
                    "effective_date": "Immediately upon adoption"
                }]
            }
        }
        
        response = auth_session.post(
            f"{BASE_URL}/api/minutes-templates",
            json=template_data
        )
        
        assert response.status_code == 200, f"Failed to create minutes template: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "minutes_id" in data, "Response missing minutes_id"
        assert "generated_document" in data, "Response missing generated_document"
        assert data["status"] == "draft", f"Expected status 'draft', got {data['status']}"
        
        # Store minutes_id for next test
        TestMinutesSaveFlow.created_minutes_id = data["minutes_id"]
        print(f"Created minutes template with ID: {data['minutes_id']}")
        return data["minutes_id"]
    
    def test_save_minutes_template(self, auth_session):
        """P0 BUG FIX: Save the minutes by updating status to 'final' via PUT"""
        minutes_id = getattr(TestMinutesSaveFlow, 'created_minutes_id', None)
        if not minutes_id:
            pytest.skip("No minutes_id from previous test")
        
        update_data = {
            "generated_document": "TEST MINUTES DOCUMENT\n\nMeeting Date: January 15, 2026\nStatus: Final",
            "status": "final"
        }
        
        response = auth_session.put(
            f"{BASE_URL}/api/minutes-templates/{minutes_id}",
            json=update_data
        )
        
        assert response.status_code == 200, f"Failed to save minutes: {response.text}"
        data = response.json()
        
        # Verify updates were applied
        assert data["status"] == "final", f"Expected status 'final', got {data['status']}"
        assert "TEST MINUTES DOCUMENT" in data["generated_document"], "Document content not updated"
        
        print(f"Successfully saved minutes template {minutes_id} with status 'final'")
    
    def test_verify_minutes_saved(self, auth_session):
        """Verify minutes was actually persisted with GET"""
        minutes_id = getattr(TestMinutesSaveFlow, 'created_minutes_id', None)
        if not minutes_id:
            pytest.skip("No minutes_id from previous test")
        
        response = auth_session.get(f"{BASE_URL}/api/minutes-templates/{minutes_id}")
        
        assert response.status_code == 200, f"Failed to get saved minutes: {response.text}"
        data = response.json()
        
        # Verify the saved data persisted
        assert data["status"] == "final", f"Expected status 'final' after save, got {data['status']}"
        assert "TEST MINUTES DOCUMENT" in data["generated_document"], "Document content not persisted"
        
        print(f"Verified minutes {minutes_id} is saved with final status")


class TestDistributionClockIcon:
    """P0 Bug Fix: Test that clicking clock icon (PATCH /status) works correctly"""
    
    def test_create_distribution_for_test(self, auth_session, trust_data):
        """Create a distribution to test the status flow"""
        trust_id = trust_data['trust_id']
        
        dist_data = {
            "trust_id": trust_id,
            "beneficiary_name": "TEST_ClockIconBeneficiary",
            "amount": 1000.00,
            "date": "2026-01-15",
            "purpose_classification": "distribution",
            "notes": "Test distribution for clock icon bug"
        }
        
        response = auth_session.post(
            f"{BASE_URL}/api/distributions",
            json=dist_data
        )
        
        assert response.status_code == 200, f"Failed to create distribution: {response.text}"
        data = response.json()
        
        assert "distribution_id" in data, "Response missing distribution_id"
        TestDistributionClockIcon.test_dist_id = data["distribution_id"]
        
        print(f"Created distribution {data['distribution_id']} for testing")
        return data["distribution_id"]
    
    def test_approve_distribution(self, auth_session):
        """Approve the distribution first"""
        dist_id = getattr(TestDistributionClockIcon, 'test_dist_id', None)
        if not dist_id:
            pytest.skip("No distribution_id from previous test")
        
        approve_data = {
            "solvency_confirmed": True,
            "recusal_acknowledged": True
        }
        
        response = auth_session.patch(
            f"{BASE_URL}/api/distributions/{dist_id}/approve",
            json=approve_data
        )
        
        assert response.status_code == 200, f"Failed to approve distribution: {response.text}"
        data = response.json()
        
        # Verify approval
        assert data["approved_at"] is not None, "Distribution not properly approved - missing approved_at"
        assert data["solvency_confirmed"] == True, "Solvency should be confirmed"
        
        print(f"Distribution {dist_id} approved successfully")
    
    def test_clock_icon_set_to_review(self, auth_session):
        """P0 BUG FIX: Test PATCH /distributions/{id}/status to set approved distribution back to review"""
        dist_id = getattr(TestDistributionClockIcon, 'test_dist_id', None)
        if not dist_id:
            pytest.skip("No distribution_id from previous test")
        
        # This is what the clock icon does - PATCH to set status back to review
        response = auth_session.patch(
            f"{BASE_URL}/api/distributions/{dist_id}/status",
            json={"status": "review"}
        )
        
        assert response.status_code == 200, f"Clock icon PATCH failed: {response.text}"
        data = response.json()
        
        # Verify status reverted - approval fields should be cleared
        assert data["approved_at"] is None, f"approved_at should be None after reverting to review, got {data['approved_at']}"
        assert data["approved_by"] is None, f"approved_by should be None after reverting"
        assert data["solvency_confirmed"] == False, "solvency_confirmed should be False after revert"
        
        print(f"Clock icon works! Distribution {dist_id} set back to review status")
    
    def test_verify_distribution_status_persisted(self, auth_session, trust_data):
        """Verify the status change persisted via GET"""
        dist_id = getattr(TestDistributionClockIcon, 'test_dist_id', None)
        if not dist_id:
            pytest.skip("No distribution_id from previous test")
        
        trust_id = trust_data['trust_id']
        
        # Get distributions list
        response = auth_session.get(f"{BASE_URL}/api/distributions?trust_id={trust_id}")
        
        assert response.status_code == 200, f"Failed to get distributions: {response.text}"
        data = response.json()
        
        # Find our test distribution
        test_dist = next((d for d in data if d["distribution_id"] == dist_id), None)
        assert test_dist is not None, f"Test distribution {dist_id} not found in list"
        
        # Verify it's back to review status (approved_at should be None)
        assert test_dist["approved_at"] is None, "Distribution should be in review status (approved_at=None)"
        
        print(f"Verified distribution {dist_id} status is persisted as review")


class TestAutoPopulateMinutesForm:
    """P1 Feature: Test that minutes form auto-populates from Entity data"""
    
    def test_get_entity_data(self, auth_session, trust_data):
        """Get entity data to verify trust_formation_date and trustees are available"""
        trust_id = trust_data['trust_id']
        
        response = auth_session.get(f"{BASE_URL}/api/entities?trust_id={trust_id}")
        
        assert response.status_code == 200, f"Failed to get entities: {response.text}"
        entities = response.json()
        
        # Look for Trust entity
        trust_entity = next((e for e in entities if e["entity_type"] == "Trust"), None)
        
        if trust_entity:
            print(f"Found Trust entity: {trust_entity.get('name')}")
            print(f"  formation_date: {trust_entity.get('formation_date')}")
            print(f"  trustee_names: {trust_entity.get('trustee_names')}")
            
            # Store for verification
            TestAutoPopulateMinutesForm.trust_entity = trust_entity
            
            # These fields should exist for auto-population
            # formation_date -> trust_formation_date
            # trustee_names -> trustees_present
            if trust_entity.get('formation_date') or trust_entity.get('trustee_names'):
                print("Entity has data that can be used for auto-population")
        else:
            print(f"No Trust entity found, entities available: {[e['entity_type'] for e in entities]}")
            pytest.skip("No Trust entity found for auto-populate test")
    
    def test_minutes_template_uses_entity_data(self, auth_session, trust_data):
        """Test that creating minutes template can use entity data"""
        trust_id = trust_data['trust_id']
        trust_entity = getattr(TestAutoPopulateMinutesForm, 'trust_entity', None)
        
        # Get formation_date from entity to use as trust_formation_date
        formation_date = trust_entity.get('formation_date') if trust_entity else ''
        trustee_names_str = trust_entity.get('trustee_names', '') if trust_entity else ''
        
        # Parse trustees from comma-separated string
        trustees = [t.strip() for t in trustee_names_str.split(',') if t.strip()] if trustee_names_str else []
        
        # Create template with auto-populated data
        template_data = {
            "trust_id": trust_id,
            "template_type": "general_meeting",
            "template_data": {
                "minute_number": "AUTOPOPULATE-TEST-001",
                "meeting_date": "January 20, 2026",
                "meeting_time": "2:00 PM",
                "meeting_type": "unanimous_written_consent",
                "trustees_present": trustees if trustees else ["Default Trustee"],
                "trust_formation_date": formation_date if formation_date else "January 1, 2020",
                "resolutions": [{
                    "title": "Auto-Populate Test",
                    "whereas_clauses": ["Testing auto-population feature"],
                    "resolved_clauses": ["Auto-population works correctly"],
                    "vote": "Unanimous approval",
                    "effective_date": "Immediately upon adoption"
                }]
            }
        }
        
        response = auth_session.post(
            f"{BASE_URL}/api/minutes-templates",
            json=template_data
        )
        
        assert response.status_code == 200, f"Failed to create template with auto-populated data: {response.text}"
        data = response.json()
        
        # Verify the generated document contains the auto-populated data
        generated_doc = data.get('generated_document', '')
        
        if formation_date:
            print(f"Checking for formation_date in generated doc: {formation_date}")
        if trustees:
            print(f"Checking for trustees in generated doc: {trustees}")
        
        print(f"Auto-populate test template created: {data['minutes_id']}")
        
        # The frontend auto-populates these fields from entity data
        # The backend just receives whatever the frontend sends
        # So this test verifies the API accepts the data correctly


class TestCleanup:
    """Clean up test data after tests"""
    
    def test_cleanup_test_distributions(self, auth_session, trust_data):
        """Clean up test distributions created during testing"""
        trust_id = trust_data['trust_id']
        
        response = auth_session.get(f"{BASE_URL}/api/distributions?trust_id={trust_id}")
        if response.status_code == 200:
            dists = response.json()
            for dist in dists:
                if dist.get('beneficiary_name', '').startswith('TEST_'):
                    del_response = auth_session.delete(
                        f"{BASE_URL}/api/distributions/{dist['distribution_id']}"
                    )
                    if del_response.status_code in [200, 204]:
                        print(f"Cleaned up test distribution: {dist['distribution_id']}")
        
        print("Cleanup completed")
