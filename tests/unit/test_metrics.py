from cthulu.observability.metrics import MetricsCollector


def test_metrics_record_and_summary():
    m = MetricsCollector()
    m.reset()
    m.record_trade(10.0)
    m.record_trade(-5.0)
    stats = m.get_metrics()
    assert stats.total_trades == 2
    assert stats.winning_trades == 1
    assert stats.losing_trades == 1
    assert abs(stats.net_profit - 5.0) < 1e-6
    # Ensure print_summary runs without exception
    m.print_summary()



