"""
Dynamic SL/TP Management System

A sophisticated, adaptive stop-loss and take-profit management system that:
1. Dynamically adjusts SL/TP based on market conditions
2. Moves stops to breakeven after profit threshold
3. Implements ATR-based adaptive trailing
4. Adjusts based on balance/equity state
5. Considers drawdown levels for more aggressive/defensive positioning
6. Implements partial take-profit scaling

This makes Cthulu a truly adaptive, loss-minimizing, gain-maximizing beast.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple, List
from enum import Enum
import math

logger = logging.getLogger(__name__)


class SLTPMode(Enum):
    """Dynamic SL/TP operational modes."""
    NORMAL = "normal"              # Standard operation
    DEFENSIVE = "defensive"        # Tighter stops, quicker profit taking
    AGGRESSIVE = "aggressive"      # Wider stops, let profits run
    SURVIVAL = "survival"          # Minimum risk, quick exits
    RECOVERY = "recovery"          # Balanced recovery approach


@dataclass
class DynamicSLTP:
    """Dynamic SL/TP values with metadata."""
    stop_loss: float
    take_profit: float
    sl_distance: Optional[float] = None
    tp_distance: Optional[float] = None
    breakeven_level: Optional[float] = None
    partial_tp_1: Optional[float] = None   # First partial TP (33%)
    partial_tp_2: Optional[float] = None   # Second partial TP (66%)
    trail_activation: Optional[float] = None
    trail_distance: Optional[float] = None
    mode: SLTPMode = SLTPMode.NORMAL
    reasoning: str = ""


class DynamicSLTPManager:
    """
    Advanced dynamic stop-loss and take-profit management.
    
    Key Features:
    - ATR-based dynamic SL/TP calculation
    - Balance-aware position protection
    - Drawdown-adaptive stop management
    - Automatic breakeven movement
    - Partial profit scaling
    - Market regime adaptation
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize with optional configuration."""
        self.config = config or {}
        
        # Default multipliers (can be overridden by config)
        self.base_sl_atr_mult = self.config.get('base_sl_atr_mult', 2.0)
        self.base_tp_atr_mult = self.config.get('base_tp_atr_mult', 4.0)
        
        # Breakeven settings
        self.breakeven_activation_pct = self.config.get('breakeven_activation_pct', 0.5)
        self.breakeven_buffer_pct = self.config.get('breakeven_buffer_pct', 0.1)
        
        # Partial TP settings
        self.partial_tp_enabled = self.config.get('partial_tp_enabled', True)
        self.partial_tp_1_pct = self.config.get('partial_tp_1_pct', 0.33)  # 33% of distance
        self.partial_tp_2_pct = self.config.get('partial_tp_2_pct', 0.66)  # 66% of distance
        
        # Trailing settings
        self.trail_activation_pct = self.config.get('trail_activation_pct', 0.7)
        self.trail_distance_atr_mult = self.config.get('trail_distance_atr_mult', 1.5)
        
        # Safety settings
        # Minimum SL distance as a percent of entry price (e.g., 0.02 => 0.02%)
        self.min_sl_distance_pct = self.config.get('min_sl_distance_pct', 0.02)
        # Fallback minimum expressed as a multiple of ATR
        self.min_sl_distance_atr_mult = self.config.get('min_sl_distance_atr_mult', 0.25)
        # Per-symbol absolute minimum SL distance (price units), e.g. {"XAUUSD": 0.1}
        self.per_symbol_min_sl = self.config.get('per_symbol_min_sl', {})
        
        # DYNAMIC MODE THRESHOLDS (configurable, no hardcoding)
        # Drawdown thresholds for mode switching
        self.survival_drawdown_pct = self.config.get('survival_drawdown_pct', 50.0)
        self.defensive_drawdown_pct = self.config.get('defensive_drawdown_pct', 25.0)
        self.recovery_drawdown_pct = self.config.get('recovery_drawdown_pct', 10.0)
        # Gain thresholds for aggressive mode
        self.aggressive_gain_pct = self.config.get('aggressive_gain_pct', 20.0)
        self.aggressive_max_drawdown_pct = self.config.get('aggressive_max_drawdown_pct', 5.0)
        # Balance-equity ratio for recovery
        self.recovery_balance_equity_ratio = self.config.get('recovery_balance_equity_ratio', 0.95)
        
        # Mode adjustments
        self.mode_adjustments = {
            SLTPMode.NORMAL: {'sl_mult': 1.0, 'tp_mult': 1.0},
            SLTPMode.DEFENSIVE: {'sl_mult': 0.7, 'tp_mult': 0.6},
            SLTPMode.AGGRESSIVE: {'sl_mult': 1.5, 'tp_mult': 2.0},
            SLTPMode.SURVIVAL: {'sl_mult': 0.5, 'tp_mult': 0.4},
            SLTPMode.RECOVERY: {'sl_mult': 0.8, 'tp_mult': 1.2},
        }
        
        # State tracking
        self.current_mode = SLTPMode.NORMAL
        self.positions_managed: Dict[int, Dict[str, Any]] = {}
        # Track peak balance for equity-based drawdown
        self.peak_balance = 0.0
        self.initial_balance_tracked = 0.0
        
        logger.info("DynamicSLTPManager initialized with dynamic thresholds")
    
    def determine_mode(self, drawdown_pct: float, balance: float, 
                       equity: float, initial_balance: float,
                       atr: Optional[float] = None, 
                       current_price: Optional[float] = None) -> SLTPMode:
        """
        Determine operational mode based on account state with EQUITY-BASED drawdown.
        
        Args:
            drawdown_pct: Current drawdown percentage (balance-based, legacy)
            balance: Current balance
            equity: Current equity
            initial_balance: Starting balance
            atr: Current ATR (optional, for volatility-adjusted thresholds)
            current_price: Current price (optional, for ATR normalization)
            
        Returns:
            Appropriate SLTPMode
        """
        # Track peak balance for equity-based drawdown calculation
        if initial_balance > 0 and self.initial_balance_tracked == 0:
            self.initial_balance_tracked = initial_balance
        
        # Update peak balance (high water mark)
        if balance > self.peak_balance:
            self.peak_balance = balance
        
        # Calculate EQUITY-BASED drawdown (more accurate than balance-based)
        equity_drawdown_pct = 0.0
        if self.peak_balance > 0:
            equity_drawdown_pct = ((self.peak_balance - equity) / self.peak_balance) * 100
        
        # Use the WORSE of balance drawdown or equity drawdown (conservative)
        effective_drawdown = max(drawdown_pct, equity_drawdown_pct)
        
        # Optional: Volatility-adjusted thresholds
        # In high volatility, be more tolerant; in low volatility, be stricter
        volatility_factor = 1.0
        if atr and current_price and current_price > 0:
            atr_pct = (atr / current_price) * 100
            # Normalize around 0.5% ATR - higher ATR = more tolerance
            volatility_factor = min(1.5, max(0.7, atr_pct / 0.5))
        
        # Dynamic thresholds (configurable via __init__)
        survival_threshold = self.survival_drawdown_pct * volatility_factor
        defensive_threshold = self.defensive_drawdown_pct * volatility_factor
        recovery_threshold = self.recovery_drawdown_pct * volatility_factor
        
        # Survival mode: severe drawdown
        if effective_drawdown >= survival_threshold:
            self.current_mode = SLTPMode.SURVIVAL
            logger.warning(f"SLTP Mode: SURVIVAL (equity_dd={equity_drawdown_pct:.1f}%, balance_dd={drawdown_pct:.1f}%, threshold={survival_threshold:.1f}%)")
            return SLTPMode.SURVIVAL
        
        # Defensive mode: significant drawdown
        if effective_drawdown >= defensive_threshold:
            self.current_mode = SLTPMode.DEFENSIVE
            logger.info(f"SLTP Mode: DEFENSIVE (equity_dd={equity_drawdown_pct:.1f}%, threshold={defensive_threshold:.1f}%)")
            return SLTPMode.DEFENSIVE
        
        # Recovery mode: recovering from drawdown
        if effective_drawdown >= recovery_threshold and balance > equity * self.recovery_balance_equity_ratio:
            self.current_mode = SLTPMode.RECOVERY
            return SLTPMode.RECOVERY
        
        # Aggressive mode: account is profitable
        gain_pct = ((balance - self.initial_balance_tracked) / self.initial_balance_tracked) * 100 if self.initial_balance_tracked > 0 else 0
        if gain_pct >= self.aggressive_gain_pct and effective_drawdown < self.aggressive_max_drawdown_pct:
            self.current_mode = SLTPMode.AGGRESSIVE
            return SLTPMode.AGGRESSIVE
        
        self.current_mode = SLTPMode.NORMAL
        return SLTPMode.NORMAL
    
    def reset_peak_tracking(self):
        """Reset peak balance tracking - call when resetting system or recovering."""
        self.peak_balance = 0.0
        self.initial_balance_tracked = 0.0
        logger.info("Peak balance tracking reset")

    def _round_to_tick(self, price: float, tick_size: Optional[float]) -> float:
        """Round a price to the nearest tick if tick_size is provided."""
        try:
            if tick_size and tick_size > 0:
                return round(price / tick_size) * tick_size
        except Exception as e:
            logger.debug("Failed to round to tick (%s): %s", tick_size, e, exc_info=True)
        return price
    
    def calculate_dynamic_sltp(
        self,
        entry_price: float,
        side: str,  # 'BUY' or 'SELL'
        atr: float,
        balance: float,
        equity: float,
        drawdown_pct: float,
        initial_balance: float,
        symbol_info: Optional[Dict[str, Any]] = None,
        risk_reward_target: float = 2.0
    ) -> DynamicSLTP:
        """
        Calculate dynamic SL/TP based on market conditions and account state.
        
        Args:
            entry_price: Entry price of the position
            side: 'BUY' or 'SELL'
            atr: Current ATR value
            balance: Account balance
            equity: Account equity
            drawdown_pct: Current drawdown percentage
            initial_balance: Starting balance
            symbol_info: Symbol information (tick size, etc.)
            risk_reward_target: Target R:R ratio
            
        Returns:
            DynamicSLTP with calculated values
        """
        # Determine mode with ATR context for volatility-adjusted thresholds
        mode = self.determine_mode(drawdown_pct, balance, equity, initial_balance, 
                                   atr=atr, current_price=entry_price)
        
        # Get mode adjustments
        adj = self.mode_adjustments[mode]
        
        # Calculate base distances
        sl_distance = atr * self.base_sl_atr_mult * adj['sl_mult']
        tp_distance = atr * self.base_tp_atr_mult * adj['tp_mult']
        
        # Ensure minimum R:R ratio
        min_rr = 1.5 if mode != SLTPMode.SURVIVAL else 2.0
        if tp_distance / sl_distance < min_rr:
            tp_distance = sl_distance * min_rr
        
        # Apply target R:R
        if risk_reward_target > min_rr:
            tp_distance = sl_distance * risk_reward_target
        
        # DYNAMIC balance-based adjustments using initial_balance ratio (no hardcoded values)
        # Calculate balance ratio relative to initial - this scales with any account size
        if initial_balance > 0:
            balance_ratio = balance / initial_balance
            
            # If balance has dropped significantly, tighten stops proportionally
            if balance_ratio < 0.5:  # Below 50% of initial
                # Scale: at 25% remaining, multiply by 0.5; at 50% remaining, multiply by 0.7
                scale_factor = 0.5 + (balance_ratio * 0.4)  # Range: 0.5 to 0.7
                sl_distance *= scale_factor
                tp_distance *= scale_factor * 0.85  # TP slightly tighter
                logger.debug(f"Balance protection: ratio={balance_ratio:.2f}, scale={scale_factor:.2f}")
            elif balance_ratio < 0.75:  # Below 75% of initial
                scale_factor = 0.7 + ((balance_ratio - 0.5) * 0.6)  # Range: 0.7 to 0.85
                sl_distance *= scale_factor
                tp_distance *= scale_factor * 0.9
        
        # Calculate actual prices
        if side.upper() == 'BUY':
            stop_loss = entry_price - sl_distance
            take_profit = entry_price + tp_distance
            breakeven = entry_price + (sl_distance * self.breakeven_activation_pct)
            partial_tp_1 = entry_price + (tp_distance * self.partial_tp_1_pct)
            partial_tp_2 = entry_price + (tp_distance * self.partial_tp_2_pct)
            trail_activation = entry_price + (tp_distance * self.trail_activation_pct)
        else:
            stop_loss = entry_price + sl_distance
            take_profit = entry_price - tp_distance
            breakeven = entry_price - (sl_distance * self.breakeven_activation_pct)
            partial_tp_1 = entry_price - (tp_distance * self.partial_tp_1_pct)
            partial_tp_2 = entry_price - (tp_distance * self.partial_tp_2_pct)
            trail_activation = entry_price - (tp_distance * self.trail_activation_pct)
        
        # Calculate trail distance
        trail_distance = atr * self.trail_distance_atr_mult

        # --- Enforce symbol-aware minimum SL distance and tick rounding ---
        tick = None
        symbol_name = None
        if symbol_info:
            tick = symbol_info.get('point') or symbol_info.get('tick_size')
            symbol_name = symbol_info.get('name') or symbol_info.get('symbol')

        # Minimums
        min_by_pct = entry_price * (self.min_sl_distance_pct / 100)
        min_by_atr = atr * self.min_sl_distance_atr_mult
        min_by_symbol = 0.0
        if symbol_info:
            point = symbol_info.get('point')
            # If broker provides a trade stops level (minimum stop distance in points), honor it
            stops_level = symbol_info.get('trade_stops_level') or symbol_info.get('stops_level')
            if point:
                try:
                    min_by_symbol = float(point) * (int(stops_level) if stops_level else float(point))
                except Exception:
                    min_by_symbol = float(point)

        per_symbol_override = 0.0
        try:
            if symbol_name and self.per_symbol_min_sl:
                per_symbol_override = float(self.per_symbol_min_sl.get(symbol_name, 0.0))
        except Exception:
            per_symbol_override = 0.0

        effective_min = max(min_by_pct, min_by_atr, min_by_symbol, per_symbol_override)

        # Enforce minimum SL distance and ensure TP follows configured RR
        if sl_distance < effective_min:
            sl_distance = effective_min
            # Ensure TP respects minimum R:R
            if tp_distance / sl_distance < min_rr:
                tp_distance = sl_distance * min_rr
            if risk_reward_target > min_rr:
                tp_distance = sl_distance * risk_reward_target

        # Recompute prices based on possibly updated distances
        if side.upper() == 'BUY':
            stop_loss = entry_price - sl_distance
            take_profit = entry_price + tp_distance
            breakeven = entry_price + (sl_distance * self.breakeven_activation_pct)
            partial_tp_1 = entry_price + (tp_distance * self.partial_tp_1_pct)
            partial_tp_2 = entry_price + (tp_distance * self.partial_tp_2_pct)
            trail_activation = entry_price + (tp_distance * self.trail_activation_pct)
        else:
            stop_loss = entry_price + sl_distance
            take_profit = entry_price - tp_distance
            breakeven = entry_price - (sl_distance * self.breakeven_activation_pct)
            partial_tp_1 = entry_price - (tp_distance * self.partial_tp_1_pct)
            partial_tp_2 = entry_price - (tp_distance * self.partial_tp_2_pct)
            trail_activation = entry_price - (tp_distance * self.trail_activation_pct)

        # Round prices to tick if available
        if tick:
            stop_loss = self._round_to_tick(stop_loss, tick)
            take_profit = self._round_to_tick(take_profit, tick)
            breakeven = self._round_to_tick(breakeven, tick)
            partial_tp_1 = self._round_to_tick(partial_tp_1, tick) if partial_tp_1 else None
            partial_tp_2 = self._round_to_tick(partial_tp_2, tick) if partial_tp_2 else None
            trail_activation = self._round_to_tick(trail_activation, tick)

        ratio = (tp_distance / sl_distance) if sl_distance > 0 else 0.0
        reasoning = (
            f"Mode: {mode.value}, ATR: {atr:.2f}, "
            f"SL dist: {sl_distance:.6f}, TP dist: {tp_distance:.6f}, "
            f"MinReq: {effective_min:.6f}, Tick: {tick if tick else 'NA'}, R:R: {ratio:.2f}"
        )

        # Return distances in DynamicSLTP for downstream decision logic
        # (sl_distance and tp_distance included for safety checks elsewhere)
        return DynamicSLTP(
            stop_loss=stop_loss,
            take_profit=take_profit,
            sl_distance=sl_distance,
            tp_distance=tp_distance,
            breakeven_level=breakeven,
            partial_tp_1=partial_tp_1 if self.partial_tp_enabled else None,
            partial_tp_2=partial_tp_2 if self.partial_tp_enabled else None,
            trail_activation=trail_activation,
            trail_distance=trail_distance,
            mode=mode,
            reasoning=reasoning
        )        
        reasoning = (
            f"Mode: {mode.value}, ATR: {atr:.2f}, "
            f"SL dist: {sl_distance:.2f}, TP dist: {tp_distance:.2f}, "
            f"R:R: {tp_distance/sl_distance:.2f}"
        )
        
        return DynamicSLTP(
            stop_loss=stop_loss,
            take_profit=take_profit,
            breakeven_level=breakeven,
            partial_tp_1=partial_tp_1 if self.partial_tp_enabled else None,
            partial_tp_2=partial_tp_2 if self.partial_tp_enabled else None,
            trail_activation=trail_activation,
            trail_distance=trail_distance,
            mode=mode,
            reasoning=reasoning
        )
    
    def should_move_to_breakeven(
        self,
        ticket: int,
        entry_price: float,
        current_price: float,
        side: str,
        current_sl: Optional[float],
        breakeven_level: float,
        sl_distance: Optional[float] = None,
        symbol_info: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Optional[float]]:
        """
        Check if SL should be moved to breakeven.
        
        Args:
            ticket: Position ticket
            entry_price: Entry price
            current_price: Current market price
            side: 'BUY' or 'SELL'
            current_sl: Current stop loss
            breakeven_level: Level at which to activate breakeven
            
        Returns:
            Tuple of (should_move: bool, new_sl: float or None)
        """
        is_long = side.upper() == 'BUY'
        
        # Check if price has reached breakeven activation level
        if is_long:
            if current_price >= breakeven_level:
                # Calculate new SL at entry + small buffer
                buffer = entry_price * self.breakeven_buffer_pct / 100
                new_sl = entry_price + buffer

                # Round to tick if available
                tick = symbol_info.get('point') if symbol_info else None
                if tick:
                    new_sl = self._round_to_tick(new_sl, tick)
                
                # Only move if it's an improvement
                if current_sl is None or new_sl > current_sl:
                    logger.info(f"Position {ticket}: Moving SL to breakeven {new_sl:.5f}")
                    return True, new_sl
        else:
            if current_price <= breakeven_level:
                # Prefer buffer relative to SL distance when available, but keep a fallback to percent of entry
                try:
                    entry_buffer = entry_price * self.breakeven_buffer_pct / 100
                    if sl_distance and sl_distance > 0:
                        # Cap buffer so it is not absurdly larger than the volatility-based SL distance
                        buffer = min(entry_buffer, sl_distance * 0.5)
                    else:
                        buffer = entry_buffer
                except Exception:
                    buffer = entry_price * self.breakeven_buffer_pct / 100

                new_sl = entry_price - buffer

                # Round to tick if available
                tick = symbol_info.get('point') if symbol_info else None
                if tick:
                    new_sl = self._round_to_tick(new_sl, tick)

                if current_sl is None or new_sl < current_sl:
                    logger.info(f"Position {ticket}: Moving SL to breakeven {new_sl:.5f} (buffer={buffer:.5f})")
                    return True, new_sl

        return False, None
    
    def calculate_trailing_sl(
        self,
        ticket: int,
        current_price: float,
        side: str,
        current_sl: Optional[float],
        trail_activation: float,
        trail_distance: float,
        highest_price: Optional[float] = None,
        lowest_price: Optional[float] = None
    ) -> Tuple[bool, Optional[float]]:
        """
        Calculate trailing stop loss.
        
        Args:
            ticket: Position ticket
            current_price: Current market price
            side: 'BUY' or 'SELL'
            current_sl: Current stop loss
            trail_activation: Price level to activate trailing
            trail_distance: Distance to trail by
            highest_price: Highest price since entry (for longs)
            lowest_price: Lowest price since entry (for shorts)
            
        Returns:
            Tuple of (should_update: bool, new_sl: float or None)
        """
        is_long = side.upper() == 'BUY'
        
        # Track position state
        if ticket not in self.positions_managed:
            self.positions_managed[ticket] = {
                'highest': current_price,
                'lowest': current_price,
                'trailing_active': False
            }
        
        state = self.positions_managed[ticket]
        
        # Update highest/lowest
        if current_price > state['highest']:
            state['highest'] = current_price
        if current_price < state['lowest']:
            state['lowest'] = current_price
        
        if is_long:
            # Check if trailing is activated
            if current_price >= trail_activation:
                state['trailing_active'] = True
            
            if state['trailing_active']:
                new_sl = state['highest'] - trail_distance
                
                # Only move if it's an improvement
                if current_sl is None or new_sl > current_sl:
                    logger.debug(f"Position {ticket}: Trailing SL to {new_sl:.5f}")
                    return True, new_sl
        else:
            if current_price <= trail_activation:
                state['trailing_active'] = True
            
            if state['trailing_active']:
                new_sl = state['lowest'] + trail_distance
                
                if current_sl is None or new_sl < current_sl:
                    logger.debug(f"Position {ticket}: Trailing SL to {new_sl:.5f}")
                    return True, new_sl
        
        return False, None
    
    def update_position_sltp(
        self,
        ticket: int,
        entry_price: float,
        current_price: float,
        side: str,
        current_sl: Optional[float],
        current_tp: Optional[float],
        atr: float,
        balance: float,
        equity: float,
        drawdown_pct: float,
        initial_balance: float,
        symbol_info: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Comprehensive SL/TP update for a position.
        
        Args:
            All position and account parameters
            
        Returns:
            Dict with update_sl, update_tp, new_sl, new_tp, action, reasoning
        """
        result = {
            'update_sl': False,
            'update_tp': False,
            'new_sl': current_sl,
            'new_tp': current_tp,
            'action': 'none',
            'reasoning': ''
        }
        
        # Calculate dynamic values
        dynamic = self.calculate_dynamic_sltp(
            entry_price=entry_price,
            side=side,
            atr=atr,
            balance=balance,
            equity=equity,
            drawdown_pct=drawdown_pct,
            initial_balance=initial_balance,
            symbol_info=symbol_info
        )
        
        # Check breakeven first
        should_be, new_sl = self.should_move_to_breakeven(
            ticket, entry_price, current_price, side,
            current_sl, dynamic.breakeven_level, dynamic.sl_distance, symbol_info
        )
        
        if should_be and new_sl is not None:
            result['update_sl'] = True
            result['new_sl'] = new_sl
            result['action'] = 'breakeven'
            result['reasoning'] = f"Moved to breakeven at {new_sl:.5f}"
            return result
        
        # Check trailing stop
        if dynamic.trail_activation and dynamic.trail_distance:
            should_trail, trail_sl = self.calculate_trailing_sl(
                ticket, current_price, side, current_sl,
                dynamic.trail_activation, dynamic.trail_distance
            )
            
            if should_trail and trail_sl is not None:
                result['update_sl'] = True
                result['new_sl'] = trail_sl
                result['action'] = 'trailing'
                result['reasoning'] = f"Trailing SL to {trail_sl:.5f}"
                return result
        
        # Check if we should tighten in survival mode
        if dynamic.mode == SLTPMode.SURVIVAL:
            is_long = side.upper() == 'BUY'
            pnl_pct = ((current_price - entry_price) / entry_price * 100) if is_long else (
                (entry_price - current_price) / entry_price * 100
            )
            
            # In survival, take any profit over 0.3%
            if pnl_pct >= 0.3:
                result['update_tp'] = True
                result['new_tp'] = current_price  # Close at market
                result['action'] = 'survival_take_profit'
                result['reasoning'] = f"Survival mode - taking {pnl_pct:.2f}% profit"
                return result
        
        result['reasoning'] = f"No adjustment needed - Mode: {dynamic.mode.value}"
        return result
    
    def get_recommended_position_size_factor(
        self,
        balance: float,
        equity: float,
        drawdown_pct: float,
        initial_balance: float
    ) -> float:
        """
        Get position size factor based on current state.
        
        Args:
            Account state parameters
            
        Returns:
            Factor to multiply base position size by (0.1 to 1.5)
        """
        mode = self.determine_mode(drawdown_pct, balance, equity, initial_balance)
        
        factors = {
            SLTPMode.NORMAL: 1.0,
            SLTPMode.DEFENSIVE: 0.5,
            SLTPMode.AGGRESSIVE: 1.3,
            SLTPMode.SURVIVAL: 0.1,
            SLTPMode.RECOVERY: 0.7,
        }
        
        return factors.get(mode, 1.0)
    
    def cleanup_position(self, ticket: int):
        """Remove position from tracking when closed."""
        if ticket in self.positions_managed:
            del self.positions_managed[ticket]
            logger.debug(f"Cleaned up tracking for position {ticket}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current manager status."""
        return {
            'current_mode': self.current_mode.value,
            'positions_tracked': len(self.positions_managed),
            'trailing_active_count': sum(
                1 for p in self.positions_managed.values() 
                if p.get('trailing_active', False)
            ),
            'config': {
                'base_sl_atr_mult': self.base_sl_atr_mult,
                'base_tp_atr_mult': self.base_tp_atr_mult,
                'breakeven_activation_pct': self.breakeven_activation_pct,
                'partial_tp_enabled': self.partial_tp_enabled,
            }
        }


# Factory function
def create_dynamic_sltp_manager(config: Optional[Dict[str, Any]] = None) -> DynamicSLTPManager:
    """Create a DynamicSLTPManager instance."""
    return DynamicSLTPManager(config)
