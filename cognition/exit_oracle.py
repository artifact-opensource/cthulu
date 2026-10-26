"""
Exit Oracle - The Judgment of Cognition

Enhanced exit signal generation with multi-indicator confluence.
Integrates with Cognition modules for intelligent exit timing.

Part of Cthulu Cognition Engine v6.0.0
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import logging

logger = logging.getLogger("cthulu.cognition.exit_oracle")


class ExitUrgency(Enum):
    """Exit signal urgency levels."""
    HOLD = "hold"
    SCALE_OUT = "scale_out"
    CLOSE_NOW = "close_now"
    EMERGENCY = "emergency"


class ExitReason(Enum):
    """Reasons for exit signal."""
    REVERSAL_CONFLUENCE = "reversal_confluence"
    PROFIT_TARGET = "profit_target"
    STOP_LOSS = "stop_loss"
    TIME_BASED = "time_based"
    REGIME_CHANGE = "regime_change"
    SENTIMENT_SHIFT = "sentiment_shift"
    PREDICTION_FLIP = "prediction_flip"
    MANUAL = "manual"


@dataclass
class ExitSignal:
    """Exit signal with details."""
    ticket: int
    symbol: str
    direction: str  # 'long' or 'short'
    urgency: ExitUrgency
    reason: ExitReason
    confidence: float
    confluence_score: float
    indicators_signaling: List[str]
    recommended_close_pct: float  # 0-100
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def is_actionable(self) -> bool:
        return self.urgency != ExitUrgency.HOLD
    
    @property
    def requires_immediate_action(self) -> bool:
        return self.urgency in (ExitUrgency.CLOSE_NOW, ExitUrgency.EMERGENCY)


@dataclass
class PositionContext:
    """Position context for exit evaluation."""
    ticket: int
    symbol: str
    direction: str
    entry_price: float
    current_price: float
    volume: float
    unrealized_pnl: float
    entry_time: datetime
    
    @property
    def profit_pct(self) -> float:
        if self.direction == 'long':
            return (self.current_price - self.entry_price) / self.entry_price * 100
        else:
            return (self.entry_price - self.current_price) / self.entry_price * 100
    
    @property
    def holding_hours(self) -> float:
        return (datetime.utcnow() - self.entry_time).total_seconds() / 3600


class ReversalDetector:
    """Base class for reversal detection."""
    
    def __init__(self, name: str, weight: float):
        self.name = name
        self.weight = weight
    
    def is_signaling(
        self, 
        position: PositionContext, 
        market_data: pd.DataFrame,
        indicators: Dict[str, float]
    ) -> Tuple[bool, float]:
        """
        Check if detector is signaling reversal.
        
        Returns: (is_signaling, signal_strength 0-1)
        """
        raise NotImplementedError


class RSIReversalDetector(ReversalDetector):
    """RSI-based reversal detection."""
    
    def __init__(self, overbought: float = 70, oversold: float = 30, weight: float = 0.20):
        super().__init__("RSI", weight)
        self.overbought = overbought
        self.oversold = oversold
    
    def is_signaling(
        self, 
        position: PositionContext, 
        market_data: pd.DataFrame,
        indicators: Dict[str, float]
    ) -> Tuple[bool, float]:
        rsi = indicators.get('rsi', 50)
        prev_rsi = indicators.get('prev_rsi', rsi)
        
        if position.direction == 'long':
            # Long exit: RSI overbought and falling
            if rsi > self.overbought and rsi < prev_rsi:
                strength = (rsi - self.overbought) / (100 - self.overbought)
                return True, min(strength, 1.0)
        else:
            # Short exit: RSI oversold and rising
            if rsi < self.oversold and rsi > prev_rsi:
                strength = (self.oversold - rsi) / self.oversold
                return True, min(strength, 1.0)
        
        return False, 0.0


class MACDCrossoverDetector(ReversalDetector):
    """MACD crossover reversal detection."""
    
    def __init__(self, weight: float = 0.15):
        super().__init__("MACD", weight)
    
    def is_signaling(
        self, 
        position: PositionContext, 
        market_data: pd.DataFrame,
        indicators: Dict[str, float]
    ) -> Tuple[bool, float]:
        macd = indicators.get('macd', 0)
        signal = indicators.get('macd_signal', 0)
        prev_macd = indicators.get('prev_macd', macd)
        prev_signal = indicators.get('prev_macd_signal', signal)
        
        if position.direction == 'long':
            # Long exit: MACD crosses below signal
            if prev_macd >= prev_signal and macd < signal:
                strength = abs(prev_macd - prev_signal) / (abs(macd) + 1e-10)
                return True, min(strength, 1.0)
        else:
            # Short exit: MACD crosses above signal
            if prev_macd <= prev_signal and macd > signal:
                strength = abs(prev_macd - prev_signal) / (abs(macd) + 1e-10)
                return True, min(strength, 1.0)
        
        return False, 0.0


class BollingerBandDetector(ReversalDetector):
    """Bollinger Band breach reversal detection."""
    
    def __init__(self, weight: float = 0.15):
        super().__init__("Bollinger", weight)
    
    def is_signaling(
        self, 
        position: PositionContext, 
        market_data: pd.DataFrame,
        indicators: Dict[str, float]
    ) -> Tuple[bool, float]:
        price = position.current_price
        upper = indicators.get('bb_upper', price * 1.02)
        lower = indicators.get('bb_lower', price * 0.98)
        middle = indicators.get('bb_middle', price)
        
        if position.direction == 'long':
            # Long exit: Price at upper band
            if price >= upper:
                strength = (price - upper) / (upper - middle + 1e-10)
                return True, min(0.5 + strength * 0.5, 1.0)
        else:
            # Short exit: Price at lower band
            if price <= lower:
                strength = (lower - price) / (middle - lower + 1e-10)
                return True, min(0.5 + strength * 0.5, 1.0)
        
        return False, 0.0


class TrendFlipDetector(ReversalDetector):
    """EMA crossover trend flip detection."""
    
    def __init__(self, weight: float = 0.25):
        super().__init__("TrendFlip", weight)
    
    def is_signaling(
        self, 
        position: PositionContext, 
        market_data: pd.DataFrame,
        indicators: Dict[str, float]
    ) -> Tuple[bool, float]:
        ema_fast = indicators.get('ema_fast', 0)
        ema_slow = indicators.get('ema_slow', 0)
        prev_ema_fast = indicators.get('prev_ema_fast', ema_fast)
        prev_ema_slow = indicators.get('prev_ema_slow', ema_slow)
        
        if position.direction == 'long':
            # Long exit: Fast EMA crosses below slow
            if prev_ema_fast >= prev_ema_slow and ema_fast < ema_slow:
                strength = abs(ema_slow - ema_fast) / (ema_slow + 1e-10) * 100
                return True, min(strength, 1.0)
        else:
            # Short exit: Fast EMA crosses above slow
            if prev_ema_fast <= prev_ema_slow and ema_fast > ema_slow:
                strength = abs(ema_fast - ema_slow) / (ema_slow + 1e-10) * 100
                return True, min(strength, 1.0)
        
        return False, 0.0


class VolumeClimaxDetector(ReversalDetector):
    """Volume climax (distribution/accumulation) detection."""
    
    def __init__(self, multiplier: float = 2.0, weight: float = 0.10):
        super().__init__("VolClmax", weight)
        self.multiplier = multiplier
    
    def is_signaling(
        self, 
        position: PositionContext, 
        market_data: pd.DataFrame,
        indicators: Dict[str, float]
    ) -> Tuple[bool, float]:
        volume = indicators.get('volume', 0)
        avg_volume = indicators.get('avg_volume', volume)
        price_change = indicators.get('bar_change', 0)
        
        # High volume with adverse price move
        if volume > avg_volume * self.multiplier:
            if position.direction == 'long' and price_change < 0:
                strength = (volume / avg_volume - 1) / self.multiplier
                return True, min(strength, 1.0)
            elif position.direction == 'short' and price_change > 0:
                strength = (volume / avg_volume - 1) / self.multiplier
                return True, min(strength, 1.0)
        
        return False, 0.0


class ProfitGivebackDetector(ReversalDetector):
    """Profit giveback (adverse price action) detection."""
    
    def __init__(self, giveback_threshold: float = 0.50, weight: float = 0.15):
        super().__init__("ProfitGiveback", weight)
        self.giveback_threshold = giveback_threshold
    
    def is_signaling(
        self, 
        position: PositionContext, 
        market_data: pd.DataFrame,
        indicators: Dict[str, float]
    ) -> Tuple[bool, float]:
        max_profit = indicators.get('max_unrealized_pnl', position.unrealized_pnl)
        
        if max_profit <= 0:
            return False, 0.0
        
        # Calculate giveback
        current_pnl = position.unrealized_pnl
        if max_profit > 0:
            giveback = (max_profit - current_pnl) / max_profit
            
            if giveback >= self.giveback_threshold:
                strength = (giveback - self.giveback_threshold) / (1 - self.giveback_threshold)
                return True, min(strength, 1.0)
        
        return False, 0.0


class ExitOracle:
    """
    Generates high-confluence exit signals.
    
    Evaluates positions against multiple reversal detectors
    and cognition modules (regime, sentiment, prediction).
    
    Confluence thresholds:
    - < 0.55: HOLD
    - 0.55-0.74: SCALE_OUT
    - 0.75-0.89: CLOSE_NOW
    - >= 0.90: EMERGENCY
    """
    
    def __init__(
        self,
        confluence_scale_out: float = 0.55,
        confluence_close: float = 0.75,
        confluence_emergency: float = 0.90,
        min_profit_to_protect: float = 0.5  # % profit before protection kicks in
    ):
        self.confluence_scale_out = confluence_scale_out
        self.confluence_close = confluence_close
        self.confluence_emergency = confluence_emergency
        self.min_profit_to_protect = min_profit_to_protect
        
        # Initialize detectors
        self.detectors: List[ReversalDetector] = [
            TrendFlipDetector(weight=0.25),
            RSIReversalDetector(weight=0.20),
            MACDCrossoverDetector(weight=0.15),
            BollingerBandDetector(weight=0.15),
            ProfitGivebackDetector(weight=0.15),
            VolumeClimaxDetector(weight=0.10),
        ]
        
        # Cognition integration
        self._regime_classifier = None
        self._price_predictor = None
        self._sentiment_analyzer = None
        
        # Position tracking
        self._max_profits: Dict[int, float] = {}  # ticket -> max unrealized pnl
        
        logger.info(f"ExitOracle initialized: {len(self.detectors)} detectors")
    
    def integrate_cognition(
        self,
        regime_classifier=None,
        price_predictor=None,
        sentiment_analyzer=None
    ):
        """Integrate cognition modules for enhanced signals."""
        self._regime_classifier = regime_classifier
        self._price_predictor = price_predictor
        self._sentiment_analyzer = sentiment_analyzer
        logger.info("Cognition modules integrated into ExitOracle")
    
    def evaluate_exits(
        self,
        positions: List[PositionContext],
        market_data: pd.DataFrame,
        indicators: Dict[str, float]
    ) -> List[ExitSignal]:
        """
        Evaluate all positions for exit conditions.
        
        Args:
            positions: List of active positions
            market_data: Recent OHLCV data
            indicators: Current indicator values
            
        Returns:
            List of exit signals
        """
        signals = []
        
        for position in positions:
            signal = self._evaluate_position(position, market_data, indicators)
            if signal:
                signals.append(signal)
        
        # Sort by urgency (most urgent first)
        urgency_order = {
            ExitUrgency.EMERGENCY: 0,
            ExitUrgency.CLOSE_NOW: 1,
            ExitUrgency.SCALE_OUT: 2,
            ExitUrgency.HOLD: 3
        }
        signals.sort(key=lambda s: urgency_order.get(s.urgency, 3))
        
        return signals
    
    def _evaluate_position(
        self,
        position: PositionContext,
        market_data: pd.DataFrame,
        indicators: Dict[str, float]
    ) -> Optional[ExitSignal]:
        """Evaluate single position for exit."""
        # Track max profit
        ticket = position.ticket
        if ticket not in self._max_profits:
            self._max_profits[ticket] = position.unrealized_pnl
        else:
            self._max_profits[ticket] = max(self._max_profits[ticket], position.unrealized_pnl)
        
        # Add max profit to indicators for detectors
        indicators['max_unrealized_pnl'] = self._max_profits[ticket]
        
        # Evaluate reversal detectors
        signaling_detectors = []
        weighted_score = 0.0
        total_weight = 0.0
        
        for detector in self.detectors:
            is_signaling, strength = detector.is_signaling(position, market_data, indicators)
            if is_signaling:
                signaling_detectors.append(detector.name)
                weighted_score += detector.weight * strength
            total_weight += detector.weight
        
        # Base confluence score
        confluence = weighted_score / (total_weight + 1e-10)
        
        # Cognition adjustments
        cognition_factor = self._get_cognition_factor(position, market_data)
        confluence = confluence * (1 + cognition_factor * 0.3)  # Up to 30% boost
        
        # Determine urgency
        urgency = self._determine_urgency(confluence, position)
        
        # Only return if actionable
        if urgency == ExitUrgency.HOLD:
            return None
        
        # Determine reason
        reason = self._determine_reason(signaling_detectors, cognition_factor, position)
        
        # Recommended close percentage
        close_pct = self._calculate_close_pct(urgency, confluence, position)
        
        return ExitSignal(
            ticket=position.ticket,
            symbol=position.symbol,
            direction=position.direction,
            urgency=urgency,
            reason=reason,
            confidence=min(confluence, 1.0),
            confluence_score=confluence,
            indicators_signaling=signaling_detectors,
            recommended_close_pct=close_pct
        )
    
    def _get_cognition_factor(self, position: PositionContext, market_data: pd.DataFrame) -> float:
        """Get cognition adjustment factor."""
        factor = 0.0
        
        # Regime check
        if self._regime_classifier:
            try:
                state = self._regime_classifier.classify(market_data)
                # Adverse regime for position
                if position.direction == 'long' and state.regime.value == 'bear':
                    factor += 0.3
                elif position.direction == 'short' and state.regime.value == 'bull':
                    factor += 0.3
                # Choppy/volatile = exit sooner
                if state.regime.value in ('choppy', 'volatile'):
                    factor += 0.15
            except Exception as e:
                logger.debug(f"Regime check error: {e}")
        
        # Prediction check
        if self._price_predictor:
            try:
                prediction = self._price_predictor.predict(market_data)
                # Prediction against position
                if position.direction == 'long' and prediction.direction.value == 'short':
                    factor += prediction.confidence * 0.2
                elif position.direction == 'short' and prediction.direction.value == 'long':
                    factor += prediction.confidence * 0.2
            except Exception as e:
                logger.debug(f"Prediction check error: {e}")
        
        # Sentiment check
        if self._sentiment_analyzer:
            try:
                sentiment = self._sentiment_analyzer.get_sentiment(position.symbol)
                # Sentiment against position
                if position.direction == 'long' and sentiment.direction.value == 'bearish':
                    factor += sentiment.confidence * 0.15
                elif position.direction == 'short' and sentiment.direction.value == 'bullish':
                    factor += sentiment.confidence * 0.15
                # Critical events
                if sentiment.suggests_caution:
                    factor += 0.1
            except Exception as e:
                logger.debug(f"Sentiment check error: {e}")
        
        return min(factor, 1.0)
    
    def _determine_urgency(self, confluence: float, position: PositionContext) -> ExitUrgency:
        """Determine exit urgency from confluence score."""
        # Adjust thresholds based on profit state
        if position.profit_pct < -5:  # Deep in loss
            # More aggressive exit
            scale_out = self.confluence_scale_out * 0.8
            close = self.confluence_close * 0.8
            emergency = self.confluence_emergency * 0.8
        elif position.profit_pct > self.min_profit_to_protect:
            # Protect profits more aggressively
            scale_out = self.confluence_scale_out * 0.9
            close = self.confluence_close * 0.9
            emergency = self.confluence_emergency * 0.9
        else:
            scale_out = self.confluence_scale_out
            close = self.confluence_close
            emergency = self.confluence_emergency
        
        if confluence >= emergency:
            return ExitUrgency.EMERGENCY
        elif confluence >= close:
            return ExitUrgency.CLOSE_NOW
        elif confluence >= scale_out:
            return ExitUrgency.SCALE_OUT
        else:
            return ExitUrgency.HOLD
    
    def _determine_reason(
        self, 
        signaling_detectors: List[str], 
        cognition_factor: float,
        position: PositionContext
    ) -> ExitReason:
        """Determine primary exit reason."""
        if not signaling_detectors:
            if cognition_factor > 0.3:
                return ExitReason.REGIME_CHANGE
            return ExitReason.TIME_BASED
        
        # Priority order
        if 'TrendFlip' in signaling_detectors:
            return ExitReason.REVERSAL_CONFLUENCE
        elif 'ProfitGiveback' in signaling_detectors and position.profit_pct > 0:
            return ExitReason.PROFIT_TARGET
        elif 'RSI' in signaling_detectors or 'MACD' in signaling_detectors:
            return ExitReason.REVERSAL_CONFLUENCE
        elif cognition_factor > 0.2:
            return ExitReason.PREDICTION_FLIP
        else:
            return ExitReason.REVERSAL_CONFLUENCE
    
    def _calculate_close_pct(
        self, 
        urgency: ExitUrgency, 
        confluence: float,
        position: PositionContext
    ) -> float:
        """Calculate recommended close percentage."""
        base_pct = {
            ExitUrgency.HOLD: 0,
            ExitUrgency.SCALE_OUT: 25,
            ExitUrgency.CLOSE_NOW: 75,
            ExitUrgency.EMERGENCY: 100
        }.get(urgency, 0)
        
        # Adjust based on confluence strength
        if urgency == ExitUrgency.SCALE_OUT:
            # Scale between 25-50%
            base_pct = 25 + (confluence - self.confluence_scale_out) / (self.confluence_close - self.confluence_scale_out) * 25
        elif urgency == ExitUrgency.CLOSE_NOW:
            # Scale between 75-100%
            base_pct = 75 + (confluence - self.confluence_close) / (self.confluence_emergency - self.confluence_close) * 25
        
        return min(100, max(0, base_pct))
    
    def clear_position_tracking(self, ticket: int):
        """Clear tracking for closed position."""
        if ticket in self._max_profits:
            del self._max_profits[ticket]
    
    def to_dict(self) -> Dict:
        """Export current state as dictionary."""
        return {
            'detectors': [d.name for d in self.detectors],
            'thresholds': {
                'scale_out': self.confluence_scale_out,
                'close': self.confluence_close,
                'emergency': self.confluence_emergency
            },
            'positions_tracked': len(self._max_profits),
            'cognition_integrated': {
                'regime': self._regime_classifier is not None,
                'predictor': self._price_predictor is not None,
                'sentiment': self._sentiment_analyzer is not None
            }
        }


# Module-level singleton
_oracle: Optional[ExitOracle] = None


def get_exit_oracle(**kwargs) -> ExitOracle:
    """Get or create the exit oracle singleton."""
    global _oracle
    if _oracle is None:
        _oracle = ExitOracle(**kwargs)
    return _oracle


def evaluate_exits(
    positions: List[PositionContext],
    market_data: pd.DataFrame,
    indicators: Dict[str, float]
) -> List[ExitSignal]:
    """Convenience function to evaluate exits."""
    return get_exit_oracle().evaluate_exits(positions, market_data, indicators)
