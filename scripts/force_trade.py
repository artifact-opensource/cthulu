"""Force a test trade using Cthulu's execution engine."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from cthulu.connector.mt5_connector import MT5Connector, ConnectionConfig
from cthulu.execution.engine import ExecutionEngine, OrderRequest, OrderType
from config_schema import Config
import json
import MetaTrader5 as mt5
import os

# Load config
config_obj = Config.load('config.json')
config = config_obj.model_dump() if hasattr(config_obj, 'model_dump') else config_obj.dict()

# Connect to MT5
print("Connecting to MT5...")
connector = MT5Connector(ConnectionConfig(**config['mt5']))
connector.connect()

# Get account info
account = connector.get_account_info()
print(f"Account: {account['login']}")
print(f"Balance: ${account['balance']:.2f}")
print(f"Equity: ${account['equity']:.2f}")

# Get current price for BTCUSD#
symbol = config['trading']['symbol']
tick = mt5.symbol_info_tick(symbol)
print(f"\n{symbol} Ask: {tick.ask}, Bid: {tick.bid}")

# Create execution engine and place a small BUY order
engine = ExecutionEngine(connector, risk_config=config.get('risk', {}))
order = OrderRequest(
    signal_id='force-test',
    symbol=symbol,
    order_type=OrderType.MARKET,
    volume=0.01,  # Minimum lot size
    side='BUY',
    client_tag='force-test',
    metadata={'note': 'Cthulu forced test trade'},
)

print(f"\nPlacing BUY order for 0.01 lot {symbol}...")
result = engine.place_order(order)
print(f"Order result: {result}")

if result and result.order_id:
    print(f"\n✅ Trade placed successfully! Ticket: {result.order_id}")
else:
    print(f"\n❌ Trade failed: {result}")

connector.disconnect()
print("\nDisconnected from MT5")




