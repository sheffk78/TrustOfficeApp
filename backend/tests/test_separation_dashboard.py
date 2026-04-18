"""
Phase 2C: Entity Separation Dashboard Backend Tests
Tests the separation-dashboard endpoint that combines entities, transactions, alerts, and relationships
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "contact@trustoffice.app"
TEST_PASSWORD = "TrustAdmin2026!"
TEST_TRUST_ID = "trust_2097657c7e1d"
TEST_ENTITY_ID = "entity_f2eb8a68d689"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json().get("token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


class TestSeparationDashboardEndpoint:
    """Tests for GET /api/transactions/separation-dashboard"""

    def test_separation_dashboard_returns_200(self, auth_headers):
        """Endpoint returns 200 with valid trust_id"""
        response = requests.get(
            f"{BASE_URL}/api/transactions/separation-dashboard",
            params={"trust_id": TEST_TRUST_ID, "days": 90},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    def test_separation_dashboard_structure(self, auth_headers):
        """Response has correct top-level structure"""
        response = requests.get(
            f"{BASE_URL}/api/transactions/separation-dashboard",
            params={"trust_id": TEST_TRUST_ID},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify top-level keys
        assert "trust_id" in data
        assert "period_days" in data
        assert "entities" in data
        assert "inter_entity_flows" in data
        assert "relationships" in data
        assert "alert_summary" in data
        assert "transaction_summary" in data
        
        # Verify trust_id matches
        assert data["trust_id"] == TEST_TRUST_ID

    def test_separation_dashboard_entities_structure(self, auth_headers):
        """Each entity has required fields for separation dashboard"""
        response = requests.get(
            f"{BASE_URL}/api/transactions/separation-dashboard",
            params={"trust_id": TEST_TRUST_ID},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["entities"]) > 0, "Expected at least one entity"
        
        for entity in data["entities"]:
            # Required fields for separation dashboard
            assert "entity_id" in entity
            assert "name" in entity
            assert "entity_type" in entity
            assert "total_inflows" in entity
            assert "total_outflows" in entity
            assert "net_flow" in entity
            assert "transaction_count" in entity
            assert "red_alerts" in entity
            assert "yellow_alerts" in entity
            assert "total_alerts" in entity
            
            # Verify numeric types
            assert isinstance(entity["total_inflows"], (int, float))
            assert isinstance(entity["total_outflows"], (int, float))
            assert isinstance(entity["net_flow"], (int, float))
            assert isinstance(entity["transaction_count"], int)
            assert isinstance(entity["red_alerts"], int)
            assert isinstance(entity["yellow_alerts"], int)
            assert isinstance(entity["total_alerts"], int)
            
            # Verify total_alerts = red + yellow
            assert entity["total_alerts"] == entity["red_alerts"] + entity["yellow_alerts"]

    def test_separation_dashboard_alert_summary(self, auth_headers):
        """Alert summary has correct structure and values"""
        response = requests.get(
            f"{BASE_URL}/api/transactions/separation-dashboard",
            params={"trust_id": TEST_TRUST_ID},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        alert_summary = data["alert_summary"]
        assert "total_active" in alert_summary
        assert "red_count" in alert_summary
        assert "yellow_count" in alert_summary
        
        # Verify total = red + yellow
        assert alert_summary["total_active"] == alert_summary["red_count"] + alert_summary["yellow_count"]

    def test_separation_dashboard_transaction_summary(self, auth_headers):
        """Transaction summary has correct structure"""
        response = requests.get(
            f"{BASE_URL}/api/transactions/separation-dashboard",
            params={"trust_id": TEST_TRUST_ID},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        txn_summary = data["transaction_summary"]
        assert "total_transactions" in txn_summary
        assert "total_inflows" in txn_summary
        assert "total_outflows" in txn_summary
        
        assert isinstance(txn_summary["total_transactions"], int)
        assert isinstance(txn_summary["total_inflows"], (int, float))
        assert isinstance(txn_summary["total_outflows"], (int, float))

    def test_separation_dashboard_inter_entity_flows(self, auth_headers):
        """Inter-entity flows have correct structure"""
        response = requests.get(
            f"{BASE_URL}/api/transactions/separation-dashboard",
            params={"trust_id": TEST_TRUST_ID},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # May or may not have inter-entity flows
        for flow in data["inter_entity_flows"]:
            assert "source_entity_id" in flow
            assert "source_entity_name" in flow
            assert "dest_entity_id" in flow
            assert "dest_entity_name" in flow
            assert "total_amount" in flow
            assert "transaction_count" in flow
            
            # Source and dest should be different
            assert flow["source_entity_id"] != flow["dest_entity_id"]

    def test_separation_dashboard_relationships(self, auth_headers):
        """Relationships have correct structure"""
        response = requests.get(
            f"{BASE_URL}/api/transactions/separation-dashboard",
            params={"trust_id": TEST_TRUST_ID},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        for rel in data["relationships"]:
            assert "relationship_id" in rel
            assert "parent_entity_id" in rel
            assert "child_entity_id" in rel
            assert "relationship_type" in rel
            # ownership_percentage may be null

    def test_separation_dashboard_days_parameter(self, auth_headers):
        """Days parameter affects the period"""
        response = requests.get(
            f"{BASE_URL}/api/transactions/separation-dashboard",
            params={"trust_id": TEST_TRUST_ID, "days": 30},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["period_days"] == 30

    def test_separation_dashboard_requires_auth(self):
        """Endpoint requires authentication"""
        response = requests.get(
            f"{BASE_URL}/api/transactions/separation-dashboard",
            params={"trust_id": TEST_TRUST_ID}
        )
        assert response.status_code == 401

    def test_separation_dashboard_requires_trust_id(self, auth_headers):
        """Endpoint requires trust_id parameter"""
        response = requests.get(
            f"{BASE_URL}/api/transactions/separation-dashboard",
            headers=auth_headers
        )
        assert response.status_code == 422  # Validation error


class TestEntityTransactionsForDetailPage:
    """Tests for entity-scoped transactions (used in EntityDetailPage)"""

    def test_get_transactions_by_entity(self, auth_headers):
        """Can filter transactions by entity_id"""
        response = requests.get(
            f"{BASE_URL}/api/transactions",
            params={"trust_id": TEST_TRUST_ID, "entity_id": TEST_ENTITY_ID, "limit": 20},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # All returned transactions should be for the specified entity
        for txn in data:
            assert txn["entity_id"] == TEST_ENTITY_ID


class TestEntityAlertsForDetailPage:
    """Tests for entity-scoped alerts (used in EntityDetailPage)"""

    def test_get_alerts_by_entity(self, auth_headers):
        """Can filter alerts by entity_id"""
        response = requests.get(
            f"{BASE_URL}/api/alerts",
            params={"trust_id": TEST_TRUST_ID, "entity_id": TEST_ENTITY_ID},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # All returned alerts should be for the specified entity
        for alert in data:
            assert alert["entity_id"] == TEST_ENTITY_ID


class TestExistingEndpointsRegression:
    """Regression tests for existing endpoints that should still work"""

    def test_entities_endpoint_still_works(self, auth_headers):
        """GET /api/entities still returns entities"""
        response = requests.get(
            f"{BASE_URL}/api/entities",
            params={"trust_id": TEST_TRUST_ID},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0

    def test_entity_relationships_endpoint_still_works(self, auth_headers):
        """GET /api/entity-relationships still returns relationships"""
        response = requests.get(
            f"{BASE_URL}/api/entity-relationships",
            params={"trust_id": TEST_TRUST_ID},
            headers=auth_headers
        )
        assert response.status_code == 200

    def test_transactions_summary_endpoint_still_works(self, auth_headers):
        """GET /api/transactions/summary still works"""
        response = requests.get(
            f"{BASE_URL}/api/transactions/summary",
            params={"trust_id": TEST_TRUST_ID},
            headers=auth_headers
        )
        assert response.status_code == 200

    def test_alerts_count_endpoint_still_works(self, auth_headers):
        """GET /api/alerts/count still works"""
        response = requests.get(
            f"{BASE_URL}/api/alerts/count",
            params={"trust_id": TEST_TRUST_ID},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_active" in data
        assert "red_count" in data
        assert "yellow_count" in data
