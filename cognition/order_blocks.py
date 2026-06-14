"""
Order Block Detection System.

Based on ICT (Inner Circle Trader) methodology and MQL5 handbook 
implementations for detecting institutional order blocks.

Order Block Types:
- Bullish Order Block: Last bearish candle before a strong bullish move
- Bearish Order Block: Last bullish candle before a strong bearish move

Detection Logic:
1. Identify swing highs/lows using fractal-based detection
2. Find the last opposing candle before a Break of Structure (BOS)
3. Mark the candle's body (open-close) as the order block zone
4. Valid until price returns to the zone (mitigation)

ICT Concepts Used:
- Break of Structure (BOS): Price closes beyond prior swing high/low
- Change of Character (ChoCH): Failure to make higher high or lower low
- Order Block: Institutional supply/demand zone
- Fair Value Gap (FVG): Imbalance between candles
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class OrderBlockType(Enum):
    """Type of order block."""
    BULLISH = "bullish"  # Demand zone - expect bounce up
    BEARISH = "bearish"  # Supply zone - expect rejection down


class StructureBreak(Enum):
    """Type of structure break."""
    BOS = "bos"      # Break of Structure - continuation
    CHOCH = "choch"  # Change of Character - potential reversal


@dataclass
class SwingPoint:
    """Represents a swing high or swing low."""
    index: int
    price: float
    timestamp: datetime
    is_high: bool  # True for swing high, False for swing low
    strength: int = 1  # Number of bars confirming the swing


@dataclass
class OrderBlock:
    """Represents a detected order block."""
    block_type: OrderBlockType
    timestamp: datetime
    index: int
    high: float  # Top of order block zone
    low: float   # Bottom of order block zone
    body_high: float  # Candle body high
    body_low: float   # Candle body low
    volume: float = 0.0
    structure_break: StructureBreak = StructureBreak.BOS
    is_valid: bool = True
    is_mitigated: bool = False
    mitigation_price: Optional[float] = None
    mitigation_time: Optional[datetime] = None
    touches: int = 0  # Number of times price touched this zone
    
    @property
    def zone_size(self) -> float:
        """Size of the order block zone."""
        return self.high - self.low
    
    @property
    def midpoint(self) -> float:
        """Midpoint of the order block."""
        return (self.high + self.low) / 2


class OrderBlockDetector:
    """
    Detects Order Blocks based on ICT methodology.
    
    Uses fractal-based swing detection and structure break analysis
    to identify high-probability institutional order flow zones.
    """
    
    def __init__(
        self,
        swing_lookback: int = 5,  # Bars on each side for swing detection
        min_move_atr: float = 1.5,  # Minimum move size as ATR multiplier
        max_age_bars: int = 100,  # Maximum age before OB considered stale
        use_body_only: bool = True,  # Use candle body vs full wick
        require_strong_move: bool = True,  # Require impulsive move after OB
    ):
        """
        Initialize Order Block Detector.
        
        Args:
            swing_lookback: Bars on each side for fractal/swing detection
            min_move_atr: Minimum structure break move size (ATR multiplier)
            max_age_bars: Max bars before order block considered stale
            use_body_only: Use candle body for zone (True) or full range (False)
            require_strong_move: Require strong impulsive move to validate OB
        """
        self.swing_lookback = swing_lookback
        self.min_move_atr = min_move_atr
        self.max_age_bars = max_age_bars
        self.use_body_only = use_body_only
        self.require_strong_move = require_strong_move
        
        # State tracking
        self.swing_highs: List[SwingPoint] = []
        self.swing_lows: List[SwingPoint] = []
        self.order_blocks: List[OrderBlock] = []
        self.last_processed_index: int = -1
        
        # Market structure state
        self.current_trend: Optional[str] = None  # 'bullish', 'bearish', None
        self.last_bos_direction: Optional[str] = None
        
        logger.info(f"OrderBlockDetector initialized (lookback={swing_lookback})")
    
    def _detect_swing_points(self, df: pd.DataFrame) -> Tuple[List[SwingPoint], List[SwingPoint]]:
        """
        Detect swing highs and lows using fractal logic.
        
        A swing high requires the center bar's high to be higher than
        swing_lookback bars on each side. Vice versa for swing low.
        """
        highs = []
        lows = []
        
        if len(df) < 2 * self.swing_lookback + 1:
            return highs, lows
        
        high_arr = df['high'].values
        low_arr = df['low'].values
        
        for i in range(self.swing_lookback, len(df) - self.swing_lookback):
            center_high = high_arr[i]
            center_low = low_arr[i]
            
            # Check for swing high
            is_swing_high = True
            for j in range(i - self.swing_lookback, i + self.swing_lookback + 1):
                if j != i and high_arr[j] >= center_high:
                    is_swing_high = False
                    break
            
            if is_swing_high:
                timestamp = df.index[i] if hasattr(df.index[i], 'hour') else datetime.now()
                highs.append(SwingPoint(
                    index=i,
                    price=center_high,
                    timestamp=timestamp,
                    is_high=True,
                    strength=self.swing_lookback
                ))
            
            # Check for swing low
            is_swing_low = True
            for j in range(i - self.swing_lookback, i + self.swing_lookback + 1):
                if j != i and low_arr[j] <= center_low:
                    is_swing_low = False
                    break
            
            if is_swing_low:
                timestamp = df.index[i] if hasattr(df.index[i], 'hour') else datetime.now()
                lows.append(SwingPoint(
                    index=i,
                    price=center_low,
                    timestamp=timestamp,
                    is_high=False,
                    strength=self.swing_lookback
                ))
        
        return highs, lows
    
    def _detect_structure_break(
        self,
        df: pd.DataFrame,
        swing_highs: List[SwingPoint],
        swing_lows: List[SwingPoint],
        atr: float
    ) -> Optional[Tuple[StructureBreak, str, int, float]]:
        """
        Detect Break of Structure (BOS) or Change of Character (ChoCH).
        
        Returns:
            Tuple of (break_type, direction, bar_index, level) or None
        """
        if len(df) < 3 or not swing_highs or not swing_lows:
            return None
        
        current_close = df['close'].iloc[-1]
        prev_close = df['close'].iloc[-2]
        current_index = len(df) - 1
        
        # Get most recent swing points
        recent_high = swing_highs[-1] if swing_highs else None
        recent_low = swing_lows[-1] if swing_lows else None
        
        min_move = self.min_move_atr * atr if atr > 0 else 0
        
        # Check for bullish BOS (close above recent swing high)
        if recent_high and current_close > recent_high.price:
            move_size = current_close - recent_high.price
            if move_size >= min_move:
                # Determine if BOS or ChoCH based on prior trend
                if self.current_trend == 'bearish':
                    return (StructureBreak.CHOCH, 'bullish', current_index, recent_high.price)
                else:
                    return (StructureBreak.BOS, 'bullish', current_index, recent_high.price)
        
        # Check for bearish BOS (close below recent swing low)
        if recent_low and current_close < recent_low.price:
            move_size = recent_low.price - current_close
            if move_size >= min_move:
                if self.current_trend == 'bullish':
                    return (StructureBreak.CHOCH, 'bearish', current_index, recent_low.price)
                else:
                    return (StructureBreak.BOS, 'bearish', current_index, recent_low.price)
        
        return None
    
    def _find_order_block_candle(
        self,
        df: pd.DataFrame,
        break_index: int,
        direction: str,
        lookback: int = 10
    ) -> Optional[int]:
        """
        Find the order block candle - last opposing candle before the move.
        
        For bullish OB: Last bearish candle before bullish structure break
        For bearish OB: Last bullish candle before bearish structure break
        """
        start_idx = max(0, break_index - lookback)
        
        if direction == 'bullish':
            # Find last bearish candle
            for i in range(break_index - 1, start_idx - 1, -1):
                if df['close'].iloc[i] < df['open'].iloc[i]:  # Bearish candle
                    return i
        else:
            # Find last bullish candle
            for i in range(break_index - 1, start_idx - 1, -1):
                if df['close'].iloc[i] > df['open'].iloc[i]:  # Bullish candle
                    return i
        
        return None
    
    def _create_order_block(
        self,
        df: pd.DataFrame,
        ob_index: int,
        direction: str,
        structure_break: StructureBreak
    ) -> OrderBlock:
        """Create an OrderBlock object from the detected candle."""
        candle = df.iloc[ob_index]
        timestamp = df.index[ob_index] if hasattr(df.index[ob_index], 'hour') else datetime.now()
        
        open_price = candle['open']
        close_price = candle['close']
        high_price = candle['high']
        low_price = candle['low']
        volume = candle.get('volume', 0)
        
        # Determine zone boundaries
        if self.use_body_only:
            zone_high = max(open_price, close_price)
            zone_low = min(open_price, close_price)
        else:
            zone_high = high_price
            zone_low = low_price
        
        block_type = OrderBlockType.BULLISH if direction == 'bullish' else OrderBlockType.BEARISH
        
        return OrderBlock(
            block_type=block_type,
            timestamp=timestamp,
            index=ob_index,
            high=zone_high,
            low=zone_low,
            body_high=max(open_price, close_price),
            body_low=min(open_price, close_price),
            volume=volume,
            structure_break=structure_break,
            is_valid=True,
            is_mitigated=False
        )
    
    def _check_mitigation(self, df: pd.DataFrame, current_price: float):
        """Check if any order blocks have been mitigated (filled)."""
        current_time = datetime.now()
        
        for ob in self.order_blocks:
            if not ob.is_valid or ob.is_mitigated:
                continue
            
            # Check if price has entered the order block zone
            if ob.low <= current_price <= ob.high:
                ob.touches += 1
                
                # Mitigation: price has filled through the zone
                if ob.block_type == OrderBlockType.BULLISH:
                    # Bullish OB mitigated when price goes through and closes below
                    if current_price < ob.low:
                        ob.is_mitigated = True
                        ob.mitigation_price = current_price
                        ob.mitigation_time = current_time
                        logger.info(f"Bullish OB mitigated at {current_price:.5f}")
                else:
                    # Bearish OB mitigated when price goes through and closes above
                    if current_price > ob.high:
                        ob.is_mitigated = True
                        ob.mitigation_price = current_price
                        ob.mitigation_time = current_time
                        logger.info(f"Bearish OB mitigated at {current_price:.5f}")
    
    def _cleanup_old_blocks(self, current_index: int):
        """Remove stale order blocks."""
        self.order_blocks = [
            ob for ob in self.order_blocks
            if ob.is_valid and not ob.is_mitigated and 
            (current_index - ob.index) < self.max_age_bars
        ]
    
    def update(
        self,
        df: pd.DataFrame,
        current_price: float,
        atr: float,
        timestamp: datetime = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update order block detection with new data.
        
        Args:
            df: OHLCV DataFrame
            current_price: Current market price
            atr: Current ATR value
            timestamp: Current timestamp
        
        Returns:
            Signal dict if price at valid order block, None otherwise
        """
        if df is None or len(df) < 2 * self.swing_lookback + 5:
            return None
        
        current_index = len(df) - 1
        
        # Only process new bars
        if current_index <= self.last_processed_index:
            # Just check for signals at existing OBs
            return self._check_for_entry_signal(current_price, atr)
        
        self.last_processed_index = current_index
        
        # Detect swing points
        swing_highs, swing_lows = self._detect_swing_points(df)
        self.swing_highs = swing_highs
        self.swing_lows = swing_lows
        
        # Detect structure break
        structure_break = self._detect_structure_break(df, swing_highs, swing_lows, atr)
        
        if structure_break:
            break_type, direction, break_index, level = structure_break
            
            # Update trend
            self.current_trend = direction
            self.last_bos_direction = direction
            
            # Find order block candle
            ob_index = self._find_order_block_candle(df, break_index, direction)
            
            if ob_index is not None:
                # Create new order block
                new_ob = self._create_order_block(df, ob_index, direction, break_type)
                self.order_blocks.append(new_ob)
                
                logger.info(
                    f"{'🟢' if direction == 'bullish' else '🔴'} "
                    f"New {direction.upper()} Order Block detected "
                    f"({break_type.value}): Zone {new_ob.low:.5f}-{new_ob.high:.5f}"
                )
        
        # Check mitigation
        self._check_mitigation(df, current_price)
        
        # Cleanup old blocks
        self._cleanup_old_blocks(current_index)
        
        # Check for entry signals
        return self._check_for_entry_signal(current_price, atr)
    
    def _check_for_entry_signal(
        self,
        current_price: float,
        atr: float
    ) -> Optional[Dict[str, Any]]:
        """Check if current price is at a valid order block for entry."""
        for ob in self.order_blocks:
            if not ob.is_valid or ob.is_mitigated:
                continue
            
            # Check if price is touching the order block zone
            buffer = atr * 0.1 if atr > 0 else 0  # Small buffer
            
            if ob.block_type == OrderBlockType.BULLISH:
                # Bullish OB: Look for long entry when price touches zone from above
                if ob.low - buffer <= current_price <= ob.high + buffer:
                    if ob.touches <= 2:  # Fresh OB (not touched too many times)
                        return {
                            'direction': 'long',
                            'entry_price': current_price,
                            'stop_loss': ob.low - (atr * 0.5),
                            'take_profit': current_price + (atr * 2),
                            'confidence': 0.80 - (ob.touches * 0.1),
                            'reason': f'Bullish Order Block ({ob.structure_break.value})',
                            'ob_high': ob.high,
                            'ob_low': ob.low,
                            'ob_type': 'bullish',
                            'touches': ob.touches
                        }
            
            else:  # Bearish OB
                # Bearish OB: Look for short entry when price touches zone from below
                if ob.low - buffer <= current_price <= ob.high + buffer:
                    if ob.touches <= 2:
                        return {
                            'direction': 'short',
                            'entry_price': current_price,
                            'stop_loss': ob.high + (atr * 0.5),
                            'take_profit': current_price - (atr * 2),
                            'confidence': 0.80 - (ob.touches * 0.1),
                            'reason': f'Bearish Order Block ({ob.structure_break.value})',
                            'ob_high': ob.high,
                            'ob_low': ob.low,
                            'ob_type': 'bearish',
                            'touches': ob.touches
                        }
        
        return None
    
    def get_active_order_blocks(self) -> List[OrderBlock]:
        """Get all currently active (unmitigated) order blocks."""
        return [ob for ob in self.order_blocks if ob.is_valid and not ob.is_mitigated]
    
    def get_nearest_order_block(
        self,
        current_price: float,
        direction: str = None
    ) -> Optional[OrderBlock]:
        """Get the nearest order block to current price."""
        active_obs = self.get_active_order_blocks()
        
        if direction:
            block_type = OrderBlockType.BULLISH if direction == 'long' else OrderBlockType.BEARISH
            active_obs = [ob for ob in active_obs if ob.block_type == block_type]
        
        if not active_obs:
            return None
        
        # Find nearest by distance to midpoint
        return min(active_obs, key=lambda ob: abs(current_price - ob.midpoint))
    
    def get_support_resistance_levels(self) -> Dict[str, List[float]]:
        """Get S/R levels from active order blocks."""
        active_obs = self.get_active_order_blocks()
        
        support = [ob.low for ob in active_obs if ob.block_type == OrderBlockType.BULLISH]
        resistance = [ob.high for ob in active_obs if ob.block_type == OrderBlockType.BEARISH]
        
        return {
            'support': sorted(support),
            'resistance': sorted(resistance, reverse=True)
        }
