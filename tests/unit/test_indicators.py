"""
Unit tests for Phase 2 indicator library.
Tests RSI, MACD, Bollinger Bands, Stochastic, ADX, and ATR indicators.
"""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


class TestRSI(unittest.TestCase):
    """Test Relative Strength Index indicator."""
    
    def setUp(self):
        """Create sample OHLCV data."""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')
        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.randn(100) * 2)
        
        self.df = pd.DataFrame({
            'time': dates,
            'open': prices,
            'high': prices + np.random.rand(100) * 2,
            'low': prices - np.random.rand(100) * 2,
            'close': prices + np.random.randn(100),
            'volume': np.random.randint(1000, 10000, 100)
        })
        self.df.set_index('time', inplace=True)
    
    def test_rsi_import(self):
        """Test that RSI indicator can be imported."""
        try:
            from cthulu.indicators.rsi import calculate_rsi
            self.assertTrue(True)
        except ImportError:
            self.fail("Could not import calculate_rsi from indicators.rsi")
    
    def test_rsi_calculation(self):
        """Test RSI calculation returns valid values."""
        from cthulu.indicators.rsi import calculate_rsi
        
        rsi = calculate_rsi(self.df, period=14)
        
        # RSI should be between 0 and 100 (ignore NaN startup values)
        self.assertTrue((rsi.dropna() >= 0).all())
        self.assertTrue((rsi.dropna() <= 100).all())
        
        # First period-1 values should be NaN
        self.assertTrue(pd.isna(rsi.iloc[:13]).all())
        
        # Rest should be valid numbers
        self.assertTrue(pd.notna(rsi.iloc[14:]).all())
    
    def test_rsi_oversold_overbought(self):
        """Test RSI oversold/overbought detection."""
        from cthulu.indicators.rsi import calculate_rsi, is_oversold, is_overbought
        
        rsi = calculate_rsi(self.df, period=14)
        
        oversold = is_oversold(rsi, threshold=30)
        overbought = is_overbought(rsi, threshold=70)
        
        # Should return boolean series
        self.assertIsInstance(oversold, pd.Series)
        self.assertIsInstance(overbought, pd.Series)
        
        # Check that oversold and overbought are not both true
        self.assertFalse((oversold & overbought).any())


class TestMACD(unittest.TestCase):
    """Test MACD indicator."""
    
    def setUp(self):
        """Create sample OHLCV data."""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')
        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.randn(100) * 2)
        
        self.df = pd.DataFrame({
            'time': dates,
            'open': prices,
            'high': prices + np.random.rand(100) * 2,
            'low': prices - np.random.rand(100) * 2,
            'close': prices + np.random.randn(100),
            'volume': np.random.randint(1000, 10000, 100)
        })
        self.df.set_index('time', inplace=True)
    
    def test_macd_import(self):
        """Test that MACD indicator can be imported."""
        try:
            from cthulu.indicators.macd import calculate_macd
            self.assertTrue(True)
        except ImportError:
            self.fail("Could not import calculate_macd from indicators.macd")
    
    def test_macd_calculation(self):
        """Test MACD calculation returns MACD line, signal, and histogram."""
        from cthulu.indicators.macd import calculate_macd
        
        macd, signal, histogram = calculate_macd(self.df, fast=12, slow=26, signal_period=9)
        
        # All should be pandas Series
        self.assertIsInstance(macd, pd.Series)
        self.assertIsInstance(signal, pd.Series)
        self.assertIsInstance(histogram, pd.Series)
        
        # Histogram should be macd - signal
        pd.testing.assert_series_equal(histogram, macd - signal)
    
    def test_macd_crossover(self):
        """Test MACD crossover detection."""
        from cthulu.indicators.macd import calculate_macd, detect_crossover
        
        macd, signal, histogram = calculate_macd(self.df)
        
        bullish, bearish = detect_crossover(macd, signal)
        
        # Should return boolean series
        self.assertIsInstance(bullish, pd.Series)
        self.assertIsInstance(bearish, pd.Series)


class TestBollingerBands(unittest.TestCase):
    """Test Bollinger Bands indicator."""
    
    def setUp(self):
        """Create sample OHLCV data."""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')
        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.randn(100) * 2)
        
        self.df = pd.DataFrame({
            'time': dates,
            'open': prices,
            'high': prices + np.random.rand(100) * 2,
            'low': prices - np.random.rand(100) * 2,
            'close': prices + np.random.randn(100),
            'volume': np.random.randint(1000, 10000, 100)
        })
        self.df.set_index('time', inplace=True)
    
    def test_bollinger_import(self):
        """Test that Bollinger Bands can be imported."""
        try:
            from cthulu.indicators.bollinger import calculate_bollinger_bands
            self.assertTrue(True)
        except ImportError:
            self.fail("Could not import calculate_bollinger_bands from indicators.bollinger")
    
    def test_bollinger_calculation(self):
        """Test Bollinger Bands calculation."""
        from cthulu.indicators.bollinger import calculate_bollinger_bands
        
        upper, middle, lower = calculate_bollinger_bands(self.df, period=20, std_dev=2)
        
        # All should be pandas Series
        self.assertIsInstance(upper, pd.Series)
        self.assertIsInstance(middle, pd.Series)
        self.assertIsInstance(lower, pd.Series)
        
        # Upper should be > middle > lower
        self.assertTrue((upper >= middle).all())
        self.assertTrue((middle >= lower).all())
    
    def test_bollinger_squeeze(self):
        """Test Bollinger Bands squeeze detection."""
        from cthulu.indicators.bollinger import calculate_bollinger_bands, detect_squeeze
        
        upper, middle, lower = calculate_bollinger_bands(self.df)
        
        squeeze = detect_squeeze(upper, lower, threshold=0.02)
        
        # Should return boolean series
        self.assertIsInstance(squeeze, pd.Series)


class TestStochastic(unittest.TestCase):
    """Test Stochastic Oscillator indicator."""
    
    def setUp(self):
        """Create sample OHLCV data."""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')
        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.randn(100) * 2)
        
        self.df = pd.DataFrame({
            'time': dates,
            'open': prices,
            'high': prices + np.random.rand(100) * 2,
            'low': prices - np.random.rand(100) * 2,
            'close': prices + np.random.randn(100),
            'volume': np.random.randint(1000, 10000, 100)
        })
        self.df.set_index('time', inplace=True)
    
    def test_stochastic_import(self):
        """Test that Stochastic indicator can be imported."""
        try:
            from cthulu.indicators.stochastic import calculate_stochastic
            self.assertTrue(True)
        except ImportError:
            self.fail("Could not import calculate_stochastic from indicators.stochastic")
    
    def test_stochastic_calculation(self):
        """Test Stochastic calculation returns %K and %D."""
        from cthulu.indicators.stochastic import calculate_stochastic
        
        k, d = calculate_stochastic(self.df, k_period=14, d_period=3)
        
        # Both should be pandas Series
        self.assertIsInstance(k, pd.Series)
        self.assertIsInstance(d, pd.Series)
        
        # Values should be between 0 and 100
        self.assertTrue((k >= 0).all())
        self.assertTrue((k <= 100).all())
        self.assertTrue((d >= 0).all())
        self.assertTrue((d <= 100).all())


class TestADX(unittest.TestCase):
    """Test Average Directional Index indicator."""
    
    def setUp(self):
        """Create sample OHLCV data."""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')
        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.randn(100) * 2)
        
        self.df = pd.DataFrame({
            'time': dates,
            'open': prices,
            'high': prices + np.random.rand(100) * 2,
            'low': prices - np.random.rand(100) * 2,
            'close': prices + np.random.randn(100),
            'volume': np.random.randint(1000, 10000, 100)
        })
        self.df.set_index('time', inplace=True)
    
    def test_adx_import(self):
        """Test that ADX indicator can be imported."""
        try:
            from cthulu.indicators.adx import calculate_adx
            self.assertTrue(True)
        except ImportError:
            self.fail("Could not import calculate_adx from indicators.adx")
    
    def test_adx_calculation(self):
        """Test ADX calculation."""
        from cthulu.indicators.adx import calculate_adx
        
        adx = calculate_adx(self.df, period=14)
        
        # Should be pandas Series
        self.assertIsInstance(adx, pd.Series)
        
        # Values should be between 0 and 100
        self.assertTrue((adx >= 0).all())
        self.assertTrue((adx <= 100).all())
    
    def test_adx_trend_strength(self):
        """Test ADX trend strength classification."""
        from cthulu.indicators.adx import calculate_adx, is_strong_trend
        
        adx = calculate_adx(self.df)
        
        strong = is_strong_trend(adx, threshold=25)
        
        # Should return boolean series
        self.assertIsInstance(strong, pd.Series)


class TestATR(unittest.TestCase):
    """Test Average True Range indicator."""
    
    def setUp(self):
        """Create sample OHLCV data."""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')
        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.randn(100) * 2)
        
        self.df = pd.DataFrame({
            'time': dates,
            'open': prices,
            'high': prices + np.random.rand(100) * 2,
            'low': prices - np.random.rand(100) * 2,
            'close': prices + np.random.randn(100),
            'volume': np.random.randint(1000, 10000, 100)
        })
    
    def test_atr_import(self):
        """Test that ATR indicator can be imported."""
        try:
            from cthulu.indicators.atr import calculate_atr
            self.assertTrue(True)
        except ImportError:
            self.fail("Could not import calculate_atr from indicators.atr")
    
    def test_atr_calculation(self):
        """Test ATR calculation."""
        from cthulu.indicators.atr import calculate_atr
        
        atr = calculate_atr(self.df, period=14)
        
        # Should be pandas Series
        self.assertIsInstance(atr, pd.Series)
        
        # ATR should always be positive
        self.assertTrue((atr > 0).all())


if __name__ == '__main__':
    unittest.main()




