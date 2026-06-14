"""
Trade Monitor Module

Monitors active trades and records snapshots for ML training data.
Also integrates with news events to pause trading during high-impact events.
"""

import threading
import time
import logging
from typing import Optional, Any, Dict, List
from datetime import datetime


class TradeMonitor:
    """
    Trade monitor that periodically scans positions and records snapshots.
    
    Features:
    - Position snapshot recording for ML training
    - News event integration for trade pausing
    - Configurable polling interval
    """
    
    def __init__(
        self,
        position_manager: Any = None,
        position_lifecycle: Any = None,
        trade_manager: Any = None,
        poll_interval: float = 5.0,
        ml_collector: Any = None,
        news_manager: Any = None,
        news_alert_window: int = 300
    ):
        """
        Initialize trade monitor.
        
        Args:
            position_manager: Position manager or tracker instance
            position_lifecycle: Position lifecycle manager (optional)
            trade_manager: Trade manager for pausing (optional)
            poll_interval: Scan interval in seconds
            ml_collector: ML data collector for recording events
            news_manager: News manager for event fetching (optional)
            news_alert_window: Pause duration in seconds for high-impact news
        """
        self.position_manager = position_manager
        self.position_lifecycle = position_lifecycle
        self.trade_manager = trade_manager
        self.poll_interval = poll_interval
        self.ml_collector = ml_collector
        self.news_manager = news_manager
        self.news_alert_window = news_alert_window
        
        self.logger = logging.getLogger(__name__)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_news_check = 0
        self._news_check_interval = 60  # Check news every 60 seconds
        
    def start(self):
        """Start the monitoring thread."""
        if self._running:
            return
            
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        self.logger.info(f"TradeMonitor started (poll_interval={self.poll_interval}s)")
        
    def stop(self):
        """Stop the monitoring thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        self.logger.info("TradeMonitor stopped")
        
    def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                self._scan_and_record()
            except Exception as e:
                self.logger.error(f"TradeMonitor scan error: {e}")
            
            time.sleep(self.poll_interval)
            
    def _scan_and_record(self):
        """Scan positions and record snapshots."""
        # Check news events first (news alerts should be handled regardless of open positions)
        if self.news_manager and time.time() - self._last_news_check > self._news_check_interval:
            self._check_news_events()
            self._last_news_check = time.time()

        # Get positions from position manager
        positions = self._get_positions()

        # Record position snapshots
        for ticket, pos in positions.items():
            self._record_position_snapshot(pos)
            
    def _get_positions(self) -> Dict[int, Any]:
        """Get positions from position manager."""
        if not self.position_manager:
            return {}
            
        # Try different position access methods
        if hasattr(self.position_manager, '_positions'):
            return self.position_manager._positions
        elif hasattr(self.position_manager, 'get_all_positions'):
            return self.position_manager.get_all_positions()
        elif hasattr(self.position_manager, 'positions'):
            return self.position_manager.positions
            
        return {}
        
    def _record_position_snapshot(self, position: Any):
        """Record a position snapshot to ML collector."""
        if not self.ml_collector:
            return
            
        try:
            snapshot = {
                'ticket': getattr(position, 'ticket', 0),
                'symbol': getattr(position, 'symbol', 'UNKNOWN'),
                'volume': getattr(position, 'volume', 0.0),
                'stop_loss': getattr(position, 'stop_loss', 0.0),
                'take_profit': getattr(position, 'take_profit', 0.0),
                'unrealized_pnl': getattr(position, 'unrealized_pnl', 0.0),
                'open_price': getattr(position, 'open_price', 0.0),
                'current_price': getattr(position, 'current_price', 0.0),
                'side': getattr(position, 'side', 'UNKNOWN'),
                'timestamp': datetime.now().isoformat()
            }
            
            if hasattr(self.ml_collector, 'record_event'):
                self.ml_collector.record_event('monitor.position_snapshot', snapshot)
            elif hasattr(self.ml_collector, 'record_position_snapshot'):
                self.ml_collector.record_position_snapshot(snapshot)
        except Exception as e:
            self.logger.debug(f"Failed to record position snapshot: {e}")
            
    def _check_news_events(self):
        """Check for high-impact news events and pause trading if needed."""
        if not self.news_manager:
            return
            
        try:
            events = self.news_manager.fetch_recent()
            if not events:
                return
                
            for event in events:
                importance = None
                if hasattr(event, 'meta') and isinstance(event.meta, dict):
                    importance = event.meta.get('importance', '')
                elif hasattr(event, 'importance'):
                    importance = event.importance
                    
                if importance and str(importance).lower() == 'high':
                    self._handle_high_impact_news(event)
                    
        except Exception as e:
            self.logger.debug(f"News check error: {e}")
            
    def _handle_high_impact_news(self, event: Any):
        """Handle high-impact news event."""
        # Record to ML collector
        if self.ml_collector:
            try:
                event_data = {
                    'provider': getattr(event, 'provider', 'unknown'),
                    'headline': getattr(event, 'headline', ''),
                    'timestamp': getattr(event, 'ts', time.time()),
                    'symbol': getattr(event, 'symbol', ''),
                    'importance': 'high'
                }
                if hasattr(self.ml_collector, 'record_event'):
                    self.ml_collector.record_event('monitor.news_alert', event_data)
            except Exception:
                pass
                
        # Pause trading if trade manager available
        if self.trade_manager and hasattr(self.trade_manager, 'pause_trading'):
            try:
                self.trade_manager.pause_trading(self.news_alert_window)
                self.logger.warning(
                    f"Trading paused for {self.news_alert_window}s due to high-impact news: "
                    f"{getattr(event, 'headline', 'Unknown')}"
                )
            except Exception as e:
                self.logger.error(f"Failed to pause trading: {e}")
