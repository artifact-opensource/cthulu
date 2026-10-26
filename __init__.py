__all__ = [
    "config",
    "connector",
    "execution",
    "indicators",
    "market",
    "persistence",
    "position",
    "risk",
    "strategy",
    "utils",
]

import sys
import importlib
import logging
logger = logging.getLogger(__name__) 

# Ensure inner package dir (./cthulu) is on __path__ so submodules like
# `cthulu.llm` are resolvable even when pytest or other tools shadow imports.
try:
    import os
    inner_pkg = os.path.join(os.path.dirname(__file__), 'cthulu')
    if os.path.isdir(inner_pkg) and inner_pkg not in __path__:
        __path__.insert(0, inner_pkg)
except Exception as e:
    logger.debug("Failed to ensure inner package on __path__: %s", e, exc_info=True)

# Lazy imports to avoid heavy import-time side-effects
_LAZY_IMPORTS = {
    "config": "cthulu.config",
    "connector": "cthulu.connector",
    "execution": "cthulu.execution",
    "indicators": "cthulu.indicators",
    "market": "cthulu.market",
    "persistence": "cthulu.persistence",
    "position": "cthulu.position",
    "risk": "cthulu.risk",
    "strategy": "cthulu.strategy",
    "utils": "cthulu.utils",
}

def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module = importlib.import_module(_LAZY_IMPORTS[name])
        globals()[name] = module
        return module
    raise AttributeError(name)


# Back-compat shim for legacy package name 'herald'
def _install_herald_shim():
    try:
        import types
        pkg_name = "herald"
        if pkg_name in sys.modules:
            return
        mod = types.ModuleType(pkg_name)
        mod.__path__ = __path__
        sys.modules[pkg_name] = mod
    except Exception as e:
        logger.debug("Failed to install herald shim: %s", e, exc_info=True)

_install_herald_shim()

def __dir__():
    return sorted(list(globals().keys()) + list(_LAZY_IMPORTS.keys()))




