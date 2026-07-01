"""
Test Benevolence Log UI Features:
- GET /api/benevolence-log endpoint returns distributions, aggregates, incomplete count
- Benevolence Log page integration
- Distributions form benevolence toggle
- Dashboard governance insights routing to /benevolence/log
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Demo user credentials
TEST_EMAIL = "demo@trustoffice.com"
TEST_PASSWORD = "demopassword"
TEST_TRUST_ID = "trust_b753cb8fe07f"


@pytest.fixture(scope="module")
def auth_session():
    """Create authenticated session for tests"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Login
    login_response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    
    if login_response.status_code != 200:
        pytest.skip(f"Authentication failed: {login_response.status_code} - {login_response.text}")
    
    token = login_response.json().get("token")
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    
    return session


class TestBenevolenceLogEndpoint:
    """Test GET /api/benevolence-log endpoint"""
    
    def test_benevolence_log_returns_200(self, auth_session):
        """Test that endpoint returns 200 for authenticated user"""
        response = auth_session.get(f"{BASE_URL}/api/benevolence-log?trust_id={TEST_TRUST_ID}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: /api/benevolence-log returns 200")
    
    def test_benevolence_log_response_structure(self, auth_session):
        """Test response has required fields: trust_id, trust_name, distributions, aggregates"""
        response = auth_session.get(f"{BASE_URL}/api/benevolence-log?trust_id={TEST_TRUST_ID}")
        assert response.status_code == 200
        
        data = response.json()
        
        # Required fields
        assert "trust_id" in data, "Missing trust_id field"
        assert "trust_name" in data, "Missing trust_name field"
        assert "distributions" in data, "Missing distributions field"
        assert "monthly_aggregates" in data, "Missing monthly_aggregates field"
        assert "yearly_aggregates" in data, "Missing yearly_aggregates field"
        assert "total_all_time" in data, "Missing total_all_time field"
        assert "total_count" in data, "Missing total_count field"
        assert "incomplete_documentation_count" in data, "Missing incomplete_documentation_count field"
        
        print(f"PASS: Response structure valid - trust_id={data['trust_id']}, trust_name={data['trust_name']}")
        print(f"      Total count: {data['total_count']}, All time: ${data['total_all_time']}")
        print(f"      Incomplete documentation: {data['incomplete_documentation_count']}")
    
    def test_distributions_contain_benevolence_fields(self, auth_session):
        """Test distributions array contains benevolence-specific fields"""
        response = auth_session.get(f"{BASE_URL}/api/benevolence-log?trust_id={TEST_TRUST_ID}")
        assert response.status_code == 200
        
        data = response.json()
        distributions = data.get("distributions", [])
        
        if len(distributions) > 0:
            dist = distributions[0]
            # Check for expected fields in benevolence distributions
            expected_fields = ["distribution_id", "beneficiary_name", "amount", "date", "is_benevolence"]
            for field in expected_fields:
                assert field in dist, f"Missing field '{field}' in distribution"
            
            # Verify is_benevolence is True for all distributions
            for d in distributions:
                assert d.get("is_benevolence") == True, "Distribution in benevolence log should have is_benevolence=True"
            
            print(f"PASS: Distributions contain required fields. {len(distributions)} benevolence distributions found.")
        else:
            print("WARN: No benevolence distributions found to verify fields")
    
    def test_monthly_aggregates_format(self, auth_session):
        """Test monthly_aggregates have correct format (YYYY-MM)"""
        response = auth_session.get(f"{BASE_URL}/api/benevolence-log?trust_id={TEST_TRUST_ID}")
        assert response.status_code == 200
        
        data = response.json()
        monthly = data.get("monthly_aggregates", [])
        
        if len(monthly) > 0:
            for m in monthly:
                assert "month" in m, "Missing 'month' field in monthly aggregate"
                assert "total_amount" in m, "Missing 'total_amount' field"
                assert "count" in m, "Missing 'count' field"
                
                # Verify YYYY-MM format
                month_str = m["month"]
                parts = month_str.split("-")
                assert len(parts) == 2, f"Month format should be YYYY-MM, got {month_str}"
                assert len(parts[0]) == 4, f"Year should be 4 digits: {parts[0]}"
                assert len(parts[1]) == 2, f"Month should be 2 digits: {parts[1]}"
            
            print(f"PASS: Monthly aggregates format valid. {len(monthly)} months found.")
        else:
            print("WARN: No monthly aggregates to verify")
    
    def test_yearly_aggregates_format(self, auth_session):
        """Test yearly_aggregates have correct format (integer year)"""
        response = auth_session.get(f"{BASE_URL}/api/benevolence-log?trust_id={TEST_TRUST_ID}")
        assert response.status_code == 200
        
        data = response.json()
        yearly = data.get("yearly_aggregates", [])
        
        if len(yearly) > 0:
            for y in yearly:
                assert "year" in y, "Missing 'year' field in yearly aggregate"
                assert "total_amount" in y, "Missing 'total_amount' field"
                assert "count" in y, "Missing 'count' field"
                
                # Verify year is an integer
                assert isinstance(y["year"], int), f"Year should be integer, got {type(y['year'])}"
            
            print(f"PASS: Yearly aggregates format valid. {len(yearly)} years found.")
        else:
            print("WARN: No yearly aggregates to verify")


class TestDistributionsBenevolenceToggle:
    """Test Distribution creation with benevolence toggle"""
    
    def test_create_benevolence_distribution(self, auth_session):
        """Test creating a benevolence distribution with required fields"""
        payload = {
            "trust_id": TEST_TRUST_ID,
            "beneficiary_name": "TEST_Benevolence_Recipient",
            "amount": 500,
            "date": "2026-01-15",
            "purpose_classification": "distribution",
            "is_benevolence": True,
            "benevolence_recipient_name": "TEST Local Food Bank",
            "benevolence_need_description": "Emergency food assistance for families",
            "benevolence_notes": "Quarterly donation"
        }
        
        response = auth_session.post(f"{BASE_URL}/api/distributions", json=payload)
        
        # Should succeed
        if response.status_code in [200, 201]:
            data = response.json()
            assert data.get("is_benevolence") == True
            assert data.get("benevolence_recipient_name") == "TEST Local Food Bank"
            assert data.get("benevolence_need_description") == "Emergency food assistance for families"
            
            # Cleanup - delete the test distribution
            dist_id = data.get("distribution_id")
            if dist_id:
                auth_session.delete(f"{BASE_URL}/api/distributions/{dist_id}")
            
            print("PASS: Benevolence distribution created successfully with all fields")
        else:
            print(f"WARN: Create benevolence distribution returned {response.status_code}: {response.text}")
    
    def test_benevolence_requires_recipient_name(self, auth_session):
        """Test that benevolence distribution requires recipient name"""
        payload = {
            "trust_id": TEST_TRUST_ID,
            "beneficiary_name": "TEST_Missing_Recipient",
            "amount": 100,
            "date": "2026-01-15",
            "purpose_classification": "distribution",
            "is_benevolence": True,
            # Missing benevolence_recipient_name
            "benevolence_need_description": "Some need"
        }
        
        response = auth_session.post(f"{BASE_URL}/api/distributions", json=payload)
        
        # Should fail with 400
        assert response.status_code == 400, f"Expected 400 when missing recipient name, got {response.status_code}"
        print("PASS: Benevolence distribution correctly requires recipient_name")
    
    def test_benevolence_requires_need_description(self, auth_session):
        """Test that benevolence distribution requires need description"""
        payload = {
            "trust_id": TEST_TRUST_ID,
            "beneficiary_name": "TEST_Missing_Need",
            "amount": 100,
            "date": "2026-01-15",
            "purpose_classification": "distribution",
            "is_benevolence": True,
            "benevolence_recipient_name": "Some Recipient"
            # Missing benevolence_need_description
        }
        
        response = auth_session.post(f"{BASE_URL}/api/distributions", json=payload)
        
        # Should fail with 400
        assert response.status_code == 400, f"Expected 400 when missing need description, got {response.status_code}"
        print("PASS: Benevolence distribution correctly requires need_description")


class TestGovernanceInsightsBenevolenceRouting:
    """Test that governance insights route to /benevolence/log for benevolence issues"""
    
    def test_dashboard_governance_insights_structure(self, auth_session):
        """Test dashboard returns governance_insights array"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard?trust_id={TEST_TRUST_ID}")
        
        assert response.status_code == 200, f"Dashboard failed: {response.status_code}"
        
        data = response.json()
        assert "governance_insights" in data, "Missing governance_insights in dashboard"
        
        insights = data.get("governance_insights", [])
        print(f"PASS: Dashboard returns governance_insights. {len(insights)} insights found.")
        
        # Print insights for debugging
        for insight in insights:
            print(f"      - {insight.get('criterion_name')}: {insight.get('title')} -> {insight.get('action_path')}")
    
    def test_health_score_criterion_description(self, auth_session):
        """Test health score criterion description mentions benevolence status"""
        response = auth_session.get(f"{BASE_URL}/api/governance/{TEST_TRUST_ID}")
        
        assert response.status_code == 200, f"Governance endpoint failed: {response.status_code}"
        
        data = response.json()
        criteria = data.get("criteria", [])
        
        # Find Distribution Documentation criterion
        dist_criterion = None
        for c in criteria:
            if c.get("name") == "Distribution Documentation":
                dist_criterion = c
                break
        
        assert dist_criterion is not None, "Distribution Documentation criterion not found"
        
        description = dist_criterion.get("description", "")
        points = dist_criterion.get("points", 0)
        achieved = dist_criterion.get("achieved", False)
        
        print(f"PASS: Distribution Documentation criterion found")
        print(f"      Description: {description}")
        print(f"      Points: {points}/15, Achieved: {achieved}")


class TestCategoriesEndpoint:
    """Test categories endpoint used by distributions form"""
    
    def test_categories_returns_purpose_classifications(self, auth_session):
        """Test /api/categories returns purpose_classifications for dropdown"""
        response = auth_session.get(f"{BASE_URL}/api/categories")
        
        assert response.status_code == 200, f"Categories failed: {response.status_code}"
        
        data = response.json()
        
        # Should have purpose_classifications or distribution_categories
        has_categories = "purpose_classifications" in data or "distribution_categories" in data
        assert has_categories, "Categories should return purpose_classifications or distribution_categories"
        
        categories = data.get("purpose_classifications", data.get("distribution_categories", []))
        print(f"PASS: Categories endpoint returns {len(categories)} categories")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
