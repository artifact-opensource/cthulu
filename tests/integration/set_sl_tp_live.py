from dotenv import load_dotenv
import os, json, time
from cthulu.connector.mt5_connector import MT5Connector, ConnectionConfig
from cthulu.position.manager import PositionManager
from cthulu.execution.engine import ExecutionEngine
from cthulu.ML_RL.instrumentation import MLDataCollector

load_dotenv()

# Read last placed order info
with open('tests/integration/live_last.json','r',encoding='utf-8') as fh:
    last = json.load(fh)

ticket = last.get('position_ticket')
sym = last.get('symbol')
price = float(last.get('price'))
print('Found live order:', ticket, sym, price)

login = os.getenv('MT5_LOGIN')
password = os.getenv('MT5_PASSWORD')
server = os.getenv('MT5_SERVER')
cfg = ConnectionConfig(login=int(login), password=password, server=server, timeout=60000, path=os.getenv('MT5_PATH',''))
conn = MT5Connector(cfg)
if not conn.connect():
    print('Connect failed'); raise SystemExit(1)

collector = MLDataCollector(prefix=f"sltp_{int(time.time())}_{os.getpid()}")
engine = ExecutionEngine(conn, ml_collector=collector)
pos_manager = PositionManager(conn, engine)

# Compute SL/TP
sym_info = conn.get_symbol_info(sym)
digits = int(sym_info.get('digits',5))
sl = round(price - 5.0, digits)
tp = round(price + 10.0, digits)
print('Setting SL=', sl, 'TP=', tp, 'on ticket', ticket)
res = pos_manager.set_sl_tp(ticket, sl=sl, tp=tp)
print('set_sl_tp result:', res)

# Read back position
import MetaTrader5 as mt5
positions = mt5.positions_get(ticket=ticket)
print('positions_get:', bool(positions))
if positions:
    p = positions[0]
    print('position sl,tp:', getattr(p,'sl',None), getattr(p,'tp',None))

# leave position open; check ML events produced
base_dir = os.path.join(os.path.dirname(__file__), '..', 'training', 'data', 'raw')
base = os.path.normpath(base_dir)
files = [f for f in os.listdir(base) if f.startswith('sltp_')]
print('New ML files with prefix sltp_:', files)

# do not close, but flush collector
time.sleep(1.0)
collector.close(timeout=2.0)

conn.disconnect()
print('Done')





