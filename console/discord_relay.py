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
                    
                    content = msg.get("content", "")
                    # If payload is large, agent sends it as an attachment (e.g. response.txt)
                    attachments = msg.get("attachments", [])
                    if attachments:
                        for att in attachments:
                            # Usually there's only one attachment with the KAAL_AGT:... payload
                            try:
                                att_resp = requests.get(att["url"], timeout=10)
                                if att_resp.status_code == 200:
                                    att_content = att_resp.text
                                    if "KAAL_AGT:" in att_content:
                                        content = att_content
                                        break
                            except Exception:
                                pass
                                
                    if content:
                        yield content
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
