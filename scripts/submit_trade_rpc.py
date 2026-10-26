#!/usr/bin/env python3
import json
import urllib.request
import urllib.error

url = 'http://127.0.0.1:8278/trade'
payload = {'symbol': 'GOLDM#', 'side': 'SELL', 'volume': 0.1}
req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        print('HTTP', resp.status)
        print(resp.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print('HTTPERR', e.code)
    try:
        print(e.read().decode('utf-8'))
    except Exception:
        pass
except Exception as e:
    print('ERR', e)
