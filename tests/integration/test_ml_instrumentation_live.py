"""
Live integration test for ML instrumentation.

This test places a small market order using the real MT5 connector and ensures
that the MLDataCollector writes event data into the raw data directory.

Run with: RUN_MT5_INTEGRATION=1 pytest Cthulu/tests/integration/test_ml_instrumentation_live.py -q
"""
import os
import time
import glob
import gzip
import json
import pytest
from dotenv import load_dotenv

load_dotenv()

# Skip unless explicitly enabled
if os.getenv('RUN_MT5_INTEGRATION') != '1' and os.getenv('RUN_MT5_CONNECT_TESTS') != '1':
    pytest.skip("MT5 integration tests disabled - set RUN_MT5_INTEGRATION=1 to enable", allow_module_level=True)

from cthulu.connector.mt5_connector import MT5Connector, ConnectionConfig
from cthulu.execution.engine import ExecutionEngine, OrderRequest, OrderType, OrderStatus
from cthulu.training import instrumentation as instr
from cthulu.ML_RL.instrumentation import MLDataCollector


def test_ml_instrumentation_end_to_end():
    # Initialize connector locally
    login = os.getenv('MT5_LOGIN')
    password = os.getenv('MT5_PASSWORD')
    server = os.getenv('MT5_SERVER')

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

    # Preconditions
    acct = connector.get_account_info()
    assert acct and acct.get('trade_allowed', False), "Trading not allowed on the connected account"

    symbol = os.getenv('TEST_SYMBOL', 'GOLDm#')
    volume = float(os.getenv('TEST_VOLUME', '0.1'))

    # Create a collector that writes to a unique prefix to avoid collisions
    prefix = f"integration_{int(time.time())}_{os.getpid()}"
    collector = MLDataCollector(prefix=prefix)

    # Wire collector into execution engine
    engine = ExecutionEngine(connector, ml_collector=collector)

    # Place a market BUY order
    order_req = OrderRequest(
        signal_id='ml_integration_test',
        symbol=symbol,
        side='BUY',
        volume=volume,
        order_type=OrderType.MARKET
    )

    place_res = engine.place_order(order_req)
    assert place_res.status == OrderStatus.FILLED, f"Order placement failed: {place_res.error}"
    assert place_res.position_ticket is not None, "No position ticket returned after placing order"

    # Close the position
    close_res = engine.close_position(ticket=place_res.position_ticket, volume=place_res.executed_volume)
    assert close_res.status == OrderStatus.FILLED, f"Position close failed: {close_res.error}"

    # Verify that the collector wrote event files
    base = instr.BASE
    pattern = os.path.join(base, f"{prefix}*.jsonl.gz")
    files = glob.glob(pattern)

    # It's possible the file wasn't rotated into gzip yet; check for fallback or raw
    if not files:
        files = glob.glob(os.path.join(base, f"{prefix}*.jsonl"))

    assert files and len(files) > 0, f"No ML event files found for prefix {prefix}"

    # Ensure at least one file has content and valid JSON lines
    found_valid = False
    for p in files:
        try:
            if p.endswith('.gz'):
                with gzip.open(p, 'rt', encoding='utf-8') as fh:
                    for line in fh:
                        if not line.strip():
                            continue
                        try:
                            obj = json.loads(line)
                            # Basic health checks on recorded events
                            assert 'event_type' in obj and 'payload' in obj
                            found_valid = True
                            break
                        except Exception:
                            continue
            else:
                with open(p, 'r', encoding='utf-8') as fh:
                    for line in fh:
                        if not line.strip():
                            continue
                        try:
                            obj = json.loads(line)
                            assert 'event_type' in obj and 'payload' in obj
                            found_valid = True
                            break
                        except Exception:
                            continue
        except Exception:
            continue

    assert found_valid, "No valid JSON event lines found in ML event files"

    # Cleanup created files to keep test environment tidy
    for p in files:
        try:
            os.remove(p)
        except Exception:
            pass





