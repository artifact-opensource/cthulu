"""
Trade Manager

Manages external trades not placed by Herald, allowing the bot
to adopt and manage manual/external trades with its exit strategies.
"""

import logging
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
import time
from dataclasses import dataclass, field

from cthulu.connector.mt5_connector import mt5
from cthulu.position.manager import PositionInfo, PositionManager
from cthulu import constants


@dataclass
class TradeAdoptionPolicy:
    """
    Policy configuration for adopting external trades.
    
    Attributes:
        enabled: Whether to adopt external trades
        adopt_symbols: List of symbols to adopt (empty = all symbols)
        ignore_symbols: List of symbols to never adopt
        apply_exit_strategies: Whether to apply exit strategies to adopted trades
        apply_trailing_stop: Whether to apply trailing stops
        apply_time_based_exit: Whether to apply time-based exits
        max_adoption_age_hours: Max age of trade to adopt (0 = any age)
        log_only: If True, only log external trades without adopting
    """
    enabled: bool = True
    adopt_symbols: List[str] = field(default_factory=list)
    ignore_symbols: List[str] = field(default_factory=list)
    apply_exit_strategies: bool = True
    apply_trailing_stop: bool = True
    apply_time_based_exit: bool = True
    max_adoption_age_hours: float = 0.0  # 0 = no limit
    log_only: bool = False


# Backwards compatibility alias
OrphanPolicy = TradeAdoptionPolicy


class TradeManager:
    """
    Manages detection and adoption of trades not placed by Herald.
    
    This allows Cthulu to:
    1. Detect manual trades placed directly in MT5
    2. Detect trades from other EAs/bots
    3. Apply Herald's exit strategies to these external trades
    4. Track and log adopted trade performance
    """
    
    # Herald's magic number (trades placed by Cthulu have this)
    HERALD_MAGIC = constants.DEFAULT_MAGIC
    
    def __init__(
        self,
        position_manager: PositionManager,
        policy: Optional[TradeAdoptionPolicy] = None,
        magic_number: int = HERALD_MAGIC,
        default_stop_pct: float = 8.0,
        default_rr: float = 2.0,
        config: Optional[Dict[str, Any]] = None
    ):
        """Initialize trade manager.

        Args:
            position_manager: Herald's position manager
            policy: Trade adoption policy
            magic_number: Herald's magic number for identifying its own trades
            default_stop_pct: Default emergency stop percent to apply when adopting
            default_rr: Default risk:reward ratio to set TP when adopting
            config: Optional full configuration dict used to derive exit/risk defaults
        """
        """Initialize trade manager.

        Args:
            position_manager: Herald's position manager
            policy: Trade adoption policy
            magic_number: Herald's magic number for identifying its own trades
            default_stop_pct: Default emergency stop percent to apply when adopting
            default_rr: Default risk:reward ratio to set TP when adopting
        """
        """
        Initialize trade manager.
        
        Args:
            position_manager: Herald's position manager
            policy: Trade adoption policy
            magic_number: Herald's magic number for identifying its own trades
        """
        self.position_manager = position_manager
        self.policy = policy or TradeAdoptionPolicy()
        self.magic_number = magic_number
        self.default_stop_pct = default_stop_pct
        self.default_rr = default_rr
        self.logger = logging.getLogger("Cthulu.trade_manager")
        
        # Track adopted trades
        self._adopted_tickets: Set[int] = set()
        self._adoption_log: List[Dict[str, Any]] = []
        # Pending SL/TP applications for adopted trades that failed (ticket -> dict)
        self._pending_sl_tp: Dict[int, Dict[str, Any]] = {}
        self.config = config or {}
        # Pause control used by monitors/alerts to temporarily block new orders
        self._paused_until: Optional[float] = None
        
    def scan_for_external_trades(self) -> List[PositionInfo]:
        """
        Scan MT5 for trades not placed by Herald.
        
        Returns:
            List of external trade PositionInfo objects
        """
        if not self.policy.enabled:
            return []
            
        try:
            # Get all MT5 positions
            mt5_positions = mt5.positions_get()
            
            if mt5_positions is None:
                return []
                
            external_trades = []
            self.logger.debug(f"MT5 reported {len(mt5_positions)} open positions")
            
            for pos in mt5_positions:
                # Log basic position info for diagnostics
                try:
                    self.logger.debug(
                        f"Found position: #{pos.ticket} symbol={pos.symbol} magic={getattr(pos,'magic',None)} "
                        f"type={getattr(pos,'type',None)} volume={getattr(pos,'volume',0)} "
                        f"open={getattr(pos,'price_open',0)} sl={getattr(pos,'sl',0)} tp={getattr(pos,'tp',0)} time={getattr(pos,'time',None)}"
                    )
                except Exception:
                    # Non-fatal - continue
                    pass
                
                # Skip if already tracked by Herald
                if pos.ticket in self.position_manager._positions:
                    self.logger.debug(f"Skipping #{pos.ticket}: already tracked in position manager")
                    continue
                    
                # Skip if already adopted
                if pos.ticket in self._adopted_tickets:
                    self.logger.debug(f"Skipping #{pos.ticket}: already adopted previously")
                    continue
                    
                # Check if this is Herald's own trade
                if pos.magic == self.magic_number:
                    # Cthulu trade not in registry - reconcile into position manager
                    try:
                        self.logger.info(f"Reconciling Cthulu trade #{pos.ticket} into registry")
                        # Build PositionInfo and add to position manager so the bot knows about its own trade
                        pi = self._create_position_info(pos)
                        # Use add_position (compat shim) to avoid requiring an ExecutionResult
                        try:
                            self.position_manager.add_position(pi)
                            self.logger.info(f"Reconciled Cthulu trade #{pos.ticket} added to registry")
                        except Exception as e:
                            self.logger.error(f"Failed to add reconciled trade #{pos.ticket} to registry: {e}")
                    except Exception:
                        self.logger.exception(f"Failed to reconcile Cthulu trade #{getattr(pos, 'ticket', 'unknown')}")
                    # Skip adoption for own trades
                    continue
                    
                # This is an external trade - check adoption policy
                if self._should_adopt(pos):
                    trade_info = self._create_position_info(pos)
                    external_trades.append(trade_info)
                    
            return external_trades
            
        except Exception as e:
            self.logger.error(f"Error scanning for external trades: {e}", exc_info=True)
            return []
            
    def _normalize_symbol(self, s: str) -> str:
        """Normalize symbol string for flexible matching (remove non-alphanumerics, upper-case)."""
        if not s:
            return ""
        return ''.join(ch for ch in s.upper() if ch.isalnum())

    def _should_adopt(self, pos) -> bool:
        """
        Check if a position should be adopted based on policy.
        
        Args:
            pos: MT5 position object
            
        Returns:
            True if position should be adopted
        """
        # Normalize symbol for robust comparisons
        pos_sym_norm = self._normalize_symbol(pos.symbol)

        # Check symbol filters (apply normalization)
        if self.policy.adopt_symbols:
            adopt_norm = [self._normalize_symbol(s) for s in self.policy.adopt_symbols]
            if pos_sym_norm not in adopt_norm:
                self.logger.debug(
                    f"Skipping #{pos.ticket}: symbol {pos.symbol} (norm={pos_sym_norm}) not in adopt list {self.policy.adopt_symbols} (norm={adopt_norm})"
                )
                return False
                
        if self.policy.ignore_symbols:
            ignore_norm = [self._normalize_symbol(s) for s in self.policy.ignore_symbols]
            if pos_sym_norm in ignore_norm:
                self.logger.debug(
                    f"Skipping #{pos.ticket}: symbol {pos.symbol} (norm={pos_sym_norm}) is in ignore list {self.policy.ignore_symbols}"
                )
                return False
                
        # Check age limit
        if self.policy.max_adoption_age_hours > 0:
            age_hours = (datetime.now().timestamp() - pos.time) / 3600.0
            if age_hours > self.policy.max_adoption_age_hours:
                self.logger.debug(
                    f"Skipping trade #{pos.ticket}: too old ({age_hours:.1f}h)"
                )
                return False
                
        return True
        
    def _create_position_info(self, pos) -> PositionInfo:
        """
        Create PositionInfo from MT5 position object.
        
        Args:
            pos: MT5 position object
            
        Returns:
            PositionInfo object
        """
        return PositionInfo(
            ticket=pos.ticket,
            symbol=pos.symbol,
            side="BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL",
            volume=pos.volume,
            open_price=pos.price_open,
            open_time=datetime.fromtimestamp(pos.time),
            stop_loss=pos.sl if pos.sl > 0 else 0.0,
            take_profit=pos.tp if pos.tp > 0 else 0.0,
            current_price=pos.price_current,
            unrealized_pnl=pos.profit,
            commission=getattr(pos, 'commission', 0.0),
            swap=getattr(pos, 'swap', 0.0),
            magic_number=pos.magic,
            comment=getattr(pos, 'comment', ''),
            metadata={
                'adopted': True,
                'adoption_time': datetime.now().isoformat(),
                'original_magic': pos.magic
            }
        )
        
    def adopt_trades(self, trades: List[PositionInfo]) -> int:
        """
        Adopt external trades into Herald's position manager and apply protective SL/TP.

        Returns:
            Number of trades adopted
        """
        if self.policy.log_only:
            for trade in trades:
                self.logger.info(
                    f"[LOG ONLY] Detected external trade: #{trade.ticket} "
                    f"{trade.symbol} {trade.side} {trade.volume:.2f} lots, "
                    f"P&L: ${trade.unrealized_pnl:.2f}"
                )
            return 0

        adopted_count = 0

        for trade in trades:
            try:
                # Add to position manager registry
                self.position_manager.add_position(trade)
                self._adopted_tickets.add(trade.ticket)
                adopted_count += 1

                # Log adoption
                self._adoption_log.append({
                    'ticket': trade.ticket,
                    'symbol': trade.symbol,
                    'side': trade.side,
                    'volume': trade.volume,
                    'adoption_time': datetime.now().isoformat(),
                    'original_magic': trade.magic_number,
                    'pnl_at_adoption': trade.unrealized_pnl
                })

                self.logger.info(
                    f"Adopted trade: #{trade.ticket} | "
                    f"{trade.symbol} {trade.side} {trade.volume:.2f} lots @ {trade.open_price:.5f}, "
                    f"Current P&L: ${trade.unrealized_pnl:.2f}"
                )

                # Apply protective SL/TP if configured to do so
                try:
                    if self.policy.apply_exit_strategies:
                        # Prefer config values if available
                        pct = None
                        rr = None
                        try:
                            pct = float(self.config.get('risk', {}).get('emergency_stop_loss_pct'))
                        except Exception:
                            pct = getattr(self, 'default_stop_pct', 8.0)
                        try:
                            rr = float(self.config.get('strategy', {}).get('params', {}).get('risk_reward_ratio'))
                        except Exception:
                            rr = getattr(self, 'default_rr', 2.0)

                        entry = trade.open_price
                        if trade.side == 'BUY':
                            sl = round(entry * (1.0 - pct / 100.0), 5)
                            tp = round(entry + (entry - sl) * rr, 5)
                        else:
                            sl = round(entry * (1.0 + pct / 100.0), 5)
                            tp = round(entry - (sl - entry) * rr, 5)

                        # Only set if not already present
                        _pos = self.position_manager.get_position(trade.ticket)
                        if _pos and ((_pos.stop_loss == 0.0 and sl) or (_pos.take_profit == 0.0 and tp)):
                            success = self.position_manager.set_sl_tp(trade.ticket, sl=sl, tp=tp)
                            if success:
                                self.logger.info(f"Applied protective SL/TP to adopted trade #{trade.ticket}: SL={sl:.5f}, TP={tp:.5f}")
                                # If there was a pending record, remove it
                                if trade.ticket in self._pending_sl_tp:
                                    del self._pending_sl_tp[trade.ticket]
                            else:
                                # Immediate aggressive retry loop (small sleeps) before falling back to queue
                                err = mt5.last_error()
                                err_msg = str(err) if err else 'unknown error'
                                self.logger.warning(f"Initial SL/TP apply failed for #{trade.ticket} (error: {err_msg}), starting aggressive retry")
                                # Exponential backoff retry strategy (1s,2s,4s,8s)
                                retried = False
                                backoff = 1
                                for attempt in range(4):
                                    try:
                                        time.sleep(backoff)
                                        self.logger.debug(f"Retrying SL/TP for #{trade.ticket} (attempt {attempt+1}, backoff={backoff}s)")
                                        success = self.position_manager.set_sl_tp(trade.ticket, sl=sl, tp=tp)
                                        if success:
                                            retried = True
                                            self.logger.info(f"Applied SL/TP on retry to adopted trade #{trade.ticket}: SL={sl:.5f}, TP={tp:.5f}")
                                            if trade.ticket in self._pending_sl_tp:
                                                del self._pending_sl_tp[trade.ticket]
                                            break
                                    except Exception as e:
                                        self.logger.debug(f"Retry attempt {attempt+1} error for #{trade.ticket}: {e}")
                                    backoff = min(backoff * 2, 60)
                                if not retried:
                                    # Record pending SL/TP to retry later and capture MT5 error
                                    err = mt5.last_error()
                                    err_msg = str(err) if err else 'unknown error'
                                    self.logger.warning(f"Failed to apply SL/TP to adopted trade #{trade.ticket} after retries; queuing for retry (error: {err_msg})")
                                    if 'AutoTrading' in err_msg or 'auto' in err_msg.lower():
                                        self.logger.warning("AutoTrading appears to be disabled in the MT5 client. Please enable AutoTrading to allow SL/TP updates; Cthulu will retry automatically.")
                                    now_ts = int(time.time())
                                    self._pending_sl_tp[trade.ticket] = {
                                        'sl': sl,
                                        'tp': tp,
                                        'attempts': self._pending_sl_tp.get(trade.ticket, {}).get('attempts', 0) + 1,
                                        'last_error': err_msg,
                                        'next_retry_ts': now_ts + 2 ** min(self._pending_sl_tp.get(trade.ticket, {}).get('attempts', 0), 6)
                                    }
                except Exception as e:
                    self.logger.error(f"Error applying SL/TP to adopted trade #{trade.ticket}: {e}")


            except Exception as e:
                self.logger.error(
                    f"Failed to adopt trade #{trade.ticket}: {e}"
                )

        return adopted_count

    def pause_trading(self, duration_seconds: float):
        """Pause new order execution for the specified number of seconds."""
        try:
            self._paused_until = time.time() + float(duration_seconds)
            self.logger.info(f"Trading paused for {duration_seconds}s until {self._paused_until}")
        except Exception:
            self.logger.exception('Failed to set pause')

    def is_paused(self) -> bool:
        """Return whether trading is currently paused by TradeManager."""
        if self._paused_until is None:
            return False
        return time.time() < self._paused_until
        
    def _retry_pending_sl_tp(self):
        """Retry setting SL/TP for any adopted trades that previously failed to update."""
        if not self._pending_sl_tp:
            return
        self.logger.debug(f"Retrying SL/TP for {len(self._pending_sl_tp)} pending trade(s)")
        for ticket, info in list(self._pending_sl_tp.items()):
            try:
                now = int(time.time())
                next_retry = info.get('next_retry_ts', 0)
                if now < next_retry:
                    self.logger.debug(f"Skipping retry for #{ticket}; next retry at {next_retry} (now={now})")
                    continue

                success = self.position_manager.set_sl_tp(ticket, sl=info.get('sl'), tp=info.get('tp'))
                info['attempts'] = info.get('attempts', 0) + 1
                if success:
                    self.logger.info(f"Successfully applied pending SL/TP to #{ticket}: SL={info.get('sl')}, TP={info.get('tp')}")
                    del self._pending_sl_tp[ticket]
                else:
                    attempts = info['attempts']
                    # exponential backoff for next retry (cap at 5 minutes)
                    delay = min(2 ** min(attempts, 8), 300)
                    info['next_retry_ts'] = int(time.time()) + delay
                    self.logger.debug(f"Retry {attempts} failed for #{ticket}; scheduling next retry in {delay}s")
                    if attempts >= 6:
                        self.logger.warning(f"Giving up on SL/TP for #{ticket} after {attempts} attempts")
                        del self._pending_sl_tp[ticket]
            except Exception as e:
                self.logger.error(f"Error retrying SL/TP for #{ticket}: {e}", exc_info=True)

    def scan_and_adopt(self) -> int:
        """
        Convenience method: scan for external trades and adopt them.
        
        Returns:
            Number of trades adopted
        """
        # First, retry applying any pending SL/TP changes
        try:
            self._retry_pending_sl_tp()
        except Exception as e:
            self.logger.error(f"Error during pending SL/TP retry: {e}", exc_info=True)

        trades = self.scan_for_external_trades()
        
        if trades:
            self.logger.info(f"Found {len(trades)} external trades")
            adopted = self.adopt_trades(trades)
            return adopted
            
        return 0
        
    def get_adopted_count(self) -> int:
        """Get total number of adopted trades."""
        return len(self._adopted_tickets)
        
    def get_adoption_log(self) -> List[Dict[str, Any]]:
        """Get log of all adopted trades."""
        return self._adoption_log.copy()
        
    def is_adopted(self, ticket: int) -> bool:
        """Check if a ticket was adopted."""
        return ticket in self._adopted_tickets


# Backwards compatibility alias
OrphanTradeManager = TradeManager




