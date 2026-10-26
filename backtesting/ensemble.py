"""
Ensemble Strategy

Multi-strategy ensemble with dynamic weighting and rebalancing.
Combines signals from multiple strategies for improved robustness.
"""

import pandas as pd
import numpy as np
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from cthulu.strategy.base import Strategy, Signal, SignalType


class WeightingMethod(Enum):
    """Methods for weighting ensemble strategies"""
    EQUAL = "equal"                          # Equal weights for all strategies
    PERFORMANCE = "performance"              # Weight by recent performance
    SHARPE = "sharpe"                        # Weight by Sharpe ratio
    WIN_RATE = "win_rate"                    # Weight by win rate
    PROFIT_FACTOR = "profit_factor"          # Weight by profit factor
    ADAPTIVE = "adaptive"                    # Adaptive combination of metrics
    INVERSE_VOLATILITY = "inverse_volatility"  # Weight by inverse volatility
    SOFTMAX = "softmax"                      # ML-based softmax probability weighting
    ARGMAX = "argmax"                        # Select single best strategy


@dataclass
class EnsembleConfig:
    """Configuration for ensemble strategy"""
    weighting_method: WeightingMethod = WeightingMethod.PERFORMANCE
    rebalance_period_bars: int = 100         # Rebalance weights every N bars
    min_weight: float = 0.05                 # Minimum weight per strategy
    max_weight: float = 0.50                 # Maximum weight per strategy
    lookback_period: int = 500               # Lookback for performance calculation
    confidence_threshold: float = 0.6        # Minimum ensemble confidence to trade
    require_unanimous: bool = False          # Require all strategies to agree
    require_majority: bool = False           # Require majority agreement
    enable_signal_filtering: bool = True     # Filter weak signals
    filter_threshold: float = 0.5            # Minimum individual signal confidence
    
    # Vote aggregation
    vote_by_confidence: bool = True          # Weight votes by signal confidence
    normalize_weights: bool = True           # Normalize weights to sum to 1.0
    
    # ML-enhanced options (for SOFTMAX/ARGMAX methods)
    softmax_temperature: float = 1.0         # Softmax temperature (lower = more greedy)
    argmax_exploration: float = 0.1          # Epsilon-greedy exploration rate
    enable_price_prediction: bool = False    # Enable ML price prediction


class EnsembleStrategy(Strategy):
    """
    Ensemble strategy that combines multiple strategies.
    
    Features:
    - Multiple weighting methods (equal, performance-based, adaptive)
    - Dynamic rebalancing based on recent performance
    - Signal aggregation with configurable voting rules
    - Confidence scoring for combined signals
    - Performance tracking per sub-strategy
    """
    
    def __init__(
        self,
        name: str,
        strategies: List[Strategy],
        config: Optional[EnsembleConfig] = None
    ):
        """
        Initialize ensemble strategy.
        
        Args:
            name: Ensemble strategy name
            strategies: List of strategy instances
            config: Ensemble configuration
        """
        super().__init__(name, {})
        self.strategies = strategies
        self.config = config or EnsembleConfig()
        self.logger = logging.getLogger(f"cthulu.backtesting.ensemble.{name}")
        
        # State
        self.weights: Dict[str, float] = {s.name: 1.0 / len(strategies) for s in strategies}
        self.strategy_performance: Dict[str, List[float]] = defaultdict(list)
        self.strategy_trades: Dict[str, int] = defaultdict(int)
        self.strategy_wins: Dict[str, int] = defaultdict(int)
        self.bar_count = 0
        self.last_rebalance = 0
        
        # Signal history for performance tracking
        self.signal_history: List[Dict[str, Any]] = []
        
        self.logger.info(f"Initialized ensemble with {len(strategies)} strategies")
        self.logger.info(f"Weighting method: {self.config.weighting_method.value}")
        
    def on_bar(self, bar: pd.Series) -> Optional[Signal]:
        """
        Process bar and generate ensemble signal.
        
        Args:
            bar: Current bar data
            
        Returns:
            Ensemble signal or None
        """
        self.bar_count += 1
        
        # Rebalance weights periodically
        if (self.bar_count - self.last_rebalance) >= self.config.rebalance_period_bars:
            self._rebalance_weights()
            self.last_rebalance = self.bar_count
            
        # Collect signals from all strategies
        signals: List[Tuple[Strategy, Signal]] = []
        for strategy in self.strategies:
            try:
                signal = strategy.on_bar(bar)
                if signal:
                    # Filter weak signals if enabled
                    if self.config.enable_signal_filtering:
                        if signal.confidence >= self.config.filter_threshold:
                            signals.append((strategy, signal))
                    else:
                        signals.append((strategy, signal))
            except Exception as e:
                self.logger.error(f"Strategy {strategy.name} error: {e}")
                
        if not signals:
            return None
            
        # Check voting rules
        if self.config.require_unanimous and len(signals) < len(self.strategies):
            return None
            
        if self.config.require_majority and len(signals) < len(self.strategies) / 2:
            return None
            
        # Aggregate signals
        ensemble_signal = self._aggregate_signals(signals, bar)
        
        # Check confidence threshold
        if ensemble_signal and ensemble_signal.confidence >= self.config.confidence_threshold:
            return ensemble_signal
            
        return None
        
    def _aggregate_signals(
        self,
        signals: List[Tuple[Strategy, Signal]],
        bar: pd.Series
    ) -> Optional[Signal]:
        """
        Aggregate signals from multiple strategies.
        
        Args:
            signals: List of (strategy, signal) tuples
            bar: Current bar data
            
        Returns:
            Aggregated ensemble signal
        """
        # Separate by signal type
        long_signals = []
        short_signals = []
        
        for strategy, signal in signals:
            weight = self.weights.get(strategy.name, 0.0)
            
            if self.config.vote_by_confidence:
                vote_power = weight * signal.confidence
            else:
                vote_power = weight
                
            if signal.side == SignalType.LONG:
                long_signals.append((vote_power, signal, strategy.name))
            elif signal.side == SignalType.SHORT:
                short_signals.append((vote_power, signal, strategy.name))
                
        # Calculate total votes
        long_votes = sum(v[0] for v in long_signals)
        short_votes = sum(v[0] for v in short_signals)
        
        # Determine winning direction
        if long_votes == 0 and short_votes == 0:
            return None
            
        if long_votes > short_votes:
            winning_signals = long_signals
            signal_type = SignalType.LONG
            total_votes = long_votes
        elif short_votes > long_votes:
            winning_signals = short_signals
            signal_type = SignalType.SHORT
            total_votes = short_votes
        else:
            # Tie - no clear signal
            return None
            
        # Calculate ensemble confidence (normalized total votes)
        if self.config.normalize_weights:
            total_possible = sum(self.weights.values())
            ensemble_confidence = total_votes / total_possible if total_possible > 0 else 0.0
        else:
            ensemble_confidence = total_votes
            
        # Weighted average of stop loss and take profit
        avg_stop_loss = None
        avg_take_profit = None
        
        stop_losses = [s[1].stop_loss for s in winning_signals if s[1].stop_loss is not None]
        if stop_losses:
            weights_with_sl = [s[0] for s in winning_signals if s[1].stop_loss is not None]
            avg_stop_loss = np.average(stop_losses, weights=weights_with_sl)
            
        take_profits = [s[1].take_profit for s in winning_signals if s[1].take_profit is not None]
        if take_profits:
            weights_with_tp = [s[0] for s in winning_signals if s[1].take_profit is not None]
            avg_take_profit = np.average(take_profits, weights=weights_with_tp)
            
        # Create ensemble signal
        ensemble_signal = Signal(
            id=f"ensemble_{self.bar_count}",
            timestamp=bar.name,
            symbol=winning_signals[0][1].symbol,
            timeframe=winning_signals[0][1].timeframe,
            side=signal_type,
            action="ensemble",
            price=bar['close'],
            stop_loss=avg_stop_loss,
            take_profit=avg_take_profit,
            confidence=ensemble_confidence,
            reason=f"Ensemble: {len(winning_signals)} strategies agree ({signal_type.value})",
            metadata={
                'ensemble': True,
                'num_strategies': len(winning_signals),
                'contributing_strategies': [s[2] for s in winning_signals],
                'votes': total_votes,
                'weighting_method': self.config.weighting_method.value,
            }
        )
        
        # Record signal for later performance tracking
        self.signal_history.append({
            'bar_count': self.bar_count,
            'signal': ensemble_signal,
            'contributing_strategies': [s[2] for s in winning_signals],
        })
        
        return ensemble_signal
        
    def _rebalance_weights(self) -> None:
        """Rebalance strategy weights based on recent performance."""
        method = self.config.weighting_method
        
        if method == WeightingMethod.EQUAL:
            # Equal weights
            weight = 1.0 / len(self.strategies)
            self.weights = {s.name: weight for s in self.strategies}
            
        elif method == WeightingMethod.PERFORMANCE:
            # Weight by recent cumulative returns
            self._rebalance_by_performance()
            
        elif method == WeightingMethod.SHARPE:
            # Weight by Sharpe ratio
            self._rebalance_by_sharpe()
            
        elif method == WeightingMethod.WIN_RATE:
            # Weight by win rate
            self._rebalance_by_win_rate()
            
        elif method == WeightingMethod.ADAPTIVE:
            # Adaptive combination
            self._rebalance_adaptive()
            
        else:
            self.logger.warning(f"Unknown weighting method: {method}, using equal weights")
            weight = 1.0 / len(self.strategies)
            self.weights = {s.name: weight for s in self.strategies}
            
        # Apply weight constraints
        self._apply_weight_constraints()
        
        self.logger.debug(f"Rebalanced weights: {self.weights}")
        
    def _rebalance_by_performance(self) -> None:
        """Rebalance by recent cumulative performance."""
        for strategy in self.strategies:
            recent_perf = self.strategy_performance[strategy.name][-self.config.lookback_period:]
            if recent_perf:
                cumulative_return = sum(recent_perf)
                # Use exponential function to amplify positive performance
                self.weights[strategy.name] = max(0.0, np.exp(cumulative_return / 100))
            else:
                self.weights[strategy.name] = 1.0
                
    def _rebalance_by_sharpe(self) -> None:
        """Rebalance by Sharpe ratio."""
        for strategy in self.strategies:
            recent_perf = self.strategy_performance[strategy.name][-self.config.lookback_period:]
            if len(recent_perf) > 10:
                mean = np.mean(recent_perf)
                std = np.std(recent_perf)
                sharpe = (mean / std) if std > 0 else 0.0
                self.weights[strategy.name] = max(0.0, sharpe)
            else:
                self.weights[strategy.name] = 1.0
                
    def _rebalance_by_win_rate(self) -> None:
        """Rebalance by win rate."""
        for strategy in self.strategies:
            trades = self.strategy_trades[strategy.name]
            wins = self.strategy_wins[strategy.name]
            if trades > 0:
                win_rate = wins / trades
                self.weights[strategy.name] = win_rate
            else:
                self.weights[strategy.name] = 1.0
                
    def _rebalance_adaptive(self) -> None:
        """Adaptive rebalancing combining multiple metrics."""
        # Combine performance, Sharpe, and win rate
        performance_weights = {}
        sharpe_weights = {}
        win_rate_weights = {}
        
        # Calculate each metric
        for strategy in self.strategies:
            # Performance
            recent_perf = self.strategy_performance[strategy.name][-self.config.lookback_period:]
            if recent_perf:
                performance_weights[strategy.name] = max(0.0, sum(recent_perf) / 100)
            else:
                performance_weights[strategy.name] = 1.0
                
            # Sharpe
            if len(recent_perf) > 10:
                mean = np.mean(recent_perf)
                std = np.std(recent_perf)
                sharpe = (mean / std) if std > 0 else 0.0
                sharpe_weights[strategy.name] = max(0.0, sharpe)
            else:
                sharpe_weights[strategy.name] = 1.0
                
            # Win rate
            trades = self.strategy_trades[strategy.name]
            wins = self.strategy_wins[strategy.name]
            if trades > 0:
                win_rate_weights[strategy.name] = wins / trades
            else:
                win_rate_weights[strategy.name] = 0.5
                
        # Combine with equal weighting (can be made configurable)
        for strategy in self.strategies:
            self.weights[strategy.name] = (
                performance_weights[strategy.name] * 0.4 +
                sharpe_weights[strategy.name] * 0.3 +
                win_rate_weights[strategy.name] * 0.3
            )
            
    def _apply_weight_constraints(self) -> None:
        """Apply min/max weight constraints and normalization."""
        # Apply min/max constraints
        for name in self.weights:
            self.weights[name] = max(self.config.min_weight, min(self.config.max_weight, self.weights[name]))
            
        # Normalize if enabled
        if self.config.normalize_weights:
            total = sum(self.weights.values())
            if total > 0:
                self.weights = {name: w / total for name, w in self.weights.items()}
                
    def record_trade_result(self, strategy_name: str, pnl: float) -> None:
        """
        Record trade result for a strategy.
        
        Args:
            strategy_name: Name of strategy that generated the signal
            pnl: Profit/loss of the trade
        """
        self.strategy_performance[strategy_name].append(pnl)
        self.strategy_trades[strategy_name] += 1
        if pnl > 0:
            self.strategy_wins[strategy_name] += 1
            
    def get_strategy_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get performance statistics for each strategy."""
        stats = {}
        
        for strategy in self.strategies:
            name = strategy.name
            trades = self.strategy_trades[name]
            wins = self.strategy_wins[name]
            perf = self.strategy_performance[name]
            
            stats[name] = {
                'weight': self.weights.get(name, 0.0),
                'trades': trades,
                'wins': wins,
                'win_rate': wins / trades if trades > 0 else 0.0,
                'total_pnl': sum(perf) if perf else 0.0,
                'avg_pnl': np.mean(perf) if perf else 0.0,
            }
            
        return stats
