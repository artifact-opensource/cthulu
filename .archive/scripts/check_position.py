import MetaTrader5 as mt5
import sys
if len(sys.argv) < 2:
    print('Usage: check_position.py <ticket>')
    raise SystemExit(1)
ticket = int(sys.argv[1])
mt5.initialize()
pos = mt5.positions_get(ticket=ticket)
print('positions_get returned:', pos)
if pos:
    p = pos[0]
    print('ticket', p.ticket, 'symbol', p.symbol, 'volume', p.volume, 'sl', p.sl, 'tp', p.tp)
mt5.shutdown()




