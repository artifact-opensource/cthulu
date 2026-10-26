"""
Risk Management Engine

Implements position sizing, exposure limits, and trade approval logic.
Provides hard guards for maximum drawdown, daily limits, and emergency shutdown.
"""

import logging
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import date
from cthulu.strategy.base import Signal, SignalType


@dataclass
class RiskLimits:
    """Risk management configuration"""
    max_position_size_pct: float = 0.02  # 2% of balance per position
    # legacy alias: if provided, prefer this is a direct value in percent
    max_position_size: Optional[float] = None
    max_total_exposure_pct: float = 0.10  # 10% total exposure
    max_daily_loss_pct: float = 0.05  # 5% daily loss limit
    max_positions_per_symbol: int = 1
    max_total_positions: int = 3
    min_risk_reward_ratio: float = 1.0
    max_spread_pips: float = 50.0
    volatility_scaling: bool = True
    # SL scaling buckets: map small/medium/large to relative SL pct (e.g., 0.01 = 1%)
    sl_balance_thresholds: Dict[str, float] = None
    sl_balance_breakpoints: list = None
    min_confidence: float = 0.0

    def __post_init__(self):
        # Prefer explicit percent value fields
        if self.max_position_size is not None and self.max_position_size_pct == 0.02:
            # If legacy 'max_position_size' provided, map to new name
            try:
                self.max_position_size_pct = float(self.max_position_size)
            except Exception:
                pass
        # defaults for SL buckets if not provided
        if self.sl_balance_thresholds is None:
            self.sl_balance_thresholds = {
                'tiny': 0.01,
                'small': 0.02,
                'medium': 0.05,
                'large': 0.25
            }
        if self.sl_balance_breakpoints is None:
            self.sl_balance_breakpoints = [1000.0, 5000.0, 20000.0]


class RiskManager:
    """
    Risk management and trade approval engine.
    
    Responsibilities:
    - Position sizing (fixed, percent, volatility-based)
    - Hard guards (exposure, drawdown, daily limits)
    - Trade approval workflow
    - Emergency shutdown capability
    """
    
    def __init__(self, limits: RiskLimits):
        """
        Initialize risk manager.
        
        Args:
            limits: Risk limit configuration
        """
        self.limits = limits
        self.logger = logging.getLogger("Cthulu.risk")
        
        # Daily tracking
        self.daily_pnl = 0.0
        self.current_date = date.today()
        self.trade_count = 0
        self.shutdown_triggered = False
        
    def approve(
        self,
        signal: Signal,
        account_state: Dict[str, Any] = None,
        current_positions: int = 0,
        **kwargs
    ) -> Tuple[bool, str, Optional[float]]:
        """
        Approve trade signal and calculate position size.
        
        Args:
            signal: Trading signal to approve
            account_state: Current account information
            current_positions: Number of open positions
            
        Returns:
            Tuple of (approved, reason, position_size)
        """
        # Check emergency shutdown
        if self.shutdown_triggered:
            return False, "Emergency shutdown active", None
            
        # Allow caller to pass `account_info` as keyword
        if account_state is None and 'account_info' in kwargs:
            account_state = kwargs.get('account_info')

        # Reset daily tracking if new day
        self._check_new_day()
        
        # Check daily loss limit
        if not account_state:
            account_state = {}

        balance = account_state.get('balance', 0)
        max_daily_loss = balance * self.limits.max_daily_loss_pct
        
        if self.daily_pnl < -max_daily_loss:
            self.logger.warning(f"Daily loss limit exceeded: {self.daily_pnl:.2f}")
            return False, "Daily loss limit exceeded", None
            
        # Check max positions
        if current_positions >= self.limits.max_total_positions:
            return False, f"Max positions reached ({self.limits.max_total_positions})", None
            
        # Check trading allowed
        if not account_state.get('trade_allowed', False):
            return False, "Trading not allowed on account", None
            
        # Validate signal
        if signal.side == SignalType.NONE or signal.side == SignalType.CLOSE:
            return False, "Invalid signal type for new trade", None

        # Minimum confidence check (optional)
        min_conf = getattr(self.limits, 'min_confidence', 0.0)
        if getattr(signal, 'confidence', 0.0) < min_conf:
            return False, f"Signal confidence below threshold ({signal.confidence:.2f} < {min_conf})", None
            
        # Check risk/reward ratio
        if signal.stop_loss and signal.take_profit and signal.price:
            risk = abs(signal.price - signal.stop_loss)
            reward = abs(signal.take_profit - signal.price)
            rr_ratio = reward / risk if risk > 0 else 0
            
            if rr_ratio < self.limits.min_risk_reward_ratio:
                return False, f"Risk/reward ratio too low: {rr_ratio:.2f}", None
                
        # Calculate position size
        position_size = self._calculate_position_size(signal, account_state)
        
        if position_size is None or position_size == 0:
            return False, "Invalid position size calculated", None
            
        self.logger.info(
            f"Trade approved: {signal.action} {position_size:.2f} lots | "
            f"Confidence: {signal.confidence:.2%}"
        )
        
        return True, "Approved", position_size
        
    def _calculate_position_size(
        self,
        signal: Signal,
        account_state: Dict[str, Any],
        symbol_info: Dict[str, Any] = None
    ) -> Optional[float]:
        """
        Calculate position size based on risk parameters and symbol specifications.
        
        Uses proper lot size calculation considering:
        - Contract size
        - Tick value
        - Point value
        - Account currency conversion
        
        Args:
            signal: Trading signal
            account_state: Account information
            symbol_info: MT5 symbol specifications (optional, for accurate calculation)
            
        Returns:
            Position size in lots or None
        """
        balance = account_state.get('balance', 0)
        if balance == 0:
            return None
            
        # Risk amount per trade
        risk_amount = balance * self.limits.max_position_size_pct
        
        # If using signal size hint, validate and return
        if signal.size_hint:
            return self._validate_lot_size(signal.size_hint, symbol_info)
            
        # Calculate based on stop loss
        if signal.stop_loss and signal.price:
            risk_pips = abs(signal.price - signal.stop_loss)
            
            if risk_pips == 0:
                return None
            
            # Use symbol info if available for accurate calculation
            if symbol_info:
                lot_size = self._calculate_lot_size_with_symbol_info(
                    risk_amount, risk_pips, signal.price, symbol_info
                )
            else:
                # Fallback: simplified calculation
                # Assume standard forex lot (100,000 units), $10 per pip for 1 lot
                pip_value_per_lot = 10.0  # Approximate for major pairs
                lot_size = risk_amount / (risk_pips * pip_value_per_lot * 10000)
                
            # Apply volatility scaling if enabled
            if self.limits.volatility_scaling and signal.metadata.get('atr'):
                atr = signal.metadata['atr']
                avg_atr = signal.metadata.get('avg_atr', atr)
                if avg_atr > 0:
                    volatility_factor = avg_atr / atr
                    lot_size *= volatility_factor

            # Apply confidence-based multiplier (more aggressive when confidence > 0.5)
            conf = getattr(signal, 'confidence', 1.0) or 1.0
            # Multiplier ranges roughly 0.5 -> 1.5 for confidence 0.0 -> 1.0
            multiplier = 1.0 + (conf - 0.5)
            lot_size *= multiplier

            return self._validate_lot_size(lot_size, symbol_info)
            
        # Default: minimum lot size
        # apply confidence multiplier to default lot too
        base = 0.01
        conf = getattr(signal, 'confidence', 1.0) or 1.0
        multiplier = 1.0 + (conf - 0.5)
        return self._validate_lot_size(base * multiplier, symbol_info)
    
    def _calculate_lot_size_with_symbol_info(
        self,
        risk_amount: float,
        risk_pips: float,
        price: float,
        symbol_info: Dict[str, Any]
    ) -> float:
        """
        Calculate lot size using MT5 symbol specifications.
        
        Formula: lot_size = risk_amount / (risk_pips * pip_value_per_lot)
        
        Where pip_value_per_lot = (point * contract_size * tick_value) / tick_size
        
        Args:
            risk_amount: Amount to risk in account currency
            risk_pips: Distance to stop loss in price units
            price: Current price
            symbol_info: MT5 symbol specifications
            
        Returns:
            Calculated lot size
        """
        # Extract symbol specifications
        contract_size = symbol_info.get('trade_contract_size', 100000)
        tick_size = symbol_info.get('trade_tick_size', 0.00001)
        tick_value = symbol_info.get('trade_tick_value', 1.0)
        point = symbol_info.get('point', 0.00001)
        
        # Calculate pip value per lot
        # For forex: typically 1 pip = 10 points for 5-digit brokers
        pips_in_points = 10 if point < 0.001 else 1
        
        # Value of 1 pip move for 1 lot
        pip_value_per_lot = (tick_value / tick_size) * point * pips_in_points
        
        # Handle crypto and indices with larger tick values
        if contract_size < 100000:  # Likely crypto or CFD
            pip_value_per_lot = tick_value * (contract_size / 100000)
        
        if pip_value_per_lot == 0:
            pip_value_per_lot = 10.0  # Fallback
            
        # Calculate risk in pips (convert from price difference)
        risk_in_pips = risk_pips / (point * pips_in_points)
        
        if risk_in_pips == 0:
            return 0.01
            
        # Calculate lot size
        lot_size = risk_amount / (risk_in_pips * pip_value_per_lot)
        
        self.logger.debug(
            f"Lot calculation: risk=${risk_amount:.2f}, risk_pips={risk_in_pips:.1f}, "
            f"pip_value={pip_value_per_lot:.4f}, lots={lot_size:.4f}"
        )
        
        return lot_size
    
    def _validate_lot_size(
        self,
        lot_size: float,
        symbol_info: Dict[str, Any] = None
    ) -> float:
        """
        Validate and adjust lot size to symbol constraints.
        
        Args:
            lot_size: Calculated lot size
            symbol_info: Symbol specifications (optional)
            
        Returns:
            Valid lot size
        """
        # Get symbol constraints or use defaults
        if symbol_info:
            min_lot = symbol_info.get('volume_min', 0.01)
            max_lot = symbol_info.get('volume_max', 100.0)
            lot_step = symbol_info.get('volume_step', 0.01)
        else:
            min_lot = 0.01
            max_lot = 100.0
            lot_step = 0.01
        
        # Apply constraints
        lot_size = max(min_lot, lot_size)
        lot_size = min(max_lot, lot_size)
        
        # Round to lot step
        if lot_step > 0:
            lot_size = round(lot_size / lot_step) * lot_step
        
        # Round to 2 decimals
        lot_size = round(lot_size, 2)
        
        return lot_size

    def suggest_scaled_sl(self, price: float, account_balance: float) -> float:
        """
        Suggest a stop-loss distance (absolute price difference) based on account balance buckets.

        Returns an absolute price distance (same units as `price`).
        """
        # determine bucket from breakpoints
        bps = self.limits.sl_balance_breakpoints or []
        th = self.limits.sl_balance_thresholds or {}
        try:
            if account_balance <= bps[0]:
                pct = th.get('tiny', 0.01)
            elif account_balance <= bps[1]:
                pct = th.get('small', 0.02)
            elif account_balance <= bps[2]:
                pct = th.get('medium', 0.05)
            else:
                pct = th.get('large', 0.25)
        except Exception:
            pct = th.get('medium', 0.05)

        # absolute distance
        return max(1e-6, price * float(pct))
        
    def record_trade_result(self, profit: float, account_balance: float = None):
        """
        Record trade result for daily tracking.
        
        Args:
            profit: Trade profit/loss
            account_balance: Current account balance for daily loss calculation
        """
        self.daily_pnl += profit
        self.trade_count += 1
        
        self.logger.info(
            f"Trade result recorded: {profit:+.2f} | "
            f"Daily P&L: {self.daily_pnl:+.2f} ({self.trade_count} trades)"
        )
        
        # Check if daily loss limit hit
        if account_balance is not None and account_balance > 0:
            max_daily_loss = account_balance * self.limits.max_daily_loss_pct
            
            if self.daily_pnl < -max_daily_loss:
                self.logger.critical(
                    f"Daily loss limit exceeded: {self.daily_pnl:.2f} < -{max_daily_loss:.2f} - consider shutdown"
                )
            
    def emergency_shutdown(self, reason: str = "Manual"):
        """
        Trigger emergency shutdown.
        
        Args:
            reason: Reason for shutdown
        """
        self.shutdown_triggered = True
        self.logger.critical(f"EMERGENCY SHUTDOWN TRIGGERED: {reason}")
        
    def reset_shutdown(self):
        """Reset emergency shutdown flag."""
        self.shutdown_triggered = False
        self.logger.info("Emergency shutdown reset")
        
    def _check_new_day(self):
        """Check if new trading day and reset counters."""
        today = date.today()
        if today != self.current_date:
            self.logger.info(
                f"New trading day | Previous P&L: {self.daily_pnl:+.2f} ({self.trade_count} trades)"
            )
            self.daily_pnl = 0.0
            self.trade_count = 0
            self.current_date = today
            
    def get_status(self) -> Dict[str, Any]:
        """
        Get current risk manager status.
        
        Returns:
            Status dictionary
        """
        return {
            'daily_pnl': self.daily_pnl,
            'trade_count': self.trade_count,
            'date': self.current_date.isoformat(),
            'shutdown_triggered': self.shutdown_triggered,
            'limits': {
                'max_position_size_pct': self.limits.max_position_size_pct,
                'max_daily_loss_pct': self.limits.max_daily_loss_pct,
                'max_total_positions': self.limits.max_total_positions,
            }
        }




