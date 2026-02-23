"""
Quick test script to check if relay is receiving messages
"""
import requests
import sys

if len(sys.argv) < 3:
    print("Usage: python test_relay.py <BOT_TOKEN> <CHAT_ID>")
    sys.exit(1)

token = sys.argv[1]
chat_id = sys.argv[2]

print(f"Testing relay with token: {token[:20]}... and chat_id: {chat_id}")

# Test 1: Get bot info
try:
    url = f"https://api.telegram.org/bot{token}/getMe"
    resp = requests.get(url)
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ Bot connected: {data['result']['first_name']} (@{data['result']['username']})")
    else:
        print(f"❌ Bot auth failed: {resp.status_code}")
        sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)

# Test 2: Get updates (check for messages)
try:
    url = f"https://api.telegram.org/bot{token}/getUpdates?limit=5"
    resp = requests.get(url)
    if resp.status_code == 200:
        data = resp.json()
        updates = data.get('result', [])
        print(f"\n📬 Found {len(updates)} recent messages:")
        for update in updates:
            if 'message' in update and 'text' in update['message']:
                text = update['message']['text']
                print(f"  - {text[:100]}")
    else:
        print(f"❌ Get updates failed: {resp.status_code}")
except Exception as e:
    print(f"❌ Error: {e}")

print("\n✅ Relay test complete!")
