"""
MT5 Connection Test Suite

Tests connection to MetaTrader 5 using credentials from .env file.
Verifies broker server connectivity and retrieves account information.

Run with: RUN_MT5_CONNECT_TESTS=1 pytest Cthulu/tests/test_connection.py -v
"""

import os
import sys
import pytest
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from cthulu.connector.mt5_connector import MT5Connector, ConnectionConfig
import pytest


@pytest.fixture(scope="module")
def mt5_connector():
    """Create and connect MT5Connector for tests."""
    login = os.getenv('MT5_LOGIN')
    password = os.getenv('MT5_PASSWORD')
    server = os.getenv('MT5_SERVER')
    
    # Skip the test unless explicitly enabled (avoid running MT5 tests in CI)
    if os.getenv('RUN_MT5_CONNECT_TESTS') != '1':
        pytest.skip("MT5 integration tests disabled - set RUN_MT5_CONNECT_TESTS=1 to enable")

    assert login and password and server, "MT5 credentials not set in environment"
    
    config = ConnectionConfig(
        login=int(login),
        password=password,
        server=server,
        timeout=60000,
        path=os.getenv('MT5_PATH', '')
    )
    
    connector = MT5Connector(config)
    assert connector.connect(), "Failed to connect to MT5"
    
    yield connector
    
    # Cleanup: disconnect after all tests
    connector.disconnect()


def test_environment_variables():
    """Verify that required MT5 environment variables are set."""
    required_vars = ['MT5_LOGIN', 'MT5_PASSWORD', 'MT5_SERVER']
    
    for var in required_vars:
        assert os.getenv(var), f"Environment variable {var} is not set"


def test_mt5_connection(mt5_connector):
    """Verify successful connection to MT5."""
    assert mt5_connector is not None, "MT5Connector is None"
    assert mt5_connector.is_connected(), "Not connected to MT5"


def test_account_info(mt5_connector):
    """Verify account information retrieval."""
    account_info = mt5_connector.get_account_info()
    
    assert account_info is not None, "Failed to retrieve account information"
    assert 'login' in account_info, "Account login missing"
    assert 'balance' in account_info, "Account balance missing"
    assert 'equity' in account_info, "Account equity missing"
    
    print(f"\nAccount Login: {account_info.get('login')}")
    print(f"Balance: {account_info.get('balance'):.2f}")
    print(f"Equity: {account_info.get('equity'):.2f}")
    print(f"Margin Level: {account_info.get('margin_level'):.2f}%")


def test_market_data(mt5_connector):
    """Verify market data retrieval for available symbols."""
    symbol = os.getenv('TEST_SYMBOL', 'EURUSD')
    
    import MetaTrader5 as mt5
    
    rates = mt5_connector.get_rates(
        symbol=symbol,
        timeframe=mt5.TIMEFRAME_H1,
        count=10
    )
    
    assert rates is not None, f"Failed to retrieve rates for {symbol}"
    assert len(rates) > 0, f"No rate data returned for {symbol}"
    
    print(f"\nRetrieved {len(rates)} bars for {symbol}")
    latest = rates[-1]
    # Handle both array indices and attribute access
    try:
        close_price = latest[4] if isinstance(latest, tuple) else latest['close']
    except (KeyError, TypeError):
        close_price = latest.close if hasattr(latest, 'close') else latest[4]
    print(f"Latest close: {close_price:.5f}")


def test_connection_health(mt5_connector):
    """Verify connection is healthy."""
    is_connected = mt5_connector.is_connected()
    assert is_connected, "Connection health check failed"





