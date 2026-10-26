"""
Exit Strategy Module

Exit strategy implementations for position management.

Includes context-aware exit coordination for intelligent exit decision-making.

**New in v6.0.0:**
- AdaptiveLossCurve: Non-linear loss tolerance (hyperbolic/softmax)
- ConfluenceExitManager: Multi-indicator confluence-based exits
"""

from .base import ExitStrategy, ExitSignal
from .trailing_stop import TrailingStop, TrailingStopExit
from .time_based import TimeBasedExit
from .profit_target import ProfitTargetExit
from .adverse_movement import AdverseMovementExit
from .stop_loss import StopLossExit
from .take_profit import TakeProfitExit
from .exit_manager import ExitDecision, ExitStrategyManager
from .coordinator import ExitCoordinator, MarketContext, PositionContext, create_exit_coordinator
from .micro_account_protection import MicroAccountProtection, SurvivalModeExit
from .profit_scaling import ProfitScalingExit, AggressiveScalingExit, ProfitScaling, AggressiveScaling
from .adaptive_loss_curve import (
    AdaptiveLossCurve, 
    AdaptiveLossExitStrategy, 
    LossCurveConfig,
    create_adaptive_loss_curve
)
from .confluence_exit_manager import (
    ConfluenceExitManager,
    ConfluenceExitStrategy,
    ConfluenceSignal,
    ExitRecommendation,
    ExitClassification,
    TrackedPosition,
    create_confluence_exit_manager
)

__all__ = [
    "ExitStrategy",
    "ExitSignal",
    "TrailingStop",
    "TimeBasedExit",
    "ProfitTargetExit",
    "AdverseMovementExit",
    "StopLossExit",
    "TakeProfitExit",
    "ExitDecision",
    "ExitStrategyManager",
    "ExitCoordinator",
    "MarketContext",
    "PositionContext",
    "create_exit_coordinator",
    "MicroAccountProtection",
    "SurvivalModeExit",
    "ProfitScalingExit",
    "AggressiveScalingExit",
    "ProfitScaling",
    "AggressiveScaling",
    # v6.0.0 additions
    "AdaptiveLossCurve",
    "AdaptiveLossExitStrategy",
    "LossCurveConfig",
    "create_adaptive_loss_curve",
    "ConfluenceExitManager",
    "ConfluenceExitStrategy",
    "ConfluenceSignal",
    "ExitRecommendation",
    "ExitClassification",
    "TrackedPosition",
    "create_confluence_exit_manager",
]




