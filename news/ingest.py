from __future__ import annotations
import threading
import time
from typing import Optional
import logging
from .manager import NewsManager
from .base import NewsAdapter, NewsEvent
from cthulu.ML_RL.instrumentation import MLDataCollector

logger = logging.getLogger('cthulu.news.ingest')


class NewsIngestor:
    """Periodically fetches news and calendar events and records to ML collector.

    Usage:
        ing = NewsIngestor(news_manager, calendar_adapter, ml_collector, interval_seconds=300)
        ing.start()
        ...
        ing.stop()
    """
    def __init__(self, news_manager: NewsManager, calendar_adapter: Optional[NewsAdapter], ml_collector: MLDataCollector, interval_seconds: int = 300):
        self.news_manager = news_manager
        self.calendar_adapter = calendar_adapter
        self.ml_collector = ml_collector
        self.interval = interval_seconds
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name='news-ingestor', daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    def _run(self):
        while not self._stop.is_set():
            try:
                events = self.news_manager.fetch_recent() or []
                for e in events:
                    try:
                        payload = e.__dict__
                        self.ml_collector.record_event('news_event', payload)
                    except Exception:
                        logger.exception('Failed to record news event')

                if self.calendar_adapter:
                    try:
                        cal = self.calendar_adapter.fetch_recent() or []
                        for e in cal:
                            try:
                                payload = e.__dict__
                                self.ml_collector.record_event('calendar_event', payload)
                            except Exception:
                                logger.exception('Failed to record calendar event')
                    except Exception:
                        logger.exception('Calendar adapter failed')
            except Exception:
                logger.exception('News ingest loop error')
            # Sleep with early exit
            for _ in range(int(max(1, self.interval))):
                if self._stop.is_set():
                    break
                time.sleep(1)





