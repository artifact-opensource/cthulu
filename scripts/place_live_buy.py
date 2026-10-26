import os, json, sys
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

# Load Cthulu modules
from cthulu.connector.mt5_connector import MT5Connector, ConnectionConfig
from cthulu.execution.engine import ExecutionEngine, OrderRequest, OrderType

import logging
logging.basicConfig(level=logging.INFO)

# Read credentials from env
login = os.getenv('MT5_LOGIN')
password = os.getenv('MT5_PASSWORD')
server = os.getenv('MT5_SERVER')
path = os.getenv('MT5_PATH') or os.getenv('MT5_TERMINAL_PATH')

if not (login and password and server):
    print(json.dumps({'error': 'Missing MT5 credentials in environment'}))
    sys.exit(2)

try:
    cfg = ConnectionConfig(login=int(login), password=password, server=server, path=path)
    conn = MT5Connector(cfg)
    ok = conn.connect()
    if not ok:
        print(json.dumps({'error': 'Failed to connect to MT5'}))
        sys.exit(3)

    eng = ExecutionEngine(conn)

    order = OrderRequest(
        signal_id='assistant_live_test',
        symbol='BTCUSD#m',
        side='BUY',
        volume=0.01,
        order_type=OrderType.MARKET,
    )

    res = eng.place_order(order)

    out = {
        'status': res.status.name if res and hasattr(res, 'status') else None,
        'order_id': getattr(res, 'order_id', None),
        'fill_price': getattr(res, 'executed_price', None),
        'filled_volume': getattr(res, 'executed_volume', None),
        'error': getattr(res, 'error', None),
        'metadata': getattr(res, 'metadata', None)
    }
    print(json.dumps(out))

except Exception as e:
    import traceback
    print(json.dumps({'exception': str(e), 'trace': traceback.format_exc()}))
    sys.exit(4)
finally:
    try:
        conn.disconnect()
    except Exception:
        pass




