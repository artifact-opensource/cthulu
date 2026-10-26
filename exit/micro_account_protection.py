"""
Micro Account Profit Protection

Aggressive profit protection specifically designed for small/micro accounts.
When you're trading with $5-50, every dollar counts. This module implements:

1. **Quick Profit Lock**: Take profits early on micro accounts
2. **Scaled Trailing**: Tighter trailing stops based on account size
3. **Survival Mode**: Protect capital at all costs when equity drops
4. **Momentum Exit**: Exit when momentum shifts against position

Philosophy:
- Greed kills micro accounts
- Compound gains require capital preservation
- One reversal can wipe everything
- Lock profits, let losers run (inverse of normal)
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass

from .base import ExitStrategy, ExitSignal
from cthulu.position.manager import PositionInfo

logger = logging.getLogger(__name__)


@dataclass
class MicroAccountConfig:
    """Configuration for micro account protection."""
    # Account thresholds
    micro_account_threshold: float = 100.0  # Below this = micro account
    small_account_threshold: float = 500.0  # Below this = small account
    
    # Profit targets (as percentage of entry)
    micro_profit_target_pct: float = 0.5  # Take profit at 0.5% for micro
    small_profit_target_pct: float = 1.0  # Take profit at 1.0% for small
    normal_profit_target_pct: float = 2.0  # Take profit at 2.0% normally
    
    # Account equity thresholds for aggressive exit
    equity_gain_lock_pct: float = 50.0  # Lock in profit if equity gained 50%+
    equity_drop_exit_pct: float = 20.0  # Exit if equity drops 20% from peak
    
    # Trailing stop multipliers (lower = tighter)
    micro_trailing_mult: float = 0.3  # Very tight trailing for micro
    small_trailing_mult: float = 0.5  # Tight trailing for small
    normal_trailing_mult: float = 1.0  # Normal trailing
    
    # Momentum protection
    rsi_exit_oversold: float = 35.0  # Exit longs if RSI drops to oversold
    rsi_exit_overbought: float = 65.0  # Exit shorts if RSI rises to overbought


class MicroAccountProtection(ExitStrategy):
    """
    Aggressive profit protection for micro/small accounts.
    
    This strategy watches for:
    1. Quick profit targets based on account size
    2. Equity-based profit locking (doubled your account? Lock it!)
    3. Momentum reversal detection
    4. Account preservation emergency exits
    """
    
    def __init__(self, params: Dict[str, Any] = None):
        params = params or {}
        super().__init__(
            name="MicroAccountProtection",
            params=params,
            priority=80  # High priority - protect capital
        )
        
        # Load config
        self.config = MicroAccountConfig(
            micro_account_threshold=params.get('micro_account_threshold', 100.0),
            small_account_threshold=params.get('small_account_threshold', 500.0),
            micro_profit_target_pct=params.get('micro_profit_target_pct', 0.5),
            small_profit_target_pct=params.get('small_profit_target_pct', 1.0),
            equity_gain_lock_pct=params.get('equity_gain_lock_pct', 50.0),
            equity_drop_exit_pct=params.get('equity_drop_exit_pct', 20.0),
        )
        
        # State tracking
        self._peak_equity: Dict[int, float] = {}  # Track peak equity per position
        self._initial_equity: float = 0.0
        self._peak_total_equity: float = 0.0
        
    def should_exit(
        self,
        position: PositionInfo,
        current_data: Dict[str, Any]
    ) -> Optional[ExitSignal]:
        """
        Check if micro account protection should trigger exit.
        
        Args:
            position: Position information
            current_data: Market data including account_balance, account_equity, indicators
            
        Returns:
            ExitSignal if protection triggered, None otherwise
        """
        if not self._enabled:
            return None
            
        account_balance = current_data.get('account_balance', 0)
        account_equity = current_data.get('account_equity', account_balance)
        current_price = current_data.get('current_price', position.current_price)
        indicators = current_data.get('indicators', {})
        
        # Initialize tracking
        if self._initial_equity == 0:
            self._initial_equity = account_balance
            self._peak_total_equity = account_equity
            
        # Update peak equity
        self._peak_total_equity = max(self._peak_total_equity, account_equity)
        
        ticket = position.ticket
        if ticket not in self._peak_equity:
            self._peak_equity[ticket] = position.unrealized_pnl
        else:
            self._peak_equity[ticket] = max(self._peak_equity[ticket], position.unrealized_pnl)
        
        # Determine account tier
        account_tier = self._get_account_tier(account_balance)
        
        # Check 1: Quick Profit Target
        exit_signal = self._check_profit_target(position, current_price, account_tier)
        if exit_signal:
            return exit_signal
            
        # Check 2: Equity Gain Lock (doubled account? lock it!)
        exit_signal = self._check_equity_gain_lock(position, account_equity)
        if exit_signal:
            return exit_signal
            
        # Check 3: Equity Drop Protection
        exit_signal = self._check_equity_drop(position, account_equity)
        if exit_signal:
            return exit_signal
            
        # Check 4: Momentum Reversal
        exit_signal = self._check_momentum_reversal(position, indicators)
        if exit_signal:
            return exit_signal
            
        # Check 5: Profit Giveback Protection
        exit_signal = self._check_profit_giveback(position)
        if exit_signal:
            return exit_signal
            
        return None
        
    def _get_account_tier(self, balance: float) -> str:
        """Determine account tier based on balance."""
        if balance < self.config.micro_account_threshold:
            return "micro"
        elif balance < self.config.small_account_threshold:
            return "small"
        else:
            return "normal"
            
    def _check_profit_target(
        self,
        position: PositionInfo,
        current_price: float,
        account_tier: str
    ) -> Optional[ExitSignal]:
        """Check if quick profit target hit based on account size."""
        if position.unrealized_pnl <= 0:
            return None
            
        # Get target based on account tier
        if account_tier == "micro":
            target_pct = self.config.micro_profit_target_pct
        elif account_tier == "small":
            target_pct = self.config.small_profit_target_pct
        else:
            target_pct = self.config.normal_profit_target_pct
            
        # Calculate profit percentage
        entry_value = position.open_price * position.volume
        profit_pct = (position.unrealized_pnl / entry_value) * 100 if entry_value > 0 else 0
        
        if profit_pct >= target_pct:
            logger.info(
                f"[MicroProtection] Profit target hit for {position.ticket}: "
                f"{profit_pct:.2f}% >= {target_pct}% ({account_tier} account)"
            )
            return ExitSignal(
                ticket=position.ticket,
                reason=f"Micro account profit target ({target_pct}%) hit",
                price=current_price,
                timestamp=datetime.now(),
                strategy_name=self.name,
                confidence=0.95,
                metadata={
                    'account_tier': account_tier,
                    'profit_pct': profit_pct,
                    'target_pct': target_pct,
                    'unrealized_pnl': position.unrealized_pnl
                }
            )
        return None
        
    def _check_equity_gain_lock(
        self,
        position: PositionInfo,
        current_equity: float
    ) -> Optional[ExitSignal]:
        """Lock in profits if account equity gained significantly."""
        if self._initial_equity <= 0:
            return None
            
        equity_gain_pct = ((current_equity - self._initial_equity) / self._initial_equity) * 100
        
        if equity_gain_pct >= self.config.equity_gain_lock_pct and position.unrealized_pnl > 0:
            logger.info(
                f"[MicroProtection] Equity gain lock for {position.ticket}: "
                f"Account up {equity_gain_pct:.1f}% - locking profits"
            )
            return ExitSignal(
                ticket=position.ticket,
                reason=f"Equity gain lock ({equity_gain_pct:.1f}% gain)",
                price=position.current_price or 0,
                timestamp=datetime.now(),
                strategy_name=self.name,
                confidence=0.90,
                metadata={
                    'equity_gain_pct': equity_gain_pct,
                    'initial_equity': self._initial_equity,
                    'current_equity': current_equity,
                    'position_pnl': position.unrealized_pnl
                }
            )
        return None
        
    def _check_equity_drop(
        self,
        position: PositionInfo,
        current_equity: float
    ) -> Optional[ExitSignal]:
        """Exit if equity drops significantly from peak."""
        if self._peak_total_equity <= 0:
            return None
            
        equity_drop_pct = ((self._peak_total_equity - current_equity) / self._peak_total_equity) * 100
        
        if equity_drop_pct >= self.config.equity_drop_exit_pct:
            logger.warning(
                f"[MicroProtection] Equity drop protection for {position.ticket}: "
                f"Account down {equity_drop_pct:.1f}% from peak - emergency exit"
            )
            return ExitSignal(
                ticket=position.ticket,
                reason=f"Equity drop protection ({equity_drop_pct:.1f}% from peak)",
                price=position.current_price or 0,
                timestamp=datetime.now(),
                strategy_name=self.name,
                confidence=1.0,  # High confidence - protect capital
                metadata={
                    'equity_drop_pct': equity_drop_pct,
                    'peak_equity': self._peak_total_equity,
                    'current_equity': current_equity
                }
            )
        return None
        
    def _check_momentum_reversal(
        self,
        position: PositionInfo,
        indicators: Dict[str, Any]
    ) -> Optional[ExitSignal]:
        """Exit if momentum shifts against position."""
        rsi = indicators.get('rsi') or indicators.get('RSI')
        if rsi is None:
            return None
            
        is_long = position.side == 'BUY'
        
        # For longs: exit if RSI drops to oversold (momentum dying)
        if is_long and rsi < self.config.rsi_exit_oversold and position.unrealized_pnl > 0:
            logger.info(
                f"[MicroProtection] Momentum reversal for LONG {position.ticket}: "
                f"RSI={rsi:.1f} dropping - taking profit before reversal"
            )
            return ExitSignal(
                ticket=position.ticket,
                reason=f"Momentum reversal (RSI={rsi:.1f})",
                price=position.current_price or 0,
                timestamp=datetime.now(),
                strategy_name=self.name,
                confidence=0.85,
                metadata={'rsi': rsi, 'side': 'BUY'}
            )
            
        # For shorts: exit if RSI rises to overbought (momentum shifting up)
        if not is_long and rsi > self.config.rsi_exit_overbought and position.unrealized_pnl > 0:
            logger.info(
                f"[MicroProtection] Momentum reversal for SHORT {position.ticket}: "
                f"RSI={rsi:.1f} rising - taking profit before reversal"
            )
            return ExitSignal(
                ticket=position.ticket,
                reason=f"Momentum reversal (RSI={rsi:.1f})",
                price=position.current_price or 0,
                timestamp=datetime.now(),
                strategy_name=self.name,
                confidence=0.85,
                metadata={'rsi': rsi, 'side': 'SELL'}
            )
            
        return None
        
    def _check_profit_giveback(self, position: PositionInfo) -> Optional[ExitSignal]:
        """Exit if position gives back too much profit."""
        ticket = position.ticket
        peak_profit = self._peak_equity.get(ticket, 0)
        
        if peak_profit <= 0:
            return None
            
        current_pnl = position.unrealized_pnl
        
        # If we had significant profit and it's dropping
        if peak_profit > 0.5 and current_pnl < peak_profit * 0.5:  # Lost 50% of peak profit
            logger.info(
                f"[MicroProtection] Profit giveback for {ticket}: "
                f"Peak ${peak_profit:.2f} -> Current ${current_pnl:.2f}"
            )
            return ExitSignal(
                ticket=position.ticket,
                reason=f"Profit giveback (peak ${peak_profit:.2f})",
                price=position.current_price or 0,
                timestamp=datetime.now(),
                strategy_name=self.name,
                confidence=0.88,
                metadata={
                    'peak_profit': peak_profit,
                    'current_pnl': current_pnl,
                    'giveback_pct': ((peak_profit - current_pnl) / peak_profit) * 100
                }
            )
        return None
        
    def reset(self):
        """Reset tracking state."""
        super().reset()
        self._peak_equity.clear()
        self._initial_equity = 0.0
        self._peak_total_equity = 0.0
        
    def remove_position(self, ticket: int):
        """Remove position from tracking when closed."""
        if ticket in self._peak_equity:
            del self._peak_equity[ticket]


class SurvivalModeExit(ExitStrategy):
    """
    Emergency survival mode for micro accounts.
    
    When account drops below critical threshold, this aggressively
    closes positions to preserve remaining capital.
    """
    
    def __init__(self, params: Dict[str, Any] = None):
        params = params or {}
        super().__init__(
            name="SurvivalMode",
            params=params,
            priority=100  # Highest priority
        )
        
        self.critical_balance = params.get('critical_balance', 2.0)  # $2 = critical
        self.survival_margin_pct = params.get('survival_margin_pct', 30.0)  # 30% margin = survival mode
        
    def should_exit(
        self,
        position: PositionInfo,
        current_data: Dict[str, Any]
    ) -> Optional[ExitSignal]:
        """Check if survival mode should trigger immediate exit."""
        if not self._enabled:
            return None
            
        account_balance = current_data.get('account_balance', 0)
        account_equity = current_data.get('account_equity', account_balance)
        margin_level = current_data.get('margin_level', 100)
        
        # Critical balance check
        if account_equity <= self.critical_balance:
            logger.critical(
                f"[SURVIVAL MODE] Critical balance ${account_equity:.2f} - "
                f"EMERGENCY EXIT for {position.ticket}"
            )
            return ExitSignal(
                ticket=position.ticket,
                reason=f"SURVIVAL MODE: Critical balance (${account_equity:.2f})",
                price=position.current_price or 0,
                timestamp=datetime.now(),
                strategy_name=self.name,
                confidence=1.0,
                metadata={
                    'account_equity': account_equity,
                    'critical_threshold': self.critical_balance,
                    'emergency': True
                }
            )
            
        # Low margin check
        if margin_level < self.survival_margin_pct:
            logger.critical(
                f"[SURVIVAL MODE] Low margin {margin_level:.1f}% - "
                f"EMERGENCY EXIT for {position.ticket}"
            )
            return ExitSignal(
                ticket=position.ticket,
                reason=f"SURVIVAL MODE: Low margin ({margin_level:.1f}%)",
                price=position.current_price or 0,
                timestamp=datetime.now(),
                strategy_name=self.name,
                confidence=1.0,
                metadata={
                    'margin_level': margin_level,
                    'survival_threshold': self.survival_margin_pct,
                    'emergency': True
                }
            )
            
        return None
