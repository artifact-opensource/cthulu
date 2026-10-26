"""
Unit tests for Phase 2 exit strategy system.
Tests all 4 exit strategies: StopLoss, TakeProfit, TrailingStop, TimeBased.

Exit strategies now return:
- ExitSignal when exit is triggered
- None when no exit should occur

ExitStrategyManager wraps ExitSignal into ExitDecision for coordination.
Priority semantics: Higher numeric value = higher urgency (0-100 scale)
"""

import unittest
from datetime import datetime, timedelta
from decimal import Decimal


class TestExitDecision(unittest.TestCase):
    """Test ExitDecision dataclass."""
    
    def test_exit_decision_import(self):
        """Test that ExitDecision can be imported."""
        try:
            from cthulu.exit.exit_manager import ExitDecision
            self.assertTrue(True)
        except ImportError:
            self.fail("Could not import ExitDecision from exit.exit_manager")
    
    def test_exit_decision_creation(self):
        """Test creating an ExitDecision instance."""
        from cthulu.exit.exit_manager import ExitDecision
        
        decision = ExitDecision(
            should_exit=True,
            strategy_name="StopLossExit",
            reason="Stop loss triggered at 1.0950",
            priority=100,
            exit_price=1.0950
        )
        
        self.assertTrue(decision.should_exit)
        self.assertEqual(decision.strategy_name, "StopLossExit")
        self.assertEqual(decision.priority, 100)


class TestStopLossExit(unittest.TestCase):
    """Test StopLossExit strategy."""
    
    def test_stop_loss_import(self):
        """Test that StopLossExit can be imported."""
        try:
            from cthulu.exit.stop_loss import StopLossExit
            self.assertTrue(True)
        except ImportError:
            self.fail("Could not import StopLossExit from exit.stop_loss")
    
    def test_stop_loss_initialization(self):
        """Test StopLossExit initialization."""
        from cthulu.exit.stop_loss import StopLossExit
        
        strategy = StopLossExit(stop_loss_pct=0.02)
        
        self.assertEqual(strategy.priority, 100)  # High priority - emergency
        self.assertEqual(strategy.stop_loss_pct, 0.02)
    
    def test_stop_loss_triggered(self):
        """Test stop loss triggering on losing position."""
        from cthulu.exit.stop_loss import StopLossExit
        from cthulu.position.manager import PositionInfo
        
        strategy = StopLossExit(stop_loss_pct=0.02)
        
        # Buy position that has lost more than 2%
        position = PositionInfo(
            ticket=12345,
            symbol="EURUSD",
            volume=1.0,
            open_price=1.1000,
            current_price=1.0750,  # 2.27% loss
            open_time=datetime.now(),
            side="BUY",
            stop_loss=1.0780
        )
        
        signal = strategy.should_exit(position)
        
        # ExitSignal returned when triggered
        self.assertIsNotNone(signal)
        self.assertEqual(signal.ticket, 12345)
        self.assertIn("stop loss", signal.reason.lower())
    
    def test_stop_loss_not_triggered(self):
        """Test stop loss not triggering on profitable position."""
        from cthulu.exit.stop_loss import StopLossExit
        from cthulu.position.manager import PositionInfo
        
        strategy = StopLossExit(stop_loss_pct=0.02)
        
        # Buy position with profit
        position = PositionInfo(
            ticket=12345,
            symbol="EURUSD",
            volume=1.0,
            open_price=1.1000,
            current_price=1.1050,  # Profit
            open_time=datetime.now(),
            side="BUY",
            stop_loss=1.0780
        )
        
        signal = strategy.should_exit(position)
        
        # None returned when not triggered
        self.assertIsNone(signal)


class TestTakeProfitExit(unittest.TestCase):
    """Test TakeProfitExit strategy."""
    
    def test_take_profit_import(self):
        """Test that TakeProfitExit can be imported."""
        try:
            from cthulu.exit.take_profit import TakeProfitExit
            self.assertTrue(True)
        except ImportError:
            self.fail("Could not import TakeProfitExit from exit.take_profit")
    
    def test_take_profit_initialization(self):
        """Test TakeProfitExit initialization."""
        from cthulu.exit.take_profit import TakeProfitExit
        
        strategy = TakeProfitExit(take_profit_pct=0.03)
        
        self.assertEqual(strategy.priority, 50)  # Medium priority
        self.assertEqual(strategy.take_profit_pct, 0.03)
    
    def test_take_profit_triggered(self):
        """Test take profit triggering on winning position."""
        from cthulu.exit.take_profit import TakeProfitExit
        from cthulu.position.manager import PositionInfo
        
        strategy = TakeProfitExit(take_profit_pct=0.03)
        
        # Buy position with >3% profit
        position = PositionInfo(
            ticket=12345,
            symbol="EURUSD",
            volume=1.0,
            open_price=1.1000,
            current_price=1.1350,  # 3.18% profit
            open_time=datetime.now(),
            side="BUY",
            take_profit=1.1330
        )
        
        signal = strategy.should_exit(position)
        
        # ExitSignal returned when triggered
        self.assertIsNotNone(signal)
        self.assertEqual(signal.ticket, 12345)
        self.assertIn("take profit", signal.reason.lower())
    
    def test_take_profit_not_triggered(self):
        """Test take profit not triggering when target not reached."""
        from cthulu.exit.take_profit import TakeProfitExit
        from cthulu.position.manager import PositionInfo
        
        strategy = TakeProfitExit(take_profit_pct=0.03)
        
        # Buy position with small profit
        position = PositionInfo(
            ticket=12345,
            symbol="EURUSD",
            volume=1.0,
            open_price=1.1000,
            current_price=1.1020,  # Only 0.18% profit
            open_time=datetime.now(),
            side="BUY",
            take_profit=1.1330
        )
        
        signal = strategy.should_exit(position)
        
        # None returned when not triggered
        self.assertIsNone(signal)


class TestTrailingStopExit(unittest.TestCase):
    """Test TrailingStopExit strategy."""
    
    def test_trailing_stop_import(self):
        """Test that TrailingStopExit can be imported."""
        try:
            from cthulu.exit.trailing_stop import TrailingStopExit
            self.assertTrue(True)
        except ImportError:
            self.fail("Could not import TrailingStopExit from exit.trailing_stop")
    
    def test_trailing_stop_initialization(self):
        """Test TrailingStopExit initialization."""
        from cthulu.exit.trailing_stop import TrailingStopExit
        
        strategy = TrailingStopExit(trail_distance=0.015)
        
        self.assertEqual(strategy.priority, 3)  # Legacy compatibility wrapper
        self.assertEqual(strategy.trail_distance, 0.015)
    
    def test_trailing_stop_adjustment(self):
        """Test trailing stop adjusts as price moves favorably."""
        from cthulu.exit.trailing_stop import TrailingStopExit
        from cthulu.position.manager import PositionInfo
        
        strategy = TrailingStopExit(trail_distance=0.015)
        
        # Buy position that has moved in profit
        position = PositionInfo(
            ticket=12345,
            symbol="EURUSD",
            volume=1.0,
            open_price=1.1000,
            current_price=1.1200,
            open_time=datetime.now(),
            side="BUY",
            stop_loss=1.0850
        )
        
        # Trailing stop should update
        new_stop = strategy.calculate_trailing_stop(position)
        
        # New stop should be higher than original stop
        self.assertGreater(new_stop, position.stop_loss)


class TestTimeBasedExit(unittest.TestCase):
    """Test TimeBasedExit strategy."""
    
    def test_time_based_import(self):
        """Test that TimeBasedExit can be imported."""
        try:
            from cthulu.exit.time_based import TimeBasedExit
            self.assertTrue(True)
        except ImportError:
            self.fail("Could not import TimeBasedExit from exit.time_based")
    
    def test_time_based_initialization(self):
        """Test TimeBasedExit initialization."""
        from cthulu.exit.time_based import TimeBasedExit
        
        strategy = TimeBasedExit(max_hold_hours=24)
        
        self.assertEqual(strategy.priority, 4)  # Default low priority
        self.assertEqual(strategy.max_hold_hours, 24)
    
    def test_time_based_triggered(self):
        """Test time-based exit triggering after hold period."""
        from cthulu.exit.time_based import TimeBasedExit
        from cthulu.position.manager import PositionInfo
        
        strategy = TimeBasedExit(max_hold_hours=24)
        
        # Position opened 25 hours ago
        position = PositionInfo(
            ticket=12345,
            symbol="EURUSD",
            volume=1.0,
            open_price=1.1000,
            current_price=1.1050,
            open_time=datetime.now() - timedelta(hours=25),
            side="BUY"
        )
        
        signal = strategy.should_exit(position)
        
        # ExitSignal returned when triggered
        self.assertIsNotNone(signal)
        self.assertEqual(signal.ticket, 12345)
        self.assertIn("hold time", signal.reason.lower())
    
    def test_time_based_not_triggered(self):
        """Test time-based exit not triggering before hold period."""
        from cthulu.exit.time_based import TimeBasedExit
        from cthulu.position.manager import PositionInfo
        
        strategy = TimeBasedExit(max_hold_hours=24)
        
        # Position opened 1 hour ago
        position = PositionInfo(
            ticket=12345,
            symbol="EURUSD",
            volume=1.0,
            open_price=1.1000,
            current_price=1.1050,
            open_time=datetime.now() - timedelta(hours=1),
            side="BUY"
        )
        
        signal = strategy.should_exit(position)
        
        # None returned when not triggered
        self.assertIsNone(signal)


class TestExitStrategyManager(unittest.TestCase):
    """Test ExitStrategyManager coordinating multiple strategies."""
    
    def test_exit_manager_import(self):
        """Test that ExitStrategyManager can be imported."""
        try:
            from cthulu.exit.exit_manager import ExitStrategyManager
            self.assertTrue(True)
        except ImportError:
            self.fail("Could not import ExitStrategyManager from exit.exit_manager")
    
    def test_exit_manager_initialization(self):
        """Test ExitStrategyManager initialization."""
        from cthulu.exit.exit_manager import ExitStrategyManager
        
        manager = ExitStrategyManager()
        
        self.assertIsNotNone(manager)
    
    def test_exit_manager_register_strategy(self):
        """Test registering exit strategies."""
        from cthulu.exit.exit_manager import ExitStrategyManager
        from cthulu.exit.stop_loss import StopLossExit
        from cthulu.exit.take_profit import TakeProfitExit
        
        manager = ExitStrategyManager()
        
        manager.register(StopLossExit(stop_loss_pct=0.02))
        manager.register(TakeProfitExit(take_profit_pct=0.03))
        
        self.assertEqual(len(manager.strategies), 2)
    
    def test_exit_manager_priority_order(self):
        """Test that exit decisions are evaluated in priority order.
        
        Priority semantics: Higher numeric value = higher urgency
        - StopLossExit: priority 100 (emergency)
        - TakeProfitExit: priority 50 (medium)
        
        Manager should return the highest priority (100) when multiple triggered.
        """
        from cthulu.exit.exit_manager import ExitStrategyManager
        from cthulu.exit.stop_loss import StopLossExit
        from cthulu.exit.take_profit import TakeProfitExit
        from cthulu.position.manager import PositionInfo
        
        manager = ExitStrategyManager()
        manager.register(TakeProfitExit(take_profit_pct=0.03))  # Priority 50
        manager.register(StopLossExit(stop_loss_pct=0.02))      # Priority 100
        
        # Position that triggers stop loss
        position = PositionInfo(
            ticket=12345,
            symbol="EURUSD",
            volume=1.0,
            open_price=1.1000,
            current_price=1.0750,  # Loss
            open_time=datetime.now(),
            side="BUY",
            stop_loss=1.0780
        )
        
        decision = manager.evaluate_exit(position)
        
        # Should return stop loss decision (priority 100 - highest)
        self.assertTrue(decision.should_exit)
        self.assertEqual(decision.priority, 100)
        self.assertIn("stop loss", decision.reason.lower())


if __name__ == '__main__':
    unittest.main()




