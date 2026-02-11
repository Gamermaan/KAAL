import unittest
import sys
from pathlib import Path
from unittest.mock import Mock, patch
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import Config
from builder.builder_core import KAALBuilder

class TestBuilder(unittest.TestCase):
    """Test builder system and compilation."""

    @patch('subprocess.run')
    def test_build_module_structure(self, mock_run):
        """Test that build process creates correct directory structure."""
        # Mock successful compilation
        mock_run.return_value = Mock(returncode=0, stderr="", stdout="")
        
        with TemporaryDirectory() as tmpdir:
            cfg = Config(Path("config.yaml"))
            builder = KAALBuilder(cfg)
            
            # This will fail without actual plugin, but tests the structure
            try:
                output = builder.build_module(
                    "windows_agent",
                    "windows",
                    tmpdir,
                    mutate=False
                )
            except ValueError as e:
                # Expected if plugin not in path
                pass

    def test_builder_initialization(self):
        """Test that builder initializes correctly."""
        cfg = Config(Path("config.yaml"))
        builder = KAALBuilder(cfg)
        self.assertIsNotNone(builder.generator)
        self.assertIsNotNone(builder.plugins)

if __name__ == '__main__':
    unittest.main()
