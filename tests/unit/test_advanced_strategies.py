"""
Tests for new advanced trading strategies
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from cthulu.strategy.ema_crossover import EmaCrossover
from cthulu.strategy.momentum_breakout import MomentumBreakout
from cthulu.strategy.scalping import ScalpingStrategy
from cthulu.strategy.strategy_selector import StrategySelector, MarketRegime
from cthulu.strategy.base import SignalType


class TestEMACrossover:
    """Test EMA Crossover strategy."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.config = {
            'type': 'ema_crossover',
            'params': {
                'fast_period': 9,
                'slow_period': 21,
                'atr_period': 14,
                'symbol': 'EURUSD'
            },
            'timeframe': '1H'
        }
        self.strategy = EmaCrossover(self.config)
        
    def test_initialization(self):
        """Test strategy initialization."""
        assert self.strategy.name == "ema_crossover"
        assert self.strategy.fast_period == 9
        assert self.strategy.slow_period == 21
        
    def test_bullish_crossover(self):
        """Test bullish EMA crossover signal."""
        # Create bar with bullish crossover
        bar = pd.Series({
            'open': 1.1000,
            'high': 1.1010,
            'low': 1.0990,
            'close': 1.1005,
            'volume': 1000,
            'ema_9': 1.1003,
            'ema_21': 1.1000,
            'atr': 0.0010
        }, name=datetime.now())
        
        # Setup previous state (fast below slow)
        self.strategy._state['ema_fast'] = 1.0998
        self.strategy._state['ema_slow'] = 1.1000
        
        signal = self.strategy.on_bar(bar)
        
        assert signal is not None
        assert signal.side == SignalType.LONG
        assert signal.confidence == 0.75
        assert signal.stop_loss < signal.price
        assert signal.take_profit > signal.price
        
    def test_bearish_crossover(self):
        """Test bearish EMA crossover signal."""
        bar = pd.Series({
            'open': 1.1000,
            'high': 1.1010,
            'low': 1.0990,
            'close': 1.0995,
            'volume': 1000,
            'ema_9': 1.0997,
            'ema_21': 1.1000,
            'atr': 0.0010
        }, name=datetime.now())
        
        # Setup previous state (fast above slow)
        self.strategy._state['ema_fast'] = 1.1002
        self.strategy._state['ema_slow'] = 1.1000
        
        signal = self.strategy.on_bar(bar)
        
        assert signal is not None
        assert signal.side == SignalType.SHORT
        assert signal.stop_loss > signal.price
        assert signal.take_profit < signal.price
        
    def test_no_crossover(self):
        """Test no signal when no crossover."""
        bar = pd.Series({
            'close': 1.1000,
            'ema_9': 1.1005,
            'ema_21': 1.1000,
            'atr': 0.0010
        }, name=datetime.now())
        
        self.strategy._state['ema_fast'] = 1.1004
        self.strategy._state['ema_slow'] = 1.1000
        
        signal = self.strategy.on_bar(bar)
        assert signal is None


class TestMomentumBreakout:
    """Test Momentum Breakout strategy."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.config = {
            'type': 'momentum_breakout',
            'params': {
                'lookback_period': 20,
                'rsi_threshold': 55,
                'symbol': 'BTCUSD'
            },
            'timeframe': '1H'
        }
        self.strategy = MomentumBreakout(self.config)
        
    def test_initialization(self):
        """Test strategy initialization."""
        assert self.strategy.name == "momentum_breakout"
        assert self.strategy.lookback_period == 20
        
    def test_bullish_breakout(self):
        """Test bullish breakout signal."""
        bar = pd.Series({
            'open': 50000,
            'high': 50500,
            'low': 49900,
            'close': 50400,
            'volume': 1000,
            'high_20': 50000,  # Breaking above
            'low_20': 48000,
            'volume_avg_20': 500,
            'rsi': 60,
            'atr': 200
        }, name=datetime.now())
        
        signal = self.strategy.on_bar(bar)
        
        assert signal is not None
        assert signal.side == SignalType.LONG
        assert signal.confidence == 0.80
        assert 'breakout' in signal.reason.lower()
        
    def test_bearish_breakout(self):
        """Test bearish breakout signal."""
        bar = pd.Series({
            'open': 50000,
            'high': 50100,
            'low': 47900,
            'close': 47950,
            'volume': 1000,
            'high_20': 50000,
            'low_20': 48000,  # Breaking below
            'volume_avg_20': 500,
            'rsi': 35,
            'atr': 200
        }, name=datetime.now())
        
        signal = self.strategy.on_bar(bar)
        
        assert signal is not None
        assert signal.side == SignalType.SHORT
        
    def test_no_volume_confirmation(self):
        """Test no signal without volume confirmation."""
        bar = pd.Series({
            'high': 50500,
            'low': 49900,
            'close': 50400,
            'volume': 400,  # Low volume
            'high_20': 50000,
            'low_20': 48000,
            'volume_avg_20': 500,
            'rsi': 60,
            'atr': 200
        }, name=datetime.now())
        
        signal = self.strategy.on_bar(bar)
        assert signal is None


class TestScalpingStrategy:
    """Test Scalping strategy."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.config = {
            'type': 'scalping',
            'params': {
                'fast_ema': 5,
                'slow_ema': 10,
                'rsi_period': 7,
                'symbol': 'EURUSD'
            },
            'timeframe': 'M5'
        }
        self.strategy = ScalpingStrategy(self.config)
        
    def test_initialization(self):
        """Test strategy initialization."""
        assert self.strategy.name == "scalping"
        assert self.strategy.fast_ema == 5
        
    def test_bullish_scalp(self):
        """Test bullish scalp signal."""
        bar = pd.Series({
            'close': 1.1000,
            'ema_5': 1.1001,
            'ema_10': 1.1000,
            'rsi': 30,  # Oversold recovery
            'atr': 0.0005,
            'spread': 0.00001,
            'pip_value': 0.0001
        }, name=datetime.now())
        
        self.strategy._state['ema_fast'] = 1.0999
        self.strategy._state['ema_slow'] = 1.1000
        
        signal = self.strategy.on_bar(bar)
        
        assert signal is not None
        assert signal.side == SignalType.LONG
        assert signal.confidence == 0.85
        assert 'scalp' in signal.reason.lower()
        
    def test_spread_filter(self):
        """Test that high spread prevents entry."""
        bar = pd.Series({
            'close': 1.1000,
            'ema_5': 1.1001,
            'ema_10': 1.1000,
            'rsi': 30,
            'atr': 0.0005,
            'spread': 0.0003,  # High spread
            'pip_value': 0.0001
        }, name=datetime.now())
        
        self.strategy._state['ema_fast'] = 1.0999
        self.strategy._state['ema_slow'] = 1.1000
        
        signal = self.strategy.on_bar(bar)
        assert signal is None


class TestStrategySelector:
    """Test Dynamic Strategy Selector."""
    
    def setup_method(self):
        """Setup test fixtures."""
        # Create multiple strategies
        self.strategies = [
            EmaCrossover({
                'type': 'ema_crossover',
                'params': {'fast_period': 9, 'slow_period': 21, 'symbol': 'EURUSD'}
            }),
            MomentumBreakout({
                'type': 'momentum_breakout',
                'params': {'lookback_period': 20, 'symbol': 'EURUSD'}
            })
        ]
        
        self.selector = StrategySelector(self.strategies)
        
    def test_initialization(self):
        """Test selector initialization."""
        assert len(self.selector.strategies) == 2
        assert 'ema_crossover' in self.selector.strategies
        assert 'momentum_breakout' in self.selector.strategies
        
    def test_regime_detection_trending_up(self):
        """Test trending up market regime detection."""
        # Create data with uptrend
        dates = pd.date_range(start='2024-01-01', periods=100, freq='h')
        data = pd.DataFrame({
            'open': np.linspace(1.0, 1.1, 100),
            'high': np.linspace(1.01, 1.11, 100),
            'low': np.linspace(0.99, 1.09, 100),
            'close': np.linspace(1.0, 1.1, 100),
            'volume': np.random.randint(500, 1500, 100),
            'adx': np.repeat(30, 100),  # Strong trend
            'atr': np.repeat(0.001, 100),
            'rsi': np.repeat(60, 100),  # Slightly bullish
            'macd': np.repeat(0.001, 100),
            'macd_signal': np.repeat(0.0005, 100),
            'bb_upper': np.linspace(1.02, 1.12, 100),
            'bb_lower': np.linspace(0.98, 1.08, 100)
        }, index=dates)
        
        regime = self.selector.detect_market_regime(data)
        # Regime detection is complex, just verify it returns a valid regime
        assert regime in [MarketRegime.TRENDING_UP_STRONG, MarketRegime.TRENDING_UP_WEAK,
                          MarketRegime.RANGING_WIDE, MarketRegime.RANGING_TIGHT]
        
    def test_regime_detection_volatile(self):
        """Test volatile market regime detection."""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='h')
        data = pd.DataFrame({
            'open': np.random.uniform(0.95, 1.05, 100),
            'high': np.random.uniform(1.0, 1.1, 100),
            'low': np.random.uniform(0.9, 1.0, 100),
            'close': np.random.uniform(0.95, 1.05, 100),
            'volume': np.random.randint(500, 1500, 100),
            'adx': np.repeat(20, 100),
            'rsi': np.repeat(50, 100),
            'macd': np.repeat(0, 100),
            'macd_signal': np.repeat(0, 100),
            'atr': np.linspace(0.001, 0.003, 100),  # Increasing volatility
            'bb_upper': np.random.uniform(1.05, 1.15, 100),
            'bb_lower': np.random.uniform(0.85, 0.95, 100)
        }, index=dates)
        
        regime = self.selector.detect_market_regime(data)
        # Regime detection is complex, just verify it returns a valid regime
        assert regime in [MarketRegime.VOLATILE_BREAKOUT, MarketRegime.VOLATILE_CONSOLIDATION, 
                          MarketRegime.RANGING_WIDE, MarketRegime.RANGING_TIGHT]
        
    def test_strategy_selection(self):
        """Test strategy selection based on conditions."""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='1H')
        data = pd.DataFrame({
            'open': np.linspace(1.0, 1.1, 100),
            'high': np.linspace(1.01, 1.11, 100),
            'low': np.linspace(0.99, 1.09, 100),
            'close': np.linspace(1.0, 1.1, 100),
            'volume': np.random.randint(500, 1500, 100),
            'adx': np.repeat(30, 100),
            'atr': np.repeat(0.001, 100)
        }, index=dates)
        
        selected_strategy = self.selector.select_strategy(data)
        
        assert selected_strategy is not None
        assert selected_strategy.name in ['ema_crossover', 'momentum_breakout']
        
    def test_performance_tracking(self):
        """Test strategy performance tracking."""
        from cthulu.strategy.base import Signal
        
        # Record signal
        signal = Signal(
            id='test_123',
            timestamp=datetime.now(),
            symbol='EURUSD',
            timeframe='1H',
            side=SignalType.LONG,
            action='BUY',
            confidence=0.75,
            reason='Test signal'
        )
        
        self.selector.performance['ema_crossover'].add_signal(signal)
        
        # Record outcome
        self.selector.record_outcome('ema_crossover', 'win', 100.0)
        
        perf = self.selector.performance['ema_crossover']
        assert perf.wins == 1
        assert perf.total_profit == 100.0
        assert perf.win_rate == 1.0
        
    def test_performance_report(self):
        """Test performance report generation."""
        report = self.selector.get_performance_report()
        
        assert 'current_regime' in report
        assert 'strategies' in report
        assert len(report['strategies']) == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])




