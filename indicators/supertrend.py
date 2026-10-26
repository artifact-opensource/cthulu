"""
Supertrend Indicator

Advanced trend-following indicator combining ATR and price action.
Provides clear buy/sell signals with adaptive stop levels.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple
from .base import Indicator


class Supertrend(Indicator):
    """
    Supertrend Indicator.
    
    Combines price action with ATR-based volatility bands to identify trends.
    Provides dynamic support/resistance levels and clear directional signals.
    
    Formula:
        Basic Upper Band = (High + Low) / 2 + (Multiplier × ATR)
        Basic Lower Band = (High + Low) / 2 - (Multiplier × ATR)
        
        Final bands adjust based on price position relative to previous bands.
    """
    
    def __init__(self, period: int = 10, multiplier: float = 3.0):
        """
        Initialize Supertrend indicator.
        
        Args:
            period: ATR period (default: 10)
            multiplier: ATR multiplier for bands (default: 3.0)
        """
        super().__init__(
            name="Supertrend",
            params={'period': period, 'multiplier': multiplier}
        )
        self.period = period
        self.multiplier = multiplier
        
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate Supertrend values.
        
        Args:
            data: DataFrame with OHLCV data
            
        Returns:
            DataFrame with supertrend, direction, and signal columns
        """
        # Validate input
        self.validate_data(data, min_periods=self.period + 1)
        
        df = data.copy()
        
        # Calculate ATR
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        atr = true_range.rolling(self.period).mean()
        
        # Calculate basic bands
        hl2 = (df['high'] + df['low']) / 2
        basic_upper = hl2 + (self.multiplier * atr)
        basic_lower = hl2 - (self.multiplier * atr)
        
        # Initialize final bands
        final_upper = basic_upper.copy()
        final_lower = basic_lower.copy()
        
        # Calculate final bands using vectorized operations
        final_upper = basic_upper.copy()
        final_lower = basic_lower.copy()
        
        # Vectorized calculation with shift
        for i in range(1, len(df)):
            # Upper band: if previous final is NaN, default to current basic
            if pd.isna(final_upper.iloc[i-1]):
                final_upper.iloc[i] = basic_upper.iloc[i]
            else:
                # Upper band: if current basic < previous final OR close crossed above
                if basic_upper.iloc[i] < final_upper.iloc[i-1] or df['close'].iloc[i-1] > final_upper.iloc[i-1]:
                    final_upper.iloc[i] = basic_upper.iloc[i]
                else:
                    final_upper.iloc[i] = final_upper.iloc[i-1]
                
            # Lower band: if previous final is NaN, default to current basic
            if pd.isna(final_lower.iloc[i-1]):
                final_lower.iloc[i] = basic_lower.iloc[i]
            else:
                # Lower band: if current basic > previous final OR close crossed below
                if basic_lower.iloc[i] > final_lower.iloc[i-1] or df['close'].iloc[i-1] < final_lower.iloc[i-1]:
                    final_lower.iloc[i] = basic_lower.iloc[i]
                else:
                    final_lower.iloc[i] = final_lower.iloc[i-1]
        
        # Determine trend direction
        supertrend = pd.Series(index=df.index, dtype=float)
        direction = pd.Series(index=df.index, dtype=int)
        
        # Initialize
        supertrend.iloc[0] = final_upper.iloc[0]
        direction.iloc[0] = -1
        
        for i in range(1, len(df)):
            # Direction logic (compare to previous final bands)
            prev_upper = final_upper.iloc[i-1]
            prev_lower = final_lower.iloc[i-1]

            if df['close'].iloc[i] > prev_upper:
                direction.iloc[i] = 1
            elif df['close'].iloc[i] < prev_lower:
                direction.iloc[i] = -1
            else:
                direction.iloc[i] = direction.iloc[i-1]

            # Supertrend value based on current direction
            if direction.iloc[i] == 1:
                supertrend.iloc[i] = final_lower.iloc[i]
            else:
                supertrend.iloc[i] = final_upper.iloc[i]
        
        # Generate trading signals (1 = buy, -1 = sell, 0 = hold)
        signal = direction.diff()
        signal.iloc[0] = 0
        
        # Update state
        self._state['latest_direction'] = direction.iloc[-1]
        self._state['latest_value'] = supertrend.iloc[-1]
        self._state['is_bullish'] = direction.iloc[-1] == 1
        self.update_calculation_time()
        
        # Return as DataFrame
        result = pd.DataFrame({
            'supertrend': supertrend,
            'supertrend_direction': direction,
            'supertrend_signal': signal,
            'supertrend_upper': final_upper,
            'supertrend_lower': final_lower
        }, index=df.index)
        
        return result
        
    def is_bullish(self) -> bool:
        """Check if supertrend indicates bullish trend."""
        return self._state.get('is_bullish', False)
        
    def get_stop_level(self) -> float:
        """Get current supertrend stop level."""
        return self._state.get('latest_value', 0.0)




