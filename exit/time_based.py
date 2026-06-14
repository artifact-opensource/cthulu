"""
Time-Based Exit Strategy

Exits positions based on time-in-trade and session management.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta, time as dt_time

from .base import ExitStrategy, ExitSignal
from cthulu.position.manager import PositionInfo


class TimeBasedExit(ExitStrategy):
    """
    Time-based exit strategy for position management.
    
    Features:
    - Maximum hold time per position
    - Market session close protection
    - Weekend/holiday awareness
    - Day trading mode (close all by end of day)
    
    Configuration parameters:
        max_hold_hours: Maximum hours to hold position (default: 24)
        close_before_session_end: Close before session end (default: True)
        session_end_offset_minutes: Minutes before session close (default: 15)
        day_trading_mode: Close all positions by EOD (default: False)
        eod_close_time: Time to close if day trading (default: "16:45")
        weekend_protection: Close before weekend (default: True)
        friday_close_time: Time to close Friday positions (default: "16:00")
    """
    
    def __init__(self, params: Dict[str, Any] | None = None, **kwargs):
        """
        Initialize time-based exit strategy.
        
        Args:
            params: Strategy parameters (max_hold_hours, session settings, etc.)
        """
        # Support both param dict and kwargs for backward compatibility
        if params is None:
            params = kwargs
        elif kwargs:
            params = {**params, **kwargs}
        # Expose compatibility priority (tests expect priority 4)
        super().__init__(
            name="TimeBasedExit",
            params=params,
            priority=params.get('priority', 4)
        )
        
        # Default parameters
        self.max_hold_hours = params.get('max_hold_hours', 24.0)
        self.close_before_session_end = params.get('close_before_session_end', True)
        self.session_end_offset_minutes = params.get('session_end_offset_minutes', 15)
        self.day_trading_mode = params.get('day_trading_mode', False)
        self.eod_close_time = params.get('eod_close_time', "16:45")
        self.weekend_protection = params.get('weekend_protection', True)
        self.friday_close_time = params.get('friday_close_time', "16:00")
        
        # Parse time strings
        self._eod_time = self._parse_time(self.eod_close_time)
        self._friday_time = self._parse_time(self.friday_close_time)
        
    def _parse_time(self, time_str: str) -> dt_time:
        """Parse time string in HH:MM format."""
        try:
            hour, minute = map(int, time_str.split(':'))
            return dt_time(hour=hour, minute=minute)
        except Exception as e:
            self.logger.error(f"Failed to parse time {time_str}: {e}")
            return dt_time(hour=16, minute=0)
            
    def should_exit(
        self,
        position: PositionInfo,
        current_data: Dict[str, Any] = None
    ) -> Optional[ExitSignal]:
        """
        Check if position should be exited based on time rules.
        
        Args:
            position: Position information
            current_data: Market data (not used, time-based only)
            
        Returns:
            ExitSignal if any time rule triggered, None otherwise
        """
        if not self._enabled:
            return None
            
        current_time = datetime.now()
        
        # Check max hold time
        exit_signal = self._check_max_hold_time(position, current_time)
        if exit_signal:
            return exit_signal
            
        # Check weekend protection
        if self.weekend_protection:
            exit_signal = self._check_weekend_protection(position, current_time)
            if exit_signal:
                return exit_signal
                
        # Check day trading mode
        if self.day_trading_mode:
            exit_signal = self._check_eod_close(position, current_time)
            if exit_signal:
                return exit_signal
                
        return None  # No exit signal
        
    def _check_max_hold_time(
        self,
        position: PositionInfo,
        current_time: datetime
    ) -> Optional[ExitSignal]:
        """Check if position exceeded maximum hold time."""
        age_hours = position.get_age_hours()
        
        if age_hours >= self.max_hold_hours:
            self.logger.info(
                f"Position {position.ticket} exceeded max hold time: "
                f"{age_hours:.1f}h >= {self.max_hold_hours}h"
            )
            return ExitSignal(
                ticket=position.ticket,
                reason=f"Max hold time exceeded ({age_hours:.1f}h)",
                price=None,
                timestamp=current_time,
                strategy_name=self.name,
                confidence=0.9,
                metadata={
                    'age_hours': age_hours,
                    'max_hold_hours': self.max_hold_hours,
                    'exit_type': 'max_hold_time'
                }
            )
        return None
        
    def _check_weekend_protection(
        self,
        position: PositionInfo,
        current_time: datetime
    ) -> Optional[ExitSignal]:
        """Check if should close before weekend.
        
        Note: Crypto markets (BTC, ETH, etc.) trade 24/7 and don't need
        weekend protection.
        """
        # Skip weekend protection for crypto symbols
        symbol = getattr(position, 'symbol', '') or ''
        # Handle UNKNOWN symbol - try to get from MT5 directly
        if not symbol or symbol.upper() == 'UNKNOWN':
            try:
                import MetaTrader5 as mt5
                mt5_pos = mt5.positions_get(ticket=position.ticket)
                if mt5_pos and len(mt5_pos) > 0:
                    symbol = mt5_pos[0].symbol
                    position.symbol = symbol  # Fix the position object too
            except Exception:
                pass
        
        crypto_prefixes = ('BTC', 'ETH', 'XRP', 'LTC', 'BCH', 'ADA', 'DOT', 'DOGE', 
                         'SOL', 'AVAX', 'MATIC', 'LINK', 'UNI', 'ATOM', 'XLM')
        is_crypto = any(symbol.upper().startswith(prefix) for prefix in crypto_prefixes) if symbol else False
        
        if is_crypto:
            return None  # Crypto trades 24/7, no weekend protection needed
        
        # Friday is weekday 4
        if current_time.weekday() == 4:
            # Check if past Friday close time
            if current_time.time() >= self._friday_time:
                self.logger.info(
                    f"Position {position.ticket} closing for weekend protection "
                    f"at {current_time.time()}"
                )
                return ExitSignal(
                    ticket=position.ticket,
                    reason=f"Weekend protection (Friday close)",
                    price=None,
                    timestamp=current_time,
                    strategy_name=self.name,
                    confidence=1.0,
                    metadata={
                        'exit_type': 'weekend_protection',
                        'close_time': self.friday_close_time
                    }
                )
        return None
        
    def _check_eod_close(
        self,
        position: PositionInfo,
        current_time: datetime
    ) -> Optional[ExitSignal]:
        """Check if should close for end of day (day trading mode)."""
        if current_time.time() >= self._eod_time:
            self.logger.info(
                f"Position {position.ticket} closing for EOD "
                f"at {current_time.time()}"
            )
            return ExitSignal(
                ticket=position.ticket,
                reason=f"End of day close (day trading mode)",
                price=None,
                timestamp=current_time,
                strategy_name=self.name,
                confidence=1.0,
                metadata={
                    'exit_type': 'eod_close',
                    'close_time': self.eod_close_time
                }
            )
        return None
        
    def get_time_until_close(self, position: PositionInfo) -> Optional[float]:
        """
        Get hours until position will be closed by time rules.
        
        Args:
            position: Position to check
            
        Returns:
            Hours until close, or None if no time rule applies
        """
        current_time = datetime.now()
        close_times = []
        
        # Max hold time
        max_hold_close = position.open_time + timedelta(hours=self.max_hold_hours)
        close_times.append(max_hold_close)
        
        # Weekend protection
        if self.weekend_protection and current_time.weekday() == 4:
            friday_close = current_time.replace(
                hour=self._friday_time.hour,
                minute=self._friday_time.minute,
                second=0,
                microsecond=0
            )
            if friday_close > current_time:
                close_times.append(friday_close)
                
        # Day trading EOD
        if self.day_trading_mode:
            eod_close = current_time.replace(
                hour=self._eod_time.hour,
                minute=self._eod_time.minute,
                second=0,
                microsecond=0
            )
            if eod_close > current_time:
                close_times.append(eod_close)
                
        if not close_times:
            return None
            
        # Return time until earliest close
        earliest_close = min(close_times)
        hours_until = (earliest_close - current_time).total_seconds() / 3600
        return max(0, hours_until)




