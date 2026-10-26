"""Normalize and cache market rates used by the trading loop."""

from threading import RLock
from typing import Any, Optional

import pandas as pd


class DataLayer:
    def __init__(self, cache_enabled: bool = True):
        self.cache_enabled = cache_enabled
        self._cache: dict[str, pd.DataFrame] = {}
        self._lock = RLock()

    def normalize_rates(self, rates: Any, symbol: Optional[str] = None) -> pd.DataFrame:
        """Convert rates into a DataFrame indexed by bar time."""
        if isinstance(rates, pd.DataFrame):
            frame = rates.copy()
        else:
            frame = pd.DataFrame.from_records(rates)

        if "time" not in frame.columns:
            if isinstance(frame.index, pd.DatetimeIndex):
                frame["time"] = frame.index
            else:
                raise ValueError("Market rates must include a 'time' column or DatetimeIndex")

        frame["time"] = pd.to_datetime(frame["time"], errors="raise")
        if "volume" not in frame.columns and "tick_volume" in frame.columns:
            frame["volume"] = frame["tick_volume"]

        normalized = frame.set_index("time")
        if self.cache_enabled and symbol:
            with self._lock:
                self._cache[symbol] = normalized.copy()
        return normalized

    def get_cached_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """Return a copy of the latest normalized data for a symbol, if cached."""
        if not self.cache_enabled:
            return None
        with self._lock:
            frame = self._cache.get(symbol)
            return frame.copy() if frame is not None else None
