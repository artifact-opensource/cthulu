"""
Multi-RRR Exit Manager - Structured Trade Exit System

Based on MQL5 Handbook: "Building a Trading System (Part 5): 
Managing Gains Through Structured Trade Exits"

Key insight from the research:
- Using multiple entries at different RRR levels significantly improves outcomes
- For 43% win-rate systems: 3-trade strategy improved profit probability from 48.6% to 61.8%
- Drawdowns reduced from 30% to 17% with multi-RRR approach
- Even high win-rate systems (65%) benefit from structured exits

This implementation:
1. Opens positions with multiple TP targets (TP1, TP2, TP3)
2. Each target has a different RRR (e.g., 1.3, 1.5, 1.7)
3. Position is split into segments, each closing at its target
4. Provides systematic profit taking while letting winners run
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone
from enum import Enum
import logging
import math

logger = logging.getLogger('cthulu.multi_rrr_exit')


@dataclass
class RRRTarget:
    """Represents a single RRR-based take profit target"""
    rrr: float           # Reward-to-Risk Ratio (e.g., 1.3 = 1.3x the stop loss distance)
    position_pct: float  # Percentage of position to close at this target (e.g., 0.33 = 33%)
    price: float = 0.0   # Calculated TP price
    filled: bool = False
    fill_time: Optional[datetime] = None
    profit: float = 0.0


@dataclass 
class MultiRRRPosition:
    """Tracks a position with multiple RRR targets"""
    ticket: int
    symbol: str
    direction: str  # 'BUY' or 'SELL'
    entry_price: float
    stop_loss: float
    initial_volume: float
    current_volume: float
    targets: List[RRRTarget] = field(default_factory=list)
    total_profit_realized: float = 0.0
    breakeven_set: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class MultiRRRConfig:
    """Configuration for multi-RRR exit system"""
    enabled: bool = True
    
    # Default RRR progression (based on Monte Carlo research)
    # These values were optimized in the MQL5 article for 43% win-rate systems
    base_rrr: float = 1.3
    rrr_step: float = 0.2  # Increment between targets
    num_targets: int = 3
    
    # Position distribution across targets
    # Default: 33% at each of 3 targets
    target_distribution: List[float] = field(default_factory=lambda: [0.33, 0.33, 0.34])
    
    # Risk-adjusted settings for different account sizes
    micro_account_threshold: float = 500.0  # Below this, use more conservative settings
    micro_base_rrr: float = 1.2
    micro_rrr_step: float = 0.15
    
    # Breakeven settings
    move_to_breakeven_after_tp1: bool = True
    breakeven_buffer_pct: float = 0.01  # Small buffer above breakeven
    
    # Trail settings after TP1
    trail_after_tp1: bool = True
    trail_distance_rrr: float = 0.5  # Trail at 50% of remaining RRR distance


class MultiRRRExitManager:
    """
    Manages structured exits with multiple RRR-based take profit levels.
    
    This replaces the simple scaling approach with a mathematically
    validated multi-target system that:
    - Secures profits systematically
    - Reduces drawdowns
    - Improves overall expectancy
    """
    
    def __init__(self, connector, execution_engine, config: Optional[MultiRRRConfig] = None):
        """
        Initialize multi-RRR exit manager.
        
        Args:
            connector: MT5Connector instance
            execution_engine: ExecutionEngine for order management  
            config: Configuration for multi-RRR behavior
        """
        self.connector = connector
        self.execution_engine = execution_engine
        self.config = config or MultiRRRConfig()
        
        self._positions: Dict[int, MultiRRRPosition] = {}
        self._history: List[Dict[str, Any]] = []
        
        logger.info(f"MultiRRRExitManager initialized: base_rrr={self.config.base_rrr}, "
                   f"step={self.config.rrr_step}, targets={self.config.num_targets}")
    
    def calculate_targets(self, entry_price: float, stop_loss: float, 
                         direction: str, account_balance: float) -> List[RRRTarget]:
        """
        Calculate RRR-based take profit targets.
        
        Args:
            entry_price: Position entry price
            stop_loss: Stop loss price
            direction: 'BUY' or 'SELL'
            account_balance: Current account balance (for adaptive RRR)
            
        Returns:
            List of RRRTarget objects with calculated prices
        """
        # Calculate SL distance
        sl_distance = abs(entry_price - stop_loss)
        
        if sl_distance <= 0:
            logger.warning("Invalid SL distance for target calculation")
            return []
        
        # Use micro settings for small accounts
        if account_balance < self.config.micro_account_threshold:
            base_rrr = self.config.micro_base_rrr
            rrr_step = self.config.micro_rrr_step
        else:
            base_rrr = self.config.base_rrr
            rrr_step = self.config.rrr_step
        
        targets = []
        is_buy = direction.upper() == 'BUY'
        
        for i in range(self.config.num_targets):
            rrr = base_rrr + (i * rrr_step)
            
            # Calculate TP price based on RRR
            tp_distance = sl_distance * rrr
            
            if is_buy:
                tp_price = entry_price + tp_distance
            else:
                tp_price = entry_price - tp_distance
            
            # Get position percentage for this target
            pct = self.config.target_distribution[i] if i < len(self.config.target_distribution) else 1.0 / self.config.num_targets
            
            target = RRRTarget(
                rrr=rrr,
                position_pct=pct,
                price=round(tp_price, 5)
            )
            targets.append(target)
            
            logger.debug(f"Target {i+1}: RRR={rrr:.2f}, TP={tp_price:.5f}, Pct={pct*100:.0f}%")
        
        return targets
    
    def register_position(self, ticket: int, symbol: str, direction: str,
                         entry_price: float, stop_loss: float, volume: float,
                         account_balance: float) -> MultiRRRPosition:
        """
        Register a position for multi-RRR management.
        
        Args:
            ticket: Position ticket/ID
            symbol: Trading symbol
            direction: 'BUY' or 'SELL'
            entry_price: Entry price
            stop_loss: Stop loss price
            volume: Position volume
            account_balance: Current account balance
            
        Returns:
            MultiRRRPosition object
        """
        # Calculate targets
        targets = self.calculate_targets(entry_price, stop_loss, direction, account_balance)
        
        position = MultiRRRPosition(
            ticket=ticket,
            symbol=symbol,
            direction=direction.upper(),
            entry_price=entry_price,
            stop_loss=stop_loss,
            initial_volume=volume,
            current_volume=volume,
            targets=targets
        )
        
        self._positions[ticket] = position
        
        logger.info(f"Registered position #{ticket} for multi-RRR management: "
                   f"{symbol} {direction} @ {entry_price}, SL={stop_loss}, Vol={volume}")
        for i, t in enumerate(targets):
            logger.info(f"  TP{i+1}: {t.price} (RRR={t.rrr:.2f}, {t.position_pct*100:.0f}%)")
        
        return position
    
    def evaluate_position(self, ticket: int, current_price: float) -> List[Dict[str, Any]]:
        """
        Evaluate a position against its RRR targets.
        
        Args:
            ticket: Position ticket
            current_price: Current market price
            
        Returns:
            List of actions to execute
        """
        if not self.config.enabled:
            return []
        
        position = self._positions.get(ticket)
        if not position:
            return []
        
        actions = []
        is_buy = position.direction == 'BUY'
        
        # Check each unfilled target
        for i, target in enumerate(position.targets):
            if target.filled:
                continue
            
            # Check if target hit
            target_hit = False
            if is_buy and current_price >= target.price:
                target_hit = True
            elif not is_buy and current_price <= target.price:
                target_hit = True
            
            if target_hit:
                # Calculate volume to close
                close_volume = position.initial_volume * target.position_pct
                
                # Get minimum lot from MT5
                try:
                    from cthulu.connector.mt5_connector import mt5
                    symbol_info = mt5.symbol_info(position.symbol)
                    min_lot = symbol_info.volume_min if symbol_info else 0.01
                    volume_step = symbol_info.volume_step if symbol_info else 0.01
                except Exception:
                    min_lot = 0.01
                    volume_step = 0.01
                
                # Normalize volume
                close_volume = round(round(close_volume / volume_step) * volume_step, 2)
                
                # Can't close less than min lot
                if close_volume < min_lot:
                    close_volume = min_lot
                
                # Don't close more than remaining
                if close_volume > position.current_volume:
                    close_volume = position.current_volume
                
                # Check if partial close is possible
                remainder = position.current_volume - close_volume
                if 0 < remainder < min_lot:
                    # Would leave invalid remainder - close all instead
                    close_volume = position.current_volume
                
                if close_volume >= min_lot:
                    actions.append({
                        'type': 'close_partial',
                        'ticket': ticket,
                        'volume': close_volume,
                        'target_idx': i,
                        'target_rrr': target.rrr,
                        'target_price': target.price,
                        'reason': f'TP{i+1} hit (RRR={target.rrr:.2f})'
                    })
                    
                    # Move to breakeven after TP1
                    if i == 0 and self.config.move_to_breakeven_after_tp1 and not position.breakeven_set:
                        # Add small buffer above breakeven
                        if is_buy:
                            be_price = position.entry_price + (abs(position.entry_price - position.stop_loss) * self.config.breakeven_buffer_pct)
                        else:
                            be_price = position.entry_price - (abs(position.entry_price - position.stop_loss) * self.config.breakeven_buffer_pct)
                        
                        actions.append({
                            'type': 'modify_sl',
                            'ticket': ticket,
                            'new_sl': be_price,
                            'reason': 'Breakeven after TP1'
                        })
                else:
                    # Position too small to partial close - just track
                    logger.debug(f"Skipping TP{i+1} for #{ticket}: volume too small")
        
        # Trailing stop after TP1
        if self.config.trail_after_tp1 and position.targets[0].filled and not all(t.filled for t in position.targets):
            # Find next unfilled target
            next_target = None
            for t in position.targets:
                if not t.filled:
                    next_target = t
                    break
            
            if next_target:
                # Trail at configured distance from current price toward next target
                distance_to_next = abs(next_target.price - current_price)
                trail_distance = distance_to_next * self.config.trail_distance_rrr
                
                if is_buy:
                    trail_sl = current_price - trail_distance
                    if position.stop_loss and trail_sl > position.stop_loss:
                        actions.append({
                            'type': 'trail_sl',
                            'ticket': ticket,
                            'new_sl': trail_sl,
                            'reason': f'Trailing toward TP{position.targets.index(next_target)+1}'
                        })
                else:
                    trail_sl = current_price + trail_distance
                    if position.stop_loss and trail_sl < position.stop_loss:
                        actions.append({
                            'type': 'trail_sl',
                            'ticket': ticket,
                            'new_sl': trail_sl,
                            'reason': f'Trailing toward TP{position.targets.index(next_target)+1}'
                        })
        
        return actions
    
    def execute_actions(self, actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute the actions returned by evaluate_position"""
        results = []
        
        for action in actions:
            try:
                ticket = action['ticket']
                position = self._positions.get(ticket)
                
                if action['type'] == 'close_partial':
                    result = self._execute_partial_close(ticket, action['volume'])
                    
                    if result.get('success') and position:
                        position.current_volume -= action['volume']
                        target_idx = action.get('target_idx', 0)
                        if target_idx < len(position.targets):
                            position.targets[target_idx].filled = True
                            position.targets[target_idx].fill_time = datetime.now(timezone.utc)
                            position.targets[target_idx].profit = result.get('profit', 0)
                        position.total_profit_realized += result.get('profit', 0)
                        
                        self._log_action(action, result)
                    results.append(result)
                    
                elif action['type'] in ['modify_sl', 'trail_sl']:
                    result = self._execute_sl_modification(ticket, action['new_sl'])
                    
                    if result.get('success') and position:
                        position.stop_loss = action['new_sl']
                        if action['type'] == 'modify_sl':
                            position.breakeven_set = True
                        self._log_action(action, result)
                    results.append(result)
                    
            except Exception as e:
                logger.exception(f"Failed to execute action: {action}")
                results.append({'success': False, 'error': str(e), 'action': action})
        
        return results
    
    def _execute_partial_close(self, ticket: int, volume: float) -> Dict[str, Any]:
        """Execute partial position close"""
        try:
            result = self.execution_engine.close_position(ticket, volume=volume)
            
            if result and result.status.value == 'FILLED':
                profit = 0.0
                if result.metadata and isinstance(result.metadata, dict):
                    profit = result.metadata.get('profit', 0.0) or 0.0
                elif hasattr(result, 'profit'):
                    profit = getattr(result, 'profit', 0.0) or 0.0
                
                logger.info(f"Multi-RRR partial close #{ticket}: {volume} lots, profit: {profit}")
                return {'success': True, 'profit': profit, 'volume': volume}
            else:
                error = result.error if result else 'Unknown error'
                logger.warning(f"Multi-RRR partial close failed for #{ticket}: {error}")
                return {'success': False, 'error': error}
                
        except Exception as e:
            logger.exception(f"Partial close error for #{ticket}")
            return {'success': False, 'error': str(e)}
    
    def _execute_sl_modification(self, ticket: int, new_sl: float) -> Dict[str, Any]:
        """Modify position stop loss"""
        try:
            from cthulu.connector.mt5_connector import mt5
            
            positions = mt5.positions_get(ticket=ticket)
            if not positions:
                return {'success': False, 'error': 'Position not found'}
            
            pos = positions[0]
            
            # Validate SL direction
            is_buy = pos.type == 0
            current_price = pos.price_current
            
            if is_buy and new_sl >= current_price:
                return {'success': False, 'error': 'Invalid SL for BUY'}
            if not is_buy and new_sl <= current_price:
                return {'success': False, 'error': 'Invalid SL for SELL'}
            
            # Don't worsen SL
            if pos.sl and pos.sl != 0:
                if is_buy and new_sl < pos.sl:
                    return {'success': False, 'error': 'Would worsen SL'}
                if not is_buy and new_sl > pos.sl:
                    return {'success': False, 'error': 'Would worsen SL'}
            
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": str(pos.symbol),
                "position": int(ticket),
                "sl": float(new_sl) if new_sl is not None else 0.0,
                "tp": float(pos.tp) if hasattr(pos, 'tp') and pos.tp else 0.0,
            }
            
            result = mt5.order_send(request)
            
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"Multi-RRR SL modified for #{ticket}: {new_sl}")
                return {'success': True, 'new_sl': new_sl}
            else:
                error = result.comment if result else 'Unknown error'
                return {'success': False, 'error': error}
                
        except Exception as e:
            logger.exception(f"SL modification error for #{ticket}")
            return {'success': False, 'error': str(e)}
    
    def _log_action(self, action: Dict[str, Any], result: Dict[str, Any]) -> None:
        """Log action for history/audit"""
        entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'action': action,
            'result': result
        }
        self._history.append(entry)
        
        if len(self._history) > 500:
            self._history = self._history[-250:]
    
    def run_cycle(self) -> List[Dict[str, Any]]:
        """
        Run a complete evaluation cycle for all tracked positions.
        
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
                
                if ticket not in self._positions:
                    # Not managed by multi-RRR
                    continue
                
                actions = self.evaluate_position(ticket, pos.price_current)
                
                if actions:
                    results = self.execute_actions(actions)
                    all_results.extend(results)
                    
        except Exception as e:
            logger.exception("Multi-RRR cycle error")
            all_results.append({'success': False, 'error': str(e)})
        
        return all_results
    
    def get_position(self, ticket: int) -> Optional[MultiRRRPosition]:
        """Get position info"""
        return self._positions.get(ticket)
    
    def get_all_positions(self) -> Dict[int, MultiRRRPosition]:
        """Get all tracked positions"""
        return dict(self._positions)
    
    def unregister_position(self, ticket: int) -> None:
        """Remove position from management"""
        if ticket in self._positions:
            del self._positions[ticket]
    
    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent action history"""
        return self._history[-limit:]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        total_positions = len(self._positions)
        
        targets_filled = 0
        total_profit = 0.0
        
        for pos in self._positions.values():
            for target in pos.targets:
                if target.filled:
                    targets_filled += 1
                    total_profit += target.profit
        
        return {
            'active_positions': total_positions,
            'targets_filled': targets_filled,
            'total_profit_realized': total_profit,
            'config': {
                'base_rrr': self.config.base_rrr,
                'rrr_step': self.config.rrr_step,
                'num_targets': self.config.num_targets
            }
        }


# Factory function
def create_multi_rrr_manager(connector, execution_engine, 
                             config_dict: Optional[Dict[str, Any]] = None) -> MultiRRRExitManager:
    """
    Create a MultiRRRExitManager with optional config.
    
    Args:
        connector: MT5Connector instance
        execution_engine: ExecutionEngine instance
        config_dict: Optional configuration overrides
        
    Returns:
        Configured MultiRRRExitManager
    """
    config = MultiRRRConfig()
    
    if config_dict:
        if 'enabled' in config_dict:
            config.enabled = bool(config_dict['enabled'])
        if 'base_rrr' in config_dict:
            config.base_rrr = float(config_dict['base_rrr'])
        if 'rrr_step' in config_dict:
            config.rrr_step = float(config_dict['rrr_step'])
        if 'num_targets' in config_dict:
            config.num_targets = int(config_dict['num_targets'])
        if 'target_distribution' in config_dict:
            config.target_distribution = config_dict['target_distribution']
        if 'move_to_breakeven_after_tp1' in config_dict:
            config.move_to_breakeven_after_tp1 = bool(config_dict['move_to_breakeven_after_tp1'])
        if 'trail_after_tp1' in config_dict:
            config.trail_after_tp1 = bool(config_dict['trail_after_tp1'])
    
    return MultiRRRExitManager(connector, execution_engine, config)
