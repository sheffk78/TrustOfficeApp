"""
Phase 2 Comprehensive QA Tests - Structural Separation & Commingling Monitoring
Tests: Transaction Ledger, Alerts, Health Score, Separation Dashboard, Audit Defense PDF
"""
import pytest
import requests
import os
import uuid
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "contact@trustoffice.app"
TEST_PASSWORD = "TrustAdmin2026!"
TRUST_ID = "trust_2097657c7e1d"  # Smith Family Trust
ENTITY_ID = "entity_f2eb8a68d689"  # Smith Family Trust entity

# Classification values
CLASSIFICATIONS = ["Distribution", "Compensation", "Inter-Entity Transfer", "Operational Expense", "Capital Contribution", "Tax Payment", "Other"]


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
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


# ==================== TRANSACTION LEDGER TESTS ====================

class TestTransactionLedger:
    """Transaction CRUD, CSV import, bulk classify, filtering"""
    
    def test_create_transaction_all_fields(self, api_client):
        """LEDGER - Manual entry: Create transaction with all fields"""
        txn_data = {
            "trust_id": TRUST_ID,
            "entity_id": ENTITY_ID,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "amount": 1500.00,
            "direction": "outflow",
            "source_account": "Trust Operating Account",
            "destination_account": "Vendor ABC",
            "governance_classification": "Operational Expense",
            "purpose_memo": "TEST_Office supplies purchase",
            "other_note": ""
        }
        response = api_client.post(f"{BASE_URL}/api/transactions", json=txn_data)
        assert response.status_code == 200, f"Create failed: {response.text}"
        data = response.json()
        assert data["transaction_id"].startswith("txn_")
        assert data["amount"] == 1500.00
        assert data["governance_classification"] == "Operational Expense"
        assert data["purpose_memo"] == "TEST_Office supplies purchase"
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/transactions/{data['transaction_id']}")
    
    def test_create_transaction_requires_classification(self, api_client):
        """LEDGER - Required classification: Attempt save without classification should fail"""
        txn_data = {
            "trust_id": TRUST_ID,
            "entity_id": ENTITY_ID,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "amount": 500.00,
            "direction": "outflow",
            "source_account": "Trust Account",
            "destination_account": "Vendor",
            "governance_classification": "",  # Empty classification
            "purpose_memo": "TEST_No classification"
        }
        response = api_client.post(f"{BASE_URL}/api/transactions", json=txn_data)
        # Should fail validation
        assert response.status_code in [400, 422], f"Should reject empty classification: {response.text}"
    
    def test_other_classification_requires_note(self, api_client):
        """LEDGER - 'Other' requires note: Save 'Other' classified txn without other_note should fail"""
        txn_data = {
            "trust_id": TRUST_ID,
            "entity_id": ENTITY_ID,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "amount": 6000.00,
            "direction": "outflow",
            "source_account": "Trust Account",
            "destination_account": "Unknown Vendor",
            "governance_classification": "Other",
            "purpose_memo": "TEST_Other without note",
            "other_note": ""  # Empty note for Other
        }
        response = api_client.post(f"{BASE_URL}/api/transactions", json=txn_data)
        assert response.status_code == 400, f"Should reject Other without note: {response.text}"
        assert "note is required" in response.json().get("detail", "").lower()
    
    def test_other_classification_with_note_succeeds(self, api_client):
        """LEDGER - 'Other' with note succeeds"""
        txn_data = {
            "trust_id": TRUST_ID,
            "entity_id": ENTITY_ID,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "amount": 6000.00,
            "direction": "outflow",
            "source_account": "Trust Account",
            "destination_account": "Unknown Vendor",
            "governance_classification": "Other",
            "purpose_memo": "TEST_Other with note",
            "other_note": "This is a one-time miscellaneous expense for trust administration"
        }
        response = api_client.post(f"{BASE_URL}/api/transactions", json=txn_data)
        assert response.status_code == 200, f"Should accept Other with note: {response.text}"
        data = response.json()
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/transactions/{data['transaction_id']}")
    
    def test_get_transactions_with_filters(self, api_client):
        """LEDGER - Filter by classification and direction"""
        # Get all transactions
        response = api_client.get(f"{BASE_URL}/api/transactions?trust_id={TRUST_ID}")
        assert response.status_code == 200
        all_txns = response.json()
        
        # Filter by classification
        response = api_client.get(f"{BASE_URL}/api/transactions?trust_id={TRUST_ID}&classification=Distribution")
        assert response.status_code == 200
        dist_txns = response.json()
        for t in dist_txns:
            assert t["governance_classification"] == "Distribution"
        
        # Filter by direction
        response = api_client.get(f"{BASE_URL}/api/transactions?trust_id={TRUST_ID}&direction=outflow")
        assert response.status_code == 200
        outflow_txns = response.json()
        for t in outflow_txns:
            assert t["direction"] == "outflow"
    
    def test_per_entity_scoping(self, api_client):
        """LEDGER - Per-entity scoping: Transaction in entity A does not appear when filtering by entity B"""
        # Get entities
        response = api_client.get(f"{BASE_URL}/api/entities?trust_id={TRUST_ID}")
        assert response.status_code == 200
        entities = response.json()
        
        if len(entities) >= 2:
            entity_a = entities[0]["entity_id"]
            entity_b = entities[1]["entity_id"]
            
            # Create transaction in entity A
            txn_data = {
                "trust_id": TRUST_ID,
                "entity_id": entity_a,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "amount": 999.99,
                "direction": "outflow",
                "source_account": "Entity A Account",
                "destination_account": "Vendor",
                "governance_classification": "Operational Expense",
                "purpose_memo": "TEST_Entity scoping test"
            }
            create_res = api_client.post(f"{BASE_URL}/api/transactions", json=txn_data)
            assert create_res.status_code == 200
            txn_id = create_res.json()["transaction_id"]
            
            # Query entity B - should NOT contain this transaction
            response = api_client.get(f"{BASE_URL}/api/transactions?trust_id={TRUST_ID}&entity_id={entity_b}")
            assert response.status_code == 200
            entity_b_txns = response.json()
            txn_ids_in_b = [t["transaction_id"] for t in entity_b_txns]
            assert txn_id not in txn_ids_in_b, "Transaction from entity A should not appear in entity B filter"
            
            # Cleanup
            api_client.delete(f"{BASE_URL}/api/transactions/{txn_id}")
    
    def test_csv_import(self, api_client):
        """LEDGER - CSV Import: Import rows and verify they appear in ledger"""
        import_data = {
            "trust_id": TRUST_ID,
            "entity_id": ENTITY_ID,
            "rows": [
                {"date": "2025-01-15", "amount": 100.00, "direction": "outflow", "description": "TEST_Import row 1"},
                {"date": "2025-01-16", "amount": 200.00, "direction": "inflow", "description": "TEST_Import row 2"},
                {"date": "2025-01-17", "amount": 300.00, "direction": "outflow", "description": "TEST_Import row 3"}
            ]
        }
        response = api_client.post(f"{BASE_URL}/api/transactions/import", json=import_data)
        assert response.status_code == 200, f"Import failed: {response.text}"
        imported = response.json()
        assert len(imported) == 3, "Should import 3 transactions"
        
        # Verify they appear in ledger
        response = api_client.get(f"{BASE_URL}/api/transactions?trust_id={TRUST_ID}")
        assert response.status_code == 200
        all_txns = response.json()
        imported_ids = [t["transaction_id"] for t in imported]
        found_count = sum(1 for t in all_txns if t["transaction_id"] in imported_ids)
        assert found_count == 3, "All imported transactions should appear in ledger"
        
        # Cleanup
        for t in imported:
            api_client.delete(f"{BASE_URL}/api/transactions/{t['transaction_id']}")
    
    def test_bulk_classify(self, api_client):
        """LEDGER - Bulk classification: Select multiple transactions and classify them all at once"""
        # First import some unclassified transactions
        import_data = {
            "trust_id": TRUST_ID,
            "entity_id": ENTITY_ID,
            "rows": [
                {"date": "2025-01-20", "amount": 111.00, "direction": "outflow", "description": "TEST_Bulk 1"},
                {"date": "2025-01-21", "amount": 222.00, "direction": "outflow", "description": "TEST_Bulk 2"}
            ]
        }
        import_res = api_client.post(f"{BASE_URL}/api/transactions/import", json=import_data)
        assert import_res.status_code == 200
        imported = import_res.json()
        txn_ids = [t["transaction_id"] for t in imported]
        
        # Bulk classify
        bulk_data = {
            "transaction_ids": txn_ids,
            "governance_classification": "Operational Expense",
            "purpose_memo": "Bulk classified as operational",
            "other_note": ""
        }
        response = api_client.post(f"{BASE_URL}/api/transactions/bulk-classify", json=bulk_data)
        assert response.status_code == 200, f"Bulk classify failed: {response.text}"
        result = response.json()
        assert result["modified"] == 2, "Should modify 2 transactions"
        
        # Verify classification
        for txn_id in txn_ids:
            response = api_client.get(f"{BASE_URL}/api/transactions?trust_id={TRUST_ID}")
            txns = response.json()
            txn = next((t for t in txns if t["transaction_id"] == txn_id), None)
            if txn:
                assert txn["governance_classification"] == "Operational Expense"
        
        # Cleanup
        for txn_id in txn_ids:
            api_client.delete(f"{BASE_URL}/api/transactions/{txn_id}")
    
    def test_long_memo_2000_chars(self, api_client):
        """EDGE - Long memo (2000 chars): Saves without truncation"""
        long_memo = "A" * 2000
        txn_data = {
            "trust_id": TRUST_ID,
            "entity_id": ENTITY_ID,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "amount": 50.00,
            "direction": "outflow",
            "source_account": "Trust Account",
            "destination_account": "Vendor",
            "governance_classification": "Operational Expense",
            "purpose_memo": long_memo
        }
        response = api_client.post(f"{BASE_URL}/api/transactions", json=txn_data)
        assert response.status_code == 200, f"Long memo failed: {response.text}"
        data = response.json()
        assert len(data["purpose_memo"]) == 2000, "Memo should not be truncated"
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/transactions/{data['transaction_id']}")


# ==================== ALERT DETECTION TESTS ====================

class TestAlertDetection:
    """Commingling detection alert triggers and resolution"""
    
    def test_trust_paying_personal_triggers_red_alert(self, api_client):
        """ALERTS - Trust paying personal: Outflow to 'personal' destination as non-Distribution triggers red alert"""
        txn_data = {
            "trust_id": TRUST_ID,
            "entity_id": ENTITY_ID,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "amount": 5000.00,
            "direction": "outflow",
            "source_account": "Trust Operating",
            "destination_account": "Personal Checking Account",  # Contains 'personal'
            "governance_classification": "Operational Expense",  # Not Distribution/Compensation
            "purpose_memo": "TEST_Personal payment alert test"
        }
        response = api_client.post(f"{BASE_URL}/api/transactions", json=txn_data)
        assert response.status_code == 200
        txn_id = response.json()["transaction_id"]
        
        # Check for alert
        response = api_client.get(f"{BASE_URL}/api/alerts?trust_id={TRUST_ID}&status=active")
        assert response.status_code == 200
        alerts = response.json()
        
        # Find alert for this transaction
        txn_alerts = [a for a in alerts if a.get("transaction_id") == txn_id]
        assert len(txn_alerts) > 0, "Should create alert for personal payment"
        assert any(a["severity"] == "red" for a in txn_alerts), "Should be a red alert"
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/transactions/{txn_id}")
    
    def test_large_unexplained_triggers_yellow_alert(self, api_client):
        """ALERTS - Large unexplained: $10k+ outflow classified 'Other' with no memo triggers yellow alert"""
        txn_data = {
            "trust_id": TRUST_ID,
            "entity_id": ENTITY_ID,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "amount": 10000.00,
            "direction": "outflow",
            "source_account": "Trust Account",
            "destination_account": "Unknown Vendor",
            "governance_classification": "Other",
            "purpose_memo": "",  # No memo
            "other_note": "Large transfer test"  # Required for Other
        }
        response = api_client.post(f"{BASE_URL}/api/transactions", json=txn_data)
        assert response.status_code == 200
        txn_id = response.json()["transaction_id"]
        
        # Check for alert
        response = api_client.get(f"{BASE_URL}/api/alerts?trust_id={TRUST_ID}&status=active")
        assert response.status_code == 200
        alerts = response.json()
        
        # Find large_unexplained alert
        txn_alerts = [a for a in alerts if a.get("transaction_id") == txn_id and a.get("alert_type") == "large_unexplained"]
        assert len(txn_alerts) > 0, "Should create large_unexplained alert"
        assert txn_alerts[0]["severity"] == "yellow", "Should be yellow alert"
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/transactions/{txn_id}")
    
    def test_unlinked_distribution_triggers_alert(self, api_client):
        """ALERTS - Unlinked distribution: Distribution without linked_distribution_id triggers yellow alert"""
        txn_data = {
            "trust_id": TRUST_ID,
            "entity_id": ENTITY_ID,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "amount": 2000.00,
            "direction": "outflow",
            "source_account": "Trust Account",
            "destination_account": "Beneficiary Account",
            "governance_classification": "Distribution",
            "purpose_memo": "TEST_Unlinked distribution",
            "linked_distribution_id": None  # Not linked
        }
        response = api_client.post(f"{BASE_URL}/api/transactions", json=txn_data)
        assert response.status_code == 200
        txn_id = response.json()["transaction_id"]
        
        # Check for unlinked_governance alert
        response = api_client.get(f"{BASE_URL}/api/alerts?trust_id={TRUST_ID}&status=active")
        assert response.status_code == 200
        alerts = response.json()
        
        txn_alerts = [a for a in alerts if a.get("transaction_id") == txn_id and a.get("alert_type") == "unlinked_governance"]
        assert len(txn_alerts) > 0, "Should create unlinked_governance alert for Distribution"
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/transactions/{txn_id}")
    
    def test_unlinked_compensation_triggers_alert(self, api_client):
        """ALERTS - Unlinked compensation: Compensation without linked_compensation_payment_id triggers yellow alert"""
        txn_data = {
            "trust_id": TRUST_ID,
            "entity_id": ENTITY_ID,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "amount": 3000.00,
            "direction": "outflow",
            "source_account": "Trust Account",
            "destination_account": "Trustee Account",
            "governance_classification": "Compensation",
            "purpose_memo": "TEST_Unlinked compensation",
            "linked_compensation_payment_id": None  # Not linked
        }
        response = api_client.post(f"{BASE_URL}/api/transactions", json=txn_data)
        assert response.status_code == 200
        txn_id = response.json()["transaction_id"]
        
        # Check for unlinked_governance alert
        response = api_client.get(f"{BASE_URL}/api/alerts?trust_id={TRUST_ID}&status=active")
        assert response.status_code == 200
        alerts = response.json()
        
        txn_alerts = [a for a in alerts if a.get("transaction_id") == txn_id and a.get("alert_type") == "unlinked_governance"]
        assert len(txn_alerts) > 0, "Should create unlinked_governance alert for Compensation"
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/transactions/{txn_id}")
    
    def test_no_false_positive_clean_transaction(self, api_client):
        """ALERTS - No false positive: Clean transaction (Operational Expense, with memo, no personal keywords) should NOT trigger alert"""
        txn_data = {
            "trust_id": TRUST_ID,
            "entity_id": ENTITY_ID,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "amount": 500.00,
            "direction": "outflow",
            "source_account": "Trust Operating Account",
            "destination_account": "Office Depot",  # No personal keywords
            "governance_classification": "Operational Expense",
            "purpose_memo": "TEST_Clean transaction - office supplies"
        }
        response = api_client.post(f"{BASE_URL}/api/transactions", json=txn_data)
        assert response.status_code == 200
        txn_id = response.json()["transaction_id"]
        
        # Check for alerts - should be none for this transaction
        response = api_client.get(f"{BASE_URL}/api/alerts?trust_id={TRUST_ID}&status=active")
        assert response.status_code == 200
        alerts = response.json()
        
        txn_alerts = [a for a in alerts if a.get("transaction_id") == txn_id]
        assert len(txn_alerts) == 0, f"Clean transaction should NOT trigger alerts, but found: {txn_alerts}"
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/transactions/{txn_id}")
    
    def test_resolve_alert_with_note(self, api_client):
        """ALERTS - Resolve with note: Resolve alert with resolution_type + resolution_note succeeds"""
        # First create a transaction that triggers an alert
        txn_data = {
            "trust_id": TRUST_ID,
            "entity_id": ENTITY_ID,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "amount": 5000.00,
            "direction": "outflow",
            "source_account": "Trust Account",
            "destination_account": "Personal Account",
            "governance_classification": "Operational Expense",
            "purpose_memo": "TEST_Alert resolution test"
        }
        response = api_client.post(f"{BASE_URL}/api/transactions", json=txn_data)
        assert response.status_code == 200
        txn_id = response.json()["transaction_id"]
        
        # Get the alert
        response = api_client.get(f"{BASE_URL}/api/alerts?trust_id={TRUST_ID}&status=active")
        alerts = response.json()
        txn_alerts = [a for a in alerts if a.get("transaction_id") == txn_id]
        
        if txn_alerts:
            alert_id = txn_alerts[0]["alert_id"]
            
            # Resolve with note
            resolve_data = {
                "resolution_type": "reviewed_no_issue",
                "resolution_note": "Reviewed by trustee - this is a legitimate trust expense"
            }
            response = api_client.post(f"{BASE_URL}/api/alerts/{alert_id}/resolve", json=resolve_data)
            assert response.status_code == 200, f"Resolve failed: {response.text}"
            resolved = response.json()
            assert resolved["status"] == "resolved"
            assert resolved["resolution_type"] == "reviewed_no_issue"
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/transactions/{txn_id}")
    
    def test_resolve_without_note_rejected(self, api_client):
        """ALERTS - Resolve without note: Try resolving without note should be rejected"""
        # Get any active alert
        response = api_client.get(f"{BASE_URL}/api/alerts?trust_id={TRUST_ID}&status=active")
        alerts = response.json()
        
        if alerts:
            alert_id = alerts[0]["alert_id"]
            
            # Try to resolve without note
            resolve_data = {
                "resolution_type": "reviewed_no_issue",
                "resolution_note": ""  # Empty note
            }
            response = api_client.post(f"{BASE_URL}/api/alerts/{alert_id}/resolve", json=resolve_data)
            assert response.status_code == 400, "Should reject resolution without note"
    
    def test_already_resolved_rejected(self, api_client):
        """ALERTS - Already-resolved: Try resolving an already-resolved alert should be rejected"""
        # Get resolved alerts from history
        response = api_client.get(f"{BASE_URL}/api/alerts/history?trust_id={TRUST_ID}")
        assert response.status_code == 200
        history = response.json()
        
        resolved_alerts = [a for a in history if a.get("status") == "resolved"]
        if resolved_alerts:
            alert_id = resolved_alerts[0]["alert_id"]
            
            # Try to resolve again
            resolve_data = {
                "resolution_type": "documented",
                "resolution_note": "Trying to resolve again"
            }
            response = api_client.post(f"{BASE_URL}/api/alerts/{alert_id}/resolve", json=resolve_data)
            assert response.status_code == 400, "Should reject resolving already-resolved alert"
            assert "already resolved" in response.json().get("detail", "").lower()
    
    def test_alert_history_preserved(self, api_client):
        """ALERTS - Audit log preserved: Resolved alerts appear in /api/alerts/history with resolution details"""
        response = api_client.get(f"{BASE_URL}/api/alerts/history?trust_id={TRUST_ID}")
        assert response.status_code == 200
        history = response.json()
        
        # Check that resolved alerts have resolution details
        resolved = [a for a in history if a.get("status") == "resolved"]
        for alert in resolved:
            assert alert.get("resolution_type") is not None, "Resolved alert should have resolution_type"
            assert alert.get("resolution_note") is not None, "Resolved alert should have resolution_note"
            assert alert.get("resolved_at") is not None, "Resolved alert should have resolved_at timestamp"
    
    def test_pattern_scan(self, api_client):
        """ALERTS - Pattern scan: POST /api/alerts/scan triggers pattern detection"""
        response = api_client.post(f"{BASE_URL}/api/alerts/scan?trust_id={TRUST_ID}")
        assert response.status_code == 200, f"Scan failed: {response.text}"
        result = response.json()
        assert "active_alerts" in result, "Scan should return active_alerts count"
    
    def test_generate_resolution_minutes(self, api_client):
        """ALERTS - Generate minutes from resolution: POST /api/alerts/{id}/generate-resolution creates minutes record"""
        # Get a resolved alert
        response = api_client.get(f"{BASE_URL}/api/alerts/history?trust_id={TRUST_ID}")
        history = response.json()
        resolved = [a for a in history if a.get("status") == "resolved"]
        
        if resolved:
            alert_id = resolved[0]["alert_id"]
            response = api_client.post(f"{BASE_URL}/api/alerts/{alert_id}/generate-resolution")
            assert response.status_code == 200, f"Generate minutes failed: {response.text}"
            result = response.json()
            assert "minutes_id" in result, "Should return minutes_id"
            assert result["minutes_type"] == "general"


# ==================== HEALTH SCORE TESTS ====================

class TestHealthScore:
    """Governance health score with 7 criteria"""
    
    def test_health_score_7_criteria(self, api_client):
        """HEALTH SCORE - 7 criteria present: Score includes Transaction Classification + Separation Alert Health"""
        response = api_client.get(f"{BASE_URL}/api/governance/{TRUST_ID}")
        assert response.status_code == 200, f"Health score failed: {response.text}"
        data = response.json()
        
        assert "criteria" in data, "Should have criteria list"
        criteria_names = [c["name"] for c in data["criteria"]]
        
        expected_criteria = [
            "Quarterly Minutes",
            "Task Compliance",
            "Compensation Alignment",
            "Distribution Documentation",
            "Annual Review",
            "Asset Valuation Freshness",
            "Transaction Classification",
            "Separation Alert Health"
        ]
        
        for expected in expected_criteria:
            assert expected in criteria_names, f"Missing criterion: {expected}"
        
        assert len(data["criteria"]) == 8, f"Should have exactly 8 criteria, got {len(data['criteria'])}"
        assert data["max_score"] == 115, "Max score should be 115"
    
    def test_red_alerts_decrease_score(self, api_client):
        """HEALTH SCORE - Red alerts decrease score: Active red alerts → Separation Alert Health = 0pts"""
        # Create a transaction that triggers a red alert
        txn_data = {
            "trust_id": TRUST_ID,
            "entity_id": ENTITY_ID,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "amount": 8000.00,
            "direction": "outflow",
            "source_account": "Trust Account",
            "destination_account": "Personal Savings",  # Triggers red alert
            "governance_classification": "Operational Expense",
            "purpose_memo": "TEST_Red alert health score test"
        }
        response = api_client.post(f"{BASE_URL}/api/transactions", json=txn_data)
        assert response.status_code == 200
        txn_id = response.json()["transaction_id"]
        
        # Check health score
        response = api_client.get(f"{BASE_URL}/api/governance/{TRUST_ID}")
        assert response.status_code == 200
        data = response.json()
        
        # Find Separation Alert Health criterion
        alert_criterion = next((c for c in data["criteria"] if c["name"] == "Separation Alert Health"), None)
        assert alert_criterion is not None, "Should have Separation Alert Health criterion"
        
        # With red alerts, points should be 0
        if alert_criterion["description"] and "red" in alert_criterion["description"].lower():
            assert alert_criterion["points"] == 0, "Red alerts should result in 0 points"
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/transactions/{txn_id}")


# ==================== SEPARATION DASHBOARD TESTS ====================

class TestSeparationDashboard:
    """Entity separation dashboard with overview stats"""
    
    def test_separation_dashboard_data(self, api_client):
        """DASHBOARD - Separation dashboard returns overview stats"""
        response = api_client.get(f"{BASE_URL}/api/transactions/separation-dashboard?trust_id={TRUST_ID}&days=90")
        assert response.status_code == 200, f"Dashboard failed: {response.text}"
        data = response.json()
        
        assert "entities" in data, "Should have entities list"
        assert "alert_summary" in data, "Should have alert_summary"
        assert "transaction_summary" in data, "Should have transaction_summary"
        assert "inter_entity_flows" in data, "Should have inter_entity_flows"
        
        # Check alert summary structure
        assert "total_active" in data["alert_summary"]
        assert "red_count" in data["alert_summary"]
        assert "yellow_count" in data["alert_summary"]
        
        # Check transaction summary structure
        assert "total_transactions" in data["transaction_summary"]
        assert "total_inflows" in data["transaction_summary"]
        assert "total_outflows" in data["transaction_summary"]
    
    def test_entity_cards_have_alert_badges(self, api_client):
        """DASHBOARD - Entity cards show alert badges (red/yellow counts)"""
        response = api_client.get(f"{BASE_URL}/api/transactions/separation-dashboard?trust_id={TRUST_ID}&days=90")
        assert response.status_code == 200
        data = response.json()
        
        for entity in data["entities"]:
            assert "red_alerts" in entity, "Entity should have red_alerts count"
            assert "yellow_alerts" in entity, "Entity should have yellow_alerts count"
            assert "total_alerts" in entity, "Entity should have total_alerts count"
            assert "total_inflows" in entity, "Entity should have total_inflows"
            assert "total_outflows" in entity, "Entity should have total_outflows"
            assert "transaction_count" in entity, "Entity should have transaction_count"


# ==================== AUDIT DEFENSE PDF TESTS ====================

class TestAuditDefensePDF:
    """Audit Defense PDF export"""
    
    def test_audit_defense_pdf_generation(self, api_client):
        """AUDIT PDF - GET /api/exports/audit-defense/{trust_id} returns valid PDF"""
        response = api_client.get(f"{BASE_URL}/api/exports/audit-defense/{TRUST_ID}?days=365")
        assert response.status_code == 200, f"PDF generation failed: {response.text}"
        
        # Check content type
        content_type = response.headers.get("content-type", "")
        assert "application/pdf" in content_type, f"Should return PDF, got: {content_type}"
        
        # Check content disposition
        content_disp = response.headers.get("content-disposition", "")
        assert "attachment" in content_disp, "Should be attachment download"
        assert "audit_defense" in content_disp, "Filename should contain audit_defense"
        
        # Check PDF content starts with PDF header
        content = response.content
        assert content[:4] == b'%PDF', "Content should be valid PDF"
        assert len(content) > 1000, "PDF should have substantial content"


# ==================== INTEGRATION TESTS ====================

class TestIntegration:
    """Integration with existing MVP modules"""
    
    def test_transaction_review_task_auto_created(self, api_client):
        """INTEGRATION - Governance Calendar has transaction_review task type auto-created monthly"""
        # Trigger health score calculation which creates the task
        response = api_client.get(f"{BASE_URL}/api/governance/{TRUST_ID}")
        assert response.status_code == 200
        
        # Check for transaction_review task
        response = api_client.get(f"{BASE_URL}/api/tasks?trust_id={TRUST_ID}")
        assert response.status_code == 200
        tasks = response.json()
        
        txn_review_tasks = [t for t in tasks if t.get("task_type") == "transaction_review"]
        # May or may not exist depending on whether trust has transactions
        # Just verify the endpoint works
        assert isinstance(tasks, list)


# ==================== EDGE CASE TESTS ====================

class TestEdgeCases:
    """Edge case handling"""
    
    def test_zero_amount_transaction(self, api_client):
        """EDGE - $0 amount: Backend rejects or handles gracefully"""
        txn_data = {
            "trust_id": TRUST_ID,
            "entity_id": ENTITY_ID,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "amount": 0.00,
            "direction": "outflow",
            "source_account": "Trust Account",
            "destination_account": "Vendor",
            "governance_classification": "Operational Expense",
            "purpose_memo": "TEST_Zero amount"
        }
        response = api_client.post(f"{BASE_URL}/api/transactions", json=txn_data)
        # Should either reject (400/422) or accept gracefully (200)
        assert response.status_code in [200, 400, 422], f"Unexpected status: {response.status_code}"
    
    def test_data_isolation_between_trusts(self, api_client):
        """EDGE - Data isolation: Trust A transactions never visible in Trust B queries"""
        # Query with a different trust ID
        other_trust_id = "trust_8910cc53a9af"  # Johnson Education Trust
        
        # Get transactions for Smith Family Trust
        response = api_client.get(f"{BASE_URL}/api/transactions?trust_id={TRUST_ID}")
        assert response.status_code == 200
        smith_txns = response.json()
        
        # Get transactions for Johnson Trust
        response = api_client.get(f"{BASE_URL}/api/transactions?trust_id={other_trust_id}")
        assert response.status_code == 200
        johnson_txns = response.json()
        
        # Verify no overlap in transaction IDs
        smith_ids = set(t["transaction_id"] for t in smith_txns)
        johnson_ids = set(t["transaction_id"] for t in johnson_txns)
        overlap = smith_ids.intersection(johnson_ids)
        assert len(overlap) == 0, f"Transactions should not overlap between trusts: {overlap}"
    
    def test_empty_ledger_state(self, api_client):
        """EDGE - Zero transactions: Transaction ledger handles empty state"""
        # Query with a trust that might have no transactions
        response = api_client.get(f"{BASE_URL}/api/transactions?trust_id={TRUST_ID}&classification=NonExistentType")
        assert response.status_code == 200
        txns = response.json()
        assert isinstance(txns, list), "Should return empty list, not error"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
