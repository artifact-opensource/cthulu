#!/usr/bin/env python3
"""
ML Training Data Generator via Backtesting

Runs backtests on historical data to generate trade outcome data
for ML model training. Outputs data in formats suitable for 
supervised learning (classification for direction, regression for PnL).

Usage:
    python scripts/generate_training_data.py --symbol XAUUSD --days 90
    python scripts/generate_training_data.py --symbol EURUSD --days 180 --output data/training
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import json
import gzip
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

import pandas as pd
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("cthulu.training_generator")


def generate_synthetic_data(num_bars: int = 5000, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic market data with realistic patterns for testing."""
    np.random.seed(seed)
    dates = pd.date_range('2024-01-01', periods=num_bars, freq='h')
    
    # Multi-regime price path
    trend = np.zeros(num_bars)
    regime_length = num_bars // 5
    
    for i in range(5):
        start = i * regime_length
        end = min((i + 1) * regime_length, num_bars)
        if i % 2 == 0:
            # Trending up
            trend[start:end] = np.linspace(0, 10, end - start) + np.random.randn(end - start).cumsum() * 0.1
        else:
            # Trending down or sideways
            trend[start:end] = np.linspace(0, -5, end - start) + np.random.randn(end - start).cumsum() * 0.1
    
    # Base price with trend and noise
    base = 100 + np.cumsum(trend) / 10 + np.random.randn(num_bars).cumsum() * 0.5
    base = np.maximum(base, 50)  # Ensure positive
    
    data = pd.DataFrame({
        'open': base * (1 + np.random.randn(num_bars) * 0.002),
        'high': base * (1 + np.abs(np.random.randn(num_bars) * 0.008)),
        'low': base * (1 - np.abs(np.random.randn(num_bars) * 0.008)),
        'close': base,
        'volume': np.random.randint(10000, 100000, num_bars),
    }, index=dates)
    
    # Fix OHLC relationships
    data['high'] = data[['open', 'close', 'high']].max(axis=1)
    data['low'] = data[['open', 'close', 'low']].min(axis=1)
    
    return data


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate indicators needed for ML features."""
    # SMA
    for period in [10, 20, 50]:
        df[f'sma_{period}'] = df['close'].rolling(window=period).mean()
    
    # EMA
    for period in [5, 10, 20]:
        df[f'ema_{period}'] = df['close'].ewm(span=period, adjust=False).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # ATR
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(window=14).mean()
    
    # MACD
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp1 - exp2
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    
    # ADX (simplified)
    df['adx'] = 25 + np.random.randn(len(df)) * 10  # Placeholder
    
    # Bollinger Bands
    df['bb_middle'] = df['close'].rolling(window=20).mean()
    df['bb_std'] = df['close'].rolling(window=20).std()
    df['bb_upper'] = df['bb_middle'] + 2 * df['bb_std']
    df['bb_lower'] = df['bb_middle'] - 2 * df['bb_std']
    
    # Volume ratio
    df['volume_sma'] = df['volume'].rolling(window=20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_sma']
    
    # Price momentum
    df['momentum_5'] = df['close'].pct_change(5)
    df['momentum_10'] = df['close'].pct_change(10)
    
    return df.dropna()


def run_backtest_for_training(
    data: pd.DataFrame,
    initial_capital: float = 10000,
    position_size_pct: float = 0.02
) -> List[Dict[str, Any]]:
    """
    Run a simple backtest and return trade records for training.
    
    Returns list of completed trades with full feature context.
    """
    from backtesting import BacktestEngine, BacktestConfig, SpeedMode
    from backtesting.engine import Trade
    from strategy.base import Strategy, Signal, SignalType
    
    class MultiStrategyTrainer(Strategy):
        """Strategy that generates signals based on multiple conditions for diverse training data."""
        
        def __init__(self):
            super().__init__('MultiTrainer', {})
            self.bar_count = 0
            
        def on_bar(self, bar):
            self.bar_count += 1
            
            # Generate signals frequently for training data volume
            if self.bar_count < 30 or self.bar_count % 5 != 0:
                return None
            
            signal = None
            confidence = 0.5
            reason = ""
            
            close = bar.get('close', 0) if isinstance(bar, dict) else bar['close']
            rsi = bar.get('rsi', 50) if isinstance(bar, dict) else bar.get('rsi', 50)
            
            # Strategy 1: RSI extremes
            if rsi < 35:
                signal = SignalType.LONG
                confidence = 0.3 + (35 - rsi) / 100
                reason = f"RSI oversold ({rsi:.1f})"
            elif rsi > 65:
                signal = SignalType.SHORT
                confidence = 0.3 + (rsi - 65) / 100
                reason = f"RSI overbought ({rsi:.1f})"
            
            # Strategy 2: EMA crossover (override if stronger)
            ema_5 = bar.get('ema_5', 0) if isinstance(bar, dict) else bar.get('ema_5', 0)
            ema_20 = bar.get('ema_20', 0) if isinstance(bar, dict) else bar.get('ema_20', 0)
            if ema_5 and ema_20:
                if ema_5 > ema_20 * 1.002:
                    signal = SignalType.LONG
                    confidence = 0.55
                    reason = "EMA bullish crossover"
                elif ema_5 < ema_20 * 0.998:
                    signal = SignalType.SHORT
                    confidence = 0.55
                    reason = "EMA bearish crossover"
            
            # Strategy 3: Momentum breakout
            momentum = bar.get('momentum_5', 0) if isinstance(bar, dict) else bar.get('momentum_5', 0)
            if momentum > 0.02:
                signal = SignalType.LONG
                confidence = 0.6
                reason = "Strong positive momentum"
            elif momentum < -0.02:
                signal = SignalType.SHORT
                confidence = 0.6
                reason = "Strong negative momentum"
            
            if signal is None:
                return None
            
            # Calculate stop/target based on ATR with tighter levels for more trades
            atr = bar.get('atr', close * 0.01) if isinstance(bar, dict) else bar.get('atr', close * 0.01)
            if atr is None or atr == 0:
                atr = close * 0.01
                
            if signal == SignalType.LONG:
                sl = close - atr * 1.5  # Tighter SL
                tp = close + atr * 2.0  # Closer TP
            else:
                sl = close + atr * 1.5
                tp = close - atr * 2.0
            
            return Signal(
                id=f'train_{self.bar_count}',
                timestamp=bar.name if hasattr(bar, 'name') else None,
                symbol='TRAIN',
                timeframe='H1',
                side=signal,
                action='buy' if signal == SignalType.LONG else 'sell',
                price=close,
                stop_loss=sl,
                take_profit=tp,
                confidence=confidence,
                reason=reason,
                metadata={
                    'rsi': rsi,
                    'ema_5': ema_5,
                    'ema_20': ema_20,
                    'atr': atr,
                    'macd': bar.get('macd', 0) if isinstance(bar, dict) else bar.get('macd', 0),
                    'volume_ratio': bar.get('volume_ratio', 1) if isinstance(bar, dict) else bar.get('volume_ratio', 1),
                }
            )
    
    # Run backtest
    config = BacktestConfig(
        initial_capital=initial_capital,
        commission=0.0001,
        slippage_pct=0.0002,
        speed_mode=SpeedMode.FAST,
        max_positions=5,  # Allow more concurrent positions
        position_size_pct=position_size_pct,
    )
    
    strategy = MultiStrategyTrainer()
    engine = BacktestEngine(strategies=[strategy], config=config)
    
    logger.info(f"Running backtest on {len(data)} bars...")
    results = engine.run(data)
    
    logger.info(f"Backtest complete: {len(engine.trades)} trades")
    
    # Convert trades to training records
    training_records = []
    for trade in engine.trades:
        # Get the bar data at entry time to capture features
        try:
            if trade.entry_time in data.index:
                entry_bar = data.loc[trade.entry_time]
            else:
                # Find nearest bar
                nearest = data.index[data.index <= trade.entry_time]
                if len(nearest) > 0:
                    entry_bar = data.loc[nearest[-1]]
                else:
                    entry_bar = {}
        except Exception:
            entry_bar = {}
        
        outcome = 'WIN' if trade.pnl > 0 else ('LOSS' if trade.pnl < 0 else 'BREAKEVEN')
        duration_seconds = (trade.exit_time - trade.entry_time).total_seconds()
        
        # Helper to safely get values
        def get_val(bar, key, default=0):
            if isinstance(bar, dict):
                return bar.get(key, default)
            return getattr(bar, key, default) if hasattr(bar, key) else default
        
        record = {
            # Trade outcome (target for ML)
            'outcome': outcome,
            'pnl': trade.pnl,
            'pnl_pct': (trade.pnl / (trade.entry_price * trade.size)) * 100 if trade.entry_price and trade.size else 0,
            
            # Trade details
            'ticket': trade.ticket,
            'symbol': trade.symbol,
            'side': trade.side.value if hasattr(trade.side, 'value') else str(trade.side),
            'entry_price': trade.entry_price,
            'exit_price': trade.exit_price,
            'entry_time': trade.entry_time.isoformat(),
            'exit_time': trade.exit_time.isoformat(),
            'duration_seconds': duration_seconds,
            'exit_reason': trade.exit_reason,
            
            # Market features at entry (from bar data)
            'rsi': get_val(entry_bar, 'rsi', 50),
            'atr': get_val(entry_bar, 'atr', 0),
            'macd': get_val(entry_bar, 'macd', 0),
            'macd_signal': get_val(entry_bar, 'macd_signal', 0),
            'adx': get_val(entry_bar, 'adx', 25),
            'bb_upper': get_val(entry_bar, 'bb_upper', 0),
            'bb_lower': get_val(entry_bar, 'bb_lower', 0),
            'volume_ratio': get_val(entry_bar, 'volume_ratio', 1),
            'momentum_5': get_val(entry_bar, 'momentum_5', 0),
            'momentum_10': get_val(entry_bar, 'momentum_10', 0),
            
            # From trade metadata
            'strategy_confidence': trade.metadata.get('confidence', 0.5) if trade.metadata else 0.5,
        }
        
        training_records.append(record)
    
    return training_records


def save_training_data(records: List[Dict[str, Any]], output_path: Path, compress: bool = True):
    """Save training data to JSONL file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    if compress:
        with gzip.open(str(output_path) + '.gz', 'wt', encoding='utf-8') as f:
            for record in records:
                f.write(json.dumps(record, default=str) + '\n')
        logger.info(f"Saved {len(records)} records to {output_path}.gz")
    else:
        with open(output_path, 'w', encoding='utf-8') as f:
            for record in records:
                f.write(json.dumps(record, default=str) + '\n')
        logger.info(f"Saved {len(records)} records to {output_path}")
    
    # Also save as CSV for easy analysis
    csv_path = output_path.with_suffix('.csv')
    df = pd.DataFrame(records)
    df.to_csv(csv_path, index=False)
    logger.info(f"Saved CSV summary to {csv_path}")


def print_summary(records: List[Dict[str, Any]]):
    """Print summary statistics of training data."""
    if not records:
        logger.warning("No records to summarize")
        return
    
    df = pd.DataFrame(records)
    
    print("\n" + "="*60)
    print("TRAINING DATA SUMMARY")
    print("="*60)
    
    print(f"\nTotal trades: {len(df)}")
    print(f"Wins: {len(df[df['outcome'] == 'WIN'])} ({len(df[df['outcome'] == 'WIN'])/len(df)*100:.1f}%)")
    print(f"Losses: {len(df[df['outcome'] == 'LOSS'])} ({len(df[df['outcome'] == 'LOSS'])/len(df)*100:.1f}%)")
    print(f"Breakeven: {len(df[df['outcome'] == 'BREAKEVEN'])}")
    
    print(f"\nP&L Statistics:")
    print(f"  Total P&L: ${df['pnl'].sum():.2f}")
    print(f"  Mean P&L: ${df['pnl'].mean():.2f}")
    print(f"  Median P&L: ${df['pnl'].median():.2f}")
    print(f"  Std Dev: ${df['pnl'].std():.2f}")
    print(f"  Best trade: ${df['pnl'].max():.2f}")
    print(f"  Worst trade: ${df['pnl'].min():.2f}")
    
    print(f"\nDuration Statistics:")
    print(f"  Mean: {df['duration_seconds'].mean()/3600:.1f} hours")
    print(f"  Median: {df['duration_seconds'].median()/3600:.1f} hours")
    
    print(f"\nExit Reasons:")
    for reason, count in df['exit_reason'].value_counts().items():
        print(f"  {reason}: {count} ({count/len(df)*100:.1f}%)")
    
    print("\nFeature Statistics (at entry):")
    for col in ['rsi', 'atr', 'macd', 'adx', 'volume_ratio']:
        if col in df.columns:
            print(f"  {col}: mean={df[col].mean():.2f}, std={df[col].std():.2f}")
    
    print("="*60 + "\n")


def main():
    parser = argparse.ArgumentParser(description='Generate ML training data via backtesting')
    parser.add_argument('--symbol', default='SYNTHETIC', help='Symbol to backtest')
    parser.add_argument('--bars', type=int, default=5000, help='Number of bars of data')
    parser.add_argument('--output', default='data/training', help='Output directory')
    parser.add_argument('--no-compress', action='store_true', help='Disable gzip compression')
    parser.add_argument('--seed', type=int, default=42, help='Random seed for synthetic data')
    
    args = parser.parse_args()
    
    logger.info(f"Generating training data for {args.symbol} ({args.bars} bars)")
    
    # Generate or load data
    if args.symbol == 'SYNTHETIC':
        logger.info("Generating synthetic market data...")
        data = generate_synthetic_data(num_bars=args.bars, seed=args.seed)
    else:
        # TODO: Load real historical data from MT5 or files
        logger.warning(f"Real data loading not implemented, using synthetic for {args.symbol}")
        data = generate_synthetic_data(num_bars=args.bars, seed=args.seed)
    
    # Calculate indicators
    logger.info("Calculating indicators...")
    data = calculate_indicators(data)
    logger.info(f"Data prepared: {len(data)} bars with {len(data.columns)} columns")
    
    # Run backtest
    records = run_backtest_for_training(data)
    
    # Print summary
    print_summary(records)
    
    # Save data
    if records:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = Path(args.output) / f'training_data_{args.symbol}_{timestamp}.jsonl'
        save_training_data(records, output_path, compress=not args.no_compress)
    else:
        logger.warning("No trades generated - try adjusting strategy parameters")
    
    return 0 if records else 1


if __name__ == '__main__':
    sys.exit(main())
