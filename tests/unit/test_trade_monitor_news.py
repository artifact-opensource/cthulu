import time
from cthulu.monitoring.trade_monitor import TradeMonitor
from cthulu.news.base import NewsEvent


class DummyTradeManager:
    def __init__(self):
        self.paused_until = None

    def pause_trading(self, sec):
        self.paused_until = time.time() + sec

    def is_paused(self):
        return self.paused_until and time.time() < self.paused_until


class DummyNewsManager:
    def __init__(self, events):
        self._events = events

    def fetch_recent(self):
        return self._events


class DummyML:
    def __init__(self):
        self.events = []

    def record_event(self, etype, payload):
        self.events.append((etype, payload))


def test_monitor_pauses_on_high_importance():
    tm = DummyTradeManager()
    ev = NewsEvent(provider='TradingEconomics', ts=time.time(), symbol='US', headline='GDP Surprise', body='GDP higher', meta={'importance': 'high'})
    nm = DummyNewsManager([ev])
    ml = DummyML()
    class DummyPositionManager:
        def __init__(self):
            self._positions = {}

    pm = DummyPositionManager()
    monitor = TradeMonitor(position_manager=pm, trade_manager=tm, poll_interval=0.1, ml_collector=ml, news_manager=nm, news_alert_window=2)
    # Run one cycle
    monitor._scan_and_record()
    # Should have recorded a news_alert and paused trading
    assert any(e[0] == 'monitor.news_alert' for e in ml.events)
    assert tm.paused_until is not None




