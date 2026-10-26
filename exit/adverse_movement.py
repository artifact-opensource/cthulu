"""
Adverse Movement Exit Strategy

Emergency exit during flash crashes or extreme adverse movements.
"""

import logging
from typing import Dict, Any, Optional, Deque
from datetime import datetime, timedelta
from collections import deque

from .base import ExitStrategy, ExitSignal
from cthulu.position.manager import PositionInfo


class AdverseMovementExit(ExitStrategy):
    """
    Adverse movement exit strategy for flash crash protection.
    
    Features:
    - Rapid adverse price movement detection
    - Volatility-adjusted thresholds
    - Time window analysis for sustained moves
    - Differentiate flash crashes from normal volatility
    - Emergency exit priority
    
    Configuration parameters:
        movement_threshold_pct: Adverse move % to trigger (default: 1.0)
        movement_threshold_pips: Adverse move pips to trigger (alternative)
        time_window_seconds: Time window for move detection (default: 60)
        ignore_during_high_volatility: Skip during known high vol (default: False)
        volatility_threshold_atr: ATR multiplier for high vol (default: 2.5)
        consecutive_moves_required: Consecutive adverse moves needed (default: 1)
        cooldown_seconds: Cooldown after exit before re-evaluating (default: 300)
    """
    
    def __init__(self, params: Dict[str, Any]):
        """
        Initialize adverse movement exit strategy.
        
        Args:
            params: Strategy parameters (thresholds, time windows, etc.)
        """
        super().__init__(
            name="AdverseMovementExit",
            params=params,
            priority=90  # Critical priority - emergency exit
        )
        
        # Default parameters
        self.movement_threshold_pct = params.get('movement_threshold_pct', 1.0)
        self.movement_threshold_pips = params.get('movement_threshold_pips', None)
        self.time_window_seconds = params.get('time_window_seconds', 60)
        self.ignore_during_high_volatility = params.get('ignore_during_high_volatility', False)
        self.volatility_threshold_atr = params.get('volatility_threshold_atr', 2.5)
        self.consecutive_moves_required = params.get('consecutive_moves_required', 1)
        self.cooldown_seconds = params.get('cooldown_seconds', 300)
        
        # Track price history per position
        self._price_history: Dict[int, Deque[tuple]] = {}
        # Track exit cooldowns
        self._last_exit: Dict[int, datetime] = {}
        
    def should_exit(
        self,
        position: PositionInfo,
        current_data: Dict[str, Any]
    ) -> Optional[ExitSignal]:
        """
        Check for adverse price movement.
        
        Args:
            position: Position information
            current_data: Market data including 'current_price', optional 'indicators'
            
        Returns:
            ExitSignal if adverse movement detected, None otherwise
        """
        if not self._enabled:
            return None
            
        ticket = position.ticket
        current_price = current_data.get('current_price')
        if current_price is None:
            self.logger.warning(f"No current_price for {ticket}")
            return None
            
        current_time = datetime.now()
        
        # Check cooldown
        if ticket in self._last_exit:
            time_since_exit = (current_time - self._last_exit[ticket]).total_seconds()
            if time_since_exit < self.cooldown_seconds:
                return None
                
        # Initialize price history for new position
        if ticket not in self._price_history:
            self._price_history[ticket] = deque(maxlen=100)
            
        # Add current price to history
        self._price_history[ticket].append((current_time, current_price))
        
        # Need at least 2 prices for movement calculation
        if len(self._price_history[ticket]) < 2:
            return None
            
        # Check if we should ignore during high volatility
        if self.ignore_during_high_volatility:
            indicators = current_data.get('indicators', {})
            atr = indicators.get('atr', None)
            if atr is not None:
                # Check if current volatility is high
                price_pct = (atr / position.open_price) * 100
                if price_pct > self.volatility_threshold_atr:
                    self.logger.debug(
                        f"{ticket}: Ignoring adverse check during high volatility "
                        f"(ATR {price_pct:.2f}% > {self.volatility_threshold_atr}%)"
                    )
                    return None
                    
        # Calculate adverse movement in time window
        time_threshold = current_time - timedelta(seconds=self.time_window_seconds)
        
        # Get prices within time window
        recent_prices = [
            (ts, price) for ts, price in self._price_history[ticket]
            if ts >= time_threshold
        ]
        
        if len(recent_prices) < 2:
            return None
            
        # Calculate movement based on position side
        is_long = position.side == 'BUY'
        start_price = recent_prices[0][1]
        
        # Check for consecutive adverse moves
        adverse_moves = 0
        for i in range(1, len(recent_prices)):
            prev_price = recent_prices[i-1][1]
            curr_price = recent_prices[i][1]
            
            if is_long:
                # For long, adverse is price going down
                if curr_price < prev_price:
                    adverse_moves += 1
                else:
                    adverse_moves = 0  # Reset counter
            else:
                # For short, adverse is price going up
                if curr_price > prev_price:
                    adverse_moves += 1
                else:
                    adverse_moves = 0
                    
        # Check consecutive moves requirement
        if adverse_moves < self.consecutive_moves_required:
            return None
            
        # Calculate total movement in window
        price_change = current_price - start_price
        
        # Determine adverse movement magnitude
        if self.movement_threshold_pips is not None:
            # Pip-based threshold
            pips_moved = abs(price_change) / 0.0001  # Rough estimate
            threshold = self.movement_threshold_pips
            is_adverse = (is_long and price_change < 0) or (not is_long and price_change > 0)
            
            if is_adverse and pips_moved >= threshold:
                self.logger.warning(
                    f"Adverse movement detected for {ticket}: {pips_moved:.1f} pips "
                    f"in {self.time_window_seconds}s (threshold: {threshold} pips)"
                )
                self._last_exit[ticket] = current_time
                return self._create_exit_signal(
                    position=position,
                    price=current_price,
                    movement_pips=pips_moved,
                    time_window=self.time_window_seconds,
                    consecutive_moves=adverse_moves
                )
        else:
            # Percentage-based threshold
            pct_moved = abs(price_change / start_price) * 100
            threshold = self.movement_threshold_pct
            is_adverse = (is_long and price_change < 0) or (not is_long and price_change > 0)
            
            if is_adverse and pct_moved >= threshold:
                self.logger.warning(
                    f"Adverse movement detected for {ticket}: {pct_moved:.2f}% "
                    f"in {self.time_window_seconds}s (threshold: {threshold}%)"
                )
                self._last_exit[ticket] = current_time
                return self._create_exit_signal(
                    position=position,
                    price=current_price,
                    movement_pct=pct_moved,
                    time_window=self.time_window_seconds,
                    consecutive_moves=adverse_moves
                )
                
        return None
        
    def _create_exit_signal(
        self,
        position: PositionInfo,
        price: float,
        time_window: int,
        consecutive_moves: int,
        movement_pips: Optional[float] = None,
        movement_pct: Optional[float] = None
    ) -> ExitSignal:
        """Create emergency exit signal for adverse movement."""
        if movement_pips is not None:
            reason = f"EMERGENCY: Adverse move {movement_pips:.1f} pips in {time_window}s"
            metric = movement_pips
            metric_type = "pips"
        else:
            reason = f"EMERGENCY: Adverse move {movement_pct:.2f}% in {time_window}s"
            metric = movement_pct
            metric_type = "percent"
            
        return ExitSignal(
            ticket=position.ticket,
            reason=reason,
            price=price,
            timestamp=datetime.now(),
            strategy_name=self.name,
            confidence=1.0,
            metadata={
                'movement_metric': metric,
                'metric_type': metric_type,
                'time_window_seconds': time_window,
                'consecutive_adverse_moves': consecutive_moves,
                'exit_type': 'emergency_adverse_movement',
                'priority': 'CRITICAL'
            }
        )
        
    def reset(self):
        """Reset adverse movement tracking state."""
        super().reset()
        self._price_history.clear()
        self._last_exit.clear()
        
    def remove_position(self, ticket: int):
        """Remove position from tracking when closed externally."""
        if ticket in self._price_history:
            del self._price_history[ticket]
        if ticket in self._last_exit:
            del self._last_exit[ticket]
        self.logger.debug(f"Removed adverse movement tracking for {ticket}")




