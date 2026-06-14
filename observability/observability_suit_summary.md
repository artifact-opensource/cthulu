# Cthulu Observability Suite - Complete System Summary

## Quick Start

```bash
# Run all three services with one command
python -m observability.suit --csv

# Or with Prometheus enabled
python -m observability.suit --csv --8181
```

---

## Architecture Overview

Three independent services providing complete observability:

```
Cthulu Trading System
│
├─→ Observability Service (separate process)
│   └─→ metrics/comprehensive_metrics.csv (173 trading metrics)
│
└─→ Monitoring Services (2 separate processes)
    ├─→ Indicator Monitoring → metrics/indicator_metrics.csv (78 fields + scoring)
    └─→ System Health → metrics/system_health.csv (80+ fields)
```

## Three Canonical CSV Files

These are the single sources of truth for Cthulu's performance analysis:

1. **metrics/comprehensive_metrics.csv** - Trading metrics (173 fields)
2. **metrics/indicator_metrics.csv** - Indicator/signal data with confidence scoring (78 fields)
3. **metrics/system_health.csv** - System health & performance (80+ fields)

---

## 1. Observability Service

**Output:** `metrics/comprehensive_metrics.csv`

### Simplified CLI

```bash
# CSV only (auto-path: observability/reporting/)
python -m observability.service --csv

# CSV + Prometheus on port 8181 (auto-path: prometheus/tmp/)
python -m observability.service --csv --8181

# CSV + Prometheus with explicit file
python -m observability.service --csv --prom --8181
```

### Features

- **173 comprehensive trading metrics** across 12 categories
- Real-time CSV export (always enabled)
- Optional Prometheus export (port-based enable: --8181, --8182, --8183)
- Separate process (non-blocking)
- Auto-path management
- Direct integration - no legacy MetricsCollector dependency

### Metric Categories

1. **Account Metrics** - Balance, equity, margin, P&L
2. **Trade Statistics** - Win rate, profit factor, total trades
3. **Risk & Drawdown** - Max/current drawdown, Sharpe ratio
4. **Advanced Statistics** - Sortino, Calmar, Omega, K-Ratio, VaR
5. **Execution Quality** - Slippage, execution time, fill rates
6. **Signals & Strategy** - Approved/rejected signals, reasons
7. **Position & Exposure** - Open positions, long/short distribution
8. **Per-Symbol Metrics** - Performance by trading pair
9. **Session & Time-Based** - Asian/European/US session analysis
10. **System Health** - CPU, memory, uptime, errors
11. **Adaptive & Dynamic** - Drawdown state, position sizing
12. **Performance Grades** - A-F grading by category

### Integration Example

```python
from observability.comprehensive_collector import ComprehensiveMetricsCollector

collector = ComprehensiveMetricsCollector()

# Direct metric updates from trading system
collector.record_trade_completed(is_win=True, pnl=25.50, duration_seconds=300)
collector.set_account_info(balance, equity, margin, free_margin, margin_level)
collector.update_position_count(active_positions, long_count, short_count)
collector.record_execution(execution_time_ms, slippage_pips)

# Bootstrap integration
from observability.integration import start_observability_service
process = start_observability_service(enable_prometheus=False)
```

---

## 2. Indicator Monitoring Service

**Output:** `metrics/indicator_metrics.csv` (78 fields)

### Features

- **JSON-Based Extensible Configuration** (`monitoring/indicator_config.json`)
- **8 Built-in Indicators:** RSI, MACD, Bollinger Bands, Stochastic, ADX, Supertrend, VWAP, ATR
- **6 Built-in Strategies:** SMA Crossover, EMA Crossover, Trend Following, Mean Reversion, Momentum, Scalping
- **Automatic Mathematical Scoring:**
  - **Confidence Score (0-1)** - Weighted combination of factors
  - **Confluence Score (0-1)** - Percentage of agreeing indicators
  - **Trend Alignment (0-1)** - Trend strength measurement
  - **Volume Confirmation (0-1)** - Volume support for signals
  - **Volatility Filter (0-1)** - Market condition filter
  - **Overall Score (0-1)** - Combined metric for signal quality

### Scoring System Explained

**Confidence Score** = Weighted average of:
- Indicator agreement (40%)
- Trend strength (30%)
- Volume confirmation (20%)
- Volatility filter (10%)

**Confluence Score** = Number of agreeing indicators / Total enabled indicators

**Overall Score** = (Confidence × 0.6) + (Confluence × 0.3) + (Trend Alignment × 0.1)

### Signal Quality Guidelines

- **Overall > 0.80**: Exceptional signal - high confidence trade
- **Overall > 0.75**: Strong signal - consider entry
- **Overall > 0.60**: Moderate signal - watch closely
- **Overall < 0.60**: Weak signal - avoid or wait

### Configuration

Edit `monitoring/indicator_config.json` to extend or reduce indicators/strategies:

```json
{
  "indicators": [
    {
      "name": "RSI",
      "enabled": true,
      "parameters": {
        "period": 14,
        "overbought": 70,
        "oversold": 30
      }
    },
    {
      "name": "MACD",
      "enabled": true,
      "parameters": {
        "fast": 12,
        "slow": 26,
        "signal": 9
      }
    }
  ],
  "strategies": [
    {
      "name": "SMA_Crossover",
      "enabled": true,
      "parameters": {
        "fast": 50,
        "slow": 200
      }
    }
  ],
  "scoring": {
    "confidence_weights": {
      "indicator_agreement": 0.4,
      "trend_strength": 0.3,
      "volume_confirmation": 0.2,
      "volatility_filter": 0.1
    }
  }
}
```

### Usage

```python
from monitoring.indicator_collector import IndicatorMetricsCollector

collector = IndicatorMetricsCollector()
collector.start()

# Update indicators in real-time
collector.update_rsi(value=65.5, signal="neutral", overbought=False, oversold=False)
collector.update_macd(macd=0.5, signal=0.3, histogram=0.2, macd_signal="bullish")
collector.update_bollinger(upper=1.2050, middle=1.2000, lower=1.1950, 
                           position="above_middle", bb_signal="bullish")
collector.update_strategy_signal("sma_crossover", signal="buy", score=0.85)

# Scores calculated automatically
snapshot = collector.get_current_snapshot()
print(f"Confidence: {snapshot.score_confidence:.2f}")
print(f"Confluence: {snapshot.score_confluence:.2f}")
print(f"Overall: {snapshot.score_overall:.2f}")

# Use scores for trade decisions
if snapshot.score_overall > 0.75 and snapshot.score_confluence > 0.6:
    # High confidence signal with good agreement
    execute_trade()
```

**Standalone:**
```bash
python -m monitoring.service indicator
```

---

## 3. System Health Monitoring Service

**Output:** `metrics/system_health.csv` (80+ fields)

### Features

- **Process Monitoring:** PID, CPU%, memory usage, thread counts
- **System Resources:** CPU load, memory stats, disk I/O, network I/O
- **Performance Metrics:** Loop rate (Hz), average loop time, GC statistics
- **Workload Tracking:** Pending/running/completed tasks, queue depths, thread pool stats
- **Database Metrics:** Connection pool statistics
- **API Status:** MT5 connection state, API latency, rate limit tracking
- **Error Tracking:** Total errors/warnings/exceptions + last hour counts
- **Uptime Tracking:** System uptime, process uptime

### Metric Categories

1. **Process Info** - PID, CPU%, memory, threads
2. **System CPU** - Overall load, per-core usage
3. **System Memory** - Total, available, used, swap
4. **Disk I/O** - Read/write bytes, IOPS
5. **Network I/O** - Sent/received bytes, packets
6. **Performance** - Loop rate, timing, GC
7. **Workload** - Tasks, queues, thread pools
8. **Database** - Connections, queries, latency
9. **API** - MT5 status, latency, limits
10. **Errors** - Counts by type and timeframe

### Usage

```python
from monitoring.system_health_collector import SystemHealthCollector

collector = SystemHealthCollector()
collector.start()  # Auto-collects system-level metrics

# Manual updates for application-specific metrics
collector.update_workload(pending=10, running=5, completed=1000)
collector.update_performance(loop_rate_hz=50.0, avg_loop_ms=20.0, gc_collections=5)
collector.update_api(mt5_connected=True, latency_ms=25.5, rate_limit_remaining=98)
collector.update_database(active_connections=8, idle_connections=2, max_connections=10)
collector.increment_error()
collector.increment_warning()
```

**Standalone:**
```bash
python -m monitoring.service system
```

---

## Running All Services

### Unified Command (Recommended)

```bash
# Run all three services at once
python -m observability.suit --csv

# With Prometheus
python -m observability.suit --csv --8181
```

### Individual Services

```bash
# Observability (trading metrics)
python -m observability.service --csv

# Monitoring (both indicator and system health)
python -m monitoring.service both

# Or separately
python -m monitoring.service indicator
python -m monitoring.service system
```

### Bootstrap Integration

```python
# Start all services from main trading system
from observability.suit import ObservabilitySuite

suite = ObservabilitySuite()
suite.start_all(enable_csv=True, enable_prometheus=False)

# Or use individual integration functions
from observability.integration import start_observability_service
from monitoring.service import start_indicator_process, start_system_health_process

obs_process = start_observability_service()
ind_process = start_indicator_process()
sys_process = start_system_health_process()
```

---

## Data Flow

```
Trading System
    │
    ├─→ ComprehensiveMetricsCollector → observability.service
    │                                         ↓
    │                         metrics/comprehensive_metrics.csv
    │                                         ↓
    │                                   (optional: Prometheus → Grafana)
    │
    ├─→ IndicatorMetricsCollector → monitoring.service (indicator)
    │                                         ↓
    │                           metrics/indicator_metrics.csv
    │
    └─→ SystemHealthCollector → monitoring.service (system)
                                              ↓
                                metrics/system_health.csv
```

---

## Performance Impact

- **CPU**: <1% per service (3 separate processes, isolated)
- **Memory**: ~50 MB per service (independent memory spaces)
- **Disk I/O**: Minimal (append-only operations)
- **Trading Loop**: Zero impact (non-blocking design)

---

## Use Cases

### 1. Signal Quality Assessment

Use the indicator monitoring service's automatic scoring to evaluate signal quality:

```python
snapshot = indicator_collector.get_current_snapshot()

if snapshot.score_overall > 0.80:
    print("EXCEPTIONAL signal - execute with full position size")
elif snapshot.score_overall > 0.75:
    print("STRONG signal - execute with standard position size")
elif snapshot.score_overall > 0.60:
    print("MODERATE signal - execute with reduced position size")
else:
    print("WEAK signal - skip trade")

# Check agreement
if snapshot.score_confluence > 0.7:
    print(f"{snapshot.signal_bullish_count} indicators agree - high conviction")
```

### 2. System Optimization

Use comprehensive metrics to optimize system performance:

```python
# Read system health CSV
import pandas as pd
health_df = pd.read_csv('metrics/system_health.csv')

# Identify performance issues
slow_loops = health_df[health_df['performance_loop_rate_hz'] < 40]
high_memory = health_df[health_df['process_memory_mb'] > 200]
high_cpu = health_df[health_df['system_cpu_percent'] > 80]

print(f"Slow loop periods: {len(slow_loops)}")
print(f"High memory periods: {len(high_memory)}")
print(f"High CPU periods: {len(high_cpu)}")
```

### 3. Trade Analysis

Use observability metrics for detailed trade analysis:

```python
# Read comprehensive metrics CSV
metrics_df = pd.read_csv('metrics/comprehensive_metrics.csv')

# Analyze execution quality
avg_slippage = metrics_df['execution_avg_slippage_pips'].mean()
avg_execution_time = metrics_df['execution_avg_time_ms'].mean()

print(f"Average slippage: {avg_slippage:.2f} pips")
print(f"Average execution: {avg_execution_time:.1f} ms")

# Analyze performance by session
asian_metrics = metrics_df[metrics_df['session_asian_trades'] > 0]
print(f"Asian session win rate: {asian_metrics['win_rate'].mean():.2%}")
```

---

## Optional: Prometheus/Grafana Integration

### Enable Prometheus Export

```bash
# Add --8181 flag to enable Prometheus on port 8181
python -m observability.suit --csv --8181
```

### Grafana Dashboards

Two comprehensive dashboards are included:

**1. Trading Dashboard** (`monitoring/grafana/dashboards/cthulu_trading.json`)
- 40+ panels covering account, performance, risk, trades, execution
- 5-second auto-refresh
- Real-time equity curve, P&L analysis
- Risk metrics: drawdown, Sharpe, win rate, profit factor

**2. System Health Dashboard** (`monitoring/grafana/dashboards/cthulu_system.json`)
- 11+ panels for system status, resources, signals
- CPU/memory monitoring
- MT5 connection status
- Error/warning tracking

### Prometheus Configuration

Configuration at `monitoring/prometheus.yml`:
- 5-second scrape interval
- 3 job configs (HTTP, textfile, node_exporter)
- Metric relabeling for cthulu_* patterns

---

## Documentation

**Observability:**
- `observability/README.md` - Complete observability guide
- `observability/DOCS.md` - Documentation index
- `observability/OBSERVABILITY_GUIDE.md` - Setup & testing guide
- `observability_suit_summary.md` - This file (system overview)

**Monitoring:**
- `monitoring/README.md` - Complete monitoring guide (11KB, 400+ lines)
- `monitoring/indicator_config.json` - Extensible configuration

**Schema & Reference:**
- `monitoring/COMPREHENSIVE_METRICS_SCHEMA.md` - All 173 trading metrics documented
- `monitoring/TRADING_REPORT.md` - Enhanced trading report with 20 new categories
- `monitoring/SUBPROGRAM_RECOMMENDATIONS.md` - 10 enhancement ideas with integration patterns

---

## Troubleshooting

### Services Won't Start

```bash
# Check if ports are in use
lsof -i :8181

# Check logs
tail -f observability/logs/observability.log
tail -f monitoring/logs/indicator.log
tail -f monitoring/logs/system_health.log
```

### CSV Files Not Updating

```bash
# Check if services are running
ps aux | grep observability
ps aux | grep monitoring

# Check file permissions
ls -la observability/reporting/
ls -la monitoring/
```

### High Memory Usage

```python
# Reduce update frequency
collector = ComprehensiveMetricsCollector(update_interval=5.0)  # 5 seconds instead of 1

# Or in service
python -m observability.service --csv --interval 5
```

---

## Summary

The Cthulu Observability Suite provides **three canonical CSV files** as single sources of truth:

1. **Trading Metrics** (173 fields) - Complete performance analysis
2. **Indicator Metrics** (78 fields) - Signal quality with automatic scoring
3. **System Health** (80+ fields) - Performance and resource monitoring

**One command to rule them all:**
```bash
python -m observability.suit --csv
```

All services run as separate processes with zero impact on trading performance. CSV files are continuously updated in real-time, providing comprehensive data for analysis, optimization, and decision-making.

