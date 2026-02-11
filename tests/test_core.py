import unittest
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import Config
from core.logger import setup_logger
from core.state_manager import TerminalState

class TestCore(unittest.TestCase):
    """Test core framework components."""

    def test_config_get(self):
        """Test config getter with dot notation."""
        cfg = Config(Path("config.yaml"))
        # Test basic get
        host = cfg.get("console.host", "default")
        self.assertIsNotNone(host)
        # Test missing key with default
        missing = cfg.get("nonexistent.key", "default_value")
        self.assertEqual(missing, "default_value")

    def test_logger_creation(self):
        """Test logger initialization."""
        logger = setup_logger("test_logger")
        self.assertIsNotNone(logger)
        self.assertEqual(logger.name, "test_logger")

    def test_terminal_state(self):
        """Test shared terminal state."""
        state = TerminalState()
        self.assertIsNotNone(state.command_history)
        self.assertEqual(len(state.command_history), 0)
        self.assertIsNone(state.current_agent)

if __name__ == '__main__':
    unittest.main()
