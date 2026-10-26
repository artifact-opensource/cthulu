from datetime import datetime
from types import SimpleNamespace

from cthulu.execution.engine import ExecutionEngine, OrderRequest, OrderType, OrderStatus


class FakeConnector:
    def is_connected(self):
        return True
    def get_account_info(self):
        return {'trade_allowed': True}
    def get_symbol_info(self, symbol):
        return {'volume_min': 0.01, 'volume_step': 0.01, 'ask': 100.0, 'bid': 99.9}
    def ensure_symbol_selected(self, symbol):
        # In production this may select the correct symbol variant; test returns input
        return symbol


class FakeMT5:
    TRADE_RETCODE_DONE = 10009
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1

    def __init__(self):
        self.calls = []
    def order_send(self, req):
        class R: pass
        r = R()
        r.retcode = self.TRADE_RETCODE_DONE
        r.order = 123456
        r.price = 100.0
        r.volume = req.get('volume') if isinstance(req, dict) else getattr(req, 'volume', None)
        r.comment = 'ok'
        self.calls.append(req)
        return r


def test_close_orders_with_different_closing_ticket_do_not_collide(monkeypatch):
    fake_mt5 = FakeMT5()

    # Patch mt5 in engine module
    import cthulu.execution.engine as eng_mod
    monkeypatch.setattr(eng_mod, 'mt5', fake_mt5)

    exec_engine = ExecutionEngine(connector=FakeConnector())

    # First close order for ticket 1
    req1 = OrderRequest(symbol='XAUUSD', side='SELL', volume=0.1, order_type=OrderType.MARKET, metadata={'closing_ticket': 1})
    r1 = exec_engine.place_order(req1)
    assert r1.status == OrderStatus.FILLED

    # Second close order for a different ticket (same symbol/volume) should NOT be treated as duplicate
    req2 = OrderRequest(symbol='XAUUSD', side='SELL', volume=0.1, order_type=OrderType.MARKET, metadata={'closing_ticket': 2})
    r2 = exec_engine.place_order(req2)
    assert r2.status == OrderStatus.FILLED

    # Ensure two mt5.order_send calls were made
    assert len(fake_mt5.calls) == 2
