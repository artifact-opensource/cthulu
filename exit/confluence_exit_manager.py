"""
Confluence Exit Manager - High-Confidence Exit Signal System

Implements multi-indicator confluence-based exit decision making:
- Tracks active positions with real-time P&L
- Generates exit signals from reverse indicator confluence
- Classifies signals: HOLD, SCALE_OUT, CLOSE_NOW, EMERGENCY

Philosophy:
- Don't hope for recovery (that's market prediction)
- Exit when multiple indicators AGREE on reversal
- Higher confluence = higher confidence = faster action

Exit Signal Classification:
- HOLD: Normal conditions, continue
- SCALE_OUT: Moderate confluence, take partial profit/loss
- CLOSE_NOW: High confluence reversal detected
- EMERGENCY: Loss curve breached or critical market event
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger('cthulu.confluence_exit')


class ExitClassification(Enum):
    """Exit signal classification."""
    HOLD = "hold"
    SCALE_OUT = "scale_out"
    CLOSE_NOW = "close_now"
    EMERGENCY = "emergency"


@dataclass
class ConfluenceSignal:
    """Individual indicator signal for confluence calculation."""
    indicator: str
    signal: str  # 'reversal_up', 'reversal_down', 'neutral'
    strength: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass  
class TrackedPosition:
    """Position tracked by confluence exit manager."""
    ticket: int
    symbol: str
    side: str  # 'BUY' or 'SELL'
    entry_price: float
    entry_time: datetime
    volume: float
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    max_favorable: float = 0.0  # Peak profit
    max_adverse: float = 0.0    # Max drawdown
    holding_bars: int = 0
    last_update: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ExitRecommendation:
    """Exit recommendation from confluence analysis."""
    ticket: int
    classification: ExitClassification
    confidence: float  # 0.0 to 1.0
    confluence_score: float  # Number of agreeing indicators
    reason: str
    indicators_agreeing: List[str]
    suggested_action: str  # 'close_full', 'close_partial', 'tighten_stop', 'hold'
    partial_pct: Optional[float] = None  # If partial close, what percentage
    urgency: int = 50  # 0-100, maps to priority
    metadata: Dict[str, Any] = field(default_factory=dict)


class ConfluenceExitManager:
    """
    High-confluence exit signal generator.
    
    Tracks active positions and generates exit recommendations
    based on multi-indicator confluence detection.
    
    **Confluence Scoring:**
    - 1 indicator: 0.2 base score
    - 2 indicators: 0.4 score  
    - 3 indicators: 0.7 score (SCALE_OUT threshold)
    - 4+ indicators: 0.9 score (CLOSE_NOW threshold)
    
    **Indicator Weights:**
    - RSI divergence: 0.20
    - MACD crossover: 0.15
    - Bollinger breach: 0.15
    - Volume spike: 0.10
    - Trend flip: 0.25
    - Price action: 0.15
    
    Example:
        manager = ConfluenceExitManager()
        manager.track_position(ticket=123, symbol='BTCUSD', side='BUY', 
                              entry_price=50000, volume=0.01)
        
        recommendation = manager.evaluate_exit(
            ticket=123,
            current_price=49500,
            indicators={'rsi': 72, 'rsi_prev': 78, 'macd_signal': -1, ...}
        )
        
        if recommendation.classification == ExitClassification.CLOSE_NOW:
            execute_close(recommendation.ticket)
    """
    
    # Indicator weights for confluence scoring
    INDICATOR_WEIGHTS = {
        'rsi_divergence': 0.20,
        'macd_crossover': 0.15,
        'bollinger_breach': 0.15,
        'volume_spike': 0.10,
        'trend_flip': 0.25,
        'price_action': 0.15,
    }
    
    # Thresholds for classification
    SCALE_OUT_THRESHOLD = 0.55
    CLOSE_NOW_THRESHOLD = 0.75
    EMERGENCY_THRESHOLD = 0.90
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize confluence exit manager.
        
        Args:
            config: Optional configuration overrides
        """
        self.config = config or {}
        self._positions: Dict[int, TrackedPosition] = {}
        self._signal_history: List[Dict[str, Any]] = []
        
        # Configurable thresholds
        self.scale_out_threshold = self.config.get('scale_out_threshold', self.SCALE_OUT_THRESHOLD)
        self.close_now_threshold = self.config.get('close_now_threshold', self.CLOSE_NOW_THRESHOLD)
        
        # RSI thresholds for reversal detection
        self.rsi_overbought = self.config.get('rsi_overbought', 70)
        self.rsi_oversold = self.config.get('rsi_oversold', 30)
        self.rsi_divergence_threshold = self.config.get('rsi_divergence', 5.0)
        
    def track_position(self, ticket: int, symbol: str, side: str,
                      entry_price: float, volume: float,
                      entry_time: Optional[datetime] = None) -> TrackedPosition:
        """
        Start tracking a position for confluence exit analysis.
        
        Args:
            ticket: Position ticket/ID
            symbol: Trading symbol
            side: 'BUY' or 'SELL'
            entry_price: Entry price
            volume: Position size
            entry_time: Optional entry time
            
        Returns:
            TrackedPosition object
        """
        position = TrackedPosition(
            ticket=ticket,
            symbol=symbol,
            side=side.upper(),
            entry_price=entry_price,
            entry_time=entry_time or datetime.now(timezone.utc),
            volume=volume,
            current_price=entry_price,
        )
        self._positions[ticket] = position
        logger.info(f"ConfluenceExitManager tracking position #{ticket}: {side} {symbol} @ {entry_price}")
        return position
        
    def untrack_position(self, ticket: int) -> None:
        """Stop tracking a position."""
        if ticket in self._positions:
            del self._positions[ticket]
            logger.info(f"ConfluenceExitManager untracked position #{ticket}")
            
    def update_position(self, ticket: int, current_price: float, 
                       unrealized_pnl: float) -> Optional[TrackedPosition]:
        """
        Update position with current market data.
        
        Args:
            ticket: Position ticket
            current_price: Current market price
            unrealized_pnl: Current unrealized P&L
            
        Returns:
            Updated TrackedPosition or None if not found
        """
        position = self._positions.get(ticket)
        if not position:
            return None
            
        position.current_price = current_price
        position.unrealized_pnl = unrealized_pnl
        position.last_update = datetime.now(timezone.utc)
        position.holding_bars += 1
        
        # Track excursions
        if unrealized_pnl > position.max_favorable:
            position.max_favorable = unrealized_pnl
        if unrealized_pnl < position.max_adverse:
            position.max_adverse = unrealized_pnl
            
        return position
        
    def evaluate_exit(self, ticket: int, current_price: float,
                     indicators: Dict[str, Any],
                     account_balance: float = 0) -> Optional[ExitRecommendation]:
        """
        Evaluate position for confluence-based exit.
        
        Args:
            ticket: Position ticket
            current_price: Current market price
            indicators: Dictionary of indicator values
            account_balance: Current account balance
            
        Returns:
            ExitRecommendation or None if no action needed
        """
        position = self._positions.get(ticket)
        if not position:
            return None
            
        # Update position
        pnl = self._calculate_pnl(position, current_price)
        self.update_position(ticket, current_price, pnl)
        
        # Detect confluence signals
        signals = self._detect_confluence_signals(position, indicators)
        
        # Calculate confluence score
        confluence_score, agreeing_indicators = self._calculate_confluence_score(signals, position.side)
        
        # Classify exit
        classification = self._classify_exit(confluence_score, position, account_balance)
        
        # Generate recommendation
        if classification != ExitClassification.HOLD:
            recommendation = self._generate_recommendation(
                position, classification, confluence_score, 
                agreeing_indicators, signals
            )
            
            # Log signal
            self._log_signal(recommendation)
            
            return recommendation
            
        return None
        
    def _calculate_pnl(self, position: TrackedPosition, current_price: float) -> float:
        """Calculate unrealized P&L for position."""
        if position.side == 'BUY':
            return (current_price - position.entry_price) * position.volume * 100  # Rough estimate
        else:
            return (position.entry_price - current_price) * position.volume * 100
            
    def _detect_confluence_signals(self, position: TrackedPosition, 
                                   indicators: Dict[str, Any]) -> List[ConfluenceSignal]:
        """
        Detect reversal signals from indicators.
        
        Returns list of ConfluenceSignal for each indicator showing reversal.
        """
        signals = []
        is_long = position.side == 'BUY'
        
        # 1. RSI Divergence
        rsi = indicators.get('rsi') or indicators.get('RSI')
        rsi_prev = indicators.get('rsi_prev') or indicators.get('RSI_prev')
        
        if rsi is not None:
            rsi_signal = self._check_rsi_reversal(rsi, rsi_prev, is_long)
            if rsi_signal:
                signals.append(rsi_signal)
                
        # 2. MACD Crossover
        macd = indicators.get('macd') or indicators.get('MACD')
        macd_signal = indicators.get('macd_signal') or indicators.get('MACD_signal')
        macd_prev = indicators.get('macd_prev')
        
        if macd is not None and macd_signal is not None:
            macd_sig = self._check_macd_crossover(macd, macd_signal, macd_prev, is_long)
            if macd_sig:
                signals.append(macd_sig)
                
        # 3. Bollinger Band breach
        bb_upper = indicators.get('bb_upper') or indicators.get('BB_upper')
        bb_lower = indicators.get('bb_lower') or indicators.get('BB_lower')
        close = indicators.get('close', position.current_price)
        
        if bb_upper and bb_lower:
            bb_signal = self._check_bollinger_breach(close, bb_upper, bb_lower, is_long)
            if bb_signal:
                signals.append(bb_signal)
                
        # 4. Volume spike
        volume = indicators.get('volume')
        volume_avg = indicators.get('volume_avg') or indicators.get('volume_ma')
        
        if volume and volume_avg:
            vol_signal = self._check_volume_spike(volume, volume_avg, is_long, 
                                                  position.unrealized_pnl)
            if vol_signal:
                signals.append(vol_signal)
                
        # 5. Trend flip (EMA crossover)
        ema_fast = indicators.get('ema_fast') or indicators.get('EMA_fast')
        ema_slow = indicators.get('ema_slow') or indicators.get('EMA_slow')
        ema_fast_prev = indicators.get('ema_fast_prev')
        ema_slow_prev = indicators.get('ema_slow_prev')
        
        if ema_fast and ema_slow:
            trend_signal = self._check_trend_flip(ema_fast, ema_slow, 
                                                  ema_fast_prev, ema_slow_prev, is_long)
            if trend_signal:
                signals.append(trend_signal)
                
        # 6. Price action (momentum)
        atr = indicators.get('atr') or indicators.get('ATR')
        
        if atr:
            pa_signal = self._check_price_action(position, close, atr, is_long)
            if pa_signal:
                signals.append(pa_signal)
                
        return signals
        
    def _check_rsi_reversal(self, rsi: float, rsi_prev: Optional[float], 
                           is_long: bool) -> Optional[ConfluenceSignal]:
        """Check for RSI-based reversal signal."""
        # For longs: exit when RSI drops from overbought
        if is_long:
            if rsi_prev and rsi_prev > self.rsi_overbought and rsi < rsi_prev:
                strength = min((rsi_prev - rsi) / 10, 1.0)
                return ConfluenceSignal(
                    indicator='rsi_divergence',
                    signal='reversal_down',
                    strength=strength,
                    confidence=0.8 if rsi_prev > 75 else 0.6,
                    metadata={'rsi': rsi, 'rsi_prev': rsi_prev}
                )
        # For shorts: exit when RSI rises from oversold
        else:
            if rsi_prev and rsi_prev < self.rsi_oversold and rsi > rsi_prev:
                strength = min((rsi - rsi_prev) / 10, 1.0)
                return ConfluenceSignal(
                    indicator='rsi_divergence',
                    signal='reversal_up',
                    strength=strength,
                    confidence=0.8 if rsi_prev < 25 else 0.6,
                    metadata={'rsi': rsi, 'rsi_prev': rsi_prev}
                )
        return None
        
    def _check_macd_crossover(self, macd: float, signal: float, 
                              macd_prev: Optional[float], is_long: bool) -> Optional[ConfluenceSignal]:
        """Check for MACD crossover reversal."""
        # Bearish crossover (MACD crosses below signal)
        if is_long and macd < signal:
            if macd_prev and macd_prev > signal:  # Just crossed
                return ConfluenceSignal(
                    indicator='macd_crossover',
                    signal='reversal_down',
                    strength=min(abs(macd - signal) * 10, 1.0),
                    confidence=0.75,
                    metadata={'macd': macd, 'signal': signal}
                )
        # Bullish crossover (MACD crosses above signal)
        elif not is_long and macd > signal:
            if macd_prev and macd_prev < signal:
                return ConfluenceSignal(
                    indicator='macd_crossover',
                    signal='reversal_up',
                    strength=min(abs(macd - signal) * 10, 1.0),
                    confidence=0.75,
                    metadata={'macd': macd, 'signal': signal}
                )
        return None
        
    def _check_bollinger_breach(self, close: float, upper: float, 
                                lower: float, is_long: bool) -> Optional[ConfluenceSignal]:
        """Check for Bollinger Band breach indicating reversal."""
        bb_width = upper - lower
        
        # For longs: price touching/exceeding upper band suggests reversal
        if is_long and close >= upper * 0.995:  # Within 0.5% of upper
            return ConfluenceSignal(
                indicator='bollinger_breach',
                signal='reversal_down',
                strength=min((close - upper) / bb_width + 0.5, 1.0),
                confidence=0.7,
                metadata={'close': close, 'upper': upper}
            )
        # For shorts: price at lower band suggests reversal
        elif not is_long and close <= lower * 1.005:
            return ConfluenceSignal(
                indicator='bollinger_breach',
                signal='reversal_up',
                strength=min((lower - close) / bb_width + 0.5, 1.0),
                confidence=0.7,
                metadata={'close': close, 'lower': lower}
            )
        return None
        
    def _check_volume_spike(self, volume: float, volume_avg: float,
                           is_long: bool, pnl: float) -> Optional[ConfluenceSignal]:
        """Check for volume spike indicating potential reversal."""
        if volume_avg <= 0:
            return None
            
        volume_ratio = volume / volume_avg
        
        # High volume with profit = potential distribution (reversal)
        if volume_ratio > 2.0 and pnl > 0:
            signal_dir = 'reversal_down' if is_long else 'reversal_up'
            return ConfluenceSignal(
                indicator='volume_spike',
                signal=signal_dir,
                strength=min(volume_ratio / 4, 1.0),
                confidence=0.6,
                metadata={'volume_ratio': volume_ratio}
            )
        return None
        
    def _check_trend_flip(self, ema_fast: float, ema_slow: float,
                         ema_fast_prev: Optional[float], 
                         ema_slow_prev: Optional[float],
                         is_long: bool) -> Optional[ConfluenceSignal]:
        """Check for EMA crossover indicating trend flip."""
        if not ema_fast_prev or not ema_slow_prev:
            return None
            
        # For longs: bearish crossover (fast crosses below slow)
        if is_long:
            was_above = ema_fast_prev > ema_slow_prev
            is_below = ema_fast < ema_slow
            if was_above and is_below:
                return ConfluenceSignal(
                    indicator='trend_flip',
                    signal='reversal_down',
                    strength=0.9,
                    confidence=0.85,
                    metadata={'ema_fast': ema_fast, 'ema_slow': ema_slow}
                )
        # For shorts: bullish crossover
        else:
            was_below = ema_fast_prev < ema_slow_prev
            is_above = ema_fast > ema_slow
            if was_below and is_above:
                return ConfluenceSignal(
                    indicator='trend_flip',
                    signal='reversal_up',
                    strength=0.9,
                    confidence=0.85,
                    metadata={'ema_fast': ema_fast, 'ema_slow': ema_slow}
                )
        return None
        
    def _check_price_action(self, position: TrackedPosition, close: float,
                           atr: float, is_long: bool) -> Optional[ConfluenceSignal]:
        """Check price action for momentum loss."""
        # Check if we've given back significant profit
        if position.max_favorable > 0:
            giveback_pct = 1 - (position.unrealized_pnl / position.max_favorable)
            
            if giveback_pct > 0.5:  # Given back 50% of peak profit
                signal_dir = 'reversal_down' if is_long else 'reversal_up'
                return ConfluenceSignal(
                    indicator='price_action',
                    signal=signal_dir,
                    strength=min(giveback_pct, 1.0),
                    confidence=0.7,
                    metadata={
                        'giveback_pct': giveback_pct,
                        'max_favorable': position.max_favorable,
                        'current_pnl': position.unrealized_pnl
                    }
                )
        return None
        
    def _calculate_confluence_score(self, signals: List[ConfluenceSignal],
                                   side: str) -> Tuple[float, List[str]]:
        """
        Calculate weighted confluence score from signals.
        
        Returns:
            Tuple of (score, list of agreeing indicator names)
        """
        expected_reversal = 'reversal_down' if side == 'BUY' else 'reversal_up'
        
        agreeing = []
        weighted_score = 0.0
        total_weight = sum(self.INDICATOR_WEIGHTS.values())
        
        for signal in signals:
            if signal.signal == expected_reversal:
                weight = self.INDICATOR_WEIGHTS.get(signal.indicator, 0.1)
                contribution = weight * signal.strength * signal.confidence
                weighted_score += contribution
                agreeing.append(signal.indicator)
                
        # Normalize score
        if total_weight > 0:
            normalized_score = weighted_score / total_weight
        else:
            normalized_score = 0.0
            
        # Bonus for multiple indicators agreeing
        if len(agreeing) >= 3:
            normalized_score = min(normalized_score * 1.2, 1.0)
        if len(agreeing) >= 4:
            normalized_score = min(normalized_score * 1.1, 1.0)
            
        return normalized_score, agreeing
        
    def _classify_exit(self, confluence_score: float, position: TrackedPosition,
                      account_balance: float) -> ExitClassification:
        """Classify exit based on confluence score and position state."""
        
        # Emergency classification
        if confluence_score >= self.EMERGENCY_THRESHOLD:
            return ExitClassification.EMERGENCY
            
        # Check for significant drawdown from peak
        if position.max_favorable > 0 and position.unrealized_pnl < 0:
            # Was profitable, now losing - higher urgency
            if confluence_score >= self.scale_out_threshold * 0.8:
                return ExitClassification.CLOSE_NOW
                
        # Close now threshold
        if confluence_score >= self.close_now_threshold:
            return ExitClassification.CLOSE_NOW
            
        # Scale out threshold
        if confluence_score >= self.scale_out_threshold:
            return ExitClassification.SCALE_OUT
            
        return ExitClassification.HOLD
        
    def _generate_recommendation(self, position: TrackedPosition,
                                classification: ExitClassification,
                                confluence_score: float,
                                agreeing_indicators: List[str],
                                signals: List[ConfluenceSignal]) -> ExitRecommendation:
        """Generate exit recommendation."""
        
        # Determine action and partial percentage
        if classification == ExitClassification.EMERGENCY:
            action = 'close_full'
            partial_pct = None
            urgency = 100
            reason = f"EMERGENCY: {len(agreeing_indicators)} indicators signal reversal"
        elif classification == ExitClassification.CLOSE_NOW:
            action = 'close_full'
            partial_pct = None
            urgency = 85
            reason = f"High confluence ({confluence_score:.2f}): {', '.join(agreeing_indicators)}"
        elif classification == ExitClassification.SCALE_OUT:
            action = 'close_partial'
            partial_pct = 0.50 if confluence_score > 0.65 else 0.30
            urgency = 60
            reason = f"Moderate confluence ({confluence_score:.2f}): {', '.join(agreeing_indicators)}"
        else:
            action = 'hold'
            partial_pct = None
            urgency = 0
            reason = "No action required"
            
        return ExitRecommendation(
            ticket=position.ticket,
            classification=classification,
            confidence=min(confluence_score + 0.1, 1.0),
            confluence_score=confluence_score,
            reason=reason,
            indicators_agreeing=agreeing_indicators,
            suggested_action=action,
            partial_pct=partial_pct,
            urgency=urgency,
            metadata={
                'signals': [{'indicator': s.indicator, 'strength': s.strength} for s in signals],
                'position_pnl': position.unrealized_pnl,
                'max_favorable': position.max_favorable,
                'holding_bars': position.holding_bars
            }
        )
        
    def _log_signal(self, recommendation: ExitRecommendation) -> None:
        """Log exit signal for history."""
        entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'ticket': recommendation.ticket,
            'classification': recommendation.classification.value,
            'confluence_score': recommendation.confluence_score,
            'indicators': recommendation.indicators_agreeing,
            'action': recommendation.suggested_action
        }
        self._signal_history.append(entry)
        
        # Keep history bounded
        if len(self._signal_history) > 500:
            self._signal_history = self._signal_history[-250:]
            
        # Log based on urgency
        if recommendation.urgency >= 80:
            logger.warning(f"[ConfluenceExit] {recommendation.classification.value.upper()}: "
                         f"#{recommendation.ticket} - {recommendation.reason}")
        else:
            logger.info(f"[ConfluenceExit] {recommendation.classification.value}: "
                       f"#{recommendation.ticket} - {recommendation.reason}")
                       
    def get_tracked_positions(self) -> Dict[int, TrackedPosition]:
        """Get all tracked positions."""
        return dict(self._positions)
        
    def get_signal_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent signal history."""
        return self._signal_history[-limit:]
        
    def get_statistics(self) -> Dict[str, Any]:
        """Get manager statistics."""
        return {
            'positions_tracked': len(self._positions),
            'signals_generated': len(self._signal_history),
            'thresholds': {
                'scale_out': self.scale_out_threshold,
                'close_now': self.close_now_threshold
            }
        }


# Integration with ExitCoordinator
class ConfluenceExitStrategy:
    """
    Exit strategy wrapper for ExitCoordinator integration.
    
    Wraps ConfluenceExitManager for use with the exit coordinator system.
    """
    
    def __init__(self, manager: Optional[ConfluenceExitManager] = None, 
                 params: Optional[Dict[str, Any]] = None):
        """Initialize strategy."""
        self.name = "ConfluenceExit"
        self.priority = 75  # High priority
        self._enabled = True
        self.manager = manager or ConfluenceExitManager(params)
        
    def should_exit(self, position: Any, current_data: Dict[str, Any]) -> Optional[Any]:
        """Check if position should exit based on confluence."""
        if not self._enabled:
            return None
            
        ticket = getattr(position, 'ticket', 0)
        current_price = current_data.get('current_price', getattr(position, 'current_price', 0))
        indicators = current_data.get('indicators', {})
        balance = current_data.get('account_balance', 0)
        
        # Ensure position is tracked
        if ticket not in self.manager._positions:
            self.manager.track_position(
                ticket=ticket,
                symbol=getattr(position, 'symbol', 'UNKNOWN'),
                side=getattr(position, 'side', 'BUY'),
                entry_price=getattr(position, 'open_price', current_price),
                volume=getattr(position, 'volume', 0.01)
            )
            
        # Evaluate
        recommendation = self.manager.evaluate_exit(ticket, current_price, indicators, balance)
        
        if recommendation and recommendation.classification != ExitClassification.HOLD:
            # Convert to ExitSignal
            from .base import ExitSignal
            
            return ExitSignal(
                ticket=ticket,
                reason=recommendation.reason,
                price=current_price,
                timestamp=datetime.now(timezone.utc),
                strategy_name=self.name,
                confidence=recommendation.confidence,
                partial_volume=recommendation.partial_pct * getattr(position, 'volume', 0.01) if recommendation.partial_pct else None,
                priority=recommendation.urgency,
                metadata={
                    'classification': recommendation.classification.value,
                    'confluence_score': recommendation.confluence_score,
                    'indicators': recommendation.indicators_agreeing,
                    'action': recommendation.suggested_action
                }
            )
            
        return None
        
    def enable(self):
        """Enable strategy."""
        self._enabled = True
        
    def disable(self):
        """Disable strategy."""
        self._enabled = False
        
    def reset(self):
        """Reset strategy state."""
        self.manager._positions.clear()
        self.manager._signal_history.clear()


# Factory function
def create_confluence_exit_manager(config: Optional[Dict[str, Any]] = None) -> ConfluenceExitManager:
    """Create configured ConfluenceExitManager."""
    return ConfluenceExitManager(config)
