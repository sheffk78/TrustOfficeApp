"""
TrustOffice API Tests
Test comprehensive backend functionality including:
- Authentication (login, register, session)
- Trusts CRUD
- Tasks CRUD
- Entities CRUD
- Entity Relationships
- Compensation Plans & Payments
- Distributions
- Minutes
- Subscription
"""

import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from requirements
TEST_EMAIL = "test@trustoffice.com"
TEST_PASSWORD = "testpassword123"

class TestHealthAndCategories:
    """Test basic health endpoints"""
    
    def test_categories_endpoint(self):
        """Categories endpoint returns all category types"""
        response = requests.get(f"{BASE_URL}/api/categories")
        assert response.status_code == 200, f"Categories failed: {response.text}"
        data = response.json()
        
        # Verify all category types are present
        assert "purpose_classifications" in data
        assert "task_types" in data
        assert "minutes_types" in data
        assert "entity_types" in data
        assert "relationship_types" in data
        
        # Verify values
        assert "distribution" in data["purpose_classifications"]
        assert "annual_review" in data["task_types"]
        assert "Trust" in data["entity_types"]
        print("Categories endpoint working correctly")


class TestAuthentication:
    """Test authentication flows"""
    
    @pytest.fixture(scope="class")
    def session(self):
        return requests.Session()
    
    def test_login_with_valid_credentials(self, session):
        """Login with test user credentials"""
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "token" in data, "No token in response"
        assert "user" in data, "No user in response"
        assert data["user"]["email"] == TEST_EMAIL
        
        # Store token for subsequent tests
        session.headers.update({"Authorization": f"Bearer {data['token']}"})
        print(f"Login successful for {TEST_EMAIL}")
        return data
    
    def test_get_current_user(self, session):
        """Verify /auth/me returns current user"""
        # First login
        login_resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        token = login_resp.json().get("token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        
        # Get current user
        response = session.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200, f"Get me failed: {response.text}"
        
        data = response.json()
        assert "user_id" in data
        assert "email" in data
        assert data["email"] == TEST_EMAIL
        print("Get current user working correctly")
    
    def test_login_invalid_credentials(self, session):
        """Login with invalid credentials returns 401"""
        response = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "invalid@test.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401


class TestTrusts:
    """Test trust CRUD operations"""
    
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
    
    def test_get_trusts(self, auth_session):
        """Get all trusts for authenticated user"""
        response = auth_session.get(f"{BASE_URL}/api/trusts")
        assert response.status_code == 200, f"Get trusts failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list)
        
        # Verify trust structure if any exist
        if len(data) > 0:
            trust = data[0]
            assert "trust_id" in trust
            assert "name" in trust
            assert "trust_type" in trust
            print(f"Found {len(data)} trusts")
        return data
    
    def test_get_single_trust(self, auth_session):
        """Get a single trust by ID"""
        # First get all trusts
        all_trusts = auth_session.get(f"{BASE_URL}/api/trusts").json()
        
        if len(all_trusts) > 0:
            trust_id = all_trusts[0]["trust_id"]
            response = auth_session.get(f"{BASE_URL}/api/trusts/{trust_id}")
            assert response.status_code == 200
            
            data = response.json()
            assert data["trust_id"] == trust_id
            print(f"Got trust: {data['name']}")


class TestGovernanceTasks:
    """Test governance task CRUD operations"""
    
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
    
    def test_get_tasks(self, auth_session, trust_id):
        """Get all tasks for a trust"""
        response = auth_session.get(f"{BASE_URL}/api/tasks?trust_id={trust_id}")
        assert response.status_code == 200, f"Get tasks failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} tasks")
    
    def test_create_task(self, auth_session, trust_id):
        """Create a new governance task"""
        due_date = (datetime.now() + timedelta(days=30)).isoformat()
        
        response = auth_session.post(f"{BASE_URL}/api/tasks", json={
            "trust_id": trust_id,
            "task_type": "custom",
            "due_date": due_date,
            "description": "TEST_Task - Automated test task"
        })
        
        assert response.status_code == 200, f"Create task failed: {response.text}"
        data = response.json()
        
        assert "task_id" in data
        assert data["task_type"] == "custom"
        assert data["status"] == "upcoming"
        print(f"Created task: {data['task_id']}")
        return data["task_id"]
    
    def test_complete_task(self, auth_session, trust_id):
        """Complete a governance task"""
        # First create a task
        due_date = (datetime.now() + timedelta(days=30)).isoformat()
        create_resp = auth_session.post(f"{BASE_URL}/api/tasks", json={
            "trust_id": trust_id,
            "task_type": "custom",
            "due_date": due_date,
            "description": "TEST_Task_Complete - Task to complete"
        })
        task_id = create_resp.json()["task_id"]
        
        # Complete the task
        response = auth_session.patch(f"{BASE_URL}/api/tasks/{task_id}/complete")
        assert response.status_code == 200, f"Complete task failed: {response.text}"
        
        data = response.json()
        assert "completed_at" in data
        print(f"Completed task: {task_id}")
        
        # Cleanup
        auth_session.delete(f"{BASE_URL}/api/tasks/{task_id}")
    
    def test_delete_task(self, auth_session, trust_id):
        """Delete a governance task"""
        # Create task to delete
        due_date = (datetime.now() + timedelta(days=30)).isoformat()
        create_resp = auth_session.post(f"{BASE_URL}/api/tasks", json={
            "trust_id": trust_id,
            "task_type": "custom",
            "due_date": due_date,
            "description": "TEST_Task_Delete - Task to delete"
        })
        task_id = create_resp.json()["task_id"]
        
        # Delete the task
        response = auth_session.delete(f"{BASE_URL}/api/tasks/{task_id}")
        assert response.status_code == 200, f"Delete task failed: {response.text}"
        
        # Verify deletion
        get_resp = auth_session.get(f"{BASE_URL}/api/tasks?trust_id={trust_id}")
        tasks = get_resp.json()
        task_ids = [t["task_id"] for t in tasks]
        assert task_id not in task_ids
        print(f"Deleted task: {task_id}")


class TestEntities:
    """Test entity CRUD operations"""
    
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
    
    def test_get_entities(self, auth_session, trust_id):
        """Get all entities for a trust"""
        response = auth_session.get(f"{BASE_URL}/api/entities?trust_id={trust_id}")
        assert response.status_code == 200, f"Get entities failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} entities")
    
    def test_create_entity(self, auth_session, trust_id):
        """Create a new entity"""
        response = auth_session.post(f"{BASE_URL}/api/entities", json={
            "trust_id": trust_id,
            "name": "TEST_Entity LLC",
            "entity_type": "Operating LLC",
            "legal_name": "Test Operating LLC",
            "governing_law": "Delaware"
        })
        
        assert response.status_code == 200, f"Create entity failed: {response.text}"
        data = response.json()
        
        assert "entity_id" in data
        assert data["name"] == "TEST_Entity LLC"
        assert data["entity_type"] == "Operating LLC"
        print(f"Created entity: {data['entity_id']}")
        
        # Cleanup
        auth_session.delete(f"{BASE_URL}/api/entities/{data['entity_id']}")
    
    def test_get_single_entity(self, auth_session, trust_id):
        """Get a single entity by ID"""
        entities = auth_session.get(f"{BASE_URL}/api/entities?trust_id={trust_id}").json()
        
        if len(entities) > 0:
            entity_id = entities[0]["entity_id"]
            response = auth_session.get(f"{BASE_URL}/api/entities/{entity_id}")
            assert response.status_code == 200
            
            data = response.json()
            assert data["entity_id"] == entity_id
            print(f"Got entity: {data['name']}")


class TestEntityRelationships:
    """Test entity relationship operations"""
    
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
    
    def test_get_relationships(self, auth_session, trust_id):
        """Get all entity relationships for a trust"""
        response = auth_session.get(f"{BASE_URL}/api/entity-relationships?trust_id={trust_id}")
        assert response.status_code == 200, f"Get relationships failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} relationships")


class TestCompensation:
    """Test compensation plans and payments"""
    
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
    
    def test_get_compensation_plans(self, auth_session, trust_id):
        """Get compensation plans"""
        response = auth_session.get(f"{BASE_URL}/api/compensation-plans?trust_id={trust_id}")
        assert response.status_code == 200, f"Get comp plans failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} compensation plans")
    
    def test_get_compensation_payments(self, auth_session, trust_id):
        """Get compensation payments"""
        response = auth_session.get(f"{BASE_URL}/api/compensation-payments?trust_id={trust_id}")
        assert response.status_code == 200, f"Get comp payments failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} compensation payments")
    
    def test_get_compensation_ytd(self, auth_session, trust_id):
        """Get YTD compensation info"""
        response = auth_session.get(f"{BASE_URL}/api/compensation-ytd?trust_id={trust_id}")
        assert response.status_code == 200, f"Get comp YTD failed: {response.text}"
        
        data = response.json()
        assert "ytd_total" in data
        assert "annual_approved" in data
        print(f"YTD Total: ${data['ytd_total']}, Annual Approved: ${data['annual_approved']}")
    
    def test_create_compensation_payment(self, auth_session, trust_id):
        """Create compensation payment"""
        response = auth_session.post(f"{BASE_URL}/api/compensation-payments", json={
            "trust_id": trust_id,
            "amount": 100.00,
            "date": datetime.now().isoformat()[:10],
            "classification_text": "TEST_Payment - Automated test"
        })
        
        assert response.status_code == 200, f"Create comp payment failed: {response.text}"
        data = response.json()
        
        assert "payment_id" in data
        assert data["amount"] == 100.00
        print(f"Created payment: {data['payment_id']}")
        
        # Cleanup
        auth_session.delete(f"{BASE_URL}/api/compensation-payments/{data['payment_id']}")


class TestDistributions:
    """Test distribution operations"""
    
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
    
    def test_get_distributions(self, auth_session, trust_id):
        """Get all distributions"""
        response = auth_session.get(f"{BASE_URL}/api/distributions?trust_id={trust_id}")
        assert response.status_code == 200, f"Get distributions failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} distributions")
    
    def test_create_distribution(self, auth_session, trust_id):
        """Create distribution"""
        response = auth_session.post(f"{BASE_URL}/api/distributions", json={
            "trust_id": trust_id,
            "beneficiary_name": "TEST_Beneficiary",
            "amount": 500.00,
            "date": datetime.now().isoformat()[:10],
            "purpose_classification": "distribution",
            "notes": "TEST_Distribution - Automated test"
        })
        
        assert response.status_code == 200, f"Create distribution failed: {response.text}"
        data = response.json()
        
        assert "distribution_id" in data
        assert data["beneficiary_name"] == "TEST_Beneficiary"
        assert data["amount"] == 500.00
        print(f"Created distribution: {data['distribution_id']}")
        
        # Cleanup
        auth_session.delete(f"{BASE_URL}/api/distributions/{data['distribution_id']}")


class TestMinutes:
    """Test minutes operations"""
    
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
    
    def test_get_minutes(self, auth_session, trust_id):
        """Get all minutes records"""
        response = auth_session.get(f"{BASE_URL}/api/minutes?trust_id={trust_id}")
        assert response.status_code == 200, f"Get minutes failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} minutes records")
    
    def test_create_minutes(self, auth_session, trust_id):
        """Create minutes record"""
        response = auth_session.post(f"{BASE_URL}/api/minutes", json={
            "trust_id": trust_id,
            "minutes_type": "quarterly",
            "meeting_date": datetime.now().isoformat()[:10],
            "participants_text": "TEST_Participants",
            "decisions_text": "TEST_Decisions - Automated test record"
        })
        
        assert response.status_code == 200, f"Create minutes failed: {response.text}"
        data = response.json()
        
        assert "minutes_id" in data
        assert data["minutes_type"] == "quarterly"
        print(f"Created minutes: {data['minutes_id']}")
        
        # Cleanup
        auth_session.delete(f"{BASE_URL}/api/minutes/{data['minutes_id']}")


class TestGovernanceHealth:
    """Test governance health score"""
    
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
    
    def test_get_governance_health(self, auth_session, trust_id):
        """Get governance health score"""
        response = auth_session.get(f"{BASE_URL}/api/governance/{trust_id}")
        assert response.status_code == 200, f"Get governance failed: {response.text}"
        
        data = response.json()
        assert "total_score" in data
        assert "max_score" in data
        assert "color" in data
        assert "criteria" in data
        
        print(f"Governance Score: {data['total_score']}/{data['max_score']} ({data['color']})")


class TestActivity:
    """Test activity timeline"""
    
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
    
    def test_get_activity(self, auth_session, trust_id):
        """Get activity timeline"""
        response = auth_session.get(f"{BASE_URL}/api/activity?trust_id={trust_id}")
        assert response.status_code == 200, f"Get activity failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} activity items")


class TestSubscription:
    """Test subscription endpoints"""
    
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
    
    def test_get_subscription(self, auth_session):
        """Get subscription status"""
        response = auth_session.get(f"{BASE_URL}/api/subscription")
        assert response.status_code == 200, f"Get subscription failed: {response.text}"
        
        data = response.json()
        assert "subscription_id" in data
        assert "status" in data
        assert "plan_type" in data
        assert "is_active" in data
        
        print(f"Subscription: {data['plan_type']} - Status: {data['status']}, Active: {data['is_active']}")


class TestOnboarding:
    """Test onboarding state"""
    
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
    
    def test_get_onboarding(self, auth_session):
        """Get onboarding state"""
        response = auth_session.get(f"{BASE_URL}/api/onboarding")
        assert response.status_code == 200, f"Get onboarding failed: {response.text}"
        
        data = response.json()
        assert "user_id" in data
        assert "entities_confirmed" in data
        assert "calendar_set" in data
        assert "minutes_generated" in data
        
        print(f"Onboarding state: entities={data['entities_confirmed']}, calendar={data['calendar_set']}")


class TestGovernanceHealthScore:
    """Test 5-criteria governance health score"""
    
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
    
    def test_get_governance_health_returns_5_criteria(self, auth_session, trust_id):
        """Governance health endpoint returns 5 criteria with scores"""
        response = auth_session.get(f"{BASE_URL}/api/governance/{trust_id}")
        assert response.status_code == 200, f"Get governance failed: {response.text}"
        
        data = response.json()
        
        # Verify 5-criteria response structure
        assert "trust_id" in data
        assert "total_score" in data
        assert "max_score" in data
        assert data["max_score"] == 100, "Max score should be 100"
        assert "color" in data
        assert data["color"] in ["red", "yellow", "green"]
        assert "criteria" in data
        
        # Verify we have 5 criteria
        criteria = data["criteria"]
        assert len(criteria) == 5, f"Expected 5 criteria, got {len(criteria)}"
        
        # Verify each criterion has correct structure
        expected_criteria_names = [
            "Quarterly Minutes",
            "Task Compliance",
            "Compensation Alignment",
            "Distribution Documentation",
            "Annual Review"
        ]
        
        for criterion in criteria:
            assert "name" in criterion
            assert "description" in criterion
            assert "points" in criterion
            assert "max_points" in criterion
            assert "achieved" in criterion
            assert criterion["max_points"] == 20, f"Each criterion should have max 20 points"
            assert criterion["name"] in expected_criteria_names, f"Unexpected criterion: {criterion['name']}"
        
        print(f"Governance health score: {data['total_score']}/{data['max_score']} ({data['color']})")
        print(f"Criteria: {[c['name'] + '=' + str(c['points']) for c in criteria]}")


class TestDistributionApproval:
    """Test distribution approval workflow with solvency/recusal confirmations"""
    
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
    
    @pytest.fixture
    def test_distribution(self, auth_session, trust_id):
        """Create a test distribution for approval testing"""
        response = auth_session.post(f"{BASE_URL}/api/distributions", json={
            "trust_id": trust_id,
            "beneficiary_name": "TEST_Approval_Beneficiary",
            "amount": 1000.0,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "purpose_classification": "distribution",
            "notes": "Test distribution for approval workflow"
        })
        assert response.status_code == 200, f"Failed to create test distribution: {response.text}"
        dist = response.json()
        yield dist
        # Cleanup
        auth_session.delete(f"{BASE_URL}/api/distributions/{dist['distribution_id']}")
    
    def test_approve_without_solvency_fails(self, auth_session, test_distribution):
        """Approval without solvency confirmation should fail"""
        dist_id = test_distribution["distribution_id"]
        
        response = auth_session.patch(f"{BASE_URL}/api/distributions/{dist_id}/approve", json={
            "solvency_confirmed": False,
            "recusal_acknowledged": True
        })
        
        assert response.status_code == 400, "Should fail without solvency"
        assert "solvency" in response.text.lower()
        print("✅ Correctly rejected approval without solvency confirmation")
    
    def test_approve_without_recusal_fails(self, auth_session, test_distribution):
        """Approval without recusal acknowledgment should fail"""
        dist_id = test_distribution["distribution_id"]
        
        response = auth_session.patch(f"{BASE_URL}/api/distributions/{dist_id}/approve", json={
            "solvency_confirmed": True,
            "recusal_acknowledged": False
        })
        
        assert response.status_code == 400, "Should fail without recusal"
        assert "recusal" in response.text.lower()
        print("✅ Correctly rejected approval without recusal acknowledgment")
    
    def test_approve_with_both_confirmations_succeeds(self, auth_session, trust_id):
        """Approval with both solvency and recusal should succeed"""
        # Create a fresh distribution for this test
        create_resp = auth_session.post(f"{BASE_URL}/api/distributions", json={
            "trust_id": trust_id,
            "beneficiary_name": "TEST_Full_Approval",
            "amount": 2000.0,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "purpose_classification": "distribution",
            "notes": "Test for full approval"
        })
        dist = create_resp.json()
        dist_id = dist["distribution_id"]
        
        try:
            response = auth_session.patch(f"{BASE_URL}/api/distributions/{dist_id}/approve", json={
                "solvency_confirmed": True,
                "recusal_acknowledged": True
            })
            
            assert response.status_code == 200, f"Approval failed: {response.text}"
            data = response.json()
            
            # Verify approval fields
            assert data["solvency_confirmed"] == True
            assert data["recusal_acknowledged"] == True
            assert data["approved_by"] is not None
            assert data["approved_at"] is not None
            
            print(f"✅ Distribution approved successfully. Approved by: {data['approved_by']} at {data['approved_at']}")
        finally:
            # Cleanup
            auth_session.delete(f"{BASE_URL}/api/distributions/{dist_id}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
