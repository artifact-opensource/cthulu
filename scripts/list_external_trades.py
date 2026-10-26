#!/usr/bin/env python
"""List external (orphan) trades visible to MT5 using a config file."""
import sys
from pathlib import Path
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from cthulu.connector.mt5_connector import MT5Connector, ConnectionConfig
from cthulu.position.trade_manager import TradeManager
from cthulu.position.manager import PositionManager

def main(cfg_path):
    cfg = json.loads(Path(cfg_path).read_text())
    conn_cfg = ConnectionConfig(**cfg['mt5'])
    conn = MT5Connector(conn_cfg)
    if not conn.connect():
        print('Failed to connect to MT5')
        return 1

    pm = PositionManager(conn)
    tm = TradeManager(pm)
    trades = tm.scan_for_external_trades()
    if not trades:
        print('No external trades found.')
        return 0

    for t in trades:
        print(f"Ticket: {t.ticket} | Symbol: {t.symbol} | Side: {t.side} | Volume: {t.volume} | PNL: {t.unrealized_pnl}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: list_external_trades.py <config.json>')
        sys.exit(2)
    sys.exit(main(sys.argv[1]))




