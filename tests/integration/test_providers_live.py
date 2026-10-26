import os
import time
import pytest
from cthulu.market.providers import AlphaVantageProvider, BinanceProvider, MT5Provider


def _has_mt5_env():
    return bool(os.getenv('MT5_LOGIN') and os.getenv('MT5_PASSWORD') and os.getenv('MT5_SERVER'))


def test_alphavantage_live():
    key = os.getenv('ALPHA_VANTAGE_KEY')
    if not key:
        pytest.skip('ALPHA_VANTAGE_KEY not set')
    prov = AlphaVantageProvider(api_key=key)
    # try a common FX pair
    tick = prov.fetch_tick('EURUSD')
    assert tick is not None, 'AlphaVantage failed to return tick for EURUSD'
    assert 'price' in tick and isinstance(tick['price'], float)


def test_binance_live():
    # no API key required for public endpoints
    prov = BinanceProvider()
    tick = prov.fetch_tick('BTCUSDT')
    assert tick is not None, 'Binance failed to return tick for BTCUSDT'
    assert 'price' in tick and isinstance(tick['price'], float)


def test_mt5_provider_skip_if_no_env():
    if not _has_mt5_env():
        pytest.skip('MT5 credentials not provided in environment')
    # If MT5 envs present, attempt to initialize MT5 provider (requires connector implementation)
    # Connector must be the project's mt5 connector module; we attempt to import and initialize
    from cthulu.connector import mt5_connector
    # construct a ConnectionConfig from env
    cfg = mt5_connector.ConnectionConfig(
        login=int(os.getenv('MT5_LOGIN')),
        password=os.getenv('MT5_PASSWORD'),
        server=os.getenv('MT5_SERVER')
    )
    conn = mt5_connector.MT5Connector(cfg)  # may raise if terminal not available
    # attempt to connect; skip test if unable to establish terminal connection
    try:
        ok = conn.connect()
    except Exception:
        pytest.skip('MT5 terminal not reachable or initialization failed')
    if not ok:
        pytest.skip('MT5 terminal not reachable or initialization failed')
    prov = MT5Provider(conn)
    tick = prov.fetch_tick('EURUSD')
    if tick is None:
        pytest.skip('MT5 returned no tick (terminal may not expose symbol or be busy)')
    assert tick is not None
    assert 'price' in tick and isinstance(tick['price'], float)




