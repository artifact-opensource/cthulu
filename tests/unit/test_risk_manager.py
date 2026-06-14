import pytest
from cthulu.position.risk_manager import suggest_sl_adjustment


def test_within_threshold_tiny_balance():
    # tiny balance; threshold 1%
    bal = 500.0
    price = 100.0
    proposed_sl = 99.0  # 1% away
    res = suggest_sl_adjustment('SYM', bal, price, proposed_sl, side='BUY')
    assert res['adjusted_sl'] is None
    assert res['reason'] == 'within threshold'


def test_exceeds_threshold_small_balance():
    bal = 2000.0
    price = 100.0
    proposed_sl = 95.0  # 5% away; threshold for 2k should be ~2%
    res = suggest_sl_adjustment('SYM', bal, price, proposed_sl, side='BUY')
    assert res['adjusted_sl'] is not None
    assert 'exceeds threshold' in res['reason']


def test_thresholds_from_config():
    bal = 8000.0
    price = 200.0
    proposed_sl = 150.0
    thresholds = {'tiny': 0.01, 'small': 0.02, 'medium': 0.05, 'large': 0.25}
    breakpoints = [1000.0, 5000.0, 20000.0]
    res = suggest_sl_adjustment('SYM', bal, price, proposed_sl, side='SELL', thresholds=thresholds, breakpoints=breakpoints)
    assert res['adjusted_sl'] is not None
    assert res['suggested_mindset'] in ('short-term','swing')




