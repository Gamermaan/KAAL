import base64
import json
import logging

logger = logging.getLogger("translator")

class MessageTranslator:
    """Mythic-style encoding: base64(agent_id + ':' + json)"""
    
    @staticmethod
    def encode(agent_id: str, data: dict) -> str:
        """Encode data for agent."""
        combined = f"{agent_id}:{json.dumps(data)}"
        return base64.b64encode(combined.encode()).decode()
    
    @staticmethod
    def decode(encoded: str) -> tuple[str, dict]:
        """Decode agent message, returns (agent_id, data)."""
        try:
            decoded = base64.b64decode(encoded).decode()
            logger.debug(f"DEBUG: Decoded string: '{decoded}'")
            if ":" not in decoded:
                raise ValueError("Missing colon")
            agent_id, json_str = decoded.split(":", 1)
            try:
                data = json.loads(json_str)
                return agent_id, data
            except json.JSONDecodeError as je:
                logger.error(f"JSON Parse Error: {je}. Raw JSON snippet: '{json_str[:50]}...'")
                raise
        except Exception as e:
            logger.error(f"Decode error: {e}")
            raise
    
    def discord_to_server(self, content: str) -> tuple[str, dict]:
        """Convert Discord message (KAAL_AGT:...) to server dict."""
        if not content.startswith("KAAL_AGT:"):
            raise ValueError("Not a KAAL agent message")
        encoded = content[9:]  # strip prefix
        agent_id, data = self.decode(encoded)
        return agent_id, data
    
    def server_to_discord(self, agent_id: str, command: dict) -> str:
        """Convert server command to Discord message (KAAL_SVR:...)."""
        encoded = self.encode(agent_id, command)
        return f"KAAL_SVR:{encoded}"
