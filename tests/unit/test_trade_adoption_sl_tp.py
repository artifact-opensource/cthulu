from cthulu.position.adoption import TradeAdoptionManager, TradeAdoptionPolicy
from cthulu.position.tracker import PositionTracker
from cthulu.position.lifecycle import PositionLifecycle


class DummyConnector:
    def __init__(self, pos):
        self._pos = pos

    def get_open_positions(self):
        return [self._pos]

    def get_point(self, symbol):
        return 1.0

    def get_position_by_ticket(self, ticket):
        if self._pos.get('ticket') == ticket:
            return self._pos
        return None


class DummyExecutionEngine:
    def __init__(self):
        self.modified = []

    def modify_position(self, ticket, sl, tp):
        self.modified.append((ticket, sl, tp))
        return True


class DummyDB:
    def __init__(self):
        self.saved = []

    def save_position(self, **kwargs):
        self.saved.append(kwargs)


def test_adopt_applies_emergency_sl_and_tracks():
    ticket = 555
    pos = {
        'ticket': ticket,
        'symbol': 'EURUSD',
        'price_open': 1.2000,
        'price_current': 1.2010,
        'profit': 10.0,
        'volume': 0.1,
        'type': 0,  # buy
        'magic': 0,
        'time': None,
        'sl': None,
        'tp': None
    }

    connector = DummyConnector(pos)
    exec_engine = DummyExecutionEngine()
    tracker = PositionTracker()
    db = DummyDB()

    lifecycle = PositionLifecycle(connector=connector, execution_engine=exec_engine, position_tracker=tracker, db_handler=db)
    policy = TradeAdoptionPolicy()
    policy.apply_emergency_sl = True
    policy.emergency_sl_points = 50  # large point distance

    manager = TradeAdoptionManager(connector=connector, position_tracker=tracker, position_lifecycle=lifecycle, policy=policy)

    adopted = manager._adopt_trade(pos)

    assert adopted is True
    # Execution engine should have been called to modify the MT5 position
    assert exec_engine.modified, "Expected modify_position to be called"

    # Tracker should have the position tracked with SL applied
    tracked = tracker.get_position(ticket)
    assert tracked is not None
    assert tracked.sl is not None
    assert tracked.sl != pos['sl']