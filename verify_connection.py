"""
Quick verification: Check if bot can see messages from agent
"""
import requests
import sys

# Get credentials
print("Enter the bot token you're using in the relay:")
token = input("> ").strip()

print("\nChecking last 5 messages from this bot...")

url = f"https://api.telegram.org/bot{token}/getUpdates?limit=5"
resp = requests.get(url)

if resp.status_code != 200:
    print(f"❌ API Error: {resp.status_code}")
    print(resp.text)
    sys.exit(1)

data = resp.json()
if not data.get("ok"):
    print(f"❌ Response not OK: {data}")
    sys.exit(1)

updates = data.get("result", [])
print(f"\n✅ Found {len(updates)} message(s):\n")

if len(updates) == 0:
    print("   No messages found!")
    print("   This means:")
    print("   1. The agent hasn't sent any messages yet, OR")
    print("   2. Agent is using a DIFFERENT bot token")
    print("\n   Fix: Make sure agent's TELEGRAM_TOKEN matches relay bot token!")
else:
    for i, update in enumerate(updates, 1):
        if "message" in update and "text" in update["message"]:
            text = update["message"]["text"]
            chat_id = update["message"]["chat"]["id"]
            print(f"   {i}. From chat {chat_id}: {text[:80]}")
            
            if text.startswith("KAAL_RELAY_MSG:"):
                print("      👉 This is a KAAL message! ✅")
        else:
            print(f"   {i}. [No text message]")

print("\n" + "="*60)
print("If you see KAAL messages above, the bot is working!")
print("The relay SHOULD be receiving these messages.")
print("="*60)
