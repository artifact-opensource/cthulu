import time
from cthulu.advisory.manager import AdvisoryManager
from cthulu.execution.engine import OrderRequest, OrderType


class DummyExec:
    def __init__(self):
        self.calls = []

    def place_order(self, req):
        self.calls.append(req)
        class R:
            order = 12345
            price = 1.234
            volume = req.volume
            retcode = 0
        return R()


class DummyML:
    def __init__(self):
        self.events = []

    def record_event(self, etype, payload):
        self.events.append((etype, payload))


def test_advisory_mode_records():
    exec_engine = DummyExec()
    ml = DummyML()
    cfg = {'enabled': True, 'mode': 'advisory'}
    m = AdvisoryManager(cfg, exec_engine, ml)

    req = OrderRequest(signal_id='s1', symbol='GOLD', side='BUY', volume=1.0, order_type=OrderType.MARKET)
    res = m.decide(req)
    assert res['action'] == 'advisory'
    assert ml.events and ml.events[-1][0] == 'advisory.signal'
    assert not exec_engine.calls


def test_ghost_mode_places_limited_trades():
    exec_engine = DummyExec()
    ml = DummyML()
    cfg = {'enabled': True, 'mode': 'ghost', 'ghost_lot_size': 0.02, 'ghost_max_trades': 2, 'ghost_max_duration': 3600}
    m = AdvisoryManager(cfg, exec_engine, ml)

    req = OrderRequest(signal_id='s2', symbol='GOLD', side='SELL', volume=1.0, order_type=OrderType.MARKET)
    # sanity checks
    assert m.enabled
    assert m.mode == 'ghost'
    assert m.ghost_trades_count == 0
    assert m.ghost_max_trades == 2

    r1 = m.decide(req)
    assert r1['action'] == 'ghost'
    # immediate exec_engine.calls should be empty because ghost runs asynchronously
    assert not exec_engine.calls

    # Wait briefly for background worker to process the queued ghost
    import time as _t
    _t.sleep(0.1)
    assert exec_engine.calls and exec_engine.calls[-1].volume == 0.02

    r2 = m.decide(req)
    assert r2['action'] == 'ghost'

    _t.sleep(0.1)
    assert len(exec_engine.calls) == 2

    r3 = m.decide(req)
    assert r3['action'] == 'reject'




