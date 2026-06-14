import json
from pathlib import Path

from cthulu.backtesting.scripts.auto_tune_runner import apply_recommendations_from_dirs


def test_apply_recommendations_basic(tmp_path):
    report_dir = tmp_path / "sweep1"
    report_dir.mkdir()

    # Create grid_sweep file
    ranked = [
        {
            "min_time_in_trade_bars": 3,
            "trail_pct": 0.5,
            "concurrency": 2,
            "metrics": {"total_profit_estimate": 100.0},
        }
    ]

    (report_dir / "grid_sweep_GOLDm#_M15.json").write_text(json.dumps(ranked))

    res = apply_recommendations_from_dirs([report_dir], output_dir=tmp_path / "out", auto_apply=False)
    assert Path(res).exists()
    data = json.loads(Path(res).read_text())
    assert 'recommended_min_time_in_trade_bars' in data
    assert 'recommended_trail_pct' in data
    assert data['source_count'] >= 1
