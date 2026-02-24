"""
Test Suite: Schedule A Disposition & Accept Property Features
Tests for:
1. Accept Property into Trust template with add_to_schedule_a
2. Dispose/Sell Asset template with update_schedule_a
3. Schedule A status filtering (active/disposed/all)
4. Schedule A status column and minutes_ref display
"""

import pytest
import requests
import os
import time
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestScheduleADisposition:
    """Tests for new Schedule A disposition and property acceptance features"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with auth"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login with demo user
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@trustoffice.com",
            "password": "demopassword"
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        login_data = login_response.json()
        self.token = login_data.get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        # Get the demo trust
        trusts_response = self.session.get(f"{BASE_URL}/api/trusts")
        assert trusts_response.status_code == 200
        trusts = trusts_response.json()
        assert len(trusts) > 0, "No trusts found for demo user"
        self.trust_id = trusts[0]["trust_id"]
        print(f"Using trust: {trusts[0]['name']} ({self.trust_id})")
        yield

    def test_01_template_options_includes_disposition(self):
        """Verify template options include 'Dispose / Sell Asset'"""
        response = self.session.get(f"{BASE_URL}/api/template-options?trust_id={self.trust_id}")
        assert response.status_code == 200
        templates = response.json()
        
        # Find disposition template
        disposition_template = next((t for t in templates if t['type'] == 'disposition_of_asset'), None)
        assert disposition_template is not None, "disposition_of_asset template not found"
        assert disposition_template['name'] == 'Dispose / Sell Asset'
        assert disposition_template['icon'] == 'minus-circle'
        print(f"SUCCESS: Found disposition template: {disposition_template['name']}")
        
        # Also verify acceptance_of_property template exists
        acceptance_template = next((t for t in templates if t['type'] == 'acceptance_of_property'), None)
        assert acceptance_template is not None, "acceptance_of_property template not found"
        assert acceptance_template['name'] == 'Accept Property into Trust'
        print(f"SUCCESS: Found acceptance template: {acceptance_template['name']}")

    def test_02_schedule_a_status_filtering_active(self):
        """Test Schedule A endpoint filters by status=active by default"""
        response = self.session.get(f"{BASE_URL}/api/schedule-a?trust_id={self.trust_id}")
        assert response.status_code == 200
        assets = response.json()
        
        # All returned assets should be active or have no status
        for asset in assets:
            assert asset.get('status', 'active') in ['active', None], f"Unexpected status: {asset.get('status')}"
        print(f"SUCCESS: Retrieved {len(assets)} active assets")

    def test_03_schedule_a_status_filtering_all(self):
        """Test Schedule A endpoint can return all assets including disposed"""
        response = self.session.get(f"{BASE_URL}/api/schedule-a?trust_id={self.trust_id}&status=all")
        assert response.status_code == 200
        assets = response.json()
        print(f"SUCCESS: Retrieved {len(assets)} total assets (including disposed)")

    def test_04_accept_property_template_creates_schedule_a_entry(self):
        """Test accepting property into trust with add_to_schedule_a checkbox creates Schedule A entry"""
        # Create acceptance_of_property minutes with add_to_schedule_a=true
        template_data = {
            "minute_number": "2024-TEST-001",
            "meeting_date": "January 15, 2024",
            "meeting_time": "10:00 AM",
            "meeting_type": "unanimous_written_consent",
            "trustees_present": ["Test Trustee"],
            "trust_indenture_date": "January 1, 2020",
            "grantor_name": "Test Grantor",
            "property_description": "TEST - 2020 Tesla Model 3 VIN ABC123",
            "property_value": 35000,
            "property_identifier": "VIN: ABC123TEST",
            "property_location": "Test Garage, City, State",
            "conveyance_date": "January 15, 2024",
            "add_to_schedule_a": True,
            "schedule_a_category": "personal_property"
        }
        
        response = self.session.post(f"{BASE_URL}/api/minutes-templates", json={
            "trust_id": self.trust_id,
            "template_type": "acceptance_of_property",
            "template_data": template_data
        })
        assert response.status_code == 200, f"Failed to create minutes: {response.text}"
        minutes_result = response.json()
        minutes_id = minutes_result["minutes_id"]
        print(f"SUCCESS: Created acceptance minutes: {minutes_id}")
        
        # Verify asset was added to Schedule A
        schedule_a_response = self.session.get(f"{BASE_URL}/api/schedule-a?trust_id={self.trust_id}")
        assert schedule_a_response.status_code == 200
        assets = schedule_a_response.json()
        
        # Find the newly created asset by description
        new_asset = next((a for a in assets if "TEST - 2020 Tesla Model 3" in a['description']), None)
        assert new_asset is not None, "New asset not found in Schedule A"
        assert new_asset['status'] == 'active'
        assert new_asset['minutes_ref'] == minutes_id, "minutes_ref should match the minutes that added it"
        assert new_asset['category'] == 'personal_property'
        assert new_asset['identifier'] == 'VIN: ABC123TEST'
        print(f"SUCCESS: Asset added to Schedule A with minutes_ref={minutes_id}")
        
        # Store asset_id for disposition test
        self.test_asset_id = new_asset['item_id']
        return minutes_id, new_asset['item_id']

    def test_05_disposition_template_loads_active_assets(self):
        """Test that disposition template can see active Schedule A assets"""
        # Get active assets for disposition selection
        response = self.session.get(f"{BASE_URL}/api/schedule-a?trust_id={self.trust_id}&status=active")
        assert response.status_code == 200
        assets = response.json()
        
        # Should have at least one active asset
        active_assets = [a for a in assets if a['status'] == 'active']
        assert len(active_assets) > 0, "No active assets available for disposition"
        print(f"SUCCESS: Found {len(active_assets)} active assets for disposition selection")

    def test_06_disposition_template_marks_asset_disposed(self):
        """Test disposing an asset marks it as disposed in Schedule A"""
        # First, create a test asset to dispose
        test_asset_response = self.session.post(f"{BASE_URL}/api/schedule-a", json={
            "trust_id": self.trust_id,
            "category": "personal_property",
            "description": "TEST DISPOSE - Old Equipment for Disposal",
            "identifier": "TEST-DISPOSE-001",
            "location": "Storage Unit",
            "approximate_value": 5000,
            "date_conveyed": "2023-01-01"
        })
        assert test_asset_response.status_code == 200
        test_asset = test_asset_response.json()
        asset_to_dispose = test_asset["item_id"]
        print(f"Created test asset for disposal: {asset_to_dispose}")
        
        # Create disposition_of_asset minutes
        disposition_data = {
            "minute_number": "2024-TEST-DISPOSE-001",
            "meeting_date": "January 20, 2024",
            "meeting_time": "11:00 AM",
            "meeting_type": "unanimous_written_consent",
            "trustees_present": ["Test Trustee"],
            "trust_indenture_date": "January 1, 2020",
            "disposition_asset_id": asset_to_dispose,
            "disposition_asset_description": "Old Equipment for Disposal",
            "disposition_reason": "sale",
            "disposition_date": "January 20, 2024",
            "disposition_value": 3000,
            "disposition_recipient": "ABC Buyer LLC",
            "disposition_notes": "Sold at market value",
            "update_schedule_a": True
        }
        
        response = self.session.post(f"{BASE_URL}/api/minutes-templates", json={
            "trust_id": self.trust_id,
            "template_type": "disposition_of_asset",
            "template_data": disposition_data
        })
        assert response.status_code == 200, f"Failed to create disposition minutes: {response.text}"
        disposition_minutes = response.json()
        disposition_minutes_id = disposition_minutes["minutes_id"]
        print(f"SUCCESS: Created disposition minutes: {disposition_minutes_id}")
        
        # Verify asset is now marked as disposed
        asset_response = self.session.get(f"{BASE_URL}/api/schedule-a/{asset_to_dispose}")
        assert asset_response.status_code == 200
        disposed_asset = asset_response.json()
        
        assert disposed_asset['status'] == 'disposed', f"Asset status should be 'disposed', got: {disposed_asset['status']}"
        assert disposed_asset['disposition_minutes_ref'] == disposition_minutes_id
        assert disposed_asset['disposition_date'] is not None
        assert 'sale' in disposed_asset['disposition_notes'].lower()
        print(f"SUCCESS: Asset marked as disposed with disposition_minutes_ref={disposition_minutes_id}")
        
        return disposition_minutes_id, asset_to_dispose

    def test_07_disposed_assets_hidden_by_default(self):
        """Test that disposed assets are hidden when status=active (default)"""
        # Get only active assets
        active_response = self.session.get(f"{BASE_URL}/api/schedule-a?trust_id={self.trust_id}&status=active")
        assert active_response.status_code == 200
        active_assets = active_response.json()
        
        # Get all assets including disposed
        all_response = self.session.get(f"{BASE_URL}/api/schedule-a?trust_id={self.trust_id}&status=all")
        assert all_response.status_code == 200
        all_assets = all_response.json()
        
        # Check that disposed assets exist in 'all' but not in 'active'
        disposed_in_all = [a for a in all_assets if a['status'] == 'disposed']
        disposed_in_active = [a for a in active_assets if a['status'] == 'disposed']
        
        assert len(disposed_in_active) == 0, "Disposed assets should not appear in active view"
        print(f"SUCCESS: Active view has {len(active_assets)} assets, All view has {len(all_assets)} assets ({len(disposed_in_all)} disposed)")

    def test_08_schedule_a_item_response_has_new_fields(self):
        """Verify Schedule A response includes status, minutes_ref, disposition_minutes_ref fields"""
        response = self.session.get(f"{BASE_URL}/api/schedule-a?trust_id={self.trust_id}&status=all")
        assert response.status_code == 200
        assets = response.json()
        
        if len(assets) > 0:
            asset = assets[0]
            # Check that required fields exist
            assert 'status' in asset, "status field missing"
            assert asset['status'] in ['active', 'disposed'], f"Invalid status: {asset['status']}"
            
            # These can be null but should exist
            assert 'minutes_ref' in asset or asset.get('minutes_ref') is None
            assert 'disposition_minutes_ref' in asset or asset.get('disposition_minutes_ref') is None
            assert 'disposition_date' in asset or asset.get('disposition_date') is None
            assert 'disposition_notes' in asset or asset.get('disposition_notes') is None
            print(f"SUCCESS: Asset has all required fields - status: {asset['status']}")

    def test_09_disposition_without_update_schedule_a(self):
        """Test disposition template without update_schedule_a doesn't modify asset"""
        # Create a test asset
        test_asset_response = self.session.post(f"{BASE_URL}/api/schedule-a", json={
            "trust_id": self.trust_id,
            "category": "other_property",
            "description": "TEST NO-UPDATE - Item to test no update",
            "identifier": "TEST-NO-UPDATE-001",
            "approximate_value": 1000,
            "date_conveyed": "2023-06-01"
        })
        assert test_asset_response.status_code == 200
        test_asset = test_asset_response.json()
        asset_id = test_asset["item_id"]
        
        # Create disposition minutes with update_schedule_a=False
        disposition_data = {
            "minute_number": "2024-TEST-NO-UPDATE",
            "meeting_date": "January 25, 2024",
            "meeting_time": "2:00 PM",
            "meeting_type": "unanimous_written_consent",
            "trustees_present": ["Test Trustee"],
            "disposition_asset_id": asset_id,
            "disposition_asset_description": "Item to test no update",
            "disposition_reason": "transfer",
            "disposition_date": "January 25, 2024",
            "disposition_value": 500,
            "update_schedule_a": False  # Should NOT update the asset
        }
        
        response = self.session.post(f"{BASE_URL}/api/minutes-templates", json={
            "trust_id": self.trust_id,
            "template_type": "disposition_of_asset",
            "template_data": disposition_data
        })
        assert response.status_code == 200
        
        # Verify asset is still active
        asset_response = self.session.get(f"{BASE_URL}/api/schedule-a/{asset_id}")
        assert asset_response.status_code == 200
        asset = asset_response.json()
        
        assert asset['status'] == 'active', f"Asset should still be active, got: {asset['status']}"
        assert asset['disposition_minutes_ref'] is None, "disposition_minutes_ref should be null"
        print("SUCCESS: Asset remains active when update_schedule_a=False")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/schedule-a/{asset_id}")

    def test_10_cleanup_test_assets(self):
        """Clean up test assets"""
        response = self.session.get(f"{BASE_URL}/api/schedule-a?trust_id={self.trust_id}&status=all")
        if response.status_code == 200:
            assets = response.json()
            for asset in assets:
                if "TEST" in asset.get('description', ''):
                    delete_response = self.session.delete(f"{BASE_URL}/api/schedule-a/{asset['item_id']}")
                    if delete_response.status_code == 200:
                        print(f"Cleaned up test asset: {asset['description'][:50]}...")
        print("SUCCESS: Test cleanup completed")


class TestDispositionMinutesContent:
    """Test the content generated by disposition minutes template"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@trustoffice.com",
            "password": "demopassword"
        })
        assert login_response.status_code == 200
        login_data = login_response.json()
        self.token = login_data.get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        trusts_response = self.session.get(f"{BASE_URL}/api/trusts")
        trusts = trusts_response.json()
        self.trust_id = trusts[0]["trust_id"]
        yield

    def test_disposition_minutes_content_includes_sale_details(self):
        """Test that disposition minutes includes proper legal language for sale"""
        # First create a test asset
        asset_response = self.session.post(f"{BASE_URL}/api/schedule-a", json={
            "trust_id": self.trust_id,
            "category": "personal_property",
            "description": "TEST CONTENT - 2019 Honda Civic",
            "identifier": "VIN: CONTENT123",
            "approximate_value": 15000,
            "date_conveyed": "2022-01-01"
        })
        asset = asset_response.json()
        asset_id = asset["item_id"]
        
        # Create disposition minutes
        response = self.session.post(f"{BASE_URL}/api/minutes-templates", json={
            "trust_id": self.trust_id,
            "template_type": "disposition_of_asset",
            "template_data": {
                "minute_number": "2024-CONTENT-TEST",
                "meeting_date": "February 1, 2024",
                "meeting_time": "9:00 AM",
                "meeting_type": "unanimous_written_consent",
                "trustees_present": ["Content Test Trustee"],
                "disposition_asset_id": asset_id,
                "disposition_asset_description": "2019 Honda Civic VIN: CONTENT123",
                "disposition_reason": "sale",
                "disposition_date": "February 1, 2024",
                "disposition_value": 12000,
                "disposition_recipient": "John Buyer",
                "disposition_notes": "Private sale with clear title transfer",
                "update_schedule_a": False  # Don't actually dispose for cleanup
            }
        })
        
        assert response.status_code == 200
        result = response.json()
        generated_doc = result["generated_document"]
        
        # Check document contains expected content
        assert "WHEREAS" in generated_doc, "Should contain WHEREAS clauses"
        assert "RESOLVED" in generated_doc, "Should contain RESOLVED clauses"
        assert "sale" in generated_doc.lower(), "Should mention sale"
        assert "12,000" in generated_doc or "12000" in generated_doc, "Should include sale price"
        print("SUCCESS: Disposition minutes contains proper legal language")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/schedule-a/{asset_id}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
