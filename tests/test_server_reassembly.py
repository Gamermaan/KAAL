import sys
import os
import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

# Add parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock terminal_state before importing web.server (because web.server imports it)
with patch("web.server.terminal_state") as mock_state:
    from web.server import app, agents

client = TestClient(app)

class TestServerReassembly(unittest.TestCase):
    def setUp(self):
        # Clear agents
        agents.clear()
        # Register a test agent
        self.agent_id = "test-agent-123"
        agents[self.agent_id] = {
            "id": self.agent_id,
            "tasks": [],
            "status": "active"
        }

    @patch("web.server.terminal_state.broadcast")
    def test_chunk_reassembly(self, mock_broadcast):
        mock_broadcast.return_value = None # Async mock handled by patch? No, broadcast is async.
        # But TestClient calls are synchronous wrappers around async app.
        # We need mock_broadcast to be awaitable or just check call_args.
        # Since 'await terminal_state.broadcast' is called, mock_broadcast MUST be awaitable.
        
        async def async_mock(*args, **kwargs):
            return None
        
        mock_broadcast.side_effect = async_mock 
        
        stream_id = "stream-1"
        task_id = "task-1"
        chunk1 = "Hello "
        chunk2 = "World!"
        
        # Send Chunk 1
        resp1 = client.post("/api/v1/agent_message", json={
            "type": "chunk",
            "agent_id": self.agent_id,
            "task_id": task_id,
            "stream_id": stream_id,
            "index": 0,
            "total": 2,
            "data": chunk1
        })
        self.assertEqual(resp1.status_code, 200)
        
        # Verify partial upload stored
        self.assertIn("partial_uploads", agents[self.agent_id])
        self.assertIn(stream_id, agents[self.agent_id]["partial_uploads"])
        self.assertEqual(len(agents[self.agent_id]["partial_uploads"][stream_id]), 1)
        
        # Send Chunk 2
        resp2 = client.post("/api/v1/agent_message", json={
            "type": "chunk",
            "agent_id": self.agent_id,
            "task_id": task_id,
            "stream_id": stream_id,
            "index": 1,
            "total": 2,
            "data": chunk2
        })
        self.assertEqual(resp2.status_code, 200)
        
        # Verify call to broadcast("task_result", ...)
        # We need to check if mock_broadcast was called with correct data
        # Since it was called multiple times (maybe for status/ack/etc? No, just chunk here), check arguments.
        
        called_with_result = False
        for call in mock_broadcast.call_args_list:
            args = call.args
            if args[0] == "task_result":
                payload = args[1]
                if payload.get("result") == "Hello World!":
                    called_with_result = True
                    break
        
        self.assertTrue(called_with_result, "Did not broadcast reassembled result 'Hello World!'")

if __name__ == "__main__":
    unittest.main()
