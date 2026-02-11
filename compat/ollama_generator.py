import requests
import json

class OllamaGenerator:
    """Uses local Ollama with a code model to rewrite source code."""
    def __init__(self, model="deepseek-coder:6.7b", base_url="http://localhost:11434"):
        self.model = model
        self.url = f"{base_url}/api/generate"

    def mutate(self, code: str, platform: str) -> str:
        prompt = f"""Rewrite this {platform} C/C++ code to avoid signature detection. Keep functionality exactly the same. Change variable names, reorder functions, add harmless dead code. Output only code, no explanations.

CODE:
{code}
"""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "temperature": 0.7
        }
        try:
            resp = requests.post(self.url, json=payload, timeout=60)
            return resp.json()["response"]
        except Exception as e:
            print(f"[!] Ollama error: {e}")
            return code
