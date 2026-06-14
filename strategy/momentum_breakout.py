"""
Momentum Breakout Strategy

Captures strong directional moves by detecting breakouts with momentum confirmation.
Optimized for aggressive day trading and trend-following.
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, Any
from datetime import datetime

from cthulu.strategy.base import Strategy, Signal, SignalType


class MomentumBreakout(Strategy):
    """
    Momentum Breakout Strategy.
    
    Identifies breakouts from consolidation zones with strong momentum confirmation.
    Uses RSI, ATR, and volume for validation. Aggressive entries with tight stops.
    
    Configuration:
        lookback_period: Period for high/low breakout (default: 20)
        rsi_threshold: RSI threshold for momentum (default: 55)
        atr_multiplier: ATR multiplier for SL (default: 1.5)
        volume_multiplier: Volume spike threshold (default: 1.5)
        risk_reward_ratio: Risk/reward ratio (default: 3.0)
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize momentum breakout strategy."""
        super().__init__("momentum_breakout", config)
        
        # Strategy parameters
        self.lookback_period = config.get('params', {}).get('lookback_period', 20)
        self.rsi_threshold = config.get('params', {}).get('rsi_threshold', 55)
        self.atr_multiplier = config.get('params', {}).get('atr_multiplier', 1.5)
        self.volume_multiplier = config.get('params', {}).get('volume_multiplier', 1.5)
        self.risk_reward_ratio = config.get('params', {}).get('risk_reward_ratio', 3.0)
        
        # State
        self._state = {
            'last_signal': None,
            'last_breakout': None,
            'recent_high': None,
            'recent_low': None,
            'avg_volume': None
        }
        
        self.logger.info(
            f"Momentum Breakout initialized: lookback={self.lookback_period}, "
            f"rsi_threshold={self.rsi_threshold}"
        )
        
    def on_bar(self, bar: pd.Series) -> Optional[Signal]:
        """
        Process new bar and check for breakout.
        
        Args:
            bar: Latest bar with indicators
            
        Returns:
            Signal if breakout detected, None otherwise
        """
        # Need indicators
        if 'rsi' not in bar or 'atr' not in bar or 'volume' not in bar:
            self.logger.warning("Required indicators not found in bar data")
            return None
            
        # Need historical data for breakout detection
        if f'high_{self.lookback_period}' not in bar or f'low_{self.lookback_period}' not in bar:
            self.logger.warning(f"Lookback period data not found")
            return None
        
        # Try to find RSI column (default or with period)
        rsi_col = 'rsi' if 'rsi' in bar else 'rsi_14'
        if rsi_col not in bar:
            self.logger.warning("RSI indicator not found")
            return None
            
        close = bar['close']
        high = bar['high']
        low = bar['low']
        rsi = bar[rsi_col]
        atr = bar['atr']
        volume = bar['volume']
        
        # Get recent high/low
        recent_high = bar[f'high_{self.lookback_period}']
        recent_low = bar[f'low_{self.lookback_period}']
        avg_volume = bar.get(f'volume_avg_{self.lookback_period}', volume)
        
        # Update state
        self._state['recent_high'] = recent_high
        self._state['recent_low'] = recent_low
        self._state['avg_volume'] = avg_volume
        
        # Check for bullish breakout
        if (high > recent_high and 
            rsi > self.rsi_threshold and 
            volume > avg_volume * self.volume_multiplier):
            
            signal = self._create_long_signal(close, atr, bar)
            if self.validate_signal(signal):
                self._state['last_signal'] = SignalType.LONG
                self._state['last_breakout'] = datetime.now()
                return signal
                
        # Check for bearish breakout
        elif (low < recent_low and 
              rsi < (100 - self.rsi_threshold) and 
              volume > avg_volume * self.volume_multiplier):
            
            signal = self._create_short_signal(close, atr, bar)
            if self.validate_signal(signal):
                self._state['last_signal'] = SignalType.SHORT
                self._state['last_breakout'] = datetime.now()
                return signal
                
        return None
        
    def _create_long_signal(self, price: float, atr: float, bar: pd.Series) -> Signal:
        """Create LONG signal for bullish breakout."""
        # Stop below recent low or ATR-based
        recent_low = self._state['recent_low']
        atr_stop = price - (atr * self.atr_multiplier)
        stop_loss = max(recent_low - (atr * 0.5), atr_stop)
        
        # Aggressive take profit
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
            confidence=0.80,  # High confidence on confirmed breakout
            reason=f"Bullish momentum breakout above {self._state['recent_high']:.5f}",
            metadata={
                'breakout_level': float(self._state['recent_high']),
                'rsi': float(bar['rsi']),
                'volume_ratio': float(bar['volume'] / self._state['avg_volume']),
                'atr': float(atr),
                'risk': float(risk),
                'reward': float(risk * self.risk_reward_ratio),
                'strategy_type': 'aggressive_breakout'
            }
        )
        
    def _create_short_signal(self, price: float, atr: float, bar: pd.Series) -> Signal:
        """Create SHORT signal for bearish breakout."""
        # Stop above recent high or ATR-based
        recent_high = self._state['recent_high']
        atr_stop = price + (atr * self.atr_multiplier)
        stop_loss = min(recent_high + (atr * 0.5), atr_stop)
        
        # Aggressive take profit
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
            confidence=0.80,  # High confidence on confirmed breakout
            reason=f"Bearish momentum breakout below {self._state['recent_low']:.5f}",
            metadata={
                'breakout_level': float(self._state['recent_low']),
                'rsi': float(bar['rsi']),
                'volume_ratio': float(bar['volume'] / self._state['avg_volume']),
                'atr': float(atr),
                'risk': float(risk),
                'reward': float(risk * self.risk_reward_ratio),
                'strategy_type': 'aggressive_breakout'
            }
        )




