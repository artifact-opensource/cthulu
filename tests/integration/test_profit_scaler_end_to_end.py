from types import SimpleNamespace
from datetime import datetime

from cthulu.position.profit_scaler import create_profit_scaler
from cthulu.execution.engine import ExecutionResult, OrderStatus


class FakeMT5:
    def __init__(self, pos):
        self._pos = pos
        self.TRADE_RETCODE_DONE = 10009

    def positions_get(self, ticket=None):
        if ticket is None:
            return [self._pos]
        if ticket == self._pos.ticket:
            return [self._pos]
        return []

    def symbol_info(self, symbol):
        return SimpleNamespace(volume_min=0.01, volume_step=0.01, point=0.01, trade_stops_level=10, trade_freeze_level=None)

    def order_send(self, req):
        class R: pass
        r = R()
        r.retcode = getattr(self, 'TRADE_RETCODE_DONE', 10009)
        r.comment = 'ok'
        return r


class RecordingExecutionEngine:
    def __init__(self):
        self.closed = []
        self.modified = []

    def close_position(self, ticket, volume):
        self.closed.append((ticket, volume))
        return ExecutionResult(order_id=None, status=OrderStatus.FILLED, executed_price=1.0, executed_volume=volume, timestamp=datetime.now(), metadata={'profit': 1.23}, position_ticket=ticket)

    def modify_position(self, ticket, sl=None, tp=None):
        self.modified.append((ticket, sl, tp))
        return True


def test_profit_scaler_partial_close_executes(monkeypatch):
    # Position volume > min_lot so partial close should be possible
    pos = SimpleNamespace(ticket=99999, symbol='XAUUSD', volume=0.03, price_current=110.0, sl=None, tp=None, profit=5.0, price_open=100.0, type=0)
    fake_mt5 = FakeMT5(pos)

    # Patch connector's mt5
    import cthulu.connector.mt5_connector as mt5_mod
    monkeypatch.setattr(mt5_mod, 'mt5', fake_mt5)

    exec_engine = RecordingExecutionEngine()

    cfg = {
        'enabled': True,
        'min_profit_amount': 0.5,
        'micro_account_threshold': 100.0,
        'tiers': [
            {'profit_threshold_pct': 0.01, 'close_pct': 0.5, 'move_sl_to_entry': True, 'trail_pct': 0.0}
        ]
    }

    scaler = create_profit_scaler(connector=None, execution_engine=exec_engine, config_dict=cfg)

    results = scaler.run_scaling_cycle(balance=1000.0)

    # Expect at least one close recorded with a positive volume <= original
    assert len(exec_engine.closed) >= 1, "Expected a partial close to be executed"
    ticket, vol = exec_engine.closed[0]
    assert ticket == pos.ticket
    assert 0 < vol <= pos.volume
    assert any(r.get('success') for r in results)
