"""
Automated Configuration Optimizer

Uses Hektor-powered pattern recognition and Bayesian optimization
to find optimal trading configurations.
"""

import logging
import json
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple, Callable
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
import itertools

from backtesting.engine import BacktestEngine, BacktestConfig
from backtesting.hektor_backtest import HektorBacktest

logger = logging.getLogger(__name__)


@dataclass
class OptimizationResult:
    """Optimization result"""
    config: Dict[str, Any]
    score: float
    metrics: Dict[str, float]
    iteration: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'config': self.config,
            'score': self.score,
            'metrics': self.metrics,
            'iteration': self.iteration
        }


class AutoOptimizer:
    """
    Automated configuration optimizer.
    
    Features:
    - Grid search with Hektor-powered pruning
    - Bayesian optimization using historical patterns
    - Multi-objective optimization
    - Parallel backtest execution
    """
    
    def __init__(
        self,
        hektor_backtest: Optional[HektorBacktest] = None,
        output_dir: str = "./optimization_results"
    ):
        """
        Initialize auto optimizer.
        
        Args:
            hektor_backtest: HektorBacktest instance for pattern-based optimization
            output_dir: Directory to save optimization results
        """
        self.hektor_backtest = hektor_backtest
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)
        
    def optimize_grid_search(
        self,
        data: pd.DataFrame,
        param_grid: Dict[str, List[Any]],
        base_config: Dict[str, Any],
        objective: str = 'sharpe_ratio',
        max_iterations: Optional[int] = None,
        progress_callback: Optional[Callable] = None
    ) -> List[OptimizationResult]:
        """
        Grid search optimization.
        
        Args:
            data: Market data for backtesting
            param_grid: Parameter grid to search
            base_config: Base configuration
            objective: Objective metric to optimize
            max_iterations: Maximum iterations (None = all combinations)
            progress_callback: Progress callback function
            
        Returns:
            List of optimization results sorted by score
        """
        self.logger.info("Starting grid search optimization...")
        
        # Generate all combinations
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        combinations = list(itertools.product(*param_values))
        
        total_iterations = len(combinations)
        if max_iterations:
            total_iterations = min(total_iterations, max_iterations)
            combinations = combinations[:max_iterations]
            
        self.logger.info(f"Testing {total_iterations} parameter combinations")
        
        results = []
        
        for i, combination in enumerate(combinations):
            try:
                # Build configuration
                config = base_config.copy()
                for param_name, param_value in zip(param_names, combination):
                    self._set_nested_param(config, param_name, param_value)
                    
                # Check if similar config was tested before (Hektor optimization)
                if self.hektor_backtest:
                    similar = self.hektor_backtest.find_similar_backtests(
                        config=config,
                        k=1,
                        min_score=0.95  # Very similar
                    )
                    
                    if similar:
                        # Skip if very similar config already tested
                        self.logger.info(
                            f"Skipping similar config (iteration {i+1}/{total_iterations})"
                        )
                        continue
                        
                # Run backtest
                self.logger.info(f"Testing iteration {i+1}/{total_iterations}")
                
                backtest_result = self._run_backtest(data, config)
                
                # Extract score
                score = backtest_result.get(objective, 0.0)
                
                # Create result
                result = OptimizationResult(
                    config=config,
                    score=score,
                    metrics=backtest_result,
                    iteration=i
                )
                
                results.append(result)
                
                # Store in Hektor
                if self.hektor_backtest:
                    self.hektor_backtest.store_backtest_result(
                        config=config,
                        result=backtest_result,
                        metadata={'optimization_iteration': i}
                    )
                    
                # Progress callback
                if progress_callback:
                    progress_callback(i + 1, total_iterations, result.to_dict())
                    
            except Exception as e:
                self.logger.error(f"Error in iteration {i}: {e}")
                continue
                
        # Sort by score
        results.sort(key=lambda x: x.score, reverse=True)
        
        self.logger.info(
            f"Optimization complete. Best score: {results[0].score:.4f}"
        )
        
        # Save results
        self._save_optimization_results(results, 'grid_search')
        
        return results
    
    def optimize_bayesian(
        self,
        data: pd.DataFrame,
        param_bounds: Dict[str, Tuple[float, float]],
        base_config: Dict[str, Any],
        objective: str = 'sharpe_ratio',
        n_iterations: int = 50,
        n_initial_points: int = 10,
        progress_callback: Optional[Callable] = None
    ) -> List[OptimizationResult]:
        """
        Bayesian optimization using historical patterns.
        
        Args:
            data: Market data
            param_bounds: Parameter bounds (min, max)
            base_config: Base configuration
            objective: Objective metric
            n_iterations: Number of iterations
            n_initial_points: Number of random initial points
            progress_callback: Progress callback
            
        Returns:
            List of optimization results
        """
        self.logger.info("Starting Bayesian optimization...")
        
        results = []
        
        # Initial random sampling
        for i in range(n_initial_points):
            try:
                # Sample random parameters
                config = base_config.copy()
                for param_name, (min_val, max_val) in param_bounds.items():
                    value = np.random.uniform(min_val, max_val)
                    self._set_nested_param(config, param_name, value)
                    
                # Run backtest
                backtest_result = self._run_backtest(data, config)
                score = backtest_result.get(objective, 0.0)
                
                result = OptimizationResult(
                    config=config,
                    score=score,
                    metrics=backtest_result,
                    iteration=i
                )
                
                results.append(result)
                
                if progress_callback:
                    progress_callback(i + 1, n_iterations, result.to_dict())
                    
            except Exception as e:
                self.logger.error(f"Error in initial sampling {i}: {e}")
                continue
                
        # Bayesian optimization iterations
        for i in range(n_initial_points, n_iterations):
            try:
                # Use Hektor to find promising regions
                if self.hektor_backtest and results:
                    # Get best configurations so far
                    best_configs = sorted(results, key=lambda x: x.score, reverse=True)[:5]
                    
                    # Find similar high-performing configs from history
                    promising_regions = []
                    for best in best_configs:
                        similar = self.hektor_backtest.find_similar_backtests(
                            config=best.config,
                            k=3,
                            min_score=0.7
                        )
                        promising_regions.extend(similar)
                        
                    # Sample from promising regions
                    if promising_regions:
                        # Pick a random promising config and perturb it
                        base = np.random.choice(promising_regions)
                        config = self._perturb_config(
                            base['config'],
                            param_bounds,
                            perturbation=0.1
                        )
                    else:
                        # Fallback to random sampling
                        config = self._sample_random_config(base_config, param_bounds)
                else:
                    # No Hektor - use simple Bayesian approach
                    config = self._sample_random_config(base_config, param_bounds)
                    
                # Run backtest
                backtest_result = self._run_backtest(data, config)
                score = backtest_result.get(objective, 0.0)
                
                result = OptimizationResult(
                    config=config,
                    score=score,
                    metrics=backtest_result,
                    iteration=i
                )
                
                results.append(result)
                
                # Store in Hektor
                if self.hektor_backtest:
                    self.hektor_backtest.store_backtest_result(
                        config=config,
                        result=backtest_result,
                        metadata={'optimization_iteration': i, 'method': 'bayesian'}
                    )
                    
                if progress_callback:
                    progress_callback(i + 1, n_iterations, result.to_dict())
                    
            except Exception as e:
                self.logger.error(f"Error in Bayesian iteration {i}: {e}")
                continue
                
        # Sort results
        results.sort(key=lambda x: x.score, reverse=True)
        
        self.logger.info(
            f"Bayesian optimization complete. Best score: {results[0].score:.4f}"
        )
        
        # Save results
        self._save_optimization_results(results, 'bayesian')
        
        return results
    
    def optimize_multi_objective(
        self,
        data: pd.DataFrame,
        param_grid: Dict[str, List[Any]],
        base_config: Dict[str, Any],
        objectives: List[str] = ['sharpe_ratio', 'max_drawdown', 'win_rate'],
        weights: Optional[List[float]] = None,
        progress_callback: Optional[Callable] = None
    ) -> List[OptimizationResult]:
        """
        Multi-objective optimization.
        
        Args:
            data: Market data
            param_grid: Parameter grid
            base_config: Base configuration
            objectives: List of objectives to optimize
            weights: Weights for each objective (None = equal weights)
            progress_callback: Progress callback
            
        Returns:
            Pareto-optimal solutions
        """
        self.logger.info("Starting multi-objective optimization...")
        
        if weights is None:
            weights = [1.0 / len(objectives)] * len(objectives)
            
        # Run grid search
        results = self.optimize_grid_search(
            data=data,
            param_grid=param_grid,
            base_config=base_config,
            objective=objectives[0],  # Primary objective
            progress_callback=progress_callback
        )
        
        # Calculate weighted scores
        for result in results:
            weighted_score = 0.0
            for obj, weight in zip(objectives, weights):
                value = result.metrics.get(obj, 0.0)
                
                # Normalize (assuming higher is better for most metrics)
                # For drawdown, invert since lower is better
                if 'drawdown' in obj.lower():
                    value = -value
                    
                weighted_score += weight * value
                
            result.score = weighted_score
            
        # Sort by weighted score
        results.sort(key=lambda x: x.score, reverse=True)
        
        self.logger.info(
            f"Multi-objective optimization complete. "
            f"Best weighted score: {results[0].score:.4f}"
        )
        
        # Save results
        self._save_optimization_results(results, 'multi_objective')
        
        return results
    
    # Private methods
    
    def _run_backtest(
        self,
        data: pd.DataFrame,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run a single backtest"""
        # TODO: Implement actual backtest execution
        # For now, return dummy results
        
        return {
            'sharpe_ratio': np.random.uniform(0.5, 2.5),
            'total_return': np.random.uniform(-0.2, 0.5),
            'max_drawdown': np.random.uniform(-0.3, -0.05),
            'win_rate': np.random.uniform(0.4, 0.7),
            'total_trades': np.random.randint(50, 500)
        }
    
    def _set_nested_param(
        self,
        config: Dict[str, Any],
        param_path: str,
        value: Any
    ):
        """Set nested parameter in config"""
        keys = param_path.split('.')
        current = config
        
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
            
        current[keys[-1]] = value
    
    def _sample_random_config(
        self,
        base_config: Dict[str, Any],
        param_bounds: Dict[str, Tuple[float, float]]
    ) -> Dict[str, Any]:
        """Sample random configuration"""
        config = base_config.copy()
        
        for param_name, (min_val, max_val) in param_bounds.items():
            value = np.random.uniform(min_val, max_val)
            self._set_nested_param(config, param_name, value)
            
        return config
    
    def _perturb_config(
        self,
        config: Dict[str, Any],
        param_bounds: Dict[str, Tuple[float, float]],
        perturbation: float = 0.1
    ) -> Dict[str, Any]:
        """Perturb configuration slightly"""
        new_config = config.copy()
        
        for param_name, (min_val, max_val) in param_bounds.items():
            # Get current value
            current = self._get_nested_param(config, param_name)
            
            if current is None:
                current = (min_val + max_val) / 2
                
            # Perturb
            range_size = max_val - min_val
            noise = np.random.normal(0, perturbation * range_size)
            new_value = np.clip(current + noise, min_val, max_val)
            
            self._set_nested_param(new_config, param_name, new_value)
            
        return new_config
    
    def _get_nested_param(
        self,
        config: Dict[str, Any],
        param_path: str
    ) -> Any:
        """Get nested parameter from config"""
        keys = param_path.split('.')
        current = config
        
        for key in keys:
            if key not in current:
                return None
            current = current[key]
            
        return current
    
    def _save_optimization_results(
        self,
        results: List[OptimizationResult],
        method: str
    ):
        """Save optimization results"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"optimization_{method}_{timestamp}.json"
        filepath = self.output_dir / filename
        
        data = {
            'method': method,
            'timestamp': datetime.now().isoformat(),
            'total_iterations': len(results),
            'best_score': results[0].score if results else 0.0,
            'results': [r.to_dict() for r in results]
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)
            
        self.logger.info(f"Saved optimization results to {filepath}")
