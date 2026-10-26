"""
Strategy Factory Module

Centralized strategy creation with validation and error handling.
Replaces scattered strategy loading logic with a clean factory pattern.
"""

import logging
from typing import Dict, Any, Optional

from cthulu.strategy.base import Strategy
from cthulu.strategy.sma_crossover import SmaCrossover
from cthulu.strategy.ema_crossover import EmaCrossover
from cthulu.strategy.momentum_breakout import MomentumBreakout
from cthulu.strategy.scalping import ScalpingStrategy
from cthulu.strategy.trend_following import TrendFollowingStrategy
from cthulu.strategy.mean_reversion import MeanReversionStrategy
from cthulu.strategy.rsi_reversal import RsiReversalStrategy
from cthulu.strategy.strategy_selector import StrategySelector
from cthulu.strategy.selector_adapter import StrategySelectorAdapter


# Strategy registry mapping type names to classes
STRATEGY_REGISTRY = {
    'sma_crossover': SmaCrossover,
    'ema_crossover': EmaCrossover,
    'momentum_breakout': MomentumBreakout,
    'scalping': ScalpingStrategy,
    'trend_following': TrendFollowingStrategy,
    'mean_reversion': MeanReversionStrategy,
    'rsi_reversal': RsiReversalStrategy
}


class StrategyFactory:
    """Factory for creating trading strategies with validation."""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize strategy factory.
        
        Args:
            logger: Logger instance for diagnostic output
        """
        self.logger = logger or logging.getLogger(__name__)
        self.registry = STRATEGY_REGISTRY.copy()
    
    def create(self, config: Dict[str, Any]) -> Strategy:
        """Create strategy from configuration.
        
        Args:
            config: Strategy configuration dictionary
            
        Returns:
            Configured strategy instance or StrategySelector for dynamic mode
            
        Raises:
            ValueError: If configuration is invalid or strategy type unknown
        """
        if not isinstance(config, dict):
            raise ValueError("Strategy config must be a dictionary")
        
        # Normalize config: expose params at top level for backward compatibility
        normalized = self._normalize_config(config)
        strategy_type = normalized.get('type', '').lower()
        
        if not strategy_type:
            raise ValueError("Strategy configuration must include 'type' field")
        
        # Dynamic strategy selection mode
        if strategy_type == 'dynamic':
            return self._create_dynamic_strategy(config)
        
        # Single strategy mode
        return self._create_single_strategy(normalized)
    
    def _normalize_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize strategy configuration.
        
        Exposes params at top level while keeping nested structure intact.
        This maintains backward compatibility with strategies expecting flat config.
        
        Args:
            config: Raw configuration
            
        Returns:
            Normalized configuration
        """
        normalized = dict(config)
        params = normalized.get('params', {})
        
        if isinstance(params, dict):
            # Expose param keys at top level without removing nested structure
            for key, value in params.items():
                if key not in normalized:
                    normalized[key] = value
        
        return normalized
    
    def _create_single_strategy(self, config: Dict[str, Any]) -> Strategy:
        """Create a single strategy instance.
        
        Args:
            config: Normalized strategy configuration
            
        Returns:
            Strategy instance
            
        Raises:
            ValueError: If strategy type is unknown
        """
        strategy_type = config['type'].lower()
        
        if strategy_type not in self.registry:
            available = ', '.join(self.registry.keys())
            raise ValueError(
                f"Unknown strategy type '{strategy_type}'. "
                f"Available types: {available}"
            )
        
        strategy_class = self.registry[strategy_type]
        
        try:
            strategy = strategy_class(config=config)
            self.logger.info(f"Created {strategy_type} strategy: {strategy.name}")
            return strategy
        except Exception as e:
            self.logger.error(f"Failed to create {strategy_type} strategy: {e}")
            raise ValueError(f"Strategy creation failed: {e}") from e
    
    def _create_dynamic_strategy(self, config: Dict[str, Any]) -> StrategySelector:
        """Create dynamic strategy selector.
        
        Args:
            config: Dynamic strategy configuration
            
        Returns:
            StrategySelector instance
            
        Raises:
            ValueError: If configuration is invalid
        """
        dynamic_config = config.get('dynamic_selection', {})
        strategies_config = config.get('strategies', [])
        
        # Extract symbol from parent config to propagate to sub-strategies
        parent_symbol = config.get('params', {}).get('symbol')
        parent_timeframe = config.get('timeframe')
        
        if not strategies_config:
            raise ValueError("Dynamic mode requires at least one strategy in 'strategies' list")
        
        if not isinstance(strategies_config, list):
            raise ValueError("Dynamic 'strategies' must be a list of strategy configurations")
        
        # Create all sub-strategies
        strategies = []
        for idx, strat_config in enumerate(strategies_config):
            try:
                # Inject parent symbol/timeframe into each sub-strategy
                if parent_symbol:
                    if 'params' not in strat_config:
                        strat_config['params'] = {}
                    if 'symbol' not in strat_config.get('params', {}):
                        strat_config['params']['symbol'] = parent_symbol
                if parent_timeframe and 'timeframe' not in strat_config:
                    strat_config['timeframe'] = parent_timeframe
                
                # Normalize each child strategy
                normalized = self._normalize_config(strat_config)
                strategy = self._create_single_strategy(normalized)
                strategies.append(strategy)
                self.logger.debug(f"Loaded dynamic sub-strategy {idx + 1}: {strategy.name}")
            except Exception as e:
                self.logger.warning(f"Failed to load dynamic sub-strategy {idx + 1}: {e}")
                # Continue with other strategies rather than failing completely
        
        if not strategies:
            raise ValueError("Failed to create any strategies for dynamic mode")
        
        selector = StrategySelector(strategies=strategies, config=dynamic_config)
        self.logger.info(f"Created dynamic strategy selector with {len(strategies)} strategies")
        # Wrap the selector in an adapter so it is compatible with BacktestEngine (implements Strategy interface)
        adapter = StrategySelectorAdapter(selector, name=selector.__class__.__name__)
        # Expose the underlying selector for code that needs it
        adapter.selector = selector
        return adapter
    
    def register_strategy(self, name: str, strategy_class):
        """Register a custom strategy type.
        
        Args:
            name: Strategy type name (will be lowercased)
            strategy_class: Strategy class (must inherit from Strategy base class)
        """
        name_lower = name.lower()
        self.registry[name_lower] = strategy_class
        self.logger.info(f"Registered custom strategy type: {name_lower}")


def load_strategy(strategy_config: Dict[str, Any]) -> Strategy:
    """Convenience function for loading a strategy.
    
    Args:
        strategy_config: Strategy configuration
        
    Returns:
        Strategy instance
    """
    factory = StrategyFactory()
    return factory.create(strategy_config)




