import asyncio
from typing import Set, Dict, Any, List, Optional
from datetime import datetime
from fastapi import WebSocket

class TerminalState:
    def __init__(self):
        self.connected_clients: Set[WebSocket] = set()
        self.command_history: List[Dict[str, Any]] = []
        self.current_agent: Optional[str] = None
        self.build_queue: List[Dict[str, Any]] = []

    async def register_client(self, websocket: WebSocket):
        await websocket.accept()
        self.connected_clients.add(websocket)

    def remove_client(self, websocket: WebSocket):
        self.connected_clients.discard(websocket)

    async def broadcast(self, event: str, data: Any):
        message = {
            "type": event,
            "timestamp": datetime.now().isoformat(),
            "data": data
        }
        # Copy set to avoid modification during iteration if a client disconnects
        for client in list(self.connected_clients):
            try:
                await client.send_json(message)
            except:
                self.connected_clients.discard(client)

terminal_state = TerminalState()
