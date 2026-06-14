from cthulu.news.manager import NewsManager
from cthulu.news.fred_adapter import FREDAdapter


def test_manager_with_fred_no_key():
    a = FREDAdapter(api_key=None)
    mgr = NewsManager(adapters=[a], cache_ttl=1)
    assert mgr.fetch_recent() == []




