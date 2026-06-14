import MetaTrader5 as mt5

print('Initializing MT5 (no params)')
ok = mt5.initialize()
print('mt5.initialize() ->', ok)
acct = mt5.account_info()
if acct:
    print('Connected account:', acct.login, 'balance:', acct.balance, 'equity:', acct.equity)
else:
    print('Account info: None')

# list symbols with XAU or GOLD
symbols = [s.name for s in mt5.symbols_get()]
found = [s for s in symbols if 'XAU' in s.upper() or 'GOLD' in s.upper()]
print('Found symbols containing XAU/GOLD:', found[:50])

mt5.shutdown()
print('MT5 shutdown')




