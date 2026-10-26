import MetaTrader5 as mt5
import sys
sym = sys.argv[1] if len(sys.argv) > 1 else 'GOLDm#'
print('Initializing MT5...')
mt5.initialize()
info = mt5.symbol_info(sym)
print('Symbol info for', sym, ':', info)
if info:
    print('volume_min', getattr(info, 'volume_min', None), 'volume_step', getattr(info, 'volume_step', None), 'digits', getattr(info, 'digits', None))
    tick = mt5.symbol_info_tick(sym)
    print('tick ask, bid:', getattr(tick, 'ask', None), getattr(tick, 'bid', None))
mt5.shutdown()
print('done')




