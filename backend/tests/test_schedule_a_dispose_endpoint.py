"""
Test Suite: Schedule A Dispose Endpoint (POST /api/schedule-a/{item_id}/dispose)
Tests for the new direct dispose endpoint that marks assets as disposed without creating minutes.

Features tested:
1. POST /api/schedule-a/{item_id}/dispose endpoint works
2. Endpoint validates required fields
3. Asset status is properly updated
4. Disposed assets can be retrieved with status=all
5. Already disposed assets cannot be disposed again
"""

import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestDisposeEndpoint:
    """Tests for POST /api/schedule-a/{item_id}/dispose endpoint"""
    
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
        
        # Create test assets list for cleanup
        self.test_assets = []
        yield
        
        # Cleanup test assets
        for asset_id in self.test_assets:
            try:
                self.session.delete(f"{BASE_URL}/api/schedule-a/{asset_id}")
            except:
                pass

    def test_01_dispose_endpoint_marks_asset_as_disposed(self):
        """Test POST /api/schedule-a/{item_id}/dispose marks asset as disposed"""
        # Create a test asset
        create_response = self.session.post(f"{BASE_URL}/api/schedule-a", json={
            "trust_id": self.trust_id,
            "category": "personal_property",
            "description": "TEST DISPOSE EP - Asset for disposal endpoint test",
            "identifier": "TEST-EP-001",
            "location": "Test Location",
            "approximate_value": 5000,
            "date_conveyed": "2023-01-01"
        })
        assert create_response.status_code == 200
        asset = create_response.json()
        asset_id = asset["item_id"]
        self.test_assets.append(asset_id)
        print(f"Created test asset: {asset_id}")
        
        # Dispose the asset using the new endpoint
        dispose_response = self.session.post(f"{BASE_URL}/api/schedule-a/{asset_id}/dispose", json={
            "disposition_date": "2024-01-15",
            "disposition_reason": "sale",
            "disposition_value": 4000,
            "disposition_recipient": "Test Buyer LLC",
            "disposition_notes": "Sold at below market value due to condition"
        })
        assert dispose_response.status_code == 200, f"Dispose failed: {dispose_response.text}"
        result = dispose_response.json()
        assert result["message"] == "Asset marked as disposed"
        assert result["item_id"] == asset_id
        print(f"SUCCESS: Asset disposed via endpoint")
        
        # Verify asset status is now disposed
        get_response = self.session.get(f"{BASE_URL}/api/schedule-a/{asset_id}")
        assert get_response.status_code == 200
        disposed_asset = get_response.json()
        assert disposed_asset["status"] == "disposed", f"Expected 'disposed', got {disposed_asset['status']}"
        assert disposed_asset["disposition_date"] == "2024-01-15"
        assert "sale" in disposed_asset["disposition_notes"].lower()
        assert "Test Buyer LLC" in disposed_asset["disposition_notes"]
        print(f"SUCCESS: Asset status verified as disposed with correct notes")

    def test_02_dispose_endpoint_with_minimal_data(self):
        """Test dispose endpoint works with only required fields"""
        # Create a test asset
        create_response = self.session.post(f"{BASE_URL}/api/schedule-a", json={
            "trust_id": self.trust_id,
            "category": "other_property",
            "description": "TEST DISPOSE EP - Minimal data test",
            "identifier": "TEST-EP-002",
            "approximate_value": 1000,
            "date_conveyed": "2023-06-01"
        })
        asset = create_response.json()
        asset_id = asset["item_id"]
        self.test_assets.append(asset_id)
        
        # Dispose with minimal required fields only
        dispose_response = self.session.post(f"{BASE_URL}/api/schedule-a/{asset_id}/dispose", json={
            "disposition_date": "2024-02-01",
            "disposition_reason": "donation"
            # No value, recipient, or notes
        })
        assert dispose_response.status_code == 200
        print("SUCCESS: Dispose endpoint works with minimal required fields")
        
        # Verify
        get_response = self.session.get(f"{BASE_URL}/api/schedule-a/{asset_id}")
        disposed_asset = get_response.json()
        assert disposed_asset["status"] == "disposed"
        assert "donation" in disposed_asset["disposition_notes"].lower()

    def test_03_dispose_already_disposed_returns_error(self):
        """Test that disposing an already disposed asset returns 400 error"""
        # Create and dispose a test asset
        create_response = self.session.post(f"{BASE_URL}/api/schedule-a", json={
            "trust_id": self.trust_id,
            "category": "financial_accounts",
            "description": "TEST DISPOSE EP - Already disposed test",
            "identifier": "TEST-EP-003",
            "approximate_value": 2000,
            "date_conveyed": "2023-03-01"
        })
        asset = create_response.json()
        asset_id = asset["item_id"]
        self.test_assets.append(asset_id)
        
        # First dispose
        dispose1 = self.session.post(f"{BASE_URL}/api/schedule-a/{asset_id}/dispose", json={
            "disposition_date": "2024-01-01",
            "disposition_reason": "transfer"
        })
        assert dispose1.status_code == 200
        
        # Try to dispose again - should fail
        dispose2 = self.session.post(f"{BASE_URL}/api/schedule-a/{asset_id}/dispose", json={
            "disposition_date": "2024-02-01",
            "disposition_reason": "sale"
        })
        assert dispose2.status_code == 400, f"Expected 400, got {dispose2.status_code}"
        error = dispose2.json()
        assert "already disposed" in error["detail"].lower()
        print("SUCCESS: Already disposed asset cannot be disposed again")

    def test_04_dispose_nonexistent_asset_returns_404(self):
        """Test that disposing a non-existent asset returns 404"""
        dispose_response = self.session.post(f"{BASE_URL}/api/schedule-a/nonexistent_asset_12345/dispose", json={
            "disposition_date": "2024-01-01",
            "disposition_reason": "sale"
        })
        assert dispose_response.status_code == 404
        print("SUCCESS: Non-existent asset returns 404")

    def test_05_dispose_all_reason_types(self):
        """Test dispose endpoint with all valid reason types"""
        reason_types = ["sale", "transfer", "donation", "destruction"]
        
        for reason in reason_types:
            # Create asset
            create_response = self.session.post(f"{BASE_URL}/api/schedule-a", json={
                "trust_id": self.trust_id,
                "category": "personal_property",
                "description": f"TEST DISPOSE EP - {reason} test",
                "identifier": f"TEST-REASON-{reason.upper()}",
                "approximate_value": 500,
                "date_conveyed": "2023-01-01"
            })
            asset = create_response.json()
            asset_id = asset["item_id"]
            self.test_assets.append(asset_id)
            
            # Dispose
            dispose_response = self.session.post(f"{BASE_URL}/api/schedule-a/{asset_id}/dispose", json={
                "disposition_date": "2024-03-01",
                "disposition_reason": reason
            })
            assert dispose_response.status_code == 200, f"Failed for reason '{reason}': {dispose_response.text}"
            
            # Verify
            get_response = self.session.get(f"{BASE_URL}/api/schedule-a/{asset_id}")
            asset_data = get_response.json()
            assert reason in asset_data["disposition_notes"].lower()
            print(f"SUCCESS: Reason type '{reason}' works correctly")

    def test_06_disposed_asset_hidden_in_active_filter(self):
        """Test that disposed asset is hidden from active view"""
        # Create and dispose asset
        create_response = self.session.post(f"{BASE_URL}/api/schedule-a", json={
            "trust_id": self.trust_id,
            "category": "digital_assets",
            "description": "TEST DISPOSE EP - Hidden from active test",
            "identifier": "TEST-HIDDEN-001",
            "approximate_value": 100,
            "date_conveyed": "2023-01-01"
        })
        asset = create_response.json()
        asset_id = asset["item_id"]
        self.test_assets.append(asset_id)
        
        # Dispose
        self.session.post(f"{BASE_URL}/api/schedule-a/{asset_id}/dispose", json={
            "disposition_date": "2024-01-01",
            "disposition_reason": "transfer"
        })
        
        # Get active assets - should not contain our disposed asset
        active_response = self.session.get(f"{BASE_URL}/api/schedule-a?trust_id={self.trust_id}&status=active")
        active_assets = active_response.json()
        active_ids = [a["item_id"] for a in active_assets]
        assert asset_id not in active_ids, "Disposed asset should not appear in active view"
        
        # Get all assets - should contain our disposed asset
        all_response = self.session.get(f"{BASE_URL}/api/schedule-a?trust_id={self.trust_id}&status=all")
        all_assets = all_response.json()
        all_ids = [a["item_id"] for a in all_assets]
        assert asset_id in all_ids, "Disposed asset should appear in all view"
        print("SUCCESS: Disposed asset hidden from active but visible in all")

    def test_07_dispose_endpoint_requires_auth(self):
        """Test that dispose endpoint requires authentication"""
        # Create a test asset first with auth
        create_response = self.session.post(f"{BASE_URL}/api/schedule-a", json={
            "trust_id": self.trust_id,
            "category": "other_property",
            "description": "TEST DISPOSE EP - Auth test",
            "identifier": "TEST-AUTH-001",
            "approximate_value": 100,
            "date_conveyed": "2023-01-01"
        })
        asset = create_response.json()
        asset_id = asset["item_id"]
        self.test_assets.append(asset_id)
        
        # Create unauthenticated session
        no_auth_session = requests.Session()
        no_auth_session.headers.update({"Content-Type": "application/json"})
        
        # Try to dispose without auth
        dispose_response = no_auth_session.post(f"{BASE_URL}/api/schedule-a/{asset_id}/dispose", json={
            "disposition_date": "2024-01-01",
            "disposition_reason": "sale"
        })
        assert dispose_response.status_code in [401, 403], f"Expected 401/403, got {dispose_response.status_code}"
        print("SUCCESS: Dispose endpoint requires authentication")


class TestScheduleASummaryWithDisposed:
    """Tests for Schedule A summary endpoint with disposed assets"""
    
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

    def test_summary_returns_correct_totals(self):
        """Test that summary endpoint returns correct totals"""
        response = self.session.get(f"{BASE_URL}/api/schedule-a/summary/{self.trust_id}")
        assert response.status_code == 200
        summary = response.json()
        
        assert "total_items" in summary
        assert "total_value" in summary
        assert "categories" in summary
        assert "trust_id" in summary
        assert summary["trust_id"] == self.trust_id
        print(f"SUCCESS: Summary shows {summary['total_items']} items with ${summary['total_value']:,.2f} total value")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
