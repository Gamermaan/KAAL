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
