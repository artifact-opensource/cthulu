"""
Multi-RRR Exit Manager - Structured Trade Exit System

Based on MQL5 "Building a Trading System (Part 5): Managing Gains Through Structured Trade Exits"

This module implements structured profit-taking at multiple Risk-Reward Ratio (RRR) levels:
- Multiple simultaneous profit targets per position
- Progressive profit locking with tiered exits
- Monte Carlo validated exit structure

Key Insight from Research:
- Low win-rate systems (< 50%) benefit MOST from multi-RRR exits
- Splitting entries across 2-3 RRR targets reduces drawdowns by 50%
- Probability of profitability increases from ~49% to ~62% with 3-trade structure

Part of Cthulu v6.0.0 APEX - Exit Quality System
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone
from enum import Enum
import logging

logger = logging.getLogger("cthulu.multi_rrr_exit")


class ExitTier(Enum):
    """Exit tier identifiers."""
    TIER_1 = "tier_1"  # First target (earliest)
    TIER_2 = "tier_2"  # Second target
    TIER_3 = "tier_3"  # Third target (final)
    RUNNER = "runner"  # Remaining runner position


@dataclass
class RRRTarget:
    """A single RRR-based profit target."""
    tier: ExitTier
    rrr: float                    # Reward-to-Risk Ratio (e.g., 1.3 = 1.3x risk)
    close_pct: float              # Percentage of position to close (0-1)
    sl_to_breakeven: bool = True  # Move SL to breakeven after this tier
    trail_pct: float = 0.0        # Trail SL by this % of profit (0 = no trail)
    
    @property
    def pip_multiplier(self) -> float:
        """Get pip distance multiplier from SL distance."""
        return self.rrr


@dataclass  
class RRRConfig:
    """Configuration for multi-RRR exit system."""
    enabled: bool = True
    
    # Default RRR targets (based on Monte Carlo research)
    # 43% win-rate: RRR 1.3, 1.5, 1.7 with rstep=0.2 -> best results
    # 65% win-rate: RRR 0.9, 1.1, 1.3 with rstep=0.2 -> 100% profitable
    base_rrr: float = 1.3
    rrr_step: float = 0.2
    num_targets: int = 3
    
    # Position sizing per target
    # With 3 targets: 40%, 30%, 30% (first closes most to lock profits early)
    target_close_pcts: List[float] = field(default_factory=lambda: [0.40, 0.30, 0.30])
    
    # Stop loss management
    move_sl_to_be_after_tier: int = 1  # Move to BE after tier 1 (1-indexed)
    trail_after_tier: int = 2          # Start trailing after tier 2
    trail_pct: float = 0.50            # Trail at 50% of profit
    
    # Win-rate based adjustments
    # Research shows: low win-rate needs wider RRR spacing
    win_rate_adjustment: bool = True
    low_win_rate_threshold: float = 0.50  # If < 50%, use larger rrr_step
    high_win_rate_rrr_start: float = 0.9  # Higher win-rate can use lower RRR
    
    # Runner configuration
    keep_runner: bool = True
    runner_pct: float = 0.10  # Keep 10% as a runner for extended moves


@dataclass
class PositionExitState:
    """Tracks multi-RRR exit state for a position."""
    ticket: int
    symbol: str
    side: str  # 'BUY' or 'SELL'
    entry_price: float
    stop_loss: float
    initial_volume: float
    current_volume: float
    
    # RRR targets for this position
    targets: List[RRRTarget] = field(default_factory=list)
    
    # Execution state
    targets_hit: List[ExitTier] = field(default_factory=list)
    targets_executed: List[ExitTier] = field(default_factory=list)
    profit_locked: float = 0.0
    sl_at_breakeven: bool = False
    trailing_active: bool = False
    trailing_sl: Optional[float] = None
    
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    @property
    def risk_distance(self) -> float:
        """Calculate risk distance in price units."""
        return abs(self.entry_price - self.stop_loss)
    
    def get_target_price(self, target: RRRTarget) -> float:
        """Calculate target price for a given RRR target."""
        risk = self.risk_distance
        if self.side.upper() == 'BUY':
            return self.entry_price + (risk * target.rrr)
        else:
            return self.entry_price - (risk * target.rrr)
    
    def is_target_hit(self, target: RRRTarget, current_price: float) -> bool:
        """Check if target price has been reached."""
        target_price = self.get_target_price(target)
        if self.side.upper() == 'BUY':
            return current_price >= target_price
        else:
            return current_price <= target_price


@dataclass
class ExitAction:
    """An exit action to execute."""
    ticket: int
    action_type: str  # 'partial_close', 'modify_sl', 'full_close'
    tier: ExitTier
    volume: Optional[float] = None  # For partial close
    new_sl: Optional[float] = None  # For modify_sl
    reason: str = ""
    target_price: Optional[float] = None


class MultiRRRExitManager:
    """
    Multi-RRR Exit Manager - Structured exit system with tiered profit targets.
    
    Research-backed approach:
    - Split positions into multiple RRR targets
    - Lock profits progressively at each tier
    - Move SL to breakeven after first target
    - Trail stops after second target
    
    Monte Carlo validated:
    - 43% win-rate: 3-trade structure → 61.8% profitable, 17% drawdown
    - 65% win-rate: 3-trade structure → 100% profitable, 4% drawdown
    """
    
    def __init__(self, connector=None, execution_engine=None, config: Optional[RRRConfig] = None):
        """
        Initialize the multi-RRR exit manager.
        
        Args:
            connector: MT5Connector instance
            execution_engine: ExecutionEngine for order management
            config: RRR exit configuration
        """
        self.connector = connector
        self.execution_engine = execution_engine
        self.config = config or RRRConfig()
        
        self._position_states: Dict[int, PositionExitState] = {}
        self._exit_log: List[Dict[str, Any]] = []
        
        logger.info(f"MultiRRRExitManager initialized: base_rrr={self.config.base_rrr}, "
                   f"step={self.config.rrr_step}, targets={self.config.num_targets}")
    
    def generate_targets(self, win_rate: float = 0.50) -> List[RRRTarget]:
        """
        Generate RRR targets based on configuration and win rate.
        
        Args:
            win_rate: Current system win rate (0-1)
            
        Returns:
            List of RRR targets
        """
        targets = []
        
        # Adjust base RRR and step based on win rate
        if self.config.win_rate_adjustment:
            if win_rate >= 0.60:
                # High win-rate: can use lower RRR targets
                base_rrr = self.config.high_win_rate_rrr_start
                rrr_step = self.config.rrr_step
            elif win_rate < self.config.low_win_rate_threshold:
                # Low win-rate: needs higher RRR targets and wider spacing
                base_rrr = max(self.config.base_rrr, 1.3)
                rrr_step = self.config.rrr_step + 0.1  # Wider spacing
            else:
                base_rrr = self.config.base_rrr
                rrr_step = self.config.rrr_step
        else:
            base_rrr = self.config.base_rrr
            rrr_step = self.config.rrr_step
        
        # Ensure we have close percentages for each target
        close_pcts = self.config.target_close_pcts
        if len(close_pcts) < self.config.num_targets:
            # Distribute remaining evenly
            remaining = 1.0 - sum(close_pcts)
            per_target = remaining / (self.config.num_targets - len(close_pcts))
            close_pcts = close_pcts + [per_target] * (self.config.num_targets - len(close_pcts))
        
        # Adjust for runner if configured
        if self.config.keep_runner:
            total_close = 1.0 - self.config.runner_pct
            close_pcts = [p * total_close / sum(close_pcts[:self.config.num_targets]) 
                         for p in close_pcts[:self.config.num_targets]]
        
        tier_names = [ExitTier.TIER_1, ExitTier.TIER_2, ExitTier.TIER_3]
        
        for i in range(self.config.num_targets):
            rrr = base_rrr + (i * rrr_step)
            tier = tier_names[i] if i < len(tier_names) else ExitTier.TIER_3
            
            # Determine if this tier triggers BE or trailing
            move_to_be = (i + 1) == self.config.move_sl_to_be_after_tier
            trail = self.config.trail_pct if (i + 1) >= self.config.trail_after_tier else 0.0
            
            targets.append(RRRTarget(
                tier=tier,
                rrr=rrr,
                close_pct=close_pcts[i] if i < len(close_pcts) else 0.25,
                sl_to_breakeven=move_to_be,
                trail_pct=trail
            ))
        
        logger.debug(f"Generated {len(targets)} targets: {[(t.tier.value, t.rrr, t.close_pct) for t in targets]}")
        return targets
    
    def register_position(
        self,
        ticket: int,
        symbol: str,
        side: str,
        entry_price: float,
        stop_loss: float,
        volume: float,
        win_rate: float = 0.50,
        custom_targets: Optional[List[RRRTarget]] = None
    ) -> PositionExitState:
        """
        Register a position for multi-RRR exit management.
        
        Args:
            ticket: Position ticket
            symbol: Trading symbol
            side: 'BUY' or 'SELL'
            entry_price: Entry price
            stop_loss: Initial stop loss
            volume: Position volume
            win_rate: Current system win rate
            custom_targets: Optional custom targets (overrides generated ones)
            
        Returns:
            Position exit state
        """
        # Generate or use custom targets
        targets = custom_targets or self.generate_targets(win_rate)
        
        state = PositionExitState(
            ticket=ticket,
            symbol=symbol,
            side=side.upper(),
            entry_price=entry_price,
            stop_loss=stop_loss,
            initial_volume=volume,
            current_volume=volume,
            targets=targets
        )
        
        self._position_states[ticket] = state
        
        logger.info(f"Registered position #{ticket} for multi-RRR exits: "
                   f"{len(targets)} targets, risk={state.risk_distance:.5f}")
        
        return state
    
    def unregister_position(self, ticket: int) -> None:
        """Remove position from multi-RRR management."""
        if ticket in self._position_states:
            del self._position_states[ticket]
            logger.info(f"Unregistered position #{ticket} from multi-RRR management")
    
    def evaluate_position(self, ticket: int, current_price: float) -> List[ExitAction]:
        """
        Evaluate a position for RRR target hits.
        
        Args:
            ticket: Position ticket
            current_price: Current market price
            
        Returns:
            List of exit actions to execute
        """
        if not self.config.enabled:
            return []
        
        state = self._position_states.get(ticket)
        if not state:
            return []
        
        actions = []
        
        # Check each target
        for target in state.targets:
            if target.tier in state.targets_executed:
                continue  # Already executed
            
            if state.is_target_hit(target, current_price):
                if target.tier not in state.targets_hit:
                    state.targets_hit.append(target.tier)
                    logger.info(f"Target {target.tier.value} hit for #{ticket}: "
                               f"RRR={target.rrr}, price={current_price:.5f}")
                
                # Calculate close volume
                close_volume = round(state.initial_volume * target.close_pct, 2)
                
                # Ensure minimum lot and valid remainder
                min_lot = 0.01  # Will be updated from symbol info
                try:
                    from cthulu.connector.mt5_connector import mt5
                    symbol_info = mt5.symbol_info(state.symbol)
                    if symbol_info:
                        min_lot = symbol_info.volume_min
                except Exception:
                    pass
                
                # Check if we can actually close this volume
                if state.current_volume <= min_lot:
                    logger.debug(f"Position #{ticket} at minimum lot, skipping partial close")
                    continue
                
                if close_volume < min_lot:
                    close_volume = min_lot
                
                if close_volume > state.current_volume:
                    close_volume = state.current_volume
                
                # Check remainder validity
                remainder = state.current_volume - close_volume
                if 0 < remainder < min_lot:
                    close_volume = state.current_volume  # Close all instead
                
                # Create partial close action
                actions.append(ExitAction(
                    ticket=ticket,
                    action_type='partial_close',
                    tier=target.tier,
                    volume=close_volume,
                    reason=f"RRR target {target.tier.value} hit (RRR={target.rrr})",
                    target_price=state.get_target_price(target)
                ))
                
                # Move SL to breakeven if configured
                if target.sl_to_breakeven and not state.sl_at_breakeven:
                    actions.append(ExitAction(
                        ticket=ticket,
                        action_type='modify_sl',
                        tier=target.tier,
                        new_sl=state.entry_price,
                        reason=f"Move SL to breakeven after {target.tier.value}"
                    ))
                
                # Trail stop if configured
                if target.trail_pct > 0:
                    profit_distance = abs(current_price - state.entry_price)
                    trail_offset = profit_distance * target.trail_pct
                    
                    if state.side == 'BUY':
                        trail_sl = current_price - trail_offset
                        if state.trailing_sl is None or trail_sl > state.trailing_sl:
                            actions.append(ExitAction(
                                ticket=ticket,
                                action_type='modify_sl',
                                tier=target.tier,
                                new_sl=trail_sl,
                                reason=f"Trailing stop after {target.tier.value} ({target.trail_pct*100:.0f}%)"
                            ))
                    else:
                        trail_sl = current_price + trail_offset
                        if state.trailing_sl is None or trail_sl < state.trailing_sl:
                            actions.append(ExitAction(
                                ticket=ticket,
                                action_type='modify_sl',
                                tier=target.tier,
                                new_sl=trail_sl,
                                reason=f"Trailing stop after {target.tier.value} ({target.trail_pct*100:.0f}%)"
                            ))
        
        return actions
    
    def execute_actions(self, actions: List[ExitAction]) -> List[Dict[str, Any]]:
        """
        Execute exit actions.
        
        Args:
            actions: List of exit actions
            
        Returns:
            List of execution results
        """
        results = []
        
        for action in actions:
            try:
                state = self._position_states.get(action.ticket)
                
                if action.action_type == 'partial_close':
                    result = self._execute_partial_close(action)
                    if result.get('success') and state:
                        state.current_volume -= action.volume or 0
                        state.targets_executed.append(action.tier)
                        state.profit_locked += result.get('profit', 0)
                        state.last_updated = datetime.now(timezone.utc)
                        self._log_action(action, result)
                    results.append(result)
                    
                elif action.action_type == 'modify_sl':
                    result = self._execute_sl_modification(action)
                    if result.get('success') and state:
                        if action.new_sl == state.entry_price:
                            state.sl_at_breakeven = True
                        if action.reason and 'Trailing' in action.reason:
                            state.trailing_active = True
                            state.trailing_sl = action.new_sl
                        state.last_updated = datetime.now(timezone.utc)
                        self._log_action(action, result)
                    results.append(result)
                    
            except Exception as e:
                logger.exception(f"Failed to execute exit action: {action}")
                results.append({'success': False, 'error': str(e), 'action': action})
        
        return results
    
    def _execute_partial_close(self, action: ExitAction) -> Dict[str, Any]:
        """Execute partial position close."""
        try:
            if not self.execution_engine:
                return {'success': False, 'error': 'No execution engine configured'}
            
            result = self.execution_engine.close_position(action.ticket, volume=action.volume)
            
            if result and result.status.value == 'FILLED':
                profit = 0.0
                if result.metadata and isinstance(result.metadata, dict):
                    profit = result.metadata.get('profit', 0.0) or 0.0
                    
                logger.info(f"Multi-RRR partial close #{action.ticket}: "
                           f"{action.volume} lots at {action.tier.value}, profit={profit:.2f}")
                return {'success': True, 'profit': profit, 'volume': action.volume, 'tier': action.tier.value}
            else:
                error = result.error if result else 'Unknown error'
                return {'success': False, 'error': error}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _execute_sl_modification(self, action: ExitAction) -> Dict[str, Any]:
        """Execute stop loss modification."""
        try:
            from cthulu.connector.mt5_connector import mt5
            
            positions = mt5.positions_get(ticket=action.ticket)
            if not positions:
                return {'success': False, 'error': 'Position not found'}
            
            pos = positions[0]
            
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": str(pos.symbol),
                "position": int(action.ticket),
                "sl": float(action.new_sl) if action.new_sl is not None else 0.0,
                "tp": float(pos.tp) if hasattr(pos, 'tp') and pos.tp else 0.0,
            }
            
            result = mt5.order_send(request)
            
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"Multi-RRR SL modified #{action.ticket}: SL={action.new_sl:.5f} ({action.reason})")
                return {'success': True, 'new_sl': action.new_sl}
            else:
                error = result.comment if result else 'Unknown error'
                return {'success': False, 'error': error}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _log_action(self, action: ExitAction, result: Dict[str, Any]) -> None:
        """Log exit action for audit."""
        entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'ticket': action.ticket,
            'action_type': action.action_type,
            'tier': action.tier.value,
            'result': result
        }
        self._exit_log.append(entry)
        
        # Keep log bounded
        if len(self._exit_log) > 1000:
            self._exit_log = self._exit_log[-500:]
    
    def run_exit_cycle(self) -> List[Dict[str, Any]]:
        """
        Run exit evaluation for all tracked positions.
        
        Returns:
            List of all execution results
        """
        if not self.config.enabled:
            return []
        
        all_results = []
        
        try:
            from cthulu.connector.mt5_connector import mt5
            
            positions = mt5.positions_get()
            if not positions:
                return []
            
            for pos in positions:
                ticket = pos.ticket
                
                # Auto-register if not tracked
                if ticket not in self._position_states:
                    side = 'BUY' if pos.type == 0 else 'SELL'
                    sl = pos.sl if hasattr(pos, 'sl') and pos.sl != 0 else None
                    
                    if sl is None:
                        continue  # Can't manage without SL
                    
                    self.register_position(
                        ticket=ticket,
                        symbol=pos.symbol,
                        side=side,
                        entry_price=pos.price_open,
                        stop_loss=sl,
                        volume=pos.volume
                    )
                
                # Evaluate for exits
                actions = self.evaluate_position(ticket, pos.price_current)
                
                if actions:
                    results = self.execute_actions(actions)
                    all_results.extend(results)
                    
        except Exception as e:
            logger.exception("Multi-RRR exit cycle error")
            all_results.append({'success': False, 'error': str(e), 'cycle_error': True})
        
        return all_results
    
    def get_position_state(self, ticket: int) -> Optional[PositionExitState]:
        """Get exit state for a position."""
        return self._position_states.get(ticket)
    
    def get_exit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent exit actions log."""
        return self._exit_log[-limit:]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get exit system statistics."""
        total_positions = len(self._position_states)
        targets_hit = sum(len(s.targets_hit) for s in self._position_states.values())
        targets_executed = sum(len(s.targets_executed) for s in self._position_states.values())
        total_profit_locked = sum(s.profit_locked for s in self._position_states.values())
        
        return {
            'total_positions': total_positions,
            'targets_hit': targets_hit,
            'targets_executed': targets_executed,
            'total_profit_locked': total_profit_locked,
            'config': {
                'base_rrr': self.config.base_rrr,
                'rrr_step': self.config.rrr_step,
                'num_targets': self.config.num_targets
            }
        }


# Convenience factory function
def create_multi_rrr_manager(
    connector=None,
    execution_engine=None,
    config_dict: Optional[Dict[str, Any]] = None
) -> MultiRRRExitManager:
    """
    Create a MultiRRRExitManager with optional configuration.
    
    Args:
        connector: MT5Connector instance
        execution_engine: ExecutionEngine instance
        config_dict: Optional configuration dictionary
        
    Returns:
        Configured MultiRRRExitManager instance
    """
    config = RRRConfig()
    
    if config_dict:
        if 'enabled' in config_dict:
            config.enabled = bool(config_dict['enabled'])
        if 'base_rrr' in config_dict:
            config.base_rrr = float(config_dict['base_rrr'])
        if 'rrr_step' in config_dict:
            config.rrr_step = float(config_dict['rrr_step'])
        if 'num_targets' in config_dict:
            config.num_targets = int(config_dict['num_targets'])
        if 'target_close_pcts' in config_dict:
            config.target_close_pcts = [float(p) for p in config_dict['target_close_pcts']]
        if 'keep_runner' in config_dict:
            config.keep_runner = bool(config_dict['keep_runner'])
        if 'runner_pct' in config_dict:
            config.runner_pct = float(config_dict['runner_pct'])
    
    return MultiRRRExitManager(connector, execution_engine, config)
