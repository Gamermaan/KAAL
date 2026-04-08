import json
import os
import logging
from typing import Dict, Optional

logger = logging.getLogger("channel_manager")

class ChannelManager:
    """Manages persistent mapping of agent_id to discord channel_id"""
    
    def __init__(self, store_path="agent_channels.json"):
        # Store in the same directory as this file
        self.store_path = os.path.join(os.path.dirname(__file__), store_path)
        data = self._load()
        self.mapping: Dict[str, str] = data.get("mapping", {})
        self.verified_agents = set(data.get("verified_agents", []))

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.store_path):
            try:
                with open(self.store_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load channel mapping from {self.store_path}: {e}")
        return {"mapping": {}, "verified_agents": []}

    def _save(self):
        try:
            with open(self.store_path, 'w') as f:
                json.dump({
                    "mapping": self.mapping,
                    "verified_agents": list(self.verified_agents)
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save channel mapping to {self.store_path}: {e}")

    def get_channel(self, agent_id: str) -> Optional[str]:
        """Get the channel ID for a specific agent."""
        return self.mapping.get(agent_id)

    def set_channel(self, agent_id: str, channel_id: str):
        """Map an agent to a specific channel and save."""
        self.mapping[agent_id] = channel_id
        self._save()
        
    def get_agent_by_channel(self, channel_id: str) -> Optional[str]:
        """Reverse lookup: get agent ID from a channel ID."""
        for agent, ch in self.mapping.items():
            if ch == channel_id:
                return agent
        return None
        
    def remove_agent(self, agent_id: str):
        """Remove an agent from the mapping."""
        if agent_id in self.mapping:
            del self.mapping[agent_id]
        if agent_id in self.verified_agents:
            self.verified_agents.remove(agent_id)
        self._save()

    def is_verified(self, agent_id: str) -> bool:
        """Check if an agent has successfully checked in from its private channel."""
        return agent_id in self.verified_agents

    def mark_verified(self, agent_id: str):
        """Mark an agent as verified (handshake complete)."""
        if agent_id and agent_id not in self.verified_agents:
            self.verified_agents.add(agent_id)
            self._save()
            logger.info(f"🛡️ VERIFIED — Agent '{agent_id}' successfully completed the channel adoption handshake.")
