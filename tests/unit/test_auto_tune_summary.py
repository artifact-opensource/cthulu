import json
from pathlib import Path

from cthulu.backtesting.scripts.auto_tune_runner import summarize_reports


def test_summarize_reports_creates_output(tmp_path):
    # Create a fake sweep report dir with a grid_sweep JSON
    report_dir = tmp_path / "sweep1"
    report_dir.mkdir()

    grid = [
        {
            "metrics": {"symbol": "GOLD#", "total_profit_estimate": 123.45},
            "min_time_in_trade_bars": 3,
            "trail_pct": 0.5,
            "concurrency": 1,
        }
    ]

    (report_dir / "grid_sweep_1.json").write_text(json.dumps(grid))

    out = summarize_reports([report_dir], output_dir=tmp_path / "out", call_ai_if_available=False)
    assert out.exists()

    data = json.loads(out.read_text())
    assert "aggregated" in data
    assert data["aggregated"]["count"] == 1
    assert data["aggregated"]["entries"][0]["symbol"] == "GOLD#"
