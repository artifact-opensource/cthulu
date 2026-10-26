"""
Profit Scaling Exit Strategy

Intelligent partial profit taking with position scaling:
- Close 25-35% at first profit tier
- Close another 25-35% at second tier
- Let remaining position run with trailing protection

This approach:
1. Locks in guaranteed profits early
2. Reduces risk exposure as profit grows
3. Allows remaining position to capture extended moves
4. Adapts scaling based on account size and volatility

Philosophy:
- "You can't go broke taking profits"
- Scale out of winners, not all at once
- Let house money ride
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

from .base import ExitStrategy, ExitSignal
from cthulu.position.manager import PositionInfo

logger = logging.getLogger(__name__)


class ScaleTier(Enum):
    """Profit tier levels for scaling out."""
    INITIAL = "initial"      # No scaling yet
    TIER_1 = "tier_1"        # First profit target hit
    TIER_2 = "tier_2"        # Second profit target hit
    TIER_3 = "tier_3"        # Third profit target hit (runner)
    COMPLETE = "complete"    # Fully scaled out


@dataclass
class ScaleConfig:
    """Configuration for profit scaling."""
    # Profit targets as percentage of entry price
    tier_1_profit_pct: float = 0.3   # First scale at 0.3% profit
    tier_2_profit_pct: float = 0.6   # Second scale at 0.6% profit
    tier_3_profit_pct: float = 1.0   # Third scale at 1.0% profit
    
    # Volume to close at each tier (as percentage of remaining)
    tier_1_close_pct: float = 30.0   # Close 30% at tier 1
    tier_2_close_pct: float = 35.0   # Close 35% of remaining at tier 2
    tier_3_close_pct: float = 50.0   # Close 50% of remaining at tier 3
    
    # Account size thresholds as RATIO of initial balance (dynamic, not hardcoded)
    # These are multipliers: micro = below 0.2x initial, small = below 0.5x initial
    micro_ratio_threshold: float = 0.2   # Below 20% of initial = micro mode
    small_ratio_threshold: float = 0.5   # Below 50% of initial = small mode

    # Legacy absolute account thresholds (useful for small/micro quick detection)
    # Values are in account currency units (e.g., USD) and take precedence when provided
    micro_account_threshold: float = 100.0
    small_account_threshold: float = 500.0
    
    # Micro account adjustments (tighter targets) - ATR-based multipliers
    micro_tier_1_atr_mult: float = 0.5   # First tier at 0.5x ATR
    micro_tier_2_atr_mult: float = 1.0   # Second tier at 1.0x ATR
    micro_tier_3_atr_mult: float = 1.5   # Third tier at 1.5x ATR
    
    # Small account adjustments - ATR-based multipliers
    small_tier_1_atr_mult: float = 0.75
    small_tier_2_atr_mult: float = 1.25
    small_tier_3_atr_mult: float = 2.0
    
    # Normal account - ATR-based multipliers
    normal_tier_1_atr_mult: float = 1.0
    normal_tier_2_atr_mult: float = 2.0
    normal_tier_3_atr_mult: float = 3.0
    
    # Legacy percentage-based thresholds (fallback if no ATR)
    micro_tier_1_pct: float = 0.15   # Tighter first tier for micro
    micro_tier_2_pct: float = 0.30
    micro_tier_3_pct: float = 0.50
    small_tier_1_pct: float = 0.20
    small_tier_2_pct: float = 0.40
    small_tier_3_pct: float = 0.70
    
    # Giveback protection thresholds (configurable, not hardcoded)
    tier_1_max_giveback_pct: float = 60.0   # Allow 60% giveback at tier 1
    tier_2_max_giveback_pct: float = 50.0   # Allow 50% giveback at tier 2
    tier_3_max_giveback_pct: float = 40.0   # Allow 40% giveback for runner
    default_max_giveback_pct: float = 70.0  # Default giveback tolerance
    
    # Dynamic adjustments
    volatility_adjust: bool = True   # Adjust targets based on ATR
    momentum_adjust: bool = True     # Adjust based on momentum strength


@dataclass
class PositionScaleState:
    """Track scaling state for a position."""
    ticket: int
    original_volume: float
    current_tier: ScaleTier = ScaleTier.INITIAL
    scales_executed: List[Dict[str, Any]] = field(default_factory=list)
    peak_profit: float = 0.0
    peak_profit_pct: float = 0.0
    entry_price: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    
    @property
    def total_scaled_volume(self) -> float:
        """Total volume already scaled out."""
        return sum(s.get('volume', 0) for s in self.scales_executed)
    
    @property
    def remaining_volume_pct(self) -> float:
        """Percentage of original volume remaining."""
        if self.original_volume <= 0:
            return 0
        return ((self.original_volume - self.total_scaled_volume) / self.original_volume) * 100


class ProfitScalingExit(ExitStrategy):
    """
    Intelligent profit scaling strategy.
    
    Takes partial profits at predetermined levels while letting
    remaining position run for larger gains.
    
    Features:
    - Multi-tier profit targets
    - Account-size adaptive targets
    - Volatility-adjusted scaling
    - Momentum-aware adjustments
    - Never gives back significant profits
    """
    
    def __init__(self, params: Dict[str, Any] = None):
        params = params or {}
        super().__init__(
            name="ProfitScaling",
            params=params,
            priority=55  # Medium-high priority
        )
        
        # Load configuration with dynamic (not hardcoded) defaults
        self.config = ScaleConfig(
            tier_1_profit_pct=params.get('tier_1_profit_pct', 0.3),
            tier_2_profit_pct=params.get('tier_2_profit_pct', 0.6),
            tier_3_profit_pct=params.get('tier_3_profit_pct', 1.0),
            tier_1_close_pct=params.get('tier_1_close_pct', 30.0),
            tier_2_close_pct=params.get('tier_2_close_pct', 35.0),
            tier_3_close_pct=params.get('tier_3_close_pct', 50.0),
            # Dynamic ratio-based thresholds (no hardcoded dollar amounts)
            micro_ratio_threshold=params.get('micro_ratio_threshold', 0.2),
            small_ratio_threshold=params.get('small_ratio_threshold', 0.5),
            # ATR multipliers for each tier (dynamic)
            micro_tier_1_atr_mult=params.get('micro_tier_1_atr_mult', 0.5),
            micro_tier_2_atr_mult=params.get('micro_tier_2_atr_mult', 1.0),
            micro_tier_3_atr_mult=params.get('micro_tier_3_atr_mult', 1.5),
            small_tier_1_atr_mult=params.get('small_tier_1_atr_mult', 0.75),
            small_tier_2_atr_mult=params.get('small_tier_2_atr_mult', 1.25),
            small_tier_3_atr_mult=params.get('small_tier_3_atr_mult', 2.0),
            normal_tier_1_atr_mult=params.get('normal_tier_1_atr_mult', 1.0),
            normal_tier_2_atr_mult=params.get('normal_tier_2_atr_mult', 2.0),
            normal_tier_3_atr_mult=params.get('normal_tier_3_atr_mult', 3.0),
            # Percentage fallbacks
            micro_tier_1_pct=params.get('micro_tier_1_pct', 0.15),
            micro_tier_2_pct=params.get('micro_tier_2_pct', 0.30),
            micro_tier_3_pct=params.get('micro_tier_3_pct', 0.50),
            small_tier_1_pct=params.get('small_tier_1_pct', 0.20),
            small_tier_2_pct=params.get('small_tier_2_pct', 0.40),
            small_tier_3_pct=params.get('small_tier_3_pct', 0.70),
            # Configurable giveback thresholds
            tier_1_max_giveback_pct=params.get('tier_1_max_giveback_pct', 60.0),
            tier_2_max_giveback_pct=params.get('tier_2_max_giveback_pct', 50.0),
            tier_3_max_giveback_pct=params.get('tier_3_max_giveback_pct', 40.0),
            default_max_giveback_pct=params.get('default_max_giveback_pct', 70.0),
            volatility_adjust=params.get('volatility_adjust', True),
            momentum_adjust=params.get('momentum_adjust', True),
        )
        
        # Track initial balance for ratio calculations
        self._initial_balance: Optional[float] = params.get('initial_balance', None)
        
        # State tracking
        self._position_states: Dict[int, PositionScaleState] = {}
        
    def should_exit(
        self,
        position: PositionInfo,
        current_data: Dict[str, Any]
    ) -> Optional[ExitSignal]:
        """
        Check if position should be partially scaled out.
        
        Args:
            position: Position information
            current_data: Market data including account_balance, indicators, current_price
            
        Returns:
            ExitSignal with partial_volume if scaling triggered, None otherwise
        """
        if not self._enabled:
            return None
            
        ticket = position.ticket
        current_price = current_data.get('current_price', position.current_price)
        account_balance = current_data.get('account_balance', 1000)
        indicators = current_data.get('indicators', {})
        
        if current_price is None or current_price <= 0:
            return None
            
        # Initialize state for new position
        if ticket not in self._position_states:
            self._position_states[ticket] = PositionScaleState(
                ticket=ticket,
                original_volume=position.volume,
                entry_price=position.open_price
            )
            logger.info(f"[ProfitScaling] Initialized tracking for {ticket}, vol={position.volume}")
            
        state = self._position_states[ticket]
        
        # Skip if fully scaled out
        if state.current_tier == ScaleTier.COMPLETE:
            return None
            
        # Calculate profit percentage
        profit_pct = self._calculate_profit_pct(position, current_price)
        
        # Update peak profit
        if profit_pct > state.peak_profit_pct:
            state.peak_profit_pct = profit_pct
            state.peak_profit = position.unrealized_pnl
        
        # Track initial balance for ratio-based mode selection
        initial_balance = current_data.get('initial_balance', self._initial_balance)
        if initial_balance is None and self._initial_balance is None:
            # First time - set initial balance
            self._initial_balance = account_balance
            initial_balance = account_balance
            
        # Get adjusted targets based on account size ratio and volatility
        targets = self._get_adjusted_targets(account_balance, indicators, initial_balance)
        
        # Check each tier
        scale_signal = self._check_scale_tiers(position, state, profit_pct, targets, current_price)
        
        if scale_signal:
            return scale_signal
            
        # Check profit giveback protection for scaled positions
        if state.current_tier != ScaleTier.INITIAL:
            giveback_signal = self._check_scaled_giveback(position, state, profit_pct, current_price)
            if giveback_signal:
                return giveback_signal
                
        return None
        
    def _calculate_profit_pct(self, position: PositionInfo, current_price: float) -> float:
        """Calculate profit as percentage of entry price."""
        if position.open_price <= 0:
            return 0
            
        if position.side == 'BUY':
            return ((current_price - position.open_price) / position.open_price) * 100
        else:
            return ((position.open_price - current_price) / position.open_price) * 100
            
    def _get_adjusted_targets(
        self,
        account_balance: float,
        indicators: Dict[str, Any],
        initial_balance: Optional[float] = None
    ) -> Dict[str, float]:
        """Get profit targets adjusted for account size and volatility.
        
        Uses ATR-based targets when available, falls back to percentage-based.
        Account size mode is determined by RATIO to initial balance (dynamic).
        """
        
        # Get ATR for dynamic calculations
        atr = indicators.get('atr', 0)
        current_price = indicators.get('current_price', indicators.get('close', 0))
        
        # Prefer absolute account thresholds (legacy quick detection) when available
        if account_balance < self.config.micro_account_threshold:
            mode = "MICRO"
            atr_mults = (self.config.micro_tier_1_atr_mult, 
                        self.config.micro_tier_2_atr_mult, 
                        self.config.micro_tier_3_atr_mult)
            pct_fallbacks = (self.config.micro_tier_1_pct,
                            self.config.micro_tier_2_pct,
                            self.config.micro_tier_3_pct)
        elif account_balance < self.config.small_account_threshold:
            mode = "SMALL"
            atr_mults = (self.config.small_tier_1_atr_mult,
                        self.config.small_tier_2_atr_mult,
                        self.config.small_tier_3_atr_mult)
            pct_fallbacks = (self.config.small_tier_1_pct,
                            self.config.small_tier_2_pct,
                            self.config.small_tier_3_pct)
        else:
            # Determine account mode based on ratio to initial (dynamic)
            # Default initial_balance to current if not provided
            effective_initial = initial_balance if initial_balance and initial_balance > 0 else account_balance
            balance_ratio = account_balance / effective_initial if effective_initial > 0 else 1.0
            
            if balance_ratio < self.config.micro_ratio_threshold:
                mode = "MICRO"
                atr_mults = (self.config.micro_tier_1_atr_mult, 
                            self.config.micro_tier_2_atr_mult, 
                            self.config.micro_tier_3_atr_mult)
                pct_fallbacks = (self.config.micro_tier_1_pct,
                                self.config.micro_tier_2_pct,
                                self.config.micro_tier_3_pct)
            elif balance_ratio < self.config.small_ratio_threshold:
                mode = "SMALL"
                atr_mults = (self.config.small_tier_1_atr_mult,
                            self.config.small_tier_2_atr_mult,
                            self.config.small_tier_3_atr_mult)
                pct_fallbacks = (self.config.small_tier_1_pct,
                                self.config.small_tier_2_pct,
                                self.config.small_tier_3_pct)
            else:
                mode = "NORMAL"
                atr_mults = (self.config.normal_tier_1_atr_mult,
                            self.config.normal_tier_2_atr_mult,
                            self.config.normal_tier_3_atr_mult)
                pct_fallbacks = (self.config.tier_1_profit_pct,
                                self.config.tier_2_profit_pct,
                                self.config.tier_3_profit_pct)
        
        # Calculate targets using ATR if available, else fall back to percentages
        if atr > 0 and current_price > 0:
            # ATR-based targets (convert to percentage of price)
            targets = {
                'tier_1': (atr * atr_mults[0] / current_price) * 100,
                'tier_2': (atr * atr_mults[1] / current_price) * 100,
                'tier_3': (atr * atr_mults[2] / current_price) * 100,
            }
            logger.debug(f"Using ATR-based {mode} targets: {targets} (ATR={atr:.4f})")
        else:
            # Fallback to percentage-based
            targets = {
                'tier_1': pct_fallbacks[0],
                'tier_2': pct_fallbacks[1],
                'tier_3': pct_fallbacks[2],
            }
            logger.debug(f"Using percentage-based {mode} targets: {targets} (no ATR)")
            
        # Volatility adjustment (additional fine-tuning)
        if self.config.volatility_adjust and atr > 0:
            # Normalize ATR as percentage of price
            atr_pct = (atr / current_price * 100) if current_price > 0 else indicators.get('atr_pct', 0)
            
            # If ATR is high, widen targets; if low, tighten
            # Normalized around 0.5% ATR baseline
            volatility_mult = max(0.7, min(1.5, atr_pct / 0.5)) if atr_pct > 0 else 1.0
            
            for key in targets:
                targets[key] *= volatility_mult
                    
        # Momentum adjustment
        if self.config.momentum_adjust:
            rsi = indicators.get('rsi') or indicators.get('RSI')
            adx = indicators.get('adx') or indicators.get('ADX')
            
            # Strong momentum = let it run (widen targets)
            if adx and adx > 30:
                momentum_mult = 1.2  # Strong trend, widen targets
            elif adx and adx < 20:
                momentum_mult = 0.85  # Weak trend, tighter targets
            else:
                momentum_mult = 1.0
                
            for key in targets:
                targets[key] *= momentum_mult
                
        return targets
        
    def _check_scale_tiers(
        self,
        position: PositionInfo,
        state: PositionScaleState,
        profit_pct: float,
        targets: Dict[str, float],
        current_price: float
    ) -> Optional[ExitSignal]:
        """Check if any profit tier is hit and return scale signal."""
        
        remaining_volume = position.volume
        
        # Check Tier 1
        if state.current_tier == ScaleTier.INITIAL and profit_pct >= targets['tier_1']:
            close_volume = self._calculate_scale_volume(
                remaining_volume,
                self.config.tier_1_close_pct
            )
            
            if close_volume > 0:
                state.current_tier = ScaleTier.TIER_1
                state.scales_executed.append({
                    'tier': 'TIER_1',
                    'volume': close_volume,
                    'profit_pct': profit_pct,
                    'price': current_price,
                    'timestamp': datetime.now()
                })
                
                logger.info(
                    f"[ProfitScaling] TIER 1 HIT for {position.ticket}: "
                    f"profit={profit_pct:.2f}%, closing {close_volume:.4f} ({self.config.tier_1_close_pct}%)"
                )
                
                return self._create_scale_signal(
                    position, close_volume, current_price,
                    tier="TIER_1", profit_pct=profit_pct, targets=targets
                )
                
        # Check Tier 2
        elif state.current_tier == ScaleTier.TIER_1 and profit_pct >= targets['tier_2']:
            close_volume = self._calculate_scale_volume(
                remaining_volume,
                self.config.tier_2_close_pct
            )
            
            if close_volume > 0:
                state.current_tier = ScaleTier.TIER_2
                state.scales_executed.append({
                    'tier': 'TIER_2',
                    'volume': close_volume,
                    'profit_pct': profit_pct,
                    'price': current_price,
                    'timestamp': datetime.now()
                })
                
                logger.info(
                    f"[ProfitScaling] TIER 2 HIT for {position.ticket}: "
                    f"profit={profit_pct:.2f}%, closing {close_volume:.4f} ({self.config.tier_2_close_pct}%)"
                )
                
                return self._create_scale_signal(
                    position, close_volume, current_price,
                    tier="TIER_2", profit_pct=profit_pct, targets=targets
                )
                
        # Check Tier 3
        elif state.current_tier == ScaleTier.TIER_2 and profit_pct >= targets['tier_3']:
            close_volume = self._calculate_scale_volume(
                remaining_volume,
                self.config.tier_3_close_pct
            )
            
            if close_volume > 0:
                state.current_tier = ScaleTier.TIER_3
                state.scales_executed.append({
                    'tier': 'TIER_3',
                    'volume': close_volume,
                    'profit_pct': profit_pct,
                    'price': current_price,
                    'timestamp': datetime.now()
                })
                
                logger.info(
                    f"[ProfitScaling] TIER 3 HIT for {position.ticket}: "
                    f"profit={profit_pct:.2f}%, closing {close_volume:.4f} - RUNNER active"
                )
                
                return self._create_scale_signal(
                    position, close_volume, current_price,
                    tier="TIER_3", profit_pct=profit_pct, targets=targets
                )
                
        return None
        
    def _check_scaled_giveback(
        self,
        position: PositionInfo,
        state: PositionScaleState,
        profit_pct: float,
        current_price: float
    ) -> Optional[ExitSignal]:
        """
        Protect scaled positions from giving back too much profit.
        
        Once we've scaled out, remaining position should not give back
        more than configured percentage of peak profit.
        """
        if state.peak_profit_pct <= 0:
            return None
            
        # Calculate giveback percentage
        giveback = state.peak_profit_pct - profit_pct
        giveback_pct = (giveback / state.peak_profit_pct) * 100 if state.peak_profit_pct > 0 else 0
        
        # Use configurable giveback thresholds (no hardcoding!)
        if state.current_tier == ScaleTier.TIER_1:
            max_giveback = self.config.tier_1_max_giveback_pct
        elif state.current_tier == ScaleTier.TIER_2:
            max_giveback = self.config.tier_2_max_giveback_pct
        elif state.current_tier == ScaleTier.TIER_3:
            max_giveback = self.config.tier_3_max_giveback_pct
        else:
            max_giveback = self.config.default_max_giveback_pct
            
        if giveback_pct >= max_giveback and profit_pct > 0:
            remaining_vol = position.volume
            
            logger.warning(
                f"[ProfitScaling] Giveback protection for {position.ticket}: "
                f"Peak {state.peak_profit_pct:.2f}% -> Current {profit_pct:.2f}% "
                f"({giveback_pct:.1f}% giveback, threshold={max_giveback}%) - closing remaining"
            )
            
            state.current_tier = ScaleTier.COMPLETE
            
            return self._create_scale_signal(
                position, remaining_vol, current_price,
                tier="GIVEBACK_PROTECTION",
                profit_pct=profit_pct,
                targets={},
                reason=f"Profit giveback protection ({giveback_pct:.1f}% giveback)"
            )
            
        return None
        
    def _calculate_scale_volume(
        self,
        current_volume: float,
        close_pct: float
    ) -> float:
        """
        Calculate volume to close for scaling.
        
        Respects minimum lot sizes and rounds appropriately.
        """
        raw_volume = current_volume * (close_pct / 100)
        
        # Round to 2 decimal places (standard lot precision)
        volume = round(raw_volume, 2)
        
        # Ensure minimum volume (0.01 for most brokers)
        if volume < 0.01:
            # If remaining is tiny, close it all
            if current_volume <= 0.02:
                return current_volume
            return 0.01
            
        # Don't close more than we have
        return min(volume, current_volume)
        
    def _create_scale_signal(
        self,
        position: PositionInfo,
        volume: float,
        price: float,
        tier: str,
        profit_pct: float,
        targets: Dict[str, float],
        reason: str = None
    ) -> ExitSignal:
        """Create exit signal for partial close."""
        
        if reason is None:
            reason = f"Profit scaling {tier}: +{profit_pct:.2f}%"
            
        return ExitSignal(
            ticket=position.ticket,
            reason=reason,
            price=price,
            timestamp=datetime.now(),
            strategy_name=self.name,
            confidence=0.92,
            partial_volume=volume,
            metadata={
                'tier': tier,
                'profit_pct': profit_pct,
                'close_volume': volume,
                'original_volume': position.volume,
                'targets': targets,
                'remaining_after_close': position.volume - volume
            }
        )
        
    def get_position_state(self, ticket: int) -> Optional[PositionScaleState]:
        """Get scaling state for a position."""
        return self._position_states.get(ticket)
        
    def reset(self):
        """Reset all position states."""
        super().reset()
        self._position_states.clear()
        logger.info("[ProfitScaling] Reset all position states")
        
    def remove_position(self, ticket: int):
        """Remove position from tracking when fully closed."""
        if ticket in self._position_states:
            state = self._position_states[ticket]
            logger.info(
                f"[ProfitScaling] Position {ticket} closed. "
                f"Final tier: {state.current_tier.value}, "
                f"Scales: {len(state.scales_executed)}"
            )
            del self._position_states[ticket]


class AggressiveScalingExit(ProfitScalingExit):
    """
    More aggressive profit scaling for volatile markets or small accounts.
    
    Takes profits faster with tighter targets:
    - Tier 1: 0.15% (vs 0.3%)
    - Tier 2: 0.30% (vs 0.6%)
    - Tier 3: 0.50% (vs 1.0%)
    
    Closes larger portions at each tier:
    - Tier 1: 35% (vs 30%)
    - Tier 2: 40% (vs 35%)
    - Tier 3: 60% (vs 50%)
    """
    
    def __init__(self, params: Dict[str, Any] = None):
        params = params or {}
        
        # Override with aggressive defaults
        aggressive_params = {
            'tier_1_profit_pct': params.get('tier_1_profit_pct', 0.15),
            'tier_2_profit_pct': params.get('tier_2_profit_pct', 0.30),
            'tier_3_profit_pct': params.get('tier_3_profit_pct', 0.50),
            'tier_1_close_pct': params.get('tier_1_close_pct', 35.0),
            'tier_2_close_pct': params.get('tier_2_close_pct', 40.0),
            'tier_3_close_pct': params.get('tier_3_close_pct', 60.0),
            'micro_tier_1_pct': params.get('micro_tier_1_pct', 0.10),
            'micro_tier_2_pct': params.get('micro_tier_2_pct', 0.20),
            'micro_tier_3_pct': params.get('micro_tier_3_pct', 0.35),
            **params
        }
        
        super().__init__(aggressive_params)
        self.name = "AggressiveScaling"
        self.priority = 60  # Slightly higher priority
        
        logger.info("[AggressiveScaling] Initialized with tight profit targets")


# Convenience exports
ProfitScaling = ProfitScalingExit
AggressiveScaling = AggressiveScalingExit
