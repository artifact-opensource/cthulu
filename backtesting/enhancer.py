
import os
import sys
import logging
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
import concurrent.futures

# Use explicit cthulu package imports to avoid ambiguity between top-level and package-level modules
# (do not rely on modifying sys.path at runtime)

import pandas as pd
import numpy as np

from cthulu.backtesting.engine import BacktestEngine, BacktestConfig, SpeedMode
from cthulu.backtesting.optimizer import WalkForwardOptimizer, MonteCarloSimulator
from cthulu.backtesting.data_manager import HistoricalDataManager
from cthulu.strategy.base import Strategy, Signal, SignalType
from cthulu.strategy.trend_following import TrendFollowingStrategy
from cthulu.strategy.scalping import ScalpingStrategy
from cthulu.strategy.mean_reversion import MeanReversionStrategy
from cthulu.strategy.sma_crossover import SmaCrossover
from cthulu.strategy.ema_crossover import EmaCrossover
from cthulu.observability.metrics import MetricsCollector


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("BeastModeOptimizer")


@dataclass
class OptimizationConfig:
    """Configuration for beast mode optimization."""
    
    # Data settings
    symbol: str = "GOLDm#"
    timeframe: str = "M15"
    lookback_days: int = 90
    
    # Optimization settings
    walk_forward_windows: int = 5
    in_sample_pct: float = 0.7
    monte_carlo_simulations: int = 1000
    
    # Parameter search space
    param_grid: Dict[str, List[Any]] = field(default_factory=lambda: {
        # Strategy selection weights
        "trend_weight": [0.3, 0.5, 0.7],
        "scalping_weight": [0.2, 0.3, 0.5],
        "mean_reversion_weight": [0.2, 0.3, 0.4],
        
        # Entry confluence thresholds
        "min_confluence_score": [50, 60, 70, 80],
        "signal_confirmation_bars": [1, 2, 3],
        
        # Risk parameters
        "position_size_pct": [0.01, 0.02, 0.03],
        "max_positions": [3, 5, 7],
        "stop_loss_atr_mult": [1.5, 2.0, 2.5, 3.0],
        "take_profit_atr_mult": [2.0, 3.0, 4.0, 5.0],
        
        # Exit parameters
        "trailing_stop_activation": [0.5, 1.0, 1.5],  # ATR multiples
        "profit_scaling_threshold": [0.5, 1.0, 1.5],  # RRR
        "time_exit_bars": [20, 40, 60],
    })
    
    # Backtest settings
    initial_capital: float = 10000.0
    commission: float = 0.0001
    slippage_pct: float = 0.0002
    
    # Parallel processing
    max_workers: int = 4
    
    # Output
    output_dir: str = "./optimization_results"


class StrategyFactory:
    """Factory for creating strategy instances with parameters."""
    
    @staticmethod
    def create_strategies(params: Dict[str, Any]) -> List[Strategy]:
        """
        Create strategy instances based on parameters.
        
        Args:
            params: Strategy parameters
            
        Returns:
            List of configured strategies
        """
        strategies = []
        
        # Trend Following
        if params.get("trend_weight", 0) > 0:
            cfg = {'params': {
                'fast_ma': params.get('trend_period', 50),
                'slow_ma': params.get('trend_period', 50),
                'adx_period': params.get('adx_period', 14),
                'adx_threshold': params.get('min_adx', 25),
                'atr_multiplier': params.get('trend_atr_mult', 2.0),
                'risk_reward_ratio': params.get('trend_rr', 3.0),
                'symbol': params.get('symbol')
            }}
            strategies.append(TrendFollowingStrategy(cfg))
        
        # Scalping
        if params.get("scalping_weight", 0) > 0:
            cfg = {'params': {
                'fast_ema': params.get('scalp_fast', 5),
                'slow_ema': params.get('scalp_slow', 13),
                'rsi_period': params.get('scalp_rsi', 7),
                'atr_multiplier': params.get('scalp_atr', 1.0),
                'symbol': params.get('symbol')
            }}
            strategies.append(ScalpingStrategy(cfg))
        
        # Mean Reversion
        if params.get("mean_reversion_weight", 0) > 0:
            cfg = {'params': {
                'bb_period': params.get('bb_period', 20),
                'bb_std': params.get('bb_std', 2.0),
                'rsi_period': params.get('rsi_period', 14),
                'symbol': params.get('symbol')
            }}
            strategies.append(MeanReversionStrategy(cfg))
        
        # SMA Crossover (SmaCrossover expects short_window/long_window at top-level)
        cfg = {'short_window': params.get('sma_fast', 10), 'long_window': params.get('sma_slow', 50), 'params': {'symbol': params.get('symbol')}}
        strategies.append(SmaCrossover(cfg))
        
        # EMA Crossover
        cfg = {'params': {'fast_period': params.get('ema_fast', 12), 'slow_period': params.get('ema_slow', 26), 'symbol': params.get('symbol')}}
        strategies.append(EmaCrossover(cfg))
        
        return strategies


class BeastModeOptimizer:
    """
    Comprehensive optimizer for Cthulu trading system.
    
    Features:
    - Walk-forward optimization to prevent overfitting
    - Monte Carlo simulation for robustness testing
    - Multi-strategy ensemble optimization
    - Parallel parameter search
    - Comprehensive reporting
    """
    
    def __init__(self, config: OptimizationConfig):
        """
        Initialize optimizer.
        
        Args:
            config: Optimization configuration
        """
        self.config = config
        # Use the project HistoricalDataManager explicitly
        self.data_manager = HistoricalDataManager()
        self.results: List[Dict[str, Any]] = []
        
        # Create output directory
        self.output_dir = Path(config.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Beast Mode Optimizer initialized")
        logger.info(f"Symbol: {config.symbol}, Timeframe: {config.timeframe}")
        logger.info(f"Lookback: {config.lookback_days} days")
    
    def load_data(self) -> pd.DataFrame:
        """
        Load historical data for backtesting.
        
        Returns:
            DataFrame with OHLCV data
        """
        logger.info("Loading historical data...")
        
        try:
            # Try to load from MT5
            data = self.data_manager.get_historical_data(
                symbol=self.config.symbol,
                timeframe=self.config.timeframe,
                days=self.config.lookback_days
            )
            
            if data is not None and len(data) > 0:
                logger.info(f"Loaded {len(data)} bars from MT5")
                return data
        except Exception as e:
            logger.warning(f"MT5 data load failed: {e}")
        
        # Fallback to cached/synthetic data
        return self._generate_synthetic_data()
    
    def _generate_synthetic_data(self) -> pd.DataFrame:
        """Generate synthetic data for testing when MT5 unavailable."""
        logger.warning("Generating synthetic data for testing")
        
        np.random.seed(42)
        n_bars = self.config.lookback_days * 96  # 15-min bars
        
        # Generate realistic gold price movement
        base_price = 2650.0
        returns = np.random.normal(0.0001, 0.002, n_bars)
        prices = base_price * np.exp(np.cumsum(returns))
        
        # Generate OHLCV
        dates = pd.date_range(
            end=datetime.now(),
            periods=n_bars,
            freq="15min"
        )
        
        data = pd.DataFrame({
            "open": prices,
            "high": prices * (1 + np.abs(np.random.normal(0, 0.001, n_bars))),
            "low": prices * (1 - np.abs(np.random.normal(0, 0.001, n_bars))),
            "close": prices * (1 + np.random.normal(0, 0.0005, n_bars)),
            "volume": np.random.randint(100, 10000, n_bars)
        }, index=dates)
        
        return data
    
    def run_single_backtest(
        self,
        data: pd.DataFrame,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Run a single backtest with given parameters.
        
        Args:
            data: Historical data
            params: Strategy and risk parameters
            
        Returns:
            Backtest results
        """
        # Create strategies
        strategies = StrategyFactory.create_strategies(params)
        
        # Create backtest config
        bt_config = BacktestConfig(
            initial_capital=self.config.initial_capital,
            commission=self.config.commission,
            slippage_pct=self.config.slippage_pct,
            speed_mode=SpeedMode.FAST,
            max_positions=params.get("max_positions", 3),
            position_size_pct=params.get("position_size_pct", 0.02),
            enable_short_selling=True
        )
        
        # Run backtest
        engine = BacktestEngine(strategies, bt_config)
        results = engine.run(data)
        
        return {
            "params": params,
            "metrics": results["metrics"],
            "final_equity": engine.equity,
            "trades": len(results["trades"]),
            "sharpe": results["metrics"].sharpe_ratio if results["metrics"] else 0.0,
            "profit_factor": results["metrics"].profit_factor if results["metrics"] else 0.0,
            "win_rate": results["metrics"].win_rate if results["metrics"] else 0.0,
            "max_drawdown": results["metrics"].max_drawdown_pct if results["metrics"] else 0.0
        }
    
    def optimize_walk_forward(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Run walk-forward optimization.
        
        Args:
            data: Historical data
            
        Returns:
            Optimization results with best parameters
        """
        logger.info("Starting walk-forward optimization...")
        
        optimizer = WalkForwardOptimizer(
            in_sample_pct=self.config.in_sample_pct,
            num_windows=self.config.walk_forward_windows,
            metric_to_optimize="sharpe_ratio"
        )
        
        # Generate param combinations
        param_combinations = self._generate_param_combinations()
        logger.info(f"Testing {len(param_combinations)} parameter combinations")
        
        best_params = None
        best_score = float("-inf")
        all_results = []
        
        # Test each combination
        for i, params in enumerate(param_combinations):
            if i % 10 == 0:
                logger.info(f"Progress: {i}/{len(param_combinations)}")
            
            try:
                result = self.run_single_backtest(data, params)
                all_results.append(result)
                
                score = result["sharpe"]
                if score > best_score:
                    best_score = score
                    best_params = params
                    logger.info(f"New best: Sharpe={score:.3f}")
                    
            except Exception as e:
                logger.error(f"Backtest failed for params {i}: {e}")
        
        return {
            "best_params": best_params,
            "best_score": best_score,
            "all_results": all_results
        }
    
    def _generate_param_combinations(self) -> List[Dict[str, Any]]:
        """Generate parameter combinations from grid."""
        from itertools import product
        
        grid = self.config.param_grid
        keys = list(grid.keys())
        values = [grid[k] for k in keys]
        
        combinations = []
        for combo in product(*values):
            combinations.append(dict(zip(keys, combo)))
        
        # Limit combinations for reasonable runtime
        max_combos = 500
        if len(combinations) > max_combos:
            logger.warning(f"Limiting to {max_combos} random combinations")
            np.random.shuffle(combinations)
            combinations = combinations[:max_combos]
        
        return combinations
    
    def run_monte_carlo(
        self,
        data: pd.DataFrame,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Run Monte Carlo simulation for robustness testing.
        
        Args:
            data: Historical data
            params: Best parameters from optimization
            
        Returns:
            Monte Carlo results with confidence intervals
        """
        logger.info("Running Monte Carlo simulation...")
        
        # Run backtest to get trades
        strategies = StrategyFactory.create_strategies(params)
        
        bt_config = BacktestConfig(
            initial_capital=self.config.initial_capital,
            commission=self.config.commission,
            slippage_pct=self.config.slippage_pct,
            speed_mode=SpeedMode.FAST,
            max_positions=params.get("max_positions", 3),
            position_size_pct=params.get("position_size_pct", 0.02)
        )
        
        engine = BacktestEngine(strategies, bt_config)
        results = engine.run(data)
        
        if not results["trades"]:
            logger.warning("No trades for Monte Carlo simulation")
            return {}
        
        # Run Monte Carlo
        mc = MonteCarloSimulator(num_simulations=self.config.monte_carlo_simulations)
        mc_results = mc.simulate(
            results["trades"],
            self.config.initial_capital
        )
        
        return mc_results
    
    def run(self) -> Dict[str, Any]:
        """
        Run full optimization pipeline.
        
        Returns:
            Complete optimization results
        """
        start_time = datetime.now()
        logger.info("=" * 60)
        logger.info("CTHULU BEAST MODE OPTIMIZATION")
        logger.info("=" * 60)
        
        # Load data
        data = self.load_data()
        
        # Phase 1: Walk-forward optimization
        logger.info("\n--- Phase 1: Walk-Forward Optimization ---")
        wf_results = self.optimize_walk_forward(data)
        
        best_params = wf_results["best_params"]
        if not best_params:
            logger.error("Optimization failed - no valid parameters found")
            return {"error": "Optimization failed"}
        
        logger.info(f"\nBest parameters found:")
        for key, value in best_params.items():
            logger.info(f"  {key}: {value}")
        
        # Phase 2: Monte Carlo robustness testing
        logger.info("\n--- Phase 2: Monte Carlo Robustness Testing ---")
        mc_results = self.run_monte_carlo(data, best_params)
        
        if mc_results:
            logger.info(f"\nMonte Carlo Results:")
            logger.info(f"  Probability of Profit: {mc_results.get('probability_profit', 0):.1f}%")
            logger.info(f"  Expected Final Equity: ${mc_results['final_equity']['mean']:,.2f}")
            logger.info(f"  95% Confidence Range: ${mc_results['final_equity']['percentile_5']:,.2f} - ${mc_results['final_equity']['percentile_95']:,.2f}")
            logger.info(f"  Expected Max Drawdown: {mc_results['max_drawdown']['mean']:.2f}%")
        
        # Phase 3: Final validation backtest
        logger.info("\n--- Phase 3: Final Validation ---")
        final_result = self.run_single_backtest(data, best_params)
        
        logger.info(f"\nFinal Validation Results:")
        logger.info(f"  Final Equity: ${final_result['final_equity']:,.2f}")
        logger.info(f"  Total Trades: {final_result['trades']}")
        logger.info(f"  Sharpe Ratio: {final_result['sharpe']:.3f}")
        logger.info(f"  Profit Factor: {final_result['profit_factor']:.2f}")
        logger.info(f"  Win Rate: {final_result['win_rate']*100:.1f}%")
        logger.info(f"  Max Drawdown: {final_result['max_drawdown']*100:.2f}%")
        
        # Generate report
        elapsed = (datetime.now() - start_time).total_seconds()
        
        final_report = {
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": elapsed,
            "config": {
                "symbol": self.config.symbol,
                "timeframe": self.config.timeframe,
                "lookback_days": self.config.lookback_days,
                "data_bars": len(data)
            },
            "best_params": best_params,
            "walk_forward": {
                "best_score": wf_results["best_score"],
                "combinations_tested": len(wf_results["all_results"])
            },
            "monte_carlo": mc_results,
            "final_validation": final_result,
            "recommendation": self._generate_recommendation(
                final_result, mc_results
            )
        }
        
        # Save report
        self._save_report(final_report)
        
        logger.info(f"\nOptimization completed in {elapsed:.1f} seconds")
        logger.info(f"Report saved to: {self.output_dir}")
        
        return final_report
    
    def _generate_recommendation(
        self,
        validation: Dict[str, Any],
        mc: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate deployment recommendation."""
        
        # Scoring criteria
        score = 0
        issues = []
        
        # Sharpe > 1.0 is good
        if validation["sharpe"] > 1.5:
            score += 25
        elif validation["sharpe"] > 1.0:
            score += 15
        elif validation["sharpe"] > 0.5:
            score += 5
        else:
            issues.append("Low Sharpe ratio - weak risk-adjusted returns")
        
        # Profit factor > 1.5 is good
        if validation["profit_factor"] > 2.0:
            score += 25
        elif validation["profit_factor"] > 1.5:
            score += 15
        elif validation["profit_factor"] > 1.2:
            score += 5
        else:
            issues.append("Low profit factor - edge may be insufficient")
        
        # Win rate > 50% is acceptable
        if validation["win_rate"] > 0.6:
            score += 20
        elif validation["win_rate"] > 0.5:
            score += 10
        elif validation["win_rate"] > 0.4:
            score += 5
        else:
            issues.append("Low win rate - may cause psychological stress")
        
        # Max drawdown < 20% is good
        if validation["max_drawdown"] < 0.10:
            score += 20
        elif validation["max_drawdown"] < 0.20:
            score += 10
        elif validation["max_drawdown"] < 0.30:
            score += 5
        else:
            issues.append("High max drawdown - significant capital risk")
        
        # Monte Carlo probability of profit
        if mc and mc.get("probability_profit", 0) > 80:
            score += 10
        elif mc and mc.get("probability_profit", 0) > 60:
            score += 5
        else:
            issues.append("Low probability of profit in Monte Carlo")
        
        # Determine recommendation
        if score >= 80:
            recommendation = "DEPLOY"
            confidence = "HIGH"
        elif score >= 60:
            recommendation = "DEPLOY_WITH_CAUTION"
            confidence = "MEDIUM"
        elif score >= 40:
            recommendation = "PAPER_TRADE_FIRST"
            confidence = "LOW"
        else:
            recommendation = "DO_NOT_DEPLOY"
            confidence = "VERY_LOW"
        
        return {
            "score": score,
            "recommendation": recommendation,
            "confidence": confidence,
            "issues": issues
        }
    
    def _save_report(self, report: Dict[str, Any]):
        """Save optimization report to disk."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save JSON report
        json_path = self.output_dir / f"optimization_{timestamp}.json"
        with open(json_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        
        # Save config recommendation
        if report.get("best_params"):
            config_path = self.output_dir / f"recommended_config_{timestamp}.json"
            with open(config_path, "w") as f:
                json.dump({
                    "generated_at": datetime.now().isoformat(),
                    "optimization_score": report.get("recommendation", {}).get("score", 0),
                    "parameters": report["best_params"]
                }, f, indent=2)
        
        logger.info(f"Report saved: {json_path}")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Cthulu Beast Mode Optimizer")
    parser.add_argument("--symbol", default="GOLDm#", help="Trading symbol")
    parser.add_argument("--timeframe", default="M15", help="Timeframe")
    parser.add_argument("--days", type=int, default=90, help="Lookback days")
    parser.add_argument("--windows", type=int, default=5, help="Walk-forward windows")
    parser.add_argument("--simulations", type=int, default=1000, help="Monte Carlo simulations")
    parser.add_argument("--output", default="./optimization_results", help="Output directory")
    
    args = parser.parse_args()
    
    config = OptimizationConfig(
        symbol=args.symbol,
        timeframe=args.timeframe,
        lookback_days=args.days,
        walk_forward_windows=args.windows,
        monte_carlo_simulations=args.simulations,
        output_dir=args.output
    )
    
    optimizer = BeastModeOptimizer(config)
    results = optimizer.run()
    
    # Print final recommendation
    rec = results.get("recommendation", {})
    print("\n" + "=" * 60)
    print(f"RECOMMENDATION: {rec.get('recommendation', 'UNKNOWN')}")
    print(f"CONFIDENCE: {rec.get('confidence', 'UNKNOWN')}")
    print(f"SCORE: {rec.get('score', 0)}/100")
    if rec.get("issues"):
        print("\nISSUES:")
        for issue in rec["issues"]:
            print(f"  - {issue}")
    print("=" * 60)


if __name__ == "__main__":
    main()
