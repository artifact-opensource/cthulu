"""
Market Regime Classifier - The Eyes of Cognition

Detects current market conditions: BULL, BEAR, SIDEWAYS, VOLATILE, CHOPPY
Uses softmax probability distribution for smooth regime transitions.

Part of Cthulu Cognition Engine v6.0.0
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger("cthulu.cognition.regime")


class MarketRegime(Enum):
    """Market regime classifications."""
    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"
    VOLATILE = "volatile"
    CHOPPY = "choppy"
    UNKNOWN = "unknown"


@dataclass
class RegimeState:
    """Current regime state with probabilities."""
    regime: MarketRegime
    confidence: float
    probabilities: Dict[str, float]
    features: Dict[str, float]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def is_trending(self) -> bool:
        return self.regime in (MarketRegime.BULL, MarketRegime.BEAR)
    
    @property
    def is_ranging(self) -> bool:
        return self.regime in (MarketRegime.SIDEWAYS, MarketRegime.CHOPPY)
    
    @property
    def is_volatile(self) -> bool:
        return self.regime == MarketRegime.VOLATILE or self.features.get('volatility_ratio', 0) > 1.5


@dataclass
class RegimeTransition:
    """Tracks regime transitions for momentum analysis."""
    from_regime: MarketRegime
    to_regime: MarketRegime
    timestamp: datetime
    confidence_delta: float


class MarketRegimeClassifier:
    """
    Softmax-based market regime classifier.
    
    Features extracted:
    - trend_strength: ADX-based trend measure
    - price_momentum: Rate of change / momentum
    - volatility_ratio: ATR relative to price
    - volume_trend: Volume moving average ratio
    - structure_score: Higher highs/lower lows analysis
    - range_bound_score: Bollinger Band %B variance
    
    Output: Softmax probability distribution over regimes
    """
    
    REGIMES = [MarketRegime.BULL, MarketRegime.BEAR, MarketRegime.SIDEWAYS, 
               MarketRegime.VOLATILE, MarketRegime.CHOPPY]
    
    def __init__(
        self,
        lookback: int = 50,
        adx_threshold: float = 25.0,
        volatility_threshold: float = 1.5,
        temperature: float = 1.0,
        transition_smoothing: float = 0.3
    ):
        self.lookback = lookback
        self.adx_threshold = adx_threshold
        self.volatility_threshold = volatility_threshold
        self.temperature = temperature
        self.transition_smoothing = transition_smoothing
        
        # State tracking
        self._previous_state: Optional[RegimeState] = None
        self._transitions: List[RegimeTransition] = []
        self._regime_history: List[Tuple[datetime, MarketRegime]] = []
        
        # Feature weights for regime scoring
        self._weights = {
            MarketRegime.BULL: {
                'trend_strength': 0.35,
                'price_momentum': 0.30,
                'structure_score': 0.20,
                'volatility_ratio': -0.10,
                'range_bound_score': -0.05
            },
            MarketRegime.BEAR: {
                'trend_strength': 0.35,
                'price_momentum': -0.30,  # Negative momentum
                'structure_score': -0.20,  # Lower lows
                'volatility_ratio': -0.10,
                'range_bound_score': -0.05
            },
            MarketRegime.SIDEWAYS: {
                'trend_strength': -0.40,  # Low ADX
                'price_momentum': -0.15,
                'structure_score': 0.00,
                'volatility_ratio': -0.25,
                'range_bound_score': 0.20
            },
            MarketRegime.VOLATILE: {
                'trend_strength': 0.10,
                'price_momentum': 0.10,
                'structure_score': 0.00,
                'volatility_ratio': 0.60,  # High volatility
                'range_bound_score': -0.10
            },
            MarketRegime.CHOPPY: {
                'trend_strength': -0.30,
                'price_momentum': 0.05,
                'structure_score': -0.10,
                'volatility_ratio': 0.25,
                'range_bound_score': -0.30
            }
        }
        
        logger.info(f"MarketRegimeClassifier initialized: lookback={lookback}, temp={temperature}")
    
    def classify(self, market_data: pd.DataFrame) -> RegimeState:
        """
        Classify current market regime.
        
        Args:
            market_data: DataFrame with OHLCV columns
            
        Returns:
            RegimeState with probabilities and features
        """
        if len(market_data) < self.lookback:
            return RegimeState(
                regime=MarketRegime.UNKNOWN,
                confidence=0.0,
                probabilities={r.value: 0.2 for r in self.REGIMES},
                features={}
            )
        
        # Extract features
        features = self._extract_features(market_data)
        
        # Compute logits for each regime
        logits = self._compute_logits(features)
        
        # Apply softmax
        probabilities = self._softmax(logits)
        
        # Determine regime (argmax with smoothing)
        regime, confidence = self._determine_regime(probabilities)
        
        # Create state
        state = RegimeState(
            regime=regime,
            confidence=confidence,
            probabilities=probabilities,
            features=features
        )
        
        # Track transition
        if self._previous_state and self._previous_state.regime != regime:
            self._record_transition(self._previous_state, state)
        
        self._previous_state = state
        self._regime_history.append((state.timestamp, regime))
        
        # Trim history
        if len(self._regime_history) > 1000:
            self._regime_history = self._regime_history[-500:]
        
        logger.debug(f"Regime: {regime.value} (conf={confidence:.2f}) - {probabilities}")
        
        return state
    
    def _extract_features(self, df: pd.DataFrame) -> Dict[str, float]:
        """Extract features from market data."""
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        volume = df['volume'].values if 'volume' in df.columns else np.ones(len(close))
        
        features = {}
        
        # 1. Trend Strength (ADX-like)
        features['trend_strength'] = self._calculate_trend_strength(high, low, close)
        
        # 2. Price Momentum (ROC)
        features['price_momentum'] = self._calculate_momentum(close)
        
        # 3. Volatility Ratio (ATR/Price)
        features['volatility_ratio'] = self._calculate_volatility_ratio(high, low, close)
        
        # 4. Volume Trend
        features['volume_trend'] = self._calculate_volume_trend(volume)
        
        # 5. Structure Score (HH/LL analysis)
        features['structure_score'] = self._calculate_structure_score(high, low)
        
        # 6. Range Bound Score (BB %B variance)
        features['range_bound_score'] = self._calculate_range_score(close)
        
        return features
    
    def _calculate_trend_strength(self, high: np.ndarray, low: np.ndarray, close: np.ndarray) -> float:
        """Calculate ADX-like trend strength (0-100 normalized to 0-1)."""
        n = min(14, len(close) - 1)
        if n < 2:
            return 0.0
        
        # True Range
        tr = np.maximum(
            high[1:] - low[1:],
            np.maximum(
                np.abs(high[1:] - close[:-1]),
                np.abs(low[1:] - close[:-1])
            )
        )
        
        # Directional Movement
        plus_dm = np.where((high[1:] - high[:-1]) > (low[:-1] - low[1:]),
                          np.maximum(high[1:] - high[:-1], 0), 0)
        minus_dm = np.where((low[:-1] - low[1:]) > (high[1:] - high[:-1]),
                           np.maximum(low[:-1] - low[1:], 0), 0)
        
        # Smoothed values
        atr = np.mean(tr[-n:])
        plus_di = 100 * np.mean(plus_dm[-n:]) / (atr + 1e-10)
        minus_di = 100 * np.mean(minus_dm[-n:]) / (atr + 1e-10)
        
        # ADX
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        adx = dx / 100.0  # Normalize to 0-1
        
        return float(np.clip(adx, 0, 1))
    
    def _calculate_momentum(self, close: np.ndarray) -> float:
        """Calculate price momentum (-1 to 1 normalized)."""
        if len(close) < 20:
            return 0.0
        
        # Multiple timeframe momentum
        roc_5 = (close[-1] - close[-5]) / close[-5] if len(close) >= 5 else 0
        roc_10 = (close[-1] - close[-10]) / close[-10] if len(close) >= 10 else 0
        roc_20 = (close[-1] - close[-20]) / close[-20] if len(close) >= 20 else 0
        
        # Weighted average
        momentum = 0.5 * roc_5 + 0.3 * roc_10 + 0.2 * roc_20
        
        # Normalize with tanh (keeps -1 to 1 range)
        return float(np.tanh(momentum * 10))
    
    def _calculate_volatility_ratio(self, high: np.ndarray, low: np.ndarray, close: np.ndarray) -> float:
        """Calculate ATR relative to price (normalized)."""
        if len(close) < 14:
            return 0.5
        
        # ATR calculation
        tr = np.maximum(
            high[-14:] - low[-14:],
            np.maximum(
                np.abs(high[-14:] - np.roll(close, 1)[-14:]),
                np.abs(low[-14:] - np.roll(close, 1)[-14:])
            )
        )
        atr = np.mean(tr)
        
        # Relative to price
        ratio = atr / close[-1]
        
        # Normalize (typical ATR/price is 0.5-3%)
        normalized = ratio / 0.02  # 2% as baseline
        
        return float(np.clip(normalized, 0, 3))
    
    def _calculate_volume_trend(self, volume: np.ndarray) -> float:
        """Calculate volume trend (expanding/contracting)."""
        if len(volume) < 20:
            return 0.5
        
        # Volume MA ratio
        vol_sma_5 = np.mean(volume[-5:])
        vol_sma_20 = np.mean(volume[-20:])
        
        ratio = vol_sma_5 / (vol_sma_20 + 1e-10)
        
        # Normalize around 1.0
        return float(np.clip(ratio - 1.0, -1, 1))
    
    def _calculate_structure_score(self, high: np.ndarray, low: np.ndarray) -> float:
        """Calculate market structure (higher highs/lower lows)."""
        if len(high) < 20:
            return 0.0
        
        # Count higher highs and lower lows in last 20 bars
        hh_count = 0
        ll_count = 0
        
        for i in range(-19, 0):
            if high[i] > high[i-1]:
                hh_count += 1
            if low[i] < low[i-1]:
                ll_count += 1
        
        # Score: positive = bullish structure, negative = bearish
        score = (hh_count - ll_count) / 19.0
        
        return float(np.clip(score, -1, 1))
    
    def _calculate_range_score(self, close: np.ndarray) -> float:
        """Calculate how range-bound the market is (BB %B variance)."""
        if len(close) < 20:
            return 0.5
        
        # Bollinger Bands
        sma = np.mean(close[-20:])
        std = np.std(close[-20:])
        
        upper = sma + 2 * std
        lower = sma - 2 * std
        
        # %B values
        pct_b = (close[-20:] - lower) / (upper - lower + 1e-10)
        
        # Variance of %B - low variance = range bound
        variance = np.var(pct_b)
        
        # Invert and normalize (low variance = high range score)
        range_score = 1.0 - np.clip(variance * 10, 0, 1)
        
        return float(range_score)
    
    def _compute_logits(self, features: Dict[str, float]) -> Dict[MarketRegime, float]:
        """Compute raw logits for each regime."""
        logits = {}
        
        for regime in self.REGIMES:
            weights = self._weights[regime]
            logit = 0.0
            
            for feature_name, weight in weights.items():
                if feature_name in features:
                    feature_val = features[feature_name]
                    # Handle negative weights (invert feature)
                    if weight < 0:
                        logit += abs(weight) * (1 - abs(feature_val))
                    else:
                        logit += weight * abs(feature_val)
            
            logits[regime] = logit
        
        return logits
    
    def _softmax(self, logits: Dict[MarketRegime, float]) -> Dict[str, float]:
        """Apply softmax with temperature to logits."""
        # Extract values
        values = np.array([logits[r] for r in self.REGIMES])
        
        # Temperature scaling
        scaled = values / self.temperature
        
        # Softmax
        exp_values = np.exp(scaled - np.max(scaled))
        probabilities = exp_values / exp_values.sum()
        
        return {r.value: float(p) for r, p in zip(self.REGIMES, probabilities)}
    
    def _determine_regime(self, probabilities: Dict[str, float]) -> Tuple[MarketRegime, float]:
        """Determine regime with optional smoothing."""
        # Find argmax
        max_regime = max(probabilities, key=probabilities.get)
        max_prob = probabilities[max_regime]
        
        regime = MarketRegime(max_regime)
        
        # Apply transition smoothing if we have previous state
        if self._previous_state and self.transition_smoothing > 0:
            prev_prob = probabilities.get(self._previous_state.regime.value, 0)
            
            # Require significant probability advantage to change
            if max_prob - prev_prob < self.transition_smoothing:
                regime = self._previous_state.regime
                max_prob = prev_prob
        
        return regime, max_prob
    
    def _record_transition(self, old_state: RegimeState, new_state: RegimeState):
        """Record regime transition."""
        transition = RegimeTransition(
            from_regime=old_state.regime,
            to_regime=new_state.regime,
            timestamp=new_state.timestamp,
            confidence_delta=new_state.confidence - old_state.confidence
        )
        self._transitions.append(transition)
        
        # Keep last 100 transitions
        if len(self._transitions) > 100:
            self._transitions = self._transitions[-50:]
        
        logger.info(f"Regime transition: {old_state.regime.value} -> {new_state.regime.value}")
    
    def get_regime_duration(self) -> int:
        """Get number of bars in current regime."""
        if not self._regime_history:
            return 0
        
        current = self._regime_history[-1][1]
        count = 0
        
        for _, regime in reversed(self._regime_history):
            if regime == current:
                count += 1
            else:
                break
        
        return count
    
    def get_recent_transitions(self, n: int = 5) -> List[RegimeTransition]:
        """Get recent regime transitions."""
        return self._transitions[-n:]
    
    def get_regime_affinity(self, strategy_name: str) -> float:
        """
        Get affinity score for a strategy based on current regime.
        Used by strategy selector to weight strategies.
        """
        if not self._previous_state:
            return 0.5
        
        regime = self._previous_state.regime
        
        # Strategy-regime affinity matrix
        affinities = {
            MarketRegime.BULL: {
                'trend_following': 0.95,
                'momentum_breakout': 0.90,
                'ema_crossover': 0.85,
                'sma_crossover': 0.80,
                'scalping': 0.60,
                'mean_reversion': 0.30,
                'rsi_reversal': 0.40
            },
            MarketRegime.BEAR: {
                'trend_following': 0.95,
                'momentum_breakout': 0.85,
                'ema_crossover': 0.80,
                'sma_crossover': 0.75,
                'scalping': 0.65,
                'mean_reversion': 0.35,
                'rsi_reversal': 0.50
            },
            MarketRegime.SIDEWAYS: {
                'trend_following': 0.20,
                'momentum_breakout': 0.30,
                'ema_crossover': 0.40,
                'sma_crossover': 0.35,
                'scalping': 0.85,
                'mean_reversion': 0.95,
                'rsi_reversal': 0.90
            },
            MarketRegime.VOLATILE: {
                'trend_following': 0.50,
                'momentum_breakout': 0.70,
                'ema_crossover': 0.55,
                'sma_crossover': 0.50,
                'scalping': 0.80,
                'mean_reversion': 0.60,
                'rsi_reversal': 0.85
            },
            MarketRegime.CHOPPY: {
                'trend_following': 0.15,
                'momentum_breakout': 0.25,
                'ema_crossover': 0.30,
                'sma_crossover': 0.25,
                'scalping': 0.70,
                'mean_reversion': 0.80,
                'rsi_reversal': 0.75
            }
        }
        
        regime_affinities = affinities.get(regime, {})
        return regime_affinities.get(strategy_name.lower(), 0.5)
    
    def to_dict(self) -> Dict:
        """Export current state as dictionary."""
        if not self._previous_state:
            return {'regime': 'unknown', 'confidence': 0.0}
        
        return {
            'regime': self._previous_state.regime.value,
            'confidence': self._previous_state.confidence,
            'probabilities': self._previous_state.probabilities,
            'features': self._previous_state.features,
            'duration': self.get_regime_duration(),
            'is_trending': self._previous_state.is_trending,
            'is_ranging': self._previous_state.is_ranging,
            'is_volatile': self._previous_state.is_volatile
        }


# Module-level singleton for easy access
_classifier: Optional[MarketRegimeClassifier] = None


def get_regime_classifier(**kwargs) -> MarketRegimeClassifier:
    """Get or create the regime classifier singleton."""
    global _classifier
    if _classifier is None:
        _classifier = MarketRegimeClassifier(**kwargs)
    return _classifier


def classify_regime(market_data: pd.DataFrame) -> RegimeState:
    """Convenience function to classify regime."""
    return get_regime_classifier().classify(market_data)
