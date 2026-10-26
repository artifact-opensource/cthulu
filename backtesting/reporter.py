"""
Report Generator

Generates comprehensive HTML and text reports for backtest results.
"""

import pandas as pd
import logging
from typing import Dict, Any, List
from enum import Enum
from pathlib import Path
from datetime import datetime


class ReportFormat(Enum):
    """Report output formats"""
    HTML = "html"
    TEXT = "text"
    JSON = "json"
    CSV = "csv"


class ReportGenerator:
    """
    Generate backtest performance reports.
    
    Features:
    - HTML reports with tables and charts
    - Text reports for console output
    - JSON export for programmatic access
    - CSV export for spreadsheet analysis
    """
    
    def __init__(self):
        """Initialize report generator."""
        self.logger = logging.getLogger("cthulu.backtesting.reporter")
        
    def generate(
        self,
        results: Dict[str, Any],
        metrics: Any,
        output_path: str | None,
        format: ReportFormat = ReportFormat.HTML
    ) -> str:
        """
        Generate backtest report and ensure it's stored in the centralized reports directory.

        Args:
            results: Backtest results dictionary
            metrics: PerformanceMetrics object
            output_path: Desired output file name or path. If None or if the provided
                         name is not inside the reports directory, the report will be
                         created under `backtesting/reports/` with a timestamped filename.
            format: Report format

        Returns:
            The final path to the generated report (as a string).
        """
        # Central reports directory (package-local)
        from . import BACKTEST_REPORTS_DIR as reports_dir
        reports_dir.mkdir(parents=True, exist_ok=True)

        # Determine final output path: always place reports under reports_dir
        timestamp = datetime.now().strftime('%Y%m%dT%H%M%S')
        if output_path:
            # Use only the basename to avoid scattering files across the repo
            base_name = Path(output_path).name
        else:
            base_name = f'backtest_{timestamp}.{format.value}'

        final_path = reports_dir / f"{Path(base_name).stem}_{timestamp}{Path(base_name).suffix or '.' + format.value}"
        final_path_str = str(final_path)

        # Generate the report file
        if format == ReportFormat.HTML:
            self._generate_html(results, metrics, final_path_str)
        elif format == ReportFormat.TEXT:
            self._generate_text(results, metrics, final_path_str)
        elif format == ReportFormat.JSON:
            self._generate_json(results, metrics, final_path_str)
        elif format == ReportFormat.CSV:
            self._generate_csv(results, metrics, final_path_str)
        else:
            raise ValueError(f"Unsupported format: {format}")

        # Update manifest (index.json) with a brief summary for the UI
        manifest_path = reports_dir / 'index.json'
        try:
            from json import loads, dumps
            entry = {
                'file': final_path.name,
                'format': format.value,
                'generated': datetime.now().isoformat(),
                'summary': {
                    'total_return': float(getattr(metrics, 'total_return', 0.0)),
                    'sharpe_ratio': float(getattr(metrics, 'sharpe_ratio', 0.0)),
                    'win_rate': float(getattr(metrics, 'win_rate', 0.0)),
                    'total_trades': int(getattr(metrics, 'total_trades', 0)),
                }
            }

            if manifest_path.exists():
                with open(manifest_path, 'r') as f:
                    manifest = loads(f.read())
            else:
                manifest = []

            # Prepend new entry
            manifest.insert(0, entry)

            with open(manifest_path, 'w') as f:
                f.write(dumps(manifest, indent=2))
        except Exception as e:
            self.logger.warning(f"Failed to update manifest: {e}")

        self.logger.info(f"Report generated: {final_path_str}")
        return final_path_str
        
    def _generate_html(self, results: Dict[str, Any], metrics: Any, output_path: str) -> None:
        """Generate HTML report."""
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Cthulu Backtest Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; }}
        h1 {{ color: #2c3e50; }}
        h2 {{ color: #34495e; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
        .metric-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin: 20px 0; }}
        .metric-card {{ background: #ecf0f1; padding: 15px; border-radius: 5px; }}
        .metric-label {{ font-size: 12px; color: #7f8c8d; text-transform: uppercase; }}
        .metric-value {{ font-size: 24px; font-weight: bold; color: #2c3e50; }}
        .positive {{ color: #27ae60; }}
        .negative {{ color: #e74c3c; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #3498db; color: white; }}
        tr:hover {{ background: #f5f5f5; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Cthulu Backtest Report</h1>
        <p><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        
        <h2>Summary</h2>
        <div class="metric-grid">
            <div class="metric-card">
                <div class="metric-label">Total Return</div>
                <div class="metric-value {'positive' if metrics.total_return > 0 else 'negative'}">
                    {metrics.total_return:.2f}%
                </div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Sharpe Ratio</div>
                <div class="metric-value">{metrics.sharpe_ratio:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Max Drawdown</div>
                <div class="metric-value negative">{metrics.max_drawdown_pct:.2f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Win Rate</div>
                <div class="metric-value">{metrics.win_rate*100:.1f}%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Profit Factor</div>
                <div class="metric-value">{metrics.profit_factor:.2f}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Total Trades</div>
                <div class="metric-value">{metrics.total_trades}</div>
            </div>
        </div>
        
        <h2>Risk-Adjusted Returns</h2>
        <table>
            <tr>
                <th>Metric</th>
                <th>Value</th>
                <th>Description</th>
            </tr>
            <tr>
                <td>Sharpe Ratio</td>
                <td>{metrics.sharpe_ratio:.2f}</td>
                <td>Risk-adjusted return</td>
            </tr>
            <tr>
                <td>Sortino Ratio</td>
                <td>{metrics.sortino_ratio:.2f}</td>
                <td>Downside risk-adjusted return</td>
            </tr>
            <tr>
                <td>Calmar Ratio</td>
                <td>{metrics.calmar_ratio:.2f}</td>
                <td>Return / Max Drawdown</td>
            </tr>
            <tr>
                <td>Omega Ratio</td>
                <td>{metrics.omega_ratio:.2f}</td>
                <td>Probability weighted ratio</td>
            </tr>
        </table>
        
        <h2>Trade Statistics</h2>
        <table>
            <tr>
                <th>Metric</th>
                <th>Value</th>
            </tr>
            <tr>
                <td>Total Trades</td>
                <td>{metrics.total_trades}</td>
            </tr>
            <tr>
                <td>Winning Trades</td>
                <td>{metrics.winning_trades}</td>
            </tr>
            <tr>
                <td>Losing Trades</td>
                <td>{metrics.losing_trades}</td>
            </tr>
            <tr>
                <td>Win Rate</td>
                <td>{metrics.win_rate*100:.1f}%</td>
            </tr>
            <tr>
                <td>Average Win</td>
                <td>${metrics.avg_win:.2f}</td>
            </tr>
            <tr>
                <td>Average Loss</td>
                <td>${metrics.avg_loss:.2f}</td>
            </tr>
            <tr>
                <td>Largest Win</td>
                <td>${metrics.largest_win:.2f}</td>
            </tr>
            <tr>
                <td>Largest Loss</td>
                <td>${metrics.largest_loss:.2f}</td>
            </tr>
            <tr>
                <td>Expectancy</td>
                <td>${metrics.expectancy:.2f}</td>
            </tr>
        </table>
        
        <h2>Configuration</h2>
        <table>
            <tr>
                <th>Parameter</th>
                <th>Value</th>
            </tr>
            <tr>
                <td>Initial Capital</td>
                <td>${results['config']['initial_capital']:,.2f}</td>
            </tr>
            <tr>
                <td>Commission</td>
                <td>{results['config']['commission']*100:.2f}%</td>
            </tr>
            <tr>
                <td>Slippage</td>
                <td>{results['config']['slippage_pct']*100:.2f}%</td>
            </tr>
            <tr>
                <td>Speed Mode</td>
                <td>{results['config']['speed_mode']}</td>
            </tr>
            <tr>
                <td>Bars Processed</td>
                <td>{results['bars_processed']:,}</td>
            </tr>
            <tr>
                <td>Duration</td>
                <td>{results['duration_seconds']:.2f} seconds</td>
            </tr>
            <tr>
                <td>Bars/Second</td>
                <td>{results['bars_per_second']:,.0f}</td>
            </tr>
        </table>
    </div>
</body>
</html>
"""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
            
    def _generate_text(self, results: Dict[str, Any], metrics: Any, output_path: str) -> None:
        """Generate text report."""
        text = f"""
CTHULU BACKTEST REPORT
{'=' * 80}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

SUMMARY
{'-' * 80}
Total Return:         {metrics.total_return:>10.2f}%
Annualized Return:    {metrics.annualized_return:>10.2f}%
Sharpe Ratio:         {metrics.sharpe_ratio:>10.2f}
Sortino Ratio:        {metrics.sortino_ratio:>10.2f}
Max Drawdown:         {metrics.max_drawdown_pct:>10.2f}%
Win Rate:             {metrics.win_rate*100:>10.1f}%
Profit Factor:        {metrics.profit_factor:>10.2f}
Total Trades:         {metrics.total_trades:>10}

TRADE STATISTICS
{'-' * 80}
Winning Trades:       {metrics.winning_trades:>10}
Losing Trades:        {metrics.losing_trades:>10}
Average Win:          ${metrics.avg_win:>10.2f}
Average Loss:         ${metrics.avg_loss:>10.2f}
Largest Win:          ${metrics.largest_win:>10.2f}
Largest Loss:         ${metrics.largest_loss:>10.2f}
Expectancy:           ${metrics.expectancy:>10.2f}

CONFIGURATION
{'-' * 80}
Initial Capital:      ${results['config']['initial_capital']:>10,.2f}
Commission:           {results['config']['commission']*100:>10.2f}%
Slippage:             {results['config']['slippage_pct']*100:>10.2f}%
Speed Mode:           {results['config']['speed_mode']:>10}
Bars Processed:       {results['bars_processed']:>10,}
Duration:             {results['duration_seconds']:>10.2f} seconds
Bars/Second:          {results['bars_per_second']:>10,.0f}
"""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(text)
            
    def _generate_json(self, results: Dict[str, Any], metrics: Any, output_path: str) -> None:
        """Generate JSON report."""
        import json
        # Be flexible about metrics representation (dataclass-like with to_dict, or simple namespace)
        if hasattr(metrics, 'to_dict'):
            metrics_data = metrics.to_dict()
        elif hasattr(metrics, '__dict__'):
            metrics_data = metrics.__dict__
        else:
            metrics_data = metrics

        report = {
            'timestamp': datetime.now().isoformat(),
            'results': results,
            'metrics': metrics_data
        }
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, default=str)
            
    def _generate_csv(self, results: Dict[str, Any], metrics: Any, output_path: str) -> None:
        """Generate CSV report with trades."""
        trades = results.get('trades', [])
        if not trades:
            self.logger.warning("No trades to export to CSV")
            return
            
        # Convert trades to DataFrame
        trade_data = []
        for t in trades:
            trade_data.append({
                'ticket': t.ticket,
                'symbol': t.symbol,
                'side': t.side.value,
                'entry_time': t.entry_time,
                'exit_time': t.exit_time,
                'entry_price': t.entry_price,
                'exit_price': t.exit_price,
                'size': t.size,
                'pnl': t.pnl,
                'commission': t.commission,
                'exit_reason': t.exit_reason,
            })
            
        df = pd.DataFrame(trade_data)
        df.to_csv(output_path, index=False, encoding='utf-8')

class BacktestReporter:
    """
    Compatibility wrapper for the backtesting UI.
    """
    
    def __init__(self):
        self.generator = ReportGenerator()
        
    def generate_report(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a report dictionary for the UI.
        
        Args:
            results: Backtest results from engine.run()
            
        Returns:
            Dictionary containing metrics and report data
        """
        metrics = results.get('metrics')
        
        # If metrics is an object, convert to dict
        if hasattr(metrics, 'to_dict'):
            metrics_data = metrics.to_dict()
        elif hasattr(metrics, '__dict__'):
            metrics_data = metrics.__dict__
        else:
            metrics_data = metrics or {}
            
        return {
            'summary': metrics_data,
            'equity_curve': [
                {'time': t.isoformat() if hasattr(t, 'isoformat') else str(t), 'equity': e}
                for t, e in results.get('equity_curve', [])
            ],
            'trades': [
                {
                    'ticket': t.ticket,
                    'symbol': t.symbol,
                    'side': t.side.value if hasattr(t.side, 'value') else str(t.side),
                    'entry_time': t.entry_time.isoformat() if hasattr(t.entry_time, 'isoformat') else str(t.entry_time),
                    'exit_time': t.exit_time.isoformat() if hasattr(t.exit_time, 'isoformat') else str(t.exit_time),
                    'entry_price': t.entry_price,
                    'exit_price': t.exit_price,
                    'pnl': t.pnl,
                    'reason': t.exit_reason
                }
                for t in results.get('trades', [])
            ],
            'config': results.get('config', {})
        }
