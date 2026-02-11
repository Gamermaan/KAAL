import requests
import time

class TelegramRelay:
    """Relay via Telegram Bot API."""
    def __init__(self, token: str, chat_id: str, enc_key: bytes):
        self.token = token
        self.chat_id = chat_id
        self.enc_key = enc_key
        self.api_base = f"https://api.telegram.org/bot{token}"
        self.offset = 0

    def get_updates(self):
        """Fetch new messages from Telegram."""
        url = f"{self.api_base}/getUpdates?offset={self.offset}&timeout=5"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    for update in data.get("result", []):
                        self.offset = update["update_id"] + 1
                        if "message" in update and "text" in update["message"]:
                            yield update["message"]["text"]
        except Exception:
            pass

    def send_message(self, text: str):
        """Post a message to the configured Telegram chat."""
        url = f"{self.api_base}/sendMessage?chat_id={self.chat_id}&text={text}"
        try:
            requests.get(url, timeout=5)
        except Exception:
            pass
