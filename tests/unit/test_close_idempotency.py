from cthulu.position.lifecycle import PositionLifecycle
from cthulu.position.manager import PositionInfo, PositionManager


class DummyConnector:
    def is_connected(self):
        return True


class DummyExec:
    def close_position(self, ticket):
        class R:
            status = 'FILLED'
            order = 123
            price = 1.2345
            volume = 1.0
        return R()


class DummyDB:
    def remove_position(self, ticket):
        pass


def test_duplicate_close_prevented():
    pm = PositionManager()
    # Add a position
    pos = PositionInfo(ticket=9999, symbol='EURUSD', volume=1.0, open_price=1.1)
    pm.add_position(pos)

    lifecycle = PositionLifecycle(DummyConnector(), DummyExec(), pm, DummyDB())

    # Simulate in-flight close
    lifecycle._inflight_closes.add(9999)

    result = lifecycle.close_position(9999, reason='test')
    assert result is False
    # Clean up for other tests
    lifecycle._inflight_closes.discard(9999)
