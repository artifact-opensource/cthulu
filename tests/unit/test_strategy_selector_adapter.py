import pandas as pd
from cthulu.strategy.strategy_selector import StrategySelector
from cthulu.strategy.selector_adapter import StrategySelectorAdapter
from cthulu.strategy.base import Strategy, Signal, SignalType
from cthulu.backtesting.engine import BacktestEngine


class DummyNoSignalStrategy(Strategy):
    def __init__(self, name='no_signal', config=None):
        super().__init__(name, config or {})

    def on_bar(self, bar: pd.Series):
        return None


class DummySignalStrategy(Strategy):
    def __init__(self, name='sig', config=None):
        super().__init__(name, config or {})

    def on_bar(self, bar: pd.Series):
        # Emit a signal on the second bar only
        # Try to use bar.name as timestamp index
        if getattr(bar, 'name', None) is not None and bar.name == 1:
            return Signal(
                id=self.generate_signal_id(),
                timestamp=pd.Timestamp.now().to_pydatetime(),
                symbol='GOLDm#',
                timeframe='M15',
                side=SignalType.LONG,
                action='open',
                size_hint=0.01,
                confidence=0.8
            )
        return None


def test_selector_adapter_runs_in_backtest():
    strategies = [DummyNoSignalStrategy(), DummySignalStrategy('sig2')]
    selector = StrategySelector(strategies=strategies, config={})
    adapter = StrategySelectorAdapter(selector)

    # Build simple OHLCV DataFrame with two bars
    df = pd.DataFrame([
        {'open':1800.0,'high':1801.0,'low':1799.0,'close':1800.5,'volume':100},
        {'open':1800.5,'high':1802.0,'low':1800.0,'close':1801.0,'volume':120}
    ])
    df.index = [0,1]

    engine = BacktestEngine(strategies=[adapter])
    res = engine.run(df)
    # Engine should complete without exceptions and return a dict
    assert isinstance(res, dict)
