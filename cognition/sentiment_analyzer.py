"""
Sentiment Analyzer - The Ears of Cognition

News and market sentiment integration for trading decisions.
Aggregates multiple sources: news, economic calendar, fear/greed indices.

Part of Cthulu Cognition Engine v6.0.0
"""
from __future__ import annotations
import numpy as np
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
import json
import os
import logging
import re
from collections import deque

logger = logging.getLogger("cthulu.cognition.sentiment")


class SentimentDirection(Enum):
    """Sentiment direction classifications."""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    MIXED = "mixed"


class EventImpact(Enum):
    """Economic event impact levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SentimentScore:
    """Sentiment analysis result."""
    score: float  # -1 to +1
    direction: SentimentDirection
    confidence: float  # 0 to 1
    components: Dict[str, float]
    events: List[Dict[str, Any]]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def is_actionable(self) -> bool:
        """Whether sentiment is strong enough to act on."""
        return abs(self.score) >= 0.3 and self.confidence >= 0.5
    
    @property
    def suggests_caution(self) -> bool:
        """Whether sentiment suggests reducing exposure."""
        return (
            self.direction == SentimentDirection.MIXED or
            any(e.get('impact') == 'critical' for e in self.events)
        )


@dataclass
class NewsItem:
    """Single news item."""
    headline: str
    source: str
    timestamp: datetime
    sentiment_score: float  # -1 to +1
    relevance: float  # 0 to 1
    symbols: List[str]
    
    @property
    def is_recent(self) -> bool:
        """Check if news is recent (< 4 hours)."""
        return (datetime.utcnow() - self.timestamp) < timedelta(hours=4)


@dataclass 
class EconomicEvent:
    """Economic calendar event."""
    name: str
    currency: str
    impact: EventImpact
    scheduled_time: datetime
    actual: Optional[float] = None
    forecast: Optional[float] = None
    previous: Optional[float] = None
    
    @property
    def is_upcoming(self) -> bool:
        """Check if event is in next 2 hours."""
        return timedelta(0) <= (self.scheduled_time - datetime.utcnow()) <= timedelta(hours=2)
    
    @property
    def surprise_factor(self) -> Optional[float]:
        """Calculate surprise if actual is available."""
        if self.actual is None or self.forecast is None:
            return None
        if self.forecast == 0:
            return 0.0
        return (self.actual - self.forecast) / abs(self.forecast)


class KeywordSentimentAnalyzer:
    """Simple keyword-based sentiment analyzer for headlines."""
    
    def __init__(self):
        # Bullish keywords with weights
        self.bullish_keywords = {
            'surge': 0.8, 'soar': 0.9, 'rally': 0.7, 'bullish': 0.9, 
            'gain': 0.5, 'rise': 0.4, 'up': 0.3, 'growth': 0.5,
            'positive': 0.4, 'beat': 0.6, 'record': 0.5, 'breakthrough': 0.7,
            'buy': 0.6, 'upgrade': 0.6, 'outperform': 0.7, 'strong': 0.5,
            'recovery': 0.5, 'boom': 0.8, 'optimism': 0.6, 'bull': 0.7,
            'highs': 0.5, 'breakout': 0.6, 'momentum': 0.4
        }
        
        # Bearish keywords with weights
        self.bearish_keywords = {
            'plunge': 0.9, 'crash': 0.95, 'selloff': 0.8, 'bearish': 0.9,
            'fall': 0.5, 'drop': 0.5, 'down': 0.3, 'decline': 0.5,
            'negative': 0.4, 'miss': 0.6, 'warning': 0.7, 'risk': 0.4,
            'sell': 0.6, 'downgrade': 0.6, 'underperform': 0.7, 'weak': 0.5,
            'recession': 0.8, 'crisis': 0.9, 'fear': 0.6, 'bear': 0.7,
            'lows': 0.5, 'breakdown': 0.6, 'concerns': 0.4
        }
        
        # Negation words that flip sentiment
        self.negation_words = {'not', 'no', 'never', "n't", 'without', 'despite'}
    
    def analyze(self, text: str) -> float:
        """
        Analyze text sentiment.
        
        Returns: Score from -1 (bearish) to +1 (bullish)
        """
        text_lower = text.lower()
        words = re.findall(r'\b\w+\b', text_lower)
        
        bullish_score = 0.0
        bearish_score = 0.0
        
        for i, word in enumerate(words):
            # Check for negation in previous 3 words
            negated = any(words[max(0, i-3):i].count(neg) > 0 for neg in self.negation_words)
            
            if word in self.bullish_keywords:
                weight = self.bullish_keywords[word]
                if negated:
                    bearish_score += weight
                else:
                    bullish_score += weight
            
            if word in self.bearish_keywords:
                weight = self.bearish_keywords[word]
                if negated:
                    bullish_score += weight
                else:
                    bearish_score += weight
        
        # Normalize to -1 to +1
        total = bullish_score + bearish_score
        if total == 0:
            return 0.0
        
        return (bullish_score - bearish_score) / max(total, 1.0)


class SentimentAnalyzer:
    """
    Aggregates sentiment from multiple sources.
    
    Sources:
    1. News headlines (keyword analysis)
    2. Economic calendar events
    3. Fear & Greed proxy indicators
    
    Output: Normalized sentiment score [-1, +1]
    """
    
    def __init__(
        self,
        news_weight: float = 0.40,
        calendar_weight: float = 0.35,
        fear_greed_weight: float = 0.25,
        cache_duration_minutes: int = 15
    ):
        self.news_weight = news_weight
        self.calendar_weight = calendar_weight
        self.fear_greed_weight = fear_greed_weight
        self.cache_duration = timedelta(minutes=cache_duration_minutes)
        
        # Sub-analyzers
        self.keyword_analyzer = KeywordSentimentAnalyzer()
        
        # Caches
        self._news_cache: List[NewsItem] = []
        self._calendar_cache: List[EconomicEvent] = []
        self._sentiment_cache: Dict[str, SentimentScore] = {}
        self._cache_time: Dict[str, datetime] = {}
        
        # Historical tracking
        self._sentiment_history: deque = deque(maxlen=100)
        
        # Data source callbacks (for external integrations)
        self._news_provider: Optional[Callable] = None
        self._calendar_provider: Optional[Callable] = None
        
        logger.info(f"SentimentAnalyzer initialized: news={news_weight}, calendar={calendar_weight}, fear_greed={fear_greed_weight}")
    
    def register_news_provider(self, provider: Callable[[str], List[Dict]]):
        """Register external news data provider."""
        self._news_provider = provider
        logger.info("News provider registered")
    
    def register_calendar_provider(self, provider: Callable[[], List[Dict]]):
        """Register external economic calendar provider."""
        self._calendar_provider = provider
        logger.info("Calendar provider registered")
    
    def get_sentiment(self, symbol: str) -> SentimentScore:
        """
        Get aggregated sentiment for symbol.
        
        Args:
            symbol: Trading symbol (e.g., 'BTCUSD', 'XAUUSD')
            
        Returns:
            SentimentScore with weighted components
        """
        # Check cache
        cache_key = symbol.upper()
        if cache_key in self._sentiment_cache:
            if datetime.utcnow() - self._cache_time.get(cache_key, datetime.min) < self.cache_duration:
                return self._sentiment_cache[cache_key]
        
        # Gather sentiment components
        news_score = self._analyze_news(symbol)
        calendar_score = self._analyze_calendar(symbol)
        fear_greed_score = self._calculate_fear_greed_proxy(symbol)
        
        # Weighted average
        weighted_score = (
            news_score * self.news_weight +
            calendar_score * self.calendar_weight +
            fear_greed_score * self.fear_greed_weight
        )
        
        # Determine direction
        if weighted_score > 0.15:
            direction = SentimentDirection.BULLISH
        elif weighted_score < -0.15:
            direction = SentimentDirection.BEARISH
        elif abs(news_score - calendar_score) > 0.5:
            direction = SentimentDirection.MIXED
        else:
            direction = SentimentDirection.NEUTRAL
        
        # Calculate confidence (agreement across sources)
        scores = [news_score, calendar_score, fear_greed_score]
        score_signs = [1 if s > 0 else -1 if s < 0 else 0 for s in scores]
        agreement = abs(sum(score_signs)) / 3.0
        confidence = 0.5 + 0.5 * agreement
        
        # Gather events
        events = self._get_relevant_events(symbol)
        
        result = SentimentScore(
            score=weighted_score,
            direction=direction,
            confidence=confidence,
            components={
                'news': news_score,
                'calendar': calendar_score,
                'fear_greed': fear_greed_score
            },
            events=events
        )
        
        # Update caches
        self._sentiment_cache[cache_key] = result
        self._cache_time[cache_key] = datetime.utcnow()
        self._sentiment_history.append((datetime.utcnow(), symbol, weighted_score))
        
        logger.debug(f"Sentiment for {symbol}: {weighted_score:.3f} ({direction.value})")
        
        return result
    
    def _analyze_news(self, symbol: str) -> float:
        """Analyze news sentiment for symbol."""
        # Try external provider first
        if self._news_provider:
            try:
                news_data = self._news_provider(symbol)
                scores = []
                for item in news_data[:10]:  # Last 10 items
                    headline = item.get('headline', '')
                    score = self.keyword_analyzer.analyze(headline)
                    # Weight by recency
                    age_hours = (datetime.utcnow() - item.get('timestamp', datetime.utcnow())).total_seconds() / 3600
                    recency_weight = max(0.1, 1.0 - age_hours / 24)
                    scores.append(score * recency_weight)
                
                if scores:
                    return float(np.mean(scores))
            except Exception as e:
                logger.warning(f"News provider error: {e}")
        
        # Fallback: use cached news
        relevant_news = [n for n in self._news_cache if symbol in n.symbols and n.is_recent]
        if relevant_news:
            return float(np.mean([n.sentiment_score for n in relevant_news]))
        
        return 0.0
    
    def _analyze_calendar(self, symbol: str) -> float:
        """Analyze economic calendar impact."""
        # Map symbols to currencies
        symbol_currency_map = {
            'BTCUSD': ['USD'],
            'ETHUSD': ['USD'],
            'XAUUSD': ['USD', 'XAU'],
            'EURUSD': ['EUR', 'USD'],
            'GBPUSD': ['GBP', 'USD'],
            'USDJPY': ['USD', 'JPY'],
        }
        
        currencies = symbol_currency_map.get(symbol.upper().replace('#', ''), ['USD'])
        
        # Try external provider
        if self._calendar_provider:
            try:
                events_data = self._calendar_provider()
                self._calendar_cache = [
                    EconomicEvent(
                        name=e['name'],
                        currency=e['currency'],
                        impact=EventImpact(e.get('impact', 'medium')),
                        scheduled_time=e['time'],
                        actual=e.get('actual'),
                        forecast=e.get('forecast'),
                        previous=e.get('previous')
                    )
                    for e in events_data
                ]
            except Exception as e:
                logger.warning(f"Calendar provider error: {e}")
        
        # Analyze events
        relevant_events = [e for e in self._calendar_cache if e.currency in currencies]
        
        if not relevant_events:
            return 0.0
        
        score = 0.0
        weight_sum = 0.0
        
        for event in relevant_events:
            # Impact weight
            impact_weights = {
                EventImpact.LOW: 0.1,
                EventImpact.MEDIUM: 0.3,
                EventImpact.HIGH: 0.6,
                EventImpact.CRITICAL: 1.0
            }
            weight = impact_weights.get(event.impact, 0.3)
            
            # Surprise factor (if available)
            surprise = event.surprise_factor
            if surprise is not None:
                # Positive surprise = bullish, negative = bearish
                event_score = np.tanh(surprise * 2)  # Normalize large surprises
                score += event_score * weight
                weight_sum += weight
            elif event.is_upcoming:
                # Upcoming high-impact events create uncertainty (slightly bearish)
                if event.impact in (EventImpact.HIGH, EventImpact.CRITICAL):
                    score -= 0.1 * weight
                    weight_sum += weight
        
        return float(score / (weight_sum + 1e-10))
    
    def _calculate_fear_greed_proxy(self, symbol: str) -> float:
        """
        Calculate fear/greed proxy from market data.
        Uses RSI extreme as proxy for sentiment.
        """
        # This would integrate with the trading loop's indicator data
        # For now, return neutral
        return 0.0
    
    def _get_relevant_events(self, symbol: str) -> List[Dict[str, Any]]:
        """Get relevant upcoming events for symbol."""
        symbol_currency_map = {
            'BTCUSD': ['USD'],
            'XAUUSD': ['USD', 'XAU'],
            'EURUSD': ['EUR', 'USD'],
        }
        currencies = symbol_currency_map.get(symbol.upper().replace('#', ''), ['USD'])
        
        events = []
        for e in self._calendar_cache:
            if e.currency in currencies and (e.is_upcoming or e.surprise_factor is not None):
                events.append({
                    'name': e.name,
                    'currency': e.currency,
                    'impact': e.impact.value,
                    'time': e.scheduled_time.isoformat(),
                    'surprise': e.surprise_factor
                })
        
        return events[:5]  # Top 5 events
    
    def add_news(self, headline: str, source: str, symbols: List[str], timestamp: Optional[datetime] = None):
        """Add news item to cache."""
        score = self.keyword_analyzer.analyze(headline)
        
        item = NewsItem(
            headline=headline,
            source=source,
            timestamp=timestamp or datetime.utcnow(),
            sentiment_score=score,
            relevance=0.8,
            symbols=[s.upper() for s in symbols]
        )
        
        self._news_cache.append(item)
        
        # Trim old news
        self._news_cache = [n for n in self._news_cache if n.is_recent]
        
        logger.debug(f"News added: {headline[:50]}... score={score:.3f}")
    
    def add_event(
        self,
        name: str,
        currency: str,
        impact: str,
        scheduled_time: datetime,
        actual: Optional[float] = None,
        forecast: Optional[float] = None,
        previous: Optional[float] = None
    ):
        """Add economic event to cache."""
        event = EconomicEvent(
            name=name,
            currency=currency.upper(),
            impact=EventImpact(impact.lower()),
            scheduled_time=scheduled_time,
            actual=actual,
            forecast=forecast,
            previous=previous
        )
        
        self._calendar_cache.append(event)
        
        # Remove old events (> 24h past)
        cutoff = datetime.utcnow() - timedelta(hours=24)
        self._calendar_cache = [e for e in self._calendar_cache if e.scheduled_time > cutoff]
        
        logger.debug(f"Event added: {name} ({currency}, {impact})")
    
    def get_sentiment_trend(self, symbol: str, hours: int = 24) -> float:
        """Get sentiment trend over time (-1 to +1 for trending direction)."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        history = [(t, s, score) for t, s, score in self._sentiment_history 
                   if s == symbol.upper() and t > cutoff]
        
        if len(history) < 2:
            return 0.0
        
        scores = [h[2] for h in history]
        
        # Simple trend: recent vs older
        mid = len(scores) // 2
        recent_avg = np.mean(scores[mid:])
        older_avg = np.mean(scores[:mid])
        
        return float(np.clip(recent_avg - older_avg, -1, 1))
    
    def should_avoid_trading(self, symbol: str) -> Tuple[bool, str]:
        """Check if sentiment suggests avoiding trading."""
        sentiment = self.get_sentiment(symbol)
        
        # Avoid on critical events
        critical_events = [e for e in sentiment.events if e.get('impact') == 'critical']
        if critical_events:
            return True, f"Critical event: {critical_events[0]['name']}"
        
        # Avoid on extreme mixed sentiment
        if sentiment.direction == SentimentDirection.MIXED and abs(sentiment.score) < 0.1:
            return True, "Mixed sentiment - conflicting signals"
        
        # Avoid on very low confidence
        if sentiment.confidence < 0.3:
            return True, "Low sentiment confidence"
        
        return False, ""
    
    def to_dict(self) -> Dict:
        """Export current state as dictionary."""
        return {
            'news_count': len(self._news_cache),
            'events_count': len(self._calendar_cache),
            'cached_symbols': list(self._sentiment_cache.keys()),
            'history_length': len(self._sentiment_history)
        }


# Module-level singleton
_analyzer: Optional[SentimentAnalyzer] = None


def get_sentiment_analyzer(**kwargs) -> SentimentAnalyzer:
    """Get or create the sentiment analyzer singleton."""
    global _analyzer
    if _analyzer is None:
        _analyzer = SentimentAnalyzer(**kwargs)
    return _analyzer


def get_sentiment(symbol: str) -> SentimentScore:
    """Convenience function to get sentiment."""
    return get_sentiment_analyzer().get_sentiment(symbol)
