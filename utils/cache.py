"""
Smart caching with TTL support.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Optional, TypeVar, Generic

T = TypeVar('T')

logger = logging.getLogger(__name__)


class SmartCache(Generic[T]):
    """
    Cache with TTL (Time To Live) support.
    
    Usage:
        cache = SmartCache(ttl_seconds=60)
        
        def fetch_data():
            return expensive_api_call()
        
        data = cache.get_or_fetch("key", fetch_data)
    """
    
    def __init__(self, ttl_seconds: int = 60, max_size: int = 1000):
        """
        Initialize cache.
        
        Args:
            ttl_seconds: Time to live for cached items
            max_size: Maximum number of items to cache
        """
        self.ttl = ttl_seconds
        self.max_size = max_size
        self.cache: dict[str, tuple[T, datetime]] = {}
        self.hits = 0
        self.misses = 0
    
    def get_or_fetch(self, key: str, fetch_func: Callable[[], T]) -> T:
        """
        Get cached value or fetch and cache it.
        
        Args:
            key: Cache key
            fetch_func: Function to call if cache miss
            
        Returns:
            Cached or freshly fetched value
        """
        # Check if key exists and is not expired
        if key in self.cache:
            value, timestamp = self.cache[key]
            age = datetime.now() - timestamp
            
            if age < timedelta(seconds=self.ttl):
                self.hits += 1
                logger.debug(f"Cache hit: {key} (age: {age.total_seconds():.1f}s)")
                return value
            else:
                logger.debug(f"Cache expired: {key} (age: {age.total_seconds():.1f}s)")
        
        # Cache miss - fetch new value
        self.misses += 1
        logger.debug(f"Cache miss: {key}, fetching new value")
        
        value = fetch_func()
        self.set(key, value)
        
        return value
    
    def set(self, key: str, value: T):
        """
        Set cache value.
        
        Args:
            key: Cache key
            value: Value to cache
        """
        # Evict oldest items if cache is full
        if len(self.cache) >= self.max_size:
            self._evict_oldest()
        
        self.cache[key] = (value, datetime.now())
    
    def get(self, key: str) -> Optional[T]:
        """
        Get cached value if exists and not expired.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None
        """
        if key in self.cache:
            value, timestamp = self.cache[key]
            age = datetime.now() - timestamp
            
            if age < timedelta(seconds=self.ttl):
                return value
        
        return None
    
    def invalidate(self, key: str):
        """Remove key from cache."""
        if key in self.cache:
            del self.cache[key]
            logger.debug(f"Cache invalidated: {key}")
    
    def clear(self):
        """Clear entire cache."""
        self.cache.clear()
        logger.info("Cache cleared")
    
    def _evict_oldest(self):
        """Evict oldest cache entry."""
        if not self.cache:
            return
        
        oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k][1])
        del self.cache[oldest_key]
        logger.debug(f"Cache evicted: {oldest_key}")
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        total_requests = self.hits + self.misses
        hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0.0
        
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': hit_rate,
            'ttl_seconds': self.ttl
        }




