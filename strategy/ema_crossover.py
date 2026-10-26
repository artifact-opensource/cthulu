"""
Exponential Moving Average Crossover Strategy

High-speed crossover strategy using EMA for faster reaction to price changes.
Optimized for day trading with quicker signals than SMA.
"""

import pandas as pd
from typing import Optional, Dict, Any
from datetime import datetime

from cthulu.strategy.base import Strategy, Signal, SignalType


class EmaCrossover(Strategy):
    """
    Exponential Moving Average Crossover Strategy.
    
    Generates faster signals than SMA crossover due to EMA's exponential weighting.
    Ideal for day trading and scalping with quicker response to price movements.
    
    Configuration:
        fast_period: Fast EMA period (default: 9)
        slow_period: Slow EMA period (default: 21)
        atr_period: ATR period for stop loss (default: 14)
        atr_multiplier: ATR multiplier for SL (default: 1.5, tighter than SMA)
        risk_reward_ratio: Risk/reward ratio (default: 2.5)
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize EMA crossover strategy."""
        super().__init__("ema_crossover", config)
        
        # Strategy parameters - optimized for day trading
        self.fast_period = config.get('params', {}).get('fast_period', 9)
        self.slow_period = config.get('params', {}).get('slow_period', 21)
        self.atr_period = config.get('params', {}).get('atr_period', 14)
        self.atr_multiplier = config.get('params', {}).get('atr_multiplier', 1.5)
        self.risk_reward_ratio = config.get('params', {}).get('risk_reward_ratio', 2.5)
        
        # State
        self._state = {
            'last_signal': None,
            'last_crossover': None,
            'ema_fast': None,
            'ema_slow': None,
            'atr': None
        }
        
        self.logger.info(
            f"EMA Crossover initialized: fast={self.fast_period}, "
            f"slow={self.slow_period}, atr={self.atr_period}"
        )
        
    def on_bar(self, bar: pd.Series) -> Optional[Signal]:
        """
        Process new bar and check for crossover OR trend continuation.
        
        Enhanced to generate trend continuation signals when:
        - EMAs are already crossed (trend established)
        - Pullback to fast EMA occurs (re-entry opportunity)
        - Strong EMA separation with momentum confirmation
        
        Args:
            bar: Latest bar with indicators
            
        Returns:
            Signal if crossover or continuation detected, None otherwise
        """
        # Need EMA values
        ema_fast_col = f'ema_{self.fast_period}'
        ema_slow_col = f'ema_{self.slow_period}'
        
        if ema_fast_col not in bar or ema_slow_col not in bar:
            self.logger.warning("EMA indicators not found in bar data")
            return None
            
        if 'atr' not in bar:
            self.logger.warning("ATR indicator not found in bar data")
            return None
            
        # Get current values
        ema_fast = bar[ema_fast_col]
        ema_slow = bar[ema_slow_col]
        atr = bar['atr']
        close = bar['close']
        low = bar.get('low', close)
        high = bar.get('high', close)
        
        # Update state
        prev_fast = self._state['ema_fast']
        prev_slow = self._state['ema_slow']
        
        self._state['ema_fast'] = ema_fast
        self._state['ema_slow'] = ema_slow
        self._state['atr'] = atr
        
        # Track pullback state
        if 'pullback_bars' not in self._state:
            self._state['pullback_bars'] = 0
            self._state['in_uptrend'] = False
            self._state['in_downtrend'] = False
            self._state['continuation_cooldown'] = 0
        
        # Reduce continuation cooldown
        if self._state['continuation_cooldown'] > 0:
            self._state['continuation_cooldown'] -= 1
        
        # Need previous values to detect crossover
        if prev_fast is None or prev_slow is None:
            return None
        
        # Calculate EMA separation as percentage
        ema_separation = abs(ema_fast - ema_slow) / ema_slow if ema_slow > 0 else 0
        ema_separation_pct = ema_separation * 100
        
        # Determine trend state
        self._state['in_uptrend'] = ema_fast > ema_slow
        self._state['in_downtrend'] = ema_fast < ema_slow
            
        # === PRIMARY: Check for bullish crossover ===
        if prev_fast <= prev_slow and ema_fast > ema_slow:
            signal = self._create_long_signal(close, atr, bar, reason_type="crossover")
            if self.validate_signal(signal):
                self._state['last_signal'] = SignalType.LONG
                self._state['last_crossover'] = datetime.now()
                self._state['pullback_bars'] = 0
                self._state['continuation_cooldown'] = 5  # Cooldown after crossover
                return signal
                
        # === PRIMARY: Check for bearish crossover ===
        elif prev_fast >= prev_slow and ema_fast < ema_slow:
            signal = self._create_short_signal(close, atr, bar, reason_type="crossover")
            if self.validate_signal(signal):
                self._state['last_signal'] = SignalType.SHORT
                self._state['last_crossover'] = datetime.now()
                self._state['pullback_bars'] = 0
                self._state['continuation_cooldown'] = 5
                return signal
        
        # === SECONDARY: Trend continuation signals (pullback entries) ===
        # Only if cooldown expired and trend is established
        if self._state['continuation_cooldown'] == 0 and ema_separation_pct > 0.1:
            
            # Uptrend continuation: price pulls back to fast EMA and bounces
            if self._state['in_uptrend']:
                # Price touched or crossed below fast EMA
                price_near_fast_ema = low <= ema_fast * 1.002  # Within 0.2%
                price_above_slow_ema = close > ema_slow
                
                if price_near_fast_ema and price_above_slow_ema and close > ema_fast:
                    # Pullback bounce detected
                    signal = self._create_long_signal(close, atr, bar, reason_type="continuation", 
                                                      confidence_adj=-0.1)  # Slightly lower confidence
                    if self.validate_signal(signal):
                        self._state['last_signal'] = SignalType.LONG
                        self._state['continuation_cooldown'] = 8  # Longer cooldown for continuation
                        self.logger.info(f"EMA continuation LONG: pullback bounce at {close:.2f}, fast EMA={ema_fast:.2f}")
                        return signal
            
            # Downtrend continuation: price pulls back to fast EMA and rejects
            elif self._state['in_downtrend']:
                # Price touched or crossed above fast EMA
                price_near_fast_ema = high >= ema_fast * 0.998  # Within 0.2%
                price_below_slow_ema = close < ema_slow
                
                if price_near_fast_ema and price_below_slow_ema and close < ema_fast:
                    # Pullback rejection detected
                    signal = self._create_short_signal(close, atr, bar, reason_type="continuation",
                                                       confidence_adj=-0.1)
                    if self.validate_signal(signal):
                        self._state['last_signal'] = SignalType.SHORT
                        self._state['continuation_cooldown'] = 8
                        self.logger.info(f"EMA continuation SHORT: pullback rejection at {close:.2f}, fast EMA={ema_fast:.2f}")
                        return signal
                
        return None
        
    def _create_long_signal(self, price: float, atr: float, bar: pd.Series, 
                             reason_type: str = "crossover", confidence_adj: float = 0.0) -> Signal:
        """Create LONG signal with calculated SL/TP."""
        # Tighter stop loss for day trading
        stop_loss = price - (atr * self.atr_multiplier)
        
        # Calculate take profit
        risk = price - stop_loss
        take_profit = price + (risk * self.risk_reward_ratio)
        
        reason = (f"EMA crossover: {self.fast_period} crossed above {self.slow_period}" 
                  if reason_type == "crossover" 
                  else f"EMA continuation: pullback bounce to {self.fast_period} EMA")
        
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
            confidence=max(0.5, 0.75 + confidence_adj),  # Base or adjusted confidence
            reason=reason,
            metadata={
                'ema_fast': float(self._state['ema_fast']),
                'ema_slow': float(self._state['ema_slow']),
                'atr': float(atr),
                'risk': float(risk),
                'reward': float(risk * self.risk_reward_ratio),
                'strategy_type': 'day_trading',
                'signal_type': reason_type
            }
        )
        
    def _create_short_signal(self, price: float, atr: float, bar: pd.Series,
                              reason_type: str = "crossover", confidence_adj: float = 0.0) -> Signal:
        """Create SHORT signal with calculated SL/TP."""
        # Tighter stop loss for day trading
        stop_loss = price + (atr * self.atr_multiplier)
        
        # Calculate take profit
        risk = stop_loss - price
        take_profit = price - (risk * self.risk_reward_ratio)
        
        reason = (f"EMA crossover: {self.fast_period} crossed below {self.slow_period}"
                  if reason_type == "crossover"
                  else f"EMA continuation: pullback rejection at {self.fast_period} EMA")
        
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
            confidence=max(0.5, 0.75 + confidence_adj),
            reason=reason,
            metadata={
                'ema_fast': float(self._state['ema_fast']),
                'ema_slow': float(self._state['ema_slow']),
                'atr': float(atr),
                'risk': float(risk),
                'reward': float(risk * self.risk_reward_ratio),
                'strategy_type': 'day_trading',
                'signal_type': reason_type
            }
        )




