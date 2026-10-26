"""Market data providers abstraction.

Lightweight provider wrappers. Each provider exposes `fetch_tick(symbol)` returning
{"ts", "bid", "ask", "price", "source"} or None on failure.

MT5 provider uses connector.low-level tick; AlphaVantage and Binance use simple REST.
These wrappers are minimal; real API keys and rate-limiting must be configured.
"""
from typing import Optional, Dict, Any
import time
import os
import json
import logging
try:
    # prefer requests if available for simplicity
    import requests
except Exception:
    requests = None
import urllib.request
import urllib.parse

logger = logging.getLogger("cthulu.providers")


def _http_get(url: str, timeout: float = 5.0, retries: int = 3, backoff: float = 0.5) -> Optional[Dict[str, Any]]:
    last_exc = None
    for attempt in range(retries):
        try:
            if requests:
                r = requests.get(url, timeout=timeout)
                if r.status_code != 200:
                    last_exc = Exception(f"HTTP {r.status_code}")
                    time.sleep(backoff * (2 ** attempt))
                    continue
                return r.json()
            else:
                with urllib.request.urlopen(url, timeout=timeout) as resp:
                    return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            last_exc = e
            time.sleep(backoff * (2 ** attempt))
            continue
    # Avoid logging full URL (may contain sensitive query params like API keys)
    try:
        from urllib.parse import urlparse, urlunparse
        p = urlparse(url)
        safe_url = urlunparse((p.scheme, p.netloc, p.path, '', '<redacted>', ''))
    except Exception:
        safe_url = '<unparseable-url>'
    logger.debug("_http_get failed for %s: %s", safe_url, last_exc)
    return None


class MT5Provider:
    def __init__(self, connector):
        self.connector = connector
        self.name = 'mt5'

    def fetch_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        try:
            tick_obj = self.connector._mt5_symbol_info_tick(symbol)
            if not tick_obj:
                return None
            bid = float(getattr(tick_obj, 'bid', 0.0))
            ask = float(getattr(tick_obj, 'ask', 0.0))
            price = (bid + ask) / 2.0 if bid and ask else bid or ask
            ts = float(getattr(tick_obj, 'time', time.time()))
            return {'ts': ts, 'bid': bid, 'ask': ask, 'price': price, 'source': self.name}
        except Exception:
            return None


class AlphaVantageProvider:
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self.name = 'alphavantage'

    def fetch_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        # Determine if symbol looks like an FX pair (e.g., EURUSD) or an equity/crypto symbol
        if not self.api_key:
            self.api_key = os.environ.get('ALPHA_VANTAGE_KEY')
        if not self.api_key:
            return None
        try:
            sym = symbol.strip()
            if len(sym) == 6 and sym.isalpha():
                # Treat as FX pair: use free CURRENCY_EXCHANGE_RATE endpoint (real-time rate)
                from_sym = sym[:3]
                to_sym = sym[3:]
                q = urllib.parse.urlencode({
                    'function': 'CURRENCY_EXCHANGE_RATE',
                    'from_currency': from_sym,
                    'to_currency': to_sym,
                    'apikey': self.api_key
                })
                url = f'https://www.alphavantage.co/query?{q}'
                data = _http_get(url, timeout=10.0)
                if not data:
                    return None
                # parse 'Realtime Currency Exchange Rate'
                key = 'Realtime Currency Exchange Rate'
                block = data.get(key) or data.get('Realtime Currency Exchange Rate')
                if not block or not isinstance(block, dict):
                    return None
                # field '5. Exchange Rate' contains the price
                price_raw = block.get('5. Exchange Rate') or block.get('5. Exchange Rate')
                try:
                    price = float(price_raw)
                except Exception:
                    return None
                bid = price
                ask = price
                ts = time.time()
                return {'ts': ts, 'bid': bid, 'ask': ask, 'price': price, 'source': self.name}
            else:
                # Try GLOBAL_QUOTE for equities
                q = urllib.parse.urlencode({'function': 'GLOBAL_QUOTE', 'symbol': sym, 'apikey': self.api_key})
                url = f'https://www.alphavantage.co/query?{q}'
                data = _http_get(url, timeout=8.0)
                if not data:
                    return None
                gq = data.get('Global Quote') or data.get('Global_Quote')
                if not gq:
                    return None
                price = float(gq.get('05. price', 0.0) or 0.0)
                bid = price
                ask = price
                ts = time.time()
                return {'ts': ts, 'bid': bid, 'ask': ask, 'price': price, 'source': self.name}
        except Exception as e:
            logger.debug(f"AlphaVantage fetch error for {symbol}: {e}")
            return None


class BinanceProvider:
    def __init__(self):
        self.name = 'binance'

    def fetch_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        # Binance requires symbol mapping (e.g., BTCUSDT). Only attempt for crypto-like symbols.
        sym = symbol.strip()
        # quick heuristic: if symbol contains 'USDT' or 'BTC' or 'ETH' treat as crypto
        if not any(x in sym.upper() for x in ['USDT', 'BTC', 'ETH', 'BUSD', 'USDC']):
            return None
        try:
            url = f'https://api.binance.com/api/v3/ticker/bookTicker?symbol={urllib.parse.quote_plus(sym)}'
            data = _http_get(url, timeout=5.0)
            if not data:
                return None
            bid = float(data.get('bidPrice', 0.0) or 0.0)
            ask = float(data.get('askPrice', 0.0) or 0.0)
            price = (bid + ask) / 2.0 if bid and ask else bid or ask
            ts = time.time()
            return {'ts': ts, 'bid': bid, 'ask': ask, 'price': price, 'source': self.name}
        except Exception as e:
            logger.debug(f"Binance fetch error for {symbol}: {e}")
            return None




