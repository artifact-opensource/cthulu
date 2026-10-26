from .base import NewsAdapter, NewsEvent
from .newsapi_adapter import NewsApiAdapter
from .rss_adapter import RssAdapter
from .manager import NewsManager
from .fred_adapter import FREDAdapter
from .tradingeconomics_adapter import TradingEconomicsAdapter
from .ingest import NewsIngestor

__all__ = ['NewsAdapter', 'NewsApiAdapter', 'RssAdapter', 'NewsManager', 'NewsEvent', 'FREDAdapter', 'TradingEconomicsAdapter', 'NewsIngestor']




