"""
Simulate execution of ProfitScaler actions locally (no MT5) over CSV bars.
This will show how quickly partial closes would reduce position volume and whether early-exit is likely.
"""
import logging
import pandas as pd

from position.profit_scaler import ProfitScaler, ScalingConfig

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("cthulu.simulate_scaling")

from cthulu.backtesting import BACKTEST_CACHE_DIR
CSV_PATH = BACKTEST_CACHE_DIR / "GOLDm#_M15_20260105.csv"
MIN_LOT = 0.01


def apply_actions(ps, ticket, actions):
    state = ps._position_states.get(ticket)
    executed = []
    for a in actions:
        if a['type'] == 'close_partial':
            vol = a['volume']
            # clamp to current
            vol = min(vol, state.current_volume)
            state.current_volume = round(state.current_volume - vol, 4)
            executed.append({'type': 'close_partial', 'volume': vol, 'reason': a.get('reason')})
        elif a['type'] in ('modify_sl', 'trail_sl'):
            state.current_sl = a['new_sl']
            executed.append({'type': a['type'], 'new_sl': a['new_sl'], 'reason': a.get('reason')})
    return executed


def main():
    df = pd.read_csv(CSV_PATH, parse_dates=["time"], index_col="time")
    cfg = ScalingConfig()
    cfg.min_time_in_trade_bars = 2
    ps = ProfitScaler(connector=None, execution_engine=None, config=cfg)

    ticket = 2002
    symbol = "GOLDm#"
    entry_price = float(df['open'].iloc[0])
    volume = 0.1
    sl = entry_price - 20.0
    tp = entry_price + 15.0

    ps.register_position(ticket, symbol, volume, entry_price, sl=sl, tp=tp)

    balance = 1000.0

    timeline = []

    for idx, (ts, row) in enumerate(df.iterrows()):
        price = float(row['close'])
        # pass bars_elapsed so min_time_in_trade_bars can be enforced
        actions = ps.evaluate_position(ticket, price, 'BUY', balance, bars_elapsed=idx)
        executed = []
        if actions:
            executed = apply_actions(ps, ticket, actions)
        timeline.append({'ts': ts, 'price': price, 'actions': actions, 'executed': executed, 'remaining_vol': ps._position_states[ticket].current_volume})

    # Print timeline
    print('Simulation timeline:')
    for t in timeline:
        print(f"{t['ts']} price={t['price']:.2f} remaining_vol={t['remaining_vol']:.4f} executed={t['executed']}")

    final_vol = ps._position_states[ticket].current_volume
    print(f"Final remaining volume: {final_vol:.4f}")


if __name__ == '__main__':
    main()
