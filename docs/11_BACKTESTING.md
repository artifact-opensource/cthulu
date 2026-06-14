---
title: BACKTESTING FRAMEWORK
description: Professional-grade strategy validation with ML-enhanced decision making, ensemble testing, and institutional-grade benchmarking
tags: [backtesting, ml, optimization, benchmarking, monte-carlo]
sidebar_position: 11
version: 6.0.0
---



![](https://img.shields.io/badge/Version-6.0.0-4B0082?style=for-the-badge&labelColor=0D1117&logo=git&logoColor=white) 
![Last Update](https://img.shields.io/badge/Last_Update-2026--01--06-4B0082?style=for-the-badge&labelColor=0D1117&logo=calendar&logoColor=white)
![](https://img.shields.io/github/last-commit/amuzetnoM/cthulu?style=for-the-badge&labelColor=0D1117&logo=github&logoColor=white)

> Professional-grade strategy validation with ML-enhanced decision making, ensemble testing, and institutional-grade benchmarking.

---

## Overview

The Cthulu Backtesting Framework provides a complete environment for strategy validation, optimization, and performance analysis. Built for professional traders and quantitative analysts, it combines traditional backtesting methodologies with modern machine learning techniques for superior strategy development.

### Key Capabilities

| Category | Features |
|----------|----------|
| **Engine** | 5 speed modes, vectorized processing, 10,000+ bars/second |
| **Benchmarking** | 20+ metrics including Sharpe, Sortino, VaR, CVaR |
| **ML Integration** | Softmax/Argmax selection, price prediction, signal blending |
| **Optimization** | Walk-forward analysis, Monte Carlo simulation, grid search |
| **Reporting** | HTML, JSON, CSV exports with interactive charts |
| **Hektor Integration** | Semantic backtest storage, pattern recognition, AI optimization |
| **Web UI** | Real-time backtesting with WebSocket updates |
| **Auto-Optimization** | Bayesian optimization with historical pattern learning |

---

## Quick Start

### Basic Backtest

```python
from backtesting import BacktestEngine, BacktestConfig, HistoricalDataManager, SpeedMode
from strategy.ema_crossover import EMAcrossoverStrategy

# Load historical data
data_mgr = HistoricalDataManager()
data, metadata = data_mgr.fetch_data(
    symbol='EURUSD',
    start_date='2023-01-01',
    end_date='2024-01-01',
    timeframe='H1',
    source='MT5'
)

print(f"Loaded {metadata.num_bars} bars (quality: {metadata.data_quality_score:.2f})")

# Configure backtest
config = BacktestConfig(
    initial_capital=10000.0,
    commission=0.0001,           # 0.01%
    slippage_pct=0.0002,         # 0.02%
    speed_mode=SpeedMode.FAST,
    max_positions=3,
    position_size_pct=0.02       # 2% risk per trade
)

# Create and run
strategy = EMAcrossoverStrategy("ema_12_26", {
    'fast_period': 12,
    'slow_period': 26
})

engine = BacktestEngine(strategies=[strategy], config=config)
results = engine.run(data)
print(engine.get_results_summary())
```

---

## Speed Modes

The framework provides five execution modes optimized for different use cases:

| Mode | Speed | Use Case |
|------|-------|----------|
| **FAST** | 10,000+ bars/sec | Quick analysis, parameter sweeps |
| **NORMAL** | 1,000-5,000 bars/sec | Standard backtesting |
| **SLOW** | Configurable | Visual debugging, development |
| **REALTIME** | Historical speed | Time-sensitive logic testing |
| **HFT_TEST** | Maximum throughput | Tick-level strategies, scalping |

```python
# Fast mode for optimization
config = BacktestConfig(speed_mode=SpeedMode.FAST)

# Slow mode with 100ms delay per bar
config = BacktestConfig(speed_mode=SpeedMode.SLOW, speed_delay_ms=100)

# Realtime for validation
config = BacktestConfig(speed_mode=SpeedMode.REALTIME)
```

---

## Comprehensive Benchmarking

### Metrics Suite

The `BenchmarkSuite` calculates over 20 professional-grade metrics:

```python
from backtesting import BenchmarkSuite, ReportGenerator, ReportFormat

benchmark_suite = BenchmarkSuite(risk_free_rate=0.02)
metrics = benchmark_suite.calculate_metrics(
    equity_curve=results['equity_curve'],
    trades=results['trades'],
    initial_capital=config.initial_capital
)

# Risk-adjusted returns
print(f"Sharpe Ratio:     {metrics.sharpe_ratio:.2f}")
print(f"Sortino Ratio:    {metrics.sortino_ratio:.2f}")
print(f"Calmar Ratio:     {metrics.calmar_ratio:.2f}")
print(f"Omega Ratio:      {metrics.omega_ratio:.2f}")

# Drawdown analysis
print(f"Max Drawdown:     {metrics.max_drawdown_pct:.2f}%")
print(f"Recovery Factor:  {metrics.recovery_factor:.2f}")

# Risk metrics
print(f"VaR 95%:          {metrics.value_at_risk_95:.2%}")
print(f"CVaR 95%:         {metrics.conditional_var_95:.2%}")
```

### Available Metrics

**Return Metrics**
- Total Return, CAGR, Annualized Return
- Sharpe Ratio, Sortino Ratio, Calmar Ratio, Omega Ratio

**Drawdown Metrics**
- Maximum Drawdown (%), Maximum Drawdown Duration
- Recovery Factor, Ulcer Index, Pain Index

**Trade Statistics**
- Win Rate, Profit Factor, Expectancy
- Average Win/Loss, Largest Win/Loss
- Consecutive Wins/Losses

**Risk Metrics**
- Value at Risk (VaR) 95%, 99%
- Conditional VaR (CVaR) 95%, 99%
- Kurtosis, Skewness, Volatility

**Benchmark Comparison**
- Alpha, Beta, Correlation
- Tracking Error, Information Ratio

---

## Ensemble Testing

### Multi-Strategy Ensemble

Test multiple strategies simultaneously with intelligent weighting:

```python
from backtesting import EnsembleStrategy, EnsembleConfig, WeightingMethod
from strategy.ema_crossover import EMAcrossoverStrategy
from strategy.rsi_reversal import RSIReversalStrategy
from strategy.momentum_breakout import MomentumBreakoutStrategy

# Create strategy pool
strategies = [
    EMAcrossoverStrategy("ema_fast", {'fast_period': 8, 'slow_period': 21}),
    RSIReversalStrategy("rsi_14", {'rsi_period': 14, 'overbought': 70, 'oversold': 30}),
    MomentumBreakoutStrategy("momentum", {'lookback': 20, 'breakout_threshold': 1.5})
]

# Configure ensemble
ensemble_config = EnsembleConfig(
    weighting_method=WeightingMethod.ADAPTIVE,
    rebalance_period_bars=100,
    confidence_threshold=0.6,
    require_majority=True,
    vote_by_confidence=True
)

ensemble = EnsembleStrategy("adaptive_ensemble", strategies, ensemble_config)
engine = BacktestEngine(strategies=[ensemble], config=config)
results = engine.run(data)

# Analyze strategy contributions
stats = ensemble.get_strategy_stats()
for name, stat in stats.items():
    print(f"{name}: weight={stat['weight']:.2%}, win_rate={stat['win_rate']:.1%}")
```

### Weighting Methods

| Method | Description |
|--------|-------------|
| **EQUAL** | All strategies have equal weight |
| **PERFORMANCE** | Weight by recent cumulative returns |
| **SHARPE** | Weight by Sharpe ratio |
| **WIN_RATE** | Weight by win rate |
| **PROFIT_FACTOR** | Weight by profit factor |
| **ADAPTIVE** | Dynamic combination of multiple metrics |
| **INVERSE_VOLATILITY** | Weight by inverse volatility |

---

## ML-Enhanced Decision Making

### Softmax Signal Selection

Temperature-controlled probabilistic strategy selection balances exploration and exploitation:

```python
from backtesting import SoftmaxSelector, SelectionMethod

selector = SoftmaxSelector(
    temperature=0.5,       # Lower = more greedy
    min_probability=0.05   # Floor probability
)

# Multiple strategy signals
signals = [
    ("ema_crossover", signal1),
    ("rsi_reversal", signal2),
    ("momentum", signal3),
]

# Probabilistic selection
selected = selector.select_signal(signals, method=SelectionMethod.SOFTMAX)
print(f"Selected: {selected[0][0]} with probability {selected[0][2]:.2%}")

# Greedy selection
best = selector.select_signal(signals, method=SelectionMethod.ARGMAX)
print(f"Best: {best[0][0]} (confidence: {best[0][1].confidence:.2f})")

# Blend signals
blended = selector.blend_signals(signals)
print(f"Blended: {blended.side} (confidence: {blended.confidence:.2f})")
```

### Price Prediction

Multi-bar ahead forecasting with trainable classifier:

```python
from backtesting import PricePredictor

predictor = PricePredictor(
    lookback_bars=20,
    prediction_horizon=5,
    neutral_threshold=0.001  # 0.1% for neutral
)

# Optional training
training_metrics = predictor.train(
    data=historical_data,
    learning_rate=0.01,
    epochs=100
)
print(f"Training accuracy: {training_metrics['accuracy']:.2%}")

# Predict
prediction = predictor.predict(recent_data)
print(f"Direction: {prediction.direction}")
print(f"Probability: {prediction.probability:.2%}")
print(f"Expected move: {prediction.expected_move_pct:.2f}%")
```

### Argmax Strategy Selection

Epsilon-greedy selection with exploration:

```python
from backtesting import ArgmaxStrategySelector

selector = ArgmaxStrategySelector(
    lookback_trades=20,
    performance_metric='sharpe',
    exploration_rate=0.1  # 10% random exploration
)

# Track performance
selector.update_performance('ema_crossover', pnl=150.0)
selector.update_performance('rsi_reversal', pnl=-50.0)
selector.update_performance('momentum', pnl=200.0)

# Select with exploration
best = selector.select_strategy(['ema_crossover', 'rsi_reversal', 'momentum'])

# Get rankings
for name, score in selector.get_rankings():
    print(f"{name}: score={score:.3f}")
```

---

## Optimization

### Walk-Forward Analysis

Prevent overfitting with rolling in-sample/out-of-sample windows:

```python
from backtesting import WalkForwardOptimizer

param_grid = {
    'fast_period': [5, 8, 12, 21],
    'slow_period': [21, 34, 55, 89],
    'atr_multiplier': [1.5, 2.0, 2.5]
}

def run_backtest(data, strategy_class, params):
    strategy = strategy_class("optimized", params)
    engine = BacktestEngine(strategies=[strategy], config=config)
    results = engine.run(data)
    return results['metrics']

optimizer = WalkForwardOptimizer(
    in_sample_pct=0.7,
    num_windows=5,
    metric_to_optimize='sharpe_ratio'
)

opt_result = optimizer.optimize(
    data=data,
    strategy_class=EMAcrossoverStrategy,
    param_grid=param_grid,
    backtest_fn=run_backtest
)

print(f"Best parameters: {opt_result.best_params}")
print(f"In-sample Sharpe: {opt_result.in_sample_metrics.get('sharpe_ratio', 0):.2f}")
print(f"Out-of-sample: {opt_result.out_sample_metrics['score']:.2f}")
```

### Monte Carlo Simulation

Assess strategy robustness with randomized trade sequences:

```python
from backtesting import MonteCarloSimulator

simulator = MonteCarloSimulator(num_simulations=1000)
mc_results = simulator.simulate(
    trades=results['trades'],
    initial_capital=config.initial_capital
)

print(f"Probability of profit: {mc_results['probability_profit']:.1f}%")
print(f"Final equity mean: ${mc_results['final_equity']['mean']:,.2f}")
print(f"Final equity 5th pctl: ${mc_results['final_equity']['percentile_5']:,.2f}")
print(f"Final equity 95th pctl: ${mc_results['final_equity']['percentile_95']:,.2f}")
print(f"Max DD mean: {mc_results['max_drawdown']['mean']:.2f}%")
print(f"Max DD 95th pctl: {mc_results['max_drawdown']['percentile_95']:.2f}%")
```

---

## Data Sources

### MetaTrader 5

```python
data, metadata = data_mgr.fetch_data(
    symbol='EURUSD',
    start_date='2023-01-01',
    end_date='2024-01-01',
    timeframe='H1',
    source=DataSource.MT5
)
```

### CSV Files

Place files in `backtesting/cache/` with required columns:
- `time` (or `timestamp`, `date`, `datetime`)
- `open`, `high`, `low`, `close`, `volume`

```python
data, metadata = data_mgr.fetch_data(
    symbol='BTCUSD',
    start_date='2023-01-01',
    end_date='2024-01-01',
    timeframe='M15',
    source=DataSource.CSV
)
```

---

## Configuration Reference

```python
BacktestConfig(
    # Capital
    initial_capital=10000.0,
    
    # Costs
    commission=0.0001,              # 0.01%
    slippage_pct=0.0002,            # 0.02%
    use_bid_ask_spread=False,
    spread_pips=2.0,
    
    # Execution
    speed_mode=SpeedMode.FAST,
    speed_delay_ms=0,               # For SLOW mode
    
    # Position Management
    max_positions=3,
    position_size_pct=0.02,         # 2% risk
    enable_short_selling=True,
    
    # Risk Controls
    stop_on_margin_call=True,
    margin_call_level=0.20,         # 20%
    
    # Advanced
    track_intrabar_data=False,
)
```

---

## Report Generation

### HTML Report

```python
reporter = ReportGenerator()
reporter.generate(
    results=results,
    metrics=metrics,
    output_path='backtest_report.html',
    format=ReportFormat.HTML
)
```

### JSON Export

```python
reporter.generate(
    results=results,
    metrics=metrics,
    output_path='backtest_data.json',
    format=ReportFormat.JSON
)
```

### CSV Export

```python
reporter.generate(
    results=results,
    metrics=metrics,
    output_path='trades.csv',
    format=ReportFormat.CSV
)
```

---

## Best Practices

1. **Walk-Forward First**: Always use walk-forward optimization to prevent overfitting
2. **Monte Carlo Validation**: Run simulations to assess robustness across scenarios
3. **Multi-Asset Testing**: Test on multiple symbols and timeframes for generalization
4. **Realistic Costs**: Include commission, slippage, and spread for accurate results
5. **Ensemble Strategies**: Combine uncorrelated strategies for improved stability
6. **Multiple Metrics**: Monitor Sharpe, drawdown, win rate — not just returns
7. **Data Quality**: Check quality scores before trusting results
8. **Export Results**: Save for further analysis and comparison

---

## 🆕 Hektor-Powered Features

### Web-Based Backtesting UI

Start the Flask server for web-based backtesting with real-time updates:

```bash
# Start UI server
python backtesting/ui_server.py

# Server runs on http://127.0.0.1:5000
# Access REST API or connect Angular frontend
```

**REST API Endpoints**:
- `POST /api/backtest/run` - Start backtest
- `GET /api/backtest/status/{id}` - Get status
- `GET /api/backtest/results/{id}` - Get results
- `GET /api/configs` - List saved configurations
- `POST /api/configs` - Save configuration
- `POST /api/optimize` - Run optimization

**WebSocket Events**:
- `progress` - Real-time progress updates
- `complete` - Backtest completion
- `error` - Error notifications

### Semantic Backtest Storage

Store and search backtest results using Hektor vector database:

```python
from backtesting.hektor_backtest import HektorBacktest
from integrations.vector_studio import VectorStudioAdapter, VectorStudioConfig

# Initialize Hektor
vector_config = VectorStudioConfig(enabled=True)
adapter = VectorStudioAdapter(vector_config)
adapter.connect()

hektor_bt = HektorBacktest(adapter)

# Store backtest result
hektor_bt.store_backtest_result(config, results)

# Find similar configurations
similar = hektor_bt.find_similar_backtests(config, k=10)

# Get best performing configurations
best = hektor_bt.get_best_configurations(metric='sharpe_ratio', k=10)

# Compare live vs backtest
comparison = hektor_bt.compare_live_vs_backtest(live_performance)
```

### AI-Powered Optimization

Automated configuration discovery using Bayesian optimization and historical patterns:

```python
from backtesting.auto_optimizer import AutoOptimizer

optimizer = AutoOptimizer(hektor_backtest)

# Grid search with Hektor pruning (10x faster!)
param_grid = {
    'risk.position_size_pct': [1, 2, 5, 10],
    'strategy.ema_fast': [5, 10, 12],
    'strategy.ema_slow': [20, 26, 30]
}

results = optimizer.optimize_grid_search(
    data=market_data,
    param_grid=param_grid,
    base_config=config,
    objective='sharpe_ratio'
)

# Bayesian optimization using historical patterns
param_bounds = {
    'risk.position_size_pct': (1.0, 15.0),
    'strategy.ema_fast': (5.0, 15.0),
    'strategy.ema_slow': (20.0, 50.0)
}

results = optimizer.optimize_bayesian(
    data=market_data,
    param_bounds=param_bounds,
    base_config=config,
    n_iterations=50
)

# Multi-objective optimization
results = optimizer.optimize_multi_objective(
    data=market_data,
    param_grid=param_grid,
    base_config=config,
    objectives=['sharpe_ratio', 'max_drawdown', 'win_rate']
)

print(f"Best configuration: {results[0].config}")
print(f"Sharpe: {results[0].metrics['sharpe_ratio']:.2f}")
```

### Production Backtest Runner

Command-line interface for automated backtesting:

```bash
# Single backtest
python scripts/run_backtest_suite.py \
  --data data/EURUSD_M15.csv \
  --config config.json \
  --mode single

# Optimization
python scripts/run_backtest_suite.py \
  --data data/EURUSD_M15.csv \
  --config config.json \
  --mode optimize

# Configuration comparison
python scripts/run_backtest_suite.py \
  --data data/EURUSD_M15.csv \
  --config config.json \
  --mode compare

# Disable Hektor (use standalone mode)
python scripts/run_backtest_suite.py \
  --data data/EURUSD_M15.csv \
  --config config.json \
  --mode optimize \
  --no-hektor
```

### Pattern Recognition in Backtesting

Analyze chart patterns during backtesting:

```python
from cognition.pattern_recognition import PatternRecognizer

recognizer = PatternRecognizer(vector_adapter, retriever)

# Detect patterns in backtest data
patterns = recognizer.detect_patterns(data, lookback_bars=50)

# Analyze pattern performance
for pattern in patterns:
    analysis = recognizer.analyze_pattern(pattern, data, symbol)
    print(f"{pattern}: {analysis.win_rate:.1%} win rate")
    print(f"Recommendation: {analysis.recommendation}")

# Adjust backtest confidence based on patterns
adjusted_confidence = recognizer.get_pattern_confidence_adjustment(
    detected_patterns=patterns,
    current_data=data,
    symbol=symbol,
    base_confidence=0.7
)
```

### ML Training Data Export

Export backtest results for machine learning:

```python
from integrations.ml_exporter import MLDataExporter

exporter = MLDataExporter(vector_adapter, output_dir="./training_data")

# Export training data
files = exporter.export_training_data(
    start_date=datetime(2025, 1, 1),
    end_date=datetime(2026, 1, 1),
    symbols=["EURUSD", "GBPUSD"],
    test_split=0.2
)

# Export successful patterns
exporter.export_successful_patterns(
    min_win_rate=0.6,
    min_samples=10
)
```

### Performance Analytics

Analyze backtest performance semantically:

```python
from integrations.performance_analyzer import PerformanceAnalyzer

analyzer = PerformanceAnalyzer(vector_adapter, retriever)

# Generate comprehensive report
report = analyzer.generate_performance_report("EURUSD", lookback_days=90)

# Find optimal conditions
optimal = analyzer.find_optimal_conditions(
    symbol="EURUSD",
    min_win_rate=0.6,
    min_samples=10
)

# Analyze regime performance
regime_insights = analyzer.analyze_regime_performance("EURUSD")

# Time-of-day analysis
time_insights = analyzer.analyze_time_of_day_performance("EURUSD")
```

---

## Directory Structure

```
backtesting/
├── __init__.py              # Module exports
├── engine.py                # Core backtest engine
├── data_manager.py          # Historical data management
├── ensemble.py              # Ensemble strategy logic
├── benchmarks.py            # Performance metrics
├── reporter.py              # Report generation
├── optimizer.py             # Optimization tools
├── 🆕 ui_server.py          # Flask server for web UI
├── 🆕 hektor_backtest.py    # Hektor-enhanced backtesting
├── 🆕 auto_optimizer.py     # AI-powered optimization
├── cache/                   # Cached historical data
├── reports/                 # Generated reports
├── examples/                # Example scripts
└── ui/                      # 🆕 Angular web interface
    ├── index.html
    ├── src/
    └── README.md
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Backtest too slow | Use `SpeedMode.FAST`, reduce data, optimize strategy |
| Results don't match live | Increase slippage/commission, use `REALTIME` mode |
| Low data quality score | Check source, use different timeframe, fill gaps |
| Ensemble not improving | Ensure strategy decorrelation, adjust weighting |

---

## Related Documentation

- [Features Guide](FEATURES_GUIDE.md) - Complete feature reference
- [Strategies](STRATEGIES.md) - Available trading strategies
- [Indicators](INDICATORS.md) - Technical indicator reference
- [Risk Management](RISK_MANAGEMENT.md) - Risk controls and limits

---

*Cthulu Backtesting Framework v6.0.0 - Professional-grade strategy validation.*
