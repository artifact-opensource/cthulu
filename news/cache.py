"""
File-based cache for news/fetch responses to avoid hitting APIs too often.
Stores JSON blobs in a cache directory with TTL.
"""
from __future__ import annotations
import os
import json
import time
from typing import Optional

CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)


class FileCache:
    def __init__(self, namespace: str = 'news', ttl: int = 300):
        self.namespace = namespace
        self.ttl = ttl
        self.path = os.path.join(CACHE_DIR, f"{namespace}.json")

    def get(self) -> Optional[dict]:
        try:
            if not os.path.exists(self.path):
                return None
            with open(self.path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            ts = data.get('_ts', 0)
            if time.time() - ts > self.ttl:
                return None
            return data.get('value')
        except Exception:
            return None

    def set(self, value: dict):
        try:
            payload = {'_ts': int(time.time()), 'value': value}
            with open(self.path, 'w', encoding='utf-8') as fh:
                json.dump(payload, fh)
        except Exception:
            pass




