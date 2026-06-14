"""
Test Profit Scaling Exit Strategy

Comprehensive tests for the profit scaling logic that:
- Takes partial profits at different tiers
- Adapts to account size
- Protects against profit giveback
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from cthulu.exit.profit_scaling import (
    ProfitScalingExit,
    AggressiveScalingExit,
    ScaleTier,
    PositionScaleState,
    ScaleConfig
)
from cthulu.position.manager import PositionInfo


class TestProfitScalingExit:
    """Test suite for ProfitScalingExit."""
    
    @pytest.fixture
    def strategy(self):
        """Create a profit scaling strategy with default params."""
        return ProfitScalingExit()
    
    @pytest.fixture
    def aggressive_strategy(self):
        """Create an aggressive scaling strategy."""
        return AggressiveScalingExit()
    
    @pytest.fixture
    def long_position(self):
        """Create a sample long position."""
        pos = MagicMock(spec=PositionInfo)
        pos.ticket = 12345
        pos.symbol = "BTCUSD"
        pos.side = "BUY"
        pos.open_price = 100000.0
        pos.volume = 0.1
        pos.current_price = 100000.0
        pos.unrealized_pnl = 0.0
        return pos
    
    @pytest.fixture
    def short_position(self):
        """Create a sample short position."""
        pos = MagicMock(spec=PositionInfo)
        pos.ticket = 12346
        pos.symbol = "GOLD#"
        pos.side = "SELL"
        pos.open_price = 2650.0
        pos.volume = 0.1
        pos.current_price = 2650.0
        pos.unrealized_pnl = 0.0
        return pos
    
    def test_initialization(self, strategy):
        """Test strategy initializes correctly."""
        assert strategy.name == "ProfitScaling"
        assert strategy.priority == 55
        assert strategy._enabled is True
        assert strategy.config is not None
        
    def test_no_signal_at_entry(self, strategy, long_position):
        """Test no signal when position is just opened (no profit)."""
        current_data = {
            'current_price': long_position.open_price,
            'account_balance': 1000.0,
            'indicators': {}
        }
        
        signal = strategy.should_exit(long_position, current_data)
        assert signal is None
        
    def test_tier_1_trigger_long(self, strategy, long_position):
        """Test Tier 1 triggers at 0.3% profit for long."""
        # First initialize at entry price
        init_data = {
            'current_price': long_position.open_price,
            'account_balance': 1000.0,
            'indicators': {}
        }
        strategy.should_exit(long_position, init_data)
        
        # Set price to trigger tier 1 (0.3% profit) - use exact value
        tier_1_price = long_position.open_price + (long_position.open_price * 0.003)  # 100300
        long_position.current_price = tier_1_price
        long_position.unrealized_pnl = 30.0  # 0.3% of 10000 (0.1 * 100000)
        
        current_data = {
            'current_price': tier_1_price,
            'account_balance': 1000.0,
            'indicators': {}
        }
        
        signal = strategy.should_exit(long_position, current_data)
        
        assert signal is not None
        assert signal.partial_volume is not None
        assert signal.partial_volume > 0
        assert "TIER_1" in signal.reason
        assert signal.metadata['tier'] == 'TIER_1'
        
    def test_tier_1_trigger_short(self, strategy, short_position):
        """Test Tier 1 triggers at 0.3% profit for short."""
        # First initialize at entry price
        init_data = {
            'current_price': short_position.open_price,
            'account_balance': 1000.0,
            'indicators': {}
        }
        strategy.should_exit(short_position, init_data)
        
        # Set price to trigger tier 1 (0.31% profit for short = price drops)
        # Use slightly higher than 0.3% to avoid floating point issues
        tier_1_price = short_position.open_price - (short_position.open_price * 0.0031)
        short_position.current_price = tier_1_price
        short_position.unrealized_pnl = 8.22  # ~0.31% profit
        
        current_data = {
            'current_price': tier_1_price,
            'account_balance': 1000.0,
            'indicators': {}
        }
        
        signal = strategy.should_exit(short_position, current_data)
        
        assert signal is not None
        assert "TIER_1" in signal.reason
        
    def test_tier_progression(self, strategy, long_position):
        """Test full tier progression from 1 to 3."""
        # Initialize at entry
        current_data = {
            'current_price': long_position.open_price,
            'account_balance': 1000.0,
            'indicators': {}
        }
        strategy.should_exit(long_position, current_data)
        
        # Tier 1 at 0.3%
        tier_1_price = long_position.open_price + (long_position.open_price * 0.003)
        long_position.current_price = tier_1_price
        long_position.volume = 0.1
        current_data['current_price'] = tier_1_price
        
        signal_1 = strategy.should_exit(long_position, current_data)
        assert signal_1 is not None
        assert signal_1.metadata['tier'] == 'TIER_1'
        
        # Simulate partial close
        long_position.volume = 0.07  # Closed 30%
        
        # Tier 2 at 0.6%
        tier_2_price = long_position.open_price + (long_position.open_price * 0.006)
        long_position.current_price = tier_2_price
        current_data['current_price'] = tier_2_price
        
        signal_2 = strategy.should_exit(long_position, current_data)
        assert signal_2 is not None
        assert signal_2.metadata['tier'] == 'TIER_2'
        
        # Simulate partial close
        long_position.volume = 0.0455  # Closed 35% of remaining
        
        # Tier 3 at 1.0%
        tier_3_price = long_position.open_price + (long_position.open_price * 0.01)
        long_position.current_price = tier_3_price
        current_data['current_price'] = tier_3_price
        
        signal_3 = strategy.should_exit(long_position, current_data)
        assert signal_3 is not None
        assert signal_3.metadata['tier'] == 'TIER_3'
        
    def test_micro_account_tighter_targets(self, strategy, long_position):
        """Test that micro accounts get tighter profit targets."""
        current_data = {
            'current_price': long_position.open_price,
            'account_balance': 50.0,  # Micro account
            'indicators': {}
        }
        
        # Get targets
        targets = strategy._get_adjusted_targets(50.0, {})
        
        # Micro should have tighter targets
        assert targets['tier_1'] < 0.3  # Default is 0.3%
        assert targets['tier_1'] == strategy.config.micro_tier_1_pct
        
    def test_small_account_targets(self, strategy, long_position):
        """Test that small accounts get appropriate targets."""
        targets = strategy._get_adjusted_targets(250.0, {})
        
        # Small account targets
        assert targets['tier_1'] == strategy.config.small_tier_1_pct
        assert targets['tier_2'] == strategy.config.small_tier_2_pct
        
    def test_giveback_protection(self, strategy, long_position):
        """Test profit giveback protection after scaling."""
        current_data = {
            'current_price': long_position.open_price,
            'account_balance': 1000.0,
            'indicators': {}
        }
        
        # Initialize
        strategy.should_exit(long_position, current_data)
        
        # Hit tier 1
        tier_1_price = long_position.open_price * 1.003
        current_data['current_price'] = tier_1_price
        long_position.current_price = tier_1_price
        strategy.should_exit(long_position, current_data)
        
        # Price goes to 0.5% profit (peak)
        peak_price = long_position.open_price * 1.005
        current_data['current_price'] = peak_price
        long_position.current_price = peak_price
        long_position.volume = 0.07
        strategy.should_exit(long_position, current_data)  # Update peak
        
        # Price retraces to 0.1% (80% giveback)
        retrace_price = long_position.open_price * 1.001
        current_data['current_price'] = retrace_price
        long_position.current_price = retrace_price
        long_position.unrealized_pnl = 0.1
        
        signal = strategy.should_exit(long_position, current_data)
        
        # Should trigger giveback protection
        assert signal is not None
        assert "GIVEBACK" in signal.metadata.get('tier', '') or "giveback" in signal.reason.lower()
        
    def test_volume_calculation(self, strategy):
        """Test volume calculation for scaling."""
        # Standard case
        vol = strategy._calculate_scale_volume(0.1, 30.0)
        assert vol == 0.03  # 30% of 0.1
        
        # Minimum volume
        vol = strategy._calculate_scale_volume(0.02, 30.0)
        assert vol >= 0.01  # Minimum 0.01
        
        # Tiny remaining - closes minimum or all if very tiny
        vol = strategy._calculate_scale_volume(0.015, 100.0)
        assert vol == 0.01 or vol == 0.015  # Either minimum or all
        
    def test_position_state_tracking(self, strategy, long_position):
        """Test position state is properly tracked."""
        current_data = {
            'current_price': long_position.open_price,
            'account_balance': 1000.0,
            'indicators': {}
        }
        
        # Initialize
        strategy.should_exit(long_position, current_data)
        
        state = strategy.get_position_state(long_position.ticket)
        assert state is not None
        assert state.ticket == long_position.ticket
        assert state.original_volume == long_position.volume
        assert state.current_tier == ScaleTier.INITIAL
        
    def test_remove_position(self, strategy, long_position):
        """Test position removal from tracking."""
        current_data = {
            'current_price': long_position.open_price,
            'account_balance': 1000.0,
            'indicators': {}
        }
        
        strategy.should_exit(long_position, current_data)
        assert strategy.get_position_state(long_position.ticket) is not None
        
        strategy.remove_position(long_position.ticket)
        assert strategy.get_position_state(long_position.ticket) is None
        
    def test_reset_clears_all_states(self, strategy, long_position):
        """Test reset clears all position states."""
        current_data = {
            'current_price': long_position.open_price,
            'account_balance': 1000.0,
            'indicators': {}
        }
        
        strategy.should_exit(long_position, current_data)
        strategy.reset()
        
        assert strategy.get_position_state(long_position.ticket) is None
        assert len(strategy._position_states) == 0


class TestAggressiveScalingExit:
    """Test suite for AggressiveScalingExit."""
    
    @pytest.fixture
    def strategy(self):
        return AggressiveScalingExit()
    
    def test_tighter_default_targets(self, strategy):
        """Test aggressive strategy has tighter defaults."""
        assert strategy.config.tier_1_profit_pct == 0.15  # vs 0.3 normal
        assert strategy.config.tier_2_profit_pct == 0.30  # vs 0.6 normal
        assert strategy.config.tier_3_profit_pct == 0.50  # vs 1.0 normal
        
    def test_higher_close_percentages(self, strategy):
        """Test aggressive strategy closes more at each tier."""
        assert strategy.config.tier_1_close_pct == 35.0  # vs 30 normal
        assert strategy.config.tier_2_close_pct == 40.0  # vs 35 normal
        assert strategy.config.tier_3_close_pct == 60.0  # vs 50 normal
        
    def test_name_and_priority(self, strategy):
        """Test aggressive strategy has correct name and priority."""
        assert strategy.name == "AggressiveScaling"
        assert strategy.priority == 60  # Higher than normal


class TestScaleConfig:
    """Test ScaleConfig dataclass."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = ScaleConfig()
        
        assert config.tier_1_profit_pct == 0.3
        assert config.tier_2_profit_pct == 0.6
        assert config.tier_3_profit_pct == 1.0
        
        assert config.tier_1_close_pct == 30.0
        assert config.tier_2_close_pct == 35.0
        assert config.tier_3_close_pct == 50.0
        
        assert config.micro_account_threshold == 100.0
        assert config.small_account_threshold == 500.0
        
    def test_custom_values(self):
        """Test custom configuration values."""
        config = ScaleConfig(
            tier_1_profit_pct=0.5,
            tier_1_close_pct=25.0
        )
        
        assert config.tier_1_profit_pct == 0.5
        assert config.tier_1_close_pct == 25.0


class TestPositionScaleState:
    """Test PositionScaleState dataclass."""
    
    def test_initial_state(self):
        """Test initial state values."""
        state = PositionScaleState(
            ticket=12345,
            original_volume=0.1,
            entry_price=100.0
        )
        
        assert state.ticket == 12345
        assert state.original_volume == 0.1
        assert state.current_tier == ScaleTier.INITIAL
        assert state.total_scaled_volume == 0
        assert state.remaining_volume_pct == 100.0
        
    def test_scaled_volume_tracking(self):
        """Test tracking of scaled volumes."""
        state = PositionScaleState(
            ticket=12345,
            original_volume=0.1,
            entry_price=100.0
        )
        
        state.scales_executed.append({'volume': 0.03})
        assert state.total_scaled_volume == 0.03
        assert state.remaining_volume_pct == 70.0
        
        state.scales_executed.append({'volume': 0.02})
        assert state.total_scaled_volume == 0.05
        assert state.remaining_volume_pct == 50.0


class TestVolatilityAdjustment:
    """Test volatility-based target adjustment."""
    
    @pytest.fixture
    def strategy(self):
        return ProfitScalingExit({'volatility_adjust': True})
    
    def test_high_volatility_widens_targets(self, strategy):
        """Test that high ATR widens profit targets."""
        indicators = {
            'atr': 0.01,  # 1% ATR
            'atr_pct': 1.0
        }
        
        targets = strategy._get_adjusted_targets(1000.0, indicators)
        
        # High volatility should widen targets
        assert targets['tier_1'] > strategy.config.tier_1_profit_pct
        
    def test_low_volatility_tightens_targets(self, strategy):
        """Test that low ATR tightens profit targets."""
        indicators = {
            'atr': 0.001,  # 0.1% ATR
            'atr_pct': 0.1
        }
        
        targets = strategy._get_adjusted_targets(1000.0, indicators)
        
        # Low volatility should tighten targets
        assert targets['tier_1'] < strategy.config.tier_1_profit_pct


class TestMomentumAdjustment:
    """Test momentum-based target adjustment."""
    
    @pytest.fixture
    def strategy(self):
        return ProfitScalingExit({'momentum_adjust': True})
    
    def test_strong_trend_widens_targets(self, strategy):
        """Test that strong ADX widens targets (let winners run)."""
        indicators = {
            'adx': 40,  # Strong trend
            'ADX': 40
        }
        
        targets = strategy._get_adjusted_targets(1000.0, indicators)
        
        # Strong trend = wider targets
        assert targets['tier_1'] > strategy.config.tier_1_profit_pct
        
    def test_weak_trend_tightens_targets(self, strategy):
        """Test that weak ADX tightens targets (take profits quick)."""
        indicators = {
            'adx': 15,  # Weak trend
            'ADX': 15
        }
        
        targets = strategy._get_adjusted_targets(1000.0, indicators)
        
        # Weak trend = tighter targets
        assert targets['tier_1'] < strategy.config.tier_1_profit_pct


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
