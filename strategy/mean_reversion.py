"""
Mean Reversion Strategy

Capitalizes on price deviations from moving averages, expecting reversion to mean.
Works well in ranging markets and corrections within trends.
"""

import pandas as pd
from typing import Optional, Dict, Any
from datetime import datetime

from cthulu.strategy.base import Strategy, Signal, SignalType


class MeanReversionStrategy(Strategy):
    """
    Mean Reversion Strategy using Bollinger Bands and RSI.

    Enters when price deviates significantly from mean and shows reversal signals.
    Uses tight stops and quick profit targets.

    Configuration:
        ma_period: Moving average period (default: 20)
        bb_std: Bollinger Band standard deviations (default: 2.0)
        rsi_period: RSI period (default: 14)
        rsi_oversold: RSI oversold level (default: 30)
        rsi_overbought: RSI overbought level (default: 70)
        atr_multiplier: ATR multiplier for SL (default: 1.5)
        risk_reward_ratio: Risk/reward ratio (default: 2.0)
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize mean reversion strategy."""
        super().__init__("mean_reversion", config)

        # Strategy parameters
        self.ma_period = config.get('params', {}).get('ma_period', 20)
        self.bb_std = config.get('params', {}).get('bb_std', 2.0)
        self.rsi_period = config.get('params', {}).get('rsi_period', 14)
        self.rsi_oversold = config.get('params', {}).get('rsi_oversold', 30)
        self.rsi_overbought = config.get('params', {}).get('rsi_overbought', 70)
        self.atr_multiplier = config.get('params', {}).get('atr_multiplier', 1.5)
        self.risk_reward_ratio = config.get('params', {}).get('risk_reward_ratio', 2.0)

        # State
        self._state = {
            'last_signal': None,
            'entry_price': None,
            'stop_loss': None
        }

        self.logger.info(
            f"Mean Reversion initialized: MA={self.ma_period}, BB={self.bb_std}, "
            f"RSI={self.rsi_period}"
        )

    def on_bar(self, bar: pd.Series) -> Optional[Signal]:
        """
        Process new bar and check for mean reversion signals.

        Args:
            bar: Latest bar with indicators

        Returns:
            Signal if mean reversion setup detected, None otherwise
        """
        # Need required indicators
        required_cols = ['close', 'high', 'low', 'atr']
        if not all(col in bar for col in required_cols):
            return None

        # Check for Bollinger Bands
        bb_upper_col = f'bb_upper_{self.ma_period}_{self.bb_std}'
        bb_lower_col = f'bb_lower_{self.ma_period}_{self.bb_std}'
        bb_middle_col = f'bb_middle_{self.ma_period}'

        if bb_upper_col not in bar or bb_lower_col not in bar:
            return None

        # Check for RSI
        rsi_col = f'rsi_{self.rsi_period}' if f'rsi_{self.rsi_period}' in bar else 'rsi'
        if rsi_col not in bar:
            return None

        close = bar['close']
        high = bar['high']
        low = bar['low']
        rsi = bar[rsi_col]
        atr = bar['atr']
        bb_upper = bar[bb_upper_col]
        bb_lower = bar[bb_lower_col]
        bb_middle = bar.get(bb_middle_col, (bb_upper + bb_lower) / 2)

        # Bullish mean reversion: Price near lower BB + oversold RSI + rejection candle
        if (close <= bb_lower * 1.005 and  # Price touched or very near lower BB
            rsi <= self.rsi_oversold and   # RSI oversold
            low < bb_lower and             # Wick below BB (rejection)
            close > low + (high - low) * 0.6):  # Closed above lower wick (bullish rejection)

            # Calculate entry and stops
            entry_price = close
            stop_loss = min(low, bb_lower - atr * 0.5)  # Below recent low or BB
            risk = entry_price - stop_loss
            take_profit = entry_price + (risk * self.risk_reward_ratio)

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
                confidence=0.75,
                reason=f"Mean reversion from lower BB (RSI={rsi:.1f})",
                metadata={
                    'strategy_type': 'mean_reversion',
                    'bb_lower': float(bb_lower),
                    'bb_upper': float(bb_upper),
                    'rsi': float(rsi),
                    'risk': float(risk),
                    'reward': float(risk * self.risk_reward_ratio)
                }
            )

        # Bearish mean reversion: Price near upper BB + overbought RSI
        # Relaxed conditions: no longer requires strict rejection candle
        bb_width = bb_upper - bb_lower
        upper_zone = bb_middle + (bb_width * 0.4)  # Upper 40% of BB
        
        if (close >= upper_zone and           # Price in upper zone of BB
              rsi >= self.rsi_overbought):      # RSI overbought

            # Calculate entry and stops
            entry_price = close
            stop_loss = max(high, bb_upper + atr * 0.5)  # Above recent high or BB
            risk = stop_loss - entry_price
            take_profit = entry_price - (risk * self.risk_reward_ratio)

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
                confidence=0.75,
                reason=f"Mean reversion from upper BB (RSI={rsi:.1f})",
                metadata={
                    'strategy_type': 'mean_reversion',
                    'bb_lower': float(bb_lower),
                    'bb_upper': float(bb_upper),
                    'rsi': float(rsi),
                    'risk': float(risk),
                    'reward': float(risk * self.risk_reward_ratio)
                }
            )

        return None



