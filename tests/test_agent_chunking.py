import unittest
import sys
import os
import json
import uuid
import time
from unittest.mock import MagicMock, patch

# Add parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from standalone_agent import DiscordRelay, AGENT_ID

class TestAgentChunking(unittest.TestCase):
    def test_chunking(self):
        # Create relay
        relay = DiscordRelay({"token": "test", "channel_id": "test"})
        relay.limiter = MagicMock() # Bypass rate limiter
        relay._api = MagicMock()
        relay._encode = MagicMock(side_effect=lambda x: json.dumps(x)) # Simple JSON encoding
        relay._upload_large = MagicMock() # Mock upload
        
        # Create large result (should be > 512KB)
        CHUNK_SIZE = 512 * 1024
        large_data = "A" * (CHUNK_SIZE) + "B" * 100 # 512KB + 100 bytes
        task_id = "test-task"
        
        # Send
        relay.send_result(task_id, large_data)
        
        # Verify calls
        # Expected:
        # - 1 call to _upload_large (chunk 0, size 512KB)
        # - 1 call to _api (chunk 1, size 100 bytes)
        
        self.assertEqual(relay._upload_large.call_count, 1)
        self.assertEqual(relay._api.call_count, 1)
        
        # Verify content of first chunk (large)
        upload_call_arg = relay._upload_large.call_args[0][0] # arg[0] is encoded payload
        payload_1 = json.loads(upload_call_arg)
        
        self.assertEqual(payload_1["type"], "chunk")
        self.assertEqual(payload_1["index"], 0)
        self.assertEqual(payload_1["total"], 2)
        self.assertEqual(len(payload_1["data"]), CHUNK_SIZE)
        
        # Verify content of second chunk (small via _api)
        # _api args: (method, endpoint, data)
        # data is {"content": "KAAL_AGT:encoded"}
        api_data = relay._api.call_args[1].get("data")
        if not api_data: 
             # try args[2] if kwargs failed, but _api(method, endpoint, data=xxx)
             api_data = relay._api.call_args[0][2] if len(relay._api.call_args[0]) > 2 else relay._api.call_args[1].get("data")
             
        encoded_payload_2 = api_data["content"][9:] # KAAL_AGT:encoded
        payload_2 = json.loads(encoded_payload_2)
        
        self.assertEqual(payload_2["type"], "chunk")
        self.assertEqual(payload_2["index"], 1)
        self.assertEqual(payload_2["total"], 2)
        self.assertEqual(len(payload_2["data"]), 100)
        
        # Verify reassembly
        reassembled = payload_1["data"] + payload_2["data"]
        self.assertEqual(reassembled, large_data)

if __name__ == "__main__":
    unittest.main()
