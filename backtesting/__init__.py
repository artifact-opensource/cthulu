"""
Backtesting Module

Comprehensive backtesting framework for Cthulu trading strategies.

Features:
- Historical data management with MT5 integration
- Adjustable speed engine (fast/slow/realtime simulation)
- Multi-strategy ensemble testing
- Advanced benchmarking (Sharpe, Sortino, Calmar, Omega, etc.)
- Detailed performance reports with visualizations
- Walk-forward optimization support
- Monte Carlo simulation for robustness testing
- ML-enhanced decision making (softmax/argmax signal selection)
- Price prediction with trainable models

Usage:
    from backtesting import BacktestEngine, HistoricalDataManager
    
    # Load historical data
    data_mgr = HistoricalDataManager()
    data = data_mgr.fetch_data('EURUSD', '2023-01-01', '2024-01-01', 'H1')
    
    # Run backtest
    engine = BacktestEngine(strategies=[strategy1, strategy2])
    results = engine.run(data, speed='fast')
    
    # Generate report
    results.generate_report('backtest_report.html')
    
    # ML-enhanced selection
    from backtesting import SoftmaxSelector, PricePredictor
    selector = SoftmaxSelector(temperature=0.5)
    predictor = PricePredictor(prediction_horizon=5)
"""

from pathlib import Path

# Package-local paths for backtesting data and reports
BASE_DIR = Path(__file__).resolve().parent
BACKTEST_CACHE_DIR = BASE_DIR / "cache"
BACKTEST_REPORTS_DIR = BASE_DIR / "reports"

from .engine import BacktestEngine, BacktestConfig, SpeedMode
from .data_manager import HistoricalDataManager, DataSource
from .ensemble import EnsembleStrategy, EnsembleConfig, WeightingMethod
from .benchmarks import BenchmarkSuite, PerformanceMetrics
from .reporter import ReportGenerator, ReportFormat
from .optimizer import WalkForwardOptimizer, MonteCarloSimulator
from .ml_decision import (
    SoftmaxSelector,
    SelectionMethod,
    PricePredictor,
    PredictionResult,
    ArgmaxStrategySelector,
)

__all__ = [
    'BacktestEngine',
    'BacktestConfig',
    'SpeedMode',
    'HistoricalDataManager',
    'DataSource',
    'EnsembleStrategy',
    'EnsembleConfig',
    'WeightingMethod',
    'BenchmarkSuite',
    'PerformanceMetrics',
    'ReportGenerator',
    'ReportFormat',
    'WalkForwardOptimizer',
    'MonteCarloSimulator',
    # ML-enhanced
    'SoftmaxSelector',
    'SelectionMethod',
    'PricePredictor',
    'PredictionResult',
    'ArgmaxStrategySelector',
]

__version__ = '1.0.0'
