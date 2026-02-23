# KAAL Agent Component

The KAAL Agent is a lightweight, cross-platform Python implant designed to communicate stealthily with the KAAL C2 Framework over decentralized relays (e.g., Discord).

## Architecture

The agent is split into two primary components to allow execution even in restricted environments where third-party packages are unavailable.

1.  **`standalone_agent.py`**: The core execution engine. It handles:
    -   Registration and Heartbeats.
    -   Polling for commands from the active C2 profile (Relay).
    -   Executing standard OS commands.
    -   Streaming large command output back to the C2 in chunks.
    -   Maintaining a pseudo-terminal session.
    -   **Zero Dependencies**: This script requires *only* the Python standard library. It will run on any target with Python installed.

2.  **`agent_core.py`** (Optional but Recommended): The advanced feature module. It requires external dependencies (`psutil`, `opencv-python`, `pynput`, `pyaudio`, etc.) and provides:
    -   Webcam capture and screen scraping.
    -   Advanced process listing and system telemetry.
    -   Keylogging.
    -   Audio recording.

## Usage & Deployment

### Configuring the Agent
Before deploying the agent, you must configure it to point to your specific Relay (e.g., Discord Bot).

Open `standalone_agent.py` and modify the `RELAY_CONFIG` dictionary at the top of the file:

```python
CURRENT_RELAY_TYPE = "discord"
RELAY_CONFIG = {
    # ... other relays ...
    "discord": {
        "token": "YOUR_DISCORD_BOT_TOKEN_HERE",
        "channel_id": "YOUR_CHANNEL_ID_HERE"
    }
}
```

### Running the Agent
Once configured, simply execute the script on the target environment:

```bash
python standalone_agent.py
```

### Extending the Agent
The `standalone_agent.py` script routes specialized commands to `agent_core.py`. If you want to add new features (e.g., a custom password dumper):

1.  Add the function to `agent_core.py`. Ensure it returns a JSON-serializable structured dictionary.
2.  In `standalone_agent.py`, update the `execute_command()` function to parse the new command keyword and call your function from `agent_core.py`.

---
**⚠️ Ethical Use Notice**: The agents deployed by this framework provide full system control ("Root/Admin" equivalence) when executed with high privileges. This software is provided exclusively for educational research and authorized red-team engagements.
