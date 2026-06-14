"""
Profit Scaling Manager - Dynamic Partial Profit Taking System

Implements intelligent profit scaling for micro and standard accounts:
- Tiered profit taking (25%, 35%, 50% at profit milestones)
- Dynamic trailing stop adjustment
- Balance-aware scaling thresholds
- Runner protection with breakeven stops
- ML-powered tier optimization (learns from outcomes)

This is critical for SPARTA mode (micro account battle testing).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
import logging
import math

logger = logging.getLogger('cthulu.profit_scaler')

# ML Tier Optimizer integration
try:
    from cthulu.ML_RL.tier_optimizer import get_tier_optimizer, record_scaling_outcome
    ML_OPTIMIZER_AVAILABLE = True
except ImportError:
    ML_OPTIMIZER_AVAILABLE = False
    logger.info("ML Tier Optimizer not available, using static tiers")


@dataclass
class ScalingTier:
    """Defines a profit-taking tier"""
    profit_threshold_pct: float  # % profit to trigger (e.g., 0.5 = 50% of position value)
    close_pct: float             # % of position to close (e.g., 0.25 = 25%)
    move_sl_to_entry: bool       # Move SL to breakeven after this tier
    trail_pct: float             # Trail SL by this % of profit after taking


@dataclass
class ScalingConfig:
    """Configuration for profit scaling behavior"""
    enabled: bool = True
    
    # RECALIBRATED TIERS - Let trades breathe and develop!
    # Philosophy: Quality over quantity - let winners run to meaningful targets
    tiers: List[ScalingTier] = field(default_factory=lambda: [
        # First scale: Only after substantial profit (1R = full risk distance)
        ScalingTier(
            profit_threshold_pct=1.00,  # Wait for full 1R (not 50%)
            close_pct=0.20,              # Take only 20% (preserve position)
            move_sl_to_entry=True,       # Lock in breakeven
            trail_pct=0.40               # Trail conservatively
        ),
        # Second scale: After 1.5R (position well in profit)
        ScalingTier(
            profit_threshold_pct=1.50,  # 1.5R
            close_pct=0.30,              # Take 30% of remaining
            move_sl_to_entry=True,
            trail_pct=0.50
        ),
        # Third scale: After 2R+ (let winners become big winners)
        ScalingTier(
            profit_threshold_pct=2.00,  # Full 2R
            close_pct=0.40,              # Take 40% of remaining
            move_sl_to_entry=True,
            trail_pct=0.60
        ),
    ])
    
    # Micro account adjustments (balance < threshold)
    # Still conservative but not choking trades
    micro_account_threshold: float = 100.0
    micro_tiers: List[ScalingTier] = field(default_factory=lambda: [
        # Micro: Scale earlier but still let trades develop
        ScalingTier(profit_threshold_pct=0.80, close_pct=0.25, move_sl_to_entry=True, trail_pct=0.35),
        ScalingTier(profit_threshold_pct=1.20, close_pct=0.30, move_sl_to_entry=True, trail_pct=0.45),
        ScalingTier(profit_threshold_pct=1.80, close_pct=0.35, move_sl_to_entry=True, trail_pct=0.55),
    ])
    
    # Minimum profit in account currency to trigger scaling
    # Must be meaningful profit, not pocket change
    min_profit_amount: float = 5.00  # $5 minimum (raised from $2)
    
    # Maximum position age before forced evaluation (hours)
    # Give trades more time to work out
    max_position_age_hours: float = 8.0  # 8 hours (raised from 4)

    # Minimum number of bars to wait before allowing scaling/close actions.
    # This prevents immediate partial exits right after entry (useful for thin/timezone-sensitive markets)
    min_time_in_trade_bars: int = 3  # Wait at least 3 bars (raised from 0)
    
    # Emergency profit lock threshold (% of balance)
    emergency_lock_threshold_pct: float = 0.15  # Lock profits if > 15% of balance (raised from 10%)
    # If True, allow a full close when position is at minimum lot to capture profit
    allow_full_close_on_min_lot: bool = True


@dataclass
class PositionScalingState:
    """Tracks scaling state for a position"""
    ticket: int
    symbol: str
    initial_volume: float
    current_volume: float
    entry_price: float
    current_sl: Optional[float]
    current_tp: Optional[float]
    tiers_executed: List[int] = field(default_factory=list)
    total_profit_taken: float = 0.0
    breakeven_set: bool = False
    last_trail_price: Optional[float] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ProfitScaler:
    """
    Dynamic profit scaling manager.
    
    Automatically takes partial profits and adjusts stops to lock gains.
    Designed for both micro accounts (SPARTA mode) and standard accounts.
    Now with ML-powered tier optimization for adaptive learning.
    """
    
    def __init__(self, connector, execution_engine, config: Optional[ScalingConfig] = None, 
                 use_ml_optimizer: bool = True):
        """
        Initialize profit scaler.
        
        Args:
            connector: MT5Connector instance
            execution_engine: ExecutionEngine for order management
            config: Scaling configuration
            use_ml_optimizer: Whether to use ML-based tier optimization
        """
        self.connector = connector
        self.execution_engine = execution_engine
        self.config = config or ScalingConfig()
        self._position_states: Dict[int, PositionScalingState] = {}
        self._scaling_log: List[Dict[str, Any]] = []
        self.use_ml_optimizer = use_ml_optimizer and ML_OPTIMIZER_AVAILABLE
        
        if self.use_ml_optimizer:
            logger.info("ProfitScaler initialized with ML tier optimization enabled")
        
    def get_active_tiers(self, balance: float) -> List[ScalingTier]:
        """Get appropriate tiers based on account balance, optionally ML-optimized"""
        # Try ML-optimized tiers first
        if self.use_ml_optimizer:
            try:
                optimizer = get_tier_optimizer()
                ml_tiers = optimizer.get_optimized_tiers(balance)
                
                if ml_tiers and len(ml_tiers) >= 3:
                    # Convert ML tier format to ScalingTier objects
                    return [
                        ScalingTier(
                            profit_threshold_pct=t['profit_threshold_pct'] / 100,  # Convert from % to ratio
                            close_pct=t['close_pct'] / 100,  # Convert from % to ratio
                            move_sl_to_entry=True,
                            trail_pct=0.50 + (i * 0.10)  # Progressive trailing
                        )
                        for i, t in enumerate(ml_tiers)
                    ]
            except Exception as e:
                logger.warning(f"ML tier optimization failed, using defaults: {e}")
                
        # Fallback to static tiers
        if balance < self.config.micro_account_threshold:
            return self.config.micro_tiers
        return self.config.tiers
    
    def _has_strong_momentum(self, state: PositionScalingState, side: str) -> Tuple[bool, str]:
        """
        Check if price has strong momentum in our favor.
        
        Don't interrupt winning trades when momentum is strong - let them run!
        
        Args:
            state: Position scaling state
            side: 'BUY' or 'SELL'
            
        Returns:
            Tuple of (has_strong_momentum, reason)
        """
        try:
            # Get recent price action from connector
            rates = self.connector.get_rates(
                symbol=state.symbol,
                timeframe=1,  # M1 for micro-momentum, fallback handled by connector
                count=10
            )
            
            if rates is None or len(rates) < 5:
                return False, "insufficient_data"
            
            # Get recent closes
            recent_closes = [r['close'] for r in rates[-5:]]
            
            # Determine if we're long or short
            is_long = side.upper() == 'BUY'
            
            # Count consecutive moves in our favor
            momentum_score = 0
            for i in range(1, len(recent_closes)):
                if is_long:
                    # For long: higher closes = momentum in our favor
                    if recent_closes[i] > recent_closes[i-1]:
                        momentum_score += 1
                    elif recent_closes[i] < recent_closes[i-1]:
                        momentum_score -= 1
                else:
                    # For short: lower closes = momentum in our favor
                    if recent_closes[i] < recent_closes[i-1]:
                        momentum_score += 1
                    elif recent_closes[i] > recent_closes[i-1]:
                        momentum_score -= 1
            
            # Strong momentum = 3+ consecutive moves in our direction (out of 4 possible)
            if momentum_score >= 3:
                return True, f"strong_momentum_score_{momentum_score}"
            
            # Also check for acceleration (bars getting bigger)
            price_changes = [abs(recent_closes[i] - recent_closes[i-1]) for i in range(1, len(recent_closes))]
            if len(price_changes) >= 3:
                # If last 2 bars are bigger than first 2 bars = acceleration
                recent_avg = sum(price_changes[-2:]) / 2
                older_avg = sum(price_changes[:2]) / 2
                if recent_avg > older_avg * 1.5:  # 50% larger bars = acceleration
                    return True, "price_accelerating"
            
            return False, f"momentum_score_{momentum_score}"
            
        except Exception as e:
            logger.debug(f"Momentum check failed for #{state.ticket}: {e}")
            return False, f"error_{str(e)[:20]}"
    
    def register_position(self, ticket: int, symbol: str, volume: float,
                         entry_price: float, sl: Optional[float] = None, 
                         tp: Optional[float] = None) -> PositionScalingState:
        """Register a new position for profit scaling"""
        state = PositionScalingState(
            ticket=ticket,
            symbol=symbol,
            initial_volume=volume,
            current_volume=volume,
            entry_price=entry_price,
            current_sl=sl,
            current_tp=tp
        )
        self._position_states[ticket] = state
        logger.info(f"Registered position #{ticket} for profit scaling: {symbol} @ {entry_price}")
        return state
    
    def unregister_position(self, ticket: int) -> None:
        """Remove position from scaling management"""
        if ticket in self._position_states:
            del self._position_states[ticket]
            logger.info(f"Unregistered position #{ticket} from profit scaling")
    
    def evaluate_position(self, ticket: int, current_price: float, 
                         side: str, balance: float, bars_elapsed: int | None = None) -> List[Dict[str, Any]]:
        """
        Evaluate a position for profit scaling actions.
        
        Args:
            ticket: Position ticket
            current_price: Current market price
            side: 'BUY' or 'SELL'
            balance: Current account balance
            bars_elapsed: Optional number of bars elapsed since position entry (if provided, used to enforce min_time_in_trade_bars)
            
        Returns:
            List of actions to take (close_partial, modify_sl, etc.)
        """
        # Enforce minimum time-in-trade (in bars) guard if requested
        if bars_elapsed is not None and self.config.min_time_in_trade_bars and bars_elapsed < self.config.min_time_in_trade_bars:
            logger.debug(f"Skipping scaling for #{ticket}: only {bars_elapsed} bars elapsed (< {self.config.min_time_in_trade_bars})")
            return []

        if not self.config.enabled:
            return []
            
        state = self._position_states.get(ticket)
        if not state:
            return []
            
        actions = []
        tiers = self.get_active_tiers(balance)
        
        # Calculate current profit relative to TP target (not entry price)
        # For GOLD/XAUUSD: TP targets are typically $10-30 from entry
        # profit_pct should be % of the way TO the target, not % of entry price
        if side.upper() == 'BUY':
            profit_pips = current_price - state.entry_price
        else:
            profit_pips = state.entry_price - current_price
        
        # Calculate profit as % of TP distance (if TP set) or use ATR-based fallback
        if state.current_tp and state.current_tp != state.entry_price:
            tp_distance = abs(state.current_tp - state.entry_price)
            profit_pct = profit_pips / tp_distance if tp_distance > 0 else 0
        else:
            # Fallback: Use ATR or generic pip target (no symbol-specific logic)
            # Use 0.0050 (50 pips equivalent) as universal baseline
            # This works for both FX pairs and other instruments when normalized
            pip_target = 0.0050
            profit_pct = profit_pips / pip_target if pip_target > 0 else 0
        
        # Estimate profit in currency
        profit_amount = abs(profit_pips) * state.current_volume * 100  # Rough estimate
        
        # Check each tier - but only if we're actually in meaningful profit
        # Use configured minimum profit threshold so behaviour is tunable via config
        min_meaningful_profit = float(getattr(self.config, 'min_profit_amount', 0.0) or 0.0)
        if profit_amount < min_meaningful_profit:
            logger.info(
                f"Skipping scaling for #{ticket}: profit_amount=${profit_amount:.2f} < min_required=${min_meaningful_profit:.2f}"
            )
            return []  # Don't scale tiny profits
        
        # ==========================================================
        # MOMENTUM CHECK - Don't interrupt winning trades!
        # If price has strong momentum in our favor, let it run
        # ==========================================================
        has_momentum, momentum_reason = self._has_strong_momentum(state, side)
        if has_momentum:
            logger.info(
                f"Deferring scaling for #{ticket}: Strong momentum detected ({momentum_reason}) - let it run!"
            )
            # Still allow trailing stop updates, but skip partial closes
            # We'll only add trailing stop actions, not close_partial
            trail_only_actions = []
            for i, tier in enumerate(tiers):
                if i in state.tiers_executed:
                    continue
                if profit_pct >= tier.profit_threshold_pct and tier.trail_pct > 0:
                    if side.upper() == 'BUY':
                        trail_sl = state.entry_price + (profit_pips * tier.trail_pct)
                    else:
                        trail_sl = state.entry_price - (profit_pips * tier.trail_pct)
                    
                    if state.current_sl is None or \
                       (side.upper() == 'BUY' and trail_sl > state.current_sl) or \
                       (side.upper() == 'SELL' and trail_sl < state.current_sl):
                        trail_only_actions.append({
                            'type': 'trail_sl',
                            'ticket': ticket,
                            'new_sl': trail_sl,
                            'reason': f'Momentum trailing: {tier.trail_pct*100:.0f}% of profit ({momentum_reason})'
                        })
                        break  # Only one trailing update per evaluation
            return trail_only_actions
        
        for i, tier in enumerate(tiers):
            if i in state.tiers_executed:
                continue
                
            if profit_pct >= tier.profit_threshold_pct:
                # CRITICAL: Check if position can actually be reduced
                # Get actual minimum lot for this symbol from MT5
                try:
                    from cthulu.connector.mt5_connector import mt5
                    symbol_info = mt5.symbol_info(state.symbol)
                    if symbol_info:
                        min_lot = symbol_info.volume_min
                        volume_step = symbol_info.volume_step
                    else:
                        min_lot = 0.01
                        volume_step = 0.01
                except Exception as e:
                    logger.debug("Failed to query symbol info from MT5 for %s: %s", state.symbol, e, exc_info=True)
                    min_lot = 0.01
                    volume_step = 0.01
                
                # At minimum lot - can't do partial closes, consider full close policy or trailing
                if state.current_volume <= min_lot + 0.001:  # Allow small tolerance
                    logger.debug(f"Skipping partial close for #{ticket}: position at minimum lot ({state.current_volume:.2f}, min={min_lot})")
                    # If configured, allow a FULL close when at minimum lot to capture profit
                    if getattr(self.config, 'allow_full_close_on_min_lot', False):
                        logger.info(f"Position #{ticket} at min lot and eligible for full close due to config; scheduling full close")
                        actions.append({
                            'type': 'close_partial',
                            'ticket': ticket,
                            'volume': float(state.current_volume),
                            'reason': 'full_close_min_lot',
                            'profit_pct': profit_pct,
                            'tier': i
                        })
                        # We already scheduled an action for this tier; continue to next tier
                        continue
                    # Still apply trailing stop if configured
                    if tier.trail_pct > 0 and profit_pct > 0:
                        if side.upper() == 'BUY':
                            trail_sl = state.entry_price + (profit_pips * tier.trail_pct)
                        else:
                            trail_sl = state.entry_price - (profit_pips * tier.trail_pct)
                            
                        if state.current_sl is None or (side.upper() == 'BUY' and trail_sl > state.current_sl) or \
                           (side.upper() == 'SELL' and trail_sl < state.current_sl):
                            actions.append({
                                'type': 'trail_sl',
                                'ticket': ticket,
                                'new_sl': trail_sl,
                                'reason': f'Trailing stop at {tier.trail_pct*100:.0f}% of profit (min lot, no partial close)'
                            })
                    # Mark tier as executed even though we couldn't close
                    state.tiers_executed.append(i)
                    continue
                
                remaining_after_close = state.current_volume - (state.current_volume * tier.close_pct)
                
                # Skip partial close if it would leave less than min_lot
                if remaining_after_close < min_lot and remaining_after_close > 0:
                    # Can't partial close - just trail the stop instead
                    logger.debug(f"Skipping partial close for #{ticket}: would leave {remaining_after_close:.4f} lots (below min {min_lot})")
                    continue
                
                # Calculate volume to close (respect volume step)
                close_volume = state.current_volume * tier.close_pct
                # Round to nearest volume step
                close_volume = round(round(close_volume / volume_step) * volume_step, 2)
                
                # Ensure minimum lot size
                if close_volume < min_lot:
                    close_volume = min_lot
                    
                # Don't close more than we have
                if close_volume > state.current_volume:
                    close_volume = state.current_volume
                
                # Final check: only proceed if this leaves valid remainder or closes all
                final_remainder = state.current_volume - close_volume
                if final_remainder > 0 and final_remainder < min_lot:
                    # Invalid remainder - adjust to close entire position
                    close_volume = state.current_volume
                
                if close_volume >= min_lot:
                    actions.append({
                        'type': 'close_partial',
                        'ticket': ticket,
                        'volume': close_volume,
                        'tier': i,
                        'reason': f'Tier {i+1} profit target ({tier.profit_threshold_pct*100:.0f}%) reached'
                    })
                    
                # Move SL to breakeven if configured
                if tier.move_sl_to_entry and not state.breakeven_set:
                    actions.append({
                        'type': 'modify_sl',
                        'ticket': ticket,
                        'new_sl': state.entry_price,
                        'reason': 'Breakeven stop after profit tier'
                    })
                    
                # Trail stop if in profit
                if tier.trail_pct > 0 and profit_pct > 0:
                    if side.upper() == 'BUY':
                        trail_sl = state.entry_price + (profit_pips * tier.trail_pct)
                    else:
                        trail_sl = state.entry_price - (profit_pips * tier.trail_pct)
                        
                    if state.current_sl is None or (side.upper() == 'BUY' and trail_sl > state.current_sl) or \
                       (side.upper() == 'SELL' and trail_sl < state.current_sl):
                        actions.append({
                            'type': 'trail_sl',
                            'ticket': ticket,
                            'new_sl': trail_sl,
                            'reason': f'Trailing stop at {tier.trail_pct*100:.0f}% of profit'
                        })
        
        # Emergency profit lock check
        if profit_amount > 0 and balance > 0:
            profit_balance_pct = profit_amount / balance
            if profit_balance_pct >= self.config.emergency_lock_threshold_pct:
                # Lock at least 50% of the position
                if not any(a['type'] == 'close_partial' for a in actions):
                    close_volume = round(state.current_volume * 0.5, 2)
                    if close_volume >= 0.01:
                        actions.append({
                            'type': 'close_partial',
                            'ticket': ticket,
                            'volume': close_volume,
                            'tier': -1,
                            'reason': f'Emergency profit lock ({profit_balance_pct*100:.1f}% of balance)'
                        })
        
        return actions
    
    def execute_actions(self, actions: List[Dict[str, Any]], balance: float = 0.0) -> List[Dict[str, Any]]:
        """
        Execute scaling actions.
        
        Args:
            actions: List of actions from evaluate_position
            balance: Current account balance for ML learning
            
        Returns:
            List of execution results
        """
        results = []
        
        for action in actions:
            try:
                ticket = action['ticket']
                state = self._position_states.get(ticket)
                
                if action['type'] == 'close_partial':
                    result = self._execute_partial_close(ticket, action['volume'])
                    if result.get('success'):
                        profit_captured = result.get('profit', 0)
                        if state:
                            state.current_volume -= action['volume']
                            state.total_profit_taken += profit_captured
                            if 'tier' in action and action['tier'] >= 0:
                                state.tiers_executed.append(action['tier'])
                            state.last_updated = datetime.now(timezone.utc)
                            
                            # Record outcome for ML optimization
                            if self.use_ml_optimizer and 'tier' in action:
                                try:
                                    tier_name = f"tier_{action['tier']+1}" if action['tier'] >= 0 else "emergency"
                                    record_scaling_outcome(
                                        ticket=ticket,
                                        tier=tier_name,
                                        profit_threshold_triggered=action.get('profit_pct', 0),
                                        close_pct=action['volume'] / state.initial_volume * 100 if state.initial_volume > 0 else 0,
                                        profit_captured=profit_captured,
                                        remaining_profit=0,  # Will be updated when position fully closes
                                        account_balance=balance,
                                        symbol=state.symbol
                                    )
                                except Exception as ml_err:
                                    logger.debug(f"ML outcome recording failed: {ml_err}")
                                    
                        self._log_scaling_action(action, result)
                    results.append(result)
                    
                elif action['type'] == 'modify_sl':
                    result = self._execute_sl_modification(ticket, action['new_sl'])
                    if result.get('success') and state:
                        state.current_sl = action['new_sl']
                        state.breakeven_set = True
                        state.last_updated = datetime.now(timezone.utc)
                        self._log_scaling_action(action, result)
                    results.append(result)
                    
                elif action['type'] == 'trail_sl':
                    result = self._execute_sl_modification(ticket, action['new_sl'])
                    if result.get('success') and state:
                        state.current_sl = action['new_sl']
                        state.last_trail_price = action['new_sl']
                        state.last_updated = datetime.now(timezone.utc)
                        self._log_scaling_action(action, result)
                    results.append(result)
                    
            except Exception as e:
                logger.exception(f"Failed to execute scaling action: {action}")
                results.append({'success': False, 'error': str(e), 'action': action})
                
        return results
    
    def _execute_partial_close(self, ticket: int, volume: float) -> Dict[str, Any]:
        """Execute partial position close with pre-validation"""
        try:
            # Pre-check: verify position still exists and has enough volume
            from cthulu.connector.mt5_connector import mt5
            positions = mt5.positions_get(ticket=ticket)
            if not positions:
                logger.debug(f"Partial close skipped for #{ticket}: position no longer exists")
                return {'success': False, 'error': 'Position closed externally', 'skipped': True}
            
            pos = positions[0]
            
            # Get symbol-specific volume constraints
            symbol_info = mt5.symbol_info(pos.symbol)
            if symbol_info:
                min_lot = symbol_info.volume_min
                volume_step = symbol_info.volume_step
            else:
                min_lot = 0.01
                volume_step = 0.01
            
            # If the position is at minimum lot and the requested close is partial (less than full volume), skip
            if pos.volume <= min_lot + 0.0001 and volume < pos.volume - 1e-12:
                logger.info(f"Partial close skipped for #{ticket}: pos.volume={pos.volume}, requested_volume={volume}, min_lot={min_lot}")
                return {'success': False, 'error': 'Position at minimum lot', 'skipped': True}

            if pos.volume < volume:
                # Adjust volume to what's available (allow full close)
                volume = pos.volume
            
            # Normalize volume to step
            volume = round(round(volume / volume_step) * volume_step, 2)
            
            # Check if partial close is even possible
            remainder = pos.volume - volume
            if remainder > 0 and remainder < min_lot:
                logger.debug(f"Partial close #{ticket}: adjusting to full close (remainder {remainder:.4f} < min_lot {min_lot})")
                volume = pos.volume  # Close entire position
            
            # Final validation
            if volume < min_lot:
                logger.debug(f"Partial close skipped for #{ticket}: calculated volume {volume} < min_lot {min_lot}")
                return {'success': False, 'error': 'Volume below minimum', 'skipped': True}
            
            # Log the close request for diagnostics
            logger.debug("Executing partial close for %s: volume=%s", ticket, volume)
            result = self.execution_engine.close_position(ticket, volume=volume)
            # Log execution result details
            try:
                logger.debug("Partial close result for %s: status=%s, error=%s, metadata=%s", ticket, getattr(result, 'status', None), getattr(result, 'error', None), getattr(result, 'metadata', None))
            except Exception:
                pass
            
            if result and result.status.value == 'FILLED':
                # Safely extract profit from metadata or result
                profit = 0.0
                if result.metadata and isinstance(result.metadata, dict):
                    profit = result.metadata.get('profit', 0.0) or 0.0
                elif hasattr(result, 'profit'):
                    profit = getattr(result, 'profit', 0.0) or 0.0
                    
                logger.info(f"Partial close #{ticket}: {volume} lots, profit: {profit}")
                return {'success': True, 'profit': profit, 'volume': volume}
            else:
                error = (getattr(result, 'error', None) if result else None) or (getattr(result, 'status', None) and getattr(result, 'status', None).value if getattr(result, 'status', None) else None) or 'Unknown error'
                logger.warning(f"Partial close failed for #{ticket}: {error}")
                return {'success': False, 'error': error}
        except Exception as e:
            logger.exception(f"Partial close error for #{ticket}")
            return {'success': False, 'error': str(e)}
    
    def _execute_sl_modification(self, ticket: int, new_sl: float) -> Dict[str, Any]:
        """Modify position stop loss with validation"""
        try:
            from cthulu.connector.mt5_connector import mt5
            
            # Get current position
            positions = mt5.positions_get(ticket=ticket)
            if not positions:
                logger.debug(f"SL modification skipped for #{ticket}: position no longer exists")
                return {'success': False, 'error': 'Position closed externally', 'skipped': True}
                
            pos = positions[0]
            
            # Validate new SL makes sense for position direction
            # BUY: SL must be below current price
            # SELL: SL must be above current price
            current_price = pos.price_current
            is_buy = pos.type == 0
            
            if is_buy and new_sl >= current_price:
                logger.debug(f"SL modification skipped for #{ticket}: SL {new_sl} >= price {current_price}")
                return {'success': False, 'error': 'Invalid SL for BUY (above current price)', 'skipped': True}
            elif not is_buy and new_sl <= current_price:
                logger.debug(f"SL modification skipped for #{ticket}: SL {new_sl} <= price {current_price}")
                return {'success': False, 'error': 'Invalid SL for SELL (below current price)', 'skipped': True}
            
            # Don't move SL backwards (worse for the position)
            if pos.sl and pos.sl != 0:
                if is_buy and new_sl < pos.sl:
                    logger.debug(f"SL modification skipped for #{ticket}: new SL {new_sl} < current {pos.sl}")
                    return {'success': False, 'error': 'Would worsen SL', 'skipped': True}
                elif not is_buy and new_sl > pos.sl:
                    logger.debug(f"SL modification skipped for #{ticket}: new SL {new_sl} > current {pos.sl}")
                    return {'success': False, 'error': 'Would worsen SL', 'skipped': True}
            
            # Build modification request - explicit type casting for MT5 API
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": str(pos.symbol),
                "position": int(ticket),
                "sl": float(new_sl) if new_sl is not None else 0.0,
                "tp": float(pos.tp) if hasattr(pos, 'tp') and pos.tp else 0.0,
            }
            
            # Log the modification request for diagnostics
            logger.debug("MT5 SLTP modification request for %s: %s", ticket, request)
            result = mt5.order_send(request)
            # Log result details for debugging (retcode/comment/last_error if available)
            try:
                rc = getattr(result, 'retcode', None)
                comment = getattr(result, 'comment', None)
                logger.debug("MT5 order_send result for SLTP modify #%s: retcode=%s, comment=%s", ticket, rc, comment)
            except Exception:
                pass
            
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"SL modified for #{ticket}: {new_sl}")
                return {'success': True, 'new_sl': new_sl}
            else:
                # Try to pull last_error for additional context
                try:
                    last_err = mt5.last_error()
                except Exception:
                    last_err = None
                error = (getattr(result, 'comment', None) or last_err or 'Unknown error')
                logger.warning(f"SL modification failed for #{ticket}: {error}")
                return {'success': False, 'error': error}
                
        except Exception as e:
            logger.exception(f"SL modification error for #{ticket}")
            return {'success': False, 'error': str(e)}
    
    def _log_scaling_action(self, action: Dict[str, Any], result: Dict[str, Any]) -> None:
        """Log scaling action for audit"""
        entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'action': action,
            'result': result
        }
        self._scaling_log.append(entry)
        
        # Keep log bounded
        if len(self._scaling_log) > 1000:
            self._scaling_log = self._scaling_log[-500:]
    
    def get_position_state(self, ticket: int) -> Optional[PositionScalingState]:
        """Get scaling state for a position"""
        return self._position_states.get(ticket)
    
    def get_all_states(self) -> Dict[int, PositionScalingState]:
        """Get all position scaling states"""
        return dict(self._position_states)
    
    def get_scaling_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent scaling actions log"""
        return self._scaling_log[-limit:]
    
    def run_scaling_cycle(self, balance: float) -> List[Dict[str, Any]]:
        """
        Run a complete scaling evaluation cycle for all tracked positions.
        
        Args:
            balance: Current account balance
            
        Returns:
            List of all execution results
        """
        if not self.config.enabled:
            return []
            
        all_results = []
        
        try:
            from cthulu.connector.mt5_connector import mt5
            
            # Get all open positions
            positions = mt5.positions_get()
            logger.debug("Running scaling cycle: found %s open positions; tracked states: %s", len(positions) if positions else 0, list(self._position_states.keys()))
            if not positions:
                return []
                
            for pos in positions:
                ticket = pos.ticket
                # Emit detailed position snapshot for debugging
                try:
                    logger.debug("Inspecting position %s: symbol=%s, volume=%s, price_current=%s, sl=%s, tp=%s, profit=%s", ticket, getattr(pos,'symbol',None), getattr(pos,'volume',None), getattr(pos,'price_current',None), getattr(pos,'sl',None), getattr(pos,'tp',None), getattr(pos,'profit',None))
                except Exception:
                    pass

                # Auto-register if not tracked
                if ticket not in self._position_states:
                    side = 'BUY' if pos.type == 0 else 'SELL'
                    self.register_position(
                        ticket=ticket,
                        symbol=pos.symbol,
                        volume=pos.volume,
                        entry_price=pos.price_open,
                        sl=getattr(pos, 'sl', None),
                        tp=getattr(pos, 'tp', None)
                    )
                
                # Evaluate for scaling
                side = 'BUY' if pos.type == 0 else 'SELL'
                actions = self.evaluate_position(
                    ticket=ticket,
                    current_price=pos.price_current,
                    side=side,
                    balance=balance
                )
                
                if actions:
                    # Emit an INFO-level message so scaling intent is visible at normal log levels
                    logger.info(f"Scaling actions scheduled for {ticket}: {actions}")
                    logger.debug("Scaling actions for %s: %s", ticket, actions)
                    # Pass balance for ML learning
                    results = self.execute_actions(actions, balance=balance)
                    logger.debug("Scaling results for %s: %s", ticket, results)
                    all_results.extend(results)

            # Emit a concise summary after evaluating all positions in this cycle
            logger.info(f"Scaling cycle: positions_evaluated={len(positions)}, actions_executed={len(all_results)}")
                    
        except Exception as e:
            logger.exception("Scaling cycle error")
            all_results.append({'success': False, 'error': str(e), 'cycle_error': True})
            
        return all_results
    
    def run_ml_optimization(self) -> Dict[str, Any]:
        """
        Trigger ML tier optimization based on collected outcomes.
        
        Returns:
            Optimization results summary
        """
        if not self.use_ml_optimizer:
            return {'error': 'ML optimizer not available'}
            
        try:
            from cthulu.ML_RL.tier_optimizer import run_tier_optimization
            return run_tier_optimization("all")
        except Exception as e:
            logger.exception("ML optimization failed")
            return {'error': str(e)}
    
    def get_ml_stats(self) -> Dict[str, Any]:
        """Get ML optimizer statistics"""
        if not self.use_ml_optimizer:
            return {'available': False}
            
        try:
            optimizer = get_tier_optimizer()
            stats = optimizer.get_stats()
            stats['available'] = True
            return stats
        except Exception as e:
            return {'available': False, 'error': str(e)}
            
        return all_results


# Convenience factory function
def create_profit_scaler(connector, execution_engine, config_dict: Optional[Dict[str, Any]] = None) -> ProfitScaler:
    """
    Create a ProfitScaler with optional configuration.
    
    Args:
        connector: MT5Connector instance
        execution_engine: ExecutionEngine instance
        config_dict: Optional configuration dictionary
        
    Returns:
        Configured ProfitScaler instance
    """
    config = ScalingConfig()
    
    if config_dict:
        if 'enabled' in config_dict:
            config.enabled = bool(config_dict['enabled'])
        if 'micro_account_threshold' in config_dict:
            config.micro_account_threshold = float(config_dict['micro_account_threshold'])
        if 'min_profit_amount' in config_dict:
            config.min_profit_amount = float(config_dict['min_profit_amount'])
        if 'emergency_lock_threshold_pct' in config_dict:
            config.emergency_lock_threshold_pct = float(config_dict['emergency_lock_threshold_pct'])
            
        # Custom tiers if provided
        if 'tiers' in config_dict:
            config.tiers = [
                ScalingTier(**t) for t in config_dict['tiers']
            ]
        if 'micro_tiers' in config_dict:
            config.micro_tiers = [
                ScalingTier(**t) for t in config_dict['micro_tiers']
            ]
    
    return ProfitScaler(connector, execution_engine, config)

