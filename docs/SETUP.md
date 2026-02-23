# KAAL Framework Setup Guide

This guide covers the installation and setup of the KAAL C2 Framework, including the server, frontend dashboard, and deploying an agent via the Discord relay.

## Prerequisites
- Python 3.9+
- Node.js 18+ and npm
- A Discord account and an active Developer Application (Bot).

## 1. Initial Setup

### Server Dependencies
Navigate to the root directory and install server requirements:
```bash
pip install -r requirements.txt
# If requirements.txt is missing, ensure FastAPI and Uvicorn are installed:
pip install fastapi uvicorn websockets
```

### Frontend Dependencies
Navigate to the `web/frontend` directory and install React dependencies:
```bash
cd web/frontend
npm install
```

## 2. Configure the Discord Relay
The framework relies on a Discord bot to act as a stealthy relay between the C2 server and the agents.

1.  Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2.  Create a "New Application" and add a "Bot".
3.  Copy the **Bot Token**.
4.  Create a fresh Discord Server (Guild) and invite your bot to it (ensure it has permissions to read/send messages).
5.  Create a new text channel (e.g., `#c2-relay`), right-click the channel, and copy the **Channel ID**.
6.  Update `discord_config.txt` in the root directory:
```
token=YOUR_BOT_TOKEN
channel_id=YOUR_CHANNEL_ID
```
*Note: You can also use `add_discord_relay.py` but ensure `discord_config.txt` is accurate for the server profile.*

## 3. Starting the Framework

You need to run the Server, the C2 Profile (Relay), and the Frontend simultaneously.

**Terminal 1 (Backend Server):**
```bash
# From the project root
python web/server.py
```
*This starts the API and WebSocket server on `http://127.0.0.1:8000`.*

**Terminal 2 (Discord C2 Profile):**
```bash
# From the project root
python profiles/discord/profile.py discord_config.txt http://127.0.0.1:8000
```
*This connects the Discord channel to your local backend.*

**Terminal 3 (Frontend Dashboard):**
```bash
# From web/frontend
npm run dev
```
*Access the dashboard at `http://localhost:5173`.*

## 4. Deploying an Agent

1.  Open `standalone_agent.py` in a text editor.
2.  Locate the `RELAY_CONFIG` dictionary near the top.
3.  Update the `discord` section with your actual **Bot Token** and **Channel ID**:
```python
    "discord": {
        "token": "YOUR_BOT_TOKEN_HERE",
        "channel_id": "YOUR_CHANNEL_ID_HERE"
    }
```
4.  Copy `standalone_agent.py` and `agent_core.py` (if available) to the target machine.
5.  Run the agent on the target machine:
```bash
python standalone_agent.py
```

The agent will register via the Discord relay, and it should immediately appear in your web dashboard.

---
**⚠️ Disclaimer**: The KAAL framework is for educational and authorized testing purposes only. Do not deploy agents on systems you do not own or have explicit permission to test.
