"""
Indicator Loader Module

Handles loading, validation, and runtime management of technical indicators.
Replaces the scattered indicator logic from __main__.py with a clean, testable interface.
"""

import logging
import inspect
import pandas as pd
from typing import Dict, Any, List, Set, Optional

from cthulu.indicators.rsi import RSI
from cthulu.indicators.macd import MACD
from cthulu.indicators.bollinger import BollingerBands
from cthulu.indicators.stochastic import Stochastic
from cthulu.indicators.adx import ADX
from cthulu.indicators.supertrend import Supertrend
from cthulu.indicators.vwap import VWAP, AnchoredVWAP
from cthulu.indicators.atr import calculate_atr


# Indicator registry mapping type names to classes
INDICATOR_REGISTRY = {
    'rsi': RSI,
    'macd': MACD,
    'bollinger': BollingerBands,
    'stochastic': Stochastic,
    'adx': ADX,
    'supertrend': Supertrend,
    'vwap': VWAP,
    'anchored_vwap': AnchoredVWAP
}

# Legacy parameter name mappings for backward compatibility
LEGACY_PARAM_MAP = {
    'smooth': 'smooth_k',
    'smoothK': 'smooth_k',
    'overbought': 'overbought',
    'oversold': 'oversold'
}


class IndicatorLoader:
    """Loads and configures indicators from configuration."""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize indicator loader.
        
        Args:
            logger: Logger instance for diagnostic output
        """
        self.logger = logger or logging.getLogger(__name__)
        self.registry = INDICATOR_REGISTRY.copy()
    
    def load_indicators(self, indicator_configs: Dict[str, Any]) -> List:
        """Load and configure indicators from configuration.
        
        Args:
            indicator_configs: Dictionary or list of indicator configurations
            
        Returns:
            List of configured indicator instances
            
        Raises:
            ValueError: If indicator configuration is invalid
        """
        indicators = []
        
        # Handle both list and dict formats
        if isinstance(indicator_configs, list):
            # List format: [{"type": "rsi", "params": {...}}, ...]
            for indicator_config in indicator_configs:
                indicator = self._create_indicator_from_config(indicator_config)
                if indicator:
                    indicators.append(indicator)
        else:
            # Dict format: {"rsi": {...}, "macd": {...}}
            for indicator_type, params in indicator_configs.items():
                indicator = self._create_indicator(indicator_type, params)
                if indicator:
                    indicators.append(indicator)
        
        self.logger.info(f"Loaded {len(indicators)} indicators: {[ind.name for ind in indicators]}")
        return indicators
    
    def _create_indicator_from_config(self, config: Dict[str, Any]):
        """Create indicator from config dict with type and params."""
        indicator_type = config.get('type', '').lower()
        params = config.get('params', {})
        return self._create_indicator(indicator_type, params)
    
    def _create_indicator(self, indicator_type: str, params: Dict[str, Any]):
        """Create a single indicator instance.
        
        Args:
            indicator_type: Type of indicator (e.g., 'rsi', 'macd')
            params: Parameters for indicator initialization
            
        Returns:
            Indicator instance or None if type not found
        """
        indicator_type_lower = indicator_type.lower()
        
        if indicator_type_lower not in self.registry:
            self.logger.warning(f"Unknown indicator type: {indicator_type}")
            return None
        
        indicator_class = self.registry[indicator_type_lower]
        prepared_params = self._prepare_params(indicator_class, params)
        
        try:
            indicator = indicator_class(**prepared_params)
            self.logger.debug(f"Created indicator: {indicator.name} with params {prepared_params}")
            return indicator
        except Exception as e:
            self.logger.error(f"Failed to create {indicator_type} indicator: {e}")
            return None
    
    def _prepare_params(self, indicator_class, params: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare parameters for indicator initialization.
        
        Handles:
        - Legacy parameter name mapping
        - Parameter filtering based on constructor signature
        - Type validation
        
        Args:
            indicator_class: Indicator class to create
            params: Raw parameters from configuration
            
        Returns:
            Filtered and validated parameters
        """
        # Copy to avoid mutation
        params_copy = dict(params or {})
        
        # Apply legacy mappings
        for old_name, new_name in LEGACY_PARAM_MAP.items():
            if old_name in params_copy and new_name not in params_copy:
                params_copy[new_name] = params_copy.pop(old_name)
        
        # Filter params based on constructor signature
        try:
            sig = inspect.signature(indicator_class.__init__)
            valid_params = {
                p.name for p in sig.parameters.values()
                if p.name != 'self' and p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
            }
            filtered = {k: v for k, v in params_copy.items() if k in valid_params}
            return filtered
        except Exception as e:
            self.logger.warning(f"Could not inspect {indicator_class.__name__} signature: {e}")
            return params_copy


class IndicatorRequirementResolver:
    """Determines which indicators a strategy requires at runtime."""
    
    def __init__(self, strategy, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """Initialize requirement resolver.
        
        Args:
            strategy: Trading strategy instance
            config: Full system configuration
            logger: Logger instance
        """
        self.strategy = strategy
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        
        # Requirements tracking
        self.required_emas: Set[int] = set()
        self.required_rsi_periods: Set[int] = set()
        self.needs_atr = False
        self.needs_adx = False
        self.needs_macd = False
        self.needs_bollinger = False
        self.needs_stochastic = False
        self.needs_supertrend = False
        self.needs_vwap = False
    
    def analyze(self) -> Dict[str, Any]:
        """Analyze strategy to determine indicator requirements.
        
        Returns:
            Dictionary of requirements
        """
        self._analyze_strategy_attributes()
        self._analyze_config_indicators()
        self._analyze_dynamic_strategies()
        
        return {
            'emas': sorted(self.required_emas),
            'rsi_periods': sorted(self.required_rsi_periods),
            'atr': self.needs_atr,
            'adx': self.needs_adx,
            'macd': self.needs_macd,
            'bollinger': self.needs_bollinger,
            'stochastic': self.needs_stochastic,
            'supertrend': self.needs_supertrend,
            'vwap': self.needs_vwap
        }
    
    def _analyze_strategy_attributes(self):
        """Extract requirements from strategy attributes."""
        try:
            # Check for EMA periods
            for attr in ('fast_period', 'slow_period', 'fast_ema', 'slow_ema', 'short_window', 'long_window'):
                if hasattr(self.strategy, attr):
                    try:
                        val = int(getattr(self.strategy, attr))
                        if 'ema' in attr or 'fast' in attr or 'slow' in attr:
                            self.required_emas.add(val)
                    except (ValueError, TypeError):
                        pass
            
            # Check for RSI period
            if hasattr(self.strategy, 'rsi_period'):
                try:
                    self.required_rsi_periods.add(int(getattr(self.strategy, 'rsi_period')))
                except (ValueError, TypeError):
                    pass
            
            # Check for ATR
            if hasattr(self.strategy, 'atr_period') or hasattr(self.strategy, 'atr_multiplier'):
                self.needs_atr = True
            
            # Check strategy name for scalping (needs ATR)
            if getattr(self.strategy, 'name', '').lower() == 'scalping':
                self.needs_atr = True
                # Scalping defaults
                self.required_emas.update({
                    getattr(self.strategy, 'fast_ema', 5),
                    getattr(self.strategy, 'slow_ema', 10)
                })
                self.required_rsi_periods.add(getattr(self.strategy, 'rsi_period', 7))
        
        except Exception as e:
            self.logger.debug(f"Error analyzing strategy attributes: {e}")
    
    def _analyze_config_indicators(self):
        """Extract requirements from configuration."""
        try:
            indicator_configs = self.config.get('indicators', [])
            
            if isinstance(indicator_configs, list):
                for ind_cfg in indicator_configs:
                    ind_type = ind_cfg.get('type', '').lower()
                    self._mark_indicator_needed(ind_type)
            else:
                for ind_type in indicator_configs.keys():
                    self._mark_indicator_needed(ind_type.lower())
        
        except Exception as e:
            self.logger.debug(f"Error analyzing config indicators: {e}")
    
    def _analyze_dynamic_strategies(self):
        """Extract requirements from dynamic strategy selector."""
        try:
            # Check if using StrategySelector (or StrategySelectorAdapter wrapping one)
            from cthulu.strategy.strategy_selector import StrategySelector
            from cthulu.strategy.selector_adapter import StrategySelectorAdapter
            
            strategy_to_check = self.strategy
            if isinstance(strategy_to_check, StrategySelectorAdapter):
                strategy_to_check = getattr(strategy_to_check, 'selector', strategy_to_check)
            
            if isinstance(strategy_to_check, StrategySelector):
                # ADX needed for regime detection
                self.needs_adx = True
                
                # Analyze each sub-strategy
                for sub_strategy in strategy_to_check.strategies.values():
                    self._extract_from_strategy(sub_strategy)
        
        except Exception as e:
            self.logger.debug(f"Error analyzing dynamic strategies: {e}")
        
        # Also check config-level strategy definitions
        try:
            strat_cfg = self.config.get('strategy', {})
            if strat_cfg.get('type') == 'dynamic':
                for s in strat_cfg.get('strategies', []):
                    self._extract_from_config(s)
        except Exception as e:
            self.logger.debug(f"Error analyzing config strategies: {e}")
    
    def _extract_from_strategy(self, strategy):
        """Extract requirements from a strategy instance."""
        # EMA periods
        for attr in ('fast_ema', 'slow_ema', 'fast_period', 'slow_period'):
            if hasattr(strategy, attr):
                try:
                    val = int(getattr(strategy, attr))
                    self.required_emas.add(val)
                except (ValueError, TypeError):
                    pass
        
        # RSI period
        if hasattr(strategy, 'rsi_period'):
            try:
                self.required_rsi_periods.add(int(getattr(strategy, 'rsi_period')))
            except (ValueError, TypeError):
                pass
        
        # ATR for scalping
        if getattr(strategy, 'name', '').lower() == 'scalping':
            self.needs_atr = True
    
    def _extract_from_config(self, strategy_config: Dict[str, Any]):
        """Extract requirements from strategy configuration."""
        params = strategy_config.get('params', {}) or {}
        
        # EMA periods
        for key in ('fast_ema', 'slow_ema', 'fast_period', 'slow_period'):
            if key in params:
                try:
                    self.required_emas.add(int(params[key]))
                except (ValueError, TypeError):
                    pass
        
        # RSI period
        if 'rsi_period' in params:
            try:
                self.required_rsi_periods.add(int(params['rsi_period']))
            except (ValueError, TypeError):
                pass
        
        # ATR
        if 'atr_period' in params or 'atr_multiplier' in params:
            self.needs_atr = True
        
        # Scalping needs ATR
        if strategy_config.get('type', '').lower() == 'scalping':
            self.needs_atr = True
    
    def _mark_indicator_needed(self, indicator_type: str):
        """Mark an indicator as needed based on its type."""
        if indicator_type == 'atr':
            self.needs_atr = True
        elif indicator_type == 'adx':
            self.needs_adx = True
        elif indicator_type == 'macd':
            self.needs_macd = True
        elif indicator_type == 'bollinger':
            self.needs_bollinger = True
        elif indicator_type == 'stochastic':
            self.needs_stochastic = True
        elif indicator_type == 'supertrend':
            self.needs_supertrend = True
        elif indicator_type == 'vwap' or indicator_type == 'anchored_vwap':
            self.needs_vwap = True
    
    def ensure_indicators(self, df: pd.DataFrame, existing_indicators: List) -> List:
        """Ensure required indicators exist, creating missing ones.
        
        Args:
            df: DataFrame with OHLCV data
            existing_indicators: List of already instantiated indicators
            
        Returns:
            List of newly created indicators (to be added to existing list)
        """
        requirements = self.analyze()
        new_indicators = []
        
        # Get existing indicator types
        existing_types = {ind.__class__.__name__.lower() for ind in existing_indicators}
        
        # Compute EMA columns directly in dataframe
        for period in requirements['emas']:
            col = f'ema_{period}'
            if col not in df.columns:
                df[col] = df['close'].ewm(span=period, adjust=False).mean()
                self.logger.debug(f"Computed {col}")
        
        # Ensure RSI indicators
        for period in requirements['rsi_periods']:
            if not self._has_rsi(existing_indicators, period):
                ind = RSI(period=period)
                new_indicators.append(ind)
                self.logger.info(f"Added runtime RSI(period={period})")
        
        # Ensure ATR
        if requirements['atr'] and 'atr' not in df.columns:
            try:
                # Get period from strategy or use default
                period = getattr(self.strategy, 'atr_period', 14)
                df['atr'] = calculate_atr(df, period=int(period))
                self.logger.info(f"Computed runtime ATR(period={period})")
            except Exception as e:
                self.logger.error(f"Failed to compute ATR: {e}")
        
        # Ensure ADX
        if requirements['adx'] and 'adx' not in df.columns and 'adx' not in existing_types:
            ind = ADX(period=14)
            new_indicators.append(ind)
            self.logger.info("Added runtime ADX")
        
        # Ensure other indicators if explicitly configured
        if requirements['macd'] and 'macd' not in df.columns and 'macd' not in existing_types:
            ind = MACD(fast_period=12, slow_period=26, signal_period=9)
            new_indicators.append(ind)
            self.logger.info("Added runtime MACD")
        
        if requirements['bollinger'] and 'bb_upper' not in df.columns and 'bollingerbands' not in existing_types:
            ind = BollingerBands(period=20, std_dev=2.0)
            new_indicators.append(ind)
            self.logger.info("Added runtime Bollinger Bands")
        
        if requirements['stochastic'] and 'stoch_k' not in df.columns and 'stochastic' not in existing_types:
            ind = Stochastic(k_period=14, d_period=3, smooth_k=3)
            new_indicators.append(ind)
            self.logger.info("Added runtime Stochastic")
        
        if requirements['supertrend'] and 'supertrend' not in df.columns and 'supertrend' not in existing_types:
            ind = Supertrend(period=10, multiplier=3.0)
            new_indicators.append(ind)
            self.logger.info("Added runtime Supertrend")
        
        if requirements['vwap'] and 'vwap' not in df.columns and 'vwap' not in existing_types:
            ind = VWAP()
            new_indicators.append(ind)
            self.logger.info("Added runtime VWAP")
        
        return new_indicators
    
    def _has_rsi(self, indicators: List, period: int) -> bool:
        """Check if RSI with specific period exists in indicator list."""
        for ind in indicators:
            if isinstance(ind, RSI) and getattr(ind, 'period', 14) == period:
                return True
        return False


def load_indicators(indicator_configs: Dict[str, Any]) -> List:
    """Convenience function for loading indicators.
    
    Args:
        indicator_configs: Indicator configuration
        
    Returns:
        List of indicator instances
    """
    loader = IndicatorLoader()
    return loader.load_indicators(indicator_configs)




