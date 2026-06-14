from unittest.mock import MagicMock
from cthulu.position.lifecycle import PositionLifecycle
from cthulu.position.manager import PositionInfo


class DummyConnector:
    def get_position_by_ticket(self, ticket):
        # Simulate MT5 state reflecting requested SL
        return {'ticket': ticket, 'symbol': 'EURUSD', 'volume': 1.0, 'price_open': 1.1, 'price_current': 1.2, 'sl': 1.05, 'tp': None}


class DummyDB:
    def remove_position(self, ticket):
        pass


def test_modify_considered_success_when_mt5_already_has_values():
    connector = DummyConnector()
    exec_engine = MagicMock()
    # Simulate execution engine returning False (rejected)
    exec_engine.modify_position.return_value = False
    tracker = MagicMock()

    # Create a tracked position that shows no SL/TP
    pos = PositionInfo(ticket=111, symbol='EURUSD', volume=1.0, open_price=1.1, current_price=1.2, sl=None, tp=None, type='buy')
    tracker.get_position.return_value = pos

    db = DummyDB()

    lifecycle = PositionLifecycle(connector, exec_engine, tracker, db)
    # Should return True because MT5 already has SL=1.05
    assert lifecycle.modify_position(111, sl=1.05, tp=None) is True


def test_execution_engine_no_changes_retcode_treated_as_success(monkeypatch):
    # Test ExecutionEngine.modify_position treats MT5 'No changes' retcode as success
    from cthulu.execution import engine as engine_module
    from cthulu.execution.engine import ExecutionEngine

    class FakeMT5:
        # minimal constants used by modify_position
        TRADE_ACTION_SLTP = 1
        TRADE_RETCODE_DONE = 0

        def positions_get(self, ticket=None):
            class P: pass
            p = P()
            p.ticket = 222
            p.symbol = 'EURUSD'
            p.volume = 1.0
            p.price_open = 1.1
            p.price_current = 1.2
            p.sl = 0.0
            p.tp = 0.0
            p.type = 0
            return [p]

        class Result:
            def __init__(self):
                self.retcode = 10025
                self.comment = 'No changes'

        def order_send(self, req):
            return FakeMT5.Result()

        def last_error(self):
            return None

    fake_mt5 = FakeMT5()
    monkeypatch.setattr(engine_module, 'mt5', fake_mt5)

    connector = MagicMock()
    connector.is_connected.return_value = True
    exec_engine = ExecutionEngine(connector)

    # Should return True treating retcode 10025 as success
    assert exec_engine.modify_position(222, sl=1.05, tp=None) is True


def test_position_lifecycle_has_logger_attribute():
    connector = DummyConnector()
    exec_engine = MagicMock()
    tracker = MagicMock()
    db = DummyDB()
    lifecycle = PositionLifecycle(connector, exec_engine, tracker, db)
    assert hasattr(lifecycle, 'logger') and lifecycle.logger is not None
