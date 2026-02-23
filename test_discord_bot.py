import requests

DISCORD_BOT_TOKEN = 'YOUR_DISCORD_BOT_TOKEN_HERE'
DISCORD_SERVER_ID = '1471272916267303145'

# Get all channels in the server
url = f'https://discord.com/api/v10/guilds/{DISCORD_SERVER_ID}/channels'
headers = {'Authorization': f'Bot {DISCORD_BOT_TOKEN}'}

print('Fetching channels from Discord server...')
resp = requests.get(url, headers=headers, timeout=10)
print(f'API response status: {resp.status_code}\n')

if resp.status_code == 200:
    channels = resp.json()
    text_channels = [ch for ch in channels if ch['type'] == 0]
    print(f'Found {len(text_channels)} text channels in your server:\n')
    for ch in text_channels:
        print(f"  - {ch['name']:30} ID: {ch['id']}")
        # Check permissions
        perms = ch.get('permission_overwrites', [])
        if perms:
            print(f"    Permissions: {len(perms)} overrides")
    
    # Try sending to the first channel
    if text_channels:
        test_channel = text_channels[0]
        print(f"\n\nTesting message send to '#{test_channel['name']}'...")
        test_url = f"https://discord.com/api/v10/channels/{test_channel['id']}/messages"
        test_data = {'content': 'Test from KAAL agent - checking bot permissions'}
        test_resp = requests.post(test_url, headers=headers, json=test_data, timeout=5)
        print(f'Send status: {test_resp.status_code}')
        
        if test_resp.status_code == 200:
            print(f'\n✅ Success! Bot can send messages!')
            print(f'\nUse this channel ID in standalone_agent.py:')
            print(f'DISCORD_CHANNEL_ID = "{test_channel["id"]}"')
        else:
            print(f'\n❌ Error sending message:')
            print(f'Response: {test_resp.text}')
            print(f'\nThe bot might not have "Send Messages" permission in this channel.')
            print(f'Go to Discord → Server Settings → Roles → {test_channel["name"]} → Enable "Send Messages"')
else:
    print(f'❌ Error fetching channels:')
    print(f'Response: {resp.text}')
    print(f'\nThe bot might not be in the server or doesn\'t have "View Channels" permission.')
