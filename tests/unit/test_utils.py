"""
Unit tests for utility modules.
"""

import pytest
import time
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.circuit_breaker import CircuitBreaker, CircuitState
from utils.retry import exponential_backoff, RetryConfig, with_retry
from utils.cache import SmartCache
from utils.rate_limiter import SlidingWindowRateLimiter, TokenBucketRateLimiter


class TestCircuitBreaker:
    """Test circuit breaker functionality."""
    
    def test_circuit_starts_closed(self):
        """Circuit should start in CLOSED state."""
        breaker = CircuitBreaker()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.is_closed
        assert not breaker.is_open
    
    def test_successful_calls_keep_circuit_closed(self):
        """Successful calls should keep circuit closed."""
        breaker = CircuitBreaker()
        
        for _ in range(10):
            result = breaker.call(lambda: "success")
            assert result == "success"
        
        assert breaker.is_closed
        assert breaker.failure_count == 0
    
    def test_circuit_opens_after_threshold_failures(self):
        """Circuit should open after reaching failure threshold."""
        breaker = CircuitBreaker(failure_threshold=3, timeout=1)
        
        def failing_func():
            raise ValueError("Test error")
        
        # Trigger failures
        for i in range(3):
            with pytest.raises(ValueError):
                breaker.call(failing_func)
        
        assert breaker.is_open
        assert breaker.failure_count == 3
    
    def test_open_circuit_rejects_calls(self):
        """Open circuit should reject new calls."""
        breaker = CircuitBreaker(failure_threshold=1, timeout=1)
        
        # Trigger failure to open circuit
        with pytest.raises(ValueError):
            breaker.call(lambda: (_ for _ in ()).throw(ValueError("Fail")))
        
        # Circuit should reject next call
        with pytest.raises(Exception, match="Circuit breaker.*is OPEN"):
            breaker.call(lambda: "test")
    
    def test_circuit_half_open_after_timeout(self):
        """Circuit should enter HALF_OPEN after timeout."""
        breaker = CircuitBreaker(failure_threshold=1, timeout=0.1)
        
        # Open circuit
        with pytest.raises(ValueError):
            breaker.call(lambda: (_ for _ in ()).throw(ValueError("Fail")))
        
        assert breaker.is_open
        
        # Wait for timeout
        time.sleep(0.2)
        
        # Next call should trigger HALF_OPEN
        result = breaker.call(lambda: "recovered")
        assert result == "recovered"
        assert breaker.is_closed
    
    def test_circuit_reset(self):
        """Manual reset should close circuit."""
        breaker = CircuitBreaker(failure_threshold=1)
        
        # Open circuit
        with pytest.raises(ValueError):
            breaker.call(lambda: (_ for _ in ()).throw(ValueError("Fail")))
        
        assert breaker.is_open
        
        breaker.reset()
        assert breaker.is_closed
        assert breaker.failure_count == 0


class TestRetry:
    """Test retry logic with exponential backoff."""
    
    def test_successful_call_no_retry(self):
        """Successful call should not trigger retry."""
        call_count = 0
        
        def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = exponential_backoff(successful_func, max_retries=3)
        assert result == "success"
        assert call_count == 1
    
    def test_retry_on_failure(self):
        """Should retry on failure up to max_retries."""
        call_count = 0
        
        def failing_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Not yet")
            return "success"
        
        result = exponential_backoff(failing_func, max_retries=5, initial_delay=0.01)
        assert result == "success"
        assert call_count == 3
    
    def test_exponential_delay(self):
        """Delay should increase exponentially."""
        call_times = []
        
        def failing_func():
            call_times.append(time.time())
            if len(call_times) < 3:
                raise ValueError("Fail")
            return "success"
        
        exponential_backoff(
            failing_func,
            max_retries=5,
            initial_delay=0.1,
            exponential_base=2.0
        )
        
        # Check that delays increase (approximately)
        assert len(call_times) == 3
        delay1 = call_times[1] - call_times[0]
        delay2 = call_times[2] - call_times[1]
        assert delay2 > delay1
    
    def test_max_retries_exceeded(self):
        """Should raise exception after max retries."""
        def always_fails():
            raise ValueError("Always fails")
        
        with pytest.raises(ValueError):
            exponential_backoff(always_fails, max_retries=2, initial_delay=0.01)
    
    def test_retry_decorator(self):
        """Retry decorator should work correctly."""
        config = RetryConfig(max_retries=3, initial_delay=0.01)
        call_count = 0
        
        @with_retry(config)
        def decorated_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Not yet")
            return "success"
        
        result = decorated_func()
        assert result == "success"
        assert call_count == 2


class TestSmartCache:
    """Test smart cache with TTL."""
    
    def test_cache_hit(self):
        """Should return cached value on hit."""
        cache = SmartCache(ttl_seconds=60)
        fetch_count = 0
        
        def fetch_func():
            nonlocal fetch_count
            fetch_count += 1
            return "value"
        
        # First call - cache miss
        result1 = cache.get_or_fetch("key1", fetch_func)
        assert result1 == "value"
        assert fetch_count == 1
        
        # Second call - cache hit
        result2 = cache.get_or_fetch("key1", fetch_func)
        assert result2 == "value"
        assert fetch_count == 1  # Not called again
        assert cache.hits == 1
        assert cache.misses == 1
    
    def test_cache_expiration(self):
        """Should fetch new value after TTL expiration."""
        cache = SmartCache(ttl_seconds=0.1)
        fetch_count = 0
        
        def fetch_func():
            nonlocal fetch_count
            fetch_count += 1
            return f"value_{fetch_count}"
        
        result1 = cache.get_or_fetch("key1", fetch_func)
        assert result1 == "value_1"
        
        # Wait for expiration
        time.sleep(0.15)
        
        result2 = cache.get_or_fetch("key1", fetch_func)
        assert result2 == "value_2"
        assert fetch_count == 2
    
    def test_cache_size_limit(self):
        """Should evict oldest entries when full."""
        cache = SmartCache(ttl_seconds=60, max_size=3)
        
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        
        assert len(cache.cache) == 3
        
        # Adding 4th item should evict oldest
        cache.set("key4", "value4")
        assert len(cache.cache) == 3
        assert cache.get("key1") is None  # Evicted
        assert cache.get("key4") == "value4"
    
    def test_cache_invalidation(self):
        """Should remove invalidated keys."""
        cache = SmartCache()
        cache.set("key1", "value1")
        
        assert cache.get("key1") == "value1"
        
        cache.invalidate("key1")
        assert cache.get("key1") is None
    
    def test_cache_statistics(self):
        """Should track cache statistics correctly."""
        cache = SmartCache()
        
        cache.get_or_fetch("key1", lambda: "value1")
        cache.get_or_fetch("key1", lambda: "value1")  # Hit
        cache.get_or_fetch("key2", lambda: "value2")
        
        stats = cache.get_stats()
        assert stats['hits'] == 1
        assert stats['misses'] == 2
        assert stats['size'] == 2


class TestSlidingWindowRateLimiter:
    """Test sliding window rate limiter."""
    
    def test_allows_requests_under_limit(self):
        """Should allow requests under the limit."""
        limiter = SlidingWindowRateLimiter(max_calls=5, window_seconds=1)
        
        for _ in range(5):
            assert limiter.allow_request() is True
    
    def test_rejects_requests_over_limit(self):
        """Should reject requests over the limit."""
        limiter = SlidingWindowRateLimiter(max_calls=3, window_seconds=1)
        
        # Use up the limit
        for _ in range(3):
            limiter.allow_request()
        
        # Next request should be rejected
        assert limiter.allow_request() is False
    
    def test_sliding_window_allows_after_expiry(self):
        """Should allow requests after old ones expire."""
        limiter = SlidingWindowRateLimiter(max_calls=2, window_seconds=0.1)
        
        # Use up limit
        limiter.allow_request()
        limiter.allow_request()
        assert limiter.allow_request() is False
        
        # Wait for window to slide
        time.sleep(0.15)
        
        # Should allow request again
        assert limiter.allow_request() is True
    
    def test_wait_time_calculation(self):
        """Should calculate wait time correctly."""
        limiter = SlidingWindowRateLimiter(max_calls=2, window_seconds=1)
        
        limiter.allow_request()
        limiter.allow_request()
        
        wait_time = limiter.wait_time()
        assert wait_time > 0
        assert wait_time <= 1.0
    
    def test_rate_limiter_statistics(self):
        """Should track statistics correctly."""
        limiter = SlidingWindowRateLimiter(max_calls=5, window_seconds=1)
        
        for _ in range(7):
            limiter.allow_request()
        
        stats = limiter.get_stats()
        assert stats['total_calls'] == 5
        assert stats['rejected_calls'] == 2
        assert stats['current_calls'] <= 5


class TestTokenBucketRateLimiter:
    """Test token bucket rate limiter."""
    
    def test_allows_burst_requests(self):
        """Should allow burst of requests up to capacity."""
        limiter = TokenBucketRateLimiter(rate=1.0, capacity=5)
        
        # Should allow burst of 5 requests
        for _ in range(5):
            assert limiter.allow_request() is True
        
        # 6th request should fail
        assert limiter.allow_request() is False
    
    def test_refills_tokens_over_time(self):
        """Tokens should refill over time."""
        limiter = TokenBucketRateLimiter(rate=10.0, capacity=10)  # 10 tokens/sec
        
        # Use all tokens
        for _ in range(10):
            limiter.allow_request()
        
        assert limiter.allow_request() is False
        
        # Wait for refill (0.2 seconds = 2 tokens)
        time.sleep(0.2)
        
        # Should allow 2 more requests
        assert limiter.allow_request() is True
        assert limiter.allow_request() is True
    
    def test_wait_time_calculation(self):
        """Should calculate wait time for tokens."""
        limiter = TokenBucketRateLimiter(rate=1.0, capacity=5)
        
        # Use all tokens
        for _ in range(5):
            limiter.allow_request()
        
        wait_time = limiter.wait_time(tokens=1)
        assert wait_time > 0
        assert wait_time <= 1.0




