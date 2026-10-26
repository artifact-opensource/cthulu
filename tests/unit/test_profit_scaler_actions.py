import types
from types import SimpleNamespace
from datetime import datetime
import pytest

from cthulu.position.profit_scaler import create_profit_scaler, ScalingTier
from cthulu.execution.engine import ExecutionResult, OrderStatus


class FakeMT5:
    def __init__(self, pos):
        self._pos = pos
        # Minimal constants expected by code
        self.TRADE_ACTION_SLTP = 1
        self.TRADE_RETCODE_DONE = 10009
        self.ORDER_TYPE_BUY = 0
        self.ORDER_TYPE_SELL = 1

    def positions_get(self, ticket=None):
        if ticket is None:
            return [self._pos]
        if ticket == self._pos.ticket:
            return [self._pos]
        return []

    def symbol_info(self, symbol):
        # Return an object with attributes (mt5.symbol_info normally does this)
        return SimpleNamespace(volume_min=0.01, volume_step=0.01, point=0.01, trade_stops_level=10, trade_freeze_level=None)

    def order_send(self, req):
        # Simulate success modify response
        class R: pass
        r = R()
        r.retcode = getattr(self, 'TRADE_RETCODE_DONE', 10009)
        r.comment = 'ok'
        return r


class FakeExecutionEngine:
    def close_position(self, ticket, volume):
        return ExecutionResult(order_id=None, status=OrderStatus.FILLED, executed_price=1.0, executed_volume=volume, timestamp=datetime.now(), metadata={'profit': 1.23}, position_ticket=ticket)
    def modify_position(self, ticket, sl=None, tp=None):
        return True


def setup_fake_mt5(monkeypatch, pos):
    import cthulu.connector.mt5_connector as mt5_mod
    fake = FakeMT5(pos)
    monkeypatch.setattr(mt5_mod, 'mt5', fake)
    return fake


def test_profit_scaler_executes_partial_close(monkeypatch):
    # Simulate a position with meaningful profit
    pos = SimpleNamespace(ticket=12345, symbol='XAUUSD', volume=0.02, price_current=101.0, sl=None, tp=None, profit=2.0, price_open=100.0, type=0)
    fake_mt5 = setup_fake_mt5(monkeypatch, pos)

    exec_engine = FakeExecutionEngine()

    # Small min profit and low tier threshold to force an immediate close
    cfg = {
        'enabled': True,
        'min_profit_amount': 0.5,
        'micro_account_threshold': 100.0,
        'tiers': [
            {'profit_threshold_pct': 0.01, 'close_pct': 1.0, 'move_sl_to_entry': True, 'trail_pct': 0.0}
        ]
    }

    scaler = create_profit_scaler(connector=None, execution_engine=exec_engine, config_dict=cfg)

    results = scaler.run_scaling_cycle(balance=1000.0)

    assert isinstance(results, list)
    assert any(r.get('success') for r in results), "Expected at least one successful scaling action"
    assert len(scaler.get_scaling_log()) > 0


def test_skips_scaling_when_profit_below_threshold(monkeypatch, caplog):
    pos = SimpleNamespace(ticket=22222, symbol='EURUSD', volume=0.01, price_current=1.0010, sl=None, tp=None, profit=0.001, price_open=1.0000, type=0)
    setup_fake_mt5(monkeypatch, pos)

    exec_engine = FakeExecutionEngine()

    cfg = {
        'enabled': True,
        'min_profit_amount': 100.0,  # Intentionally high to force skip
    }

    scaler = create_profit_scaler(connector=None, execution_engine=exec_engine, config_dict=cfg)

    with caplog.at_level('INFO'):
        results = scaler.run_scaling_cycle(balance=1000.0)

    assert results == []
    assert any('Skipping scaling for' in rec.message for rec in caplog.records)
