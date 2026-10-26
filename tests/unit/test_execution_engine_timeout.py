import time
import pytest
from cthulu.execution.engine import ExecutionEngine, OrderRequest, OrderType, OrderStatus


class DummyConnector:
    def is_connected(self):
        return True

    def get_account_info(self):
        return {'trade_allowed': True, 'balance': 1000.0}

    def ensure_symbol_selected(self, symbol: str) -> str:
        return symbol

    def get_symbol_info(self, symbol: str):
        # Provide bid/ask and volume constraints
        return {
            'ask': 2000.0,
            'bid': 1999.5,
            'volume_min': 0.01,
            'volume_max': 100.0,
            'volume_step': 0.01,
            'point': 0.01
        }

    def _mt5_symbol_info_tick(self, symbol: str):
        class Tick:
            ask = 2000.0
            bid = 1999.5
        return Tick()


class DummyOrder:
    def __init__(self, *a, **k):
        pass


def test_place_order_times_out(monkeypatch):
    engine = ExecutionEngine(connector=DummyConnector())
    # Shorten timeout for test speed
    engine.ORDER_SUBMIT_TIMEOUT = 0.5

    # Patch mt5.order_send to sleep longer than timeout
    def slow_order_send(req):
        time.sleep(1.0)
        return DummyOrder()

    # Ensure mt5 is patched in module
    import cthulu.execution.engine as eng_mod

    monkeypatch.setattr(eng_mod, 'mt5', eng_mod.mt5)
    monkeypatch.setattr(eng_mod.mt5, 'order_send', slow_order_send)

    req = OrderRequest(signal_id='s1', symbol='GOLDM', side='BUY', volume=0.01, order_type=OrderType.MARKET)

    res = engine.place_order(req)

    assert res.status == OrderStatus.REJECTED
    assert 'timed out' in (res.error or '')
