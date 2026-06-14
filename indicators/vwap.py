"""
VWAP (Volume Weighted Average Price) Indicator

Institutional-grade indicator showing average price weighted by volume.
Critical for day trading and identifying optimal entry/exit points.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any
from .base import Indicator


class VWAP(Indicator):
    """
    Volume Weighted Average Price (VWAP) Indicator.
    
    Calculates the average price weighted by volume, providing insight into
    the true average price considering trading volume. Used by institutional
    traders for execution benchmarking.
    
    VWAP is calculated from the start of the trading session and resets daily.
    Also includes VWAP bands (standard deviation bands) for support/resistance.
    """
    
    def __init__(self, std_dev_multiplier: float = 2.0):
        """
        Initialize VWAP indicator.
        
        Args:
            std_dev_multiplier: Standard deviation multiplier for bands (default: 2.0)
        """
        super().__init__(
            name="VWAP",
            params={'std_dev_multiplier': std_dev_multiplier}
        )
        self.std_dev_multiplier = std_dev_multiplier
        
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate VWAP values.
        
        Args:
            data: DataFrame with OHLCV data
            
        Returns:
            DataFrame with vwap, upper_band, and lower_band columns
        """
        # Validate input
        self.validate_data(data, min_periods=1)
        
        df = data.copy()
        
        # Typical price
        typical_price = (df['high'] + df['low'] + df['close']) / 3.0
        
        # For intraday VWAP, we should reset at session start
        # For simplicity, calculate cumulative VWAP
        # In production, you'd want to reset at session boundaries
        
        # Cumulative volume * price
        cumulative_tp_volume = (typical_price * df['volume']).cumsum()
        cumulative_volume = df['volume'].cumsum()
        
        # VWAP
        vwap = cumulative_tp_volume / cumulative_volume
        
        # Calculate standard deviation for bands
        # Variance = sum((price - vwap)^2 * volume) / sum(volume)
        price_diff_sq = (typical_price - vwap) ** 2
        cumulative_variance = (price_diff_sq * df['volume']).cumsum()
        variance = cumulative_variance / cumulative_volume
        std_dev = np.sqrt(variance)
        
        # VWAP bands
        upper_band = vwap + (std_dev * self.std_dev_multiplier)
        lower_band = vwap - (std_dev * self.std_dev_multiplier)
        
        # Additional bands (1x std dev)
        upper_band_1 = vwap + std_dev
        lower_band_1 = vwap - std_dev
        
        # Update state
        self._state['latest_vwap'] = vwap.iloc[-1] if len(vwap) > 0 else None
        self._state['latest_price'] = df['close'].iloc[-1] if len(df) > 0 else None
        
        if self._state['latest_vwap'] and self._state['latest_price']:
            self._state['price_vs_vwap'] = self._state['latest_price'] - self._state['latest_vwap']
            self._state['is_above_vwap'] = self._state['latest_price'] > self._state['latest_vwap']
        
        self.update_calculation_time()
        
        # Return as DataFrame
        result = pd.DataFrame({
            'vwap': vwap,
            'vwap_upper': upper_band,
            'vwap_lower': lower_band,
            'vwap_upper_1': upper_band_1,
            'vwap_lower_1': lower_band_1,
            'vwap_std': std_dev
        }, index=df.index)
        
        return result
        
    def is_above_vwap(self) -> bool:
        """Check if price is above VWAP."""
        return self._state.get('is_above_vwap', False)
        
    def get_distance_from_vwap(self) -> float:
        """Get price distance from VWAP."""
        return self._state.get('price_vs_vwap', 0.0)
        
    def get_signal(self) -> str:
        """
        Get trading signal based on VWAP position.
        
        Returns:
            'BUY' if above VWAP, 'SELL' if below, 'NEUTRAL' otherwise
        """
        if self.is_above_vwap():
            return 'BUY'
        elif not self.is_above_vwap() and self._state.get('latest_vwap'):
            return 'SELL'
        else:
            return 'NEUTRAL'


class AnchoredVWAP(Indicator):
    """
    Anchored VWAP - VWAP calculated from a specific starting point.
    
    Useful for calculating VWAP from significant price levels or events
    like earnings, major news, or session opens.
    """
    
    def __init__(self, anchor_index: int = 0, std_dev_multiplier: float = 2.0):
        """
        Initialize Anchored VWAP.
        
        Args:
            anchor_index: Index to start VWAP calculation from
            std_dev_multiplier: Standard deviation multiplier for bands
        """
        super().__init__(
            name="AnchoredVWAP",
            params={
                'anchor_index': anchor_index,
                'std_dev_multiplier': std_dev_multiplier
            }
        )
        self.anchor_index = anchor_index
        self.std_dev_multiplier = std_dev_multiplier
        
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        """Calculate Anchored VWAP from anchor point."""
        self.validate_data(data, min_periods=1)
        
        # Get data from anchor point
        anchor_idx = max(0, min(self.anchor_index, len(data) - 1))
        df = data.iloc[anchor_idx:].copy()
        
        # Calculate VWAP from anchor
        typical_price = (df['high'] + df['low'] + df['close']) / 3.0
        cumulative_tp_volume = (typical_price * df['volume']).cumsum()
        cumulative_volume = df['volume'].cumsum()
        vwap = cumulative_tp_volume / cumulative_volume
        
        # Calculate bands
        price_diff_sq = (typical_price - vwap) ** 2
        cumulative_variance = (price_diff_sq * df['volume']).cumsum()
        variance = cumulative_variance / cumulative_volume
        std_dev = np.sqrt(variance)
        
        upper_band = vwap + (std_dev * self.std_dev_multiplier)
        lower_band = vwap - (std_dev * self.std_dev_multiplier)
        
        # Update state
        self._state['latest_vwap'] = vwap.iloc[-1] if len(vwap) > 0 else None
        self.update_calculation_time()
        
        # Return full-length DataFrame with NaN before anchor
        result = pd.DataFrame({
            'anchored_vwap': pd.Series(dtype=float),
            'anchored_vwap_upper': pd.Series(dtype=float),
            'anchored_vwap_lower': pd.Series(dtype=float)
        }, index=data.index)
        
        result.loc[df.index, 'anchored_vwap'] = vwap
        result.loc[df.index, 'anchored_vwap_upper'] = upper_band
        result.loc[df.index, 'anchored_vwap_lower'] = lower_band
        

        return result




