"""
Quick script to seed a position and run ProfitScaler.evaluate_position across bars
from CSV to see what actions would be proposed (no execution).
"""
import logging
import pandas as pd

from position.profit_scaler import ProfitScaler, ScalingConfig

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("cthulu.eval_profit_scaler")

from cthulu.backtesting import BACKTEST_CACHE_DIR
CSV_PATH = BACKTEST_CACHE_DIR / "GOLDm#_M15_20260105.csv"


def main():
    df = pd.read_csv(CSV_PATH, parse_dates=["time"], index_col="time")
    ps = ProfitScaler(connector=None, execution_engine=None, config=ScalingConfig())

    # Seed a sample position resembling the live event
    ticket = 1001
    symbol = "GOLDm#"
    entry_price = float(df['open'].iloc[0])  # use first bar open as entry
    volume = 0.1  # lots
    sl = entry_price - 20.0
    tp = entry_price + 15.0

    ps.register_position(ticket, symbol, volume, entry_price, sl=sl, tp=tp)

    balance = 1000.0

    print(f"Seeded position #{ticket}: {symbol} @ {entry_price} (SL={sl}, TP={tp}), balance={balance}")

    for ts, row in df.iterrows():
        price = float(row['close'])
        actions = ps.evaluate_position(ticket, price, 'BUY', balance)
        if actions:
            print(f"{ts} price={price:.2f} -> actions={actions}")
        else:
            print(f"{ts} price={price:.2f} -> no action")


if __name__ == '__main__':
    main()
