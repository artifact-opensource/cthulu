"""
ADX (Average Directional Index) Indicator

Measures trend strength regardless of direction.
Components:
- ADX: Trend strength (0-100)
- +DI: Positive directional indicator
- -DI: Negative directional indicator
"""

import pandas as pd
import numpy as np
from typing import Dict, Any
from .base import Indicator


class ADX(Indicator):
    """
    Average Directional Index indicator.
    
    Measures the strength of a trend without regard to direction.
    Values range from 0 to 100:
    - ADX > 25: Strong trend
    - ADX < 20: Weak trend or ranging market
    - ADX > 50: Very strong trend
    
    +DI and -DI crossovers indicate trend direction:
    - +DI crosses above -DI: Bullish
    - -DI crosses above +DI: Bearish
    
    Formula:
        TR = max(High - Low, abs(High - Close[1]), abs(Low - Close[1]))
        +DM = High - High[1] if > 0 and > -(Low - Low[1]), else 0
        -DM = Low[1] - Low if > 0 and > (High - High[1]), else 0
        +DI = 100 * EMA(+DM, period) / EMA(TR, period)
        -DI = 100 * EMA(-DM, period) / EMA(TR, period)
        DX = 100 * abs(+DI - -DI) / (+DI + -DI)
        ADX = EMA(DX, period)
    """
    
    def __init__(self, period: int = 14):
        """
        Initialize ADX indicator.
        
        Args:
            period: Lookback period for ADX calculation (default: 14)
        """
        super().__init__(
            name="ADX",
            params={'period': period}
        )
        self.period = period
        
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate ADX and directional indicators.
        
        Args:
            data: DataFrame with OHLCV data
            
        Returns:
            DataFrame with 'adx', 'plus_di', 'minus_di' columns
        """
        # Validate input (need 2x period for smoothing)
        min_periods = self.period * 2
        self.validate_data(data, min_periods=min_periods)
        
        high = data['high']
        low = data['low']
        close = data['close']
        
        # Calculate True Range (TR)
        high_low = high - low
        high_close = (high - close.shift(1)).abs()
        low_close = (low - close.shift(1)).abs()
        
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        
        # Calculate Directional Movement
        high_diff = high.diff()
        low_diff = -low.diff()
        
        # +DM when upward movement is greater than downward movement
        plus_dm = pd.Series(0.0, index=data.index)
        plus_dm[(high_diff > low_diff) & (high_diff > 0)] = high_diff
        
        # -DM when downward movement is greater than upward movement
        minus_dm = pd.Series(0.0, index=data.index)
        minus_dm[(low_diff > high_diff) & (low_diff > 0)] = low_diff
        
        # Smooth TR, +DM, -DM using Wilder's smoothing (EMA with alpha = 1/period)
        alpha = 1.0 / self.period
        
        tr_smooth = tr.ewm(alpha=alpha, adjust=False).mean()
        plus_dm_smooth = plus_dm.ewm(alpha=alpha, adjust=False).mean()
        minus_dm_smooth = minus_dm.ewm(alpha=alpha, adjust=False).mean()
        
        # Calculate Directional Indicators
        plus_di = 100.0 * plus_dm_smooth / tr_smooth
        minus_di = 100.0 * minus_dm_smooth / tr_smooth
        
        # Calculate DX (Directional Index)
        di_sum = plus_di + minus_di
        di_diff = (plus_di - minus_di).abs()
        
        # Avoid division by zero
        dx = pd.Series(0.0, index=data.index)
        dx[di_sum != 0] = 100.0 * di_diff[di_sum != 0] / di_sum[di_sum != 0]
        
        # Calculate ADX (smoothed DX)
        adx = dx.ewm(alpha=alpha, adjust=False).mean()
        
        # Create result DataFrame
        result = pd.DataFrame({
            'adx': adx,
            'plus_di': plus_di,
            'minus_di': minus_di
        }, index=data.index)
        
        # Update state
        if len(result) > 0:
            self._state['latest_adx'] = result['adx'].iloc[-1]
            self._state['latest_plus_di'] = result['plus_di'].iloc[-1]
            self._state['latest_minus_di'] = result['minus_di'].iloc[-1]
            
            adx_value = result['adx'].iloc[-1]
            plus_di_value = result['plus_di'].iloc[-1]
            minus_di_value = result['minus_di'].iloc[-1]
            
            # Determine trend strength
            if pd.notna(adx_value):
                self._state['strong_trend'] = adx_value > 25
                self._state['very_strong_trend'] = adx_value > 50
                self._state['weak_trend'] = adx_value < 20
            else:
                self._state['strong_trend'] = False
                self._state['very_strong_trend'] = False
                self._state['weak_trend'] = True
                
            # Determine trend direction
            if pd.notna(plus_di_value) and pd.notna(minus_di_value):
                self._state['bullish_trend'] = plus_di_value > minus_di_value
                self._state['bearish_trend'] = minus_di_value > plus_di_value
            else:
                self._state['bullish_trend'] = False
                self._state['bearish_trend'] = False
                
            # Detect DI crossovers
            if len(result) > 1:
                prev_plus = result['plus_di'].iloc[-2]
                prev_minus = result['minus_di'].iloc[-2]
                
                if pd.notna(prev_plus) and pd.notna(prev_minus):
                    prev_diff = prev_plus - prev_minus
                    curr_diff = plus_di_value - minus_di_value
                    
                    self._state['bullish_crossover'] = prev_diff <= 0 and curr_diff > 0
                    self._state['bearish_crossover'] = prev_diff >= 0 and curr_diff < 0
                else:
                    self._state['bullish_crossover'] = False
                    self._state['bearish_crossover'] = False
            else:
                self._state['bullish_crossover'] = False
                self._state['bearish_crossover'] = False
                
        self.update_calculation_time()
        
        return result
        
    def is_trending(self, threshold: float = 25.0) -> bool:
        """
        Check if market is trending.
        
        Args:
            threshold: ADX threshold for trending (default: 25)
            
        Returns:
            True if ADX is above threshold (trending market)
        """
        adx_value = self._state.get('latest_adx')
        return adx_value is not None and adx_value > threshold
        
    def is_ranging(self, threshold: float = 20.0) -> bool:
        """
        Check if market is ranging.
        
        Args:
            threshold: ADX threshold for ranging (default: 20)
            
        Returns:
            True if ADX is below threshold (ranging market)
        """
        adx_value = self._state.get('latest_adx')
        return adx_value is not None and adx_value < threshold
        
    def get_trend_direction(self) -> str:
        """
        Get current trend direction based on +DI and -DI.
        
        Returns:
            'BULLISH' if +DI > -DI, 'BEARISH' if -DI > +DI, 'NEUTRAL' if no clear direction
        """
        if self._state.get('bullish_trend'):
            return 'BULLISH'
        elif self._state.get('bearish_trend'):
            return 'BEARISH'
        else:
            return 'NEUTRAL'
            
    def get_trend_strength(self) -> str:
        """
        Get trend strength classification.
        
        Returns:
            'VERY_STRONG' if ADX > 50
            'STRONG' if ADX > 25
            'WEAK' if ADX < 20
            'MODERATE' otherwise
        """
        adx_value = self._state.get('latest_adx')
        
        if adx_value is None:
            return 'UNKNOWN'
        elif adx_value > 50:
            return 'VERY_STRONG'
        elif adx_value > 25:
            return 'STRONG'
        elif adx_value < 20:
            return 'WEAK'
        else:
            return 'MODERATE'
            
    def is_bullish_crossover(self) -> bool:
        """
        Check if +DI crossed above -DI (bullish signal).
        
        Returns:
            True if bullish DI crossover occurred
        """
        return self._state.get('bullish_crossover', False)
        
    def is_bearish_crossover(self) -> bool:
        """
        Check if -DI crossed above +DI (bearish signal).
        
        Returns:
            True if bearish DI crossover occurred
        """
        return self._state.get('bearish_crossover', False)
        
    def get_signal(self) -> str:
        """
        Get trading signal based on ADX and directional indicators.
        
        Returns:
            'BUY' if bullish crossover in trending market
            'SELL' if bearish crossover in trending market
            'NEUTRAL' if ranging or no clear signal
        """
        # Only generate signals in trending markets
        if not self.is_trending():
            return 'NEUTRAL'
            
        if self.is_bullish_crossover():
            return 'BUY'
        elif self.is_bearish_crossover():
            return 'SELL'
        else:
            return 'NEUTRAL'


# Backwards-compatible helper functions
def calculate_adx(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """Convenience wrapper: return ADX series."""
    adx_inst = ADX(period=period)
    result = adx_inst.calculate(data)
    return result['adx']


def is_strong_trend(adx_series: pd.Series, threshold: float = 25.0) -> pd.Series:
    """Convenience wrapper: identify strong trend points in ADX series."""
    return adx_series > threshold




