from .rule_generator import RuleGenerator
from .deepseek_generator import DeepSeekGenerator
from .ollama_generator import OllamaGenerator

class HybridGenerator:
    """Orchestrates multiple code transformation strategies."""
    def __init__(self):
        self.rule = RuleGenerator()
        self.deepseek = None
        self.ollama = None

    def enable_deepseek(self, api_key: str):
        self.deepseek = DeepSeekGenerator(api_key)

    def enable_ollama(self, model: str = "deepseek-coder:6.7b"):
        self.ollama = OllamaGenerator(model)

    def mutate(self, code: str, platform: str,
               use_deepseek: bool = False,
               use_ollama: bool = False,
               instructions: str = "") -> str:
        """Apply rule‑based transformations, then optionally AI‑based ones."""
        # Always apply rule‑based first (fast, deterministic)
        code = self.rule.rename_vars(code)
        code = self.rule.reorder_funcs(code)
        code = self.rule.insert_deadcode(code)
        code = self.rule.encrypt_strings(code)

        if use_deepseek and self.deepseek:
            code = self.deepseek.mutate(code, platform, instructions)
        if use_ollama and self.ollama:
            code = self.ollama.mutate(code, platform)

        return code
