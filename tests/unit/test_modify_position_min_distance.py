from types import SimpleNamespace
import cthulu.execution.engine as eng


def test_modify_position_rejects_too_close_sl(monkeypatch, caplog):
    # Prepare fake position returned by mt5.positions_get
    fake_pos = SimpleNamespace()
    fake_pos.ticket = 123
    fake_pos.symbol = 'GOLDm#'
    fake_pos.sl = None
    fake_pos.tp = None
    fake_pos.price_open = 4443.85
    fake_pos.price_current = 4442.6
    fake_pos.volume = 0.1
    fake_pos.type = 1  # SELL or BUY mapping depends on stub, but we'll set SELL for test

    monkeypatch.setattr(eng.mt5, 'positions_get', lambda ticket=None: [fake_pos])

    # Symbol info: point=0.01, trade_stops_level=50 -> min_dist=0.5
    # Fake connector with symbol info
    conn = SimpleNamespace()
    conn.get_symbol_info = lambda s: {'point': 0.01, 'trade_stops_level': 50}

    # Create ExecutionEngine instance with our connector
    engine = eng.ExecutionEngine.__new__(eng.ExecutionEngine)
    engine.connector = conn
    engine.logger = eng.logging.getLogger('test')
    engine.magic_number = 0

    # Try to set SL too close (difference < 0.5) for a BUY position
    # We'll set new_sl to 4442.2 which is 0.4 away from current price 4442.6
    # Modify should reject before calling mt5.order_send

    monkeypatch.setattr(eng.mt5, 'ORDER_TYPE_BUY', 0)
    monkeypatch.setattr(eng.mt5, 'ORDER_TYPE_SELL', 1)
    fake_pos.type = 0  # BUY

    # Ensure order_send would raise if called (protection)
    monkeypatch.setattr(eng.mt5, 'order_send', lambda req: (_ for _ in ()).throw(Exception('order_send should not be called')))

    # Run modify - expect False and log mentioning 'too close'
    res = engine.modify_position(123, sl=4442.2, tp=None)
    assert res is False
    assert any('too close' in r.message or 'Rejected SL' in r.message for r in caplog.records) or any('Rejected SL' in rec.getMessage() for rec in caplog.records)