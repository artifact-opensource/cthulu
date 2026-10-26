from cthulu.news.newsapi_adapter import NewsApiAdapter
from cthulu.news.rss_adapter import RssAdapter
from cthulu.news.manager import NewsManager


def test_news_manager_fallback(tmp_path, monkeypatch):
    # Adapter 1 raises, adapter 2 returns
    class FailAdapter(NewsApiAdapter):
        def fetch_recent(self):
            raise RuntimeError('fail')

    class SuccessAdapter(RssAdapter):
        def __init__(self):
            super().__init__(feeds=[])
        def fetch_recent(self):
            return [
                type('E', (), {'provider': 'rss', 'ts': 0, 'symbol': 'GOLD', 'headline': 'h', 'body': 'b', 'meta': {}})()
            ]

    manager = NewsManager([FailAdapter(api_key='x'), SuccessAdapter()], cache_ttl=1)
    events = manager.fetch_recent()
    assert events and events[0].symbol == 'GOLD'

    # Subsequent fetch should hit cache
    events2 = manager.fetch_recent()
    assert events2 and events2[0].symbol == 'GOLD'



