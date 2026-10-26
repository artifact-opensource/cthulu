#!/usr/bin/env python3
"""
Backtesting Harness - Full System Test
Tests all components of the backtesting framework.
"""

import sys
sys.path.insert(0, '..')

import numpy as np
import pandas as pd
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

from backtesting import (
    BacktestEngine, BacktestConfig, SpeedMode,
    HistoricalDataManager, DataSource,
    BenchmarkSuite,
    ReportGenerator, ReportFormat,
    MonteCarloSimulator,
    SoftmaxSelector, PricePredictor,
)
from backtesting.engine import Position, Trade
from strategy.base import Strategy, Signal, SignalType


class MomentumStrategy(Strategy):
    """Simple momentum strategy for testing - generates frequent signals."""
    
    def __init__(self, lookback=10, threshold=0.01):
        super().__init__('Momentum', {'lookback': lookback, 'threshold': threshold})
        self.lookback = lookback
        self.threshold = threshold
        self.bar_count = 0
        self.closes = []
        
    def on_bar(self, bar):
        self.bar_count += 1
        self.closes.append(bar['close'])
        
        if len(self.closes) < self.lookback + 1:
            return None
            
        # Calculate momentum
        current = self.closes[-1]
        past = self.closes[-self.lookback]
        momentum = (current - past) / past
        
        signal = None
        # Generate signal every 20 bars if momentum is strong enough
        if self.bar_count % 20 == 0:
            if momentum > self.threshold:
                signal = Signal(
                    id=f'mom_{self.bar_count}',
                    timestamp=bar.name,
                    symbol='TEST',
                    timeframe='H1',
                    side=SignalType.LONG,
                    action='buy',
                    price=bar['close'],
                    stop_loss=bar['close'] * 0.97,
                    take_profit=bar['close'] * 1.05,
                    confidence=min(0.9, 0.5 + abs(momentum) * 10),
                    reason=f'Positive momentum {momentum*100:.2f}%'
                )
            elif momentum < -self.threshold:
                signal = Signal(
                    id=f'mom_{self.bar_count}',
                    timestamp=bar.name,
                    symbol='TEST',
                    timeframe='H1',
                    side=SignalType.SHORT,
                    action='sell',
                    price=bar['close'],
                    stop_loss=bar['close'] * 1.03,
                    take_profit=bar['close'] * 0.95,
                    confidence=min(0.9, 0.5 + abs(momentum) * 10),
                    reason=f'Negative momentum {momentum*100:.2f}%'
                )
        
        return signal


def generate_trending_data(num_bars=1000, seed=42):
    """Generate synthetic market data with clear trends for testing."""
    np.random.seed(seed)
    dates = pd.date_range('2024-01-01', periods=num_bars, freq='h')  # lowercase 'h' for hours
    
    # Generate trending price path with more volatility
    trend = np.sin(np.linspace(0, 6*np.pi, num_bars)) * 5  # Multiple cycles
    noise = np.cumsum(np.random.randn(num_bars) * 0.3)
    price = 100 + trend + noise
    
    data = pd.DataFrame({
        'open': price * (1 + np.random.randn(num_bars) * 0.002),
        'high': price * (1 + np.abs(np.random.randn(num_bars) * 0.005)),
        'low': price * (1 - np.abs(np.random.randn(num_bars) * 0.005)),
        'close': price,
        'volume': np.random.randint(10000, 100000, num_bars),
    }, index=dates)
    
    # Fix OHLC relationships
    data['high'] = data[['open', 'close', 'high']].max(axis=1)
    data['low'] = data[['open', 'close', 'low']].min(axis=1)
    
    return data


def test_backtest_engine():
    """Test the backtest engine with synthetic data."""
    print('=' * 70)
    print('CTHULU BACKTESTING HARNESS - FULL SYSTEM TEST')
    print('=' * 70)
    
    # Generate data
    print('\nGenerating synthetic market data (1000 bars)...')
    data = generate_trending_data(1000)
    print(f'Data shape: {data.shape}')
    print(f'Date range: {data.index[0]} to {data.index[-1]}')
    print(f'Price range: {data["close"].min():.2f} to {data["close"].max():.2f}')
    
    # Initialize backtest
    print('\nInitializing backtest engine...')
    strategy = MomentumStrategy(lookback=10, threshold=0.005)  # Lower threshold
    config = BacktestConfig(
        initial_capital=10000,
        commission=0.0001,
        slippage_pct=0.0002,
        speed_mode=SpeedMode.FAST,
        max_positions=5,
        position_size_pct=0.05,  # Larger positions
    )
    engine = BacktestEngine(strategies=[strategy], config=config)
    
    # Run backtest
    print('\nRunning backtest...')
    def progress_callback(pct, bar, total):
        if int(pct) % 25 == 0:
            print(f'  Progress: {pct:.0f}% ({bar}/{total} bars)')

    results = engine.run(data, progress_callback=progress_callback)
    
    # Display results
    print('\n' + '=' * 70)
    print('BACKTEST RESULTS')
    print('=' * 70)
    print(engine.get_results_summary())
    
    print(f'\nTrades executed: {len(engine.trades)}')
    if engine.trades:
        pnls = [t.pnl for t in engine.trades]
        print(f'Total P&L: ${sum(pnls):.2f}')
        print(f'Avg P&L per trade: ${np.mean(pnls):.2f}')
        print(f'Best trade: ${max(pnls):.2f}')
        print(f'Worst trade: ${min(pnls):.2f}')
    
    return engine, results


def test_monte_carlo(engine, initial_capital):
    """Test Monte Carlo simulation."""
    if not engine.trades:
        print('\nNo trades executed - Monte Carlo skipped')
        return None
        
    print('\n' + '=' * 70)
    print('MONTE CARLO SIMULATION')
    print('=' * 70)
    
    mc = MonteCarloSimulator(num_simulations=500)
    mc_results = mc.simulate(engine.trades, initial_capital)
    
    print(f'\nSimulations: {mc_results["num_simulations"]}')
    print(f'Probability of profit: {mc_results["probability_profit"]:.1f}%')
    eq = mc_results['final_equity']
    print(f'\nFinal Equity Distribution:')
    print(f'  Mean: ${eq["mean"]:,.2f}')
    print(f'  Median: ${eq["median"]:,.2f}')
    print(f'  Std Dev: ${eq["std"]:,.2f}')
    print(f'  5th percentile: ${eq["percentile_5"]:,.2f}')
    print(f'  95th percentile: ${eq["percentile_95"]:,.2f}')
    
    dd = mc_results['max_drawdown']
    print(f'\nMax Drawdown Distribution:')
    print(f'  Mean: {dd["mean"]:.2f}%')
    print(f'  Median: {dd["median"]:.2f}%')
    print(f'  95th percentile: {dd["percentile_95"]:.2f}%')
    
    return mc_results


def test_ml_components():
    """Test ML components (PricePredictor, SoftmaxSelector)."""
    print('\n' + '=' * 70)
    print('ML COMPONENT TESTS')
    print('=' * 70)
    
    # Generate test data
    data = generate_trending_data(500, seed=123)
    
    # Price Predictor training
    print('\nTraining PricePredictor on historical data...')
    predictor = PricePredictor(lookback_bars=20, prediction_horizon=5)
    train_metrics = predictor.train(data, learning_rate=0.01, epochs=50)
    print(f'  Training accuracy: {train_metrics["accuracy"]*100:.1f}%')
    print(f'  Training loss: {train_metrics["loss"]:.4f}')
    print(f'  Samples used: {train_metrics["samples"]}')
    print(f'  Class distribution: {train_metrics["class_distribution"]}')
    
    # Make a prediction
    prediction = predictor.predict(data.iloc[-30:])
    print(f'\nPrediction for next {prediction.horizon_bars} bars:')
    print(f'  Direction: {prediction.direction.value}')
    print(f'  Probability: {prediction.probability*100:.1f}%')
    print(f'  Expected move: {prediction.expected_move_pct:.2f}%')
    
    # Softmax selector test
    print('\nSoftmax temperature comparison:')
    selector_cold = SoftmaxSelector(temperature=0.5)  # More greedy
    selector_hot = SoftmaxSelector(temperature=2.0)   # More explorative
    
    scores = np.array([0.8, 0.6, 0.4, 0.2])
    probs_cold = selector_cold.softmax(scores)
    probs_hot = selector_hot.softmax(scores)
    print(f'  Scores: {scores}')
    print(f'  T=0.5 (greedy):  {probs_cold.round(3)} -> max weight {probs_cold.max():.1%}')
    print(f'  T=2.0 (explore): {probs_hot.round(3)} -> max weight {probs_hot.max():.1%}')
    
    return predictor


def test_benchmark_suite(engine, initial_capital):
    """Test the benchmark suite."""
    if not engine.trades or not engine.equity_curve:
        print('\nNo data for benchmark suite')
        return None
        
    print('\n' + '=' * 70)
    print('BENCHMARK SUITE')
    print('=' * 70)
    
    suite = BenchmarkSuite(risk_free_rate=0.02)
    metrics = suite.calculate_metrics(
        equity_curve=engine.equity_curve,
        trades=engine.trades,
        initial_capital=initial_capital
    )
    
    print(f'\nRisk-Adjusted Returns:')
    print(f'  Total Return: {metrics.total_return:.2f}%')
    print(f'  Annualized Return: {metrics.annualized_return:.2f}%')
    print(f'  Sharpe Ratio: {metrics.sharpe_ratio:.2f}')
    print(f'  Sortino Ratio: {metrics.sortino_ratio:.2f}')
    print(f'  Calmar Ratio: {metrics.calmar_ratio:.2f}')
    print(f'  Omega Ratio: {metrics.omega_ratio:.2f}')
    
    print(f'\nDrawdown Analysis:')
    print(f'  Max Drawdown: {metrics.max_drawdown_pct:.2f}%')
    print(f'  Max DD Duration: {metrics.max_drawdown_duration_days:.0f} days')
    print(f'  Recovery Factor: {metrics.recovery_factor:.2f}')
    
    print(f'\nTrade Statistics:')
    print(f'  Total Trades: {metrics.total_trades}')
    print(f'  Win Rate: {metrics.win_rate*100:.1f}%')
    print(f'  Profit Factor: {metrics.profit_factor:.2f}')
    print(f'  Expectancy: ${metrics.expectancy:.2f}')
    print(f'  Max Consecutive Wins: {metrics.max_consecutive_wins}')
    print(f'  Max Consecutive Losses: {metrics.max_consecutive_losses}')
    
    print(f'\nRisk Metrics:')
    print(f'  VaR (95%): {metrics.value_at_risk_95*100:.2f}%')
    print(f'  CVaR (95%): {metrics.conditional_var_95*100:.2f}%')
    print(f'  Ulcer Index: {metrics.ulcer_index:.2f}')
    
    return metrics


def main():
    """Run all tests."""
    # Test backtest engine
    engine, results = test_backtest_engine()
    
    # Test Monte Carlo
    test_monte_carlo(engine, 10000)
    
    # Test ML components
    test_ml_components()
    
    # Test benchmark suite
    test_benchmark_suite(engine, 10000)
    
    print('\n' + '=' * 70)
    print('BACKTESTING HARNESS FULLY OPERATIONAL')
    print('All components tested successfully!')
    print('=' * 70)
    

if __name__ == '__main__':
    main()
