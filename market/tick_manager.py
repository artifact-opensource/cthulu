"""Tick manager: lightweight in-memory ring buffers and poller.

Features:
- Ring buffer per symbol storing (ts, bid, ask, price, source)
- subscribe(symbol, callback, priority)
- get_recent_ticks(symbol, seconds, max_points)
- background poller that queries MT5 via connector.symbol_info_tick

This is intentionally simple and dependency-free.
"""
from threading import Thread, Lock, Event
from collections import deque
from time import time, sleep
from typing import Callable, Deque, Dict, Any, List, Tuple, Optional

try:
    # Prefer relative imports when running inside the package (pytest collection)
    from .providers import MT5Provider, AlphaVantageProvider, BinanceProvider
    from ..observability.prometheus import PrometheusExporter
except Exception:
    # Fallback to absolute imports for scripts run outside the package context
    from cthulu.market.providers import MT5Provider, AlphaVantageProvider, BinanceProvider
    from cthulu.observability.prometheus import PrometheusExporter
import os


class TokenBucket:
    def __init__(self, rate: float, capacity: float):
        self.rate = rate
        self.capacity = capacity
        self._tokens = capacity
        self._last = time()
        self.lock = Lock()

    def consume(self, amount: float = 1.0) -> bool:
        with self.lock:
            now = time()
            elapsed = now - self._last
            self._last = now
            # refill
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
            if self._tokens >= amount:
                self._tokens -= amount
                return True
            return False


class RingBuffer:
    def __init__(self, capacity: int = 1024):
        self.capacity = capacity
        self.buf: Deque[Tuple[float, float, float, float, str]] = deque(maxlen=capacity)
        self.lock = Lock()

    def append(self, ts: float, bid: float, ask: float, price: float, source: str = 'mt5'):
        with self.lock:
            self.buf.append((ts, bid, ask, price, source))

    def get_recent(self, seconds: float = 60.0, max_points: int = 200) -> List[Dict[str, Any]]:
        cutoff = time() - seconds
        with self.lock:
            items = [v for v in list(self.buf) if v[0] >= cutoff]
        # return up to max_points most recent
        items = items[-max_points:]
        return [ {'ts': t, 'bid': b, 'ask': a, 'price': p, 'source': s} for (t,b,a,p,s) in items ]


class TickManager:
    def __init__(self, connector, poll_interval_high: float = 0.2):
        self.connector = connector
        self.buffers: Dict[str, RingBuffer] = {}
        self.subscribers: Dict[str, List[Tuple[Callable, str, int]]] = {}
        self.priorities: Dict[str, int] = {}  # symbol -> priority
        self._stop = Event()
        self._thread = Thread(target=self._poller_loop, daemon=True)
        self._lock = Lock()
        # priority -> interval mapping
        self.intervals = { 'high': 0.2, 'medium': 2.0, 'low': 10.0 }
        # providers and rate limits
        self.providers = [MT5Provider(self.connector)]
        av_key = os.environ.get('ALPHA_VANTAGE_KEY')
        if av_key:
            self.providers.append(AlphaVantageProvider(api_key=av_key))
        # Binance provider is optional
        self.providers.append(BinanceProvider())
        # token buckets per provider name (requests per second, capacity)
        self._buckets: Dict[str, TokenBucket] = {
            'mt5': TokenBucket(rate=1000.0, capacity=1000.0),
            'alphavantage': TokenBucket(rate=float(os.environ.get('ALPHA_VANTAGE_RATE', 1/12.0)), capacity=float(os.environ.get('ALPHA_VANTAGE_BURST', 5.0))),  # ~5/min
            'binance': TokenBucket(rate=float(os.environ.get('BINANCE_RATE', 10.0)), capacity=float(os.environ.get('BINANCE_BURST', 20.0))),
        }
        self.exporter = PrometheusExporter()
        self._tick_poll_errors = 0
        # adaptive provider health tracking
        self._provider_errors: Dict[str, int] = {p.name: 0 for p in self.providers}
        self._provider_backoff_until: Dict[str, float] = {}
        self._provider_original_rate: Dict[str, float] = {name: b.rate for name, b in self._buckets.items()}
        self._thread.start()

    def ensure_buffer(self, symbol: str):
        if symbol not in self.buffers:
            self.buffers[symbol] = RingBuffer()

    def subscribe(self, symbol: str, callback: Callable[[Dict[str,Any]], None], priority: str = 'high'):
        with self._lock:
            self.ensure_buffer(symbol)
            self.subscribers.setdefault(symbol, []).append((callback, 'mt5', 0))
            self.priorities[symbol] = max(self.priorities.get(symbol, 0),  {'low':1,'medium':2,'high':3}.get(priority,2))

    def unsubscribe(self, symbol: str, callback: Callable[[Dict[str,Any]], None]):
        with self._lock:
            subs = self.subscribers.get(symbol, [])
            subs = [s for s in subs if s[0] != callback]
            if subs:
                self.subscribers[symbol] = subs
            else:
                self.subscribers.pop(symbol, None)
                self.priorities.pop(symbol, None)

    def get_recent(self, symbol: str, seconds: float = 60.0, max_points: int = 200):
        buf = self.buffers.get(symbol)
        if not buf:
            return []
        return buf.get_recent(seconds=seconds, max_points=max_points)

    def stop(self):
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _poller_loop(self):
        # Simple loop: poll symbols grouped by priority with their intervals
        while not self._stop.is_set():
            try:
                with self._lock:
                    symbols = list(self.priorities.items())
                if not symbols:
                    sleep(0.5)
                    continue

                # Group by priority
                buckets = { 'high': [], 'medium': [], 'low': [] }
                for sym, p in symbols:
                    if p >= 3:
                        buckets['high'].append(sym)
                    elif p == 2:
                        buckets['medium'].append(sym)
                    else:
                        buckets['low'].append(sym)

                # Poll each bucket with its interval
                for level in ('high','medium','low'):
                    syms = buckets[level]
                    interval = self.intervals.get(level, 1.0)
                    for s in syms:
                        try:
                            # Use connector.symbol_info_tick if available for low-overhead tick
                            tick = None
                            try:
                                tick_obj = self.connector._mt5_symbol_info_tick(s)
                                if tick_obj:
                                    bid = float(getattr(tick_obj, 'bid', 0.0))
                                    ask = float(getattr(tick_obj, 'ask', 0.0))
                                    price = (bid + ask) / 2.0 if bid and ask else bid or ask
                                    ts = float(getattr(tick_obj, 'time', time()))
                                    tick = {'ts': ts, 'bid': bid, 'ask': ask, 'price': price, 'source': 'mt5'}
                            except Exception:
                                tick = None

                            if not tick:
                                # Try provider fallbacks (AlphaVantage, Binance)
                                for prov in self.providers[1:]:
                                    # skip provider if in backoff
                                    backoff_until = self._provider_backoff_until.get(prov.name, 0)
                                    if time() < backoff_until:
                                        continue
                                    bucket = self._buckets.get(prov.name)
                                    allowed = True
                                    if bucket:
                                        allowed = bucket.consume(1.0)
                                    if not allowed:
                                        continue
                                    try:
                                        ptick = prov.fetch_tick(s)
                                    except Exception:
                                        ptick = None
                                    if ptick:
                                        # success -> reset error count and restore rate if modified
                                        self._provider_errors[prov.name] = 0
                                        if prov.name in self._provider_original_rate and prov.name in self._buckets:
                                            orig = self._provider_original_rate.get(prov.name)
                                            if orig and self._buckets[prov.name].rate != orig:
                                                self._buckets[prov.name].rate = orig
                                    else:
                                        # failure -> increase error count and possibly backoff
                                        self._provider_errors[prov.name] = self._provider_errors.get(prov.name, 0) + 1
                                        errs = self._provider_errors[prov.name]
                                        if errs >= 3:
                                            # exponential backoff window
                                            wait = min(60 * (2 ** (errs - 3)), 3600)
                                            self._provider_backoff_until[prov.name] = time() + wait
                                            # reduce token bucket rate to reduce pressure
                                            if prov.name in self._buckets:
                                                b = self._buckets[prov.name]
                                                b.rate = max(0.1, b.rate * 0.5)
                                    if ptick:
                                        tick = ptick
                                        break
                                # last-resort: connector.get_symbol_info
                                if not tick:
                                    try:
                                        info = self.connector.get_symbol_info(s)
                                    except Exception:
                                        info = None
                                    if info:
                                        bid = float(info.get('bid', 0.0))
                                        ask = float(info.get('ask', 0.0))
                                        price = (bid + ask)/2.0 if bid and ask else bid or ask
                                        ts = time()
                                        tick = {'ts': ts, 'bid': bid, 'ask': ask, 'price': price, 'source': 'connector-fallback'}

                            if tick:
                                self.ensure_buffer(s)
                                self.buffers[s].append(tick['ts'], tick['bid'], tick['ask'], tick['price'], tick.get('source','mt5'))
                                # notify subscribers
                                subs = list(self.subscribers.get(s, []))
                                for cb, src, _ in subs:
                                    try:
                                        cb(tick)
                                    except Exception:
                                        # swallow subscriber errors
                                        continue
                                # observability: tick age and source
                                try:
                                    age = time() - float(tick.get('ts', time()))
                                    self.exporter._update_metric(
                                        f"Cthulu_tick_age_seconds",
                                        float(age),
                                        "gauge",
                                        "Age of most recent tick in seconds",
                                        labels={"symbol": s, "source": tick.get('source','unknown')}
                                    )
                                    # count source switches (non-mt5 source)
                                    if tick.get('source') and not tick.get('source').startswith('mt5'):
                                        self.exporter._update_metric(
                                            f"Cthulu_tick_source_switches_total",
                                            1.0,
                                            "counter",
                                            "Count of ticks originating from fallback sources",
                                            labels={"symbol": s, "source": tick.get('source')}
                                        )
                                except Exception as e:
                                    self.logger.debug("Failed to update fallback tick source metric for %s: %s", s, e, exc_info=True)
                            else:
                                # record poll error
                                self._tick_poll_errors += 1
                                try:
                                    self.exporter._update_metric(
                                        f"Cthulu_tick_poll_errors_total",
                                        float(self._tick_poll_errors),
                                        "counter",
                                        "Total tick poll errors"
                                    )
                                except Exception as e:
                                    self.logger.debug("Failed to update tick poll error metric: %s", e, exc_info=True)
                        except Exception as e:
                            self.logger.debug("Error processing tick bucket for %s: %s", s, e, exc_info=True)
                            continue
                    # sleep a bit between buckets to avoid tight looping
                    sleep(interval)

            except Exception as e:
                self.logger.debug("Tick manager loop encountered error: %s", e, exc_info=True)
                sleep(0.5)




