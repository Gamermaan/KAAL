from core.plugin_base import ModulePlugin
from pathlib import Path

class WindowsKAAL(ModulePlugin):
    @property
    def id(self): return "windows_agent"
    @property
    def name(self): return "Windows KAAL Agent"
    @property
    def version(self): return "1.0.0"
    @property
    def type(self): return "module"
    @property
    def module_type(self): return "agent"
    @property
    def platforms(self): return ["windows"]

    def build(self, config):
        # Builder handles compilation; just provide source path
        return str(Path(__file__).parent / "src" / "agent.cpp")
