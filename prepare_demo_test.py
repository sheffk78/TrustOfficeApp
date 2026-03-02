#!/usr/bin/env python3

import requests
import json

BACKEND_URL = "https://governance-hub-63.preview.emergentagent.com"
API_URL = f"{BACKEND_URL}/api"

def test_demo_user_and_seed():
    """Test demo user and seed demo data if needed"""
    print("🔍 Testing Demo User and Seeding Demo Data...")
    
    try:
        # Login
        login_response = requests.post(
            f"{API_URL}/auth/login",
            json={"email": "demo@trustoffice.com", "password": "demo123"},
            headers={"Content-Type": "application/json"}
        )
        
        if login_response.status_code == 200:
            login_data = login_response.json()
            token = login_data.get('token')
            
            if token:
                auth_headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }
                
                # Check current trusts
                trusts_response = requests.get(f"{API_URL}/trusts", headers=auth_headers)
                
                if trusts_response.status_code == 200:
                    trusts = trusts_response.json()
                    print(f"Current trusts count: {len(trusts)}")
                    
                    if len(trusts) == 0:
                        print("No trusts found - creating demo data...")
                        
                        # Seed demo data
                        seed_response = requests.post(f"{API_URL}/demo/seed", headers=auth_headers)
                        
                        if seed_response.status_code == 200:
                            seed_data = seed_response.json()
                            print(f"Demo data seeded: {seed_data}")
                            
                            # Re-check trusts
                            trusts_response = requests.get(f"{API_URL}/trusts", headers=auth_headers)
                            if trusts_response.status_code == 200:
                                trusts = trusts_response.json()
                                print(f"Trusts after seeding: {len(trusts)}")
                                
                                if trusts:
                                    trust = trusts[0]
                                    print(f"Demo trust: {trust['name']} (Score: {trust['governance_score']})")
                        else:
                            print(f"Failed to seed demo data: {seed_response.text}")
                    
                    else:
                        trust = trusts[0]
                        print(f"Demo trust already exists: {trust['name']} (Score: {trust['governance_score']})")
                        
                        # Test distributions endpoint
                        dist_response = requests.get(f"{API_URL}/distributions?trust_id={trust['trust_id']}", headers=auth_headers)
                        if dist_response.status_code == 200:
                            distributions = dist_response.json()
                            print(f"Distributions: {len(distributions)}")
                            
                            for dist in distributions[:2]:  # Show first 2
                                print(f"  - ${dist['amount']} to {dist['beneficiary']} ({dist['status']})")
                        
                        # Test expenses endpoint
                        exp_response = requests.get(f"{API_URL}/expenses?trust_id={trust['trust_id']}", headers=auth_headers)
                        if exp_response.status_code == 200:
                            expenses = exp_response.json()
                            print(f"Expenses: {len(expenses)}")
                            
                            for exp in expenses[:2]:  # Show first 2
                                print(f"  - ${exp['amount']} to {exp['payee']} ({exp['status']})")
                    
                    return True
            
    except Exception as e:
        print(f"Error: {str(e)}")
        return False

if __name__ == "__main__":
    test_demo_user_and_seed()