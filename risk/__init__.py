"""Risk management module - Unified Architecture

Single source of truth for all risk evaluation logic.

Components:
- evaluator.py: Unified risk evaluation (consolidates all previous risk logic)
- adaptive_drawdown.py: Dynamic drawdown state management
- adaptive_account_manager.py: Phase-based account & timeframe management
- liquidity_trap_detector.py: Market trap detection heuristics
- equity_curve_manager.py: Equity curve tracking and protection

Legacy modules (deprecated, will be removed):
- manager.py: Replaced by evaluator.py
- position/risk_manager.py: Merged into evaluator.py
"""

from .evaluator import RiskEvaluator, RiskLimits, DailyRiskTracker

# Adaptive systems
try:
    from .adaptive_drawdown import AdaptiveDrawdownManager, create_adaptive_manager
except ImportError:
    AdaptiveDrawdownManager = None
    create_adaptive_manager = None

try:
    from .adaptive_account_manager import (
        AdaptiveAccountManager,
        AccountPhase,
        TimeframeMode,
        create_adaptive_account_manager,
        AccountPhaseIntegration
    )
except ImportError:
    AdaptiveAccountManager = None
    AccountPhase = None
    TimeframeMode = None
    create_adaptive_account_manager = None
    AccountPhaseIntegration = None

# Legacy import for backward compatibility during transition
try:
    from .manager import RiskManager
except ImportError:
    RiskManager = None

__all__ = [
    "RiskEvaluator", 
    "RiskLimits", 
    "DailyRiskTracker", 
    "RiskManager",
    "AdaptiveDrawdownManager",
    "create_adaptive_manager",
    "AdaptiveAccountManager",
    "AccountPhase",
    "TimeframeMode",
    "create_adaptive_account_manager",
    "AccountPhaseIntegration",
]




