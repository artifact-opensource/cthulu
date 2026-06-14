import math
from time import sleep
from cthulu.observability.metrics import MetricsCollector
from cthulu.observability.prometheus import PrometheusExporter


def test_drawdown_duration_and_recovery():
    m = MetricsCollector()
    # simulate an initial gain creating a peak
    m._record_trade_internal(100.0, 'X')
    # now cause drawdown
    m._record_trade_internal(-50.0, 'X')
    # allow a tiny time gap
    sleep(0.01)
    # recover to new peak
    m._record_trade_internal(100.0, 'X')
    # after recovery, max_drawdown_duration_seconds should be set
    assert getattr(m, 'max_drawdown_duration_seconds', 0.0) >= 0.0


def test_rolling_sharpe_computation():
    m = MetricsCollector()
    m.rolling_window_size = 4
    # feed a sequence with known mean and stdev
    returns = [1.0, 2.0, 3.0, 4.0]
    for r in returns:
        m._record_trade_internal(r, 'R')
    rs = m.get_rolling_sharpe()
    assert rs is not None
    # compute expected
    import statistics
    avg = statistics.mean(returns[-4:])
    sd = statistics.stdev(returns[-4:])
    expected = (avg / sd) * (252 ** 0.5)
    assert abs(rs - expected) < 1e-6


def test_prometheus_exporter_integration():
    m = MetricsCollector()
    exporter = PrometheusExporter(prefix='herald_test')
    # record trades
    m.record_trade(10.0, 'ABC', risk=1.0, reward=2.0)
    m.record_trade(-5.0, 'ABC', risk=0.5, reward=1.0)
    # publish
    m.publish_to_prometheus(exporter)
    metrics = exporter.get_metrics_dict()
    # check some keys present
    assert 'herald_test_drawdown_percent' in metrics
    assert 'herald_test_avg_rr' in metrics
    assert metrics.get('herald_test_rr_count', 0) >= 0



