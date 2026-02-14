from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any

class Plugin(ABC):
    @property
    @abstractmethod
    def id(self) -> str: ...
    @property
    @abstractmethod
    def name(self) -> str: ...
    @property
    @abstractmethod
    def version(self) -> str: ...
    @property
    @abstractmethod
    def type(self) -> str: ...  # module, loader, assessment, autostart, evasion, steganography, propagation, proxy, c2_profile, utility, ai

class ModulePlugin(Plugin):
    @property
    @abstractmethod
    def module_type(self) -> str: ...
    @property
    @abstractmethod
    def platforms(self) -> List[str]: ...
    @abstractmethod
    def build(self, config: Dict[str, Any]) -> str: ...

class LoaderPlugin(Plugin):
    @abstractmethod
    def generate(self, target_platform: str, output_dir: str) -> str: ...

class AssessmentPlugin(Plugin):
    @abstractmethod
    def run(self, agent_id: str, params: Dict[str, Any]) -> Dict[str, Any]: ...

class AutostartPlugin(Plugin):
    @abstractmethod
    def install(self, target_path: str) -> bool: ...
    @abstractmethod
    def remove(self) -> bool: ...

class EvasionPlugin(Plugin):
    @abstractmethod
    def apply(self, process_handle: Optional[int] = None) -> bool: ...

class SteganographyPlugin(Plugin):
    @abstractmethod
    def embed(self, payload_path: str, carrier_path: str, output_path: str) -> str: ...
    @abstractmethod
    def extract(self, stego_path: str) -> bytes: ...

class PropagationPlugin(Plugin):
    @abstractmethod
    def spread(self, payload_path: str) -> bool: ...

class ProxyPlugin(Plugin):
    @abstractmethod
    def start_tunnel(self, relay_url: str) -> str: ...

class C2ProfilePlugin(Plugin):
    @abstractmethod
    def generate_config(self, profile: Dict) -> Dict: ...

class UtilityPlugin(Plugin):
    @abstractmethod
    def execute(self, input_file: str, **kwargs) -> Optional[str]: ...

class AIPlugin(Plugin):
    @abstractmethod
    def query(self, prompt: str, context: Optional[Dict] = None) -> str: ...
