Report Interface (Prototype)

- Static UI located at: `backtesting/report_ui/static/index.html`
- Simple server: `python backtesting/report_ui/serve.py` (serves the repo on port 8000 and opens the UI)
- Reports are centralized in `backtesting/reports/`. The `ReportGenerator` writes reports there and updates `backtesting/reports/index.json` manifest.

Usage
1. Generate a report using `backtesting.ReportGenerator.generate(...)` or any scripts that create reports.
2. Run: `python backtesting/report_ui/serve.py`
3. The UI will open: `http://localhost:8000/backtesting/report_ui/static/index.html`

Notes
- HTML reports will open inline in an iframe.
- JSON reports will be visualized using Chart.js (basic summary visualization).
- This is intentionally small and dependency-free (no Flask) for easy local prototyping.
