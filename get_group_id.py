"""
Get Telegram group chat ID
"""
import requests

# Use your RELAY bot token (the new one you just created)
token = input("Enter your RELAY bot token: ").strip()

print("\nFetching updates from Telegram...")
url = f'https://api.telegram.org/bot{token}/getUpdates'
resp = requests.get(url)
data = resp.json()

print("\n=== Chat IDs Found ===\n")

chat_ids = set()
for update in data.get('result', []):
    if 'message' in update:
        chat = update['message']['chat']
        chat_id = chat.get('id')
        chat_title = chat.get('title', chat.get('first_name', 'Private chat'))
        chat_type = chat.get('type')
        
        if chat_id not in chat_ids:
            chat_ids.add(chat_id)
            print(f"Chat: {chat_title}")
            print(f"  Type: {chat_type}")
            print(f"  ID: {chat_id}")
            
            if chat_type == 'group' or chat_type == 'supergroup':
                print(f"  👉 USE THIS ID: {chat_id}")
            print()

if not chat_ids:
    print("❌ No messages found!")
    print("\nMake sure you:")
    print("1. Created a group in Telegram")
    print("2. Added both bots to the group")
    print("3. Sent a message in the group (like /start)")
    print("\nThen run this script again.")
else:
    print("\nℹ️  Use the GROUP chat ID (negative number) in your config!")
