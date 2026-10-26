"""
Market Structure Detection - BOS/ChoCH Implementation

Based on MQL5 Handbook: "Automating BOS and CHoCH Detection in MQL5"
(Price Action Analysis Toolkit Development Part 39)

This module implements:
- Fractal pivot detection for reliable local anchors
- Break of Structure (BOS): Decisive violation of prior swing high/low
- Change of Character (ChoCH): Early warning that market bias is changing

BOS = Confirmation of trend shift (momentum committed)
ChoCH = Warning signal (trend weakening, prepare for reversal)

Key principles:
1. All signals evaluated on CLOSED bars only (no repainting)
2. Fractals provide non-repainting anchor points
3. ChoCH precedes BOS - use as early warning
4. Multi-timeframe analysis for noise filtering
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone
from enum import Enum
import logging
import pandas as pd
import numpy as np

logger = logging.getLogger('cthulu.market_structure')


class StructureType(Enum):
    """Market structure event types"""
    BOS_BULLISH = "Bull BOS"      # Break of Structure upward (confirmed bullish shift)
    BOS_BEARISH = "Bear BOS"      # Break of Structure downward (confirmed bearish shift)
    CHOCH_BULLISH = "Bull ChoCH"  # Change of Character bullish (bearish trend weakening)
    CHOCH_BEARISH = "Bear ChoCH"  # Change of Character bearish (bullish trend weakening)


class MarketBias(Enum):
    """Current market bias/state"""
    NEUTRAL = 0
    BULLISH = 1
    BEARISH = -1


@dataclass
class Fractal:
    """Represents a fractal pivot point"""
    timestamp: datetime
    price: float
    is_high: bool  # True = high fractal, False = low fractal
    bar_index: int
    marked: bool = False  # Has this fractal been processed for BOS/ChoCH?


@dataclass
class StructureEvent:
    """Market structure event (BOS or ChoCH)"""
    event_type: StructureType
    timestamp: datetime
    price: float
    fractal_price: float
    fractal_time: datetime
    bar_index: int
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MarketStructureConfig:
    """Configuration for market structure detection"""
    # Fractal detection
    fractal_length: int = 5  # Must be odd (2*p + 1), p = neighbors on each side
    auto_detect_length: bool = True  # Adjust based on timeframe
    
    # History management
    max_fractal_history: int = 100  # Keep last N fractals
    min_bars_for_detection: int = 10  # Minimum bars needed
    
    # Signal sensitivity
    require_close_confirmation: bool = True  # Only signal on closed bars
    min_break_distance_atr_mult: float = 0.0  # Minimum distance for break (ATR multiple)
    
    # Multi-timeframe
    higher_tf_confirmation: bool = False  # Require HTF alignment


class MarketStructureDetector:
    """
    Detects market structure shifts (BOS/ChoCH) using fractal pivots.
    
    This is the "smart entry filter" - signals should only be acted on
    when they align with BOS/ChoCH confirmation.
    """
    
    def __init__(self, config: Optional[MarketStructureConfig] = None):
        self.config = config or MarketStructureConfig()
        
        # Storage for fractals
        self._high_fractals: List[Fractal] = []
        self._low_fractals: List[Fractal] = []
        
        # Current market bias
        self._current_bias: MarketBias = MarketBias.NEUTRAL
        
        # Recent structure events
        self._events: List[StructureEvent] = []
        
        # Cached calculations
        self._last_bar_time: Optional[datetime] = None
        self._p_half: int = self.config.fractal_length // 2
        
    def _get_adaptive_length(self, timeframe: str) -> int:
        """Auto-detect fractal length based on timeframe"""
        tf_upper = timeframe.upper() if timeframe else "M15"
        
        if tf_upper in ['M1', 'M5', 'M15', 'M30']:
            return 5
        elif tf_upper in ['H1']:
            return 5
        elif tf_upper in ['H4']:
            return 7
        elif tf_upper in ['D1']:
            return 9
        else:
            return 11
    
    def _is_fractal_high(self, data: pd.DataFrame, idx: int) -> bool:
        """
        Check if bar at idx is a high fractal (local high).
        
        A high fractal occurs when the center bar's high is >= all neighboring highs.
        """
        p = self._p_half
        
        # Bounds check
        if idx < p or idx >= len(data) - p:
            return False
        
        center_high = data['high'].iloc[idx]
        
        # Check all neighbors
        for k in range(-p, p + 1):
            if k == 0:
                continue
            neighbor_idx = idx + k
            if neighbor_idx < 0 or neighbor_idx >= len(data):
                return False
            if data['high'].iloc[neighbor_idx] > center_high:
                return False
        
        return True
    
    def _is_fractal_low(self, data: pd.DataFrame, idx: int) -> bool:
        """
        Check if bar at idx is a low fractal (local low).
        
        A low fractal occurs when the center bar's low is <= all neighboring lows.
        """
        p = self._p_half
        
        # Bounds check
        if idx < p or idx >= len(data) - p:
            return False
        
        center_low = data['low'].iloc[idx]
        
        # Check all neighbors
        for k in range(-p, p + 1):
            if k == 0:
                continue
            neighbor_idx = idx + k
            if neighbor_idx < 0 or neighbor_idx >= len(data):
                return False
            if data['low'].iloc[neighbor_idx] < center_low:
                return False
        
        return True
    
    def _scan_for_fractals(self, data: pd.DataFrame, timeframe: str = "M15") -> None:
        """
        Scan for new fractal pivots in the data.
        
        Only evaluates the center bar of the fractal window (shift = p_half from end).
        """
        if len(data) <= self.config.fractal_length:
            return
        
        # Auto-adjust fractal length based on timeframe
        if self.config.auto_detect_length:
            new_length = self._get_adaptive_length(timeframe)
            if new_length != self.config.fractal_length:
                self.config.fractal_length = new_length
                self._p_half = new_length // 2
        
        # Ensure odd length
        if self.config.fractal_length % 2 == 0:
            self.config.fractal_length += 1
            self._p_half = self.config.fractal_length // 2
        
        # Check the most recent confirmed bar (shift = p_half from end)
        # This is the center of our fractal window
        center_idx = len(data) - 1 - self._p_half
        
        if center_idx < self._p_half:
            return
        
        bar_time = data['time'].iloc[center_idx] if 'time' in data.columns else datetime.now(timezone.utc)
        
        # Check for high fractal
        if self._is_fractal_high(data, center_idx):
            fractal_price = data['high'].iloc[center_idx]
            
            # Check if already recorded
            exists = any(f.timestamp == bar_time and f.is_high for f in self._high_fractals)
            
            if not exists:
                fractal = Fractal(
                    timestamp=bar_time,
                    price=fractal_price,
                    is_high=True,
                    bar_index=center_idx
                )
                self._high_fractals.append(fractal)
                logger.debug(f"High fractal detected at {bar_time}: {fractal_price}")
        
        # Check for low fractal
        if self._is_fractal_low(data, center_idx):
            fractal_price = data['low'].iloc[center_idx]
            
            # Check if already recorded
            exists = any(f.timestamp == bar_time and not f.is_high for f in self._low_fractals)
            
            if not exists:
                fractal = Fractal(
                    timestamp=bar_time,
                    price=fractal_price,
                    is_high=False,
                    bar_index=center_idx
                )
                self._low_fractals.append(fractal)
                logger.debug(f"Low fractal detected at {bar_time}: {fractal_price}")
        
        # Prune old fractals
        self._prune_fractals()
    
    def _prune_fractals(self) -> None:
        """Remove old fractals to prevent memory growth"""
        max_keep = self.config.max_fractal_history
        
        if len(self._high_fractals) > max_keep:
            self._high_fractals = self._high_fractals[-max_keep:]
        
        if len(self._low_fractals) > max_keep:
            self._low_fractals = self._low_fractals[-max_keep:]
    
    def _crossed_over(self, prev_close: float, cur_close: float, level: float) -> bool:
        """Check if price crossed over a level (bullish break)"""
        return prev_close <= level and cur_close > level
    
    def _crossed_under(self, prev_close: float, cur_close: float, level: float) -> bool:
        """Check if price crossed under a level (bearish break)"""
        return prev_close >= level and cur_close < level
    
    def _process_fractal_crosses(self, data: pd.DataFrame) -> List[StructureEvent]:
        """
        Check if recent closes crossed any fractal levels.
        
        Returns new structure events (BOS/ChoCH).
        """
        if len(data) < 3:
            return []
        
        events = []
        
        # Get the two most recent CLOSED bars
        prev_close = data['close'].iloc[-2]  # Previous completed bar
        cur_close = data['close'].iloc[-1]   # Most recent completed bar
        cur_time = data['time'].iloc[-1] if 'time' in data.columns else datetime.now(timezone.utc)
        cur_idx = len(data) - 1
        
        # Process high fractals (bullish breaks)
        for fractal in self._high_fractals:
            if fractal.marked:
                continue
            
            if self._crossed_over(prev_close, cur_close, fractal.price):
                # Bullish break of high fractal
                # If we were bearish, this is a ChoCH (change of character)
                # If we were neutral or bullish, this is a BOS (break of structure)
                is_choch = self._current_bias == MarketBias.BEARISH
                
                event = StructureEvent(
                    event_type=StructureType.CHOCH_BULLISH if is_choch else StructureType.BOS_BULLISH,
                    timestamp=cur_time,
                    price=cur_close,
                    fractal_price=fractal.price,
                    fractal_time=fractal.timestamp,
                    bar_index=cur_idx,
                    confidence=0.9 if is_choch else 1.0,
                    metadata={'prev_bias': self._current_bias.name}
                )
                events.append(event)
                
                # Update state
                fractal.marked = True
                self._current_bias = MarketBias.BULLISH
                
                logger.info(f"{event.event_type.value} detected at {cur_time}: "
                           f"price {cur_close} broke fractal {fractal.price}")
        
        # Process low fractals (bearish breaks)
        for fractal in self._low_fractals:
            if fractal.marked:
                continue
            
            if self._crossed_under(prev_close, cur_close, fractal.price):
                # Bearish break of low fractal
                is_choch = self._current_bias == MarketBias.BULLISH
                
                event = StructureEvent(
                    event_type=StructureType.CHOCH_BEARISH if is_choch else StructureType.BOS_BEARISH,
                    timestamp=cur_time,
                    price=cur_close,
                    fractal_price=fractal.price,
                    fractal_time=fractal.timestamp,
                    bar_index=cur_idx,
                    confidence=0.9 if is_choch else 1.0,
                    metadata={'prev_bias': self._current_bias.name}
                )
                events.append(event)
                
                # Update state
                fractal.marked = True
                self._current_bias = MarketBias.BEARISH
                
                logger.info(f"{event.event_type.value} detected at {cur_time}: "
                           f"price {cur_close} broke fractal {fractal.price}")
        
        # Store events
        self._events.extend(events)
        
        # Keep event history bounded
        if len(self._events) > 100:
            self._events = self._events[-50:]
        
        return events
    
    def update(self, data: pd.DataFrame, timeframe: str = "M15") -> List[StructureEvent]:
        """
        Update market structure analysis with new data.
        
        This should be called on each new bar (or tick, but action only on new bar).
        
        Args:
            data: DataFrame with OHLC data (columns: open, high, low, close, time)
            timeframe: Timeframe string for adaptive length
            
        Returns:
            List of new structure events detected
        """
        if len(data) < self.config.min_bars_for_detection:
            return []
        
        # Ensure required columns (lowercase)
        required = ['open', 'high', 'low', 'close']
        df = data.copy()
        
        # Normalize column names
        df.columns = df.columns.str.lower()
        
        if not all(c in df.columns for c in required):
            logger.warning(f"Missing required columns. Have: {list(df.columns)}")
            return []
        
        # Add time column if missing
        if 'time' not in df.columns:
            df['time'] = pd.date_range(end=datetime.now(timezone.utc), periods=len(df), freq='15min')
        
        # Check if we have a new bar
        cur_bar_time = df['time'].iloc[-1]
        if self._last_bar_time is not None and cur_bar_time <= self._last_bar_time:
            return []  # Same bar, skip
        
        self._last_bar_time = cur_bar_time
        
        # Step 1: Scan for new fractals
        self._scan_for_fractals(df, timeframe)
        
        # Step 2: Process fractal crosses for BOS/ChoCH
        events = self._process_fractal_crosses(df)
        
        return events
    
    def get_current_bias(self) -> MarketBias:
        """Get current market bias"""
        return self._current_bias
    
    def get_recent_events(self, limit: int = 10) -> List[StructureEvent]:
        """Get recent structure events"""
        return self._events[-limit:]
    
    def get_last_bos(self) -> Optional[StructureEvent]:
        """Get the most recent BOS event"""
        for event in reversed(self._events):
            if event.event_type in [StructureType.BOS_BULLISH, StructureType.BOS_BEARISH]:
                return event
        return None
    
    def get_last_choch(self) -> Optional[StructureEvent]:
        """Get the most recent ChoCH event"""
        for event in reversed(self._events):
            if event.event_type in [StructureType.CHOCH_BULLISH, StructureType.CHOCH_BEARISH]:
                return event
        return None
    
    def is_aligned_with_signal(self, signal_direction: str) -> Tuple[bool, float, str]:
        """
        Check if a trading signal aligns with current market structure.
        
        Args:
            signal_direction: 'BUY' or 'SELL'
            
        Returns:
            Tuple of (aligned, confidence_multiplier, reason)
        """
        direction = signal_direction.upper()
        
        # Get recent events (last 5)
        recent = self.get_recent_events(5)
        
        if not recent:
            # No structure data yet - allow with reduced confidence
            return True, 0.7, "No structure data available"
        
        last_event = recent[-1]
        
        if direction == 'BUY':
            # BUY should align with bullish BOS or ChoCH
            if last_event.event_type == StructureType.BOS_BULLISH:
                return True, 1.0, f"Aligned with Bull BOS at {last_event.price}"
            elif last_event.event_type == StructureType.CHOCH_BULLISH:
                return True, 0.85, f"Aligned with Bull ChoCH at {last_event.price}"
            elif last_event.event_type in [StructureType.BOS_BEARISH, StructureType.CHOCH_BEARISH]:
                # Counter-trend - high risk
                return False, 0.3, f"Counter to {last_event.event_type.value}"
        
        elif direction == 'SELL':
            # SELL should align with bearish BOS or ChoCH
            if last_event.event_type == StructureType.BOS_BEARISH:
                return True, 1.0, f"Aligned with Bear BOS at {last_event.price}"
            elif last_event.event_type == StructureType.CHOCH_BEARISH:
                return True, 0.85, f"Aligned with Bear ChoCH at {last_event.price}"
            elif last_event.event_type in [StructureType.BOS_BULLISH, StructureType.CHOCH_BULLISH]:
                return False, 0.3, f"Counter to {last_event.event_type.value}"
        
        return True, 0.6, "Direction unclear"
    
    def get_structure_score(self, data: pd.DataFrame, direction: str) -> int:
        """
        Get a structure score (0-100) for entry confluence.
        
        Considers:
        - Alignment with recent BOS/ChoCH
        - Proximity to key fractal levels
        - Overall bias alignment
        """
        score = 50  # Neutral base
        
        direction_upper = direction.upper()
        
        # Bias alignment (+/- 20)
        if direction_upper == 'BUY' and self._current_bias == MarketBias.BULLISH:
            score += 20
        elif direction_upper == 'SELL' and self._current_bias == MarketBias.BEARISH:
            score += 20
        elif self._current_bias != MarketBias.NEUTRAL:
            score -= 15
        
        # Recent BOS/ChoCH alignment (+/- 20)
        aligned, mult, _ = self.is_aligned_with_signal(direction_upper)
        if aligned:
            score += int(20 * mult)
        else:
            score -= 20
        
        # Recent ChoCH gives extra points (early warning confirmation)
        last_choch = self.get_last_choch()
        if last_choch:
            if (direction_upper == 'BUY' and last_choch.event_type == StructureType.CHOCH_BULLISH) or \
               (direction_upper == 'SELL' and last_choch.event_type == StructureType.CHOCH_BEARISH):
                score += 10
        
        return max(0, min(100, score))
    
    def reset(self) -> None:
        """Reset all state"""
        self._high_fractals.clear()
        self._low_fractals.clear()
        self._current_bias = MarketBias.NEUTRAL
        self._events.clear()
        self._last_bar_time = None


# Factory function
def create_structure_detector(config_dict: Optional[Dict[str, Any]] = None) -> MarketStructureDetector:
    """Create a MarketStructureDetector with optional config"""
    config = MarketStructureConfig()
    
    if config_dict:
        for key, value in config_dict.items():
            if hasattr(config, key):
                setattr(config, key, value)
    
    return MarketStructureDetector(config)


# Integration helper for entry confluence
def get_structure_confluence_score(detector: MarketStructureDetector, 
                                    data: pd.DataFrame, 
                                    direction: str) -> Dict[str, Any]:
    """
    Get comprehensive structure analysis for entry confluence.
    
    Returns a dict with:
    - score: 0-100 structure score
    - aligned: bool
    - bias: current market bias
    - events: recent structure events
    - recommendation: STRONG_ENTRY, ENTRY, WAIT, or AVOID
    """
    # Update detector with latest data
    new_events = detector.update(data)
    
    # Get alignment
    aligned, confidence, reason = detector.is_aligned_with_signal(direction)
    
    # Get score
    score = detector.get_structure_score(data, direction)
    
    # Determine recommendation
    if score >= 80 and aligned:
        recommendation = "STRONG_ENTRY"
    elif score >= 60 and aligned:
        recommendation = "ENTRY"
    elif score >= 40:
        recommendation = "WAIT"
    else:
        recommendation = "AVOID"
    
    return {
        'score': score,
        'aligned': aligned,
        'confidence_multiplier': confidence,
        'reason': reason,
        'bias': detector.get_current_bias().name,
        'recent_events': [
            {
                'type': e.event_type.value,
                'time': e.timestamp.isoformat() if isinstance(e.timestamp, datetime) else str(e.timestamp),
                'price': e.price
            }
            for e in detector.get_recent_events(3)
        ],
        'new_events': [
            {
                'type': e.event_type.value,
                'time': e.timestamp.isoformat() if isinstance(e.timestamp, datetime) else str(e.timestamp),
                'price': e.price
            }
            for e in new_events
        ],
        'recommendation': recommendation
    }
