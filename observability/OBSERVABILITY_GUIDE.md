# Cthulu Observability Guide

**Version:** 1.0
**Last Updated:** 2025-12-29

---

## Purpose

This guide provides comprehensive instructions for setting up, running, and analyzing Cthulu's monitoring, stress testing, and observability infrastructure. Reading this document should bring any AI agent or human fully up to speed with the testing methodology and goals.

---

## Quick Context

**Current State:**
- Demo Account: ****0069
- Symbol: BTCUSD#
- Mindset: ultra_aggressive
- Prometheus: http://127.0.0.1:8181/metrics
- RPC Server: http://127.0.0.1:8278/trade

**Goal:** Achieve 120 minutes of error-free runtime while stress testing all indicators, signal generation, risk management, and trade execution pipelines.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CTHULU SYSTEM                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────┐    ┌────────────┐    ┌─────────────┐    ┌──────────┐ │
│  │ Market   │───▶│ Indicators │───▶│  Strategy   │───▶│  Signal  │ │
│  │ Data     │    │ (11 types) │    │  Evaluator  │    │Generator │ │
│  └──────────┘    └────────────┘    └─────────────┘    └────┬─────┘ │
│                                                            │       │
│  ┌──────────┐    ┌────────────┐    ┌─────────────┐    ┌────▼─────┐ │
│  │   MT5    │◀───│ Execution  │◀───│    Risk     │◀───│  Signal  │ │
│  │ Broker   │    │  Engine    │    │  Evaluator  │    │  Queue   │ │
│  └──────────┘    └────────────┘    └─────────────┘    └──────────┘ │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    RPC Server (:8278)                         │  │
│  │    POST /trade - Manual trade injection                       │  │
│  │    GET /provenance - Order audit trail                        │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                 Prometheus Exporter (:8181)                   │  │
│  │    /metrics - All performance and trading metrics             │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Monitoring Infrastructure

### File Structure

```
C:\workspace\cthulu\monitoring\
├── run_stress.ps1              # Main 120-minute stress test orchestrator
├── inject_signals.py           # Signal injection tool (burst/pattern/manual)
├── collect_metrics.ps1         # Prometheus + process metric collector
├── indicator_stress_test.py    # Indicator calculation validation
├── dual_monitor.ps1            # Split-pane view (Cthulu + Injection logs)
├── live_monitor.bat            # Double-click launcher for live tail
├── metrics.csv                 # Time-series metrics (auto-populated)
├── signal_checklist.md         # Exhaustive test matrix
├── monitoring_report.md        # Analysis and insights
└── observability_guide.md      # This file
```

---

## How to Run the Full Stress Test

### Prerequisites

1. **MT5 Terminal** - Running and logged into demo/live account ****0069
2. **Python 3.12+** - With cthulu package installed
3. **PowerShell 7+** - For running monitoring scripts

### Step-by-Step Execution

#### Step 1: Start Cthulu with RPC Enabled

```powershell
cd C:\workspace\cthulu
python -m cthulu --config config.json --mindset ultra_aggressive --skip-setup
```

Verify RPC is running:
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8278/trade" -Method POST `
  -Headers @{"Content-Type"="application/json"} `
  -Body '{"symbol":"BTCUSD#","side":"BUY","volume":0.01}'
```

#### Step 2: Launch Dual Monitor View

```powershell
# Opens split view: Left=Cthulu logs, Right=Injection logs
.\monitoring\dual_monitor.ps1
```

Or double-click: `C:\workspace\cthulu\monitoring\live_monitor.bat`

#### Step 3: Run Full Stress Test (120 minutes)

```powershell
.\monitoring\run_stress.ps1 -DurationMinutes 120 -BurstCount 200 -BurstRate 10
```

This will:
1. Backup current config.json
2. Apply ultra_aggressive mindset
3. Start Cthulu with RPC enabled
4. Launch metric collector (10s intervals)
5. Launch auto-restart monitor
6. Execute burst injection (200 trades @ 10/sec)
7. Run for 120 minutes
8. Restore original config

---

## Signal Injection Methods

### Method 1: RPC Trade Injection

Direct trade placement via HTTP:

```python
# From inject_signals.py
python monitoring\inject_signals.py --mode burst --count 100 --rate 5 --symbol BTCUSD#
python monitoring\inject_signals.py --mode pattern --pattern "BUY,SELL,BUY" --repeat 50
python monitoring\inject_signals.py --mode manual --side BUY --volume 0.05 --symbol BTCUSD#
```

### Method 2: Indicator Stress Testing

Validates all 11 indicators with synthetic data:

```python
python monitoring\indicator_stress_test.py
```

**Indicators Tested:**
| Indicator | Test Cases | Validation |
|-----------|------------|------------|
| RSI | Overbought(100), Oversold(0), Neutral(50) | Range 0-100 |
| MACD | Uptrend, Downtrend, Crossover | Histogram sign |
| Bollinger | Squeeze, Expansion, Touch bands | Band width |
| ADX | Strong trend(>25), Ranging(<20) | DI+/DI- crossover |
| Supertrend | Uptrend(+1), Downtrend(-1) | Direction flip |
| ATR | High volatility, Low volatility | Value magnitude |
| Stochastic | Overbought, Oversold, Cross | %K/%D levels |
| VWAP | Above/Below price | Deviation calc |
| Volume | Spike detection, Average volume | Ratio check |

---

## Metrics Collection

### Prometheus Metrics (http://127.0.0.1:8181/metrics)

**Trading Metrics:**
- `cthulu_trades_total` - Total trades executed
- `cthulu_trades_won` - Winning trades
- `cthulu_trades_lost` - Losing trades
- `cthulu_pnl_total` - Net P&L
- `cthulu_win_rate` - Win percentage
- `cthulu_profit_factor` - Gross profit / Gross loss

**Risk Metrics:**
- `cthulu_drawdown_percent` - Current drawdown %
- `cthulu_drawdown_abs` - Drawdown in currency
- `cthulu_avg_rr` - Average risk:reward ratio
- `cthulu_expectancy` - Expected value per trade

**System Metrics:**
- `cthulu_sharpe` - Sharpe ratio
- `cthulu_open_positions` - Current open positions
- `cthulu_symbol_exposure{symbol}` - Per-symbol exposure

### CSV Metrics (monitoring/metrics.csv)

Collected every 10 seconds:
```csv
timestamp,cthulu_pid,mt5_pids,cpu_percent,memory_mb,open_positions,equity,balance
```

---

## Grading System

### Component Grades

| Grade | Range | Description |
|-------|-------|-------------|
| A+ | 100% | Perfect - All tests pass |
| A | 95-99% | Excellent - Minor issues only |
| A- | 90-94% | Very Good - Few failures |
| B+ | 85-89% | Good - Some issues |
| B | 80-84% | Acceptable - Multiple issues |
| B- | 75-79% | **TARGET MINIMUM** |
| C | 70-74% | Needs improvement |
| D | 60-69% | Significant problems |
| F | <60% | Critical failures |

### Grading Formula

```
Overall Grade = (
    Indicator_Score * 0.20 +
    Signal_Score * 0.20 +
    Risk_Score * 0.20 +
    Execution_Score * 0.20 +
    Stability_Score * 0.20
)

Where:
- Indicator_Score = (Tests_Passed / Total_Tests) * 100
- Signal_Score = (Signals_Generated / Expected_Signals) * 100
- Risk_Score = (Correct_Approvals / Total_Checks) * 100
- Execution_Score = (Successful_Orders / Total_Orders) * 100
- Stability_Score = (Uptime_Minutes / 120) * 100
```

---

## Troubleshooting

### RPC Connection Issues

**Symptom:** `SIMULATED (RPC down)` in inject logs

**Solutions:**
1. Verify Cthulu is running: `Get-Process python | Where-Object {$_.CommandLine -match 'cthulu'}`
2. Check RPC port: `Test-NetConnection -ComputerName localhost -Port 8278`
3. Verify config has RPC enabled: `"rpc": {"enabled": true, "port": 8278}`

### Spread Rejection Issues

**Symptom:** `Risk rejected: Spread X exceeds limit Y`

**Solutions:**
1. Increase spread limits in config.json:
   ```json
   "risk": {
     "max_spread_points": 5000,
     "max_spread_pct": 0.05
   }
   ```
2. Verify config_schema.py includes these fields

### MT5 Connection Issues

**Symptom:** Orders show as executed but MT5 terminal shows no trades

**Solutions:**
1. Verify MT5 is logged into correct account (demo ****0069)
2. Check for stuck MT5 instances: `Get-Process terminal64`
3. Restart MT5 and Cthulu
4. Check dry_run mode is disabled in config

---

## Documentation Hierarchy

```
SYSTEM_REPORT.md          <- Source of truth, final findings
    │
    ├── monitoring_report.md      <- Analysis, insights, recommendations
    │       │
    │       ├── observability_guide.md   <- How-to (this file)
    │       │
    │       └── signal_checklist.md      <- Test matrix
    │
    └── metrics.csv               <- Raw time-series data
```

---

## Key Commands Reference

```powershell
# Start Cthulu
python -m cthulu --config config.json --mindset ultra_aggressive --skip-setup

# View live logs
Get-Content -Path logs\cthulu.log -Tail 50 -Wait

# Check Prometheus metrics
Invoke-RestMethod http://127.0.0.1:8181/metrics

# Manual RPC trade
$body = '{"symbol":"BTCUSD#","side":"BUY","volume":0.01}'
Invoke-RestMethod -Uri "http://127.0.0.1:8278/trade" -Method POST -Body $body -ContentType "application/json"

# Run indicator tests
python monitoring\indicator_stress_test.py

# View injection logs
Get-Content -Path logs\inject.log -Tail 50 -Wait

# Full stress test
.\monitoring\run_stress.ps1 -DurationMinutes 120
```

---

## Success Criteria

**Target: 120 minutes with 0 fatal errors**

| Checkpoint | Time | Requirements |
|------------|------|--------------|
| T+15 min | First burst complete | >95% trades successful |
| T+30 min | All indicators validated | 100% indicator tests pass |
| T+60 min | Mid-point stability | No crashes, <5 risk rejections |
| T+90 min | Extended stability | MT5 connection maintained |
| T+120 min | **COMPLETE** | Overall grade ≥ B- |

---

## Next Steps After Successful Test

1. **Review SYSTEM_REPORT.md** for final grade and findings
2. **Analyze metrics.csv** for performance trends
3. **Consider live account deployment** if grade ≥ A-
4. **Fine-tune parameters** based on rejection patterns
5. **Document any manual interventions** in monitoring_report.md

---

*This guide should be updated after each major test session with lessons learned.*
