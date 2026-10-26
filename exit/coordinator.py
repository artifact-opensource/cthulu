"""
Exit Strategy Coordinator

Context-aware exit management system that orchestrates multiple exit strategies
with dynamic priority adjustment based on market conditions and position state.

This module provides intelligent exit decision-making with:
- Priority-based strategy evaluation
- Context-aware priority adjustment
- Market condition adaptation
- Comprehensive logging and metrics
- Testable architecture
"""

import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime

from .base import ExitStrategy
from .exit_manager import ExitDecision
from .stop_loss import StopLoss
from .take_profit import TakeProfit
from .trailing_stop import TrailingStop
from .time_based import TimeBasedExit
from .profit_target import ProfitTargetExit
from .adverse_movement import AdverseMovementExit


logger = logging.getLogger(__name__)


@dataclass
class MarketContext:
    """Market condition context for priority adjustment."""
    volatility: float = 0.0  # Current volatility measure
    spread: float = 0.0  # Current spread in pips
    trend_strength: float = 0.0  # Trend strength (-1 to 1)
    session: str = "unknown"  # Trading session (asian/european/american)
    is_news_event: bool = False  # High-impact news active
    is_market_close: bool = False  # Near market close


@dataclass
class PositionContext:
    """Position state context for priority adjustment."""
    unrealized_pnl: float = 0.0  # Current P&L
    unrealized_pnl_percent: float = 0.0  # P&L as percentage
    holding_time_minutes: int = 0  # How long position held
    max_favorable_excursion: float = 0.0  # Max profit achieved
    max_adverse_excursion: float = 0.0  # Max drawdown experienced
    is_in_profit: bool = False  # Currently profitable
    is_in_loss: bool = False  # Currently losing


class ExitCoordinator:
    """
    Context-aware exit strategy coordinator.
    
    Orchestrates multiple exit strategies with intelligent priority adjustment
    based on market conditions and position state. Provides comprehensive
    exit decision-making with logging and metrics.
    
    **Priority Semantics** (0-100 scale):
    - 76-100: Critical (stop loss, adverse movement)
    - 51-75: High (session close, profit protection)
    - 26-50: Medium (profit targets, time-based)
    - 0-25: Low (trailing stops)
    
    **Priority Adjustments:**
    - High volatility → Increase stop loss priority
    - Wide spreads → Decrease exit urgency
    - News events → Increase all exit priorities
    - Near profit target → Increase take profit priority
    - Long holding time → Increase time-based exit priority
    
    Example:
        coordinator = ExitCoordinator()
        coordinator.register_strategy(StopLoss(distance_pips=20))
        coordinator.register_strategy(TakeProfit(target_pips=40))
        
        decision = coordinator.evaluate_exit(
            position=position_info,
            market_ctx=market_context,
            position_ctx=position_context,
            current_data={"close": 1.1000}
        )
        
        if decision and decision.should_exit:
            execute_exit(decision)
    """
    
    def __init__(self):
        """Initialize exit coordinator."""
        self.strategies: List[ExitStrategy] = []
        self.base_priorities: Dict[str, int] = {}
        self._evaluation_count = 0
        self._exit_triggered_count = 0
        
    def register_strategy(self, strategy: ExitStrategy):
        """
        Register an exit strategy with the coordinator.
        
        Args:
            strategy: ExitStrategy instance to register
            
        The strategy is added to the evaluation list and sorted by priority.
        """
        self.strategies.append(strategy)
        # Store base priority for later adjustment
        self.base_priorities[strategy.__class__.__name__] = getattr(strategy, 'priority', 50)
        # Sort strategies by priority (highest first)
        self.strategies.sort(key=lambda s: getattr(s, 'priority', 50), reverse=True)
        logger.info(f"Registered exit strategy: {strategy.__class__.__name__} "
                   f"(priority: {getattr(strategy, 'priority', 50)})")
    
    def evaluate_exit(
        self,
        position: Any,
        market_ctx: Optional[MarketContext] = None,
        position_ctx: Optional[PositionContext] = None,
        current_data: Optional[Dict[str, Any]] = None
    ) -> Optional[ExitDecision]:
        """
        Evaluate all registered exit strategies and return best decision.
        
        Args:
            position: Position information (PositionInfo or compatible)
            market_ctx: Market condition context for priority adjustment
            position_ctx: Position state context for priority adjustment
            current_data: Current market data dictionary
            
        Returns:
            ExitDecision if any strategy triggers exit, None otherwise
            
        The coordinator evaluates strategies in priority order (after adjustment)
        and returns the highest-priority exit decision. Context information
        is used to dynamically adjust strategy priorities.
        """
        self._evaluation_count += 1
        current_data = current_data or {}
        market_ctx = market_ctx or MarketContext()
        position_ctx = position_ctx or PositionContext()
        
        # Adjust priorities based on context
        adjusted_strategies = self._adjust_priorities(
            self.strategies.copy(),
            market_ctx,
            position_ctx
        )
        
        # Evaluate strategies in adjusted priority order
        best_decision = None
        best_priority = -1
        
        for strategy in adjusted_strategies:
            try:
                result = strategy.should_exit(position, current_data)
                
                if result and isinstance(result, ExitDecision) and result.should_exit:
                    # Track the highest priority exit decision
                    if result.priority > best_priority:
                        best_decision = result
                        best_priority = result.priority
                        logger.debug(f"Exit signal from {strategy.__class__.__name__}: "
                                   f"{result.reason} (priority: {result.priority})")
                        
            except Exception as e:
                logger.error(f"Error evaluating exit strategy {strategy.__class__.__name__}: {e}",
                           exc_info=True)
                # Continue with other strategies
                
        if best_decision:
            self._exit_triggered_count += 1
            logger.info(f"Exit decision: {best_decision.strategy_name} - "
                       f"{best_decision.reason} (priority: {best_decision.priority})")
                       
        return best_decision
    
    def _adjust_priorities(
        self,
        strategies: List[ExitStrategy],
        market_ctx: MarketContext,
        position_ctx: PositionContext
    ) -> List[ExitStrategy]:
        """
        Adjust strategy priorities based on market and position context.
        
        Args:
            strategies: List of strategies to adjust
            market_ctx: Market condition context
            position_ctx: Position state context
            
        Returns:
            Strategies sorted by adjusted priority (highest first)
            
        **Adjustment Rules:**
        
        1. **High Volatility** (volatility > 2.0):
           - StopLoss +10 priority
           - AdverseMovement +10 priority
           
        2. **Wide Spreads** (spread > 3 pips):
           - All exit priorities -5
           
        3. **News Events**:
           - All exit priorities +15
           
        4. **Market Close Approaching**:
           - TimeBasedExit +20 priority
           
        5. **Near Profit Target** (P&L > 80% of max favorable):
           - ProfitTargetExit +15 priority
           - TakeProfit +15 priority
           
        6. **Long Holding Time** (> 240 minutes):
           - TimeBasedExit +10 priority
           
        7. **Deep Loss** (P&L < -2%):
           - StopLoss +20 priority
        """
        for strategy in strategies:
            base_priority = self.base_priorities.get(strategy.__class__.__name__, 50)
            adjusted_priority = base_priority
            adjustments = []
            
            # High volatility → Increase stop loss urgency
            if market_ctx.volatility > 2.0:
                if isinstance(strategy, (StopLoss, AdverseMovementExit)):
                    adjusted_priority += 10
                    adjustments.append("high_volatility+10")
                    
            # Wide spreads → Decrease exit urgency (costly)
            if market_ctx.spread > 3.0:
                adjusted_priority -= 5
                adjustments.append("wide_spread-5")
                
            # News events → Increase all exit priorities
            if market_ctx.is_news_event:
                adjusted_priority += 15
                adjustments.append("news_event+15")
                
            # Market close approaching → Increase time-based exit
            if market_ctx.is_market_close and isinstance(strategy, TimeBasedExit):
                adjusted_priority += 20
                adjustments.append("market_close+20")
                
            # Near profit target → Increase profit-taking priority
            if (position_ctx.max_favorable_excursion > 0 and 
                position_ctx.unrealized_pnl > 0.8 * position_ctx.max_favorable_excursion):
                if isinstance(strategy, (ProfitTargetExit, TakeProfit)):
                    adjusted_priority += 15
                    adjustments.append("near_target+15")
                    
            # Long holding time → Increase time-based exit
            if position_ctx.holding_time_minutes > 240:
                if isinstance(strategy, TimeBasedExit):
                    adjusted_priority += 10
                    adjustments.append("long_hold+10")
                    
            # Deep loss → Increase stop loss priority
            if position_ctx.unrealized_pnl_percent < -2.0:
                if isinstance(strategy, StopLoss):
                    adjusted_priority += 20
                    adjustments.append("deep_loss+20")
                    
            # Apply adjusted priority
            strategy.priority = max(0, min(100, adjusted_priority))
            
            if adjustments:
                logger.debug(f"Priority adjustment for {strategy.__class__.__name__}: "
                           f"{base_priority} → {strategy.priority} "
                           f"({', '.join(adjustments)})")
                           
        # Re-sort by adjusted priority
        strategies.sort(key=lambda s: s.priority, reverse=True)
        return strategies
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get coordinator statistics.
        
        Returns:
            Dictionary with coordinator metrics
        """
        return {
            "evaluations": self._evaluation_count,
            "exits_triggered": self._exit_triggered_count,
            "registered_strategies": len(self.strategies),
            "strategy_names": [s.__class__.__name__ for s in self.strategies]
        }
    
    def reset_statistics(self):
        """Reset evaluation statistics."""
        self._evaluation_count = 0
        self._exit_triggered_count = 0
        logger.info("Exit coordinator statistics reset")
    
    def __repr__(self) -> str:
        """String representation of coordinator."""
        return (f"ExitCoordinator("
               f"strategies={len(self.strategies)}, "
               f"evaluations={self._evaluation_count}, "
               f"exits={self._exit_triggered_count})")


def create_exit_coordinator(exit_config: Dict[str, Any]) -> ExitCoordinator:
    """
    Factory function to create and configure an exit coordinator.
    
    Args:
        exit_config: Configuration dictionary with exit strategy settings
        
    Returns:
        Configured ExitCoordinator instance
        
    Example config:
        {
            "strategies": [
                {"type": "stop_loss", "distance_pips": 20},
                {"type": "take_profit", "target_pips": 40},
                {"type": "trailing_stop", "activation_pips": 15, "distance_pips": 10},
                {"type": "time_based", "max_duration_minutes": 480}
            ]
        }
    """
    coordinator = ExitCoordinator()
    
    strategy_map = {
        "stop_loss": StopLoss,
        "take_profit": TakeProfit,
        "trailing_stop": TrailingStop,
        "time_based": TimeBasedExit,
        "profit_target": ProfitTargetExit,
        "adverse_movement": AdverseMovementExit
    }
    
    strategies_config = exit_config.get("strategies", [])
    
    for strategy_cfg in strategies_config:
        strategy_type = strategy_cfg.get("type")
        strategy_cls = strategy_map.get(strategy_type)
        
        if not strategy_cls:
            logger.warning(f"Unknown exit strategy type: {strategy_type}")
            continue
            
        try:
            # Extract params (everything except 'type')
            params = {k: v for k, v in strategy_cfg.items() if k != "type"}
            strategy = strategy_cls(**params)
            coordinator.register_strategy(strategy)
        except Exception as e:
            logger.error(f"Failed to create exit strategy {strategy_type}: {e}")
            
    logger.info(f"Created exit coordinator with {len(coordinator.strategies)} strategies")
    return coordinator




