"""
Indicator Calculator Utility

Standalone utility for calculating technical indicators needed by trading strategies.
Used by backtesting, optimization, and live trading systems.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
import logging
from cthulu.indicators import RSI, MACD, BollingerBands, Stochastic, ADX, Supertrend, VWAP
from cthulu.indicators.atr import ATR

logger = logging.getLogger(__name__)


def calculate_basic_indicators(df: pd.DataFrame, strategies: List[Any] = None) -> pd.DataFrame:
    """
    Calculate basic technical indicators required by most strategies.
    
    Args:
        df: OHLCV DataFrame with columns: open, high, low, close, volume
        strategies: List of strategy instances to determine required indicators
        
    Returns:
        DataFrame with additional indicator columns
    """
    if df is None or len(df) < 50:
        logger.warning(f"Insufficient data for indicator calculation: {len(df) if df is not None else 0} bars")
        return df
    
    df = df.copy()
    
    try:
        # Calculate SMA indicators
        df = _calculate_sma_indicators(df, strategies)
        
        # Calculate EMA indicators  
        df = _calculate_ema_indicators(df, strategies)
        
        # Calculate ATR (required by most strategies)
        df = _calculate_atr(df)
        
        # Calculate additional technical indicators
        df = _calculate_technical_indicators(df)
        
        logger.debug(f"Successfully calculated indicators. Columns: {list(df.columns)}")
        return df
        
    except Exception as e:
        logger.error(f"Error calculating indicators: {e}", exc_info=True)
        return df


def _calculate_sma_indicators(df: pd.DataFrame, strategies: List[Any] = None) -> pd.DataFrame:
    """Calculate SMA indicators based on strategy requirements."""
    sma_periods = set()
    
    # Collect required SMA periods from strategies
    if strategies:
        for strategy in strategies:
            # Check for SMA crossover strategy attributes
            if hasattr(strategy, 'short_window') and hasattr(strategy, 'long_window'):
                try:
                    sma_periods.add(int(strategy.short_window))
                    sma_periods.add(int(strategy.long_window))
                except (ValueError, TypeError):
                    pass
            
            # Check for fast/slow periods that might be SMAs
            if hasattr(strategy, 'fast_period') and hasattr(strategy, 'slow_period'):
                # Only add if this looks like an SMA strategy
                if 'sma' in str(type(strategy)).lower():
                    try:
                        sma_periods.add(int(strategy.fast_period))
                        sma_periods.add(int(strategy.slow_period))
                    except (ValueError, TypeError):
                        pass
    
    # Add common SMA periods
    sma_periods.update([10, 20, 50])  # Common periods used in optimizer
    
    # Calculate SMAs
    for period in sorted(sma_periods):
        if period > 0 and period <= len(df):
            df[f'sma_{period}'] = df['close'].rolling(window=period, min_periods=1).mean()
            logger.debug(f"Calculated SMA_{period}")
    
    return df


def _calculate_ema_indicators(df: pd.DataFrame, strategies: List[Any] = None) -> pd.DataFrame:
    """Calculate EMA indicators based on strategy requirements."""
    ema_periods = set()
    
    # Collect required EMA periods from strategies
    if strategies:
        for strategy in strategies:
            # Check for EMA-specific attributes
            if hasattr(strategy, 'fast_period') and hasattr(strategy, 'slow_period'):
                if 'ema' in str(type(strategy)).lower():
                    try:
                        ema_periods.add(int(strategy.fast_period))
                        ema_periods.add(int(strategy.slow_period))
                    except (ValueError, TypeError):
                        pass
            
            # Check for explicit EMA attributes
            for attr in ['fast_ema', 'slow_ema']:
                if hasattr(strategy, attr):
                    try:
                        ema_periods.add(int(getattr(strategy, attr)))
                    except (ValueError, TypeError):
                        pass
    
    # Add common EMA periods
    ema_periods.update([5, 10, 12, 26])  # Common periods
    
    # Calculate EMAs
    for period in sorted(ema_periods):
        if period > 0 and period <= len(df):
            df[f'ema_{period}'] = df['close'].ewm(span=period, adjust=False).mean()
            logger.debug(f"Calculated EMA_{period}")
    
    return df


def _calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Calculate Average True Range."""
    try:
        # Calculate True Range
        df['prev_close'] = df['close'].shift(1)
        df['tr1'] = df['high'] - df['low']
        df['tr2'] = abs(df['high'] - df['prev_close'])
        df['tr3'] = abs(df['low'] - df['prev_close'])
        
        df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
        df['atr'] = df['tr'].rolling(window=period, min_periods=1).mean()
        
        # Clean up intermediate columns
        df = df.drop(['prev_close', 'tr1', 'tr2', 'tr3', 'tr'], axis=1)
        
        logger.debug(f"Calculated ATR with period {period}")
        
    except Exception as e:
        logger.error(f"Error calculating ATR: {e}")
    
    return df


def _calculate_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate additional technical indicators."""
    try:
        # RSI
        rsi_indicator = RSI(period=14)
        rsi_data = rsi_indicator.calculate(df)
        if rsi_data is not None:
            df['rsi'] = rsi_data
            logger.debug("Calculated RSI")
        
        # MACD  
        macd_indicator = MACD(fast=12, slow=26, signal=9)
        macd_data = macd_indicator.calculate(df)
        if macd_data is not None:
            if isinstance(macd_data, pd.DataFrame):
                for col in macd_data.columns:
                    df[col] = macd_data[col]
            else:
                df['macd'] = macd_data
            logger.debug("Calculated MACD")
        
        # Bollinger Bands
        bb_indicator = BollingerBands(period=20, std_dev=2)
        bb_data = bb_indicator.calculate(df)
        if bb_data is not None:
            if isinstance(bb_data, pd.DataFrame):
                for col in bb_data.columns:
                    df[col] = bb_data[col]
            logger.debug("Calculated Bollinger Bands")
        
        # Stochastic
        stoch_indicator = Stochastic(k_period=14, d_period=3)
        stoch_data = stoch_indicator.calculate(df)
        if stoch_data is not None:
            if isinstance(stoch_data, pd.DataFrame):
                for col in stoch_data.columns:
                    df[col] = stoch_data[col]
            logger.debug("Calculated Stochastic")
        
        # ADX
        adx_indicator = ADX(period=14)
        adx_data = adx_indicator.calculate(df)
        if adx_data is not None:
            if isinstance(adx_data, pd.DataFrame):
                for col in adx_data.columns:
                    df[col] = adx_data[col]
            else:
                df['adx'] = adx_data
            logger.debug("Calculated ADX")
            
    except Exception as e:
        logger.error(f"Error calculating technical indicators: {e}")
    
    return df


def add_momentum_indicators(df: pd.DataFrame, lookback_period: int = 20) -> pd.DataFrame:
    """Add momentum and price level indicators."""
    try:
        # Price levels for momentum breakout
        df[f'high_{lookback_period}'] = df['high'].rolling(window=lookback_period, min_periods=1).max()
        df[f'low_{lookback_period}'] = df['low'].rolling(window=lookback_period, min_periods=1).min()
        
        # Volume analysis
        df[f'volume_avg_{lookback_period}'] = df['volume'].rolling(window=lookback_period, min_periods=1).mean()
        
        logger.debug(f"Added momentum indicators with lookback period {lookback_period}")
        
    except Exception as e:
        logger.error(f"Error calculating momentum indicators: {e}")
    
    return df


def validate_data_quality(df: pd.DataFrame) -> bool:
    """Validate that DataFrame has required data quality for trading."""
    if df is None or len(df) == 0:
        logger.error("DataFrame is None or empty")
        return False
    
    # Check required columns
    required_cols = ['open', 'high', 'low', 'close', 'volume']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        logger.error(f"Missing required columns: {missing_cols}")
        return False
    
    # Check for sufficient data
    if len(df) < 50:
        logger.warning(f"Insufficient data: {len(df)} bars (minimum 50 recommended)")
        return False
    
    # Check for NaN values in OHLCV
    ohlcv_cols = ['open', 'high', 'low', 'close', 'volume']
    nan_counts = df[ohlcv_cols].isnull().sum()
    if nan_counts.any():
        logger.warning(f"NaN values found in OHLCV data: {nan_counts[nan_counts > 0].to_dict()}")
    
    # Check for invalid OHLC relationships
    invalid_ohlc = (df['high'] < df['low']) | (df['high'] < df['close']) | (df['high'] < df['open']) | \
                   (df['low'] > df['close']) | (df['low'] > df['open']) | (df['close'] < 0)
    
    if invalid_ohlc.any():
        logger.warning(f"Found {invalid_ohlc.sum()} bars with invalid OHLC relationships")
    
    return True