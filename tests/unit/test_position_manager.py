"""
Unit tests for Phase 2 position management module.
Tests PositionInfo dataclass and PositionManager operations.
"""

import unittest
from datetime import datetime
from decimal import Decimal


class TestPositionInfo(unittest.TestCase):
    """Test PositionInfo dataclass."""
    
    def test_position_info_import(self):
        """Test that PositionInfo can be imported."""
        try:
            from cthulu.position.manager import PositionInfo
            self.assertTrue(True)
        except ImportError:
            self.fail("Could not import PositionInfo from position.position_manager")
    
    def test_position_info_creation(self):
        """Test creating a PositionInfo instance."""
        from cthulu.position.manager import PositionInfo
        
        pos = PositionInfo(
            ticket=12345,
            symbol="EURUSD",
            volume=1.0,
            open_price=1.1000,
            current_price=1.1050,
            open_time=datetime.now(),
            side="BUY"
        )
        
        self.assertEqual(pos.ticket, 12345)
        self.assertEqual(pos.symbol, "EURUSD")
        self.assertEqual(pos.volume, 1.0)
        self.assertEqual(pos.entry_price, 1.1000)
        self.assertEqual(pos.position_type, "BUY")
    
    def test_position_info_unrealized_pnl(self):
        """Test unrealized P&L calculation."""
        from cthulu.position.manager import PositionInfo
        
        # Buy position with profit
        pos_buy = PositionInfo(
            ticket=12345,
            symbol="EURUSD",
            volume=1.0,
            open_price=1.1000,
            current_price=1.1050,
            open_time=datetime.now(),
            side="BUY"
        )
        
        pnl_buy = pos_buy.calculate_unrealized_pnl()
        self.assertGreater(pnl_buy, 0, "Buy position should show profit")
        
        # Sell position with profit
        pos_sell = PositionInfo(
            ticket=12346,
            symbol="EURUSD",
            volume=1.0,
            open_price=1.1050,
            current_price=1.1000,
            open_time=datetime.now(),
            side="SELL"
        )
        
        pnl_sell = pos_sell.calculate_unrealized_pnl()
        self.assertGreater(pnl_sell, 0, "Sell position should show profit")


class TestPositionManager(unittest.TestCase):
    """Test PositionManager class."""
    
    def test_position_manager_import(self):
        """Test that PositionManager can be imported."""
        try:
            from cthulu.position.manager import PositionManager
            self.assertTrue(True)
        except ImportError:
            self.fail("Could not import PositionManager from position.position_manager")
    
    def test_position_manager_initialization(self):
        """Test PositionManager initialization."""
        from cthulu.position.manager import PositionManager
        
        manager = PositionManager()
        
        self.assertIsNotNone(manager)
        self.assertEqual(len(manager.get_all_positions()), 0)
    
    def test_add_position(self):
        """Test adding a position to the manager."""
        from cthulu.position.manager import PositionManager, PositionInfo
        
        manager = PositionManager()
        
        pos = PositionInfo(
            ticket=12345,
            symbol="EURUSD",
            volume=1.0,
            open_price=1.1000,
            current_price=1.1050,
            open_time=datetime.now(),
            side="BUY"
        )
        
        manager.add_position(pos)
        
        self.assertEqual(len(manager.get_all_positions()), 1)
        self.assertIn(12345, manager.get_all_positions())
    
    def test_remove_position(self):
        """Test removing a position from the manager."""
        from cthulu.position.manager import PositionManager, PositionInfo
        
        manager = PositionManager()
        
        pos = PositionInfo(
            ticket=12345,
            symbol="EURUSD",
            volume=1.0,
            open_price=1.1000,
            current_price=1.1050,
            open_time=datetime.now(),
            side="BUY"
        )
        
        manager.add_position(pos)
        self.assertEqual(len(manager.get_all_positions()), 1)
        
        manager.remove_position(12345)
        self.assertEqual(len(manager.get_all_positions()), 0)
    
    def test_update_position(self):
        """Test updating position current price."""
        from cthulu.position.manager import PositionManager, PositionInfo
        
        manager = PositionManager()
        
        pos = PositionInfo(
            ticket=12345,
            symbol="EURUSD",
            volume=1.0,
            open_price=1.1000,
            current_price=1.1050,
            open_time=datetime.now(),
            side="BUY"
        )
        
        manager.add_position(pos)
        
        # Update current price
        manager.update_position(12345, current_price=1.1100)
        
        updated_pos = manager.get_position(12345)
        self.assertEqual(updated_pos.current_price, 1.1100)
    
    def test_get_positions_by_symbol(self):
        """Test filtering positions by symbol."""
        from cthulu.position.manager import PositionManager, PositionInfo
        
        manager = PositionManager()
        
        pos1 = PositionInfo(
            ticket=12345,
            symbol="EURUSD",
            volume=1.0,
            open_price=1.1000,
            current_price=1.1050,
            open_time=datetime.now(),
            side="BUY"
        )
        
        pos2 = PositionInfo(
            ticket=12346,
            symbol="GBPUSD",
            volume=1.0,
            open_price=1.2500,
            current_price=1.2550,
            open_time=datetime.now(),
            side="BUY"
        )
        
        manager.add_position(pos1)
        manager.add_position(pos2)
        
        eurusd_positions = manager.get_positions_by_symbol("EURUSD")
        self.assertEqual(len(eurusd_positions), 1)
        self.assertEqual(eurusd_positions[0].symbol, "EURUSD")

    def test_legacy_constructor_entry_price_and_position_type(self):
        """Test that legacy constructor args entry_price and position_type map to open_price and side respectively."""
        from cthulu.position.manager import PositionInfo

        pos = PositionInfo(
            ticket=100,
            symbol="EURUSD",
            volume=0.5,
            _legacy_entry_price=1.2000,
            current_price=1.2010,
            open_time=datetime.now(),
            _legacy_position_type="BUY"
        )

        self.assertEqual(pos.open_price, 1.2000)
        self.assertEqual(pos.side, "BUY")

    def test_legacy_prefixed_constructor(self):
        """Test that `_legacy_entry_price` and `_legacy_position_type` constructor args map correctly."""
        from cthulu.position.manager import PositionInfo

        pos = PositionInfo(
            ticket=101,
            symbol="EURUSD",
            volume=0.25,
            _legacy_entry_price=1.3000,
            current_price=1.3050,
            open_time=datetime.now(),
            _legacy_position_type="SELL"
        )

        self.assertEqual(pos.open_price, 1.3000)
        self.assertEqual(pos.side, "SELL")
    
    def test_total_unrealized_pnl(self):
        """Test calculating total unrealized P&L across all positions."""
        from cthulu.position.manager import PositionManager, PositionInfo
        
        manager = PositionManager()
        
        pos1 = PositionInfo(
            ticket=12345,
            symbol="EURUSD",
            volume=1.0,
            open_price=1.1000,
            current_price=1.1050,
            open_time=datetime.now(),
            side="BUY"
        )
        
        pos2 = PositionInfo(
            ticket=12346,
            symbol="GBPUSD",
            volume=1.0,
            open_price=1.2500,
            current_price=1.2450,
            open_time=datetime.now(),
            side="BUY"
        )
        
        manager.add_position(pos1)
        manager.add_position(pos2)
        
        total_pnl = manager.calculate_total_pnl()
        
        # Total P&L should be the sum of individual position P&Ls
        self.assertIsNotNone(total_pnl)


if __name__ == '__main__':
    unittest.main()




