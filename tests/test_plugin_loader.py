import unittest
import sys
import json
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.plugin_loader import PluginLoader

class TestPluginLoader(unittest.TestCase):
    """Test plugin discovery and loading."""

    def test_plugin_discovery(self):
        """Test that plugin loader can discover plugins."""
        loader = PluginLoader([Path("plugins/modules"), Path("plugins/loaders")])
        plugins = loader.discover()
        
        # Check that plugin types exist
        self.assertIn("module", plugins)
        self.assertIn("loader", plugins)
        
        # Print discovered plugins for debugging
        print("\nDiscovered plugins:")
        for ptype, plist in plugins.items():
            print(f"  {ptype}: {list(plist.keys())}")

    def test_plugin_instantiation(self):
        """Test that plugins can be instantiated."""
        loader = PluginLoader([Path("plugins/modules")])
        plugins = loader.discover()
        
        if "windows_agent" in plugins.get("module", {}):
            plugin = plugins["module"]["windows_agent"]
            self.assertEqual(plugin.id, "windows_agent")
            self.assertEqual(plugin.type, "module")
            self.assertIn("windows", plugin.platforms)

if __name__ == '__main__':
    unittest.main()
