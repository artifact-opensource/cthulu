"""
Simple Moving Average Crossover Strategy

Implementation of SMA crossover strategy.
Entry on crossovers, exit on opposite signals or stop loss/take profit.
"""

import pandas as pd
from cthulu.connector.mt5_connector import mt5
from typing import Optional, Dict, Any
from datetime import datetime

from cthulu.strategy.base import Strategy, Signal, SignalType


class SmaCrossover(Strategy):
    """
    Simple Moving Average Crossover Strategy.
    
    Generates LONG signal when short SMA crosses above long SMA.
    Generates SHORT signal when short SMA crosses below long SMA.
    
    Configuration:
        short_window: Fast SMA period (default: 20)
        long_window: Slow SMA period (default: 50)
        atr_period: ATR period for stop loss (default: 14)
        atr_multiplier: ATR multiplier for SL (default: 2.0)
        risk_reward_ratio: Risk/reward ratio (default: 2.0)
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize SMA crossover strategy."""
        super().__init__("sma_crossover", config)
        
        # Strategy parameters
        # Accept legacy aliases: fast_period, slow_period
        self.short_window = config.get('short_window', config.get('fast_period', 20))
        self.long_window = config.get('long_window', config.get('slow_period', 50))
        self.atr_period = config.get('atr_period', config.get('atr', 14))
        self.atr_multiplier = config.get('atr_multiplier', 2.0)
        self.risk_reward_ratio = config.get('risk_reward_ratio', 2.0)
        
        # State
        self._state = {
            'last_signal': None,
            'last_crossover': None,
            'sma_short': None,
            'sma_long': None,
            'atr': None
        }
        
        self.logger.info(
            f"SMA Crossover initialized: short={self.short_window}, "
            f"long={self.long_window}, atr={self.atr_period}"
        )
        
    def on_bar(self, bar: pd.Series) -> Optional[Signal]:
        """
        Process new bar and check for crossover.
        
        Args:
            bar: Latest bar with indicators
            
        Returns:
            Signal if crossover detected, None otherwise
        """
        # Need SMA values
        sma_short_col = f'sma_{self.short_window}'
        sma_long_col = f'sma_{self.long_window}'
        
        if sma_short_col not in bar or sma_long_col not in bar:
            self.logger.warning("SMA indicators not found in bar data")
            return None
            
        if 'atr' not in bar:
            self.logger.warning("ATR indicator not found in bar data")
            return None
            
        # Get current values
        sma_short = bar[sma_short_col]
        sma_long = bar[sma_long_col]
        atr = bar['atr']
        close = bar['close']
        
        # Update state
        prev_short = self._state['sma_short']
        prev_long = self._state['sma_long']
        
        self._state['sma_short'] = sma_short
        self._state['sma_long'] = sma_long
        self._state['atr'] = atr
        
        # Need previous values to detect crossover
        if prev_short is None or prev_long is None:
            return None
            
        # Check for bullish crossover
        if prev_short <= prev_long and sma_short > sma_long:
            signal = self._create_long_signal(close, atr, bar)
            if self.validate_signal(signal):
                self._state['last_signal'] = SignalType.LONG
                self._state['last_crossover'] = datetime.now()
                return signal
                
        # Check for bearish crossover
        elif prev_short >= prev_long and sma_short < sma_long:
            signal = self._create_short_signal(close, atr, bar)
            if self.validate_signal(signal):
                self._state['last_signal'] = SignalType.SHORT
                self._state['last_crossover'] = datetime.now()
                return signal
                
        return None
        
    def _create_long_signal(self, price: float, atr: float, bar: pd.Series) -> Signal:
        """Create LONG signal with calculated SL/TP."""
        # Calculate stop loss
        stop_loss = price - (atr * self.atr_multiplier)
        
        # Calculate take profit
        risk = price - stop_loss
        take_profit = price + (risk * self.risk_reward_ratio)
        
        return Signal(
            id=self.generate_signal_id(),
            timestamp=bar.name,
            symbol=self.config.get('params', {}).get('symbol', 'UNKNOWN'),
            timeframe=self.config.get('timeframe', '1H'),
            side=SignalType.LONG,
            action='BUY',
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=0.7,
            reason=f"SMA crossover: {self.short_window} crossed above {self.long_window}",
            metadata={
                'sma_short': float(self._state['sma_short']),
                'sma_long': float(self._state['sma_long']),
                'atr': float(atr),
                'risk': float(risk),
                'reward': float(risk * self.risk_reward_ratio)
            }
        )
        
    def _create_short_signal(self, price: float, atr: float, bar: pd.Series) -> Signal:
        """Create SHORT signal with calculated SL/TP."""
        # Calculate stop loss
        stop_loss = price + (atr * self.atr_multiplier)
        
        # Calculate take profit
        risk = stop_loss - price
        take_profit = price - (risk * self.risk_reward_ratio)
        
        return Signal(
            id=self.generate_signal_id(),
            timestamp=bar.name,
            symbol=self.config.get('params', {}).get('symbol', 'UNKNOWN'),
            timeframe=self.config.get('timeframe', '1H'),
            side=SignalType.SHORT,
            action='SELL',
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=0.7,
            reason=f"SMA crossover: {self.short_window} crossed below {self.long_window}",
            metadata={
                'sma_short': float(self._state['sma_short']),
                'sma_long': float(self._state['sma_long']),
                'atr': float(atr),
                'risk': float(risk),
                'reward': float(risk * self.risk_reward_ratio)
            }
        )




