# Backtesting Framework

 ![Version](https://img.shields.io/badge/Version-6.0.0-4B0082?style=for-the-badge&labelColor=0D1117&logo=git&logoColor=white) 
 ![Last Update](https://img.shields.io/badge/Last_Update-2026--01--06-4B0082?style=for-the-badge&labelColor=0D1117&logo=calendar&logoColor=white) 
 ![Last Commit](https://img.shields.io/github/last-commit/amuzetnoM/cthulu?branch=main&style=for-the-badge&logo=github&labelColor=0D1117&color=6A00FF)

> Comprehensive backtesting framework for Cthulu trading strategies with ML-enhanced decision making, ensemble testing, and institutional-grade benchmarking.

---

## Overview

The Cthulu Backtesting Framework provides a complete environment for strategy validation, optimization, and performance analysis. Built for professional traders and quantitative analysts, it combines traditional backtesting with modern machine learning techniques.

---

## Features

### Performance Engine
- **Adjustable Speed Modes**: Fast vectorized, normal bar-by-bar, slow replay, realtime simulation, and HFT testing
- **Efficient Data Management**: Smart caching, quality checks, multiple data sources (MT5, CSV)
- **Scalable Architecture**: Process 10,000+ bars per second in FAST mode

### Comprehensive Benchmarking
- **Risk-Adjusted Returns**: Sharpe, Sortino, Calmar, Omega ratios
- **Drawdown Analysis**: Max drawdown, duration, recovery factor, Ulcer Index
- **Trade Statistics**: Win rate, profit factor, expectancy, consecutive streaks
- **Advanced Metrics**: VaR, CVaR, kurtosis, skewness
- **Benchmark Comparison**: Alpha, beta, correlation, tracking error

### Ensemble Testing
- **Multi-Strategy Testing**: Run multiple strategies simultaneously
- **Dynamic Weighting**: Performance-based, Sharpe-based, adaptive, or equal weighting
- **Auto-Rebalancing**: Periodic weight adjustment based on recent performance
- **Signal Aggregation**: Confidence-weighted voting with customizable rules

### ML-Enhanced Decision Making
- **Softmax Signal Selection**: Temperature-controlled probabilistic strategy selection
- **Argmax Strategy Selection**: Epsilon-greedy best-strategy selection with exploration
- **Price Prediction**: Multi-bar ahead forecasting with trainable softmax classifier
- **Signal Blending**: ML-weighted signal combination for improved accuracy

### Optimization Tools
- **Walk-Forward Analysis**: Prevent overfitting with in-sample/out-of-sample validation
- **Monte Carlo Simulation**: Robustness testing with confidence intervals
- **Parameter Grid Search**: Systematic parameter optimization

### Reporting
- **HTML Reports**: Interactive visualizations with charts and tables
- **Text Reports**: Console-friendly summaries
- **JSON/CSV Export**: Programmatic access and spreadsheet analysis

### Web Dashboard (Prototype) 🔧

A small static web dashboard prototype is provided under `backtesting/report_ui/` which reads centralized reports from `backtesting/reports/`.

- Generate reports with `ReportGenerator.generate(...)` — files will be written into `backtesting/reports/` and an `index.json` manifest will be updated automatically.
- Serve the UI locally with:
  - `python backtesting/report_ui/serve.py`
  - Open `http://localhost:8000/backtesting/report_ui/static/index.html` to view reports (HTML inline, JSON visualized, text/CSV previewable).

This viewer is intentionally lightweight and dependency-free for local workflows.

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

print(f"Loaded {metadata.num_bars} bars (quality score: {metadata.data_quality_score:.2f})")

# Configure backtest
config = BacktestConfig(
    initial_capital=10000.0,
    commission=0.0001,           # 0.01%
    slippage_pct=0.0002,         # 0.02%
    speed_mode=SpeedMode.FAST,   # FAST, NORMAL, SLOW, REALTIME, HFT_TEST
    max_positions=3,
    position_size_pct=0.02       # 2% risk per trade
)

# Create strategy
strategy = EMAcrossoverStrategy("ema_12_26", {
    'fast_period': 12,
    'slow_period': 26
})

# Run backtest
engine = BacktestEngine(strategies=[strategy], config=config)
results = engine.run(data)

# Print summary
print(engine.get_results_summary())
```

### Ensemble Backtest

```python
from backtesting import EnsembleStrategy, EnsembleConfig, WeightingMethod
from strategy.ema_crossover import EMAcrossoverStrategy
from strategy.rsi_reversal import RSIReversalStrategy
from strategy.momentum_breakout import MomentumBreakoutStrategy

# Create multiple strategies
strategies = [
    EMAcrossoverStrategy("ema_fast", {'fast_period': 8, 'slow_period': 21}),
    RSIReversalStrategy("rsi_14", {'rsi_period': 14, 'overbought': 70, 'oversold': 30}),
    MomentumBreakoutStrategy("momentum", {'lookback': 20, 'breakout_threshold': 1.5})
]

# Configure ensemble
ensemble_config = EnsembleConfig(
    weighting_method=WeightingMethod.ADAPTIVE,   # EQUAL, PERFORMANCE, SHARPE, ADAPTIVE
    rebalance_period_bars=100,
    confidence_threshold=0.6,
    require_majority=True,
    vote_by_confidence=True
)

# Create ensemble
ensemble = EnsembleStrategy("adaptive_ensemble", strategies, ensemble_config)

# Run backtest
engine = BacktestEngine(strategies=[ensemble], config=config)
results = engine.run(data)

# Check strategy weights
stats = ensemble.get_strategy_stats()
for name, stat in stats.items():
    print(f"{name}: weight={stat['weight']:.2%}, win_rate={stat['win_rate']:.1%}")
```

### Comprehensive Benchmarking

```python
from backtesting import BenchmarkSuite, ReportGenerator, ReportFormat

# Calculate comprehensive metrics
benchmark_suite = BenchmarkSuite(risk_free_rate=0.02)
metrics = benchmark_suite.calculate_metrics(
    equity_curve=results['equity_curve'],
    trades=results['trades'],
    initial_capital=config.initial_capital
)

# Print key metrics
print(f"Sharpe Ratio:     {metrics.sharpe_ratio:.2f}")
print(f"Sortino Ratio:    {metrics.sortino_ratio:.2f}")
print(f"Calmar Ratio:     {metrics.calmar_ratio:.2f}")
print(f"Omega Ratio:      {metrics.omega_ratio:.2f}")
print(f"Max Drawdown:     {metrics.max_drawdown_pct:.2f}%")
print(f"Recovery Factor:  {metrics.recovery_factor:.2f}")
print(f"Expectancy:       ${metrics.expectancy:.2f}")
print(f"VaR 95%:          {metrics.value_at_risk_95:.2%}")
print(f"CVaR 95%:         {metrics.conditional_var_95:.2%}")

# Generate HTML report
reporter = ReportGenerator()
reporter.generate(
    results=results,
    metrics=metrics,
    output_path='backtest_report.html',
    format=ReportFormat.HTML
)
```

### Walk-Forward Optimization

```python
from backtesting import WalkForwardOptimizer

# Define parameter grid
param_grid = {
    'fast_period': [5, 8, 12, 21],
    'slow_period': [21, 34, 55, 89],
    'atr_multiplier': [1.5, 2.0, 2.5]
}

# Define backtest function
def run_backtest(data, strategy_class, params):
    strategy = strategy_class("optimized", params)
    engine = BacktestEngine(strategies=[strategy], config=config)
    results = engine.run(data)
    return results['metrics']

# Run optimization
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
print(f"Out-of-sample score: {opt_result.out_sample_metrics['score']:.2f}")
```

### Monte Carlo Simulation

```python
from backtesting import MonteCarloSimulator

# Run Monte Carlo simulation
simulator = MonteCarloSimulator(num_simulations=1000)
mc_results = simulator.simulate(
    trades=results['trades'],
    initial_capital=config.initial_capital
)

print(f"Probability of profit: {mc_results['probability_profit']:.1f}%")
print(f"Final equity mean: ${mc_results['final_equity']['mean']:,.2f}")
print(f"Final equity 5th percentile: ${mc_results['final_equity']['percentile_5']:,.2f}")
print(f"Final equity 95th percentile: ${mc_results['final_equity']['percentile_95']:,.2f}")
print(f"Max DD mean: {mc_results['max_drawdown']['mean']:.2f}%")
print(f"Max DD 95th percentile: {mc_results['max_drawdown']['percentile_95']:.2f}%")
```

### ML-Enhanced Signal Selection

```python
from backtesting import SoftmaxSelector, SelectionMethod, PricePredictor

# Softmax-based signal selection
selector = SoftmaxSelector(
    temperature=0.5,       # Lower = more greedy selection
    min_probability=0.05   # Floor probability for any strategy
)

# Given multiple strategy signals
signals = [
    ("ema_crossover", signal1),
    ("rsi_reversal", signal2),
    ("momentum", signal3),
]

# Probabilistic selection (exploration/exploitation balance)
selected = selector.select_signal(signals, method=SelectionMethod.SOFTMAX)
print(f"Selected: {selected[0][0]} with probability {selected[0][2]:.2%}")

# Argmax selection (greedy - best signal only)
best = selector.select_signal(signals, method=SelectionMethod.ARGMAX)
print(f"Best signal: {best[0][0]} (confidence: {best[0][1].confidence:.2f})")

# Blend multiple signals into one
blended_signal = selector.blend_signals(signals)
print(f"Blended: {blended_signal.side} (confidence: {blended_signal.confidence:.2f})")
```

### Price Prediction with ML

```python
from backtesting import PricePredictor

# Create predictor for 5-bar ahead forecasting
predictor = PricePredictor(
    lookback_bars=20,
    prediction_horizon=5,
    neutral_threshold=0.001  # 0.1% for neutral classification
)

# Train on historical data (optional - uses heuristics by default)
training_metrics = predictor.train(
    data=historical_data,
    learning_rate=0.01,
    epochs=100
)
print(f"Training accuracy: {training_metrics['accuracy']:.2%}")

# Make predictions
prediction = predictor.predict(recent_data)
print(f"Direction: {prediction.direction}")
print(f"Probability: {prediction.probability:.2%}")
print(f"Expected move: {prediction.expected_move_pct:.2f}%")
print(f"Horizon: {prediction.horizon_bars} bars")
```

### Argmax Strategy Selector with Exploration

```python
from backtesting import ArgmaxStrategySelector

# Epsilon-greedy strategy selection
selector = ArgmaxStrategySelector(
    lookback_trades=20,
    performance_metric='sharpe',  # 'sharpe', 'profit_factor', 'win_rate'
    exploration_rate=0.1          # 10% random exploration
)

# Track strategy performance over time
selector.update_performance('ema_crossover', pnl=150.0)
selector.update_performance('rsi_reversal', pnl=-50.0)
selector.update_performance('momentum', pnl=200.0)

# Select best strategy (with occasional exploration)
best = selector.select_strategy(['ema_crossover', 'rsi_reversal', 'momentum'])
print(f"Selected: {best}")

# Get rankings
rankings = selector.get_rankings()
for name, score in rankings:
    print(f"{name}: score={score:.3f}")
```

## Speed Modes

### FAST
- Vectorized processing (when possible)
- Processes data as quickly as CPU allows
- Best for: Quick analysis, parameter sweeps
- Speed: 10,000+ bars/second

### NORMAL
- Bar-by-bar processing
- No artificial delays
- Best for: Standard backtesting
- Speed: 1,000-5,000 bars/second

### SLOW
- Bar-by-bar with configurable delays
- Useful for: Visual debugging, strategy development
- Speed: Configurable (e.g., 100ms per bar)

### REALTIME
- Replays at historical speed
- Respects actual time between bars
- Best for: Testing time-sensitive logic
- Speed: Matches historical timeframe

### HFT_TEST
- Ultra-fast for high-frequency testing
- Minimal overhead
- Best for: Tick-level strategies, scalping validation
- Speed: Maximum throughput

## Data Sources

### MT5 (MetaTrader 5)
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
Place CSV files in `backtesting/cache/` with format:
- Required columns: `time`, `open`, `high`, `low`, `close`, `volume`
- Time column can be: `time`, `timestamp`, `date`, or `datetime`

```python
data, metadata = data_mgr.fetch_data(
    symbol='BTCUSD',
    start_date='2023-01-01',
    end_date='2024-01-01',
    timeframe='M15',
    source=DataSource.CSV
)
```

## Ensemble Weighting Methods

- **EQUAL**: All strategies have equal weight
- **PERFORMANCE**: Weight by recent cumulative returns
- **SHARPE**: Weight by Sharpe ratio
- **WIN_RATE**: Weight by win rate
- **PROFIT_FACTOR**: Weight by profit factor  
- **ADAPTIVE**: Dynamic combination of multiple metrics
- **INVERSE_VOLATILITY**: Weight by inverse volatility

## Configuration Options

```python
BacktestConfig(
    initial_capital=10000.0,          # Starting capital
    commission=0.0001,                # Commission per trade (0.01%)
    slippage_pct=0.0002,              # Slippage (0.02%)
    speed_mode=SpeedMode.FAST,        # Execution speed
    speed_delay_ms=0,                 # Delay between bars (SLOW mode)
    use_bid_ask_spread=False,         # Simulate bid/ask spread
    spread_pips=2.0,                  # Spread in pips
    max_positions=3,                  # Max concurrent positions
    position_size_pct=0.02,           # Position size (2% risk)
    stop_on_margin_call=True,         # Stop on margin call
    margin_call_level=0.20,           # Margin call threshold (20%)
    enable_short_selling=True,        # Allow short positions
    track_intrabar_data=False,        # Track high/low within bars
)
```

## Best Practices

1. **Always use walk-forward optimization** to prevent overfitting
2. **Run Monte Carlo simulations** to assess robustness
3. **Test on multiple symbols and timeframes** for generalization
4. **Include realistic commission and slippage** for accurate results
5. **Use ensemble strategies** for improved robustness
6. **Monitor multiple metrics**, not just returns
7. **Check data quality scores** before trusting results
8. **Export results** for further analysis in spreadsheets

## Advanced Usage

See `/backtesting/examples/` for more examples:
- `advanced_ensemble.py` - Complex ensemble configurations
- `parameter_optimization.py` - Systematic parameter search
- `multi_symbol_backtest.py` - Portfolio-level backtesting
- `custom_metrics.py` - Adding custom performance metrics

## Directory Structure

```
backtesting/
├── __init__.py              # Module exports
├── engine.py                # Core backtest engine
├── data_manager.py          # Historical data management
├── ensemble.py              # Ensemble strategy logic
├── benchmarks.py            # Performance metrics calculation
├── reporter.py              # Report generation
├── optimizer.py             # Optimization tools
├── cache/                   # Cached historical data
├── reports/                 # Generated reports
└── examples/                # Example scripts
```

## Requirements

- Python 3.10+
- pandas
- numpy
- MetaTrader5 (for MT5 data source)
- matplotlib (optional, for plotting)

## Performance Tips

1. Use `SpeedMode.FAST` for initial testing
2. Enable data caching with `use_cache=True`
3. Limit `lookback_bars` to minimum needed
4. Use CSV files for repeated tests (faster than MT5 API)
5. Profile slow strategies with `cProfile`

## Troubleshooting

**Issue**: Backtest too slow  
**Solution**: Use `SpeedMode.FAST`, reduce data size, optimize strategy code

**Issue**: Results don't match live trading  
**Solution**: Increase slippage/commission, use `REALTIME` mode, test with bid/ask spreads

**Issue**: Data quality score low  
**Solution**: Check source data, use different timeframe, fill gaps manually

**Issue**: Ensemble not improving performance  
**Solution**: Ensure strategies are uncorrelated, adjust weighting method, increase rebalance period

## Support

- **Documentation**: See `/docs/BACKTESTING.md` for comprehensive guide
- **Examples**: Review scripts in `/backtesting/examples/`
- **Logs**: Check `backtesting/backtesting.log` for execution details

---

*Cthulu Backtesting Framework v6.0.0 - Professional-grade strategy validation.*
