import pytest
from datetime import datetime

from cthulu.position.lifecycle import PositionLifecycle
from cthulu.position.tracker import PositionTracker


class DummyConnector:
    def __init__(self, mt5_pos):
        self._mt5_pos = mt5_pos

    def get_position_by_ticket(self, ticket):
        return self._mt5_pos if self._mt5_pos and self._mt5_pos.get('ticket') == ticket else None


class DummyExecutionEngine:
    def __init__(self):
        self.modified = []

    def modify_position(self, ticket, sl, tp):
        # Simulate successful modification
        self.modified.append((ticket, sl, tp))
        return True


class DummyDB:
    def __init__(self):
        self.saved = []

    def save_position(self, **kwargs):
        self.saved.append(kwargs)

    def remove_position(self, ticket):
        return True


def test_modify_untracked_position_creates_and_persists():
    ticket = 12345
    mt5_pos = {
        'ticket': ticket,
        'symbol': 'BTCUSD#',
        'price_open': 100.0,
        'price_current': 101.0,
        'profit': 1.0,
        'volume': 0.1,
        'type': 0,  # buy
        'magic': 0,
        'time': datetime.now(),
        'sl': None,
        'tp': None
    }

    connector = DummyConnector(mt5_pos)
    exec_engine = DummyExecutionEngine()
    tracker = PositionTracker()
    db = DummyDB()

    lifecycle = PositionLifecycle(connector=connector, execution_engine=exec_engine, position_tracker=tracker, db_handler=db)

    # Call modify_position for an untracked ticket - should modify MT5 position and then track & persist
    sl = 95.0
    tp = 110.0
    result = lifecycle.modify_position(ticket, sl=sl, tp=tp)

    assert result is True
    # Check execution engine was asked to modify
    assert exec_engine.modified == [(ticket, sl, tp)]

    # Position should now be tracked
    p = tracker.get_position(ticket)
    assert p is not None
    assert p.sl == sl
    assert p.tp == tp

    # And db should have saved the position once
    assert len(db.saved) == 1
    saved = db.saved[0]
    assert saved['ticket'] == ticket
    assert saved['symbol'] == 'BTCUSD#'