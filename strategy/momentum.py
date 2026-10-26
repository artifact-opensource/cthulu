"""
Momentum Strategy - Rule-Based
Generates signals based on multi-indicator momentum alignment.

This is a more ACTIVE strategy that generates signals when
momentum indicators align, without requiring crossovers.

Signal Logic:
- BUY: RSI > 50, ADX > 20, MACD histogram positive, price above EMAs
- SELL: RSI < 50, ADX > 20, MACD histogram negative, price below EMAs
"""
import logging
import numpy as np
from typing import Dict, Any, Optional

from .base import BaseStrategy, Signal

logger = logging.getLogger(__name__)


class MomentumStrategy(BaseStrategy):
    """
    Momentum-based strategy that generates signals on indicator alignment.
    
    More active than crossover strategies - signals on momentum alignment
    rather than waiting for specific events.
    
    Config:
    - rsi_bull_threshold: RSI level for bullish (default: 55)
    - rsi_bear_threshold: RSI level for bearish (default: 45)
    - adx_threshold: Minimum ADX for signal (default: 20)
    - min_alignment: Minimum indicator alignment (default: 3 of 5)
    """
    
    def __init__(self, config: Dict[str, Any], symbol: str):
        super().__init__(config, symbol)
        
        self.rsi_bull_threshold = config.get('rsi_bull_threshold', 55)
        self.rsi_bear_threshold = config.get('rsi_bear_threshold', 45)
        self.adx_threshold = config.get('adx_threshold', 20)
        self.min_alignment = config.get('min_alignment', 3)
        
        # Cooldown to prevent overtrading
        self._last_signal_bar = -100
        self._signal_cooldown = config.get('signal_cooldown', 5)  # bars
        
        logger.info(f"Momentum Strategy initialized: RSI thresholds {self.rsi_bear_threshold}/{self.rsi_bull_threshold}")
    
    def generate_signal(
        self,
        data: Any,
        indicators: Dict[str, Any]
    ) -> Optional[Signal]:
        """Generate momentum-based signal."""
        if data is None or len(data) < 30:
            return None
        
        # Cooldown check
        current_bar = len(data)
        if current_bar - self._last_signal_bar < self._signal_cooldown:
            return None
        
        close = data['close'].values
        high = data['high'].values
        low = data['low'].values
        
        # Get indicators
        rsi = indicators.get('RSI', 50)
        adx = indicators.get('ADX', 15)
        atr = indicators.get('ATR', self._calculate_atr(high, low, close))
        
        macd_data = indicators.get('MACD', {})
        macd_hist = macd_data.get('histogram', 0) if isinstance(macd_data, dict) else 0
        
        # Calculate EMAs
        ema_fast = self._calculate_ema(close, 12)
        ema_slow = self._calculate_ema(close, 26)
        
        entry_price = close[-1]
        
        # Count bullish/bearish alignments
        bull_count = 0
        bear_count = 0
        
        # RSI
        if rsi >= self.rsi_bull_threshold:
            bull_count += 1
        elif rsi <= self.rsi_bear_threshold:
            bear_count += 1
        
        # ADX (trend strength - counts for both if strong)
        if adx >= self.adx_threshold:
            bull_count += 0.5
            bear_count += 0.5
        
        # MACD histogram
        if macd_hist > 0:
            bull_count += 1
        elif macd_hist < 0:
            bear_count += 1
        
        # Price vs EMAs
        if entry_price > ema_fast and entry_price > ema_slow:
            bull_count += 1
        elif entry_price < ema_fast and entry_price < ema_slow:
            bear_count += 1
        
        # EMA alignment
        if ema_fast > ema_slow:
            bull_count += 1
        elif ema_fast < ema_slow:
            bear_count += 1
        
        # Generate signal if enough alignment
        signal = None
        
        if bull_count >= self.min_alignment and bull_count > bear_count:
            confidence = min(0.90, 0.55 + (bull_count * 0.08))
            sl, tp = self._calculate_atr_based_sltp(entry_price, 'buy', atr)
            
            signal = Signal(
                direction='buy',
                symbol=self.symbol,
                confidence=confidence,
                strategy_name='momentum',
                entry_price=entry_price,
                sl=sl,
                tp=tp,
                reason=f"Momentum BUY: {bull_count:.1f} indicators aligned, RSI={rsi:.1f}, ADX={adx:.1f}"
            )
            logger.info(f"🟢 MOMENTUM LONG: {bull_count:.1f} aligned, RSI={rsi:.1f}, ADX={adx:.1f}")
            self._last_signal_bar = current_bar
        
        elif bear_count >= self.min_alignment and bear_count > bull_count:
            confidence = min(0.90, 0.55 + (bear_count * 0.08))
            sl, tp = self._calculate_atr_based_sltp(entry_price, 'sell', atr)
            
            signal = Signal(
                direction='sell',
                symbol=self.symbol,
                confidence=confidence,
                strategy_name='momentum',
                entry_price=entry_price,
                sl=sl,
                tp=tp,
                reason=f"Momentum SELL: {bear_count:.1f} indicators aligned, RSI={rsi:.1f}, ADX={adx:.1f}"
            )
            logger.info(f"🔴 MOMENTUM SHORT: {bear_count:.1f} aligned, RSI={rsi:.1f}, ADX={adx:.1f}")
            self._last_signal_bar = current_bar
        
        return signal
    
    def get_regime_fitness(self, regime: str) -> float:
        """Momentum works in trending and moderate ranging."""
        regime_scores = {
            'trending_up_strong': 0.90,
            'trending_up_weak': 0.80,
            'trending_down_strong': 0.90,
            'trending_down_weak': 0.80,
            'ranging_wide': 0.60,
            'ranging_tight': 0.50,
            'volatile': 0.65,
            'unknown': 0.60
        }
        return regime_scores.get(regime, 0.60)
    
    def _calculate_ema(self, data, period: int) -> float:
        """Calculate EMA."""
        if len(data) < period:
            return data[-1] if len(data) > 0 else 0
        
        multiplier = 2 / (period + 1)
        ema = np.mean(data[:period])
        
        for price in data[period:]:
            ema = (price - ema) * multiplier + ema
        
        return ema
    
    def _calculate_atr(self, high, low, close, period: int = 14) -> float:
        """Calculate ATR."""
        if len(high) < period + 1:
            return abs(high[-1] - low[-1])
        
        tr = []
        for i in range(1, len(high)):
            tr.append(max(
                high[i] - low[i],
                abs(high[i] - close[i-1]),
                abs(low[i] - close[i-1])
            ))
        
        return np.mean(tr[-period:])
