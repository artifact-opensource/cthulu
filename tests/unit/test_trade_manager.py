"""
Tests for TradeManager.
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from cthulu.position.manager import PositionInfo, PositionManager
from cthulu.position.trade_manager import TradeManager, TradeAdoptionPolicy


class TestTradeAdoptionPolicy(unittest.TestCase):
    """Test TradeAdoptionPolicy configuration."""
    
    def test_default_policy(self):
        """Test default policy values."""
        policy = TradeAdoptionPolicy()
        
        self.assertTrue(policy.enabled)
        self.assertEqual(policy.adopt_symbols, [])
        self.assertEqual(policy.ignore_symbols, [])
        self.assertTrue(policy.apply_exit_strategies)
        self.assertEqual(policy.max_adoption_age_hours, 0.0)
        self.assertFalse(policy.log_only)
        
    def test_custom_policy(self):
        """Test custom policy configuration."""
        policy = TradeAdoptionPolicy(
            enabled=True,
            adopt_symbols=["EURUSD", "GBPUSD"],
            ignore_symbols=["XAUUSD"],
            apply_exit_strategies=True,
            max_adoption_age_hours=24.0,
            log_only=False
        )
        
        self.assertTrue(policy.enabled)
        self.assertEqual(len(policy.adopt_symbols), 2)
        self.assertIn("EURUSD", policy.adopt_symbols)
        self.assertEqual(policy.max_adoption_age_hours, 24.0)


class TestTradeManager(unittest.TestCase):
    """Test TradeManager functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_connector = MagicMock()
        self.mock_connector.is_connected.return_value = True
        
        self.mock_execution_engine = MagicMock()
        
        self.position_manager = PositionManager(
            connector=self.mock_connector,
            execution_engine=self.mock_execution_engine
        )
        
        self.policy = TradeAdoptionPolicy(enabled=True)
        self.trade_manager = TradeManager(
            position_manager=self.position_manager,
            policy=self.policy,
            magic_number=123456
        )
        
    def test_initialization(self):
        """Test trade manager initialization."""
        self.assertIsNotNone(self.trade_manager)
        self.assertEqual(self.trade_manager.magic_number, 123456)
        self.assertEqual(len(self.trade_manager._adopted_tickets), 0)
        
    def test_disabled_policy_returns_empty(self):
        """Test that disabled policy returns no trades."""
        disabled_policy = TradeAdoptionPolicy(enabled=False)
        manager = TradeManager(
            position_manager=self.position_manager,
            policy=disabled_policy
        )
        
        trades = manager.scan_for_external_trades()
        self.assertEqual(trades, [])
        
    @patch('cthulu.position.trade_manager.mt5')
    def test_scan_detects_external_trade(self, mock_mt5):
        """Test that scan detects external trades."""
        # Create mock MT5 position with different magic number
        mock_position = MagicMock()
        mock_position.ticket = 999999
        mock_position.symbol = "EURUSD"
        mock_position.type = 0  # BUY
        mock_position.volume = 0.1
        mock_position.price_open = 1.1000
        mock_position.time = datetime.now().timestamp()
        mock_position.sl = 1.0950
        mock_position.tp = 1.1100
        mock_position.price_current = 1.1020
        mock_position.profit = 20.0
        mock_position.magic = 0  # Manual trade (no magic)
        mock_position.swap = 0.0
        mock_position.commission = 0.0
        mock_position.comment = "Manual"
        
        mock_mt5.positions_get.return_value = [mock_position]
        mock_mt5.ORDER_TYPE_BUY = 0
        mock_mt5.ORDER_TYPE_SELL = 1
        
        trades = self.trade_manager.scan_for_external_trades()
        
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].ticket, 999999)
        self.assertEqual(trades[0].symbol, "EURUSD")
        self.assertEqual(trades[0].side, "BUY")
        
    @patch('cthulu.position.trade_manager.mt5')
    def test_scan_ignores_Cthulu_trades(self, mock_mt5):
        """Test that scan ignores Cthulu's own trades."""
        # Create mock MT5 position with Cthulu's magic number
        mock_position = MagicMock()
        mock_position.ticket = 888888
        mock_position.symbol = "EURUSD"
        mock_position.type = 0
        mock_position.volume = 0.1
        mock_position.price_open = 1.1000
        mock_position.time = datetime.now().timestamp()
        mock_position.sl = 0
        mock_position.tp = 0
        mock_position.price_current = 1.1020
        mock_position.profit = 20.0
        mock_position.magic = 123456  # Cthulu's magic number
        mock_position.swap = 0.0
        mock_position.commission = 0.0
        mock_position.comment = "Cthulu"
        
        mock_mt5.positions_get.return_value = [mock_position]
        
        trades = self.trade_manager.scan_for_external_trades()
        
        # Should be empty since it's Cthulu's trade
        self.assertEqual(len(trades), 0)
        
    @patch('cthulu.position.trade_manager.mt5')
    def test_scan_respects_symbol_filter(self, mock_mt5):
        """Test that scan respects adopt_symbols filter."""
        policy = TradeAdoptionPolicy(enabled=True, adopt_symbols=["GBPUSD"])
        manager = TradeManager(
            position_manager=self.position_manager,
            policy=policy
        )
        
        mock_position = MagicMock()
        mock_position.ticket = 777777
        mock_position.symbol = "EURUSD"  # Not in adopt_symbols
        mock_position.type = 0
        mock_position.volume = 0.1
        mock_position.price_open = 1.1000
        mock_position.time = datetime.now().timestamp()
        mock_position.sl = 0
        mock_position.tp = 0
        mock_position.price_current = 1.1020
        mock_position.profit = 20.0
        mock_position.magic = 0
        mock_position.swap = 0.0
        mock_position.commission = 0.0
        mock_position.comment = ""
        
        mock_mt5.positions_get.return_value = [mock_position]
        
        trades = manager.scan_for_external_trades()
        
        # Should be empty since EURUSD not in adopt_symbols
        self.assertEqual(len(trades), 0)
        
    @patch('cthulu.position.trade_manager.mt5')
    def test_scan_respects_ignore_symbols(self, mock_mt5):
        """Test that scan respects ignore_symbols filter."""
        policy = TradeAdoptionPolicy(enabled=True, ignore_symbols=["XAUUSD"])
        manager = TradeManager(
            position_manager=self.position_manager,
            policy=policy
        )
        
        mock_position = MagicMock()
        mock_position.ticket = 666666
        mock_position.symbol = "XAUUSD"  # In ignore list
        mock_position.type = 0
        mock_position.volume = 0.1
        mock_position.price_open = 2000.0
        mock_position.time = datetime.now().timestamp()
        mock_position.sl = 0
        mock_position.tp = 0
        mock_position.price_current = 2010.0
        mock_position.profit = 100.0
        mock_position.magic = 0
        mock_position.swap = 0.0
        mock_position.commission = 0.0
        mock_position.comment = ""
        
        mock_mt5.positions_get.return_value = [mock_position]
        
        trades = manager.scan_for_external_trades()
        
        # Should be empty since XAUUSD is ignored
        self.assertEqual(len(trades), 0)
        
    def test_adopt_trade(self):
        """Test adopting an external trade."""
        trade = PositionInfo(
            ticket=555555,
            symbol="BTCUSD#",
            side="BUY",
            volume=0.01,
            open_price=90000.0,
            open_time=datetime.now(),
            current_price=90500.0,
            unrealized_pnl=50.0,
            magic_number=0,
            metadata={'adopted': True}
        )
        
        adopted = self.trade_manager.adopt_trades([trade])
        
        self.assertEqual(adopted, 1)
        self.assertIn(555555, self.trade_manager._adopted_tickets)
        self.assertIn(555555, self.position_manager._positions)
        
    def test_log_only_mode(self):
        """Test log_only mode doesn't adopt."""
        policy = TradeAdoptionPolicy(enabled=True, log_only=True)
        manager = TradeManager(
            position_manager=self.position_manager,
            policy=policy
        )
        
        trade = PositionInfo(
            ticket=444444,
            symbol="EURUSD",
            side="SELL",
            volume=0.1,
            open_price=1.1000,
            open_time=datetime.now(),
            current_price=1.0980,
            unrealized_pnl=20.0
        )
        
        adopted = manager.adopt_trades([trade])
        
        self.assertEqual(adopted, 0)
        self.assertNotIn(444444, manager._adopted_tickets)
        
    def test_is_adopted(self):
        """Test is_adopted check."""
        self.trade_manager._adopted_tickets.add(333333)
        
        self.assertTrue(self.trade_manager.is_adopted(333333))
        self.assertFalse(self.trade_manager.is_adopted(222222))
        
    def test_get_adoption_log(self):
        """Test getting adoption log."""
        trade = PositionInfo(
            ticket=111111,
            symbol="GBPUSD",
            side="BUY",
            volume=0.5,
            open_price=1.2500,
            open_time=datetime.now(),
            current_price=1.2550,
            unrealized_pnl=250.0,
            magic_number=999
        )
        
        self.trade_manager.adopt_trades([trade])
        
        log = self.trade_manager.get_adoption_log()
        
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]['ticket'], 111111)
        self.assertEqual(log[0]['symbol'], "GBPUSD")


if __name__ == '__main__':
    unittest.main()




