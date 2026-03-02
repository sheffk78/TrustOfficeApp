"""
Test Demo Data Management and Forever Free Account Features

Tests:
1. GET /api/demo/status - returns data counts for user
2. POST /api/demo/seed - seeds comprehensive demo data
3. DELETE /api/demo/data - deletes all user data
4. Forever free account has plan_type=forever_free and full premium access
5. Demo data includes disposed assets and disposition minutes
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestDemoEndpoints:
    """Test demo data management endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login as demo user"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as demo user
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@trustoffice.com",
            "password": "demopassword"
        })
        
        if response.status_code != 200:
            pytest.skip("Demo user login failed")
        
        data = response.json()
        self.token = data.get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        self.user_id = data.get("user", {}).get("user_id")
    
    def test_demo_status_endpoint(self):
        """GET /api/demo/status returns data counts"""
        response = self.session.get(f"{BASE_URL}/api/demo/status")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Validate response structure
        assert "has_data" in data, "Response should contain has_data field"
        assert "total_records" in data, "Response should contain total_records field"
        assert "counts" in data, "Response should contain counts field"
        assert "can_seed" in data, "Response should contain can_seed field"
        assert "can_delete" in data, "Response should contain can_delete field"
        
        # Validate counts structure
        counts = data["counts"]
        expected_count_fields = ["trusts", "entities", "schedule_a_items", "minutes_records", 
                                  "distribution_records", "benevolence_records", "governance_tasks",
                                  "compensation_plans", "compensation_payments", "trust_unit_certificates"]
        for field in expected_count_fields:
            assert field in counts, f"Counts should contain {field}"
            assert isinstance(counts[field], int), f"{field} should be an integer"
        
        print(f"Demo status: has_data={data['has_data']}, total_records={data['total_records']}")
    
    def test_demo_status_requires_auth(self):
        """GET /api/demo/status requires authentication"""
        session_no_auth = requests.Session()
        response = session_no_auth.get(f"{BASE_URL}/api/demo/status")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    
    def test_demo_seed_endpoint(self):
        """POST /api/demo/seed returns appropriate response"""
        response = self.session.post(f"{BASE_URL}/api/demo/seed")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Response should indicate whether seeding happened or user already has data
        assert "seeded" in data, "Response should contain seeded field"
        assert "message" in data, "Response should contain message field"
        
        if data["seeded"]:
            # If seeding occurred, should include trust IDs and features
            assert "trust_ids" in data, "Seeded response should contain trust_ids"
            assert "features_demonstrated" in data, "Seeded response should contain features_demonstrated"
            assert len(data["trust_ids"]) == 2, "Should create 2 demo trusts"
            
            # Verify features list includes disposed assets
            features = data.get("features_demonstrated", [])
            assert any("disposed" in f.lower() for f in features), "Should mention disposed assets in features"
            assert any("disposition minutes" in f.lower() for f in features), "Should mention disposition minutes"
        else:
            # If not seeded, user already has data
            assert "already has" in data["message"].lower(), "Message should indicate user has data"
        
        print(f"Demo seed response: seeded={data['seeded']}, message={data['message']}")
    
    def test_demo_seed_requires_auth(self):
        """POST /api/demo/seed requires authentication"""
        session_no_auth = requests.Session()
        response = session_no_auth.post(f"{BASE_URL}/api/demo/seed")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"


class TestDeleteDemoData:
    """Test DELETE /api/demo/data endpoint - run separately to avoid affecting other tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Create a test user specifically for delete testing"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Use a test-specific email to avoid affecting demo user
        self.test_email = "test_delete_demo@trustoffice.com"
        self.test_password = "TestPassword123!"
        
        # Try to register test user
        register_response = self.session.post(f"{BASE_URL}/api/auth/register", json={
            "email": self.test_email,
            "password": self.test_password,
            "name": "Test Delete User"
        })
        
        # Login (whether registration succeeded or user already exists)
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": self.test_email,
            "password": self.test_password
        })
        
        if login_response.status_code != 200:
            pytest.skip(f"Test user login failed: {login_response.text}")
        
        data = login_response.json()
        self.token = data.get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_delete_data_endpoint_exists(self):
        """DELETE /api/demo/data endpoint returns valid response"""
        # First check status
        status_response = self.session.get(f"{BASE_URL}/api/demo/status")
        assert status_response.status_code == 200
        
        # If no data, seed first
        status_data = status_response.json()
        if not status_data["has_data"]:
            seed_response = self.session.post(f"{BASE_URL}/api/demo/seed")
            assert seed_response.status_code == 200
        
        # Now delete
        delete_response = self.session.delete(f"{BASE_URL}/api/demo/data")
        assert delete_response.status_code == 200, f"Expected 200, got {delete_response.status_code}: {delete_response.text}"
        
        data = delete_response.json()
        
        # Validate response structure
        assert "message" in data, "Response should contain message field"
        assert "deleted_counts" in data, "Response should contain deleted_counts field"
        assert "notes" in data, "Response should contain notes field"
        
        # Verify data was deleted
        status_after = self.session.get(f"{BASE_URL}/api/demo/status")
        assert status_after.status_code == 200
        after_data = status_after.json()
        assert after_data["total_records"] == 0 or not after_data["has_data"], "All data should be deleted"
        
        print(f"Delete response: {data['message']}")
    
    def test_delete_data_requires_auth(self):
        """DELETE /api/demo/data requires authentication"""
        session_no_auth = requests.Session()
        response = session_no_auth.delete(f"{BASE_URL}/api/demo/data")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"


class TestForeverFreeAccount:
    """Test forever free account (admin@wingpointtrusts.com) has full access"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login as forever free user"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as forever free user
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@wingpointtrusts.com",
            "password": "Admin123!"
        })
        
        if response.status_code != 200:
            pytest.skip(f"Forever free user login failed: {response.text}")
        
        data = response.json()
        self.token = data.get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        self.user_id = data.get("user", {}).get("user_id")
    
    def test_forever_free_subscription_status(self):
        """Forever free account has plan_type=forever_free and active status"""
        response = self.session.get(f"{BASE_URL}/api/subscription")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify forever free plan type
        assert data.get("plan_type") == "forever_free", f"Expected plan_type=forever_free, got {data.get('plan_type')}"
        assert data.get("status") == "active", f"Expected status=active, got {data.get('status')}"
        assert data.get("is_active") == True, "is_active should be True"
        assert data.get("is_read_only") == False, "is_read_only should be False"
        
        print(f"Forever free account: plan_type={data.get('plan_type')}, status={data.get('status')}")
    
    def test_forever_free_has_all_features(self):
        """Forever free account has access to all premium features"""
        response = self.session.get(f"{BASE_URL}/api/subscription/features")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        features = data.get("features", {})
        
        # Verify all premium features are enabled
        premium_features = [
            "pdf_no_watermark",
            "csv_export",
            "multiple_trusts",
            "benevolence_mode",
            "beneficiary_dashboard",
            "trust_units",
            "governance_history",
            "advanced_templates"
        ]
        
        for feature in premium_features:
            assert features.get(feature) == True, f"Forever free should have {feature}=True, got {features.get(feature)}"
        
        print(f"Forever free features: all {len(premium_features)} premium features enabled")
    
    def test_forever_free_can_access_beneficiary_dashboard(self):
        """Forever free account can access beneficiary dashboard (premium feature)"""
        # First ensure user has trusts (seed if needed)
        status_response = self.session.get(f"{BASE_URL}/api/demo/status")
        if status_response.status_code == 200:
            status_data = status_response.json()
            if not status_data["has_data"]:
                self.session.post(f"{BASE_URL}/api/demo/seed")
        
        # Get trusts
        trusts_response = self.session.get(f"{BASE_URL}/api/trusts")
        if trusts_response.status_code != 200:
            pytest.skip("Could not get trusts")
        
        trusts = trusts_response.json()
        if not trusts:
            pytest.skip("No trusts available for testing")
        
        trust_id = trusts[0].get("trust_id")
        
        # Try accessing beneficiary dashboard endpoint
        response = self.session.get(f"{BASE_URL}/api/trusts/{trust_id}/beneficiary-summary")
        
        # Should not return 402 (premium feature error)
        assert response.status_code != 402, f"Forever free should access premium features, got 402"
        # Should return 200 or 404 (if no data), but not 402
        assert response.status_code in [200, 404], f"Expected 200 or 404, got {response.status_code}"
        
        print(f"Beneficiary dashboard access: status_code={response.status_code}")
    
    def test_forever_free_write_access(self):
        """Forever free account has write access (not read-only)"""
        # Try creating a trust (write operation)
        response = self.session.post(f"{BASE_URL}/api/trusts", json={
            "name": "TEST_ForeverFree Trust",
            "trust_type": "family",
            "jurisdiction": "Delaware"
        })
        
        # Should not return 403 (read-only error)
        assert response.status_code != 403, f"Forever free should have write access, got 403"
        
        if response.status_code == 201:
            # Clean up - delete the test trust
            trust_id = response.json().get("trust_id")
            if trust_id:
                self.session.delete(f"{BASE_URL}/api/trusts/{trust_id}")
        
        print(f"Write access test: status_code={response.status_code}")


class TestDemoDataContent:
    """Test that demo data includes disposed assets and disposition minutes"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login and ensure demo data is seeded"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Use forever free account to test demo data content
        response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@wingpointtrusts.com",
            "password": "Admin123!"
        })
        
        if response.status_code != 200:
            pytest.skip(f"Login failed: {response.text}")
        
        data = response.json()
        self.token = data.get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        # Check if data exists, seed if not
        status_response = self.session.get(f"{BASE_URL}/api/demo/status")
        if status_response.status_code == 200:
            status_data = status_response.json()
            if not status_data["has_data"]:
                seed_response = self.session.post(f"{BASE_URL}/api/demo/seed")
                if seed_response.status_code != 200:
                    pytest.skip("Could not seed demo data")
    
    def test_demo_data_includes_disposed_asset(self):
        """Demo data includes at least one disposed Schedule A asset"""
        # Get trusts
        trusts_response = self.session.get(f"{BASE_URL}/api/trusts")
        if trusts_response.status_code != 200:
            pytest.skip("Could not get trusts")
        
        trusts = trusts_response.json()
        if not trusts:
            pytest.skip("No trusts available")
        
        # Check Schedule A items for each trust
        disposed_found = False
        disposed_asset = None
        
        for trust in trusts:
            trust_id = trust.get("trust_id")
            
            # Get all Schedule A items (including disposed)
            schedule_response = self.session.get(f"{BASE_URL}/api/schedule-a?trust_id={trust_id}&status=all")
            if schedule_response.status_code == 200:
                items = schedule_response.json()
                for item in items:
                    if item.get("status") == "disposed":
                        disposed_found = True
                        disposed_asset = item
                        break
            if disposed_found:
                break
        
        assert disposed_found, "Demo data should include at least one disposed asset"
        
        # Verify disposed asset has proper fields
        assert disposed_asset.get("disposition_date") is not None, "Disposed asset should have disposition_date"
        assert disposed_asset.get("disposition_notes") is not None, "Disposed asset should have disposition_notes"
        
        print(f"Found disposed asset: {disposed_asset.get('description', 'Unknown')}")
    
    def test_demo_data_includes_disposition_minutes(self):
        """Demo data includes disposition minutes"""
        # Get trusts
        trusts_response = self.session.get(f"{BASE_URL}/api/trusts")
        if trusts_response.status_code != 200:
            pytest.skip("Could not get trusts")
        
        trusts = trusts_response.json()
        if not trusts:
            pytest.skip("No trusts available")
        
        # Check minutes for each trust
        disposition_minutes_found = False
        
        for trust in trusts:
            trust_id = trust.get("trust_id")
            
            minutes_response = self.session.get(f"{BASE_URL}/api/minutes?trust_id={trust_id}")
            if minutes_response.status_code == 200:
                minutes = minutes_response.json()
                for record in minutes:
                    template = record.get("generated_from_template", "")
                    decisions = record.get("decisions_text", "")
                    
                    if template == "disposition_of_asset" or "disposition" in decisions.lower() or "sale" in decisions.lower():
                        disposition_minutes_found = True
                        print(f"Found disposition minutes: {record.get('minutes_id')}, template={template}")
                        break
            if disposition_minutes_found:
                break
        
        assert disposition_minutes_found, "Demo data should include disposition minutes"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
