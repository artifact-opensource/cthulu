import importlib, pkgutil
try:
    import cthulu
    print('cthulu file:', getattr(cthulu, '__file__', None))
    print('cthulu path:', list(getattr(cthulu, '__path__', [])))
    print('available submodules sample:', [m.name for m in pkgutil.iter_modules(getattr(cthulu,'__path__',[]))][:40])
except Exception as e:
    print('import error:', e)
    import traceback; traceback.print_exc()