"""
Benchmark Suite

Comprehensive performance benchmarking beyond just Sharpe ratio.
Includes multiple risk-adjusted return metrics, drawdown analysis, and trade statistics.
"""

import pandas as pd
import numpy as np
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics"""
    # Basic metrics
    total_return: float = 0.0
    annualized_return: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    
    # Profit metrics
    total_profit: float = 0.0
    total_loss: float = 0.0
    net_profit: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    profit_factor: float = 0.0
    
    # Risk-adjusted returns
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    omega_ratio: float = 0.0
    information_ratio: float = 0.0
    
    # Drawdown metrics
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_days: float = 0.0
    avg_drawdown: float = 0.0
    recovery_factor: float = 0.0
    
    # Consistency metrics
    monthly_returns: List[float] = field(default_factory=list)
    monthly_win_rate: float = 0.0
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    
    # Trade duration
    avg_trade_duration_hours: float = 0.0
    avg_winning_trade_duration_hours: float = 0.0
    avg_losing_trade_duration_hours: float = 0.0
    
    # Expectancy and risk
    expectancy: float = 0.0
    risk_reward_ratio: float = 0.0
    payoff_ratio: float = 0.0
    
    # Advanced metrics
    ulcer_index: float = 0.0
    kurtosis: float = 0.0
    skewness: float = 0.0
    value_at_risk_95: float = 0.0
    conditional_var_95: float = 0.0
    
    # Benchmark comparison
    benchmark_correlation: float = 0.0
    beta: float = 0.0
    alpha: float = 0.0
    tracking_error: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'total_return': self.total_return,
            'annualized_return': self.annualized_return,
            'total_trades': self.total_trades,
            'win_rate': self.win_rate,
            'profit_factor': self.profit_factor,
            'sharpe_ratio': self.sharpe_ratio,
            'sortino_ratio': self.sortino_ratio,
            'calmar_ratio': self.calmar_ratio,
            'omega_ratio': self.omega_ratio,
            'max_drawdown_pct': self.max_drawdown_pct,
            'recovery_factor': self.recovery_factor,
            'expectancy': self.expectancy,
            'risk_reward_ratio': self.risk_reward_ratio,
        }


class BenchmarkSuite:
    """
    Comprehensive benchmarking suite for backtest results.
    
    Calculates multiple performance metrics including:
    - Sharpe, Sortino, Calmar, Omega ratios
    - Multiple drawdown metrics
    - Trade statistics and consistency measures
    - Risk metrics (VaR, CVaR, Ulcer Index)
    - Benchmark comparison (alpha, beta, correlation)
    """
    
    def __init__(self, risk_free_rate: float = 0.02):
        """
        Initialize benchmark suite.
        
        Args:
            risk_free_rate: Annual risk-free rate (default 2%)
        """
        self.logger = logging.getLogger("cthulu.backtesting.benchmarks")
        self.risk_free_rate = risk_free_rate
        
    def calculate_metrics(
        self,
        equity_curve: List[Tuple[datetime, float]],
        trades: List[Any],
        initial_capital: float,
        benchmark_returns: Optional[pd.Series] = None
    ) -> PerformanceMetrics:
        """
        Calculate comprehensive performance metrics.
        
        Args:
            equity_curve: List of (timestamp, equity) tuples
            trades: List of Trade objects
            initial_capital: Starting capital
            benchmark_returns: Optional benchmark returns for comparison
            
        Returns:
            PerformanceMetrics object with all calculated metrics
        """
        if not equity_curve or not trades:
            self.logger.warning("Empty equity curve or trades, returning zero metrics")
            return PerformanceMetrics()
            
        metrics = PerformanceMetrics()
        
        # Convert equity curve to DataFrame
        df = pd.DataFrame(equity_curve, columns=['timestamp', 'equity'])
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        df['returns'] = df['equity'].pct_change()
        
        # Basic metrics
        metrics.total_return = (df['equity'].iloc[-1] / initial_capital - 1) * 100
        
        # Calculate annualized return
        days = (df.index[-1] - df.index[0]).days
        years = days / 365.25
        if years > 0:
            metrics.annualized_return = ((df['equity'].iloc[-1] / initial_capital) ** (1 / years) - 1) * 100
        
        # Trade statistics
        metrics.total_trades = len(trades)
        winning = [t for t in trades if t.pnl > 0]
        losing = [t for t in trades if t.pnl < 0]
        metrics.winning_trades = len(winning)
        metrics.losing_trades = len(losing)
        metrics.win_rate = len(winning) / len(trades) if trades else 0.0
        
        # Profit metrics
        if winning:
            metrics.total_profit = sum(t.pnl for t in winning)
            metrics.avg_win = metrics.total_profit / len(winning)
            metrics.largest_win = max(t.pnl for t in winning)
        if losing:
            metrics.total_loss = abs(sum(t.pnl for t in losing))
            metrics.avg_loss = metrics.total_loss / len(losing)
            metrics.largest_loss = min(t.pnl for t in losing)
            
        metrics.net_profit = metrics.total_profit - metrics.total_loss
        if metrics.total_loss > 0:
            metrics.profit_factor = metrics.total_profit / metrics.total_loss
            
        # Risk-adjusted returns
        metrics.sharpe_ratio = self._calculate_sharpe(df['returns'])
        metrics.sortino_ratio = self._calculate_sortino(df['returns'])
        metrics.calmar_ratio = self._calculate_calmar(df, initial_capital)
        metrics.omega_ratio = self._calculate_omega(df['returns'])
        
        # Drawdown analysis
        dd_metrics = self._calculate_drawdown_metrics(df['equity'], initial_capital)
        metrics.max_drawdown = dd_metrics['max_drawdown']
        metrics.max_drawdown_pct = dd_metrics['max_drawdown_pct']
        metrics.max_drawdown_duration_days = dd_metrics['max_drawdown_duration_days']
        metrics.avg_drawdown = dd_metrics['avg_drawdown']
        
        # Recovery factor
        if metrics.max_drawdown > 0:
            metrics.recovery_factor = metrics.net_profit / metrics.max_drawdown
            
        # Consistency metrics
        metrics.monthly_returns = self._calculate_monthly_returns(df)
        if metrics.monthly_returns:
            winning_months = sum(1 for r in metrics.monthly_returns if r > 0)
            metrics.monthly_win_rate = winning_months / len(metrics.monthly_returns)
            
        # Consecutive wins/losses
        consec = self._calculate_consecutive_streaks(trades)
        metrics.max_consecutive_wins = consec['max_wins']
        metrics.max_consecutive_losses = consec['max_losses']
        
        # Trade duration
        durations = self._calculate_trade_durations(trades)
        metrics.avg_trade_duration_hours = durations['avg_all']
        metrics.avg_winning_trade_duration_hours = durations['avg_winning']
        metrics.avg_losing_trade_duration_hours = durations['avg_losing']
        
        # Expectancy and risk
        metrics.expectancy = self._calculate_expectancy(trades)
        metrics.risk_reward_ratio = abs(metrics.avg_win / metrics.avg_loss) if metrics.avg_loss != 0 else 0.0
        metrics.payoff_ratio = metrics.avg_win / abs(metrics.avg_loss) if metrics.avg_loss != 0 else 0.0
        
        # Advanced metrics
        metrics.ulcer_index = self._calculate_ulcer_index(df['equity'])
        metrics.kurtosis = df['returns'].kurtosis() if len(df['returns']) > 3 else 0.0
        metrics.skewness = df['returns'].skew() if len(df['returns']) > 2 else 0.0
        metrics.value_at_risk_95 = df['returns'].quantile(0.05)
        metrics.conditional_var_95 = df['returns'][df['returns'] <= metrics.value_at_risk_95].mean()
        
        # Benchmark comparison
        if benchmark_returns is not None:
            bench_metrics = self._calculate_benchmark_metrics(df['returns'], benchmark_returns)
            metrics.benchmark_correlation = bench_metrics['correlation']
            metrics.beta = bench_metrics['beta']
            metrics.alpha = bench_metrics['alpha']
            metrics.information_ratio = bench_metrics['information_ratio']
            metrics.tracking_error = bench_metrics['tracking_error']
            
        return metrics
        
    def _calculate_sharpe(self, returns: pd.Series, periods_per_year: int = 252) -> float:
        """Calculate annualized Sharpe ratio."""
        if len(returns) < 2:
            return 0.0
        excess_returns = returns - (self.risk_free_rate / periods_per_year)
        if excess_returns.std() == 0:
            return 0.0
        return (excess_returns.mean() / excess_returns.std()) * np.sqrt(periods_per_year)
        
    def _calculate_sortino(self, returns: pd.Series, periods_per_year: int = 252) -> float:
        """Calculate Sortino ratio (uses downside deviation)."""
        if len(returns) < 2:
            return 0.0
        excess_returns = returns - (self.risk_free_rate / periods_per_year)
        downside = excess_returns[excess_returns < 0]
        if len(downside) == 0 or downside.std() == 0:
            return 0.0
        return (excess_returns.mean() / downside.std()) * np.sqrt(periods_per_year)
        
    def _calculate_calmar(self, df: pd.DataFrame, initial_capital: float) -> float:
        """Calculate Calmar ratio (return / max drawdown)."""
        dd_metrics = self._calculate_drawdown_metrics(df['equity'], initial_capital)
        max_dd = dd_metrics['max_drawdown_pct']
        if max_dd == 0:
            return 0.0
        days = (df.index[-1] - df.index[0]).days
        years = days / 365.25
        if years > 0:
            annual_return = ((df['equity'].iloc[-1] / initial_capital) ** (1 / years) - 1)
            return annual_return / (max_dd / 100)
        return 0.0
        
    def _calculate_omega(self, returns: pd.Series, threshold: float = 0.0) -> float:
        """Calculate Omega ratio."""
        if len(returns) == 0:
            return 0.0
        gains = returns[returns > threshold].sum()
        losses = abs(returns[returns < threshold].sum())
        if losses == 0:
            return float('inf') if gains > 0 else 0.0
        return gains / losses
        
    def _calculate_drawdown_metrics(
        self,
        equity: pd.Series,
        initial_capital: float
    ) -> Dict[str, float]:
        """Calculate comprehensive drawdown metrics."""
        # Calculate drawdown series
        cummax = equity.cummax()
        drawdown = (equity - cummax) / cummax * 100
        
        # Max drawdown
        max_dd_pct = drawdown.min()
        max_dd_abs = (cummax - equity).max()
        
        # Find max drawdown duration
        in_drawdown = drawdown < 0
        drawdown_periods = []
        start = None
        for idx, is_dd in in_drawdown.items():
            if is_dd and start is None:
                start = idx
            elif not is_dd and start is not None:
                duration = (idx - start).days
                drawdown_periods.append(duration)
                start = None
        if start is not None:  # Still in drawdown
            duration = (in_drawdown.index[-1] - start).days
            drawdown_periods.append(duration)
            
        max_dd_duration = max(drawdown_periods) if drawdown_periods else 0
        avg_dd = drawdown.mean()
        
        return {
            'max_drawdown': max_dd_abs,
            'max_drawdown_pct': abs(max_dd_pct),
            'max_drawdown_duration_days': max_dd_duration,
            'avg_drawdown': abs(avg_dd),
        }
        
    def _calculate_ulcer_index(self, equity: pd.Series) -> float:
        """Calculate Ulcer Index (measures downside volatility)."""
        cummax = equity.cummax()
        drawdown_pct = ((equity - cummax) / cummax * 100)
        ulcer = np.sqrt((drawdown_pct ** 2).mean())
        return ulcer
        
    def _calculate_monthly_returns(self, df: pd.DataFrame) -> List[float]:
        """Calculate monthly returns."""
        if len(df) == 0:
            return []
        monthly = df['equity'].resample('ME').last()  # Use 'ME' for month-end
        monthly_returns = monthly.pct_change().dropna() * 100
        return monthly_returns.tolist()
        
    def _calculate_consecutive_streaks(self, trades: List[Any]) -> Dict[str, int]:
        """Calculate consecutive winning/losing streaks."""
        if not trades:
            return {'max_wins': 0, 'max_losses': 0}
            
        current_wins = 0
        current_losses = 0
        max_wins = 0
        max_losses = 0
        
        for trade in trades:
            if trade.pnl > 0:
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)
                
        return {'max_wins': max_wins, 'max_losses': max_losses}
        
    def _calculate_trade_durations(self, trades: List[Any]) -> Dict[str, float]:
        """Calculate average trade durations."""
        if not trades:
            return {'avg_all': 0.0, 'avg_winning': 0.0, 'avg_losing': 0.0}
            
        all_durations = []
        winning_durations = []
        losing_durations = []
        
        for trade in trades:
            duration_hours = (trade.exit_time - trade.entry_time).total_seconds() / 3600
            all_durations.append(duration_hours)
            if trade.pnl > 0:
                winning_durations.append(duration_hours)
            else:
                losing_durations.append(duration_hours)
                
        return {
            'avg_all': np.mean(all_durations) if all_durations else 0.0,
            'avg_winning': np.mean(winning_durations) if winning_durations else 0.0,
            'avg_losing': np.mean(losing_durations) if losing_durations else 0.0,
        }
        
    def _calculate_expectancy(self, trades: List[Any]) -> float:
        """Calculate trade expectancy."""
        if not trades:
            return 0.0
        winning = [t.pnl for t in trades if t.pnl > 0]
        losing = [t.pnl for t in trades if t.pnl < 0]
        
        if not winning and not losing:
            return 0.0
            
        win_rate = len(winning) / len(trades)
        avg_win = np.mean(winning) if winning else 0.0
        avg_loss = abs(np.mean(losing)) if losing else 0.0
        
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        return expectancy
        
    def _calculate_benchmark_metrics(
        self,
        strategy_returns: pd.Series,
        benchmark_returns: pd.Series
    ) -> Dict[str, float]:
        """Calculate metrics relative to benchmark."""
        # Align series
        aligned = pd.DataFrame({
            'strategy': strategy_returns,
            'benchmark': benchmark_returns
        }).dropna()
        
        if len(aligned) < 2:
            return {
                'correlation': 0.0,
                'beta': 0.0,
                'alpha': 0.0,
                'information_ratio': 0.0,
                'tracking_error': 0.0,
            }
            
        # Correlation
        correlation = aligned['strategy'].corr(aligned['benchmark'])
        
        # Beta (covariance / variance)
        covariance = aligned['strategy'].cov(aligned['benchmark'])
        benchmark_variance = aligned['benchmark'].var()
        beta = covariance / benchmark_variance if benchmark_variance != 0 else 0.0
        
        # Alpha (excess return over benchmark)
        strategy_return = aligned['strategy'].mean()
        benchmark_return = aligned['benchmark'].mean()
        rf_daily = self.risk_free_rate / 252
        alpha = strategy_return - (rf_daily + beta * (benchmark_return - rf_daily))
        
        # Information ratio
        excess_returns = aligned['strategy'] - aligned['benchmark']
        tracking_error = excess_returns.std()
        information_ratio = excess_returns.mean() / tracking_error if tracking_error != 0 else 0.0
        
        return {
            'correlation': correlation,
            'beta': beta,
            'alpha': alpha * 252,  # Annualized
            'information_ratio': information_ratio * np.sqrt(252),  # Annualized
            'tracking_error': tracking_error * np.sqrt(252),  # Annualized
        }
