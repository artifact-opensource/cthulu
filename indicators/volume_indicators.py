"""
Volume Price Trend (VPT) Indicator

Combines price and volume to identify accumulation/distribution patterns.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional

from cthulu.indicators.base import Indicator


class VPT(Indicator):
    """
    Volume Price Trend (VPT) Indicator.

    VPT combines price movements with volume to identify accumulation
    and distribution patterns. Rising VPT indicates buying pressure,
    falling VPT indicates selling pressure.

    Parameters:
        None (VPT is calculated from price and volume)
    """

    def __init__(self, **kwargs):
        """Initialize VPT indicator."""
        super().__init__("vpt", **kwargs)

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """
        Calculate Volume Price Trend.

        Args:
            data: DataFrame with OHLCV data

        Returns:
            Series with VPT values
        """
        if not all(col in data.columns for col in ['close', 'volume']):
            raise ValueError("VPT requires 'close' and 'volume' columns")

        # Calculate price change percentage
        price_change = data['close'].pct_change()

        # Calculate VPT: cumulative sum of (price_change * volume)
        vpt = (price_change * data['volume']).cumsum()

        # Fill NaN with 0 for the first value
        vpt = vpt.fillna(0)

        vpt.name = 'vpt'
        return vpt


class VolumeOscillator(Indicator):
    """
    Volume Oscillator Indicator.

    Shows the difference between fast and slow volume moving averages.
    Positive values indicate increasing volume, negative values indicate decreasing volume.

    Parameters:
        fast_period: Fast EMA period for volume (default: 5)
        slow_period: Slow EMA period for volume (default: 10)
    """

    def __init__(self, fast_period: int = 5, slow_period: int = 10, **kwargs):
        """Initialize Volume Oscillator indicator."""
        super().__init__(f"volume_oscillator_{fast_period}_{slow_period}", **kwargs)
        self.fast_period = fast_period
        self.slow_period = slow_period

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """
        Calculate Volume Oscillator.

        Args:
            data: DataFrame with volume data

        Returns:
            Series with volume oscillator values
        """
        if 'volume' not in data.columns:
            raise ValueError("Volume Oscillator requires 'volume' column")

        # Calculate fast and slow volume EMAs
        fast_ema = data['volume'].ewm(span=self.fast_period, adjust=False).mean()
        slow_ema = data['volume'].ewm(span=self.slow_period, adjust=False).mean()

        # Calculate oscillator
        oscillator = ((fast_ema - slow_ema) / slow_ema) * 100

        oscillator.name = f'volume_oscillator_{self.fast_period}_{self.slow_period}'
        return oscillator


class PriceVolumeTrend(Indicator):
    """
    Price Volume Trend (PVT) Indicator.

    Similar to VPT but uses typical price instead of close price.
    More responsive to price movements.

    Parameters:
        None
    """

    def __init__(self, **kwargs):
        """Initialize PVT indicator."""
        super().__init__("pvt", **kwargs)

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """
        Calculate Price Volume Trend.

        Args:
            data: DataFrame with OHLCV data

        Returns:
            Series with PVT values
        """
        if not all(col in data.columns for col in ['high', 'low', 'close', 'volume']):
            raise ValueError("PVT requires 'high', 'low', 'close', and 'volume' columns")

        # Calculate typical price
        typical_price = (data['high'] + data['low'] + data['close']) / 3

        # Calculate price change percentage
        price_change = typical_price.pct_change()

        # Calculate PVT: cumulative sum of (price_change * volume)
        pvt = (price_change * data['volume']).cumsum()

        # Fill NaN with 0 for the first value
        pvt = pvt.fillna(0)

        pvt.name = 'pvt'
        return pvt



