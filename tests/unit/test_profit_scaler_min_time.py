import pandas as pd
from position.profit_scaler import ProfitScaler, ScalingConfig


def test_min_time_in_trade_bars():
    from cthulu.backtesting import BACKTEST_CACHE_DIR
    df = pd.read_csv(BACKTEST_CACHE_DIR / 'GOLDm#_M15_20260105.csv', parse_dates=['time'], index_col='time')
    cfg = ScalingConfig()
    cfg.min_time_in_trade_bars = 2
    ps = ProfitScaler(connector=None, execution_engine=None, config=cfg, use_ml_optimizer=False)

    ticket = 42
    entry_price = float(df['open'].iloc[0])
    ps.register_position(ticket, 'GOLDm#', 0.1, entry_price, sl=entry_price-20.0, tp=entry_price+15.0)

    # Bars: idx 0,1,2
    actions0 = ps.evaluate_position(ticket, float(df.iloc[0]['close']), 'BUY', 1000.0, bars_elapsed=0)
    assert actions0 == []

    actions1 = ps.evaluate_position(ticket, float(df.iloc[1]['close']), 'BUY', 1000.0, bars_elapsed=1)
    assert actions1 == []

    # Use a micro-account balance to lower min_meaningful_profit and trigger actions
    actions2 = ps.evaluate_position(ticket, float(df.iloc[2]['close']), 'BUY', 50.0, bars_elapsed=2)
    assert isinstance(actions2, list) and len(actions2) > 0
