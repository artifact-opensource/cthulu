"""
Pattern Recognition Module

Leverages Hektor vector database for semantic pattern matching.
Identifies similar historical market patterns and analyzes their outcomes.
"""

import logging
import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class PatternType(Enum):
    """Chart pattern types"""
    HEAD_AND_SHOULDERS = "head_and_shoulders"
    INVERSE_HEAD_AND_SHOULDERS = "inverse_head_and_shoulders"
    DOUBLE_TOP = "double_top"
    DOUBLE_BOTTOM = "double_bottom"
    TRIPLE_TOP = "triple_top"
    TRIPLE_BOTTOM = "triple_bottom"
    ASCENDING_TRIANGLE = "ascending_triangle"
    DESCENDING_TRIANGLE = "descending_triangle"
    SYMMETRICAL_TRIANGLE = "symmetrical_triangle"
    RISING_WEDGE = "rising_wedge"
    FALLING_WEDGE = "falling_wedge"
    BULL_FLAG = "bull_flag"
    BEAR_FLAG = "bear_flag"
    CUP_AND_HANDLE = "cup_and_handle"
    ROUNDING_BOTTOM = "rounding_bottom"
    ROUNDING_TOP = "rounding_top"


@dataclass
class PatternMatch:
    """A matched historical pattern"""
    pattern_type: PatternType
    similarity_score: float
    historical_outcome: str  # WIN, LOSS, BREAKEVEN
    pnl: float
    duration_bars: int
    entry_price: float
    exit_price: float
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'pattern_type': self.pattern_type.value,
            'similarity_score': self.similarity_score,
            'outcome': self.historical_outcome,
            'pnl': self.pnl,
            'duration_bars': self.duration_bars,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'timestamp': self.timestamp.isoformat(),
            'metadata': self.metadata
        }


@dataclass
class PatternAnalysis:
    """Analysis of pattern matches"""
    pattern_type: PatternType
    total_matches: int
    win_rate: float
    avg_pnl: float
    avg_duration_bars: int
    confidence_score: float
    recommendation: str  # STRONG_BUY, BUY, NEUTRAL, SELL, STRONG_SELL
    matches: List[PatternMatch] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'pattern_type': self.pattern_type.value,
            'total_matches': self.total_matches,
            'win_rate': self.win_rate,
            'avg_pnl': self.avg_pnl,
            'avg_duration_bars': self.avg_duration_bars,
            'confidence_score': self.confidence_score,
            'recommendation': self.recommendation,
            'matches': [m.to_dict() for m in self.matches]
        }


class PatternRecognizer:
    """
    Recognizes chart patterns and queries Hektor for similar historical patterns.
    
    Uses semantic search to find similar market conditions and analyze outcomes.
    """
    
    def __init__(self, vector_adapter=None, retriever=None):
        """
        Initialize pattern recognizer.
        
        Args:
            vector_adapter: VectorStudioAdapter instance
            retriever: ContextRetriever instance
        """
        self.vector_adapter = vector_adapter
        self.retriever = retriever
        self.logger = logging.getLogger(__name__)
        
        # Pattern detection thresholds
        self.min_pattern_bars = 10
        self.max_pattern_bars = 100
        self.min_similarity_score = 0.65
        
    def detect_patterns(
        self,
        data: pd.DataFrame,
        lookback_bars: int = 50
    ) -> List[PatternType]:
        """
        Detect chart patterns in recent price data.
        
        Args:
            data: DataFrame with OHLCV data
            lookback_bars: Number of bars to analyze
            
        Returns:
            List of detected pattern types
        """
        detected = []
        
        if len(data) < self.min_pattern_bars:
            return detected
            
        recent_data = data.tail(lookback_bars)
        
        # Detect various patterns
        if self._detect_head_and_shoulders(recent_data):
            detected.append(PatternType.HEAD_AND_SHOULDERS)
            
        if self._detect_double_top(recent_data):
            detected.append(PatternType.DOUBLE_TOP)
            
        if self._detect_double_bottom(recent_data):
            detected.append(PatternType.DOUBLE_BOTTOM)
            
        if self._detect_ascending_triangle(recent_data):
            detected.append(PatternType.ASCENDING_TRIANGLE)
            
        if self._detect_descending_triangle(recent_data):
            detected.append(PatternType.DESCENDING_TRIANGLE)
            
        if self._detect_bull_flag(recent_data):
            detected.append(PatternType.BULL_FLAG)
            
        if self._detect_bear_flag(recent_data):
            detected.append(PatternType.BEAR_FLAG)
            
        return detected
    
    def analyze_pattern(
        self,
        pattern_type: PatternType,
        current_data: pd.DataFrame,
        symbol: str,
        k: int = 20
    ) -> Optional[PatternAnalysis]:
        """
        Analyze a detected pattern by querying similar historical patterns.
        
        Args:
            pattern_type: Type of pattern detected
            current_data: Current market data
            symbol: Trading symbol
            k: Number of similar patterns to retrieve
            
        Returns:
            PatternAnalysis with historical outcomes
        """
        if not self.retriever:
            self.logger.warning("No retriever available for pattern analysis")
            return None
            
        try:
            # Build pattern description for semantic search
            pattern_desc = self._build_pattern_description(
                pattern_type, current_data, symbol
            )
            
            # Query Hektor for similar patterns
            similar_contexts = self.retriever.get_pattern_matches(
                pattern_description=pattern_desc,
                timeframe=self._get_timeframe(current_data),
                k=k,
                min_score=self.min_similarity_score
            )
            
            if not similar_contexts:
                self.logger.info(f"No similar {pattern_type.value} patterns found")
                return None
                
            # Parse matches
            matches = []
            for ctx in similar_contexts:
                match = self._parse_pattern_match(ctx, pattern_type)
                if match:
                    matches.append(match)
                    
            if not matches:
                return None
                
            # Analyze outcomes
            analysis = self._analyze_outcomes(pattern_type, matches)
            
            self.logger.info(
                f"Pattern analysis: {pattern_type.value} - "
                f"{len(matches)} matches, {analysis.win_rate:.1%} win rate, "
                f"recommendation: {analysis.recommendation}"
            )
            
            return analysis
            
        except Exception as e:
            self.logger.error(f"Error analyzing pattern: {e}", exc_info=True)
            return None
    
    def get_pattern_confidence_adjustment(
        self,
        detected_patterns: List[PatternType],
        current_data: pd.DataFrame,
        symbol: str,
        base_confidence: float
    ) -> float:
        """
        Adjust signal confidence based on detected patterns.
        
        Args:
            detected_patterns: List of detected patterns
            current_data: Current market data
            symbol: Trading symbol
            base_confidence: Base confidence score
            
        Returns:
            Adjusted confidence score
        """
        if not detected_patterns:
            return base_confidence
            
        adjustments = []
        
        for pattern in detected_patterns:
            analysis = self.analyze_pattern(pattern, current_data, symbol)
            
            if analysis and analysis.total_matches >= 5:
                # Calculate adjustment based on historical performance
                if analysis.win_rate > 0.6 and analysis.avg_pnl > 0:
                    # Positive pattern - boost confidence
                    adjustment = min(0.15, analysis.win_rate * 0.2)
                    adjustments.append(adjustment)
                elif analysis.win_rate < 0.4 or analysis.avg_pnl < 0:
                    # Negative pattern - reduce confidence
                    adjustment = -min(0.15, (1 - analysis.win_rate) * 0.2)
                    adjustments.append(adjustment)
                    
        if adjustments:
            # Average adjustments and apply
            avg_adjustment = np.mean(adjustments)
            adjusted = base_confidence + avg_adjustment
            return np.clip(adjusted, 0.0, 1.0)
            
        return base_confidence
    
    # Pattern detection methods
    
    def _detect_head_and_shoulders(self, data: pd.DataFrame) -> bool:
        """Detect head and shoulders pattern"""
        if len(data) < 20:
            return False
            
        highs = data['high'].values
        
        # Find three peaks
        peaks = self._find_peaks(highs, min_distance=5)
        
        if len(peaks) < 3:
            return False
            
        # Check if middle peak is highest
        recent_peaks = peaks[-3:]
        middle_idx = recent_peaks[1]
        left_idx = recent_peaks[0]
        right_idx = recent_peaks[2]
        
        middle_high = highs[middle_idx]
        left_high = highs[left_idx]
        right_high = highs[right_idx]
        
        # Head should be higher than shoulders
        if middle_high > left_high and middle_high > right_high:
            # Shoulders should be roughly equal
            shoulder_diff = abs(left_high - right_high) / middle_high
            if shoulder_diff < 0.02:  # Within 2%
                return True
                
        return False
    
    def _detect_double_top(self, data: pd.DataFrame) -> bool:
        """Detect double top pattern"""
        if len(data) < 15:
            return False
            
        highs = data['high'].values
        peaks = self._find_peaks(highs, min_distance=5)
        
        if len(peaks) < 2:
            return False
            
        # Check last two peaks
        peak1_idx = peaks[-2]
        peak2_idx = peaks[-1]
        
        peak1 = highs[peak1_idx]
        peak2 = highs[peak2_idx]
        
        # Peaks should be roughly equal (within 1%)
        if abs(peak1 - peak2) / peak1 < 0.01:
            # Check for valley between peaks
            valley = highs[peak1_idx:peak2_idx].min()
            if valley < peak1 * 0.98:  # At least 2% retracement
                return True
                
        return False
    
    def _detect_double_bottom(self, data: pd.DataFrame) -> bool:
        """Detect double bottom pattern"""
        if len(data) < 15:
            return False
            
        lows = data['low'].values
        troughs = self._find_troughs(lows, min_distance=5)
        
        if len(troughs) < 2:
            return False
            
        # Check last two troughs
        trough1_idx = troughs[-2]
        trough2_idx = troughs[-1]
        
        trough1 = lows[trough1_idx]
        trough2 = lows[trough2_idx]
        
        # Troughs should be roughly equal (within 1%)
        if abs(trough1 - trough2) / trough1 < 0.01:
            # Check for peak between troughs
            peak = lows[trough1_idx:trough2_idx].max()
            if peak > trough1 * 1.02:  # At least 2% rally
                return True
                
        return False
    
    def _detect_ascending_triangle(self, data: pd.DataFrame) -> bool:
        """Detect ascending triangle pattern"""
        if len(data) < 20:
            return False
            
        highs = data['high'].values
        lows = data['low'].values
        
        # Find resistance (flat top)
        recent_highs = highs[-20:]
        resistance = recent_highs.max()
        
        # Count touches near resistance
        touches = np.sum(recent_highs > resistance * 0.995)
        
        if touches >= 2:
            # Check for rising lows
            recent_lows = lows[-20:]
            if self._is_rising_trend(recent_lows):
                return True
                
        return False
    
    def _detect_descending_triangle(self, data: pd.DataFrame) -> bool:
        """Detect descending triangle pattern"""
        if len(data) < 20:
            return False
            
        highs = data['high'].values
        lows = data['low'].values
        
        # Find support (flat bottom)
        recent_lows = lows[-20:]
        support = recent_lows.min()
        
        # Count touches near support
        touches = np.sum(recent_lows < support * 1.005)
        
        if touches >= 2:
            # Check for falling highs
            recent_highs = highs[-20:]
            if self._is_falling_trend(recent_highs):
                return True
                
        return False
    
    def _detect_bull_flag(self, data: pd.DataFrame) -> bool:
        """Detect bullish flag pattern"""
        if len(data) < 15:
            return False
            
        closes = data['close'].values
        
        # Check for strong uptrend (pole)
        pole_start = closes[-15]
        pole_end = closes[-10]
        
        if pole_end > pole_start * 1.03:  # At least 3% rally
            # Check for consolidation (flag)
            flag_data = closes[-10:]
            if self._is_consolidating(flag_data):
                return True
                
        return False
    
    def _detect_bear_flag(self, data: pd.DataFrame) -> bool:
        """Detect bearish flag pattern"""
        if len(data) < 15:
            return False
            
        closes = data['close'].values
        
        # Check for strong downtrend (pole)
        pole_start = closes[-15]
        pole_end = closes[-10]
        
        if pole_end < pole_start * 0.97:  # At least 3% decline
            # Check for consolidation (flag)
            flag_data = closes[-10:]
            if self._is_consolidating(flag_data):
                return True
                
        return False
    
    # Helper methods
    
    def _find_peaks(self, data: np.ndarray, min_distance: int = 5) -> List[int]:
        """Find peaks in data"""
        peaks = []
        for i in range(min_distance, len(data) - min_distance):
            if all(data[i] > data[i-j] for j in range(1, min_distance + 1)):
                if all(data[i] > data[i+j] for j in range(1, min_distance + 1)):
                    peaks.append(i)
        return peaks
    
    def _find_troughs(self, data: np.ndarray, min_distance: int = 5) -> List[int]:
        """Find troughs in data"""
        troughs = []
        for i in range(min_distance, len(data) - min_distance):
            if all(data[i] < data[i-j] for j in range(1, min_distance + 1)):
                if all(data[i] < data[i+j] for j in range(1, min_distance + 1)):
                    troughs.append(i)
        return troughs
    
    def _is_rising_trend(self, data: np.ndarray) -> bool:
        """Check if data shows rising trend"""
        if len(data) < 3:
            return False
        # Simple linear regression slope
        x = np.arange(len(data))
        slope = np.polyfit(x, data, 1)[0]
        return slope > 0
    
    def _is_falling_trend(self, data: np.ndarray) -> bool:
        """Check if data shows falling trend"""
        if len(data) < 3:
            return False
        x = np.arange(len(data))
        slope = np.polyfit(x, data, 1)[0]
        return slope < 0
    
    def _is_consolidating(self, data: np.ndarray, threshold: float = 0.02) -> bool:
        """Check if data is consolidating (low volatility)"""
        if len(data) < 3:
            return False
        volatility = np.std(data) / np.mean(data)
        return volatility < threshold
    
    def _build_pattern_description(
        self,
        pattern_type: PatternType,
        data: pd.DataFrame,
        symbol: str
    ) -> str:
        """Build natural language pattern description for semantic search"""
        recent = data.tail(20)
        
        desc = f"[Pattern] {pattern_type.value} detected on {symbol}\n"
        desc += f"Price: {recent['close'].iloc[-1]:.5f}\n"
        desc += f"Range: {recent['low'].min():.5f} - {recent['high'].max():.5f}\n"
        desc += f"Volatility: {recent['close'].std():.5f}\n"
        
        # Add trend context
        if self._is_rising_trend(recent['close'].values):
            desc += "Trend: Bullish\n"
        elif self._is_falling_trend(recent['close'].values):
            desc += "Trend: Bearish\n"
        else:
            desc += "Trend: Sideways\n"
            
        return desc
    
    def _get_timeframe(self, data: pd.DataFrame) -> str:
        """Infer timeframe from data"""
        if len(data) < 2:
            return "M15"
            
        time_diff = (data.index[-1] - data.index[-2]).total_seconds()
        
        if time_diff <= 60:
            return "M1"
        elif time_diff <= 300:
            return "M5"
        elif time_diff <= 900:
            return "M15"
        elif time_diff <= 1800:
            return "M30"
        elif time_diff <= 3600:
            return "H1"
        elif time_diff <= 14400:
            return "H4"
        else:
            return "D1"
    
    def _parse_pattern_match(
        self,
        context: Any,
        pattern_type: PatternType
    ) -> Optional[PatternMatch]:
        """Parse a similar context into a PatternMatch"""
        try:
            metadata = context.metadata
            
            return PatternMatch(
                pattern_type=pattern_type,
                similarity_score=context.score,
                historical_outcome=metadata.get('outcome', 'UNKNOWN'),
                pnl=metadata.get('pnl', 0.0),
                duration_bars=metadata.get('duration_bars', 0),
                entry_price=metadata.get('entry_price', 0.0),
                exit_price=metadata.get('exit_price', 0.0),
                timestamp=datetime.fromisoformat(metadata.get('timestamp', datetime.now().isoformat())),
                metadata=metadata
            )
        except Exception as e:
            self.logger.error(f"Error parsing pattern match: {e}")
            return None
    
    def _analyze_outcomes(
        self,
        pattern_type: PatternType,
        matches: List[PatternMatch]
    ) -> PatternAnalysis:
        """Analyze historical pattern outcomes"""
        total = len(matches)
        wins = sum(1 for m in matches if m.historical_outcome == 'WIN')
        win_rate = wins / total if total > 0 else 0.0
        
        avg_pnl = np.mean([m.pnl for m in matches]) if matches else 0.0
        avg_duration = int(np.mean([m.duration_bars for m in matches])) if matches else 0
        
        # Calculate confidence score
        confidence = self._calculate_pattern_confidence(
            total, win_rate, avg_pnl, matches
        )
        
        # Generate recommendation
        recommendation = self._generate_recommendation(win_rate, avg_pnl, confidence)
        
        return PatternAnalysis(
            pattern_type=pattern_type,
            total_matches=total,
            win_rate=win_rate,
            avg_pnl=avg_pnl,
            avg_duration_bars=avg_duration,
            confidence_score=confidence,
            recommendation=recommendation,
            matches=matches
        )
    
    def _calculate_pattern_confidence(
        self,
        total_matches: int,
        win_rate: float,
        avg_pnl: float,
        matches: List[PatternMatch]
    ) -> float:
        """Calculate confidence score for pattern"""
        # Base confidence on sample size
        sample_confidence = min(1.0, total_matches / 20)
        
        # Adjust for win rate
        win_rate_factor = win_rate
        
        # Adjust for profitability
        pnl_factor = 1.0 if avg_pnl > 0 else 0.5
        
        # Adjust for similarity scores
        avg_similarity = np.mean([m.similarity_score for m in matches]) if matches else 0.0
        
        confidence = (
            sample_confidence * 0.3 +
            win_rate_factor * 0.3 +
            pnl_factor * 0.2 +
            avg_similarity * 0.2
        )
        
        return np.clip(confidence, 0.0, 1.0)
    
    def _generate_recommendation(
        self,
        win_rate: float,
        avg_pnl: float,
        confidence: float
    ) -> str:
        """Generate trading recommendation"""
        if confidence < 0.4:
            return "NEUTRAL"
            
        if win_rate > 0.65 and avg_pnl > 0:
            return "STRONG_BUY" if confidence > 0.7 else "BUY"
        elif win_rate < 0.35 or avg_pnl < 0:
            return "STRONG_SELL" if confidence > 0.7 else "SELL"
        else:
            return "NEUTRAL"
