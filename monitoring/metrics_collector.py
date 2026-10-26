"""
Metrics Collector - Clean Implementation
Collects and exposes performance metrics.
"""
import logging
from typing import Dict, Any, Optional
import time

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Collects and tracks performance metrics.
    
    Metrics:
    - Trade statistics (win rate, profit factor, etc.)
    - Exposure metrics
    - System health
    """
    
    def __init__(self, database, config: Dict[str, Any]):
        """
        Initialize metrics collector.
        
        Args:
            database: Database instance
            config: System configuration
        """
        self.database = database
        self.config = config
        
        # In-memory metrics
        self._metrics = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'gross_profit': 0.0,
            'gross_loss': 0.0,
            'peak_balance': 0.0,
            'max_drawdown': 0.0,
            'current_drawdown': 0.0,
            'consecutive_wins': 0,
            'consecutive_losses': 0,
            'last_updated': 0
        }
        
        logger.info("MetricsCollector initialized")
    
    def record_trade_result(
        self,
        profit: float,
        strategy: str = ""
    ):
        """
        Record a trade result.
        
        Args:
            profit: Trade P&L
            strategy: Strategy that generated the trade
        """
        self._metrics['total_trades'] += 1
        
        if profit > 0:
            self._metrics['winning_trades'] += 1
            self._metrics['gross_profit'] += profit
            self._metrics['consecutive_wins'] += 1
            self._metrics['consecutive_losses'] = 0
        else:
            self._metrics['losing_trades'] += 1
            self._metrics['gross_loss'] += abs(profit)
            self._metrics['consecutive_losses'] += 1
            self._metrics['consecutive_wins'] = 0
        
        self._metrics['last_updated'] = time.time()
    
    def update_balance(self, balance: float):
        """
        Update balance-based metrics.
        
        Args:
            balance: Current account balance
        """
        if balance > self._metrics['peak_balance']:
            self._metrics['peak_balance'] = balance
        
        if self._metrics['peak_balance'] > 0:
            drawdown = (self._metrics['peak_balance'] - balance) / self._metrics['peak_balance'] * 100
            self._metrics['current_drawdown'] = drawdown
            
            if drawdown > self._metrics['max_drawdown']:
                self._metrics['max_drawdown'] = drawdown
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics snapshot."""
        total = self._metrics['total_trades']
        wins = self._metrics['winning_trades']
        
        # Calculate derived metrics
        win_rate = wins / total if total > 0 else 0.5
        avg_win = self._metrics['gross_profit'] / wins if wins > 0 else 0
        losses = self._metrics['losing_trades']
        avg_loss = self._metrics['gross_loss'] / losses if losses > 0 else 0
        
        profit_factor = (
            self._metrics['gross_profit'] / self._metrics['gross_loss']
            if self._metrics['gross_loss'] > 0 else float('inf')
        )
        
        return {
            'total_trades': total,
            'winning_trades': wins,
            'losing_trades': losses,
            'win_rate': win_rate,
            'gross_profit': self._metrics['gross_profit'],
            'gross_loss': self._metrics['gross_loss'],
            'net_profit': self._metrics['gross_profit'] - self._metrics['gross_loss'],
            'profit_factor': profit_factor,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'peak_balance': self._metrics['peak_balance'],
            'max_drawdown': self._metrics['max_drawdown'],
            'current_drawdown': self._metrics['current_drawdown'],
            'consecutive_wins': self._metrics['consecutive_wins'],
            'consecutive_losses': self._metrics['consecutive_losses']
        }
    
    def reset(self):
        """Reset all metrics."""
        for key in self._metrics:
            if isinstance(self._metrics[key], (int, float)):
                self._metrics[key] = 0
        logger.info("Metrics reset")
