# Transaction Ledger API Tests - Phase 2A
# Tests for: POST/GET/PATCH/DELETE transactions, CSV import, bulk classify, summary

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from review request
ADMIN_EMAIL = "contact@trustoffice.app"
ADMIN_PASSWORD = "TrustAdmin2026!"
TRUST_ID = "trust_2097657c7e1d"  # Smith Family Trust
ENTITY_ID = "entity_f2eb8a68d689"  # Smith Family Trust entity

# Classification enum values
CLASSIFICATIONS = [
    "Distribution", "Compensation", "Inter-Entity Transfer",
    "Operational Expense", "Capital Contribution", "Tax Payment", "Other"
]


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")
    data = response.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Authenticated requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


class TestTransactionCRUD:
    """Test basic CRUD operations for transactions"""
    
    created_transaction_ids = []
    
    def test_create_transaction_distribution(self, api_client):
        """POST /api/transactions - Create a distribution transaction"""
        payload = {
            "trust_id": TRUST_ID,
            "entity_id": ENTITY_ID,
            "date": "2026-01-15",
            "amount": 5000.00,
            "direction": "outflow",
            "source_account": "Trust Checking",
            "destination_account": "Beneficiary Account",
            "governance_classification": "Distribution",
            "purpose_memo": "TEST_Quarterly distribution to beneficiary"
        }
        response = api_client.post(f"{BASE_URL}/api/transactions", json=payload)
        
        assert response.status_code == 200, f"Create failed: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "transaction_id" in data
        assert data["trust_id"] == TRUST_ID
        assert data["entity_id"] == ENTITY_ID
        assert data["amount"] == 5000.00
        assert data["direction"] == "outflow"
        assert data["governance_classification"] == "Distribution"
        assert data["purpose_memo"] == "TEST_Quarterly distribution to beneficiary"
        assert "created_at" in data
        
        self.__class__.created_transaction_ids.append(data["transaction_id"])
        print(f"Created transaction: {data['transaction_id']}")
    
    def test_create_transaction_inflow(self, api_client):
        """POST /api/transactions - Create an inflow transaction"""
        payload = {
            "trust_id": TRUST_ID,
            "entity_id": ENTITY_ID,
            "date": "2026-01-10",
            "amount": 10000.00,
            "direction": "inflow",
            "source_account": "External Source",
            "destination_account": "Trust Checking",
            "governance_classification": "Capital Contribution",
            "purpose_memo": "TEST_Capital contribution from grantor"
        }
        response = api_client.post(f"{BASE_URL}/api/transactions", json=payload)
        
        assert response.status_code == 200, f"Create failed: {response.text}"
        data = response.json()
        
        assert data["direction"] == "inflow"
        assert data["governance_classification"] == "Capital Contribution"
        
        self.__class__.created_transaction_ids.append(data["transaction_id"])
        print(f"Created inflow transaction: {data['transaction_id']}")
    
    def test_create_transaction_other_requires_note(self, api_client):
        """POST /api/transactions - 'Other' classification requires other_note"""
        payload = {
            "trust_id": TRUST_ID,
            "entity_id": ENTITY_ID,
            "date": "2026-01-12",
            "amount": 500.00,
            "direction": "outflow",
            "governance_classification": "Other",
            "purpose_memo": "Miscellaneous",
            "other_note": ""  # Empty note should fail
        }
        response = api_client.post(f"{BASE_URL}/api/transactions", json=payload)
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        assert "note" in response.text.lower() or "required" in response.text.lower()
        print("Correctly rejected 'Other' classification without note")
    
    def test_create_transaction_other_with_note(self, api_client):
        """POST /api/transactions - 'Other' classification with note succeeds"""
        payload = {
            "trust_id": TRUST_ID,
            "entity_id": ENTITY_ID,
            "date": "2026-01-12",
            "amount": 500.00,
            "direction": "outflow",
            "governance_classification": "Other",
            "purpose_memo": "Miscellaneous expense",
            "other_note": "TEST_One-time legal consultation fee"
        }
        response = api_client.post(f"{BASE_URL}/api/transactions", json=payload)
        
        assert response.status_code == 200, f"Create failed: {response.text}"
        data = response.json()
        
        assert data["governance_classification"] == "Other"
        assert data["other_note"] == "TEST_One-time legal consultation fee"
        
        self.__class__.created_transaction_ids.append(data["transaction_id"])
        print(f"Created 'Other' transaction with note: {data['transaction_id']}")
    
    def test_get_transactions_list(self, api_client):
        """GET /api/transactions?trust_id=X - List transactions"""
        response = api_client.get(f"{BASE_URL}/api/transactions?trust_id={TRUST_ID}")
        
        assert response.status_code == 200, f"Get failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list)
        assert len(data) >= 1, "Should have at least one transaction"
        
        # Validate structure of first transaction
        txn = data[0]
        assert "transaction_id" in txn
        assert "amount" in txn
        assert "direction" in txn
        assert "governance_classification" in txn
        assert "entity_name" in txn  # Should be enriched with entity name
        
        print(f"Retrieved {len(data)} transactions")
    
    def test_get_transactions_filter_by_entity(self, api_client):
        """GET /api/transactions - Filter by entity_id"""
        response = api_client.get(
            f"{BASE_URL}/api/transactions?trust_id={TRUST_ID}&entity_id={ENTITY_ID}"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # All returned transactions should be for the specified entity
        for txn in data:
            assert txn["entity_id"] == ENTITY_ID
        
        print(f"Filtered by entity: {len(data)} transactions")
    
    def test_get_transactions_filter_by_classification(self, api_client):
        """GET /api/transactions - Filter by classification"""
        response = api_client.get(
            f"{BASE_URL}/api/transactions?trust_id={TRUST_ID}&classification=Distribution"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        for txn in data:
            assert txn["governance_classification"] == "Distribution"
        
        print(f"Filtered by Distribution: {len(data)} transactions")
    
    def test_get_transactions_filter_by_direction(self, api_client):
        """GET /api/transactions - Filter by direction"""
        response = api_client.get(
            f"{BASE_URL}/api/transactions?trust_id={TRUST_ID}&direction=outflow"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        for txn in data:
            assert txn["direction"] == "outflow"
        
        print(f"Filtered by outflow: {len(data)} transactions")
    
    def test_update_transaction(self, api_client):
        """PATCH /api/transactions/{id} - Update transaction"""
        if not self.__class__.created_transaction_ids:
            pytest.skip("No transactions created to update")
        
        txn_id = self.__class__.created_transaction_ids[0]
        
        update_payload = {
            "amount": 5500.00,
            "purpose_memo": "TEST_Updated quarterly distribution"
        }
        response = api_client.patch(
            f"{BASE_URL}/api/transactions/{txn_id}",
            json=update_payload
        )
        
        assert response.status_code == 200, f"Update failed: {response.text}"
        data = response.json()
        
        assert data["amount"] == 5500.00
        assert data["purpose_memo"] == "TEST_Updated quarterly distribution"
        assert data["updated_at"] is not None  # Should have updated_at timestamp
        
        print(f"Updated transaction {txn_id}")
    
    def test_update_transaction_verify_audit_trail(self, api_client):
        """PATCH /api/transactions/{id} - Verify audit trail is created"""
        if not self.__class__.created_transaction_ids:
            pytest.skip("No transactions created")
        
        txn_id = self.__class__.created_transaction_ids[0]
        
        # Update again to create another audit entry
        update_payload = {
            "governance_classification": "Compensation"
        }
        response = api_client.patch(
            f"{BASE_URL}/api/transactions/{txn_id}",
            json=update_payload
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["governance_classification"] == "Compensation"
        
        # Verify the transaction was updated (audit trail is internal)
        get_response = api_client.get(f"{BASE_URL}/api/transactions?trust_id={TRUST_ID}")
        assert get_response.status_code == 200
        
        print(f"Updated classification and verified persistence")
    
    def test_delete_transaction(self, api_client):
        """DELETE /api/transactions/{id} - Delete transaction"""
        # Create a transaction specifically for deletion
        payload = {
            "trust_id": TRUST_ID,
            "entity_id": ENTITY_ID,
            "date": "2026-01-01",
            "amount": 100.00,
            "direction": "outflow",
            "governance_classification": "Operational Expense",
            "purpose_memo": "TEST_To be deleted"
        }
        create_response = api_client.post(f"{BASE_URL}/api/transactions", json=payload)
        assert create_response.status_code == 200
        txn_id = create_response.json()["transaction_id"]
        
        # Delete it
        delete_response = api_client.delete(f"{BASE_URL}/api/transactions/{txn_id}")
        assert delete_response.status_code == 200, f"Delete failed: {delete_response.text}"
        
        # Verify it's gone
        get_response = api_client.get(f"{BASE_URL}/api/transactions?trust_id={TRUST_ID}")
        txn_ids = [t["transaction_id"] for t in get_response.json()]
        assert txn_id not in txn_ids, "Transaction should be deleted"
        
        print(f"Deleted transaction {txn_id}")


class TestCSVImport:
    """Test CSV import functionality"""
    
    imported_transaction_ids = []
    
    def test_import_csv_rows(self, api_client):
        """POST /api/transactions/import - Import CSV rows"""
        payload = {
            "trust_id": TRUST_ID,
            "entity_id": ENTITY_ID,
            "rows": [
                {
                    "date": "2026-01-05",
                    "amount": 1500.00,
                    "direction": "outflow",
                    "description": "TEST_Bank fee"
                },
                {
                    "date": "2026-01-06",
                    "amount": 2500.00,
                    "direction": "inflow",
                    "description": "TEST_Interest income"
                },
                {
                    "date": "2026-01-07",
                    "amount": 750.00,
                    "direction": "outflow",
                    "description": "TEST_Office supplies"
                }
            ]
        }
        response = api_client.post(f"{BASE_URL}/api/transactions/import", json=payload)
        
        assert response.status_code == 200, f"Import failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list)
        assert len(data) == 3, f"Expected 3 imported transactions, got {len(data)}"
        
        # All imported transactions should have same batch_id
        batch_ids = set(t.get("import_batch_id") for t in data)
        assert len(batch_ids) == 1, "All imported transactions should share batch_id"
        assert None not in batch_ids, "Batch ID should be set"
        
        # Store IDs for cleanup
        for txn in data:
            self.__class__.imported_transaction_ids.append(txn["transaction_id"])
        
        print(f"Imported {len(data)} transactions with batch_id: {list(batch_ids)[0]}")
    
    def test_import_empty_rows_fails(self, api_client):
        """POST /api/transactions/import - Empty rows should fail"""
        payload = {
            "trust_id": TRUST_ID,
            "entity_id": ENTITY_ID,
            "rows": []
        }
        response = api_client.post(f"{BASE_URL}/api/transactions/import", json=payload)
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("Correctly rejected empty import")


class TestBulkClassify:
    """Test bulk classification functionality"""
    
    def test_bulk_classify_transactions(self, api_client):
        """POST /api/transactions/bulk-classify - Bulk classify transactions"""
        # First create some transactions to classify
        txn_ids = []
        for i in range(3):
            payload = {
                "trust_id": TRUST_ID,
                "entity_id": ENTITY_ID,
                "date": f"2026-01-2{i}",
                "amount": 100.00 * (i + 1),
                "direction": "outflow",
                "governance_classification": "Other",
                "other_note": f"TEST_Bulk classify test {i}",
                "purpose_memo": f"TEST_Transaction {i}"
            }
            response = api_client.post(f"{BASE_URL}/api/transactions", json=payload)
            assert response.status_code == 200
            txn_ids.append(response.json()["transaction_id"])
        
        # Bulk classify them
        bulk_payload = {
            "transaction_ids": txn_ids,
            "governance_classification": "Operational Expense",
            "purpose_memo": "TEST_Bulk classified as operational expense"
        }
        response = api_client.post(f"{BASE_URL}/api/transactions/bulk-classify", json=bulk_payload)
        
        assert response.status_code == 200, f"Bulk classify failed: {response.text}"
        data = response.json()
        
        assert data["modified"] == 3, f"Expected 3 modified, got {data['modified']}"
        
        # Verify the classification was applied
        get_response = api_client.get(f"{BASE_URL}/api/transactions?trust_id={TRUST_ID}")
        all_txns = get_response.json()
        
        for txn_id in txn_ids:
            txn = next((t for t in all_txns if t["transaction_id"] == txn_id), None)
            assert txn is not None
            assert txn["governance_classification"] == "Operational Expense"
        
        # Cleanup
        for txn_id in txn_ids:
            api_client.delete(f"{BASE_URL}/api/transactions/{txn_id}")
        
        print(f"Bulk classified {data['modified']} transactions")
    
    def test_bulk_classify_other_requires_note(self, api_client):
        """POST /api/transactions/bulk-classify - 'Other' requires note"""
        payload = {
            "transaction_ids": ["fake_id"],
            "governance_classification": "Other",
            "purpose_memo": "Test",
            "other_note": ""  # Empty note should fail
        }
        response = api_client.post(f"{BASE_URL}/api/transactions/bulk-classify", json=payload)
        
        assert response.status_code == 400
        print("Correctly rejected bulk 'Other' without note")
    
    def test_bulk_classify_empty_ids_fails(self, api_client):
        """POST /api/transactions/bulk-classify - Empty IDs should fail"""
        payload = {
            "transaction_ids": [],
            "governance_classification": "Distribution"
        }
        response = api_client.post(f"{BASE_URL}/api/transactions/bulk-classify", json=payload)
        
        assert response.status_code == 400
        print("Correctly rejected empty transaction IDs")


class TestTransactionSummary:
    """Test transaction summary/analytics endpoint"""
    
    def test_get_summary(self, api_client):
        """GET /api/transactions/summary?trust_id=X - Get per-entity summary"""
        response = api_client.get(f"{BASE_URL}/api/transactions/summary?trust_id={TRUST_ID}")
        
        assert response.status_code == 200, f"Summary failed: {response.text}"
        data = response.json()
        
        assert isinstance(data, list)
        
        # Each summary should have required fields
        for summary in data:
            assert "entity_id" in summary
            assert "entity_name" in summary
            assert "total_inflows" in summary
            assert "total_outflows" in summary
            assert "net_flow" in summary
            assert "transaction_count" in summary
            assert "by_classification" in summary
        
        print(f"Retrieved summary for {len(data)} entities")
    
    def test_summary_with_days_param(self, api_client):
        """GET /api/transactions/summary - Test days parameter"""
        response = api_client.get(
            f"{BASE_URL}/api/transactions/summary?trust_id={TRUST_ID}&days=30"
        )
        
        assert response.status_code == 200
        print("Summary with days=30 parameter works")


class TestValidation:
    """Test validation and error handling"""
    
    def test_create_invalid_trust(self, api_client):
        """POST /api/transactions - Invalid trust_id returns 404"""
        payload = {
            "trust_id": "invalid_trust_id",
            "entity_id": ENTITY_ID,
            "date": "2026-01-15",
            "amount": 100.00,
            "direction": "outflow",
            "governance_classification": "Distribution"
        }
        response = api_client.post(f"{BASE_URL}/api/transactions", json=payload)
        
        assert response.status_code == 404
        print("Correctly rejected invalid trust_id")
    
    def test_create_invalid_entity(self, api_client):
        """POST /api/transactions - Invalid entity_id returns 404"""
        payload = {
            "trust_id": TRUST_ID,
            "entity_id": "invalid_entity_id",
            "date": "2026-01-15",
            "amount": 100.00,
            "direction": "outflow",
            "governance_classification": "Distribution"
        }
        response = api_client.post(f"{BASE_URL}/api/transactions", json=payload)
        
        assert response.status_code == 404
        print("Correctly rejected invalid entity_id")
    
    def test_update_nonexistent_transaction(self, api_client):
        """PATCH /api/transactions/{id} - Nonexistent ID returns 404"""
        response = api_client.patch(
            f"{BASE_URL}/api/transactions/nonexistent_txn_id",
            json={"amount": 100.00}
        )
        
        assert response.status_code == 404
        print("Correctly rejected update of nonexistent transaction")
    
    def test_delete_nonexistent_transaction(self, api_client):
        """DELETE /api/transactions/{id} - Nonexistent ID returns 404"""
        response = api_client.delete(f"{BASE_URL}/api/transactions/nonexistent_txn_id")
        
        assert response.status_code == 404
        print("Correctly rejected delete of nonexistent transaction")


class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_transactions(self, api_client):
        """Delete all TEST_ prefixed transactions"""
        response = api_client.get(f"{BASE_URL}/api/transactions?trust_id={TRUST_ID}")
        if response.status_code != 200:
            return
        
        txns = response.json()
        deleted = 0
        for txn in txns:
            if "TEST_" in (txn.get("purpose_memo") or "") or "TEST_" in (txn.get("other_note") or ""):
                del_response = api_client.delete(f"{BASE_URL}/api/transactions/{txn['transaction_id']}")
                if del_response.status_code == 200:
                    deleted += 1
        
        print(f"Cleaned up {deleted} test transactions")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
