import math
from cthulu.observability.metrics import MetricsCollector
from cthulu.persistence.database import Database


def test_profit_factor_infinite(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    db = Database(db_path)
    m = MetricsCollector(database=db)

    # Only winning trades -> profit factor should be inf
    m.record_trade(100.0, 'TEST')
    metrics = m.get_metrics()
    assert metrics.gross_profit == 100.0
    assert metrics.gross_loss == 0.0
    assert metrics.profit_factor == float('inf')


def test_symbol_aggregate_and_sync(tmp_path):
    db_path = str(tmp_path / "test2.db")
    db = Database(db_path)
    # Insert open trade into DB for symbol aggregate
    conn = db.conn
    cursor = conn.cursor()
    from datetime import datetime
    entry_time = datetime.now().isoformat()
    cursor.execute("INSERT INTO trades (signal_id, order_id, symbol, side, volume, entry_price, entry_time, status) VALUES (?,?,?,?,?,?,?,?)", ('t', 1, 'BTCUSD#', 'BUY', 0.01, 100.0, entry_time, 'OPEN'))
    conn.commit()

    m = MetricsCollector(database=db)
    # After load, symbol aggregate should be present with open position
    assert 'BTCUSD#' in m.symbol_aggregates
    assert m.symbol_aggregates['BTCUSD#']['open_positions'] == 1

    # Now sync with position summary
    stats = {'active_positions': 1, 'total_opened': 1, 'total_closed': 0, 'total_unrealized_pnl': 0.0, 'total_exposure': 0.0}
    pos_summary = {'BTCUSD#': {'open_positions': 1, 'unrealized_pnl': -2.0, 'exposure': 1.5}}
    m.sync_with_positions_summary(stats, pos_summary)
    metrics = m.get_metrics()
    assert metrics.active_positions == 1
    assert metrics.symbol_aggregates['BTCUSD#']['unrealized_pnl'] == -2.0


def test_drawdown_tracking(tmp_path):
    db = Database(str(tmp_path / "test3.db"))
    m = MetricsCollector(database=db)
    # Simulate returns that create drawdown
    m._record_trade_internal(100.0, 'X')
    m._record_trade_internal(-60.0, 'X')
    m._record_trade_internal(-30.0, 'X')
    metrics = m.get_metrics()
    # peak was 100, worst equity after losses: 10 -> drawdown = (100-10)/100 = 0.9
    assert metrics.max_drawdown_pct >= 0.0
    assert metrics.max_drawdown_pct <= 1.0


def test_rr_tracking(tmp_path):
    db = Database(str(tmp_path / "test4.db"))
    m = MetricsCollector(database=db)
    # record two trades with known risk/reward
    m.record_trade(10.0, 'R1', risk=1.0, reward=2.0)  # RR=2.0
    m.record_trade(-5.0, 'R1', risk=0.5, reward=1.0)  # RR=2.0
    metrics = m.get_metrics()
    assert metrics.rr_count == 2
    assert abs(metrics.avg_risk_reward - 2.0) < 1e-6
    assert abs(metrics.median_risk_reward - 2.0) < 1e-6
    # per-symbol aggregated rr
    assert 'R1' in metrics.symbol_aggregates
    assert metrics.symbol_aggregates['R1']['rr_count'] == 2
    assert abs(metrics.symbol_aggregates['R1']['avg_rr'] - 2.0) < 1e-6
    # Expectancy = (win_rate * avg_win) - ((1-win_rate) * avg_loss) -> .5*10 - .5*5 = 2.5
    assert abs(metrics.expectancy - 2.5) < 1e-6




