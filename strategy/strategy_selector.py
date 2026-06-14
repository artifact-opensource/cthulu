"""
Dynamic Strategy Selector

Intelligently selects and switches between strategies based on market regime,
performance metrics, and real-time conditions. Enables autonomous strategy adaptation.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import deque
import pandas as pd
import numpy as np

from cthulu.strategy.base import Strategy, Signal


class MarketRegime:
    """Market regime classification."""
    TRENDING_UP_STRONG = "trending_up_strong"
    TRENDING_UP_WEAK = "trending_up_weak"
    TRENDING_DOWN_STRONG = "trending_down_strong"
    TRENDING_DOWN_WEAK = "trending_down_weak"
    RANGING_TIGHT = "ranging_tight"
    RANGING_WIDE = "ranging_wide"
    VOLATILE_BREAKOUT = "volatile_breakout"
    VOLATILE_CONSOLIDATION = "volatile_consolidation"
    CONSOLIDATING = "consolidating"
    REVERSAL = "reversal"


class StrategyPerformance:
    """Track strategy performance metrics."""
    
    def __init__(self, strategy_name: str, window_size: int = 50):
        self.strategy_name = strategy_name
        self.window_size = window_size
        self.signals_count = 0
        self.wins = 0
        self.losses = 0
        self.total_profit = 0.0
        self.total_loss = 0.0
        self.recent_signals = deque(maxlen=window_size)
        self.last_signal_time = None
        self.confidence_scores = deque(maxlen=window_size)
        
    def add_signal(self, signal: Optional[Signal] = None, outcome: Optional[str] = None, pnl: Optional[float] = None):
        """Record a signal and its outcome."""
        if signal:
            self.signals_count += 1
            self.last_signal_time = datetime.now()
            self.confidence_scores.append(signal.confidence)
        
        if outcome:
            self.recent_signals.append({
                'outcome': outcome,
                'pnl': pnl or 0.0,
                'timestamp': datetime.now()
            })
            
            if outcome == 'win' and pnl:
                self.wins += 1
                self.total_profit += pnl
            elif outcome == 'loss' and pnl:
                self.losses += 1
                self.total_loss += abs(pnl)
                
    @property
    def win_rate(self) -> float:
        """Calculate win rate."""
        total = self.wins + self.losses
        return self.wins / total if total > 0 else 0.0
        
    @property
    def profit_factor(self) -> float:
        """Calculate profit factor."""
        return self.total_profit / self.total_loss if self.total_loss > 0 else 0.0
        
    @property
    def avg_confidence(self) -> float:
        """Average confidence of recent signals."""
        return np.mean(self.confidence_scores) if self.confidence_scores else 0.0
        
    @property
    def recent_performance_score(self) -> float:
        """Score based on recent signals (0-1)."""
        if not self.recent_signals:
            return 0.5  # Neutral score with no history
            
        recent_wins = sum(1 for s in self.recent_signals if s['outcome'] == 'win')
        recent_total = len(self.recent_signals)
        
        return recent_wins / recent_total if recent_total > 0 else 0.5


class StrategySelector:
    """
    Dynamic strategy selector that chooses the best strategy based on:
    - Market regime detection
    - Individual strategy performance
    - Market conditions (volatility, trend strength)
    - Strategy confidence scores
    """
    
    def __init__(self, strategies: List[Strategy], config: Dict[str, Any] = None):
        """
        Initialize strategy selector.
        
        Args:
            strategies: List of available strategies
            config: Configuration parameters
        """
        self.strategies = {s.name: s for s in strategies}
        self.config = config or {}
        self.logger = logging.getLogger("cthulu.strategy_selector")
        
        # Performance tracking
        self.performance = {
            name: StrategyPerformance(name) 
            for name in self.strategies.keys()
        }
        
        # Current state
        self.current_strategy = None
        self.current_regime = MarketRegime.RANGING_TIGHT
        self.last_regime_check = None
        self.regime_history = deque(maxlen=20)
        
        # Configuration
        self.regime_check_interval = self.config.get('regime_check_interval', 30)  # Check regime every 30 seconds
        self.min_strategy_signals = self.config.get('min_strategy_signals', 5)
        self.performance_weight = self.config.get('performance_weight', 0.4)
        self.regime_weight = self.config.get('regime_weight', 0.4)
        self.confidence_weight = self.config.get('confidence_weight', 0.2)
        
        # Strategy-regime affinity (which strategies work best in which regimes)
        self.strategy_affinity = {
            'sma_crossover': {
                MarketRegime.TRENDING_UP_STRONG: 0.95,
                MarketRegime.TRENDING_UP_WEAK: 0.85,
                MarketRegime.TRENDING_DOWN_STRONG: 0.95,
                MarketRegime.TRENDING_DOWN_WEAK: 0.85,
                MarketRegime.RANGING_TIGHT: 0.4,
                MarketRegime.RANGING_WIDE: 0.6,
                MarketRegime.VOLATILE_BREAKOUT: 0.7,
                MarketRegime.VOLATILE_CONSOLIDATION: 0.5,
                MarketRegime.CONSOLIDATING: 0.5,
                MarketRegime.REVERSAL: 0.3
            },
            'ema_crossover': {
                MarketRegime.TRENDING_UP_STRONG: 0.98,
                MarketRegime.TRENDING_UP_WEAK: 0.90,
                MarketRegime.TRENDING_DOWN_STRONG: 0.98,
                MarketRegime.TRENDING_DOWN_WEAK: 0.90,
                MarketRegime.RANGING_TIGHT: 0.5,
                MarketRegime.RANGING_WIDE: 0.7,
                MarketRegime.VOLATILE_BREAKOUT: 0.8,
                MarketRegime.VOLATILE_CONSOLIDATION: 0.6,
                MarketRegime.CONSOLIDATING: 0.6,
                MarketRegime.REVERSAL: 0.4
            },
            'momentum_breakout': {
                MarketRegime.TRENDING_UP_STRONG: 0.8,
                MarketRegime.TRENDING_UP_WEAK: 0.6,
                MarketRegime.TRENDING_DOWN_STRONG: 0.8,
                MarketRegime.TRENDING_DOWN_WEAK: 0.6,
                MarketRegime.RANGING_TIGHT: 0.7,
                MarketRegime.RANGING_WIDE: 0.8,
                MarketRegime.VOLATILE_BREAKOUT: 0.95,
                MarketRegime.VOLATILE_CONSOLIDATION: 0.4,
                MarketRegime.CONSOLIDATING: 0.3,
                MarketRegime.REVERSAL: 0.9
            },
            'scalping': {
                MarketRegime.TRENDING_UP_STRONG: 0.7,
                MarketRegime.TRENDING_UP_WEAK: 0.5,
                MarketRegime.TRENDING_DOWN_STRONG: 0.7,
                MarketRegime.TRENDING_DOWN_WEAK: 0.5,
                MarketRegime.RANGING_TIGHT: 0.95,
                MarketRegime.RANGING_WIDE: 0.8,
                MarketRegime.VOLATILE_BREAKOUT: 0.6,
                MarketRegime.VOLATILE_CONSOLIDATION: 0.9,
                MarketRegime.CONSOLIDATING: 0.8,
                MarketRegime.REVERSAL: 0.7
            },
            'mean_reversion': {
                MarketRegime.TRENDING_UP_STRONG: 0.3,
                MarketRegime.TRENDING_UP_WEAK: 0.4,
                MarketRegime.TRENDING_DOWN_STRONG: 0.3,
                MarketRegime.TRENDING_DOWN_WEAK: 0.4,
                MarketRegime.RANGING_TIGHT: 0.95,
                MarketRegime.RANGING_WIDE: 0.85,
                MarketRegime.VOLATILE_BREAKOUT: 0.5,
                MarketRegime.VOLATILE_CONSOLIDATION: 0.7,
                MarketRegime.CONSOLIDATING: 0.9,
                MarketRegime.REVERSAL: 0.8
            },
            'rsi_reversal': {
                MarketRegime.TRENDING_UP_STRONG: 0.5,
                MarketRegime.TRENDING_UP_WEAK: 0.6,
                MarketRegime.TRENDING_DOWN_STRONG: 0.5,
                MarketRegime.TRENDING_DOWN_WEAK: 0.6,
                MarketRegime.RANGING_TIGHT: 0.90,
                MarketRegime.RANGING_WIDE: 0.85,
                MarketRegime.VOLATILE_BREAKOUT: 0.7,
                MarketRegime.VOLATILE_CONSOLIDATION: 0.95,
                MarketRegime.CONSOLIDATING: 0.85,
                MarketRegime.REVERSAL: 0.98
            },
            'trend_following': {
                MarketRegime.TRENDING_UP_STRONG: 0.98,
                MarketRegime.TRENDING_UP_WEAK: 0.9,
                MarketRegime.TRENDING_DOWN_STRONG: 0.98,
                MarketRegime.TRENDING_DOWN_WEAK: 0.9,
                MarketRegime.RANGING_TIGHT: 0.2,
                MarketRegime.RANGING_WIDE: 0.3,
                MarketRegime.VOLATILE_BREAKOUT: 0.8,
                MarketRegime.VOLATILE_CONSOLIDATION: 0.4,
                MarketRegime.CONSOLIDATING: 0.3,
                MarketRegime.REVERSAL: 0.5
            }
        }
        
        self.logger.info(f"StrategySelector initialized with {len(strategies)} strategies")
        
    def detect_market_regime(self, data: pd.DataFrame) -> str:
        """
        Detect current market regime from price data using multiple indicators.
        
        Args:
            data: DataFrame with OHLCV and indicators
            
        Returns:
            Market regime classification
        """
        try:
            if len(data) < 50:
                self.logger.warning("Insufficient data for regime detection (need 50 bars)")
                return MarketRegime.RANGING_TIGHT
                
            # Get latest values (coerce to safe numeric defaults when missing)
            adx = data['adx'].iloc[-1] if 'adx' in data.columns and pd.notna(data['adx'].iloc[-1]) else 0.0
            rsi = data['rsi'].iloc[-1] if 'rsi' in data.columns and pd.notna(data['rsi'].iloc[-1]) else 50.0
            macd = data['macd'].iloc[-1] if 'macd' in data.columns and pd.notna(data['macd'].iloc[-1]) else 0.0
            macd_signal = data['macd_signal'].iloc[-1] if 'macd_signal' in data.columns and pd.notna(data['macd_signal'].iloc[-1]) else 0.0
            bb_upper = data['bb_upper'].iloc[-1] if 'bb_upper' in data.columns and pd.notna(data['bb_upper'].iloc[-1]) else data['high'].iloc[-1]
            bb_lower = data['bb_lower'].iloc[-1] if 'bb_lower' in data.columns and pd.notna(data['bb_lower'].iloc[-1]) else data['low'].iloc[-1]
            
            # Calculate additional metrics (guard against NaN)
            returns = data['close'].pct_change(20).iloc[-1]
            returns = returns if pd.notna(returns) else 0.0
            volatility = data['close'].pct_change().rolling(20).std().iloc[-1]
            volatility = volatility if pd.notna(volatility) else 0.0
            bb_width = (bb_upper - bb_lower) / data['close'].iloc[-1] if pd.notna(data['close'].iloc[-1]) and (bb_upper - bb_lower) != 0 else 0.0  # Normalized BB width
            
            # Trend strength indicators
            trend_strength = adx if adx else abs(returns) * 100
            
            # MACD momentum
            macd_histogram = macd - macd_signal
            macd_trend = 1 if macd_histogram > 0 else -1
            
            # Price position in BB
            price_pos = (data['close'].iloc[-1] - bb_lower) / (bb_upper - bb_lower) if bb_upper != bb_lower else 0.5
            
            # Regime classification logic
            regime = MarketRegime.RANGING_TIGHT  # Default
            
            # Strong trending regimes
            if trend_strength > 30:
                if returns > 0.005:  # Strong uptrend
                    regime = MarketRegime.TRENDING_UP_STRONG
                elif returns < -0.005:  # Strong downtrend
                    regime = MarketRegime.TRENDING_DOWN_STRONG
                elif returns > 0.002:  # Weak uptrend
                    regime = MarketRegime.TRENDING_UP_WEAK
                elif returns < -0.002:  # Weak downtrend
                    regime = MarketRegime.TRENDING_DOWN_WEAK
            
            # Volatile regimes
            elif volatility > 0.015:  # High volatility
                if bb_width > 0.03:  # Wide bands = potential breakout
                    regime = MarketRegime.VOLATILE_BREAKOUT
                else:  # Tight bands = consolidation before move
                    regime = MarketRegime.VOLATILE_CONSOLIDATION
            
            # Ranging regimes
            elif bb_width < 0.015:  # Tight range
                regime = MarketRegime.RANGING_TIGHT
            elif bb_width > 0.025:  # Wide range
                regime = MarketRegime.RANGING_WIDE
            
            # Consolidation (low volatility, medium trend)
            elif trend_strength < 20 and volatility < 0.01:
                regime = MarketRegime.CONSOLIDATING
            
            # Reversal signals (RSI extreme + MACD divergence)
            elif ((rsi > 70 and macd_trend < 0) or (rsi < 30 and macd_trend > 0)):
                regime = MarketRegime.REVERSAL
            
            # Log regime with details
            self.logger.info(
                f"Market regime: {regime} "
                f"(ADX={adx:.1f}, RSI={rsi:.1f}, Returns={returns:.3f}, Vol={volatility:.3f}, BB={bb_width:.3f})"
            )
            
            return regime
            
        except Exception as e:
            self.logger.exception(f"Error in regime detection: {e}")
            return MarketRegime.RANGING_TIGHT
        
    def select_strategy(self, data: pd.DataFrame) -> Strategy:
        """
        Select the best strategy for current conditions.
        
        Args:
            data: Market data with indicators
            
        Returns:
            Selected strategy instance
        """
        # Update market regime if needed
        now = datetime.now()
        time_since_check = (now - self.last_regime_check).total_seconds() if self.last_regime_check else float('inf')
        
        if self.last_regime_check is None or time_since_check > self.regime_check_interval:
            self.logger.info(f"Updating market regime (last check: {time_since_check:.1f}s ago)")
            self.current_regime = self.detect_market_regime(data)
            self.last_regime_check = now
        else:
            self.logger.debug(f"Using cached regime: {self.current_regime} (checked {time_since_check:.1f}s ago)")
            
        # Calculate scores for each strategy
        scores = {}
        
        for name, strategy in self.strategies.items():
            perf = self.performance[name]
            
            # Performance score
            if perf.signals_count >= self.min_strategy_signals:
                perf_score = (perf.win_rate * 0.5 + 
                             min(perf.profit_factor / 2.0, 1.0) * 0.3 +
                             perf.recent_performance_score * 0.2)
            else:
                perf_score = 0.5  # Neutral for untested strategies
                
            # Regime affinity score
            affinity = self.strategy_affinity.get(name, {})
            regime_score = affinity.get(self.current_regime, 0.5)
            
            # Confidence score
            confidence_score = perf.avg_confidence if perf.confidence_scores else 0.5
            
            # Combined weighted score
            total_score = (perf_score * self.performance_weight +
                          regime_score * self.regime_weight +
                          confidence_score * self.confidence_weight)
                          
            scores[name] = {
                'total': total_score,
                'performance': perf_score,
                'regime': regime_score,
                'confidence': confidence_score
            }
            
        # Select strategy with highest score
        best_strategy_name = max(scores.keys(), key=lambda k: scores[k]['total'])
        best_score = scores[best_strategy_name]
        
        # Log selection reasoning
        self.logger.info(
            f"Selected strategy: {best_strategy_name} "
            f"(score={best_score['total']:.3f}, perf={best_score['performance']:.3f}, "
            f"regime={best_score['regime']:.3f}, conf={best_score['confidence']:.3f})"
        )
        
        # Log all scores for transparency
        for name, score in scores.items():
            if name != best_strategy_name:
                self.logger.debug(
                    f"  {name}: total={score['total']:.3f}, "
                    f"perf={score['performance']:.3f}, "
                    f"regime={score['regime']:.3f}"
                )
        
        self.current_strategy = self.strategies[best_strategy_name]
        return self.current_strategy
        
    def generate_signal(self, data: pd.DataFrame, bar: pd.Series) -> Optional[Signal]:
        """
        Generate signal using selected strategy with CONTROLLED fallback.
        
        CRITICAL FIX: No longer tries ALL strategies blindly. Requires:
        1. Primary strategy signal OR
        2. At least 2 high-scoring strategies agreeing on direction
        
        Args:
            data: Full market data
            bar: Latest bar
            
        Returns:
            Signal from selected strategy or consensus fallback
        """
        # Select best strategy
        primary_strategy = self.select_strategy(data)
        
        # Try primary strategy first
        signal = primary_strategy.on_bar(bar)
        
        if signal:
            # Track and return primary signal
            self.performance[primary_strategy.name].add_signal(signal)
            return signal
        
        # CRITICAL FIX: Only use fallback if we have CONSENSUS
        # No more "try all and take first signal" approach
        scores = self._calculate_all_scores(data)
        sorted_strategies = sorted(
            [(name, s['total']) for name, s in scores.items() if name != primary_strategy.name],
            key=lambda x: x[1],
            reverse=True
        )
        
        # Only try TOP 2 highest scoring strategies for consensus
        # AND they must have score > 0.65 (strong affinity to current regime)
        fallback_signals = []
        min_fallback_score = self.config.get('min_fallback_score', 0.65)
        max_fallback_attempts = self.config.get('max_fallback_strategies', 2)
        
        for name, score in sorted_strategies[:max_fallback_attempts]:
            if score < min_fallback_score:
                self.logger.debug(f"Skipping {name} - score {score:.3f} below threshold {min_fallback_score}")
                continue
                
            fallback = self.strategies[name]
            try:
                fb_signal = fallback.on_bar(bar)
                if fb_signal:
                    fallback_signals.append({
                        'name': name,
                        'score': score,
                        'signal': fb_signal
                    })
            except Exception as e:
                self.logger.debug(f"Fallback {name} failed: {e}")
        
        # CONSENSUS CHECK: Need at least 1 high-quality fallback
        # If we have multiple, they must agree on direction
        if len(fallback_signals) == 0:
            self.logger.info("No valid fallback signals - market unclear, skipping")
            return None
        
        if len(fallback_signals) == 1:
            # Single high-quality fallback - use it but mark as lower confidence
            fb = fallback_signals[0]
            signal = fb['signal']
            original_conf = signal.confidence
            signal.confidence = signal.confidence * 0.85  # Reduce confidence for fallback
            self.logger.info(
                f"Fallback signal from {fb['name']} (score={fb['score']:.3f}, "
                f"conf: {original_conf:.2f} → {signal.confidence:.2f})"
            )
            self.performance[fb['name']].add_signal(signal)
            return signal
        
        # Multiple fallbacks - check for direction consensus
        directions = [s['signal'].side for s in fallback_signals]
        if all(d == directions[0] for d in directions):
            # CONSENSUS - use highest scoring signal with boosted confidence
            best = fallback_signals[0]
            signal = best['signal']
            signal.confidence = min(1.0, signal.confidence * 1.1)  # Slight boost for consensus
            self.logger.info(
                f"CONSENSUS signal ({len(fallback_signals)} strategies agree): "
                f"{best['name']} (score={best['score']:.3f})"
            )
            self.performance[best['name']].add_signal(signal)
            return signal
        else:
            # CONFLICT - strategies disagree, do NOT enter
            dir_names = [(s['name'], s['signal'].side.name) for s in fallback_signals]
            self.logger.info(f"Direction conflict between strategies: {dir_names} - NO SIGNAL")
            return None
    
    def _calculate_all_scores(self, data: pd.DataFrame) -> Dict[str, Dict[str, float]]:
        """Calculate scores for all strategies."""
        scores = {}
        
        for name, strategy in self.strategies.items():
            perf = self.performance[name]
            
            # Performance score
            if perf.signals_count >= self.min_strategy_signals:
                perf_score = (perf.win_rate * 0.5 + 
                             min(perf.profit_factor / 2.0, 1.0) * 0.3 +
                             perf.recent_performance_score * 0.2)
            else:
                perf_score = 0.5  # Neutral for untested strategies
                
            # Regime affinity score
            affinity = self.strategy_affinity.get(name, {})
            regime_score = affinity.get(self.current_regime, 0.5)
            
            # Confidence score
            confidence_score = perf.avg_confidence if perf.confidence_scores else 0.5
            
            # Combined weighted score
            total_score = (perf_score * self.performance_weight +
                          regime_score * self.regime_weight +
                          confidence_score * self.confidence_weight)
                          
            scores[name] = {
                'total': total_score,
                'performance': perf_score,
                'regime': regime_score,
                'confidence': confidence_score
            }
            
        return scores
        
    def record_outcome(self, strategy_name: str, outcome: str, pnl: float):
        """
        Record the outcome of a signal.
        
        Args:
            strategy_name: Name of strategy that generated the signal
            outcome: 'win' or 'loss'
            pnl: Profit/loss amount
        """
        if strategy_name in self.performance:
            # Update the most recent signal with outcome
            self.performance[strategy_name].add_signal(
                None,  # No new signal, just updating outcome
                outcome=outcome,
                pnl=pnl
            )
            
            self.logger.info(
                f"Recorded {outcome} for {strategy_name}: "
                f"${pnl:.2f} (WinRate={self.performance[strategy_name].win_rate:.2%})"
            )
            
    def get_performance_report(self) -> Dict[str, Any]:
        """Get detailed performance report for all strategies."""
        report = {
            'current_regime': self.current_regime,
            'current_strategy': self.current_strategy.name if self.current_strategy else None,
            'strategies': {}
        }
        
        for name, perf in self.performance.items():
            report['strategies'][name] = {
                'signals_count': perf.signals_count,
                'win_rate': perf.win_rate,
                'profit_factor': perf.profit_factor,
                'avg_confidence': perf.avg_confidence,
                'recent_performance': perf.recent_performance_score,
                'total_profit': perf.total_profit,
                'total_loss': perf.total_loss
            }
            
        return report




