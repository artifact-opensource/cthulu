import logging
import importlib

logger = logging.getLogger('cthulu.tests')
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
logger.addHandler(ch)

try:
    m = importlib.import_module('cthulu.tests.test_runtime_indicators')
except Exception as e:
    # direct import path fallback
    import sys
    sys.path.insert(0, 'c:\\workspace\\cthulu')
    m = importlib.import_module('tests.test_runtime_indicators')

failures = []
for name in dir(m):
    if name.startswith('test_'):
        fn = getattr(m, name)
        try:
            print(f"Running {name}...")
            fn()
            print(f"{name}: PASS")
        except AssertionError as ae:
            print(f"{name}: FAIL - {ae}")
            failures.append((name, ae))
        except Exception as ex:
            print(f"{name}: ERROR - {ex}")
            failures.append((name, ex))

if failures:
    print('\nSome tests failed:\n')
    for n, err in failures:
        print(n, err)
    raise SystemExit(1)
else:
    print('\nAll runtime indicator tests passed!')
