"""
Rate limiting utilities.
"""

import logging
from collections import deque
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class SlidingWindowRateLimiter:
    """
    Sliding window rate limiter for API calls.
    
    Usage:
        limiter = SlidingWindowRateLimiter(max_calls=100, window_seconds=60)
        
        if limiter.allow_request():
            make_api_call()
        else:
            wait_time = limiter.wait_time()
            time.sleep(wait_time)
    """
    
    def __init__(self, max_calls: int, window_seconds: int, name: str = "default"):
        """
        Initialize rate limiter.
        
        Args:
            max_calls: Maximum number of calls allowed in the time window
            window_seconds: Time window in seconds
            name: Identifier for logging
        """
        self.max_calls = max_calls
        self.window = timedelta(seconds=window_seconds)
        self.name = name
        self.calls: deque[datetime] = deque()
        self.total_calls = 0
        self.rejected_calls = 0
    
    def allow_request(self) -> bool:
        """
        Check if request is allowed under rate limit.
        
        Returns:
            True if request is allowed, False otherwise
        """
        now = datetime.now()
        
        # Remove calls outside the sliding window
        while self.calls and self.calls[0] < now - self.window:
            self.calls.popleft()
        
        # Check if we're under the limit
        if len(self.calls) < self.max_calls:
            self.calls.append(now)
            self.total_calls += 1
            return True
        
        self.rejected_calls += 1
        logger.warning(
            f"Rate limit exceeded for '{self.name}': "
            f"{len(self.calls)}/{self.max_calls} in {self.window.total_seconds()}s"
        )
        return False
    
    def wait_time(self) -> float:
        """
        Get wait time in seconds until next request is allowed.
        
        Returns:
            Seconds to wait before next request
        """
        if len(self.calls) < self.max_calls:
            return 0.0
        
        # Oldest call in the window
        oldest = self.calls[0]
        wait_until = oldest + self.window
        wait_seconds = (wait_until - datetime.now()).total_seconds()
        
        return max(0.0, wait_seconds)
    
    def get_stats(self) -> dict:
        """Get rate limiter statistics."""
        now = datetime.now()
        
        # Clean old calls
        while self.calls and self.calls[0] < now - self.window:
            self.calls.popleft()
        
        return {
            'name': self.name,
            'current_calls': len(self.calls),
            'max_calls': self.max_calls,
            'window_seconds': self.window.total_seconds(),
            'total_calls': self.total_calls,
            'rejected_calls': self.rejected_calls,
            'utilization': (len(self.calls) / self.max_calls * 100) if self.max_calls > 0 else 0.0
        }
    
    def reset(self):
        """Reset rate limiter."""
        self.calls.clear()
        self.total_calls = 0
        self.rejected_calls = 0
        logger.info(f"Rate limiter '{self.name}' reset")


class TokenBucketRateLimiter:
    """
    Token bucket rate limiter with burst support.
    
    Allows bursts of traffic while maintaining long-term rate limit.
    """
    
    def __init__(
        self,
        rate: float,
        capacity: int,
        name: str = "default"
    ):
        """
        Initialize token bucket rate limiter.
        
        Args:
            rate: Tokens added per second
            capacity: Maximum bucket capacity (burst size)
            name: Identifier for logging
        """
        self.rate = rate
        self.capacity = capacity
        self.name = name
        self.tokens = float(capacity)
        self.last_update = datetime.now()
        self.total_requests = 0
        self.rejected_requests = 0
    
    def allow_request(self, tokens: int = 1) -> bool:
        """
        Check if request is allowed.
        
        Args:
            tokens: Number of tokens to consume
            
        Returns:
            True if request is allowed, False otherwise
        """
        self._refill()
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            self.total_requests += 1
            return True
        
        self.rejected_requests += 1
        logger.warning(
            f"Rate limit exceeded for '{self.name}': "
            f"{self.tokens:.1f}/{self.capacity} tokens available"
        )
        return False
    
    def _refill(self):
        """Refill tokens based on elapsed time."""
        now = datetime.now()
        elapsed = (now - self.last_update).total_seconds()
        self.last_update = now
        
        # Add tokens based on rate and elapsed time
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
    
    def wait_time(self, tokens: int = 1) -> float:
        """
        Calculate wait time for required tokens.
        
        Args:
            tokens: Number of tokens needed
            
        Returns:
            Seconds to wait
        """
        self._refill()
        
        if self.tokens >= tokens:
            return 0.0
        
        tokens_needed = tokens - self.tokens
        return tokens_needed / self.rate
    
    def get_stats(self) -> dict:
        """Get rate limiter statistics."""
        self._refill()
        
        return {
            'name': self.name,
            'tokens_available': self.tokens,
            'capacity': self.capacity,
            'rate_per_second': self.rate,
            'total_requests': self.total_requests,
            'rejected_requests': self.rejected_requests,
            'utilization': ((self.capacity - self.tokens) / self.capacity * 100) if self.capacity > 0 else 0.0
        }




