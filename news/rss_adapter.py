"""
Simple RSS/Atom adapter using built-in libraries (no external API key required).
Fetches entries from provided feed URLs and maps them to NewsEvent objects.
"""
from __future__ import annotations
import urllib.request
import xml.etree.ElementTree as ET
from typing import List, Dict, Any
import time
from .base import NewsAdapter, NewsEvent


class RssAdapter(NewsAdapter):
    def __init__(self, feeds: List[str]):
        self.feeds = feeds or []
        self.provider_name = 'rss'

    def fetch_recent(self) -> List[NewsEvent]:
        events: List[NewsEvent] = []
        for url in self.feeds:
            try:
                with urllib.request.urlopen(url, timeout=10) as resp:
                    raw = resp.read()
                    # Parse XML
                    root = ET.fromstring(raw)
                    # Support RSS and Atom
                    if root.tag.lower().endswith('rss'):
                        channel = root.find('channel')
                        if channel is None:
                            continue
                        for item in channel.findall('item'):
                            title = item.findtext('title') or ''
                            desc = item.findtext('description') or ''
                            link = item.findtext('link') or ''
                            pub = item.findtext('pubDate') or ''
                            # symbol extraction best-effort (headline-based)
                            symbol = self._extract_symbol(title + ' ' + desc)
                            events.append(NewsEvent(provider=self.provider_name, ts=time.time(), symbol=symbol, headline=title, body=desc, meta={'link': link, 'pubDate': pub, 'source_url': url}))
                    else:
                        # Atom feed
                        for entry in root.findall('.//{http://www.w3.org/2005/Atom}entry'):
                            title = entry.findtext('{http://www.w3.org/2005/Atom}title') or ''
                            summary = entry.findtext('{http://www.w3.org/2005/Atom}summary') or ''
                            link_el = entry.find('{http://www.w3.org/2005/Atom}link')
                            link = link_el.get('href') if link_el is not None else ''
                            pub = entry.findtext('{http://www.w3.org/2005/Atom}updated') or ''
                            symbol = self._extract_symbol(title + ' ' + summary)
                            events.append(NewsEvent(provider=self.provider_name, ts=time.time(), symbol=symbol, headline=title, body=summary, meta={'link': link, 'pubDate': pub, 'source_url': url}))
            except Exception:
                # best-effort fallback: continue to next feed
                continue
        return events

    def _extract_symbol(self, text: str) -> str:
        # Very lightweight heuristic: look for GOLD or XAU keywords
        t = text.upper()
        if 'GOLD' in t or 'XAU' in t:
            return 'GOLD'
        # Could be extended with regexes for tickers
        return ''




