"""
Fetch GOLD M15 bars from local MT5 via HistoricalDataManager and save CSV for backtesting.

Usage:
    python scripts/fetch_gold_m15.py
"""
import logging
from datetime import datetime
from pathlib import Path

from backtesting.data_manager import HistoricalDataManager, DataSource

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("cthulu.fetch_gold_m15")

SYMBOL_CANDIDATES = ["GOLD#", "GOLDm#", "XAUUSD", "GOLD", "Gold#"]
TIMEFRAME = "M15"
START = datetime.fromisoformat("2026-01-05T15:45:00")
END = datetime.fromisoformat("2026-01-05T16:45:00")


def main():
    mgr = HistoricalDataManager()
    out_dir = Path(mgr.cache_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for s in SYMBOL_CANDIDATES:
        try:
            log.info(f"Attempting to fetch {s} {TIMEFRAME} from MT5: {START} -> {END}")
            df, meta = mgr.fetch_data(s, START, END, timeframe=TIMEFRAME, source=DataSource.MT5)
            csv_path = out_dir / f"{s}_M15_20260105.csv"
            df.to_csv(csv_path)
            log.info(f"SUCCESS: Fetched {len(df)} bars for {s}. Saved CSV: {csv_path}")
            print(f"SUCCESS: {s} -> {csv_path}")
            print(meta)
            return
        except Exception as e:
            log.warning(f"Failed to fetch for symbol {s}: {e}")

    from cthulu.backtesting import BACKTEST_CACHE_DIR
    print("ERROR: Unable to fetch GOLD M15 bars. Ensure the MetaTrader terminal is running and the 'MetaTrader5' Python package is installed in the active Python environment.")
    print(f"If MT5 is unavailable, please provide a CSV with columns: time,open,high,low,close,volume into {BACKTEST_CACHE_DIR}/")


if __name__ == '__main__':
    main()
