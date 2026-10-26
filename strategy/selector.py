"""
Strategy Selector - Rule-Based
Dynamically selects the best strategy based on market regime and performance.
"""
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from .base import BaseStrategy, Signal

logger = logging.getLogger(__name__)


@dataclass
class StrategyScore:
    """Score breakdown for a strategy."""
    name: str
    regime_fitness: float
    performance_score: float
    confidence: float
    total_score: float


class StrategySelector:
    """
    Selects the best strategy for current market conditions.
    
    Selection factors:
    1. Market regime fitness (40%)
    2. Recent performance (30%)
    3. Signal confidence (30%)
    """
    
    def __init__(self, config: Dict[str, Any], symbol: str):
        self.config = config
        self.symbol = symbol
        
        # Initialize strategies
        self.strategies: Dict[str, BaseStrategy] = {}
        self._initialize_strategies()
        
        # Performance tracking
        self._performance: Dict[str, Dict[str, Any]] = {}
        for name in self.strategies:
            self._performance[name] = {
                'wins': 0,
                'losses': 0,
                'total_pnl': 0.0,
                'recent_signals': []
            }
        
        # Weights for scoring
        self.regime_weight = 0.40
        self.performance_weight = 0.30
        self.confidence_weight = 0.30
        
        logger.info(f"StrategySelector initialized with {len(self.strategies)} strategies")
    
    def _initialize_strategies(self):
        """Initialize all available strategies."""
        from .sma_crossover import SMACrossoverStrategy
        from .ema_crossover import EMACrossoverStrategy
        from .scalping import ScalpingStrategy
        from .momentum import MomentumStrategy
        from .mean_reversion import MeanReversionStrategy
        from .trend_following import TrendFollowingStrategy
        from .rsi_reversal import RSIReversalStrategy

        enabled = self.config.get('enabled_strategies', [])

        _registry = {
            'sma_crossover': SMACrossoverStrategy,
            'ema_crossover': EMACrossoverStrategy,
            'scalping': ScalpingStrategy,
            'momentum': MomentumStrategy,
            'momentum_breakout': MomentumStrategy,  # alias
            'mean_reversion': MeanReversionStrategy,
            'trend_following': TrendFollowingStrategy,
            'rsi_reversal': RSIReversalStrategy,
        }

        for name, cls in _registry.items():
            # Skip duplicates (momentum_breakout → momentum)
            canonical = name.replace('_breakout', '')
            if canonical in self.strategies:
                continue
            # If enabled list is specified, honour it (match either name or alias)
            if enabled and name not in enabled and canonical not in enabled:
                continue
            strategy_config = self.config.get(name, self.config.get(canonical, {}))
            self.strategies[canonical] = cls(strategy_config, self.symbol)

        for name, strategy in self.strategies.items():
            logger.info(f"Initialized strategy: {name}")
    
    def generate_signal(
        self,
        data: Any,
        indicators: Dict[str, Any],
        regime: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Generate signal using the best strategy for current conditions.
        
        Args:
            data: OHLCV DataFrame
            indicators: Pre-calculated indicators
            regime: Current market regime
            
        Returns:
            Signal dict or None
        """
        if regime is None:
            regime = 'unknown'
        
        # Score all strategies
        scores = self._score_strategies(regime)
        
        # Sort by total score
        scores.sort(key=lambda x: x.total_score, reverse=True)
        
        # Log selected strategy
        best = scores[0]
        logger.info(f"Selected strategy: {best.name} (score={best.total_score:.3f}, "
                   f"perf={best.performance_score:.3f}, regime={best.regime_fitness:.3f}, "
                   f"conf={best.confidence:.3f})")
        
        # Try strategies in order until one generates a signal
        for score in scores:
            strategy = self.strategies[score.name]
            signal = strategy.generate_signal(data, indicators)
            
            if signal:
                signal_dict = signal.to_dict()
                signal_dict['strategy_score'] = score.total_score
                signal_dict['regime'] = regime
                return signal_dict
            
            # Log fallback attempts
            if score != scores[0]:
                logger.info(f"Fallback signal from {score.name} (score={score.total_score:.3f})")
        
        return None
    
    def _score_strategies(self, regime: str) -> List[StrategyScore]:
        """Score all strategies for current regime."""
        scores = []
        
        for name, strategy in self.strategies.items():
            # Regime fitness
            regime_fitness = strategy.get_regime_fitness(regime)
            
            # Performance score (win rate normalized to 0-1)
            perf = self._performance[name]
            total_trades = perf['wins'] + perf['losses']
            if total_trades > 0:
                performance_score = perf['wins'] / total_trades
            else:
                performance_score = 0.5  # Default neutral
            
            # Confidence (based on recent signals)
            recent = perf['recent_signals'][-10:] if perf['recent_signals'] else []
            if recent:
                confidence = sum(s.get('confidence', 0.5) for s in recent) / len(recent)
            else:
                confidence = 0.5
            
            # Calculate total score
            total = (
                regime_fitness * self.regime_weight +
                performance_score * self.performance_weight +
                confidence * self.confidence_weight
            )
            
            scores.append(StrategyScore(
                name=name,
                regime_fitness=regime_fitness,
                performance_score=performance_score,
                confidence=confidence,
                total_score=total
            ))
        
        return scores
    
    def update_performance(self, strategy_name: str, trade_result: Dict[str, Any]):
        """Update strategy performance after trade closes."""
        if strategy_name not in self._performance:
            return
        
        perf = self._performance[strategy_name]
        pnl = trade_result.get('pnl', 0)
        
        if pnl > 0:
            perf['wins'] += 1
        else:
            perf['losses'] += 1
        
        perf['total_pnl'] += pnl
        
        # Keep recent signals
        perf['recent_signals'].append(trade_result)
        if len(perf['recent_signals']) > 50:
            perf['recent_signals'] = perf['recent_signals'][-50:]
    
    def get_all_signals(
        self,
        data: Any,
        indicators: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Get signals from all strategies (for analysis/debugging)."""
        signals = []
        
        for name, strategy in self.strategies.items():
            signal = strategy.generate_signal(data, indicators)
            if signal:
                signal_dict = signal.to_dict()
                signal_dict['strategy'] = name
                signals.append(signal_dict)
        
        return signals
