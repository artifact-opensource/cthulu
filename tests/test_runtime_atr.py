import pandas as pd
import numpy as np
import logging

from cthulu.__main__ import ensure_runtime_indicators
from cthulu.strategy.scalping import ScalpingStrategy
from types import SimpleNamespace


def make_sample_df(n=100):
    idx = pd.date_range(end=pd.Timestamp.now(), periods=n, freq='T')
    df = pd.DataFrame({
        'open': 100 + np.random.randn(n).cumsum(),
        'high': 100 + np.random.randn(n).cumsum() + 1,
        'low': 100 + np.random.randn(n).cumsum() - 1,
        'close': 100 + np.random.randn(n).cumsum(),
    }, index=idx)
    return df


def test_runtime_atr_added_for_scalping():
    logger = logging.getLogger('test')
    df = make_sample_df()
    # Start without 'atr' column
    assert 'atr' not in df.columns

    indicators = []
    # Create scalping strategy instance (using default params)
    strat = ScalpingStrategy({'params': {}})
    config = {'strategy': {'type': 'scalping', 'params': {}}}

    extra = ensure_runtime_indicators(df, indicators, strat, config, logger)

    # After ensure_runtime_indicators, df should contain 'atr'
    assert 'atr' in df.columns
    assert df['atr'].notnull().any()




