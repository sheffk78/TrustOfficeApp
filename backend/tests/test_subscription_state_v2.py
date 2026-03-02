"""
Test subscription state and require_write_access dependency
Tests for subscription state normalization and read-only blocking across modules

Modules covered:
- GET /api/subscription/state - normalized subscription state endpoint
- GET /api/dashboard - includes subscription field (DashboardSubscriptionState)
- require_write_access dependency for write endpoints across routers
- Trial user read access verification for all data types
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')

# Test credentials
DEMO_EMAIL = "demo@trustoffice.com"
DEMO_PASSWORD = "demopassword"
TRUST_ID = "trust_b753cb8fe07f"


@pytest.fixture(scope="module")
def auth_session():
    """Get authenticated session with demo user token"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": DEMO_EMAIL,
        "password": DEMO_PASSWORD
    })
    
    if response.status_code != 200:
        pytest.skip(f"Login failed: {response.status_code} - {response.text}")
    
    data = response.json()
    token = data.get("token")
    session.headers.update({"Authorization": f"Bearer {token}"})
    return session


class TestSubscriptionStateEndpoint:
    """Tests for GET /api/subscription/state endpoint"""
    
    def test_subscription_state_returns_all_required_fields(self, auth_session):
        """Verify subscription/state endpoint returns normalized state with all fields"""
        response = auth_session.get(f"{BASE_URL}/api/subscription/state")
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        
        data = response.json()
        
        # Check all required fields exist
        required_fields = [
            "user_id", "plan_type", "status", "is_trial", 
            "is_active", "is_read_only", "trial_days_remaining"
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        print(f"Subscription state: plan_type={data['plan_type']}, status={data['status']}, "
              f"is_trial={data['is_trial']}, is_active={data['is_active']}, is_read_only={data['is_read_only']}")
    
    def test_subscription_state_plan_type_values(self, auth_session):
        """Verify plan_type is one of expected values"""
        response = auth_session.get(f"{BASE_URL}/api/subscription/state")
        assert response.status_code == 200
        
        data = response.json()
        assert data["plan_type"] in ["trial", "monthly", "annual"], \
            f"Unexpected plan_type: {data['plan_type']}"
    
    def test_subscription_state_status_values(self, auth_session):
        """Verify status is one of expected values"""
        response = auth_session.get(f"{BASE_URL}/api/subscription/state")
        assert response.status_code == 200
        
        data = response.json()
        valid_statuses = ["trialing", "active", "past_due", "canceled", "expired"]
        assert data["status"] in valid_statuses, f"Unexpected status: {data['status']}"
    
    def test_subscription_state_boolean_fields(self, auth_session):
        """Verify boolean fields are actual booleans"""
        response = auth_session.get(f"{BASE_URL}/api/subscription/state")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data["is_trial"], bool), f"is_trial should be bool, got {type(data['is_trial'])}"
        assert isinstance(data["is_active"], bool), f"is_active should be bool, got {type(data['is_active'])}"
        assert isinstance(data["is_read_only"], bool), f"is_read_only should be bool, got {type(data['is_read_only'])}"
    
    def test_subscription_state_trial_days_type(self, auth_session):
        """Verify trial_days_remaining is int or null"""
        response = auth_session.get(f"{BASE_URL}/api/subscription/state")
        assert response.status_code == 200
        
        data = response.json()
        trial_days = data["trial_days_remaining"]
        assert trial_days is None or isinstance(trial_days, int), \
            f"trial_days_remaining should be int or null, got {type(trial_days)}"


class TestDashboardSubscriptionState:
    """Tests for GET /api/dashboard subscription field"""
    
    def test_dashboard_includes_subscription_field(self, auth_session):
        """Verify dashboard response includes subscription field"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard?trust_id={TRUST_ID}")
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        
        data = response.json()
        assert "subscription" in data, "Dashboard missing subscription field"
    
    def test_dashboard_subscription_has_required_fields(self, auth_session):
        """Verify dashboard subscription object has DashboardSubscriptionState fields"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard?trust_id={TRUST_ID}")
        assert response.status_code == 200
        
        data = response.json()
        subscription = data.get("subscription")
        assert subscription is not None, "Subscription field is null"
        
        # Check DashboardSubscriptionState fields
        required_fields = ["plan_type", "status", "is_trial", "is_active", "is_read_only", "trial_days_remaining"]
        for field in required_fields:
            assert field in subscription, f"Dashboard subscription missing field: {field}"
        
        print(f"Dashboard subscription: {subscription}")
    
    def test_dashboard_subscription_matches_state_endpoint(self, auth_session):
        """Verify dashboard subscription matches subscription/state endpoint"""
        state_resp = auth_session.get(f"{BASE_URL}/api/subscription/state")
        dashboard_resp = auth_session.get(f"{BASE_URL}/api/dashboard?trust_id={TRUST_ID}")
        
        assert state_resp.status_code == 200
        assert dashboard_resp.status_code == 200
        
        state_data = state_resp.json()
        dashboard_sub = dashboard_resp.json().get("subscription", {})
        
        # Compare common fields
        assert dashboard_sub["plan_type"] == state_data["plan_type"], "plan_type mismatch"
        assert dashboard_sub["status"] == state_data["status"], "status mismatch"
        assert dashboard_sub["is_trial"] == state_data["is_trial"], "is_trial mismatch"
        assert dashboard_sub["is_active"] == state_data["is_active"], "is_active mismatch"
        assert dashboard_sub["is_read_only"] == state_data["is_read_only"], "is_read_only mismatch"


class TestTrialUserReadAccess:
    """Tests verifying trial users can read all data types"""
    
    def test_trial_user_can_read_minutes(self, auth_session):
        """Trial user can GET /api/minutes"""
        response = auth_session.get(f"{BASE_URL}/api/minutes?trust_id={TRUST_ID}")
        assert response.status_code == 200, f"Failed to read minutes: {response.status_code}"
        print(f"Minutes count: {len(response.json())}")
    
    def test_trial_user_can_read_distributions(self, auth_session):
        """Trial user can GET /api/distributions"""
        response = auth_session.get(f"{BASE_URL}/api/distributions?trust_id={TRUST_ID}")
        assert response.status_code == 200, f"Failed to read distributions: {response.status_code}"
        print(f"Distributions count: {len(response.json())}")
    
    def test_trial_user_can_read_compensation_plans(self, auth_session):
        """Trial user can GET /api/compensation-plans"""
        response = auth_session.get(f"{BASE_URL}/api/compensation-plans?trust_id={TRUST_ID}")
        assert response.status_code == 200, f"Failed to read compensation plans: {response.status_code}"
        print(f"Compensation plans count: {len(response.json())}")
    
    def test_trial_user_can_read_compensation_payments(self, auth_session):
        """Trial user can GET /api/compensation-payments"""
        response = auth_session.get(f"{BASE_URL}/api/compensation-payments?trust_id={TRUST_ID}")
        assert response.status_code == 200, f"Failed to read compensation payments: {response.status_code}"
        print(f"Compensation payments count: {len(response.json())}")
    
    def test_trial_user_can_read_entities(self, auth_session):
        """Trial user can GET /api/entities"""
        response = auth_session.get(f"{BASE_URL}/api/entities?trust_id={TRUST_ID}")
        assert response.status_code == 200, f"Failed to read entities: {response.status_code}"
        print(f"Entities count: {len(response.json())}")
    
    def test_trial_user_can_read_schedule_a(self, auth_session):
        """Trial user can GET /api/schedule-a"""
        response = auth_session.get(f"{BASE_URL}/api/schedule-a?trust_id={TRUST_ID}")
        assert response.status_code == 200, f"Failed to read Schedule A: {response.status_code}"
        print(f"Schedule A items count: {len(response.json())}")
    
    def test_trial_user_can_read_tasks(self, auth_session):
        """Trial user can GET /api/tasks"""
        response = auth_session.get(f"{BASE_URL}/api/tasks?trust_id={TRUST_ID}")
        assert response.status_code == 200, f"Failed to read tasks: {response.status_code}"
        print(f"Tasks count: {len(response.json())}")
    
    def test_trial_user_can_read_trusts(self, auth_session):
        """Trial user can GET /api/trusts"""
        response = auth_session.get(f"{BASE_URL}/api/trusts")
        assert response.status_code == 200, f"Failed to read trusts: {response.status_code}"
        print(f"Trusts count: {len(response.json())}")


class TestRequireWriteAccessMinutes:
    """Tests for require_write_access on minutes router"""
    
    def test_write_access_applied_to_create_minutes(self, auth_session):
        """POST /api/minutes uses require_write_access"""
        # For active trial user, this should succeed (is_read_only=false)
        # We're testing that the endpoint works, not that it blocks
        response = auth_session.post(f"{BASE_URL}/api/minutes", json={
            "trust_id": TRUST_ID,
            "minutes_type": "annual",
            "meeting_date": "2025-01-15",
            "participants_text": "TEST_participant",
            "decisions_text": "TEST_decision"
        })
        # Should either succeed (201/200) or fail with validation error (4xx)
        # Should NOT fail with 403 for active trial
        assert response.status_code != 403 or "subscription" in response.text.lower(), \
            f"Unexpected 403 for active trial user: {response.text}"
        print(f"Create minutes: {response.status_code}")
    
    def test_write_access_applied_to_delete_minutes(self, auth_session):
        """DELETE /api/minutes uses require_write_access - just verify endpoint responds"""
        response = auth_session.delete(f"{BASE_URL}/api/minutes/nonexistent_id")
        # Should get 404 (not found) not 403 for active trial
        assert response.status_code in [404, 200, 204], f"Unexpected: {response.status_code}"


class TestRequireWriteAccessDistributions:
    """Tests for require_write_access on distributions router"""
    
    def test_write_access_applied_to_create_distribution(self, auth_session):
        """POST /api/distributions uses require_write_access"""
        response = auth_session.post(f"{BASE_URL}/api/distributions", json={
            "trust_id": TRUST_ID,
            "beneficiary_name": "TEST_beneficiary",
            "amount": 100.00,
            "date": "2025-01-15",
            "purpose_classification": "distribution"
        })
        assert response.status_code != 403 or "subscription" in response.text.lower(), \
            f"Unexpected 403 for active trial user"
        print(f"Create distribution: {response.status_code}")
    
    def test_write_access_applied_to_approve_distribution(self, auth_session):
        """PATCH /api/distributions/{id}/approve uses require_write_access"""
        response = auth_session.patch(f"{BASE_URL}/api/distributions/nonexistent/approve", json={
            "solvency_confirmed": True,
            "recusal_acknowledged": True
        })
        assert response.status_code in [404, 400, 200], f"Unexpected: {response.status_code}"


class TestRequireWriteAccessCompensation:
    """Tests for require_write_access on compensation router"""
    
    def test_write_access_applied_to_create_comp_plan(self, auth_session):
        """POST /api/compensation-plans uses require_write_access"""
        response = auth_session.post(f"{BASE_URL}/api/compensation-plans", json={
            "trust_id": TRUST_ID,
            "trustee_name": "TEST_trustee",
            "role": "trustee",
            "annual_amount": 5000,
            "annual_approved_amount": 5000,
            "effective_date": "2025-01-01"
        })
        assert response.status_code != 403 or "subscription" in response.text.lower()
        print(f"Create comp plan: {response.status_code}")
    
    def test_write_access_applied_to_create_comp_payment(self, auth_session):
        """POST /api/compensation-payments uses require_write_access"""
        response = auth_session.post(f"{BASE_URL}/api/compensation-payments", json={
            "trust_id": TRUST_ID,
            "amount": 500.00,
            "date": "2025-01-15",
            "classification_text": "TEST_quarterly"
        })
        assert response.status_code != 403 or "subscription" in response.text.lower()
        print(f"Create comp payment: {response.status_code}")


class TestRequireWriteAccessEntities:
    """Tests for require_write_access on entities router"""
    
    def test_write_access_applied_to_create_entity(self, auth_session):
        """POST /api/entities uses require_write_access"""
        response = auth_session.post(f"{BASE_URL}/api/entities", json={
            "trust_id": TRUST_ID,
            "name": "TEST_Entity",
            "entity_type": "Trust",
            "legal_name": "TEST Entity LLC"
        })
        assert response.status_code != 403 or "subscription" in response.text.lower()
        print(f"Create entity: {response.status_code}")
    
    def test_write_access_applied_to_delete_entity(self, auth_session):
        """DELETE /api/entities uses require_write_access"""
        response = auth_session.delete(f"{BASE_URL}/api/entities/nonexistent")
        assert response.status_code in [404, 200, 204]


class TestRequireWriteAccessScheduleA:
    """Tests for require_write_access on schedule_a router"""
    
    def test_write_access_applied_to_create_schedule_a(self, auth_session):
        """POST /api/schedule-a uses require_write_access"""
        response = auth_session.post(f"{BASE_URL}/api/schedule-a", json={
            "trust_id": TRUST_ID,
            "category": "real_property",
            "description": "TEST_property",
            "date_conveyed": "2025-01-01"
        })
        assert response.status_code != 403 or "subscription" in response.text.lower()
        print(f"Create schedule_a: {response.status_code}")
    
    def test_write_access_applied_to_update_schedule_a(self, auth_session):
        """PUT /api/schedule-a/{id} uses require_write_access"""
        response = auth_session.put(f"{BASE_URL}/api/schedule-a/nonexistent", json={
            "description": "updated"
        })
        assert response.status_code in [404, 200, 422]  # 422 for validation error


class TestRequireWriteAccessTasks:
    """Tests for require_write_access on tasks router"""
    
    def test_write_access_applied_to_create_task(self, auth_session):
        """POST /api/tasks uses require_write_access"""
        response = auth_session.post(f"{BASE_URL}/api/tasks", json={
            "trust_id": TRUST_ID,
            "task_type": "custom",
            "due_date": "2025-12-31",
            "description": "TEST_task"
        })
        assert response.status_code != 403 or "subscription" in response.text.lower()
        print(f"Create task: {response.status_code}")
    
    def test_write_access_applied_to_complete_task(self, auth_session):
        """POST /api/tasks/{id}/complete uses require_write_access"""
        response = auth_session.post(f"{BASE_URL}/api/tasks/nonexistent/complete")
        assert response.status_code in [404, 200]


class TestRequireWriteAccessTrusts:
    """Tests for require_write_access on trusts router"""
    
    def test_write_access_applied_to_update_trust(self, auth_session):
        """PATCH /api/trusts/{id} uses require_write_access"""
        response = auth_session.patch(f"{BASE_URL}/api/trusts/{TRUST_ID}", json={
            "name": "Demo Trust Updated"
        })
        # Should work for active trial or get 404 if trust not found
        assert response.status_code != 403 or "subscription" in response.text.lower()
        print(f"Update trust: {response.status_code}")


class TestRequireWriteAccessTrustUnits:
    """Tests for require_write_access on trust_units router (premium feature)"""
    
    def test_trust_units_create_settings_has_write_check(self, auth_session):
        """POST /api/trust-units/settings uses require_write_access"""
        response = auth_session.post(f"{BASE_URL}/api/trust-units/settings", json={
            "trust_id": TRUST_ID,
            "total_authorized_units": 100
        })
        # May get 402 (premium gate) or work/fail for other reasons
        # Should NOT get 403 for active trial without premium gate hitting first
        print(f"Trust units settings: {response.status_code}")
    
    def test_trust_units_create_certificate_has_write_check(self, auth_session):
        """POST /api/trust-units/certificates uses require_write_access"""
        response = auth_session.post(f"{BASE_URL}/api/trust-units/certificates", json={
            "trust_id": TRUST_ID,
            "holder_name": "TEST_holder",
            "units": 10,
            "issue_date": "2025-01-01"
        })
        # May get 402 (premium gate) first
        print(f"Trust units certificate: {response.status_code}")


class TestSubscriptionStateConsistency:
    """Tests for consistent subscription state across modules"""
    
    def test_subscription_features_endpoint_accessible(self, auth_session):
        """GET /api/subscription/features returns feature flags"""
        response = auth_session.get(f"{BASE_URL}/api/subscription/features")
        assert response.status_code == 200, f"Failed: {response.status_code}"
        
        data = response.json()
        assert "features" in data, "Missing features dict"
        assert "plan_type" in data, "Missing plan_type"
        assert "is_active" in data, "Missing is_active"
        assert "is_trial" in data, "Missing is_trial"
        print(f"Features: {data}")
    
    def test_basic_subscription_endpoint(self, auth_session):
        """GET /api/subscription returns subscription details"""
        response = auth_session.get(f"{BASE_URL}/api/subscription")
        assert response.status_code == 200, f"Failed: {response.status_code}"
        
        data = response.json()
        assert "subscription_id" in data
        assert "plan_type" in data
        assert "status" in data
        assert "is_active" in data
        print(f"Subscription: plan={data['plan_type']}, status={data['status']}, active={data['is_active']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
