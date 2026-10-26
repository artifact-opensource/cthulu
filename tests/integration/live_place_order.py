from dotenv import load_dotenv
import os, json, time
from cthulu.connector.mt5_connector import MT5Connector, ConnectionConfig
from cthulu.ML_RL.instrumentation import MLDataCollector
from cthulu.execution.engine import ExecutionEngine, OrderRequest, OrderType, OrderStatus

load_dotenv()

login = os.getenv('MT5_LOGIN')
password = os.getenv('MT5_PASSWORD')
server = os.getenv('MT5_SERVER')
symbol = os.getenv('TEST_SYMBOL', 'GOLDm#')
volume = float(os.getenv('TEST_VOLUME', '0.1'))

cfg = ConnectionConfig(login=int(login), password=password, server=server, timeout=60000, path=os.getenv('MT5_PATH',''))
conn = MT5Connector(cfg)
if not conn.connect():
    print(json.dumps({'status':'connect_failed'}))
else:
    sel = conn.ensure_symbol_selected(symbol)
    sym = conn.get_symbol_info(sel) if sel else None
    prefix = f"live_{int(time.time())}_{os.getpid()}"
    collector = MLDataCollector(prefix=prefix)
    engine = ExecutionEngine(conn, ml_collector=collector)

    order_req = OrderRequest(signal_id='live_run', symbol=sel, side='BUY', volume=volume, order_type=OrderType.MARKET)
    res = engine.place_order(order_req)
    out = {
        'status': 'placed' if res.status == OrderStatus.FILLED else 'failed',
        'order_status': res.status.name if res.status else None,
        'order_id': res.order_id,
        'position_ticket': res.position_ticket,
        'price': res.executed_price,
        'volume': res.executed_volume,
        'error': res.error,
        'symbol': sel,
        'collector_prefix': prefix,
        'symbol_info': sym
    }
    with open('tests/integration/live_last.json','w',encoding='utf-8') as fh:
        json.dump(out, fh, default=str)
    print(json.dumps(out, default=str))




