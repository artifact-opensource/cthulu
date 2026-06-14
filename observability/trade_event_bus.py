"""
Trade Event Bus - Centralized Non-Blocking Trade Event Collection

Provides a unified, thread-safe event bus for collecting all trade-related events
from multiple sources:
- System trades (Cthulu's own signals)
- RPC trades (external API calls)
- Adopted trades (user's manual trades taken over by Cthulu)

All events are collected non-blocking and dispatched to multiple consumers:
- MetricsCollector (performance tracking)
- ComprehensiveMetricsCollector (real-time metrics)
- TrainingDataLogger (ML training data)
- Database (persistence)

Part of Cthulu Observability v6.0.0
"""

from __future__ import annotations
import logging
import threading
import time
from queue import Queue, Empty
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable
from enum import Enum

logger = logging.getLogger('cthulu.observability.event_bus')


class TradeEventType(Enum):
    """Types of trade events"""
    # Entry events
    TRADE_OPENED = "trade_opened"
    TRADE_ADOPTED = "trade_adopted"  # External trade brought under management
    
    # Management events
    TRADE_MODIFIED = "trade_modified"
    TRADE_SCALED = "trade_scaled"  # Partial close
    SL_TP_UPDATED = "sl_tp_updated"
    
    # Exit events
    TRADE_CLOSED = "trade_closed"
    TRADE_STOPPED_OUT = "trade_stopped_out"
    TRADE_TP_HIT = "trade_tp_hit"
    
    # Signal events
    SIGNAL_GENERATED = "signal_generated"
    SIGNAL_APPROVED = "signal_approved"
    SIGNAL_REJECTED = "signal_rejected"
    
    # Risk events
    RISK_LIMIT_HIT = "risk_limit_hit"
    DRAWDOWN_EVENT = "drawdown_event"
    
    # System events
    POSITION_RECONCILED = "position_reconciled"
    CONNECTION_EVENT = "connection_event"


@dataclass
class TradeEvent:
    """Unified trade event structure"""
    event_type: TradeEventType
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Core trade data
    ticket: Optional[int] = None
    symbol: str = ""
    side: str = ""  # BUY or SELL
    volume: float = 0.0
    price: float = 0.0
    
    # P&L data
    pnl: float = 0.0
    pnl_pct: float = 0.0
    
    # SL/TP
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    
    # Source tracking
    source: str = "system"  # system, rpc, adopted, manual
    strategy: str = ""
    signal_id: str = ""
    
    # Risk/reward tracking
    risk_amount: Optional[float] = None
    reward_amount: Optional[float] = None
    
    # Context
    account_balance: float = 0.0
    equity: float = 0.0
    
    # Indicators at event time
    indicators: Dict[str, float] = field(default_factory=dict)
    
    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Trade duration (for closed trades)
    duration_seconds: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        d = asdict(self)
        d['event_type'] = self.event_type.value
        d['timestamp'] = self.timestamp.isoformat()
        return d


class TradeEventBus:
    """
    Non-blocking event bus for trade events.
    
    Uses a background thread to process events, ensuring the main trading loop
    is never blocked by metrics collection or database writes.
    
    Thread-safe for multiple producers (trading loop, RPC server, adoption manager).
    """
    
    def __init__(self, queue_size: int = 10000, flush_interval: float = 1.0):
        """
        Initialize the event bus.
        
        Args:
            queue_size: Maximum events to queue before dropping
            flush_interval: Seconds between batch flushes
        """
        self._queue: Queue[TradeEvent] = Queue(maxsize=queue_size)
        self._subscribers: Dict[str, Callable[[TradeEvent], None]] = {}
        self._batch_subscribers: Dict[str, Callable[[List[TradeEvent]], None]] = {}
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._flush_interval = flush_interval
        
        # Stats
        self._events_processed = 0
        self._events_dropped = 0
        self._errors_count = 0
        self._lock = threading.Lock()
        
        logger.info("TradeEventBus initialized")
    
    def start(self) -> None:
        """Start the background event processor"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(
            target=self._process_loop,
            name="trade-event-bus",
            daemon=True
        )
        self._thread.start()
        logger.info("TradeEventBus started")
    
    def stop(self, timeout: float = 5.0) -> None:
        """Stop the event processor gracefully"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        logger.info(f"TradeEventBus stopped. Processed: {self._events_processed}, Dropped: {self._events_dropped}")
    
    def subscribe(self, name: str, callback: Callable[[TradeEvent], None]) -> None:
        """
        Subscribe to individual events.
        
        Args:
            name: Subscriber name (for logging/debugging)
            callback: Function to call for each event
        """
        with self._lock:
            self._subscribers[name] = callback
            logger.info(f"Subscriber registered: {name}")
    
    def subscribe_batch(self, name: str, callback: Callable[[List[TradeEvent]], None]) -> None:
        """
        Subscribe to batch events (more efficient for bulk processing).
        
        Args:
            name: Subscriber name
            callback: Function to call with batch of events
        """
        with self._lock:
            self._batch_subscribers[name] = callback
            logger.info(f"Batch subscriber registered: {name}")
    
    def unsubscribe(self, name: str) -> None:
        """Unsubscribe from events"""
        with self._lock:
            self._subscribers.pop(name, None)
            self._batch_subscribers.pop(name, None)
    
    def publish(self, event: TradeEvent) -> bool:
        """
        Publish an event (non-blocking).
        
        Args:
            event: Trade event to publish
            
        Returns:
            True if queued, False if dropped
        """
        try:
            self._queue.put_nowait(event)
            return True
        except Exception:
            with self._lock:
                self._events_dropped += 1
            return False
    
    def publish_trade_opened(
        self,
        ticket: int,
        symbol: str,
        side: str,
        volume: float,
        price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        source: str = "system",
        strategy: str = "",
        signal_id: str = "",
        account_balance: float = 0.0,
        **kwargs
    ) -> bool:
        """Convenience method to publish trade opened event"""
        event = TradeEvent(
            event_type=TradeEventType.TRADE_OPENED,
            ticket=ticket,
            symbol=symbol,
            side=side,
            volume=volume,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            source=source,
            strategy=strategy,
            signal_id=signal_id,
            account_balance=account_balance,
            metadata=kwargs
        )
        return self.publish(event)
    
    def publish_trade_closed(
        self,
        ticket: int,
        symbol: str,
        side: str,
        volume: float,
        entry_price: float,
        exit_price: float,
        pnl: float,
        duration_seconds: float = 0.0,
        source: str = "system",
        exit_reason: str = "",
        account_balance: float = 0.0,
        risk_amount: Optional[float] = None,
        reward_amount: Optional[float] = None,
        **kwargs
    ) -> bool:
        """Convenience method to publish trade closed event"""
        pnl_pct = ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
        if side.upper() == "SELL":
            pnl_pct = -pnl_pct
        
        event = TradeEvent(
            event_type=TradeEventType.TRADE_CLOSED,
            ticket=ticket,
            symbol=symbol,
            side=side,
            volume=volume,
            price=exit_price,
            pnl=pnl,
            pnl_pct=pnl_pct,
            source=source,
            duration_seconds=duration_seconds,
            account_balance=account_balance,
            risk_amount=risk_amount,
            reward_amount=reward_amount,
            metadata={'entry_price': entry_price, 'exit_reason': exit_reason, **kwargs}
        )
        return self.publish(event)
    
    def publish_trade_adopted(
        self,
        ticket: int,
        symbol: str,
        side: str,
        volume: float,
        price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        **kwargs
    ) -> bool:
        """Convenience method to publish trade adopted event"""
        event = TradeEvent(
            event_type=TradeEventType.TRADE_ADOPTED,
            ticket=ticket,
            symbol=symbol,
            side=side,
            volume=volume,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            source="adopted",
            metadata=kwargs
        )
        return self.publish(event)
    
    def publish_signal(
        self,
        event_type: TradeEventType,
        symbol: str,
        side: str,
        confidence: float,
        strategy: str,
        signal_id: str = "",
        reason: str = "",
        indicators: Optional[Dict[str, float]] = None,
        **kwargs
    ) -> bool:
        """Convenience method to publish signal events"""
        event = TradeEvent(
            event_type=event_type,
            symbol=symbol,
            side=side,
            source="system",
            strategy=strategy,
            signal_id=signal_id,
            indicators=indicators or {},
            metadata={'confidence': confidence, 'reason': reason, **kwargs}
        )
        return self.publish(event)
    
    def _process_loop(self) -> None:
        """Background event processing loop"""
        batch: List[TradeEvent] = []
        last_flush = time.time()
        
        while self._running:
            try:
                # Get events with timeout
                try:
                    event = self._queue.get(timeout=self._flush_interval)
                    batch.append(event)
                except Empty:
                    pass
                
                # Flush batch if interval elapsed or batch is large enough
                now = time.time()
                if batch and (len(batch) >= 100 or (now - last_flush) >= self._flush_interval):
                    self._dispatch_batch(batch)
                    batch = []
                    last_flush = now
                    
            except Exception as e:
                logger.error(f"Error in event processing loop: {e}")
                with self._lock:
                    self._errors_count += 1
        
        # Final flush on shutdown
        if batch:
            self._dispatch_batch(batch)
    
    def _dispatch_batch(self, batch: List[TradeEvent]) -> None:
        """Dispatch a batch of events to subscribers"""
        if not batch:
            return
        
        with self._lock:
            subscribers = dict(self._subscribers)
            batch_subscribers = dict(self._batch_subscribers)
        
        # Dispatch to individual subscribers
        for name, callback in subscribers.items():
            for event in batch:
                try:
                    callback(event)
                except Exception as e:
                    logger.error(f"Subscriber {name} error: {e}")
        
        # Dispatch to batch subscribers
        for name, callback in batch_subscribers.items():
            try:
                callback(batch)
            except Exception as e:
                logger.error(f"Batch subscriber {name} error: {e}")
        
        with self._lock:
            self._events_processed += len(batch)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get event bus statistics"""
        with self._lock:
            return {
                'events_processed': self._events_processed,
                'events_dropped': self._events_dropped,
                'errors_count': self._errors_count,
                'queue_size': self._queue.qsize(),
                'subscribers': list(self._subscribers.keys()),
                'batch_subscribers': list(self._batch_subscribers.keys()),
                'running': self._running
            }


# ============================================================================
# Subscriber Adapters - Connect event bus to existing collectors
# ============================================================================

class MetricsCollectorSubscriber:
    """Adapter to feed events to MetricsCollector"""
    
    def __init__(self, metrics_collector):
        self.metrics = metrics_collector
        self.logger = logging.getLogger('cthulu.event_bus.metrics_subscriber')
    
    def on_event(self, event: TradeEvent) -> None:
        """Process a trade event"""
        try:
            if event.event_type == TradeEventType.TRADE_OPENED:
                self.metrics.record_position_opened(event.symbol)
            
            elif event.event_type == TradeEventType.TRADE_CLOSED:
                # Record trade with P&L
                self.metrics.record_trade(
                    profit=event.pnl,
                    symbol=event.symbol,
                    risk=event.risk_amount,
                    reward=event.reward_amount
                )
                self.metrics.record_position_closed(event.symbol)
            
            elif event.event_type == TradeEventType.TRADE_ADOPTED:
                self.metrics.record_position_opened(event.symbol)
                self.logger.info(f"Adopted trade recorded: {event.ticket} {event.symbol}")
            
            elif event.event_type == TradeEventType.TRADE_SCALED:
                # Partial close - record partial P&L
                if event.pnl != 0:
                    self.metrics.record_trade(
                        profit=event.pnl,
                        symbol=event.symbol
                    )
                    
        except Exception as e:
            self.logger.error(f"Error processing event in metrics subscriber: {e}")


class ComprehensiveCollectorSubscriber:
    """Adapter to feed events to ComprehensiveMetricsCollector"""
    
    def __init__(self, comprehensive_collector):
        self.collector = comprehensive_collector
        self.logger = logging.getLogger('cthulu.event_bus.comprehensive_subscriber')
    
    def on_event(self, event: TradeEvent) -> None:
        """Process a trade event"""
        try:
            if event.event_type == TradeEventType.TRADE_CLOSED:
                is_win = event.pnl > 0
                self.collector.record_trade_completed(
                    is_win=is_win,
                    pnl=event.pnl,
                    duration_seconds=event.duration_seconds
                )
            
            elif event.event_type in (TradeEventType.TRADE_OPENED, TradeEventType.TRADE_ADOPTED):
                # Update position count
                pass  # Will be synced from position manager
            
            elif event.event_type == TradeEventType.SIGNAL_GENERATED:
                self.collector.increment_signal_counter(event.strategy)
            
            elif event.event_type == TradeEventType.SIGNAL_REJECTED:
                reason = event.metadata.get('reason', 'unknown')
                self.collector.increment_rejection_counter(reason)
                
        except Exception as e:
            self.logger.error(f"Error in comprehensive subscriber: {e}")


class TrainingDataSubscriber:
    """Adapter to feed events to TrainingDataLogger"""
    
    def __init__(self, training_logger=None):
        self.training_logger = training_logger
        self.logger = logging.getLogger('cthulu.event_bus.training_subscriber')
        self._pending_trades: Dict[int, TradeEvent] = {}
    
    def on_event(self, event: TradeEvent) -> None:
        """Process a trade event for training data"""
        try:
            if event.event_type == TradeEventType.TRADE_OPENED:
                # Store for later outcome matching
                if event.ticket:
                    self._pending_trades[event.ticket] = event
            
            elif event.event_type == TradeEventType.TRADE_CLOSED:
                if self.training_logger and event.ticket:
                    # Log outcome
                    outcome = "WIN" if event.pnl > 0 else "LOSS" if event.pnl < 0 else "BREAKEVEN"
                    self.training_logger.log_outcome(
                        ticket=event.ticket,
                        outcome=outcome,
                        pnl=event.pnl,
                        exit_price=event.price,
                        max_favorable=event.metadata.get('max_favorable', 0),
                        max_adverse=event.metadata.get('max_adverse', 0)
                    )
                    # Remove from pending
                    self._pending_trades.pop(event.ticket, None)
                    
        except Exception as e:
            self.logger.error(f"Error in training subscriber: {e}")


class DatabaseSubscriber:
    """Adapter to persist events to database"""
    
    def __init__(self, database):
        self.database = database
        self.logger = logging.getLogger('cthulu.event_bus.database_subscriber')
    
    def on_batch(self, events: List[TradeEvent]) -> None:
        """Process a batch of events for persistence"""
        for event in events:
            try:
                if event.event_type == TradeEventType.TRADE_CLOSED:
                    # Update trade exit in database
                    self.database.update_trade_exit(
                        order_id=event.ticket,
                        exit_price=event.price,
                        exit_time=event.timestamp,
                        profit=event.pnl,
                        exit_reason=event.metadata.get('exit_reason', '')
                    )
                    
            except Exception as e:
                self.logger.error(f"Error persisting event to database: {e}")


class MLDataCollectorSubscriber:
    """Adapter to feed events to ML instrumentation collector"""
    
    def __init__(self, ml_collector):
        self.ml_collector = ml_collector
        self.logger = logging.getLogger('cthulu.event_bus.ml_subscriber')
    
    def on_event(self, event: TradeEvent) -> None:
        """Process a trade event for ML data collection"""
        try:
            event_data = event.to_dict()
            
            if event.event_type == TradeEventType.TRADE_OPENED:
                self.ml_collector.record_event('trade_opened', event_data)
            
            elif event.event_type == TradeEventType.TRADE_CLOSED:
                self.ml_collector.record_event('trade_closed', event_data)
            
            elif event.event_type == TradeEventType.TRADE_ADOPTED:
                self.ml_collector.record_event('trade_adopted', event_data)
            
            elif event.event_type == TradeEventType.SIGNAL_GENERATED:
                self.ml_collector.record_event('signal', event_data)
                
        except Exception as e:
            self.logger.error(f"Error in ML subscriber: {e}")


# ============================================================================
# Global singleton
# ============================================================================

_event_bus: Optional[TradeEventBus] = None


def get_event_bus() -> TradeEventBus:
    """Get or create the global event bus singleton"""
    global _event_bus
    if _event_bus is None:
        _event_bus = TradeEventBus()
        _event_bus.start()
    return _event_bus


def initialize_event_bus(
    metrics_collector=None,
    comprehensive_collector=None,
    training_logger=None,
    database=None,
    ml_collector=None
) -> TradeEventBus:
    """
    Initialize the event bus with all collectors.
    
    Call this during system startup to wire up all metrics collection.
    """
    bus = get_event_bus()
    
    if metrics_collector:
        subscriber = MetricsCollectorSubscriber(metrics_collector)
        bus.subscribe('metrics', subscriber.on_event)
    
    if comprehensive_collector:
        subscriber = ComprehensiveCollectorSubscriber(comprehensive_collector)
        bus.subscribe('comprehensive', subscriber.on_event)
    
    if training_logger:
        subscriber = TrainingDataSubscriber(training_logger)
        bus.subscribe('training', subscriber.on_event)
    
    if database:
        subscriber = DatabaseSubscriber(database)
        bus.subscribe_batch('database', subscriber.on_batch)
    
    if ml_collector:
        subscriber = MLDataCollectorSubscriber(ml_collector)
        bus.subscribe('ml_collector', subscriber.on_event)
    
    logger.info(f"Event bus initialized with subscribers: {bus.get_stats()['subscribers']}")
    return bus


def publish_trade_opened(**kwargs) -> bool:
    """Convenience function to publish trade opened event"""
    return get_event_bus().publish_trade_opened(**kwargs)


def publish_trade_closed(**kwargs) -> bool:
    """Convenience function to publish trade closed event"""
    return get_event_bus().publish_trade_closed(**kwargs)


def publish_trade_adopted(**kwargs) -> bool:
    """Convenience function to publish trade adopted event"""
    return get_event_bus().publish_trade_adopted(**kwargs)


def publish_signal(**kwargs) -> bool:
    """Convenience function to publish signal event"""
    return get_event_bus().publish_signal(**kwargs)
