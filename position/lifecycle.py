"""
Position Lifecycle Module

Handles all position operations including opening, closing, modification,
and exit strategy application. This module contains execution logic that
changes position state.

Responsibilities:
- Open positions via ExecutionEngine
- Close positions (market, limit orders)
- Modify stop-loss and take-profit
- Apply exit strategies (trailing, time-based, profit-target, drawdown)
- Refresh position data from MT5
- Persist position data to database

Does NOT:
- Track position state (see tracker.py)
- Make risk decisions (see risk/evaluator.py)
- Handle external trade adoption (see adoption.py)
"""

from typing import Optional, List, Dict, Any
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class PositionLifecycle:
    """
    Manages the complete lifecycle of trading positions.
    
    This class handles all operations that change position state,
    from opening to closing, including modifications and exit strategy application.
    """
    
    def __init__(self, connector, execution_engine, position_tracker, db_handler):
        """
        Initialize the position lifecycle manager.
        
        Args:
            connector: MT5 connector for market operations
            execution_engine: ExecutionEngine for order placement
            position_tracker: PositionTracker for state management
            db_handler: Database handler for persistence
        """
        self.connector = connector
        self.execution_engine = execution_engine
        self.tracker = position_tracker
        self.db = db_handler
        # Expose logger on instance for callers that expect self.logger
        self.logger = logger
        # Track in-flight close operations to prevent duplicate submissions
        import threading
        self._inflight_closes = set()
        self._inflight_lock = threading.Lock()
        logger.info("PositionLifecycle initialized")
    
    def open_position(self, symbol: str, order_type: str, volume: float,
                     sl: Optional[float] = None, tp: Optional[float] = None,
                     comment: str = "", magic_number: int = 0,
                     strategy_name: Optional[str] = None) -> Optional[int]:
        """
        Open a new position via ExecutionEngine.
        
        Args:
            symbol: Trading symbol
            order_type: "buy" or "sell"
            volume: Position size
            sl: Stop loss price
            tp: Take profit price
            comment: Order comment
            magic_number: Magic number for identification
            strategy_name: Name of strategy placing order
            
        Returns:
            Position ticket number if successful, None otherwise
        """
        try:
            # Use execution engine to place order
            ticket = self.execution_engine.execute_order(
                symbol=symbol,
                order_type=order_type,
                volume=volume,
                sl=sl,
                tp=tp,
                comment=comment,
                magic_number=magic_number
            )
            
            if ticket:
                # Get position info from MT5
                position_info = self.connector.get_position_by_ticket(ticket)
                if position_info:
                    # Import PositionInfo here to avoid circular import
                    try:
                        from cthulu.position.tracker import PositionInfo
                    except ImportError:
                        try:
                            from position.tracker import PositionInfo
                        except ImportError as import_err:
                            logger.error(f"Failed to import PositionInfo: {import_err}")
                            return None
                    
                    # Create tracked position
                    tracked_pos = PositionInfo(
                        ticket=ticket,
                        symbol=symbol,
                        type=order_type,
                        volume=volume,
                        open_price=position_info.get('price_open', 0.0),
                        current_price=position_info.get('price_current', 0.0),
                        sl=sl,
                        tp=tp,
                        profit=position_info.get('profit', 0.0),
                        open_time=datetime.now(),
                        magic_number=magic_number,
                        comment=comment,
                        strategy_name=strategy_name
                    )
                    
                    # Add to tracker
                    self.tracker.track_position(tracked_pos)
                    
                    # Persist to database
                    self.persist_position(tracked_pos)
                    
                    logger.info(f"Opened position {ticket}: {symbol} {order_type} {volume}")
                    return ticket
            
            logger.error(f"Failed to open position: {symbol} {order_type}")
            return None
            
        except Exception as e:
            logger.error(f"Error opening position: {e}", exc_info=True)
            return None
    
    def close_position(self, ticket: int, reason: str = "") -> bool:
        """
        Close a position by ticket number.
        
        Args:
            ticket: Position ticket to close
            reason: Reason for closure (for logging)
            
        Returns:
            True if closed successfully, False otherwise
        """
        try:
            # Get position from tracker
            position = self.tracker.get_position(ticket)
            if not position:
                logger.warning(f"Position {ticket} not found in tracker")
                return False

            # Prevent duplicate concurrent close attempts
            with self._inflight_lock:
                if ticket in self._inflight_closes:
                    logger.warning(f"Close already in-flight for position {ticket}, skipping duplicate request")
                    return False
                self._inflight_closes.add(ticket)

            try:
                # Store position data before close for PnL calculation
                pre_close_position = {
                    'ticket': ticket,
                    'symbol': getattr(position, 'symbol', 'UNKNOWN'),
                    'type': getattr(position, 'type', getattr(position, 'side', 'UNKNOWN')),
                    'volume': getattr(position, 'volume', 0),
                    'open_price': getattr(position, 'open_price', 0),
                    'current_price': getattr(position, 'current_price', 0),
                    'profit': getattr(position, 'profit', 0),
                    'sl': getattr(position, 'sl', None),
                    'tp': getattr(position, 'tp', None),
                    'open_time': getattr(position, 'open_time', None),
                    'magic_number': getattr(position, 'magic_number', 0),
                    'strategy_name': getattr(position, 'strategy_name', 'unknown'),
                }
                
                # Close via execution engine
                result = self.execution_engine.close_position(ticket)

                # Support both legacy boolean return values and ExecutionResult objects
                success = False
                exit_price = None
                profit = None
                try:
                    # If engine returned an ExecutionResult-like object, inspect status
                    if hasattr(result, 'status'):
                        from cthulu.execution.engine import OrderStatus
                        success = (getattr(result, 'status', None) == OrderStatus.FILLED)
                        exit_price = getattr(result, 'executed_price', None) or getattr(result, 'price', None)
                        # Try to get profit from result metadata
                        if hasattr(result, 'metadata') and result.metadata:
                            profit = result.metadata.get('profit')
                    else:
                        # Fallback: truthiness for legacy boolean API
                        success = bool(result)
                except (ImportError, AttributeError) as e:
                    logger.warning(f"Error checking close result for {ticket}: {e}")
                    success = bool(result) if result else False

                if success:
                    # Calculate PnL if not provided
                    if profit is None:
                        profit = pre_close_position.get('profit', 0)
                    if exit_price is None:
                        exit_price = pre_close_position.get('current_price', pre_close_position.get('open_price', 0))
                    
                    # Calculate duration
                    duration_seconds = 0
                    try:
                        open_time = pre_close_position.get('open_time')
                        if open_time:
                            from datetime import datetime, timezone
                            now = datetime.now(timezone.utc) if hasattr(open_time, 'tzinfo') and open_time.tzinfo else datetime.now()
                            duration_seconds = (now - open_time).total_seconds()
                    except Exception:
                        pass
                    
                    # Emit TRADE_CLOSED event for ML collection
                    self._emit_trade_closed_event_from_dict(pre_close_position, exit_price, profit, reason or "manual_close", duration_seconds)
                    
                    # Remove from tracker
                    self.tracker.remove_position(ticket)

                    # Remove from database (closed positions don't need to persist)
                    self.db.remove_position(ticket)

                    logger.info(f"Closed position {ticket}: {reason} | PnL: {profit:.2f}")
                    return True
                else:
                    logger.error(f"Failed to close position {ticket}")
                    return False

            except Exception as e:
                logger.error(f"Error closing position {ticket}: {e}", exc_info=True)
                return False

            finally:
                # Ensure we clear in-flight marker
                try:
                    with self._inflight_lock:
                        self._inflight_closes.discard(ticket)
                except Exception as e:
                    logger.debug("Failed to clear inflight close for %s: %s", ticket, e, exc_info=True)

        except Exception as e:
            logger.error(f"Error closing position {ticket}: {e}", exc_info=True)
            return False

    def _emit_trade_closed_event_from_dict(self, position_dict: dict, exit_price: float, 
                                            profit: float, exit_reason: str, 
                                            duration_seconds: float) -> None:
        """
        Emit TRADE_CLOSED event from position dict data.
        Helper for close_position which stores position data before close.
        """
        try:
            ml_collector = getattr(self.execution_engine, 'ml_collector', None)
            
            if ml_collector:
                outcome = 'WIN' if profit > 0 else ('LOSS' if profit < 0 else 'BREAKEVEN')
                
                trade_closed_payload = {
                    'event_type': 'TRADE_CLOSED',
                    'ticket': position_dict.get('ticket'),
                    'symbol': position_dict.get('symbol', 'UNKNOWN'),
                    'side': position_dict.get('type', 'UNKNOWN'),
                    'volume': position_dict.get('volume', 0),
                    'entry_price': position_dict.get('open_price', 0),
                    'exit_price': exit_price,
                    'stop_loss': position_dict.get('sl'),
                    'take_profit': position_dict.get('tp'),
                    'pnl': profit,
                    'outcome': outcome,
                    'exit_reason': exit_reason,
                    'duration_seconds': duration_seconds,
                    'magic_number': position_dict.get('magic_number', 0),
                    'strategy_name': position_dict.get('strategy_name', 'unknown'),
                    'timestamp': datetime.now().isoformat()
                }
                
                if hasattr(ml_collector, 'record_event'):
                    ml_collector.record_event('trade_closed', trade_closed_payload)
                elif hasattr(ml_collector, 'record_execution'):
                    ml_collector.record_execution(trade_closed_payload)
                    
                logger.debug(f"Emitted TRADE_CLOSED event for #{position_dict.get('ticket')}: {outcome}, PnL={profit:.2f}")
                
        except Exception as e:
            logger.debug(f"Failed to emit TRADE_CLOSED event: {e}")
    
    def close_all_positions(self, symbol: Optional[str] = None) -> int:
        """
        Close all open positions, optionally filtered by symbol.
        
        Args:
            symbol: If provided, only close positions for this symbol
            
        Returns:
            Number of positions closed
        """
        try:
            positions = self.tracker.get_all_positions()
            if symbol:
                positions = [p for p in positions if p.symbol == symbol]
            
            closed_count = 0
            for position in positions:
                if self.close_position(position.ticket, "Close all"):
                    closed_count += 1
            
            logger.info(f"Closed {closed_count} positions")
            return closed_count
            
        except Exception as e:
            logger.error(f"Error closing all positions: {e}", exc_info=True)
            return 0
    
    def close_positions_by_symbol(self, symbol: str) -> int:
        """Close all positions for a specific symbol."""
        return self.close_all_positions(symbol=symbol)
    
    def modify_position(self, ticket: int, sl: Optional[float] = None,
                       tp: Optional[float] = None) -> bool:
        """
        Modify stop-loss and/or take-profit for a position.
        
        Args:
            ticket: Position ticket to modify
            sl: New stop loss (None to keep current)
            tp: New take profit (None to keep current)
            
        Returns:
            True if modified successfully, False otherwise
        """
        try:
            position = self.tracker.get_position(ticket)
            # If position is not currently tracked, attempt to fetch live MT5 position
            if not position:
                logger.debug(f"Position {ticket} not found in tracker, checking MT5 directly")
                try:
                    mt5_pos = self.connector.get_position_by_ticket(ticket)
                except Exception as e:
                    logger.error(f"Error fetching MT5 position for {ticket}: {e}")
                    return False

                if not mt5_pos:
                    logger.warning(f"Position {ticket} not found")
                    return False

                # Try to apply modification directly to MT5 position
                success = self.execution_engine.modify_position(ticket, sl, tp)
                if not success:
                    try:
                        mt5_pos = self.connector.get_position_by_ticket(ticket)
                    except Exception as e:
                        mt5_pos = f"<error_fetching_mt5:{e}>"
                    logger.error(f"Failed to modify untracked MT5 position {ticket}; mt5_pos={mt5_pos}")
                    return False

                # On success, create a tracked PositionInfo and persist it so the system knows about it
                try:
                    from cthulu.position.tracker import PositionInfo
                except ImportError:
                    try:
                        from position.tracker import PositionInfo
                    except Exception as import_err:
                        logger.error(f"Failed to import PositionInfo: {import_err}")
                        return True  # Modification succeeded on MT5; treat as success even if we can't track

                # Build PositionInfo from MT5 data and applied SL/TP
                tracked_pos = PositionInfo(
                    ticket=ticket,
                    symbol=mt5_pos.get('symbol'),
                    type=("buy" if mt5_pos.get('type') == 0 else "sell"),
                    volume=mt5_pos.get('volume', 0.0),
                    open_price=mt5_pos.get('price_open', 0.0),
                    current_price=mt5_pos.get('price_current', mt5_pos.get('price_open', 0.0)),
                    sl=(sl if sl is not None else mt5_pos.get('sl')),
                    tp=(tp if tp is not None else mt5_pos.get('tp')),
                    profit=mt5_pos.get('profit', 0.0),
                    open_time=mt5_pos.get('time', datetime.now()),
                    magic_number=mt5_pos.get('magic', 0),
                    comment="[ADOPTED_SYNC]",
                )

                # Track and persist
                try:
                    self.tracker.track_position(tracked_pos)
                    self.persist_position(tracked_pos)
                except Exception as e:
                    logger.warning(f"Modified MT5 position {ticket} but failed to track/persist: {e}")

                logger.info(f"Modified and tracked untracked position {ticket}: SL={tracked_pos.sl}, TP={tracked_pos.tp}")
                return True
        
            # Position exists in tracker - proceed with normal modification
            success = self.execution_engine.modify_position(ticket, sl, tp)
            
            if success:
                # Update tracker
                if sl is not None:
                    position.sl = sl
                if tp is not None:
                    position.tp = tp
                
                logger.info(f"Modified position {ticket}: SL={sl}, TP={tp}")
                return True
            else:
                try:
                    mt5_pos = self.connector.get_position_by_ticket(ticket)
                except Exception as e:
                    mt5_pos = f"<error_fetching_mt5:{e}>"

                # If MT5 already reports the requested values (within tolerance), accept as success
                try:
                    actual_sl = None
                    actual_tp = None
                    if isinstance(mt5_pos, dict):
                        actual_sl = mt5_pos.get('sl') if 'sl' in mt5_pos else mt5_pos.get('stop_loss')
                        actual_tp = mt5_pos.get('tp') if 'tp' in mt5_pos else mt5_pos.get('take_profit')
                    tol = 1e-4
                    sl_ok = (sl is None) or (actual_sl is not None and abs(actual_sl - sl) <= tol)
                    tp_ok = (tp is None) or (actual_tp is not None and abs(actual_tp - tp) <= tol)
                    if sl_ok and tp_ok:
                        if sl is not None:
                            position.sl = sl
                        if tp is not None:
                            position.tp = tp
                        logger.info(f"Modification considered successful for {ticket}: MT5 reports desired SL/TP")
                        return True
                except Exception:
                    pass

                logger.error(
                    f"Failed to modify position {ticket}; tracker_sl={getattr(position,'sl',None)}, tracker_tp={getattr(position,'tp',None)}, requested_sl={sl}, requested_tp={tp}, mt5_pos={mt5_pos}"
                )
                return False
                
        except Exception as e:
            logger.error(f"Error modifying position {ticket}: {e}", exc_info=True)
            return False
    
    def apply_trailing_stop(self, ticket: int, trail_points: float) -> bool:
        """
        Apply trailing stop logic to a position.
        
        Args:
            ticket: Position ticket
            trail_points: Number of points to trail by
            
        Returns:
            True if trailing stop applied successfully
        """
        try:
            position = self.tracker.get_position(ticket)
            if not position:
                return False
            
            # Calculate new SL based on current price and trail points
            if position.type == "buy":
                new_sl = position.current_price - trail_points
                if position.sl is None or new_sl > position.sl:
                    return self.modify_position(ticket, sl=new_sl)
            else:  # sell
                new_sl = position.current_price + trail_points
                if position.sl is None or new_sl < position.sl:
                    return self.modify_position(ticket, sl=new_sl)
            
            return False
            
        except Exception as e:
            logger.error(f"Error applying trailing stop to {ticket}: {e}", exc_info=True)
            return False
    
    def apply_time_based_exit(self, ticket: int, max_age_hours: float) -> bool:
        """
        Close position if it exceeds maximum age.
        
        Args:
            ticket: Position ticket
            max_age_hours: Maximum age in hours
            
        Returns:
            True if position was closed, False otherwise
        """
        try:
            position = self.tracker.get_position(ticket)
            if not position:
                return False
            
            age = datetime.now() - position.open_time
            if age > timedelta(hours=max_age_hours):
                return self.close_position(ticket, f"Time-based exit ({max_age_hours}h)")
            
            return False
            
        except Exception as e:
            logger.error(f"Error applying time-based exit to {ticket}: {e}", exc_info=True)
            return False
    
    def apply_profit_target(self, ticket: int, target_profit: float) -> bool:
        """
        Close position if profit target is reached.
        
        Args:
            ticket: Position ticket
            target_profit: Profit target in account currency
            
        Returns:
            True if position was closed, False otherwise
        """
        try:
            position = self.tracker.get_position(ticket)
            if position and position.profit >= target_profit:
                return self.close_position(ticket, f"Profit target ({target_profit})")
            
            return False
            
        except AttributeError as e:
            logger.warning(f"Position {ticket} missing profit attribute: {e}")
            return False
        except Exception as e:
            logger.error(f"Error applying profit target to {ticket}: {e}", exc_info=True)
            return False
    
    def apply_drawdown_protection(self, ticket: int, max_drawdown: float) -> bool:
        """
        Close position if drawdown exceeds limit.
        
        Args:
            ticket: Position ticket
            max_drawdown: Maximum allowed drawdown (negative value)
            
        Returns:
            True if position was closed, False otherwise
        """
        try:
            position = self.tracker.get_position(ticket)
            if not position:
                return False
            
            if position.profit <= max_drawdown:
                return self.close_position(ticket, f"Drawdown protection ({max_drawdown})")
            
            return False
            
        except Exception as e:
            logger.error(f"Error applying drawdown protection to {ticket}: {e}", exc_info=True)
            return False
    
    def refresh_positions(self) -> None:
        """
        Refresh all tracked positions with latest data from MT5.
        
        CRITICAL: This method detects positions closed at broker level (SL/TP hit)
        and records the trade completion for ML training data.
        """
        try:
            for position in self.tracker.get_all_positions():
                mt5_position = self.connector.get_position_by_ticket(position.ticket)
                if mt5_position:
                    # Update tracker with fresh data
                    self.tracker.update_position(
                        position.ticket,
                        mt5_position.get('price_current', position.current_price),
                        mt5_position.get('profit', position.profit)
                    )
                else:
                    # Position no longer exists in MT5 - it was closed (SL/TP hit or manual close)
                    # CRITICAL: Record trade closure with PnL for ML training
                    self._record_broker_closed_trade(position)
                    self.tracker.remove_position(position.ticket)
                    
        except Exception as e:
            logger.error(f"Error refreshing positions: {e}", exc_info=True)

    def _record_broker_closed_trade(self, position) -> None:
        """
        Record a trade that was closed at the broker level (SL/TP hit).
        
        This ensures trades closed by broker-side stop/target orders are properly
        recorded for ML training data collection.
        
        Args:
            position: The tracked position that is no longer open in MT5
        """
        try:
            from cthulu.connector.mt5_connector import mt5
            
            # Query deal history to get actual exit details
            exit_price = None
            exit_time = None
            profit = None
            exit_reason = "broker_close"
            
            # Try to get deal history for this position
            try:
                # Query recent deals for this ticket
                from datetime import datetime, timedelta, timezone
                end_time = datetime.now(timezone.utc)
                start_time = end_time - timedelta(days=1)  # Look back 1 day
                
                deals = mt5.history_deals_get(
                    position=position.ticket,
                    from_date=start_time,
                    to_date=end_time
                )
                
                if deals:
                    # Find the closing deal (type 1 = close)
                    for deal in deals:
                        if hasattr(deal, 'entry') and deal.entry == 1:  # DEAL_ENTRY_OUT
                            exit_price = getattr(deal, 'price', None)
                            exit_time = datetime.fromtimestamp(deal.time, tz=timezone.utc) if hasattr(deal, 'time') else datetime.now(timezone.utc)
                            profit = getattr(deal, 'profit', None)
                            
                            # Determine exit reason from deal comment or type
                            comment = getattr(deal, 'comment', '') or ''
                            if 'sl' in comment.lower() or 'stop' in comment.lower():
                                exit_reason = "stop_loss"
                            elif 'tp' in comment.lower() or 'profit' in comment.lower():
                                exit_reason = "take_profit"
                            break
            except Exception as e:
                logger.debug(f"Could not query deal history for {position.ticket}: {e}")
            
            # Fallback: estimate PnL from last known position data
            if profit is None:
                profit = getattr(position, 'profit', 0) or getattr(position, 'unrealized_pnl', 0) or 0
            if exit_price is None:
                exit_price = getattr(position, 'current_price', position.open_price)
            if exit_time is None:
                from datetime import datetime, timezone
                exit_time = datetime.now(timezone.utc)
            
            # Log the closure
            logger.info(f"Broker-closed trade detected: #{position.ticket} | "
                       f"Exit: {exit_price} | PnL: {profit:.2f} | Reason: {exit_reason}")
            
            # Update database with trade exit
            try:
                self.db.update_trade_exit(
                    order_id=position.ticket,
                    exit_price=exit_price,
                    exit_time=exit_time,
                    profit=profit,
                    exit_reason=exit_reason
                )
            except Exception as e:
                logger.warning(f"Failed to update trade exit in database: {e}")
            
            # Calculate trade duration
            duration_seconds = 0
            try:
                open_time = getattr(position, 'open_time', None)
                if open_time:
                    if hasattr(open_time, 'timestamp'):
                        duration_seconds = (exit_time - open_time).total_seconds()
                    else:
                        duration_seconds = 0
            except Exception:
                pass
            
            # Emit TRADE_CLOSED event for ML collection
            self._emit_trade_closed_event(position, exit_price, profit, exit_reason, duration_seconds)
            
        except Exception as e:
            logger.error(f"Error recording broker-closed trade {position.ticket}: {e}", exc_info=True)

    def _emit_trade_closed_event(self, position, exit_price: float, profit: float, 
                                  exit_reason: str, duration_seconds: float) -> None:
        """
        Emit TRADE_CLOSED event for ML data collection.
        
        This event is consumed by the ML collector to build training datasets
        with actual trade outcomes.
        """
        try:
            # Get ML collector if available via execution engine
            ml_collector = getattr(self.execution_engine, 'ml_collector', None)
            
            if ml_collector:
                outcome = 'WIN' if profit > 0 else ('LOSS' if profit < 0 else 'BREAKEVEN')
                
                trade_closed_payload = {
                    'event_type': 'TRADE_CLOSED',
                    'ticket': position.ticket,
                    'symbol': getattr(position, 'symbol', 'UNKNOWN'),
                    'side': getattr(position, 'type', getattr(position, 'side', 'UNKNOWN')),
                    'volume': getattr(position, 'volume', 0),
                    'entry_price': getattr(position, 'open_price', 0),
                    'exit_price': exit_price,
                    'stop_loss': getattr(position, 'sl', None),
                    'take_profit': getattr(position, 'tp', None),
                    'pnl': profit,
                    'outcome': outcome,
                    'exit_reason': exit_reason,
                    'duration_seconds': duration_seconds,
                    'magic_number': getattr(position, 'magic_number', 0),
                    'strategy_name': getattr(position, 'strategy_name', 'unknown'),
                    'timestamp': datetime.now().isoformat()
                }
                
                # Record via ML collector
                if hasattr(ml_collector, 'record_event'):
                    ml_collector.record_event('trade_closed', trade_closed_payload)
                elif hasattr(ml_collector, 'record_execution'):
                    ml_collector.record_execution(trade_closed_payload)
                    
                logger.debug(f"Emitted TRADE_CLOSED event for #{position.ticket}: {outcome}, PnL={profit:.2f}")
                
        except Exception as e:
            logger.debug(f"Failed to emit TRADE_CLOSED event: {e}")
    
    def persist_position(self, position) -> None:
        """
        Save position to database.
        
        Args:
            position: PositionInfo object to persist
        """
        try:
            # Get current_price, defaulting to open_price if not available
            current_price = getattr(position, 'current_price', None) or getattr(position, 'price_current', None) or position.open_price
            
            self.db.save_position(
                ticket=position.ticket,
                symbol=position.symbol,
                type=position.type,
                volume=position.volume,
                open_price=position.open_price,
                current_price=current_price,
                sl=position.sl,
                tp=position.tp,
                open_time=position.open_time,
                magic_number=position.magic_number,
                comment=position.comment,
                strategy_name=position.strategy_name
            )
        except Exception as e:
            logger.error(f"Error persisting position {position.ticket}: {e}", exc_info=True)
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get position statistics.
        
        Returns:
            Dict with position metrics
        """
        positions = self.tracker.get_all_positions()
        
        return {
            'total_positions': len(positions),
            'total_profit': sum(p.profit for p in positions),
            'total_exposure': sum(abs(p.volume) for p in positions),
            'long_positions': len([p for p in positions if p.type == "buy"]),
            'short_positions': len([p for p in positions if p.type == "sell"]),
            'external_positions': len([p for p in positions if p.is_external]),
            'symbols': list(set(p.symbol for p in positions))
        }
    
    def is_healthy(self) -> bool:
        """
        Check if position lifecycle is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            # Check connector
            if not self.connector.is_connected():
                logger.error("MT5 connector not connected")
                return False
            
            # Check execution engine
            if not hasattr(self.execution_engine, 'execute_order'):
                logger.error("Execution engine missing execute_order method")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking position lifecycle health: {e}", exc_info=True)
            return False




