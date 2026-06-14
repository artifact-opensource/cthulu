"""
Consolidated Auto-Tune Runner

This script unifies the smoke/full sweep, summarization, and safe apply workflow.
Writes all outputs under BACKTEST_REPORTS_DIR and avoids writing outside that tree unless --apply is used (and then it will write recommended files under configs/recommendations).
"""
from __future__ import annotations
import argparse
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any

from cthulu.backtesting import BACKTEST_REPORTS_DIR
from scripts.grid_sweep_scaler import run_grid_sweep_for_df
from backtesting.data_manager import HistoricalDataManager, DataSource
from cthulu.ops.guardrails import allow_auto_apply

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("cthulu.auto_tune.runner")

DEFAULT_TIMEFRAMES = ['M1', 'M5', 'M15', 'H1', 'H4', 'D1']
SYMBOLS_CFG = Path('config/symbols.json')

# Single root for all auto-tune artifacts to keep repo tidy
AUTOTUNE_ROOT = BACKTEST_REPORTS_DIR / 'auto_tune'
AUTOTUNE_ROOT.mkdir(parents=True, exist_ok=True)


def load_symbols():
    if SYMBOLS_CFG.exists():
        try:
            return json.loads(SYMBOLS_CFG.read_text())
        except Exception:
            log.warning("Failed to read symbols config; defaulting to provided symbols")
    return {}


def rolling_windows(end_date: datetime, days: int = 30):
    end = end_date
    start = end - timedelta(days=days)
    return [(start, end)]


def _is_weekend_only_range(start: datetime, end: datetime) -> bool:
    cur = start.date()
    while cur <= end.date():
        if cur.weekday() < 5:
            return False
        cur = cur + timedelta(days=1)
    return True


def run_smoke_sweep(symbols: List[str], timeframes: List[str] | None = None, days: int = 30, out_root: Path | None = None) -> Path:
    dm = HistoricalDataManager()
    sym_cfgs = load_symbols()
    timeframes = timeframes or DEFAULT_TIMEFRAMES

    now = datetime.now().astimezone()
    base_out_root = out_root or (AUTOTUNE_ROOT / 'runs')
    out_root = base_out_root / now.strftime('%Y%m%d_%H%M%S')
    out_root.mkdir(parents=True, exist_ok=True)

    for symbol in symbols:
        cfg = sym_cfgs.get(symbol, {})
        for timeframe in timeframes:
            windows = rolling_windows(now, days=days)
            for (start, end) in windows:
                # Skip weekends for non-weekend trading symbols
                if not cfg.get('weekend_trading', False) and _is_weekend_only_range(start, end):
                    log.info(f"Skipping weekend-only window for {symbol} {timeframe} {start} -> {end}")
                    continue

                try:
                    df, meta = dm.fetch_data(symbol, start, end, timeframe=timeframe, source=DataSource.MT5, use_cache=True)
                except Exception as e:
                    log.warning(f"Failed to fetch {symbol} {timeframe} {start}->{end}: {e}")
                    continue

                # Discover mindsets
                mindsets_dir = Path('configs/mindsets')
                mindset_cfgs = []
                if mindsets_dir.exists():
                    for ms_dir in mindsets_dir.iterdir():
                        if ms_dir.is_dir():
                            candidate = ms_dir / f'config_{ms_dir.name}_{timeframe.lower()}.json'
                            if candidate.exists():
                                try:
                                    cfg_parsed = json.loads(candidate.read_text())
                                    mindset_cfgs.append({'name': ms_dir.name, 'cfg': cfg_parsed})
                                except Exception:
                                    log.warning(f"Failed to parse mindset config {candidate}")

                if not mindset_cfgs:
                    mindset_cfgs = [{'name': 'default_dynamic', 'cfg': None}]

                for m in mindset_cfgs:
                    out_dir = out_root / f"{symbol}_{timeframe}_{m['name']}_{start.date()}_{end.date()}"
                    ranked = run_grid_sweep_for_df(df, symbol, timeframe, m['cfg'], out_dir)
                    summary = {
                        'symbol': symbol,
                        'timeframe': timeframe,
                        'mindset': m['name'],
                        'window_start': start.isoformat(),
                        'window_end': end.isoformat(),
                        'top_config': ranked[0] if ranked else None
                    }
                    (out_dir / 'summary.json').write_text(json.dumps(summary, indent=2, default=str))
                    log.info(f"Completed sweep for {symbol} {timeframe} mindset={m['name']} ({start.date()} -> {end.date()}); results at {out_dir}")

    return out_root


def run_full_sweep(symbols: list, timeframes: list = None, days_list: list | None = None, mindsets: list = None):
    """Run expanded sweep across multiple rolling windows (days_list)."""
    days_list = days_list or [30]
    results_root = AUTOTUNE_ROOT / 'full' / datetime.now().astimezone().strftime('%Y%m%d_%H%M%S')
    results_root.mkdir(parents=True, exist_ok=True)

    for days in days_list:
        log.info(f"Starting sweeps for window={days} days")
        out_root = results_root / f"window_{days}d"
        out_root.mkdir(parents=True, exist_ok=True)

        dm = HistoricalDataManager()
        sym_cfgs = load_symbols()
        timeframes = timeframes or DEFAULT_TIMEFRAMES

        now = datetime.now().astimezone()
        windows = rolling_windows(now, days=days)

        for symbol in symbols:
            cfg = sym_cfgs.get(symbol, {})
            for timeframe in timeframes:
                for (start, end) in windows:
                    if not cfg.get('weekend_trading', False) and _is_weekend_only_range(start, end):
                        log.info(f"Skipping weekend-only window for {symbol} {timeframe} {start} -> {end}")
                        continue

                    try:
                        df, meta = dm.fetch_data(symbol, start, end, timeframe=timeframe, source=DataSource.MT5, use_cache=True)
                    except Exception as e:
                        log.warning(f"Failed to fetch {symbol} {timeframe} {start}->{end}: {e}")
                        continue

                    mindset_cfgs = []
                    mindsets_dir = Path('configs/mindsets')
                    if mindsets_dir.exists():
                        for ms_dir in mindsets_dir.iterdir():
                            if ms_dir.is_dir():
                                candidate = ms_dir / f'config_{ms_dir.name}_{timeframe.lower()}.json'
                                if candidate.exists():
                                    try:
                                        cfg_parsed = json.loads(candidate.read_text())
                                        mindset_cfgs.append({'name': ms_dir.name, 'cfg': cfg_parsed})
                                    except Exception:
                                        log.warning(f"Failed to parse mindset config {candidate}")

                    if not mindset_cfgs:
                        mindset_cfgs = [{'name': 'default_dynamic', 'cfg': None}]

                    for m in mindset_cfgs:
                        out_dir = out_root / f"{symbol}_{timeframe}_{m['name']}_{start.date()}_{end.date()}"
                        ranked = run_grid_sweep_for_df(df, symbol, timeframe, m['cfg'], out_dir)
                        summary = {
                            'symbol': symbol,
                            'timeframe': timeframe,
                            'mindset': m['name'],
                            'window_start': start.isoformat(),
                            'window_end': end.isoformat(),
                            'top_config': ranked[0] if ranked else None
                        }
                        (out_dir / 'summary.json').write_text(json.dumps(summary, indent=2, default=str))
                        log.info(f"Completed sweep for {symbol} {timeframe} mindset={m['name']} ({start.date()} -> {end.date()}); results at {out_dir}")

    return results_root

# Summarizer utilities (self-contained; writes into BACKTEST_REPORTS_DIR/auto_tune_summaries by default)
import statistics
import requests
import os


def _collect_grid_files(root: Path) -> List[Path]:
    return list(root.rglob('grid_sweep_*.json'))


def _load_ranked(path: Path) -> List[Dict[str, Any]]:
    try:
        return json.loads(path.read_text())
    except Exception as e:
        log.warning(f"Failed to load {path}: {e}")
        return []


def aggregate_rankings(dirs: List[Path]) -> Dict[str, Any]:
    entries = []
    for d in dirs:
        for p in _collect_grid_files(d):
            ranked = _load_ranked(p)
            if not ranked:
                continue
            top = ranked[0]
            entries.append({
                'file': str(p),
                'symbol': top.get('metrics', {}).get('symbol') if isinstance(top.get('metrics', {}), dict) else None,
                'min_time_in_trade_bars': top.get('min_time_in_trade_bars'),
                'trail_pct': top.get('trail_pct'),
                'concurrency': top.get('concurrency'),
                'total_profit_estimate': top.get('metrics', {}).get('total_profit_estimate', 0.0) if isinstance(top.get('metrics', {}), dict) else 0.0,
            })

    out = {'count': len(entries), 'entries': entries}
    if entries:
        out['stats'] = {
            'avg_profit_est': statistics.mean([e['total_profit_estimate'] for e in entries]),
            'median_profit_est': statistics.median([e['total_profit_estimate'] for e in entries]),
            'min_time_mode': statistics.mode([e['min_time_in_trade_bars'] for e in entries]) if len(entries) > 0 else None,
        }
    else:
        out['stats'] = {}

    return out


def compose_human_summary(agg: Dict[str, Any]) -> str:
    lines = []
    lines.append("Auto-Tune Aggregate Summary")
    lines.append("--------------------------")
    lines.append(f"Windows processed: {agg.get('count', 0)}")

    stats = agg.get('stats', {})
    if stats:
        lines.append(f"Average profit estimate: {stats.get('avg_profit_est', 0):.2f}")
        lines.append(f"Median profit estimate: {stats.get('median_profit_est', 0):.2f}")
        lines.append(f"Mode min_time_in_trade_bars: {stats.get('min_time_mode')}")

    lines.append("\nTop entries (top 5):")
    for e in sorted(agg.get('entries', []), key=lambda x: x['total_profit_estimate'], reverse=True)[:5]:
        lines.append(f"- file={Path(e['file']).name} profit_est={e['total_profit_estimate']:.2f} min_time={e['min_time_in_trade_bars']} trail={e['trail_pct']} concurrency={e['concurrency']}")

    return "\n".join(lines)


# Prefer local LLM via llama-cpp when available, else deterministic fallback
def call_llm_for_enhanced_summary(prompt: str) -> str:
    """Return an enhanced summary using configured LLM backend.

    Priority:
    1. Local LLM (llama-cpp via cthulu.llm.local_llm)
    2. Remote LLM endpoint if LLM_ENDPOINT set
    3. Deterministic local fallback (tests/CI)
    """
    try:
        from cthulu.llm.local_llm import available as llm_available, summarize as llm_summarize
        if llm_available():
            try:
                return llm_summarize(prompt)
            except Exception as e:
                log.warning(f"Local LLM generation failed: {e}")
    except Exception as e:
        # local LLM not present or failed to import - try adding project root to sys.path as a fallback
        log.debug("Initial import of local LLM failed: %s", e)
        try:
            import sys
            from pathlib import Path
            project_root = Path(__file__).resolve().parents[2]
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            from cthulu.llm.local_llm import available as llm_available, summarize as llm_summarize
            if llm_available():
                try:
                    return llm_summarize(prompt)
                except Exception as e2:
                    log.warning(f"Local LLM generation failed after sys.path fix: {e2}")
        except Exception as e2:
            log.debug("Failed to import local LLM after sys.path adjustment: %s", e2)


    # Remote LLM endpoint support (legacy)
    endpoint = os.environ.get('LLM_ENDPOINT')
    api_key = os.environ.get('LLM_API_KEY')
    if endpoint:
        try:
            payload = {"prompt": prompt}
            headers = {'Content-Type': 'application/json'}
            if api_key:
                headers['Authorization'] = f"Bearer {api_key}"
            resp = requests.post(endpoint, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data.get('text') or data.get('response') or json.dumps(data)
        except Exception as e:
            log.warning(f"Remote LLM call failed: {e}")

    # Deterministic fallback
    from cthulu.llm.local_llm import deterministic_fallback
    return deterministic_fallback(prompt)


def summarize_reports(report_dirs: List[Path], output_dir: Path | None = None, call_ai_if_available: bool = True) -> Path:
    output_dir = Path(output_dir or (AUTOTUNE_ROOT / 'summaries'))
    output_dir.mkdir(parents=True, exist_ok=True)

    agg = aggregate_rankings(report_dirs)
    human = compose_human_summary(agg)

    ai_text = None
    if call_ai_if_available:
        try:
            ai_text = call_llm_for_enhanced_summary(human)
        except Exception as e:
            log.warning(f"LLM call failed: {e}")

    ts = datetime.now().astimezone().strftime('%Y%m%d_%H%M%S')
    out_json = output_dir / f'auto_tune_summary_{ts}.json'
    out_txt = output_dir / f'auto_tune_summary_{ts}.txt'

    out_json.write_text(json.dumps({'aggregated': agg, 'ai_summary': ai_text}, indent=2, default=str))
    out_txt.write_text(human + ("\n\nAI_SUMMARY:\n" + ai_text if ai_text else ""))

    log.info(f"Wrote summaries to {out_json} and {out_txt}")
    return out_json


def apply_recommendations_from_dirs(report_dirs: List[Path], output_dir: Path | None = None, auto_apply: bool = False) -> Path:
    # Aggregate top configs and write a recommendations file. If auto_apply True, a recommended config file will be written into configs/recommendations.
    output_dir = Path(output_dir or (AUTOTUNE_ROOT / 'recommendations'))
    output_dir.mkdir(parents=True, exist_ok=True)

    agg = aggregate_rankings(report_dirs)
    # Heuristic: take mode of min_time and top average trail_pct from top N
    if not agg.get('entries'):
        raise RuntimeError('No entries to recommend from')

    top_entries = sorted(agg['entries'], key=lambda x: x['total_profit_estimate'], reverse=True)[:10]
    rec = {
        'recommended_min_time_in_trade_bars': int(statistics.mode([e['min_time_in_trade_bars'] for e in top_entries if e['min_time_in_trade_bars'] is not None])),
        'recommended_trail_pct': float(statistics.mean([e['trail_pct'] for e in top_entries if e['trail_pct'] is not None or e['trail_pct'] == 0.0])),
        'recommended_concurrency': int(statistics.median([e['concurrency'] for e in top_entries if e['concurrency'] is not None])),
        'source_count': agg.get('count', 0)
    }

    ts = datetime.now().astimezone().strftime('%Y%m%d_%H%M%S')
    out = output_dir / f'recommendations_{ts}.json'
    out.write_text(json.dumps(rec, indent=2))

    if auto_apply:
        # Require explicit opt-in to auto-apply recommendations for safety
        if not allow_auto_apply():
            log.warning("Auto-apply requested but guardrails prevent auto application. Set AUTO_APPLY_RECOMMENDATIONS=true and LIVE_RUN_CONFIRM=1 to enable.")
        else:
            # Write recommended file into configs/recommendations for review/application
            rec_cfg_dir = Path('configs/recommendations')
            rec_cfg_dir.mkdir(parents=True, exist_ok=True)
            rec_cfg_file = rec_cfg_dir / f'recommended_{ts}.json'
            rec_cfg_file.write_text(json.dumps(rec, indent=2))
            log.info(f"Auto-applied recommendations to {rec_cfg_file}")

    log.info(f"Wrote recommendations to {out}")
    return out


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--mode', choices=['smoke', 'full'], default='smoke')
    p.add_argument('--symbols', nargs='+', required=True)
    p.add_argument('--timeframes', nargs='*')
    p.add_argument('--days', type=int, default=30)
    p.add_argument('--days-list', nargs='*', type=int)
    p.add_argument('--no-ai', action='store_true')
    p.add_argument('--auto-apply', action='store_true')
    p.add_argument('--output-dir', type=str, default=None)
    args = p.parse_args(argv)

    if args.mode == 'smoke':
        out = run_smoke_sweep(args.symbols, timeframes=args.timeframes, days=args.days, out_root=Path(args.output_dir) if args.output_dir else None)
    else:
        out = run_full_sweep(args.symbols, timeframes=args.timeframes, days_list=args.days_list or [args.days])

    # Summarize
    summary_path = summarize_reports([out], call_ai_if_available=(not args.no_ai))

    # Optionally apply recommendations
    rec_path = None
    if args.auto_apply:
        rec_path = apply_recommendations_from_dirs([out], auto_apply=True)

    # Emit a small JSON summary for the PS entrypoint to parse
    final = {'smoke_out_dir': str(out), 'summary_json': str(summary_path), 'recommendations_json': str(rec_path) if rec_path else None}
    print(json.dumps(final))


if __name__ == '__main__':
    main()
