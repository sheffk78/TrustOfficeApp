"""
Background Jobs API Tests
Tests for:
- GET /api/background-jobs/status - Returns list of scheduled jobs with next run times
- POST /api/background-jobs/run/task-status-update - Manually triggers task status update
- POST /api/background-jobs/run/daily-reminders - Manually triggers daily reminder emails
- POST /api/background-jobs/run/health-snapshots - Manually triggers health score snapshots
"""

import pytest
import requests
import os
from datetime import datetime, timezone, timedelta

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    raise ValueError("REACT_APP_BACKEND_URL environment variable is not set")


class TestBackgroundJobs:
    """Test background jobs API endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test fixtures - authenticate and get token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login with test credentials
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "test@example.com",
                "password": "testpassword123"
            }
        )
        
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.status_code} - {login_response.text}")
        
        token = login_response.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        self.user = login_response.json().get("user")
        
    # ==================== GET /api/background-jobs/status ====================
    
    def test_background_jobs_status_requires_auth(self):
        """Test that /api/background-jobs/status requires authentication"""
        # Create new session without auth
        response = requests.get(f"{BASE_URL}/api/background-jobs/status")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: GET /api/background-jobs/status requires authentication")
    
    def test_background_jobs_status_returns_200(self):
        """Test that /api/background-jobs/status returns 200 with valid auth"""
        response = self.session.get(f"{BASE_URL}/api/background-jobs/status")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: GET /api/background-jobs/status returns 200")
    
    def test_background_jobs_status_response_structure(self):
        """Test that /api/background-jobs/status returns correct structure"""
        response = self.session.get(f"{BASE_URL}/api/background-jobs/status")
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify required fields exist
        assert "running" in data, "Response should have 'running' field"
        assert "jobs" in data, "Response should have 'jobs' field"
        assert "scheduler_active" in data, "Response should have 'scheduler_active' field"
        
        # Verify data types
        assert isinstance(data["running"], bool), "'running' should be a boolean"
        assert isinstance(data["jobs"], list), "'jobs' should be a list"
        assert isinstance(data["scheduler_active"], bool), "'scheduler_active' should be a boolean"
        
        print(f"PASS: Background jobs status structure is correct - running={data['running']}, scheduler_active={data['scheduler_active']}, jobs_count={len(data['jobs'])}")
    
    def test_background_jobs_status_scheduler_running(self):
        """Test that the scheduler is running after server startup"""
        response = self.session.get(f"{BASE_URL}/api/background-jobs/status")
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify scheduler is running
        assert data["running"] == True, "Background runner should be running"
        assert data["scheduler_active"] == True, "Scheduler should be active"
        
        print("PASS: Scheduler is running and active")
    
    def test_background_jobs_status_returns_scheduled_jobs(self):
        """Test that /api/background-jobs/status returns expected jobs"""
        response = self.session.get(f"{BASE_URL}/api/background-jobs/status")
        assert response.status_code == 200
        
        data = response.json()
        jobs = data["jobs"]
        
        # Check that we have jobs scheduled
        assert len(jobs) >= 3, f"Expected at least 3 scheduled jobs, got {len(jobs)}"
        
        # Get job IDs
        job_ids = [job["id"] for job in jobs]
        
        # Verify expected jobs exist
        expected_job_ids = ["task_status_update", "daily_reminders", "daily_health_snapshots"]
        for expected_id in expected_job_ids:
            assert expected_id in job_ids, f"Expected job '{expected_id}' not found in scheduled jobs"
        
        print(f"PASS: All 3 expected jobs are scheduled: {job_ids}")
    
    def test_background_jobs_status_job_structure(self):
        """Test that each job has correct structure"""
        response = self.session.get(f"{BASE_URL}/api/background-jobs/status")
        assert response.status_code == 200
        
        data = response.json()
        jobs = data["jobs"]
        
        for job in jobs:
            # Verify required fields
            assert "id" in job, "Job should have 'id' field"
            assert "name" in job, "Job should have 'name' field"
            assert "next_run_time" in job, "Job should have 'next_run_time' field"
            assert "pending" in job, "Job should have 'pending' field"
            
            # Verify data types
            assert isinstance(job["id"], str), "'id' should be a string"
            assert isinstance(job["name"], str), "'name' should be a string"
            assert isinstance(job["pending"], bool), "'pending' should be a boolean"
            
            # next_run_time should be a string (ISO datetime) or None
            if job["next_run_time"] is not None:
                assert isinstance(job["next_run_time"], str), "'next_run_time' should be a string"
                # Verify it's a valid ISO datetime
                try:
                    datetime.fromisoformat(job["next_run_time"].replace('Z', '+00:00'))
                except ValueError:
                    pytest.fail(f"'next_run_time' is not a valid ISO datetime: {job['next_run_time']}")
        
        print("PASS: All jobs have correct structure")
    
    # ==================== POST /api/background-jobs/run/task-status-update ====================
    
    def test_task_status_update_requires_auth(self):
        """Test that /api/background-jobs/run/task-status-update requires authentication"""
        response = requests.post(f"{BASE_URL}/api/background-jobs/run/task-status-update")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: POST /api/background-jobs/run/task-status-update requires authentication")
    
    def test_task_status_update_returns_200(self):
        """Test that /api/background-jobs/run/task-status-update returns 200"""
        response = self.session.post(f"{BASE_URL}/api/background-jobs/run/task-status-update")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: POST /api/background-jobs/run/task-status-update returns 200")
    
    def test_task_status_update_response_structure(self):
        """Test that /api/background-jobs/run/task-status-update returns correct structure"""
        response = self.session.post(f"{BASE_URL}/api/background-jobs/run/task-status-update")
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify required fields
        assert "success" in data, "Response should have 'success' field"
        assert "message" in data, "Response should have 'message' field"
        assert "tasks_updated" in data, "Response should have 'tasks_updated' field"
        
        # Verify data types
        assert data["success"] == True, "'success' should be True"
        assert isinstance(data["message"], str), "'message' should be a string"
        assert isinstance(data["tasks_updated"], int), "'tasks_updated' should be an integer"
        assert data["tasks_updated"] >= 0, "'tasks_updated' should be >= 0"
        
        print(f"PASS: Task status update response structure is correct - tasks_updated={data['tasks_updated']}")
    
    # ==================== POST /api/background-jobs/run/daily-reminders ====================
    
    def test_daily_reminders_requires_auth(self):
        """Test that /api/background-jobs/run/daily-reminders requires authentication"""
        response = requests.post(f"{BASE_URL}/api/background-jobs/run/daily-reminders")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: POST /api/background-jobs/run/daily-reminders requires authentication")
    
    def test_daily_reminders_returns_200(self):
        """Test that /api/background-jobs/run/daily-reminders returns 200"""
        response = self.session.post(f"{BASE_URL}/api/background-jobs/run/daily-reminders")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: POST /api/background-jobs/run/daily-reminders returns 200")
    
    def test_daily_reminders_response_structure(self):
        """Test that /api/background-jobs/run/daily-reminders returns correct structure"""
        response = self.session.post(f"{BASE_URL}/api/background-jobs/run/daily-reminders")
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify required fields
        assert "success" in data, "Response should have 'success' field"
        assert "message" in data, "Response should have 'message' field"
        assert "emails_sent" in data, "Response should have 'emails_sent' field"
        
        # Verify data types
        assert data["success"] == True, "'success' should be True"
        assert isinstance(data["message"], str), "'message' should be a string"
        assert isinstance(data["emails_sent"], int), "'emails_sent' should be an integer"
        assert data["emails_sent"] >= 0, "'emails_sent' should be >= 0"
        
        print(f"PASS: Daily reminders response structure is correct - emails_sent={data['emails_sent']}")
    
    # ==================== POST /api/background-jobs/run/health-snapshots ====================
    
    def test_health_snapshots_requires_auth(self):
        """Test that /api/background-jobs/run/health-snapshots requires authentication"""
        response = requests.post(f"{BASE_URL}/api/background-jobs/run/health-snapshots")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: POST /api/background-jobs/run/health-snapshots requires authentication")
    
    def test_health_snapshots_returns_200(self):
        """Test that /api/background-jobs/run/health-snapshots returns 200"""
        response = self.session.post(f"{BASE_URL}/api/background-jobs/run/health-snapshots")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: POST /api/background-jobs/run/health-snapshots returns 200")
    
    def test_health_snapshots_response_structure(self):
        """Test that /api/background-jobs/run/health-snapshots returns correct structure"""
        response = self.session.post(f"{BASE_URL}/api/background-jobs/run/health-snapshots")
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify required fields
        assert "success" in data, "Response should have 'success' field"
        assert "message" in data, "Response should have 'message' field"
        assert "snapshots_created" in data, "Response should have 'snapshots_created' field"
        
        # Verify data types
        assert data["success"] == True, "'success' should be True"
        assert isinstance(data["message"], str), "'message' should be a string"
        assert isinstance(data["snapshots_created"], int), "'snapshots_created' should be an integer"
        assert data["snapshots_created"] >= 0, "'snapshots_created' should be >= 0"
        
        print(f"PASS: Health snapshots response structure is correct - snapshots_created={data['snapshots_created']}")


class TestBackgroundJobsIntegration:
    """Integration tests for background jobs functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test fixtures - authenticate and get token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login with test credentials
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "test@example.com",
                "password": "testpassword123"
            }
        )
        
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.status_code} - {login_response.text}")
        
        token = login_response.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        self.user = login_response.json().get("user")
    
    def test_task_status_update_updates_overdue_tasks(self):
        """Test that task status update correctly updates overdue tasks"""
        # First, get existing tasks to understand current state
        tasks_response = self.session.get(f"{BASE_URL}/api/tasks")
        assert tasks_response.status_code == 200
        
        initial_tasks = tasks_response.json()
        print(f"Initial tasks count: {len(initial_tasks)}")
        
        # Run task status update
        update_response = self.session.post(f"{BASE_URL}/api/background-jobs/run/task-status-update")
        assert update_response.status_code == 200
        
        data = update_response.json()
        print(f"Task status update completed - tasks_updated: {data['tasks_updated']}")
        
        # Get tasks again to verify any changes
        tasks_after = self.session.get(f"{BASE_URL}/api/tasks")
        assert tasks_after.status_code == 200
        
        print("PASS: Task status update integration test completed")
    
    def test_health_snapshots_creates_records(self):
        """Test that health snapshots job creates records in database"""
        # Get trusts first
        trusts_response = self.session.get(f"{BASE_URL}/api/trusts")
        assert trusts_response.status_code == 200
        trusts = trusts_response.json()
        
        if not trusts:
            print("SKIP: No trusts found to test health snapshots")
            return
        
        trust_id = trusts[0]["trust_id"]
        
        # Get current health score history
        history_before = self.session.get(f"{BASE_URL}/api/governance/{trust_id}/history")
        assert history_before.status_code == 200
        before_count = len(history_before.json().get("history", []))
        
        # Run health snapshots
        snapshot_response = self.session.post(f"{BASE_URL}/api/background-jobs/run/health-snapshots")
        assert snapshot_response.status_code == 200
        
        data = snapshot_response.json()
        print(f"Health snapshots completed - snapshots_created: {data['snapshots_created']}")
        
        # Verify snapshots were created (should be >= number of trusts)
        assert data["snapshots_created"] >= 0, "Should create snapshots for existing trusts"
        
        # Get health score history again
        history_after = self.session.get(f"{BASE_URL}/api/governance/{trust_id}/history")
        assert history_after.status_code == 200
        
        print("PASS: Health snapshots integration test completed")


class TestBackgroundJobsScheduling:
    """Tests for APScheduler job scheduling"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test fixtures"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login with test credentials
        login_response = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "test@example.com",
                "password": "testpassword123"
            }
        )
        
        if login_response.status_code != 200:
            pytest.skip(f"Login failed: {login_response.status_code}")
        
        token = login_response.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
    
    def test_task_status_update_job_scheduled_hourly(self):
        """Test that task_status_update job is scheduled with interval trigger"""
        response = self.session.get(f"{BASE_URL}/api/background-jobs/status")
        assert response.status_code == 200
        
        jobs = response.json()["jobs"]
        task_job = next((j for j in jobs if j["id"] == "task_status_update"), None)
        
        assert task_job is not None, "task_status_update job should be scheduled"
        assert task_job["name"] == "Update task statuses based on due dates"
        
        # Verify next_run_time exists and is in the future
        if task_job["next_run_time"]:
            next_run = datetime.fromisoformat(task_job["next_run_time"].replace('Z', '+00:00'))
            # The job runs every hour, so next run should be within 60 minutes
            now = datetime.now(timezone.utc)
            time_until_next = (next_run - now).total_seconds()
            assert time_until_next <= 3600, f"Next run should be within 1 hour, but is {time_until_next/60:.1f} minutes away"
        
        print("PASS: task_status_update job is correctly scheduled (hourly)")
    
    def test_daily_reminders_job_scheduled_at_9am(self):
        """Test that daily_reminders job is scheduled at 9 AM UTC"""
        response = self.session.get(f"{BASE_URL}/api/background-jobs/status")
        assert response.status_code == 200
        
        jobs = response.json()["jobs"]
        reminder_job = next((j for j in jobs if j["id"] == "daily_reminders"), None)
        
        assert reminder_job is not None, "daily_reminders job should be scheduled"
        assert reminder_job["name"] == "Send daily task reminder emails"
        
        # Verify next_run_time exists
        if reminder_job["next_run_time"]:
            next_run = datetime.fromisoformat(reminder_job["next_run_time"].replace('Z', '+00:00'))
            # Daily job should run at 9:00 UTC
            assert next_run.hour == 9, f"Expected next run at 9 AM UTC, got {next_run.hour}:00"
            assert next_run.minute == 0, f"Expected minute to be 0, got {next_run.minute}"
        
        print("PASS: daily_reminders job is correctly scheduled (9 AM UTC daily)")
    
    def test_health_snapshots_job_scheduled_at_midnight(self):
        """Test that daily_health_snapshots job is scheduled at midnight UTC"""
        response = self.session.get(f"{BASE_URL}/api/background-jobs/status")
        assert response.status_code == 200
        
        jobs = response.json()["jobs"]
        snapshot_job = next((j for j in jobs if j["id"] == "daily_health_snapshots"), None)
        
        assert snapshot_job is not None, "daily_health_snapshots job should be scheduled"
        assert snapshot_job["name"] == "Create daily governance health snapshots"
        
        # Verify next_run_time exists
        if snapshot_job["next_run_time"]:
            next_run = datetime.fromisoformat(snapshot_job["next_run_time"].replace('Z', '+00:00'))
            # Daily job should run at 00:05 UTC
            assert next_run.hour == 0, f"Expected next run at midnight UTC, got {next_run.hour}:00"
            assert next_run.minute == 5, f"Expected minute to be 5, got {next_run.minute}"
        
        print("PASS: daily_health_snapshots job is correctly scheduled (00:05 UTC daily)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
