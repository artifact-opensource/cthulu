import pandas as pd
import numpy as np
import logging

from cthulu.__main__ import ensure_runtime_indicators
from cthulu.strategy.sma_crossover import SmaCrossover
from cthulu.indicators.supertrend import Supertrend
from cthulu.indicators.vwap import VWAP

logger = logging.getLogger('cthulu.tests')


def _make_ohlcv(n=300):
    rng = pd.date_range('2025-01-01', periods=n, freq='T')
    price = np.cumsum(np.random.normal(0, 0.1, n)) + 100.0
    df = pd.DataFrame({'open': price, 'high': price + 0.1, 'low': price - 0.1, 'close': price, 'volume': np.random.randint(1, 100, n)}, index=rng)
    return df


def test_ensure_runtime_adds_supertrend_and_vwap():
    df = _make_ohlcv(200)

    # Config includes indicators that should be present
    config = {
        'strategy': {'type': 'sma_crossover', 'params': {'fast_period': 10, 'slow_period': 30}},
        'indicators': [
            {'type': 'supertrend', 'params': {'period': 10, 'atr_multiplier': 3.0}},
            {'type': 'vwap', 'params': {}}
        ]
    }

    strat = SmaCrossover({'type': 'sma_crossover', 'params': {'fast_period': 10, 'slow_period': 30}})
    indicators = []

    extra = ensure_runtime_indicators(df, indicators, strat, config, logger)

    types = [i.__class__.__name__.lower() for i in extra]
    assert 'supertrend' in types or any(isinstance(i, Supertrend) for i in extra)
    assert 'vwap' in types or any(isinstance(i, VWAP) for i in extra)

    # Apply the extra indicators to the DF (simulate main loop behavior)
    for ind in extra:
        data = ind.calculate(df)
        if data is not None:
            df = df.join(data, how='left')

    # Validate columns
    assert 'supertrend' in df.columns and 'supertrend_direction' in df.columns
    assert 'vwap' in df.columns and 'vwap_upper' in df.columns and 'vwap_lower' in df.columns




