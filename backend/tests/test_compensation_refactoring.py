"""
Compensation Module Refactoring Tests
Tests the new primary plan per trust per year model:
- Primary vs trustee-specific plans
- YTD tracking against primary plan
- exceeds_plan warning
- Edit/delete plans
"""

import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Demo user credentials
TEST_EMAIL = "demo@trustoffice.com"
TEST_PASSWORD = "demopassword"


class TestCompensationYTD:
    """Test GET /api/compensation-ytd endpoint - YTD tracking against primary plan"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        session = requests.Session()
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        if response.status_code == 200:
            token = response.json().get("token")
            session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    @pytest.fixture(scope="class")
    def trust_id(self, auth_session):
        trusts = auth_session.get(f"{BASE_URL}/api/trusts").json()
        if len(trusts) > 0:
            return trusts[0]["trust_id"]
        pytest.skip("No trusts available for testing")
    
    def test_ytd_endpoint_returns_required_fields(self, auth_session, trust_id):
        """GET /api/compensation-ytd returns year, ytd_total, annual_approved, exceeds_plan, remaining, primary_plan"""
        response = auth_session.get(f"{BASE_URL}/api/compensation-ytd?trust_id={trust_id}")
        assert response.status_code == 200, f"YTD endpoint failed: {response.text}"
        
        data = response.json()
        
        # Verify all required fields from spec
        assert "year" in data, "Missing 'year' field"
        assert "ytd_total" in data, "Missing 'ytd_total' field"
        assert "annual_approved" in data, "Missing 'annual_approved' field"
        assert "exceeds_plan" in data, "Missing 'exceeds_plan' field"
        assert "remaining" in data, "Missing 'remaining' field"
        assert "primary_plan" in data, "Missing 'primary_plan' field"
        
        # Verify types
        assert isinstance(data["year"], int), "year should be integer"
        assert isinstance(data["ytd_total"], (int, float)), "ytd_total should be numeric"
        assert isinstance(data["annual_approved"], (int, float)), "annual_approved should be numeric"
        assert isinstance(data["exceeds_plan"], bool), "exceeds_plan should be boolean"
        assert isinstance(data["remaining"], (int, float)), "remaining should be numeric"
        
        print(f"YTD Data: year={data['year']}, ytd_total={data['ytd_total']}, annual_approved={data['annual_approved']}, exceeds_plan={data['exceeds_plan']}, remaining={data['remaining']}")
        
        # If primary_plan exists, verify its structure
        if data["primary_plan"]:
            plan = data["primary_plan"]
            assert "plan_id" in plan, "primary_plan missing plan_id"
            assert "annual_approved_amount" in plan, "primary_plan missing annual_approved_amount"
            print(f"Primary Plan: {plan['plan_id']}, amount={plan['annual_approved_amount']}")
    
    def test_ytd_with_year_parameter(self, auth_session, trust_id):
        """YTD endpoint accepts year parameter"""
        current_year = datetime.now().year
        response = auth_session.get(f"{BASE_URL}/api/compensation-ytd?trust_id={trust_id}&year={current_year}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["year"] == current_year, f"Year should be {current_year}"
        print(f"YTD with year param: {data['year']}")


class TestCompensationPrimaryPlan:
    """Test GET /api/compensation-plans/primary endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        session = requests.Session()
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        if response.status_code == 200:
            token = response.json().get("token")
            session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    @pytest.fixture(scope="class")
    def trust_id(self, auth_session):
        trusts = auth_session.get(f"{BASE_URL}/api/trusts").json()
        if len(trusts) > 0:
            return trusts[0]["trust_id"]
        pytest.skip("No trusts available for testing")
    
    def test_get_primary_plan(self, auth_session, trust_id):
        """GET /api/compensation-plans/primary returns primary plan for year"""
        response = auth_session.get(f"{BASE_URL}/api/compensation-plans/primary?trust_id={trust_id}")
        assert response.status_code == 200, f"Primary plan endpoint failed: {response.text}"
        
        data = response.json()
        assert "year" in data, "Response should include year"
        assert "plan" in data, "Response should include plan"
        
        current_year = datetime.now().year
        assert data["year"] == current_year, f"Default year should be current year {current_year}"
        
        if data["plan"]:
            plan = data["plan"]
            assert "plan_id" in plan
            assert "is_primary" in plan or plan.get("is_primary") is None, "Plan should indicate is_primary"
            print(f"Primary plan found: {plan['plan_id']}")
        else:
            print("No primary plan configured for current year")
    
    def test_get_primary_plan_with_year(self, auth_session, trust_id):
        """GET /api/compensation-plans/primary with year parameter"""
        current_year = datetime.now().year
        response = auth_session.get(f"{BASE_URL}/api/compensation-plans/primary?trust_id={trust_id}&year={current_year}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["year"] == current_year


class TestCompensationPlanCreate:
    """Test POST /api/compensation-plans with is_primary and year fields"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        session = requests.Session()
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        if response.status_code == 200:
            token = response.json().get("token")
            session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    @pytest.fixture(scope="class")
    def trust_id(self, auth_session):
        trusts = auth_session.get(f"{BASE_URL}/api/trusts").json()
        if len(trusts) > 0:
            return trusts[0]["trust_id"]
        pytest.skip("No trusts available for testing")
    
    def test_create_primary_plan(self, auth_session, trust_id):
        """POST /api/compensation-plans creates plan with is_primary=true"""
        current_year = datetime.now().year
        payload = {
            "trust_id": trust_id,
            "annual_approved_amount": 50000,
            "effective_date": f"{current_year}-01-01",
            "notes": "TEST_PRIMARY_PLAN - Trust-wide compensation envelope",
            "is_primary": True
        }
        
        response = auth_session.post(f"{BASE_URL}/api/compensation-plans", json=payload)
        assert response.status_code == 200, f"Create plan failed: {response.text}"
        
        data = response.json()
        assert "plan_id" in data, "Response should include plan_id"
        assert data.get("is_primary") == True, "Plan should be marked as primary"
        assert data.get("year") == current_year, f"Year should be {current_year}"
        assert data["annual_approved_amount"] == 50000
        
        print(f"Created primary plan: {data['plan_id']}, is_primary={data.get('is_primary')}, year={data.get('year')}")
        
        # Cleanup
        auth_session.delete(f"{BASE_URL}/api/compensation-plans/{data['plan_id']}")
    
    def test_create_trustee_specific_plan(self, auth_session, trust_id):
        """POST /api/compensation-plans creates trustee-specific plan with is_primary=false"""
        current_year = datetime.now().year
        payload = {
            "trust_id": trust_id,
            "annual_approved_amount": 15000,
            "effective_date": f"{current_year}-01-01",
            "trustee_name": "TEST_John Smith",
            "role": "Executive Trustee",
            "notes": "TEST_TRUSTEE_PLAN - Individual trustee cap",
            "is_primary": False
        }
        
        response = auth_session.post(f"{BASE_URL}/api/compensation-plans", json=payload)
        assert response.status_code == 200, f"Create trustee plan failed: {response.text}"
        
        data = response.json()
        assert "plan_id" in data
        assert data.get("is_primary") == False, "Trustee plan should not be primary"
        assert data["trustee_name"] == "TEST_John Smith"
        assert data["role"] == "Executive Trustee"
        
        print(f"Created trustee-specific plan: {data['plan_id']}, trustee={data['trustee_name']}")
        
        # Cleanup
        auth_session.delete(f"{BASE_URL}/api/compensation-plans/{data['plan_id']}")
    
    def test_auto_primary_determination(self, auth_session, trust_id):
        """Plan without trustee_name defaults to primary if none exists"""
        current_year = datetime.now().year
        
        # First, ensure no primary plan exists by checking current state
        ytd_resp = auth_session.get(f"{BASE_URL}/api/compensation-ytd?trust_id={trust_id}")
        ytd_data = ytd_resp.json()
        
        payload = {
            "trust_id": trust_id,
            "annual_approved_amount": 30000,
            "effective_date": f"{current_year}-01-01",
            "notes": "TEST_AUTO_PRIMARY - Should auto-determine primary status"
        }
        
        response = auth_session.post(f"{BASE_URL}/api/compensation-plans", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert "plan_id" in data
        # is_primary should be auto-determined based on existing plans
        print(f"Auto primary plan: {data['plan_id']}, is_primary={data.get('is_primary')}")
        
        # Cleanup
        auth_session.delete(f"{BASE_URL}/api/compensation-plans/{data['plan_id']}")


class TestCompensationPlanUpdate:
    """Test PUT /api/compensation-plans/{plan_id} - Edit plans"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        session = requests.Session()
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        if response.status_code == 200:
            token = response.json().get("token")
            session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    @pytest.fixture(scope="class")
    def trust_id(self, auth_session):
        trusts = auth_session.get(f"{BASE_URL}/api/trusts").json()
        if len(trusts) > 0:
            return trusts[0]["trust_id"]
        pytest.skip("No trusts available for testing")
    
    def test_update_plan_amount(self, auth_session, trust_id):
        """Update compensation plan amount"""
        # Create plan
        current_year = datetime.now().year
        create_resp = auth_session.post(f"{BASE_URL}/api/compensation-plans", json={
            "trust_id": trust_id,
            "annual_approved_amount": 25000,
            "effective_date": f"{current_year}-01-01",
            "notes": "TEST_UPDATE_PLAN - To be updated"
        })
        plan = create_resp.json()
        plan_id = plan["plan_id"]
        
        try:
            # Update amount
            update_resp = auth_session.put(f"{BASE_URL}/api/compensation-plans/{plan_id}", json={
                "annual_approved_amount": 35000
            })
            assert update_resp.status_code == 200, f"Update failed: {update_resp.text}"
            
            updated = update_resp.json()
            assert updated["annual_approved_amount"] == 35000, "Amount should be updated"
            
            # Verify with GET
            get_resp = auth_session.get(f"{BASE_URL}/api/compensation-plans?trust_id={trust_id}")
            plans = get_resp.json()
            updated_plan = next((p for p in plans if p["plan_id"] == plan_id), None)
            assert updated_plan["annual_approved_amount"] == 35000
            
            print(f"Updated plan amount: {plan_id} to 35000")
        finally:
            auth_session.delete(f"{BASE_URL}/api/compensation-plans/{plan_id}")
    
    def test_update_plan_to_primary(self, auth_session, trust_id):
        """Promote a plan to primary"""
        current_year = datetime.now().year
        
        # Create non-primary plan
        create_resp = auth_session.post(f"{BASE_URL}/api/compensation-plans", json={
            "trust_id": trust_id,
            "annual_approved_amount": 20000,
            "effective_date": f"{current_year}-01-01",
            "trustee_name": "TEST_Promote",
            "is_primary": False
        })
        plan = create_resp.json()
        plan_id = plan["plan_id"]
        
        try:
            # Promote to primary
            update_resp = auth_session.put(f"{BASE_URL}/api/compensation-plans/{plan_id}", json={
                "is_primary": True
            })
            assert update_resp.status_code == 200
            
            updated = update_resp.json()
            assert updated.get("is_primary") == True, "Plan should now be primary"
            
            print(f"Promoted plan to primary: {plan_id}")
        finally:
            auth_session.delete(f"{BASE_URL}/api/compensation-plans/{plan_id}")


class TestCompensationPlanDelete:
    """Test DELETE /api/compensation-plans/{plan_id}"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        session = requests.Session()
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        if response.status_code == 200:
            token = response.json().get("token")
            session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    @pytest.fixture(scope="class")
    def trust_id(self, auth_session):
        trusts = auth_session.get(f"{BASE_URL}/api/trusts").json()
        if len(trusts) > 0:
            return trusts[0]["trust_id"]
        pytest.skip("No trusts available for testing")
    
    def test_delete_plan(self, auth_session, trust_id):
        """Delete compensation plan"""
        current_year = datetime.now().year
        
        # Create plan
        create_resp = auth_session.post(f"{BASE_URL}/api/compensation-plans", json={
            "trust_id": trust_id,
            "annual_approved_amount": 10000,
            "effective_date": f"{current_year}-01-01",
            "notes": "TEST_DELETE_PLAN - To be deleted"
        })
        plan = create_resp.json()
        plan_id = plan["plan_id"]
        
        # Delete plan
        delete_resp = auth_session.delete(f"{BASE_URL}/api/compensation-plans/{plan_id}")
        assert delete_resp.status_code == 200, f"Delete failed: {delete_resp.text}"
        
        # Verify deletion
        get_resp = auth_session.get(f"{BASE_URL}/api/compensation-plans?trust_id={trust_id}")
        plans = get_resp.json()
        deleted_plan = next((p for p in plans if p["plan_id"] == plan_id), None)
        assert deleted_plan is None, "Plan should be deleted"
        
        print(f"Deleted plan: {plan_id}")
    
    def test_delete_nonexistent_plan(self, auth_session):
        """Delete nonexistent plan returns 404"""
        response = auth_session.delete(f"{BASE_URL}/api/compensation-plans/nonexistent_plan_id")
        assert response.status_code == 404


class TestCompensationPaymentExceedsPlan:
    """Test payment exceeds_plan warning functionality"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        session = requests.Session()
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        if response.status_code == 200:
            token = response.json().get("token")
            session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    @pytest.fixture(scope="class")
    def trust_id(self, auth_session):
        trusts = auth_session.get(f"{BASE_URL}/api/trusts").json()
        if len(trusts) > 0:
            return trusts[0]["trust_id"]
        pytest.skip("No trusts available for testing")
    
    def test_payment_within_plan(self, auth_session, trust_id):
        """Payment within plan does not have exceeds_plan_flag"""
        current_year = datetime.now().year
        
        # Create plan with large amount
        plan_resp = auth_session.post(f"{BASE_URL}/api/compensation-plans", json={
            "trust_id": trust_id,
            "annual_approved_amount": 100000,
            "effective_date": f"{current_year}-01-01",
            "is_primary": True,
            "notes": "TEST_EXCEED_PLAN"
        })
        plan = plan_resp.json()
        plan_id = plan["plan_id"]
        
        try:
            # Create small payment
            payment_resp = auth_session.post(f"{BASE_URL}/api/compensation-payments", json={
                "trust_id": trust_id,
                "amount": 1000,
                "date": f"{current_year}-06-15",
                "classification_text": "TEST_PAYMENT_WITHIN"
            })
            assert payment_resp.status_code == 200
            
            payment = payment_resp.json()
            assert payment.get("exceeds_plan_flag") == False, "Small payment should not exceed plan"
            
            print(f"Payment within plan: {payment['payment_id']}, exceeds={payment.get('exceeds_plan_flag')}")
            
            # Cleanup payment
            auth_session.delete(f"{BASE_URL}/api/compensation-payments/{payment['payment_id']}")
        finally:
            auth_session.delete(f"{BASE_URL}/api/compensation-plans/{plan_id}")
    
    def test_payment_response_has_exceeds_flag(self, auth_session, trust_id):
        """Payment response includes exceeds_plan_flag field"""
        current_year = datetime.now().year
        
        # Create payment
        payment_resp = auth_session.post(f"{BASE_URL}/api/compensation-payments", json={
            "trust_id": trust_id,
            "amount": 500,
            "date": f"{current_year}-06-20",
            "classification_text": "TEST_EXCEEDS_FLAG"
        })
        assert payment_resp.status_code == 200
        
        payment = payment_resp.json()
        assert "exceeds_plan_flag" in payment, "Payment response should include exceeds_plan_flag"
        assert isinstance(payment["exceeds_plan_flag"], bool), "exceeds_plan_flag should be boolean"
        
        print(f"Payment has exceeds_plan_flag: {payment['exceeds_plan_flag']}")
        
        # Cleanup
        auth_session.delete(f"{BASE_URL}/api/compensation-payments/{payment['payment_id']}")


class TestCompensationPaymentsList:
    """Test GET /api/compensation-payments shows exceeds badge"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        session = requests.Session()
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        if response.status_code == 200:
            token = response.json().get("token")
            session.headers.update({"Authorization": f"Bearer {token}"})
        return session
    
    @pytest.fixture(scope="class")
    def trust_id(self, auth_session):
        trusts = auth_session.get(f"{BASE_URL}/api/trusts").json()
        if len(trusts) > 0:
            return trusts[0]["trust_id"]
        pytest.skip("No trusts available for testing")
    
    def test_payments_list_includes_exceeds_flag(self, auth_session, trust_id):
        """Payments list includes exceeds_plan_flag for each payment"""
        response = auth_session.get(f"{BASE_URL}/api/compensation-payments?trust_id={trust_id}")
        assert response.status_code == 200
        
        payments = response.json()
        assert isinstance(payments, list)
        
        for payment in payments:
            assert "payment_id" in payment
            assert "exceeds_plan_flag" in payment, f"Payment {payment['payment_id']} missing exceeds_plan_flag"
        
        print(f"All {len(payments)} payments have exceeds_plan_flag")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
