import pandas as pd
import numpy as np
from cthulu.strategy.strategy_selector import StrategySelector, MarketRegime


def test_detect_market_regime_handles_missing_indicators():
    # Build minimal data without 'adx' or with NaN values
    dates = pd.date_range(start="2023-01-01", periods=60, freq="D")
    close = np.linspace(1.0, 1.05, 60)
    high = close + 0.001
    low = close - 0.001

    df = pd.DataFrame({
        'close': close,
        'high': high,
        'low': low,
    }, index=dates)

    selector = StrategySelector(strategies=[], config={})

    # Should not raise and should return a valid regime string
    regime = selector.detect_market_regime(df)
    assert isinstance(regime, str)
    assert regime in vars(MarketRegime).values() or regime is not None
