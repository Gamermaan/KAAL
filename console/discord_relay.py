"""
Discord Relay - Message broker for proxy agents
"""
import requests

class DiscordRelay:
    def __init__(self, token: str, channel_id: str):
        self.token = token
        self.channel_id = channel_id
        self.api_base = "https://discord.com/api/v10"
        self.headers = {"Authorization": f"Bot {token}"}
        self.last_message_id = None
        
    def get_messages(self, limit=10):
        """Poll for new messages"""
        url = f"{self.api_base}/channels/{self.channel_id}/messages?limit={limit}"
        if self.last_message_id:
            url += f"&after={self.last_message_id}"
        
        try:
            resp = requests.get(url, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                msgs = resp.json()
                for msg in reversed(msgs):
                    self.last_message_id = msg["id"]
                    yield msg["content"]
        except Exception:
            pass
            
    def send_message(self, text: str):
        """Send message to Discord"""
        url = f"{self.api_base}/channels/{self.channel_id}/messages"
        payload = {"content": text}
        try:
            requests.post(url, headers=self.headers, json=payload, timeout=5)
        except Exception:
            pass
