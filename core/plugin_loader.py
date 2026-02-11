import importlib.util
import json
from pathlib import Path
from typing import Dict, List
from .plugin_base import *

class PluginLoader:
    """Discovers and loads all plugins from specified directories."""
    def __init__(self, plugin_dirs: List[Path]):
        self.plugin_dirs = plugin_dirs
        self.plugins: Dict[str, Dict[str, Plugin]] = {
            "module": {},
            "loader": {},
            "assessment": {},
            "utility": {},
            "ai": {}
        }

    def discover(self) -> Dict[str, Dict[str, Plugin]]:
        """Scan plugin directories and load all valid plugins."""
        for plugin_dir in self.plugin_dirs:
            if not plugin_dir.exists():
                continue
            for manifest in plugin_dir.glob("*/plugin.json"):
                plugin_path = manifest.parent
                try:
                    with open(manifest, 'r') as f:
                        meta = json.load(f)
                except Exception as e:
                    print(f"[-] Failed to load manifest {manifest}: {e}")
                    continue

                # Load entry module
                entry = plugin_path / meta.get("entry", "main.py")
                if not entry.exists():
                    print(f"[-] Plugin {meta['id']}: entry file {entry} not found")
                    continue

                spec = importlib.util.spec_from_file_location(meta["id"], entry)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)

                # Instantiate plugin class
                try:
                    cls = getattr(mod, meta["class"])
                    instance = cls()
                    self.plugins[meta["type"]][meta["id"]] = instance
                    print(f"[+] Loaded plugin: {meta['id']} v{meta['version']}")
                except Exception as e:
                    print(f"[-] Failed to instantiate {meta['id']}: {e}")

        return self.plugins
