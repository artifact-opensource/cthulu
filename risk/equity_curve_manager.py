"""
Equity Curve Management System

A cutting-edge equity curve protection and optimization system that:
1. Monitors balance, equity, and exposure in real-time
2. Implements trailing equity protection (locks in profits)
3. Dynamic risk scaling based on curve trajectory
4. Detects curve inflection points for regime adaptation
5. Provides partial close recommendations for profit protection
6. Manages exposure limits based on equity state

This ensures Cthulu protects capital while maximizing gain potential.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from enum import Enum
import math
import statistics

logger = logging.getLogger(__name__)


class EquityState(Enum):
    """Current state of the equity curve."""
    ASCENDING = "ascending"           # Equity rising steadily
    DESCENDING = "descending"         # Equity falling
    CONSOLIDATING = "consolidating"   # Sideways movement
    BREAKOUT_UP = "breakout_up"       # Breaking to new highs
    BREAKDOWN = "breakdown"           # Breaking to new lows
    RECOVERY = "recovery"             # Recovering from drawdown


class ExposureLevel(Enum):
    """Current exposure level classification."""
    MINIMAL = "minimal"     # <10% of balance at risk
    LOW = "low"             # 10-25% at risk
    MODERATE = "moderate"   # 25-50% at risk
    HIGH = "high"           # 50-75% at risk
    EXTREME = "extreme"     # >75% at risk
    OVERLEVERAGED = "overleveraged"  # >100% (margin call territory)


@dataclass
class EquityCurveMetrics:
    """Comprehensive equity curve metrics."""
    # Core values
    balance: float = 0.0
    equity: float = 0.0
    margin: float = 0.0
    free_margin: float = 0.0
    margin_level: float = 0.0
    
    # Derived metrics
    floating_pnl: float = 0.0
    exposure_pct: float = 0.0
    
    # High watermarks
    peak_balance: float = 0.0
    peak_equity: float = 0.0
    trough_balance: float = float('inf')
    trough_equity: float = float('inf')
    
    # Trailing protection
    trailing_equity_high: float = 0.0
    locked_profit_amount: float = 0.0
    locked_profit_pct: float = 0.0
    
    # Curve analysis
    equity_state: EquityState = EquityState.CONSOLIDATING
    exposure_level: ExposureLevel = ExposureLevel.LOW
    
    # Velocity and momentum
    equity_velocity: float = 0.0       # Rate of change per minute
    equity_momentum: float = 0.0       # Acceleration
    balance_velocity: float = 0.0
    
    # Risk metrics
    current_drawdown_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    drawdown_from_peak: float = 0.0
    recovery_needed_pct: float = 0.0
    
    # Timestamps
    last_peak_time: Optional[datetime] = None
    drawdown_start_time: Optional[datetime] = None
    last_update: Optional[datetime] = None


@dataclass
class EquityProtectionSettings:
    """Dynamic settings based on equity curve state."""
    allow_new_positions: bool = True
    max_position_size_factor: float = 1.0
    close_all_at_equity_pct: float = 0.0  # If set, close all at this % of peak
    partial_close_pct: float = 0.0        # Partial close recommendation %
    tighten_stops: bool = False
    move_to_breakeven: bool = False
    reduce_exposure: bool = False
    target_exposure_pct: float = 50.0
    require_higher_confidence: float = 0.0  # Additional confidence required
    message: str = ""


class EquityCurveManager:
    """
    Advanced Equity Curve Management System.
    
    Key Features:
    - Real-time balance/equity/exposure monitoring
    - Trailing equity protection with profit locking
    - Curve velocity and momentum analysis
    - Dynamic exposure management
    - Partial close recommendations
    - State-based risk adjustment
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize with optional configuration."""
        self.config = config or {}
        
        # Initial balance (set on first update)
        self.initial_balance: float = 0.0
        
        # Trailing protection settings
        self.trailing_lock_pct = self.config.get('trailing_lock_pct', 0.5)  # Lock 50% of new gains
        self.profit_lock_threshold = self.config.get('profit_lock_threshold', 5.0)  # Start locking at 5% gain
        
        # Protection thresholds
        self.equity_warning_pct = self.config.get('equity_warning_pct', 90.0)   # Warn at 90% of peak
        self.equity_danger_pct = self.config.get('equity_danger_pct', 80.0)     # Danger at 80%
        self.equity_critical_pct = self.config.get('equity_critical_pct', 70.0) # Critical at 70%
        self.equity_emergency_pct = self.config.get('equity_emergency_pct', 50.0) # Emergency at 50%
        
        # Exposure limits
        self.max_exposure_normal = self.config.get('max_exposure_normal', 50.0)
        self.max_exposure_caution = self.config.get('max_exposure_caution', 30.0)
        self.max_exposure_danger = self.config.get('max_exposure_danger', 15.0)
        
        # History for velocity calculations
        self.equity_history: List[Tuple[datetime, float]] = []
        self.balance_history: List[Tuple[datetime, float]] = []
        self.history_max_size = 100
        
        # Current metrics
        self.metrics = EquityCurveMetrics()
        
        # State tracking
        self._consecutive_losses = 0
        self._consecutive_wins = 0
        self._recent_trades: List[float] = []
        
        logger.info("EquityCurveManager initialized")
    
    def update(self, balance: float, equity: float, margin: float = 0.0,
               free_margin: float = 0.0, open_positions: int = 0) -> EquityProtectionSettings:
        """
        Update metrics and get protection recommendations.
        
        Args:
            balance: Current account balance
            equity: Current account equity
            margin: Used margin
            free_margin: Free margin available
            open_positions: Number of open positions
            
        Returns:
            EquityProtectionSettings with current recommendations
        """
        now = datetime.now()
        
        # Initialize on first call
        if self.initial_balance == 0:
            self.initial_balance = balance
            self.metrics.peak_balance = balance
            self.metrics.peak_equity = equity
            self.metrics.trailing_equity_high = equity
            self.metrics.trough_balance = balance
            self.metrics.trough_equity = equity
            logger.info(f"EquityCurve: Initial balance ${balance:.2f}")
        
        # Update core values
        self.metrics.balance = balance
        self.metrics.equity = equity
        self.metrics.margin = margin
        self.metrics.free_margin = free_margin
        self.metrics.floating_pnl = equity - balance
        self.metrics.last_update = now
        
        # Calculate margin level
        if margin > 0:
            self.metrics.margin_level = (equity / margin) * 100
        else:
            self.metrics.margin_level = float('inf') if equity > 0 else 0
        
        # Calculate exposure
        if balance > 0:
            self.metrics.exposure_pct = (margin / balance) * 100
        
        # Classify exposure level
        self.metrics.exposure_level = self._classify_exposure(self.metrics.exposure_pct)
        
        # Update high watermarks
        if balance > self.metrics.peak_balance:
            self.metrics.peak_balance = balance
        if equity > self.metrics.peak_equity:
            self.metrics.peak_equity = equity
            self.metrics.last_peak_time = now
            self.metrics.drawdown_start_time = None
        
        # Update lows
        if balance < self.metrics.trough_balance:
            self.metrics.trough_balance = balance
        if equity < self.metrics.trough_equity:
            self.metrics.trough_equity = equity
        
        # Update trailing equity protection
        self._update_trailing_protection(equity)
        
        # Calculate drawdowns
        self._calculate_drawdowns()
        
        # Update history for velocity
        self.equity_history.append((now, equity))
        self.balance_history.append((now, balance))
        if len(self.equity_history) > self.history_max_size:
            self.equity_history.pop(0)
            self.balance_history.pop(0)
        
        # Calculate velocity and momentum
        self._calculate_velocity()
        
        # Determine equity state
        self.metrics.equity_state = self._determine_state()
        
        # Generate protection settings
        return self._generate_protection_settings(open_positions)
    
    def _update_trailing_protection(self, equity: float):
        """Update trailing equity protection."""
        # Calculate gain from initial
        gain_from_initial = equity - self.initial_balance
        gain_pct = (gain_from_initial / self.initial_balance) * 100 if self.initial_balance > 0 else 0
        
        # Only start locking after threshold
        if gain_pct >= self.profit_lock_threshold:
            # Update trailing high
            if equity > self.metrics.trailing_equity_high:
                # Calculate new gains to lock
                new_gain = equity - self.metrics.trailing_equity_high
                lock_amount = new_gain * self.trailing_lock_pct
                
                self.metrics.trailing_equity_high = equity
                self.metrics.locked_profit_amount += lock_amount
                
                # Calculate locked profit as percentage of initial
                self.metrics.locked_profit_pct = (
                    self.metrics.locked_profit_amount / self.initial_balance
                ) * 100 if self.initial_balance > 0 else 0
                
                if lock_amount > 0:
                    logger.info(f"Equity curve: Locked ${lock_amount:.2f} profit "
                              f"(Total locked: ${self.metrics.locked_profit_amount:.2f}, "
                              f"{self.metrics.locked_profit_pct:.1f}%)")
    
    def _calculate_drawdowns(self):
        """Calculate current and max drawdowns."""
        if self.metrics.peak_equity > 0:
            self.metrics.drawdown_from_peak = self.metrics.peak_equity - self.metrics.equity
            self.metrics.current_drawdown_pct = (
                self.metrics.drawdown_from_peak / self.metrics.peak_equity
            ) * 100
            
            if self.metrics.current_drawdown_pct > self.metrics.max_drawdown_pct:
                self.metrics.max_drawdown_pct = self.metrics.current_drawdown_pct
                if self.metrics.drawdown_start_time is None:
                    self.metrics.drawdown_start_time = datetime.now()
            
            # Calculate recovery needed
            if self.metrics.current_drawdown_pct > 0:
                # Recovery needed = (peak - current) / current * 100
                self.metrics.recovery_needed_pct = (
                    self.metrics.drawdown_from_peak / self.metrics.equity
                ) * 100 if self.metrics.equity > 0 else 100
    
    def _calculate_velocity(self):
        """Calculate equity velocity (rate of change) and momentum."""
        if len(self.equity_history) < 3:
            return
        
        # Use last 10 data points for velocity
        recent = self.equity_history[-10:]
        if len(recent) >= 2:
            time_diff = (recent[-1][0] - recent[0][0]).total_seconds() / 60  # minutes
            equity_diff = recent[-1][1] - recent[0][1]
            
            if time_diff > 0:
                self.metrics.equity_velocity = equity_diff / time_diff
        
        # Calculate momentum (change in velocity)
        if len(self.equity_history) >= 20:
            older = self.equity_history[-20:-10]
            if len(older) >= 2:
                old_time_diff = (older[-1][0] - older[0][0]).total_seconds() / 60
                old_equity_diff = older[-1][1] - older[0][1]
                
                if old_time_diff > 0:
                    old_velocity = old_equity_diff / old_time_diff
                    self.metrics.equity_momentum = self.metrics.equity_velocity - old_velocity
        
        # Balance velocity
        recent_bal = self.balance_history[-10:]
        if len(recent_bal) >= 2:
            time_diff = (recent_bal[-1][0] - recent_bal[0][0]).total_seconds() / 60
            bal_diff = recent_bal[-1][1] - recent_bal[0][1]
            
            if time_diff > 0:
                self.metrics.balance_velocity = bal_diff / time_diff
    
    def _classify_exposure(self, exposure_pct: float) -> ExposureLevel:
        """Classify current exposure level."""
        if exposure_pct >= 100:
            return ExposureLevel.OVERLEVERAGED
        elif exposure_pct >= 75:
            return ExposureLevel.EXTREME
        elif exposure_pct >= 50:
            return ExposureLevel.HIGH
        elif exposure_pct >= 25:
            return ExposureLevel.MODERATE
        elif exposure_pct >= 10:
            return ExposureLevel.LOW
        else:
            return ExposureLevel.MINIMAL
    
    def _determine_state(self) -> EquityState:
        """Determine current equity curve state."""
        velocity = self.metrics.equity_velocity
        momentum = self.metrics.equity_momentum
        dd_pct = self.metrics.current_drawdown_pct
        
        # Check for recovery
        if dd_pct > 5 and velocity > 0:
            return EquityState.RECOVERY
        
        # Check for breakdown
        if dd_pct > 15 and velocity < 0:
            return EquityState.BREAKDOWN
        
        # Check for breakout
        if dd_pct < 2 and velocity > 0 and self.metrics.equity >= self.metrics.peak_equity * 0.99:
            return EquityState.BREAKOUT_UP
        
        # Velocity-based states
        if velocity > 0.5:  # Gaining more than $0.50/min
            return EquityState.ASCENDING
        elif velocity < -0.5:  # Losing more than $0.50/min
            return EquityState.DESCENDING
        else:
            return EquityState.CONSOLIDATING
    
    def _generate_protection_settings(self, open_positions: int) -> EquityProtectionSettings:
        """Generate protection settings based on current state."""
        settings = EquityProtectionSettings()
        
        equity_vs_peak = (self.metrics.equity / self.metrics.peak_equity * 100) if self.metrics.peak_equity > 0 else 100
        dd_pct = self.metrics.current_drawdown_pct
        exposure = self.metrics.exposure_pct
        state = self.metrics.equity_state
        
        # Check trailing equity protection breach
        if self.metrics.locked_profit_amount > 0:
            current_profit = self.metrics.equity - self.initial_balance
            if current_profit < self.metrics.locked_profit_amount * 0.5:
                # We've given back more than 50% of locked profits - tighten everything
                settings.tighten_stops = True
                settings.move_to_breakeven = True
                settings.partial_close_pct = 50.0
                settings.message = f"ALERT: Giving back locked profits. Current: ${current_profit:.2f}, Locked: ${self.metrics.locked_profit_amount:.2f}"
                logger.warning(settings.message)
        
        # Emergency level (50% or more drawdown)
        if equity_vs_peak <= self.equity_emergency_pct:
            settings.allow_new_positions = False
            settings.max_position_size_factor = 0.0
            settings.close_all_at_equity_pct = self.equity_emergency_pct - 5
            settings.reduce_exposure = True
            settings.target_exposure_pct = 5.0
            settings.require_higher_confidence = 0.5
            settings.message = f"EMERGENCY: Equity at {equity_vs_peak:.1f}% of peak. Closing positions."
            logger.critical(settings.message)
            return settings
        
        # Critical level (70% or more drawdown)
        if equity_vs_peak <= self.equity_critical_pct:
            settings.allow_new_positions = False
            settings.max_position_size_factor = 0.1
            settings.partial_close_pct = 75.0
            settings.tighten_stops = True
            settings.move_to_breakeven = True
            settings.reduce_exposure = True
            settings.target_exposure_pct = 10.0
            settings.require_higher_confidence = 0.4
            settings.message = f"CRITICAL: Equity at {equity_vs_peak:.1f}% of peak. Defensive mode."
            logger.error(settings.message)
            return settings
        
        # Danger level (80%)
        if equity_vs_peak <= self.equity_danger_pct:
            settings.allow_new_positions = open_positions < 3
            settings.max_position_size_factor = 0.25
            settings.partial_close_pct = 50.0
            settings.tighten_stops = True
            settings.reduce_exposure = True
            settings.target_exposure_pct = 20.0
            settings.require_higher_confidence = 0.3
            settings.message = f"DANGER: Equity at {equity_vs_peak:.1f}% of peak. Reducing risk."
            logger.warning(settings.message)
            return settings
        
        # Warning level (90%)
        if equity_vs_peak <= self.equity_warning_pct:
            settings.allow_new_positions = open_positions < 5
            settings.max_position_size_factor = 0.5
            settings.partial_close_pct = 25.0
            settings.tighten_stops = True
            settings.require_higher_confidence = 0.2
            settings.message = f"WARNING: Equity at {equity_vs_peak:.1f}% of peak. Caution advised."
            logger.info(settings.message)
            return settings
        
        # Exposure-based adjustments
        if self.metrics.exposure_level == ExposureLevel.OVERLEVERAGED:
            settings.allow_new_positions = False
            settings.reduce_exposure = True
            settings.target_exposure_pct = 50.0
            settings.partial_close_pct = 50.0
            settings.message = "OVERLEVERAGED: Reduce exposure immediately."
            logger.error(settings.message)
        elif self.metrics.exposure_level == ExposureLevel.EXTREME:
            settings.allow_new_positions = False
            settings.max_position_size_factor = 0.25
            settings.message = "EXTREME exposure. No new positions."
        elif self.metrics.exposure_level == ExposureLevel.HIGH:
            settings.max_position_size_factor = 0.5
            settings.message = "HIGH exposure. Reduced position sizing."
        
        # State-based adjustments
        if state == EquityState.BREAKDOWN:
            settings.tighten_stops = True
            settings.move_to_breakeven = True
            settings.max_position_size_factor *= 0.5
        elif state == EquityState.ASCENDING or state == EquityState.BREAKOUT_UP:
            # Allow slightly larger positions when curve is healthy
            settings.max_position_size_factor = min(1.2, settings.max_position_size_factor * 1.1)
        
        # Velocity-based adjustments
        if self.metrics.equity_velocity < -1.0:  # Losing > $1/min
            settings.tighten_stops = True
            settings.max_position_size_factor *= 0.7
            settings.message = f"Rapid equity decline (${self.metrics.equity_velocity:.2f}/min). Tightening stops."
        
        return settings
    
    def record_trade_result(self, pnl: float):
        """Record a trade result for analysis."""
        self._recent_trades.append(pnl)
        if len(self._recent_trades) > 50:
            self._recent_trades.pop(0)
        
        if pnl > 0:
            self._consecutive_wins += 1
            self._consecutive_losses = 0
        elif pnl < 0:
            self._consecutive_losses += 1
            self._consecutive_wins = 0
    
    def should_partial_close(self, position_pnl: float, position_pnl_pct: float) -> Tuple[bool, float, str]:
        """
        Determine if a position should be partially closed to protect profits.
        
        Args:
            position_pnl: Current P&L of the position
            position_pnl_pct: P&L as percentage of entry
            
        Returns:
            Tuple of (should_close: bool, close_pct: float, reason: str)
        """
        state = self.metrics.equity_state
        dd_pct = self.metrics.current_drawdown_pct
        
        # Always take some profit at significant gains
        if position_pnl_pct >= 5.0:  # 5% profit
            if state == EquityState.BREAKDOWN or dd_pct > 15:
                return True, 75.0, f"Taking 75% profit during drawdown (P&L: {position_pnl_pct:.1f}%)"
            elif state == EquityState.DESCENDING:
                return True, 50.0, f"Taking 50% profit during decline (P&L: {position_pnl_pct:.1f}%)"
            elif position_pnl_pct >= 10.0:
                return True, 33.0, f"Locking 33% profit at {position_pnl_pct:.1f}% gain"
        
        # During danger situations, take smaller profits
        if dd_pct > 20 and position_pnl_pct >= 2.0:
            return True, 50.0, f"Protecting capital: taking 50% at {position_pnl_pct:.1f}% during {dd_pct:.1f}% drawdown"
        
        return False, 0.0, ""
    
    def get_position_size_factor(self) -> float:
        """
        Get position sizing factor based on equity curve state.
        
        Returns:
            Factor between 0.1 and 1.5 to multiply base position size
        """
        settings = self._generate_protection_settings(0)
        return max(0.1, min(1.5, settings.max_position_size_factor))
    
    def get_max_allowed_positions(self, base_max: int) -> int:
        """
        Get maximum allowed positions based on equity state.
        
        Args:
            base_max: Base maximum positions from config
            
        Returns:
            Adjusted maximum positions
        """
        dd_pct = self.metrics.current_drawdown_pct
        exposure = self.metrics.exposure_level
        
        if dd_pct >= 50:
            return 1
        elif dd_pct >= 30:
            return max(1, base_max // 4)
        elif dd_pct >= 20:
            return max(2, base_max // 2)
        elif exposure in [ExposureLevel.EXTREME, ExposureLevel.OVERLEVERAGED]:
            return max(1, base_max // 3)
        elif exposure == ExposureLevel.HIGH:
            return max(2, base_max // 2)
        
        return base_max
    
    def get_status_report(self) -> Dict[str, Any]:
        """Get comprehensive status report."""
        return {
            'balance': round(self.metrics.balance, 2),
            'equity': round(self.metrics.equity, 2),
            'floating_pnl': round(self.metrics.floating_pnl, 2),
            'margin': round(self.metrics.margin, 2),
            'free_margin': round(self.metrics.free_margin, 2),
            'margin_level': round(self.metrics.margin_level, 2),
            'exposure_pct': round(self.metrics.exposure_pct, 2),
            'exposure_level': self.metrics.exposure_level.value,
            'peak_balance': round(self.metrics.peak_balance, 2),
            'peak_equity': round(self.metrics.peak_equity, 2),
            'current_drawdown_pct': round(self.metrics.current_drawdown_pct, 2),
            'max_drawdown_pct': round(self.metrics.max_drawdown_pct, 2),
            'recovery_needed_pct': round(self.metrics.recovery_needed_pct, 2),
            'trailing_equity_high': round(self.metrics.trailing_equity_high, 2),
            'locked_profit_amount': round(self.metrics.locked_profit_amount, 2),
            'locked_profit_pct': round(self.metrics.locked_profit_pct, 2),
            'equity_state': self.metrics.equity_state.value,
            'equity_velocity': round(self.metrics.equity_velocity, 4),
            'equity_momentum': round(self.metrics.equity_momentum, 4),
            'consecutive_wins': self._consecutive_wins,
            'consecutive_losses': self._consecutive_losses,
            'initial_balance': round(self.initial_balance, 2),
            'total_return_pct': round(
                ((self.metrics.balance - self.initial_balance) / self.initial_balance * 100)
                if self.initial_balance > 0 else 0, 2
            ),
        }


# Factory function
def create_equity_curve_manager(config: Optional[Dict[str, Any]] = None) -> EquityCurveManager:
    """Create an EquityCurveManager instance."""
    return EquityCurveManager(config)
