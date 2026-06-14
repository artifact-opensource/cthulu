"""
Backtest Engine

Core backtesting engine with adjustable speed simulation.
Supports fast vectorized execution and slow bar-by-bar replay.
"""

import pandas as pd
import numpy as np
import logging
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from copy import deepcopy

from cthulu.strategy.base import Strategy, Signal, SignalType
from cthulu.observability.metrics import MetricsCollector, PerformanceMetrics


class SpeedMode(Enum):
    """Backtest execution speed modes"""
    FAST = "fast"                    # Vectorized, process all bars at once
    NORMAL = "normal"                # Bar-by-bar, no delays
    SLOW = "slow"                    # Bar-by-bar with configurable delays
    REALTIME = "realtime"            # Replay at actual historical speed
    HFT_TEST = "hft_test"            # Ultra-fast for high-frequency testing


@dataclass
class BacktestConfig:
    """Backtesting configuration"""
    initial_capital: float = 10000.0
    commission: float = 0.0001       # 0.01% per trade
    slippage_pct: float = 0.0002     # 0.02% slippage
    speed_mode: SpeedMode = SpeedMode.FAST
    speed_delay_ms: float = 0        # Delay between bars (for SLOW mode)
    use_bid_ask_spread: bool = False
    spread_pips: float = 2.0         # Default spread for FX pairs
    max_positions: int = 3
    position_size_pct: float = 0.02  # 2% risk per trade
    stop_on_margin_call: bool = True
    margin_call_level: float = 0.20  # Stop if equity drops below 20% of initial
    enable_short_selling: bool = True
    track_intrabar_data: bool = False  # Track high/low within each bar
    
    # Ensemble-specific settings
    enable_ensemble: bool = False
    ensemble_rebalance_bars: int = 100  # Rebalance ensemble weights every N bars
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'initial_capital': self.initial_capital,
            'commission': self.commission,
            'slippage_pct': self.slippage_pct,
            'speed_mode': self.speed_mode.value,
            'speed_delay_ms': self.speed_delay_ms,
            'use_bid_ask_spread': self.use_bid_ask_spread,
            'spread_pips': self.spread_pips,
            'max_positions': self.max_positions,
            'position_size_pct': self.position_size_pct,
            'stop_on_margin_call': self.stop_on_margin_call,
            'margin_call_level': self.margin_call_level,
            'enable_short_selling': self.enable_short_selling,
        }


@dataclass
class Position:
    """Backtest position"""
    ticket: int
    symbol: str
    side: SignalType
    entry_price: float
    entry_time: datetime
    size: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    commission_paid: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def unrealized_pnl(self, current_price: float) -> float:
        """Calculate unrealized P&L."""
        if self.side == SignalType.LONG:
            return (current_price - self.entry_price) * self.size
        else:  # SHORT
            return (self.entry_price - current_price) * self.size


@dataclass
class Trade:
    """Completed trade"""
    ticket: int
    symbol: str
    side: SignalType
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    size: float
    pnl: float
    commission: float
    exit_reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class BacktestEngine:
    """
    High-performance backtesting engine.
    
    Features:
    - Multiple speed modes (fast vectorized to slow replay)
    - Realistic commission and slippage simulation
    - Position management with stops and targets
    - Multi-strategy support
    - Real-time progress tracking
    - Comprehensive performance metrics
    """
    
    def __init__(
        self,
        strategies: List[Strategy],
        config: Optional[BacktestConfig] = None
    ):
        """
        Initialize backtest engine.
        
        Args:
            strategies: List of Strategy instances to test
            config: Backtesting configuration
        """
        self.strategies = strategies
        self.config = config or BacktestConfig()
        self.logger = logging.getLogger("cthulu.backtesting.engine")
        
        # State
        self.equity = self.config.initial_capital
        self.cash = self.config.initial_capital
        self.positions: Dict[int, Position] = {}
        self.trades: List[Trade] = []
        self.next_ticket = 1
        
        # Metrics
        self.metrics = MetricsCollector()
        self.equity_curve: List[Tuple[datetime, float]] = []
        
        # Progress tracking
        self.current_bar_idx = 0
        self.total_bars = 0
        self.start_time = None
        
    def run(
        self,
        data: pd.DataFrame,
        indicators: Optional[List[Any]] = None,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Run backtest on historical data.
        
        Args:
            data: DataFrame with OHLCV data (indexed by datetime)
            indicators: Optional list of indicators to calculate
            progress_callback: Optional callback function(progress_pct, current_bar, total_bars)
            
        Returns:
            Dictionary with backtest results
        """
        self.logger.info(f"Starting backtest with {len(self.strategies)} strategies on {len(data)} bars")
        self.logger.info(f"Speed mode: {self.config.speed_mode.value}")
        self.logger.info(f"Initial capital: ${self.config.initial_capital:,.2f}")
        
        self.start_time = time.time()
        self.total_bars = len(data)
        
        # Calculate indicators if provided
        if indicators:
            self.logger.info(f"Calculating {len(indicators)} indicators...")
            for indicator in indicators:
                try:
                    data = indicator.calculate(data)
                except Exception as e:
                    self.logger.error(f"Indicator calculation failed: {e}")
        
        # Choose execution mode
        if self.config.speed_mode == SpeedMode.FAST:
            results = self._run_fast(data, progress_callback)
        else:
            results = self._run_slow(data, progress_callback)
        
        # Close any remaining open positions at end of backtest
        if self.positions:
            last_bar = data.iloc[-1]
            last_timestamp = data.index[-1]
            self.logger.info(f"Closing {len(self.positions)} open positions at backtest end")
            self._close_all_positions(last_timestamp, last_bar['close'], "backtest_end")
            
        # Calculate final metrics
        final_metrics = self.metrics.get_metrics()  # Get current metrics snapshot
        
        elapsed = time.time() - self.start_time
        self.logger.info(f"Backtest completed in {elapsed:.2f} seconds")
        self.logger.info(f"Final equity: ${self.equity:,.2f}")
        self.logger.info(f"Total trades: {len(self.trades)}")
        self.logger.info(f"Win rate: {final_metrics.win_rate*100:.1f}%")
        
        return {
            'config': self.config.to_dict(),
            'equity_curve': self.equity_curve,
            'trades': self.trades,
            'metrics': final_metrics,
            'duration_seconds': elapsed,
            'bars_processed': self.total_bars,
            'bars_per_second': self.total_bars / elapsed if elapsed > 0 else 0,
        }
        
    def _run_fast(
        self,
        data: pd.DataFrame,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """Fast vectorized execution (processes all data at once)."""
        self.logger.info("Running in FAST mode (vectorized)")
        
        # This is a simplified fast mode - processes bar by bar but without delays
        return self._run_slow(data, progress_callback)
        
    def _run_slow(
        self,
        data: pd.DataFrame,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """Slow bar-by-bar execution with optional delays."""
        mode_name = self.config.speed_mode.value.upper()
        self.logger.info(f"Running in {mode_name} mode (bar-by-bar)")
        
        for idx, (timestamp, bar) in enumerate(data.iterrows()):
            self.current_bar_idx = idx
            
            # Progress callback
            if progress_callback and idx % 100 == 0:
                progress_pct = (idx / self.total_bars) * 100
                progress_callback(progress_pct, idx, self.total_bars)
                
            # Apply speed delay
            if self.config.speed_mode == SpeedMode.SLOW and self.config.speed_delay_ms > 0:
                time.sleep(self.config.speed_delay_ms / 1000.0)
            elif self.config.speed_mode == SpeedMode.REALTIME and idx > 0:
                # Calculate actual time difference between bars
                prev_timestamp = data.index[idx - 1]
                actual_delay = (timestamp - prev_timestamp).total_seconds()
                time.sleep(min(actual_delay, 60))  # Cap at 60 seconds
                
            # Update positions (check stops/targets)
            self._update_positions(timestamp, bar)
            
            # Generate signals from strategies
            for strategy in self.strategies:
                try:
                    signal = strategy.on_bar(bar)
                    if signal:
                        self._process_signal(signal, timestamp, bar)
                except Exception as e:
                    self.logger.error(f"Strategy {strategy.name} error: {e}", exc_info=True)
                    
            # Update equity curve
            unrealized = sum(pos.unrealized_pnl(bar['close']) for pos in self.positions.values())
            self.equity = self.cash + unrealized
            self.equity_curve.append((timestamp, self.equity))
            
            # Check margin call
            if self.config.stop_on_margin_call:
                if self.equity < self.config.initial_capital * self.config.margin_call_level:
                    self.logger.warning(f"Margin call at bar {idx}: Equity ${self.equity:.2f}")
                    self._close_all_positions(timestamp, bar['close'], "margin_call")
                    break
                    
        return {}
        
    def _process_signal(self, signal: Signal, timestamp: datetime, bar: pd.Series) -> None:
        """Process trading signal."""
        # Check if we can open more positions
        if len(self.positions) >= self.config.max_positions:
            self.logger.debug(f"Max positions reached, ignoring signal for {signal.symbol}")
            return
            
        # Check if shorting is allowed
        if signal.side == SignalType.SHORT and not self.config.enable_short_selling:
            self.logger.debug("Short selling disabled, ignoring SHORT signal")
            return
            
        # Calculate position size
        size = self._calculate_position_size(signal, bar['close'])
        if size <= 0:
            self.logger.debug(f"Position size zero or negative: {size}")
            return
            
        # Calculate entry price with slippage
        entry_price = self._apply_slippage(bar['close'], signal.side)
        
        # Calculate commission
        commission = size * entry_price * self.config.commission
        
        # Check if we have enough cash
        required_cash = size * entry_price + commission
        if required_cash > self.cash:
            self.logger.debug(f"Insufficient cash for trade: required ${required_cash:.2f}, available ${self.cash:.2f}")
            return
            
        # Open position
        position = Position(
            ticket=self.next_ticket,
            symbol=signal.symbol,
            side=signal.side,
            entry_price=entry_price,
            entry_time=timestamp,
            size=size,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            commission_paid=commission,
            metadata={'strategy': signal.metadata.get('strategy', 'unknown')}
        )
        
        self.positions[self.next_ticket] = position
        self.next_ticket += 1
        
        # Update cash
        self.cash -= required_cash
        
        self.logger.info(f"Opened {signal.side.value} #{position.ticket} @ {entry_price:.2f} size {size:.4f}")
        
    def _update_positions(self, timestamp: datetime, bar: pd.Series) -> None:
        """Update open positions and check for exits."""
        positions_to_close = []
        
        for ticket, pos in self.positions.items():
            current_price = bar['close']
            
            # Check stop loss
            if pos.stop_loss:
                if pos.side == SignalType.LONG and bar['low'] <= pos.stop_loss:
                    positions_to_close.append((ticket, pos.stop_loss, "stop_loss"))
                elif pos.side == SignalType.SHORT and bar['high'] >= pos.stop_loss:
                    positions_to_close.append((ticket, pos.stop_loss, "stop_loss"))
                    
            # Check take profit
            if pos.take_profit:
                if pos.side == SignalType.LONG and bar['high'] >= pos.take_profit:
                    positions_to_close.append((ticket, pos.take_profit, "take_profit"))
                elif pos.side == SignalType.SHORT and bar['low'] <= pos.take_profit:
                    positions_to_close.append((ticket, pos.take_profit, "take_profit"))
                    
        # Close positions
        for ticket, exit_price, reason in positions_to_close:
            self._close_position(ticket, timestamp, exit_price, reason)
            
    def _close_position(
        self,
        ticket: int,
        exit_time: datetime,
        exit_price: float,
        reason: str
    ) -> None:
        """Close a position."""
        if ticket not in self.positions:
            return
            
        pos = self.positions[ticket]
        
        # Apply slippage to exit
        exit_price = self._apply_slippage(exit_price, SignalType.LONG if pos.side == SignalType.SHORT else SignalType.SHORT)
        
        # Calculate P&L
        if pos.side == SignalType.LONG:
            pnl = (exit_price - pos.entry_price) * pos.size
        else:  # SHORT
            pnl = (pos.entry_price - exit_price) * pos.size
            
        # Subtract commissions
        exit_commission = pos.size * exit_price * self.config.commission
        pnl -= (pos.commission_paid + exit_commission)
        
        # Create trade record
        trade = Trade(
            ticket=ticket,
            symbol=pos.symbol,
            side=pos.side,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            entry_time=pos.entry_time,
            exit_time=exit_time,
            size=pos.size,
            pnl=pnl,
            commission=pos.commission_paid + exit_commission,
            exit_reason=reason,
            metadata=pos.metadata
        )
        
        self.trades.append(trade)
        
        # Update cash
        proceeds = pos.size * exit_price - exit_commission
        self.cash += proceeds
        
        # Update metrics
        self.metrics.record_trade(pnl)
        
        # Remove position
        del self.positions[ticket]
        
        self.logger.info(f"Closed #{ticket} @ {exit_price:.2f}: P&L ${pnl:.2f} ({reason})")
        
    def _close_all_positions(self, timestamp: datetime, price: float, reason: str) -> None:
        """Close all open positions."""
        tickets = list(self.positions.keys())
        for ticket in tickets:
            self._close_position(ticket, timestamp, price, reason)
            
    def _calculate_position_size(self, signal: Signal, price: float) -> float:
        """Calculate position size based on risk parameters."""
        # Simple percentage of equity sizing
        risk_amount = self.equity * self.config.position_size_pct
        size = risk_amount / price
        return size
        
    def _apply_slippage(self, price: float, side: SignalType) -> float:
        """Apply slippage to price."""
        if side == SignalType.LONG:
            # Buy at ask (higher)
            return price * (1 + self.config.slippage_pct)
        else:
            # Sell at bid (lower)
            return price * (1 - self.config.slippage_pct)
            
    def get_results_summary(self) -> str:
        """Get human-readable results summary."""
        metrics = self.metrics.get_metrics()
        
        summary = f"""
Backtest Results Summary
========================
Initial Capital: ${self.config.initial_capital:,.2f}
Final Equity: ${self.equity:,.2f}
Net Profit: ${self.equity - self.config.initial_capital:,.2f}
Return: {((self.equity / self.config.initial_capital) - 1) * 100:.2f}%

Total Trades: {metrics.total_trades}
Winning Trades: {metrics.winning_trades}
Losing Trades: {metrics.losing_trades}
Win Rate: {metrics.win_rate * 100:.1f}%

Average Win: ${metrics.avg_win:.2f}
Average Loss: ${metrics.avg_loss:.2f}
Profit Factor: {metrics.profit_factor or 0:.2f}

Max Drawdown: {metrics.max_drawdown_pct * 100:.2f}%
Sharpe Ratio: {metrics.sharpe_ratio:.2f}

Duration: {self.total_bars} bars
Speed: {self.config.speed_mode.value}
"""
        return summary
