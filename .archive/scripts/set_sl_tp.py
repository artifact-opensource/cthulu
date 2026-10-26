import MetaTrader5 as mt5
import sys
if len(sys.argv) < 3:
    print('Usage: set_sl_tp.py <ticket> <sl> [tp]')
    raise SystemExit(1)

ticket = int(sys.argv[1])
sl = float(sys.argv[2])
tp = float(sys.argv[3]) if len(sys.argv) > 3 else None

mt5.initialize()
pos = mt5.positions_get(ticket=ticket)
if not pos:
    print('Position not found')
    mt5.shutdown()
    raise SystemExit(1)

sym = pos[0].symbol
req = {'action': mt5.TRADE_ACTION_SLTP, 'position': ticket, 'symbol': sym}
if sl is not None:
    req['sl'] = sl
if tp is not None:
    req['tp'] = tp
print('Sending request:', req)
res = mt5.order_send(req)
print('Result:', res)
print('Last error:', mt5.last_error())
# read back
p = mt5.positions_get(ticket=ticket)[0]
print('Position after:', p.ticket, 'sl', p.sl, 'tp', p.tp)
mt5.shutdown()




