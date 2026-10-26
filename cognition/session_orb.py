"""
Session-Based Opening Range Breakout (ORB) System.

Based on MQL5 handbook implementation - detects opening ranges for
different trading sessions and generates signals on breakouts.

Sessions:
- London: 08:00-08:30 UTC (default 30 min range)
- New York: 13:30-14:00 UTC
- Asian: 00:00-00:30 UTC
- Custom: User-defined

Logic:
1. Define opening range (high/low) during first N minutes of session
2. Wait for breakout above high (bullish) or below low (bearish)
3. Optional: Require N bars to close beyond level for confirmation
4. Execute trade in breakout direction with ATR-based SL/TP
"""

import logging
from datetime import datetime, time, timedelta
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class SessionType(Enum):
    """Trading session types."""
    LONDON = "london"
    NEW_YORK = "new_york"
    ASIAN = "asian"
    CUSTOM = "custom"


@dataclass
class SessionConfig:
    """Configuration for a trading session."""
    name: str
    start_hour: int
    start_minute: int
    range_duration_minutes: int = 30
    timezone_offset: int = 0  # Hours from UTC
    
    @property
    def start_time(self) -> time:
        return time(self.start_hour, self.start_minute)


@dataclass
class OpeningRange:
    """Represents a detected opening range."""
    session: str
    date: datetime
    range_start: datetime
    range_end: datetime
    high: float
    low: float
    is_complete: bool = False
    breakout_direction: Optional[str] = None  # 'bullish', 'bearish', None
    breakout_price: Optional[float] = None
    breakout_time: Optional[datetime] = None
    traded: bool = False


class SessionORBDetector:
    """
    Detects Opening Range Breakouts for configurable trading sessions.
    
    Based on MQL5 handbook article: "Session-Based Opening Range Breakout (ORB) System"
    """
    
    # Default session configurations (UTC times)
    DEFAULT_SESSIONS = {
        SessionType.LONDON: SessionConfig("London", 8, 0, 30),
        SessionType.NEW_YORK: SessionConfig("New York", 13, 30, 30),
        SessionType.ASIAN: SessionConfig("Asian", 0, 0, 30),
    }
    
    def __init__(
        self,
        sessions: list = None,
        range_duration_minutes: int = 30,
        confirm_bars: int = 1,
        use_breakout_filter: bool = True,
        min_range_size_atr: float = 0.5,  # Minimum range size as ATR multiplier
        max_range_size_atr: float = 3.0,  # Maximum range size as ATR multiplier
    ):
        """
        Initialize Session ORB Detector.
        
        Args:
            sessions: List of SessionType or SessionConfig objects
            range_duration_minutes: Duration of opening range in minutes
            confirm_bars: Bars required to confirm breakout (0 = instant)
            use_breakout_filter: Apply additional breakout filtering
            min_range_size_atr: Minimum range size relative to ATR
            max_range_size_atr: Maximum range size relative to ATR
        """
        self.range_duration_minutes = range_duration_minutes
        self.confirm_bars = confirm_bars
        self.use_breakout_filter = use_breakout_filter
        self.min_range_size_atr = min_range_size_atr
        self.max_range_size_atr = max_range_size_atr
        
        # Configure sessions
        self.sessions: Dict[str, SessionConfig] = {}
        if sessions is None:
            sessions = [SessionType.LONDON, SessionType.NEW_YORK]
        
        for session in sessions:
            if isinstance(session, SessionType):
                config = self.DEFAULT_SESSIONS.get(session)
                if config:
                    self.sessions[session.value] = config
            elif isinstance(session, SessionConfig):
                self.sessions[session.name.lower()] = session
        
        # State tracking
        self.current_ranges: Dict[str, OpeningRange] = {}
        self.completed_ranges: list = []
        
        logger.info(f"SessionORBDetector initialized with sessions: {list(self.sessions.keys())}")
    
    def _get_session_for_time(self, dt: datetime) -> Optional[Tuple[str, SessionConfig]]:
        """Check if given datetime falls within any session start window."""
        current_time = dt.time()
        
        for name, config in self.sessions.items():
            session_start = config.start_time
            # Check if we're at session start (within first minute)
            if (current_time.hour == session_start.hour and 
                current_time.minute == session_start.minute):
                return name, config
        
        return None
    
    def _is_in_range_period(self, dt: datetime, range_obj: OpeningRange) -> bool:
        """Check if datetime is within the opening range period."""
        return range_obj.range_start <= dt < range_obj.range_end
    
    def update(
        self,
        df: pd.DataFrame,
        current_price: float,
        atr: float,
        timestamp: datetime = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update ORB detection with new data.
        
        Args:
            df: OHLCV DataFrame with recent bars
            current_price: Current market price
            atr: Current ATR value for filtering
            timestamp: Current timestamp (uses latest bar if None)
        
        Returns:
            Signal dict if breakout detected, None otherwise
        """
        if df is None or len(df) < 10:
            return None
        
        if timestamp is None:
            timestamp = df.index[-1] if hasattr(df.index[-1], 'hour') else datetime.now()
        
        # Check for new session start
        session_info = self._get_session_for_time(timestamp)
        if session_info:
            session_name, config = session_info
            self._start_new_range(session_name, config, timestamp, df)
        
        # Update existing ranges
        for session_name, range_obj in list(self.current_ranges.items()):
            if not range_obj.is_complete:
                # Still building range - update high/low
                if self._is_in_range_period(timestamp, range_obj):
                    self._update_range_levels(range_obj, df, timestamp)
                else:
                    # Range period ended - finalize
                    range_obj.is_complete = True
                    logger.info(
                        f"ORB Range complete for {session_name}: "
                        f"High={range_obj.high:.5f}, Low={range_obj.low:.5f}, "
                        f"Size={range_obj.high - range_obj.low:.5f}"
                    )
            
            # Check for breakout on completed ranges
            if range_obj.is_complete and not range_obj.traded:
                signal = self._check_breakout(range_obj, df, current_price, atr, timestamp)
                if signal:
                    return signal
        
        return None
    
    def _start_new_range(
        self,
        session_name: str,
        config: SessionConfig,
        timestamp: datetime,
        df: pd.DataFrame
    ):
        """Start tracking a new opening range."""
        # Check if we already have a range for today's session
        today = timestamp.date()
        existing = self.current_ranges.get(session_name)
        if existing and existing.date.date() == today:
            return  # Already tracking today's range
        
        # Create new range
        range_end = timestamp + timedelta(minutes=config.range_duration_minutes)
        
        # Initialize with current bar's high/low
        current_high = df['high'].iloc[-1]
        current_low = df['low'].iloc[-1]
        
        new_range = OpeningRange(
            session=session_name,
            date=timestamp,
            range_start=timestamp,
            range_end=range_end,
            high=current_high,
            low=current_low,
            is_complete=False
        )
        
        self.current_ranges[session_name] = new_range
        logger.info(f"Started new ORB range for {session_name} at {timestamp}")
    
    def _update_range_levels(
        self,
        range_obj: OpeningRange,
        df: pd.DataFrame,
        timestamp: datetime
    ):
        """Update the high/low of an in-progress opening range."""
        # Get bars within the range period
        if hasattr(df.index, 'to_pydatetime'):
            mask = (df.index >= range_obj.range_start) & (df.index < range_obj.range_end)
            range_data = df[mask]
        else:
            range_data = df.tail(10)  # Fallback: use recent bars
        
        if len(range_data) > 0:
            range_obj.high = max(range_obj.high, range_data['high'].max())
            range_obj.low = min(range_obj.low, range_data['low'].min())
    
    def _check_breakout(
        self,
        range_obj: OpeningRange,
        df: pd.DataFrame,
        current_price: float,
        atr: float,
        timestamp: datetime
    ) -> Optional[Dict[str, Any]]:
        """Check for breakout from completed opening range."""
        range_size = range_obj.high - range_obj.low
        
        # Filter: Range size validation
        if atr > 0:
            if range_size < self.min_range_size_atr * atr:
                return None  # Range too small
            if range_size > self.max_range_size_atr * atr:
                return None  # Range too large (likely news spike)
        
        # Get recent closes for confirmation
        if len(df) < self.confirm_bars + 1:
            return None
        
        recent_closes = df['close'].iloc[-(self.confirm_bars + 1):].values
        prev_close = recent_closes[-2] if len(recent_closes) > 1 else recent_closes[-1]
        curr_close = recent_closes[-1]
        
        signal = None
        
        # Check bullish breakout
        if curr_close > range_obj.high and not range_obj.breakout_direction:
            # Confirm with bar closes if required
            if self.confirm_bars == 0 or self._confirm_breakout(df, range_obj.high, 'bullish'):
                range_obj.breakout_direction = 'bullish'
                range_obj.breakout_price = current_price
                range_obj.breakout_time = timestamp
                range_obj.traded = True
                
                signal = {
                    'direction': 'long',
                    'entry_price': current_price,
                    'stop_loss': range_obj.low,  # SL at range low
                    'take_profit': current_price + (range_size * 2),  # 2:1 RR
                    'confidence': 0.85,
                    'reason': f'ORB Bullish Breakout ({range_obj.session})',
                    'range_high': range_obj.high,
                    'range_low': range_obj.low,
                    'range_size': range_size,
                    'session': range_obj.session
                }
                
                logger.info(
                    f"🟢 ORB BULLISH BREAKOUT ({range_obj.session}): "
                    f"Price {current_price:.5f} broke above {range_obj.high:.5f}"
                )
        
        # Check bearish breakout
        elif curr_close < range_obj.low and not range_obj.breakout_direction:
            # Confirm with bar closes if required
            if self.confirm_bars == 0 or self._confirm_breakout(df, range_obj.low, 'bearish'):
                range_obj.breakout_direction = 'bearish'
                range_obj.breakout_price = current_price
                range_obj.breakout_time = timestamp
                range_obj.traded = True
                
                signal = {
                    'direction': 'short',
                    'entry_price': current_price,
                    'stop_loss': range_obj.high,  # SL at range high
                    'take_profit': current_price - (range_size * 2),  # 2:1 RR
                    'confidence': 0.85,
                    'reason': f'ORB Bearish Breakout ({range_obj.session})',
                    'range_high': range_obj.high,
                    'range_low': range_obj.low,
                    'range_size': range_size,
                    'session': range_obj.session
                }
                
                logger.info(
                    f"🔴 ORB BEARISH BREAKOUT ({range_obj.session}): "
                    f"Price {current_price:.5f} broke below {range_obj.low:.5f}"
                )
        
        return signal
    
    def _confirm_breakout(
        self,
        df: pd.DataFrame,
        level: float,
        direction: str
    ) -> bool:
        """Confirm breakout with multiple bar closes."""
        if self.confirm_bars == 0:
            return True
        
        recent_closes = df['close'].iloc[-self.confirm_bars:].values
        
        if direction == 'bullish':
            # All closes must be above level
            return all(close > level for close in recent_closes)
        else:
            # All closes must be below level
            return all(close < level for close in recent_closes)
    
    def get_active_ranges(self) -> Dict[str, OpeningRange]:
        """Get all currently tracked opening ranges."""
        return self.current_ranges.copy()
    
    def get_range_levels(self, session: str = None) -> Optional[Dict[str, float]]:
        """Get high/low levels for a specific session or all sessions."""
        if session:
            range_obj = self.current_ranges.get(session)
            if range_obj and range_obj.is_complete:
                return {
                    'high': range_obj.high,
                    'low': range_obj.low,
                    'size': range_obj.high - range_obj.low
                }
            return None
        
        # Return all completed ranges
        result = {}
        for name, range_obj in self.current_ranges.items():
            if range_obj.is_complete:
                result[name] = {
                    'high': range_obj.high,
                    'low': range_obj.low,
                    'size': range_obj.high - range_obj.low
                }
        return result if result else None
    
    def cleanup_old_ranges(self, max_age_hours: int = 24):
        """Remove ranges older than specified age."""
        now = datetime.now()
        for session_name in list(self.current_ranges.keys()):
            range_obj = self.current_ranges[session_name]
            age = now - range_obj.date
            if age.total_seconds() > max_age_hours * 3600:
                self.completed_ranges.append(range_obj)
                del self.current_ranges[session_name]
