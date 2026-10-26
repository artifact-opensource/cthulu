"""
MACD (Moving Average Convergence Divergence) Indicator

Trend-following momentum indicator showing relationship between two moving averages.
Components:
- MACD Line: fast EMA - slow EMA
- Signal Line: EMA of MACD line
- Histogram: MACD line - Signal line
"""

import pandas as pd
import numpy as np
from typing import Dict, Any
from .base import Indicator


class MACD(Indicator):
    """
    Moving Average Convergence Divergence indicator.
    
    Shows the relationship between two exponential moving averages.
    Generates signals through crossovers and divergence.
    
    Formula:
        MACD Line = EMA(fast) - EMA(slow)
        Signal Line = EMA(MACD Line, signal_period)
        Histogram = MACD Line - Signal Line
    """
    
    def __init__(self, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9):
        """
        Initialize MACD indicator.
        
        Args:
            fast_period: Fast EMA period (default: 12)
            slow_period: Slow EMA period (default: 26)
            signal_period: Signal line EMA period (default: 9)
        """
        super().__init__(
            name="MACD",
            params={
                'fast_period': fast_period,
                'slow_period': slow_period,
                'signal_period': signal_period
            }
        )
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate MACD components.
        
        Args:
            data: DataFrame with OHLCV data
            
        Returns:
            DataFrame with 'macd', 'signal', 'histogram' columns
        """
        # Validate input (need enough data for slow EMA + signal calculation)
        min_periods = self.slow_period + self.signal_period
        self.validate_data(data, min_periods=min_periods)
        
        close = data['close']
        
        # Calculate fast and slow EMAs
        ema_fast = close.ewm(span=self.fast_period, adjust=False).mean()
        ema_slow = close.ewm(span=self.slow_period, adjust=False).mean()
        
        # Calculate MACD line
        macd_line = ema_fast - ema_slow
        
        # Calculate signal line
        signal_line = macd_line.ewm(span=self.signal_period, adjust=False).mean()
        
        # Calculate histogram
        histogram = macd_line - signal_line
        
        # Create result DataFrame
        result = pd.DataFrame({
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        }, index=data.index)
        
        # Update state
        if len(result) > 0:
            self._state['latest_macd'] = result['macd'].iloc[-1]
            self._state['latest_signal'] = result['signal'].iloc[-1]
            self._state['latest_histogram'] = result['histogram'].iloc[-1]
            
            # Detect crossover
            if len(result) > 1:
                prev_diff = result['macd'].iloc[-2] - result['signal'].iloc[-2]
                curr_diff = result['macd'].iloc[-1] - result['signal'].iloc[-1]
                
                self._state['bullish_crossover'] = prev_diff <= 0 and curr_diff > 0
                self._state['bearish_crossover'] = prev_diff >= 0 and curr_diff < 0
            else:
                self._state['bullish_crossover'] = False
                self._state['bearish_crossover'] = False
                
        self.update_calculation_time()
        
        return result
        
    def is_bullish_crossover(self) -> bool:
        """
        Check if MACD line crossed above signal line (bullish signal).
        
        Returns:
            True if bullish crossover occurred
        """
        return self._state.get('bullish_crossover', False)
        
    def is_bearish_crossover(self) -> bool:
        """
        Check if MACD line crossed below signal line (bearish signal).
        
        Returns:
            True if bearish crossover occurred
        """
        return self._state.get('bearish_crossover', False)
        
    def get_signal(self) -> str:
        """
        Get trading signal based on MACD crossovers.
        
        Returns:
            'BUY' if bullish crossover, 'SELL' if bearish crossover, 'NEUTRAL' otherwise
        """
        if self.is_bullish_crossover():
            return 'BUY'
        elif self.is_bearish_crossover():
            return 'SELL'
        else:
            return 'NEUTRAL'
            
    def get_histogram_trend(self) -> str:
        """
        Get histogram trend direction.
        
        Returns:
            'INCREASING' if histogram growing, 'DECREASING' if shrinking, 'NEUTRAL' otherwise
        """
        histogram = self._state.get('latest_histogram')
        if histogram is None:
            return 'NEUTRAL'

        if histogram > 0:
            return 'INCREASING'
        elif histogram < 0:
            return 'DECREASING'
        else:
            return 'NEUTRAL'


# Backwards-compatible helper functions
def calculate_macd(data: pd.DataFrame, fast: int = 12, slow: int = 26, signal_period: int = 9):
    inst = MACD(fast_period=fast, slow_period=slow, signal_period=signal_period)
    result = inst.calculate(data)
    hist = result['histogram'].copy()
    # Match test expectations: histogram returned without a name
    hist.name = None
    return result['macd'], result['signal'], hist


def detect_crossover(macd_series: pd.Series, signal_series: pd.Series):
    bullish = (macd_series > signal_series) & (macd_series.shift(1) <= signal_series.shift(1))
    bearish = (macd_series < signal_series) & (macd_series.shift(1) >= signal_series.shift(1))
    return bullish.fillna(False), bearish.fillna(False)




