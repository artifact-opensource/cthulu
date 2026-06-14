import MetaTrader5 as mt5
import time

print('Initializing MT5 (no params)...')
ok = mt5.initialize()
print('mt5.initialize() ->', ok)
acct = mt5.account_info()
print('Connected account:', acct.login if acct else None)

# Find a GOLD symbol candidate
sym = None
candidates = [s.name for s in mt5.symbols_get()[:200] if 'GOLD' in s.name.upper()]
if candidates:
    sym = candidates[0]
    print('Using symbol:', sym)
else:
    print('No GOLD symbol found in MT5 symbols; aborting')
    mt5.shutdown()
    raise SystemExit(1)

# Ensure symbol is selected
if not mt5.symbol_select(sym, True):
    print('Failed to select symbol', sym)
    mt5.shutdown()
    raise SystemExit(1)

# Place market BUY 0.1 as an external trade (magic=0)

tick = mt5.symbol_info_tick(sym)
if not tick:
    print('No tick data for', sym)
    mt5.shutdown()
    raise SystemExit(1)

info = mt5.symbol_info(sym)
vol_min = getattr(info, 'volume_min', 0.01)
vol_step = getattr(info, 'volume_step', 0.01)
volume = max(vol_min, vol_step)
print(f"Using volume: {volume}")

price = tick.ask
request = {
    'action': mt5.TRADE_ACTION_DEAL,
    'symbol': sym,
    'volume': volume,
    'type': mt5.ORDER_TYPE_BUY,
    'price': price,
    'deviation': 20,
    'magic': 0,
    'comment': 'external test trade',
    'type_time': mt5.ORDER_TIME_GTC,
    'type_filling': mt5.ORDER_FILLING_IOC,
}
print('Sending external order:', request)
res = mt5.order_send(request)
print('Order send result:', res)
try:
    print('retcode:', getattr(res,'retcode',None), 'comment:', getattr(res,'comment',None), 'order:', getattr(res,'order',None))
except Exception:
    print('Result did not have expected attributes, repr:', repr(res))

mt5.shutdown()
print('MT5 shutdown')




