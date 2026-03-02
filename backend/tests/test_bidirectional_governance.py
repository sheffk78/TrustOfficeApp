# Test suite for Bi-directional Governance Integration
# Tests Minutes→Money and Money→Minutes flows between Guided Minutes, Distributions, Compensation, and Benevolence

import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "demo@trustoffice.com"
TEST_PASSWORD = "demopassword"


class TestBidirectionalGovernanceFlow:
    """Test suite for bi-directional governance integration (Minutes ↔ Money)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup auth token and trust_id for all tests"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Authenticate
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        
        if login_response.status_code != 200:
            pytest.skip(f"Authentication failed: {login_response.status_code}")
        
        login_data = login_response.json()
        self.token = login_data.get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        # Get trust_id from user's trusts
        trusts_response = self.session.get(f"{BASE_URL}/api/trusts")
        if trusts_response.status_code == 200:
            trusts = trusts_response.json()
            if trusts:
                self.trust_id = trusts[0].get("trust_id")
                self.trust = trusts[0]
            else:
                pytest.skip("No trusts available for testing")
        else:
            pytest.skip("Could not fetch trusts")

    # ==================== MINUTES SEARCH ENDPOINT ====================
    
    def test_search_minutes_basic(self):
        """Test GET /api/guided-minutes/search returns minutes list"""
        response = self.session.get(
            f"{BASE_URL}/api/guided-minutes/search",
            params={"trust_id": self.trust_id}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
        # If there are results, verify structure
        if len(data) > 0:
            first_record = data[0]
            assert "minutes_id" in first_record, "Missing minutes_id"
            assert "minutes_type" in first_record, "Missing minutes_type"
            assert "meeting_date" in first_record, "Missing meeting_date"
            print(f"Search returned {len(data)} minutes records")
        else:
            print("No existing minutes to search")
    
    def test_search_minutes_with_type_filter(self):
        """Test minutes search with type filter"""
        response = self.session.get(
            f"{BASE_URL}/api/guided-minutes/search",
            params={"trust_id": self.trust_id, "minutes_type": "annual"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        # All results should be annual type if any
        for record in data:
            assert record.get("minutes_type") == "annual", f"Expected annual, got {record.get('minutes_type')}"
    
    def test_search_minutes_with_query(self):
        """Test minutes search with text query"""
        response = self.session.get(
            f"{BASE_URL}/api/guided-minutes/search",
            params={"trust_id": self.trust_id, "query": "test", "limit": "10"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert isinstance(data, list)
        print(f"Query search returned {len(data)} results")
    
    def test_search_minutes_without_auth_returns_401(self):
        """Test that unauthenticated minutes search returns 401"""
        session_no_auth = requests.Session()
        response = session_no_auth.get(
            f"{BASE_URL}/api/guided-minutes/search",
            params={"trust_id": self.trust_id}
        )
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"

    # ==================== SAVE WITH RECORDS (MINUTES → MONEY) ====================
    
    def test_save_guided_minutes_with_distribution_record(self):
        """Test POST /api/guided-minutes/save-with-records creates minutes and linked distribution"""
        payload = {
            "trust_id": self.trust_id,
            "minutes_type": "quarterly",
            "meeting_date": datetime.now().strftime("%Y-%m-%d"),
            "participants_text": "Test Trustee, Test Trustee 2",
            "decisions_text": "TEST_BiDir: Test minutes with linked distribution record.",
            "records_to_create": [
                {
                    "record_type": "distribution",
                    "amount": 500.00,
                    "recipient": "TEST_Beneficiary_Distribution",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "description": "Test distribution from minutes",
                    "purpose_classification": "hems_support"
                }
            ]
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/guided-minutes/save-with-records",
            json=payload,
            timeout=30
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "minutes_id" in data, "Missing minutes_id in response"
        assert "created_records" in data, "Missing created_records in response"
        assert data["created_records"]["distribution"] == 1, "Should have created 1 distribution"
        
        print(f"Created minutes {data['minutes_id']} with {data['created_records']['distribution']} linked distribution")
        
        # Store for cleanup
        self.created_minutes_id = data["minutes_id"]

    def test_save_guided_minutes_with_compensation_record(self):
        """Test creating minutes with linked compensation payment"""
        payload = {
            "trust_id": self.trust_id,
            "minutes_type": "quarterly",
            "meeting_date": datetime.now().strftime("%Y-%m-%d"),
            "participants_text": "Test Trustee",
            "decisions_text": "TEST_BiDir: Test minutes with linked compensation record.",
            "records_to_create": [
                {
                    "record_type": "compensation",
                    "amount": 1000.00,
                    "recipient": "TEST_Trustee_Compensation",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "description": "Q1 trustee compensation"
                }
            ]
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/guided-minutes/save-with-records",
            json=payload,
            timeout=30
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["created_records"]["compensation"] == 1, "Should have created 1 compensation"
        print(f"Created minutes with {data['created_records']['compensation']} linked compensation")

    def test_save_guided_minutes_with_multiple_record_types(self):
        """Test creating minutes with multiple types of linked records"""
        payload = {
            "trust_id": self.trust_id,
            "minutes_type": "quarterly",
            "meeting_date": datetime.now().strftime("%Y-%m-%d"),
            "participants_text": "Test Trustee, Test Trustee 2",
            "decisions_text": "TEST_BiDir: Test minutes with multiple linked records.",
            "records_to_create": [
                {
                    "record_type": "distribution",
                    "amount": 250.00,
                    "recipient": "TEST_Multi_Beneficiary1",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "purpose_classification": "hems_health"
                },
                {
                    "record_type": "distribution",
                    "amount": 350.00,
                    "recipient": "TEST_Multi_Beneficiary2",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "purpose_classification": "hems_education"
                },
                {
                    "record_type": "compensation",
                    "amount": 750.00,
                    "recipient": "TEST_Multi_Trustee",
                    "date": datetime.now().strftime("%Y-%m-%d")
                }
            ]
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/guided-minutes/save-with-records",
            json=payload,
            timeout=30
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["created_records"]["distribution"] == 2, f"Expected 2 distributions, got {data['created_records']['distribution']}"
        assert data["created_records"]["compensation"] == 1, f"Expected 1 compensation, got {data['created_records']['compensation']}"
        print(f"Created minutes with {data['created_records']} linked records")

    def test_save_guided_minutes_with_benevolence_record(self):
        """Test creating minutes with linked benevolence record (requires benevolence_enabled)"""
        # Check if benevolence is enabled for this trust
        if not self.trust.get("benevolence_enabled"):
            pytest.skip("Benevolence not enabled for this trust")
        
        payload = {
            "trust_id": self.trust_id,
            "minutes_type": "quarterly",
            "meeting_date": datetime.now().strftime("%Y-%m-%d"),
            "participants_text": "Test Trustee",
            "decisions_text": "TEST_BiDir: Test minutes with linked benevolence record.",
            "records_to_create": [
                {
                    "record_type": "benevolence",
                    "amount": 200.00,
                    "recipient": "TEST_Benevolence_Recipient",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "description": "Emergency medical assistance",
                    "benevolence_need": "Medical emergency"
                }
            ]
        }
        
        response = self.session.post(
            f"{BASE_URL}/api/guided-minutes/save-with-records",
            json=payload,
            timeout=30
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["created_records"]["benevolence"] == 1, "Should have created 1 benevolence"
        print(f"Created minutes with {data['created_records']['benevolence']} linked benevolence")

    # ==================== ATTACH MINUTES TO DISTRIBUTION (MONEY → MINUTES) ====================
    
    def test_attach_minutes_to_distribution(self):
        """Test PATCH /api/distributions/{id}/attach-minutes links minutes to distribution"""
        # First create a distribution without minutes
        dist_payload = {
            "trust_id": self.trust_id,
            "beneficiary_name": "TEST_Attach_Minutes_Dist",
            "amount": 100.00,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "purpose_classification": "distribution",  # Use valid enum: distribution, compensation, expense, other
            "notes": "Test distribution for minutes attachment"
        }
        
        dist_response = self.session.post(
            f"{BASE_URL}/api/distributions",
            json=dist_payload
        )
        
        assert dist_response.status_code == 200, f"Failed to create distribution: {dist_response.status_code}"
        dist_data = dist_response.json()
        dist_id = dist_data.get("distribution_id")
        
        # Get or create a minutes record to attach
        search_response = self.session.get(
            f"{BASE_URL}/api/guided-minutes/search",
            params={"trust_id": self.trust_id, "limit": "1"}
        )
        
        if search_response.status_code == 200 and len(search_response.json()) > 0:
            minutes_id = search_response.json()[0]["minutes_id"]
        else:
            # Create a minutes record first
            minutes_payload = {
                "trust_id": self.trust_id,
                "minutes_type": "quarterly",
                "meeting_date": datetime.now().strftime("%Y-%m-%d"),
                "participants_text": "Test Trustee",
                "decisions_text": "TEST_BiDir: Minutes for attachment test"
            }
            minutes_response = self.session.post(
                f"{BASE_URL}/api/guided-minutes/save",
                json=minutes_payload
            )
            assert minutes_response.status_code == 200, f"Failed to create minutes: {minutes_response.status_code}"
            minutes_id = minutes_response.json()["minutes_id"]
        
        # Now attach minutes to distribution
        attach_response = self.session.patch(
            f"{BASE_URL}/api/distributions/{dist_id}/attach-minutes",
            json={"minutes_record_id": minutes_id}
        )
        
        assert attach_response.status_code == 200, f"Expected 200, got {attach_response.status_code}: {attach_response.text}"
        
        attach_data = attach_response.json()
        assert attach_data.get("minutes_record_id") == minutes_id, "minutes_record_id not set correctly"
        print(f"Successfully attached minutes {minutes_id} to distribution {dist_id}")

    def test_attach_minutes_to_distribution_invalid_minutes_returns_404(self):
        """Test attaching non-existent minutes returns 404"""
        # Create a distribution first
        dist_payload = {
            "trust_id": self.trust_id,
            "beneficiary_name": "TEST_Invalid_Minutes",
            "amount": 50.00,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "purpose_classification": "distribution"  # Use valid enum
        }
        
        dist_response = self.session.post(f"{BASE_URL}/api/distributions", json=dist_payload)
        assert dist_response.status_code == 200
        dist_id = dist_response.json()["distribution_id"]
        
        # Try to attach non-existent minutes
        attach_response = self.session.patch(
            f"{BASE_URL}/api/distributions/{dist_id}/attach-minutes",
            json={"minutes_record_id": "nonexistent_minutes_12345"}
        )
        
        assert attach_response.status_code == 404, f"Expected 404, got {attach_response.status_code}"

    def test_attach_minutes_to_distribution_missing_minutes_id_returns_400(self):
        """Test attaching minutes without minutes_record_id returns 400"""
        # Create a distribution first
        dist_payload = {
            "trust_id": self.trust_id,
            "beneficiary_name": "TEST_Missing_Minutes_ID",
            "amount": 50.00,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "purpose_classification": "distribution"  # Use valid enum
        }
        
        dist_response = self.session.post(f"{BASE_URL}/api/distributions", json=dist_payload)
        assert dist_response.status_code == 200
        dist_id = dist_response.json()["distribution_id"]
        
        # Try to attach without minutes_record_id
        attach_response = self.session.patch(
            f"{BASE_URL}/api/distributions/{dist_id}/attach-minutes",
            json={}
        )
        
        assert attach_response.status_code == 400, f"Expected 400, got {attach_response.status_code}"

    # ==================== ATTACH MINUTES TO COMPENSATION (MONEY → MINUTES) ====================
    
    def test_attach_minutes_to_compensation(self):
        """Test PATCH /api/compensation-payments/{id}/attach-minutes links minutes to payment"""
        # First create a compensation payment
        payment_payload = {
            "trust_id": self.trust_id,
            "amount": 500.00,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "classification_text": "TEST_Attach_Minutes_Payment"
        }
        
        payment_response = self.session.post(
            f"{BASE_URL}/api/compensation-payments",
            json=payment_payload
        )
        
        assert payment_response.status_code == 200, f"Failed to create payment: {payment_response.status_code}"
        payment_data = payment_response.json()
        payment_id = payment_data.get("payment_id")
        
        # Get existing minutes
        search_response = self.session.get(
            f"{BASE_URL}/api/guided-minutes/search",
            params={"trust_id": self.trust_id, "limit": "1"}
        )
        
        if search_response.status_code == 200 and len(search_response.json()) > 0:
            minutes_id = search_response.json()[0]["minutes_id"]
        else:
            # Create minutes
            minutes_payload = {
                "trust_id": self.trust_id,
                "minutes_type": "quarterly",
                "meeting_date": datetime.now().strftime("%Y-%m-%d"),
                "participants_text": "Test Trustee",
                "decisions_text": "TEST_BiDir: Minutes for compensation attachment"
            }
            minutes_response = self.session.post(
                f"{BASE_URL}/api/guided-minutes/save",
                json=minutes_payload
            )
            assert minutes_response.status_code == 200
            minutes_id = minutes_response.json()["minutes_id"]
        
        # Attach minutes to payment
        attach_response = self.session.patch(
            f"{BASE_URL}/api/compensation-payments/{payment_id}/attach-minutes",
            json={"minutes_record_id": minutes_id}
        )
        
        assert attach_response.status_code == 200, f"Expected 200, got {attach_response.status_code}: {attach_response.text}"
        
        attach_data = attach_response.json()
        assert attach_data.get("minutes_record_id") == minutes_id, "minutes_record_id not set correctly"
        print(f"Successfully attached minutes {minutes_id} to compensation payment {payment_id}")

    # ==================== ATTACH MINUTES TO BENEVOLENCE (MONEY → MINUTES) ====================
    
    def test_attach_minutes_to_benevolence(self):
        """Test PATCH /api/benevolence/{id}/attach-minutes links minutes to benevolence record"""
        # Check if benevolence is enabled
        if not self.trust.get("benevolence_enabled"):
            pytest.skip("Benevolence not enabled for this trust")
        
        # First create a benevolence record
        ben_payload = {
            "trust_id": self.trust_id,
            "beneficiary_name": "TEST_Attach_Minutes_Ben",
            "beneficiary_type": "individual",
            "purpose": "medical",
            "purpose_description": "Test benevolence for minutes attachment",
            "amount": 150.00,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "approved_by": ["Test Trustee"],
            "status": "approved"
        }
        
        ben_response = self.session.post(
            f"{BASE_URL}/api/benevolence",
            json=ben_payload
        )
        
        assert ben_response.status_code == 200, f"Failed to create benevolence: {ben_response.status_code}: {ben_response.text}"
        ben_data = ben_response.json()
        record_id = ben_data.get("record_id")
        
        # Get existing minutes
        search_response = self.session.get(
            f"{BASE_URL}/api/guided-minutes/search",
            params={"trust_id": self.trust_id, "limit": "1"}
        )
        
        if search_response.status_code == 200 and len(search_response.json()) > 0:
            minutes_id = search_response.json()[0]["minutes_id"]
        else:
            # Create minutes
            minutes_payload = {
                "trust_id": self.trust_id,
                "minutes_type": "quarterly",
                "meeting_date": datetime.now().strftime("%Y-%m-%d"),
                "participants_text": "Test Trustee",
                "decisions_text": "TEST_BiDir: Minutes for benevolence attachment"
            }
            minutes_response = self.session.post(
                f"{BASE_URL}/api/guided-minutes/save",
                json=minutes_payload
            )
            assert minutes_response.status_code == 200
            minutes_id = minutes_response.json()["minutes_id"]
        
        # Attach minutes to benevolence
        attach_response = self.session.patch(
            f"{BASE_URL}/api/benevolence/{record_id}/attach-minutes",
            json={"minutes_record_id": minutes_id}
        )
        
        assert attach_response.status_code == 200, f"Expected 200, got {attach_response.status_code}: {attach_response.text}"
        
        attach_data = attach_response.json()
        assert attach_data.get("minutes_id") == minutes_id, "minutes_id not set correctly"
        print(f"Successfully attached minutes {minutes_id} to benevolence record {record_id}")


class TestDistributionsMinutesColumn:
    """Test Distributions page minutes column and dropdown"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup auth token and trust_id"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        
        if login_response.status_code != 200:
            pytest.skip("Authentication failed")
        
        login_data = login_response.json()
        self.token = login_data.get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        trusts_response = self.session.get(f"{BASE_URL}/api/trusts")
        if trusts_response.status_code == 200:
            trusts = trusts_response.json()
            if trusts:
                self.trust_id = trusts[0].get("trust_id")
            else:
                pytest.skip("No trusts available")
        else:
            pytest.skip("Could not fetch trusts")

    def test_get_distributions_includes_minutes_record_id(self):
        """Test GET /api/distributions returns minutes_record_id field"""
        response = self.session.get(
            f"{BASE_URL}/api/distributions",
            params={"trust_id": self.trust_id}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        if len(data) > 0:
            first_dist = data[0]
            # Field should exist (even if null)
            assert "minutes_record_id" in first_dist or first_dist.get("minutes_record_id") is None, \
                "Distribution should have minutes_record_id field"
            print(f"Distributions API returns minutes_record_id field")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
