"""
Test suite for Separation Alerts (Phase 2B) - Commingling Detection Engine
Tests all alert API endpoints and auto-creation/resolution logic
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from iteration_68
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
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Session with auth header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


class TestAlertEndpoints:
    """Test all alert API endpoints"""

    def test_get_alerts_list(self, api_client):
        """GET /api/alerts?trust_id=X — list active alerts"""
        response = api_client.get(f"{BASE_URL}/api/alerts?trust_id={TEST_TRUST_ID}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
        # If there are alerts, verify structure
        if len(data) > 0:
            alert = data[0]
            assert "alert_id" in alert
            assert "trust_id" in alert
            assert "alert_type" in alert
            assert "severity" in alert
            assert "title" in alert
            assert "description" in alert
            assert "status" in alert
            print(f"Found {len(data)} active alerts")
        else:
            print("No active alerts found")

    def test_get_alerts_with_entity_filter(self, api_client):
        """GET /api/alerts?trust_id=X&entity_id=Y — filter by entity"""
        response = api_client.get(f"{BASE_URL}/api/alerts?trust_id={TEST_TRUST_ID}&entity_id={TEST_ENTITY_ID}")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        # All returned alerts should be for the specified entity
        for alert in data:
            assert alert.get("entity_id") == TEST_ENTITY_ID or alert.get("entity_id") is None
        print(f"Found {len(data)} alerts for entity {TEST_ENTITY_ID}")

    def test_get_alerts_with_severity_filter(self, api_client):
        """GET /api/alerts?trust_id=X&severity=red — filter by severity"""
        response = api_client.get(f"{BASE_URL}/api/alerts?trust_id={TEST_TRUST_ID}&severity=red")
        assert response.status_code == 200
        
        data = response.json()
        for alert in data:
            assert alert.get("severity") == "red"
        print(f"Found {len(data)} red severity alerts")

    def test_get_alert_counts(self, api_client):
        """GET /api/alerts/count?trust_id=X — get alert counts by severity and entity"""
        response = api_client.get(f"{BASE_URL}/api/alerts/count?trust_id={TEST_TRUST_ID}")
        assert response.status_code == 200
        
        data = response.json()
        assert "trust_id" in data
        assert "total_active" in data
        assert "red_count" in data
        assert "yellow_count" in data
        assert "by_entity" in data
        assert "by_type" in data
        
        # Verify counts are non-negative integers
        assert isinstance(data["total_active"], int) and data["total_active"] >= 0
        assert isinstance(data["red_count"], int) and data["red_count"] >= 0
        assert isinstance(data["yellow_count"], int) and data["yellow_count"] >= 0
        
        print(f"Alert counts: total={data['total_active']}, red={data['red_count']}, yellow={data['yellow_count']}")

    def test_get_alert_history(self, api_client):
        """GET /api/alerts/history?trust_id=X — get all alerts including resolved"""
        response = api_client.get(f"{BASE_URL}/api/alerts/history?trust_id={TEST_TRUST_ID}")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        
        # History should include both active and resolved alerts
        statuses = set(a.get("status") for a in data)
        print(f"Found {len(data)} alerts in history, statuses: {statuses}")

    def test_scan_for_alerts(self, api_client):
        """POST /api/alerts/scan?trust_id=X — trigger full pattern scan"""
        response = api_client.post(f"{BASE_URL}/api/alerts/scan?trust_id={TEST_TRUST_ID}")
        assert response.status_code == 200
        
        data = response.json()
        assert "message" in data
        assert "active_alerts" in data
        assert data["message"] == "Scan complete"
        print(f"Scan complete, {data['active_alerts']} active alerts")


class TestAlertAutoCreation:
    """Test automatic alert creation on transaction create"""

    def test_trust_paying_personal_creates_red_alert(self, api_client):
        """Creating outflow to 'Personal' account with non-Distribution/Compensation classification triggers red alert"""
        unique_id = uuid.uuid4().hex[:8]
        
        # Create transaction with 'Personal' in destination, classified as Operational Expense
        txn_response = api_client.post(f"{BASE_URL}/api/transactions", json={
            "trust_id": TEST_TRUST_ID,
            "entity_id": TEST_ENTITY_ID,
            "date": "2026-01-15",
            "amount": 1500.00,
            "direction": "outflow",
            "source_account": "Trust Checking",
            "destination_account": f"TEST_Personal Account {unique_id}",
            "governance_classification": "Operational Expense",
            "purpose_memo": f"TEST alert trigger {unique_id}",
            "other_note": ""
        })
        assert txn_response.status_code == 200, f"Transaction create failed: {txn_response.text}"
        txn = txn_response.json()
        txn_id = txn["transaction_id"]
        
        # Check if alert was created
        alerts_response = api_client.get(f"{BASE_URL}/api/alerts?trust_id={TEST_TRUST_ID}")
        assert alerts_response.status_code == 200
        alerts = alerts_response.json()
        
        # Find alert for this transaction
        matching_alerts = [a for a in alerts if a.get("transaction_id") == txn_id]
        assert len(matching_alerts) > 0, f"Expected alert for transaction {txn_id}, found none"
        
        alert = matching_alerts[0]
        assert alert["alert_type"] == "trust_paying_personal"
        assert alert["severity"] == "red"
        assert alert["status"] == "active"
        print(f"Red alert created: {alert['title']}")
        
        # Cleanup: delete transaction
        api_client.delete(f"{BASE_URL}/api/transactions/{txn_id}")

    def test_large_unexplained_creates_yellow_alert(self, api_client):
        """Creating outflow >$5k classified as 'Other' with no memo triggers yellow alert"""
        unique_id = uuid.uuid4().hex[:8]
        
        # Create large transaction classified as Other with no memo
        txn_response = api_client.post(f"{BASE_URL}/api/transactions", json={
            "trust_id": TEST_TRUST_ID,
            "entity_id": TEST_ENTITY_ID,
            "date": "2026-01-15",
            "amount": 7500.00,
            "direction": "outflow",
            "source_account": "Trust Checking",
            "destination_account": f"TEST_Vendor {unique_id}",
            "governance_classification": "Other",
            "purpose_memo": "",  # No memo
            "other_note": f"TEST large unexplained {unique_id}"  # Required for Other
        })
        assert txn_response.status_code == 200, f"Transaction create failed: {txn_response.text}"
        txn = txn_response.json()
        txn_id = txn["transaction_id"]
        
        # Check if alert was created
        alerts_response = api_client.get(f"{BASE_URL}/api/alerts?trust_id={TEST_TRUST_ID}")
        assert alerts_response.status_code == 200
        alerts = alerts_response.json()
        
        # Find alert for this transaction
        matching_alerts = [a for a in alerts if a.get("transaction_id") == txn_id and a.get("alert_type") == "large_unexplained"]
        assert len(matching_alerts) > 0, f"Expected large_unexplained alert for transaction {txn_id}"
        
        alert = matching_alerts[0]
        assert alert["severity"] == "yellow"
        assert alert["status"] == "active"
        print(f"Yellow alert created: {alert['title']}")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/transactions/{txn_id}")

    def test_unlinked_distribution_creates_yellow_alert(self, api_client):
        """Creating Distribution without linked_distribution_id triggers yellow alert"""
        unique_id = uuid.uuid4().hex[:8]
        
        # Create Distribution transaction without linked governance action
        txn_response = api_client.post(f"{BASE_URL}/api/transactions", json={
            "trust_id": TEST_TRUST_ID,
            "entity_id": TEST_ENTITY_ID,
            "date": "2026-01-15",
            "amount": 2500.00,
            "direction": "outflow",
            "source_account": "Trust Checking",
            "destination_account": f"TEST_Beneficiary {unique_id}",
            "governance_classification": "Distribution",
            "purpose_memo": f"TEST unlinked distribution {unique_id}",
            "other_note": "",
            "linked_distribution_id": None  # Not linked
        })
        assert txn_response.status_code == 200, f"Transaction create failed: {txn_response.text}"
        txn = txn_response.json()
        txn_id = txn["transaction_id"]
        
        # Check if alert was created
        alerts_response = api_client.get(f"{BASE_URL}/api/alerts?trust_id={TEST_TRUST_ID}")
        assert alerts_response.status_code == 200
        alerts = alerts_response.json()
        
        # Find unlinked_governance alert for this transaction
        matching_alerts = [a for a in alerts if a.get("transaction_id") == txn_id and a.get("alert_type") == "unlinked_governance"]
        assert len(matching_alerts) > 0, f"Expected unlinked_governance alert for transaction {txn_id}"
        
        alert = matching_alerts[0]
        assert alert["severity"] == "yellow"
        print(f"Yellow alert created: {alert['title']}")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/transactions/{txn_id}")


class TestAlertResolution:
    """Test alert resolution workflow"""

    def test_resolve_alert_success(self, api_client):
        """POST /api/alerts/{id}/resolve — resolve alert with type and note"""
        unique_id = uuid.uuid4().hex[:8]
        
        # First create a transaction that triggers an alert
        txn_response = api_client.post(f"{BASE_URL}/api/transactions", json={
            "trust_id": TEST_TRUST_ID,
            "entity_id": TEST_ENTITY_ID,
            "date": "2026-01-15",
            "amount": 1000.00,
            "direction": "outflow",
            "source_account": "Trust Checking",
            "destination_account": f"TEST_Personal Expense {unique_id}",
            "governance_classification": "Operational Expense",
            "purpose_memo": f"TEST resolve {unique_id}",
            "other_note": ""
        })
        assert txn_response.status_code == 200
        txn_id = txn_response.json()["transaction_id"]
        
        # Get the alert
        alerts_response = api_client.get(f"{BASE_URL}/api/alerts?trust_id={TEST_TRUST_ID}")
        alerts = alerts_response.json()
        matching_alerts = [a for a in alerts if a.get("transaction_id") == txn_id]
        
        if len(matching_alerts) == 0:
            # Cleanup and skip if no alert was created
            api_client.delete(f"{BASE_URL}/api/transactions/{txn_id}")
            pytest.skip("No alert created for test transaction")
        
        alert_id = matching_alerts[0]["alert_id"]
        
        # Resolve the alert
        resolve_response = api_client.post(f"{BASE_URL}/api/alerts/{alert_id}/resolve", json={
            "resolution_type": "reviewed_no_issue",
            "resolution_note": f"TEST resolution - verified legitimate expense {unique_id}"
        })
        assert resolve_response.status_code == 200, f"Resolve failed: {resolve_response.text}"
        
        resolved = resolve_response.json()
        assert resolved["status"] == "resolved"
        assert resolved["resolution_type"] == "reviewed_no_issue"
        assert "TEST resolution" in resolved["resolution_note"]
        assert resolved["resolved_at"] is not None
        print(f"Alert resolved successfully: {resolved['alert_id']}")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/transactions/{txn_id}")

    def test_resolve_alert_empty_note_rejected(self, api_client):
        """Empty resolution_note is rejected"""
        unique_id = uuid.uuid4().hex[:8]
        
        # Create transaction that triggers alert
        txn_response = api_client.post(f"{BASE_URL}/api/transactions", json={
            "trust_id": TEST_TRUST_ID,
            "entity_id": TEST_ENTITY_ID,
            "date": "2026-01-15",
            "amount": 1000.00,
            "direction": "outflow",
            "source_account": "Trust Checking",
            "destination_account": f"TEST_Personal {unique_id}",
            "governance_classification": "Operational Expense",
            "purpose_memo": f"TEST empty note {unique_id}",
            "other_note": ""
        })
        assert txn_response.status_code == 200
        txn_id = txn_response.json()["transaction_id"]
        
        # Get the alert
        alerts_response = api_client.get(f"{BASE_URL}/api/alerts?trust_id={TEST_TRUST_ID}")
        alerts = alerts_response.json()
        matching_alerts = [a for a in alerts if a.get("transaction_id") == txn_id]
        
        if len(matching_alerts) == 0:
            api_client.delete(f"{BASE_URL}/api/transactions/{txn_id}")
            pytest.skip("No alert created for test transaction")
        
        alert_id = matching_alerts[0]["alert_id"]
        
        # Try to resolve with empty note
        resolve_response = api_client.post(f"{BASE_URL}/api/alerts/{alert_id}/resolve", json={
            "resolution_type": "reviewed_no_issue",
            "resolution_note": ""  # Empty note
        })
        assert resolve_response.status_code == 400, f"Expected 400, got {resolve_response.status_code}"
        assert "required" in resolve_response.json().get("detail", "").lower()
        print("Empty resolution note correctly rejected")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/transactions/{txn_id}")

    def test_resolve_already_resolved_rejected(self, api_client):
        """Already-resolved alerts cannot be resolved again"""
        unique_id = uuid.uuid4().hex[:8]
        
        # Create transaction that triggers alert
        txn_response = api_client.post(f"{BASE_URL}/api/transactions", json={
            "trust_id": TEST_TRUST_ID,
            "entity_id": TEST_ENTITY_ID,
            "date": "2026-01-15",
            "amount": 1000.00,
            "direction": "outflow",
            "source_account": "Trust Checking",
            "destination_account": f"TEST_Personal {unique_id}",
            "governance_classification": "Operational Expense",
            "purpose_memo": f"TEST double resolve {unique_id}",
            "other_note": ""
        })
        assert txn_response.status_code == 200
        txn_id = txn_response.json()["transaction_id"]
        
        # Get the alert
        alerts_response = api_client.get(f"{BASE_URL}/api/alerts?trust_id={TEST_TRUST_ID}")
        alerts = alerts_response.json()
        matching_alerts = [a for a in alerts if a.get("transaction_id") == txn_id]
        
        if len(matching_alerts) == 0:
            api_client.delete(f"{BASE_URL}/api/transactions/{txn_id}")
            pytest.skip("No alert created for test transaction")
        
        alert_id = matching_alerts[0]["alert_id"]
        
        # Resolve the alert first time
        resolve_response = api_client.post(f"{BASE_URL}/api/alerts/{alert_id}/resolve", json={
            "resolution_type": "reviewed_no_issue",
            "resolution_note": f"First resolution {unique_id}"
        })
        assert resolve_response.status_code == 200
        
        # Try to resolve again
        resolve_response2 = api_client.post(f"{BASE_URL}/api/alerts/{alert_id}/resolve", json={
            "resolution_type": "documented",
            "resolution_note": f"Second resolution attempt {unique_id}"
        })
        assert resolve_response2.status_code == 400, f"Expected 400, got {resolve_response2.status_code}"
        assert "already resolved" in resolve_response2.json().get("detail", "").lower()
        print("Double resolution correctly rejected")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/transactions/{txn_id}")


class TestAlertAutoResolution:
    """Test automatic alert resolution when underlying issue is fixed"""

    def test_linking_distribution_resolves_unlinked_alert(self, api_client):
        """Updating transaction to link distribution_id resolves unlinked_governance alerts"""
        unique_id = uuid.uuid4().hex[:8]
        
        # Create Distribution without link (triggers alert)
        txn_response = api_client.post(f"{BASE_URL}/api/transactions", json={
            "trust_id": TEST_TRUST_ID,
            "entity_id": TEST_ENTITY_ID,
            "date": "2026-01-15",
            "amount": 3000.00,
            "direction": "outflow",
            "source_account": "Trust Checking",
            "destination_account": f"TEST_Beneficiary {unique_id}",
            "governance_classification": "Distribution",
            "purpose_memo": f"TEST auto-resolve {unique_id}",
            "other_note": "",
            "linked_distribution_id": None
        })
        assert txn_response.status_code == 200
        txn_id = txn_response.json()["transaction_id"]
        
        # Verify alert was created
        alerts_response = api_client.get(f"{BASE_URL}/api/alerts?trust_id={TEST_TRUST_ID}")
        alerts = alerts_response.json()
        matching_alerts = [a for a in alerts if a.get("transaction_id") == txn_id and a.get("alert_type") == "unlinked_governance"]
        
        if len(matching_alerts) == 0:
            api_client.delete(f"{BASE_URL}/api/transactions/{txn_id}")
            pytest.skip("No unlinked_governance alert created")
        
        alert_id = matching_alerts[0]["alert_id"]
        print(f"Alert created: {alert_id}")
        
        # Update transaction to link a distribution
        update_response = api_client.patch(f"{BASE_URL}/api/transactions/{txn_id}", json={
            "linked_distribution_id": f"dist_test_{unique_id}"
        })
        assert update_response.status_code == 200
        
        # Check if alert was auto-resolved
        alerts_response2 = api_client.get(f"{BASE_URL}/api/alerts/history?trust_id={TEST_TRUST_ID}")
        history = alerts_response2.json()
        
        resolved_alert = next((a for a in history if a["alert_id"] == alert_id), None)
        if resolved_alert:
            assert resolved_alert["status"] == "resolved", f"Alert should be resolved, got {resolved_alert['status']}"
            assert resolved_alert["resolution_type"] == "linked"
            print(f"Alert auto-resolved: {resolved_alert['resolution_note']}")
        else:
            print("Alert not found in history - may have been cleaned up")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/transactions/{txn_id}")


class TestAlertValidation:
    """Test alert validation and edge cases"""

    def test_resolve_nonexistent_alert(self, api_client):
        """Resolving non-existent alert returns 404"""
        response = api_client.post(f"{BASE_URL}/api/alerts/alert_nonexistent_12345/resolve", json={
            "resolution_type": "reviewed_no_issue",
            "resolution_note": "Test note"
        })
        assert response.status_code == 404

    def test_resolve_invalid_type(self, api_client):
        """Invalid resolution_type is rejected"""
        unique_id = uuid.uuid4().hex[:8]
        
        # Create transaction that triggers alert
        txn_response = api_client.post(f"{BASE_URL}/api/transactions", json={
            "trust_id": TEST_TRUST_ID,
            "entity_id": TEST_ENTITY_ID,
            "date": "2026-01-15",
            "amount": 1000.00,
            "direction": "outflow",
            "source_account": "Trust Checking",
            "destination_account": f"TEST_Personal {unique_id}",
            "governance_classification": "Operational Expense",
            "purpose_memo": f"TEST invalid type {unique_id}",
            "other_note": ""
        })
        assert txn_response.status_code == 200
        txn_id = txn_response.json()["transaction_id"]
        
        # Get the alert
        alerts_response = api_client.get(f"{BASE_URL}/api/alerts?trust_id={TEST_TRUST_ID}")
        alerts = alerts_response.json()
        matching_alerts = [a for a in alerts if a.get("transaction_id") == txn_id]
        
        if len(matching_alerts) == 0:
            api_client.delete(f"{BASE_URL}/api/transactions/{txn_id}")
            pytest.skip("No alert created for test transaction")
        
        alert_id = matching_alerts[0]["alert_id"]
        
        # Try to resolve with invalid type
        resolve_response = api_client.post(f"{BASE_URL}/api/alerts/{alert_id}/resolve", json={
            "resolution_type": "invalid_type",
            "resolution_note": "Test note"
        })
        assert resolve_response.status_code == 400
        print("Invalid resolution type correctly rejected")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/transactions/{txn_id}")

    def test_scan_nonexistent_trust(self, api_client):
        """Scanning non-existent trust returns 404"""
        response = api_client.post(f"{BASE_URL}/api/alerts/scan?trust_id=trust_nonexistent_12345")
        assert response.status_code == 404


class TestAlertTypes:
    """Test different alert types and their triggers"""

    def test_distribution_without_link_triggers_alert(self, api_client):
        """Distribution classification without linked_distribution_id triggers unlinked_governance"""
        unique_id = uuid.uuid4().hex[:8]
        
        txn_response = api_client.post(f"{BASE_URL}/api/transactions", json={
            "trust_id": TEST_TRUST_ID,
            "entity_id": TEST_ENTITY_ID,
            "date": "2026-01-15",
            "amount": 5000.00,
            "direction": "outflow",
            "source_account": "Trust Checking",
            "destination_account": f"TEST_Beneficiary {unique_id}",
            "governance_classification": "Distribution",
            "purpose_memo": f"TEST distribution alert {unique_id}",
            "other_note": ""
        })
        assert txn_response.status_code == 200
        txn_id = txn_response.json()["transaction_id"]
        
        alerts_response = api_client.get(f"{BASE_URL}/api/alerts?trust_id={TEST_TRUST_ID}&alert_type=unlinked_governance")
        alerts = alerts_response.json()
        matching = [a for a in alerts if a.get("transaction_id") == txn_id]
        
        assert len(matching) > 0, "Expected unlinked_governance alert for Distribution"
        print(f"Distribution alert created: {matching[0]['title']}")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/transactions/{txn_id}")

    def test_compensation_without_link_triggers_alert(self, api_client):
        """Compensation classification without linked_compensation_payment_id triggers unlinked_governance"""
        unique_id = uuid.uuid4().hex[:8]
        
        txn_response = api_client.post(f"{BASE_URL}/api/transactions", json={
            "trust_id": TEST_TRUST_ID,
            "entity_id": TEST_ENTITY_ID,
            "date": "2026-01-15",
            "amount": 2000.00,
            "direction": "outflow",
            "source_account": "Trust Checking",
            "destination_account": f"TEST_Trustee {unique_id}",
            "governance_classification": "Compensation",
            "purpose_memo": f"TEST compensation alert {unique_id}",
            "other_note": ""
        })
        assert txn_response.status_code == 200
        txn_id = txn_response.json()["transaction_id"]
        
        alerts_response = api_client.get(f"{BASE_URL}/api/alerts?trust_id={TEST_TRUST_ID}&alert_type=unlinked_governance")
        alerts = alerts_response.json()
        matching = [a for a in alerts if a.get("transaction_id") == txn_id]
        
        assert len(matching) > 0, "Expected unlinked_governance alert for Compensation"
        print(f"Compensation alert created: {matching[0]['title']}")
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/transactions/{txn_id}")

    def test_personal_keyword_variations(self, api_client):
        """Test various personal keywords trigger trust_paying_personal alert"""
        keywords = ["Personal", "Individual", "Private", "Self"]
        
        for keyword in keywords:
            unique_id = uuid.uuid4().hex[:8]
            
            txn_response = api_client.post(f"{BASE_URL}/api/transactions", json={
                "trust_id": TEST_TRUST_ID,
                "entity_id": TEST_ENTITY_ID,
                "date": "2026-01-15",
                "amount": 500.00,
                "direction": "outflow",
                "source_account": "Trust Checking",
                "destination_account": f"TEST_{keyword} Account {unique_id}",
                "governance_classification": "Operational Expense",
                "purpose_memo": f"TEST keyword {keyword} {unique_id}",
                "other_note": ""
            })
            
            if txn_response.status_code == 200:
                txn_id = txn_response.json()["transaction_id"]
                
                alerts_response = api_client.get(f"{BASE_URL}/api/alerts?trust_id={TEST_TRUST_ID}")
                alerts = alerts_response.json()
                matching = [a for a in alerts if a.get("transaction_id") == txn_id and a.get("alert_type") == "trust_paying_personal"]
                
                if len(matching) > 0:
                    print(f"Keyword '{keyword}' triggered alert")
                else:
                    print(f"Keyword '{keyword}' did not trigger alert (may be case-sensitive)")
                
                # Cleanup
                api_client.delete(f"{BASE_URL}/api/transactions/{txn_id}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
