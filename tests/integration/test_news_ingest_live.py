import os
import time
import pytest
from cthulu.ML_RL.instrumentation import MLDataCollector


def test_news_ingest_live_one_cycle():
    # Gated: set RUN_NEWS_INTEGRATION=1 to enable this test
    if os.getenv('RUN_NEWS_INTEGRATION') != '1':
        pytest.skip('News integration tests disabled - set RUN_NEWS_INTEGRATION=1 to enable')

    # Require at least one provider to be configured
    if not (os.getenv('NEWSAPI_KEY') or os.getenv('FRED_API_KEY') or os.getenv('NEWS_RSS_FEEDS') or os.getenv('ECON_CAL_API_KEY')):
        pytest.skip('No external news/calendar providers configured in environment')

    # Build adapters similar to production flow
    from cthulu.news import RssAdapter, NewsApiAdapter, FREDAdapter, TradingEconomicsAdapter, NewsManager, NewsIngestor

    adapters = []
    if os.getenv('NEWS_USE_RSS', 'true').lower() in ('1', 'true', 'yes'):
        feeds = os.getenv('NEWS_RSS_FEEDS', '')
        feeds_list = [f.strip() for f in feeds.split(',') if f.strip()]
        if feeds_list:
            adapters.append(RssAdapter(feeds=feeds_list))

    if os.getenv('NEWSAPI_KEY'):
        adapters.append(NewsApiAdapter(api_key=os.getenv('NEWSAPI_KEY')))
    if os.getenv('FRED_API_KEY'):
        adapters.append(FREDAdapter(api_key=os.getenv('FRED_API_KEY')))

    manager = NewsManager(adapters=adapters, cache_ttl=int(os.getenv('NEWS_CACHE_TTL', '60')))
    cal = TradingEconomicsAdapter(api_key=os.getenv('ECON_CAL_API_KEY')) if os.getenv('ECON_CAL_API_KEY') else None

    collector = MLDataCollector(prefix=f'int_news_{int(time.time())}', rotate_size_bytes=1024 * 10)
    ing = NewsIngestor(manager, cal, collector, interval_seconds=2)
    try:
        ing.start()
        # allow a couple of cycles
        time.sleep(4)
    finally:
        ing.stop()
        collector.close()

    # Check ML raw output files for the collector prefix
    from cthulu.ML_RL.instrumentation import BASE as ML_BASE
    files = [f for f in os.listdir(ML_BASE) if f.startswith(collector.prefix)]
    assert files, 'No ML files written by live news ingest (check provider keys and network)'





