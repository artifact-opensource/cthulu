import json
from pathlib import Path
from unittest.mock import MagicMock
from datetime import datetime, timezone

import pytest
import pandas as pd

from cthulu.backtesting.scripts import auto_tune_runner as runner


def fake_run_grid_sweep_for_df(df, symbol, timeframe, cfg, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    # write a fake grid_sweep file
    (out_dir / 'grid_sweep_1.json').write_text(json.dumps([
        {
            'metrics': {'symbol': symbol, 'total_profit_estimate': 123.45},
            'min_time_in_trade_bars': 3,
            'trail_pct': 0.5,
            'concurrency': 1
        }
    ]))
    return [{
        'metrics': {'symbol': symbol, 'total_profit_estimate': 123.45},
        'min_time_in_trade_bars': 3,
        'trail_pct': 0.5,
        'concurrency': 1
    }]


def test_smoke_sweep_and_summarize(tmp_path, monkeypatch):
    # Patch grid sweep function
    monkeypatch.setattr(runner, 'run_grid_sweep_for_df', fake_run_grid_sweep_for_df)
    
    # Create a fake DataFrame to return from fetch_data
    fake_df = pd.DataFrame({
        'time': pd.date_range(start='2026-01-15', periods=100, freq='30min'),
        'open': [100.0] * 100,
        'high': [101.0] * 100,
        'low': [99.0] * 100,
        'close': [100.5] * 100,
        'volume': [1000] * 100
    })
    fake_meta = {'symbol': 'GOLDm#', 'timeframe': 'M15'}
    
    # Mock HistoricalDataManager.fetch_data to return fake data
    mock_dm = MagicMock()
    mock_dm.fetch_data.return_value = (fake_df, fake_meta)
    
    # Patch the HistoricalDataManager class
    monkeypatch.setattr(runner, 'HistoricalDataManager', lambda: mock_dm)

    out = runner.run_smoke_sweep(['GOLDm#'], timeframes=['M15'], days=1, out_root=tmp_path / 'reports')
    assert out.exists()

    summary = runner.summarize_reports([out], output_dir=tmp_path / 'summaries', call_ai_if_available=False)
    assert summary.exists()

    rec = runner.apply_recommendations_from_dirs([out], output_dir=tmp_path / 'recommend', auto_apply=False)
    assert rec.exists()

    # Read recommendations content
    data = json.loads(rec.read_text())
    assert 'recommended_min_time_in_trade_bars' in data
    assert 'recommended_trail_pct' in data
    assert data['source_count'] >= 1
