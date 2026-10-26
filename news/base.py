from typing import List, Dict, Any
from dataclasses import dataclass

@dataclass
class NewsEvent:
    provider: str
    ts: float
    symbol: str
    headline: str
    body: str
    meta: Dict[str, Any]


class NewsAdapter:
    """Base class for news/economic calendar adapters."""
    def fetch_recent(self) -> List[NewsEvent]:
        """Fetch recent news/events and return as list of NewsEvent."""
        raise NotImplementedError()




