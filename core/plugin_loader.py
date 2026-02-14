import importlib.util
import json
from pathlib import Path
from typing import Dict, List
from .logger import setup_logger
from .plugin_base import *

log = setup_logger("plugin_loader")

class PluginLoader:
    def __init__(self, plugin_dirs: List[Path]):
        self.plugin_dirs = plugin_dirs
        self.plugins: Dict[str, Dict[str, Plugin]] = {
            "module": {}, "loader": {}, "assessment": {}, "autostart": {},
            "evasion": {}, "steganography": {}, "propagation": {}, "proxy": {},
            "c2_profile": {}, "utility": {}, "ai": {}
        }

    def discover(self) -> Dict[str, Dict[str, Plugin]]:
        for plugin_dir in self.plugin_dirs:
            if not plugin_dir.exists():
                continue
            for manifest in plugin_dir.glob("*/plugin.json"):
                plugin_path = manifest.parent
                try:
                    with open(manifest, 'r') as f:
                        meta = json.load(f)
                except Exception as e:
                    log.error(f"Failed to load manifest {manifest}: {e}")
                    continue
                entry = plugin_path / meta.get("entry", "main.py")
                if not entry.exists():
                    log.error(f"Plugin {meta['id']}: entry file {entry} not found")
                    continue
                spec = importlib.util.spec_from_file_location(meta["id"], entry)
                mod = importlib.util.module_from_spec(spec)
                try:
                    spec.loader.exec_module(mod)
                except Exception as e:
                    log.error(f"Failed to load module {meta['id']}: {e}")
                    continue
                try:
                    cls = getattr(mod, meta["class"])
                    instance = cls()
                    if meta["type"] in self.plugins:
                        self.plugins[meta["type"]][meta["id"]] = instance
                        log.info(f"Loaded plugin: {meta['id']} v{meta['version']}")
                    else:
                        log.warning(f"Unknown plugin type: {meta['type']}")
                except Exception as e:
                    log.error(f"Failed to instantiate {meta['id']}: {e}")
        return self.plugins
