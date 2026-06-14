import pandas as pd
import numpy as np
from cthulu.core.trading_loop import ensure_runtime_indicators
from cthulu.strategy.scalping import ScalpingStrategy
import logging

idx = pd.date_range(end=pd.Timestamp.now(), periods=100, freq='T')
df = pd.DataFrame({'open':100+np.random.randn(100).cumsum(), 'high':100+np.random.randn(100).cumsum()+1, 'low':100+np.random.randn(100).cumsum()-1, 'close':100+np.random.randn(100).cumsum()}, index=idx)
strat = ScalpingStrategy({'params': {}})
config = {'strategy': {'type': 'scalping', 'params': {}}}
extra = ensure_runtime_indicators(df, [], strat, config, logging.getLogger())
print('extra types:', [e.__class__.__name__ for e in extra])
print('df cols:', list(df.columns))




