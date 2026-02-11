from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any

class Plugin(ABC):
    """Base class for all KAAL plugins."""
    @property
    @abstractmethod
    def id(self) -> str:
        """Unique plugin identifier."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human‑readable plugin name."""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """Plugin version (semver)."""
        pass

    @property
    @abstractmethod
    def type(self) -> str:
        """Plugin type: module, loader, assessment, autostart, compatibility, utility, ai."""
        pass


class ModulePlugin(Plugin):
    """Remote administration agent module (was PayloadPlugin)."""
    @property
    @abstractmethod
    def module_type(self) -> str:
        """Type of module: agent, collector, etc."""
        pass

    @property
    @abstractmethod
    def platforms(self) -> List[str]:
        """Supported operating systems."""
        pass

    @abstractmethod
    def build(self, config: Dict[str, Any]) -> str:
        """Compile or generate the agent binary. Returns path to binary."""
        pass


class LoaderPlugin(Plugin):
    """Bootstrap loader (was StagerPlugin)."""
    @abstractmethod
    def generate(self, target_platform: str, output_dir: str) -> str:
        """Generate loader source code. Returns path to source file."""
        pass


class AssessmentPlugin(Plugin):
    """Post‑deployment assessment module (was PostExploitPlugin)."""
    @abstractmethod
    def run(self, agent_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute assessment routine on an active agent."""
        pass


class UtilityPlugin(Plugin):
    """Miscellaneous utilities (signing, embedding, etc.)."""
    @abstractmethod
    def execute(self, input_file: str, **kwargs) -> Optional[str]:
        """Run the utility on an input file."""
        pass


class AIPlugin(Plugin):
    """AI backend for the assistant."""
    @abstractmethod
    def query(self, prompt: str, context: Optional[Dict] = None) -> str:
        """Send a query to the AI model."""
        pass
