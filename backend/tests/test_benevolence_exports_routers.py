"""
Backend tests for Benevolence and Exports router migrations (P1)
Tests migrated endpoints from server.py to router modules:
- /app/backend/routers/benevolence.py - Benevolence CRUD and PDF export
- /app/backend/routers/exports.py - CSV export endpoints (Premium feature)
"""
import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')

# Test credentials
DEMO_EMAIL = "demo@trustoffice.com"
DEMO_PASSWORD = "demopassword"
TRUST_ID = "trust_b753cb8fe07f"  # Trust with benevolence_enabled=true


@pytest.fixture(scope="module")
def auth_token():
    """Login and get auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": DEMO_EMAIL,
        "password": DEMO_PASSWORD
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Auth headers for API calls"""
    return {"Authorization": f"Bearer {auth_token}"}


# ==================== BENEVOLENCE ROUTER TESTS ====================

class TestBenevolenceRouter:
    """Tests for /api/benevolence endpoints migrated to benevolence.py"""
    
    def test_get_benevolence_requires_auth(self):
        """GET /api/benevolence requires authentication"""
        response = requests.get(f"{BASE_URL}/api/benevolence?trust_id={TRUST_ID}")
        assert response.status_code == 401
        print("✓ GET /api/benevolence returns 401 without auth")
    
    def test_get_benevolence_returns_list(self, auth_headers):
        """GET /api/benevolence returns list of records"""
        response = requests.get(
            f"{BASE_URL}/api/benevolence?trust_id={TRUST_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/benevolence returns list ({len(data)} records)")
    
    def test_create_benevolence_record(self, auth_headers):
        """POST /api/benevolence creates a new record"""
        payload = {
            "trust_id": TRUST_ID,
            "beneficiary_name": "TEST_BenevolenceRecipient",
            "beneficiary_type": "individual",
            "purpose": "medical",
            "purpose_description": "Medical expense assistance",
            "amount": 500.00,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "approved_by": ["John Trustee", "Jane Trustee"],
            "approval_method": "unanimous",
            "notes": "Test benevolence record",
            "status": "approved"
        }
        response = requests.post(
            f"{BASE_URL}/api/benevolence",
            headers=auth_headers,
            json=payload
        )
        assert response.status_code == 200, f"Create failed: {response.text}"
        data = response.json()
        assert "record_id" in data
        assert data["beneficiary_name"] == "TEST_BenevolenceRecipient"
        assert data["purpose"] == "medical"
        assert data["amount"] == 500.00
        print(f"✓ POST /api/benevolence creates record: {data['record_id']}")
        return data["record_id"]
    
    def test_create_and_get_benevolence_record(self, auth_headers):
        """Create then GET verifies persistence"""
        # Create
        payload = {
            "trust_id": TRUST_ID,
            "beneficiary_name": "TEST_PersistenceTest",
            "beneficiary_type": "family",
            "purpose": "housing",
            "purpose_description": "Housing assistance for family",
            "amount": 1000.00,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "approved_by": ["Trustee A"],
            "approval_method": "single_trustee",
            "notes": "Persistence test",
            "status": "approved"
        }
        create_resp = requests.post(
            f"{BASE_URL}/api/benevolence",
            headers=auth_headers,
            json=payload
        )
        assert create_resp.status_code == 200
        record_id = create_resp.json()["record_id"]
        
        # GET to verify persistence
        get_resp = requests.get(
            f"{BASE_URL}/api/benevolence/{record_id}",
            headers=auth_headers
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["record_id"] == record_id
        assert data["beneficiary_name"] == "TEST_PersistenceTest"
        assert data["amount"] == 1000.00
        print(f"✓ Create->GET verifies persistence for record: {record_id}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/benevolence/{record_id}", headers=auth_headers)
    
    def test_update_benevolence_record(self, auth_headers):
        """PUT /api/benevolence/{record_id} updates a record"""
        # First create a record
        payload = {
            "trust_id": TRUST_ID,
            "beneficiary_name": "TEST_UpdateTest",
            "beneficiary_type": "individual",
            "purpose": "education",
            "purpose_description": "Educational support",
            "amount": 250.00,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "approved_by": ["Trustee"],
            "approval_method": "unanimous",
            "notes": "To be updated",
            "status": "pending"
        }
        create_resp = requests.post(
            f"{BASE_URL}/api/benevolence",
            headers=auth_headers,
            json=payload
        )
        assert create_resp.status_code == 200
        record_id = create_resp.json()["record_id"]
        
        # Update the record
        update_payload = {
            "amount": 300.00,
            "notes": "Updated notes",
            "status": "approved"
        }
        update_resp = requests.put(
            f"{BASE_URL}/api/benevolence/{record_id}",
            headers=auth_headers,
            json=update_payload
        )
        assert update_resp.status_code == 200
        updated = update_resp.json()
        assert updated["amount"] == 300.00
        assert updated["notes"] == "Updated notes"
        assert updated["status"] == "approved"
        assert updated["updated_at"] is not None
        print(f"✓ PUT /api/benevolence/{record_id} updates correctly")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/benevolence/{record_id}", headers=auth_headers)
    
    def test_delete_benevolence_record(self, auth_headers):
        """DELETE /api/benevolence/{record_id} removes a record"""
        # Create a record to delete
        payload = {
            "trust_id": TRUST_ID,
            "beneficiary_name": "TEST_ToDelete",
            "beneficiary_type": "individual",
            "purpose": "emergency",
            "purpose_description": "Emergency assistance",
            "amount": 100.00,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "approved_by": ["Trustee"],
            "approval_method": "unanimous",
            "notes": "Will be deleted",
            "status": "approved"
        }
        create_resp = requests.post(
            f"{BASE_URL}/api/benevolence",
            headers=auth_headers,
            json=payload
        )
        assert create_resp.status_code == 200
        record_id = create_resp.json()["record_id"]
        
        # Delete the record
        delete_resp = requests.delete(
            f"{BASE_URL}/api/benevolence/{record_id}",
            headers=auth_headers
        )
        assert delete_resp.status_code == 200
        
        # Verify deletion
        get_resp = requests.get(
            f"{BASE_URL}/api/benevolence/{record_id}",
            headers=auth_headers
        )
        assert get_resp.status_code == 404
        print(f"✓ DELETE /api/benevolence/{record_id} removes record successfully")
    
    def test_delete_benevolence_not_found(self, auth_headers):
        """DELETE /api/benevolence/{record_id} returns 404 for invalid ID"""
        response = requests.delete(
            f"{BASE_URL}/api/benevolence/ben_invalid12345",
            headers=auth_headers
        )
        assert response.status_code == 404
        print("✓ DELETE /api/benevolence returns 404 for invalid ID")
    
    def test_get_benevolence_with_filters(self, auth_headers):
        """GET /api/benevolence with query filters"""
        # Test with purpose filter
        response = requests.get(
            f"{BASE_URL}/api/benevolence?trust_id={TRUST_ID}&purpose=medical",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        # All records should have medical purpose if any returned
        for record in data:
            assert record.get("purpose") == "medical"
        print(f"✓ GET /api/benevolence with purpose filter works ({len(data)} records)")
    
    def test_get_benevolence_summary(self, auth_headers):
        """GET /api/benevolence/summary/{trust_id} returns aggregated data"""
        response = requests.get(
            f"{BASE_URL}/api/benevolence/summary/{TRUST_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        # Verify summary structure
        assert "trust_id" in data
        assert "trust_name" in data
        assert "total_amount" in data
        assert "total_count" in data
        assert "by_purpose" in data
        assert "by_month" in data
        assert "by_quarter" in data
        assert "by_year" in data
        assert "approvers" in data
        print(f"✓ GET /api/benevolence/summary/{TRUST_ID} returns summary: total=${data['total_amount']:.2f}, count={data['total_count']}")
    
    def test_get_benevolence_summary_invalid_trust(self, auth_headers):
        """GET /api/benevolence/summary/{trust_id} returns 404 for invalid trust"""
        response = requests.get(
            f"{BASE_URL}/api/benevolence/summary/trust_invalid123",
            headers=auth_headers
        )
        assert response.status_code == 404
        print("✓ GET /api/benevolence/summary returns 404 for invalid trust")
    
    def test_create_benevolence_invalid_trust(self, auth_headers):
        """POST /api/benevolence returns 404 for invalid trust"""
        payload = {
            "trust_id": "trust_invalid123",
            "beneficiary_name": "Test",
            "beneficiary_type": "individual",
            "purpose": "medical",
            "purpose_description": "Test",
            "amount": 100.00,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "approved_by": ["Trustee"],
            "approval_method": "unanimous",
            "notes": "",
            "status": "approved"
        }
        response = requests.post(
            f"{BASE_URL}/api/benevolence",
            headers=auth_headers,
            json=payload
        )
        assert response.status_code == 404
        print("✓ POST /api/benevolence returns 404 for invalid trust")


# ==================== BENEVOLENCE PDF EXPORT TESTS ====================

class TestBenevolencePDFExport:
    """Tests for /api/benevolence/export/{trust_id}/pdf endpoint"""
    
    def test_benevolence_pdf_export_requires_auth(self):
        """GET /api/benevolence/export/{trust_id}/pdf requires authentication"""
        response = requests.get(f"{BASE_URL}/api/benevolence/export/{TRUST_ID}/pdf")
        assert response.status_code == 401
        print("✓ Benevolence PDF export requires auth")
    
    def test_benevolence_pdf_export_returns_pdf(self, auth_headers):
        """GET /api/benevolence/export/{trust_id}/pdf returns PDF document"""
        response = requests.get(
            f"{BASE_URL}/api/benevolence/export/{TRUST_ID}/pdf",
            headers=auth_headers
        )
        assert response.status_code == 200
        assert response.headers.get("content-type") == "application/pdf"
        assert "Content-Disposition" in response.headers
        assert "benevolence_report" in response.headers.get("Content-Disposition", "")
        print("✓ Benevolence PDF export returns valid PDF")
    
    def test_benevolence_pdf_export_with_year_filter(self, auth_headers):
        """GET /api/benevolence/export/{trust_id}/pdf?year=2024 filters by year"""
        response = requests.get(
            f"{BASE_URL}/api/benevolence/export/{TRUST_ID}/pdf?year=2024",
            headers=auth_headers
        )
        assert response.status_code == 200
        assert response.headers.get("content-type") == "application/pdf"
        print("✓ Benevolence PDF export with year filter works")
    
    def test_benevolence_pdf_export_invalid_trust(self, auth_headers):
        """GET /api/benevolence/export/{trust_id}/pdf returns 404 for invalid trust"""
        response = requests.get(
            f"{BASE_URL}/api/benevolence/export/trust_invalid123/pdf",
            headers=auth_headers
        )
        assert response.status_code == 404
        print("✓ Benevolence PDF export returns 404 for invalid trust")


# ==================== EXPORTS ROUTER TESTS (CSV - Premium Feature) ====================

class TestExportsRouter:
    """
    Tests for /api/export/* endpoints migrated to exports.py
    These endpoints require CSV_EXPORT premium feature (paid subscription)
    Trial users should get 402 Payment Required
    """
    
    def test_export_minutes_requires_auth(self):
        """GET /api/export/minutes requires authentication"""
        response = requests.get(f"{BASE_URL}/api/export/minutes")
        assert response.status_code == 401
        print("✓ GET /api/export/minutes requires auth")
    
    def test_export_minutes_premium_feature(self, auth_headers):
        """GET /api/export/minutes requires premium subscription"""
        response = requests.get(
            f"{BASE_URL}/api/export/minutes",
            headers=auth_headers
        )
        # Trial users get 402, paid users get 200 with CSV
        if response.status_code == 402:
            # Expected for trial users
            assert "feature" in response.text.lower() or "subscription" in response.text.lower()
            print("✓ GET /api/export/minutes returns 402 for trial users (expected)")
        elif response.status_code == 200:
            # Paid user gets CSV
            assert response.headers.get("content-type") == "text/csv"
            print("✓ GET /api/export/minutes returns CSV for paid users")
        else:
            pytest.fail(f"Unexpected status code: {response.status_code}")
    
    def test_export_distributions_requires_auth(self):
        """GET /api/export/distributions requires authentication"""
        response = requests.get(f"{BASE_URL}/api/export/distributions")
        assert response.status_code == 401
        print("✓ GET /api/export/distributions requires auth")
    
    def test_export_distributions_premium_feature(self, auth_headers):
        """GET /api/export/distributions requires premium subscription"""
        response = requests.get(
            f"{BASE_URL}/api/export/distributions",
            headers=auth_headers
        )
        # Trial users get 402, paid users get 200 with CSV
        if response.status_code == 402:
            print("✓ GET /api/export/distributions returns 402 for trial users (expected)")
        elif response.status_code == 200:
            assert response.headers.get("content-type") == "text/csv"
            print("✓ GET /api/export/distributions returns CSV for paid users")
        else:
            pytest.fail(f"Unexpected status code: {response.status_code}")
    
    def test_export_compensation_requires_auth(self):
        """GET /api/export/compensation requires authentication"""
        response = requests.get(f"{BASE_URL}/api/export/compensation")
        assert response.status_code == 401
        print("✓ GET /api/export/compensation requires auth")
    
    def test_export_compensation_premium_feature(self, auth_headers):
        """GET /api/export/compensation requires premium subscription"""
        response = requests.get(
            f"{BASE_URL}/api/export/compensation",
            headers=auth_headers
        )
        # Trial users get 402, paid users get 200 with CSV
        if response.status_code == 402:
            print("✓ GET /api/export/compensation returns 402 for trial users (expected)")
        elif response.status_code == 200:
            assert response.headers.get("content-type") == "text/csv"
            print("✓ GET /api/export/compensation returns CSV for paid users")
        else:
            pytest.fail(f"Unexpected status code: {response.status_code}")
    
    def test_export_tasks_requires_auth(self):
        """GET /api/export/tasks requires authentication"""
        response = requests.get(f"{BASE_URL}/api/export/tasks")
        assert response.status_code == 401
        print("✓ GET /api/export/tasks requires auth")
    
    def test_export_tasks_premium_feature(self, auth_headers):
        """GET /api/export/tasks requires premium subscription"""
        response = requests.get(
            f"{BASE_URL}/api/export/tasks",
            headers=auth_headers
        )
        # Trial users get 402, paid users get 200 with CSV
        if response.status_code == 402:
            print("✓ GET /api/export/tasks returns 402 for trial users (expected)")
        elif response.status_code == 200:
            assert response.headers.get("content-type") == "text/csv"
            print("✓ GET /api/export/tasks returns CSV for paid users")
        else:
            pytest.fail(f"Unexpected status code: {response.status_code}")
    
    def test_export_with_trust_filter(self, auth_headers):
        """CSV exports accept optional trust_id filter"""
        response = requests.get(
            f"{BASE_URL}/api/export/minutes?trust_id={TRUST_ID}",
            headers=auth_headers
        )
        # Either 402 (trial) or 200 (paid) is acceptable
        assert response.status_code in [200, 402]
        print(f"✓ Export with trust_id filter returns {response.status_code}")


# ==================== PREVIOUSLY MIGRATED ROUTERS - REGRESSION TESTS ====================

class TestPreviouslyMigratedRouters:
    """Regression tests for Schedule A, Compensation, and Subscriptions routers"""
    
    def test_schedule_a_list_still_works(self, auth_headers):
        """GET /api/schedule-a still returns list"""
        response = requests.get(
            f"{BASE_URL}/api/schedule-a?trust_id={TRUST_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        print(f"✓ Schedule A list endpoint works ({len(response.json())} items)")
    
    def test_schedule_a_summary_still_works(self, auth_headers):
        """GET /api/schedule-a/summary/{trust_id} still returns summary"""
        response = requests.get(
            f"{BASE_URL}/api/schedule-a/summary/{TRUST_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_value" in data
        assert "categories" in data
        print(f"✓ Schedule A summary endpoint works (total=${data['total_value']:,.2f})")
    
    def test_compensation_plans_still_works(self, auth_headers):
        """GET /api/compensation-plans still returns list"""
        response = requests.get(
            f"{BASE_URL}/api/compensation-plans?trust_id={TRUST_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        print(f"✓ Compensation plans endpoint works ({len(response.json())} plans)")
    
    def test_compensation_payments_still_works(self, auth_headers):
        """GET /api/compensation-payments still returns list"""
        response = requests.get(
            f"{BASE_URL}/api/compensation-payments?trust_id={TRUST_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        print(f"✓ Compensation payments endpoint works ({len(response.json())} payments)")
    
    def test_compensation_ytd_still_works(self, auth_headers):
        """GET /api/compensation-ytd still returns YTD totals"""
        response = requests.get(
            f"{BASE_URL}/api/compensation-ytd?trust_id={TRUST_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "ytd_total" in data  # Fixed: field name is ytd_total not ytd_paid
        print(f"✓ Compensation YTD endpoint works (ytd=${data['ytd_total']:,.2f})")
    
    def test_subscription_state_still_works(self, auth_headers):
        """GET /api/subscription/state still returns subscription state"""
        response = requests.get(
            f"{BASE_URL}/api/subscription/state",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "plan_type" in data
        assert "status" in data
        assert "is_active" in data
        print(f"✓ Subscription state endpoint works (plan={data['plan_type']}, status={data['status']})")
    
    def test_subscription_features_still_works(self, auth_headers):
        """GET /api/subscription/features still returns feature flags"""
        response = requests.get(
            f"{BASE_URL}/api/subscription/features",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "features" in data
        assert "csv_export" in data["features"]
        print(f"✓ Subscription features endpoint works (csv_export={data['features']['csv_export']})")


# ==================== ROUTER INTEGRATION TESTS ====================

class TestRouterIntegration:
    """Integration tests to verify all routers are properly mounted"""
    
    def test_all_migrated_routers_respond(self, auth_headers):
        """All migrated router endpoints are accessible"""
        endpoints = [
            ("/api/benevolence", f"?trust_id={TRUST_ID}"),
            (f"/api/benevolence/summary/{TRUST_ID}", ""),
            ("/api/export/minutes", ""),
            ("/api/export/distributions", ""),
            ("/api/export/compensation", ""),
            ("/api/export/tasks", ""),
            ("/api/schedule-a", f"?trust_id={TRUST_ID}"),
            ("/api/compensation-plans", f"?trust_id={TRUST_ID}"),
            ("/api/compensation-payments", f"?trust_id={TRUST_ID}"),
            ("/api/subscription/state", ""),
            ("/api/subscription/features", ""),
        ]
        
        results = []
        for endpoint, params in endpoints:
            url = f"{BASE_URL}{endpoint}{params}"
            response = requests.get(url, headers=auth_headers)
            # All endpoints should return 200, 402 (premium feature), or valid response
            is_ok = response.status_code in [200, 402]
            results.append((endpoint, response.status_code, is_ok))
            print(f"  {endpoint}: {response.status_code} {'✓' if is_ok else '✗'}")
        
        # All should be accessible (200 or 402)
        all_ok = all(r[2] for r in results)
        assert all_ok, f"Some endpoints failed: {[r for r in results if not r[2]]}"
        print(f"✓ All {len(endpoints)} migrated endpoints are accessible")
    
    def test_router_includes_correct_prefix(self, auth_headers):
        """Routers are included with /api prefix"""
        # Test a few endpoints that would fail without /api prefix
        endpoints_to_test = [
            "/api/benevolence",
            "/api/export/minutes",
            "/api/schedule-a",
        ]
        for endpoint in endpoints_to_test:
            response = requests.get(
                f"{BASE_URL}{endpoint}?trust_id={TRUST_ID}",
                headers=auth_headers
            )
            # Should not get 404 (would mean router not mounted correctly)
            assert response.status_code != 404, f"{endpoint} returned 404 - router not mounted?"
        print("✓ All routers mounted with /api prefix")


# ==================== CLEANUP ====================

@pytest.fixture(scope="module", autouse=True)
def cleanup_test_data(auth_headers):
    """Cleanup TEST_ prefixed benevolence records after tests"""
    yield
    # Cleanup after all tests
    try:
        response = requests.get(
            f"{BASE_URL}/api/benevolence?trust_id={TRUST_ID}",
            headers=auth_headers
        )
        if response.status_code == 200:
            for record in response.json():
                if record.get("beneficiary_name", "").startswith("TEST_"):
                    requests.delete(
                        f"{BASE_URL}/api/benevolence/{record['record_id']}",
                        headers=auth_headers
                    )
            print("✓ Cleaned up TEST_ prefixed benevolence records")
    except Exception as e:
        print(f"Warning: Cleanup failed: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
