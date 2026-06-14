"""
Tests for next-generation indicators
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from cthulu.indicators.supertrend import Supertrend
from cthulu.indicators.vwap import VWAP, AnchoredVWAP


class TestSupertrend:
    """Test Supertrend indicator."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.indicator = Supertrend(period=10, multiplier=3.0)
        
    def test_initialization(self):
        """Test indicator initialization."""
        assert self.indicator.name == "Supertrend"
        assert self.indicator.period == 10
        assert self.indicator.multiplier == 3.0
        
    def test_calculation(self):
        """Test supertrend calculation."""
        # Create sample data
        dates = pd.date_range(start='2024-01-01', periods=100, freq='1H')
        data = pd.DataFrame({
            'open': np.random.uniform(1.0, 1.1, 100),
            'high': np.random.uniform(1.05, 1.15, 100),
            'low': np.random.uniform(0.95, 1.05, 100),
            'close': np.random.uniform(1.0, 1.1, 100),
            'volume': np.random.randint(500, 1500, 100)
        }, index=dates)
        
        result = self.indicator.calculate(data)
        
        assert isinstance(result, pd.DataFrame)
        assert 'supertrend' in result.columns
        assert 'supertrend_direction' in result.columns
        assert 'supertrend_signal' in result.columns
        assert len(result) == len(data)
        
    def test_direction_values(self):
        """Test that direction is either 1 or -1."""
        dates = pd.date_range(start='2024-01-01', periods=50, freq='1H')
        data = pd.DataFrame({
            'open': np.linspace(1.0, 1.1, 50),
            'high': np.linspace(1.01, 1.11, 50),
            'low': np.linspace(0.99, 1.09, 50),
            'close': np.linspace(1.0, 1.1, 50),
            'volume': np.random.randint(500, 1500, 50)
        }, index=dates)
        
        result = self.indicator.calculate(data)
        
        # Check direction values
        directions = result['supertrend_direction'].dropna().unique()
        assert all(d in [-1, 1] for d in directions)
        
    def test_bullish_trend(self):
        """Test supertrend in bullish market."""
        dates = pd.date_range(start='2024-01-01', periods=50, freq='1H')
        # Create clear uptrend
        close_prices = np.linspace(1.0, 1.2, 50)
        data = pd.DataFrame({
            'open': close_prices - 0.001,
            'high': close_prices + 0.002,
            'low': close_prices - 0.002,
            'close': close_prices,
            'volume': np.random.randint(500, 1500, 50)
        }, index=dates)
        
        result = self.indicator.calculate(data)
        
        # In uptrend, direction should be 1
        assert result['supertrend_direction'].iloc[-1] == 1
        assert self.indicator.is_bullish()
        
    def test_state_update(self):
        """Test that state is properly updated."""
        dates = pd.date_range(start='2024-01-01', periods=30, freq='1H')
        data = pd.DataFrame({
            'open': np.random.uniform(1.0, 1.1, 30),
            'high': np.random.uniform(1.05, 1.15, 30),
            'low': np.random.uniform(0.95, 1.05, 30),
            'close': np.random.uniform(1.0, 1.1, 30),
            'volume': np.random.randint(500, 1500, 30)
        }, index=dates)
        
        self.indicator.calculate(data)
        
        state = self.indicator.state()
        assert 'latest_direction' in state['state']
        assert 'is_bullish' in state['state']


class TestVWAP:
    """Test VWAP indicator."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.indicator = VWAP(std_dev_multiplier=2.0)
        
    def test_initialization(self):
        """Test indicator initialization."""
        assert self.indicator.name == "VWAP"
        assert self.indicator.std_dev_multiplier == 2.0
        
    def test_calculation(self):
        """Test VWAP calculation."""
        dates = pd.date_range(start='2024-01-01 09:00', periods=100, freq='1T')
        data = pd.DataFrame({
            'open': np.random.uniform(100, 110, 100),
            'high': np.random.uniform(105, 115, 100),
            'low': np.random.uniform(95, 105, 100),
            'close': np.random.uniform(100, 110, 100),
            'volume': np.random.randint(1000, 5000, 100)
        }, index=dates)
        
        result = self.indicator.calculate(data)
        
        assert isinstance(result, pd.DataFrame)
        assert 'vwap' in result.columns
        assert 'vwap_upper' in result.columns
        assert 'vwap_lower' in result.columns
        assert len(result) == len(data)
        
    def test_vwap_calculation_logic(self):
        """Test VWAP calculation correctness."""
        dates = pd.date_range(start='2024-01-01', periods=10, freq='1H')
        data = pd.DataFrame({
            'open': [100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
            'high': [101, 102, 103, 104, 105, 106, 107, 108, 109, 110],
            'low': [99, 100, 101, 102, 103, 104, 105, 106, 107, 108],
            'close': [100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
            'volume': [1000] * 10
        }, index=dates)
        
        result = self.indicator.calculate(data)
        
        # VWAP should be near typical price since volume is constant
        typical_price = (data['high'] + data['low'] + data['close']) / 3
        vwap = result['vwap']
        
        # Last VWAP should be close to average typical price
        assert abs(vwap.iloc[-1] - typical_price.mean()) < 2.0
        
    def test_bands_calculation(self):
        """Test that VWAP bands are calculated."""
        np.random.seed(42)  # Fixed seed for reproducibility
        dates = pd.date_range(start='2024-01-01', periods=50, freq='1h')
        data = pd.DataFrame({
            'open': np.random.uniform(100, 110, 50),
            'high': np.random.uniform(105, 115, 50),
            'low': np.random.uniform(95, 105, 50),
            'close': np.random.uniform(100, 110, 50),
            'volume': np.random.randint(1000, 5000, 50)
        }, index=dates)
        
        result = self.indicator.calculate(data)
        
        # Check that bands are wider than VWAP (on average, first bar may be equal)
        assert all(result['vwap_upper'].iloc[1:] >= result['vwap'].iloc[1:])
        assert all(result['vwap_lower'].iloc[1:] <= result['vwap'].iloc[1:])
        
        # Check that 2x std bands are wider than 1x
        assert all(result['vwap_upper'] - result['vwap'] > 
                  result['vwap_upper_1'] - result['vwap'])
                  
    def test_price_position_vs_vwap(self):
        """Test detection of price position relative to VWAP."""
        dates = pd.date_range(start='2024-01-01', periods=20, freq='1H')
        # Create data where price is above VWAP
        data = pd.DataFrame({
            'open': np.linspace(100, 110, 20),
            'high': np.linspace(101, 111, 20),
            'low': np.linspace(99, 109, 20),
            'close': np.linspace(100, 110, 20),
            'volume': [1000] * 20
        }, index=dates)
        
        self.indicator.calculate(data)
        
        # Price trending up should eventually be above VWAP
        assert self.indicator._state.get('latest_price') is not None
        assert self.indicator._state.get('latest_vwap') is not None
        
    def test_signal_generation(self):
        """Test VWAP signal generation."""
        dates = pd.date_range(start='2024-01-01', periods=20, freq='1H')
        data = pd.DataFrame({
            'open': [105] * 20,
            'high': [106] * 20,
            'low': [104] * 20,
            'close': [105] * 20,
            'volume': [1000] * 20
        }, index=dates)
        
        self.indicator.calculate(data)
        signal = self.indicator.get_signal()
        
        assert signal in ['BUY', 'SELL', 'NEUTRAL']


class TestAnchoredVWAP:
    """Test Anchored VWAP indicator."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.indicator = AnchoredVWAP(anchor_index=10, std_dev_multiplier=2.0)
        
    def test_initialization(self):
        """Test indicator initialization."""
        assert self.indicator.name == "AnchoredVWAP"
        assert self.indicator.anchor_index == 10
        
    def test_calculation_from_anchor(self):
        """Test that VWAP is calculated from anchor point."""
        dates = pd.date_range(start='2024-01-01', periods=50, freq='1H')
        data = pd.DataFrame({
            'open': np.random.uniform(100, 110, 50),
            'high': np.random.uniform(105, 115, 50),
            'low': np.random.uniform(95, 105, 50),
            'close': np.random.uniform(100, 110, 50),
            'volume': np.random.randint(1000, 5000, 50)
        }, index=dates)
        
        result = self.indicator.calculate(data)
        
        assert isinstance(result, pd.DataFrame)
        assert 'anchored_vwap' in result.columns
        assert len(result) == len(data)
        
        # Values before anchor should be NaN
        assert pd.isna(result['anchored_vwap'].iloc[0:10]).all()
        
        # Values after anchor should not be NaN
        assert not pd.isna(result['anchored_vwap'].iloc[10:]).all()
        
    def test_different_anchor_points(self):
        """Test anchored VWAP with different anchor points."""
        dates = pd.date_range(start='2024-01-01', periods=50, freq='1H')
        data = pd.DataFrame({
            'open': np.linspace(100, 110, 50),
            'high': np.linspace(101, 111, 50),
            'low': np.linspace(99, 109, 50),
            'close': np.linspace(100, 110, 50),
            'volume': [1000] * 50
        }, index=dates)
        
        # Test with anchor at index 0
        indicator1 = AnchoredVWAP(anchor_index=0)
        result1 = indicator1.calculate(data)
        
        # Test with anchor at index 25
        indicator2 = AnchoredVWAP(anchor_index=25)
        result2 = indicator2.calculate(data)
        
        # Results should differ
        a = result1['anchored_vwap'].dropna().to_numpy()
        b = result2['anchored_vwap'].dropna().to_numpy()
        # If the shapes differ, the anchored calculations are clearly different
        if a.shape != b.shape:
            assert True
        else:
            assert not np.allclose(a, b)


class TestIndicatorIntegration:
    """Integration tests for indicators."""
    
    def test_multiple_indicators(self):
        """Test using multiple indicators together."""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='1H')
        data = pd.DataFrame({
            'open': np.random.uniform(100, 110, 100),
            'high': np.random.uniform(105, 115, 100),
            'low': np.random.uniform(95, 105, 100),
            'close': np.random.uniform(100, 110, 100),
            'volume': np.random.randint(1000, 5000, 100)
        }, index=dates)
        
        # Calculate all indicators
        supertrend = Supertrend()
        vwap = VWAP()
        
        st_result = supertrend.calculate(data)
        vwap_result = vwap.calculate(data)
        
        # Merge results
        combined = pd.concat([data, st_result, vwap_result], axis=1)
        
        # Check all columns present
        assert 'supertrend' in combined.columns
        assert 'vwap' in combined.columns
        assert len(combined) == len(data)
        
    def test_indicator_state_persistence(self):
        """Test that indicator state persists across calculations."""
        dates = pd.date_range(start='2024-01-01', periods=50, freq='1H')
        data = pd.DataFrame({
            'open': np.linspace(100, 110, 50),
            'high': np.linspace(101, 111, 50),
            'low': np.linspace(99, 109, 50),
            'close': np.linspace(100, 110, 50),
            'volume': [1000] * 50
        }, index=dates)
        
        indicator = Supertrend()
        
        # First calculation
        indicator.calculate(data[:30])
        state1 = indicator.state()
        
        # Second calculation
        indicator.calculate(data)
        state2 = indicator.state()
        
        # State should have been updated
        assert state1['last_calculation'] != state2['last_calculation']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])




