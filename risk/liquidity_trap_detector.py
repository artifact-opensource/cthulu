"""
Liquidity Trap Detection & Market Flip Protection

Advanced market microstructure analysis for detecting:
1. Liquidity traps (stop hunts, fakeouts)
2. Market regime flips
3. Institutional footprints
4. Volume anomalies

This module protects against:
- Stop hunts that trigger stops before reversing
- Fakeout breakouts designed to trap retail traders
- Sudden regime changes (trend → range, bullish → bearish)
- Low liquidity periods with high slippage risk

Philosophy:
- Smart money leaves footprints
- Extreme moves on low volume = trap
- Sudden spikes into support/resistance = stop hunt
- Volume divergence signals manipulation
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from collections import deque
import statistics

logger = logging.getLogger(__name__)


@dataclass
class LiquidityTrapSignal:
    """Signal indicating potential liquidity trap."""
    trap_type: str  # "stop_hunt", "fakeout", "volume_divergence", "regime_flip"
    confidence: float  # 0.0 to 1.0
    direction: str  # "bullish_trap" or "bearish_trap"
    price_level: float
    timestamp: datetime
    metadata: Dict[str, Any]


class LiquidityTrapDetector:
    """
    Detects liquidity traps and market manipulation patterns.
    
    Implements multiple detection methods:
    1. **Stop Hunt Detection**: Spike beyond S/R then quick reversal
    2. **Fakeout Detection**: Breakout on low volume
    3. **Volume Divergence**: Price move without volume confirmation
    4. **Regime Flip Detection**: Sudden trend reversal signals
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        config = config or {}
        
        # Detection parameters
        self.spike_threshold_pct = config.get('spike_threshold_pct', 0.3)  # 0.3% = potential stop hunt
        self.reversal_bars = config.get('reversal_bars', 3)  # Bars to confirm reversal
        self.volume_divergence_mult = config.get('volume_divergence_mult', 0.5)  # 50% below avg = suspicious
        self.fakeout_volume_mult = config.get('fakeout_volume_mult', 0.7)  # Breakout on <70% volume = fakeout
        
        # State tracking
        self._price_history: deque = deque(maxlen=100)
        self._volume_history: deque = deque(maxlen=50)
        self._swing_highs: List[float] = []
        self._swing_lows: List[float] = []
        self._recent_traps: List[LiquidityTrapSignal] = []
        
        # Moving averages
        self._avg_volume: float = 0
        self._avg_range: float = 0
        
    def update(self, bar_data: Dict[str, Any]) -> Optional[LiquidityTrapSignal]:
        """
        Update detector with new bar data and check for traps.
        
        Args:
            bar_data: OHLCV data for current bar
            
        Returns:
            LiquidityTrapSignal if trap detected, None otherwise
        """
        high = bar_data.get('high', 0)
        low = bar_data.get('low', 0)
        close = bar_data.get('close', 0)
        open_price = bar_data.get('open', close)
        volume = bar_data.get('volume', 0)
        
        # Update history
        self._price_history.append({
            'high': high,
            'low': low,
            'close': close,
            'open': open_price,
            'volume': volume,
            'timestamp': datetime.now()
        })
        
        if volume > 0:
            self._volume_history.append(volume)
            
        # Update averages
        if len(self._volume_history) >= 10:
            self._avg_volume = statistics.mean(self._volume_history)
            
        if len(self._price_history) >= 10:
            ranges = [p['high'] - p['low'] for p in list(self._price_history)[-10:]]
            self._avg_range = statistics.mean(ranges)
            
        # Update swing points
        self._update_swing_points()
        
        # Run detection algorithms
        trap = None
        
        # Check for stop hunt
        trap = self._detect_stop_hunt(bar_data)
        if trap:
            return trap
            
        # Check for fakeout
        trap = self._detect_fakeout(bar_data)
        if trap:
            return trap
            
        # Check for volume divergence
        trap = self._detect_volume_divergence(bar_data)
        if trap:
            return trap
            
        # Check for regime flip
        trap = self._detect_regime_flip(bar_data)
        if trap:
            return trap
            
        return None
        
    def _update_swing_points(self):
        """Update swing high/low levels for trap detection."""
        if len(self._price_history) < 5:
            return
            
        recent = list(self._price_history)[-5:]
        
        # Check for swing high (middle bar highest)
        if (recent[2]['high'] > recent[1]['high'] and 
            recent[2]['high'] > recent[3]['high'] and
            recent[2]['high'] > recent[0]['high'] and
            recent[2]['high'] > recent[4]['high']):
            if recent[2]['high'] not in self._swing_highs[-5:] if self._swing_highs else True:
                self._swing_highs.append(recent[2]['high'])
                if len(self._swing_highs) > 20:
                    self._swing_highs = self._swing_highs[-20:]
                    
        # Check for swing low
        if (recent[2]['low'] < recent[1]['low'] and 
            recent[2]['low'] < recent[3]['low'] and
            recent[2]['low'] < recent[0]['low'] and
            recent[2]['low'] < recent[4]['low']):
            if recent[2]['low'] not in self._swing_lows[-5:] if self._swing_lows else True:
                self._swing_lows.append(recent[2]['low'])
                if len(self._swing_lows) > 20:
                    self._swing_lows = self._swing_lows[-20:]
                    
    def _detect_stop_hunt(self, bar_data: Dict[str, Any]) -> Optional[LiquidityTrapSignal]:
        """
        Detect stop hunt patterns.
        
        Stop hunt signature:
        - Price spikes beyond recent swing high/low
        - Quick reversal back inside range
        - Often on slightly elevated volume
        """
        if len(self._price_history) < 10:
            return None
            
        high = bar_data.get('high', 0)
        low = bar_data.get('low', 0)
        close = bar_data.get('close', 0)
        open_price = bar_data.get('open', close)
        
        # Check for bearish stop hunt (spike high then close low)
        if self._swing_highs:
            recent_high = max(self._swing_highs[-3:]) if len(self._swing_highs) >= 3 else self._swing_highs[-1]
            
            # Spike above recent high but close below it
            if high > recent_high * 1.001 and close < recent_high:
                # Confirm with wick analysis (long upper wick)
                body = abs(close - open_price)
                upper_wick = high - max(close, open_price)
                
                if upper_wick > body * 2:  # Upper wick 2x body = rejection
                    logger.warning(f"[TRAP] Stop hunt detected: Bearish - spiked to {high}, closed at {close}")
                    return LiquidityTrapSignal(
                        trap_type="stop_hunt",
                        confidence=0.85,
                        direction="bearish_trap",
                        price_level=high,
                        timestamp=datetime.now(),
                        metadata={
                            'swing_high': recent_high,
                            'spike_high': high,
                            'close': close,
                            'upper_wick_ratio': upper_wick / body if body > 0 else 999
                        }
                    )
                    
        # Check for bullish stop hunt (spike low then close high)
        if self._swing_lows:
            recent_low = min(self._swing_lows[-3:]) if len(self._swing_lows) >= 3 else self._swing_lows[-1]
            
            if low < recent_low * 0.999 and close > recent_low:
                body = abs(close - open_price)
                lower_wick = min(close, open_price) - low
                
                if lower_wick > body * 2:
                    logger.warning(f"[TRAP] Stop hunt detected: Bullish - spiked to {low}, closed at {close}")
                    return LiquidityTrapSignal(
                        trap_type="stop_hunt",
                        confidence=0.85,
                        direction="bullish_trap",
                        price_level=low,
                        timestamp=datetime.now(),
                        metadata={
                            'swing_low': recent_low,
                            'spike_low': low,
                            'close': close,
                            'lower_wick_ratio': lower_wick / body if body > 0 else 999
                        }
                    )
                    
        return None
        
    def _detect_fakeout(self, bar_data: Dict[str, Any]) -> Optional[LiquidityTrapSignal]:
        """
        Detect fakeout breakouts.
        
        Fakeout signature:
        - Breakout beyond consolidation range
        - Low volume compared to average
        - Quick reversal back inside range
        """
        if len(self._price_history) < 20 or self._avg_volume <= 0:
            return None
            
        volume = bar_data.get('volume', 0)
        close = bar_data.get('close', 0)
        
        # Check volume relative to average
        if volume < self._avg_volume * self.fakeout_volume_mult:
            # Low volume - check if price made new extreme
            recent_closes = [p['close'] for p in list(self._price_history)[-20:-1]]
            recent_high = max(recent_closes)
            recent_low = min(recent_closes)
            
            if close > recent_high:
                logger.warning(f"[TRAP] Potential fakeout: Breakout high on low volume ({volume}/{self._avg_volume:.0f})")
                return LiquidityTrapSignal(
                    trap_type="fakeout",
                    confidence=0.70,
                    direction="bearish_trap",  # Fakeout high = bearish trap
                    price_level=close,
                    timestamp=datetime.now(),
                    metadata={
                        'volume': volume,
                        'avg_volume': self._avg_volume,
                        'volume_ratio': volume / self._avg_volume,
                        'breakout_type': 'high'
                    }
                )
                
            if close < recent_low:
                logger.warning(f"[TRAP] Potential fakeout: Breakout low on low volume ({volume}/{self._avg_volume:.0f})")
                return LiquidityTrapSignal(
                    trap_type="fakeout",
                    confidence=0.70,
                    direction="bullish_trap",  # Fakeout low = bullish trap
                    price_level=close,
                    timestamp=datetime.now(),
                    metadata={
                        'volume': volume,
                        'avg_volume': self._avg_volume,
                        'volume_ratio': volume / self._avg_volume,
                        'breakout_type': 'low'
                    }
                )
                
        return None
        
    def _detect_volume_divergence(self, bar_data: Dict[str, Any]) -> Optional[LiquidityTrapSignal]:
        """
        Detect price moves without volume confirmation.
        
        Signature:
        - Large price move (> 1.5x avg range)
        - Volume below average
        - Signals potential reversal
        """
        if len(self._price_history) < 15 or self._avg_volume <= 0 or self._avg_range <= 0:
            return None
            
        high = bar_data.get('high', 0)
        low = bar_data.get('low', 0)
        volume = bar_data.get('volume', 0)
        
        current_range = high - low
        
        # Large move on low volume
        if current_range > self._avg_range * 1.5 and volume < self._avg_volume * self.volume_divergence_mult:
            close = bar_data.get('close', 0)
            open_price = bar_data.get('open', close)
            
            direction = "bearish_trap" if close > open_price else "bullish_trap"
            
            logger.warning(
                f"[TRAP] Volume divergence: Range {current_range:.2f} vs avg {self._avg_range:.2f}, "
                f"Volume {volume} vs avg {self._avg_volume:.0f}"
            )
            
            return LiquidityTrapSignal(
                trap_type="volume_divergence",
                confidence=0.65,
                direction=direction,
                price_level=close,
                timestamp=datetime.now(),
                metadata={
                    'range': current_range,
                    'avg_range': self._avg_range,
                    'range_ratio': current_range / self._avg_range,
                    'volume': volume,
                    'avg_volume': self._avg_volume,
                    'volume_ratio': volume / self._avg_volume
                }
            )
            
        return None
        
    def _detect_regime_flip(self, bar_data: Dict[str, Any]) -> Optional[LiquidityTrapSignal]:
        """
        Detect sudden market regime changes.
        
        Signature:
        - Trend reversal after extended move
        - Divergence in momentum indicators
        - Break of trend structure
        """
        if len(self._price_history) < 30:
            return None
            
        recent = list(self._price_history)[-30:]
        
        # Calculate trend direction for first and last halves
        first_half = recent[:15]
        second_half = recent[15:]
        
        first_trend = first_half[-1]['close'] - first_half[0]['close']
        second_trend = second_half[-1]['close'] - second_half[0]['close']
        
        # Regime flip = opposite trends
        if first_trend > 0 and second_trend < 0:
            # Was bullish, now bearish
            if abs(second_trend) > abs(first_trend) * 0.5:  # Significant reversal
                logger.warning("[TRAP] Regime flip detected: Bullish → Bearish")
                return LiquidityTrapSignal(
                    trap_type="regime_flip",
                    confidence=0.75,
                    direction="bearish_trap",
                    price_level=bar_data.get('close', 0),
                    timestamp=datetime.now(),
                    metadata={
                        'first_half_move': first_trend,
                        'second_half_move': second_trend,
                        'flip_type': 'bullish_to_bearish'
                    }
                )
                
        elif first_trend < 0 and second_trend > 0:
            # Was bearish, now bullish
            if abs(second_trend) > abs(first_trend) * 0.5:
                logger.warning("[TRAP] Regime flip detected: Bearish → Bullish")
                return LiquidityTrapSignal(
                    trap_type="regime_flip",
                    confidence=0.75,
                    direction="bullish_trap",
                    price_level=bar_data.get('close', 0),
                    timestamp=datetime.now(),
                    metadata={
                        'first_half_move': first_trend,
                        'second_half_move': second_trend,
                        'flip_type': 'bearish_to_bullish'
                    }
                )
                
        return None
        
    def get_trap_avoidance_recommendation(self, trap: LiquidityTrapSignal) -> Dict[str, Any]:
        """
        Get recommendation for avoiding/exploiting a detected trap.
        
        Returns trading recommendations based on trap type.
        """
        recommendations = {
            'action': 'wait',
            'reason': '',
            'alternative': None
        }
        
        if trap.trap_type == "stop_hunt":
            if trap.direction == "bearish_trap":
                recommendations = {
                    'action': 'short',
                    'reason': 'Stop hunt completed - smart money accumulated shorts',
                    'entry': trap.price_level * 0.998,  # Enter slightly below spike
                    'stop_loss': trap.price_level * 1.002,
                    'confidence': trap.confidence
                }
            else:
                recommendations = {
                    'action': 'long',
                    'reason': 'Stop hunt completed - smart money accumulated longs',
                    'entry': trap.price_level * 1.002,
                    'stop_loss': trap.price_level * 0.998,
                    'confidence': trap.confidence
                }
                
        elif trap.trap_type == "fakeout":
            recommendations = {
                'action': 'fade',
                'reason': 'Fakeout detected - fade the move',
                'entry': trap.price_level,
                'confidence': trap.confidence * 0.8  # Lower confidence for fakeouts
            }
            
        elif trap.trap_type == "volume_divergence":
            recommendations = {
                'action': 'wait',
                'reason': 'Volume divergence - wait for confirmation',
                'wait_bars': 3,
                'confidence': trap.confidence
            }
            
        elif trap.trap_type == "regime_flip":
            if trap.direction == "bearish_trap":
                recommendations = {
                    'action': 'short',
                    'reason': 'Regime flipped bearish - follow new trend',
                    'confidence': trap.confidence
                }
            else:
                recommendations = {
                    'action': 'long',
                    'reason': 'Regime flipped bullish - follow new trend',
                    'confidence': trap.confidence
                }
                
        return recommendations
        
    def should_avoid_entry(self, bar_data: Dict[str, Any], signal_direction: str) -> Tuple[bool, str]:
        """
        Check if current conditions suggest avoiding entry.
        
        Args:
            bar_data: Current bar data
            signal_direction: "long" or "short"
            
        Returns:
            (should_avoid, reason)
        """
        trap = self.update(bar_data)
        
        if trap is None:
            return False, ""
            
        # If trap detected, check if it conflicts with signal
        if trap.direction == "bearish_trap" and signal_direction == "long":
            return True, f"Bearish trap detected ({trap.trap_type}) - avoid long entry"
            
        if trap.direction == "bullish_trap" and signal_direction == "short":
            return True, f"Bullish trap detected ({trap.trap_type}) - avoid short entry"
            
        return False, ""


class MarketFlipProtector:
    """
    Protects positions against sudden market flips.
    
    Monitors for:
    - Momentum reversal
    - Volume surge in opposite direction
    - Break of key levels
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        config = config or {}
        self.momentum_threshold = config.get('momentum_threshold', 30)  # RSI threshold
        self.volume_surge_mult = config.get('volume_surge_mult', 2.0)  # 2x avg = surge
        
        self._position_entry_data: Dict[int, Dict] = {}  # Track entry conditions per position
        
    def register_position(self, ticket: int, entry_data: Dict[str, Any]):
        """Register a new position with entry conditions."""
        self._position_entry_data[ticket] = {
            'entry_price': entry_data.get('price', 0),
            'entry_rsi': entry_data.get('rsi', 50),
            'entry_volume': entry_data.get('volume', 0),
            'entry_trend': entry_data.get('trend', 'neutral'),
            'side': entry_data.get('side', 'long'),
            'timestamp': datetime.now()
        }
        
    def check_flip_protection(
        self,
        ticket: int,
        current_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Check if position needs flip protection.
        
        Returns exit recommendation if flip detected.
        """
        if ticket not in self._position_entry_data:
            return None
            
        entry = self._position_entry_data[ticket]
        
        current_rsi = current_data.get('rsi', 50)
        current_volume = current_data.get('volume', 0)
        avg_volume = current_data.get('avg_volume', current_volume)
        
        is_long = entry['side'] == 'long'
        
        # Check momentum flip
        if is_long:
            # Long position: danger if RSI drops sharply
            if entry['entry_rsi'] > 50 and current_rsi < self.momentum_threshold:
                return {
                    'action': 'exit',
                    'reason': f'Momentum flip: RSI dropped from {entry["entry_rsi"]:.0f} to {current_rsi:.0f}',
                    'urgency': 'high'
                }
        else:
            # Short position: danger if RSI rises sharply
            if entry['entry_rsi'] < 50 and current_rsi > (100 - self.momentum_threshold):
                return {
                    'action': 'exit',
                    'reason': f'Momentum flip: RSI rose from {entry["entry_rsi"]:.0f} to {current_rsi:.0f}',
                    'urgency': 'high'
                }
                
        # Check volume surge against position
        if avg_volume > 0 and current_volume > avg_volume * self.volume_surge_mult:
            current_price = current_data.get('close', 0)
            entry_price = entry['entry_price']
            
            if is_long and current_price < entry_price:
                return {
                    'action': 'exit',
                    'reason': f'Volume surge ({current_volume/avg_volume:.1f}x) against long position',
                    'urgency': 'high'
                }
            elif not is_long and current_price > entry_price:
                return {
                    'action': 'exit',
                    'reason': f'Volume surge ({current_volume/avg_volume:.1f}x) against short position',
                    'urgency': 'high'
                }
                
        return None
        
    def remove_position(self, ticket: int):
        """Remove position from tracking."""
        if ticket in self._position_entry_data:
            del self._position_entry_data[ticket]
