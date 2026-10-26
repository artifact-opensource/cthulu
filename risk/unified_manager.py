"""
Unified Risk Manager - Complete Risk Management System

Based on MQL5 "Risk Management (Part 1): Fundamentals for Building a Risk Management Class"

This module provides a complete, unified risk management system that consolidates:
- Position sizing based on risk per trade
- Daily/Weekly/Total loss limits
- Dynamic lot calculation
- Real-time position monitoring
- Adaptive risk based on account balance

Key Functions (from MQL5 design):
1. GetMaxLot - Maximum lot based on margin
2. GetIdealLot - Optimal lot based on risk percentage and SL
3. GetSL - Calculate SL based on risk and lot size
4. Loss tracking - Daily/Weekly/Total profit/loss monitoring

Part of Cthulu v6.0.0 APEX - Unified Risk System
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta, timezone
from enum import Enum
import logging

logger = logging.getLogger("cthulu.unified_risk")


class RiskAction(Enum):
    """Risk manager actions."""
    APPROVED = "approved"
    REDUCED = "reduced"       # Approved but with reduced size
    REJECTED = "rejected"
    LOCKED = "locked"         # Trading locked due to limits


@dataclass
class RiskLimits:
    """Risk limit configuration."""
    # Maximum loss limits (as percentage of balance)
    max_daily_loss_pct: float = 0.03       # 3% daily loss limit
    max_weekly_loss_pct: float = 0.06      # 6% weekly loss limit
    max_total_loss_pct: float = 0.10       # 10% total loss limit (drawdown)
    
    # Per-trade limits
    max_risk_per_trade_pct: float = 0.01   # 1% risk per trade
    max_positions: int = 5                  # Maximum concurrent positions
    max_positions_per_symbol: int = 3       # Maximum positions per symbol
    
    # Recovery mode settings
    recovery_mode_threshold: float = 0.08   # Enter recovery at 8% drawdown
    recovery_mode_risk_mult: float = 0.50   # Reduce risk to 50% in recovery
    
    # Minimum lot size
    min_lot: float = 0.01
    
    # Balance breakpoints for adaptive sizing
    balance_breakpoints: List[float] = field(default_factory=lambda: [1000.0, 5000.0, 20000.0])
    
    # Risk categories by balance
    risk_by_category: Dict[str, float] = field(default_factory=lambda: {
        'tiny': 0.005,     # 0.5% for accounts <= $1,000
        'small': 0.01,     # 1% for accounts <= $5,000
        'medium': 0.015,   # 1.5% for accounts <= $20,000
        'large': 0.02      # 2% for accounts > $20,000
    })


@dataclass
class RiskState:
    """Current risk management state."""
    # Time tracking
    day_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0))
    week_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc) - timedelta(days=datetime.now(timezone.utc).weekday()))
    
    # Balance tracking
    initial_balance: float = 0.0
    peak_balance: float = 0.0
    current_balance: float = 0.0
    
    # Profit/Loss tracking
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    total_pnl: float = 0.0
    
    # Position tracking
    open_positions: int = 0
    positions_by_symbol: Dict[str, int] = field(default_factory=dict)
    
    # State flags
    daily_limit_hit: bool = False
    weekly_limit_hit: bool = False
    total_limit_hit: bool = False
    recovery_mode: bool = False
    
    # Trade history (for win rate calculation)
    recent_trades: List[Dict[str, Any]] = field(default_factory=list)
    wins: int = 0
    losses: int = 0
    
    @property
    def win_rate(self) -> float:
        """Calculate current win rate."""
        total = self.wins + self.losses
        return self.wins / total if total > 0 else 0.5
    
    @property
    def drawdown_pct(self) -> float:
        """Calculate current drawdown percentage."""
        if self.peak_balance <= 0:
            return 0.0
        return (self.peak_balance - self.current_balance) / self.peak_balance


class UnifiedRiskManager:
    """
    Unified Risk Management System.
    
    Consolidates all risk management functions:
    - Position sizing (GetMaxLot, GetIdealLot)
    - Stop loss calculation (GetSL)
    - Loss limit enforcement
    - Recovery mode management
    - Adaptive risk by account size
    
    Based on MQL5 Risk Management design with Python enhancements.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None, limits: Optional[RiskLimits] = None):
        """
        Initialize the unified risk manager.
        
        Args:
            config: Configuration dictionary
            limits: Risk limits configuration
        """
        self.config = config or {}
        self.limits = limits or RiskLimits()
        self.state = RiskState()
        
        # Magic number for trade identification
        self.magic_number = self.config.get('magic_number', 0)
        
        # Load limits from config if provided
        if config:
            self._apply_config(config)
        
        logger.info(f"UnifiedRiskManager initialized: max_risk={self.limits.max_risk_per_trade_pct*100}%, "
                   f"max_positions={self.limits.max_positions}")
    
    def _apply_config(self, config: Dict[str, Any]) -> None:
        """Apply configuration to limits."""
        if 'max_positions' in config:
            self.limits.max_positions = int(config['max_positions'])
        if 'per_trade_risk_pct' in config:
            self.limits.max_risk_per_trade_pct = float(config['per_trade_risk_pct'])
        if 'min_lot' in config:
            self.limits.min_lot = float(config['min_lot'])
        if 'max_daily_loss_pct' in config:
            self.limits.max_daily_loss_pct = float(config['max_daily_loss_pct'])
        if 'max_weekly_loss_pct' in config:
            self.limits.max_weekly_loss_pct = float(config['max_weekly_loss_pct'])
        if 'max_total_loss_pct' in config:
            self.limits.max_total_loss_pct = float(config['max_total_loss_pct'])
    
    def initialize_balances(self, balance: float, equity: float = None) -> None:
        """
        Initialize balance tracking.
        
        Args:
            balance: Current account balance
            equity: Current account equity (defaults to balance)
        """
        self.state.initial_balance = balance
        self.state.peak_balance = balance
        self.state.current_balance = balance
        
        logger.info(f"Risk manager initialized with balance: {balance:.2f}")
    
    def update_balance(self, balance: float, equity: float = None) -> None:
        """
        Update current balance and check limits.
        
        Args:
            balance: Current account balance
            equity: Current account equity
        """
        self.state.current_balance = balance
        
        # Update peak balance
        if balance > self.state.peak_balance:
            self.state.peak_balance = balance
        
        # Check for recovery mode
        if self.state.drawdown_pct >= self.limits.recovery_mode_threshold:
            if not self.state.recovery_mode:
                logger.warning(f"Entering RECOVERY MODE: drawdown={self.state.drawdown_pct*100:.1f}%")
                self.state.recovery_mode = True
        elif self.state.recovery_mode and self.state.drawdown_pct < self.limits.recovery_mode_threshold * 0.5:
            logger.info("Exiting recovery mode")
            self.state.recovery_mode = False
        
        self._check_limits()
    
    def _check_limits(self) -> None:
        """Check if any risk limits are hit."""
        balance = self.state.current_balance
        initial = self.state.initial_balance
        
        if initial <= 0:
            return
        
        # Check daily limit
        daily_loss = -self.state.daily_pnl if self.state.daily_pnl < 0 else 0
        if daily_loss / initial >= self.limits.max_daily_loss_pct:
            if not self.state.daily_limit_hit:
                logger.warning(f"DAILY LOSS LIMIT HIT: {daily_loss:.2f} ({daily_loss/initial*100:.1f}%)")
                self.state.daily_limit_hit = True
        
        # Check weekly limit
        weekly_loss = -self.state.weekly_pnl if self.state.weekly_pnl < 0 else 0
        if weekly_loss / initial >= self.limits.max_weekly_loss_pct:
            if not self.state.weekly_limit_hit:
                logger.warning(f"WEEKLY LOSS LIMIT HIT: {weekly_loss:.2f} ({weekly_loss/initial*100:.1f}%)")
                self.state.weekly_limit_hit = True
        
        # Check total limit (drawdown)
        if self.state.drawdown_pct >= self.limits.max_total_loss_pct:
            if not self.state.total_limit_hit:
                logger.error(f"TOTAL LOSS LIMIT HIT: drawdown={self.state.drawdown_pct*100:.1f}%")
                self.state.total_limit_hit = True
    
    def get_balance_category(self, balance: float) -> str:
        """
        Determine account category based on balance.
        
        Args:
            balance: Account balance
            
        Returns:
            Category name ('tiny', 'small', 'medium', 'large')
        """
        breakpoints = self.limits.balance_breakpoints
        
        if balance <= breakpoints[0]:
            return 'tiny'
        elif balance <= breakpoints[1]:
            return 'small'
        elif balance <= breakpoints[2]:
            return 'medium'
        else:
            return 'large'
    
    def get_risk_percentage(self, balance: float) -> float:
        """
        Get risk percentage based on account size.
        
        Args:
            balance: Account balance
            
        Returns:
            Risk percentage (0-1)
        """
        category = self.get_balance_category(balance)
        base_risk = self.limits.risk_by_category.get(category, self.limits.max_risk_per_trade_pct)
        
        # Apply recovery mode reduction
        if self.state.recovery_mode:
            base_risk *= self.limits.recovery_mode_risk_mult
        
        return min(base_risk, self.limits.max_risk_per_trade_pct)
    
    def get_max_lot(
        self,
        symbol: str,
        order_type: str = 'BUY',
        price: Optional[float] = None
    ) -> float:
        """
        Calculate maximum lot size based on available margin.
        
        Based on MQL5 GetMaxLote function.
        
        Formula: max_lot = free_margin / margin_per_lot
        
        Args:
            symbol: Trading symbol
            order_type: 'BUY' or 'SELL'
            price: Order price (uses current price if not provided)
            
        Returns:
            Maximum lot size
        """
        try:
            from cthulu.connector.mt5_connector import mt5
            
            # Get symbol info
            symbol_info = mt5.symbol_info(symbol)
            if not symbol_info:
                logger.warning(f"Symbol info not available for {symbol}")
                return self.limits.min_lot
            
            # Get account info
            account_info = mt5.account_info()
            if not account_info:
                return self.limits.min_lot
            
            free_margin = account_info.margin_free
            volume_step = symbol_info.volume_step
            
            # Get price for margin calculation
            if price is None:
                tick = mt5.symbol_info_tick(symbol)
                if tick:
                    price = tick.ask if order_type.upper() == 'BUY' else tick.bid
                else:
                    return self.limits.min_lot
            
            # Calculate margin required for 1 lot
            mt5_order_type = mt5.ORDER_TYPE_BUY if order_type.upper() == 'BUY' else mt5.ORDER_TYPE_SELL
            margin = None
            
            # Try to calculate margin
            try:
                margin_result = mt5.order_calc_margin(mt5_order_type, symbol, 1.0, price)
                if margin_result is not None:
                    margin = margin_result
            except Exception:
                pass
            
            if margin is None or margin <= 0:
                return self.limits.min_lot
            
            # Calculate max lot
            max_lot = (free_margin / margin)
            max_lot = np.floor(max_lot / volume_step) * volume_step
            
            # Apply symbol limits
            max_lot = min(max_lot, symbol_info.volume_max)
            max_lot = max(max_lot, symbol_info.volume_min)
            
            return round(max_lot, 2)
            
        except Exception as e:
            logger.error(f"Error calculating max lot: {e}")
            return self.limits.min_lot
    
    def get_ideal_lot(
        self,
        symbol: str,
        stop_loss_points: int,
        side: str = 'BUY',
        risk_override: Optional[float] = None
    ) -> Tuple[float, float]:
        """
        Calculate ideal lot size based on risk per trade and stop loss distance.
        
        Based on MQL5 GetIdealLot function.
        
        Args:
            symbol: Trading symbol
            stop_loss_points: Stop loss distance in points
            side: 'BUY' or 'SELL'
            risk_override: Optional override for risk percentage
            
        Returns:
            Tuple of (ideal_lot, actual_risk_amount)
        """
        if stop_loss_points <= 0:
            logger.warning("Invalid stop loss distance")
            return self.limits.min_lot, 0.0
        
        try:
            from cthulu.connector.mt5_connector import mt5
            
            # Get account info
            account_info = mt5.account_info()
            if not account_info:
                return self.limits.min_lot, 0.0
            
            balance = account_info.balance
            
            # Get symbol info
            symbol_info = mt5.symbol_info(symbol)
            if not symbol_info:
                return self.limits.min_lot, 0.0
            
            spread = symbol_info.spread
            tick_value = symbol_info.trade_tick_value
            volume_step = symbol_info.volume_step
            
            # Get risk percentage
            risk_pct = risk_override or self.get_risk_percentage(balance)
            risk_amount = balance * risk_pct
            
            # Get max lot for upper bound
            max_lot = self.get_max_lot(symbol, side)
            
            # Calculate risk per lot
            # Risk = lot * (spread + 1 + (stop_loss * tick_value))
            risk_per_lot = (spread + 1 + (stop_loss_points * tick_value))
            
            if risk_per_lot <= 0:
                return self.limits.min_lot, 0.0
            
            # Calculate ideal lot
            current_risk = max_lot * risk_per_lot
            
            if current_risk > risk_amount:
                # Need to reduce lot size
                ideal_lot = (risk_amount / current_risk) * max_lot
                ideal_lot = np.floor(ideal_lot / volume_step) * volume_step
            else:
                # Can use max lot
                ideal_lot = max_lot
            
            # Apply limits
            ideal_lot = max(ideal_lot, symbol_info.volume_min)
            ideal_lot = min(ideal_lot, symbol_info.volume_max)
            ideal_lot = max(ideal_lot, self.limits.min_lot)
            
            # Calculate actual risk
            actual_risk = ideal_lot * risk_per_lot
            
            return round(ideal_lot, 2), round(actual_risk, 2)
            
        except Exception as e:
            logger.error(f"Error calculating ideal lot: {e}")
            return self.limits.min_lot, 0.0
    
    def get_stop_loss(
        self,
        symbol: str,
        lot_size: float,
        risk_amount: Optional[float] = None
    ) -> int:
        """
        Calculate stop loss in points based on lot size and risk amount.
        
        Based on MQL5 GetSL function.
        
        Formula: SL = ((risk / lot) - spread - 1) / tick_value
        
        Args:
            symbol: Trading symbol
            lot_size: Position lot size
            risk_amount: Risk amount in account currency (uses default if not provided)
            
        Returns:
            Stop loss distance in points
        """
        try:
            from cthulu.connector.mt5_connector import mt5
            
            # Get account info for default risk
            if risk_amount is None:
                account_info = mt5.account_info()
                if account_info:
                    risk_pct = self.get_risk_percentage(account_info.balance)
                    risk_amount = account_info.balance * risk_pct
                else:
                    return 0
            
            # Get symbol info
            symbol_info = mt5.symbol_info(symbol)
            if not symbol_info:
                return 0
            
            spread = symbol_info.spread
            tick_value = symbol_info.trade_tick_value
            
            if tick_value <= 0 or lot_size <= 0:
                return 0
            
            # Calculate SL: ((risk / lot) - spread - 1) / tick_value
            sl_points = ((risk_amount / lot_size) - spread - 1) / tick_value
            
            return int(round(max(0, sl_points)))
            
        except Exception as e:
            logger.error(f"Error calculating stop loss: {e}")
            return 0
    
    def approve(
        self,
        signal: Any,
        account_info: Optional[Dict[str, Any]] = None,
        current_positions: int = 0
    ) -> Tuple[bool, str, float]:
        """
        Approve or reject a trading signal.
        
        Main entry point for risk approval. Checks all limits and calculates position size.
        
        Args:
            signal: Trading signal object
            account_info: Account information dictionary
            current_positions: Number of current open positions
            
        Returns:
            Tuple of (approved, reason, position_size)
        """
        try:
            # Check if trading is locked
            if self.state.total_limit_hit:
                return False, "Trading locked: total loss limit hit", 0.0
            
            if self.state.daily_limit_hit:
                return False, "Trading locked: daily loss limit hit", 0.0
            
            if self.state.weekly_limit_hit:
                return False, "Trading locked: weekly loss limit hit", 0.0
            
            # Check position limits
            if current_positions >= self.limits.max_positions:
                return False, f"Max positions reached ({current_positions}/{self.limits.max_positions})", 0.0
            
            # Check per-symbol limit
            symbol = getattr(signal, 'symbol', 'UNKNOWN')
            symbol_positions = self.state.positions_by_symbol.get(symbol, 0)
            if symbol_positions >= self.limits.max_positions_per_symbol:
                return False, f"Max positions for {symbol} reached", 0.0
            
            # Get balance
            balance = 0.0
            if account_info:
                if isinstance(account_info, dict):
                    balance = float(account_info.get('balance', 0))
                else:
                    balance = float(getattr(account_info, 'balance', 0))
            
            if balance <= 0:
                return False, "Invalid balance", 0.0
            
            # Update balance tracking
            self.update_balance(balance)
            
            # Get position size
            size_hint = getattr(signal, 'size_hint', None) or getattr(signal, 'volume', None)
            
            if size_hint:
                position_size = float(size_hint)
            else:
                # Calculate based on risk and SL
                stop_loss = getattr(signal, 'stop_loss', None)
                entry_price = getattr(signal, 'price', None) or getattr(signal, 'entry_price', None)
                
                if stop_loss and entry_price:
                    sl_distance = abs(entry_price - stop_loss)
                    # Convert to points (rough estimate)
                    sl_points = int(sl_distance * 10000) if sl_distance < 1 else int(sl_distance)
                    position_size, _ = self.get_ideal_lot(symbol, sl_points, 'BUY')
                else:
                    # Fallback to minimum lot
                    position_size = self.limits.min_lot
            
            # Apply recovery mode reduction
            if self.state.recovery_mode:
                original_size = position_size
                position_size = max(self.limits.min_lot, position_size * self.limits.recovery_mode_risk_mult)
                logger.info(f"Recovery mode: reduced size {original_size:.2f} -> {position_size:.2f}")
            
            # Ensure minimum lot
            if position_size < self.limits.min_lot:
                position_size = self.limits.min_lot
            
            return True, "Risk approved", round(position_size, 2)
            
        except Exception as e:
            logger.exception("Risk approval error")
            return False, str(e), 0.0
    
    def record_trade_result(self, pnl: float, symbol: str = None) -> None:
        """
        Record a trade result for tracking.
        
        Args:
            pnl: Profit/loss amount
            symbol: Trading symbol
        """
        # Update P&L tracking
        self.state.daily_pnl += pnl
        self.state.weekly_pnl += pnl
        self.state.total_pnl += pnl
        
        # Update win/loss counts
        if pnl > 0:
            self.state.wins += 1
        elif pnl < 0:
            self.state.losses += 1
        
        # Update position count
        if symbol and symbol in self.state.positions_by_symbol:
            self.state.positions_by_symbol[symbol] = max(0, self.state.positions_by_symbol[symbol] - 1)
        
        # Record trade
        self.state.recent_trades.append({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'pnl': pnl,
            'symbol': symbol
        })
        
        # Keep only recent trades
        if len(self.state.recent_trades) > 100:
            self.state.recent_trades = self.state.recent_trades[-50:]
        
        # Check limits
        self._check_limits()
        
        logger.info(f"Trade recorded: PnL={pnl:.2f}, Daily={self.state.daily_pnl:.2f}, "
                   f"Win rate={self.state.win_rate*100:.1f}%")
    
    def record_position_opened(self, symbol: str) -> None:
        """Record that a position was opened."""
        self.state.open_positions += 1
        self.state.positions_by_symbol[symbol] = self.state.positions_by_symbol.get(symbol, 0) + 1
    
    def record_position_closed(self, symbol: str) -> None:
        """Record that a position was closed."""
        self.state.open_positions = max(0, self.state.open_positions - 1)
        if symbol in self.state.positions_by_symbol:
            self.state.positions_by_symbol[symbol] = max(0, self.state.positions_by_symbol[symbol] - 1)
    
    def reset_daily(self) -> None:
        """Reset daily tracking (call at start of trading day)."""
        self.state.daily_pnl = 0.0
        self.state.daily_limit_hit = False
        self.state.day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        logger.info("Daily risk limits reset")
    
    def reset_weekly(self) -> None:
        """Reset weekly tracking (call at start of trading week)."""
        self.state.weekly_pnl = 0.0
        self.state.weekly_limit_hit = False
        self.state.week_start = datetime.now(timezone.utc)
        logger.info("Weekly risk limits reset")
    
    def get_state(self) -> Dict[str, Any]:
        """Get current risk state as dictionary."""
        return {
            'balance': self.state.current_balance,
            'initial_balance': self.state.initial_balance,
            'peak_balance': self.state.peak_balance,
            'drawdown_pct': self.state.drawdown_pct * 100,
            'daily_pnl': self.state.daily_pnl,
            'weekly_pnl': self.state.weekly_pnl,
            'total_pnl': self.state.total_pnl,
            'win_rate': self.state.win_rate * 100,
            'open_positions': self.state.open_positions,
            'daily_limit_hit': self.state.daily_limit_hit,
            'weekly_limit_hit': self.state.weekly_limit_hit,
            'total_limit_hit': self.state.total_limit_hit,
            'recovery_mode': self.state.recovery_mode,
            'category': self.get_balance_category(self.state.current_balance),
            'current_risk_pct': self.get_risk_percentage(self.state.current_balance) * 100
        }
    
    def can_trade(self) -> Tuple[bool, str]:
        """
        Check if trading is currently allowed.
        
        Returns:
            Tuple of (can_trade, reason)
        """
        if self.state.total_limit_hit:
            return False, "Total loss limit hit"
        if self.state.daily_limit_hit:
            return False, "Daily loss limit hit"
        if self.state.weekly_limit_hit:
            return False, "Weekly loss limit hit"
        if self.state.open_positions >= self.limits.max_positions:
            return False, f"Max positions ({self.limits.max_positions}) reached"
        
        return True, "Trading allowed"


# Factory function for creating risk manager
def create_unified_risk_manager(config: Optional[Dict[str, Any]] = None) -> UnifiedRiskManager:
    """
    Create a UnifiedRiskManager with optional configuration.
    
    Args:
        config: Optional configuration dictionary
        
    Returns:
        Configured UnifiedRiskManager instance
    """
    return UnifiedRiskManager(config=config)


# Module-level singleton
_risk_manager: Optional[UnifiedRiskManager] = None


def get_unified_risk_manager(**kwargs) -> UnifiedRiskManager:
    """Get or create the unified risk manager singleton."""
    global _risk_manager
    if _risk_manager is None:
        _risk_manager = UnifiedRiskManager(**kwargs)
    return _risk_manager
