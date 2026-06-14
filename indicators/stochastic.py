"""
Stochastic Oscillator Indicator

Momentum indicator comparing closing price to price range over time.
Shows where price is relative to its high-low range.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any
from .base import Indicator


class Stochastic(Indicator):
    """
    Stochastic Oscillator indicator.
    
    Compares current close to the high-low range over a period.
    Oscillates between 0 and 100:
    - Above 80: Overbought
    - Below 20: Oversold
    
    Formula:
        %K = 100 * (Close - Lowest Low) / (Highest High - Lowest Low)
        %D = SMA(%K, d_period)
    """
    
    def __init__(self, k_period: int = 14, d_period: int = 3, smooth_k: int = 3, smooth: int = None, **kwargs):
        """
        Initialize Stochastic Oscillator indicator.

        Accepts legacy parameter names for compatibility:
          - smooth -> smooth_k
        Extra keyword args are ignored to be resilient to older configs.
        
        Args:
            k_period: Lookback period for %K calculation (default: 14)
            d_period: Smoothing period for %D signal line (default: 3)
            smooth_k: Smoothing period for %K line (default: 3)
            smooth: Legacy alias for smooth_k (optional)
        """
        # Backwards compatibility: prefer explicit smooth_k, but allow legacy 'smooth'
        if smooth is not None:
            smooth_k = smooth
        # Also accept camelCase legacy name if present
        if 'smoothK' in kwargs and kwargs.get('smoothK') is not None:
            smooth_k = kwargs.get('smoothK')

        super().__init__(
            name="Stochastic",
            params={
                'k_period': k_period,
                'd_period': d_period,
                'smooth_k': smooth_k
            }
        )
        self.k_period = k_period
        self.d_period = d_period
        self.smooth_k = smooth_k
        
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate Stochastic Oscillator.
        
        Args:
            data: DataFrame with OHLCV data
            
        Returns:
            DataFrame with 'stoch_k', 'stoch_d' columns
        """
        # Validate input
        min_periods = self.k_period + self.smooth_k + self.d_period
        self.validate_data(data, min_periods=min_periods)
        
        # Get high, low, close
        high = data['high']
        low = data['low']
        close = data['close']
        
        # Calculate rolling high and low
        lowest_low = low.rolling(window=self.k_period).min()
        highest_high = high.rolling(window=self.k_period).max()
        
        # Calculate raw %K
        raw_k = 100.0 * (close - lowest_low) / (highest_high - lowest_low)
        # Clamp to [0,100] to handle data where 'close' may exceed generated high/low in tests
        raw_k = raw_k.clip(lower=0.0, upper=100.0)
        
        # Smooth %K
        stoch_k = raw_k.rolling(window=self.smooth_k).mean()
        
        # Calculate %D (signal line)
        stoch_d = stoch_k.rolling(window=self.d_period).mean()
        
        # Handle division by zero
        stoch_k = stoch_k.fillna(50.0)
        stoch_d = stoch_d.fillna(50.0)
        
        # Create result DataFrame
        result = pd.DataFrame({
            'stoch_k': stoch_k,
            'stoch_d': stoch_d
        }, index=data.index)
        
        # Update state
        if len(result) > 0:
            self._state['latest_k'] = result['stoch_k'].iloc[-1]
            self._state['latest_d'] = result['stoch_d'].iloc[-1]
            
            k_value = result['stoch_k'].iloc[-1]
            d_value = result['stoch_d'].iloc[-1]
            
            # Determine overbought/oversold
            self._state['is_overbought'] = k_value > 80 and d_value > 80
            self._state['is_oversold'] = k_value < 20 and d_value < 20
            
            # Detect crossovers
            if len(result) > 1:
                prev_diff = result['stoch_k'].iloc[-2] - result['stoch_d'].iloc[-2]
                curr_diff = result['stoch_k'].iloc[-1] - result['stoch_d'].iloc[-1]
                
                self._state['bullish_crossover'] = prev_diff <= 0 and curr_diff > 0
                self._state['bearish_crossover'] = prev_diff >= 0 and curr_diff < 0
            else:
                self._state['bullish_crossover'] = False
                self._state['bearish_crossover'] = False
                
        self.update_calculation_time()
        
        return result
        
    def is_overbought(self, threshold: float = 80.0) -> bool:
        """
        Check if both %K and %D are above overbought threshold.
        
        Args:
            threshold: Overbought threshold (default: 80)
            
        Returns:
            True if overbought
        """
        k_value = self._state.get('latest_k')
        d_value = self._state.get('latest_d')
        
        if k_value is None or d_value is None:
            return False
            
        return k_value > threshold and d_value > threshold
        
    def is_oversold(self, threshold: float = 20.0) -> bool:
        """
        Check if both %K and %D are below oversold threshold.
        
        Args:
            threshold: Oversold threshold (default: 20)
            
        Returns:
            True if oversold
        """
        k_value = self._state.get('latest_k')
        d_value = self._state.get('latest_d')
        
        if k_value is None or d_value is None:
            return False
            
        return k_value < threshold and d_value < threshold
        
    def is_bullish_crossover(self) -> bool:
        """
        Check if %K crossed above %D (bullish signal).
        
        Returns:
            True if bullish crossover occurred
        """
        return self._state.get('bullish_crossover', False)
        
    def is_bearish_crossover(self) -> bool:
        """
        Check if %K crossed below %D (bearish signal).
        
        Returns:
            True if bearish crossover occurred
        """
        return self._state.get('bearish_crossover', False)
        
    def get_signal(self) -> str:
        """
        Get trading signal based on Stochastic levels and crossovers.
        
        Returns:
            'BUY' if oversold or bullish crossover in oversold zone
            'SELL' if overbought or bearish crossover in overbought zone
            'NEUTRAL' otherwise
        """
        k_value = self._state.get('latest_k')
        
        if k_value is None:
            return 'NEUTRAL'

        # Strong signals: crossovers in extreme zones
        if self.is_bullish_crossover() and k_value < 30:
            return 'BUY'
        elif self.is_bearish_crossover() and k_value > 70:
            return 'SELL'
        # Basic signals: extreme levels
        elif self.is_oversold():
            return 'BUY'
        elif self.is_overbought():
            return 'SELL'
        else:
            return 'NEUTRAL'


# Backwards-compatible wrapper
def calculate_stochastic(data: pd.DataFrame, k_period: int = 14, d_period: int = 3, smooth_k: int = 3):
    inst = Stochastic(k_period=k_period, d_period=d_period, smooth_k=smooth_k)
    res = inst.calculate(data)
    return res['stoch_k'], res['stoch_d']
            




