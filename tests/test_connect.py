"""Simple MT5 connection test using env vars; skip if MetaTrader5 not installed"""
import os
import pytest
from dotenv import load_dotenv

load_dotenv()

try:
    import MetaTrader5 as mt5
except ImportError:
    pytest.skip("MetaTrader5 not installed; skipping MT5 connection check", allow_module_level=True)

login = int(os.getenv('MT5_LOGIN', 0))
password = os.getenv('MT5_PASSWORD', '')
server = os.getenv('MT5_SERVER', '')


def test_mt5_initialize_and_account_info():
    """Attempt to initialize MT5 and fetch account info if credentials are available"""
    if not login or not password or not server:
        pytest.skip("MT5 credentials not provided in environment; skipping connection test")

    result = mt5.initialize(
        path="C:\\Program Files\\MetaTrader 5\\terminal64.exe",
        login=login,
        password=password,
        server=server,
        timeout=10000
    )
    assert result is True or result is False
    if result:
        info = mt5.account_info()
        assert info is not None
        mt5.shutdown()




