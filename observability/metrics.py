"""
Metrics Module

Performance metrics collection and reporting.
Tracks PnL, trades, win rate, Sharpe ratio, max drawdown.
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import statistics


@dataclass
class PerformanceMetrics:
    """Performance metrics snapshot"""
    timestamp: datetime
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_profit: float = 0.0            # Sum of positive P&L
    total_loss: float = 0.0              # Sum of absolute negative P&L
    net_profit: float = 0.0              # total_profit - total_loss
    gross_profit: float = 0.0            # Alias for total_profit
    gross_loss: float = 0.0              # Alias for total_loss
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: Optional[float] = None
    max_drawdown_pct: float = 0.0        # Fraction (0.05 == 5%)
    max_drawdown_abs: float = 0.0        # Absolute amount
    max_drawdown_duration_seconds: float = 0.0
    current_drawdown_duration_seconds: float = 0.0
    sharpe_ratio: float = 0.0
    rolling_sharpe: Optional[float] = None
    positions_opened_total: int = 0      # cumulative ever opened
    active_positions: int = 0            # currently open
    avg_risk_reward: Optional[float] = None
    rr_count: int = 0
    median_risk_reward: Optional[float] = None
    expectancy: Optional[float] = None
    symbol_aggregates: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    returns: List[float] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp.isoformat(),
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'total_profit': self.total_profit,
            'total_loss': self.total_loss,
            'net_profit': self.net_profit,
            'gross_profit': self.gross_profit,
            'gross_loss': self.gross_loss,
            'win_rate': self.win_rate,
            'avg_win': self.avg_win,
            'avg_loss': self.avg_loss,
            'profit_factor': self.profit_factor,
            'avg_risk_reward': self.avg_risk_reward,
            'rr_count': self.rr_count,
            'median_risk_reward': self.median_risk_reward,
            'max_drawdown_pct': self.max_drawdown_pct,
            'max_drawdown_abs': self.max_drawdown_abs,
            'max_drawdown_duration_seconds': self.max_drawdown_duration_seconds,
            'current_drawdown_duration_seconds': self.current_drawdown_duration_seconds,
            'sharpe_ratio': self.sharpe_ratio,
            'rolling_sharpe': self.rolling_sharpe,
            'positions_opened_total': self.positions_opened_total,
            'active_positions': self.active_positions,
            'symbol_aggregates': self.symbol_aggregates,
            'returns': self.returns,
            'expectancy': self.expectancy,
        }


class MetricsCollector:
    """
    Metrics collection and calculation engine.
    
    Tracks trading performance metrics:
    - PnL tracking (total, daily, per-symbol)
    - Win rate and profit factor
    - Sharpe ratio
    - Maximum drawdown
    - Trade statistics
    """
    
    def __init__(self, database=None):
        """Initialize metrics collector."""
        self.logger = logging.getLogger("cthulu.metrics")
        self.database = database
        self.trade_results: List[float] = []
        self.equity_curve: List[float] = [0.0]
        # Ensure base attributes exist even if reset fails
        self.symbol_aggregates = {}
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_profit = 0.0
        self.total_loss = 0.0
        self.positions_opened = 0
        self.unrealized_by_symbol = {}
        # Initialize full state
        self.reset()

    def reset(self):
        """Reset internal metrics state (useful for unit tests)."""
        self.trade_results = []
        self.equity_curve = [0.0]
        self.peak_equity = 0.0
        self.peak_time = None
        self.drawdown_start_time = None
        self.max_drawdown_duration_seconds = 0.0
        self.current_drawdown_duration_seconds = 0.0
        self.max_drawdown = 0.0
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_profit = 0.0
        self.total_loss = 0.0
        self.positions_opened = 0
        self.symbol_aggregates = {}
        self.unrealized_by_symbol = {}
        self.rr_list = []
        self.abs_max_drawdown_amount = 0.0
        self.rolling_sharpe = None
        self.rolling_window_size = 50
        self.rolling_sharpe = None
        self.peak_equity: float = 0.0
        self.peak_time: Optional[datetime] = None
        self.drawdown_start_time: Optional[datetime] = None
        self.max_drawdown_duration_seconds: float = 0.0
        self.current_drawdown_duration_seconds: float = 0.0
        self.max_drawdown: float = 0.0
        
        # Counters
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_profit = 0.0
        self.total_loss = 0.0
        # Open positions counter
        self.positions_opened = 0
        # per-symbol aggregates
        self.symbol_aggregates: Dict[str, Dict[str, Any]] = {}
        # current unrealized exposures per symbol
        self.unrealized_by_symbol: Dict[str, float] = {}
        # list of risk:reward ratios recorded for realized trades
        self.rr_list: List[float] = []
        # store absolute max drawdown amount for reporting
        self.abs_max_drawdown_amount: float = 0.0
        # rolling sharpe window
        self.rolling_window_size: int = 50
        self.rolling_sharpe: Optional[float] = None

        # Load historical trades if database is available
        if self.database:
            self._load_historical_trades()
            self._load_open_positions()
        
    def _load_historical_trades(self):
        """Load historical closed trades from database and replay them."""
        try:
            # Get all closed trades with profit
            cursor = self.database.conn.cursor()
            cursor.execute("""
                SELECT profit, symbol FROM trades
                WHERE status = 'CLOSED' AND profit IS NOT NULL
                ORDER BY exit_time ASC
            """)
            
            for row in cursor.fetchall():
                profit = row['profit']
                symbol = row['symbol']
                # Replay the trade without incrementing positions_opened
                self._record_trade_internal(profit, symbol, update_positions=False)
                
            self.logger.info(f"Loaded {self.total_trades} historical trades from database")
            
        except Exception as e:
            self.logger.warning(f"Failed to load historical trades: {e}")

    def _load_open_positions(self):
        """Load currently open trades to seed active positions counts and unrealized P&L."""
        try:
            cursor = self.database.conn.cursor()
            cursor.execute("""
                SELECT symbol, COUNT(*) as open_count, COALESCE(SUM(COALESCE(profit,0)),0) as unrealized
                FROM trades
                WHERE status = 'OPEN'
                GROUP BY symbol
            """)
            rows = cursor.fetchall()
            for row in rows:
                symbol = row['symbol']
                open_count = row['open_count']
                unrealized = row['unrealized']
                self.unrealized_by_symbol[symbol] = unrealized
                entry = self.symbol_aggregates.setdefault(symbol, {
                    'realized_pnl': 0.0,
                    'realized_wins': 0,
                    'realized_losses': 0,
                    'unrealized_pnl': 0.0,
                    'open_positions': 0,
                    'exposure': 0.0,
                })
                entry['open_positions'] = open_count
                entry['unrealized_pnl'] = unrealized
                self.positions_opened += open_count
        except Exception as e:
            self.logger.warning(f"Failed to load open positions: {e}")

    def record_trade(self, profit: float, symbol: str = 'UNKNOWN', risk: Optional[float] = None, reward: Optional[float] = None):
        """
        Record trade result.
        
        Args:
            profit: Trade profit/loss
            symbol: Trading symbol
            risk: Amount risked (currency) for this trade (optional)
            reward: Amount rewarded (currency) for this trade (optional)
        """
        self._record_trade_internal(profit, symbol, update_positions=True, risk=risk, reward=reward)
        
    def _record_trade_internal(self, profit: float, symbol: str, update_positions: bool = True, risk: Optional[float] = None, reward: Optional[float] = None):
        self.total_trades += 1
        self.trade_results.append(profit)
        
        # Update symbol aggregates for realized trades
        entry = self.symbol_aggregates.setdefault(symbol, {
            'realized_pnl': 0.0,
            'realized_wins': 0,
            'realized_losses': 0,
            'unrealized_pnl': 0.0,
            'open_positions': 0,
            'exposure': 0.0,
            'rr_values': []
        })

        if profit > 0:
            self.winning_trades += 1
            self.total_profit += profit
            entry['realized_wins'] += 1
            entry['realized_pnl'] += profit
        elif profit < 0:
            self.losing_trades += 1
            self.total_loss += abs(profit)
            entry['realized_losses'] += 1
            entry['realized_pnl'] += profit
        else:
            # zero profit trade still counts
            entry['realized_pnl'] += profit

        # record R:R if both risk and reward provided
        rr_val = None
        try:
            if risk is not None and reward is not None:
                if risk == 0 and reward > 0:
                    rr_val = float('inf')
                elif risk == 0 and reward == 0:
                    rr_val = None
                else:
                    rr_val = float(reward) / float(risk) if risk != 0 else None
            if rr_val is not None:
                self.rr_list.append(rr_val)
                entry['rr_values'].append(rr_val)
        except Exception:
            rr_val = None

        # Update gross aliases
        self.gross_profit = self.total_profit
        self.gross_loss = self.total_loss

        # Update equity curve
        current_time = datetime.now()
        current_equity = self.equity_curve[-1] + profit
        self.equity_curve.append(current_equity)

        # Update peak equity and times
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity
            self.peak_time = current_time
            # if a drawdown was active, close it and record duration
            if self.drawdown_start_time is not None:
                duration = (current_time - self.drawdown_start_time).total_seconds()
                if duration > self.max_drawdown_duration_seconds:
                    self.max_drawdown_duration_seconds = duration
                self.drawdown_start_time = None

        # Update drawdown magnitude and durations
        if self.peak_equity > 0:
            drawdown = (self.peak_equity - current_equity) / self.peak_equity
            if drawdown > self.max_drawdown:
                self.max_drawdown = drawdown
                # store absolute drawdown amount
                self.abs_max_drawdown_amount = self.peak_equity * self.max_drawdown
            # if drawdown > 0 and not already tracking, start drawdown at peak time
            if drawdown > 0 and self.drawdown_start_time is None:
                self.drawdown_start_time = self.peak_time or current_time
            # set current drawdown duration
            if self.drawdown_start_time is not None:
                self.current_drawdown_duration_seconds = (current_time - self.drawdown_start_time).total_seconds()
            else:
                self.current_drawdown_duration_seconds = 0.0

        # Update rolling sharpe
        try:
            self.rolling_sharpe = self.get_rolling_sharpe()
        except Exception:
            self.rolling_sharpe = None

        self.logger.debug(
            f"Trade recorded: {profit:+.2f} on {symbol} | "
            f"Total trades: {self.total_trades} | "
            f"Net P&L: {current_equity:+.2f}"
        )

    def record_position_opened(self):
        """
        Record that a new position was opened/tracked by the system.
        This does not imply a closed trade; it is useful for observability.
        """
        try:
            self.positions_opened += 1
            self.logger.debug(f"Position opened recorded: total_opened={self.positions_opened}")
        except Exception:
            pass
        
    def get_metrics(self) -> PerformanceMetrics:
        """
        Calculate current performance metrics.
        
        Returns:
            PerformanceMetrics snapshot
        """
        metrics = PerformanceMetrics(timestamp=datetime.now())
        
        metrics.total_trades = self.total_trades
        metrics.winning_trades = self.winning_trades
        metrics.losing_trades = self.losing_trades
        metrics.total_profit = self.total_profit
        metrics.total_loss = self.total_loss
        
        # Net profit and aliases
        metrics.net_profit = self.total_profit - self.total_loss
        metrics.gross_profit = self.total_profit
        metrics.gross_loss = self.total_loss
        
        # Win rate
        if self.total_trades > 0:
            metrics.win_rate = self.winning_trades / self.total_trades
            
        # Average win/loss
        if self.winning_trades > 0:
            metrics.avg_win = self.total_profit / self.winning_trades
        if self.losing_trades > 0:
            metrics.avg_loss = self.total_loss / self.losing_trades
        else:
            metrics.avg_loss = 0.0
            
        # Profit factor: gross_profit / gross_loss
        if self.total_loss > 0:
            metrics.profit_factor = self.total_profit / self.total_loss
        elif self.total_profit > 0 and self.total_loss == 0:
            metrics.profit_factor = float('inf')
        else:
            metrics.profit_factor = None
            
        # Max drawdown (fraction and absolute)
        metrics.max_drawdown_pct = getattr(self, 'max_drawdown', 0.0)
        metrics.max_drawdown_abs = getattr(self, 'peak_equity', 0.0) * metrics.max_drawdown_pct
        metrics.max_drawdown_duration_seconds = getattr(self, 'max_drawdown_duration_seconds', 0.0)
        metrics.current_drawdown_duration_seconds = getattr(self, 'current_drawdown_duration_seconds', 0.0)

        # Open positions and totals
        try:
            metrics.positions_opened_total = self.positions_opened
        except Exception:
            metrics.positions_opened_total = 0
        # active positions will be synced from position manager when available
        metrics.active_positions = getattr(self, 'active_positions', 0)

        # Rolling Sharpe
        metrics.rolling_sharpe = getattr(self, 'rolling_sharpe', None)
        
        # Sharpe ratio (simplified)
        if len(self.trade_results) > 1:
            avg_return = statistics.mean(self.trade_results)
            std_return = statistics.stdev(self.trade_results)
            if std_return > 0:
                metrics.sharpe_ratio = (avg_return / std_return) * (252 ** 0.5)  # Annualized
                
        metrics.returns = self.trade_results.copy()

        # Fill symbol aggregates snapshot
        metrics.symbol_aggregates = {}
        for s, v in self.symbol_aggregates.items():
            metrics.symbol_aggregates[s] = v.copy()
            metrics.symbol_aggregates[s]['unrealized_pnl'] = self.unrealized_by_symbol.get(s, 0.0)
            # include rr summary for symbol if available
            rr_vals = v.get('rr_values', [])
            metrics.symbol_aggregates[s]['avg_rr'] = statistics.mean(rr_vals) if rr_vals else None
            metrics.symbol_aggregates[s]['rr_count'] = len(rr_vals)

        # Active positions snapshot if set
        metrics.active_positions = getattr(self, 'active_positions', 0)

        # Avg & median risk:reward summary
        if len(self.rr_list) > 0:
            metrics.avg_risk_reward = statistics.mean(self.rr_list)
            metrics.median_risk_reward = statistics.median(self.rr_list)
            metrics.rr_count = len(self.rr_list)
        else:
            metrics.avg_risk_reward = None
            metrics.median_risk_reward = None
            metrics.rr_count = 0

        # Expectancy: E = (win_rate * avg_win) - ((1-win_rate) * avg_loss)
        if metrics.total_trades > 0:
            try:
                prob_win = metrics.win_rate
                avg_win = metrics.avg_win
                avg_loss = metrics.avg_loss
                metrics.expectancy = (prob_win * avg_win) - ((1 - prob_win) * avg_loss)
            except Exception:
                metrics.expectancy = None
        else:
            metrics.expectancy = None

        return metrics

    def sync_with_positions_summary(self, stats: Dict[str, Any], pos_summary: Dict[str, Dict[str, Any]]):
        """Update metrics with live position manager summary.

        Args:
            stats: Global stats dict from PositionManager.get_statistics()
            pos_summary: Per-symbol summary from PositionManager.get_position_summary_by_symbol()
        """
        try:
            self.active_positions = int(stats.get('active_positions', 0))
            self.positions_opened = int(stats.get('total_opened', getattr(self, 'positions_opened', 0)))

            # Sync per-symbol
            for s, v in pos_summary.items():
                entry = self.symbol_aggregates.setdefault(s, {
                    'realized_pnl': 0.0,
                    'realized_wins': 0,
                    'realized_losses': 0,
                    'unrealized_pnl': 0.0,
                    'open_positions': 0,
                    'exposure': 0.0,
                })
                entry['open_positions'] = int(v.get('open_positions', 0))
                entry['unrealized_pnl'] = float(v.get('unrealized_pnl', 0.0))
                entry['exposure'] = float(v.get('exposure', 0.0))
                self.unrealized_by_symbol[s] = float(v.get('unrealized_pnl', 0.0))

        except Exception as e:
            self.logger.exception(f"Failed to sync positions summary: {e}")

    def record_position_opened(self, symbol: str):
        """Record an open position event for live tracking."""
        try:
            entry = self.symbol_aggregates.setdefault(symbol, {
                'realized_pnl': 0.0,
                'realized_wins': 0,
                'realized_losses': 0,
                'unrealized_pnl': 0.0,
                'open_positions': 0,
                'exposure': 0.0,
            })
            entry['open_positions'] = entry.get('open_positions', 0) + 1
            self.positions_opened = getattr(self, 'positions_opened', 0) + 1
            self.logger.debug(f"Recorded position opened for {symbol}; total_opened={self.positions_opened}")
        except Exception:
            self.logger.exception('Failed to record position opened')

    def get_rolling_sharpe(self, window: Optional[int] = None) -> Optional[float]:
        """Compute a rolling Sharpe ratio over the last `window` trades.

        Returns annualized Sharpe (uses sqrt(252) multiplier) or None if not computable.
        """
        try:
            w = window or self.rolling_window_size
            if len(self.trade_results) < 2:
                return None
            last = self.trade_results[-w:] if len(self.trade_results) >= w else self.trade_results
            if len(last) < 2:
                return None
            avg = statistics.mean(last)
            std = statistics.stdev(last)
            if std > 0:
                return (avg / std) * (252 ** 0.5)
            return None
        except Exception:
            return None

    def publish_to_prometheus(self, exporter: Any):
        """Publish current metrics to a Prometheus exporter instance.

        The exporter should implement `update_from_metrics_dict(dict)` which accepts
        the output of `PerformanceMetrics.to_dict()`.
        """
        try:
            metrics = self.get_metrics()
            d = metrics.to_dict()
            # add extra computed fields
            d['max_drawdown_duration_seconds'] = getattr(self, 'max_drawdown_duration_seconds', 0.0)
            d['current_drawdown_duration_seconds'] = getattr(self, 'current_drawdown_duration_seconds', 0.0)
            d['rolling_sharpe'] = getattr(self, 'rolling_sharpe', None)
            # export
            if hasattr(exporter, 'update_from_metrics_dict'):
                exporter.update_from_metrics_dict(d)
            elif hasattr(exporter, 'get_metrics_dict'):
                # fallback: set some basic metrics via exporter interface
                exporter.set_account_balance(d.get('net_profit', 0.0), d.get('net_profit', 0.0))
        except Exception as e:
            self.logger.exception(f"Failed to publish metrics to Prometheus exporter: {e}")

    def record_position_closed(self, symbol: str):
        """Record that a position was closed; update open count."""
        try:
            entry = self.symbol_aggregates.setdefault(symbol, {
                'realized_pnl': 0.0,
                'realized_wins': 0,
                'realized_losses': 0,
                'unrealized_pnl': 0.0,
                'open_positions': 0,
                'exposure': 0.0,
            })
            if entry.get('open_positions', 0) > 0:
                entry['open_positions'] -= 1
            self.logger.debug(f"Recorded position closed for {symbol}; remaining_open={entry.get('open_positions',0)}")
        except Exception:
            self.logger.exception('Failed to record position closed')
        
    def print_summary(self):
        """Print metrics summary to log in a structured, human-readable format."""
        metrics = self.get_metrics()

        # Header
        self.logger.info("""
============================================================
                 PERFORMANCE SUMMARY
============================================================
""")

        # High-level numbers
        # Use ASCII-friendly representation to avoid console encoding errors on Windows
        pf = None
        if metrics.profit_factor is None:
            pf = "N/A"
        elif metrics.profit_factor == float('inf'):
            pf = "INF"
        else:
            try:
                pf = f"{metrics.profit_factor:.2f}"
            except Exception:
                pf = str(metrics.profit_factor)
        rr_display = f"{metrics.avg_risk_reward:.2f} (n={metrics.rr_count})" if metrics.avg_risk_reward is not None else "N/A"
        median_rr_display = f"{metrics.median_risk_reward:.2f}" if metrics.median_risk_reward is not None else "N/A"
        expectancy_display = f"{metrics.expectancy:+.2f}" if metrics.expectancy is not None else "N/A"
        self.logger.info(f"Total Trades       : {metrics.total_trades}")
        self.logger.info(f"Winning Trades     : {metrics.winning_trades}")
        self.logger.info(f"Losing Trades      : {metrics.losing_trades}")
        self.logger.info(f"Win Rate           : {metrics.win_rate:.1%}")
        self.logger.info(f"Gross Profit       : {metrics.gross_profit:+.2f}")
        self.logger.info(f"Gross Loss         : {metrics.gross_loss:+.2f}")
        self.logger.info(f"Net P&L            : {metrics.net_profit:+.2f}")
        self.logger.info(f"Avg Win            : {metrics.avg_win:.2f}")
        self.logger.info(f"Avg Loss           : {metrics.avg_loss:.2f}")
        self.logger.info(f"Profit Factor      : {pf}")
        self.logger.info(f"Avg R:R            : {rr_display}")
        self.logger.info(f"Median R:R         : {median_rr_display}")
        self.logger.info(f"Expectancy         : {expectancy_display}")
        self.logger.info(f"Max Drawdown       : {metrics.max_drawdown_pct:.1%} ({metrics.max_drawdown_abs:+.2f})")
        self.logger.info(f"Max Drawdown Dur.  : {metrics.max_drawdown_duration_seconds:.1f}s")
        self.logger.info(f"Current Drawdown   : {metrics.current_drawdown_duration_seconds:.1f}s")
        self.logger.info(f"Active Positions   : {metrics.active_positions}")
        self.logger.info(f"Total Opened       : {metrics.positions_opened_total}")
        sharpe_disp = f"{metrics.sharpe_ratio:.2f}" if metrics.sharpe_ratio is not None else "N/A"
        try:
            rsh_disp = f"{metrics.rolling_sharpe:.2f}" if metrics.rolling_sharpe is not None else "N/A"
        except Exception:
            rsh_disp = "N/A"
        self.logger.info(f"Sharpe Ratio       : {sharpe_disp} | Rolling Sharpe: {rsh_disp}")

        # Symbol breakdown
        if metrics.symbol_aggregates:
            self.logger.info("")
            self.logger.info("Symbol breakdown:")
            self.logger.info("Symbol | Open | Unrealized | Realized PnL | Wins | Losses | Exposure")
            for s, v in metrics.symbol_aggregates.items():
                self.logger.info(
                    f"{s:6} | {v.get('open_positions',0):4d} | {v.get('unrealized_pnl',0.0):+9.2f} | {v.get('realized_pnl',0.0):+11.2f} | {v.get('realized_wins',0):4d} | {v.get('realized_losses',0):4d} | {v.get('exposure',0.0):+.2f}"
                )

        self.logger.info("============================================================")
        





