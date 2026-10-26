# Monitoring Services

 ![Version](https://img.shields.io/badge/Version-6.0.0-4B0082?style=for-the-badge&labelColor=0D1117&logo=git&logoColor=white) 
 ![Last Update](https://img.shields.io/badge/Last_Update-2026--01--06-4B0082?style=for-the-badge&labelColor=0D1117&logo=calendar&logoColor=white) 
 ![Last Commit](https://img.shields.io/github/last-commit/amuzetnoM/cthulu?branch=main&style=for-the-badge&logo=github&labelColor=0D1117&color=6A00FF)

> Core monitoring infrastructure for Cthulu's indicators, signals, and system health.

## Overview

Three specialized monitoring services that create comprehensive CSV outputs:

1. **Indicator Monitoring** - Real-time indicator values, signals, and confidence scoring
2. **System Health Monitoring** - Process metrics, resources, and performance tracking
3. **Comprehensive Metrics** - Trading performance, equity, and position tracking

### v6.0.0

- **Real-Time Dashboard** - HTML dashboard with live charts and benchmarking
- **RSI Reversal Tracking** - Monitors RSI extreme reversals for signal analysis
- **Multi-Strategy Attribution** - Tracks which strategy (primary or fallback) generated signals
- **Enhanced Benchmarking** - Automated grade calculation (A+ to F)

## Architecture

```
Cthulu Trading System v6.0.0
    ├─→ Indicator Collector → metrics/indicator_metrics.csv
    ├─→ System Health Collector → metrics/system_health.csv
    └─→ Comprehensive Collector → metrics/comprehensive_metrics.csv
                                        │
                                        ↓
                              Dashboard (dashboard.html)
                                 ├─→ Balance/Equity Charts
                                 ├─→ RSI/ADX Charts
                                 ├─→ Benchmarking Tools
                                 └─→ Performance Grades
```

**3 Canonical CSV Files:**
1. `metrics/indicator_metrics.csv` - Indicator/signal data with scoring
2. `metrics/system_health.csv` - System health metrics  
3. `metrics/comprehensive_metrics.csv` - Trading metrics

## 1. Indicator Monitoring Service

**File:** `monitoring/indicator_collector.py`  
**Output:** `metrics/indicator_metrics.csv`  
**Purpose:** Monitor all indicators and strategies with automatic confidence/confluence scoring

### Features

- **JSON-Based Configuration** - Extensible indicator/strategy setup
- **Real-Time Collection** - All indicator values in single CSV
- **Automatic Scoring** - Confidence, confluence, trend alignment
- **Signal Analysis** - Agreement percentage, direction counts
- **Near-Perfect Signal Detection** - Mathematical scoring for optimization

### Configuration

Edit `monitoring/indicator_config.json` to add/remove indicators:

```json
{
  "indicators": [
    {
      "name": "RSI",
      "enabled": true,
      "parameters": {"period": 14},
      "outputs": ["value", "overbought", "oversold"]
    }
  ],
  "strategies": [
    {
      "name": "SMA_Crossover",
      "enabled": true,
      "parameters": {"fast_period": 50, "slow_period": 200},
      "outputs": ["signal", "strength"]
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

### Current Indicators (8)

- RSI - Relative Strength Index
- MACD - Moving Average Convergence Divergence
- Bollinger Bands - Volatility bands
- Stochastic - Momentum oscillator
- ADX - Trend strength
- Supertrend - Trend following
- VWAP - Volume weighted average price
- ATR - Average True Range

### Current Strategies (7)

- SMA Crossover - Simple moving average
- EMA Crossover - Exponential moving average
- Trend Following - Directional trends
- Mean Reversion - Overbought/oversold
- Momentum Breakout - Breakout detection
- Scalping - Quick trades
- **RSI Reversal (NEW in v5.1)** - Pure RSI-based trading without crossovers

### Output Columns (78 fields)

**Indicator Values:**
- RSI, MACD, Bollinger Bands, Stochastic, ADX, Supertrend, VWAP, ATR
- Volume metrics (current, average, relative)
- Price action (current, change %)

**Strategy Signals:**
- Signal for each strategy (buy/sell/none)
- Strength/score for each signal

**Calculated Scores (Frozen Columns):**
- `score_confidence` - Weighted combination of factors (0-1)
- `score_confluence` - Number of agreeing indicators (0-1)
- `score_trend_alignment` - Trend strength component (0-1)
- `score_volume_confirmation` - Volume confirmation (0-1)
- `score_volatility_filter` - Volatility filter (0-1)
- `score_overall` - Combined confidence + confluence (0-1)

**Signal Summary:**
- `signal_count_bullish` - Number of buy signals
- `signal_count_bearish` - Number of sell signals
- `signal_count_neutral` - Number of neutral signals
- `signal_agreement_pct` - Agreement percentage (0-100%)

### Usage

```python
from monitoring.indicator_collector import IndicatorMetricsCollector

# Create collector
collector = IndicatorMetricsCollector(
    csv_path="metrics/indicator_metrics.csv",  # Optional
    config_path="monitoring/indicator_config.json",  # Optional
    update_interval=1.0  # Seconds between CSV writes
)

# Start background thread
collector.start()

# Update indicators
collector.update_rsi(value=65.5, overbought=True)
collector.update_macd(macd=0.5, signal=0.3, histogram=0.2)
collector.update_bollinger(upper=1.1050, middle=1.1000, lower=1.0950, price=1.1020)

# Update strategy signals
collector.update_strategy_signal("sma_crossover", signal="buy", score=0.85)
collector.update_strategy_signal("ema_crossover", signal="buy", score=0.78)

# Scores are calculated automatically on each update
snapshot = collector.get_current_snapshot()
print(f"Confidence: {snapshot.score_confidence:.2f}")
print(f"Confluence: {snapshot.score_confluence:.2f}")
print(f"Overall: {snapshot.score_overall:.2f}")

# Stop when done
collector.stop()
```

### Standalone Service

```bash
# Run indicator monitoring service
python -m monitoring.service indicator

# With custom interval
python -m monitoring.service indicator --interval 2.0

# With custom config
python -m monitoring.service indicator --config my_config.json
```

## 2. System Health Monitoring Service

**File:** `monitoring/system_health_collector.py`  
**Output:** `metrics/system_health.csv`  
**Purpose:** Track system-level operations, NOT trading metrics

### Features

- **Process Monitoring** - CPU, memory, threads per process
- **System Resources** - CPU, memory, disk, network
- **Performance Tracking** - Loop rate, timing, GC stats
- **Error Tracking** - Errors, warnings, exceptions
- **Workload Metrics** - Tasks, queues, thread pools

### Output Columns (80+ fields)

**Process Info:**
- PID, name, status, threads, CPU%, memory

**Child Processes:**
- Count, total CPU, total memory

**System CPU:**
- Percent, core count, frequency

**System Memory:**
- Total, available, used, percent, cached

**System Disk:**
- Total, used, free, percent, read/write MB

**Network:**
- Sent/received MB, connections, established

**System Load:**
- 1min, 5min, 15min averages

**Workload:**
- Tasks (pending, running, completed), queue size

**Thread Pool:**
- Size, active, idle threads

**Performance:**
- Loop rate (Hz), average loop time, max loop time, GC stats

**Database:**
- Active connections, idle, pool size

**API Connections:**
- MT5 status, latency, rate limits

**Errors:**
- Total errors, warnings, exceptions (total + last hour)

**Uptime:**
- System uptime, process uptime

**Temperature:**
- CPU temp, GPU temp (if available)

### Usage

```python
from monitoring.system_health_collector import SystemHealthCollector

# Create collector
collector = SystemHealthCollector(
    csv_path="metrics/system_health.csv",  # Optional
    update_interval=5.0  # Seconds between collections
)

# Start (auto-collects system metrics)
collector.start()

# Manual updates for application-specific metrics
collector.update_workload(pending=10, running=5, completed=1000, queue_size=15)
collector.update_threadpool(size=10, active=3, idle=7)
collector.update_performance(loop_rate_hz=50.0, avg_loop_ms=20.0, max_loop_ms=100.0)
collector.update_database(active=5, idle=10, pool_size=15)
collector.update_api(mt5_connected=True, latency_ms=25.5, rate_limit=1000)

# Error tracking
collector.increment_error()
collector.increment_warning()
collector.increment_exception()

# Stop when done
collector.stop()
```

### Standalone Service

```bash
# Run system health monitoring service
python -m monitoring.service system

# With custom interval
python -m monitoring.service system --system-interval 10.0
```

## Running Both Services

```bash
# Run both services simultaneously
python -m monitoring.service both

# With custom intervals
python -m monitoring.service both --interval 1.0 --system-interval 5.0
```

## Integration with Cthulu

### Bootstrap Integration

Add to `core/bootstrap.py`:

```python
from monitoring.service import start_indicator_process, start_system_health_process

# Start monitoring services
indicator_process = start_indicator_process(update_interval=1.0)
system_process = start_system_health_process(update_interval=5.0)

# Store for cleanup
components.indicator_monitor = indicator_process
components.system_monitor = system_process
```

### Trading Loop Integration

```python
from monitoring.indicator_collector import IndicatorMetricsCollector
from monitoring.system_health_collector import SystemHealthCollector

# Get collectors
indicator_collector = IndicatorMetricsCollector()
system_collector = SystemHealthCollector()

# In trading loop, update indicator values
indicator_collector.update_rsi(rsi_value, overbought, oversold)
indicator_collector.update_macd(macd, signal, histogram)
# ... update all indicators

# Update strategy signals
for strategy in active_strategies:
    indicator_collector.update_strategy_signal(
        strategy.name, 
        strategy.current_signal,
        strategy.signal_strength
    )

# Check scores for trade decisions
snapshot = indicator_collector.get_current_snapshot()
if snapshot.score_overall > 0.75 and snapshot.signal_agreement_pct > 70:
    # High confidence signal - consider taking trade
    pass

# Update system health
system_collector.update_workload(pending, running, completed, queue_size)
system_collector.update_performance(loop_rate, avg_time, max_time)
```

## File Locations

**Core Files:**
- `monitoring/indicator_collector.py` - Indicator monitoring collector
- `monitoring/system_health_collector.py` - System health collector
- `monitoring/service.py` - Service runners
- `monitoring/indicator_config.json` - Indicator configuration

**Outputs:**
- `metrics/indicator_metrics.csv` - Indicator data (1-second updates)
- `metrics/system_health.csv` - System health (5-second updates)

**Configuration:**
- `monitoring/indicator_config.json` - Extensible indicator/strategy config

## Best Practices

1. **Indicator Monitoring**
   - Update all indicators every tick/bar
   - Use scores for trade filtering
   - Adjust `confidence_weights` based on backtesting
   - Add/remove indicators via JSON config

2. **System Health Monitoring**
   - Monitor for resource leaks
   - Track error rates
   - Alert on high CPU/memory
   - Correlate performance with trading activity

3. **CSV Management**
   - Rotate files daily/weekly (can get large)
   - Archive historical data
   - Use for post-analysis and optimization
   - Parse for real-time alerts if needed

4. **Performance**
   - Indicator service: 1-second interval (fast updates)
   - System health: 5-second interval (adequate for monitoring)
   - Run as separate processes (non-blocking)

## Troubleshooting

**Indicator CSV not updating:**
- Check service is running: `ps aux | grep indicator_service`
- Verify config JSON is valid
- Check file write permissions

**System health CSV not updating:**
- Check service is running: `ps aux | grep system_health_service`
- Verify psutil is installed: `pip install psutil`
- Check file write permissions

**High resource usage:**
- Increase update intervals
- Disable unused indicators in JSON config
- Check for CSV file size (rotate if needed)

**Missing indicators:**
- Add to `indicator_config.json`
- Ensure indicator class exists
- Check indicator is enabled in config

## Requirements

```bash
pip install psutil  # For system health monitoring
```

---

**Purpose:** Comprehensive monitoring of indicators, signals, and system health  
**Outputs:** 2 canonical CSV files  
**Design:** Extensible, JSON-configured, with automatic scoring  
**Integration:** Direct integration with trading loop

