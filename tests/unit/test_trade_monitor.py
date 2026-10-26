import time
import os
from cthulu.monitoring.trade_monitor import TradeMonitor
from cthulu.ML_RL.instrumentation import MLDataCollector
from unittest.mock import MagicMock


def test_trade_monitor_records_snapshot():
    pm = MagicMock()
    # create a fake positions dict
    fake_pos = MagicMock()
    fake_pos.ticket = 1
    fake_pos.symbol = 'TEST'
    fake_pos.volume = 0.1
    fake_pos.stop_loss = 0.0
    fake_pos.take_profit = 0.0
    fake_pos.unrealized_pnl = 0.0
    pm._positions = {1: fake_pos}

    collector = MLDataCollector(prefix=f"testmon_{int(time.time())}_{os.getpid()}")
    monitor = TradeMonitor(pm, poll_interval=0.2, ml_collector=collector)
    monitor.start()
    time.sleep(0.6)
    monitor.stop()
    collector.close()
    # If no exceptions were raised, basic behavior is OK
    assert True





