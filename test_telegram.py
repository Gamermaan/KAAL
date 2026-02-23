"""
Test if relay can actually receive Telegram messages
"""
import requests
import time

# REPLACE WITH YOUR ACTUAL CREDENTIALS
BOT_TOKEN = input("Enter bot token: ")
CHAT_ID = input("Enter chat ID: ")

print(f"\nTesting Telegram connection...")
print(f"Bot: {BOT_TOKEN[:20]}...")
print(f"Chat: {CHAT_ID}\n")

# 1. Send a test message
print("1. Sending test message...")
url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
data = {"chat_id": CHAT_ID, "text": "KAAL_RELAY_MSG:{\"type\":\"test\",\"agent_id\":\"test-agent\"}"}
resp = requests.post(url, json=data)
if resp.status_code == 200:
    print("   ✅ Message sent successfully")
else:
    print(f"   ❌ Send failed: {resp.status_code} - {resp.text}")
    exit(1)

time.sleep(2)

# 2. Poll for the message
print("\n2. Polling for messages...")
url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?limit=5"
resp = requests.get(url)
if resp.status_code == 200:
    data = resp.json()
    updates = data.get('result', [])
    print(f"   Found {len(updates)} message(s)")
    
    for update in updates:
        if 'message' in update and 'text' in update['message']:
            text = update['message']['text']
            print(f"   - {text[:100]}")
            
            if text.startswith("KAAL_RELAY_MSG:"):
                print("   ✅ KAAL message received!")
else:
    print(f"   ❌ Poll failed: {resp.status_code}")
    exit(1)

print("\n✅ Telegram bot is working correctly!")
print("\nNow check:")
print("1. Is this the SAME bot token in test_agent_proxy.py?")
print("2. Is this the SAME bot token you added to the relay in GUI?")
print("3. If not, they won't communicate!")
