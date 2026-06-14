#!/usr/bin/env python
"""
Production Backtest Suite Runner

Runs comprehensive backtesting suite to find optimal configurations.
Can be run from command line without UI.
"""

import argparse
import logging
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backtesting.engine import BacktestEngine, BacktestConfig, SpeedMode
from backtesting.auto_optimizer import AutoOptimizer
from backtesting.hektor_backtest import HektorBacktest
from backtesting.reporter import BacktestReporter
from integrations.vector_studio import VectorStudioAdapter, VectorStudioConfig
import pandas as pd


def setup_logging(log_level: str = 'INFO'):
    """Setup logging configuration"""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(f'backtest_suite_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
        ]
    )


def load_market_data(data_path: str) -> pd.DataFrame:
    """Load market data from CSV"""
    logger = logging.getLogger(__name__)
    logger.info(f"Loading market data from {data_path}")
    
    df = pd.read_csv(data_path, parse_dates=['Date'], index_col='Date')
    
    logger.info(f"Loaded {len(df)} bars from {df.index[0]} to {df.index[-1]}")
    
    return df


def run_single_backtest(
    data: pd.DataFrame,
    config: Dict[str, Any],
    output_dir: Path
) -> Dict[str, Any]:
    """Run a single backtest"""
    logger = logging.getLogger(__name__)
    logger.info("Running single backtest...")
    
    # Create backtest config
    backtest_config = BacktestConfig(
        initial_capital=config.get('initial_capital', 10000.0),
        commission=config.get('commission', 0.0001),
        slippage_pct=config.get('slippage_pct', 0.0002),
        speed_mode=SpeedMode(config.get('speed_mode', 'fast'))
    )
    
    # Create strategies
    # TODO: Load strategies from config
    strategies = []
    
    # Create engine
    engine = BacktestEngine(strategies, backtest_config)
    
    # Run backtest
    result = engine.run(data)
    
    # Generate report
    reporter = BacktestReporter()
    report = reporter.generate_report(result)
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_file = output_dir / f"backtest_{timestamp}.json"
    
    with open(result_file, 'w') as f:
        json.dump(report, f, indent=2, default=str)
        
    logger.info(f"Results saved to {result_file}")
    logger.info(f"Sharpe Ratio: {report.get('sharpe_ratio', 0):.2f}")
    logger.info(f"Total Return: {report.get('total_return', 0):.2%}")
    logger.info(f"Max Drawdown: {report.get('max_drawdown', 0):.2%}")
    
    return report


def run_optimization_suite(
    data: pd.DataFrame,
    config: Dict[str, Any],
    output_dir: Path,
    use_hektor: bool = True
) -> List[Dict[str, Any]]:
    """Run optimization suite"""
    logger = logging.getLogger(__name__)
    logger.info("Running optimization suite...")
    
    # Initialize Hektor if enabled
    hektor_backtest = None
    if use_hektor:
        try:
            vector_config = VectorStudioConfig(
                enabled=True,
                database_path=config.get('hektor', {}).get('database_path', './vectors/backtest_memory')
            )
            vector_adapter = VectorStudioAdapter(vector_config)
            vector_adapter.connect()
            hektor_backtest = HektorBacktest(vector_adapter=vector_adapter)
            logger.info("Hektor integration enabled")
        except Exception as e:
            logger.warning(f"Hektor initialization failed: {e}. Continuing without Hektor.")
            
    # Create optimizer
    optimizer = AutoOptimizer(
        hektor_backtest=hektor_backtest,
        output_dir=str(output_dir)
    )
    
    # Get optimization parameters
    opt_config = config.get('optimization', {})
    method = opt_config.get('method', 'grid_search')
    
    # Progress callback
    def progress_callback(iteration: int, total: int, result: Dict[str, Any]):
        logger.info(
            f"Optimization progress: {iteration}/{total} "
            f"(Best score: {result.get('score', 0):.4f})"
        )
    
    # Run optimization based on method
    if method == 'grid_search':
        param_grid = opt_config.get('param_grid', {})
        results = optimizer.optimize_grid_search(
            data=data,
            param_grid=param_grid,
            base_config=config,
            objective=opt_config.get('objective', 'sharpe_ratio'),
            max_iterations=opt_config.get('max_iterations'),
            progress_callback=progress_callback
        )
    elif method == 'bayesian':
        param_bounds = opt_config.get('param_bounds', {})
        results = optimizer.optimize_bayesian(
            data=data,
            param_bounds=param_bounds,
            base_config=config,
            objective=opt_config.get('objective', 'sharpe_ratio'),
            n_iterations=opt_config.get('n_iterations', 50),
            progress_callback=progress_callback
        )
    elif method == 'multi_objective':
        param_grid = opt_config.get('param_grid', {})
        results = optimizer.optimize_multi_objective(
            data=data,
            param_grid=param_grid,
            base_config=config,
            objectives=opt_config.get('objectives', ['sharpe_ratio', 'max_drawdown']),
            progress_callback=progress_callback
        )
    else:
        logger.error(f"Unknown optimization method: {method}")
        return []
        
    # Print top results
    logger.info("\n" + "="*80)
    logger.info("TOP 10 CONFIGURATIONS")
    logger.info("="*80)
    
    for i, result in enumerate(results[:10], 1):
        logger.info(f"\n#{i} - Score: {result.score:.4f}")
        logger.info(f"  Sharpe Ratio: {result.metrics.get('sharpe_ratio', 0):.2f}")
        logger.info(f"  Total Return: {result.metrics.get('total_return', 0):.2%}")
        logger.info(f"  Max Drawdown: {result.metrics.get('max_drawdown', 0):.2%}")
        logger.info(f"  Win Rate: {result.metrics.get('win_rate', 0):.2%}")
        logger.info(f"  Config: {json.dumps(result.config, indent=2)}")
        
    return [r.to_dict() for r in results]


def run_comparison_suite(
    data: pd.DataFrame,
    configs: List[Dict[str, Any]],
    output_dir: Path
) -> Dict[str, Any]:
    """Run comparison across multiple configurations"""
    logger = logging.getLogger(__name__)
    logger.info(f"Running comparison suite with {len(configs)} configurations...")
    
    results = []
    
    for i, config in enumerate(configs, 1):
        logger.info(f"\nTesting configuration {i}/{len(configs)}")
        
        try:
            result = run_single_backtest(data, config, output_dir)
            results.append({
                'config_index': i,
                'config': config,
                'result': result
            })
        except Exception as e:
            logger.error(f"Error testing configuration {i}: {e}")
            continue
            
    # Compare results
    comparison = {
        'total_configs': len(configs),
        'successful_tests': len(results),
        'results': results,
        'best_by_sharpe': max(results, key=lambda x: x['result'].get('sharpe_ratio', 0)),
        'best_by_return': max(results, key=lambda x: x['result'].get('total_return', 0)),
        'best_by_drawdown': min(results, key=lambda x: abs(x['result'].get('max_drawdown', 0)))
    }
    
    # Save comparison
    comparison_file = output_dir / f"comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(comparison_file, 'w') as f:
        json.dump(comparison, f, indent=2, default=str)
        
    logger.info(f"\nComparison results saved to {comparison_file}")
    
    return comparison


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Run Cthulu backtest suite')
    
    parser.add_argument(
        '--data',
        type=str,
        required=True,
        help='Path to market data CSV file'
    )
    
    parser.add_argument(
        '--config',
        type=str,
        required=True,
        help='Path to configuration JSON file'
    )
    
    parser.add_argument(
        '--mode',
        type=str,
        choices=['single', 'optimize', 'compare'],
        default='single',
        help='Backtest mode'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default='./backtesting/results',
        help='Output directory for results'
    )
    
    parser.add_argument(
        '--no-hektor',
        action='store_true',
        help='Disable Hektor integration'
    )
    
    parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load configuration
    logger.info(f"Loading configuration from {args.config}")
    with open(args.config, 'r') as f:
        config = json.load(f)
        
    # Load market data
    data = load_market_data(args.data)
    
    # Run based on mode
    if args.mode == 'single':
        result = run_single_backtest(data, config, output_dir)
        
    elif args.mode == 'optimize':
        results = run_optimization_suite(
            data, config, output_dir,
            use_hektor=not args.no_hektor
        )
        
        # Save best configuration
        if results:
            best_config = results[0]['config']
            best_config_file = output_dir / 'best_config.json'
            
            with open(best_config_file, 'w') as f:
                json.dump(best_config, f, indent=2)
                
            logger.info(f"\nBest configuration saved to {best_config_file}")
            
    elif args.mode == 'compare':
        # Load multiple configs
        configs = config.get('configs', [config])
        comparison = run_comparison_suite(data, configs, output_dir)
        
    logger.info("\n" + "="*80)
    logger.info("BACKTEST SUITE COMPLETED")
    logger.info("="*80)


if __name__ == '__main__':
    main()
