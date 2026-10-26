"""
Run single bar-by-bar backtest for GOLD M15 (2026-01-05 11:00–11:30 UTC)
using the Ultra-Aggressive dynamic mindset (overridden to symbol GOLDm#).
Then simulate the ProfitScaler over the resulting open positions to observe scaling actions.
"""
import json
import logging
from pathlib import Path
from datetime import datetime

import pandas as pd

from backtesting.engine import BacktestEngine, BacktestConfig
from backtesting.data_manager import HistoricalDataManager, DataSource
from core.strategy_factory import load_strategy
from position.profit_scaler import ProfitScaler, ScalingConfig
from cthulu.backtesting import BACKTEST_CACHE_DIR, BACKTEST_REPORTS_DIR

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("cthulu.replay_incident")

MINDSET_PATH = Path('configs/mindsets/ultra_aggressive/config_ultra_aggressive_m15.json')
CSV_PATH = BACKTEST_CACHE_DIR / 'GOLDm#_M15_20260105.csv'

START = datetime.fromisoformat('2026-01-05T11:00:00')
END = datetime.fromisoformat('2026-01-05T11:30:00')


def load_mindset_strategy(symbol_override: str = 'GOLDm#'):
    with open(MINDSET_PATH, 'r', encoding='utf-8') as f:
        cfg = json.load(f)

    strat_cfg = cfg.get('strategy', {})
    # Ensure symbol/timeframe override
    if 'params' not in strat_cfg:
        strat_cfg['params'] = {}
    strat_cfg['params']['symbol'] = symbol_override
    strat_cfg['params']['timeframe'] = 'M15'
    # Also ensure top-level timeframe used by factory
    strat_cfg['timeframe'] = 'TIMEFRAME_M15'

    strategy = load_strategy(strat_cfg)
    return strategy


def run_backtest(strat, start: datetime, end: datetime, initial_capital: float = 1000.0):
    # Load CSV directly (we prefer the cached CSV fetched earlier)
    df = pd.read_csv(CSV_PATH, parse_dates=['time'], index_col='time')
    df = df[(df.index >= start) & (df.index <= end)]

    if df.empty:
        raise RuntimeError('No bars found in the requested window')

    bt_cfg = BacktestConfig()
    bt_cfg.initial_capital = initial_capital
    # Use NORMAL (bar-by-bar) execution
    from backtesting.engine import SpeedMode
    bt_cfg.speed_mode = SpeedMode.NORMAL

    engine = BacktestEngine(strategies=[strat], config=bt_cfg)

    results = engine.run(df)
    return engine, results


def simulate_profit_scaler_over_backtest(engine, results, min_time_in_trade_bars: int = 0):
    # Create a ProfitScaler with configured min_time
    cfg = ScalingConfig()
    cfg.min_time_in_trade_bars = min_time_in_trade_bars
    ps = ProfitScaler(connector=None, execution_engine=None, config=cfg, use_ml_optimizer=False)

    # Seed states from engine.positions initial opens (we'll inspect trades list for opens)
    # For simplicity, we will simulate for any trades that have entry_time in our window
    seed_positions = []
    for trade in results.get('trades', []):
        # If trade pnl exists, it's a completed trade; we want to simulate during the bar window
        pass

    # Instead, we look for engine.trades that opened; BacktestEngine stores trades only on close,
    # so we need to reconstruct opens from engine.equity_curve/positions snapshots. For our narrow window,
    # we'll just seed a synthetic position using first bar's open price and simulate across bars.

    df = engine.config  # not used

    # Take first open price from engine run data
    # The engine stored last processed data as engine, but we still have the original DataFrame in results via bars_processed
    # Re-read CSV window
    df = pd.read_csv(CSV_PATH, parse_dates=['time'], index_col='time')
    df = df[(df.index >= START) & (df.index <= END)]

    if df.empty:
        raise RuntimeError('No data for scaling simulation')

    # Seed one position that matches typical live behavior
    ticket = 9001
    entry_price = float(df['open'].iloc[0])
    volume = 0.1
    sl = entry_price - 20.0
    tp = entry_price + 15.0
    ps.register_position(ticket, 'GOLDm#', volume, entry_price, sl=sl, tp=tp)

    balance = engine.config.initial_capital

    timeline = []
    for idx, (ts, row) in enumerate(df.iterrows()):
        price = float(row['close'])
        actions = ps.evaluate_position(ticket, price, 'BUY', balance, bars_elapsed=idx)
        timeline.append({'ts': ts, 'price': price, 'actions': actions})

    return timeline


if __name__ == '__main__':
    strat = load_mindset_strategy(symbol_override='GOLDm#')
    print('Loaded strategy selector with class:', strat.__class__.__name__)

    engine, results = run_backtest(strat, START, END)
    print('Backtest completed. Trades:', len(results.get('trades', [])))

    timeline_default = simulate_profit_scaler_over_backtest(engine, results, min_time_in_trade_bars=0)
    print('\nProfit scaler timeline (min_time=0):')
    for t in timeline_default:
        print(f"{t['ts']} price={t['price']:.2f} actions={t['actions']}")

    timeline_guarded = simulate_profit_scaler_over_backtest(engine, results, min_time_in_trade_bars=2)
    print('\nProfit scaler timeline (min_time=2):')
    for t in timeline_guarded:
        print(f"{t['ts']} price={t['price']:.2f} actions={t['actions']}")

    # Save a short report
    report = {
        'start': START.isoformat(),
        'end': END.isoformat(),
        'trades_count': len(results.get('trades', [])),
        'timeline_default': timeline_default,
        'timeline_guarded': timeline_guarded
    }
    out = BACKTEST_REPORTS_DIR
    out.mkdir(parents=True, exist_ok=True)
    (out / 'gold_incident_replay.json').write_text(json.dumps(report, default=str, indent=2))
    print(f'\nReport written to {out / "gold_incident_replay.json"}')
