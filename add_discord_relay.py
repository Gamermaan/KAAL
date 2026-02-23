"""Add Discord relay to relay manager"""
import requests

DISCORD_BOT_TOKEN = "YOUR_DISCORD_BOT_TOKEN_HERE"
DISCORD_CHANNEL_ID = "1471272917403697248"

print("Adding Discord relay...")
data = {
    'relay_type': 'discord',
    'relay_id': 'kaal',
    'token': DISCORD_BOT_TOKEN,
    'channel_id': DISCORD_CHANNEL_ID
}

try:
    resp = requests.post('http://localhost:5000/api/relay/add', json=data, timeout=5)
    if resp.status_code == 200:
        print("✅ Discord relay added successfully!")
        print(f"\nNow start the agent:")
        print(f"  python test_agent_proxy.py")
    else:
        print(f"❌ Error: {resp.status_code}")
        print(f"Response: {resp.text}")
except Exception as e:
    print(f"❌ Error: {e}")
    print("\nIs the server running?")
