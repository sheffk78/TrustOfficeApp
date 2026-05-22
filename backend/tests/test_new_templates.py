"""
Test suite for TrustOffice new minutes templates:
- Designation of Beneficiaries
- Bank Account Authorization  
- Change of Situs
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestNewMinutesTemplates:
    """Test the 3 new minutes templates"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup authentication and get trust_id"""
        # Login
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@trustoffice.com",
            "password": "demo123"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Get trusts and use the first one
        trusts_response = requests.get(f"{BASE_URL}/api/trusts", headers=self.headers)
        if trusts_response.status_code == 200 and trusts_response.json():
            self.trust_id = trusts_response.json()[0]["trust_id"]
        else:
            # Create a trust if none exists
            create_trust = requests.post(f"{BASE_URL}/api/trusts", 
                headers=self.headers,
                json={"name": "Test Trust", "trust_type": "family"}
            )
            assert create_trust.status_code == 200
            self.trust_id = create_trust.json()["trust_id"]
    
    def test_template_options_returns_9_templates(self):
        """Verify all 9 templates are available"""
        response = requests.get(f"{BASE_URL}/api/template-options", headers=self.headers)
        assert response.status_code == 200, f"Failed to get templates: {response.text}"
        
        templates = response.json()
        assert len(templates) == 9, f"Expected 9 templates, got {len(templates)}"
        
        # Verify the 3 new templates exist
        template_types = [t["type"] for t in templates]
        assert "designation_of_beneficiaries" in template_types
        assert "bank_account_authorization" in template_types
        assert "change_of_situs" in template_types
        
        print(f"SUCCESS: All 9 templates available: {template_types}")
    
    def test_designation_of_beneficiaries_template_generation(self):
        """Test Designation of Beneficiaries template generates correct document"""
        template_data = {
            "minute_number": "2026-TEST-001",
            "meeting_date": "February 24, 2026",
            "meeting_time": "10:00 AM",
            "meeting_type": "unanimous_written_consent",
            "trustees_present": ["John Smith", "Jane Doe"],
            "trust_formation_date": "January 1, 2020",
            "designation_type": "initial",
            "total_units": 100,
            "beneficiaries": [
                {"name": "Beneficiary One", "units": 50, "percentage": 50, "relationship": "Son"},
                {"name": "Beneficiary Two", "units": 30, "percentage": 30, "relationship": "Daughter"},
                {"name": "Beneficiary Three", "units": 20, "percentage": 20, "relationship": "Spouse"}
            ]
        }
        
        response = requests.post(f"{BASE_URL}/api/minutes-templates",
            headers=self.headers,
            json={
                "trust_id": self.trust_id,
                "template_type": "designation_of_beneficiaries",
                "template_data": template_data
            }
        )
        
        assert response.status_code == 200, f"Failed to generate template: {response.text}"
        
        result = response.json()
        assert "minutes_id" in result
        assert "generated_document" in result
        
        doc = result["generated_document"]
        
        # Verify document contains beneficiary designation content
        assert "Designation of Beneficiaries" in doc, "Missing 'Designation of Beneficiaries' in document"
        assert "WHEREAS" in doc, "Missing WHEREAS clause"
        assert "RESOLVED" in doc, "Missing RESOLVED clause"
        assert "Units of Beneficial Interest" in doc, "Missing 'Units of Beneficial Interest'"
        assert "Beneficiary One" in doc, "Missing beneficiary name"
        assert "50 Units" in doc or "50%" in doc, "Missing unit/percentage allocation"
        
        # Cleanup - delete the test minutes
        delete_response = requests.delete(f"{BASE_URL}/api/minutes-templates/{result['minutes_id']}", headers=self.headers)
        
        print(f"SUCCESS: Designation of Beneficiaries template generated with ID: {result['minutes_id']}")
    
    def test_bank_account_authorization_template_generation(self):
        """Test Bank Account Authorization template generates correct document"""
        template_data = {
            "minute_number": "2026-TEST-002",
            "meeting_date": "February 24, 2026",
            "meeting_time": "11:00 AM",
            "meeting_type": "unanimous_written_consent",
            "trustees_present": ["John Smith", "Jane Doe"],
            "trust_formation_date": "January 1, 2020",
            "bank_name": "First National Bank",
            "account_type": "checking",
            "purpose": "general trust administration",
            "authorized_signers": ["John Smith", "Jane Doe"],
            "signature_requirement": "any_one",
            "initial_deposit": 10000
        }
        
        response = requests.post(f"{BASE_URL}/api/minutes-templates",
            headers=self.headers,
            json={
                "trust_id": self.trust_id,
                "template_type": "bank_account_authorization",
                "template_data": template_data
            }
        )
        
        assert response.status_code == 200, f"Failed to generate template: {response.text}"
        
        result = response.json()
        assert "minutes_id" in result
        assert "generated_document" in result
        
        doc = result["generated_document"]
        
        # Verify document contains bank account content
        assert "Bank Account" in doc or "bank account" in doc.lower(), "Missing bank account reference"
        assert "WHEREAS" in doc, "Missing WHEREAS clause"
        assert "RESOLVED" in doc, "Missing RESOLVED clause"
        assert "First National Bank" in doc, "Missing bank name"
        assert "authorized" in doc.lower(), "Missing authorization language"
        
        # Cleanup
        delete_response = requests.delete(f"{BASE_URL}/api/minutes-templates/{result['minutes_id']}", headers=self.headers)
        
        print(f"SUCCESS: Bank Account Authorization template generated with ID: {result['minutes_id']}")
    
    def test_change_of_situs_template_generation(self):
        """Test Change of Situs template generates correct document"""
        template_data = {
            "minute_number": "2026-TEST-003",
            "meeting_date": "February 24, 2026",
            "meeting_time": "2:00 PM",
            "meeting_type": "unanimous_written_consent",
            "trustees_present": ["John Smith", "Jane Doe"],
            "trust_formation_date": "January 1, 2020",
            "current_situs": "State of Texas",
            "new_situs": "State of Nevada",
            "effective_date": "March 1, 2026",
            "reasons": [
                "Favorable trust laws",
                "Tax considerations",
                "Proximity to beneficiaries"
            ]
        }
        
        response = requests.post(f"{BASE_URL}/api/minutes-templates",
            headers=self.headers,
            json={
                "trust_id": self.trust_id,
                "template_type": "change_of_situs",
                "template_data": template_data
            }
        )
        
        assert response.status_code == 200, f"Failed to generate template: {response.text}"
        
        result = response.json()
        assert "minutes_id" in result
        assert "generated_document" in result
        
        doc = result["generated_document"]
        
        # Verify document contains situs change content
        assert "Change" in doc or "situs" in doc.lower(), "Missing situs change reference"
        assert "WHEREAS" in doc, "Missing WHEREAS clause"
        assert "RESOLVED" in doc, "Missing RESOLVED clause"
        assert "Texas" in doc, "Missing current situs (Texas)"
        assert "Nevada" in doc, "Missing new situs (Nevada)"
        assert "Favorable trust laws" in doc, "Missing reason"
        
        # Cleanup
        delete_response = requests.delete(f"{BASE_URL}/api/minutes-templates/{result['minutes_id']}", headers=self.headers)
        
        print(f"SUCCESS: Change of Situs template generated with ID: {result['minutes_id']}")
    
    def test_bank_account_with_threshold_signature(self):
        """Test Bank Account Authorization with threshold signature requirement"""
        template_data = {
            "minute_number": "2026-TEST-004",
            "meeting_date": "February 24, 2026",
            "meeting_time": "3:00 PM",
            "meeting_type": "unanimous_written_consent",
            "trustees_present": ["John Smith", "Jane Doe"],
            "trust_formation_date": "January 1, 2020",
            "bank_name": "Chase Bank",
            "account_type": "brokerage",
            "purpose": "investment holdings",
            "authorized_signers": ["John Smith", "Jane Doe"],
            "signature_requirement": "threshold",
            "signature_threshold": 25000,
            "initial_deposit": 50000
        }
        
        response = requests.post(f"{BASE_URL}/api/minutes-templates",
            headers=self.headers,
            json={
                "trust_id": self.trust_id,
                "template_type": "bank_account_authorization",
                "template_data": template_data
            }
        )
        
        assert response.status_code == 200, f"Failed to generate template: {response.text}"
        
        result = response.json()
        doc = result["generated_document"]
        
        # Verify threshold language is present
        assert "25,000" in doc or "threshold" in doc.lower(), "Missing threshold amount or language"
        assert "Chase Bank" in doc, "Missing bank name"
        assert "brokerage" in doc.lower() or "investment" in doc.lower(), "Missing account type"
        
        # Cleanup
        delete_response = requests.delete(f"{BASE_URL}/api/minutes-templates/{result['minutes_id']}", headers=self.headers)
        
        print(f"SUCCESS: Bank Account with threshold signature generated")
    
    def test_designation_amendment_type(self):
        """Test Designation of Beneficiaries with amendment type"""
        template_data = {
            "minute_number": "2026-TEST-005",
            "meeting_date": "February 24, 2026",
            "meeting_time": "4:00 PM",
            "meeting_type": "unanimous_written_consent",
            "trustees_present": ["John Smith"],
            "trust_formation_date": "January 1, 2020",
            "designation_type": "amendment",
            "total_units": 100,
            "beneficiaries": [
                {"name": "New Beneficiary", "units": 100, "percentage": 100, "relationship": "Grandchild"}
            ]
        }
        
        response = requests.post(f"{BASE_URL}/api/minutes-templates",
            headers=self.headers,
            json={
                "trust_id": self.trust_id,
                "template_type": "designation_of_beneficiaries",
                "template_data": template_data
            }
        )
        
        assert response.status_code == 200, f"Failed to generate template: {response.text}"
        
        result = response.json()
        doc = result["generated_document"]
        
        # Verify amendment language is present
        assert "amend" in doc.lower(), "Missing amendment language"
        
        # Cleanup
        delete_response = requests.delete(f"{BASE_URL}/api/minutes-templates/{result['minutes_id']}", headers=self.headers)
        
        print(f"SUCCESS: Designation amendment type generated")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
