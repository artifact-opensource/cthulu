"""
Unit tests for Trade Event Bus

Tests the non-blocking event collection system that unifies trade metrics
from system trades, RPC trades, and adopted trades.
"""

import pytest
import time
import threading
from datetime import datetime
from unittest.mock import MagicMock, patch


class TestTradeEventBus:
    """Tests for TradeEventBus"""
    
    def test_event_bus_initialization(self):
        """Test event bus initializes correctly"""
        from observability.trade_event_bus import TradeEventBus
        
        bus = TradeEventBus(queue_size=100)
        assert bus._queue.maxsize == 100
        assert bus._running == False
        assert bus._events_processed == 0
    
    def test_event_bus_start_stop(self):
        """Test event bus can start and stop"""
        from observability.trade_event_bus import TradeEventBus
        
        bus = TradeEventBus()
        bus.start()
        assert bus._running == True
        assert bus._thread is not None
        assert bus._thread.is_alive()
        
        bus.stop(timeout=2.0)
        assert bus._running == False
    
    def test_publish_trade_opened(self):
        """Test publishing a trade opened event"""
        from observability.trade_event_bus import TradeEventBus, TradeEventType
        
        bus = TradeEventBus()
        bus.start()
        
        try:
            events_received = []
            
            def callback(event):
                events_received.append(event)
            
            bus.subscribe('test', callback)
            
            result = bus.publish_trade_opened(
                ticket=12345,
                symbol='EURUSD',
                side='BUY',
                volume=0.1,
                price=1.1234,
                stop_loss=1.1200,
                take_profit=1.1300,
                source='system',
                strategy='test_strategy'
            )
            
            assert result == True
            
            # Wait for event to be processed
            time.sleep(2.0)
            
            assert len(events_received) >= 1
            event = events_received[0]
            assert event.event_type == TradeEventType.TRADE_OPENED
            assert event.ticket == 12345
            assert event.symbol == 'EURUSD'
            assert event.side == 'BUY'
            assert event.source == 'system'
        finally:
            bus.stop()
    
    def test_publish_trade_closed(self):
        """Test publishing a trade closed event"""
        from observability.trade_event_bus import TradeEventBus, TradeEventType
        
        bus = TradeEventBus()
        bus.start()
        
        try:
            events_received = []
            
            def callback(event):
                events_received.append(event)
            
            bus.subscribe('test', callback)
            
            result = bus.publish_trade_closed(
                ticket=12345,
                symbol='EURUSD',
                side='BUY',
                volume=0.1,
                entry_price=1.1234,
                exit_price=1.1300,
                pnl=6.60,
                duration_seconds=3600,
                exit_reason='TP hit'
            )
            
            assert result == True
            
            # Wait for event to be processed
            time.sleep(2.0)
            
            assert len(events_received) >= 1
            event = events_received[0]
            assert event.event_type == TradeEventType.TRADE_CLOSED
            assert event.pnl == 6.60
        finally:
            bus.stop()
    
    def test_publish_trade_adopted(self):
        """Test publishing an adopted trade event"""
        from observability.trade_event_bus import TradeEventBus, TradeEventType
        
        bus = TradeEventBus()
        bus.start()
        
        try:
            events_received = []
            
            def callback(event):
                events_received.append(event)
            
            bus.subscribe('test', callback)
            
            result = bus.publish_trade_adopted(
                ticket=99999,
                symbol='XAUUSD',
                side='SELL',
                volume=0.05,
                price=2050.50
            )
            
            assert result == True
            
            # Wait for event to be processed
            time.sleep(2.0)
            
            assert len(events_received) >= 1
            event = events_received[0]
            assert event.event_type == TradeEventType.TRADE_ADOPTED
            assert event.source == 'adopted'
        finally:
            bus.stop()
    
    def test_multiple_subscribers(self):
        """Test multiple subscribers receive events"""
        from observability.trade_event_bus import TradeEventBus
        
        bus = TradeEventBus()
        bus.start()
        
        try:
            events_1 = []
            events_2 = []
            
            def callback_1(event):
                events_1.append(event)
            
            def callback_2(event):
                events_2.append(event)
            
            bus.subscribe('sub1', callback_1)
            bus.subscribe('sub2', callback_2)
            
            bus.publish_trade_opened(
                ticket=111,
                symbol='TEST',
                side='BUY',
                volume=0.1,
                price=100.0
            )
            
            time.sleep(2.0)
            
            assert len(events_1) >= 1
            assert len(events_2) >= 1
        finally:
            bus.stop()
    
    def test_batch_subscriber(self):
        """Test batch subscriber receives batches"""
        from observability.trade_event_bus import TradeEventBus
        
        bus = TradeEventBus(flush_interval=0.5)
        bus.start()
        
        try:
            batches = []
            
            def batch_callback(batch):
                batches.append(batch)
            
            bus.subscribe_batch('batch_test', batch_callback)
            
            # Publish multiple events
            for i in range(5):
                bus.publish_trade_opened(
                    ticket=i,
                    symbol='TEST',
                    side='BUY',
                    volume=0.1,
                    price=100.0 + i
                )
            
            time.sleep(2.0)
            
            # Should have received at least one batch
            assert len(batches) >= 1
            total_events = sum(len(b) for b in batches)
            assert total_events == 5
        finally:
            bus.stop()
    
    def test_get_stats(self):
        """Test get_stats returns correct information"""
        from observability.trade_event_bus import TradeEventBus
        
        bus = TradeEventBus()
        bus.start()
        
        try:
            bus.subscribe('test', lambda e: None)
            
            stats = bus.get_stats()
            
            assert 'events_processed' in stats
            assert 'events_dropped' in stats
            assert 'subscribers' in stats
            assert 'running' in stats
            assert stats['running'] == True
            assert 'test' in stats['subscribers']
        finally:
            bus.stop()
    
    def test_metrics_collector_subscriber(self):
        """Test MetricsCollectorSubscriber integration"""
        from observability.trade_event_bus import (
            TradeEventBus, TradeEvent, TradeEventType, MetricsCollectorSubscriber
        )
        
        # Create mock metrics collector
        mock_metrics = MagicMock()
        subscriber = MetricsCollectorSubscriber(mock_metrics)
        
        # Test trade opened event
        event = TradeEvent(
            event_type=TradeEventType.TRADE_OPENED,
            ticket=123,
            symbol='EURUSD'
        )
        subscriber.on_event(event)
        mock_metrics.record_position_opened.assert_called_once_with('EURUSD')
        
        # Test trade closed event
        mock_metrics.reset_mock()
        event = TradeEvent(
            event_type=TradeEventType.TRADE_CLOSED,
            ticket=123,
            symbol='EURUSD',
            pnl=10.0
        )
        subscriber.on_event(event)
        mock_metrics.record_trade.assert_called_once()
        mock_metrics.record_position_closed.assert_called_once_with('EURUSD')
    
    def test_non_blocking_behavior(self):
        """Test that publishing is non-blocking"""
        from observability.trade_event_bus import TradeEventBus
        
        bus = TradeEventBus()
        bus.start()
        
        try:
            # Add a slow subscriber
            def slow_callback(event):
                time.sleep(0.5)
            
            bus.subscribe('slow', slow_callback)
            
            # Measure time to publish multiple events
            start = time.time()
            for i in range(10):
                bus.publish_trade_opened(
                    ticket=i,
                    symbol='TEST',
                    side='BUY',
                    volume=0.1,
                    price=100.0
                )
            elapsed = time.time() - start
            
            # Should complete quickly (non-blocking)
            assert elapsed < 0.1, f"Publishing took {elapsed}s, expected < 0.1s"
        finally:
            bus.stop()


class TestGlobalEventBus:
    """Tests for global event bus singleton"""
    
    def test_get_event_bus_singleton(self):
        """Test get_event_bus returns singleton"""
        from observability.trade_event_bus import get_event_bus
        
        bus1 = get_event_bus()
        bus2 = get_event_bus()
        
        assert bus1 is bus2
    
    def test_convenience_functions(self):
        """Test convenience publish functions"""
        from observability.trade_event_bus import (
            get_event_bus, publish_trade_opened, publish_trade_closed
        )
        
        bus = get_event_bus()
        if not bus._running:
            bus.start()
        
        # These should not raise
        result1 = publish_trade_opened(
            ticket=1, symbol='TEST', side='BUY', volume=0.1, price=100.0
        )
        result2 = publish_trade_closed(
            ticket=1, symbol='TEST', side='BUY', volume=0.1,
            entry_price=100.0, exit_price=101.0, pnl=1.0
        )
        
        assert result1 == True
        assert result2 == True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
