# Compatibility shim: expose legacy 'herald' package by reusing the internal 'news' package
import importlib as _importlib
import sys as _sys

_news = _importlib.import_module('news')

# Expose as herald.news
news = _news
_sys.modules['herald'] = _sys.modules.get('herald') or _news
_sys.modules['herald.news'] = _news
