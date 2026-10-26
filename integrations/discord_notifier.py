"""
Discord Notification System for Cthulu Trading System

Provides rich, formatted notifications to Discord webhooks for:
- Alerts: Trade executions, risk alerts, system health, adoption events
- Health: Session summaries, model performance, portfolio snapshots
- Signals: Signal quality, regime changes, milestone events

Part of Cthulu Observability v6.0.0
"""

from __future__ import annotations
import os
import json
import time
import logging
import threading
import queue
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
import urllib.request
import urllib.error

logger = logging.getLogger('cthulu.discord_notifier')


class NotificationChannel(Enum):
    """Discord notification channels"""
    ALERTS = "alerts"       # Trade executions, risk, system health, adoptions
    HEALTH = "health"       # Session summaries, model performance, portfolio
    SIGNALS = "signals"     # Signal quality, regime changes, milestones


class NotificationPriority(Enum):
    """Notification priority levels"""
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class DiscordNotification:
    """Discord notification structure"""
    channel: NotificationChannel
    title: str
    description: str
    color: int = 0x00ff00  # Green default
    priority: NotificationPriority = NotificationPriority.MEDIUM
    timestamp: datetime = field(default_factory=datetime.utcnow)
    fields: List[Dict[str, Any]] = field(default_factory=list)
    footer: Optional[str] = None
    thumbnail_url: Optional[str] = None
    
    def to_embed(self) -> Dict[str, Any]:
        """Convert to Discord embed format"""
        embed = {
            "title": self.title,
            "description": self.description,
            "color": self.color,
            "timestamp": self.timestamp.isoformat(),
            "footer": {"text": self.footer or "Cthulu Trading System"}
        }
        
        if self.fields:
            embed["fields"] = self.fields
            
        if self.thumbnail_url:
            embed["thumbnail"] = {"url": self.thumbnail_url}
            
        return embed


# Color palette for notifications
class Colors:
    """Discord embed colors"""
    SUCCESS = 0x00FF00      # Green - profitable trades, healthy
    WARNING = 0xFFFF00      # Yellow - warnings, attention needed
    DANGER = 0xFF0000       # Red - losses, critical alerts
    INFO = 0x0099FF         # Blue - informational
    NEUTRAL = 0x808080      # Gray - neutral events
    GOLD = 0xFFD700         # Gold - milestones, achievements
    PURPLE = 0x9B59B6       # Purple - signals, predictions
    ORANGE = 0xFF8C00       # Orange - moderate warnings
    CYAN = 0x00FFFF         # Cyan - system events


class DiscordRateLimiter:
    """
    Rate limiter for Discord webhooks.
    
    Discord rate limits:
    - 30 requests per minute per webhook
    - 5 embeds per message
    """
    
    def __init__(self, max_requests: int = 25, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: List[float] = []
        self._lock = threading.Lock()
    
    def can_send(self) -> bool:
        """Check if we can send a request"""
        with self._lock:
            now = time.time()
            # Remove old timestamps
            self._timestamps = [ts for ts in self._timestamps 
                              if now - ts < self.window_seconds]
            return len(self._timestamps) < self.max_requests
    
    def record_request(self):
        """Record a sent request"""
        with self._lock:
            self._timestamps.append(time.time())
    
    def wait_time(self) -> float:
        """Get time to wait before next request"""
        with self._lock:
            if len(self._timestamps) < self.max_requests:
                return 0
            oldest = min(self._timestamps)
            return max(0, self.window_seconds - (time.time() - oldest))


class DiscordNotifier:
    """
    Non-blocking Discord notification system.
    
    Features:
    - Rate limiting to respect Discord API limits
    - Message batching for efficiency
    - Priority queue for critical alerts
    - Non-blocking background thread
    - Graceful degradation on webhook failures
    """
    
    def __init__(
        self,
        alerts_webhook: Optional[str] = None,
        health_webhook: Optional[str] = None,
        signals_webhook: Optional[str] = None,
        enabled: bool = True,
        batch_interval: float = 5.0,
        max_queue_size: int = 1000
    ):
        """
        Initialize Discord notifier.
        
        Args:
            alerts_webhook: Webhook URL for alerts channel
            health_webhook: Webhook URL for health channel  
            signals_webhook: Webhook URL for signals channel
            enabled: Enable/disable notifications
            batch_interval: Seconds between batch sends
            max_queue_size: Maximum pending notifications
        """
        # Load from env if not provided
        self.webhooks = {
            NotificationChannel.ALERTS: alerts_webhook or os.getenv('DISCORD_WEBHOOK_ALERTS', ''),
            NotificationChannel.HEALTH: health_webhook or os.getenv('DISCORD_WEBHOOK_HEALTH', ''),
            NotificationChannel.SIGNALS: signals_webhook or os.getenv('DISCORD_WEBHOOK_SIGNALS', ''),
        }
        
        self.enabled = enabled and any(self.webhooks.values())
        self.batch_interval = batch_interval
        
        # Rate limiters per channel
        self._rate_limiters = {
            channel: DiscordRateLimiter() for channel in NotificationChannel
        }
        
        # Notification queues per channel (priority-based)
        self._queues: Dict[NotificationChannel, queue.PriorityQueue] = {
            channel: queue.PriorityQueue(maxsize=max_queue_size) 
            for channel in NotificationChannel
        }
        
        # Stats
        self._stats = {
            'sent': 0,
            'failed': 0,
            'dropped': 0,
            'batched': 0
        }
        self._stats_lock = threading.Lock()
        
        # Background thread
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        if self.enabled:
            logger.info("Discord notifier initialized")
            for channel, webhook in self.webhooks.items():
                status = "ACTIVE" if webhook else "DISABLED"
                logger.info(f"  {channel.value}: {status}")
        else:
            logger.info("Discord notifier DISABLED (no webhooks configured)")
    
    def start(self) -> None:
        """Start the background notification thread"""
        if not self.enabled or self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(
            target=self._notification_loop,
            name="discord-notifier",
            daemon=True
        )
        self._thread.start()
        logger.info("Discord notification thread started")
    
    def stop(self, timeout: float = 10.0) -> None:
        """Stop the notification thread gracefully"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        logger.info(f"Discord notifier stopped. Stats: {self.get_stats()}")
    
    def notify(self, notification: DiscordNotification) -> bool:
        """
        Queue a notification (non-blocking).
        
        Args:
            notification: Notification to send
            
        Returns:
            True if queued, False if dropped
        """
        if not self.enabled:
            return False
            
        try:
            # Priority queue: lower number = higher priority (inverted)
            priority = -notification.priority.value
            item = (priority, time.time(), notification)
            self._queues[notification.channel].put_nowait(item)
            return True
        except queue.Full:
            with self._stats_lock:
                self._stats['dropped'] += 1
            return False
    
    # =========================================================================
    # Convenience Methods for Common Notifications
    # =========================================================================
    
    def notify_trade_opened(
        self,
        ticket: int,
        symbol: str,
        side: str,
        volume: float,
        price: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        source: str = "system"
    ) -> bool:
        """Notify trade opened"""
        emoji = "🟢" if side.upper() == "BUY" else "🔴"
        color = Colors.SUCCESS if side.upper() == "BUY" else Colors.DANGER
        
        fields = [
            {"name": "Symbol", "value": symbol, "inline": True},
            {"name": "Direction", "value": f"{emoji} {side.upper()}", "inline": True},
            {"name": "Volume", "value": f"{volume:.2f} lots", "inline": True},
            {"name": "Entry Price", "value": f"{price:.5f}", "inline": True},
        ]
        
        if sl:
            fields.append({"name": "Stop Loss", "value": f"{sl:.5f}", "inline": True})
        if tp:
            fields.append({"name": "Take Profit", "value": f"{tp:.5f}", "inline": True})
        
        fields.append({"name": "Source", "value": source.capitalize(), "inline": True})
        fields.append({"name": "Ticket", "value": str(ticket), "inline": True})
        
        return self.notify(DiscordNotification(
            channel=NotificationChannel.ALERTS,
            title=f"Trade Opened: {symbol}",
            description=f"New {side.upper()} position opened",
            color=color,
            priority=NotificationPriority.HIGH,
            fields=fields
        ))
    
    def notify_trade_closed(
        self,
        ticket: int,
        symbol: str,
        side: str,
        volume: float,
        entry_price: float,
        exit_price: float,
        pnl: float,
        duration_seconds: float = 0,
        exit_reason: str = ""
    ) -> bool:
        """Notify trade closed"""
        is_profit = pnl > 0
        emoji = "✅" if is_profit else "❌"
        color = Colors.SUCCESS if is_profit else Colors.DANGER
        pnl_str = f"+${pnl:.2f}" if is_profit else f"-${abs(pnl):.2f}"
        
        # Format duration
        if duration_seconds > 0:
            hours = int(duration_seconds // 3600)
            minutes = int((duration_seconds % 3600) // 60)
            duration_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
        else:
            duration_str = "N/A"
        
        fields = [
            {"name": "Symbol", "value": symbol, "inline": True},
            {"name": "Direction", "value": side.upper(), "inline": True},
            {"name": "P&L", "value": f"{emoji} {pnl_str}", "inline": True},
            {"name": "Entry", "value": f"{entry_price:.5f}", "inline": True},
            {"name": "Exit", "value": f"{exit_price:.5f}", "inline": True},
            {"name": "Volume", "value": f"{volume:.2f} lots", "inline": True},
            {"name": "Duration", "value": duration_str, "inline": True},
        ]
        
        if exit_reason:
            fields.append({"name": "Exit Reason", "value": exit_reason, "inline": True})
        
        return self.notify(DiscordNotification(
            channel=NotificationChannel.ALERTS,
            title=f"{'PROFIT' if is_profit else 'LOSS'} Trade Closed: {symbol}",
            description=f"Position closed with {pnl_str}",
            color=color,
            priority=NotificationPriority.HIGH,
            fields=fields
        ))
    
    def notify_trade_adopted(
        self,
        ticket: int,
        symbol: str,
        side: str,
        volume: float,
        price: float
    ) -> bool:
        """Notify when Cthulu adopts a manual trade"""
        return self.notify(DiscordNotification(
            channel=NotificationChannel.ALERTS,
            title=f"Trade Adopted: {symbol}",
            description=f"Cthulu has taken over management of a manual {side.upper()} position",
            color=Colors.CYAN,
            priority=NotificationPriority.HIGH,
            fields=[
                {"name": "Symbol", "value": symbol, "inline": True},
                {"name": "Direction", "value": side.upper(), "inline": True},
                {"name": "Volume", "value": f"{volume:.2f} lots", "inline": True},
                {"name": "Entry Price", "value": f"{price:.5f}", "inline": True},
                {"name": "Ticket", "value": str(ticket), "inline": True},
            ]
        ))
    
    def notify_risk_alert(
        self,
        alert_type: str,
        message: str,
        current_value: Optional[float] = None,
        threshold: Optional[float] = None
    ) -> bool:
        """Notify risk alert (drawdown, margin, position limits)"""
        fields = []
        if current_value is not None:
            fields.append({"name": "Current", "value": f"{current_value:.2%}", "inline": True})
        if threshold is not None:
            fields.append({"name": "Threshold", "value": f"{threshold:.2%}", "inline": True})
        
        return self.notify(DiscordNotification(
            channel=NotificationChannel.ALERTS,
            title=f"⚠️ Risk Alert: {alert_type}",
            description=message,
            color=Colors.DANGER,
            priority=NotificationPriority.CRITICAL,
            fields=fields
        ))
    
    def notify_system_health(
        self,
        status: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Notify system health event (errors, connection issues)"""
        is_error = status.lower() in ('error', 'critical', 'failure')
        color = Colors.DANGER if is_error else Colors.WARNING
        
        fields = []
        if details:
            for key, value in list(details.items())[:6]:  # Max 6 fields
                fields.append({"name": key, "value": str(value), "inline": True})
        
        return self.notify(DiscordNotification(
            channel=NotificationChannel.ALERTS,
            title=f"{'🔴' if is_error else '🟡'} System: {status}",
            description=message,
            color=color,
            priority=NotificationPriority.CRITICAL if is_error else NotificationPriority.HIGH,
            fields=fields
        ))
    
    def notify_session_summary(
        self,
        wins: int,
        losses: int,
        total_pnl: float,
        trade_count: int,
        win_rate: float,
        avg_win: float = 0,
        avg_loss: float = 0,
        best_trade: float = 0,
        worst_trade: float = 0
    ) -> bool:
        """Send daily session summary"""
        is_profitable = total_pnl > 0
        status = "UP" if is_profitable else "DOWN"
        color = Colors.SUCCESS if is_profitable else Colors.DANGER
        pnl_str = f"+${total_pnl:.2f}" if is_profitable else f"-${abs(total_pnl):.2f}"
        
        return self.notify(DiscordNotification(
            channel=NotificationChannel.HEALTH,
            title=f"{status} Daily Session Summary",
            description=f"Session closed with **{pnl_str}** total P&L",
            color=color,
            priority=NotificationPriority.MEDIUM,
            fields=[
                {"name": "Total Trades", "value": str(trade_count), "inline": True},
                {"name": "Wins", "value": str(wins), "inline": True},
                {"name": "Losses", "value": str(losses), "inline": True},
                {"name": "Win Rate", "value": f"{win_rate:.1%}", "inline": True},
                {"name": "Avg Win", "value": f"${avg_win:.2f}", "inline": True},
                {"name": "Avg Loss", "value": f"${abs(avg_loss):.2f}", "inline": True},
                {"name": "Best Trade", "value": f"${best_trade:.2f}", "inline": True},
                {"name": "Worst Trade", "value": f"${worst_trade:.2f}", "inline": True},
            ]
        ))
    
    def notify_model_performance(
        self,
        model_name: str,
        accuracy: float,
        predictions: int,
        drift_detected: bool = False,
        drift_score: float = 0
    ) -> bool:
        """Notify ML model performance"""
        color = Colors.WARNING if drift_detected else Colors.INFO
        
        fields = [
            {"name": "Accuracy", "value": f"{accuracy:.1%}", "inline": True},
            {"name": "Predictions", "value": str(predictions), "inline": True},
        ]
        
        if drift_detected:
            fields.append({"name": "Drift", "value": f"Score: {drift_score:.3f}", "inline": True})
        
        return self.notify(DiscordNotification(
            channel=NotificationChannel.HEALTH,
            title=f"Model Performance: {model_name}",
            description="Drift detected - consider retraining" if drift_detected else "Model operating normally",
            color=color,
            priority=NotificationPriority.MEDIUM if drift_detected else NotificationPriority.LOW,
            fields=fields
        ))
    
    def notify_portfolio_snapshot(
        self,
        open_positions: int,
        total_exposure: float,
        unrealized_pnl: float,
        margin_used: float,
        free_margin: float,
        equity: float
    ) -> bool:
        """Send portfolio snapshot"""
        is_positive = unrealized_pnl >= 0
        color = Colors.SUCCESS if is_positive else Colors.DANGER
        
        return self.notify(DiscordNotification(
            channel=NotificationChannel.HEALTH,
            title="💼 Portfolio Snapshot",
            description=f"Current portfolio status with {open_positions} open position(s)",
            color=color,
            priority=NotificationPriority.LOW,
            fields=[
                {"name": "Open Positions", "value": str(open_positions), "inline": True},
                {"name": "Unrealized P&L", "value": f"${unrealized_pnl:+.2f}", "inline": True},
                {"name": "Total Exposure", "value": f"${total_exposure:.2f}", "inline": True},
                {"name": "Equity", "value": f"${equity:.2f}", "inline": True},
                {"name": "Margin Used", "value": f"${margin_used:.2f}", "inline": True},
                {"name": "Free Margin", "value": f"${free_margin:.2f}", "inline": True},
            ]
        ))
    
    def notify_signal_quality(
        self,
        symbol: str,
        direction: str,
        confidence: float,
        strategy: str,
        indicators: Optional[Dict[str, float]] = None
    ) -> bool:
        """Notify high-confidence signal detected"""
        emoji = "🟢" if direction.upper() == "BUY" else "🔴"
        
        fields = [
            {"name": "Symbol", "value": symbol, "inline": True},
            {"name": "Direction", "value": f"{emoji} {direction.upper()}", "inline": True},
            {"name": "Confidence", "value": f"{confidence:.1%}", "inline": True},
            {"name": "Strategy", "value": strategy, "inline": True},
        ]
        
        if indicators:
            for name, value in list(indicators.items())[:4]:
                fields.append({"name": name, "value": f"{value:.4f}", "inline": True})
        
        return self.notify(DiscordNotification(
            channel=NotificationChannel.SIGNALS,
            title=f"📡 High-Confidence Signal: {symbol}",
            description=f"Strategy '{strategy}' detected strong {direction.upper()} setup",
            color=Colors.PURPLE,
            priority=NotificationPriority.MEDIUM,
            fields=fields
        ))
    
    def notify_regime_change(
        self,
        symbol: str,
        old_regime: str,
        new_regime: str,
        confidence: float = 0
    ) -> bool:
        """Notify market regime change"""
        return self.notify(DiscordNotification(
            channel=NotificationChannel.SIGNALS,
            title=f"🔄 Regime Change: {symbol}",
            description=f"Market condition shifted from **{old_regime}** to **{new_regime}**",
            color=Colors.ORANGE,
            priority=NotificationPriority.MEDIUM,
            fields=[
                {"name": "Previous", "value": old_regime, "inline": True},
                {"name": "Current", "value": new_regime, "inline": True},
                {"name": "Confidence", "value": f"{confidence:.1%}" if confidence else "N/A", "inline": True},
            ]
        ))
    
    def notify_milestone(
        self,
        milestone_type: str,
        message: str,
        value: Optional[float] = None
    ) -> bool:
        """Notify milestone achievement"""
        return self.notify(DiscordNotification(
            channel=NotificationChannel.SIGNALS,
            title=f"Milestone: {milestone_type}",
            description=message,
            color=Colors.GOLD,
            priority=NotificationPriority.HIGH,
            fields=[
                {"name": "Value", "value": f"${value:.2f}" if value else "N/A", "inline": True}
            ] if value else []
        ))
    
    # =========================================================================
    # Internal Methods
    # =========================================================================
    
    def _notification_loop(self) -> None:
        """Background notification processing loop"""
        while self._running:
            try:
                for channel in NotificationChannel:
                    self._process_channel_queue(channel)
                
                time.sleep(self.batch_interval)
                
            except Exception as e:
                logger.error(f"Error in notification loop: {e}")
    
    def _process_channel_queue(self, channel: NotificationChannel) -> None:
        """Process notifications for a single channel"""
        webhook = self.webhooks.get(channel)
        if not webhook:
            return
        
        rate_limiter = self._rate_limiters[channel]
        q = self._queues[channel]
        
        # Collect batch of notifications (up to 5 embeds per message)
        batch: List[DiscordNotification] = []
        
        while len(batch) < 5 and not q.empty():
            try:
                _, _, notification = q.get_nowait()
                batch.append(notification)
            except queue.Empty:
                break
        
        if not batch:
            return
        
        # Check rate limit
        wait_time = rate_limiter.wait_time()
        if wait_time > 0:
            time.sleep(wait_time)
        
        # Send batch
        if rate_limiter.can_send():
            success = self._send_webhook(webhook, batch)
            rate_limiter.record_request()
            
            with self._stats_lock:
                if success:
                    self._stats['sent'] += len(batch)
                    self._stats['batched'] += 1
                else:
                    self._stats['failed'] += len(batch)
    
    def _send_webhook(self, webhook_url: str, notifications: List[DiscordNotification]) -> bool:
        """Send notifications to Discord webhook"""
        try:
            embeds = [n.to_embed() for n in notifications]
            payload = {"embeds": embeds}
            
            data = json.dumps(payload).encode('utf-8')
            request = urllib.request.Request(
                webhook_url,
                data=data,
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'Cthulu/6.0.0'
                },
                method='POST'
            )
            
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status == 204  # Discord returns 204 on success
                
        except urllib.error.HTTPError as e:
            if e.code == 429:  # Rate limited
                logger.warning(f"Discord rate limited, will retry")
            else:
                logger.error(f"Discord webhook error: {e.code}")
            return False
        except Exception as e:
            logger.error(f"Failed to send Discord notification: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get notification statistics"""
        with self._stats_lock:
            return dict(self._stats)
    
    def send_test_notification(self, channel: NotificationChannel) -> bool:
        """Send a test notification to verify webhook setup"""
        test_notifications = {
            NotificationChannel.ALERTS: DiscordNotification(
                channel=NotificationChannel.ALERTS,
                title="🧪 Test Alert",
                description="This is a test notification for the Alerts channel",
                color=Colors.INFO,
                priority=NotificationPriority.LOW,
                fields=[
                    {"name": "Status", "value": "✅ Connected", "inline": True},
                    {"name": "Timestamp", "value": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"), "inline": True}
                ]
            ),
            NotificationChannel.HEALTH: DiscordNotification(
                channel=NotificationChannel.HEALTH,
                title="🧪 Test Health Report",
                description="This is a test notification for the Health channel",
                color=Colors.INFO,
                priority=NotificationPriority.LOW,
                fields=[
                    {"name": "Status", "value": "✅ Connected", "inline": True},
                    {"name": "Timestamp", "value": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"), "inline": True}
                ]
            ),
            NotificationChannel.SIGNALS: DiscordNotification(
                channel=NotificationChannel.SIGNALS,
                title="🧪 Test Signal",
                description="This is a test notification for the Signals channel",
                color=Colors.PURPLE,
                priority=NotificationPriority.LOW,
                fields=[
                    {"name": "Status", "value": "✅ Connected", "inline": True},
                    {"name": "Timestamp", "value": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"), "inline": True}
                ]
            )
        }
        
        notification = test_notifications.get(channel)
        if not notification:
            return False
        
        webhook = self.webhooks.get(channel)
        if not webhook:
            logger.warning(f"No webhook configured for {channel.value}")
            return False
        
        # Send directly (bypass queue for testing)
        return self._send_webhook(webhook, [notification])


# =============================================================================
# Event Bus Subscriber - Integrates with TradeEventBus
# =============================================================================

class DiscordEventSubscriber:
    """
    Subscribes to TradeEventBus and forwards relevant events to Discord.
    
    Filters events based on configuration to avoid notification spam.
    """
    
    def __init__(self, notifier: DiscordNotifier, config: Optional[Dict] = None):
        """
        Initialize subscriber.
        
        Args:
            notifier: DiscordNotifier instance
            config: Configuration dict with notification preferences
        """
        self.notifier = notifier
        self.config = config or {}
        self.logger = logging.getLogger('cthulu.discord_subscriber')
        
        # Notification preferences
        self.notify_trades = self.config.get('notify_trades', True)
        self.notify_adoptions = self.config.get('notify_adoptions', True)
        self.notify_risk = self.config.get('notify_risk', True)
        self.min_pnl_notify = self.config.get('min_pnl_notify', 0)  # Min P&L to notify
        
    def on_event(self, event) -> None:
        """Process a trade event from the event bus"""
        try:
            from observability.trade_event_bus import TradeEventType
            
            if event.event_type == TradeEventType.TRADE_OPENED and self.notify_trades:
                self.notifier.notify_trade_opened(
                    ticket=event.ticket or 0,
                    symbol=event.symbol,
                    side=event.side,
                    volume=event.volume,
                    price=event.price,
                    sl=event.stop_loss,
                    tp=event.take_profit,
                    source=event.source
                )
            
            elif event.event_type == TradeEventType.TRADE_CLOSED and self.notify_trades:
                # Only notify if P&L exceeds threshold
                if abs(event.pnl) >= self.min_pnl_notify:
                    entry_price = event.metadata.get('entry_price', event.price)
                    self.notifier.notify_trade_closed(
                        ticket=event.ticket or 0,
                        symbol=event.symbol,
                        side=event.side,
                        volume=event.volume,
                        entry_price=entry_price,
                        exit_price=event.price,
                        pnl=event.pnl,
                        duration_seconds=event.duration_seconds,
                        exit_reason=event.metadata.get('exit_reason', '')
                    )
            
            elif event.event_type == TradeEventType.TRADE_ADOPTED and self.notify_adoptions:
                self.notifier.notify_trade_adopted(
                    ticket=event.ticket or 0,
                    symbol=event.symbol,
                    side=event.side,
                    volume=event.volume,
                    price=event.price
                )
            
            elif event.event_type == TradeEventType.RISK_LIMIT_HIT and self.notify_risk:
                self.notifier.notify_risk_alert(
                    alert_type=event.metadata.get('type', 'Risk Limit'),
                    message=event.metadata.get('message', 'Risk limit hit'),
                    current_value=event.metadata.get('current'),
                    threshold=event.metadata.get('threshold')
                )
            
            elif event.event_type == TradeEventType.DRAWDOWN_EVENT and self.notify_risk:
                self.notifier.notify_risk_alert(
                    alert_type="Drawdown",
                    message=event.metadata.get('message', 'Drawdown limit reached'),
                    current_value=event.metadata.get('drawdown'),
                    threshold=event.metadata.get('threshold')
                )
                
        except Exception as e:
            self.logger.error(f"Error processing event for Discord: {e}")


# =============================================================================
# Global Singleton & Helper Functions
# =============================================================================

_notifier: Optional[DiscordNotifier] = None


def get_discord_notifier() -> DiscordNotifier:
    """Get or create the global Discord notifier singleton"""
    global _notifier
    if _notifier is None:
        _notifier = DiscordNotifier()
        _notifier.start()
    return _notifier


def initialize_discord_notifier(
    alerts_webhook: Optional[str] = None,
    health_webhook: Optional[str] = None,
    signals_webhook: Optional[str] = None,
    config: Optional[Dict] = None
) -> DiscordNotifier:
    """
    Initialize the Discord notifier with webhooks.
    
    Call this during system startup.
    """
    global _notifier
    
    _notifier = DiscordNotifier(
        alerts_webhook=alerts_webhook,
        health_webhook=health_webhook,
        signals_webhook=signals_webhook,
        enabled=True
    )
    _notifier.start()
    
    # Wire up to event bus if available
    try:
        from observability.trade_event_bus import get_event_bus
        event_bus = get_event_bus()
        subscriber = DiscordEventSubscriber(_notifier, config)
        event_bus.subscribe('discord', subscriber.on_event)
        logger.info("Discord notifier connected to event bus")
    except Exception as e:
        logger.warning(f"Could not connect Discord to event bus: {e}")
    
    return _notifier


def stop_discord_notifier() -> None:
    """Stop the Discord notifier gracefully"""
    global _notifier
    if _notifier:
        _notifier.stop()
        _notifier = None
