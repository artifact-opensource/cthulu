import time
from cthulu.news.manager import NewsManager
from cthulu.news.base import NewsEvent, NewsAdapter
from cthulu.news.ingest import NewsIngestor
from cthulu.ML_RL.instrumentation import MLDataCollector


class FakeManager(NewsManager):
    def __init__(self, events):
        self._events = events

    def fetch_recent(self):
        return self._events


class DummyAdapter(NewsAdapter):
    def __init__(self, events):
        self._events = events

    def fetch_recent(self):
        return self._events


def test_ingestor_records_events(tmp_path):
    ev = NewsEvent(provider='X', ts=123.0, symbol='TEST', headline='h', body='b', meta={})
    mgr = FakeManager([ev])
    cal = DummyAdapter([ev])
    collector = MLDataCollector(prefix=f'test_ingest_{int(time.time())}', rotate_size_bytes=200)
    ing = NewsIngestor(mgr, cal, collector, interval_seconds=1)
    ing.start()
    # let it run a couple of loops
    time.sleep(1.5)
    ing.stop()
    collector.close()

    # Verify some output files exist for the collector prefix
    import os
    # Use the collector's BASE directory for ML files
    from cthulu.ML_RL.instrumentation import BASE as ML_BASE
    files = [f for f in os.listdir(ML_BASE) if f.startswith(collector.prefix)]
    assert files, 'No ML files written by ingest loop'





