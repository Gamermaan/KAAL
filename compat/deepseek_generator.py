import requests
import json
import hashlib
import time

class DeepSeekGenerator:
    """Uses DeepSeek API to rewrite source code for enhanced compatibility."""
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        })
        self.cache = {}
        self.api_url = "https://api.deepseek.com/v1/chat/completions"

    def _abstract_code(self, code: str) -> str:
        """Remove comments and shorten code to reduce token usage."""
        lines = code.split('\n')
        out = []
        for line in lines:
            if '//' in line:
                line = line[:line.index('//')]
            out.append(line)
        return '\n'.join(out)

    def mutate(self, code: str, platform: str, instructions: str = "") -> str:
        """Request a rewritten version of the code from DeepSeek."""
        abstract = self._abstract_code(code)
        cache_key = hashlib.md5((abstract + platform + instructions).encode()).hexdigest()
        if cache_key in self.cache:
            return self.cache[cache_key]

        prompt = f"""Rewrite this {platform} C/C++ code to be functionally identical but structurally different to improve compatibility and avoid signature‑based detection.
- Change all variable and function names to realistic {platform} API style.
- Reorder functions arbitrarily.
- Insert harmless dead code (opaque predicates, dummy loops).
- Use different API call sequences if possible (e.g., NtCreateFile instead of CreateFile).
- Preserve all original functionality.
- Output only compilable code, no explanations.

CODE:
{abstract}

{instructions}
"""
        payload = {
            "model": "deepseek-coder",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 4096,
            "top_p": 0.95
        }
        try:
            print("[*] DeepSeek: requesting code transformation...")
            resp = self.session.post(self.api_url, json=payload, timeout=45)
            resp.raise_for_status()
            result = resp.json()
            mutated = result["choices"][0]["message"]["content"]
            # Extract code from markdown if present
            if '```' in mutated:
                mutated = mutated.split('```')[1]
                if mutated.startswith('c') or mutated.startswith('cpp'):
                    mutated = mutated[3:].lstrip()
            self.cache[cache_key] = mutated
            print("[✓] DeepSeek transformation successful")
            return mutated
        except Exception as e:
            print(f"[!] DeepSeek error: {e}")
            return code
