from __future__ import annotations
import time
from typing import List, Optional
import requests
import logging
from .base import NewsAdapter, NewsEvent
from datetime import datetime

logger = logging.getLogger('cthulu.news.fred')


class FREDAdapter(NewsAdapter):
    """Adapter to fetch recent FRED series latest observations.

    This is intentionally lightweight: by default it will fetch the latest
    observation for a short list of series (configurable) and return them
    as NewsEvent objects for ingestion into ML pipelines.
    """
    def __init__(self, api_key: Optional[str] = None, series: Optional[List[str]] = None, timeout: float = 5.0):
        self.api_key = api_key
        self.series = series or ['GDP']
        self.timeout = timeout

    def fetch_recent(self) -> List[NewsEvent]:
        if not self.api_key:
            return []
        out = []
        for s in self.series:
            try:
                url = 'https://api.stlouisfed.org/fred/series/observations'
                params = {
                    'series_id': s,
                    'api_key': self.api_key,
                    'file_type': 'json',
                    'limit': 1,
                    'sort_order': 'desc',
                }
                resp = requests.get(url, params=params, timeout=self.timeout)
                resp.raise_for_status()
                data = resp.json()
                obs = data.get('observations') or []
                if not obs:
                    continue
                latest = obs[0]
                date = latest.get('date')
                value = latest.get('value')
                try:
                    ts = datetime.strptime(date, '%Y-%m-%d').timestamp()
                except Exception:
                    ts = time.time()
                headline = f'FRED {s} latest {date}: {value}'
                body = f'Latest observation for {s}: {value} (as of {date})'
                evt = NewsEvent(provider='FRED', ts=ts, symbol=s, headline=headline, body=body, meta={'value': value})
                out.append(evt)
            except Exception:
                logger.exception('Failed to fetch FRED series %s', s)
                continue
        return out




