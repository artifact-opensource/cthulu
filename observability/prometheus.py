"""
Prometheus Metrics Exporter

Exports trading metrics in Prometheus format for monitoring and alerting.
Can be served via HTTP or written to a file for node_exporter textfile collector.
"""

import os
import logging
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class PrometheusMetric:
    """A single Prometheus metric"""
    name: str
    value: float
    metric_type: str  # gauge, counter, histogram
    help_text: str
    labels: Dict[str, str] = None
    
    def to_prometheus_format(self) -> str:
        """Format as Prometheus text format."""
        lines = []
        
        # HELP line
        lines.append(f"# HELP {self.name} {self.help_text}")
        # TYPE line
        lines.append(f"# TYPE {self.name} {self.metric_type}")
        
        # Value line with optional labels
        if self.labels:
            label_str = ",".join(f'{k}="{v}"' for k, v in self.labels.items())
            lines.append(f"{self.name}{{{label_str}}} {self.value}")
        else:
            lines.append(f"{self.name} {self.value}")
        
        return "\n".join(lines)


class PrometheusExporter:
    """
    Prometheus metrics exporter for Cthulu trading system.
    
    Exports metrics such as:
    - Trade count (total, wins, losses)
    - PnL (net profit, daily, per symbol)
    - Performance (win rate, profit factor, Sharpe)
    - System health (MT5 connected, uptime)
    """
    
    def __init__(self, prefix: str = "Cthulu"):
        """
        Initialize Prometheus exporter.
        
        Args:
            prefix: Metric name prefix
        """
        self.logger = logging.getLogger("cthulu.prometheus")
        self.prefix = prefix
        self._start_time = time.time()
        self._metrics_cache: Dict[str, PrometheusMetric] = {}
        
        # Initialize counters
        self._trade_count = 0
        self._win_count = 0
        self._loss_count = 0
        self._total_profit = 0.0
        self._total_loss = 0.0
        
    def record_trade(self, profit: float, symbol: str = "unknown"):
        """Record a trade result."""
        self._trade_count += 1
        if profit > 0:
            self._win_count += 1
            self._total_profit += profit
        elif profit < 0:
            self._loss_count += 1
            self._total_loss += abs(profit)
            
    def set_connection_status(self, connected: bool):
        """Set MT5 connection status."""
        self._update_metric(
            f"{self.prefix}_mt5_connected",
            1 if connected else 0,
            "gauge",
            "MT5 terminal connection status (1=connected, 0=disconnected)"
        )
        
    def set_account_balance(self, balance: float, equity: float):
        """Set account balance metrics."""
        self._update_metric(
            f"{self.prefix}_account_balance",
            balance,
            "gauge",
            "Current account balance"
        )
        self._update_metric(
            f"{self.prefix}_account_equity",
            equity,
            "gauge",
            "Current account equity"
        )
        
    def set_open_positions(self, count: int, total_volume: float = 0.0):
        """Set open positions metrics."""
        self._update_metric(
            f"{self.prefix}_open_positions",
            count,
            "gauge",
            "Number of open positions"
        )
        self._update_metric(
            f"{self.prefix}_open_volume",
            total_volume,
            "gauge",
            "Total volume of open positions"
        )

    def record_sl_tp_success(self, ticket: int, symbol: str = "unknown"):
        """Record a successful SL/TP application for observability."""
        self._update_metric(
            f"{self.prefix}_sl_tp_success_total",
            1.0,
            "counter",
            "Count of successful SL/TP modifications applied to broker",
            labels={"symbol": symbol, "ticket": str(ticket)}
        )

    def record_sl_tp_failure(self, ticket: int, symbol: str = "unknown"):
        """Record a failed SL/TP modification for observability."""
        self._update_metric(
            f"{self.prefix}_sl_tp_failure_total",
            1.0,
            "counter",
            "Count of failed SL/TP modifications applied to broker",
            labels={"symbol": symbol, "ticket": str(ticket)}
        )
        
    def set_drawdown(self, drawdown_pct: float):
        """Set current drawdown percentage."""
        self._update_metric(
            f"{self.prefix}_drawdown_percent",
            drawdown_pct * 100,
            "gauge",
            "Current drawdown percentage"
        )
        
    def _update_metric(self, name: str, value: float, metric_type: str, help_text: str, labels: Dict[str, str] = None):
        """Update or create a metric."""
        self._metrics_cache[name] = PrometheusMetric(
            name=name,
            value=value,
            metric_type=metric_type,
            help_text=help_text,
            labels=labels
        )
        
    def get_all_metrics(self) -> List[PrometheusMetric]:
        """Get all current metrics."""
        # Update computed metrics
        self._update_computed_metrics()
        return list(self._metrics_cache.values())
    
    def _update_computed_metrics(self):
        """Update computed/derived metrics."""
        # Uptime
        uptime = time.time() - self._start_time
        self._update_metric(
            f"{self.prefix}_uptime_seconds",
            uptime,
            "counter",
            "Cthulu uptime in seconds"
        )
        
        # Trade counters
        self._update_metric(
            f"{self.prefix}_trades_total",
            self._trade_count,
            "counter",
            "Total number of trades"
        )
        self._update_metric(
            f"{self.prefix}_trades_won",
            self._win_count,
            "counter",
            "Number of winning trades"
        )
        self._update_metric(
            f"{self.prefix}_trades_lost",
            self._loss_count,
            "counter",
            "Number of losing trades"
        )
        
        # PnL
        net_profit = self._total_profit - self._total_loss
        self._update_metric(
            f"{self.prefix}_pnl_total",
            net_profit,
            "gauge",
            "Total net profit/loss"
        )
        self._update_metric(
            f"{self.prefix}_profit_total",
            self._total_profit,
            "counter",
            "Total gross profit"
        )
        self._update_metric(
            f"{self.prefix}_loss_total",
            self._total_loss,
            "counter",
            "Total gross loss"
        )
        
        # Win rate
        win_rate = self._win_count / self._trade_count if self._trade_count > 0 else 0
        self._update_metric(
            f"{self.prefix}_win_rate",
            win_rate,
            "gauge",
            "Win rate (0-1)"
        )
        
        # Profit factor
        profit_factor = self._total_profit / self._total_loss if self._total_loss > 0 else 0
        self._update_metric(
            f"{self.prefix}_profit_factor",
            profit_factor,
            "gauge",
            "Profit factor (gross profit / gross loss)"
        )

    def update_from_metrics_dict(self, metrics: Dict[str, Any]):
        """Update exporter metrics from a PerformanceMetrics.to_dict() output.

        This method maps commonly used performance keys to Prometheus gauges/counters
        and labels per-symbol metrics where available.
        """
        try:
            # Basic counts and PnL
            self._update_metric(f"{self.prefix}_trades_total", metrics.get('total_trades', 0), 'counter', 'Total number of trades')
            self._update_metric(f"{self.prefix}_trades_won", metrics.get('winning_trades', 0), 'counter', 'Winning trades')
            self._update_metric(f"{self.prefix}_trades_lost", metrics.get('losing_trades', 0), 'counter', 'Losing trades')
            self._update_metric(f"{self.prefix}_pnl_total", metrics.get('net_profit', 0.0), 'gauge', 'Net profit/loss')
            self._update_metric(f"{self.prefix}_profit_total", metrics.get('gross_profit', 0.0), 'counter', 'Gross profit')
            self._update_metric(f"{self.prefix}_loss_total", metrics.get('gross_loss', 0.0), 'counter', 'Gross loss')
            self._update_metric(f"{self.prefix}_win_rate", metrics.get('win_rate', 0.0), 'gauge', 'Win rate (0-1)')
            self._update_metric(f"{self.prefix}_profit_factor", metrics.get('profit_factor', 0.0) or 0.0, 'gauge', 'Profit factor')

            # Drawdown magnitudes
            self._update_metric(f"{self.prefix}_drawdown_percent", metrics.get('max_drawdown_pct', 0.0) * 100.0, 'gauge', 'Max drawdown percent')
            self._update_metric(f"{self.prefix}_drawdown_abs", metrics.get('max_drawdown_abs', 0.0), 'gauge', 'Max drawdown absolute')

            # Drawdown durations
            self._update_metric(f"{self.prefix}_drawdown_duration_seconds", metrics.get('max_drawdown_duration_seconds', 0.0), 'gauge', 'Max drawdown duration in seconds')
            self._update_metric(f"{self.prefix}_current_drawdown_duration_seconds", metrics.get('current_drawdown_duration_seconds', 0.0), 'gauge', 'Current drawdown duration in seconds')

            # Risk/Reward and expectancy
            self._update_metric(f"{self.prefix}_avg_rr", metrics.get('avg_risk_reward', 0.0) or 0.0, 'gauge', 'Average risk:reward')
            self._update_metric(f"{self.prefix}_median_rr", metrics.get('median_risk_reward', 0.0) or 0.0, 'gauge', 'Median risk:reward')
            self._update_metric(f"{self.prefix}_rr_count", metrics.get('rr_count', 0), 'counter', 'Risk:Reward count')
            self._update_metric(f"{self.prefix}_expectancy", metrics.get('expectancy', 0.0) or 0.0, 'gauge', 'Expectancy per trade')

            # Sharpe metrics
            self._update_metric(f"{self.prefix}_sharpe", metrics.get('sharpe_ratio', 0.0) or 0.0, 'gauge', 'Sharpe ratio')
            self._update_metric(f"{self.prefix}_rolling_sharpe", metrics.get('rolling_sharpe', 0.0) or 0.0, 'gauge', 'Rolling Sharpe ratio')

            # Per-symbol metrics
            sym_map = metrics.get('symbol_aggregates', {}) or {}
            for s, v in sym_map.items():
                labels = {'symbol': s}
                self._update_metric(f"{self.prefix}_symbol_realized_pnl", v.get('realized_pnl', 0.0), 'gauge', 'Realized PnL per symbol', labels=labels)
                self._update_metric(f"{self.prefix}_symbol_unrealized_pnl", v.get('unrealized_pnl', 0.0), 'gauge', 'Unrealized PnL per symbol', labels=labels)
                self._update_metric(f"{self.prefix}_symbol_open_positions", v.get('open_positions', 0), 'gauge', 'Open positions per symbol', labels=labels)
                self._update_metric(f"{self.prefix}_symbol_exposure", v.get('exposure', 0.0), 'gauge', 'Exposure per symbol', labels=labels)

        except Exception as e:
            self.logger.exception(f"Failed to update metrics from performance snapshot: {e}")
    
    def export_text(self) -> str:
        """
        Export all metrics as Prometheus text format.
        
        Returns:
            String in Prometheus exposition format
        """
        metrics = self.get_all_metrics()
        lines = []
        
        for metric in metrics:
            lines.append(metric.to_prometheus_format())
            lines.append("")  # Empty line between metrics
        
        return "\n".join(lines)
    
    def write_to_file(self, path: Optional[str] = None):
        """
        Write metrics to a file for node_exporter textfile collector.
        If path is None, use the configured exporter._file_path if present, otherwise
        choose a sensible default (Windows-friendly path under the workspace or /tmp on Unix).
        Args:
            path: Output file path
        """
        try:
            if path is None:
                # prefer instance configured path
                path = getattr(self, '_file_path', None)
            if path is None:
                if os.name == 'nt':
                    path = r"C:\workspace\cthulu\metrics\Cthulu_metrics.prom"
                else:
                    path = "/tmp/Cthulu_metrics.prom"
            # Ensure parent dir exists
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            content = self.export_text()
            # Write atomically
            temp_path = Path(path).with_suffix(".tmp")
            temp_path.write_text(content)
            temp_path.replace(path)
            self.logger.debug(f"Metrics written to {path}")
        except Exception as e:
            self.logger.error(f"Failed to write metrics: {e}")
    
    def get_metrics_dict(self) -> Dict[str, Any]:
        """
        Get metrics as dictionary (for JSON export).
        
        Returns:
            Dict of metric names to values
        """
        metrics = self.get_all_metrics()
        return {m.name: m.value for m in metrics}
    
    def update_from_comprehensive_metrics(self, comprehensive_snapshot):
        """
        Update Prometheus metrics from ComprehensiveMetricsSnapshot.
        
        Exports all 173 comprehensive metrics to Prometheus format.
        
        Args:
            comprehensive_snapshot: Instance of ComprehensiveMetricsSnapshot
        """
        try:
            # Convert snapshot to dict
            if hasattr(comprehensive_snapshot, '__dict__'):
                data = vars(comprehensive_snapshot)
            else:
                data = comprehensive_snapshot
            
            # Core Account Metrics
            self._update_metric(f"{self.prefix}_account_balance", data.get('account_balance', 0.0), 'gauge', 'Account balance')
            self._update_metric(f"{self.prefix}_account_equity", data.get('account_equity', 0.0), 'gauge', 'Account equity')
            self._update_metric(f"{self.prefix}_account_margin", data.get('account_margin', 0.0), 'gauge', 'Used margin')
            self._update_metric(f"{self.prefix}_account_free_margin", data.get('account_free_margin', 0.0), 'gauge', 'Free margin')
            self._update_metric(f"{self.prefix}_account_margin_level", data.get('account_margin_level', 0.0), 'gauge', 'Margin level percent')
            self._update_metric(f"{self.prefix}_realized_pnl", data.get('realized_pnl', 0.0), 'gauge', 'Realized P&L')
            self._update_metric(f"{self.prefix}_unrealized_pnl", data.get('unrealized_pnl', 0.0), 'gauge', 'Unrealized P&L')
            self._update_metric(f"{self.prefix}_total_pnl", data.get('total_pnl', 0.0), 'gauge', 'Total P&L')
            
            # Trade Statistics
            self._update_metric(f"{self.prefix}_total_trades", data.get('total_trades', 0), 'counter', 'Total trades')
            self._update_metric(f"{self.prefix}_winning_trades", data.get('winning_trades', 0), 'counter', 'Winning trades')
            self._update_metric(f"{self.prefix}_losing_trades", data.get('losing_trades', 0), 'counter', 'Losing trades')
            self._update_metric(f"{self.prefix}_breakeven_trades", data.get('breakeven_trades', 0), 'counter', 'Breakeven trades')
            self._update_metric(f"{self.prefix}_active_positions", data.get('active_positions', 0), 'gauge', 'Active positions')
            self._update_metric(f"{self.prefix}_gross_profit", data.get('gross_profit', 0.0), 'counter', 'Gross profit')
            self._update_metric(f"{self.prefix}_gross_loss", data.get('gross_loss', 0.0), 'counter', 'Gross loss')
            self._update_metric(f"{self.prefix}_net_profit", data.get('net_profit', 0.0), 'gauge', 'Net profit')
            self._update_metric(f"{self.prefix}_avg_win", data.get('avg_win', 0.0), 'gauge', 'Average win')
            self._update_metric(f"{self.prefix}_avg_loss", data.get('avg_loss', 0.0), 'gauge', 'Average loss')
            self._update_metric(f"{self.prefix}_largest_win", data.get('largest_win', 0.0), 'gauge', 'Largest win')
            self._update_metric(f"{self.prefix}_largest_loss", data.get('largest_loss', 0.0), 'gauge', 'Largest loss')
            self._update_metric(f"{self.prefix}_win_rate_pct", data.get('win_rate', 0.0) * 100, 'gauge', 'Win rate percent')
            self._update_metric(f"{self.prefix}_profit_factor", data.get('profit_factor', 0.0), 'gauge', 'Profit factor')
            self._update_metric(f"{self.prefix}_expectancy", data.get('expectancy', 0.0), 'gauge', 'Expectancy')
            self._update_metric(f"{self.prefix}_avg_trade_duration_seconds", data.get('avg_trade_duration', 0.0), 'gauge', 'Average trade duration')
            self._update_metric(f"{self.prefix}_median_trade_duration_seconds", data.get('median_trade_duration', 0.0), 'gauge', 'Median trade duration')
            self._update_metric(f"{self.prefix}_trades_per_hour", data.get('trades_per_hour', 0.0), 'gauge', 'Trades per hour')
            self._update_metric(f"{self.prefix}_trades_today", data.get('trades_today', 0), 'counter', 'Trades today')
            self._update_metric(f"{self.prefix}_daily_pnl", data.get('daily_pnl', 0.0), 'gauge', 'Daily P&L')
            self._update_metric(f"{self.prefix}_weekly_pnl", data.get('weekly_pnl', 0.0), 'gauge', 'Weekly P&L')
            self._update_metric(f"{self.prefix}_monthly_pnl", data.get('monthly_pnl', 0.0), 'gauge', 'Monthly P&L')
            
            # Risk & Drawdown
            self._update_metric(f"{self.prefix}_max_drawdown_pct", data.get('max_drawdown_pct', 0.0) * 100, 'gauge', 'Max drawdown percent')
            self._update_metric(f"{self.prefix}_max_drawdown_abs", data.get('max_drawdown_abs', 0.0), 'gauge', 'Max drawdown absolute')
            self._update_metric(f"{self.prefix}_current_drawdown_pct", data.get('current_drawdown_pct', 0.0) * 100, 'gauge', 'Current drawdown percent')
            self._update_metric(f"{self.prefix}_current_drawdown_abs", data.get('current_drawdown_abs', 0.0), 'gauge', 'Current drawdown absolute')
            self._update_metric(f"{self.prefix}_drawdown_duration_seconds", data.get('max_drawdown_duration_seconds', 0.0), 'gauge', 'Max drawdown duration')
            self._update_metric(f"{self.prefix}_current_drawdown_duration_seconds", data.get('current_drawdown_duration_seconds', 0.0), 'gauge', 'Current drawdown duration')
            self._update_metric(f"{self.prefix}_peak_equity", data.get('peak_equity', 0.0), 'gauge', 'Peak equity')
            self._update_metric(f"{self.prefix}_trough_equity", data.get('trough_equity', 0.0), 'gauge', 'Trough equity')
            self._update_metric(f"{self.prefix}_risk_reward_ratio", data.get('risk_reward_ratio', 0.0), 'gauge', 'Average risk:reward ratio')
            
            # Advanced Statistics
            self._update_metric(f"{self.prefix}_sharpe_ratio", data.get('sharpe_ratio', 0.0), 'gauge', 'Sharpe ratio')
            self._update_metric(f"{self.prefix}_sortino_ratio", data.get('sortino_ratio', 0.0), 'gauge', 'Sortino ratio')
            self._update_metric(f"{self.prefix}_calmar_ratio", data.get('calmar_ratio', 0.0), 'gauge', 'Calmar ratio')
            self._update_metric(f"{self.prefix}_recovery_factor", data.get('recovery_factor', 0.0), 'gauge', 'Recovery factor')
            self._update_metric(f"{self.prefix}_rolling_sharpe_50", data.get('rolling_sharpe_50', 0.0), 'gauge', 'Rolling Sharpe 50')
            self._update_metric(f"{self.prefix}_rolling_sharpe_100", data.get('rolling_sharpe_100', 0.0), 'gauge', 'Rolling Sharpe 100')
            
            # Execution Quality
            self._update_metric(f"{self.prefix}_avg_slippage_pips", data.get('avg_slippage_pips', 0.0), 'gauge', 'Average slippage pips')
            self._update_metric(f"{self.prefix}_median_slippage_pips", data.get('median_slippage_pips', 0.0), 'gauge', 'Median slippage pips')
            self._update_metric(f"{self.prefix}_max_slippage_pips", data.get('max_slippage_pips', 0.0), 'gauge', 'Max slippage pips')
            self._update_metric(f"{self.prefix}_avg_execution_time_ms", data.get('avg_execution_time_ms', 0.0), 'gauge', 'Average execution time ms')
            self._update_metric(f"{self.prefix}_median_execution_time_ms", data.get('median_execution_time_ms', 0.0), 'gauge', 'Median execution time ms')
            self._update_metric(f"{self.prefix}_fill_rate_pct", data.get('fill_rate_pct', 0.0), 'gauge', 'Fill rate percent')
            self._update_metric(f"{self.prefix}_order_rejection_rate_pct", data.get('order_rejection_rate_pct', 0.0), 'gauge', 'Order rejection rate')
            self._update_metric(f"{self.prefix}_orders_total", data.get('orders_total', 0), 'counter', 'Total orders')
            self._update_metric(f"{self.prefix}_orders_filled", data.get('orders_filled', 0), 'counter', 'Orders filled')
            
            # Signals & Strategy
            self._update_metric(f"{self.prefix}_signals_generated", data.get('signals_generated_total', 0), 'counter', 'Signals generated')
            self._update_metric(f"{self.prefix}_signals_approved", data.get('signals_approved_total', 0), 'counter', 'Signals approved')
            self._update_metric(f"{self.prefix}_signals_rejected", data.get('signals_rejected_total', 0), 'counter', 'Signals rejected')
            self._update_metric(f"{self.prefix}_signal_approval_rate_pct", data.get('signal_approval_rate_pct', 0.0), 'gauge', 'Signal approval rate')
            self._update_metric(f"{self.prefix}_spread_rejections", data.get('spread_rejections', 0), 'counter', 'Spread rejections')
            self._update_metric(f"{self.prefix}_position_limit_rejections", data.get('position_limit_rejections', 0), 'counter', 'Position limit rejections')
            self._update_metric(f"{self.prefix}_drawdown_limit_rejections", data.get('drawdown_limit_rejections', 0), 'counter', 'Drawdown limit rejections')
            self._update_metric(f"{self.prefix}_exit_tp_count", data.get('exit_tp_count', 0), 'counter', 'Take profit exits')
            self._update_metric(f"{self.prefix}_exit_sl_count", data.get('exit_sl_count', 0), 'counter', 'Stop loss exits')
            
            # Position & Exposure
            self._update_metric(f"{self.prefix}_open_positions_volume", data.get('open_positions_volume', 0.0), 'gauge', 'Open positions volume')
            self._update_metric(f"{self.prefix}_long_positions", data.get('long_positions_count', 0), 'gauge', 'Long positions')
            self._update_metric(f"{self.prefix}_short_positions", data.get('short_positions_count', 0), 'gauge', 'Short positions')
            self._update_metric(f"{self.prefix}_long_exposure", data.get('long_exposure_usd', 0.0), 'gauge', 'Long exposure USD')
            self._update_metric(f"{self.prefix}_short_exposure", data.get('short_exposure_usd', 0.0), 'gauge', 'Short exposure USD')
            self._update_metric(f"{self.prefix}_net_exposure", data.get('net_exposure_usd', 0.0), 'gauge', 'Net exposure USD')
            
            # System Health
            self._update_metric(f"{self.prefix}_system_uptime_seconds", data.get('system_uptime_seconds', 0.0), 'counter', 'System uptime')
            self._update_metric(f"{self.prefix}_mt5_connected", data.get('mt5_connected', 0), 'gauge', 'MT5 connected')
            self._update_metric(f"{self.prefix}_cpu_usage_pct", data.get('cpu_usage_pct', 0.0), 'gauge', 'CPU usage percent')
            self._update_metric(f"{self.prefix}_memory_usage_mb", data.get('memory_usage_mb', 0.0), 'gauge', 'Memory usage MB')
            self._update_metric(f"{self.prefix}_memory_usage_pct", data.get('memory_usage_pct', 0.0), 'gauge', 'Memory usage percent')
            self._update_metric(f"{self.prefix}_errors_total", data.get('errors_total', 0), 'counter', 'Total errors')
            self._update_metric(f"{self.prefix}_warnings_total", data.get('warnings_total', 0), 'counter', 'Total warnings')
            
            # Session metrics
            self._update_metric(f"{self.prefix}_session_asian_trades", data.get('session_asian_trades', 0), 'counter', 'Asian session trades')
            self._update_metric(f"{self.prefix}_session_european_trades", data.get('session_european_trades', 0), 'counter', 'European session trades')
            self._update_metric(f"{self.prefix}_session_us_trades", data.get('session_us_trades', 0), 'counter', 'US session trades')
            
        except Exception as e:
            self.logger.exception(f"Failed to update from comprehensive metrics: {e}")




