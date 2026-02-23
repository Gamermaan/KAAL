"""
Telegram Relay - Message broker for proxy agents
"""
import requests
import json
import logging
from core.logger import setup_logger

log = setup_logger("telegram_relay", console_level=logging.DEBUG)

class TelegramRelay:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.api_base = f"https://api.telegram.org/bot{token}"
        self.offset = 0
        log.info(f"TelegramRelay initialized: chat_id={chat_id}, token={token[:20]}...")
        
    def get_updates(self):
        """Poll for new messages"""
        url = f"{self.api_base}/getUpdates?offset={self.offset}&timeout=5"
        try:
            log.debug(f"Polling Telegram: offset={self.offset}")
            resp = requests.get(url, timeout=10)
            
            if resp.status_code != 200:
                log.error(f"Telegram API error: {resp.status_code} - {resp.text[:200]}")
                return
                
            data = resp.json()
            if not data.get("ok"):
                log.error(f"Telegram response not OK: {data}")
                return
                
            updates = data.get("result", [])
            log.debug(f"Received {len(updates)} update(s)")
            
            for update in updates:
                self.offset = update["update_id"] + 1
                
                # Debug: log the full message structure
                if "message" in update:
                    message = update["message"]
                    log.debug(f"Message keys: {message.keys()}")
                    log.debug(f"Message content: {message}")
                    
                    if "text" in message:
                        text = message["text"]
                        log.debug(f"Yielding message: {text[:100]}")
                        yield text
                    else:
                        log.warning(f"Message has no 'text' field. Full message: {message}")
                else:
                    log.debug(f"Update has no text message: {update.keys()}")
                    
        except requests.exceptions.RequestException as e:
            log.error(f"HTTP error: {e}")
        except Exception as e:
            log.error(f"Unexpected error in get_updates: {e}", exc_info=True)
            
    def send_message(self, text: str):
        """Send message to Telegram"""
        url = f"{self.api_base}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text
        }
        try:
            log.debug(f"Sending message: {text[:100]}")
            resp = requests.post(url, json=payload, timeout=5)
            if resp.status_code != 200:
                log.error(f"Send failed: {resp.status_code} - {resp.text[:200]}")
        except Exception as e:
            log.error(f"Send error: {e}")
