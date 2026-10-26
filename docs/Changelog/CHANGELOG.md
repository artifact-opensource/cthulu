---
title: CHANGELOG
description: Project release notes and version history (canonical)
tags: [changelog, releases]
sidebar_position: 13
slug: /docs/changelog
---

```
_________   __  .__          .__         
\_   ___ \_/  |_|  |__  __ __|  |  __ __ 
/    \  \/\   __\  |  \|  |  \  | |  |  \
\     \____|  | |   Y  \  |  /  |_|  |  /
 \______  /|__| |___|  /____/|____/____/ 
        \/           \/                  
```

▸ [View releases on GitHub](https://github.com/amuzetnoM/Cthulu/releases)

![](https://img.shields.io/badge/Version-6.0.0_K9-4B0082?style=for-the-badge&labelColor=0D1117&logo=git&logoColor=white) 
![](https://img.shields.io/github/last-commit/amuzetnoM/cthulu?branch=main&style=for-the-badge&logo=github&labelColor=0D1117&color=6A00FF)

All notable changes are recorded here using [Keep a Changelog](https://keepachangelog.com/) conventions and [Semantic Versioning](https://semver.org/).

---

## [5.2.4] "NEXUS" — 2026-01-17

### ◆ Highlight

- **ML/RL Training Infrastructure** ▸ Complete machine learning pipeline with price prediction, tier optimization, reinforcement learning, and MLOps
- **Discord Integration** ▸ Automated alerts for trades, risk events, health monitoring, and signal quality across dedicated channels
- **Comprehensive Trade Collection** ▸ Robust non-blocking trade metrics collection for system trades, RPC trades, and adopted positions
- **Data Storage CLI** ▸ Database and output tracking utility integrated into existing CLI pattern

### ◇ Added

**Machine Learning & Reinforcement Learning:**
- `ML_RL/price_predictor.py` ▸ Softmax classifier for price direction prediction using historical data
- `ML_RL/tier_optimizer.py` ▸ Analyzes scaling outcomes and optimizes profit-taking tiers
- `ML_RL/reinforcement_learning.py` ▸ Hybrid Q-learning and PPO for adaptive position sizing
- `ML_RL/llm_analysis.py` ▸ Local LLM integration for market narrative generation
- `ML_RL/feature_pipeline.py` ▸ Robust feature engineering with technical indicators and market regime detection
- `ML_RL/mlops.py` ▸ Model versioning, drift detection, and automated retraining pipeline
- `ML_RL/train_models.py` ▸ Unified training orchestrator for all ML components
- `ML_RL/ML_ARCHITECTURE.md` ▸ Comprehensive architecture documentation with Mermaid diagrams
- `ML_RL/system_map.md` ▸ Exhaustive endpoint mapping for data collection

**Discord Notifications:**
- `integrations/discord_alerts.py` ▸ Rate-limited webhook integration with rich embeds
- Alerts channel ▸ Trade executions, risk alerts, system health, adoption events
- Health channel ▸ Session summaries, model performance, portfolio snapshots
- Signals channel ▸ Signal quality alerts, regime changes, milestone events
- Automatic startup/shutdown notifications with session statistics

**Trade Collection System:**
- `core/trade_collector.py` ▸ Centralized non-blocking trade metrics collection
- Background queue processing with configurable batch sizes
- System trade, RPC trade, and adopted trade differentiation
- Comprehensive metrics: PnL, duration, slippage, execution quality
- SQLite persistence with full audit trail

**Position Adoption:**
- `position/adoption.py` ▸ Enhanced adoption system for manual/external trades
- Dynamic SL/TP management for adopted positions
- Full integration with trade collection and Discord alerts

**Tools & CLI:**
- `tools/data_storage_cli.py` ▸ Database and output space tracking utility
- `tools/analyze_cthulu.py` ▸ Extended to cover ML/RL components

### ◇ Fixed

- Auto-tune runner import resolution for local LLM modules
- Trade metrics not recording properly for all trade types
- Summary system display issues during live trading loop
- Position adoption not fully operational for external trades

### ◇ Security

- Discord webhook URLs stored in `.env` (not committed)
- ML model files excluded from git tracking
- HuggingFace repository configured for model distribution

---

## [5.2.34] "PRECISION" — 2026-01-17

### ◆ Highlight

- **Strict Quality Gate** ▸ Only GOOD/PREMIUM entries execute; MARGINAL queued, POOR/REJECT blocked
- **Momentum Detection** ▸ Profit scaler detects strong momentum and defers scaling to let winners run
- **Centralized Position Sizing** ▸ Full audit trail with `PositionSizeDecision` dataclass
- **Recalibrated Profit Tiers** ▸ Scale at 1R/1.5R/2R instead of 0.5R/0.8R/1.2R

### ◇ Added

- Strict Entry Quality Gate (`core/trading_loop.py`)
  - Explicit `EntryQuality` enum checks (PREMIUM, GOOD, MARGINAL, POOR, REJECT)
  - REJECT/POOR entries blocked; MARGINAL queued for better price
  - Visual indicators in logs: ▣ ▢ ◐ ◉
- Momentum Detection in Profit Scaler (`position/profit_scaler.py`)
  - `_has_strong_momentum()` method checking recent price action
  - Consecutive move counting and acceleration detection
  - Deferred partial closes when momentum strong
- Centralized Position Sizing
  - `PositionSizeDecision` dataclass with full audit trail
  - `_calculate_final_position_size()` method consolidating all adjustments
- Performance-Based Sizing (configurable via `risk.performance_based_sizing`)
- New config options: `drawdown_halt_percent`, `strict_quality_gate`, `trend_weight`, `profit_scaling`

### ◇ Fixed

- `test_auto_tune_runner.py` ▸ Properly mocked `HistoricalDataManager`
- `test_symbol_matching.py` ▸ Updated for exact symbol match refactoring

### ◇ Security

- Config audit notes and optimization comments documented
- All changes traced to AUDIT_EXECUTION_LOOP.md and AUDIT_MAIN_LOOP.md

---

## [6.0.0] "EVOLUTION" — 2026-01-06

### ◆ Highlight

- **Web-based Backtesting UI** ▸ Complete interface for backtesting with local/backend execution
- **Local LLM Integration** ▸ llama-cpp (GGUF) support with deterministic fallback
- **Hektor Vector Studio** ▸ Vector database with semantic memory and MQL5 knowledge retrieval
- **Profit Scaler System** ▸ Intelligent partial profit-taking mechanism
- **207 commits** of intelligence amplification since v5.1.0

### ◇ Added

- Web UI with chart components for equity curves and asset visualization
- Local llama-cpp integration with GGUF model support
- Hektor Vector Studio with SQLite fallback and semantic memory
- Consolidated backtesting package with grid sweep system
- Auto-tune scheduler CLI with AI-assisted summarization
- Profit Scaler with minimum time-in-trade enforcement
- Singleton lock preventing multiple instances
- RPC security hardening (rate limiting, IP control, TLS, audit logging)
- GCP deployment scripts and VM auto-install
- Advisory and ghost mode for non-trading analysis

### ◇ Fixed

- ▣ Critical: Stop loss bug causing excessive losses for large accounts
- ▣ Critical: UNKNOWN symbol handling with MT5 fallback
- ▣ Critical: Singleton lock preventing multiple instances
- Database locking and UNIQUE constraint issues
- Cognition engine overly restrictive behavior

### ◇ Security

- Secrets scanner for exposed credentials
- Exception handling overhaul eliminating silent failures

---

## [5.1.0] "APEX" — 2025-12-31

### ◆ Highlight

- **RSI Reversal Strategy** ▸ Pure RSI-based trading without crossover requirements
- **Multi-Strategy Fallback** ▸ System tries up to 4 strategies per bar
- **SAFE Engine** ▸ Set And Forget autonomous trading capability
- **Adaptive Drawdown Manager** ▸ 7-state risk management with survival mode

### ◇ Added

- RSI Reversal Strategy (`strategy/rsi_reversal.py`)
- Multi-Strategy Fallback Mechanism (primary + top 3 alternatives)
- Mean Reversion Strategy in dynamic selection
- Database WAL Mode for concurrent access
- Adaptive Drawdown Manager with states: NORMAL → CAUTION → WARNING → DANGER → CRITICAL → SURVIVAL
- Survival Mode (micro sizing, 95% confidence, 5:1 R:R minimum)
- Negative Balance Protection system
- Prometheus metrics for trading, risk, and system health
- Flash Orders (opt-in) for sub-second micro-trends

### ◇ Fixed

- Signal generation gap when market ranges without crossovers
- Database lock contention under high-throughput trading
- Spread limits schema (added `max_spread_points`, `max_spread_pct`)
- Windows logging and console encoding issues

### ◇ Security

- Emergency Kill-Switch with automatic safe-recovery
- Complete audit logging for forensic analysis

---

## [5.0.0] — 2025-12-27

### ◆ Highlight

- **Major Architecture Upgrade** ▸ Modular core with separated concerns
- **Runtime Indicator Stability** ▸ Namespace, aliasing, and fallback calculations
- **Live-Run Improvements** ▸ Safety gate replaced with prominent warnings

### ◇ Added

- Runtime indicator namespacing with `runtime_` prefix
- Indicator fallback calculations for RSI/ATR
- Unit tests for alias/fallback behavior
- CI enhancements for Windows and coverage

### ◇ Fixed

- DataFrame join ValueError from overlapping columns
- Unicode encoding errors on Windows console
- PositionManager initialization handling

---

## [4.0.0] — 2025-12-25

### ◆ Highlight

- **Multi-Strategy Framework** ▸ Dynamic strategy selection with regime affinity
- **Next-Gen Indicators** ▸ ATR-based calculations across all strategies
- **GUI Dashboard** ▸ Desktop interface with MT5 integration

### ◇ Added

- Multi-strategy framework with 7 trading strategies
- Tkinter GUI dashboard for system monitoring
- Comprehensive validation tests
- Pydantic v2 compatibility

---

## [3.3.1] — 2025-12-20

### ◇ Added

- Advisory and ghost modes for non-blocking analysis
- News ingestion with importance mapping
- ML flag configuration handling tests

---

## [3.2.1] — 2025-12-17

### ◇ Added

- SL/TP verification with readback
- Aggressive retry loop for trade adoption
- Prometheus metrics for SL/TP failures

### ◇ Fixed

- Symbol normalization for matching
- SL/TP retry queue persistence

---

## [3.1.0] — 2025-12-07

### ◇ Added

- Trade adoption (`--adopt-only` flag)
- `Cthulu-trade` CLI
- Pydantic config validation
- Health and Prometheus metrics

---

## [3.0.0] — 2024-12-07

### ◆ Highlight

- **Production-Ready** ▸ ATR indicator suite, CI pipeline, robust testing

---

## [2.0.0] — 2024-12-06

### ◆ Highlight

- **Autonomous Trading Loop** ▸ Core indicators, position management, exit strategies

---

## [1.0.0] — 2024-11-15

### ◆ Highlight

- **Foundation Release** ▸ Core architecture, persistence, MT5 connector, strategy scaffolding

---

## Release Table

| Version | Date | Codename | Description |
|---------|------|----------|-------------|
| 5.2.4 | 2026-01-17 | NEXUS | ML/RL infrastructure, Discord integration, trade collection |
| 5.2.34 | 2026-01-17 | PRECISION | Execution quality, strict gates, momentum detection |
| 6.0.0 | 2026-01-06 | EVOLUTION | Web UI, LLM, Vector DB, Profit Scaler (207 commits) |
| 5.1.0 | 2025-12-31 | APEX | RSI Reversal, SAFE engine, adaptive drawdown |
| 5.0.0 | 2025-12-27 | — | Architecture upgrade, runtime stability |
| 4.0.0 | 2025-12-25 | — | Multi-strategy framework, GUI |
| 3.3.1 | 2025-12-20 | — | Advisory mode, news ingestion |
| 3.2.1 | 2025-12-17 | — | SL/TP reliability, retry queue |
| 3.1.0 | 2025-12-07 | — | Trade adoption, CLI |
| 3.0.0 | 2024-12-07 | — | Production-ready |
| 2.0.0 | 2024-12-06 | — | Autonomous loop |
| 1.0.0 | 2024-11-15 | — | Foundation |

---

## Technical Specifications

- **Python**: 3.10 - 3.13
- **Database**: SQLite with WAL mode
- **Dependencies**: MetaTrader5, pandas, numpy, torch, scikit-learn
- **Testing**: pytest with fixtures and harnesses
- **Logging**: Structured JSON logging

## Data Pipeline

```
Signal → OrderRequest → ExecutionResult → TradeRecord
   ↓                                          ↓
RiskLimits                              PerformanceMetrics
```

---

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for development process and coding standards.

## License

AGPL 3.0 — See [LICENSE](../LICENSE)

---

> **Cthulu** ▸ *The future of algorithmic trading.*




