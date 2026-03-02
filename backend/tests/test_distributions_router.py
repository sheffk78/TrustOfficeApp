# Test file for distributions router endpoints
# Tests: GET/POST/PATCH/DELETE distributions, benevolence-log, and subscription gating

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


@pytest.fixture(scope="module")
def auth_token():
    """Login and get authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("token")
    pytest.skip(f"Auth failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def session():
    """Create a requests session"""
    return requests.Session()


@pytest.fixture(scope="module")
def auth_session(session, auth_token):
    """Session with auth headers"""
    session.headers.update({
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    })
    return session


class TestDistributionsRead:
    """Test read operations on distributions - require_current_user"""
    
    def test_get_distributions_list(self, auth_session):
        """GET /api/distributions - should return list of distributions"""
        response = auth_session.get(f"{BASE_URL}/api/distributions")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"Found {len(data)} distributions")
    
    def test_get_distributions_with_trust_id_filter(self, auth_session):
        """GET /api/distributions?trust_id=xxx - should filter by trust"""
        response = auth_session.get(f"{BASE_URL}/api/distributions?trust_id={TRUST_ID}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        # All distributions should belong to the specified trust
        for dist in data:
            assert dist.get("trust_id") == TRUST_ID, f"Distribution {dist.get('distribution_id')} has wrong trust_id"
        print(f"Found {len(data)} distributions for trust {TRUST_ID}")
    
    def test_get_distributions_with_search(self, auth_session):
        """GET /api/distributions?search=xxx - should filter by search term"""
        # First get all distributions to find something to search
        response = auth_session.get(f"{BASE_URL}/api/distributions")
        assert response.status_code == 200
        
        data = response.json()
        if len(data) > 0:
            # Search by beneficiary name
            beneficiary = data[0].get("beneficiary_name", "")
            if beneficiary:
                search_term = beneficiary[:5]  # Use first 5 chars
                search_response = auth_session.get(f"{BASE_URL}/api/distributions?search={search_term}")
                assert search_response.status_code == 200
                search_data = search_response.json()
                print(f"Search for '{search_term}' returned {len(search_data)} results")
    
    def test_get_distributions_status_filter_approved(self, auth_session):
        """GET /api/distributions?status=approved - should filter approved"""
        response = auth_session.get(f"{BASE_URL}/api/distributions?status=approved")
        assert response.status_code == 200
        
        data = response.json()
        for dist in data:
            assert dist.get("approved_at") is not None, "Approved distributions should have approved_at"
        print(f"Found {len(data)} approved distributions")
    
    def test_get_distributions_status_filter_pending(self, auth_session):
        """GET /api/distributions?status=pending - should filter pending"""
        response = auth_session.get(f"{BASE_URL}/api/distributions?status=pending")
        assert response.status_code == 200
        
        data = response.json()
        for dist in data:
            assert dist.get("approved_at") is None, "Pending distributions should not have approved_at"
        print(f"Found {len(data)} pending distributions")


class TestBenevolenceLog:
    """Test benevolence log endpoint - require_current_user"""
    
    def test_get_benevolence_log(self, auth_session):
        """GET /api/benevolence-log - should return benevolence aggregates"""
        response = auth_session.get(f"{BASE_URL}/api/benevolence-log")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Validate response structure
        assert "trust_id" in data, "Response should have trust_id"
        assert "trust_name" in data, "Response should have trust_name"
        assert "distributions" in data, "Response should have distributions"
        assert "monthly_aggregates" in data, "Response should have monthly_aggregates"
        assert "yearly_aggregates" in data, "Response should have yearly_aggregates"
        assert "total_all_time" in data, "Response should have total_all_time"
        assert "total_count" in data, "Response should have total_count"
        assert "incomplete_documentation_count" in data, "Response should have incomplete_documentation_count"
        
        print(f"Benevolence log: {data['total_count']} distributions, ${data['total_all_time']} total")
    
    def test_get_benevolence_log_with_trust_id(self, auth_session):
        """GET /api/benevolence-log?trust_id=xxx - should filter by trust"""
        response = auth_session.get(f"{BASE_URL}/api/benevolence-log?trust_id={TRUST_ID}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["trust_id"] == TRUST_ID, f"Expected trust_id {TRUST_ID}, got {data['trust_id']}"


class TestDistributionsWrite:
    """Test write operations - require_write_access (should work with active subscription)"""
    
    def test_create_distribution(self, auth_session):
        """POST /api/distributions - should create new distribution"""
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "trust_id": TRUST_ID,
            "beneficiary_name": f"TEST_Beneficiary_{unique_id}",
            "amount": 1000.00,
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "purpose_classification": "distribution",  # Valid enum: distribution, compensation, expense, other
            "authority_clause_ref": "Section 5.1",
            "notes": f"TEST distribution created by pytest {unique_id}",
            "is_benevolence": False
        }
        
        response = auth_session.post(f"{BASE_URL}/api/distributions", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "distribution_id" in data, "Response should have distribution_id"
        assert data["beneficiary_name"] == payload["beneficiary_name"]
        assert data["amount"] == payload["amount"]
        assert data["trust_id"] == TRUST_ID
        
        # Store for cleanup and later tests
        TestDistributionsWrite.created_distribution_id = data["distribution_id"]
        print(f"Created distribution: {data['distribution_id']}")
        return data["distribution_id"]
    
    def test_create_benevolence_distribution(self, auth_session):
        """POST /api/distributions with is_benevolence=true - requires additional fields"""
        unique_id = uuid.uuid4().hex[:8]
        payload = {
            "trust_id": TRUST_ID,
            "beneficiary_name": f"TEST_Benevolence_{unique_id}",
            "amount": 500.00,
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "purpose_classification": "other",  # Valid enum: distribution, compensation, expense, other
            "authority_clause_ref": "Section 6.2",
            "notes": f"TEST benevolence distribution {unique_id}",
            "is_benevolence": True,
            "benevolence_recipient_name": "John Doe",
            "benevolence_need_description": "Medical expenses assistance"
        }
        
        response = auth_session.post(f"{BASE_URL}/api/distributions", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["is_benevolence"] == True
        assert data["benevolence_recipient_name"] == "John Doe"
        
        TestDistributionsWrite.benevolence_distribution_id = data["distribution_id"]
        print(f"Created benevolence distribution: {data['distribution_id']}")
    
    def test_create_benevolence_missing_recipient_fails(self, auth_session):
        """POST /api/distributions with is_benevolence=true but missing recipient should fail"""
        payload = {
            "trust_id": TRUST_ID,
            "beneficiary_name": "TEST_Should_Fail",
            "amount": 100.00,
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "purpose_classification": "other",  # Valid enum: distribution, compensation, expense, other
            "is_benevolence": True,
            # Missing benevolence_recipient_name and benevolence_need_description
        }
        
        response = auth_session.post(f"{BASE_URL}/api/distributions", json=payload)
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print("Correctly rejected benevolence distribution without required fields")
    
    def test_update_distribution(self, auth_session):
        """PATCH /api/distributions/{id} - should update distribution"""
        dist_id = getattr(TestDistributionsWrite, 'created_distribution_id', None)
        if not dist_id:
            pytest.skip("No distribution created in previous test")
        
        update_payload = {
            "amount": 1500.00,
            "notes": "Updated notes via pytest"
        }
        
        response = auth_session.patch(f"{BASE_URL}/api/distributions/{dist_id}", json=update_payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["amount"] == 1500.00
        assert "Updated notes" in data["notes"]
        print(f"Updated distribution {dist_id}")
    
    def test_approve_distribution(self, auth_session):
        """PATCH /api/distributions/{id}/approve - should approve distribution"""
        dist_id = getattr(TestDistributionsWrite, 'created_distribution_id', None)
        if not dist_id:
            pytest.skip("No distribution created in previous test")
        
        approve_payload = {
            "solvency_confirmed": True,
            "recusal_acknowledged": True
        }
        
        response = auth_session.patch(f"{BASE_URL}/api/distributions/{dist_id}/approve", json=approve_payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["solvency_confirmed"] == True
        assert data["recusal_acknowledged"] == True
        assert data["approved_at"] is not None
        assert data["approved_by"] is not None
        print(f"Approved distribution {dist_id}")
    
    def test_approve_distribution_without_solvency_fails(self, auth_session):
        """PATCH /api/distributions/{id}/approve without solvency should fail"""
        dist_id = getattr(TestDistributionsWrite, 'benevolence_distribution_id', None)
        if not dist_id:
            pytest.skip("No benevolence distribution created")
        
        approve_payload = {
            "solvency_confirmed": False,  # Should fail
            "recusal_acknowledged": True
        }
        
        response = auth_session.patch(f"{BASE_URL}/api/distributions/{dist_id}/approve", json=approve_payload)
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        assert "Solvency" in response.json().get("detail", "")
        print("Correctly rejected approval without solvency confirmation")
    
    def test_update_nonexistent_distribution_fails(self, auth_session):
        """PATCH /api/distributions/{nonexistent_id} - should return 404"""
        response = auth_session.patch(
            f"{BASE_URL}/api/distributions/dist_nonexistent123",
            json={"amount": 999}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
    
    def test_delete_distribution(self, auth_session):
        """DELETE /api/distributions/{id} - should delete distribution"""
        # Create a new distribution to delete
        unique_id = uuid.uuid4().hex[:8]
        create_payload = {
            "trust_id": TRUST_ID,
            "beneficiary_name": f"TEST_ToDelete_{unique_id}",
            "amount": 100.00,
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "purpose_classification": "distribution",  # Valid enum: distribution, compensation, expense, other
            "is_benevolence": False
        }
        
        create_response = auth_session.post(f"{BASE_URL}/api/distributions", json=create_payload)
        assert create_response.status_code == 200
        dist_id = create_response.json()["distribution_id"]
        
        # Now delete it
        delete_response = auth_session.delete(f"{BASE_URL}/api/distributions/{dist_id}")
        assert delete_response.status_code == 200, f"Expected 200, got {delete_response.status_code}: {delete_response.text}"
        
        # Verify it's deleted by trying to get distributions and checking it's not there
        get_response = auth_session.get(f"{BASE_URL}/api/distributions")
        assert get_response.status_code == 200
        distributions = get_response.json()
        dist_ids = [d["distribution_id"] for d in distributions]
        assert dist_id not in dist_ids, "Distribution should be deleted"
        print(f"Deleted distribution {dist_id}")
    
    def test_delete_nonexistent_distribution_fails(self, auth_session):
        """DELETE /api/distributions/{nonexistent} - should return 404"""
        response = auth_session.delete(f"{BASE_URL}/api/distributions/dist_nonexistent456")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"


class TestDistributionsPurposeFilter:
    """Test purpose classification filter"""
    
    def test_get_distributions_by_purpose(self, auth_session):
        """GET /api/distributions?purpose=xxx - should filter by purpose"""
        # First get all to see what purposes exist
        response = auth_session.get(f"{BASE_URL}/api/distributions")
        assert response.status_code == 200
        
        data = response.json()
        if len(data) > 0:
            # Get a purpose that exists
            purpose = data[0].get("purpose_classification")
            if purpose:
                purpose_response = auth_session.get(f"{BASE_URL}/api/distributions?purpose={purpose}")
                assert purpose_response.status_code == 200
                purpose_data = purpose_response.json()
                for dist in purpose_data:
                    assert dist.get("purpose_classification") == purpose
                print(f"Filtered by purpose '{purpose}': {len(purpose_data)} results")


class TestCleanup:
    """Clean up test data"""
    
    def test_cleanup_test_distributions(self, auth_session):
        """Delete TEST_ prefixed distributions created during tests"""
        response = auth_session.get(f"{BASE_URL}/api/distributions")
        assert response.status_code == 200
        
        distributions = response.json()
        deleted_count = 0
        for dist in distributions:
            if dist.get("beneficiary_name", "").startswith("TEST_"):
                del_response = auth_session.delete(f"{BASE_URL}/api/distributions/{dist['distribution_id']}")
                if del_response.status_code == 200:
                    deleted_count += 1
        
        print(f"Cleaned up {deleted_count} test distributions")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
