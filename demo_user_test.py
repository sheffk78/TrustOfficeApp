#!/usr/bin/env python3

import requests
import json

BACKEND_URL = "https://health-dashboard-124.preview.emergentagent.com"
API_URL = f"{BACKEND_URL}/api"

def test_demo_user_login():
    """Test the specific demo user mentioned in the agent notes"""
    print("🔍 Testing Demo User Login...")
    
    # Demo credentials from agent notes
    demo_email = "demo@trustoffice.com"
    demo_password = "demo123"
    
    try:
        # Test login
        login_response = requests.post(
            f"{API_URL}/auth/login",
            json={"email": demo_email, "password": demo_password},
            headers={"Content-Type": "application/json"}
        )
        
        print(f"Login Status: {login_response.status_code}")
        
        if login_response.status_code == 200:
            print("✅ Demo user login successful")
            login_data = login_response.json()
            
            # Get token and user info
            token = login_data.get('token')
            user_info = login_data.get('user', {})
            
            print(f"User: {user_info.get('name')} ({user_info.get('email')})")
            print(f"User ID: {user_info.get('user_id')}")
            
            # Test authenticated call - get trusts
            if token:
                auth_headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }
                
                trusts_response = requests.get(
                    f"{API_URL}/trusts",
                    headers=auth_headers
                )
                
                print(f"Trusts API Status: {trusts_response.status_code}")
                
                if trusts_response.status_code == 200:
                    trusts_data = trusts_response.json()
                    print(f"Number of trusts: {len(trusts_data)}")
                    
                    if trusts_data:
                        trust = trusts_data[0]
                        print(f"First trust: {trust.get('name')} (Score: {trust.get('governance_score')})")
                        
                        # Test governance endpoint
                        trust_id = trust.get('trust_id')
                        if trust_id:
                            gov_response = requests.get(
                                f"{API_URL}/governance/{trust_id}",
                                headers=auth_headers
                            )
                            print(f"Governance API Status: {gov_response.status_code}")
                            
                            if gov_response.status_code == 200:
                                gov_data = gov_response.json()
                                print(f"Governance Score: {gov_data.get('overall_score')}")
                                print(f"Status: {gov_data.get('status')}")
                    
                    return True
                else:
                    print(f"❌ Failed to get trusts: {trusts_response.text}")
                    return False
            else:
                print("❌ No token received in login response")
                return False
        else:
            print(f"❌ Demo user login failed: {login_response.text}")
            return False
    
    except Exception as e:
        print(f"❌ Error testing demo user: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_demo_user_login()
    exit(0 if success else 1)