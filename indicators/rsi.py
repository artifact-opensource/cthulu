"""
RSI (Relative Strength Index) Indicator

Measures momentum by comparing magnitude of recent gains to recent losses.
RSI oscillates between 0 and 100:
- Above 70: Overbought condition
- Below 30: Oversold condition
"""

import pandas as pd
import numpy as np
from typing import Dict, Any
from .base import Indicator

# Small epsilon to avoid division by zero in RSI calculation
EPSILON = 1e-10


class RSI(Indicator):
    """
    Relative Strength Index indicator.
    
    The RSI compares the magnitude of recent gains to recent losses
    to determine overbought and oversold conditions.
    
    Formula:
        RS = Average Gain / Average Loss
        RSI = 100 - (100 / (1 + RS))
    """
    
    def __init__(self, period: int = 14, overbought: float = 70.0, oversold: float = 30.0, **kwargs):
        """
        Initialize RSI indicator.

        Args:
            period: Lookback period for RSI calculation (default: 14)
            overbought: Threshold considered overbought (default: 70.0)
            oversold: Threshold considered oversold (default: 30.0)
            **kwargs: Accept and ignore legacy/extra kwargs for forward-compatibility
        """
        params = {'period': period, 'overbought': overbought, 'oversold': oversold}
        # Preserve any additional params passed for backwards compatibility
        params.update({k: v for k, v in kwargs.items() if k not in params})
        super().__init__(
            name="RSI",
            params=params
        )
        self.period = period
        self.overbought = float(overbought)
        self.oversold = float(oversold)
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """
        Calculate RSI values.
        
        Args:
            data: DataFrame with OHLCV data
            
        Returns:
            Series with RSI values (0-100)
        """
        # Validate input; RSI only requires 'close' values so allow a relaxed
        # validation (helps runtime fallback when only close series is present)
        self.validate_data(data, min_periods=self.period + 1, required_cols=['close'])
        
        # Calculate price changes
        delta = data['close'].diff()
        
        # Separate gains and losses
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        
        # Calculate average gain and loss using exponential moving average
        avg_gain = gain.ewm(span=self.period, adjust=False, min_periods=self.period).mean()
        avg_loss = loss.ewm(span=self.period, adjust=False, min_periods=self.period).mean()
        
        # Calculate RS and RSI
        # Handle division by zero: when avg_loss is 0, RSI = 100
        rs = avg_gain / avg_loss.replace(0, EPSILON)  # Avoid division by zero
        rsi = 100.0 - (100.0 / (1.0 + rs))
        
        # Clip to ensure values stay within bounds
        rsi = rsi.clip(lower=0.0, upper=100.0)
        
        # Handle special cases
        # When there are no losses, RSI should be 100
        rsi.loc[avg_loss == 0] = 100.0
        # When there are no gains, RSI should be 0
        rsi.loc[avg_gain == 0] = 0.0
        
        # Set initial values to NaN (insufficient data for calculation)
        rsi.iloc[: max(0, self.period - 1)] = float('nan')
        
        # Update state
        self._state['latest_rsi'] = rsi.iloc[-1] if len(rsi) > 0 and not pd.isna(rsi.iloc[-1]) else None
        self._state['is_overbought'] = rsi.iloc[-1] > self.overbought if len(rsi) > 0 and not pd.isna(rsi.iloc[-1]) else False
        self._state['is_oversold'] = rsi.iloc[-1] < self.oversold if len(rsi) > 0 and not pd.isna(rsi.iloc[-1]) else False
        self.update_calculation_time()
        
        # Name the series with period to avoid conflicts
        rsi.name = f'rsi_{self.period}' if self.period != 14 else 'rsi'
        
        return rsi
        
    def is_overbought(self, threshold: float = 70.0) -> bool:
        """
        Check if RSI indicates overbought condition.
        
        Args:
            threshold: Overbought threshold (default: 70)
            
        Returns:
            True if overbought
        """
        latest_rsi = self._state.get('latest_rsi')
        return latest_rsi is not None and latest_rsi > threshold
        
    def is_oversold(self, threshold: float = 30.0) -> bool:
        """
        Check if RSI indicates oversold condition.
        
        Args:
            threshold: Oversold threshold (default: 30)
            
        Returns:
            True if oversold
        """
        latest_rsi = self._state.get('latest_rsi')
        return latest_rsi is not None and latest_rsi < threshold
        
    def get_signal(self) -> str:
        """
        Get trading signal based on RSI levels.
        
        Returns:
            'BUY' if oversold, 'SELL' if overbought, 'NEUTRAL' otherwise
        """
        if self.is_oversold():
            return 'BUY'
        elif self.is_overbought():
            return 'SELL'
        else:
            return 'NEUTRAL'


# Module-level convenience wrappers for backwards compatibility
def calculate_rsi(data: pd.DataFrame, period: int = 14) -> pd.Series:
    inst = RSI(period=period)
    return inst.calculate(data)


def is_overbought(rsi_series: pd.Series, threshold: float = 70.0) -> pd.Series:
    return rsi_series > threshold


def is_oversold(rsi_series: pd.Series, threshold: float = 30.0) -> pd.Series:
    return rsi_series < threshold




