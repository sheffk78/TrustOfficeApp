"""
Test suite for Admin Impersonation Feature
Tests the user impersonation functionality for admin panel

Features tested:
- POST /api/admin/impersonate/{user_id} - Generate token for target user
- POST /api/admin/impersonation/log-exit - Log when admin exits impersonation
- GET /api/admin/impersonation/audit-log - Get audit log of impersonation actions
- Security: Cannot impersonate admin accounts
- Security: Requires admin authentication
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://trust-governance-fix.preview.emergentagent.com')

# Test credentials
ADMIN_EMAIL = "contact@trustoffice.app"
ADMIN_PASSWORD = "TrustAdmin2026!"


class TestImpersonationFeature:
    """Test suite for admin impersonation functionality"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in login response"
        return data["token"]
    
    @pytest.fixture(scope="class")
    def admin_user_id(self, admin_token):
        """Get admin user ID"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        return response.json()["user_id"]
    
    @pytest.fixture(scope="class")
    def non_admin_user(self, admin_token):
        """Get a non-admin user to impersonate"""
        response = requests.get(
            f"{BASE_URL}/api/admin/customers?limit=10",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        customers = response.json()["customers"]
        
        # Find a non-admin user
        for customer in customers:
            if not customer.get("is_admin", False):
                return customer
        
        pytest.skip("No non-admin users found to test impersonation")
    
    # ==================== IMPERSONATE ENDPOINT TESTS ====================
    
    def test_impersonate_non_admin_user_success(self, admin_token, non_admin_user):
        """Test successful impersonation of a non-admin user"""
        response = requests.post(
            f"{BASE_URL}/api/admin/impersonate/{non_admin_user['user_id']}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200, f"Impersonation failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "token" in data, "No token in impersonation response"
        assert "user" in data, "No user data in impersonation response"
        assert "message" in data, "No message in impersonation response"
        
        # Verify user data matches target
        assert data["user"]["user_id"] == non_admin_user["user_id"]
        assert data["user"]["email"] == non_admin_user["email"]
        
        # Verify token is valid by using it
        verify_response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {data['token']}"}
        )
        assert verify_response.status_code == 200
        assert verify_response.json()["user_id"] == non_admin_user["user_id"]
    
    def test_impersonate_admin_blocked(self, admin_token, admin_user_id):
        """Test that impersonating admin accounts is blocked"""
        response = requests.post(
            f"{BASE_URL}/api/admin/impersonate/{admin_user_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        data = response.json()
        assert "Cannot impersonate admin accounts" in data.get("detail", "")
    
    def test_impersonate_nonexistent_user(self, admin_token):
        """Test impersonating a non-existent user returns 404"""
        response = requests.post(
            f"{BASE_URL}/api/admin/impersonate/user_nonexistent123",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        data = response.json()
        assert "not found" in data.get("detail", "").lower()
    
    def test_impersonate_without_auth(self, non_admin_user):
        """Test that impersonation requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/admin/impersonate/{non_admin_user['user_id']}"
        )
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    
    def test_impersonate_with_non_admin_token(self, non_admin_user, admin_token):
        """Test that non-admin users cannot impersonate"""
        # First get a token for the non-admin user via impersonation
        impersonate_response = requests.post(
            f"{BASE_URL}/api/admin/impersonate/{non_admin_user['user_id']}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert impersonate_response.status_code == 200
        non_admin_token = impersonate_response.json()["token"]
        
        # Try to impersonate using the non-admin token
        response = requests.post(
            f"{BASE_URL}/api/admin/impersonate/{non_admin_user['user_id']}",
            headers={"Authorization": f"Bearer {non_admin_token}"}
        )
        
        # Should get 403 - either for admin access or subscription (both are valid blocks)
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        detail = response.json().get("detail", "")
        # Either admin access required or subscription inactive - both are valid blocks
        assert "Admin access required" in detail or "subscription" in detail.lower()
    
    # ==================== AUDIT LOG TESTS ====================
    
    def test_audit_log_records_impersonation(self, admin_token, non_admin_user):
        """Test that impersonation actions are recorded in audit log"""
        # Perform an impersonation
        requests.post(
            f"{BASE_URL}/api/admin/impersonate/{non_admin_user['user_id']}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Check audit log
        response = requests.get(
            f"{BASE_URL}/api/admin/impersonation/audit-log",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "logs" in data
        assert "total" in data
        assert len(data["logs"]) > 0
        
        # Verify log structure
        latest_log = data["logs"][0]
        assert "audit_id" in latest_log
        assert "action" in latest_log
        assert "admin_user_id" in latest_log
        assert "admin_email" in latest_log
        assert "timestamp" in latest_log
        
        # Verify the impersonation was logged
        impersonation_logs = [log for log in data["logs"] if log["action"] == "impersonate_user"]
        assert len(impersonation_logs) > 0
    
    def test_audit_log_pagination(self, admin_token):
        """Test audit log pagination"""
        response = requests.get(
            f"{BASE_URL}/api/admin/impersonation/audit-log?page=1&limit=5",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "logs" in data
        assert "total" in data
        assert "page" in data
        assert "pages" in data
        assert data["page"] == 1
    
    def test_audit_log_requires_admin(self, admin_token, non_admin_user):
        """Test that audit log requires admin access"""
        # Get non-admin token
        impersonate_response = requests.post(
            f"{BASE_URL}/api/admin/impersonate/{non_admin_user['user_id']}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        non_admin_token = impersonate_response.json()["token"]
        
        # Try to access audit log with non-admin token
        response = requests.get(
            f"{BASE_URL}/api/admin/impersonation/audit-log",
            headers={"Authorization": f"Bearer {non_admin_token}"}
        )
        
        assert response.status_code == 403
    
    # ==================== LOG EXIT TESTS ====================
    
    def test_log_exit_success(self, admin_token):
        """Test logging impersonation exit"""
        response = requests.post(
            f"{BASE_URL}/api/admin/impersonation/log-exit",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "ended" in data["message"].lower()
    
    def test_log_exit_recorded_in_audit(self, admin_token):
        """Test that exit is recorded in audit log"""
        # Log an exit
        requests.post(
            f"{BASE_URL}/api/admin/impersonation/log-exit",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Check audit log
        response = requests.get(
            f"{BASE_URL}/api/admin/impersonation/audit-log",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify exit was logged
        exit_logs = [log for log in data["logs"] if log["action"] == "exit_impersonation"]
        assert len(exit_logs) > 0
    
    def test_log_exit_requires_admin(self, admin_token, non_admin_user):
        """Test that log-exit requires admin access"""
        # Get non-admin token
        impersonate_response = requests.post(
            f"{BASE_URL}/api/admin/impersonate/{non_admin_user['user_id']}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        non_admin_token = impersonate_response.json()["token"]
        
        # Try to log exit with non-admin token
        response = requests.post(
            f"{BASE_URL}/api/admin/impersonation/log-exit",
            headers={"Authorization": f"Bearer {non_admin_token}"}
        )
        
        assert response.status_code == 403


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
