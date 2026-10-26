"""Simple script to test order provenance logging locally.

Usage: python Cthulu/scripts/test_order_provenance.py

This will create an ExecutionEngine with a stub connector, monkeypatch mt5.order_send, and call place_order.
It prints the ExecutionResult and the latest entry in `Cthulu/logs/order_provenance.log`.
"""

import os
import json
from unittest.mock import MagicMock
# Stub missing modules to allow running in isolated test environment
import types, sys
mod = types.ModuleType('cthulu.position')
mod.risk_manager = types.SimpleNamespace()
sys.modules['cthulu.position'] = mod

# Import engine module directly from file to avoid package import side-effects
from importlib.machinery import SourceFileLoader
eng_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'execution', 'engine.py'))
eng_mod = SourceFileLoader('execution_engine_mod', eng_path).load_module()
ExecutionEngine = eng_mod.ExecutionEngine
OrderRequest = eng_mod.OrderRequest
OrderType = eng_mod.OrderType
mt5 = eng_mod.mt5

# Prepare connector stub
connector = MagicMock()
connector.is_connected.return_value = True
connector.get_symbol_info.return_value = {'ask': 1.2346, 'bid': 1.2344}
connector.get_account_info.return_value = {'trade_allowed': True}

# Monkeypatch mt5.order_send
import cthulu.execution.engine as eng_mod
mock_result = MagicMock()
# Simulate MT5 success
mock_result.retcode = getattr(eng_mod.mt5, 'TRADE_RETCODE_DONE', 10009)
mock_result.price = 1.2345
mock_result.volume = 0.1
mock_result.order = 777
mock_result.comment = 'done'
eng_mod.mt5.order_send = MagicMock(return_value=mock_result)
eng_mod.mt5.positions_get = MagicMock(return_value=[])

# Create a DB for telemetry and Telemetry helper (use a temp file)
from importlib.machinery import SourceFileLoader as _SFL
# Load persistence.database without triggering package-level imports
db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'temp_prov.db'))
db_mod = _SFL('persistence_database', os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'persistence', 'database.py'))).load_module()
Database = db_mod.Database
# Ensure we start with a clean DB
try:
    os.remove(db_path)
except Exception:
    pass

db = Database(db_path)
telemetry_mod = _SFL('telemetry_mod', os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'observability', 'telemetry.py'))).load_module()
Telemetry = telemetry_mod.Telemetry
telemetry = Telemetry(db)

# Create engine with telemetry
engine = ExecutionEngine(connector=connector, telemetry=telemetry)

order_req = OrderRequest(
    signal_id='test_sig',
    symbol='EURUSD',
    side='BUY',
    volume=0.1,
    order_type=OrderType.MARKET
)

res = engine.place_order(order_req)
print('ExecutionResult:', res)

# Show last provenance entry
prov_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'logs', 'order_provenance.log'))
if os.path.exists(prov_path):
    with open(prov_path, 'r', encoding='utf-8') as fh:
        lines = fh.readlines()
        print('\nLast provenance entry:')
        print(lines[-1].strip())
else:
    print('No provenance log found at', prov_path)




