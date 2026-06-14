"""
Market Intelligence Layer — Cthulu Autonomous Trading
Provides macro context: risk-on/risk-off classification, key economic
indicators, fear-greed sentiment, and per-asset directional biases.

Data Sources (priority order):
  1. Internal MT5 webhook (cross-asset analysis — free, always available)
  2. Alpha Vantage (VIX via ^VIX, DXY via UUP, oil via USO, gold via GLD)
  3. FRED (Federal Reserve): VIX, DXY, Treasury yields, oil (free, reliable)
  4. alternative.me: Crypto Fear & Greed Index (free, no key)
  5. NewsAPI: Headline sentiment (rate-limited, 50 req/12h free)

Caching: All API data cached with 30-min TTL to minimise API calls.
Update cadence: Every 30 minutes (configurable), NOT every trading cycle.
Graceful degradation: Works fully without any API keys (returns neutral regime).
"""
import json
import logging
import os
import time
import urllib.request
import urllib.error
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)

# Persistent cache across restarts
CACHE_FILE = Path(__file__).parent.parent / "data" / "market_intel_cache.json"


@dataclass
class MacroSnapshot:
    """Current macro environment assessment."""
    # Classification
    regime: str = "neutral"           # risk_on | risk_off | crisis | neutral
    confidence: float = 0.5           # 0.0–1.0

    # Key indicators
    vix: float = 0.0
    vix_trend: str = "stable"         # rising | falling | stable
    dxy_trend: str = "stable"         # strengthening | weakening | stable
    yields_10y: float = 0.0
    yield_curve: str = "normal"       # normal | flat | inverted
    oil_trend: str = "stable"         # rising | falling | spike | crash | stable

    # Directional biases per asset class (-1 bearish … +1 bullish)
    gold_bias: float = 0.0
    oil_bias: float = 0.0
    crypto_bias: float = 0.0
    forex_eur_bias: float = 0.0

    # Sentiment
    sentiment_score: float = 0.0      # -1 fear … +1 greed
    fear_greed_index: float = 50.0    # 0–100 (alternative.me)
    key_events: List[str] = field(default_factory=list)

    # Meta
    timestamp: float = 0.0
    data_age_minutes: float = 0.0
    sources_used: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'regime': self.regime,
            'confidence': self.confidence,
            'vix': self.vix,
            'vix_trend': self.vix_trend,
            'dxy_trend': self.dxy_trend,
            'yields_10y': self.yields_10y,
            'yield_curve': self.yield_curve,
            'oil_trend': self.oil_trend,
            'gold_bias': self.gold_bias,
            'oil_bias': self.oil_bias,
            'crypto_bias': self.crypto_bias,
            'forex_eur_bias': self.forex_eur_bias,
            'sentiment_score': self.sentiment_score,
            'fear_greed_index': self.fear_greed_index,
            'key_events': self.key_events,
            'timestamp': self.timestamp,
            'data_age_minutes': self.data_age_minutes,
            'sources_used': self.sources_used,
        }


class MarketIntelligence:
    """
    Collects macro data, caches it, and produces a MacroSnapshot
    that the trading orchestrator uses for directional bias.

    Principles:
    1. NEVER block the trading loop — all fetches best-effort with timeouts
    2. Cache aggressively — macro data doesn't change every 15 seconds
    3. Degrade gracefully — if ALL APIs fail → regime='neutral', conf=0.3
    4. Respect rate limits — cache TTL ≥ 30 min per source
    """

    # ── HTTP helpers ─────────────────────────────────────────────────

    _TIMEOUT = 10  # seconds per request

    def __init__(self, config: Dict[str, Any] = None):
        config = config or {}

        # API keys — any or all may be absent
        self.alpha_vantage_key = (
            os.environ.get('ALPHA_VANTAGE_KEY')
            or os.environ.get('ALPHA_VANTAGE_API_KEY')
            or config.get('alpha_vantage_key', '')
        )
        self.fred_key = os.environ.get('FRED_API_KEY', config.get('fred_api_key', ''))
        self.newsapi_key = os.environ.get('NEWSAPI_KEY', config.get('newsapi_key', ''))

        # Update interval (default 30 min)
        self.update_interval = config.get('update_interval_minutes', 30) * 60
        self.cache_ttl = config.get('cache_ttl_seconds', 1800)  # 30 min

        # Internal state
        self._cache: Dict[str, Any] = {}
        self._cache_ttl: Dict[str, float] = {}
        self._last_update: float = 0.0
        self._last_snapshot: Optional[MacroSnapshot] = None

        # Load persistent cache
        self._load_cache()

        logger.info(
            f"MarketIntelligence initialised: "
            f"AlphaVantage={'✅' if self.alpha_vantage_key else '❌'}, "
            f"FRED={'✅' if self.fred_key else '❌'}, "
            f"NewsAPI={'✅' if self.newsapi_key else '❌'}, "
            f"FearGreed=✅ (no key needed)"
        )

    # ── Main interface ───────────────────────────────────────────────

    def get_snapshot(self, force_refresh: bool = False) -> MacroSnapshot:
        """
        Return current macro snapshot, refreshing if stale.
        This is the primary interface for the trading orchestrator.
        """
        now = time.time()

        # Return cached snapshot if fresh
        if (
            not force_refresh
            and self._last_snapshot is not None
            and now - self._last_update < self.update_interval
        ):
            self._last_snapshot.data_age_minutes = (now - self._last_update) / 60
            return self._last_snapshot

        logger.info("MarketIntel: refreshing macro data …")
        snapshot = MacroSnapshot(timestamp=now)
        sources: List[str] = []

        # ── 1. Internal cross-asset (always available) ───────────────
        try:
            self._analyze_cross_asset(snapshot)
            sources.append('internal')
        except Exception as e:
            logger.debug(f"Cross-asset analysis error: {e}")

        # ── 2. Alpha Vantage quotes ─────────────────────────────────
        if self.alpha_vantage_key:
            try:
                self._fetch_alpha_vantage(snapshot)
                sources.append('AlphaVantage')
            except Exception as e:
                logger.warning(f"AlphaVantage fetch error: {e}")

        # ── 3. FRED economic data ───────────────────────────────────
        if self.fred_key:
            try:
                self._fetch_fred_data(snapshot)
                sources.append('FRED')
            except Exception as e:
                logger.warning(f"FRED fetch error: {e}")

        # ── 4. Crypto Fear & Greed (free, no key) ───────────────────
        try:
            self._fetch_fear_greed(snapshot)
            sources.append('FearGreed')
        except Exception as e:
            logger.debug(f"Fear-Greed index error: {e}")

        # ── 5. News sentiment ───────────────────────────────────────
        if self.newsapi_key and self._can_use_newsapi():
            try:
                self._fetch_news_sentiment(snapshot)
                sources.append('NewsAPI')
            except Exception as e:
                logger.debug(f"NewsAPI error: {e}")

        # ── Classify & bias ──────────────────────────────────────────
        self._classify_regime(snapshot)
        self._calculate_biases(snapshot)

        snapshot.sources_used = sources
        snapshot.data_age_minutes = 0

        self._last_snapshot = snapshot
        self._last_update = now
        self._save_cache()

        logger.info(
            f"MarketIntel: regime={snapshot.regime} (conf={snapshot.confidence:.2f}), "
            f"VIX={snapshot.vix:.1f} ({snapshot.vix_trend}), FG={snapshot.fear_greed_index:.0f}, "
            f"biases: gold={snapshot.gold_bias:+.2f} oil={snapshot.oil_bias:+.2f} "
            f"crypto={snapshot.crypto_bias:+.2f} eur={snapshot.forex_eur_bias:+.2f}"
        )
        return snapshot

    # ── Alpha Vantage ────────────────────────────────────────────────

    def _fetch_alpha_vantage(self, snapshot: MacroSnapshot):
        """
        Use Alpha Vantage GLOBAL_QUOTE for ETF proxies.
        Free tier: 25 requests/day — we cache 30 min so ≤48/day across all symbols.
        We batch the most critical symbols only.
        """
        quotes: Dict[str, float] = {}
        # ^VIX is not on AV; use VIXY ETF as proxy
        for symbol in ['VIXY', 'UUP', 'GLD', 'USO']:
            cache_key = f'av_{symbol}'
            cached = self._get_cached(cache_key)
            if cached is not None:
                quotes[symbol] = cached
                continue

            price = self._av_quote(symbol)
            if price is not None:
                quotes[symbol] = price
                self._set_cached(cache_key, price)

        # VIX proxy via VIXY price trend (not a direct VIX value)
        # Real VIX comes from FRED if available; VIXY is a fallback trend indicator
        if 'VIXY' in quotes:
            prev = self._get_cached('av_VIXY_prev')
            current = quotes['VIXY']
            if prev is not None and prev > 0:
                pct = (current - prev) / prev * 100
                if pct > 5:
                    snapshot.vix_trend = 'rising'
                elif pct < -5:
                    snapshot.vix_trend = 'falling'
                # else keep 'stable'
            # Store current as prev for next cycle
            self._set_cached('av_VIXY_prev', current, ttl=86400)

    def _av_quote(self, symbol: str) -> Optional[float]:
        """Fetch last price from Alpha Vantage GLOBAL_QUOTE."""
        try:
            url = (
                f"https://www.alphavantage.co/query"
                f"?function=GLOBAL_QUOTE&symbol={symbol}"
                f"&apikey={self.alpha_vantage_key}"
            )
            req = urllib.request.Request(url, headers={'User-Agent': 'Cthulu/5.3'})
            with urllib.request.urlopen(req, timeout=self._TIMEOUT) as resp:
                data = json.loads(resp.read().decode())
            gq = data.get('Global Quote', {})
            price_str = gq.get('05. price', '')
            if price_str:
                return float(price_str)
        except Exception as e:
            logger.debug(f"AV quote {symbol}: {e}")
        return None

    # ── FRED ─────────────────────────────────────────────────────────

    def _fetch_fred_data(self, snapshot: MacroSnapshot):
        """Fetch key macro indicators from FRED."""
        # VIX (CBOE Volatility Index)
        vix_data = self._fred_series('VIXCLS', days=10)
        if vix_data:
            snapshot.vix = float(vix_data[0]['value'])
            if len(vix_data) >= 3:
                prev_vix = float(vix_data[2]['value'])
                delta = snapshot.vix - prev_vix
                if delta > 5:
                    snapshot.vix_trend = 'rising'
                elif delta > 2:
                    snapshot.vix_trend = 'rising'
                elif delta < -3:
                    snapshot.vix_trend = 'falling'
                # else stable (default)

        # 10-Year Treasury
        t10 = self._fred_series('DGS10', days=10)
        if t10:
            snapshot.yields_10y = float(t10[0]['value'])

        # 2-Year (yield curve)
        t2 = self._fred_series('DGS2', days=5)
        if t10 and t2:
            spread = float(t10[0]['value']) - float(t2[0]['value'])
            if spread < -0.2:
                snapshot.yield_curve = 'inverted'
            elif spread < 0.2:
                snapshot.yield_curve = 'flat'
            # else normal (default)

        # WTI Oil
        oil = self._fred_series('DCOILWTICO', days=10)
        if oil and len(oil) >= 3:
            curr = float(oil[0]['value'])
            prev = float(oil[2]['value'])
            pct = (curr - prev) / prev * 100 if prev else 0
            if pct > 10:
                snapshot.oil_trend = 'spike'
            elif pct > 3:
                snapshot.oil_trend = 'rising'
            elif pct < -10:
                snapshot.oil_trend = 'crash'
            elif pct < -3:
                snapshot.oil_trend = 'falling'

        # Trade-weighted USD (DXY proxy)
        dxy = self._fred_series('DTWEXBGS', days=10)
        if dxy and len(dxy) >= 3:
            delta = float(dxy[0]['value']) - float(dxy[2]['value'])
            if delta > 1:
                snapshot.dxy_trend = 'strengthening'
            elif delta < -1:
                snapshot.dxy_trend = 'weakening'

    def _fred_series(self, series_id: str, days: int = 5) -> List[Dict]:
        """Fetch recent observations from FRED (30-min cache)."""
        cache_key = f'fred_{series_id}'
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            url = (
                f"https://api.stlouisfed.org/fred/series/observations"
                f"?series_id={series_id}"
                f"&api_key={self.fred_key}"
                f"&file_type=json"
                f"&sort_order=desc"
                f"&limit={days}"
            )
            req = urllib.request.Request(url, headers={'User-Agent': 'Cthulu/5.3'})
            with urllib.request.urlopen(req, timeout=self._TIMEOUT) as resp:
                data = json.loads(resp.read().decode())

            observations = [
                obs for obs in data.get('observations', [])
                if obs.get('value', '.') != '.'  # FRED uses '.' for missing
            ]
            self._set_cached(cache_key, observations)
            return observations
        except Exception as e:
            logger.debug(f"FRED {series_id}: {e}")
            return []

    # ── Crypto Fear & Greed Index (free, no key) ─────────────────────

    def _fetch_fear_greed(self, snapshot: MacroSnapshot):
        """Fetch crypto fear-greed index from alternative.me (free, no key)."""
        cache_key = 'fear_greed'
        cached = self._get_cached(cache_key)
        if cached is not None:
            snapshot.fear_greed_index = cached
            return

        try:
            url = "https://api.alternative.me/fng/?limit=1&format=json"
            req = urllib.request.Request(url, headers={'User-Agent': 'Cthulu/5.3'})
            with urllib.request.urlopen(req, timeout=self._TIMEOUT) as resp:
                data = json.loads(resp.read().decode())

            entries = data.get('data', [])
            if entries:
                fg_value = float(entries[0].get('value', 50))
                snapshot.fear_greed_index = fg_value
                self._set_cached(cache_key, fg_value)
                logger.debug(
                    f"Fear-Greed: {fg_value} ({entries[0].get('value_classification', 'N/A')})"
                )
        except Exception as e:
            logger.debug(f"Fear-Greed index: {e}")

    # ── Internal cross-asset from webhook server ─────────────────────

    def _analyze_cross_asset(self, snapshot: MacroSnapshot):
        """
        Analyse relationships between traded instruments via the local
        webhook server (port 9002). Zero external API calls.
        """
        base = "http://127.0.0.1:9002"
        ticks: Dict[str, Dict] = {}

        for sym in ['GOLDm#', 'GOLD#', 'BTCUSD#', 'OILCash#', 'EURUSD']:
            try:
                sym_enc = urllib.parse.quote(sym, safe='')
                req = urllib.request.Request(
                    f"{base}/latest_tick?symbol={sym_enc}",
                    headers={'User-Agent': 'Cthulu/5.3'},
                )
                with urllib.request.urlopen(req, timeout=3) as resp:
                    tick = json.loads(resp.read().decode())
                    if tick and 'bid' in tick:
                        ticks[sym] = tick
            except Exception:
                pass

        self._cache['_internal_ticks'] = ticks

    # ── News Sentiment ───────────────────────────────────────────────

    def _can_use_newsapi(self) -> bool:
        """Respect NewsAPI rate limits (≤2 calls/hour)."""
        last = self._cache.get('_newsapi_last_call', 0)
        return time.time() - last > 1800

    def _fetch_news_sentiment(self, snapshot: MacroSnapshot):
        cache_key = 'newsapi_headlines'
        cached = self._get_cached(cache_key, ttl=3600)
        if cached is not None:
            snapshot.sentiment_score = cached.get('score', 0)
            snapshot.key_events = cached.get('events', [])
            return

        try:
            url = (
                f"https://newsapi.org/v2/top-headlines"
                f"?category=business&language=en&pageSize=10"
                f"&apiKey={self.newsapi_key}"
            )
            req = urllib.request.Request(url, headers={'User-Agent': 'Cthulu/5.3'})
            with urllib.request.urlopen(req, timeout=self._TIMEOUT) as resp:
                data = json.loads(resp.read().decode())

            self._cache['_newsapi_last_call'] = time.time()
            if data.get('status') != 'ok':
                return

            headlines = [
                a['title'] for a in data.get('articles', []) if a.get('title')
            ]
            score, events = self._score_headlines(headlines)
            snapshot.sentiment_score = score
            snapshot.key_events = events[:5]
            self._set_cached(cache_key, {'score': score, 'events': events}, ttl=3600)
        except Exception as e:
            logger.debug(f"NewsAPI: {e}")

    _FEAR_WORDS = frozenset([
        'crash', 'crisis', 'war', 'sanctions', 'recession', 'collapse',
        'panic', 'plunge', 'sell-off', 'selloff', 'default', 'downgrade',
        'inflation', 'tariff', 'tension', 'escalat', 'attack', 'missile',
        'nuclear', 'invasion', 'shutdown', 'bankruptcy', 'layoff',
    ])
    _GREED_WORDS = frozenset([
        'rally', 'surge', 'boom', 'record high', 'growth', 'bull',
        'recovery', 'breakthrough', 'deal', 'peace', 'ceasefire',
        'cut rates', 'rate cut', 'stimulus', 'strong jobs',
        'beat expectations', 'optimism', 'upgrade',
    ])

    def _score_headlines(self, headlines: List[str]) -> Tuple[float, List[str]]:
        score = 0
        events: List[str] = []
        for hl in headlines:
            low = hl.lower()
            for kw in self._FEAR_WORDS:
                if kw in low:
                    score -= 1
                    events.append(f"📉 {hl[:60]}")
                    break
            else:
                for kw in self._GREED_WORDS:
                    if kw in low:
                        score += 1
                        events.append(f"📈 {hl[:60]}")
                        break
        if headlines:
            score = max(-1.0, min(1.0, score / max(len(headlines) * 0.5, 1)))
        return score, events

    # ── Regime classification ────────────────────────────────────────

    def _classify_regime(self, snapshot: MacroSnapshot):
        """
        Classify macro regime from all available signals.

        VIX thresholds (spec):
            > 35 → crisis
            > 25 → risk_off
            < 18 → risk_on
            else  → neutral

        Fear-greed index (alternative.me):
            < 25 → Extreme Fear → risk_off boost
            > 75 → Extreme Greed → risk_on boost
        """
        risk_score = 0    # negative → risk-off, positive → risk-on
        signals = 0

        # ── VIX ──────────────────────────────────────────────────────
        if snapshot.vix > 0:
            signals += 1
            if snapshot.vix > 35:
                risk_score -= 4
            elif snapshot.vix > 25:
                risk_score -= 2
            elif snapshot.vix > 20:
                risk_score -= 1
            elif snapshot.vix < 15:
                risk_score += 2
            elif snapshot.vix < 18:
                risk_score += 1

            if snapshot.vix_trend == 'rising':
                risk_score -= 1
            elif snapshot.vix_trend == 'falling':
                risk_score += 1

        # ── Yield curve ──────────────────────────────────────────────
        signals += 1
        if snapshot.yield_curve == 'inverted':
            risk_score -= 2
        elif snapshot.yield_curve == 'flat':
            risk_score -= 1
        else:
            risk_score += 1

        # ── Oil ──────────────────────────────────────────────────────
        if snapshot.oil_trend in ('spike', 'rising'):
            signals += 1
            risk_score -= 1
        elif snapshot.oil_trend == 'crash':
            signals += 1
            risk_score -= 1

        # ── Fear-greed ───────────────────────────────────────────────
        fg = snapshot.fear_greed_index
        if fg < 25:
            signals += 1
            risk_score -= 2
        elif fg < 40:
            signals += 1
            risk_score -= 1
        elif fg > 75:
            signals += 1
            risk_score += 2
        elif fg > 60:
            signals += 1
            risk_score += 1

        # ── News ─────────────────────────────────────────────────────
        if abs(snapshot.sentiment_score) > 0.1:
            signals += 1
            risk_score += int(snapshot.sentiment_score * 2)

        # ── DXY ──────────────────────────────────────────────────────
        if snapshot.dxy_trend == 'strengthening':
            signals += 1
            risk_score -= 1      # strong dollar = risk-off
        elif snapshot.dxy_trend == 'weakening':
            signals += 1
            risk_score += 1

        # ── Final classification ─────────────────────────────────────
        if signals == 0:
            snapshot.regime = 'neutral'
            snapshot.confidence = 0.3
            return

        avg = risk_score / signals
        if avg <= -1.5:
            snapshot.regime = 'crisis'
            snapshot.confidence = min(0.95, 0.6 + abs(avg) * 0.1)
        elif avg <= -0.5:
            snapshot.regime = 'risk_off'
            snapshot.confidence = min(0.85, 0.5 + abs(avg) * 0.15)
        elif avg >= 1.0:
            snapshot.regime = 'risk_on'
            snapshot.confidence = min(0.85, 0.5 + avg * 0.15)
        else:
            snapshot.regime = 'neutral'
            snapshot.confidence = 0.4

    # ── Directional biases ───────────────────────────────────────────

    def _calculate_biases(self, snapshot: MacroSnapshot):
        """
        Per-asset biases in [-1, +1] based on regime + individual signals.

        Gold rises in risk_off/crisis (safe haven).
        BTC follows risk-on (trades like tech equity).
        Oil follows supply/geopolitics (spike = war premium).
        EUR weakens when USD strengthens (inverse).
        """
        r = snapshot.regime
        c = snapshot.confidence

        if r == 'crisis':
            snapshot.gold_bias = 0.8 * c
            snapshot.crypto_bias = -0.7 * c
            snapshot.oil_bias = 0.3 * c
            snapshot.forex_eur_bias = -0.3 * c
        elif r == 'risk_off':
            snapshot.gold_bias = 0.5 * c
            snapshot.crypto_bias = -0.4 * c
            snapshot.oil_bias = -0.2 * c
            snapshot.forex_eur_bias = -0.2 * c
        elif r == 'risk_on':
            snapshot.gold_bias = -0.2 * c
            snapshot.crypto_bias = 0.5 * c
            snapshot.oil_bias = 0.3 * c
            snapshot.forex_eur_bias = 0.3 * c
        else:  # neutral
            snapshot.gold_bias = 0.0
            snapshot.crypto_bias = 0.0
            snapshot.oil_bias = 0.0
            snapshot.forex_eur_bias = 0.0

        # Fear-greed override for crypto
        fg = snapshot.fear_greed_index
        if fg < 20:
            snapshot.crypto_bias = min(snapshot.crypto_bias, -0.6)
        elif fg > 80:
            snapshot.crypto_bias = max(snapshot.crypto_bias, 0.6)

        # Oil supply shock override
        if snapshot.oil_trend == 'spike':
            snapshot.oil_bias = max(snapshot.oil_bias, 0.6)
        elif snapshot.oil_trend == 'crash':
            snapshot.oil_bias = min(snapshot.oil_bias, -0.5)

        # VIX spike → strong gold bid, BTC dump
        if snapshot.vix_trend == 'rising' and snapshot.vix > 25:
            snapshot.gold_bias = max(snapshot.gold_bias, 0.7)
            snapshot.crypto_bias = min(snapshot.crypto_bias, -0.5)

        # Clamp all biases
        snapshot.gold_bias = max(-1.0, min(1.0, snapshot.gold_bias))
        snapshot.oil_bias = max(-1.0, min(1.0, snapshot.oil_bias))
        snapshot.crypto_bias = max(-1.0, min(1.0, snapshot.crypto_bias))
        snapshot.forex_eur_bias = max(-1.0, min(1.0, snapshot.forex_eur_bias))

    # ── Cache management ─────────────────────────────────────────────

    def _get_cached(self, key: str, ttl: int = None) -> Optional[Any]:
        ttl = ttl or self.cache_ttl
        if key in self._cache and key in self._cache_ttl:
            if time.time() - self._cache_ttl[key] < ttl:
                return self._cache[key]
        return None

    def _set_cached(self, key: str, value: Any, ttl: int = None):
        self._cache[key] = value
        self._cache_ttl[key] = time.time()

    def _load_cache(self):
        try:
            if CACHE_FILE.exists():
                with open(CACHE_FILE) as f:
                    data = json.load(f)
                self._cache = data.get('cache', {})
                self._cache_ttl = {k: float(v) for k, v in data.get('ttl', {}).items()}
                logger.info(f"Loaded {len(self._cache)} cached market intel entries")
        except Exception as e:
            logger.debug(f"Cache load error: {e}")

    def _save_cache(self):
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            serialisable = {
                k: v for k, v in self._cache.items() if not k.startswith('_')
            }
            with open(CACHE_FILE, 'w') as f:
                json.dump(
                    {
                        'cache': serialisable,
                        'ttl': self._cache_ttl,
                        'saved_at': datetime.now(timezone.utc).isoformat(),
                    },
                    f,
                    indent=2,
                    default=str,
                )
        except Exception as e:
            logger.debug(f"Cache save error: {e}")
