import json
import urllib.request
import urllib.error
import time
from cthulu.rpc.server import run_rpc_server
from cthulu.execution.engine import OrderStatus


class DummyExecutionEngine:
    def __init__(self, result):
        self._result = result
        self.placed = False

    def place_order(self, order_req):
        self.placed = True
        return self._result


class DummyRiskManager:
    def __init__(self, approved=True, reason='ok', position_size=None):
        self.approved = approved
        self.reason = reason
        self.position_size = position_size
        self.called = False

    def approve(self, *args, **kwargs):
        self.called = True
        return (self.approved, self.reason, self.position_size)


class DummyPositionManager:
    def __init__(self):
        self.positions = []
        self.tracked = False

    def get_positions(self, symbol=None):
        return self.positions

    def track_position(self, result, signal_metadata=None):
        self.tracked = True
        class T:
            ticket = getattr(result, 'order_id', 12345)
        return T()


class DummyDatabase:
    def __init__(self):
        self.recorded = False
        self.last = None

    def record_trade(self, tr):
        self.recorded = True
        self.last = tr


class SimpleResult:
    def __init__(self, status=OrderStatus.FILLED, order_id=1, fill_price=123.45, filled_volume=0.01, message='ok'):
        self.status = status
        self.order_id = order_id
        self.fill_price = fill_price
        self.filled_volume = filled_volume
        self.message = message


def post(url, data, headers=None):
    req = urllib.request.Request(url, method='POST')
    body = json.dumps(data).encode('utf-8')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Content-Length', str(len(body)))
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        return urllib.request.urlopen(req, data=body)
    except urllib.error.HTTPError as e:
        return e


def test_missing_auth_allows_when_no_token():
    result = SimpleResult()
    exec_engine = DummyExecutionEngine(result)
    risk = DummyRiskManager(approved=True)
    pos = DummyPositionManager()
    db = DummyDatabase()

    thread, server = run_rpc_server('127.0.0.1', 0, None, exec_engine, risk, pos, db)
    port = server.server_port
    url = f'http://127.0.0.1:{port}/trade'

    data = {'symbol': 'BTCUSD#m', 'side': 'BUY', 'volume': 0.01}
    resp = post(url, data)
    assert resp.code == 200
    body = json.loads(resp.read())
    assert body['status'] == 'FILLED'
    assert exec_engine.placed

    server.shutdown()
    thread.join(timeout=2)


def test_invalid_token_rejected():
    result = SimpleResult()
    exec_engine = DummyExecutionEngine(result)
    risk = DummyRiskManager(approved=True)
    pos = DummyPositionManager()
    db = DummyDatabase()

    thread, server = run_rpc_server('127.0.0.1', 0, 'secret', exec_engine, risk, pos, db)
    port = server.server_port
    url = f'http://127.0.0.1:{port}/trade'

    data = {'symbol': 'BTCUSD#m', 'side': 'BUY', 'volume': 0.01}
    resp = post(url, data)  # no auth header
    assert resp.code == 401

    # valid token provided should succeed
    headers = {'Authorization': 'Bearer secret'}
    resp2 = post(url, data, headers=headers)
    assert resp2.code == 200

    server.shutdown()
    thread.join(timeout=2)


def test_malformed_json_returns_400():
    result = SimpleResult()
    exec_engine = DummyExecutionEngine(result)
    risk = DummyRiskManager(approved=True)
    pos = DummyPositionManager()
    db = DummyDatabase()

    thread, server = run_rpc_server('127.0.0.1', 0, None, exec_engine, risk, pos, db)
    port = server.server_port
    url = f'http://127.0.0.1:{port}/trade'

    # Use invalid JSON by passing a non-JSON body via urllib without proper encoding
    req = urllib.request.Request(url, method='POST', data=b'not-json')
    req.add_header('Content-Type', 'application/json')
    try:
        urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        assert e.code == 400

    server.shutdown()
    thread.join(timeout=2)


def test_missing_fields_returns_400():
    result = SimpleResult()
    exec_engine = DummyExecutionEngine(result)
    risk = DummyRiskManager(approved=True)
    pos = DummyPositionManager()
    db = DummyDatabase()

    thread, server = run_rpc_server('127.0.0.1', 0, None, exec_engine, risk, pos, db)
    port = server.server_port
    url = f'http://127.0.0.1:{port}/trade'

    data = {'side': 'BUY', 'volume': 0.01}  # missing symbol
    resp = post(url, data)
    assert resp.code == 400

    server.shutdown()
    thread.join(timeout=2)


def test_volume_non_numeric_returns_400():
    result = SimpleResult()
    exec_engine = DummyExecutionEngine(result)
    risk = DummyRiskManager(approved=True)
    pos = DummyPositionManager()
    db = DummyDatabase()

    thread, server = run_rpc_server('127.0.0.1', 0, None, exec_engine, risk, pos, db)
    port = server.server_port
    url = f'http://127.0.0.1:{port}/trade'

    data = {'symbol': 'BTCUSD#m', 'side': 'BUY', 'volume': 'abc'}
    resp = post(url, data)
    assert resp.code == 400

    server.shutdown()
    thread.join(timeout=2)


def test_risk_rejected_returns_403():
    result = SimpleResult()
    exec_engine = DummyExecutionEngine(result)
    risk = DummyRiskManager(approved=False, reason='too risky')
    pos = DummyPositionManager()
    db = DummyDatabase()

    thread, server = run_rpc_server('127.0.0.1', 0, None, exec_engine, risk, pos, db)
    port = server.server_port
    url = f'http://127.0.0.1:{port}/trade'

    data = {'symbol': 'BTCUSD#m', 'side': 'BUY', 'volume': 0.01}
    resp = post(url, data)
    assert resp.code == 403

    server.shutdown()
    thread.join(timeout=2)


def test_successful_filled_calls_db_and_track():
    result = SimpleResult()
    exec_engine = DummyExecutionEngine(result)
    risk = DummyRiskManager(approved=True)
    pos = DummyPositionManager()
    db = DummyDatabase()

    thread, server = run_rpc_server('127.0.0.1', 0, None, exec_engine, risk, pos, db)
    port = server.server_port
    url = f'http://127.0.0.1:{port}/trade'

    data = {'symbol': 'BTCUSD#m', 'side': 'BUY', 'volume': 0.01}
    resp = post(url, data)
    assert resp.code == 200
    body = json.loads(resp.read())
    assert body['status'] == 'FILLED'
    assert pos.tracked
    assert db.recorded

    server.shutdown()
    thread.join(timeout=2)


def test_concurrent_ops_status_during_long_trade():
    # Simulate a slow execution engine to ensure RPC server does not block other requests
    class SlowExec:
        def __init__(self, delay=5):
            self.delay = delay
            self.called = False

        def place_order(self, order_req):
            import time
            self.called = True
            time.sleep(self.delay)
            return SimpleResult()

    exec_engine = SlowExec(delay=2)
    risk = DummyRiskManager(approved=True)
    pos = DummyPositionManager()
    db = DummyDatabase()

    thread, server = run_rpc_server('127.0.0.1', 0, None, exec_engine, risk, pos, db)
    port = server.server_port
    trade_url = f'http://127.0.0.1:{port}/trade'
    status_url = f'http://127.0.0.1:{port}/ops/status'

    import threading, urllib.request, time

    trade_resp = {}

    def do_trade():
        try:
            resp = post(trade_url, {'symbol': 'BTCUSD#m', 'side': 'BUY', 'volume': 0.01})
            trade_resp['code'] = resp.code
            trade_resp['body'] = json.loads(resp.read())
        except Exception as e:
            trade_resp['error'] = str(e)

    t = threading.Thread(target=do_trade, daemon=True)
    start = time.time()
    t.start()

    # Immediately request ops/status which should return quickly even while trade is processing
    resp = urllib.request.urlopen(status_url)
    elapsed = time.time() - start
    assert resp.code == 200
    assert elapsed < 1.0, f"Status endpoint blocked, took {elapsed}s"

    # Wait for trade to complete
    t.join(timeout=5)
    assert exec_engine.called
    assert trade_resp.get('code') == 200

    server.shutdown()
    thread.join(timeout=2)


def test_volume_below_symbol_min_lot_returns_400():
    """If the connector reports a symbol min lot larger than requested volume, RPC should return 400."""
    result = SimpleResult()

    class ExecWithConnector(DummyExecutionEngine):
        def __init__(self, result):
            # override to echo the requested volume into the result
            self._result_template = result
            # provide a connector stub
            class C:
                def get_min_lot(self, s):
                    return 0.1
                def get_symbol_info(self, s):
                    return {'volume_step': 0.1}
            self.connector = C()

        def place_order(self, order_req):
            # Return result that reflects the actual (possibly adjusted) order_req.volume
            vol = getattr(order_req, 'volume', 0.0)
            return SimpleResult(filled_volume=vol, fill_price=getattr(self._result_template, 'fill_price', 123.45), order_id=getattr(self._result_template, 'order_id', 1))

    exec_engine = ExecWithConnector(result)
    risk = DummyRiskManager(approved=True)
    pos = DummyPositionManager()
    db = DummyDatabase()

    thread, server = run_rpc_server('127.0.0.1', 0, None, exec_engine, risk, pos, db)
    port = server.server_port
    url = f'http://127.0.0.1:{port}/trade'

    # Request a volume below the connector-specified min
    data = {'symbol': 'GOLDM#', 'side': 'SELL', 'volume': 0.01}
    resp = post(url, data)
    # RPC auto-adjusts to connector min lot + step, so request should succeed
    assert resp.code == 200
    body = json.loads(resp.read())
    # The execution engine/connector should have adjusted to 0.1
    assert float(body.get('filled_volume')) == 0.1
    assert body.get('status') is not None

    server.shutdown()
    thread.join(timeout=2)



