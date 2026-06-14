"""
Adaptive Account Manager - Dynamic Account Phase & Timeframe Management

Implements intelligent account scaling with dynamic timeframe adjustment:
- Smaller balance → smaller positions, tighter losses, shorter timeframes
- Recovery mode → faster trades, quicker profits, more frequent entries
- Growth mode → larger positions, wider stops, longer timeframes
- Mature mode → balanced approach with compounding focus

Uses argmax-style decision making for optimal phase transitions.

Integration with:
- AdaptiveLossCurve for loss tolerance
- AdaptiveDrawdownManager for drawdown state
- ProfitScaler for profit taking
- ExitCoordinator for exit decisions

This creates a complete account lifecycle management system.
"""

import math
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple
from enum import Enum

logger = logging.getLogger('cthulu.adaptive_account_manager')


class AccountPhase(Enum):
    """Account growth phases with distinct trading strategies."""
    MICRO = "micro"           # $0-25: Survival mode, micro positions
    SEED = "seed"             # $25-100: Building phase, conservative
    GROWTH = "growth"         # $100-500: Aggressive growth, scaling up
    ESTABLISHED = "established"  # $500-2000: Balanced growth
    MATURE = "mature"         # $2000+: Compounding focus
    RECOVERY = "recovery"     # Any balance in drawdown > 20%


class TimeframeMode(Enum):
    """Timeframe aggressiveness modes."""
    SCALP = "scalp"          # M1-M5: Quick profits, high frequency
    INTRADAY = "intraday"    # M15-H1: Day trading
    SWING = "swing"          # H4-D1: Position trading
    POSITION = "position"    # D1-W1: Long-term holds


@dataclass
class PhaseConfig:
    """Configuration for each account phase."""
    phase: AccountPhase
    balance_range: Tuple[float, float]  # (min, max)
    
    # Position management
    max_lot_size: float
    position_risk_pct: float  # % of balance per trade
    max_concurrent_positions: int
    
    # Timeframe selection
    preferred_timeframe: TimeframeMode
    allowed_timeframes: List[TimeframeMode]
    
    # Loss management
    max_loss_per_trade_pct: float
    max_daily_loss_pct: float
    stop_loss_atr_mult: float
    
    # Profit management
    take_profit_atr_mult: float
    profit_lock_threshold_pct: float
    scale_out_enabled: bool
    
    # Trade frequency
    min_trade_interval_seconds: int
    max_trades_per_hour: int
    
    # Confidence requirements
    min_signal_confidence: float
    min_risk_reward: float


# Phase configurations
PHASE_CONFIGS: Dict[AccountPhase, PhaseConfig] = {
    AccountPhase.MICRO: PhaseConfig(
        phase=AccountPhase.MICRO,
        balance_range=(0, 25),
        max_lot_size=0.01,
        position_risk_pct=0.10,  # 10% risk per trade (tight stops)
        max_concurrent_positions=2,  # Allow 2 positions for hedging/DCA
        preferred_timeframe=TimeframeMode.SCALP,
        allowed_timeframes=[TimeframeMode.SCALP, TimeframeMode.INTRADAY],
        max_loss_per_trade_pct=0.10,  # 10% max loss - more room to breathe
        max_daily_loss_pct=0.20,  # 20% daily - aggressive for micro
        stop_loss_atr_mult=1.0,  # Tight stops
        take_profit_atr_mult=1.5,
        profit_lock_threshold_pct=0.05,  # Lock at 5%
        scale_out_enabled=False,  # No scaling on micro
        min_trade_interval_seconds=30,  # Faster for scalping
        max_trades_per_hour=15,  # More trades for micro accounts
        min_signal_confidence=0.50,  # REDUCED from 0.70 - allow more signals
        min_risk_reward=1.2,  # REDUCED from 1.5 - allow quick scalps
    ),
    AccountPhase.SEED: PhaseConfig(
        phase=AccountPhase.SEED,
        balance_range=(25, 100),
        max_lot_size=0.02,
        position_risk_pct=0.05,
        max_concurrent_positions=3,  # Increased from 2
        preferred_timeframe=TimeframeMode.SCALP,
        allowed_timeframes=[TimeframeMode.SCALP, TimeframeMode.INTRADAY],
        max_loss_per_trade_pct=0.05,
        max_daily_loss_pct=0.12,  # Increased from 0.10
        stop_loss_atr_mult=1.2,
        take_profit_atr_mult=2.0,
        profit_lock_threshold_pct=0.04,
        scale_out_enabled=True,
        min_trade_interval_seconds=60,  # Reduced from 120
        max_trades_per_hour=12,  # Increased from 8
        min_signal_confidence=0.55,  # REDUCED from 0.65
        min_risk_reward=1.5,  # REDUCED from 1.8
    ),
    AccountPhase.GROWTH: PhaseConfig(
        phase=AccountPhase.GROWTH,
        balance_range=(100, 500),
        max_lot_size=0.05,
        position_risk_pct=0.03,
        max_concurrent_positions=3,
        preferred_timeframe=TimeframeMode.INTRADAY,
        allowed_timeframes=[TimeframeMode.SCALP, TimeframeMode.INTRADAY, TimeframeMode.SWING],
        max_loss_per_trade_pct=0.03,
        max_daily_loss_pct=0.08,
        stop_loss_atr_mult=1.5,
        take_profit_atr_mult=2.5,
        profit_lock_threshold_pct=0.03,
        scale_out_enabled=True,
        min_trade_interval_seconds=180,
        max_trades_per_hour=6,
        min_signal_confidence=0.55,
        min_risk_reward=2.0,
    ),
    AccountPhase.ESTABLISHED: PhaseConfig(
        phase=AccountPhase.ESTABLISHED,
        balance_range=(500, 2000),
        max_lot_size=0.10,
        position_risk_pct=0.02,
        max_concurrent_positions=5,
        preferred_timeframe=TimeframeMode.INTRADAY,
        allowed_timeframes=[TimeframeMode.INTRADAY, TimeframeMode.SWING],
        max_loss_per_trade_pct=0.02,
        max_daily_loss_pct=0.05,
        stop_loss_atr_mult=2.0,
        take_profit_atr_mult=3.0,
        profit_lock_threshold_pct=0.02,
        scale_out_enabled=True,
        min_trade_interval_seconds=300,
        max_trades_per_hour=4,
        min_signal_confidence=0.50,
        min_risk_reward=2.0,
    ),
    AccountPhase.MATURE: PhaseConfig(
        phase=AccountPhase.MATURE,
        balance_range=(2000, float('inf')),
        max_lot_size=0.50,
        position_risk_pct=0.01,
        max_concurrent_positions=7,
        preferred_timeframe=TimeframeMode.SWING,
        allowed_timeframes=[TimeframeMode.INTRADAY, TimeframeMode.SWING, TimeframeMode.POSITION],
        max_loss_per_trade_pct=0.015,
        max_daily_loss_pct=0.04,
        stop_loss_atr_mult=2.5,
        take_profit_atr_mult=4.0,
        profit_lock_threshold_pct=0.015,
        scale_out_enabled=True,
        min_trade_interval_seconds=600,
        max_trades_per_hour=3,
        min_signal_confidence=0.45,
        min_risk_reward=2.5,
    ),
    AccountPhase.RECOVERY: PhaseConfig(
        phase=AccountPhase.RECOVERY,
        balance_range=(0, float('inf')),  # Any balance
        max_lot_size=0.01,
        position_risk_pct=0.03,  # Moderate risk for recovery
        max_concurrent_positions=2,
        preferred_timeframe=TimeframeMode.SCALP,  # Quick trades for recovery
        allowed_timeframes=[TimeframeMode.SCALP],
        max_loss_per_trade_pct=0.02,  # Tight loss
        max_daily_loss_pct=0.05,
        stop_loss_atr_mult=0.8,  # Very tight stops
        take_profit_atr_mult=1.2,  # Quick profits
        profit_lock_threshold_pct=0.02,
        scale_out_enabled=False,  # Lock in profits immediately
        min_trade_interval_seconds=30,  # More frequent
        max_trades_per_hour=15,  # Higher frequency
        min_signal_confidence=0.75,  # Higher confidence required
        min_risk_reward=1.2,  # Lower R:R acceptable for quick wins
    ),
}


@dataclass
class AccountState:
    """Current account state snapshot."""
    balance: float
    equity: float
    phase: AccountPhase
    drawdown_pct: float
    peak_balance: float
    initial_balance: float
    
    # Recovery metrics
    in_recovery: bool = False
    recovery_progress_pct: float = 0.0
    
    # Trading metrics
    trades_today: int = 0
    trades_this_hour: int = 0
    last_trade_time: Optional[datetime] = None
    daily_pnl: float = 0.0
    
    # Performance
    win_rate_recent: float = 0.5
    avg_win: float = 0.0
    avg_loss: float = 0.0
    
    # Current timeframe
    active_timeframe: TimeframeMode = TimeframeMode.INTRADAY


class AdaptiveAccountManager:
    """
    Dynamic account management with phase-based trading parameters.
    
    Philosophy:
    - Account phase determines trading style
    - Smaller accounts need faster profits and tighter risk
    - Recovery mode prioritizes capital preservation and quick wins
    - Growth phases can take larger positions with wider stops
    - Mature accounts focus on compounding with lower frequency
    
    The argmax decision system selects the optimal phase based on
    multiple factors: balance, drawdown, momentum, and market conditions.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize adaptive account manager."""
        self.config = config or {}
        
        # Custom phase thresholds
        self.phase_thresholds = self.config.get('phase_thresholds', {
            'micro': 25,
            'seed': 100,
            'growth': 500,
            'established': 2000,
        })
        
        # Recovery threshold
        self.recovery_drawdown_threshold = self.config.get('recovery_threshold', 0.20)
        
        # State tracking
        self._state = AccountState(
            balance=0,
            equity=0,
            phase=AccountPhase.MICRO,
            drawdown_pct=0,
            peak_balance=0,
            initial_balance=0,
        )
        
        # Performance tracking
        self._trade_history: List[Dict[str, Any]] = []
        self._daily_trades: List[Dict[str, Any]] = []
        self._hourly_trades: List[Dict[str, Any]] = []
        
        # Timeframe mapping to MT5 constants
        self.timeframe_map = {
            TimeframeMode.SCALP: ['TIMEFRAME_M1', 'TIMEFRAME_M5'],
            TimeframeMode.INTRADAY: ['TIMEFRAME_M15', 'TIMEFRAME_M30', 'TIMEFRAME_H1'],
            TimeframeMode.SWING: ['TIMEFRAME_H4', 'TIMEFRAME_D1'],
            TimeframeMode.POSITION: ['TIMEFRAME_D1', 'TIMEFRAME_W1'],
        }
        
        logger.info("AdaptiveAccountManager initialized")
    
    def update(self, balance: float, equity: float, 
               peak_balance: Optional[float] = None,
               initial_balance: Optional[float] = None) -> PhaseConfig:
        """
        Update account state and return current phase configuration.
        
        Args:
            balance: Current account balance
            equity: Current account equity
            peak_balance: Historical peak balance (optional)
            initial_balance: Initial deposit (optional)
            
        Returns:
            PhaseConfig for current account state
        """
        now = datetime.now(timezone.utc)
        
        # Initialize if first call
        if self._state.initial_balance == 0:
            self._state.initial_balance = initial_balance or balance
            self._state.peak_balance = peak_balance or balance
        
        # Update balances
        self._state.balance = balance
        self._state.equity = equity
        
        if peak_balance:
            self._state.peak_balance = max(self._state.peak_balance, peak_balance)
        elif balance > self._state.peak_balance:
            self._state.peak_balance = balance
        
        if initial_balance:
            self._state.initial_balance = initial_balance
        
        # Calculate drawdown
        if self._state.peak_balance > 0:
            self._state.drawdown_pct = (
                (self._state.peak_balance - balance) / self._state.peak_balance
            )
        
        # Check recovery mode
        self._state.in_recovery = self._state.drawdown_pct >= self.recovery_drawdown_threshold
        
        if self._state.in_recovery:
            # Calculate recovery progress
            max_dd = self._state.peak_balance - min(balance, self._state.peak_balance * 0.8)
            current_dd = self._state.peak_balance - balance
            if max_dd > 0:
                self._state.recovery_progress_pct = max(0, (max_dd - current_dd) / max_dd * 100)
        
        # Determine phase using argmax
        self._state.phase = self._determine_phase_argmax(balance)
        
        # Update timeframe based on phase
        phase_config = PHASE_CONFIGS[self._state.phase]
        self._state.active_timeframe = phase_config.preferred_timeframe
        
        # Clean up old trades
        self._cleanup_trade_history(now)
        
        logger.debug(f"Account state updated: phase={self._state.phase.value}, "
                    f"balance=${balance:.2f}, drawdown={self._state.drawdown_pct*100:.1f}%")
        
        return phase_config
    
    def _determine_phase_argmax(self, balance: float) -> AccountPhase:
        """
        Determine optimal phase using argmax over multiple factors.
        
        Factors considered:
        1. Balance tier
        2. Drawdown state
        3. Recent performance momentum
        4. Recovery progress
        
        Returns highest-scoring phase.
        """
        # If in significant drawdown, recovery mode takes precedence
        if self._state.in_recovery and self._state.drawdown_pct >= 0.25:
            return AccountPhase.RECOVERY
        
        # Calculate scores for each phase
        scores: Dict[AccountPhase, float] = {}
        
        for phase, config in PHASE_CONFIGS.items():
            if phase == AccountPhase.RECOVERY:
                continue  # Handled separately
            
            score = 0.0
            min_bal, max_bal = config.balance_range
            
            # Balance fit score (primary factor)
            if min_bal <= balance < max_bal:
                # Perfect fit
                range_size = max_bal - min_bal if max_bal != float('inf') else 10000
                position_in_range = (balance - min_bal) / range_size
                score += 50 + (position_in_range * 20)  # 50-70 points for balance fit
            elif balance >= max_bal:
                # Above range
                score += 30  # Still valid but not optimal
            else:
                # Below range
                score += 10
            
            # Drawdown adjustment
            if self._state.drawdown_pct > 0.15:
                # In drawdown, prefer more conservative phases
                if phase in [AccountPhase.MICRO, AccountPhase.SEED]:
                    score += 15
                elif phase in [AccountPhase.GROWTH]:
                    score += 5
            
            # Recent performance adjustment
            if self._state.win_rate_recent > 0.6:
                # Winning streak - can be more aggressive
                if phase in [AccountPhase.GROWTH, AccountPhase.ESTABLISHED]:
                    score += 10
            elif self._state.win_rate_recent < 0.4:
                # Losing streak - be conservative
                if phase in [AccountPhase.MICRO, AccountPhase.SEED]:
                    score += 10
            
            scores[phase] = score
        
        # Argmax selection
        best_phase = max(scores, key=scores.get)
        
        logger.debug(f"Phase scores: {[(p.value, s) for p, s in scores.items()]}")
        logger.debug(f"Selected phase: {best_phase.value} (score: {scores[best_phase]:.1f})")
        
        return best_phase
    
    def get_optimal_timeframe(self, market_volatility: Optional[float] = None) -> TimeframeMode:
        """
        Get optimal timeframe for current account state and market conditions.
        
        Args:
            market_volatility: Current market volatility (0-1 scale, 1 = high)
            
        Returns:
            Optimal TimeframeMode
        """
        phase_config = PHASE_CONFIGS[self._state.phase]
        base_timeframe = phase_config.preferred_timeframe
        
        # Adjust for volatility
        if market_volatility is not None:
            if market_volatility > 0.7:
                # High volatility - use shorter timeframes
                if TimeframeMode.SCALP in phase_config.allowed_timeframes:
                    return TimeframeMode.SCALP
            elif market_volatility < 0.3:
                # Low volatility - can use longer timeframes
                if TimeframeMode.SWING in phase_config.allowed_timeframes:
                    return TimeframeMode.SWING
        
        # Recovery mode always prefers scalp
        if self._state.in_recovery:
            return TimeframeMode.SCALP
        
        return base_timeframe
    
    def get_position_size(self, entry_price: float, stop_loss: float,
                         symbol_info: Optional[Dict[str, Any]] = None) -> float:
        """
        Calculate optimal position size based on current phase.
        
        Args:
            entry_price: Planned entry price
            stop_loss: Planned stop loss price
            symbol_info: Symbol specifications (pip_value, lot_step, etc.)
            
        Returns:
            Position size in lots
        """
        phase_config = PHASE_CONFIGS[self._state.phase]
        
        # Calculate risk amount
        risk_amount = self._state.balance * phase_config.position_risk_pct
        
        # Calculate pip distance
        pip_distance = abs(entry_price - stop_loss)
        
        if pip_distance <= 0:
            return phase_config.max_lot_size * 0.5  # Default if no stop provided
        
        # Get pip value (default estimation if not provided)
        pip_value = 10.0  # Default: $10 per lot per pip for major pairs
        if symbol_info:
            pip_value = symbol_info.get('pip_value', 10.0)
        
        # Calculate lot size
        # lot_size = risk_amount / (pip_distance * pip_value)
        if pip_distance * pip_value > 0:
            lot_size = risk_amount / (pip_distance * pip_value * 10000)  # Normalize
        else:
            lot_size = 0.01
        
        # Apply constraints
        lot_size = max(0.01, min(lot_size, phase_config.max_lot_size))
        
        # Round to valid lot step
        lot_step = 0.01
        if symbol_info:
            lot_step = symbol_info.get('lot_step', 0.01)
        
        lot_size = round(lot_size / lot_step) * lot_step
        lot_size = max(0.01, lot_size)
        
        logger.debug(f"Position size calculated: {lot_size} lots "
                    f"(risk ${risk_amount:.2f}, pip_dist: {pip_distance})")
        
        return lot_size
    
    def can_open_trade(self) -> Tuple[bool, str]:
        """
        Check if a new trade can be opened based on phase limits.
        
        Returns:
            Tuple of (can_trade, reason)
        """
        phase_config = PHASE_CONFIGS[self._state.phase]
        now = datetime.now(timezone.utc)
        
        # Check max trades per hour
        if self._state.trades_this_hour >= phase_config.max_trades_per_hour:
            return False, f"Max trades/hour reached ({phase_config.max_trades_per_hour})"
        
        # Check trade interval
        if self._state.last_trade_time:
            elapsed = (now - self._state.last_trade_time).total_seconds()
            if elapsed < phase_config.min_trade_interval_seconds:
                remaining = phase_config.min_trade_interval_seconds - elapsed
                return False, f"Trade interval not met ({remaining:.0f}s remaining)"
        
        # Check daily loss limit
        if self._state.daily_pnl < 0:
            daily_loss_pct = abs(self._state.daily_pnl) / self._state.balance if self._state.balance > 0 else 0
            if daily_loss_pct >= phase_config.max_daily_loss_pct:
                return False, f"Daily loss limit reached ({daily_loss_pct*100:.1f}%)"
        
        return True, "OK"
    
    def validate_signal(self, confidence: float, risk_reward: float) -> Tuple[bool, str]:
        """
        Validate a trading signal against current phase requirements.
        
        Args:
            confidence: Signal confidence (0-1)
            risk_reward: Expected risk/reward ratio
            
        Returns:
            Tuple of (is_valid, reason)
        """
        phase_config = PHASE_CONFIGS[self._state.phase]
        
        if confidence < phase_config.min_signal_confidence:
            return False, f"Confidence {confidence:.2f} below min {phase_config.min_signal_confidence:.2f}"
        
        if risk_reward < phase_config.min_risk_reward:
            return False, f"R:R {risk_reward:.2f} below min {phase_config.min_risk_reward:.2f}"
        
        return True, "OK"
    
    def record_trade(self, pnl: float, was_win: bool) -> None:
        """Record a completed trade for tracking."""
        now = datetime.now(timezone.utc)
        
        trade = {
            'timestamp': now,
            'pnl': pnl,
            'win': was_win,
            'phase': self._state.phase.value,
            'balance': self._state.balance,
        }
        
        self._trade_history.append(trade)
        self._daily_trades.append(trade)
        self._hourly_trades.append(trade)
        
        # Update state
        self._state.trades_today += 1
        self._state.trades_this_hour += 1
        self._state.last_trade_time = now
        self._state.daily_pnl += pnl
        
        # Update performance metrics
        self._update_performance_metrics()
        
        # Keep history bounded
        if len(self._trade_history) > 1000:
            self._trade_history = self._trade_history[-500:]
    
    def _update_performance_metrics(self) -> None:
        """Update win rate and average win/loss from recent trades."""
        recent = self._trade_history[-20:] if len(self._trade_history) >= 5 else self._trade_history
        
        if not recent:
            return
        
        wins = [t for t in recent if t['win']]
        losses = [t for t in recent if not t['win']]
        
        self._state.win_rate_recent = len(wins) / len(recent) if recent else 0.5
        self._state.avg_win = sum(t['pnl'] for t in wins) / len(wins) if wins else 0
        self._state.avg_loss = sum(abs(t['pnl']) for t in losses) / len(losses) if losses else 0
    
    def _cleanup_trade_history(self, now: datetime) -> None:
        """Clean up old trades from daily/hourly tracking."""
        # Reset daily trades at midnight
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        self._daily_trades = [t for t in self._daily_trades if t['timestamp'] >= day_start]
        self._state.trades_today = len(self._daily_trades)
        
        # Reset hourly trades
        hour_ago = now - timedelta(hours=1)
        self._hourly_trades = [t for t in self._hourly_trades if t['timestamp'] >= hour_ago]
        self._state.trades_this_hour = len(self._hourly_trades)
        
        # Reset daily P&L at midnight
        if not self._daily_trades:
            self._state.daily_pnl = 0.0
    
    def get_current_config(self) -> PhaseConfig:
        """Get current phase configuration."""
        return PHASE_CONFIGS[self._state.phase]
    
    def get_state(self) -> AccountState:
        """Get current account state."""
        return self._state
    
    def get_status_report(self) -> Dict[str, Any]:
        """Get comprehensive status report."""
        phase_config = PHASE_CONFIGS[self._state.phase]
        
        return {
            'phase': self._state.phase.value,
            'balance': round(self._state.balance, 2),
            'equity': round(self._state.equity, 2),
            'peak_balance': round(self._state.peak_balance, 2),
            'drawdown_pct': round(self._state.drawdown_pct * 100, 2),
            'in_recovery': self._state.in_recovery,
            'recovery_progress_pct': round(self._state.recovery_progress_pct, 1),
            
            # Phase config summary
            'max_lot_size': phase_config.max_lot_size,
            'max_positions': phase_config.max_concurrent_positions,
            'timeframe': self._state.active_timeframe.value,
            'min_confidence': phase_config.min_signal_confidence,
            'min_rr': phase_config.min_risk_reward,
            
            # Trading metrics
            'trades_today': self._state.trades_today,
            'trades_this_hour': self._state.trades_this_hour,
            'daily_pnl': round(self._state.daily_pnl, 2),
            'win_rate': round(self._state.win_rate_recent * 100, 1),
            
            # Limits
            'can_trade': self.can_open_trade()[0],
            'next_trade_allowed': self._get_next_trade_time(),
        }
    
    def _get_next_trade_time(self) -> Optional[str]:
        """Get next allowed trade time."""
        if not self._state.last_trade_time:
            return "Now"
        
        phase_config = PHASE_CONFIGS[self._state.phase]
        next_time = self._state.last_trade_time + timedelta(
            seconds=phase_config.min_trade_interval_seconds
        )
        
        now = datetime.now(timezone.utc)
        if next_time <= now:
            return "Now"
        
        remaining = (next_time - now).total_seconds()
        return f"In {remaining:.0f}s"
    
    def get_timeframe_mt5_constant(self) -> str:
        """Get MT5 timeframe constant for current phase."""
        timeframe = self._state.active_timeframe
        mt5_timeframes = self.timeframe_map.get(timeframe, ['TIMEFRAME_M15'])
        return mt5_timeframes[0]  # Return primary timeframe


# Factory function
def create_adaptive_account_manager(config: Optional[Dict[str, Any]] = None) -> AdaptiveAccountManager:
    """Create an AdaptiveAccountManager with optional configuration."""
    return AdaptiveAccountManager(config)


# Integration helper for trading loop
class AccountPhaseIntegration:
    """
    Helper class to integrate AdaptiveAccountManager with trading loop.
    
    Provides unified interface for:
    - Position sizing
    - Timeframe selection
    - Trade validation
    - Risk limits
    """
    
    def __init__(self, account_manager: AdaptiveAccountManager,
                 loss_curve: Optional[Any] = None,
                 drawdown_manager: Optional[Any] = None):
        """
        Initialize integration.
        
        Args:
            account_manager: AdaptiveAccountManager instance
            loss_curve: AdaptiveLossCurve instance (optional)
            drawdown_manager: AdaptiveDrawdownManager instance (optional)
        """
        self.account_manager = account_manager
        self.loss_curve = loss_curve
        self.drawdown_manager = drawdown_manager
    
    def get_trade_parameters(self, balance: float, equity: float,
                            entry_price: float, stop_loss: float,
                            signal_confidence: float,
                            market_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Get unified trade parameters from all adaptive systems.
        
        Returns dict with:
        - position_size
        - max_loss
        - timeframe
        - can_trade
        - validation_result
        """
        # Update account manager
        phase_config = self.account_manager.update(balance, equity)
        
        # Get position size
        position_size = self.account_manager.get_position_size(entry_price, stop_loss)
        
        # Get max loss from loss curve if available
        max_loss = balance * phase_config.max_loss_per_trade_pct
        if self.loss_curve:
            max_loss = min(max_loss, self.loss_curve.get_max_loss(balance, per_trade=True))
        
        # Get timeframe
        volatility = market_data.get('volatility', 0.5) if market_data else 0.5
        timeframe = self.account_manager.get_optimal_timeframe(volatility)
        
        # Check if can trade
        can_trade, trade_reason = self.account_manager.can_open_trade()
        
        # Validate signal
        risk_reward = abs(entry_price - stop_loss) / stop_loss if stop_loss > 0 else 1.0
        is_valid, valid_reason = self.account_manager.validate_signal(
            signal_confidence, risk_reward
        )
        
        # Get drawdown adjustments if available
        dd_multiplier = 1.0
        if self.drawdown_manager:
            dd_settings = self.drawdown_manager.update(balance, equity, market_data)
            dd_multiplier = dd_settings.position_size_multiplier
            
            # Override can_trade if drawdown manager blocks
            if not dd_settings.allow_new_trades:
                can_trade = False
                trade_reason = "Drawdown manager blocking new trades"
        
        # Apply drawdown multiplier to position size
        adjusted_size = round(position_size * dd_multiplier, 2)
        adjusted_size = max(0.01, adjusted_size)
        
        return {
            'position_size': adjusted_size,
            'raw_position_size': position_size,
            'max_loss': max_loss,
            'timeframe': timeframe.value,
            'mt5_timeframe': self.account_manager.get_timeframe_mt5_constant(),
            'can_trade': can_trade and is_valid,
            'trade_reason': trade_reason if not can_trade else valid_reason,
            'phase': self.account_manager.get_state().phase.value,
            'drawdown_multiplier': dd_multiplier,
            'phase_config': {
                'min_confidence': phase_config.min_signal_confidence,
                'min_rr': phase_config.min_risk_reward,
                'max_positions': phase_config.max_concurrent_positions,
            }
        }
