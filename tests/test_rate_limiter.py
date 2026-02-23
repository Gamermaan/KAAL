
import unittest
import time
import sys
import os
import threading
from unittest.mock import MagicMock, patch

# Add parent directory to path to import standalone_agent
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from standalone_agent import RateLimiter, DiscordRelay

class TestRateLimiter(unittest.TestCase):
    def test_token_consumption(self):
        limiter = RateLimiter(max_tokens=5, refill_rate=10.0)
        # Consume 5
        self.assertTrue(limiter.try_acquire(5))
        # Should be empty
        self.assertFalse(limiter.try_acquire(1))
        
    def test_refill(self):
        limiter = RateLimiter(max_tokens=5, refill_rate=10.0) # 10 tokens/sec = 1 token/0.1s
        limiter.try_acquire(5) # Empty it
        self.assertFalse(limiter.try_acquire(1))
        
        time.sleep(0.15) # Wait for >1 token
        self.assertTrue(limiter.try_acquire(1))

    def test_wait_for_token(self):
        limiter = RateLimiter(max_tokens=1, refill_rate=5.0) # 1 token/0.2s
        limiter.try_acquire(1) # Empty
        
        start = time.time()
        limiter.wait_for_token(1)
        duration = time.time() - start
        
        self.assertGreater(duration, 0.15)
        self.assertLess(duration, 0.3)

class TestBackoff(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_429_backoff(self, mock_urlopen):
        # Setup Relay
        relay = DiscordRelay({"token": "test", "channel_id": "test"})
        # Bypass rate limiter for this test
        relay.limiter = MagicMock()
        
        # Mock 429 Error
        error_429 = urllib.error.HTTPError(
            url="http://test", code=429, msg="Too Many Requests", 
            hdrs={}, fp=MagicMock()
        )
        error_429.read = MagicMock(return_value=b'{"retry_after": 1}')
        
        # Mock success on 2nd attempt
        success_response = MagicMock()
        success_response.read.return_value = b'{"success": true}'
        success_response.__enter__.return_value = success_response
        
        # Side effect: Raise 429 once, then return success
        mock_urlopen.side_effect = [error_429, success_response]
        
        start = time.time()
        res = relay._api("GET", "test")
        duration = time.time() - start
        
        # Should have waited at least 1s (retry_after)
        self.assertGreater(duration, 1.0)
        self.assertEqual(res, {"success": True})

import urllib.error # Needed for mock setup
if __name__ == "__main__":
    unittest.main()
