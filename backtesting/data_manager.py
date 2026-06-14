"""
Historical Data Manager

Handles fetching, caching, and managing historical market data for backtesting.
Supports multiple data sources including MT5, CSV files, and external APIs.
"""

import pandas as pd
import numpy as np
import logging
import pickle
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None


class DataSource(Enum):
    """Available data sources for historical data"""
    MT5 = "mt5"
    CSV = "csv"
    CACHE = "cache"
    EXTERNAL_API = "external_api"


@dataclass
class DataMetadata:
    """Metadata for historical data"""
    symbol: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    num_bars: int
    source: DataSource
    fetch_time: datetime
    data_quality_score: float = 1.0  # 0.0 to 1.0


class HistoricalDataManager:
    """
    Historical data manager for backtesting.
    
    Features:
    - Fetch data from MT5 or CSV files
    - Cache data locally for fast access
    - Data quality checks and cleaning
    - Support for multiple symbols and timeframes
    - Data alignment and resampling
    """
    
    def __init__(self, cache_dir: str | None = None):
        """
        Initialize data manager.
        
        Args:
            cache_dir: Directory for caching downloaded data; if None uses package default
        """
        from . import BACKTEST_CACHE_DIR
        self.logger = logging.getLogger("cthulu.backtesting.data")
        cache_dir_path = Path(cache_dir) if cache_dir else Path(BACKTEST_CACHE_DIR)
        self.cache_dir = cache_dir_path
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, Tuple[pd.DataFrame, DataMetadata]] = {}
        
    def fetch_data(
        self,
        symbol: str,
        start_date: str | datetime,
        end_date: str | datetime,
        timeframe: str = "H1",
        source: DataSource = DataSource.MT5,
        use_cache: bool = True
    ) -> Tuple[pd.DataFrame, DataMetadata]:
        """
        Fetch historical OHLCV data.
        
        Args:
            symbol: Trading symbol (e.g., 'EURUSD', 'BTCUSD#')
            start_date: Start date (ISO format string or datetime)
            end_date: End date (ISO format string or datetime)
            timeframe: Timeframe (M1, M5, M15, M30, H1, H4, D1, etc.)
            source: Data source to use
            use_cache: Use cached data if available
            
        Returns:
            Tuple of (DataFrame with OHLCV data, DataMetadata)
            
        Raises:
            ValueError: If data cannot be fetched
        """
        # Convert dates
        if isinstance(start_date, str):
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        if isinstance(end_date, str):
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            
        # Check cache first
        cache_key = f"{symbol}_{timeframe}_{start_date.date()}_{end_date.date()}"
        if use_cache and cache_key in self._cache:
            self.logger.info(f"Using cached data for {cache_key}")
            return self._cache[cache_key]
            
        # Try to load from disk cache
        cache_file = self.cache_dir / f"{cache_key}.pkl"
        if use_cache and cache_file.exists():
            try:
                with open(cache_file, 'rb') as f:
                    cached = pickle.load(f)
                    self._cache[cache_key] = cached
                    self.logger.info(f"Loaded data from disk cache: {cache_file}")
                    return cached
            except Exception as e:
                self.logger.warning(f"Failed to load cache file: {e}")
                
        # Fetch data based on source
        if source == DataSource.MT5:
            df, metadata = self._fetch_from_mt5(symbol, start_date, end_date, timeframe)
        elif source == DataSource.CSV:
            df, metadata = self._fetch_from_csv(symbol, start_date, end_date, timeframe)
        else:
            raise ValueError(f"Unsupported data source: {source}")
            
        # Quality checks
        df = self._clean_data(df)
        metadata.data_quality_score = self._calculate_quality_score(df)
        
        # Cache the data
        self._cache[cache_key] = (df, metadata)
        
        # Save to disk
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump((df, metadata), f)
            self.logger.info(f"Cached data to disk: {cache_file}")
        except Exception as e:
            self.logger.warning(f"Failed to cache data to disk: {e}")
            
        return df, metadata
        
    def _fetch_from_mt5(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str
    ) -> Tuple[pd.DataFrame, DataMetadata]:
        """Fetch data from MT5 terminal."""
        if mt5 is None:
            raise ImportError("MetaTrader5 not available")
            
        # Convert timeframe string to MT5 constant
        tf_map = {
            'M1': mt5.TIMEFRAME_M1,
            'M5': mt5.TIMEFRAME_M5,
            'M15': mt5.TIMEFRAME_M15,
            'M30': mt5.TIMEFRAME_M30,
            'H1': mt5.TIMEFRAME_H1,
            'H4': mt5.TIMEFRAME_H4,
            'D1': mt5.TIMEFRAME_D1,
            'W1': mt5.TIMEFRAME_W1,
            'MN1': mt5.TIMEFRAME_MN1,
        }
        mt5_timeframe = tf_map.get(timeframe)
        if mt5_timeframe is None:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
            
        # Initialize MT5 if not already connected
        if not mt5.initialize():
            raise ConnectionError(f"MT5 initialization failed: {mt5.last_error()}")
            
        # Fetch rates
        rates = mt5.copy_rates_range(symbol, mt5_timeframe, start_date, end_date)
        
        if rates is None or len(rates) == 0:
            raise ValueError(f"No data returned from MT5 for {symbol} {timeframe}")
            
        # Convert to DataFrame
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        df = df[['open', 'high', 'low', 'close', 'tick_volume']]
        df.rename(columns={'tick_volume': 'volume'}, inplace=True)
        
        metadata = DataMetadata(
            symbol=symbol,
            timeframe=timeframe,
            start_date=df.index[0].to_pydatetime(),
            end_date=df.index[-1].to_pydatetime(),
            num_bars=len(df),
            source=DataSource.MT5,
            fetch_time=datetime.now()
        )
        
        self.logger.info(f"Fetched {len(df)} bars from MT5 for {symbol} {timeframe}")
        return df, metadata
        
    def _fetch_from_csv(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str
    ) -> Tuple[pd.DataFrame, DataMetadata]:
        """Fetch data from CSV file."""
        csv_path = self.cache_dir / f"{symbol}_{timeframe}.csv"
        
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")
            
        df = pd.read_csv(csv_path)
        
        # Detect time column
        time_cols = ['time', 'timestamp', 'date', 'datetime']
        time_col = next((col for col in time_cols if col in df.columns), None)
        if time_col is None:
            raise ValueError(f"No time column found in CSV. Expected one of: {time_cols}")
            
        df[time_col] = pd.to_datetime(df[time_col])
        df.set_index(time_col, inplace=True)
        
        # Filter by date range
        df = df[(df.index >= start_date) & (df.index <= end_date)]
        
        # Ensure required columns
        required = ['open', 'high', 'low', 'close', 'volume']
        for col in required:
            if col not in df.columns:
                raise ValueError(f"Missing required column '{col}' in CSV")
                
        df = df[required]
        
        metadata = DataMetadata(
            symbol=symbol,
            timeframe=timeframe,
            start_date=df.index[0].to_pydatetime(),
            end_date=df.index[-1].to_pydatetime(),
            num_bars=len(df),
            source=DataSource.CSV,
            fetch_time=datetime.now()
        )
        
        self.logger.info(f"Loaded {len(df)} bars from CSV for {symbol} {timeframe}")
        return df, metadata
        
    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean and validate data."""
        # Remove duplicates
        df = df[~df.index.duplicated(keep='first')]
        
        # Forward fill missing values (small gaps only)
        df = df.fillna(method='ffill', limit=3)
        
        # Drop rows with NaN after filling
        initial_len = len(df)
        df = df.dropna()
        if len(df) < initial_len:
            self.logger.warning(f"Dropped {initial_len - len(df)} rows with missing data")
            
        # Validate OHLC relationships
        invalid = (df['high'] < df['low']) | (df['high'] < df['close']) | (df['low'] > df['open'])
        if invalid.any():
            self.logger.warning(f"Found {invalid.sum()} bars with invalid OHLC relationships")
            df = df[~invalid]
            
        # Remove zero-volume bars (optional, depending on use case)
        zero_volume = df['volume'] == 0
        if zero_volume.any():
            self.logger.info(f"Found {zero_volume.sum()} zero-volume bars")
            
        return df
        
    def _calculate_quality_score(self, df: pd.DataFrame) -> float:
        """Calculate data quality score (0.0 to 1.0)."""
        if df.empty:
            return 0.0
            
        score = 1.0
        
        # Penalize for missing data
        missing_pct = df.isnull().sum().sum() / (len(df) * len(df.columns))
        score -= missing_pct * 0.5
        
        # Penalize for large gaps (more than 2x expected interval)
        time_diffs = df.index.to_series().diff()
        median_diff = time_diffs.median()
        large_gaps = (time_diffs > median_diff * 2).sum()
        gap_penalty = min(large_gaps / len(df) * 0.3, 0.3)
        score -= gap_penalty
        
        # Penalize for suspicious price movements (>20% in one bar)
        price_changes = df['close'].pct_change().abs()
        suspicious = (price_changes > 0.20).sum()
        score -= min(suspicious / len(df) * 0.2, 0.2)
        
        return max(0.0, min(1.0, score))
        
    def export_to_csv(self, symbol: str, timeframe: str, output_path: str) -> None:
        """Export cached data to CSV file."""
        # Find matching cache entry
        cache_key = next((k for k in self._cache.keys() if k.startswith(f"{symbol}_{timeframe}")), None)
        if cache_key is None:
            raise ValueError(f"No cached data found for {symbol} {timeframe}")
            
        df, metadata = self._cache[cache_key]
        df.to_csv(output_path)
        self.logger.info(f"Exported {len(df)} bars to {output_path}")
        
    def get_available_symbols(self) -> List[str]:
        """Get list of symbols available in cache."""
        symbols = set()
        for key in self._cache.keys():
            symbol = key.split('_')[0]
            symbols.add(symbol)
        return sorted(list(symbols))
