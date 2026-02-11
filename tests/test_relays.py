import unittest
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from console.relay_manager import RelayManager

class TestRelays(unittest.TestCase):
    """Test relay encryption and message handling."""

    def setUp(self):
        self.manager = RelayManager()

    def test_encryption_decryption(self):
        """Test that encryption/decryption is symmetric."""
        original = "test message 123"
        encrypted = self.manager._encrypt(original)
        decrypted = self.manager._decrypt(encrypted)
        self.assertEqual(original, decrypted)

    def test_encryption_changes_text(self):
        """Test that encryption actually changes the text."""
        original = "test message"
        encrypted = self.manager._encrypt(original)
        self.assertNotEqual(original, encrypted)

    @patch('console.relay_manager.time.time')
    def test_message_processing(self, mock_time):
        """Test agent registration message processing."""
        mock_time.return_value = 1234567890.0
        
        # Simulate agent registration message
        message = {
            "agent_id": "test-agent-001",
            "type": "register",
            "platform": "windows",
            "hostname": "TEST-PC"
        }
        
        import json
        encrypted = self.manager._encrypt(json.dumps(message))
        self.manager._process_message("telegram", encrypted)
        
        # Check that agent was registered
        self.assertIn("test-agent-001", self.manager.agents)
        agent_info = self.manager.agents["test-agent-001"]
        self.assertEqual(agent_info["platform"], "windows")
        self.assertEqual(agent_info["via"], "telegram")

if __name__ == '__main__':
    unittest.main()
