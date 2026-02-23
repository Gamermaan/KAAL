import requests
import json

# Test relay API endpoints
base_url = "http://localhost:5000"

print("Testing Relay API Endpoints...\n")

# Test 1: List relays (GET)
print("1. Testing GET /api/relay/list")
try:
    resp = requests.get(f"{base_url}/api/relay/list")
    print(f"   Status: {resp.status_code}")
    print(f"   Response: {resp.json()}")
except Exception as e:
    print(f"   Error: {e}")

print()

# Test 2: Add relay (POST)
print("2. Testing POST /api/relay/add")
try:
    payload = {
        "relay_type": "telegram",
        "relay_id": "test-relay",
        "token": "123456:ABC-TEST-TOKEN",
        "chat_id": "123456789"
    }
    resp = requests.post(f"{base_url}/api/relay/add", json=payload)
    print(f"   Status: {resp.status_code}")
    print(f"   Response: {resp.json()}")
except Exception as e:
    print(f"   Error: {e}")

print()

# Test 3: List relays again
print("3. Testing GET /api/relay/list (after add)")
try:
    resp = requests.get(f"{base_url}/api/relay/list")
    print(f"   Status: {resp.status_code}")
    print(f"   Response: {resp.json()}")
except Exception as e:
    print(f"   Error: {e}")

print()

# Test 4: Health check
print("4. Testing GET /api/health")
try:
    resp = requests.get(f"{base_url}/api/health")
    print(f"   Status: {resp.status_code}")
    print(f"   Response: {resp.json()}")
except Exception as e:
    print(f"   Error: {e}")
