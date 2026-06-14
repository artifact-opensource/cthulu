"""
Bollinger Bands Indicator

Volatility bands placed above and below a moving average.
Bands expand during volatile periods and contract during calm periods.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any
from .base import Indicator


class BollingerBands(Indicator):
    """
    Bollinger Bands indicator.
    
    Consists of a middle band (SMA) and two outer bands at standard deviations
    above and below the middle band. Used to identify overbought/oversold conditions
    and volatility.
    
    Formula:
        Middle Band = SMA(close, period)
        Upper Band = Middle Band + (std_dev * Standard Deviation)
        Lower Band = Middle Band - (std_dev * Standard Deviation)
    """
    
    def __init__(self, period: int = 20, std_dev: float = 2.0):
        """
        Initialize Bollinger Bands indicator.
        
        Args:
            period: Moving average period (default: 20)
            std_dev: Number of standard deviations (default: 2.0)
        """
        super().__init__(
            name="BollingerBands",
            params={
                'period': period,
                'std_dev': std_dev
            }
        )
        self.period = period
        self.std_dev = std_dev
        
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate Bollinger Bands.
        
        Args:
            data: DataFrame with OHLCV data
            
        Returns:
            DataFrame with 'bb_upper', 'bb_middle', 'bb_lower', 'bb_width', 'bb_percent' columns
        """
        # Validate input
        self.validate_data(data, min_periods=self.period)
        
        close = data['close']
        
        # Calculate middle band (SMA) with fallback to use min_periods=1 so initial rows are defined
        middle_band = close.rolling(window=self.period, min_periods=1).mean()
        
        # Calculate standard deviation with min_periods=1
        std = close.rolling(window=self.period, min_periods=1).std().fillna(0)
        
        # Calculate upper and lower bands
        upper_band = middle_band + (std * self.std_dev)
        lower_band = middle_band - (std * self.std_dev)
        
        # Calculate band width (volatility measure)
        band_width = (upper_band - lower_band) / middle_band
        
        # Calculate %B (where price is relative to bands)
        # %B = (Close - Lower Band) / (Upper Band - Lower Band)
        # %B > 1: Above upper band, %B < 0: Below lower band, %B = 0.5: At middle band
        percent_b = (close - lower_band) / (upper_band - lower_band)
        
        # Create result DataFrame
        result = pd.DataFrame({
            'bb_upper': upper_band,
            'bb_middle': middle_band,
            'bb_lower': lower_band,
            'bb_width': band_width,
            'bb_percent': percent_b
        }, index=data.index)
        
        # Update state
        if len(result) > 0:
            latest_close = close.iloc[-1]
            self._state['latest_upper'] = result['bb_upper'].iloc[-1]
            self._state['latest_middle'] = result['bb_middle'].iloc[-1]
            self._state['latest_lower'] = result['bb_lower'].iloc[-1]
            self._state['latest_width'] = result['bb_width'].iloc[-1]
            self._state['latest_percent'] = result['bb_percent'].iloc[-1]
            self._state['latest_close'] = latest_close
            
            # Determine position relative to bands
            percent_b_value = result['bb_percent'].iloc[-1]
            if pd.notna(percent_b_value):
                self._state['above_upper'] = percent_b_value > 1.0
                self._state['below_lower'] = percent_b_value < 0.0
                self._state['near_upper'] = 0.8 < percent_b_value <= 1.0
                self._state['near_lower'] = 0.0 <= percent_b_value < 0.2
            else:
                self._state['above_upper'] = False
                self._state['below_lower'] = False
                self._state['near_upper'] = False
                self._state['near_lower'] = False
                
        self.update_calculation_time()
        
        return result
        
    def is_above_upper_band(self) -> bool:
        """
        Check if price is above upper Bollinger Band (overbought).
        
        Returns:
            True if price is above upper band
        """
        return self._state.get('above_upper', False)
        
    def is_below_lower_band(self) -> bool:
        """
        Check if price is below lower Bollinger Band (oversold).
        
        Returns:
            True if price is below lower band
        """
        return self._state.get('below_lower', False)
        
    def is_near_upper_band(self) -> bool:
        """
        Check if price is near upper band (80-100% range).
        
        Returns:
            True if price is near upper band
        """
        return self._state.get('near_upper', False)
        
    def is_near_lower_band(self) -> bool:
        """
        Check if price is near lower band (0-20% range).
        
        Returns:
            True if price is near lower band
        """
        return self._state.get('near_lower', False)
        
    def get_volatility_state(self) -> str:
        """
        Get volatility state based on band width.
        
        Returns:
            'HIGH' if width > average, 'LOW' if width < average, 'NORMAL' otherwise
        """
        width = self._state.get('latest_width')
        if width is None:
            return 'UNKNOWN'
            
        # Simple heuristic: high volatility if width > 0.05, low if < 0.02
        if width > 0.05:
            return 'HIGH'
        elif width < 0.02:
            return 'LOW'
        else:
            return 'NORMAL'
            
    def get_signal(self) -> str:
        """
        Get trading signal based on Bollinger Band position.
        
        Returns:
            'BUY' if below lower band, 'SELL' if above upper band, 'NEUTRAL' otherwise
        """
        if self.is_below_lower_band():
            return 'BUY'
        elif self.is_above_upper_band():
            return 'SELL'
        else:
            return 'NEUTRAL'


# Module-level wrappers for legacy API
def calculate_bollinger_bands(data: pd.DataFrame, period: int = 20, std_dev: float = 2.0):
    inst = BollingerBands(period=period, std_dev=std_dev)
    res = inst.calculate(data)
    return res['bb_upper'], res['bb_middle'], res['bb_lower']


def detect_squeeze(upper_series: pd.Series, lower_series: pd.Series, threshold: float = 0.02):
    width = (upper_series - lower_series) / upper_series
    return width < threshold




