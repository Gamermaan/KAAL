"""
Add relay with second bot configuration
"""
import requests

# Remove old relay
print("Removing old relay...")
try:
    resp = requests.delete('http://localhost:5000/api/relay/telegram/kaal', timeout=5)
    print(f"Remove response: {resp.status_code}")
except Exception as e:
    print(f"Remove error (may not exist): {e}")

# Add new relay with Bot 2
print("\nAdding new relay with Bot 2...")
data = {
    'relay_type': 'telegram',
    'relay_id': 'kaal',
    'token': '8324811543:AAER4k0GhQQA4JODA0CZqZI8YqTDbauNABM',  # Bot 2
    'chat_id': '-5105960756'  # Group chat
}

try:
    resp = requests.post('http://localhost:5000/api/relay/add', json=data, timeout=5)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")
    
    if resp.status_code == 200:
        print("\n✅ Relay configured successfully!")
        print(f"   Bot Token: 8324811543:...")
        print(f"   Chat ID: -5105960756")
        print("\nNow restart the agent: python test_agent_proxy.py")
    else:
        print(f"\n❌ Error: {resp.text}")
except Exception as e:
    print(f"❌ Connection error: {e}")
    print("\nIs the server running? Check if uvicorn is started.")
