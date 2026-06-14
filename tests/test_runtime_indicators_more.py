import pandas as pd
import numpy as np
import logging

from cthulu.__main__ import ensure_runtime_indicators
from cthulu.strategy.sma_crossover import SmaCrossover
from cthulu.indicators.macd import MACD
from cthulu.indicators.bollinger import BollingerBands
from cthulu.indicators.stochastic import Stochastic

logger = logging.getLogger('cthulu.tests')


def _make_ohlcv(n=300):
    rng = pd.date_range('2025-01-01', periods=n, freq='T')
    price = np.cumsum(np.random.normal(0, 0.1, n)) + 100.0
    df = pd.DataFrame({'open': price, 'high': price + 0.1, 'low': price - 0.1, 'close': price, 'volume': np.random.randint(1, 100, n)}, index=rng)
    return df


def test_ensure_runtime_adds_macd_bollinger_stochastic():
    df = _make_ohlcv(200)

    # Config includes indicators that should be present
    config = {
        'strategy': {'type': 'sma_crossover', 'params': {'fast_period': 10, 'slow_period': 30}},
        'indicators': [
            {'type': 'macd', 'params': {}},
            {'type': 'bollinger', 'params': {'period': 20, 'std_dev': 2.0}},
            {'type': 'stochastic', 'params': {'k_period': 14, 'd_period': 3, 'smooth': 3}}
        ]
    }

    strat = SmaCrossover({'type': 'sma_crossover', 'params': {'fast_period': 10, 'slow_period': 30}})
    indicators = []

    extra = ensure_runtime_indicators(df, indicators, strat, config, logger)

    types = [i.__class__.__name__.lower() for i in extra]
    assert 'macd' in types or any(isinstance(i, MACD) for i in extra)
    assert 'bollingerbands' in types or any(isinstance(i, BollingerBands) for i in extra)
    assert 'stochastic' in types or any(isinstance(i, Stochastic) for i in extra)

    # Apply the extra indicators to the DF (simulate main loop behavior)
    for ind in extra:
        data = ind.calculate(df)
        if data is not None:
            df = df.join(data, how='left')

    # Validate columns
    assert 'macd' in df.columns and 'signal' in df.columns and 'histogram' in df.columns
    assert 'bb_upper' in df.columns and 'bb_middle' in df.columns and 'bb_lower' in df.columns
    assert 'stoch_k' in df.columns and 'stoch_d' in df.columns




