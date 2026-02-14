# test_api.py
"""
Simple test script to verify backend API functionality.
Run after starting the server: python test_api.py
"""

import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8000"

def print_response(title, response):
    """Pretty print API response"""
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")
    print(f"Status: {response.status_code}")
    try:
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    except:
        print(f"Response: {response.text}")


def test_health_check():
    """Test server is running"""
    response = requests.get(f"{BASE_URL}/health")
    print_response("Health Check", response)
    return response.status_code == 200


def test_register():
    """Test user registration"""
    # Generate unique email
    email = f"test_{datetime.now().timestamp()}@example.com"
    
    response = requests.post(
        f"{BASE_URL}/auth/register",
        json={
            "email": email,
            "password": "testpassword123"
        }
    )
    print_response("User Registration", response)
    
    if response.status_code == 201:
        return response.json()["access_token"], email
    return None, None


def test_login(email, password="testpassword123"):
    """Test user login"""
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={
            "email": email,
            "password": password
        }
    )
    print_response("User Login", response)
    
    if response.status_code == 200:
        return response.json()["access_token"]
    return None


def test_user_status(token):
    """Test getting user status"""
    response = requests.get(
        f"{BASE_URL}/users/status",
        headers={"Authorization": f"Bearer {token}"}
    )
    print_response("User Status", response)


def test_user_info(token):
    """Test getting user info"""
    response = requests.get(
        f"{BASE_URL}/users/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    print_response("User Info", response)


def test_create_payment_intent(token):
    """Test creating payment intent"""
    response = requests.post(
        f"{BASE_URL}/payments/create-intent",
        headers={"Authorization": f"Bearer {token}"},
        json={"package_type": "package_10"}
    )
    print_response("Create Payment Intent", response)
    
    if response.status_code == 200:
        return response.json()["client_secret"]
    return None


def test_process_document(token):
    """Test processing a document (trial period)"""
    response = requests.post(
        f"{BASE_URL}/documents/process",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "document_name": "test_document.pdf",
            "case_id": "case_12345"
        }
    )
    print_response("Process Document", response)


def run_all_tests():
    """Run complete test suite"""
    print("\n" + "="*60)
    print("BACKEND API TEST SUITE")
    print("="*60)
    
    # 1. Health check
    if not test_health_check():
        print("\n❌ Server is not running! Start with: uvicorn main:app --reload")
        return
    
    print("\n✅ Server is running")
    
    # 2. Register new user
    token, email = test_register()
    if not token:
        print("\n❌ Registration failed")
        return
    
    print(f"\n✅ User registered: {email}")
    print(f"Token: {token[:20]}...")
    
    # 3. Test login
    login_token = test_login(email)
    if not login_token:
        print("\n❌ Login failed")
        return
    
    print("\n✅ Login successful")
    
    # 4. Get user info
    test_user_info(token)
    
    # 5. Get user status
    test_user_status(token)
    
    # 6. Process document (should work - trial period)
    test_process_document(token)
    
    # 7. Create payment intent
    client_secret = test_create_payment_intent(token)
    if client_secret:
        print(f"\n✅ Payment intent created")
        print(f"Client Secret: {client_secret[:20]}...")
    
    print("\n" + "="*60)
    print("TEST SUITE COMPLETED")
    print("="*60)
    print("\nNext steps:")
    print("1. Check database: forensic_app.db")
    print("2. View API docs: http://localhost:8000/docs")
    print("3. Test Stripe payment with test card: 4242 4242 4242 4242")


if __name__ == "__main__":
    try:
        run_all_tests()
    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Cannot connect to server")
        print("Start the server first: python -m uvicorn main:app --reload")
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
