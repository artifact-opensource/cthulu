"""
RSI Reversal Strategy

Ultra-aggressive strategy that trades purely based on RSI extremes.
Designed for volatile markets where price oscillates rapidly.
Does NOT require crossover events - trades immediately on extreme RSI levels.
"""

import pandas as pd
from typing import Optional, Dict, Any
from datetime import datetime

from cthulu.strategy.base import Strategy, Signal, SignalType


class RsiReversalStrategy(Strategy):
    """
    RSI Reversal Strategy - Pure RSI-based trading.
    
    Generates signals when RSI reaches extreme levels, anticipating reversals.
    More aggressive than crossover-based strategies for active trading.
    
    Configuration:
        rsi_period: RSI period (default: 14)
        rsi_extreme_oversold: Extreme oversold level for LONG (default: 20)
        rsi_extreme_overbought: Extreme overbought level for SHORT (default: 80)
        atr_multiplier: ATR multiplier for SL (default: 1.5)
        risk_reward_ratio: Risk/reward ratio (default: 2.0)
        cooldown_bars: Minimum bars between signals (default: 3)
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize RSI reversal strategy."""
        super().__init__("rsi_reversal", config)
        
        # Strategy parameters - aggressive settings
        self.rsi_period = config.get('params', {}).get('rsi_period', 14)
        self.rsi_extreme_oversold = config.get('params', {}).get('rsi_extreme_oversold', 20)
        self.rsi_extreme_overbought = config.get('params', {}).get('rsi_extreme_overbought', 80)
        self.atr_multiplier = config.get('params', {}).get('atr_multiplier', 1.5)
        self.risk_reward_ratio = config.get('params', {}).get('risk_reward_ratio', 2.0)
        self.cooldown_bars = config.get('params', {}).get('cooldown_bars', 3)
        
        # State
        self._state = {
            'last_signal': None,
            'last_signal_time': None,
            'bars_since_signal': 0,
            'prev_rsi': None
        }
        
        self.logger.info(
            f"RSI Reversal Strategy initialized: period={self.rsi_period}, "
            f"oversold={self.rsi_extreme_oversold}, overbought={self.rsi_extreme_overbought}"
        )
        
    def on_bar(self, bar: pd.Series) -> Optional[Signal]:
        """
        Process new bar and check for RSI extreme reversals.
        
        Args:
            bar: Latest bar with indicators
            
        Returns:
            Signal if RSI extreme detected, None otherwise
        """
        # Increment bars counter
        self._state['bars_since_signal'] += 1
        
        # Find RSI column
        rsi_col = f'rsi_{self.rsi_period}' if f'rsi_{self.rsi_period}' in bar else 'rsi'
        
        if rsi_col not in bar:
            self.logger.warning(f"RSI column '{rsi_col}' not found")
            return None
            
        if 'atr' not in bar:
            self.logger.warning("ATR not found in bar")
            return None
            
        # Get current values
        rsi = bar[rsi_col]
        atr = bar['atr']
        close = bar['close']
        prev_rsi = self._state['prev_rsi']
        
        # Update state
        self._state['prev_rsi'] = rsi
        
        # Need previous RSI for reversal detection
        if prev_rsi is None:
            return None
            
        # Check cooldown
        if self._state['bars_since_signal'] < self.cooldown_bars:
            return None
        
        # LONG: RSI was in extreme oversold and is now rising (reversal starting)
        if (prev_rsi <= self.rsi_extreme_oversold and 
            rsi > prev_rsi and 
            rsi < 50):  # Still in lower half, catching the bounce
            
            signal = self._create_long_signal(close, atr, rsi, bar)
            if self.validate_signal(signal):
                self._state['last_signal'] = SignalType.LONG
                self._state['last_signal_time'] = datetime.now()
                self._state['bars_since_signal'] = 0
                self.logger.info(f"LONG signal: RSI reversal from {prev_rsi:.1f} to {rsi:.1f}")
                return signal
                
        # SHORT: RSI was in extreme overbought and is now falling (reversal starting)
        elif (prev_rsi >= self.rsi_extreme_overbought and 
              rsi < prev_rsi and 
              rsi > 50):  # Still in upper half, catching the drop
            
            signal = self._create_short_signal(close, atr, rsi, bar)
            if self.validate_signal(signal):
                self._state['last_signal'] = SignalType.SHORT
                self._state['last_signal_time'] = datetime.now()
                self._state['bars_since_signal'] = 0
                self.logger.info(f"SHORT signal: RSI reversal from {prev_rsi:.1f} to {rsi:.1f}")
                return signal
                
        return None
        
    def _create_long_signal(self, price: float, atr: float, rsi: float, bar: pd.Series) -> Signal:
        """Create LONG signal for RSI oversold reversal."""
        stop_loss = price - (atr * self.atr_multiplier)
        risk = price - stop_loss
        take_profit = price + (risk * self.risk_reward_ratio)
        
        # Get symbol from params, config, or bar index name
        symbol = self.config.get('params', {}).get('symbol') or self.config.get('symbol') or 'BTCUSD#'
        
        return Signal(
            id=self.generate_signal_id(),
            timestamp=bar.name,
            symbol=symbol,
            timeframe=self.config.get('timeframe', 'M15'),
            side=SignalType.LONG,
            action='BUY',
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=0.75,
            reason=f"RSI oversold reversal (RSI={rsi:.1f})",
            metadata={
                'strategy_type': 'rsi_reversal',
                'rsi': float(rsi),
                'prev_rsi': float(self._state['prev_rsi']),
                'atr': float(atr),
                'risk': float(risk),
                'reward': float(risk * self.risk_reward_ratio)
            }
        )
        
    def _create_short_signal(self, price: float, atr: float, rsi: float, bar: pd.Series) -> Signal:
        """Create SHORT signal for RSI overbought reversal."""
        stop_loss = price + (atr * self.atr_multiplier)
        risk = stop_loss - price
        take_profit = price - (risk * self.risk_reward_ratio)
        
        # Get symbol from params, config, or default
        symbol = self.config.get('params', {}).get('symbol') or self.config.get('symbol') or 'BTCUSD#'
        
        return Signal(
            id=self.generate_signal_id(),
            timestamp=bar.name,
            symbol=symbol,
            timeframe=self.config.get('timeframe', 'M15'),
            side=SignalType.SHORT,
            action='SELL',
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=0.75,
            reason=f"RSI overbought reversal (RSI={rsi:.1f})",
            metadata={
                'strategy_type': 'rsi_reversal',
                'rsi': float(rsi),
                'prev_rsi': float(self._state['prev_rsi']),
                'atr': float(atr),
                'risk': float(risk),
                'reward': float(risk * self.risk_reward_ratio)
            }
        )
