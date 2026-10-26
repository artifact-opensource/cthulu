from cthulu.news.newsapi_adapter import NewsApiAdapter


def test_news_api_adapter_returns_events():
    adapter = NewsApiAdapter(api_key='dummy')
    events = adapter.fetch_recent()
    assert events and isinstance(events[0].headline, str)




