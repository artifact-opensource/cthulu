"""
Market Structure Detector - BOS/ChoCH Detection Layer

Based on MQL5 Price Action Analysis Toolkit (Part 39): Automating BOS and ChoCH Detection.

This module provides production-ready fractal-based market structure analysis:
- Break of Structure (BOS): Decisive violation of prior swing high/low - CONFIRMATION
- Change of Character (ChoCH): Early warning of bias shift - WARNING

Key Philosophy:
- ChoCH is the early warning, BOS is the confirmation
- All signals must be evaluated using closed bars only (no repainting)
- Fractal pivots provide stable, non-repainting anchors

Part of Cthulu v6.0.0 APEX - Entry Quality System
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from enum import Enum
import logging

logger = logging.getLogger("cthulu.structure_detector")


class StructureSignalType(Enum):
    """Types of market structure signals."""
    BULL_BOS = "bull_bos"      # Bullish Break of Structure - CONFIRMATION
    BEAR_BOS = "bear_bos"      # Bearish Break of Structure - CONFIRMATION
    BULL_CHOCH = "bull_choch"  # Bullish Change of Character - WARNING
    BEAR_CHOCH = "bear_choch"  # Bearish Change of Character - WARNING
    NONE = "none"


class MarketBias(Enum):
    """Current market bias/trend direction."""
    BULLISH = 1
    BEARISH = -1
    NEUTRAL = 0


@dataclass
class FractalPivot:
    """A detected fractal pivot point."""
    time: datetime
    price: float
    is_high: bool  # True for high fractal, False for low fractal
    bar_index: int
    marked: bool = False  # True if already processed for BOS/ChoCH
    strength: float = 1.0  # Based on window size


@dataclass
class StructureSignal:
    """Market structure signal (BOS or ChoCH)."""
    signal_type: StructureSignalType
    timestamp: datetime
    price: float
    fractal_price: float
    fractal_time: datetime
    is_confirmation: bool  # True for BOS, False for ChoCH
    prior_bias: MarketBias
    new_bias: MarketBias
    confidence: float = 0.8
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_bullish(self) -> bool:
        return self.signal_type in [StructureSignalType.BULL_BOS, StructureSignalType.BULL_CHOCH]
    
    @property
    def is_bearish(self) -> bool:
        return self.signal_type in [StructureSignalType.BEAR_BOS, StructureSignalType.BEAR_CHOCH]


@dataclass
class StructureState:
    """Current market structure state."""
    bias: MarketBias = MarketBias.NEUTRAL
    last_signal: Optional[StructureSignal] = None
    swing_high: Optional[float] = None
    swing_low: Optional[float] = None
    swing_high_time: Optional[datetime] = None
    swing_low_time: Optional[datetime] = None
    trend_strength: float = 0.0  # 0-1, how strong is current trend


class MarketStructureDetector:
    """
    Fractal-based BOS/ChoCH detector for entry confirmation.
    
    Uses fractal pivots as reliable local anchors and detects:
    - ChoCH (Change of Character): Early warning of bias shift
    - BOS (Break of Structure): Confirmation of new bias
    
    Philosophy:
    - ChoCH = early warning (prepare, tighten stops, look for reversals)
    - BOS = confirmation (commit to new direction)
    - All signals use closed-bar logic for non-repainting results
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the structure detector.
        
        Args:
            config: Configuration dictionary with:
                - fractal_length: Window size for fractal detection (odd, >= 3)
                - max_history_bars: Max bars to keep fractal history
                - auto_detect_length: Auto-adjust length by timeframe
        """
        self.config = config or {}
        self.logger = logging.getLogger("cthulu.structure_detector")
        
        # Configuration
        self.auto_detect_length = self.config.get('auto_detect_length', True)
        self.fractal_length = self.config.get('fractal_length', 5)
        self.max_history_bars = self.config.get('max_history_bars', 2000)
        
        # Ensure odd length >= 3
        if self.fractal_length < 3:
            self.fractal_length = 5
        if self.fractal_length % 2 == 0:
            self.fractal_length += 1
        
        self.p_half = self.fractal_length // 2
        
        # State tracking
        self._bull_fractals: List[FractalPivot] = []
        self._bear_fractals: List[FractalPivot] = []
        self._market_state: Dict[str, StructureState] = {}  # Per-symbol state
        self._signal_history: List[StructureSignal] = []
        
        self.logger.info(f"MarketStructureDetector initialized: length={self.fractal_length}, p_half={self.p_half}")
    
    def adjust_length_for_timeframe(self, timeframe: str) -> int:
        """
        Auto-adjust fractal length based on timeframe.
        
        Args:
            timeframe: MT5 timeframe string (e.g., 'M1', 'H1', 'D1')
            
        Returns:
            Appropriate fractal length
        """
        if not self.auto_detect_length:
            return self.fractal_length
        
        timeframe_upper = timeframe.upper()
        
        if 'M1' in timeframe_upper or 'M5' in timeframe_upper:
            return 5
        elif 'M15' in timeframe_upper or 'M30' in timeframe_upper:
            return 5
        elif 'H1' in timeframe_upper:
            return 5
        elif 'H4' in timeframe_upper:
            return 7
        elif 'D1' in timeframe_upper:
            return 9
        else:
            return 11
    
    def detect_fractals(self, df: pd.DataFrame, symbol: str = 'UNKNOWN') -> Tuple[List[FractalPivot], List[FractalPivot]]:
        """
        Scan for new fractal pivots in market data.
        
        Uses closed-bar logic: only considers bars that are fully formed.
        
        Args:
            df: Market data DataFrame with columns: high, low, close, time/datetime
            symbol: Trading symbol for state tracking
            
        Returns:
            Tuple of (new_high_fractals, new_low_fractals)
        """
        if len(df) <= self.fractal_length:
            return [], []
        
        # Get time column
        time_col = 'time' if 'time' in df.columns else 'datetime'
        if time_col not in df.columns:
            # Use index if datetime
            df = df.copy()
            df['time'] = df.index
            time_col = 'time'
        
        new_high_fractals = []
        new_low_fractals = []
        
        # Center bar at p_half shift (closed bar)
        center_shift = self.p_half
        
        if center_shift >= len(df):
            return [], []
        
        highs = df['high'].values
        lows = df['low'].values
        times = df[time_col].values
        
        # Check for high fractal at center
        if self._is_fractal_high(highs, center_shift):
            fractal_time = pd.to_datetime(times[-center_shift - 1])
            fractal_price = float(highs[-center_shift - 1])
            
            # Check if already recorded
            if not self._fractal_exists(fractal_time, is_high=True):
                pivot = FractalPivot(
                    time=fractal_time,
                    price=fractal_price,
                    is_high=True,
                    bar_index=len(df) - center_shift - 1,
                    marked=False,
                    strength=1.0
                )
                self._bull_fractals.append(pivot)
                new_high_fractals.append(pivot)
                self.logger.debug(f"High fractal detected: {fractal_price:.5f} at {fractal_time}")
        
        # Check for low fractal at center
        if self._is_fractal_low(lows, center_shift):
            fractal_time = pd.to_datetime(times[-center_shift - 1])
            fractal_price = float(lows[-center_shift - 1])
            
            if not self._fractal_exists(fractal_time, is_high=False):
                pivot = FractalPivot(
                    time=fractal_time,
                    price=fractal_price,
                    is_high=False,
                    bar_index=len(df) - center_shift - 1,
                    marked=False,
                    strength=1.0
                )
                self._bear_fractals.append(pivot)
                new_low_fractals.append(pivot)
                self.logger.debug(f"Low fractal detected: {fractal_price:.5f} at {fractal_time}")
        
        # Prune old fractals
        self._prune_fractals(df)
        
        return new_high_fractals, new_low_fractals
    
    def _is_fractal_high(self, highs: np.ndarray, shift: int) -> bool:
        """Check if bar at shift is a high fractal (local maximum)."""
        if shift < 0 or shift >= len(highs):
            return False
        
        idx = len(highs) - shift - 1
        
        # Need full window on both sides
        if idx < self.p_half or idx >= len(highs) - self.p_half:
            return False
        
        center = highs[idx]
        
        # Check all neighbors
        for k in range(-self.p_half, self.p_half + 1):
            if k == 0:
                continue
            if highs[idx + k] > center:
                return False
        
        return True
    
    def _is_fractal_low(self, lows: np.ndarray, shift: int) -> bool:
        """Check if bar at shift is a low fractal (local minimum)."""
        if shift < 0 or shift >= len(lows):
            return False
        
        idx = len(lows) - shift - 1
        
        # Need full window on both sides
        if idx < self.p_half or idx >= len(lows) - self.p_half:
            return False
        
        center = lows[idx]
        
        # Check all neighbors
        for k in range(-self.p_half, self.p_half + 1):
            if k == 0:
                continue
            if lows[idx + k] < center:
                return False
        
        return True
    
    def _fractal_exists(self, time: datetime, is_high: bool) -> bool:
        """Check if fractal already recorded."""
        fractals = self._bull_fractals if is_high else self._bear_fractals
        return any(f.time == time for f in fractals)
    
    def _prune_fractals(self, df: pd.DataFrame):
        """Remove fractals older than max_history_bars."""
        if len(df) < self.max_history_bars:
            return
        
        cutoff_idx = len(df) - self.max_history_bars
        
        self._bull_fractals = [f for f in self._bull_fractals if f.bar_index >= cutoff_idx]
        self._bear_fractals = [f for f in self._bear_fractals if f.bar_index >= cutoff_idx]
    
    def process_crosses(self, df: pd.DataFrame, symbol: str = 'UNKNOWN') -> List[StructureSignal]:
        """
        Check if price has crossed any stored fractal levels.
        
        Uses closed-bar crossing detection for non-repainting signals.
        
        Args:
            df: Market data DataFrame
            symbol: Trading symbol
            
        Returns:
            List of new structure signals (BOS/ChoCH)
        """
        if len(df) < 3:
            return []
        
        signals = []
        
        # Get closes for crossing detection
        prev_close = float(df['close'].iloc[-2])
        cur_close = float(df['close'].iloc[-1])
        cur_time = pd.to_datetime(df.index[-1] if isinstance(df.index, pd.DatetimeIndex) 
                                  else df['time'].iloc[-1] if 'time' in df.columns 
                                  else datetime.now())
        
        # Get current state
        state = self._get_or_create_state(symbol)
        
        # Process bullish fractals (high fractals)
        for fractal in self._bull_fractals:
            if fractal.marked:
                continue
            
            # Check for upward cross (bullish BOS)
            if self._crossed_over(prev_close, cur_close, fractal.price):
                is_choch = state.bias == MarketBias.BEARISH
                
                signal = StructureSignal(
                    signal_type=StructureSignalType.BULL_CHOCH if is_choch else StructureSignalType.BULL_BOS,
                    timestamp=cur_time,
                    price=cur_close,
                    fractal_price=fractal.price,
                    fractal_time=fractal.time,
                    is_confirmation=not is_choch,  # BOS is confirmation
                    prior_bias=state.bias,
                    new_bias=MarketBias.BULLISH,
                    confidence=0.85 if is_choch else 0.90,
                    metadata={
                        'cross_type': 'upward',
                        'prev_close': prev_close,
                        'cur_close': cur_close
                    }
                )
                
                signals.append(signal)
                fractal.marked = True
                state.bias = MarketBias.BULLISH
                state.last_signal = signal
                state.swing_high = fractal.price
                state.swing_high_time = fractal.time
                
                self._signal_history.append(signal)
                
                signal_name = "Bull ChoCH" if is_choch else "Bull BOS"
                self.logger.info(f"{signal_name} detected: {symbol} @ {cur_close:.5f} (fractal={fractal.price:.5f})")
        
        # Process bearish fractals (low fractals)
        for fractal in self._bear_fractals:
            if fractal.marked:
                continue
            
            # Check for downward cross (bearish BOS)
            if self._crossed_under(prev_close, cur_close, fractal.price):
                is_choch = state.bias == MarketBias.BULLISH
                
                signal = StructureSignal(
                    signal_type=StructureSignalType.BEAR_CHOCH if is_choch else StructureSignalType.BEAR_BOS,
                    timestamp=cur_time,
                    price=cur_close,
                    fractal_price=fractal.price,
                    fractal_time=fractal.time,
                    is_confirmation=not is_choch,
                    prior_bias=state.bias,
                    new_bias=MarketBias.BEARISH,
                    confidence=0.85 if is_choch else 0.90,
                    metadata={
                        'cross_type': 'downward',
                        'prev_close': prev_close,
                        'cur_close': cur_close
                    }
                )
                
                signals.append(signal)
                fractal.marked = True
                state.bias = MarketBias.BEARISH
                state.last_signal = signal
                state.swing_low = fractal.price
                state.swing_low_time = fractal.time
                
                self._signal_history.append(signal)
                
                signal_name = "Bear ChoCH" if is_choch else "Bear BOS"
                self.logger.info(f"{signal_name} detected: {symbol} @ {cur_close:.5f} (fractal={fractal.price:.5f})")
        
        return signals
    
    def _crossed_over(self, prev_close: float, cur_close: float, level: float) -> bool:
        """Check if price crossed above a level (closed-bar logic)."""
        return prev_close <= level and cur_close > level
    
    def _crossed_under(self, prev_close: float, cur_close: float, level: float) -> bool:
        """Check if price crossed below a level (closed-bar logic)."""
        return prev_close >= level and cur_close < level
    
    def _get_or_create_state(self, symbol: str) -> StructureState:
        """Get or create market structure state for a symbol."""
        if symbol not in self._market_state:
            self._market_state[symbol] = StructureState()
        return self._market_state[symbol]
    
    def analyze(self, df: pd.DataFrame, symbol: str = 'UNKNOWN') -> Tuple[List[StructureSignal], StructureState]:
        """
        Full structure analysis: detect fractals and check for BOS/ChoCH.
        
        Args:
            df: Market data DataFrame
            symbol: Trading symbol
            
        Returns:
            Tuple of (new_signals, current_state)
        """
        # Detect new fractals
        self.detect_fractals(df, symbol)
        
        # Process crosses
        signals = self.process_crosses(df, symbol)
        
        # Get current state
        state = self._get_or_create_state(symbol)
        
        return signals, state
    
    def get_entry_confirmation(
        self,
        signal_direction: str,  # 'long' or 'short'
        symbol: str,
        df: pd.DataFrame
    ) -> Tuple[bool, str, float]:
        """
        Check if market structure confirms entry direction.
        
        This is the primary interface for the entry confluence filter.
        
        Args:
            signal_direction: 'long' or 'short'
            symbol: Trading symbol
            df: Market data DataFrame
            
        Returns:
            Tuple of (confirmed, reason, confidence_multiplier)
        """
        # Run analysis
        signals, state = self.analyze(df, symbol)
        
        # Check for recent BOS/ChoCH in our direction
        recent_signals = [s for s in signals]  # Signals from this bar
        
        # Also check last signal in state
        if state.last_signal and state.last_signal not in recent_signals:
            recent_signals.append(state.last_signal)
        
        if signal_direction.lower() == 'long':
            # For long entries, we want bullish structure
            if state.bias == MarketBias.BULLISH:
                # Check if we just got a bullish BOS (strongest confirmation)
                for sig in recent_signals:
                    if sig.signal_type == StructureSignalType.BULL_BOS:
                        return True, "Bullish BOS confirmed - structure break upward", 1.15
                    elif sig.signal_type == StructureSignalType.BULL_CHOCH:
                        return True, "Bullish ChoCH - early reversal warning", 1.05
                
                # General bullish bias
                return True, "Market structure bullish", 1.0
            
            elif state.bias == MarketBias.BEARISH:
                # Trading against structure - warning
                return False, "Market structure bearish - long entry risky", 0.6
            
            else:  # Neutral
                return True, "Market structure neutral", 0.85
        
        else:  # short
            # For short entries, we want bearish structure
            if state.bias == MarketBias.BEARISH:
                for sig in recent_signals:
                    if sig.signal_type == StructureSignalType.BEAR_BOS:
                        return True, "Bearish BOS confirmed - structure break downward", 1.15
                    elif sig.signal_type == StructureSignalType.BEAR_CHOCH:
                        return True, "Bearish ChoCH - early reversal warning", 1.05
                
                return True, "Market structure bearish", 1.0
            
            elif state.bias == MarketBias.BULLISH:
                return False, "Market structure bullish - short entry risky", 0.6
            
            else:
                return True, "Market structure neutral", 0.85
    
    def get_current_state(self, symbol: str) -> StructureState:
        """Get current market structure state for a symbol."""
        return self._get_or_create_state(symbol)
    
    def get_recent_signals(self, symbol: str = None, limit: int = 10) -> List[StructureSignal]:
        """Get recent structure signals."""
        signals = self._signal_history
        if symbol:
            signals = [s for s in signals if hasattr(s, 'metadata') and 
                      s.metadata.get('symbol') == symbol]
        return signals[-limit:]
    
    def clear_state(self, symbol: str = None):
        """Clear state for a symbol or all symbols."""
        if symbol:
            if symbol in self._market_state:
                del self._market_state[symbol]
        else:
            self._market_state.clear()
        
        self._bull_fractals.clear()
        self._bear_fractals.clear()
        self._signal_history.clear()


# Module-level singleton
_structure_detector: Optional[MarketStructureDetector] = None


def get_structure_detector(**kwargs) -> MarketStructureDetector:
    """Get or create the structure detector singleton."""
    global _structure_detector
    if _structure_detector is None:
        _structure_detector = MarketStructureDetector(**kwargs)
    return _structure_detector


def check_structure_confirmation(
    signal_direction: str,
    symbol: str,
    market_data: pd.DataFrame
) -> Tuple[bool, str, float]:
    """
    Convenience function to check structure confirmation.
    
    Args:
        signal_direction: 'long' or 'short'
        symbol: Trading symbol
        market_data: OHLCV DataFrame
        
    Returns:
        Tuple of (confirmed, reason, confidence_multiplier)
    """
    detector = get_structure_detector()
    return detector.get_entry_confirmation(signal_direction, symbol, market_data)
