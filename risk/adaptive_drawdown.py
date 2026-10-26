"""
Adaptive Drawdown Management System

A cutting-edge, dynamic risk management module that:
1. Monitors real-time drawdown and adjusts position sizing dynamically
2. Implements trailing equity protection (locks in gains)
3. Detects market regime changes and adapts behavior
4. Uses exponential recovery scaling after drawdowns
5. Implements liquidity-aware position management
6. Provides trap detection heuristics

This is designed to make Cthulu a zero-loss-tolerant, gain-maximizing beast.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from enum import Enum
import math

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Market regime classification for adaptive behavior."""
    TRENDING_BULL = "trending_bull"
    TRENDING_BEAR = "trending_bear"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    TRAP_DETECTED = "trap_detected"


class DrawdownState(Enum):
    """Current drawdown state for position scaling."""
    NORMAL = "normal"           # 0-5% drawdown
    CAUTION = "caution"         # 5-10% drawdown
    WARNING = "warning"         # 10-20% drawdown
    DANGER = "danger"           # 20-35% drawdown
    CRITICAL = "critical"       # 35-50% drawdown
    SURVIVAL = "survival"       # 50-90% drawdown - extreme defensive mode
    RECOVERY = "recovery"       # Coming back from drawdown


@dataclass
class DrawdownMetrics:
    """Real-time drawdown metrics tracking."""
    current_balance: float = 0.0
    peak_balance: float = 0.0
    initial_balance: float = 0.0
    lowest_balance: float = float('inf')
    
    # Drawdown calculations
    current_drawdown_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    drawdown_duration_minutes: int = 0
    
    # Recovery tracking
    recovery_pct: float = 0.0
    time_since_peak: int = 0
    
    # Trailing equity high watermark
    trailing_equity_high: float = 0.0
    locked_profit_pct: float = 0.0
    
    # State
    state: DrawdownState = DrawdownState.NORMAL
    regime: MarketRegime = MarketRegime.RANGING
    
    # Timestamps
    peak_timestamp: Optional[datetime] = None
    drawdown_start: Optional[datetime] = None


@dataclass
class AdaptiveSettings:
    """Dynamic settings that change based on drawdown state."""
    position_size_multiplier: float = 1.0
    max_positions_allowed: int = 10
    confidence_threshold: float = 0.25
    risk_reward_min: float = 1.5
    allow_new_trades: bool = True
    require_confirmation: bool = False
    scale_in_enabled: bool = True
    scale_out_enabled: bool = True


class AdaptiveDrawdownManager:
    """
    Advanced drawdown management with dynamic adaptation.
    
    Key Features:
    - Real-time drawdown monitoring with state transitions
    - Dynamic position sizing based on drawdown state
    - Trailing equity protection (locks in X% of gains)
    - Market regime detection and adaptation
    - Exponential recovery scaling
    - Liquidity trap detection heuristics
    - Win streak / lose streak tracking for confidence adjustment
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize with optional configuration."""
        self.config = config or {}
        
        # Drawdown thresholds for state transitions
        self.thresholds = {
            DrawdownState.NORMAL: 5.0,
            DrawdownState.CAUTION: 10.0,
            DrawdownState.WARNING: 20.0,
            DrawdownState.DANGER: 35.0,
            DrawdownState.CRITICAL: 50.0,
            DrawdownState.SURVIVAL: 90.0,
        }
        
        # Position size multipliers per state
        self.size_multipliers = {
            DrawdownState.NORMAL: 1.0,
            DrawdownState.CAUTION: 0.75,
            DrawdownState.WARNING: 0.5,
            DrawdownState.DANGER: 0.25,
            DrawdownState.CRITICAL: 0.1,   # Minimal positions only
            DrawdownState.SURVIVAL: 0.05,  # Micro positions - survival mode
            DrawdownState.RECOVERY: 0.6,
        }
        
        # Trailing equity lock percentages (lock in X% of gains above high watermark)
        self.trailing_lock_pct = self.config.get('trailing_lock_pct', 0.5)  # Lock 50% of gains
        
        # Initialize metrics
        self.metrics = DrawdownMetrics()
        
        # Trade history for streak tracking
        self.trade_results: List[float] = []  # Recent P&L results
        self.max_streak_history = 20
        
        # Regime detection parameters
        self.regime_lookback = 50  # bars
        self.volatility_threshold_high = 2.0  # ATR multiplier
        self.volatility_threshold_low = 0.5
        
        # Trap detection
        self.trap_indicators: List[Dict[str, Any]] = []
        self.trap_cooldown_minutes = 30
        self.last_trap_time: Optional[datetime] = None
        
        logger.info("AdaptiveDrawdownManager initialized")
    
    def update(self, balance: float, equity: float, 
               market_data: Optional[Dict[str, Any]] = None) -> AdaptiveSettings:
        """
        Update metrics and return adaptive settings for current state.
        
        Args:
            balance: Current account balance
            equity: Current account equity (balance + floating P&L)
            market_data: Optional market data for regime detection
            
        Returns:
            AdaptiveSettings with current recommendations
        """
        now = datetime.now()
        
        # Initialize on first call
        if self.metrics.initial_balance == 0:
            self.metrics.initial_balance = balance
            self.metrics.peak_balance = balance
            self.metrics.trailing_equity_high = equity
            self.metrics.peak_timestamp = now
            self.metrics.lowest_balance = balance
            logger.info(f"AdaptiveDrawdown: Initial balance set to ${balance:.2f}")
        
        # Update current metrics
        self.metrics.current_balance = balance
        
        # Track lowest point
        if balance < self.metrics.lowest_balance:
            self.metrics.lowest_balance = balance
        
        # Update peak balance (high watermark)
        if balance > self.metrics.peak_balance:
            self.metrics.peak_balance = balance
            self.metrics.peak_timestamp = now
            self.metrics.drawdown_start = None
            self.metrics.drawdown_duration_minutes = 0
            logger.info(f"New peak balance: ${balance:.2f}")
        
        # Update trailing equity high
        if equity > self.metrics.trailing_equity_high:
            self.metrics.trailing_equity_high = equity
            # Calculate locked profit
            gain_from_initial = equity - self.metrics.initial_balance
            if gain_from_initial > 0:
                self.metrics.locked_profit_pct = (gain_from_initial / self.metrics.initial_balance) * self.trailing_lock_pct
        
        # Calculate current drawdown
        if self.metrics.peak_balance > 0:
            self.metrics.current_drawdown_pct = (
                (self.metrics.peak_balance - balance) / self.metrics.peak_balance
            ) * 100
        
        # Track max drawdown
        if self.metrics.current_drawdown_pct > self.metrics.max_drawdown_pct:
            self.metrics.max_drawdown_pct = self.metrics.current_drawdown_pct
            if self.metrics.drawdown_start is None:
                self.metrics.drawdown_start = now
        
        # Calculate drawdown duration
        if self.metrics.drawdown_start:
            duration = now - self.metrics.drawdown_start
            self.metrics.drawdown_duration_minutes = int(duration.total_seconds() / 60)
        
        # Calculate time since peak
        if self.metrics.peak_timestamp:
            time_since = now - self.metrics.peak_timestamp
            self.metrics.time_since_peak = int(time_since.total_seconds() / 60)
        
        # Calculate recovery percentage
        if self.metrics.max_drawdown_pct > 0 and self.metrics.current_drawdown_pct < self.metrics.max_drawdown_pct:
            self.metrics.recovery_pct = (
                (self.metrics.max_drawdown_pct - self.metrics.current_drawdown_pct) / 
                self.metrics.max_drawdown_pct
            ) * 100
        
        # Determine state
        self.metrics.state = self._determine_state()
        
        # Detect market regime if data available
        if market_data:
            self.metrics.regime = self._detect_regime(market_data)
        
        # Generate adaptive settings
        return self._generate_settings()
    
    def _determine_state(self) -> DrawdownState:
        """Determine current drawdown state based on metrics."""
        dd = self.metrics.current_drawdown_pct
        
        # Check if we're in recovery mode
        if self.metrics.recovery_pct > 50 and dd > self.thresholds[DrawdownState.CAUTION]:
            return DrawdownState.RECOVERY
        
        # State transitions based on drawdown percentage
        if dd >= self.thresholds[DrawdownState.SURVIVAL]:
            return DrawdownState.SURVIVAL
        elif dd >= self.thresholds[DrawdownState.CRITICAL]:
            return DrawdownState.CRITICAL
        elif dd >= self.thresholds[DrawdownState.DANGER]:
            return DrawdownState.DANGER
        elif dd >= self.thresholds[DrawdownState.WARNING]:
            return DrawdownState.WARNING
        elif dd >= self.thresholds[DrawdownState.CAUTION]:
            return DrawdownState.CAUTION
        else:
            return DrawdownState.NORMAL
    
    def _detect_regime(self, market_data: Dict[str, Any]) -> MarketRegime:
        """
        Detect current market regime from market data.
        
        Args:
            market_data: Dict with 'atr', 'atr_avg', 'trend_direction', 'range_bound'
            
        Returns:
            MarketRegime classification
        """
        try:
            atr = market_data.get('atr', 0)
            atr_avg = market_data.get('atr_avg', atr)
            trend = market_data.get('trend_direction', 0)  # 1 = up, -1 = down, 0 = none
            range_bound = market_data.get('range_bound', False)
            
            # Check for trap conditions first
            if self._detect_trap(market_data):
                return MarketRegime.TRAP_DETECTED
            
            # Volatility classification
            if atr_avg > 0:
                vol_ratio = atr / atr_avg
                if vol_ratio > self.volatility_threshold_high:
                    return MarketRegime.HIGH_VOLATILITY
                elif vol_ratio < self.volatility_threshold_low:
                    return MarketRegime.LOW_VOLATILITY
            
            # Trend classification
            if range_bound:
                return MarketRegime.RANGING
            elif trend > 0:
                return MarketRegime.TRENDING_BULL
            elif trend < 0:
                return MarketRegime.TRENDING_BEAR
            
            return MarketRegime.RANGING
            
        except Exception as e:
            logger.error(f"Error detecting regime: {e}")
            return MarketRegime.RANGING
    
    def _detect_trap(self, market_data: Dict[str, Any]) -> bool:
        """
        Detect potential liquidity trap or stop hunt.
        
        Heuristics:
        - Rapid price spike followed by reversal
        - Volume spike without follow-through
        - Price touching key levels and reversing
        - Divergence between price and momentum
        """
        try:
            # Check cooldown
            if self.last_trap_time:
                cooldown_elapsed = (datetime.now() - self.last_trap_time).total_seconds() / 60
                if cooldown_elapsed < self.trap_cooldown_minutes:
                    return True  # Still in cooldown
            
            # Get trap indicators from market data
            spike_detected = market_data.get('price_spike', False)
            volume_divergence = market_data.get('volume_divergence', False)
            key_level_rejection = market_data.get('key_level_rejection', False)
            momentum_divergence = market_data.get('momentum_divergence', False)
            
            # Count trap signals
            trap_signals = sum([
                spike_detected,
                volume_divergence,
                key_level_rejection,
                momentum_divergence
            ])
            
            if trap_signals >= 2:
                self.last_trap_time = datetime.now()
                logger.warning(f"TRAP DETECTED: {trap_signals} signals triggered")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error detecting trap: {e}")
            return False
    
    def _generate_settings(self) -> AdaptiveSettings:
        """Generate adaptive settings based on current state and regime."""
        state = self.metrics.state
        regime = self.metrics.regime
        
        settings = AdaptiveSettings()
        
        # Base position size multiplier from state
        settings.position_size_multiplier = self.size_multipliers.get(state, 1.0)
        
        # Adjust for regime
        if regime == MarketRegime.TRAP_DETECTED:
            settings.allow_new_trades = False
            settings.require_confirmation = True
            logger.warning("Trap detected - new trades blocked")
        elif regime == MarketRegime.HIGH_VOLATILITY:
            settings.position_size_multiplier *= 0.5
            settings.risk_reward_min = 2.0  # Require higher R:R in volatile markets
        elif regime == MarketRegime.LOW_VOLATILITY:
            settings.position_size_multiplier *= 1.2  # Can size up slightly
            settings.risk_reward_min = 1.5
        
        # Adjust max positions based on state
        state_position_limits = {
            DrawdownState.NORMAL: 10,
            DrawdownState.CAUTION: 7,
            DrawdownState.WARNING: 5,
            DrawdownState.DANGER: 3,
            DrawdownState.CRITICAL: 1,    # Single position only
            DrawdownState.SURVIVAL: 1,    # Single micro position
            DrawdownState.RECOVERY: 4,
        }
        settings.max_positions_allowed = state_position_limits.get(state, 5)
        
        # Adjust confidence threshold - require higher confidence when in drawdown
        state_confidence = {
            DrawdownState.NORMAL: 0.25,
            DrawdownState.CAUTION: 0.35,
            DrawdownState.WARNING: 0.50,
            DrawdownState.DANGER: 0.70,
            DrawdownState.CRITICAL: 0.85,  # Very high confidence required
            DrawdownState.SURVIVAL: 0.95,  # Near-certain signals only
            DrawdownState.RECOVERY: 0.45,
        }
        settings.confidence_threshold = state_confidence.get(state, 0.50)
        
        # Win/lose streak adjustment
        streak_adj = self._get_streak_adjustment()
        settings.position_size_multiplier *= streak_adj
        
        # Apply exponential recovery scaling
        if state == DrawdownState.RECOVERY:
            # Scale up gradually as we recover
            recovery_factor = min(1.0, self.metrics.recovery_pct / 100)
            settings.position_size_multiplier *= (0.5 + 0.5 * recovery_factor)
        
        # Ensure multiplier is within bounds
        settings.position_size_multiplier = max(0.1, min(1.5, settings.position_size_multiplier))
        
        # Block new trades in survival state only if no high-confidence opportunities
        if state == DrawdownState.SURVIVAL:
            settings.allow_new_trades = True  # Allow micro positions with very high confidence
            settings.require_confirmation = True
            settings.risk_reward_min = 5.0  # Require exceptional R:R in survival mode
            logger.critical("SURVIVAL MODE - Only highest confidence micro trades allowed!")
        elif state == DrawdownState.CRITICAL:
            settings.risk_reward_min = 3.0  # Require high R:R
            logger.warning("CRITICAL DRAWDOWN - Defensive positioning only")
        
        return settings
    
    def _get_streak_adjustment(self) -> float:
        """
        Calculate position size adjustment based on win/lose streaks.
        
        Anti-martingale: Increase size on wins, decrease on losses.
        """
        if len(self.trade_results) < 3:
            return 1.0
        
        recent = self.trade_results[-5:]  # Last 5 trades
        wins = sum(1 for r in recent if r > 0)
        losses = sum(1 for r in recent if r < 0)
        
        if wins >= 4:
            return 1.2  # Winning streak - slight increase
        elif losses >= 4:
            return 0.6  # Losing streak - significant decrease
        elif losses >= 3:
            return 0.8  # Starting to lose - decrease
        
        return 1.0
    
    def record_trade_result(self, pnl: float):
        """Record a trade result for streak tracking."""
        self.trade_results.append(pnl)
        if len(self.trade_results) > self.max_streak_history:
            self.trade_results.pop(0)
        
        logger.debug(f"Trade recorded: P&L ${pnl:.2f}, streak history: {len(self.trade_results)}")
    
    def should_close_position(self, position: Any, current_pnl: float) -> Tuple[bool, str]:
        """
        Determine if a position should be closed based on adaptive rules.
        
        Args:
            position: Position object
            current_pnl: Current P&L of the position
            
        Returns:
            Tuple of (should_close: bool, reason: str)
        """
        state = self.metrics.state
        
        # In critical state, close profitable positions to preserve capital
        if state == DrawdownState.CRITICAL and current_pnl > 0:
            return True, "Critical drawdown - taking profit to preserve capital"
        
        # Trailing equity protection - if we're about to give back locked profits
        if self.metrics.locked_profit_pct > 0:
            current_gain_pct = (
                (self.metrics.current_balance - self.metrics.initial_balance) / 
                self.metrics.initial_balance
            ) * 100 if self.metrics.initial_balance > 0 else 0
            
            if current_gain_pct < self.metrics.locked_profit_pct and current_pnl < 0:
                return True, f"Trailing equity protection - preserving {self.metrics.locked_profit_pct:.1f}% locked gains"
        
        # If in danger state and position is at breakeven or small profit, take it
        if state == DrawdownState.DANGER and current_pnl >= 0:
            return True, "Danger state - securing breakeven or better"
        
        return False, ""
    
    def get_status_report(self) -> Dict[str, Any]:
        """Get comprehensive status report for monitoring."""
        return {
            'state': self.metrics.state.value,
            'regime': self.metrics.regime.value,
            'current_balance': self.metrics.current_balance,
            'peak_balance': self.metrics.peak_balance,
            'initial_balance': self.metrics.initial_balance,
            'current_drawdown_pct': round(self.metrics.current_drawdown_pct, 2),
            'max_drawdown_pct': round(self.metrics.max_drawdown_pct, 2),
            'recovery_pct': round(self.metrics.recovery_pct, 2),
            'drawdown_duration_minutes': self.metrics.drawdown_duration_minutes,
            'trailing_equity_high': self.metrics.trailing_equity_high,
            'locked_profit_pct': round(self.metrics.locked_profit_pct, 2),
            'time_since_peak_minutes': self.metrics.time_since_peak,
            'recent_trade_count': len(self.trade_results),
            'recent_wins': sum(1 for r in self.trade_results[-10:] if r > 0),
            'recent_losses': sum(1 for r in self.trade_results[-10:] if r < 0),
        }
    def get_survival_strategy(self) -> Dict[str, Any]:
        """
        Get specific strategy parameters for survival mode.
        
        In survival mode (90%+ drawdown), the system:
        1. Only takes micro positions (0.01 lots)
        2. Requires exceptional R:R (5:1 minimum)
        3. Only trades high-probability setups
        4. Uses wider stops to survive volatility
        5. Targets small, consistent gains to rebuild
        
        Returns:
            Dict with survival-specific parameters
        """
        balance_remaining_pct = 100 - self.metrics.current_drawdown_pct
        
        # Calculate micro position based on remaining balance
        if self.metrics.current_balance > 0:
            micro_lot = max(0.01, min(0.02, self.metrics.current_balance / 10000))
        else:
            micro_lot = 0.01
        
        return {
            'mode': 'survival',
            'position_size': micro_lot,
            'max_positions': 1,
            'confidence_required': 0.95,
            'risk_reward_min': 5.0,
            'stop_loss_multiplier': 2.0,  # Wider stops
            'take_profit_multiplier': 10.0,  # Small targets
            'allowed_strategies': ['trend_following'],  # Only high-probability
            'time_filter': {
                'avoid_news': True,
                'session_filter': ['london', 'newyork'],  # High liquidity only
            },
            'recovery_target_pct': 5.0,  # Aim for 5% recovery per trade cycle
            'balance_remaining_pct': round(balance_remaining_pct, 2),
        }
    
    def calculate_recovery_position_size(self, target_recovery_pct: float = 5.0) -> float:
        """
        Calculate optimal position size for recovery.
        
        Uses a modified Kelly criterion for recovery scenarios:
        - More aggressive if win rate is high
        - Very conservative if in losing streak
        
        Args:
            target_recovery_pct: Target percentage recovery per trade
            
        Returns:
            Optimal position size as lot value
        """
        if len(self.trade_results) < 5:
            return 0.01  # Default micro lot
        
        recent = self.trade_results[-10:]
        wins = [r for r in recent if r > 0]
        losses = [r for r in recent if r < 0]
        
        if not wins or not losses:
            return 0.01
        
        win_rate = len(wins) / len(recent)
        avg_win = sum(wins) / len(wins)
        avg_loss = abs(sum(losses) / len(losses))
        
        # Modified Kelly for recovery
        if avg_loss > 0:
            kelly = win_rate - ((1 - win_rate) / (avg_win / avg_loss))
        else:
            kelly = win_rate * 0.5
        
        # In survival mode, use fractional Kelly (1/4)
        recovery_kelly = max(0.01, kelly * 0.25)
        
        # Convert to lot size based on remaining balance
        if self.metrics.current_balance > 0:
            lot_size = (self.metrics.current_balance * recovery_kelly) / 1000
            return max(0.01, min(0.05, lot_size))
        
        return 0.01


# Convenience function for integration
def create_adaptive_manager(config: Optional[Dict[str, Any]] = None) -> AdaptiveDrawdownManager:
    """Factory function to create an AdaptiveDrawdownManager."""
    return AdaptiveDrawdownManager(config)
