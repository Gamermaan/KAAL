import yaml
from pathlib import Path
from typing import Any, Optional

class Config:
    def __init__(self, config_name: str = "config.yaml"):
        self.config_path = self._find_config(config_name)
        self.data = self._load()

    def _find_config(self, name: str) -> Path:
        """Search for config in current and parent directories."""
        curr = Path(".").resolve()
        for parent in [curr] + list(curr.parents):
            p = parent / name
            if p.exists():
                return p
        return Path(name) # Fallback

    def _load(self) -> dict:
        if not self.config_path.exists():
            print(f"DEBUG: Config file NOT FOUND at {self.config_path}")
            return {}
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f) or {}

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        keys = key.split('.')
        val = self.data
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
                if val is None:
                    return default
            else:
                return default
        return val

    def set(self, key: str, value: Any) -> None:
        keys = key.split('.')
        d = self.data
        for k in keys[:-1]:
            if k not in d or not isinstance(d[k], dict):
                d[k] = {}
            d = d[k]
        d[keys[-1]] = value
        with open(self.config_path, 'w') as f:
            yaml.dump(self.data, f)
