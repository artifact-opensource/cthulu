"""
Profit Target Exit Strategy

Exits positions when reaching profit targets.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from .base import ExitStrategy, ExitSignal
from cthulu.position.manager import PositionInfo


class ProfitTargetExit(ExitStrategy):
    """
    Profit target exit strategy with multiple target levels.
    
    Features:
    - Percentage-based profit targets
    - Pip-based profit targets
    - Multiple target levels with partial closes
    - Risk/reward ratio enforcement
    - Target scaling based on volatility
    
    Configuration parameters:
        target_pct: Profit target as percentage of entry (default: 2.0)
        target_pips: Profit target in pips (alternative to pct)
        partial_close_enabled: Enable partial closes at targets (default: False)
        target_levels: List of (target_pct, close_pct) tuples for scaling out
        risk_reward_ratio: Minimum R:R ratio to set target (default: 2.0)
        scale_with_volatility: Adjust targets based on ATR (default: False)
    """
    
    def __init__(self, params: Dict[str, Any]):
        """
        Initialize profit target exit strategy.
        
        Args:
            params: Strategy parameters (target_pct, target_pips, etc.)
        """
        super().__init__(
            name="ProfitTargetExit",
            params=params,
            priority=40  # Medium priority
        )
        
        # Default parameters
        self.target_pct = params.get('target_pct', 2.0)
        self.target_pips = params.get('target_pips', None)
        self.partial_close_enabled = params.get('partial_close_enabled', False)
        self.risk_reward_ratio = params.get('risk_reward_ratio', 2.0)
        self.scale_with_volatility = params.get('scale_with_volatility', False)
        
        # Multiple target levels: [(target_pct, close_pct)]
        # Example: [(1.0, 0.5), (2.0, 0.5)] = 50% at +1%, remaining 50% at +2%
        self.target_levels = params.get('target_levels', None)
        if self.target_levels and self.partial_close_enabled:
            self.logger.info(f"Partial close enabled with levels: {self.target_levels}")
            
        # Track which targets hit per position
        self._targets_hit: Dict[int, List[int]] = {}
        
    def should_exit(
        self,
        position: PositionInfo,
        current_data: Dict[str, Any]
    ) -> Optional[ExitSignal]:
        """
        Check if profit target reached.
        
        Args:
            position: Position information
            current_data: Market data including 'current_price', optional 'indicators'
            
        Returns:
            ExitSignal if target hit, None otherwise
        """
        if not self._enabled:
            return None
            
        ticket = position.ticket
        current_price = current_data.get('current_price')
        if current_price is None:
            self.logger.warning(f"No current_price for {ticket}")
            return None
            
        # Calculate current profit
        if self.target_pips is not None:
            profit_pips = position.get_pnl_pips()
            profit_metric = profit_pips
            target_metric = self.target_pips
            metric_name = "pips"
        else:
            # Profit percentage based on entry capital
            profit_pct = (position.unrealized_pnl / (position.volume * position.open_price)) * 100
            profit_metric = profit_pct
            target_metric = self.target_pct
            metric_name = "%"
            
        # Adjust target if scaling with volatility
        if self.scale_with_volatility:
            indicators = current_data.get('indicators', {})
            atr = indicators.get('atr', None)
            if atr is not None:
                # Scale target based on ATR (higher volatility = larger target)
                # ATR as percentage of price
                atr_pct = (atr / position.open_price) * 100
                scaling_factor = max(0.5, min(2.0, atr_pct / 1.0))  # Clamp 0.5x to 2.0x
                target_metric = target_metric * scaling_factor
                self.logger.debug(f"{ticket}: ATR-scaled target to {target_metric:.2f}{metric_name}")
                
        # Check for partial close targets
        if self.partial_close_enabled and self.target_levels:
            return self._check_partial_targets(
                position=position,
                profit_metric=profit_metric,
                metric_name=metric_name,
                current_price=current_price
            )
            
        # Single target check
        if profit_metric >= target_metric:
            self.logger.info(
                f"Profit target hit for {ticket}: {profit_metric:.2f}{metric_name} >= "
                f"{target_metric:.2f}{metric_name}"
            )
            return ExitSignal(
                ticket=position.ticket,
                reason=f"Profit target reached ({profit_metric:.2f}{metric_name})",
                price=current_price,
                timestamp=datetime.now(),
                strategy_name=self.name,
                confidence=1.0,
                metadata={
                    'profit_metric': profit_metric,
                    'target_metric': target_metric,
                    'metric_type': metric_name,
                    'profit_amount': position.unrealized_pnl
                }
            )
            
        return None
        
    def _check_partial_targets(
        self,
        position: PositionInfo,
        profit_metric: float,
        metric_name: str,
        current_price: float
    ) -> Optional[ExitSignal]:
        """
        Check multiple target levels for partial closes.
        
        Args:
            position: Position information
            profit_metric: Current profit (pips or %)
            metric_name: Metric type ("pips" or "%")
            current_price: Current market price
            
        Returns:
            ExitSignal with partial_volume if target hit, None otherwise
        """
        ticket = position.ticket
        
        # Initialize tracking for new position
        if ticket not in self._targets_hit:
            self._targets_hit[ticket] = []
            
        # Check each target level
        for i, (target_level, close_pct) in enumerate(self.target_levels):
            # Skip if already hit
            if i in self._targets_hit[ticket]:
                continue
                
            # Check if target reached
            if profit_metric >= target_level:
                # Calculate volume to close
                partial_volume = position.volume * (close_pct / 100.0)
                
                # Mark target as hit
                self._targets_hit[ticket].append(i)
                
                self.logger.info(
                    f"Partial target {i+1} hit for {ticket}: {profit_metric:.2f}{metric_name} >= "
                    f"{target_level:.2f}{metric_name}, closing {close_pct}% ({partial_volume:.2f} lots)"
                )
                
                # Check if this is the last target (close everything)
                is_final_target = (i == len(self.target_levels) - 1)
                
                return ExitSignal(
                    ticket=position.ticket,
                    reason=f"Partial target {i+1}/{len(self.target_levels)} "
                           f"({profit_metric:.2f}{metric_name})",
                    price=current_price,
                    timestamp=datetime.now(),
                    strategy_name=self.name,
                    confidence=1.0,
                    partial_volume=None if is_final_target else partial_volume,
                    metadata={
                        'target_level': i + 1,
                        'total_targets': len(self.target_levels),
                        'profit_metric': profit_metric,
                        'target_metric': target_level,
                        'metric_type': metric_name,
                        'close_percentage': close_pct,
                        'is_final_target': is_final_target
                    }
                )
                
        return None
        
    def reset(self):
        """Reset target tracking state."""
        super().reset()
        self._targets_hit.clear()
        
    def remove_position(self, ticket: int):
        """Remove position from tracking when closed externally."""
        if ticket in self._targets_hit:
            del self._targets_hit[ticket]
            self.logger.debug(f"Removed profit target tracking for {ticket}")
            
    def get_distance_to_target(self, position: PositionInfo) -> Optional[float]:
        """
        Calculate distance to next profit target.
        
        Args:
            position: Position to check
            
        Returns:
            Distance in pips or percent, None if target already hit
        """
        if self.target_pips is not None:
            current_pips = position.get_pnl_pips()
            return max(0, self.target_pips - current_pips)
        else:
            profit_pct = (position.unrealized_pnl / (position.volume * position.open_price)) * 100
            return max(0, self.target_pct - profit_pct)




