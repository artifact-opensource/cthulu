from datetime import datetime

from cthulu.position.lifecycle import PositionLifecycle


class DummyEngine:
    def __init__(self, ticket=None):
        self._ticket = ticket

    def execute_order(self, symbol, order_type, volume, sl=None, tp=None, comment="", magic_number=None):
        return self._ticket


class DummyConnector:
    def get_position_by_ticket(self, ticket):
        if ticket == 123:
            return {
                'ticket': 123,
                'symbol': 'EURUSD',
                'price_open': 1.2345,
                'price_current': 1.2350,
                'profit': 5.0,
                'volume': 0.01
            }
        return None


class DummyTracker:
    def __init__(self):
        self.tracked = []

    def track_position(self, pos):
        self.tracked.append(pos)


class DummyDB:
    def __init__(self):
        self.saved = []

    def save_position(self, **kwargs):
        self.saved.append(kwargs)


def test_open_position_places_order_and_tracks():
    engine = DummyEngine(ticket=123)
    connector = DummyConnector()
    tracker = DummyTracker()
    db = DummyDB()

    lifecycle = PositionLifecycle(connector=connector, execution_engine=engine, position_tracker=tracker, db_handler=db)

    ticket = lifecycle.open_position(symbol='EURUSD', order_type='buy', volume=0.01, sl=1.23, tp=1.24, comment='test', magic_number=0)

    assert ticket == 123
    assert len(tracker.tracked) == 1
    assert db.saved, "Position should be persisted via save_position"



