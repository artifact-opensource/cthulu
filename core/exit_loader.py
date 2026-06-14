"""
Exit Strategy Loader Module

Handles loading and configuration of exit strategies.
Extracted from __main__.py for better modularity.
"""

import logging
from typing import Dict, Any, List, Optional

from cthulu.exit.trailing_stop import TrailingStop
from cthulu.exit.time_based import TimeBasedExit
from cthulu.exit.profit_target import ProfitTargetExit
from cthulu.exit.adverse_movement import AdverseMovementExit
from cthulu.exit.micro_account_protection import MicroAccountProtection, SurvivalModeExit
from cthulu.exit.profit_scaling import ProfitScalingExit, AggressiveScalingExit


# Exit strategy registry mapping type names to classes
EXIT_STRATEGY_REGISTRY = {
    'trailing_stop': TrailingStop,
    'time_based': TimeBasedExit,
    'profit_target': ProfitTargetExit,
    'adverse_movement': AdverseMovementExit,
    'micro_account_protection': MicroAccountProtection,
    'survival_mode': SurvivalModeExit,
    'profit_scaling': ProfitScalingExit,
    'aggressive_scaling': AggressiveScalingExit,
}


class ExitStrategyLoader:
    """Loads and configures exit strategies from configuration."""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize exit strategy loader.
        
        Args:
            logger: Logger instance for diagnostic output
        """
        self.logger = logger or logging.getLogger(__name__)
        self.registry = EXIT_STRATEGY_REGISTRY.copy()
    
    def load_exit_strategies(self, exit_configs: Dict[str, Any]) -> List:
        """Load and configure exit strategies.
        
        Args:
            exit_configs: Dictionary or list of exit strategy configurations
            
        Returns:
            List of configured exit strategy instances, sorted by priority (highest first)
        """
        exit_strategies = []
        
        # Handle both list and dict formats
        if isinstance(exit_configs, list):
            # List format: [{"type": "trailing_stop", "enabled": true, ...}, ...]
            for exit_config in exit_configs:
                exit_strategy = self._create_exit_strategy_from_config(exit_config)
                if exit_strategy:
                    exit_strategies.append(exit_strategy)
        else:
            # Dict format: {"trailing_stop": {...}, "time_based": {...}}
            for exit_type, config in exit_configs.items():
                exit_strategy = self._create_exit_strategy(exit_type, config)
                if exit_strategy:
                    exit_strategies.append(exit_strategy)
        
        # Sort by priority (highest first)
        exit_strategies.sort(key=lambda x: x.priority, reverse=True)
        
        self.logger.info(
            f"Loaded {len(exit_strategies)} exit strategies: "
            f"{[f'{s.name}(priority={s.priority})' for s in exit_strategies]}"
        )
        
        return exit_strategies
    
    def _create_exit_strategy_from_config(self, config: Dict[str, Any]):
        """Create exit strategy from config dict with type and enabled flag."""
        exit_type = config.get('type', '').lower()
        enabled = config.get('enabled', True)
        
        if not enabled:
            self.logger.debug(f"Exit strategy '{exit_type}' disabled in configuration")
            return None
        
        return self._create_exit_strategy(exit_type, config)
    
    def _create_exit_strategy(self, exit_type: str, config: Dict[str, Any]):
        """Create a single exit strategy instance.
        
        Args:
            exit_type: Type of exit strategy (e.g., 'trailing_stop', 'time_based')
            config: Configuration for the exit strategy
            
        Returns:
            Exit strategy instance or None if type not found or disabled
        """
        exit_type_lower = exit_type.lower()
        enabled = config.get('enabled', True)
        
        if not enabled:
            self.logger.debug(f"Exit strategy '{exit_type}' disabled in configuration")
            return None
        
        if exit_type_lower not in self.registry:
            self.logger.warning(f"Unknown exit strategy type: {exit_type}")
            return None
        
        exit_class = self.registry[exit_type_lower]
        
        try:
            exit_strategy = exit_class(config)
            self.logger.debug(
                f"Created exit strategy: {exit_strategy.name} "
                f"(priority={exit_strategy.priority})"
            )
            return exit_strategy
        except Exception as e:
            self.logger.error(f"Failed to create {exit_type} exit strategy: {e}")
            return None
    
    def register_exit_strategy(self, name: str, exit_class):
        """Register a custom exit strategy type.
        
        Args:
            name: Exit strategy type name (will be lowercased)
            exit_class: Exit strategy class
        """
        name_lower = name.lower()
        self.registry[name_lower] = exit_class
        self.logger.info(f"Registered custom exit strategy type: {name_lower}")


def load_exit_strategies(exit_configs: Dict[str, Any]) -> List:
    """Convenience function for loading exit strategies.
    
    Args:
        exit_configs: Exit strategy configuration
        
    Returns:
        List of exit strategy instances, sorted by priority
    """
    loader = ExitStrategyLoader()
    return loader.load_exit_strategies(exit_configs)




