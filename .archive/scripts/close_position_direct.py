import MetaTrader5 as mt5
import sys
import re

if len(sys.argv) < 2:
    print('Usage: close_position_direct.py <ticket>')
    raise SystemExit(1)

ticket = int(sys.argv[1])
mt5.initialize()
pos = mt5.positions_get(ticket=ticket)
if not pos:
    print('Position not found')
    mt5.shutdown()
    raise SystemExit(1)

p = pos[0]
side = 'BUY' if p.type == mt5.ORDER_TYPE_BUY else 'SELL'
if p.type == mt5.ORDER_TYPE_BUY:
    close_price = mt5.symbol_info_tick(p.symbol).bid
    order_type = mt5.ORDER_TYPE_SELL
else:
    close_price = mt5.symbol_info_tick(p.symbol).ask
    order_type = mt5.ORDER_TYPE_BUY

request = {
    'action': mt5.TRADE_ACTION_DEAL,
    'symbol': p.symbol,
    'volume': p.volume,
    'type': order_type,
    'position': ticket,
    'price': close_price,
    'deviation': 10,
    'magic': 9999,
    'type_time': mt5.ORDER_TIME_GTC,
    'type_filling': mt5.ORDER_FILLING_IOC,
}

raw_comment = 'Close: test close'
cleaned = re.sub(r"[\r\n\t]+", ' ', raw_comment)
cleaned = re.sub(r"\s+", ' ', cleaned).strip()
cleaned = ''.join(ch for ch in cleaned if 32 <= ord(ch) <= 126)
if len(cleaned) > 31:
    cleaned = cleaned[:31]
if cleaned:
    request['comment'] = cleaned

print('Sending close request:', request)
res = mt5.order_send(request)
print('Result:', res)
try:
    print('retcode, comment, order, deal:', getattr(res,'retcode',None), getattr(res,'comment',None), getattr(res,'order',None), getattr(res,'deal',None))
except Exception:
    print('Result repr:', repr(res))

# If broker rejects due to comment, retry without comment
if res is None or getattr(res,'retcode',None) != mt5.TRADE_RETCODE_DONE:
    comment_text = getattr(res,'comment','') if res is not None else ''
    err = getattr(res,'comment',None) if res else mt5.last_error()
    if (comment_text and 'Invalid "comment" argument' in comment_text) or (getattr(res,'retcode',None) == -2):
        print('Broker rejected comment; retrying without comment')
        req2 = {k:v for k,v in request.items() if k != 'comment'}
        r2 = mt5.order_send(req2)
        print('Retry result:', r2)

mt5.shutdown()
print('done')




