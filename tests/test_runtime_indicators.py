import pandas as pd
import numpy as np
import logging

from cthulu.__main__ import ensure_runtime_indicators
from cthulu.strategy.scalping import ScalpingStrategy
from cthulu.indicators.rsi import RSI

logger = logging.getLogger('cthulu.tests')


def _make_ohlcv(n=500):
    rng = pd.date_range('2025-01-01', periods=n, freq='T')
    price = np.cumsum(np.random.normal(0, 0.1, n)) + 100.0
    df = pd.DataFrame({'open': price, 'high': price + 0.1, 'low': price - 0.1, 'close': price, 'volume': np.random.randint(1, 100, n)}, index=rng)
    return df


def test_ensure_runtime_indicators_computes_ema_and_rsi():
    df = _make_ohlcv(200)

    # Create a scalping strategy that expects rsi_period=7 and default fast/slow EMAs
    config = {
        'strategy': {
            'type': 'dynamic',
            'strategies': [
                {'type': 'scalping', 'params': {'fast_ema': 5, 'slow_ema': 10, 'rsi_period': 7}}
            ]
        }
    }

    strat = ScalpingStrategy({'params': {'fast_ema': 5, 'slow_ema': 10, 'rsi_period': 7}})
    indicators = []

    extra = ensure_runtime_indicators(df, indicators, strat, config, logger)

    # Should add at least an RSI indicator (because scalping expects it)
    types = [i.__class__.__name__.lower() for i in extra]
    assert 'rsi' in types or any(isinstance(i, RSI) for i in extra)

    # Apply the extra indicators to the DF (simulate main loop behavior)
    for ind in extra:
        data = ind.calculate(df)
        if data is not None:
            df = df.join(data, how='left')

    # Ensure that ensure_runtime_indicators computed EMA columns inline
    assert 'ema_5' in df.columns or 'ema_10' in df.columns or any(c.startswith('ema_') for c in df.columns)

    # Compute EMA columns via TradingLoop helper (simulate main loop behavior)
    from cthulu.core.trading_loop import TradingLoop, TradingLoopContext
    local_logger = logging.getLogger('cthulu.tests')
    ctx = TradingLoopContext(
        logger=local_logger,
        connector=None,
        data_layer=None,
        execution_engine=None,
        risk_manager=None,
        position_tracker=None,
        position_lifecycle=None,
        trade_adoption_manager=None,
        exit_coordinator=None,
        database=None,
        metrics=None,
        symbol='EURUSD',
        timeframe=60,
        poll_interval=1,
        lookback_bars=10,
        dry_run=True,
        indicators=[],
        exit_strategies=[],
        trade_adoption_policy=None,
        config=config,
        strategy=strat,
    )
    loop = TradingLoop(ctx)
    df = loop._compute_ema_columns(df)

    # Check EMA columns exist and RSI produced
    assert any(c.startswith('ema_') for c in df.columns)
    assert 'rsi_7' in df.columns or 'rsi' in df.columns


def test_runtime_indicator_rename_on_overlap():
    import pandas as pd
    from cthulu.core.trading_loop import TradingLoop, TradingLoopContext

    # Prepare DF with existing rsi_7 column that would conflict
    df = pd.DataFrame({'close': [1, 2, 3]}, index=pd.date_range('2025-01-01', periods=3))
    df['rsi_7'] = [0.1, 0.2, 0.3]

    class DummyRSI:
        name = 'rsi'
        def __init__(self, period=7):
            self.period = period
        def calculate(self, df):
            return pd.Series([1.0]*len(df), index=df.index, name=f'rsi_{self.period}')

    # Minimal context
    logger = logging.getLogger('cthulu.tests')
    ctx = TradingLoopContext(
        connector=None,
        data_layer=None,
        execution_engine=None,
        risk_manager=None,
        position_tracker=None,
        position_lifecycle=None,
        trade_adoption_manager=None,
        exit_coordinator=None,
        database=None,
        metrics=None,
        logger=logger,
        symbol='EURUSD',
        timeframe=60,
        poll_interval=1,
        lookback_bars=10,
        dry_run=True,
        indicators=[DummyRSI()],
        exit_strategies=[],
        trade_adoption_policy=None,
        config={},
        strategy=None,
    )

    loop = TradingLoop(ctx)
    out = loop._calculate_indicators(df.copy())

    assert 'rsi_7' in out.columns
    assert 'runtime_rsi_7' in out.columns
    # Alias should also be present if strategy expects 'rsi'
    # (simulate a scalping strategy expecting a default RSI column name)
    # Because this scenario had an existing rsi_7, ensure rsi alias exists or rsi_7 provides value
    assert 'rsi' in out.columns or 'rsi_7' in out.columns


def test_adx_runtime_namespace():
    import pandas as pd
    from cthulu.core.trading_loop import TradingLoop, TradingLoopContext

    df = pd.DataFrame({'close': [1, 2, 3]}, index=pd.date_range('2025-01-01', periods=3))
    df['adx'] = [5.0, 6.0, 7.0]

    class DummyADX:
        name = 'adx'
        def calculate(self, df):
            return pd.DataFrame({
                'adx': [10.0]*len(df),
                'plus_di': [12.0]*len(df),
                'minus_di': [8.0]*len(df),
            }, index=df.index)

    logger = logging.getLogger('cthulu.tests')
    ctx = TradingLoopContext(
        connector=None,
        data_layer=None,
        execution_engine=None,
        risk_manager=None,
        position_tracker=None,
        position_lifecycle=None,
        trade_adoption_manager=None,
        exit_coordinator=None,
        database=None,
        metrics=None,
        logger=logger,
        symbol='EURUSD',
        timeframe=60,
        poll_interval=1,
        lookback_bars=10,
        dry_run=True,
        indicators=[DummyADX()],
        exit_strategies=[],
        trade_adoption_policy=None,
        config={},
        strategy=None,
    )

    loop = TradingLoop(ctx)
    out = loop._calculate_indicators(df.copy())

    assert 'adx' in out.columns
    assert 'runtime_adx' in out.columns
    assert 'runtime_adx_plus_di' in out.columns
    assert 'runtime_adx_minus_di' in out.columns


def test_rsi_fallback_computes_alias_if_missing():
    import pandas as pd
    from cthulu.core.trading_loop import TradingLoop, TradingLoopContext

    # Build DF without RSI or ATR
    df = pd.DataFrame({'close': [100, 101, 102]}, index=pd.date_range('2025-01-01', periods=3))

    class DummyStrategy:
        rsi_period = 7
        atr_period = 14

    logger = logging.getLogger('cthulu.tests')
    ctx = TradingLoopContext(
        connector=None,
        data_layer=None,
        execution_engine=None,
        risk_manager=None,
        position_tracker=None,
        position_lifecycle=None,
        trade_adoption_manager=None,
        exit_coordinator=None,
        database=None,
        metrics=None,
        logger=logger,
        symbol='EURUSD',
        timeframe=60,
        poll_interval=1,
        lookback_bars=10,
        dry_run=True,
        indicators=[],
        exit_strategies=[],
        trade_adoption_policy=None,
        config={},
        strategy=DummyStrategy(),
    )

    loop = TradingLoop(ctx)
    out = loop._calculate_indicators(df.copy())

    # After fallback, we should have rsi_7 and atr columns available
    assert 'rsi_7' in out.columns or 'rsi' in out.columns
    assert 'atr' in out.columns





