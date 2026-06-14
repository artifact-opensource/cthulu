"""
ML Feature Pipeline - Robust Feature Engineering for Model Training

This module provides a comprehensive feature engineering pipeline for
Cthulu's ML models. It extracts, normalizes, and validates features
from market data for training and inference.

Features Categories:
1. Price Momentum (multi-timeframe)
2. Volatility (ATR, Bollinger bands)
3. Volume Profile
4. Market Structure (swing points, S/R)
5. Technical Indicators (RSI, MACD, ADX)
6. Time-based Features (session, day of week)
7. Regime Features (trend strength, choppiness)

Part of Cthulu ML Pipeline v6.0.0
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone
from enum import Enum
import logging
import json
import os

logger = logging.getLogger("cthulu.ml.feature_pipeline")

# Feature configuration
FEATURE_CONFIG = {
    # Momentum features
    "momentum_periods": [5, 10, 20, 50],
    # Volatility features
    "atr_period": 14,
    "bb_period": 20,
    "bb_std": 2.0,
    # Volume features
    "volume_ma_periods": [5, 10, 20],
    # Structure features
    "swing_lookback": 20,
    # Indicator features
    "rsi_period": 14,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "adx_period": 14,
}


class FeatureCategory(Enum):
    """Feature category classification."""
    MOMENTUM = "momentum"
    VOLATILITY = "volatility"
    VOLUME = "volume"
    STRUCTURE = "structure"
    INDICATOR = "indicator"
    TIME = "time"
    REGIME = "regime"


@dataclass
class FeatureSpec:
    """Specification for a single feature."""
    name: str
    category: FeatureCategory
    description: str
    min_lookback: int
    normalizer: str = "zscore"  # zscore, minmax, none


@dataclass
class FeatureSet:
    """Complete set of extracted features."""
    features: np.ndarray
    feature_names: List[str]
    feature_specs: List[FeatureSpec]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    valid: bool = True
    errors: List[str] = field(default_factory=list)
    
    @property
    def shape(self) -> Tuple[int, ...]:
        return self.features.shape
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary of feature name -> value."""
        return {name: float(self.features[i]) for i, name in enumerate(self.feature_names)}


class FeaturePipeline:
    """
    Robust feature engineering pipeline for ML model training.
    
    Usage:
        pipeline = FeaturePipeline()
        features = pipeline.extract(market_data)
        X = features.features  # numpy array
        
        # For training data:
        X_train, y_train, feature_names = pipeline.prepare_training_data(
            df=historical_data,
            target_horizon=5,
            target_threshold=0.1
        )
    """
    
    # Feature specifications
    FEATURE_SPECS: List[FeatureSpec] = [
        # Momentum features (4)
        FeatureSpec("mom_5", FeatureCategory.MOMENTUM, "5-bar momentum %", 6),
        FeatureSpec("mom_10", FeatureCategory.MOMENTUM, "10-bar momentum %", 11),
        FeatureSpec("mom_20", FeatureCategory.MOMENTUM, "20-bar momentum %", 21),
        FeatureSpec("mom_50", FeatureCategory.MOMENTUM, "50-bar momentum %", 51),
        
        # Volatility features (4)
        FeatureSpec("atr_ratio", FeatureCategory.VOLATILITY, "ATR/price ratio", 15),
        FeatureSpec("bb_position", FeatureCategory.VOLATILITY, "Bollinger band position", 21),
        FeatureSpec("bb_width", FeatureCategory.VOLATILITY, "Bollinger band width", 21),
        FeatureSpec("range_position", FeatureCategory.VOLATILITY, "Position in 20-bar range", 21),
        
        # Volume features (3)
        FeatureSpec("vol_ratio_5_20", FeatureCategory.VOLUME, "Volume ratio 5/20 MA", 21),
        FeatureSpec("vol_trend", FeatureCategory.VOLUME, "Volume trend (10-bar slope)", 11),
        FeatureSpec("vol_spike", FeatureCategory.VOLUME, "Volume spike indicator", 21),
        
        # Structure features (3)
        FeatureSpec("higher_highs", FeatureCategory.STRUCTURE, "Count of higher highs", 21),
        FeatureSpec("lower_lows", FeatureCategory.STRUCTURE, "Count of lower lows", 21),
        FeatureSpec("swing_position", FeatureCategory.STRUCTURE, "Position relative to swings", 21),
        
        # Indicator features (6)
        FeatureSpec("rsi_norm", FeatureCategory.INDICATOR, "RSI normalized [-1, 1]", 15),
        FeatureSpec("rsi_slope", FeatureCategory.INDICATOR, "RSI 5-bar slope", 20),
        FeatureSpec("macd_norm", FeatureCategory.INDICATOR, "MACD normalized", 27),
        FeatureSpec("macd_hist", FeatureCategory.INDICATOR, "MACD histogram", 27),
        FeatureSpec("adx_norm", FeatureCategory.INDICATOR, "ADX normalized", 28),
        FeatureSpec("adx_direction", FeatureCategory.INDICATOR, "ADX direction (+DI - -DI)", 28),
        
        # Time features (3)
        FeatureSpec("hour_sin", FeatureCategory.TIME, "Hour of day (sin)", 1),
        FeatureSpec("hour_cos", FeatureCategory.TIME, "Hour of day (cos)", 1),
        FeatureSpec("day_of_week", FeatureCategory.TIME, "Day of week (normalized)", 1),
        
        # Regime features (3)
        FeatureSpec("trend_strength", FeatureCategory.REGIME, "Trend strength (ADX-based)", 28),
        FeatureSpec("choppiness", FeatureCategory.REGIME, "Choppiness index", 15),
        FeatureSpec("mean_reversion", FeatureCategory.REGIME, "Mean reversion score", 21),
        
        # Recent returns (5)
        FeatureSpec("ret_1", FeatureCategory.MOMENTUM, "1-bar return", 2),
        FeatureSpec("ret_2", FeatureCategory.MOMENTUM, "2-bar return", 3),
        FeatureSpec("ret_3", FeatureCategory.MOMENTUM, "3-bar return", 4),
        FeatureSpec("ret_4", FeatureCategory.MOMENTUM, "4-bar return", 5),
        FeatureSpec("ret_5", FeatureCategory.MOMENTUM, "5-bar return", 6),
    ]
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize feature pipeline."""
        self.config = {**FEATURE_CONFIG, **(config or {})}
        self.min_lookback = max(spec.min_lookback for spec in self.FEATURE_SPECS)
        
        # Normalization parameters (fitted during training)
        self._means: Optional[np.ndarray] = None
        self._stds: Optional[np.ndarray] = None
        self._fitted = False
        
        logger.info(f"FeaturePipeline initialized: {len(self.FEATURE_SPECS)} features, min_lookback={self.min_lookback}")
    
    @property
    def feature_names(self) -> List[str]:
        """Get list of feature names."""
        return [spec.name for spec in self.FEATURE_SPECS]
    
    @property
    def feature_count(self) -> int:
        """Get total number of features."""
        return len(self.FEATURE_SPECS)
    
    def extract(self, df: pd.DataFrame) -> FeatureSet:
        """
        Extract features from market data.
        
        Args:
            df: DataFrame with OHLCV columns (open, high, low, close, volume)
            
        Returns:
            FeatureSet with extracted features
        """
        errors = []
        
        if len(df) < self.min_lookback:
            return FeatureSet(
                features=np.zeros(self.feature_count),
                feature_names=self.feature_names,
                feature_specs=self.FEATURE_SPECS,
                valid=False,
                errors=[f"Insufficient data: {len(df)} < {self.min_lookback}"]
            )
        
        try:
            features = []
            
            # Get arrays
            close = df['close'].values
            high = df['high'].values
            low = df['low'].values
            open_price = df['open'].values
            volume = df['volume'].values if 'volume' in df.columns else np.ones(len(close))
            
            # Time column
            if 'time' in df.columns:
                times = pd.to_datetime(df['time'])
            else:
                times = df.index if isinstance(df.index, pd.DatetimeIndex) else None
            
            # === MOMENTUM FEATURES ===
            for period in self.config["momentum_periods"]:
                if len(close) >= period + 1:
                    mom = (close[-1] - close[-period-1]) / (close[-period-1] + 1e-10) * 100
                else:
                    mom = 0
                features.append(np.clip(mom, -10, 10))
            
            # === VOLATILITY FEATURES ===
            # ATR ratio
            atr = self._calculate_atr(high, low, close, self.config["atr_period"])
            atr_ratio = (atr / close[-1]) * 100 if close[-1] > 0 else 0
            features.append(np.clip(atr_ratio, 0, 10))
            
            # Bollinger band position
            bb_upper, bb_middle, bb_lower = self._calculate_bollinger(
                close, self.config["bb_period"], self.config["bb_std"]
            )
            bb_range = bb_upper - bb_lower
            bb_pos = (close[-1] - bb_lower) / (bb_range + 1e-10) if bb_range > 0 else 0.5
            bb_pos = (bb_pos - 0.5) * 2  # Normalize to [-1, 1]
            features.append(np.clip(bb_pos, -1.5, 1.5))
            
            # Bollinger band width
            bb_width = bb_range / (bb_middle + 1e-10) * 100
            features.append(np.clip(bb_width, 0, 20))
            
            # Range position
            high_20 = np.max(high[-20:]) if len(high) >= 20 else high[-1]
            low_20 = np.min(low[-20:]) if len(low) >= 20 else low[-1]
            range_pos = (close[-1] - low_20) / (high_20 - low_20 + 1e-10)
            range_pos = (range_pos - 0.5) * 2
            features.append(np.clip(range_pos, -1.5, 1.5))
            
            # === VOLUME FEATURES ===
            vol_ma_5 = np.mean(volume[-5:]) if len(volume) >= 5 else volume[-1]
            vol_ma_20 = np.mean(volume[-20:]) if len(volume) >= 20 else volume[-1]
            vol_ratio = (vol_ma_5 / (vol_ma_20 + 1e-10)) - 1
            features.append(np.clip(vol_ratio, -2, 2))
            
            # Volume trend
            if len(volume) >= 10:
                vol_trend = np.polyfit(range(10), volume[-10:], 1)[0]
                vol_trend_norm = vol_trend / (vol_ma_20 + 1e-10)
            else:
                vol_trend_norm = 0
            features.append(np.clip(vol_trend_norm, -1, 1))
            
            # Volume spike
            vol_spike = (volume[-1] / (vol_ma_20 + 1e-10)) - 1
            features.append(np.clip(vol_spike, -1, 5))
            
            # === STRUCTURE FEATURES ===
            higher_highs, lower_lows = self._count_structure(high, low, 20)
            features.append(higher_highs / 10)  # Normalize
            features.append(lower_lows / 10)
            
            # Swing position
            swing_high, swing_low = self._find_swings(high, low, 20)
            swing_range = swing_high - swing_low
            swing_pos = (close[-1] - swing_low) / (swing_range + 1e-10)
            swing_pos = (swing_pos - 0.5) * 2
            features.append(np.clip(swing_pos, -1.5, 1.5))
            
            # === INDICATOR FEATURES ===
            # RSI
            rsi = self._calculate_rsi(close, self.config["rsi_period"])
            rsi_norm = (rsi - 50) / 50
            features.append(np.clip(rsi_norm, -1, 1))
            
            # RSI slope
            rsi_history = [self._calculate_rsi(close[:-i] if i > 0 else close, 14) for i in range(5)]
            rsi_slope = (rsi_history[0] - rsi_history[-1]) / 5 / 10  # Normalize
            features.append(np.clip(rsi_slope, -1, 1))
            
            # MACD
            macd_line, signal_line, macd_hist = self._calculate_macd(
                close,
                self.config["macd_fast"],
                self.config["macd_slow"],
                self.config["macd_signal"]
            )
            macd_norm = macd_line / (close[-1] + 1e-10) * 100
            features.append(np.clip(macd_norm, -2, 2))
            features.append(np.clip(macd_hist / (close[-1] + 1e-10) * 100, -2, 2))
            
            # ADX
            adx, plus_di, minus_di = self._calculate_adx(high, low, close, self.config["adx_period"])
            adx_norm = (adx - 25) / 25  # Center at 25
            features.append(np.clip(adx_norm, -1, 1))
            features.append(np.clip((plus_di - minus_di) / 50, -1, 1))
            
            # === TIME FEATURES ===
            if times is not None:
                hour = times.iloc[-1].hour
                day = times.iloc[-1].dayofweek
            else:
                hour = 12
                day = 2
            features.append(np.sin(2 * np.pi * hour / 24))
            features.append(np.cos(2 * np.pi * hour / 24))
            features.append((day - 2) / 2)  # Center at Wednesday
            
            # === REGIME FEATURES ===
            trend_strength = adx / 100  # Already calculated
            features.append(np.clip(trend_strength, 0, 1))
            
            # Choppiness index
            chop = self._calculate_choppiness(high, low, close, 14)
            chop_norm = (chop - 50) / 25
            features.append(np.clip(chop_norm, -1, 1))
            
            # Mean reversion score
            mean_rev = -bb_pos * rsi_norm  # High when oversold at low BB
            features.append(np.clip(mean_rev, -1, 1))
            
            # === RECENT RETURNS ===
            for i in range(1, 6):
                if len(close) > i:
                    ret = (close[-i] - close[-i-1]) / (close[-i-1] + 1e-10) * 100
                else:
                    ret = 0
                features.append(np.clip(ret, -5, 5))
            
            features_array = np.array(features, dtype=np.float32)
            
            # Apply normalization if fitted
            if self._fitted:
                features_array = self._normalize(features_array)
            
            return FeatureSet(
                features=features_array,
                feature_names=self.feature_names,
                feature_specs=self.FEATURE_SPECS,
                valid=True,
                errors=errors
            )
            
        except Exception as e:
            logger.error(f"Feature extraction error: {e}")
            return FeatureSet(
                features=np.zeros(self.feature_count),
                feature_names=self.feature_names,
                feature_specs=self.FEATURE_SPECS,
                valid=False,
                errors=[str(e)]
            )
    
    def prepare_training_data(
        self,
        df: pd.DataFrame,
        target_horizon: int = 5,
        target_threshold: float = 0.1
    ) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """
        Prepare training data from historical OHLCV.
        
        Args:
            df: Historical DataFrame
            target_horizon: Bars ahead to predict
            target_threshold: % move to classify as LONG/SHORT (vs NEUTRAL)
            
        Returns:
            X: Feature matrix (n_samples, n_features)
            y: Labels (n_samples, 3) - one-hot encoded [LONG, SHORT, NEUTRAL]
            feature_names: List of feature names
        """
        X = []
        y = []
        
        close = df['close'].values
        
        for i in range(self.min_lookback, len(df) - target_horizon):
            # Extract features at time i
            window = df.iloc[:i+1]
            feature_set = self.extract(window)
            
            if not feature_set.valid:
                continue
            
            X.append(feature_set.features)
            
            # Calculate target: future return
            future_return = (close[i + target_horizon] - close[i]) / (close[i] + 1e-10) * 100
            
            # Classify
            if future_return > target_threshold:
                label = [1, 0, 0]  # LONG
            elif future_return < -target_threshold:
                label = [0, 1, 0]  # SHORT
            else:
                label = [0, 0, 1]  # NEUTRAL
            
            y.append(label)
        
        X = np.array(X, dtype=np.float32)
        y = np.array(y, dtype=np.float32)
        
        # Fit normalizer on training data
        self._fit_normalizer(X)
        X = self._normalize(X)
        
        logger.info(f"Prepared training data: {len(X)} samples, {X.shape[1]} features")
        logger.info(f"Label distribution: LONG={np.sum(y[:,0])}, SHORT={np.sum(y[:,1])}, NEUTRAL={np.sum(y[:,2])}")
        
        return X, y, self.feature_names
    
    def _fit_normalizer(self, X: np.ndarray):
        """Fit normalization parameters."""
        self._means = np.mean(X, axis=0)
        self._stds = np.std(X, axis=0)
        self._stds[self._stds < 1e-10] = 1.0
        self._fitted = True
    
    def _normalize(self, X: np.ndarray) -> np.ndarray:
        """Apply normalization."""
        if not self._fitted:
            return X
        return (X - self._means) / (self._stds + 1e-10)
    
    # === TECHNICAL INDICATOR CALCULATIONS ===
    
    def _calculate_atr(self, high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> float:
        """Calculate Average True Range."""
        if len(close) < period + 1:
            return np.mean(high - low)
        
        high_slice = high[-period:]
        low_slice = low[-period:]
        prev_close = close[-period-1:-1]
        
        tr = np.maximum(
            high_slice - low_slice,
            np.maximum(
                np.abs(high_slice - prev_close),
                np.abs(low_slice - prev_close)
            )
        )
        return float(np.mean(tr))
    
    def _calculate_bollinger(self, close: np.ndarray, period: int, std_mult: float) -> Tuple[float, float, float]:
        """Calculate Bollinger Bands."""
        if len(close) < period:
            return close[-1], close[-1], close[-1]
        
        middle = np.mean(close[-period:])
        std = np.std(close[-period:])
        upper = middle + std_mult * std
        lower = middle - std_mult * std
        
        return upper, middle, lower
    
    def _calculate_rsi(self, close: np.ndarray, period: int) -> float:
        """Calculate RSI."""
        if len(close) < period + 1:
            return 50.0
        
        deltas = np.diff(close[-(period+1):])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def _calculate_macd(self, close: np.ndarray, fast: int, slow: int, signal: int) -> Tuple[float, float, float]:
        """Calculate MACD."""
        if len(close) < slow + signal:
            return 0.0, 0.0, 0.0
        
        ema_fast = self._ema(close, fast)
        ema_slow = self._ema(close, slow)
        macd_line = ema_fast - ema_slow
        
        # Calculate signal line from MACD history
        macd_history = []
        for i in range(signal):
            if len(close) - i > slow:
                ef = self._ema(close[:-i] if i > 0 else close, fast)
                es = self._ema(close[:-i] if i > 0 else close, slow)
                macd_history.append(ef - es)
        
        signal_line = np.mean(macd_history) if macd_history else macd_line
        histogram = macd_line - signal_line
        
        return float(macd_line), float(signal_line), float(histogram)
    
    def _ema(self, data: np.ndarray, period: int) -> float:
        """Calculate EMA."""
        if len(data) < period:
            return data[-1]
        
        multiplier = 2 / (period + 1)
        ema = data[-period]
        
        for price in data[-period+1:]:
            ema = (price - ema) * multiplier + ema
        
        return float(ema)
    
    def _calculate_adx(self, high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> Tuple[float, float, float]:
        """Calculate ADX with +DI and -DI."""
        if len(close) < period + 1:
            return 25.0, 25.0, 25.0
        
        # Calculate +DM and -DM
        high_diff = np.diff(high[-period-1:])
        low_diff = -np.diff(low[-period-1:])
        
        plus_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0)
        minus_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0)
        
        # ATR
        atr = self._calculate_atr(high, low, close, period)
        
        # +DI and -DI
        plus_di = 100 * np.mean(plus_dm) / (atr + 1e-10)
        minus_di = 100 * np.mean(minus_dm) / (atr + 1e-10)
        
        # DX and ADX
        di_diff = abs(plus_di - minus_di)
        di_sum = plus_di + minus_di
        dx = 100 * di_diff / (di_sum + 1e-10)
        
        return float(dx), float(plus_di), float(minus_di)
    
    def _calculate_choppiness(self, high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> float:
        """Calculate Choppiness Index."""
        if len(close) < period + 1:
            return 50.0
        
        atr_sum = sum(self._calculate_atr(high[:i], low[:i], close[:i], 1) 
                     for i in range(-period, 0))
        
        high_max = np.max(high[-period:])
        low_min = np.min(low[-period:])
        price_range = high_max - low_min
        
        if price_range == 0:
            return 50.0
        
        chop = 100 * np.log10(atr_sum / price_range) / np.log10(period)
        return float(np.clip(chop, 0, 100))
    
    def _count_structure(self, high: np.ndarray, low: np.ndarray, lookback: int) -> Tuple[int, int]:
        """Count higher highs and lower lows."""
        if len(high) < lookback:
            return 0, 0
        
        higher_highs = 0
        lower_lows = 0
        
        for i in range(-lookback + 1, 0):
            if high[i] > high[i-1]:
                higher_highs += 1
            if low[i] < low[i-1]:
                lower_lows += 1
        
        return higher_highs, lower_lows
    
    def _find_swings(self, high: np.ndarray, low: np.ndarray, lookback: int) -> Tuple[float, float]:
        """Find recent swing high and low."""
        if len(high) < lookback:
            return high[-1], low[-1]
        
        return float(np.max(high[-lookback:])), float(np.min(low[-lookback:]))
    
    def save(self, path: str):
        """Save pipeline state."""
        state = {
            "config": self.config,
            "means": self._means.tolist() if self._means is not None else None,
            "stds": self._stds.tolist() if self._stds is not None else None,
            "fitted": self._fitted
        }
        with open(path, 'w') as f:
            json.dump(state, f, indent=2)
        logger.info(f"Saved pipeline to {path}")
    
    def load(self, path: str):
        """Load pipeline state."""
        with open(path, 'r') as f:
            state = json.load(f)
        self.config = state["config"]
        self._means = np.array(state["means"]) if state["means"] else None
        self._stds = np.array(state["stds"]) if state["stds"] else None
        self._fitted = state["fitted"]
        logger.info(f"Loaded pipeline from {path}")


# Singleton instance
_feature_pipeline: Optional[FeaturePipeline] = None


def get_feature_pipeline(config: Optional[Dict[str, Any]] = None) -> FeaturePipeline:
    """Get or create singleton feature pipeline."""
    global _feature_pipeline
    if _feature_pipeline is None:
        _feature_pipeline = FeaturePipeline(config)
    return _feature_pipeline
