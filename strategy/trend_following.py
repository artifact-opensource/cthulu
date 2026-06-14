"""
Trend Following Strategy

Follows established trends using ADX for trend strength confirmation.
Uses moving averages and trend continuation patterns for entries.
"""

import pandas as pd
from typing import Optional, Dict, Any
from datetime import datetime

from cthulu.strategy.base import Strategy, Signal, SignalType


class TrendFollowingStrategy(Strategy):
    """
    Trend Following Strategy using ADX and moving averages.

    Enters on trend continuation signals when ADX confirms trend strength.
    Uses wider stops and longer targets for trend trades.

    Configuration:
        fast_ma: Fast moving average period (default: 20)
        slow_ma: Slow moving average period (default: 50)
        adx_period: ADX period (default: 14)
        adx_threshold: ADX trend strength threshold (default: 25)
        atr_multiplier: ATR multiplier for SL (default: 2.0)
        risk_reward_ratio: Risk/reward ratio (default: 3.0)
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize trend following strategy."""
        super().__init__("trend_following", config)

        # Strategy parameters
        self.fast_ma = config.get('params', {}).get('fast_ma', 20)
        self.slow_ma = config.get('params', {}).get('slow_ma', 50)
        self.adx_period = config.get('params', {}).get('adx_period', 14)
        self.adx_threshold = config.get('params', {}).get('adx_threshold', 25)
        self.atr_multiplier = config.get('params', {}).get('atr_multiplier', 2.0)
        self.risk_reward_ratio = config.get('params', {}).get('risk_reward_ratio', 3.0)

        # State
        self._state = {
            'trend_direction': 0,  # 1 = uptrend, -1 = downtrend, 0 = no trend
            'last_signal': None
        }

        self.logger.info(
            f"Trend Following initialized: MA({self.fast_ma},{self.slow_ma}), "
            f"ADX({self.adx_period}, {self.adx_threshold})"
        )

    def on_bar(self, bar: pd.Series) -> Optional[Signal]:
        """
        Process new bar and check for trend following signals.

        Enhanced to be more aggressive in strong trends - doesn't require
        exact pullback timing, generates signals on strong trend confirmation.

        Args:
            bar: Latest bar with indicators

        Returns:
            Signal if trend continuation setup detected, None otherwise
        """
        # Need required indicators
        required_cols = ['close', 'high', 'low', 'atr']
        if not all(col in bar for col in required_cols):
            return None

        # Check for ADX - try multiple column naming conventions
        adx = None
        for col in [f'adx_{self.adx_period}', 'adx', f'adx_{14}']:
            if col in bar:
                adx = bar[col]
                break
        if adx is None:
            return None

        # Check for moving averages - try EMA first, then SMA
        fast_ma = None
        slow_ma = None
        
        for prefix in ['ema', 'sma']:
            fast_col = f'{prefix}_{self.fast_ma}'
            slow_col = f'{prefix}_{self.slow_ma}'
            if fast_col in bar and fast_ma is None:
                fast_ma = bar[fast_col]
            if slow_col in bar and slow_ma is None:
                slow_ma = bar[slow_col]
        
        if fast_ma is None or slow_ma is None:
            return None

        close = bar['close']
        high = bar['high']
        low = bar['low']
        atr = bar['atr']

        # Check for trend direction and strength
        ma_trend = 1 if fast_ma > slow_ma else -1  # 1 = uptrend, -1 = downtrend
        trend_strength = adx >= self.adx_threshold
        
        # Calculate MA separation percentage
        ma_separation = abs(fast_ma - slow_ma) / slow_ma if slow_ma > 0 else 0
        ma_separation_pct = ma_separation * 100

        # Update trend state
        prev_trend = self._state['trend_direction']
        if trend_strength:
            self._state['trend_direction'] = ma_trend
        else:
            self._state['trend_direction'] = 0
        
        # Track signal cooldown
        if 'cooldown' not in self._state:
            self._state['cooldown'] = 0
        if self._state['cooldown'] > 0:
            self._state['cooldown'] -= 1
            return None

        # Only trade if we have a confirmed trend
        if not trend_strength or self._state['trend_direction'] == 0:
            return None

        # --- UPTREND SIGNALS ---
        if self._state['trend_direction'] == 1 and close > fast_ma:
            signal = None
            reason = None
            confidence = 0.70
            
            # Strong trend continuation: price well above MAs with strong ADX
            if adx > 30 and close > fast_ma * 1.001:
                reason = f"Strong uptrend continuation (ADX={adx:.1f}, sep={ma_separation_pct:.2f}%)"
                confidence = 0.80
                signal = True
            
            # Pullback entry: price touched fast MA and bounced
            elif low <= fast_ma * 1.003 and close > fast_ma:
                reason = f"Uptrend pullback entry to EMA (ADX={adx:.1f})"
                confidence = 0.75
                signal = True
            
            # New trend establishment: MAs just crossed
            elif prev_trend != 1 and ma_trend == 1:
                reason = f"New uptrend established (ADX={adx:.1f})"
                confidence = 0.78
                signal = True
            
            if signal:
                entry_price = close
                stop_loss = fast_ma - (atr * self.atr_multiplier)
                risk = entry_price - stop_loss
                take_profit = entry_price + (risk * self.risk_reward_ratio)
                
                self._state['cooldown'] = 5  # Cooldown bars
                
                return Signal(
                    id=self.generate_signal_id(),
                    timestamp=bar.name,
                    symbol=self.config.get('params', {}).get('symbol', 'UNKNOWN'),
                    timeframe=self.config.get('timeframe', '1H'),
                    side=SignalType.LONG,
                    action='BUY',
                    price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    confidence=confidence,
                    reason=reason,
                    metadata={
                        'strategy_type': 'trend_following',
                        'trend_direction': 'up',
                        'adx': float(adx),
                        'fast_ma': float(fast_ma),
                        'slow_ma': float(slow_ma),
                        'ma_separation_pct': float(ma_separation_pct),
                        'risk': float(risk),
                        'reward': float(risk * self.risk_reward_ratio)
                    }
                )

        # --- DOWNTREND SIGNALS ---
        elif self._state['trend_direction'] == -1 and close < fast_ma:
            signal = None
            reason = None
            confidence = 0.70
            
            # Strong trend continuation
            if adx > 30 and close < fast_ma * 0.999:
                reason = f"Strong downtrend continuation (ADX={adx:.1f}, sep={ma_separation_pct:.2f}%)"
                confidence = 0.80
                signal = True
            
            # Pullback entry
            elif high >= fast_ma * 0.997 and close < fast_ma:
                reason = f"Downtrend pullback entry to EMA (ADX={adx:.1f})"
                confidence = 0.75
                signal = True
            
            # New trend establishment
            elif prev_trend != -1 and ma_trend == -1:
                reason = f"New downtrend established (ADX={adx:.1f})"
                confidence = 0.78
                signal = True
            
            if signal:
                entry_price = close
                stop_loss = fast_ma + (atr * self.atr_multiplier)
                risk = stop_loss - entry_price
                take_profit = entry_price - (risk * self.risk_reward_ratio)
                
                self._state['cooldown'] = 5
                
                return Signal(
                    id=self.generate_signal_id(),
                    timestamp=bar.name,
                    symbol=self.config.get('params', {}).get('symbol', 'UNKNOWN'),
                    timeframe=self.config.get('timeframe', '1H'),
                    side=SignalType.SHORT,
                    action='SELL',
                    price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    confidence=confidence,
                    reason=reason,
                    metadata={
                        'strategy_type': 'trend_following',
                        'trend_direction': 'down',
                        'adx': float(adx),
                        'fast_ma': float(fast_ma),
                        'slow_ma': float(slow_ma),
                        'ma_separation_pct': float(ma_separation_pct),
                        'risk': float(risk),
                        'reward': float(risk * self.risk_reward_ratio)
                    }
                )

        return None



