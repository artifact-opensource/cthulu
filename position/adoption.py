"""
Trade Adoption Module

Handles detection and adoption of external (manual) trades that were placed
outside of Herald. This allows Cthulu to manage positions that users create
manually in MT5.

Responsibilities:
- Scan for external/manual trades
- Apply Cthulu's exit strategies to external trades
- Policy-based filtering (which trades to adopt)
- Logging and tracking of adoptions

Does NOT:
- Execute new trades (see lifecycle.py)
- Track position state (see tracker.py)
- Make risk decisions (see risk/evaluator.py)
"""

from dataclasses import dataclass
from typing import List, Optional, Set
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class TradeAdoptionPolicy:
    """
    Configuration for trade adoption behavior.
    """
    # Enable/disable adoption
    enabled: bool = True
    
    # Symbol filters
    allowed_symbols: Optional[List[str]] = None  # None = all symbols
    blocked_symbols: List[str] = None  # Symbols to never adopt
    
    # Age filters
    max_age_hours: Optional[float] = None  # Don't adopt trades older than this
    min_age_seconds: float = 60  # Wait this long before adopting (avoid race conditions)
    
    # Size filters
    min_volume: Optional[float] = None
    max_volume: Optional[float] = None
    
    # Magic number filters
    excluded_magic_numbers: Set[int] = None  # Don't adopt these magic numbers
    
    # Safety - ATR-based SL/TP (CRITICAL FIX)
    apply_emergency_sl: bool = True  # Add SL if none exists
    use_atr_based_sltp: bool = True  # Use ATR-based calculation (not fixed points)
    emergency_sl_atr_mult: float = 2.0  # SL distance as multiple of ATR
    emergency_tp_atr_mult: float = 4.0  # TP distance as multiple of ATR
    # Fallback fixed points (only used if ATR unavailable)
    emergency_sl_points: float = 100  # Emergency SL distance (fallback)
    apply_emergency_tp: bool = False  # Add TP if none exists
    emergency_tp_points: float = 100  # Emergency TP distance (fallback)
    
    # Logging
    log_only: bool = False  # If True, only log orphans without adopting
    
    def __post_init__(self):
        """Initialize default values for mutable fields."""
        if self.blocked_symbols is None:
            self.blocked_symbols = []
        if self.excluded_magic_numbers is None:
            self.excluded_magic_numbers = set()


class TradeAdoptionManager:
    """
    Manages adoption of external trades into Cthulu's management system.
    
    This class identifies manual trades placed outside Cthulu and brings them
    under Herald's exit strategy management.
    """
    
    def __init__(self, connector, position_tracker, position_lifecycle, 
                 policy: Optional[TradeAdoptionPolicy] = None):
        """
        Initialize the trade adoption manager.
        
        Args:
            connector: MT5 connector
            position_tracker: PositionTracker instance
            position_lifecycle: PositionLifecycle instance
            policy: TradeAdoptionPolicy configuration
        """
        self.connector = connector
        self.tracker = position_tracker
        self.lifecycle = position_lifecycle
        self.policy = policy or TradeAdoptionPolicy()
        
        # Track which tickets we've already adopted
        self._adopted_tickets: Set[int] = set()
        
        logger.info(f"TradeAdoptionManager initialized (enabled={self.policy.enabled})")
    
    def scan_and_adopt(self) -> int:
        """
        Scan for external trades and adopt them based on policy.
        
        Returns:
            Number of trades adopted in this scan
        """
        if not self.policy.enabled:
            return 0
        
        try:
            # Get all trades identified as external
            external_trades = self._identify_external_trades()
            
            adopted_count = 0
            for trade in external_trades:
                if self._should_adopt(trade):
                    if self._adopt_trade(trade):
                        adopted_count += 1
            
            if adopted_count > 0:
                logger.info(f"Adopted {adopted_count} external trades")
            
            return adopted_count
            
        except Exception as e:
            logger.error(f"Error during trade adoption scan: {e}", exc_info=True)
            return 0
    
    def _identify_external_trades(self) -> List[dict]:
        """
        Identify trades that were not opened by Cthulu.
        
        Returns:
            List of external trade dicts from MT5
        """
        try:
            # Get all open positions from MT5
            all_positions = self.connector.get_open_positions()
            if not all_positions:
                return []
            
            # Filter to find external trades
            external_trades = []
            for position in all_positions:
                ticket = position.get('ticket')
                
                # Skip if already tracking this ticket
                if self.tracker.get_position(ticket):
                    continue
                
                # Skip if already adopted in a previous scan
                if ticket in self._adopted_tickets:
                    continue
                
                # This is an external trade
                external_trades.append(position)
            
            return external_trades
            
        except Exception as e:
            logger.error(f"Error identifying external trades: {e}", exc_info=True)
            return []
    
    def _should_adopt(self, trade: dict) -> bool:
        """
        Determine if a trade should be adopted based on policy.
        
        Args:
            trade: Trade dict from MT5
            
        Returns:
            True if trade should be adopted, False otherwise
        """
        try:
            symbol = trade.get('symbol')
            ticket = trade.get('ticket')
            volume = trade.get('volume', 0.0)
            magic = trade.get('magic', 0)
            open_time = trade.get('time', datetime.now())
            if isinstance(open_time, (int, float)):
                open_time = datetime.fromtimestamp(open_time)
            # Ensure timezone awareness for comparison
            if open_time.tzinfo is None:
                from datetime import timezone as tz
                open_time = open_time.replace(tzinfo=tz.utc)
            
            # Check symbol whitelist
            if self.policy.allowed_symbols and symbol not in self.policy.allowed_symbols:
                logger.debug(f"Trade {ticket} symbol {symbol} not in allowed list")
                return False
            
            # Check symbol blacklist
            if symbol in self.policy.blocked_symbols:
                logger.debug(f"Trade {ticket} symbol {symbol} is blocked")
                return False
            
            # Check magic number exclusions
            if magic in self.policy.excluded_magic_numbers:
                logger.debug(f"Trade {ticket} magic {magic} is excluded")
                return False
            
            # Check age limits - use timezone-aware datetime
            from datetime import timezone as tz
            now = datetime.now(tz.utc)
            age = now - open_time
            if self.policy.max_age_hours and age > timedelta(hours=self.policy.max_age_hours):
                logger.debug(f"Trade {ticket} too old ({age.total_seconds() / 3600:.1f}h)")
                return False
            
            if age < timedelta(seconds=self.policy.min_age_seconds):
                logger.debug(f"Trade {ticket} too new ({age.total_seconds():.0f}s)")
                return False
            
            # Check volume limits
            if self.policy.min_volume and volume < self.policy.min_volume:
                logger.debug(f"Trade {ticket} volume {volume} below minimum")
                return False
            
            if self.policy.max_volume and volume > self.policy.max_volume:
                logger.debug(f"Trade {ticket} volume {volume} above maximum")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking adoption policy: {e}", exc_info=True)
            return False
    
    def _adopt_trade(self, trade: dict) -> bool:
        """
        Adopt an external trade into Cthulu's management.
        
        Args:
            trade: Trade dict from MT5
            
        Returns:
            True if adopted successfully, False otherwise
        """
        try:
            from position.tracker import PositionInfo
            
            ticket = trade.get('ticket')
            symbol = trade.get('symbol')
            trade_type = trade.get('type')  # 0=buy, 1=sell
            volume = trade.get('volume', 0.0)
            open_price = trade.get('price_open', 0.0)
            current_price = trade.get('price_current', 0.0)
            sl = trade.get('sl')
            tp = trade.get('tp')
            profit = trade.get('profit', 0.0)
            open_time = trade.get('time', datetime.now())
            magic = trade.get('magic', 0)
            comment = trade.get('comment', '')
            
            # Convert trade type to string
            type_str = "buy" if trade_type == 0 else "sell"
            
            # Apply emergency SL/TP if configured - USE ATR-BASED CALCULATION
            if self.policy.apply_emergency_sl and not sl:
                # Try to get ATR for market-condition-based SL/TP
                atr = None
                if self.policy.use_atr_based_sltp:
                    try:
                        # Try to get ATR from lifecycle's dynamic SLTP manager
                        if hasattr(self.lifecycle, 'dynamic_sltp_manager') and self.lifecycle.dynamic_sltp_manager:
                            # Get recent market data to calculate ATR
                            # Check if connector has method to get recent data
                            if hasattr(self.connector, 'get_rates'):
                                import pandas as pd
                                rates = self.connector.get_rates(symbol, '1H', 100)  # Get last 100 H1 bars
                                if rates is not None and len(rates) > 0:
                                    # Calculate ATR if not in data
                                    if 'atr' in rates.columns:
                                        atr = rates['atr'].iloc[-1]
                                    else:
                                        # Calculate simple ATR
                                        high_low = rates['high'] - rates['low']
                                        high_close = abs(rates['high'] - rates['close'].shift())
                                        low_close = abs(rates['low'] - rates['close'].shift())
                                        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                                        atr = true_range.rolling(14).mean().iloc[-1]
                                    logger.info(f"Calculated ATR for {symbol}: {atr:.5f}")
                    except Exception as e:
                        logger.warning(f"Could not calculate ATR for {symbol}, using fallback: {e}")
                
                # Calculate SL based on ATR or fallback to fixed points
                if atr and atr > 0 and self.policy.use_atr_based_sltp:
                    # ATR-BASED SL/TP - PROPER MARKET CONDITION ADAPTATION
                    sl_distance = atr * self.policy.emergency_sl_atr_mult
                    if type_str == "buy":
                        sl = open_price - sl_distance
                    else:
                        sl = open_price + sl_distance
                    logger.info(f"Applied ATR-based SL to {ticket}: distance={sl_distance:.5f} ({self.policy.emergency_sl_atr_mult}x ATR={atr:.5f})")
                else:
                    # Fallback to fixed points
                    if type_str == "buy":
                        sl = open_price - self.policy.emergency_sl_points * self.connector.get_point(symbol)
                    else:
                        sl = open_price + self.policy.emergency_sl_points * self.connector.get_point(symbol)
                    logger.warning(f"Applied fixed-point SL to {ticket} (ATR unavailable)")
                
                # Modify position with emergency SL
                self.lifecycle.modify_position(ticket, sl=sl)
                logger.info(f"Applied emergency SL to external trade {ticket}")
            
            if self.policy.apply_emergency_tp and not tp:
                # Try to get ATR for TP calculation
                atr = None
                if self.policy.use_atr_based_sltp:
                    try:
                        if hasattr(self.connector, 'get_rates'):
                            import pandas as pd
                            rates = self.connector.get_rates(symbol, '1H', 100)
                            if rates is not None and len(rates) > 0:
                                if 'atr' in rates.columns:
                                    atr = rates['atr'].iloc[-1]
                                else:
                                    high_low = rates['high'] - rates['low']
                                    high_close = abs(rates['high'] - rates['close'].shift())
                                    low_close = abs(rates['low'] - rates['close'].shift())
                                    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                                    atr = true_range.rolling(14).mean().iloc[-1]
                    except Exception as e:
                        logger.warning(f"Could not calculate ATR for TP: {e}")
                
                # Calculate TP based on ATR or fallback
                if atr and atr > 0 and self.policy.use_atr_based_sltp:
                    # ATR-BASED TP
                    tp_distance = atr * self.policy.emergency_tp_atr_mult
                    if type_str == "buy":
                        tp = open_price + tp_distance
                    else:
                        tp = open_price - tp_distance
                    logger.info(f"Applied ATR-based TP to {ticket}: distance={tp_distance:.5f} ({self.policy.emergency_tp_atr_mult}x ATR={atr:.5f})")
                else:
                    # Fallback to fixed points
                    if type_str == "buy":
                        tp = open_price + self.policy.emergency_tp_points * self.connector.get_point(symbol)
                    else:
                        tp = open_price - self.policy.emergency_tp_points * self.connector.get_point(symbol)
                    logger.warning(f"Applied fixed-point TP to {ticket} (ATR unavailable)")
                
                # Modify position with emergency TP
                self.lifecycle.modify_position(ticket, tp=tp)
                logger.info(f"Applied emergency TP to external trade {ticket}")
            
            # Create PositionInfo for tracking
            position = PositionInfo(
                ticket=ticket,
                symbol=symbol,
                type=type_str,
                volume=volume,
                open_price=open_price,
                current_price=current_price,
                sl=sl,
                tp=tp,
                profit=profit,
                open_time=open_time,
                magic_number=magic,
                comment=f"[ADOPTED] {comment}",
                strategy_name="external",
                entry_reason="Manual trade adopted by Cthulu",
                is_external=True
            )
            
            # Add to tracker
            self.tracker.track_position(position)
            
            # Persist to database
            self.lifecycle.persist_position(position)
            
            # Mark as adopted
            self._adopted_tickets.add(ticket)
            
            # ==========================================================
            # PUBLISH ADOPTED TRADE EVENT TO EVENT BUS (Non-blocking)
            # ==========================================================
            try:
                from cthulu.observability.trade_event_bus import publish_trade_adopted
                publish_trade_adopted(
                    ticket=ticket,
                    symbol=symbol,
                    side=type_str.upper(),
                    volume=volume,
                    price=open_price,
                    stop_loss=sl,
                    take_profit=tp,
                    magic=magic,
                    original_comment=comment
                )
            except Exception as e:
                logger.debug(f"Event bus publish adopted (non-critical): {e}")
            
            logger.info(f"Adopted external trade {ticket}: {symbol} {type_str} {volume}")
            return True
            
        except Exception as e:
            logger.error(f"Error adopting trade {trade.get('ticket')}: {e}", exc_info=True)
            return False
    
    def get_adopted_count(self) -> int:
        """
        Get count of adopted trades.
        
        Returns:
            Number of trades adopted
        """
        return len(self._adopted_tickets)
    
    def get_adoption_statistics(self) -> dict:
        """
        Get adoption statistics.
        
        Returns:
            Dict with adoption metrics
        """
        external_positions = [p for p in self.tracker.get_all_positions() if p.is_external]
        
        return {
            'total_adopted': len(self._adopted_tickets),
            'currently_tracked': len(external_positions),
            'policy_enabled': self.policy.enabled,
            'symbols': list(set(p.symbol for p in external_positions))
        }
    
    def log_external_trade(self, trade: dict) -> None:
        """
        Log details of an external trade for analysis.
        
        Args:
            trade: Trade dict from MT5
        """
        logger.info(
            f"External trade detected: "
            f"Ticket={trade.get('ticket')}, "
            f"Symbol={trade.get('symbol')}, "
            f"Type={trade.get('type')}, "
            f"Volume={trade.get('volume')}, "
            f"Magic={trade.get('magic')}"
        )




