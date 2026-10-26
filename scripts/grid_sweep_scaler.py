"""
Grid sweep over ProfitScaler parameters: min_time_in_trade_bars, trail_pct (applied to all tiers), and backtest concurrency (max_positions).
Produces ranked results and a JSON report.
"""
import json
from pathlib import Path
import itertools
import logging

import pandas as pd

from position.profit_scaler import ProfitScaler, ScalingConfig, ScalingTier
from backtesting.engine import BacktestEngine, BacktestConfig, SpeedMode
from core.strategy_factory import load_strategy
from cthulu.backtesting import BACKTEST_CACHE_DIR

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("cthulu.grid_sweep")

CSV_PATH = BACKTEST_CACHE_DIR / 'GOLDm#_M15_20260105.csv'
START_IDX = 0


def run_simulation(cfg: ScalingConfig, backtest_max_positions: int):
    # Load CSV window (full cached CSV is small for this sample)
    df = pd.read_csv(CSV_PATH, parse_dates=['time'], index_col='time')
    # Use the full file for sweep

    # Run backtest with dynamic strategy to simulate signal generation (we don't rely on trades)
    # Load dynamic mindset strategy config from the existing ultra_aggressive mindset
    from pathlib import Path
    MINDSET_PATH = Path('cthulu/configs/mindsets/ultra_aggressive/config_ultra_aggressive_m15.json')
    with open(MINDSET_PATH, 'r', encoding='utf-8') as f:
        mindset_cfg = json.load(f)
    strat_cfg = mindset_cfg.get('strategy', {})
    if 'params' not in strat_cfg:
        strat_cfg['params'] = {}
    strat_cfg['params']['symbol'] = 'GOLDm#'
    strat_cfg['params']['timeframe'] = 'M15'
    strat_cfg['timeframe'] = 'TIMEFRAME_M15'
    strat = load_strategy(strat_cfg)

    bt_cfg = BacktestConfig()
    bt_cfg.speed_mode = SpeedMode.NORMAL
    bt_cfg.max_positions = backtest_max_positions

    engine = BacktestEngine(strategies=[strat], config=bt_cfg)
    engine.run(df)

    # Now simulate profit scaler on synthetic seeded position
    ps = ProfitScaler(connector=None, execution_engine=None, config=cfg, use_ml_optimizer=False)
    ticket = 9001
    entry_price = float(df['open'].iloc[0])
    volume = 0.1
    sl = entry_price - 20.0
    tp = entry_price + 15.0
    ps.register_position(ticket, 'GOLDm#', volume, entry_price, sl=sl, tp=tp)

    balance = bt_cfg.initial_capital

    metrics = {
        'closed_volume_total': 0.0,
        'close_actions_count': 0,
        'trail_actions_count': 0,
        'modify_actions_count': 0,
        'final_remaining_volume': None,
        'first_close_bar': None,
        'total_profit_estimate': 0.0
    }

    for idx, (ts, row) in enumerate(df.iterrows()):
        price = float(row['close'])
        actions = ps.evaluate_position(ticket, price, 'BUY', balance, bars_elapsed=idx)
        if actions:
            # Apply actions locally (no MT5) similar to simulate_scaling_execution
            for a in actions:
                if a['type'] == 'close_partial':
                    vol = min(a['volume'], ps._position_states[ticket].current_volume)
                    profit_pips = price - entry_price
                    profit = vol * profit_pips * 100
                    metrics['closed_volume_total'] += vol
                    metrics['close_actions_count'] += 1
                    metrics['total_profit_estimate'] += profit
                    ps._position_states[ticket].current_volume = round(ps._position_states[ticket].current_volume - vol, 4)
                    if metrics['first_close_bar'] is None:
                        metrics['first_close_bar'] = idx
                elif a['type'] == 'trail_sl':
                    metrics['trail_actions_count'] += 1
                    ps._position_states[ticket].current_sl = a['new_sl']
                elif a['type'] == 'modify_sl':
                    metrics['modify_actions_count'] += 1
                    ps._position_states[ticket].current_sl = a['new_sl']

    metrics['final_remaining_volume'] = ps._position_states[ticket].current_volume
    return metrics


def run_grid_sweep_for_df(df, symbol: str, timeframe: str, mindset_cfg: dict, out_dir: Path, min_time_options=None, trail_options=None, concurrency_options=None):
    """Run grid sweep for a given DataFrame / symbol / timeframe and return ranked results."""
    min_time_options = min_time_options or [0, 1, 2, 4]
    trail_options = trail_options or [0.3, 0.5, 0.7]
    concurrency_options = concurrency_options or [1, 3, 5]

    combos = list(itertools.product(min_time_options, trail_options, concurrency_options))
    results = []

    for min_time, trail_pct, concurrency in combos:
        # Build ScalingConfig and override tiers to use trail_pct
        cfg = ScalingConfig()
        cfg.min_time_in_trade_bars = min_time
        # Apply same trail_pct to all tiers (and micro tiers)
        for t in cfg.tiers:
            t.trail_pct = trail_pct
        for t in cfg.micro_tiers:
            t.trail_pct = trail_pct

        # Run simulation on provided df
        metrics = run_simulation_on_df(cfg, df, symbol, timeframe, backtest_max_positions=concurrency, mindset_cfg=mindset_cfg)
        result = {
            'min_time_in_trade_bars': min_time,
            'trail_pct': trail_pct,
            'concurrency': concurrency,
            'metrics': metrics
        }
        results.append(result)
        log.info(f"Combo {symbol} {timeframe} min_time={min_time} trail={trail_pct} concurrency={concurrency} -> closed_vol={metrics['closed_volume_total']:.4f} profit_est={metrics['total_profit_estimate']:.2f} first_close={metrics['first_close_bar']}")

    # Rank by total_profit_estimate desc, penalize full early closure (final_remaining_volume small)
    def score(r):
        m = r['metrics']
        score = m['total_profit_estimate']
        # Penalize very small final remaining volume (prefers not fully closed early)
        score -= (0.1 - m['final_remaining_volume']) * 100 if m['final_remaining_volume'] < 0.1 else 0
        return score

    ranked = sorted(results, key=lambda r: score(r), reverse=True)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f'grid_sweep_{symbol}_{timeframe}.json').write_text(json.dumps(ranked, indent=2, default=str))

    return ranked


# Helper to run simulation on provided df (extracted from run_simulation)
def run_simulation_on_df(cfg: ScalingConfig, df, symbol: str, timeframe: str, backtest_max_positions: int = 1, mindset_cfg: dict = None):
    # Run backtest with dynamic strategy to simulate signal generation (we don't rely on trades)
    # If mindset_cfg provided, load strategy config from it
    if mindset_cfg:
        strat_cfg = mindset_cfg.get('strategy', {})
    else:
        strat_cfg = {
            'type': 'dynamic',
            'timeframe': f'TIMEFRAME_{timeframe}',
            'params': {'symbol': symbol}
        }

    # Ensure overrides
    if 'params' not in strat_cfg:
        strat_cfg['params'] = {}
    strat_cfg['params']['symbol'] = symbol
    strat_cfg['params']['timeframe'] = timeframe
    strat_cfg['timeframe'] = f'TIMEFRAME_{timeframe}'

    # Load strategy; if dynamic mindset config is invalid (e.g., no child strategies), fall back to default dynamic selector
    try:
        strat = load_strategy(strat_cfg)
    except ValueError as e:
        log.warning(f"Mindset strategy config invalid or incomplete ({e}), falling back to default dynamic selector")
        fallback_cfg = {
            'type': 'sma_crossover',
            'timeframe': f'TIMEFRAME_{timeframe}',
            'params': {'symbol': symbol, 'short': 5, 'long': 13}
        }
        strat = load_strategy(fallback_cfg)

    bt_cfg = BacktestConfig()
    bt_cfg.speed_mode = SpeedMode.NORMAL
    bt_cfg.max_positions = backtest_max_positions

    engine = BacktestEngine(strategies=[strat], config=bt_cfg)
    engine.run(df)

    # Now simulate profit scaler on synthetic seeded position
    ps = ProfitScaler(connector=None, execution_engine=None, config=cfg, use_ml_optimizer=False)
    ticket = 9001
    entry_price = float(df['open'].iloc[0])
    volume = 0.1
    sl = entry_price - 20.0
    tp = entry_price + 15.0
    ps.register_position(ticket, symbol, volume, entry_price, sl=sl, tp=tp)

    balance = bt_cfg.initial_capital

    metrics = {
        'closed_volume_total': 0.0,
        'close_actions_count': 0,
        'trail_actions_count': 0,
        'modify_actions_count': 0,
        'final_remaining_volume': None,
        'first_close_bar': None,
        'total_profit_estimate': 0.0
    }

    for idx, (ts, row) in enumerate(df.iterrows()):
        price = float(row['close'])
        actions = ps.evaluate_position(ticket, price, 'BUY', balance, bars_elapsed=idx)
        if actions:
            # Apply actions locally (no MT5) similar to simulate_scaling_execution
            for a in actions:
                if a['type'] == 'close_partial':
                    vol = min(a['volume'], ps._position_states[ticket].current_volume)
                    profit_pips = price - entry_price
                    profit = vol * profit_pips * 100
                    metrics['closed_volume_total'] += vol
                    metrics['close_actions_count'] += 1
                    metrics['total_profit_estimate'] += profit
                    ps._position_states[ticket].current_volume = round(ps._position_states[ticket].current_volume - vol, 4)
                    if metrics['first_close_bar'] is None:
                        metrics['first_close_bar'] = idx
                elif a['type'] == 'trail_sl':
                    metrics['trail_actions_count'] += 1
                    ps._position_states[ticket].current_sl = a['new_sl']
                elif a['type'] == 'modify_sl':
                    metrics['modify_actions_count'] += 1
                    ps._position_states[ticket].current_sl = a['new_sl']

    metrics['final_remaining_volume'] = ps._position_states[ticket].current_volume
    return metrics


if __name__ == '__main__':
    # Keep backwards compatibility for script execution
    main()
