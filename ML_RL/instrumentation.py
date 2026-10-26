"""
ML instrumentation and lightweight collector.
Writes JSONL entries to `training/data/raw/` and provides simple rotate-by-size logic.
"""
from __future__ import annotations
import os
import json
import gzip
import time
from datetime import datetime
from threading import Lock, Thread
from queue import Queue, Empty
from typing import Dict, Any, Optional

BASE = os.path.join(os.path.dirname(__file__), 'data', 'raw')
os.makedirs(BASE, exist_ok=True)

class MLDataCollector:
    """Non-blocking JSONL event collector using a background writer thread.

    Usage:
        collector = MLDataCollector()
        collector.record_event('order', {...})  # returns quickly
        collector.close()  # flushes queued events and stops writer thread
    """
    def __init__(self, prefix: str = 'events', rotate_size_bytes: int = 10_000_000, queue_max: int = 10000):
        self.prefix = prefix
        self.rotate_size_bytes = rotate_size_bytes
        self._queue: Queue[str] = Queue(maxsize=queue_max)
        self._stop_marker = object()
        self._thread = Thread(target=self._writer_loop, name=f"ml-writer-{self.prefix}", daemon=True)
        self._open_path: Optional[str] = None
        self._open_handle = None
        self._lock = Lock()  # used only by writer thread for file rotation
        self._thread.start()

    def _path(self):
        ts = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
        return os.path.join(BASE, f"{self.prefix}.{ts}.jsonl.gz")

    def _ensure_rotated(self):
        # Only called from writer thread under _lock
        if self._open_handle:
            try:
                size = os.path.getsize(self._open_path)
            except Exception:
                size = 0
            if size >= self.rotate_size_bytes:
                try:
                    self._open_handle.close()
                except Exception:
                    pass
                self._open_handle = None
                self._open_path = None
        if not self._open_handle:
            self._open_path = self._path()
            # open in text append mode on gzip
            self._open_handle = gzip.open(self._open_path, 'at', encoding='utf-8')

    def _writer_loop(self):
        buffer = []
        last_flush = time.time()
        FLUSH_INTERVAL = 1.0  # seconds
        while True:
            try:
                item = self._queue.get(timeout=FLUSH_INTERVAL)
                if item is self._stop_marker:
                    # flush remaining buffer then exit
                    if buffer:
                        self._flush_buffer(buffer)
                        buffer = []
                    break
                buffer.append(item)
                # Bulk write when enough buffered or time elapsed
                if len(buffer) >= 100 or (time.time() - last_flush) >= FLUSH_INTERVAL:
                    self._flush_buffer(buffer)
                    buffer = []
                    last_flush = time.time()
            except Empty:
                # Periodic flush
                if buffer and (time.time() - last_flush) >= FLUSH_INTERVAL:
                    self._flush_buffer(buffer)
                    buffer = []
                    last_flush = time.time()
                continue
            except Exception:
                # Unexpected error in writer thread; swallow to avoid crashing
                try:
                    import logging
                    logging.getLogger('cthulu.ml').exception('ML writer loop error')
                except Exception:
                    pass
                continue

    def _flush_buffer(self, buffer):
        # Write buffer lines to file under lock
        if not buffer:
            return
        with self._lock:
            try:
                self._ensure_rotated()
                if self._open_handle:
                    for line in buffer:
                        try:
                            self._open_handle.write(line + "\n")
                        except Exception:
                            # If write fails, fallback to an uncompressed file append for that line
                            try:
                                fallback = os.path.join(BASE, f"{self.prefix}.fallback.{int(time.time())}.jsonl")
                                with open(fallback, 'a', encoding='utf-8') as f:
                                    f.write(line + "\n")
                            except Exception:
                                pass
                    try:
                        self._open_handle.flush()
                    except Exception:
                        pass
            except Exception:
                try:
                    import logging
                    logging.getLogger('cthulu.ml').exception('Failed to flush ML buffer')
                except Exception:
                    pass

    def record_event(self, event_type: str, payload: Dict[str, Any]):
        entry = {
            'ts': datetime.utcnow().isoformat() + 'Z',
            'event_type': event_type,
            'payload': payload
        }
        line = json.dumps(entry, default=str)
        try:
            # Non-blocking put with small timeout to avoid stalling application
            self._queue.put(line, timeout=0.1)
        except Exception:
            # Queue full or other issue; fallback to best-effort synchronous write
            try:
                fallback = os.path.join(BASE, f"{self.prefix}.fallback.{int(time.time())}.jsonl")
                with open(fallback, 'a', encoding='utf-8') as f:
                    f.write(line + "\n")
            except Exception:
                pass

    def record_order(self, order_req: Dict[str, Any]):
        self.record_event('order_request', order_req)

    def record_execution(self, exec_result: Dict[str, Any]):
        self.record_event('execution', exec_result)

    def record_market_snapshot(self, snapshot: Dict[str, Any]):
        self.record_event('market_snapshot', snapshot)

    def close(self, timeout: float = 5.0):
        """Flush queued events and stop the writer thread."""
        try:
            self._queue.put(self._stop_marker, timeout=0.5)
        except Exception:
            pass
        if self._thread.is_alive():
            self._thread.join(timeout=timeout)
        # Final flush and close file handle
        with self._lock:
            try:
                if self._open_handle:
                    try:
                        self._open_handle.close()
                    except Exception:
                        pass
                    self._open_handle = None
                    self._open_path = None
            except Exception:
                pass



