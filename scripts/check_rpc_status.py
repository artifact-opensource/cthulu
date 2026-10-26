import urllib.request
import urllib.error

url='http://127.0.0.1:8278/ops/status'
try:
    with urllib.request.urlopen(url, timeout=5) as r:
        print('HTTP', r.status)
        print(r.read().decode())
except urllib.error.HTTPError as e:
    print('HTTPERR', e.code)
    try:
        print(e.read().decode())
    except Exception:
        pass
except Exception as e:
    print('ERR', e)
