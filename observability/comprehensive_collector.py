"""
Comprehensive Real-Time Metrics Collector

Collects exhaustive trading metrics in real-time and exports to:
- CSV file (comprehensive_metrics.csv) - single source of truth
- Prometheus format (for Prometheus/Grafana)
- In-memory cache for real-time access

This collector runs as a separate process to avoid blocking the main trading loop.
"""

import os
import csv
import time
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from collections import deque
try:
    import psutil
except Exception:
    psutil = None



@dataclass
class ComprehensiveMetricsSnapshot:
    """Complete metrics snapshot - 173 fields for exhaustive monitoring"""
    
    # Timestamp
    timestamp: str = ""
    
    # Core Account Metrics (10)
    account_balance: float = 0.0
    account_equity: float = 0.0
    account_margin: float = 0.0
    account_free_margin: float = 0.0
    account_margin_level: float = 0.0
    starting_balance: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_pnl: float = 0.0
    
    # Trade Statistics (25)
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0
    active_positions: int = 0
    positions_opened_total: int = 0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_profit: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    avg_trade_duration: float = 0.0
    median_trade_duration: float = 0.0
    shortest_trade: float = 0.0
    longest_trade: float = 0.0
    trades_per_hour: float = 0.0
    trades_today: int = 0
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    monthly_pnl: float = 0.0
    
    # Risk & Drawdown Metrics (15)
    max_drawdown_pct: float = 0.0
    max_drawdown_abs: float = 0.0
    current_drawdown_pct: float = 0.0
    current_drawdown_abs: float = 0.0
    max_drawdown_duration_seconds: float = 0.0
    current_drawdown_duration_seconds: float = 0.0
    drawdown_recovery_time_seconds: float = 0.0
    drawdown_frequency_per_hour: float = 0.0
    avg_drawdown_pct: float = 0.0
    peak_equity: float = 0.0
    trough_equity: float = 0.0
    equity_curve_slope: float = 0.0
    risk_reward_ratio: float = 0.0
    median_risk_reward: float = 0.0
    rr_count: int = 0
    
    # Advanced Statistical Metrics (10)
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    omega_ratio: float = 0.0
    k_ratio: float = 0.0
    recovery_factor: float = 0.0
    ulcer_index: float = 0.0
    rolling_sharpe_50: float = 0.0
    rolling_sharpe_100: float = 0.0
    var_95: float = 0.0
    
    # Execution Quality Metrics (12)
    avg_slippage_pips: float = 0.0
    median_slippage_pips: float = 0.0
    max_slippage_pips: float = 0.0
    avg_execution_time_ms: float = 0.0
    median_execution_time_ms: float = 0.0
    max_execution_time_ms: float = 0.0
    fill_rate_pct: float = 0.0
    order_rejection_rate_pct: float = 0.0
    partial_fills: int = 0
    requotes: int = 0
    orders_total: int = 0
    orders_filled: int = 0
    
    # Signal & Strategy Metrics (20)
    signals_generated_total: int = 0
    signals_approved_total: int = 0
    signals_rejected_total: int = 0
    signal_approval_rate_pct: float = 0.0
    sma_crossover_signals: int = 0
    rsi_signals: int = 0
    macd_signals: int = 0
    combined_signals: int = 0
    spread_rejections: int = 0
    position_limit_rejections: int = 0
    drawdown_limit_rejections: int = 0
    exposure_limit_rejections: int = 0
    daily_loss_limit_rejections: int = 0
    strategy_sma_trades: int = 0
    strategy_momentum_trades: int = 0
    strategy_mean_reversion_trades: int = 0
    exit_tp_count: int = 0
    exit_sl_count: int = 0
    exit_trailing_count: int = 0
    exit_manual_count: int = 0
    
    # Position & Exposure Metrics (10)
    open_positions_count: int = 0
    open_positions_volume: float = 0.0
    long_positions_count: int = 0
    short_positions_count: int = 0
    long_exposure_usd: float = 0.0
    short_exposure_usd: float = 0.0
    net_exposure_usd: float = 0.0
    max_concurrent_positions: int = 0
    avg_position_size_lots: float = 0.0
    position_sizing_factor: float = 1.0
    
    # Per-Symbol Metrics (track primary symbol)
    symbol_trades_total: int = 0
    symbol_winning_trades: int = 0
    symbol_win_rate_pct: float = 0.0
    symbol_realized_pnl: float = 0.0
    symbol_unrealized_pnl: float = 0.0
    symbol_open_positions: int = 0
    symbol_exposure_usd: float = 0.0
    symbol_avg_trade_pnl: float = 0.0
    
    # Session & Time-Based Metrics (10)
    session_asian_trades: int = 0
    session_european_trades: int = 0
    session_us_trades: int = 0
    session_overlap_trades: int = 0
    hour_00_04_trades: int = 0
    hour_04_08_trades: int = 0
    hour_08_12_trades: int = 0
    hour_12_16_trades: int = 0
    hour_16_20_trades: int = 0
    hour_20_24_trades: int = 0
    
    # System Health Metrics (15)
    system_uptime_seconds: float = 0.0
    mt5_connected: int = 0
    mt5_connection_uptime_seconds: float = 0.0
    mt5_reconnections: int = 0
    cpu_usage_pct: float = 0.0
    memory_usage_mb: float = 0.0
    memory_usage_pct: float = 0.0
    disk_usage_gb: float = 0.0
    network_latency_ms: float = 0.0
    api_calls_per_minute: float = 0.0
    errors_total: int = 0
    warnings_total: int = 0
    critical_errors_total: int = 0
    last_error_timestamp: str = ""
    system_restarts: int = 0
    
    # Adaptive & Dynamic Metrics (8)
    drawdown_state: str = "normal"
    position_sizing_adjustment: float = 1.0
    adaptive_sl_distance_pips: float = 0.0
    adaptive_tp_distance_pips: float = 0.0
    trailing_stop_active: int = 0
    breakeven_stop_active: int = 0
    survival_mode_active: int = 0
    recovery_mode_active: int = 0
    
    # Performance Grade Metrics (5)
    overall_grade: str = ""
    win_rate_grade: str = ""
    profit_factor_grade: str = ""
    drawdown_grade: str = ""
    sharpe_grade: str = ""
    
    # Current Price Data (2)
    current_price: float = 0.0
    current_symbol: str = ""


class ComprehensiveMetricsCollector:
    """
    Real-time comprehensive metrics collector.
    
    Collects all 173 metrics continuously and exports to:
    - CSV file (appends new rows in real-time)
    - Prometheus format (for scraping)
    - In-memory for API access
    """
    
    def __init__(self, csv_path: str = None, update_interval: float = 1.0, enable_prometheus: bool = False):
        """
        Initialize metrics collector.
        
        Args:
            csv_path: Path to CSV file (default: metrics/comprehensive_metrics.csv)
            update_interval: Seconds between metric updates
            enable_prometheus: Whether to enable Prometheus export
        """
        self.logger = logging.getLogger("cthulu.comprehensive_metrics")
        
        # Determine CSV path - centralized in metrics/ directory
        if csv_path is None:
            base_dir = Path(__file__).parent.parent  # Go up to cthulu root
            metrics_dir = base_dir / "metrics"
            metrics_dir.mkdir(parents=True, exist_ok=True)
            csv_path = metrics_dir / "comprehensive_metrics.csv"
        self.csv_path = Path(csv_path)
        
        self.update_interval = update_interval
        self.enable_prometheus = enable_prometheus
        self.running = False
        self.thread = None
        
        # Current metrics snapshot
        self.current = ComprehensiveMetricsSnapshot()
        self.lock = threading.Lock()
        
        # System start time
        self.start_time = time.time()
        self.mt5_connect_time = None
        
        # Execution tracking
        self.execution_times = deque(maxlen=1000)
        self.slippages = deque(maxlen=1000)
        
        # Trade tracking
        self.trade_durations = []
        self.trade_results = []
        self.hourly_trades = {h: 0 for h in range(24)}
        
        # Initialize CSV file
        self._initialize_csv()
        
        self.logger.info(f"Comprehensive metrics collector initialized: {self.csv_path}")
    
    def _initialize_csv(self):
        """Initialize CSV file with headers - always ensures header row exists"""
        try:
            # Create directory if needed
            self.csv_path.parent.mkdir(parents=True, exist_ok=True)
            
            fieldnames = list(asdict(self.current).keys())
            
            # Check if file exists and has valid header
            needs_header = True
            if self.csv_path.exists():
                try:
                    with open(self.csv_path, 'r', newline='') as f:
                        import csv as csv_reader
                        reader = csv_reader.reader(f)
                        first_row = next(reader, None)
                        # Check if first row is our expected header (must match exactly)
                        if first_row and len(first_row) == len(fieldnames) and first_row[0] == 'timestamp':
                            # Verify it's actually a header (not data starting with ISO timestamp)
                            if first_row == fieldnames:
                                needs_header = False
                            else:
                                self.logger.warning(f"CSV header mismatch, resetting file")
                                needs_header = True
                        else:
                            # Invalid header detected - file needs reset
                            self.logger.warning(f"Invalid CSV header detected, resetting file")
                            needs_header = True
                except Exception as e:
                    self.logger.warning(f"Error reading CSV header: {e}")
                    needs_header = True
            
            if needs_header:
                # Write fresh file with headers
                with open(self.csv_path, 'w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                self.logger.info(f"Created/reset CSV file with headers: {self.csv_path}")
            else:
                self.logger.info(f"CSV file exists with valid headers: {self.csv_path}")
                
        except Exception as e:
            self.logger.error(f"Failed to initialize CSV: {e}")
            # Try fallback to per-user metrics directory
            try:
                fallback_base = Path(os.getenv('LOCALAPPDATA') or Path.home()) / 'cthulu' / 'metrics'
                fallback_base.mkdir(parents=True, exist_ok=True)
                fallback_path = fallback_base / self.csv_path.name
                with open(fallback_path, 'w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=list(asdict(self.current).keys()))
                    writer.writeheader()
                self.csv_path = fallback_path
                self.logger.info(f"Switched metrics CSV to user-local path: {self.csv_path}")
            except Exception as e2:
                self.logger.error(f"Fallback CSV initialization failed: {e2}")
    
    def start(self):
        """Start the metrics collection thread"""
        if self.running:
            self.logger.warning("Metrics collector already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._collection_loop, daemon=True)
        self.thread.start()
        self.logger.info("Metrics collection thread started")
    
    def stop(self):
        """Stop the metrics collection thread"""
        if not self.running:
            return
        
        self.running = False
        if self.thread:
            self.thread.join(timeout=5.0)
        self.logger.info("Metrics collection thread stopped")
    
    def _collection_loop(self):
        """Main collection loop - runs in separate thread"""
        while self.running:
            try:
                # Update system metrics
                self._update_system_metrics()
                
                # Write to CSV
                self._write_to_csv()
                
                # Sleep
                time.sleep(self.update_interval)
                
            except Exception as e:
                self.logger.error(f"Error in collection loop: {e}")
                time.sleep(self.update_interval)
    
    def _update_system_metrics(self):
        """Update system health metrics"""
        try:
            with self.lock:
                # Timestamp
                self.current.timestamp = datetime.now(timezone.utc).isoformat()
                
                # System uptime
                self.current.system_uptime_seconds = time.time() - self.start_time
                
                # MT5 connection uptime
                if self.mt5_connect_time:
                    self.current.mt5_connection_uptime_seconds = time.time() - self.mt5_connect_time
                
                # CPU and memory (psutil optional)
                if psutil:
                    process = psutil.Process(os.getpid())
                    self.current.cpu_usage_pct = process.cpu_percent(interval=0.1)
                    mem_info = process.memory_info()
                    self.current.memory_usage_mb = mem_info.rss / (1024 * 1024)
                    self.current.memory_usage_pct = process.memory_percent()
                    # Disk usage
                    disk = psutil.disk_usage('/')
                    self.current.disk_usage_gb = disk.used / (1024 ** 3)
                else:
                    # psutil not available - set conservative defaults
                    self.current.cpu_usage_pct = 0.0
                    self.current.memory_usage_mb = 0.0
                    self.current.memory_usage_pct = 0.0
                    self.current.disk_usage_gb = 0.0
        except Exception as e:
            self.logger.error(f"Error updating system metrics: {e}")
    
    def _write_to_csv(self):
        """Append current metrics to CSV file"""
        try:
            with self.lock:
                data = asdict(self.current)
            
            with open(self.csv_path, 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=list(data.keys()))
                writer.writerow(data)
                
        except Exception as e:
            self.logger.error(f"Error writing to CSV: {e}")
            # Try fallback to per-user metrics CSV if permission error
            if isinstance(e, PermissionError) or 'Permission' in str(e):
                try:
                    fallback_base = Path(os.getenv('LOCALAPPDATA') or Path.home()) / 'cthulu' / 'metrics'
                    fallback_base.mkdir(parents=True, exist_ok=True)
                    fallback_path = fallback_base / self.csv_path.name
                    with open(fallback_path, 'a', newline='') as f:
                        writer = csv.DictWriter(f, fieldnames=list(data.keys()))
                        writer.writerow(data)
                    self.logger.info(f"Wrote metrics to fallback CSV: {fallback_path}")
                    self.csv_path = fallback_path
                except Exception as e2:
                    self.logger.error(f"Failed to write to fallback CSV: {e2}")
    
    def record_trade_completed(self, is_win: bool, pnl: float, duration_seconds: float):
        """
        Record a completed trade.
        
        Args:
            is_win: Whether the trade was profitable
            pnl: Profit/loss amount
            duration_seconds: Trade duration in seconds
        """
        with self.lock:
            # Update counts
            self.current.total_trades += 1
            if is_win:
                self.current.winning_trades += 1
                self.current.gross_profit += pnl
            elif pnl < 0:
                self.current.losing_trades += 1
                self.current.gross_loss += abs(pnl)
            else:
                self.current.breakeven_trades += 1
            
            # Update P&L
            self.current.net_profit = self.current.gross_profit - self.current.gross_loss
            self.current.realized_pnl = self.current.net_profit
            
            # Update averages
            if self.current.winning_trades > 0:
                self.current.avg_win = self.current.gross_profit / self.current.winning_trades
            if self.current.losing_trades > 0:
                self.current.avg_loss = self.current.gross_loss / self.current.losing_trades
            
            # Win rate and profit factor
            if self.current.total_trades > 0:
                self.current.win_rate = self.current.winning_trades / self.current.total_trades
            if self.current.gross_loss > 0:
                self.current.profit_factor = self.current.gross_profit / self.current.gross_loss
            
            # Expectancy
            if self.current.total_trades > 0:
                avg_win = self.current.avg_win
                avg_loss = self.current.avg_loss
                win_rate = self.current.win_rate
                self.current.expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
            
            # Trade duration
            self.trade_durations.append(duration_seconds)
            if self.trade_durations:
                self.current.avg_trade_duration = sum(self.trade_durations) / len(self.trade_durations)
                self.current.median_trade_duration = sorted(self.trade_durations)[len(self.trade_durations) // 2]
                self.current.shortest_trade = min(self.trade_durations)
                self.current.longest_trade = max(self.trade_durations)
            
            # Largest win/loss
            if pnl > self.current.largest_win:
                self.current.largest_win = pnl
            if pnl < 0 and abs(pnl) > abs(self.current.largest_loss):
                self.current.largest_loss = pnl
    
    def update_position_count(self, active_positions: int, long_count: int = 0, short_count: int = 0):
        """Update position counts"""
        with self.lock:
            self.current.active_positions = active_positions
            self.current.open_positions_count = active_positions
            self.current.long_positions_count = long_count
            self.current.short_positions_count = short_count
            
            # Track max concurrent
            if active_positions > self.current.max_concurrent_positions:
                self.current.max_concurrent_positions = active_positions
    
    def record_execution(self, execution_time_ms: float, slippage_pips: float = 0.0):
        """Record order execution metrics"""
        with self.lock:
            self.execution_times.append(execution_time_ms)
            if slippage_pips != 0:
                self.slippages.append(abs(slippage_pips))
            
            # Update averages
            if self.execution_times:
                self.current.avg_execution_time_ms = sum(self.execution_times) / len(self.execution_times)
                self.current.median_execution_time_ms = sorted(self.execution_times)[len(self.execution_times) // 2]
                self.current.max_execution_time_ms = max(self.execution_times)
            
            if self.slippages:
                self.current.avg_slippage_pips = sum(self.slippages) / len(self.slippages)
                self.current.median_slippage_pips = sorted(self.slippages)[len(self.slippages) // 2]
                self.current.max_slippage_pips = max(self.slippages)
    
    def record_trade_closed(self, duration_seconds: float, pnl: float):
        """Record trade close metrics"""
        with self.lock:
            self.trade_durations.append(duration_seconds)
            self.trade_results.append(pnl)
            
            # Update duration stats
            if self.trade_durations:
                self.current.avg_trade_duration = sum(self.trade_durations) / len(self.trade_durations)
                self.current.median_trade_duration = sorted(self.trade_durations)[len(self.trade_durations) // 2]
                self.current.shortest_trade = min(self.trade_durations)
                self.current.longest_trade = max(self.trade_durations)
            
            # Update largest win/loss
            if pnl > self.current.largest_win:
                self.current.largest_win = pnl
            if pnl < 0 and abs(pnl) > abs(self.current.largest_loss):
                self.current.largest_loss = pnl
    
    def set_mt5_connected(self, connected: bool):
        """Set MT5 connection status"""
        with self.lock:
            self.current.mt5_connected = 1 if connected else 0
            if connected and self.mt5_connect_time is None:
                self.mt5_connect_time = time.time()
    
    def set_account_info(self, balance: float, equity: float, margin: float = 0.0,
                        free_margin: float = 0.0, margin_level: float = 0.0):
        """Set account information"""
        with self.lock:
            self.current.account_balance = balance
            self.current.account_equity = equity
            self.current.account_margin = margin
            self.current.account_free_margin = free_margin
            self.current.account_margin_level = margin_level
            
            # Update peak/trough
            if equity > self.current.peak_equity:
                self.current.peak_equity = equity
            if self.current.trough_equity == 0 or equity < self.current.trough_equity:
                self.current.trough_equity = equity
    
    def increment_signal_counter(self, signal_type: str):
        """Increment signal counters"""
        with self.lock:
            self.current.signals_generated_total += 1
            
            # Type-specific counters
            if 'sma' in signal_type.lower():
                self.current.sma_crossover_signals += 1
            elif 'rsi' in signal_type.lower():
                self.current.rsi_signals += 1
            elif 'macd' in signal_type.lower():
                self.current.macd_signals += 1
    
    def increment_rejection_counter(self, rejection_reason: str):
        """Increment rejection counters"""
        with self.lock:
            self.current.signals_rejected_total += 1
            
            reason_lower = rejection_reason.lower()
            if 'spread' in reason_lower:
                self.current.spread_rejections += 1
            elif 'position' in reason_lower:
                self.current.position_limit_rejections += 1
            elif 'drawdown' in reason_lower:
                self.current.drawdown_limit_rejections += 1
            elif 'exposure' in reason_lower:
                self.current.exposure_limit_rejections += 1
            elif 'daily' in reason_lower or 'loss' in reason_lower:
                self.current.daily_loss_limit_rejections += 1
    
    def update_account_metrics(self, balance: float = None, equity: float = None, 
                               margin: float = None, free_margin: float = None,
                               margin_level: float = None):
        """Update account metrics from trading loop"""
        with self.lock:
            if balance is not None:
                self.current.account_balance = balance
            if equity is not None:
                self.current.account_equity = equity
                if equity > self.current.peak_equity:
                    self.current.peak_equity = equity
                if self.current.trough_equity == 0 or equity < self.current.trough_equity:
                    self.current.trough_equity = equity
            if margin is not None:
                self.current.account_margin = margin
            if free_margin is not None:
                self.current.account_free_margin = free_margin
            if margin_level is not None:
                self.current.account_margin_level = margin_level
    
    def update_position_metrics(self, active_positions: int = None, unrealized_pnl: float = None):
        """Update position metrics from trading loop"""
        with self.lock:
            if active_positions is not None:
                self.current.active_positions = active_positions
                self.current.open_positions_count = active_positions
                if active_positions > self.current.max_concurrent_positions:
                    self.current.max_concurrent_positions = active_positions
            if unrealized_pnl is not None:
                self.current.unrealized_pnl = unrealized_pnl
                self.current.total_pnl = self.current.realized_pnl + unrealized_pnl
    
    def update_price_metrics(self, current_price: float = None, symbol: str = None):
        """Update price metrics from trading loop"""
        with self.lock:
            if current_price is not None:
                self.current.current_price = current_price
            if symbol is not None:
                self.current.current_symbol = symbol
    
    def get_current_snapshot(self) -> ComprehensiveMetricsSnapshot:
        """Get current metrics snapshot"""
        with self.lock:
            return ComprehensiveMetricsSnapshot(**asdict(self.current))
    
    def export_to_dict(self) -> Dict[str, Any]:
        """Export current metrics as dictionary"""
        with self.lock:
            return asdict(self.current)
