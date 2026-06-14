# Cthulu Comprehensive Observability System

## Overview

Real-time metrics collection system for exhaustive trading system monitoring and benchmarking.

**Core Feature:** Comprehensive CSV export (173 metrics)  
**Optional Feature:** Prometheus/Grafana integration

## Architecture

```
Trading System → ComprehensiveCollector → comprehensive_metrics.csv (REQUIRED)
                                       → Prometheus Export (OPTIONAL with --enable-prometheus)
                                       → Grafana Dashboards (OPTIONAL)
```

**Key Design Principle:** Direct integration. No legacy MetricsCollector dependency.

## Core Component: ComprehensiveMetricsCollector

**File:** `observability/comprehensive_collector.py`

Collects **173 metrics** in real-time across 12 categories:
- Core Account Metrics (10)
- Trade Statistics (25)
- Risk & Drawdown (15)
- Advanced Statistics (10)
- Execution Quality (12)
- Signals & Strategy (20)
- Position & Exposure (10)
- Per-Symbol Metrics (8)
- Session & Time-Based (10)
- System Health (15)
- Adaptive & Dynamic (8)
- Performance Grades (5)

**Output:** `observability/comprehensive_metrics.csv` (continuously appended, single source of truth)

### Direct Integration Methods

```python
from observability.comprehensive_collector import ComprehensiveMetricsCollector

collector = ComprehensiveMetricsCollector()
collector.start()  # Starts background thread

# Direct metric updates from trading system
collector.set_account_info(balance=10000.0, equity=10050.0, margin=100.0, 
                          free_margin=9900.0, margin_level=10050.0)

collector.record_trade_completed(is_win=True, pnl=25.50, duration_seconds=300)

collector.update_position_count(active_positions=2, long_count=1, short_count=1)

collector.record_execution(execution_time_ms=50.5, slippage_pips=0.2)

collector.increment_signal_counter("sma_crossover")

collector.increment_rejection_counter("spread_too_wide")

collector.set_mt5_connected(True)
```

## Observability Service (Separate Process)

**File:** `observability/service.py`

Runs as independent process to avoid blocking main trading loop.

**Required:** CSV export  
**Optional:** Prometheus export (use `--enable-prometheus` flag)

### Standalone Usage

**Simplified CLI:**

```bash
# CSV only (writes to observability/reporting/)
python -m observability.service --csv

# CSV + Prometheus on port 8181 (auto-enabled, writes to prometheus/tmp/)
python -m observability.service --csv --8181

# CSV + Prometheus + custom prometheus output
python -m observability.service --csv --prom --8181

# Other port options
python -m observability.service --csv --8182  # Port 8182
python -m observability.service --csv --8183  # Port 8183
```

**Legacy CLI (still supported):**

```bash
# CSV with explicit path
python -m observability.service --csv observability/comprehensive_metrics.csv

# CSV + Prometheus with explicit paths
python -m observability.service --csv observability/comprehensive_metrics.csv \
                                 --prometheus /tmp/cthulu_metrics.prom \
                                 --enable-prometheus \
                                 --http-port 8181
```

### Programmatic Integration

```python
from observability.integration import start_observability_service, stop_observability_service

# CSV only
process = start_observability_service()

# CSV + Prometheus
process = start_observability_service(
    enable_prometheus=True,
    http_port=8181
)

# Later: stop service
stop_observability_service(process)
```

## Bootstrap Integration

Add to `core/bootstrap.py`:

```python
from observability.integration import start_observability_service

# During system initialization
observability_process = start_observability_service(
    enable_prometheus=False  # Set True only if using Grafana
)

# Store for cleanup
components.observability_process = observability_process
```

Add to `core/shutdown.py`:

```python
from observability.integration import stop_observability_service

if hasattr(components, 'observability_process'):
    stop_observability_service(components.observability_process)
```

## Trading Loop Integration

```python
# In trading loop, update metrics directly
from observability.comprehensive_collector import ComprehensiveMetricsCollector

# Get collector instance (or create if needed)
collector = ComprehensiveMetricsCollector()

# After trade execution
collector.record_trade_completed(
    is_win=(pnl > 0),
    pnl=pnl,
    duration_seconds=trade_duration
)

# After order execution
collector.record_execution(
    execution_time_ms=execution_time,
    slippage_pips=slippage
)

# Update account info periodically
collector.set_account_info(
    balance=account.balance,
    equity=account.equity,
    margin=account.margin,
    free_margin=account.free_margin,
    margin_level=account.margin_level
)

# Update position counts
collector.update_position_count(
    active_positions=len(open_positions),
    long_count=long_positions,
    short_count=short_positions
)

# Track signals
collector.increment_signal_counter(signal_type)

# Track rejections
collector.increment_rejection_counter(rejection_reason)
```

## Optional: Prometheus/Grafana Setup

**Only configure if you need real-time dashboards. CSV is the primary output.**

### 1. Install Dependencies

```bash
pip install prometheus-client
```

### 2. Configure Prometheus

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'cthulu'
    static_configs:
      - targets: ['localhost:8181']  # If using HTTP
    scrape_interval: 5s

  - job_name: 'cthulu_textfile'
    static_configs:
      - targets: ['localhost:9100']
    metric_relabel_configs:
      - source_labels: [__name__]
        regex: 'cthulu_.*'
        action: keep
```

### 3. Import Grafana Dashboards

1. Open Grafana UI
2. Navigate to Dashboards → Import
3. Upload `monitoring/grafana/dashboards/cthulu_trading.json`
4. Upload `monitoring/grafana/dashboards/cthulu_system.json`

## Metrics Reference

See `monitoring/COMPREHENSIVE_METRICS_SCHEMA.md` for all 173 metrics.

**Key Metrics:**
- `cthulu_account_balance` - Account balance ($)
- `cthulu_account_equity` - Account equity ($)
- `cthulu_total_pnl` - Total P&L ($)
- `cthulu_total_trades` - Total trades
- `cthulu_win_rate_pct` - Win rate (%)
- `cthulu_profit_factor` - Profit factor
- `cthulu_max_drawdown_pct` - Max drawdown (%)
- `cthulu_sharpe_ratio` - Sharpe ratio
- `cthulu_active_positions` - Open positions
- `cthulu_mt5_connected` - MT5 status (0/1)

## Performance

- **CPU**: <1% (separate process)
- **Memory**: ~50 MB (isolated)
- **Disk I/O**: Minimal (append-only)
- **Trading Loop**: Zero impact

## Troubleshooting

### CSV not updating
- Check observability service is running: `ps aux | grep observability`
- Verify write permissions on CSV location
- Check service logs

### Prometheus not working (if enabled)
- Verify `--enable-prometheus` flag is used
- Check Prometheus config
- Verify textfile collector path
- Query metrics directly: `curl localhost:8181/metrics`

### High resource usage
- Increase `update_interval` (default 1.0s)
- Disable Prometheus if not needed
- Use CSV-only mode

## Best Practices

1. **Always use CSV mode** - It's the single source of truth
2. **Prometheus is optional** - Only enable if you need Grafana dashboards
3. **Run as separate process** - Never block the trading loop
4. **Monitor CSV file size** - Rotate or archive periodically (1 day ≈ 15-20 MB)
5. **Back up CSV regularly** - It contains all historical metrics

## Files

**Core:**
- `observability/comprehensive_collector.py` - Metrics collector
- `observability/service.py` - Separate process manager
- `observability/integration.py` - Bootstrap hooks

**Documentation:**
- `monitoring/COMPREHENSIVE_METRICS_SCHEMA.md` - All 173 metrics
- `monitoring/TRADING_REPORT.md` - Enhanced report template
- `monitoring/SUBPROGRAM_RECOMMENDATIONS.md` - System enhancements

**Optional (Grafana):**
- `monitoring/grafana/dashboards/cthulu_trading.json`
- `monitoring/grafana/dashboards/cthulu_system.json`
- `monitoring/prometheus.yml`

---

**Version:** 2.0.0 (Simplified)  
**Status:** Production Ready  
**Core Principle:** Direct integration, CSV-first, Prometheus optional
