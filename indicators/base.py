"""
Base Indicator Module

Abstract base class for all technical indicators.
"""

import pandas as pd
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Union
from datetime import datetime


class Indicator(ABC):
    """
    Abstract base class for technical indicators.
    
    All indicators must inherit from this class and implement the calculate() method.
    Provides standardized interface for indicator calculation, state management, and reset.
    """
    
    def __init__(self, name: str, params: Dict[str, Any]):
        """
        Initialize indicator.
        
        Args:
            name: Indicator name
            params: Configuration parameters
        """
        self.name = name
        self.params = params
        self.logger = logging.getLogger(f"cthulu.indicators.{name}")
        self._state: Dict[str, Any] = {}
        self._last_calculation: datetime = None
        
    @abstractmethod
    def calculate(self, data: pd.DataFrame) -> Union[pd.Series, pd.DataFrame]:
        """
        Calculate indicator values from OHLCV data.
        
        Args:
            data: DataFrame with OHLCV columns (open, high, low, close, volume)
                 Must have datetime index
                 
        Returns:
            Series or DataFrame with indicator values, indexed by timestamp
            
        Raises:
            ValueError: If data format is invalid or insufficient
        """
        pass
        
    def validate_data(self, data: pd.DataFrame, min_periods: int = 1, required_cols: list | None = None):
        """
        Validate input data format and sufficiency.
        
        Args:
            data: DataFrame to validate
            min_periods: Minimum required data points
            
        Raises:
            ValueError: If validation fails
        """
        if data is None or data.empty:
            raise ValueError(f"{self.name}: Data is empty")
            
        # Default required columns are full OHLCV. Some indicators (e.g., RSI)
        # only need `close`, while others (ATR) need high/low/close. Allow
        # callers to specify `required_cols` to relax validation for fallback
        # calculation paths.
        if required_cols is None:
            required_cols = ['open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_cols if col not in data.columns]
        if missing_cols:
            raise ValueError(f"{self.name}: Missing required columns: {missing_cols}")
            
        if len(data) < min_periods:
            # Do not raise here; allow indicators to compute and return NaNs for short series.
            # Fallback paths rely on the presence of columns even when full period data isn't available.
            self.logger.debug(
                f"{self.name}: Insufficient data for full calculation. Required: {min_periods}, Got: {len(data)}"
            )
            
        if not isinstance(data.index, pd.DatetimeIndex):
            raise ValueError(f"{self.name}: Index must be DatetimeIndex")
            
    def reset(self):
        """Reset indicator internal state."""
        self._state.clear()
        self._last_calculation = None
        self.logger.debug(f"{self.name} state reset")
        
    def state(self) -> Dict[str, Any]:
        """
        Get current indicator state.
        
        Returns:
            Dictionary with indicator state and metadata
        """
        return {
            'name': self.name,
            'params': self.params,
            'last_calculation': self._last_calculation.isoformat() if self._last_calculation else None,
            'state': self._state.copy()
        }
        
    def update_calculation_time(self):
        """Update last calculation timestamp (ensure monotonic uniqueness)."""
        from datetime import timedelta
        new_ts = datetime.now()
        if self._last_calculation is not None and new_ts == self._last_calculation:
            new_ts = new_ts + timedelta(microseconds=1)
        self._last_calculation = new_ts
        
    def get_metadata(self) -> Dict[str, Any]:
        """
        Get indicator metadata for signal enrichment.
        
        Returns:
            Dictionary with indicator name, parameters, and calculation time
        """
        return {
            'indicator_name': self.name,
            'parameters': self.params,
            'calculation_timestamp': self._last_calculation.isoformat() if self._last_calculation else None
        }




