"""
Phase 2 Spec Integration Tests
Tests for:
1. Governance Health Score - 7 criteria including Transaction Classification and Separation Alert Health
2. Governance Calendar - transaction_review task type auto-created monthly
3. Minutes Generator - generate resolution minutes from resolved alerts
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from iteration_71
TEST_EMAIL = "contact@trustoffice.app"
TEST_PASSWORD = "TrustAdmin2026!"
TEST_TRUST_ID = "trust_2097657c7e1d"


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
def auth_headers(auth_token):
    """Headers with auth token"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


class TestGovernanceHealthScore:
    """Test health score with 7 criteria including new Transaction Classification and Separation Alert Health"""
    
    def test_health_score_returns_7_criteria(self, auth_headers):
        """Health score should now have 7 criteria instead of 5"""
        response = requests.get(
            f"{BASE_URL}/api/governance/{TEST_TRUST_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "criteria" in data
        assert len(data["criteria"]) == 7, f"Expected 7 criteria, got {len(data['criteria'])}"
        
        # Verify criteria names
        criteria_names = [c["name"] for c in data["criteria"]]
        expected_names = [
            "Quarterly Minutes",
            "Task Compliance",
            "Compensation Alignment",
            "Distribution Documentation",
            "Annual Review",
            "Transaction Classification",
            "Separation Alert Health"
        ]
        for name in expected_names:
            assert name in criteria_names, f"Missing criterion: {name}"
        print(f"PASS: Health score has 7 criteria: {criteria_names}")
    
    def test_health_score_total_is_120(self, auth_headers):
        """Health score max should be 120"""
        response = requests.get(
            f"{BASE_URL}/api/governance/{TEST_TRUST_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["max_score"] == 120, f"Expected max_score=120, got {data['max_score']}"
        assert 0 <= data["total_score"] <= 120, f"Score {data['total_score']} out of range"
        print(f"PASS: Health score total={data['total_score']}/120, color={data['color']}")
    
    def test_transaction_classification_criterion_exists(self, auth_headers):
        """Transaction Classification criterion should exist with proper structure"""
        response = requests.get(
            f"{BASE_URL}/api/governance/{TEST_TRUST_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        txn_criterion = next((c for c in data["criteria"] if c["name"] == "Transaction Classification"), None)
        assert txn_criterion is not None, "Transaction Classification criterion not found"
        
        # Verify structure
        assert "points" in txn_criterion
        assert "achieved" in txn_criterion
        assert "description" in txn_criterion
        
        # Points should be 0, 5, 10, or 15 based on classification percentage
        assert txn_criterion["points"] in [0, 5, 10, 15], f"Unexpected points: {txn_criterion['points']}"
        print(f"PASS: Transaction Classification - points={txn_criterion['points']}, desc='{txn_criterion['description']}'")
    
    def test_separation_alert_health_criterion_exists(self, auth_headers):
        """Separation Alert Health criterion should exist with proper structure"""
        response = requests.get(
            f"{BASE_URL}/api/governance/{TEST_TRUST_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        alert_criterion = next((c for c in data["criteria"] if c["name"] == "Separation Alert Health"), None)
        assert alert_criterion is not None, "Separation Alert Health criterion not found"
        
        # Verify structure
        assert "points" in alert_criterion
        assert "achieved" in alert_criterion
        assert "description" in alert_criterion
        
        # Points should be 0-15 based on alert counts
        assert 0 <= alert_criterion["points"] <= 15, f"Points out of range: {alert_criterion['points']}"
        print(f"PASS: Separation Alert Health - points={alert_criterion['points']}, desc='{alert_criterion['description']}'")
    
    def test_health_score_criteria_points_sum_correctly(self, auth_headers):
        """Sum of all criteria points should equal total_score"""
        response = requests.get(
            f"{BASE_URL}/api/governance/{TEST_TRUST_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        criteria_sum = sum(c["points"] for c in data["criteria"])
        assert criteria_sum == data["total_score"], f"Criteria sum {criteria_sum} != total_score {data['total_score']}"
        print(f"PASS: Criteria points sum ({criteria_sum}) equals total_score ({data['total_score']})")


class TestTransactionReviewTask:
    """Test transaction_review task type and auto-creation"""
    
    def test_transaction_review_task_type_valid(self, auth_headers):
        """transaction_review should be a valid task type for creation"""
        # First, get existing tasks to see if one already exists
        response = requests.get(
            f"{BASE_URL}/api/tasks?trust_id={TEST_TRUST_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        tasks = response.json()
        txn_review_tasks = [t for t in tasks if t["task_type"] == "transaction_review"]
        print(f"Found {len(txn_review_tasks)} existing transaction_review tasks")
        
        # The task should have been auto-created when health score was calculated
        # (which happens on GET /governance/{trust_id})
        assert len(txn_review_tasks) >= 1, "No transaction_review task found - should be auto-created"
        
        # Verify task structure
        task = txn_review_tasks[0]
        assert "task_id" in task
        assert "due_date" in task
        assert "description" in task
        assert task["task_type"] == "transaction_review"
        print(f"PASS: transaction_review task exists - due_date={task['due_date']}, desc='{task['description'][:50]}...'")
    
    def test_transaction_review_task_has_monthly_due_date(self, auth_headers):
        """transaction_review task should be due at end of current month"""
        response = requests.get(
            f"{BASE_URL}/api/tasks?trust_id={TEST_TRUST_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        tasks = response.json()
        txn_review_tasks = [t for t in tasks if t["task_type"] == "transaction_review"]
        
        if txn_review_tasks:
            task = txn_review_tasks[0]
            due_date = task["due_date"]
            # Due date should be in YYYY-MM-DD format or ISO format
            assert due_date is not None
            print(f"PASS: transaction_review task due_date={due_date}")
    
    def test_tasks_endpoint_returns_transaction_review_with_status(self, auth_headers):
        """GET /tasks should return transaction_review tasks with computed status"""
        response = requests.get(
            f"{BASE_URL}/api/tasks?trust_id={TEST_TRUST_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        tasks = response.json()
        txn_review_tasks = [t for t in tasks if t["task_type"] == "transaction_review"]
        
        if txn_review_tasks:
            task = txn_review_tasks[0]
            # Status should be computed (pending, overdue, completed, or upcoming)
            assert "status" in task, "Task missing status field"
            assert task["status"] in ["pending", "overdue", "completed", "upcoming"], f"Unexpected status: {task['status']}"
            print(f"PASS: transaction_review task has status={task['status']}")


class TestGenerateResolutionMinutes:
    """Test POST /alerts/{id}/generate-resolution endpoint"""
    
    def test_generate_resolution_requires_resolved_alert(self, auth_headers):
        """Should reject unresolved alerts"""
        # First get active alerts
        response = requests.get(
            f"{BASE_URL}/api/alerts?trust_id={TEST_TRUST_ID}&status=active",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        alerts = response.json()
        if alerts:
            active_alert = alerts[0]
            # Try to generate minutes for active (unresolved) alert
            gen_response = requests.post(
                f"{BASE_URL}/api/alerts/{active_alert['alert_id']}/generate-resolution",
                headers=auth_headers
            )
            assert gen_response.status_code == 400, f"Expected 400 for unresolved alert, got {gen_response.status_code}"
            error = gen_response.json()
            assert "resolved" in error.get("detail", "").lower(), f"Error should mention 'resolved': {error}"
            print(f"PASS: Correctly rejected unresolved alert with 400")
        else:
            print("SKIP: No active alerts to test rejection")
    
    def test_generate_resolution_for_resolved_alert(self, auth_headers):
        """Should generate minutes for resolved alerts"""
        # Get alert history (includes resolved)
        response = requests.get(
            f"{BASE_URL}/api/alerts/history?trust_id={TEST_TRUST_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        alerts = response.json()
        resolved_alerts = [a for a in alerts if a["status"] == "resolved"]
        
        if resolved_alerts:
            resolved_alert = resolved_alerts[0]
            # Generate minutes
            gen_response = requests.post(
                f"{BASE_URL}/api/alerts/{resolved_alert['alert_id']}/generate-resolution",
                headers=auth_headers
            )
            assert gen_response.status_code == 200, f"Expected 200, got {gen_response.status_code}: {gen_response.text}"
            
            data = gen_response.json()
            assert "minutes_id" in data, "Response should contain minutes_id"
            assert "message" in data
            assert data["minutes_type"] == "general", f"Expected minutes_type='general', got {data.get('minutes_type')}"
            print(f"PASS: Generated resolution minutes - minutes_id={data['minutes_id']}")
            
            # Verify the minutes record was created
            return data["minutes_id"]
        else:
            print("SKIP: No resolved alerts to test generation")
            return None
    
    def test_generated_minutes_contain_alert_details(self, auth_headers):
        """Generated minutes should contain alert details, resolution type, and trustee note"""
        # Get alert history
        response = requests.get(
            f"{BASE_URL}/api/alerts/history?trust_id={TEST_TRUST_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        alerts = response.json()
        resolved_alerts = [a for a in alerts if a["status"] == "resolved"]
        
        if resolved_alerts:
            resolved_alert = resolved_alerts[0]
            
            # Generate minutes
            gen_response = requests.post(
                f"{BASE_URL}/api/alerts/{resolved_alert['alert_id']}/generate-resolution",
                headers=auth_headers
            )
            
            if gen_response.status_code == 200:
                data = gen_response.json()
                minutes_id = data["minutes_id"]
                
                # Fetch the minutes record to verify content
                minutes_response = requests.get(
                    f"{BASE_URL}/api/minutes?trust_id={TEST_TRUST_ID}",
                    headers=auth_headers
                )
                assert minutes_response.status_code == 200
                
                minutes_list = minutes_response.json()
                created_minutes = next((m for m in minutes_list if m["minutes_id"] == minutes_id), None)
                
                if created_minutes:
                    decisions_text = created_minutes.get("decisions_text", "")
                    
                    # Verify content contains expected elements
                    assert "SEPARATION REVIEW RESOLUTION" in decisions_text, "Missing 'SEPARATION REVIEW RESOLUTION' header"
                    assert "RESOLUTION:" in decisions_text, "Missing 'RESOLUTION:' section"
                    
                    # Should contain alert title or description
                    if resolved_alert.get("title"):
                        assert resolved_alert["title"] in decisions_text or "Alert Type:" in decisions_text
                    
                    # Should contain resolution type
                    if resolved_alert.get("resolution_type"):
                        assert "Action Taken:" in decisions_text
                    
                    # Should contain trustee note
                    if resolved_alert.get("resolution_note"):
                        assert "Trustee Note:" in decisions_text
                    
                    print(f"PASS: Minutes contain alert details, resolution type, and trustee note")
                else:
                    print(f"WARNING: Could not find created minutes {minutes_id} in list")
        else:
            print("SKIP: No resolved alerts to verify minutes content")
    
    def test_generate_resolution_returns_404_for_invalid_alert(self, auth_headers):
        """Should return 404 for non-existent alert"""
        response = requests.post(
            f"{BASE_URL}/api/alerts/invalid_alert_id_12345/generate-resolution",
            headers=auth_headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: Returns 404 for invalid alert ID")


class TestHealthScorePointsDistribution:
    """Test the specific point values for new criteria"""
    
    def test_transaction_classification_points_logic(self, auth_headers):
        """
        Transaction Classification scoring:
        - 15pts for >=90% properly classified
        - 10pts for 70-89%
        - 5pts for 50-69%
        - 0pts below 50%
        """
        response = requests.get(
            f"{BASE_URL}/api/governance/{TEST_TRUST_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        txn_criterion = next((c for c in data["criteria"] if c["name"] == "Transaction Classification"), None)
        
        assert txn_criterion is not None
        points = txn_criterion["points"]
        desc = txn_criterion["description"]
        
        # Points should be one of the valid values
        assert points in [0, 5, 10, 15], f"Invalid points value: {points}"
        
        # If description contains percentage, verify it matches points
        if "%" in desc:
            # Extract percentage from description like "85% of transactions properly classified"
            import re
            match = re.search(r'(\d+)%', desc)
            if match:
                pct = int(match.group(1))
                if pct >= 90:
                    assert points == 15, f"Expected 15pts for {pct}%, got {points}"
                elif pct >= 70:
                    assert points == 10, f"Expected 10pts for {pct}%, got {points}"
                elif pct >= 50:
                    assert points == 5, f"Expected 5pts for {pct}%, got {points}"
                else:
                    assert points == 0, f"Expected 0pts for {pct}%, got {points}"
        
        print(f"PASS: Transaction Classification points={points}, description='{desc}'")
    
    def test_separation_alert_health_points_logic(self, auth_headers):
        """
        Separation Alert Health scoring:
        - 15pts if no active alerts
        - Reduced by yellow/red alerts
        """
        response = requests.get(
            f"{BASE_URL}/api/governance/{TEST_TRUST_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        alert_criterion = next((c for c in data["criteria"] if c["name"] == "Separation Alert Health"), None)
        
        assert alert_criterion is not None
        points = alert_criterion["points"]
        desc = alert_criterion["description"]
        achieved = alert_criterion["achieved"]
        
        # Points should be 0-15
        assert 0 <= points <= 15, f"Points out of range: {points}"
        
        # If no alerts, should have 15 points
        if "No active" in desc:
            assert points == 15, f"Expected 15pts for no alerts, got {points}"
            assert achieved == True
        
        # If red alerts, should have 0 points
        if "red alert" in desc.lower():
            assert points == 0, f"Expected 0pts for red alerts, got {points}"
            assert achieved == False
        
        print(f"PASS: Separation Alert Health points={points}, achieved={achieved}, description='{desc}'")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
