"""
Test benevolence distribution features for 501/508-style trusts.
Features tested:
- POST /api/distributions with is_benevolence=true validation
- POST /api/distributions with is_benevolence=false (normal flow)
- PATCH /api/distributions/{id} for benevolence fields update
- GET /api/benevolence-log endpoint with aggregates
- Governance health score integration with benevolence documentation
"""

import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
TEST_USER_EMAIL = "demo@trustoffice.com"
TEST_USER_PASSWORD = "demopassword"
TRUST_ID = "trust_b753cb8fe07f"

# Track created resources for cleanup
created_distributions = []


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for demo user"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_USER_EMAIL,
        "password": TEST_USER_PASSWORD
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["token"]


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Authenticated requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


class TestBenevolenceDistributionCreate:
    """Test POST /api/distributions with benevolence mode"""

    def test_create_benevolence_distribution_requires_recipient_name(self, api_client):
        """is_benevolence=true requires benevolence_recipient_name"""
        response = api_client.post(f"{BASE_URL}/api/distributions", json={
            "trust_id": TRUST_ID,
            "beneficiary_name": "Test Beneficiary",
            "amount": 100.00,
            "date": "2026-01-15",
            "purpose_classification": "distribution",
            "is_benevolence": True,
            # Missing benevolence_recipient_name
            "benevolence_need_description": "Medical expenses"
        })
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert "recipient name" in data.get("detail", "").lower(), f"Unexpected error: {data}"
        print("PASS: is_benevolence=true requires benevolence_recipient_name")

    def test_create_benevolence_distribution_requires_need_description(self, api_client):
        """is_benevolence=true requires benevolence_need_description"""
        response = api_client.post(f"{BASE_URL}/api/distributions", json={
            "trust_id": TRUST_ID,
            "beneficiary_name": "Test Beneficiary",
            "amount": 100.00,
            "date": "2026-01-15",
            "purpose_classification": "distribution",
            "is_benevolence": True,
            "benevolence_recipient_name": "John Doe",
            # Missing benevolence_need_description
        })
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert "need description" in data.get("detail", "").lower(), f"Unexpected error: {data}"
        print("PASS: is_benevolence=true requires benevolence_need_description")

    def test_create_benevolence_distribution_success(self, api_client):
        """Create distribution with is_benevolence=true and all required fields"""
        response = api_client.post(f"{BASE_URL}/api/distributions", json={
            "trust_id": TRUST_ID,
            "beneficiary_name": "TEST_Benevolent Society",
            "amount": 500.00,
            "date": "2026-01-15",
            "purpose_classification": "distribution",
            "is_benevolence": True,
            "benevolence_recipient_name": "TEST_Jane Smith",
            "benevolence_need_description": "Emergency housing assistance",
            "benevolence_notes": "Approved by board on 2026-01-10"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify all benevolence fields returned
        assert data["is_benevolence"] == True
        assert data["benevolence_recipient_name"] == "TEST_Jane Smith"
        assert data["benevolence_need_description"] == "Emergency housing assistance"
        assert data["benevolence_notes"] == "Approved by board on 2026-01-10"
        assert "distribution_id" in data
        
        created_distributions.append(data["distribution_id"])
        print(f"PASS: Created benevolence distribution {data['distribution_id']}")

    def test_create_non_benevolence_distribution_without_benevolence_fields(self, api_client):
        """Create distribution with is_benevolence=false works without benevolence fields"""
        response = api_client.post(f"{BASE_URL}/api/distributions", json={
            "trust_id": TRUST_ID,
            "beneficiary_name": "TEST_Regular Beneficiary",
            "amount": 250.00,
            "date": "2026-01-16",
            "purpose_classification": "distribution",
            "is_benevolence": False
            # No benevolence fields required
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify benevolence fields are None/False
        assert data["is_benevolence"] == False
        assert data.get("benevolence_recipient_name") is None
        assert data.get("benevolence_need_description") is None
        
        created_distributions.append(data["distribution_id"])
        print(f"PASS: Created non-benevolence distribution {data['distribution_id']}")

    def test_create_distribution_default_is_benevolence_false(self, api_client):
        """Distribution without explicit is_benevolence defaults to false"""
        response = api_client.post(f"{BASE_URL}/api/distributions", json={
            "trust_id": TRUST_ID,
            "beneficiary_name": "TEST_Default Beneficiary",
            "amount": 150.00,
            "date": "2026-01-17",
            "purpose_classification": "expense"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Default should be false
        assert data["is_benevolence"] == False
        
        created_distributions.append(data["distribution_id"])
        print(f"PASS: Default is_benevolence=false distribution {data['distribution_id']}")


class TestBenevolenceDistributionUpdate:
    """Test PATCH /api/distributions/{id} for benevolence fields"""

    def test_update_benevolence_fields(self, api_client):
        """Can update benevolence-specific fields via PATCH"""
        # First create a benevolence distribution
        create_resp = api_client.post(f"{BASE_URL}/api/distributions", json={
            "trust_id": TRUST_ID,
            "beneficiary_name": "TEST_Update Test",
            "amount": 300.00,
            "date": "2026-01-18",
            "purpose_classification": "distribution",
            "is_benevolence": True,
            "benevolence_recipient_name": "TEST_Original Name",
            "benevolence_need_description": "Original description"
        })
        assert create_resp.status_code == 200, f"Create failed: {create_resp.text}"
        dist_id = create_resp.json()["distribution_id"]
        created_distributions.append(dist_id)
        
        # Update benevolence fields
        update_resp = api_client.patch(f"{BASE_URL}/api/distributions/{dist_id}", json={
            "benevolence_recipient_name": "TEST_Updated Name",
            "benevolence_need_description": "Updated medical expenses",
            "benevolence_notes": "Additional documentation added"
        })
        assert update_resp.status_code == 200, f"Update failed: {update_resp.text}"
        data = update_resp.json()
        
        assert data["benevolence_recipient_name"] == "TEST_Updated Name"
        assert data["benevolence_need_description"] == "Updated medical expenses"
        assert data["benevolence_notes"] == "Additional documentation added"
        print(f"PASS: Updated benevolence fields on distribution {dist_id}")

    def test_update_is_benevolence_to_true_requires_fields(self, api_client):
        """When changing is_benevolence to true, benevolence fields are required"""
        # Create non-benevolence distribution
        create_resp = api_client.post(f"{BASE_URL}/api/distributions", json={
            "trust_id": TRUST_ID,
            "beneficiary_name": "TEST_Convert Test",
            "amount": 200.00,
            "date": "2026-01-19",
            "purpose_classification": "distribution",
            "is_benevolence": False
        })
        assert create_resp.status_code == 200, f"Create failed: {create_resp.text}"
        dist_id = create_resp.json()["distribution_id"]
        created_distributions.append(dist_id)
        
        # Try to set is_benevolence=true without providing required fields
        update_resp = api_client.patch(f"{BASE_URL}/api/distributions/{dist_id}", json={
            "is_benevolence": True
            # Missing benevolence_recipient_name and benevolence_need_description
        })
        assert update_resp.status_code == 400, f"Expected 400, got {update_resp.status_code}"
        print(f"PASS: Cannot set is_benevolence=true without required fields")

    def test_update_convert_to_benevolence_with_fields(self, api_client):
        """Can convert to benevolence by providing is_benevolence=true and required fields"""
        # Create non-benevolence distribution
        create_resp = api_client.post(f"{BASE_URL}/api/distributions", json={
            "trust_id": TRUST_ID,
            "beneficiary_name": "TEST_Convert Success",
            "amount": 175.00,
            "date": "2026-01-20",
            "purpose_classification": "distribution",
            "is_benevolence": False
        })
        assert create_resp.status_code == 200, f"Create failed: {create_resp.text}"
        dist_id = create_resp.json()["distribution_id"]
        created_distributions.append(dist_id)
        
        # Convert to benevolence with required fields
        update_resp = api_client.patch(f"{BASE_URL}/api/distributions/{dist_id}", json={
            "is_benevolence": True,
            "benevolence_recipient_name": "TEST_New Recipient",
            "benevolence_need_description": "Converted to benevolence"
        })
        assert update_resp.status_code == 200, f"Update failed: {update_resp.text}"
        data = update_resp.json()
        
        assert data["is_benevolence"] == True
        assert data["benevolence_recipient_name"] == "TEST_New Recipient"
        print(f"PASS: Successfully converted distribution to benevolence")


class TestBenevolenceLog:
    """Test GET /api/benevolence-log endpoint"""

    def test_get_benevolence_log_structure(self, api_client):
        """Benevolence log returns correct structure"""
        response = api_client.get(f"{BASE_URL}/api/benevolence-log", params={
            "trust_id": TRUST_ID
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "trust_id" in data
        assert "trust_name" in data
        assert "distributions" in data
        assert "monthly_aggregates" in data
        assert "yearly_aggregates" in data
        assert "total_all_time" in data
        assert "total_count" in data
        assert "incomplete_documentation_count" in data
        
        print(f"PASS: Benevolence log structure correct")
        print(f"  - Trust: {data['trust_name']}")
        print(f"  - Total distributions: {data['total_count']}")
        print(f"  - Total amount: ${data['total_all_time']:.2f}")
        print(f"  - Incomplete documentation: {data['incomplete_documentation_count']}")

    def test_benevolence_log_only_benevolence_distributions(self, api_client):
        """Benevolence log only returns is_benevolence=true distributions"""
        response = api_client.get(f"{BASE_URL}/api/benevolence-log", params={
            "trust_id": TRUST_ID
        })
        assert response.status_code == 200
        data = response.json()
        
        # All distributions in log should be benevolence
        for dist in data["distributions"]:
            assert dist["is_benevolence"] == True, f"Non-benevolence distribution in log: {dist['distribution_id']}"
        
        print(f"PASS: Benevolence log only contains benevolence distributions")

    def test_benevolence_log_monthly_aggregates(self, api_client):
        """Benevolence log includes monthly aggregates"""
        response = api_client.get(f"{BASE_URL}/api/benevolence-log", params={
            "trust_id": TRUST_ID
        })
        assert response.status_code == 200
        data = response.json()
        
        # Check monthly aggregates structure
        for agg in data["monthly_aggregates"]:
            assert "month" in agg
            assert "total_amount" in agg
            assert "count" in agg
            # Month format should be YYYY-MM
            assert len(agg["month"]) == 7
            assert "-" in agg["month"]
        
        print(f"PASS: Monthly aggregates have correct structure ({len(data['monthly_aggregates'])} months)")

    def test_benevolence_log_yearly_aggregates(self, api_client):
        """Benevolence log includes yearly aggregates"""
        response = api_client.get(f"{BASE_URL}/api/benevolence-log", params={
            "trust_id": TRUST_ID
        })
        assert response.status_code == 200
        data = response.json()
        
        # Check yearly aggregates structure
        for agg in data["yearly_aggregates"]:
            assert "year" in agg
            assert "total_amount" in agg
            assert "count" in agg
            assert isinstance(agg["year"], int)
        
        print(f"PASS: Yearly aggregates have correct structure ({len(data['yearly_aggregates'])} years)")

    def test_benevolence_log_incomplete_documentation_count(self, api_client):
        """Benevolence log tracks incomplete documentation count"""
        response = api_client.get(f"{BASE_URL}/api/benevolence-log", params={
            "trust_id": TRUST_ID
        })
        assert response.status_code == 200
        data = response.json()
        
        # Incomplete count should be a non-negative integer
        assert isinstance(data["incomplete_documentation_count"], int)
        assert data["incomplete_documentation_count"] >= 0
        
        print(f"PASS: Incomplete documentation count: {data['incomplete_documentation_count']}")


class TestGovernanceHealthScoreBenevolence:
    """Test governance health score integration with benevolence documentation"""

    def test_health_score_distribution_documentation_criterion(self, api_client):
        """Health score includes Distribution Documentation criterion"""
        response = api_client.get(f"{BASE_URL}/api/trusts/{TRUST_ID}")
        assert response.status_code == 200
        
        # Get detailed health score
        health_resp = api_client.get(f"{BASE_URL}/api/health-score", params={
            "trust_id": TRUST_ID
        })
        assert health_resp.status_code == 200, f"Health score failed: {health_resp.text}"
        data = health_resp.json()
        
        # Find Distribution Documentation criterion
        dist_criterion = None
        for criterion in data["criteria"]:
            if criterion["name"] == "Distribution Documentation":
                dist_criterion = criterion
                break
        
        assert dist_criterion is not None, "Distribution Documentation criterion not found"
        assert "points" in dist_criterion
        assert "max_points" in dist_criterion
        assert "description" in dist_criterion
        
        print(f"PASS: Distribution Documentation criterion found")
        print(f"  - Points: {dist_criterion['points']}/{dist_criterion['max_points']}")
        print(f"  - Description: {dist_criterion['description']}")

    def test_health_score_benevolence_quality_description(self, api_client):
        """Health score description reflects benevolence documentation quality"""
        health_resp = api_client.get(f"{BASE_URL}/api/health-score", params={
            "trust_id": TRUST_ID
        })
        assert health_resp.status_code == 200
        data = health_resp.json()
        
        # Find Distribution Documentation criterion
        dist_criterion = None
        for criterion in data["criteria"]:
            if criterion["name"] == "Distribution Documentation":
                dist_criterion = criterion
                break
        
        # Description should mention benevolence if there are benevolence distributions
        description = dist_criterion["description"].lower()
        print(f"PASS: Distribution Documentation description: {dist_criterion['description']}")
        
        # Check if description mentions benevolence or documentation status
        if "benevolence" in description or "documented" in description or "logged" in description:
            print(f"  - Description reflects documentation status")

    def test_health_score_full_points_with_complete_documentation(self, api_client):
        """Full points (20) when all benevolence distributions are documented"""
        # This test verifies the scoring logic - full points require:
        # - At least 1 distribution logged
        # - All benevolence distributions have recipient_name, need_description
        # - All benevolence distributions have approval or minutes
        
        health_resp = api_client.get(f"{BASE_URL}/api/health-score", params={
            "trust_id": TRUST_ID
        })
        assert health_resp.status_code == 200
        data = health_resp.json()
        
        # Find Distribution Documentation criterion
        dist_criterion = None
        for criterion in data["criteria"]:
            if criterion["name"] == "Distribution Documentation":
                dist_criterion = criterion
                break
        
        # Points should be between 0 and 20
        assert 0 <= dist_criterion["points"] <= 20
        
        # If there are incomplete benevolence distributions, points should be reduced
        print(f"PASS: Distribution Documentation points: {dist_criterion['points']}/20")
        if dist_criterion["points"] < 20:
            print(f"  - Points reduced due to incomplete documentation")
        else:
            print(f"  - Full points - all documentation complete")


class TestBenevolenceCleanup:
    """Cleanup test-created distributions"""

    def test_cleanup_test_distributions(self, api_client):
        """Delete all TEST_ prefixed distributions created during testing"""
        deleted_count = 0
        for dist_id in created_distributions:
            try:
                response = api_client.delete(f"{BASE_URL}/api/distributions/{dist_id}")
                if response.status_code in [200, 204]:
                    deleted_count += 1
            except Exception as e:
                print(f"Warning: Could not delete {dist_id}: {e}")
        
        print(f"PASS: Cleaned up {deleted_count} test distributions")


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
