"""
Discord Relay Setup - Quick Switch from Telegram

This script:
1. Updates the agent to use Discord instead of Telegram
2. Configures the relay manager with Discord
3. Tests the connection
"""
import requests

# Discord Configuration (from tokens.txt)
DISCORD_BOT_TOKEN = "YOUR_DISCORD_BOT_TOKEN_HERE"
DISCORD_SERVER_ID = "1471272916267303145"

print("=" * 60)
print("Discord Relay Setup")
print("=" * 60)

# Step 1: Get list of channels in the server
print("\n[1] Fetching channels from Discord server...")
try:
    url = f"https://discord.com/api/v10/guilds/{DISCORD_SERVER_ID}/channels"
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
    resp = requests.get(url, headers=headers, timeout=10)
    
    if resp.status_code == 200:
        channels = resp.json()
        print(f"✅ Found {len(channels)} channels:")
        
        text_channels = [ch for ch in channels if ch['type'] == 0]  # Type 0 = text channel
        
        for ch in text_channels:
            print(f"   - {ch['name']} (ID: {ch['id']})")
        
        if text_channels:
            # Use the first text channel
            channel_id = text_channels[0]['id']
            channel_name = text_channels[0]['name']
            print(f"\n👉 Will use channel: #{channel_name} (ID: {channel_id})")
            
            # Step 2: Test sending a message
            print(f"\n[2] Testing Discord connection...")
            test_url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
            test_payload = {"content": "KAAL_RELAY_MSG:{\"type\":\"test\",\"agent_id\":\"setup-test\"}"}
            test_resp = requests.post(test_url, headers=headers, json=test_payload, timeout=5)
            
            if test_resp.status_code == 200:
                print("✅ Test message sent successfully!")
                print(f"\n📋 Configuration:\n")
                print(f"   Discord Bot Token: {DISCORD_BOT_TOKEN[:30]}...")
                print(f"   Channel ID: {channel_id}")
                print(f"   Channel Name: #{channel_name}")
                
                # Save config for agent
                config_file = "discord_config.txt"
                with open(config_file, "w") as f:
                    f.write(f"DISCORD_BOT_TOKEN={DISCORD_BOT_TOKEN}\n")
                    f.write(f"DISCORD_CHANNEL_ID={channel_id}\n")
                
                print(f"\n✅ Config saved to {config_file}")
                print(f"\n🎯 Next steps:")
                print(f"   1. Update test_agent_proxy.py to use Discord")
                print(f"   2. Add Discord relay via GUI")
                print(f"   3. Restart agent")
                
            else:
                print(f"❌ Failed to send test message: {test_resp.status_code}")
                print(f"   Response: {test_resp.text}")
        else:
            print("❌ No text channels found in server!")
            print("   Create a text channel in Discord and run this again.")
    else:
        print(f"❌ Failed to fetch channels: {resp.status_code}")
        print(f"   Response: {resp.text}")
        
except Exception as e:
    print(f"❌ Error: {e}")
    
print("\n" + "=" * 60)
