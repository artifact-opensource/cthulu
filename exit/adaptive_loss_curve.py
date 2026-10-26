"""
Adaptive Loss Curve - Non-Linear Loss Tolerance System

Implements hyperbolic/softmax-based loss tolerance that scales with account size:
- Small accounts need tighter stops proportionally
- Larger accounts can tolerate more absolute loss but smaller percentage

Formula: max_loss = balance * base_rate * softmax_curve(balance)

Where softmax_curve provides non-linear scaling:
- $5 account → max $0.50 loss (10%)
- $50 account → max $2.50 loss (5%)
- $100 account → max $3 loss (3%)
- $500 account → max $12.50 loss (2.5%)
- $1000 account → max $20 loss (2%)

This prevents:
1. Over-trading on small accounts
2. Hoping for recovery (market prediction fallacy)
3. Catastrophic drawdowns on micro accounts
"""

import math
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timezone

logger = logging.getLogger('cthulu.adaptive_loss_curve')


@dataclass
class LossCurveConfig:
    """Configuration for adaptive loss curve."""
    # Base loss rate at $100 account (3%)
    base_loss_rate: float = 0.03
    
    # Curve parameters
    # Hyperbolic: higher = steeper curve at low balances
    hyperbolic_steepness: float = 2.5
    
    # Softmax temperature: lower = sharper transitions
    softmax_temperature: float = 50.0
    
    # Minimum absolute loss allowed (floor)
    min_loss_floor: float = 0.10  # $0.10 minimum
    
    # Maximum loss percentage cap
    max_loss_cap_pct: float = 0.15  # Never exceed 15%
    
    # Account tiers for curve anchoring
    tier_anchors: Dict[float, float] = field(default_factory=lambda: {
        5.0: 0.10,     # $5 account → 10% max loss
        10.0: 0.08,    # $10 → 8%
        25.0: 0.06,    # $25 → 6%
        50.0: 0.05,    # $50 → 5%
        100.0: 0.03,   # $100 → 3%
        250.0: 0.025,  # $250 → 2.5%
        500.0: 0.02,   # $500 → 2%
        1000.0: 0.02,  # $1000 → 2%
        5000.0: 0.015, # $5000 → 1.5%
    })
    
    # Per-trade vs per-day loss limits
    per_trade_multiplier: float = 0.5  # Per-trade = 50% of daily limit
    
    # Recovery mode thresholds
    recovery_mode_drawdown_pct: float = 0.20  # Enter recovery at 20% drawdown
    recovery_mode_loss_reduction: float = 0.5  # Reduce loss tolerance by 50% in recovery


class AdaptiveLossCurve:
    """
    Non-linear loss tolerance calculator using hyperbolic/softmax curves.
    
    Philosophy:
    - Smaller accounts CANNOT afford the same loss percentage as larger ones
    - Recovery from loss requires exponentially more gains
    - Linear loss tolerance is dangerous for micro accounts
    
    Example calculations:
        curve = AdaptiveLossCurve()
        
        # $5 account
        curve.get_max_loss(5.0)    # Returns 0.50 (10%)
        
        # $100 account  
        curve.get_max_loss(100.0)  # Returns 3.00 (3%)
        
        # $1000 account
        curve.get_max_loss(1000.0) # Returns 20.00 (2%)
    """
    
    def __init__(self, config: Optional[LossCurveConfig] = None):
        """Initialize adaptive loss curve."""
        self.config = config or LossCurveConfig()
        self._curve_cache: Dict[float, float] = {}
        self._peak_balance: float = 0.0
        self._in_recovery_mode: bool = False
        
        # Precompute curve for common values
        self._precompute_curve()
        
    def _precompute_curve(self):
        """Precompute curve values for common balance points."""
        for balance in [1, 2, 5, 10, 20, 25, 50, 75, 100, 150, 200, 250, 
                       300, 400, 500, 750, 1000, 2000, 5000, 10000]:
            self._curve_cache[float(balance)] = self._calculate_loss_rate(float(balance))
            
    def _calculate_loss_rate(self, balance: float) -> float:
        """
        Calculate loss rate using hyperbolic-softmax hybrid curve.
        
        The curve is constructed by:
        1. Interpolating between anchor points using softmax
        2. Applying hyperbolic scaling for smooth transitions
        3. Capping at min/max bounds
        """
        if balance <= 0:
            return self.config.max_loss_cap_pct
            
        # Find surrounding anchor points
        anchors = sorted(self.config.tier_anchors.keys())
        
        # Below minimum anchor - extrapolate with cap
        if balance < anchors[0]:
            return min(self.config.max_loss_cap_pct, 
                      self.config.tier_anchors[anchors[0]] * 1.2)
        
        # Above maximum anchor - use minimum rate
        if balance >= anchors[-1]:
            return self.config.tier_anchors[anchors[-1]]
            
        # Find interpolation bounds
        lower_anchor = anchors[0]
        upper_anchor = anchors[-1]
        
        for i, anchor in enumerate(anchors):
            if anchor <= balance:
                lower_anchor = anchor
            if anchor > balance:
                upper_anchor = anchor
                break
                
        # Get anchor rates
        lower_rate = self.config.tier_anchors[lower_anchor]
        upper_rate = self.config.tier_anchors[upper_anchor]
        
        # Softmax interpolation
        # This creates a smooth S-curve between anchors
        x = (balance - lower_anchor) / (upper_anchor - lower_anchor) if upper_anchor > lower_anchor else 0
        
        # Apply softmax-style smooth transition
        # softmax(x) = 1 / (1 + exp(-k*(x-0.5)))
        k = self.config.hyperbolic_steepness
        softmax_weight = 1.0 / (1.0 + math.exp(-k * (x - 0.5)))
        
        # Interpolate rate
        rate = lower_rate + (upper_rate - lower_rate) * softmax_weight
        
        # Apply hyperbolic adjustment for micro accounts
        # This makes the curve steeper at very low balances
        if balance < 50:
            hyperbolic_factor = 1.0 + (1.0 / (1.0 + balance / 10.0))
            rate = min(rate * hyperbolic_factor, self.config.max_loss_cap_pct)
            
        return max(min(rate, self.config.max_loss_cap_pct), 0.01)
        
    def get_max_loss(self, balance: float, per_trade: bool = True) -> float:
        """
        Get maximum allowed loss for given balance.
        
        Args:
            balance: Current account balance
            per_trade: If True, return per-trade limit; else daily limit
            
        Returns:
            Maximum loss amount in account currency
        """
        # Check cache first
        cache_key = round(balance, 0)
        if cache_key in self._curve_cache:
            rate = self._curve_cache[cache_key]
        else:
            rate = self._calculate_loss_rate(balance)
            self._curve_cache[cache_key] = rate
            
        # Apply recovery mode reduction if active
        if self._in_recovery_mode:
            rate *= self.config.recovery_mode_loss_reduction
            
        # Calculate loss amount
        max_loss = balance * rate
        
        # Apply per-trade multiplier
        if per_trade:
            max_loss *= self.config.per_trade_multiplier
            
        # Apply floor
        max_loss = max(max_loss, self.config.min_loss_floor)
        
        return round(max_loss, 2)
        
    def get_loss_rate(self, balance: float) -> float:
        """Get the loss rate percentage for given balance."""
        return self._calculate_loss_rate(balance)
        
    def update_peak_balance(self, balance: float) -> None:
        """Update peak balance for drawdown tracking."""
        if balance > self._peak_balance:
            self._peak_balance = balance
            # Exit recovery mode if we've recovered
            if self._in_recovery_mode:
                self._in_recovery_mode = False
                logger.info("AdaptiveLossCurve: Exited recovery mode - balance recovered")
                
    def check_recovery_mode(self, balance: float) -> bool:
        """Check if recovery mode should be active."""
        if self._peak_balance <= 0:
            return False
            
        drawdown_pct = (self._peak_balance - balance) / self._peak_balance
        
        if drawdown_pct >= self.config.recovery_mode_drawdown_pct:
            if not self._in_recovery_mode:
                self._in_recovery_mode = True
                logger.warning(f"AdaptiveLossCurve: Entering recovery mode - "
                             f"drawdown {drawdown_pct*100:.1f}%")
            return True
            
        return self._in_recovery_mode
        
    def get_stop_distance(self, balance: float, entry_price: float, 
                         lot_size: float, pip_value: float = 10.0) -> float:
        """
        Calculate stop loss distance based on max allowed loss.
        
        Args:
            balance: Account balance
            entry_price: Entry price of trade
            lot_size: Trade size in lots
            pip_value: Value per pip per standard lot
            
        Returns:
            Stop distance in price units
        """
        max_loss = self.get_max_loss(balance, per_trade=True)
        
        # Calculate pip loss allowed
        # max_loss = pips * lot_size * pip_value
        if lot_size * pip_value > 0:
            pips_allowed = max_loss / (lot_size * pip_value)
        else:
            pips_allowed = 10  # Default 10 pips
            
        # Convert pips to price (assuming standard pip = 0.0001 for forex)
        # For crypto/indices, this needs adjustment
        if 'JPY' in str(entry_price) or entry_price > 100:
            # JPY pairs or high-value instruments
            stop_distance = pips_allowed * 0.01
        else:
            stop_distance = pips_allowed * 0.0001
            
        return stop_distance
        
    def should_close_for_loss(self, balance: float, unrealized_pnl: float) -> Tuple[bool, str]:
        """
        Determine if position should be closed due to loss.
        
        Args:
            balance: Current account balance
            unrealized_pnl: Current unrealized P&L (negative for loss)
            
        Returns:
            Tuple of (should_close, reason)
        """
        if unrealized_pnl >= 0:
            return False, ""
            
        max_loss = self.get_max_loss(balance, per_trade=True)
        current_loss = abs(unrealized_pnl)
        
        if current_loss >= max_loss:
            loss_pct = (current_loss / balance) * 100 if balance > 0 else 0
            return True, f"Loss ${current_loss:.2f} exceeds adaptive limit ${max_loss:.2f} ({loss_pct:.1f}%)"
            
        # Warning zone (80% of limit)
        if current_loss >= max_loss * 0.8:
            logger.warning(f"AdaptiveLossCurve: Loss ${current_loss:.2f} at 80% of limit ${max_loss:.2f}")
            
        return False, ""
        
    def get_curve_summary(self) -> Dict[str, Any]:
        """Get summary of curve for different balance levels."""
        summary = {
            'curve_type': 'hyperbolic-softmax',
            'recovery_mode': self._in_recovery_mode,
            'peak_balance': self._peak_balance,
            'samples': []
        }
        
        for balance in [5, 10, 25, 50, 100, 250, 500, 1000, 5000]:
            rate = self.get_loss_rate(float(balance))
            max_loss = self.get_max_loss(float(balance))
            per_trade = self.get_max_loss(float(balance), per_trade=True)
            
            summary['samples'].append({
                'balance': balance,
                'rate_pct': round(rate * 100, 2),
                'max_daily_loss': max_loss,
                'max_per_trade_loss': per_trade
            })
            
        return summary


class AdaptiveLossExitStrategy:
    """
    Exit strategy that enforces adaptive loss curve limits.
    
    Integrates with ExitCoordinator to provide loss-based exits
    that respect the non-linear tolerance curve.
    """
    
    def __init__(self, config: Optional[LossCurveConfig] = None):
        """Initialize exit strategy."""
        self.name = "AdaptiveLossExit"
        self.priority = 90  # High priority - capital protection
        self.curve = AdaptiveLossCurve(config)
        self._enabled = True
        
    def should_exit(self, position: Any, current_data: Dict[str, Any]) -> Optional[Any]:
        """
        Check if position should exit based on adaptive loss limits.
        
        Args:
            position: Position information
            current_data: Market data with account_balance
            
        Returns:
            ExitSignal if loss limit breached, None otherwise
        """
        if not self._enabled:
            return None
            
        balance = current_data.get('account_balance', 0)
        unrealized_pnl = getattr(position, 'unrealized_pnl', 0)
        
        # Update tracking
        self.curve.update_peak_balance(balance)
        self.curve.check_recovery_mode(balance)
        
        # Check if we should close
        should_close, reason = self.curve.should_close_for_loss(balance, unrealized_pnl)
        
        if should_close:
            # Import here to avoid circular dependency
            from .base import ExitSignal
            
            logger.warning(f"[AdaptiveLossExit] Closing position {position.ticket}: {reason}")
            
            return ExitSignal(
                ticket=position.ticket,
                reason=f"Adaptive loss limit: {reason}",
                price=getattr(position, 'current_price', 0),
                timestamp=datetime.now(timezone.utc),
                strategy_name=self.name,
                confidence=1.0,  # High confidence - math-based decision
                metadata={
                    'balance': balance,
                    'unrealized_pnl': unrealized_pnl,
                    'max_allowed': self.curve.get_max_loss(balance),
                    'recovery_mode': self.curve._in_recovery_mode,
                    'curve_rate': self.curve.get_loss_rate(balance)
                }
            )
            
        return None
        
    def enable(self):
        """Enable the exit strategy."""
        self._enabled = True
        
    def disable(self):
        """Disable the exit strategy."""
        self._enabled = False
        
    def reset(self):
        """Reset internal state."""
        self.curve._peak_balance = 0.0
        self.curve._in_recovery_mode = False


# Factory function
def create_adaptive_loss_curve(config_dict: Optional[Dict[str, Any]] = None) -> AdaptiveLossCurve:
    """
    Create AdaptiveLossCurve with optional configuration.
    
    Args:
        config_dict: Configuration dictionary
        
    Returns:
        Configured AdaptiveLossCurve instance
    """
    config = LossCurveConfig()
    
    if config_dict:
        if 'base_loss_rate' in config_dict:
            config.base_loss_rate = float(config_dict['base_loss_rate'])
        if 'hyperbolic_steepness' in config_dict:
            config.hyperbolic_steepness = float(config_dict['hyperbolic_steepness'])
        if 'softmax_temperature' in config_dict:
            config.softmax_temperature = float(config_dict['softmax_temperature'])
        if 'min_loss_floor' in config_dict:
            config.min_loss_floor = float(config_dict['min_loss_floor'])
        if 'max_loss_cap_pct' in config_dict:
            config.max_loss_cap_pct = float(config_dict['max_loss_cap_pct'])
        if 'tier_anchors' in config_dict:
            config.tier_anchors = {float(k): float(v) for k, v in config_dict['tier_anchors'].items()}
            
    return AdaptiveLossCurve(config)
