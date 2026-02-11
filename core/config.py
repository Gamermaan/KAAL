import yaml
from pathlib import Path
from typing import Any, Optional

class Config:
    """YAML configuration loader with dot notation."""
    def __init__(self, config_path: Path = Path("config.yaml")):
        self.config_path = config_path
        self.data = self._load()

    def _load(self) -> dict:
        if not self.config_path.exists():
            return {}
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f) or {}

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        """Retrieve a value using dot notation, e.g. 'c2.host'."""
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
        """Set a value using dot notation."""
        keys = key.split('.')
        d = self.data
        for k in keys[:-1]:
            if k not in d or not isinstance(d[k], dict):
                d[k] = {}
            d = d[k]
        d[keys[-1]] = value
        with open(self.config_path, 'w') as f:
            yaml.dump(self.data, f)
