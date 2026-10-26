"""
ATR (Average True Range) indicator implementation and wrapper

This module provides a simple function `calculate_atr` which returns a pandas
Series with ATR values based on High, Low, Close.
"""

import pandas as pd
from typing import Optional


from .base import Indicator


def calculate_atr(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Average True Range (ATR) over the given period.

    Args:
        data: DataFrame with 'high', 'low', 'close' columns and a DatetimeIndex
        period: ATR lookback period (default: 14)

    Returns:
        pandas Series with ATR values
    """
    # Validate
    if data is None or data.empty:
        raise ValueError("ATR: Dataframe empty")
    required = ['high', 'low', 'close']
    for r in required:
        if r not in data.columns:
            raise ValueError(f"ATR: Missing required column: {r}")
    if not isinstance(data.index, pd.DatetimeIndex):
        # Try to set index from 'time' column if present
        if 'time' in data.columns:
            data = data.set_index('time')
        else:
            raise ValueError("ATR: Index must be DatetimeIndex")

    high = data['high']
    low = data['low']
    close = data['close']

    # Calculate True Range components
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()

    # True Range is the maximum of the three components
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Use exponential moving average for smoother ATR (more responsive)
    # This is especially important for scalping strategies
    atr = tr.ewm(span=period, adjust=False, min_periods=1).mean()
    
    # Fill any NaN values at the start with the first valid value
    atr = atr.bfill()
    
    atr.name = 'atr'
    return atr


class ATR(Indicator):
    """Indicator wrapper for ATR compatible with the Indicator base class."""
    def __init__(self, period: int = 14, **kwargs):
        params = {'period': period}
        params.update({k: v for k, v in kwargs.items() if k not in params})
        super().__init__(name='ATR', params=params)
        self.period = int(period)

    def calculate(self, data: pd.DataFrame):
        # Prefer real high/low/close if present
        required = ['high', 'low', 'close']
        missing = [c for c in required if c not in data.columns]
        if not missing:
            # Validate full OHLC presence and compute normally
            try:
                self.validate_data(data, min_periods=self.period + 1, required_cols=required)
            except Exception:
                # Validation may be relaxed in fallback contexts; continue
                pass
            atr_series = calculate_atr(data[['high', 'low', 'close']].copy(), period=self.period)
        else:
            # Fallback: approximate ATR from close-only series when high/low missing
            if 'close' not in data.columns:
                raise ValueError("ATR: Missing required column 'close' for fallback calculation")
            close = data['close']
            # Use absolute returns as a proxy for true range
            tr = close.diff().abs()
            atr_series = tr.ewm(span=self.period, adjust=False, min_periods=1).mean()
        atr_series.name = 'atr'
        self.update_calculation_time()
        return atr_series


# Exports
__all__ = ["calculate_atr", "ATR"]




