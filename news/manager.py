"""
NewsManager: orchestrates multiple adapters with fallback and caching
"""
from __future__ import annotations
from typing import List, Dict, Any
from .base import NewsEvent, NewsAdapter
from .cache import FileCache
import logging

logger = logging.getLogger('cthulu.news')

class NewsManager:
    def __init__(self, adapters: List[NewsAdapter], cache_ttl: int = 300):
        self.adapters = adapters
        self.cache = FileCache(namespace='news_manager', ttl=cache_ttl)

    def fetch_recent(self) -> List[NewsEvent]:
        # Try cache first
        cached = self.cache.get()
        if cached is not None:
            try:
                # Rehydrate minimal events
                return [NewsEvent(**e) for e in cached]
            except Exception:
                # If cache corrupt, ignore
                pass

        # Query adapters in order until we get results
        for adapter in self.adapters:
            try:
                events = adapter.fetch_recent()
                if events:
                    try:
                        # Cache the serializable representation
                        ser = [e.__dict__ for e in events]
                        self.cache.set(ser)
                    except Exception:
                        logger.exception('Failed to cache news events')
                    return events
            except Exception:
                logger.exception(f'Adapter {adapter} failed; trying next')
                continue

        # If none produced results, return empty list
        return []




