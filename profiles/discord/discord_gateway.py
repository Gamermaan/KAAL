import asyncio
import aiohttp
import json
import logging

try:
    import websockets
except ImportError:
    websockets = None

logger = logging.getLogger("discord_gateway")

class DiscordGateway:
    def __init__(self, token: str, on_message_callback):
        self.token = token
        self.on_message = on_message_callback
        self.ws = None
        self.seq = None
        self.session_id = None
        self.heartbeat_interval = None
        self._heartbeat_task = None
        self.running = False

    async def connect(self):
        if websockets is None:
            logger.error("websockets package is not installed. Run: pip install websockets")
            return

        self.running = True
        
        # Get gateway URL
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bot {self.token}"}
                async with session.get("https://discord.com/api/v10/gateway/bot", headers=headers) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    gateway_url = data['url'] + '?v=10&encoding=json'
        except Exception as e:
            logger.error(f"Failed to get gateway URL: {e}")
            return

        while self.running:
            try:
                logger.info(f"Connecting to WSS Gateway: {gateway_url}")
                async with websockets.connect(gateway_url) as ws:
                    self.ws = ws
                    async for message in ws:
                        await self._process_message(message)
            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"Connection closed: {e}")
                if not self.running:
                    break
                await asyncio.sleep(5) # Reconnect delay
            except Exception as e:
                logger.error(f"Gateway connection error: {e}")
                if not self.running:
                    break
                await asyncio.sleep(5)

    async def _process_message(self, message_str: str):
        data = json.loads(message_str)
        op = data.get('op')
        self.seq = data.get('s', self.seq)
        
        if op == 10: # Hello
            self.heartbeat_interval = data['d']['heartbeat_interval'] / 1000.0
            if self._heartbeat_task:
                self._heartbeat_task.cancel()
            self._heartbeat_task = asyncio.create_task(self._heartbeater())
            
            if self.session_id:
                asyncio.create_task(self._resume())
            else:
                asyncio.create_task(self._identify())
                
        elif op == 0: # Dispatch
            event = data.get('t')
            if event == 'READY':
                self.session_id = data['d']['session_id']
                logger.info("Gateway READY")
            elif event == 'MESSAGE_CREATE':
                # Call callback asynchronously to not block the gateway loop
                asyncio.create_task(self.on_message(data['d']))
                
        elif op == 9: # Invalid Session
            logger.warning("Invalid Session, identifying again")
            self.session_id = None
            await asyncio.sleep(1)
            asyncio.create_task(self._identify())
            
        elif op == 7: # Reconnect
            logger.info("Gateway requested reconnect")
            if self.ws:
                await self.ws.close(1012)
            
        elif op == 11: # Heartbeat ACK
            pass # We could track latency here

    async def _heartbeater(self):
        while self.running and self.ws:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                payload = {"op": 1, "d": self.seq}
                await self.ws.send(json.dumps(payload))
            except Exception as e:
                logger.debug(f"Heartbeat failed: {e}")
                break

    async def _identify(self):
        logger.info("Identifying with Discord WSS...")
        payload = {
            "op": 2,
            "d": {
                "token": self.token,
                "intents": (1 << 15) | (1 << 9),  # MESSAGE_CONTENT (32768) + GUILD_MESSAGES (512)
                "properties": {
                    "os": "linux",
                    "browser": "kaal",
                    "device": "kaal"
                }
            }
        }
        await self.ws.send(json.dumps(payload))

    async def _resume(self):
        logger.info("Resuming Discord WSS session...")
        payload = {
            "op": 6,
            "d": {
                "token": self.token,
                "session_id": self.session_id,
                "seq": self.seq
            }
        }
        await self.ws.send(json.dumps(payload))
        
    async def close(self):
        self.running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self.ws:
            await self.ws.close()
