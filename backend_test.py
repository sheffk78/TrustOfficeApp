import requests
import sys
import json
from datetime import datetime, timedelta
import uuid

class TrustOfficeAPITester:
    def __init__(self, base_url="https://trustee-hub.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.session_token = None
        self.user_id = None
        self.trust_id = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_test(self, name, success, details=""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
        
        result = {
            "test": name,
            "success": success,
            "details": details
        }
        self.test_results.append(result)
        
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {name}")
        if details:
            print(f"   {details}")
        return success

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.api_url}/{endpoint}"
        test_headers = {'Content-Type': 'application/json'}
        
        # Add session token if available
        if self.session_token:
            test_headers['Authorization'] = f'Bearer {self.session_token}'
        
        # Add any additional headers
        if headers:
            test_headers.update(headers)

        try:
            if method == 'GET':
                response = requests.get(url, headers=test_headers)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=test_headers)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=test_headers)
            elif method == 'DELETE':
                response = requests.delete(url, headers=test_headers)

            success = response.status_code == expected_status
            details = f"Status: {response.status_code}"
            
            if not success:
                try:
                    error_data = response.json()
                    details += f" | Error: {error_data.get('detail', 'Unknown error')}"
                except:
                    details += f" | Response: {response.text[:100]}"
            
            return self.log_test(name, success, details), response

        except Exception as e:
            return self.log_test(name, False, f"Exception: {str(e)}"), None

    def test_health_check(self):
        """Test basic API health"""
        try:
            response = requests.get(f"{self.base_url}/docs", timeout=10)
            return self.log_test("API Health Check", response.status_code == 200, f"Docs endpoint: {response.status_code}")
        except Exception as e:
            return self.log_test("API Health Check", False, f"Connection failed: {str(e)}")

    def test_user_registration(self):
        """Test user registration"""
        test_email = f"test.user.{int(datetime.now().timestamp())}@example.com"
        user_data = {
            "email": test_email,
            "password": "TestPass123!",
            "name": "Test User"
        }
        
        success, response = self.run_test(
            "User Registration",
            "POST",
            "auth/register",
            200,
            data=user_data
        )
        
        if success and response:
            try:
                user_info = response.json()
                self.user_id = user_info.get('user_id')
                return True, test_email, "TestPass123!"
            except:
                return False, None, None
        return False, None, None

    def test_user_login(self, email, password):
        """Test user login"""
        login_data = {
            "email": email,
            "password": password
        }
        
        success, response = self.run_test(
            "User Login",
            "POST",
            "auth/login",
            200,
            data=login_data
        )
        
        if success and response:
            try:
                login_info = response.json()
                self.session_token = login_info.get('token')
                user_info = login_info.get('user', {})
                self.user_id = user_info.get('user_id')
                return True
            except:
                return False
        return False

    def test_auth_me(self):
        """Test get current user"""
        if not self.session_token:
            return self.log_test("Get Current User", False, "No session token available")
        
        success, response = self.run_test(
            "Get Current User",
            "GET",
            "auth/me",
            200
        )
        return success

    def test_create_trust(self):
        """Test creating a trust"""
        if not self.session_token:
            return self.log_test("Create Trust", False, "Not authenticated")
        
        trust_data = {
            "name": f"Test Trust {int(datetime.now().timestamp())}",
            "role": "Trustee", 
            "review_cadence": "quarterly",
            "description": "Test trust for API testing"
        }
        
        success, response = self.run_test(
            "Create Trust",
            "POST",
            "trusts",
            200,
            data=trust_data
        )
        
        if success and response:
            try:
                trust_info = response.json()
                self.trust_id = trust_info.get('trust_id')
                return True
            except:
                return False
        return False

    def test_get_trusts(self):
        """Test getting trusts list"""
        if not self.session_token:
            return self.log_test("Get Trusts", False, "Not authenticated")
        
        success, response = self.run_test(
            "Get Trusts",
            "GET",
            "trusts",
            200
        )
        return success

    def test_create_minutes(self):
        """Test creating minutes entry"""
        if not self.trust_id:
            return self.log_test("Create Minutes", False, "No trust available")
        
        minutes_data = {
            "trust_id": self.trust_id,
            "entry_type": "meeting",
            "date": datetime.now().isoformat(),
            "participants": ["Test User", "Jane Doe"],
            "summary": "Test meeting minutes",
            "details": "This is a test meeting entry for API testing purposes.",
            "best_interest_rationale": "Testing API functionality is in the best interest of the trust."
        }
        
        success, response = self.run_test(
            "Create Minutes",
            "POST",
            "minutes",
            200,
            data=minutes_data
        )
        return success

    def test_get_minutes(self):
        """Test getting minutes list"""
        if not self.trust_id:
            return self.log_test("Get Minutes", False, "No trust available")
        
        success, response = self.run_test(
            "Get Minutes",
            "GET",
            f"minutes?trust_id={self.trust_id}",
            200
        )
        return success

    def test_create_distribution(self):
        """Test creating distribution"""
        if not self.trust_id:
            return self.log_test("Create Distribution", False, "No trust available")
        
        dist_data = {
            "trust_id": self.trust_id,
            "date": datetime.now().isoformat(),
            "amount": 1000.00,
            "distribution_type": "trust_distribution",
            "beneficiary": "Test Beneficiary",
            "category": "Education",
            "notes": "Test distribution for API testing",
            "status": "review"
        }
        
        success, response = self.run_test(
            "Create Distribution",
            "POST",
            "distributions",
            200,
            data=dist_data
        )
        return success

    def test_get_distributions(self):
        """Test getting distributions list"""
        if not self.trust_id:
            return self.log_test("Get Distributions", False, "No trust available")
        
        success, response = self.run_test(
            "Get Distributions",
            "GET",
            f"distributions?trust_id={self.trust_id}",
            200
        )
        return success

    def test_create_expense(self):
        """Test creating expense"""
        if not self.trust_id:
            return self.log_test("Create Expense", False, "No trust available")
        
        expense_data = {
            "trust_id": self.trust_id,
            "date": datetime.now().isoformat(),
            "amount": 500.00,
            "payee": "Test Legal Firm",
            "category": "Legal",
            "notes": "Test expense for API testing",
            "status": "review"
        }
        
        success, response = self.run_test(
            "Create Expense",
            "POST",
            "expenses",
            200,
            data=expense_data
        )
        return success

    def test_get_expenses(self):
        """Test getting expenses list"""
        if not self.trust_id:
            return self.log_test("Get Expenses", False, "No trust available")
        
        success, response = self.run_test(
            "Get Expenses",
            "GET",
            f"expenses?trust_id={self.trust_id}",
            200
        )
        return success

    def test_governance_health(self):
        """Test governance health endpoint"""
        if not self.trust_id:
            return self.log_test("Governance Health", False, "No trust available")
        
        success, response = self.run_test(
            "Governance Health",
            "GET",
            f"governance/{self.trust_id}",
            200
        )
        return success

    def test_activity_timeline(self):
        """Test activity timeline"""
        if not self.trust_id:
            return self.log_test("Activity Timeline", False, "No trust available")
        
        success, response = self.run_test(
            "Activity Timeline",
            "GET",
            f"activity?trust_id={self.trust_id}&limit=10",
            200
        )
        return success

    def test_categories(self):
        """Test categories endpoint"""
        success, response = self.run_test(
            "Get Categories",
            "GET",
            "categories",
            200
        )
        return success

    def test_demo_seed(self):
        """Test demo data seeding"""
        if not self.session_token:
            return self.log_test("Demo Seed", False, "Not authenticated")
        
        success, response = self.run_test(
            "Demo Seed Data",
            "POST",
            "demo/seed",
            200
        )
        return success

    def run_full_test_suite(self):
        """Run all tests"""
        print("🚀 Starting TrustOffice API Tests")
        print("=" * 50)
        
        # Health check
        if not self.test_health_check():
            print("❌ API is not accessible, stopping tests")
            return False
        
        # Authentication flow
        success, email, password = self.test_user_registration()
        if not success:
            print("❌ User registration failed, stopping tests")
            return False
        
        if not self.test_user_login(email, password):
            print("❌ User login failed, stopping tests") 
            return False
        
        if not self.test_auth_me():
            print("❌ Auth verification failed, stopping tests")
            return False
        
        # Trust management
        if not self.test_create_trust():
            print("❌ Trust creation failed, stopping tests")
            return False
        
        self.test_get_trusts()
        
        # Core functionality
        self.test_create_minutes()
        self.test_get_minutes()
        self.test_create_distribution() 
        self.test_get_distributions()
        self.test_create_expense()
        self.test_get_expenses()
        
        # Additional features
        self.test_governance_health()
        self.test_activity_timeline()
        self.test_categories()
        
        # Demo data (only if user has no other trusts)
        # self.test_demo_seed()  # Commenting out to avoid conflicts
        
        # Print results
        print("\n" + "=" * 50)
        print(f"📊 Test Results: {self.tests_passed}/{self.tests_run} passed")
        
        if self.tests_passed < self.tests_run:
            print("\n❌ Failed Tests:")
            for result in self.test_results:
                if not result["success"]:
                    print(f"   - {result['test']}: {result['details']}")
        
        return self.tests_passed == self.tests_run

def main():
    tester = TrustOfficeAPITester()
    success = tester.run_full_test_suite()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())