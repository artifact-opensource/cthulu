from __future__ import annotations
from typing import List, Optional
import requests
import logging
from .base import NewsAdapter, NewsEvent
import time

logger = logging.getLogger('cthulu.news.tradingeconomics')


class TradingEconomicsAdapter(NewsAdapter):
    """Adapter to fetch economic calendar events from TradingEconomics

    Notes:
    - If no API key is supplied, the adapter is a no-op and returns [].
    - For production integration you may want to refine the request parameters
      (country, start/end dates, importance filtering), this is a minimal PoC.
    """
    def __init__(self, api_key: Optional[str] = None, timeout: float = 5.0):
        self.api_key = api_key
        self.timeout = timeout

    def fetch_recent(self) -> List[NewsEvent]:
        if not self.api_key:
            return []
        try:
            # Basic calendar endpoint - TradingEconomics uses `c` for client key
            url = 'https://api.tradingeconomics.com/calendar'
            params = {'c': self.api_key, 'format': 'json', 'last': 10}
            resp = requests.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json() or []
            out = []
            for ev in data:
                try:
                    ts = time.time()
                    provider = 'TradingEconomics'
                    symbol = ev.get('country') or 'GLOBAL'
                    headline = ev.get('event') or ev.get('title') or 'Economic event'
                    body = str(ev)
                    # Normalize importance/impact if provided
                    importance_raw = ev.get('importance') or ev.get('impact') or ev.get('impact_level')
                    importance = None
                    if importance_raw is not None:
                        try:
                            # If numeric, map thresholds; otherwise normalize common strings
                            if isinstance(importance_raw, (int, float)):
                                if importance_raw >= 8:
                                    importance = 'high'
                                elif importance_raw >= 4:
                                    importance = 'medium'
                                else:
                                    importance = 'low'
                            else:
                                s = str(importance_raw).strip().lower()
                                if 'high' in s or 'major' in s:
                                    importance = 'high'
                                elif 'med' in s or 'medium' in s:
                                    importance = 'medium'
                                elif 'low' in s:
                                    importance = 'low'
                        except Exception:
                            importance = None

                    meta = dict(ev)
                    if importance:
                        meta['importance'] = importance

                    evt = NewsEvent(provider=provider, ts=ts, symbol=symbol, headline=headline, body=body, meta=meta)
                    out.append(evt)
                except Exception:
                    continue
            return out
        except Exception:
            logger.exception('Failed to fetch tradingeconomics calendar')
            return []




