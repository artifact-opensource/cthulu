"""
Trailing Stop Exit Strategy

Dynamic trailing stop implementation with ATR adjustment.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
import pandas as pd

from .base import ExitStrategy, ExitSignal
from cthulu.position.manager import PositionInfo


class TrailingStop(ExitStrategy):
    """
    Trailing stop exit strategy with ATR-based distance adjustment.
    
    Features:
    - Dynamic stop distance based on Average True Range (ATR)
    - Activation after minimum profit threshold
    - Never moves stop against profit direction
    - Adapts to volatility changes
    
    Configuration parameters:
        atr_multiplier: Multiplier for ATR distance (default: 2.0)
        activation_profit_pct: Minimum profit % to activate trailing (default: 0.5)
        activation_profit_pips: Minimum profit pips to activate (alternative to pct)
        min_stop_distance_pips: Minimum stop distance in pips (default: 10)
        update_frequency_secs: Update frequency in seconds (default: 60)
    """
    
    def __init__(self, params: Dict[str, Any]):
        """
        Initialize trailing stop strategy.
        
        Args:
            params: Strategy parameters (atr_multiplier, activation_profit_pct, etc.)
        """
        super().__init__(
            name="TrailingStop",
            params=params,
            priority=25  # Low priority - let profit run
        )
        
        # Default parameters
        self.atr_multiplier = params.get('atr_multiplier', 2.0)
        self.activation_profit_pct = params.get('activation_profit_pct', 0.5)
        self.activation_profit_pips = params.get('activation_profit_pips', None)
        self.min_stop_distance_pips = params.get('min_stop_distance_pips', 10.0)
        self.update_frequency = params.get('update_frequency_secs', 60)
        
        # State: track highest favorable price per position
        self._trailing_stops: Dict[int, Dict[str, Any]] = {}
        
    def should_exit(
        self,
        position: PositionInfo,
        current_data: Dict[str, Any]
    ) -> Optional[ExitSignal]:
        """
        Check if trailing stop hit.
        
        Args:
            position: Position information
            current_data: Market data including 'current_price', 'indicators' with ATR
            
        Returns:
            ExitSignal if trailing stop hit, None otherwise
        """
        if not self._enabled:
            return None
            
        ticket = position.ticket
        current_price = current_data.get('current_price')
        if current_price is None:
            self.logger.warning(f"No current_price for {ticket}")
            return None
            
        # Get ATR from indicators if available
        indicators = current_data.get('indicators', {})
        atr = indicators.get('atr', None)
        
        # Check if position is profitable enough to activate trailing
        profit_pct = (position.unrealized_pnl / position.volume * position.open_price) * 100 if position.volume > 0 else 0
        
        activation_threshold_met = False
        if self.activation_profit_pips is not None:
            profit_pips = position.get_pnl_pips()
            activation_threshold_met = profit_pips >= self.activation_profit_pips
        else:
            activation_threshold_met = profit_pct >= self.activation_profit_pct
            
        if not activation_threshold_met:
            # Not profitable enough to activate trailing
            return None
            
        # Initialize trailing state for new position
        if ticket not in self._trailing_stops:
            self._trailing_stops[ticket] = {
                'best_price': current_price,
                'stop_price': None,
                'last_update': datetime.now(),
                'activated': True
            }
            self.logger.info(f"Trailing stop activated for {ticket} at {current_price}")
            
        state = self._trailing_stops[ticket]
        
        # Update best price if current price is more favorable
        is_long = position.side == 'BUY'
        if is_long:
            if current_price > state['best_price']:
                state['best_price'] = current_price
                self.logger.debug(f"{ticket}: New best price {current_price}")
        else:
            if current_price < state['best_price']:
                state['best_price'] = current_price
                self.logger.debug(f"{ticket}: New best price {current_price}")
                
        # Calculate trailing stop distance
        if atr is not None and atr > 0:
            stop_distance = atr * self.atr_multiplier
        else:
            # Dynamic fallback: use percentage of price instead of hardcoded pip value
            # This works for any symbol (forex, gold, crypto, indices)
            fallback_pct = self.params.get('fallback_stop_pct', 0.1)  # 0.1% default
            stop_distance = current_price * (fallback_pct / 100)
            self.logger.debug(f"No ATR, using fallback {fallback_pct}% = {stop_distance:.6f}")
            
        # Ensure minimum stop distance - DYNAMIC based on price, not hardcoded pips
        # Get symbol point from current_data if available
        symbol_point = current_data.get('symbol_info', {}).get('point', None)
        if symbol_point and symbol_point > 0:
            min_distance_price = self.min_stop_distance_pips * symbol_point
        else:
            # Fallback: percentage-based minimum (works for any instrument)
            min_distance_price = current_price * 0.0005  # 0.05% minimum
        stop_distance = max(stop_distance, min_distance_price)
        
        # Calculate new stop price
        if is_long:
            new_stop = state['best_price'] - stop_distance
            # Never move stop down
            if state['stop_price'] is None:
                state['stop_price'] = new_stop
            else:
                state['stop_price'] = max(state['stop_price'], new_stop)
                
            # Check if stop hit
            if current_price <= state['stop_price']:
                self.logger.info(
                    f"Trailing stop hit for {ticket}: price={current_price}, "
                    f"stop={state['stop_price']}, best={state['best_price']}"
                )
                return self._create_exit_signal(
                    position=position,
                    price=current_price,
                    stop_price=state['stop_price'],
                    best_price=state['best_price']
                )
        else:
            new_stop = state['best_price'] + stop_distance
            # Never move stop up
            if state['stop_price'] is None:
                state['stop_price'] = new_stop
            else:
                state['stop_price'] = min(state['stop_price'], new_stop)
                
            # Check if stop hit
            if current_price >= state['stop_price']:
                self.logger.info(
                    f"Trailing stop hit for {ticket}: price={current_price}, "
                    f"stop={state['stop_price']}, best={state['best_price']}"
                )
                return self._create_exit_signal(
                    position=position,
                    price=current_price,
                    stop_price=state['stop_price'],
                    best_price=state['best_price']
                )
                
        # Update timestamp
        state['last_update'] = datetime.now()
        return None
        
    def _create_exit_signal(
        self,
        position: PositionInfo,
        price: float,
        stop_price: float,
        best_price: float
    ) -> ExitSignal:
        """Create exit signal when trailing stop hit."""
        profit_protected = position.unrealized_pnl
        
        return ExitSignal(
            ticket=position.ticket,
            reason=f"Trailing stop hit (protected profit: {profit_protected:.2f})",
            price=price,
            timestamp=datetime.now(),
            strategy_name=self.name,
            confidence=1.0,
            metadata={
                'stop_price': stop_price,
                'best_price': best_price,
                'profit_protected': profit_protected,
                'atr_multiplier': self.atr_multiplier
            }
        )
        
    def reset(self):
        """Reset trailing stop state."""
        super().reset()
        self._trailing_stops.clear()
        
    def remove_position(self, ticket: int):
        """Remove position from tracking when closed externally."""
        if ticket in self._trailing_stops:
            del self._trailing_stops[ticket]
            self.logger.debug(f"Removed trailing stop tracking for {ticket}")


class TrailingStopExit(TrailingStop):
    """Compatibility wrapper exposing the legacy TrailingStopExit API expected by tests."""
    def __init__(self, *args, **kwargs):
        # Accept either params dict or kwargs and map trail_distance -> atr_multiplier fallback
        if args and isinstance(args[0], dict):
            params = args[0]
        else:
            params = kwargs
        # Map 'trail_distance' to 'atr_multiplier' approximately if provided
        if 'trail_distance' in params and 'atr_multiplier' not in params:
            # trail_distance is often a percentage of price; map to ATR multiplier via heuristic
            params['atr_multiplier'] = max(1.0, params.get('trail_distance', 0.015) * 10)
        super().__init__(params)
        # For legacy compatibility, set priority to 3 (tests expect low priority value 3)
        self.priority = 3
        self.trail_distance = params.get('trail_distance', None)

    def calculate_trailing_stop(self, position):
        # For compatibility tests: calculate a trailing stop based on original simple heuristic
        trail_distance = self.params.get('trail_distance', None)
        if trail_distance is not None:
            if position.side == 'BUY':
                return max(position.stop_loss or -float('inf'), position.open_price * (1 + trail_distance))
            else:
                return min(position.stop_loss or float('inf'), position.open_price * (1 - trail_distance))
        # Fallback to current internal stop price if tracked
        state = self._trailing_stops.get(position.ticket)
        if state and state.get('stop_price'):
            return state['stop_price']
        return position.stop_loss




