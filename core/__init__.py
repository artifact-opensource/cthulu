"""
Cthulu Core Module

Contains the refactored core components of Cthulu:
- bootstrap: System initialization
- trading_loop: Main trading logic ✅
- indicator_loader: Indicator management  
- strategy_factory: Strategy creation
- exit_loader: Exit strategy loading
- shutdown: Graceful shutdown ✅
- ml_enhancement: Automatic ML integration ✅
"""

from .indicator_loader import IndicatorLoader, IndicatorRequirementResolver
from .strategy_factory import StrategyFactory
from .bootstrap import CthuluBootstrap, SystemComponents
from .exit_loader import ExitStrategyLoader
from .trading_loop import TradingLoop, TradingLoopContext, ensure_runtime_indicators
from .shutdown import ShutdownHandler, create_shutdown_handler
from .ml_enhancement import (
    MLEnhancementManager, 
    MLEnhancementConfig,
    MLEnhancementState,
    get_ml_enhancement_manager,
    initialize_ml_enhancements
)

__all__ = [
    'IndicatorLoader',
    'IndicatorRequirementResolver',
    'StrategyFactory',
    'CthuluBootstrap',
    'SystemComponents',
    'ExitStrategyLoader',
    'TradingLoop',
    'TradingLoopContext',
    'ensure_runtime_indicators',
    'ShutdownHandler',
    'create_shutdown_handler',
    # ML Enhancement
    'MLEnhancementManager',
    'MLEnhancementConfig',
    'MLEnhancementState',
    'get_ml_enhancement_manager',
    'initialize_ml_enhancements',
]




