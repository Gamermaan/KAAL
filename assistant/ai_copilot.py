import requests
import json
from pathlib import Path
from .rag_indexer import RAGIndexer
from core.state_manager import terminal_state

class AICopilot:
    """Offline AI assistant with RAG and terminal context awareness."""
    def __init__(self, model="deepseek-coder:6.7b", ollama_url="http://localhost:11434"):
        self.model = model
        self.ollama_url = ollama_url
        self.rag = RAGIndexer()

    def ask(self, question: str) -> str:
        """Process a user query and return an AI‑generated answer."""
        # Retrieve relevant documentation
        docs = self.rag.search(question)
        context = "\n".join(docs[:3])

        # Get recent terminal activity
        term = self._get_terminal_context()

        prompt = f"""You are KAAL Copilot, an AI assistant for the KAAL remote administration framework.
You have access to the following documentation context:
{context}

Current terminal context (last commands):
{term}

User question: {question}

Answer concisely and helpfully. If the user asks for code, output only the code without explanation.
"""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "temperature": 0.3
        }
        try:
            resp = requests.post(f"{self.ollama_url}/api/generate", json=payload, timeout=30)
            return resp.json()["response"]
        except Exception as e:
            return f"[!] AI Copilot error: {e}"

    def _get_terminal_context(self) -> str:
        """Extract the last 5 commands and their output from terminal state."""
        hist = terminal_state.command_history[-5:]
        lines = []
        for h in hist:
            lines.append(f"> {h.get('command', '')}")
            out = h.get('output', '')[:200]
            if out:
                lines.append(out)
        return "\n".join(lines)
