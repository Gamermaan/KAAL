"""
Rate limiter implementing token bucket algorithm with burst support.
Matches Discord's rate limiting behavior.
"""

import time
import threading
from typing import Optional

class TokenBucket:
    """Token bucket rate limiter."""
    
    def __init__(self, rate: float, capacity: int):
        """
        Args:
            rate: Tokens per second
            capacity: Maximum token bucket size (burst)
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_refill = time.time()
        self._lock = threading.Lock()
    
    def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens from the bucket.
        Returns True if successful, False if rate limited.
        """
        with self._lock:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False
    
    def wait_and_consume(self, tokens: int = 1) -> None:
        """Block until tokens are available."""
        while not self.consume(tokens):
            sleep_time = self._time_until_next_token()
            time.sleep(sleep_time)
    
    def _refill(self):
        """Add tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill
        new_tokens = elapsed * self.rate
        self.tokens = min(self.capacity, self.tokens + new_tokens)
        self.last_refill = now
    
    def _time_until_next_token(self) -> float:
        """Calculate time until next token becomes available."""
        with self._lock:
            self._refill()
            if self.tokens < 1:
                return 1.0 / self.rate
            return 0.0

class RateLimiter:
    """
    Combined rate limiter for Discord API with per-endpoint limits.
    """
    
    def __init__(self, config: dict):
        self.global_limiter = TokenBucket(
            rate=config.get('max_requests_per_second', 50),
            capacity=config.get('burst_multiplier', 2) * 50
        )
        self.endpoint_limiters = {}
        self._lock = threading.Lock()
    
    def wait_for_endpoint(self, endpoint: str):
        """
        Wait for both global and endpoint-specific rate limits.
        """
        # Global limit first
        self.global_limiter.wait_and_consume()
        
        # Endpoint-specific limit (if any)
        with self._lock:
            if endpoint not in self.endpoint_limiters:
                # Default per-endpoint limit is 5/second
                self.endpoint_limiters[endpoint] = TokenBucket(5, 10)
        
        self.endpoint_limiters[endpoint].wait_and_consume()
