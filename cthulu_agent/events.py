"""Tiny thread-safe pub/sub with a replay ring, feeding the dashboard's live stream."""
from __future__ import annotations

import collections
import queue
import threading
import time
from typing import Any, Deque, Dict, List, Set


class EventBus:
    def __init__(self, ring: int = 400):
        self._lock = threading.Lock()
        self._subs: Set[queue.Queue] = set()
        self._ring: Deque[Dict[str, Any]] = collections.deque(maxlen=ring)
        self._seq = 0

    def emit(self, type_: str, **data: Any) -> Dict[str, Any]:
        with self._lock:
            self._seq += 1
            evt = {"id": self._seq, "ts": time.time(), "type": type_, "data": data}
            self._ring.append(evt)
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(evt)
            except queue.Full:
                pass
        return evt

    def subscribe(self, replay: int = 30) -> "queue.Queue":
        q: queue.Queue = queue.Queue(maxsize=500)
        with self._lock:
            self._subs.add(q)
            for e in list(self._ring)[-replay:]:
                q.put_nowait(e)
        return q

    def unsubscribe(self, q: "queue.Queue") -> None:
        with self._lock:
            self._subs.discard(q)

    def recent(self, n: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._ring)[-n:]
