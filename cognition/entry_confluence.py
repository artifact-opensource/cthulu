"""
Entry Confluence Filter - The Quality Gate

This module provides entry-level confluence analysis to ensure we only execute
trades at optimal price levels. It acts as a filter between signal generation
and order execution.

Professional trading insight: A signal is worthless without proper execution.
The edge isn't in knowing the direction - it's in the timing and level of entry.

Key concepts:
1. Price Level Analysis - Are we at a meaningful level (S/R, round numbers, FVGs)?
2. Momentum Confirmation - Is price moving in our favor or against?
3. Liquidity Considerations - Are we entering into liquidity or from it?
4. Multi-Timeframe Alignment - Does higher TF support this entry?

Part of Cthulu v6.0.0 - Entry Quality System
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from enum import Enum
import logging

# Import Order Block and Session ORB detectors
try:
    from cthulu.cognition.order_blocks import (
        OrderBlockDetector,
        OrderBlock,
        OrderBlockType,
        StructureBreak
    )
    from cthulu.cognition.session_orb import (
        SessionORBDetector,
        SessionType,
        OpeningRange
    )
    HAS_STRUCTURE_DETECTORS = True
except ImportError:
    HAS_STRUCTURE_DETECTORS = False

# Import Chart Manager for zone tracking and visual reasoning
try:
    from cthulu.cognition.chart_manager import (
        get_chart_manager,
        ChartManager,
        ZoneType,
        ZoneState
    )
    HAS_CHART_MANAGER = True
except ImportError:
    HAS_CHART_MANAGER = False

logger = logging.getLogger("cthulu.entry_confluence")


class EntryQuality(Enum):
    """Entry quality classification."""
    PREMIUM = "premium"      # Optimal entry - full position
    GOOD = "good"            # Acceptable entry - standard position
    MARGINAL = "marginal"    # Suboptimal entry - reduced position
    POOR = "poor"            # Bad entry - wait or skip
    REJECT = "reject"        # Do not enter - signal invalidated


class PriceLevelType(Enum):
    """Types of significant price levels."""
    SUPPORT = "support"
    RESISTANCE = "resistance"
    ROUND_NUMBER = "round_number"
    PIVOT = "pivot"
    VWAP = "vwap"
    EMA = "ema"
    FVG = "fair_value_gap"         # Imbalance zone
    ORDER_BLOCK = "order_block"
    PREVIOUS_HIGH = "previous_high"
    PREVIOUS_LOW = "previous_low"


@dataclass
class PriceLevel:
    """A significant price level."""
    price: float
    level_type: PriceLevelType
    strength: float  # 0-1, how strong is this level
    touches: int     # Number of times price touched this level
    last_touch: Optional[datetime] = None
    broken: bool = False
    notes: str = ""


@dataclass
class EntryConfluenceResult:
    """Result of entry confluence analysis."""
    quality: EntryQuality
    score: float              # 0-100
    should_enter: bool
    position_mult: float      # Position size multiplier (0.5 = half size)
    wait_for_better: bool     # Should we wait for better entry?
    optimal_entry: Optional[float] = None  # Better entry price if waiting
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    levels_near: List[PriceLevel] = field(default_factory=list)
    momentum_aligned: bool = True
    timing_score: float = 0.0
    level_score: float = 0.0
    
    @property
    def summary(self) -> str:
        """Get summary of entry analysis."""
        return (f"Entry: {self.quality.value} (score={self.score:.0f}), "
                f"mult={self.position_mult:.2f}, wait={self.wait_for_better}")


class EntryConfluenceFilter:
    """
    Entry Confluence Filter - Quality gate for trade entries.
    
    Analyzes whether current price is a good entry point for a signal,
    considering:
    - Proximity to key levels (S/R, round numbers, EMAs)
    - Current momentum and micro-structure
    - Risk/reward from current level
    - Multi-timeframe alignment
    
    Philosophy:
    - A bad entry can turn a winning signal into a loser
    - Wait for price to come to your level, don't chase
    - Enter from liquidity (levels where stops cluster)
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.logger = logging.getLogger("cthulu.entry_confluence")
        
        # Configuration
        self.min_score_to_enter = self.config.get('min_score_to_enter', 50)
        self.min_score_for_full_size = self.config.get('min_score_for_full_size', 75)
        self.enable_wait_mode = self.config.get('enable_wait_mode', True)
        self.max_wait_bars = self.config.get('max_wait_bars', 10)
        
        # Level detection parameters
        self.sr_lookback = self.config.get('sr_lookback', 100)
        self.sr_min_touches = self.config.get('sr_min_touches', 2)
        self.level_tolerance_atr = self.config.get('level_tolerance_atr', 0.5)
        
        # Momentum parameters
        self.momentum_bars = self.config.get('momentum_bars', 5)
        
        # Score component weights - MUST sum to 1.0
        # Distribution: Level=0.18, Momentum=0.15, Timing=0.10, Structure=0.08,
        #               Trend=0.17, BOS=0.12, OrderBlock=0.12, SessionORB=0.08
        self.level_weight = self.config.get('level_weight', 0.18)
        self.momentum_weight = self.config.get('momentum_weight', 0.15)
        self.timing_weight = self.config.get('timing_weight', 0.10)
        self.structure_weight = self.config.get('structure_weight', 0.08)
        self.trend_weight = self.config.get('trend_weight', 0.17)
        self.bos_weight = self.config.get('bos_weight', 0.12)
        self.order_block_weight = self.config.get('order_block_weight', 0.12)
        self.session_orb_weight = self.config.get('session_orb_weight', 0.08)
        
        # State: tracked levels and pending entries
        self._price_levels: Dict[str, List[PriceLevel]] = {}
        self._pending_entries: Dict[str, Dict[str, Any]] = {}
        
        # Initialize Order Block and Session ORB detectors
        self._order_block_detector = None
        self._session_orb_detector = None
        self._chart_manager = None
        self._init_structure_detectors()
        self._init_chart_manager()
        
        self.logger.info("EntryConfluenceFilter initialized with OB/ORB/ChartManager integration")
    
    def _init_chart_manager(self):
        """Initialize Chart Manager for zone tracking and visual reasoning."""
        if not HAS_CHART_MANAGER:
            self.logger.warning("Chart Manager not available - zone tracking disabled")
            return
        
        try:
            cm_config = self.config.get('chart_manager', {})
            self._chart_manager = get_chart_manager(config=cm_config)
            self.logger.debug("Chart Manager initialized")
        except Exception as e:
            self.logger.warning(f"Failed to initialize Chart Manager: {e}")
            self._chart_manager = None
    
    def _sync_zones_to_chart_manager(
        self,
        symbol: str,
        market_data: pd.DataFrame,
        atr: float
    ):
        """Sync detected zones from OB/ORB detectors to Chart Manager."""
        if self._chart_manager is None:
            return
        
        timeframe = self.config.get('timeframe', 'M30')
        
        # Sync Order Blocks
        if self._order_block_detector is not None:
            try:
                active_obs = self._order_block_detector.get_active_order_blocks()
                self._chart_manager.sync_from_order_blocks(active_obs, symbol, timeframe)
            except Exception as e:
                self.logger.debug(f"Failed to sync order blocks: {e}")
        
        # Sync Session ORB
        if self._session_orb_detector is not None:
            try:
                active_ranges = self._session_orb_detector.get_active_ranges()
                self._chart_manager.sync_from_session_orb(active_ranges, symbol, timeframe)
            except Exception as e:
                self.logger.debug(f"Failed to sync session ORB: {e}")
    
    def _get_chart_manager_analysis(
        self,
        symbol: str,
        direction: str,
        current_price: float,
        atr: float
    ) -> Tuple[float, List[str]]:
        """
        Get zone analysis from Chart Manager for confluence scoring.
        
        Returns:
            Tuple of (score_modifier, reasons)
        """
        if self._chart_manager is None:
            return 0.0, []
        
        timeframe = self.config.get('timeframe', 'M30')
        reasons = []
        score_mod = 0.0
        
        try:
            analysis = self._chart_manager.get_zones_for_entry(
                symbol=symbol,
                direction=direction,
                current_price=current_price,
                atr=atr,
                timeframe=timeframe
            )
            
            # Process supporting zones
            if analysis['supporting_zones']:
                count = len(analysis['supporting_zones'])
                avg_strength = sum(z.effective_strength for z in analysis['supporting_zones']) / count
                score_mod += avg_strength * 0.15  # Up to 15% boost
                reasons.append(f"ChartMgr: {count} supporting zones (strength={avg_strength:.2f})")
            
            # Process opposing zones - penalty
            if analysis['opposing_zones']:
                count = len(analysis['opposing_zones'])
                avg_strength = sum(z.effective_strength for z in analysis['opposing_zones']) / count
                score_mod -= avg_strength * 0.10  # Up to 10% penalty
                reasons.append(f"ChartMgr WARNING: {count} opposing zones")
            
            # Zone score integration
            zone_score = analysis['zone_score']
            if zone_score > 0.7:
                score_mod += 0.05
                reasons.append(f"ChartMgr: Strong zone confluence ({zone_score:.2f})")
            elif zone_score < 0.3:
                score_mod -= 0.05
                reasons.append(f"ChartMgr: Weak zone confluence ({zone_score:.2f})")
            
            # Add any warnings from chart manager
            reasons.extend(analysis.get('warnings', []))
            
        except Exception as e:
            self.logger.debug(f"Chart Manager analysis failed: {e}")
        
        return score_mod, reasons
    
    def _init_structure_detectors(self):
        """Initialize Order Block and Session ORB detectors."""
        if not HAS_STRUCTURE_DETECTORS:
            self.logger.warning("Structure detectors not available - OB/ORB confluence disabled")
            return
        
        try:
            # Order Block Detector - ICT methodology
            ob_config = self.config.get('order_blocks', {})
            self._order_block_detector = OrderBlockDetector(
                swing_lookback=ob_config.get('swing_lookback', 5),
                min_move_atr=ob_config.get('min_move_atr', 1.5),
                max_age_bars=ob_config.get('max_age_bars', 100),
                use_body_only=ob_config.get('use_body_only', True)
            )
            self.logger.debug("Order Block detector initialized")
        except Exception as e:
            self.logger.warning(f"Failed to initialize Order Block detector: {e}")
            self._order_block_detector = None
        
        try:
            # Session ORB Detector - London/NY sessions
            orb_config = self.config.get('session_orb', {})
            sessions = []
            for s in orb_config.get('sessions', ['london', 'new_york']):
                if s.lower() == 'london':
                    sessions.append(SessionType.LONDON)
                elif s.lower() in ['new_york', 'ny']:
                    sessions.append(SessionType.NEW_YORK)
                elif s.lower() in ['asian', 'asia', 'tokyo']:
                    sessions.append(SessionType.ASIAN)
            
            if not sessions:
                sessions = [SessionType.LONDON, SessionType.NEW_YORK]
            
            self._session_orb_detector = SessionORBDetector(
                sessions=sessions,
                range_duration_minutes=orb_config.get('range_duration_minutes', 30),
                confirm_bars=orb_config.get('confirm_bars', 1)
            )
            self.logger.debug("Session ORB detector initialized")
        except Exception as e:
            self.logger.warning(f"Failed to initialize Session ORB detector: {e}")
            self._session_orb_detector = None
    
    def analyze_entry(
        self,
        signal_direction: str,  # 'long' or 'short'
        current_price: float,
        symbol: str,
        market_data: pd.DataFrame,
        atr: Optional[float] = None,
        signal_entry_price: Optional[float] = None
    ) -> EntryConfluenceResult:
        """
        Analyze whether current conditions support a quality entry.
        
        Args:
            signal_direction: 'long' or 'short'
            current_price: Current market price
            symbol: Trading symbol
            market_data: OHLCV DataFrame
            atr: Current ATR (will compute if not provided)
            signal_entry_price: Price where signal was generated (for drift check)
            
        Returns:
            EntryConfluenceResult with entry quality assessment
        """
        reasons = []
        warnings = []
        
        # Compute ATR if not provided
        if atr is None:
            atr = self._compute_atr(market_data)
        
        # Detect price levels
        levels = self._detect_price_levels(symbol, market_data, atr)
        
        # 1. LEVEL SCORE - Are we at a meaningful level?
        level_score, level_reasons, nearby_levels = self._score_price_levels(
            signal_direction, current_price, levels, atr
        )
        reasons.extend(level_reasons)
        
        # 2. MOMENTUM SCORE - Is momentum aligned with entry?
        momentum_score, momentum_aligned, momentum_reasons = self._score_momentum(
            signal_direction, market_data
        )
        reasons.extend(momentum_reasons)
        
        # 3. TIMING SCORE - Entry timing quality
        timing_score, timing_reasons, wait_for_better, optimal_entry = self._score_timing(
            signal_direction, current_price, market_data, atr, levels
        )
        reasons.extend(timing_reasons)
        
        # 4. STRUCTURE SCORE - Market structure alignment (basic)
        structure_score, structure_reasons = self._score_structure(
            signal_direction, market_data
        )
        reasons.extend(structure_reasons)
        
        # 5. BOS/ChoCH STRUCTURE CHECK (NEW) - Fractal-based structure confirmation
        bos_confirmed, bos_score, bos_reasons = self._check_bos_choch_structure(
            signal_direction, symbol, market_data
        )
        reasons.extend(bos_reasons)
        
        # 6. TREND ALIGNMENT CHECK - Macro trend must support direction
        trend_aligned, trend_score, trend_reasons = self._check_trend_alignment(
            signal_direction, market_data
        )
        reasons.extend(trend_reasons)
        
        # 7. ORDER BLOCK SCORE - ICT institutional zones
        ob_score, ob_aligned, ob_reasons, ob_signal = self._score_order_blocks(
            signal_direction, current_price, market_data, atr
        )
        reasons.extend(ob_reasons)
        
        # 8. SESSION ORB SCORE - Opening Range Breakout alignment
        orb_score, orb_aligned, orb_reasons, orb_signal = self._score_session_orb(
            signal_direction, current_price, market_data, atr
        )
        reasons.extend(orb_reasons)
        
        # 9. CHART MANAGER ANALYSIS - Zone tracking and visual reasoning
        cm_score_mod, cm_reasons = self._get_chart_manager_analysis(
            symbol, signal_direction, current_price, atr
        )
        reasons.extend(cm_reasons)
        
        # Sync zones to chart manager (async write - non-blocking)
        self._sync_zones_to_chart_manager(symbol, market_data, atr)
        
        # 10. Check for signal drift (price moved away from signal)
        drift_penalty = 0.0
        if signal_entry_price is not None:
            drift = abs(current_price - signal_entry_price) / atr if atr > 0 else 0
            if drift > 1.5:  # Price moved more than 1.5 ATR from signal
                drift_penalty = min(drift * 10, 30)  # Max 30 point penalty
                warnings.append(f"Price drifted {drift:.1f} ATR from signal")
        
        # Calculate weighted total score
        # Weights sum to 1.0: level=0.18, momentum=0.15, timing=0.10, structure=0.08,
        #                     trend=0.17, bos=0.12, order_block=0.12, session_orb=0.08
        total_score = (
            level_score * self.level_weight +
            momentum_score * self.momentum_weight +
            timing_score * self.timing_weight +
            structure_score * self.structure_weight +
            trend_score * self.trend_weight +
            bos_score * self.bos_weight +
            ob_score * self.order_block_weight +
            orb_score * self.session_orb_weight
        ) * 100 - drift_penalty + (cm_score_mod * 100)  # Apply chart manager modifier
        
        # CRITICAL: Counter-trend penalty (applied BEFORE bonuses)
        # Trading against the trend is inherently risky
        if not trend_aligned:
            counter_trend_penalty = 25  # Base penalty
            # Extra penalty if ADX shows strong trend
            adx = market_data['adx'].iloc[-1] if 'adx' in market_data.columns else None
            if adx is not None and not (np.isnan(adx) if isinstance(adx, float) else False):
                if adx > 30:
                    counter_trend_penalty += 10  # Strong trend = bigger penalty
                if adx > 40:
                    counter_trend_penalty += 10  # Very strong trend
            total_score -= counter_trend_penalty
            reasons.append(f"COUNTER-TREND PENALTY: -{counter_trend_penalty} points")
        else:
            # Bonus for trading WITH the trend
            total_score += 8
            reasons.append("TREND ALIGNMENT BONUS: +8 points")
        
        # BONUS/PENALTY SYSTEM
        # Order Block alignment bonus (strong institutional confluence)
        if ob_aligned and ob_score > 0.7:
            total_score += 8
            reasons.append("OB BONUS: Strong institutional level confluence")
        
        # Session ORB breakout bonus (momentum confirmation)
        if orb_aligned and orb_score > 0.7:
            total_score += 5
            reasons.append("ORB BONUS: Session breakout confluence")
        
        # Combined OB + ORB super confluence
        if ob_aligned and orb_aligned and ob_score > 0.6 and orb_score > 0.6:
            total_score += 7
            reasons.append("SUPER CONFLUENCE: OB + ORB aligned")
        
        # BOS confirmation boost
        if bos_confirmed and bos_score > 0.6:
            total_score += 5
        elif not bos_confirmed:
            total_score -= 10
        
        total_score = max(0, min(100, total_score))
        
        # Determine entry quality
        if total_score >= 85:
            quality = EntryQuality.PREMIUM
        elif total_score >= 70:
            quality = EntryQuality.GOOD
        elif total_score >= self.min_score_to_enter:
            quality = EntryQuality.MARGINAL
        elif total_score >= 20:
            quality = EntryQuality.POOR
        else:
            quality = EntryQuality.REJECT
        
        # Determine position size multiplier
        if quality == EntryQuality.PREMIUM:
            position_mult = 1.0
        elif quality == EntryQuality.GOOD:
            position_mult = 0.85
        elif quality == EntryQuality.MARGINAL:
            position_mult = 0.6
        elif quality == EntryQuality.POOR:
            position_mult = 0.3
        else:
            position_mult = 0.0
        
        # Should we enter? Allow entry if score meets minimum threshold
        should_enter = total_score >= self.min_score_to_enter
        
        # Override: If momentum strongly against, don't enter
        if not momentum_aligned and momentum_score < 0.3:
            should_enter = False
            warnings.append("Momentum strongly against entry direction")
        
        # CRITICAL: If trend not aligned and require_trend_alignment is True, reduce quality
        require_trend = self.config.get('require_trend_alignment', True)
        if require_trend and not trend_aligned:
            if quality in [EntryQuality.PREMIUM, EntryQuality.GOOD]:
                quality = EntryQuality.MARGINAL
                position_mult = 0.5
                warnings.append("Entry against macro trend - reduced size")
            elif quality == EntryQuality.MARGINAL:
                quality = EntryQuality.POOR
                position_mult = 0.25
                warnings.append("Entry against macro trend - significantly reduced")
        
        result = EntryConfluenceResult(
            quality=quality,
            score=total_score,
            should_enter=should_enter,
            position_mult=position_mult,
            wait_for_better=wait_for_better and self.enable_wait_mode,
            optimal_entry=optimal_entry,
            reasons=reasons,
            warnings=warnings,
            levels_near=nearby_levels,
            momentum_aligned=momentum_aligned,
            timing_score=timing_score,
            level_score=level_score
        )
        
        self.logger.info(f"Entry analysis: {result.summary}")
        if reasons:
            self.logger.debug(f"  Reasons: {reasons}")
        if warnings:
            self.logger.warning(f"  Warnings: {warnings}")
        
        return result
    
    def _check_trend_alignment(
        self,
        direction: str,
        data: pd.DataFrame
    ) -> Tuple[bool, float, List[str]]:
        """
        Check if signal direction aligns with macro trend.
        
        Uses multiple EMAs, ADX, and price action to determine trend.
        LONG signals should be in uptrend or neutral.
        SHORT signals should be in downtrend or neutral.
        
        CRITICAL: Counter-trend trades receive significant penalties.
        """
        if len(data) < 50:
            return True, 0.5, []  # Neutral if insufficient data
        
        reasons = []
        score = 0.5  # Neutral
        aligned = True
        trend = 'neutral'
        
        close = data['close'].iloc[-1]
        
        # Check EMA alignment - handle NaN values properly
        ema_20 = data['ema_20'].iloc[-1] if 'ema_20' in data.columns else None
        ema_50 = data['ema_50'].iloc[-1] if 'ema_50' in data.columns else None
        sma_50 = data['sma_50'].iloc[-1] if 'sma_50' in data.columns else None
        
        # Filter out NaN values
        if ema_20 is not None and (np.isnan(ema_20) if isinstance(ema_20, float) else False):
            ema_20 = None
        if ema_50 is not None and (np.isnan(ema_50) if isinstance(ema_50, float) else False):
            ema_50 = None
        if sma_50 is not None and (np.isnan(sma_50) if isinstance(sma_50, float) else False):
            sma_50 = None
        
        # Use whatever we have
        fast_ma = ema_20
        slow_ma = ema_50 or sma_50
        
        # If EMAs not available, calculate trend from price action
        if fast_ma is None or slow_ma is None:
            # Use simple price-based trend detection
            lookback = min(50, len(data))
            recent_highs = data['high'].iloc[-lookback:].rolling(10).max()
            recent_lows = data['low'].iloc[-lookback:].rolling(10).min()
            
            if len(recent_highs.dropna()) > 2 and len(recent_lows.dropna()) > 2:
                # Higher highs and higher lows = uptrend
                # Lower highs and lower lows = downtrend
                start_high = recent_highs.dropna().iloc[0]
                end_high = recent_highs.dropna().iloc[-1]
                start_low = recent_lows.dropna().iloc[0]
                end_low = recent_lows.dropna().iloc[-1]
                
                if end_high > start_high and end_low > start_low:
                    trend = 'up'
                    if direction == 'long':
                        score += 0.25
                        reasons.append("Trend UP: Higher highs/lows")
                        aligned = True
                    else:
                        score -= 0.35  # Strong penalty for shorting uptrend
                        reasons.append("COUNTER-TREND: Shorting in uptrend")
                        aligned = False
                elif end_high < start_high and end_low < start_low:
                    trend = 'down'
                    if direction == 'short':
                        score += 0.25
                        reasons.append("Trend DOWN: Lower highs/lows")
                        aligned = True
                    else:
                        score -= 0.35  # Strong penalty for buying downtrend
                        reasons.append("COUNTER-TREND: Buying in downtrend")
                        aligned = False
                else:
                    reasons.append("Trend: Neutral/ranging (mixed structure)")
        else:
            # EMA-based trend detection
            if fast_ma > slow_ma:
                trend = 'up'
                if direction == 'long':
                    score += 0.35  # Increased boost for aligned trades
                    reasons.append("Trend UP: EMAs bullish aligned")
                    aligned = True
                else:  # short in uptrend
                    score -= 0.4  # Strong penalty for counter-trend
                    reasons.append("COUNTER-TREND: Shorting in uptrend (EMAs bullish)")
                    aligned = False
            elif fast_ma < slow_ma:
                trend = 'down'
                if direction == 'short':
                    score += 0.35  # Increased boost for aligned trades
                    reasons.append("Trend DOWN: EMAs bearish aligned")
                    aligned = True
                else:  # long in downtrend
                    score -= 0.4  # Strong penalty for counter-trend
                    reasons.append("COUNTER-TREND: Buying in downtrend (EMAs bearish)")
                    aligned = False
            else:
                trend = 'neutral'
                reasons.append("Trend NEUTRAL: EMAs flat")
        
        # Price vs MA check - additional penalty for price position
        if slow_ma is not None:
            if direction == 'long' and close < slow_ma:
                score -= 0.15
                reasons.append(f"Price below EMA50 ({close:.2f} < {slow_ma:.2f})")
                if aligned:  # Don't double-penalize
                    aligned = close > slow_ma * 0.98  # Allow 2% below
            elif direction == 'short' and close > slow_ma:
                score -= 0.15
                reasons.append(f"Price above EMA50 ({close:.2f} > {slow_ma:.2f})")
                if aligned:
                    aligned = close < slow_ma * 1.02  # Allow 2% above
        
        # ADX trend strength check - stronger penalties when trend is strong
        adx = data['adx'].iloc[-1] if 'adx' in data.columns else None
        if adx is not None and not (np.isnan(adx) if isinstance(adx, float) else False):
            if adx < 20:
                # Weak trend - all directions acceptable, override alignment
                score += 0.1
                reasons.append(f"ADX weak ({adx:.1f}) - ranging market")
                aligned = True  # Override - ranging markets accept both directions
            elif adx > 30:
                # Strong trend - boost aligned trades, penalize counter-trend
                if aligned:
                    score += 0.1  # Bonus for trading with strong trend
                    reasons.append(f"ADX strong ({adx:.1f}) - trend confirmed")
                else:
                    score -= 0.25  # Heavy penalty for fading strong trend
                    reasons.append(f"ADX strong ({adx:.1f}) - RISKY to fade this trend")
        
        return aligned, max(0, min(1, score)), reasons
    
    def _check_bos_choch_structure(
        self,
        direction: str,
        symbol: str,
        data: pd.DataFrame
    ) -> Tuple[bool, float, List[str]]:
        """
        Check market structure using BOS/ChoCH detection.
        
        Uses fractal-based structure detector for:
        - Break of Structure (BOS): Confirmation of direction
        - Change of Character (ChoCH): Early warning of reversal
        
        Args:
            direction: 'long' or 'short'
            symbol: Trading symbol
            data: Market data DataFrame
            
        Returns:
            Tuple of (confirmed, score, reasons)
        """
        if len(data) < 20:
            return True, 0.5, []  # Neutral if insufficient data
        
        reasons = []
        score = 0.5  # Neutral
        confirmed = True
        
        try:
            from cthulu.cognition.structure_detector import get_structure_detector
            
            detector = get_structure_detector()
            is_confirmed, reason, conf_mult = detector.get_entry_confirmation(
                signal_direction=direction,
                symbol=symbol,
                df=data
            )
            
            if is_confirmed:
                if conf_mult > 1.0:
                    # Strong confirmation (BOS/ChoCH in our direction)
                    score = 0.5 + min(0.3, (conf_mult - 1.0))
                    reasons.append(f"Structure confirmed: {reason}")
                else:
                    # Neutral or weak confirmation
                    score = 0.5
                    if reason:
                        reasons.append(f"Structure: {reason}")
                confirmed = True
            else:
                # Trading against structure
                score = 0.5 - min(0.3, (1.0 - conf_mult))
                reasons.append(f"Structure WARNING: {reason}")
                confirmed = False
            
        except ImportError:
            # Structure detector not available, use neutral score
            self.logger.debug("BOS/ChoCH structure detector not available")
        except Exception as e:
            self.logger.debug(f"BOS/ChoCH check failed: {e}")
        
        return confirmed, max(0, min(1, score)), reasons
    
    def _score_order_blocks(
        self,
        direction: str,
        current_price: float,
        data: pd.DataFrame,
        atr: float
    ) -> Tuple[float, bool, List[str], Optional[Dict[str, Any]]]:
        """
        Score entry based on Order Block (ICT) proximity and alignment.
        
        Order Blocks represent institutional supply/demand zones.
        - Bullish OB: Last bearish candle before bullish BOS (demand zone)
        - Bearish OB: Last bullish candle before bearish BOS (supply zone)
        
        For LONG: We want price at or near a bullish order block (demand)
        For SHORT: We want price at or near a bearish order block (supply)
        
        Args:
            direction: 'long' or 'short'
            current_price: Current market price
            data: OHLCV DataFrame
            atr: Current ATR
            
        Returns:
            Tuple of (score, aligned, reasons, signal_if_any)
        """
        if self._order_block_detector is None:
            return 0.5, True, [], None  # Neutral if detector not available
        
        reasons = []
        score = 0.5  # Neutral starting point
        aligned = True
        signal = None
        
        try:
            # Update detector with current market data
            timestamp = data.index[-1] if hasattr(data.index[-1], 'timestamp') else datetime.utcnow()
            signal = self._order_block_detector.update(
                df=data,
                current_price=current_price,
                atr=atr,
                timestamp=timestamp
            )
            
            # Get active order blocks
            active_obs = self._order_block_detector.get_active_order_blocks()
            
            if not active_obs:
                reasons.append("No active order blocks detected")
                return score, aligned, reasons, signal
            
            # Find order blocks near current price
            tolerance = atr * 1.5
            
            bullish_obs_near = []
            bearish_obs_near = []
            
            for ob in active_obs:
                # Check if price is within OB zone (between high and low) or very close
                in_zone = ob.low <= current_price <= ob.high
                near_zone = abs(current_price - ob.mid_price) < tolerance
                
                if in_zone or near_zone:
                    if ob.block_type == OrderBlockType.BULLISH:
                        bullish_obs_near.append(ob)
                    else:
                        bearish_obs_near.append(ob)
            
            # Score based on direction and OB proximity
            if direction == 'long':
                if bullish_obs_near:
                    # Excellent: Long signal at bullish OB (demand zone)
                    best_ob = max(bullish_obs_near, key=lambda x: x.strength)
                    score = 0.6 + min(0.35, best_ob.strength * 0.4)
                    aligned = True
                    
                    # Extra boost for fresh (untouched) order blocks
                    if best_ob.touches == 0:
                        score += 0.1
                        reasons.append(f"FRESH bullish OB @ {best_ob.low:.2f}-{best_ob.high:.2f}")
                    else:
                        reasons.append(f"Bullish OB @ {best_ob.low:.2f}-{best_ob.high:.2f} (touched {best_ob.touches}x)")
                    
                    # BOS/ChoCH context boost
                    if best_ob.structure_break == StructureBreak.BOS:
                        score += 0.05
                        reasons.append("OB confirmed by BOS")
                    elif best_ob.structure_break == StructureBreak.CHOCH:
                        score += 0.08
                        reasons.append("OB confirmed by ChoCH (trend reversal)")
                
                elif bearish_obs_near:
                    # Warning: Long signal at bearish OB (supply zone - resistance)
                    score = 0.35
                    aligned = False
                    reasons.append(f"WARNING: Long near bearish OB (supply) @ {bearish_obs_near[0].low:.2f}")
                else:
                    reasons.append("No nearby order blocks for long")
            
            elif direction == 'short':
                if bearish_obs_near:
                    # Excellent: Short signal at bearish OB (supply zone)
                    best_ob = max(bearish_obs_near, key=lambda x: x.strength)
                    score = 0.6 + min(0.35, best_ob.strength * 0.4)
                    aligned = True
                    
                    if best_ob.touches == 0:
                        score += 0.1
                        reasons.append(f"FRESH bearish OB @ {best_ob.low:.2f}-{best_ob.high:.2f}")
                    else:
                        reasons.append(f"Bearish OB @ {best_ob.low:.2f}-{best_ob.high:.2f} (touched {best_ob.touches}x)")
                    
                    if best_ob.structure_break == StructureBreak.BOS:
                        score += 0.05
                        reasons.append("OB confirmed by BOS")
                    elif best_ob.structure_break == StructureBreak.CHOCH:
                        score += 0.08
                        reasons.append("OB confirmed by ChoCH (trend reversal)")
                
                elif bullish_obs_near:
                    # Warning: Short signal at bullish OB (demand zone - support)
                    score = 0.35
                    aligned = False
                    reasons.append(f"WARNING: Short near bullish OB (demand) @ {bullish_obs_near[0].high:.2f}")
                else:
                    reasons.append("No nearby order blocks for short")
            
            # If we got a signal from detector that matches our direction, boost
            if signal and signal.get('direction') == direction:
                score += 0.1
                reasons.append(f"OB detector signal: {signal.get('reason', 'OB signal')}")
            
        except Exception as e:
            self.logger.debug(f"Order block scoring failed: {e}")
        
        return max(0, min(1, score)), aligned, reasons, signal
    
    def _score_session_orb(
        self,
        direction: str,
        current_price: float,
        data: pd.DataFrame,
        atr: float
    ) -> Tuple[float, bool, List[str], Optional[Dict[str, Any]]]:
        """
        Score entry based on Session Opening Range Breakout alignment.
        
        Sessions tracked: London (08:00 UTC), New York (13:30 UTC)
        
        Logic:
        - If session range is forming, neutral (wait for breakout)
        - If breakout occurred in our direction, boost score
        - If breakout occurred against our direction, reduce score
        - If price is testing range boundaries, context-dependent scoring
        
        Args:
            direction: 'long' or 'short'
            current_price: Current market price
            data: OHLCV DataFrame
            atr: Current ATR
            
        Returns:
            Tuple of (score, aligned, reasons, signal_if_any)
        """
        if self._session_orb_detector is None:
            return 0.5, True, [], None  # Neutral if detector not available
        
        reasons = []
        score = 0.5  # Neutral starting point
        aligned = True
        signal = None
        
        try:
            # Update detector
            timestamp = data.index[-1] if hasattr(data.index[-1], 'timestamp') else datetime.utcnow()
            signal = self._session_orb_detector.update(
                df=data,
                current_price=current_price,
                atr=atr,
                timestamp=timestamp
            )
            
            # Get active session ranges
            active_ranges = self._session_orb_detector.get_active_ranges()
            
            if not active_ranges:
                # No active session ranges - could be outside trading hours
                return score, aligned, reasons, signal
            
            for session_name, range_obj in active_ranges.items():
                if not range_obj.is_complete:
                    # Range still forming
                    reasons.append(f"{session_name} ORB forming ({range_obj.low:.2f}-{range_obj.high:.2f})")
                    continue
                
                range_size = range_obj.high - range_obj.low
                
                # Check for breakout
                if range_obj.breakout_direction:
                    if range_obj.breakout_direction == 'bullish':
                        if direction == 'long':
                            # Perfect: Long signal with bullish ORB breakout
                            score = 0.75
                            aligned = True
                            reasons.append(f"{session_name} BULLISH ORB breakout confirmed")
                            
                            # Extra boost if price is pulling back to range high
                            if abs(current_price - range_obj.high) < atr * 0.5:
                                score += 0.1
                                reasons.append("Pullback to ORB high (optimal entry)")
                        else:
                            # Short against bullish breakout
                            score = 0.3
                            aligned = False
                            reasons.append(f"WARNING: Short against {session_name} bullish breakout")
                    
                    elif range_obj.breakout_direction == 'bearish':
                        if direction == 'short':
                            # Perfect: Short signal with bearish ORB breakout
                            score = 0.75
                            aligned = True
                            reasons.append(f"{session_name} BEARISH ORB breakout confirmed")
                            
                            # Extra boost if price is pulling back to range low
                            if abs(current_price - range_obj.low) < atr * 0.5:
                                score += 0.1
                                reasons.append("Pullback to ORB low (optimal entry)")
                        else:
                            # Long against bearish breakout
                            score = 0.3
                            aligned = False
                            reasons.append(f"WARNING: Long against {session_name} bearish breakout")
                
                else:
                    # No breakout yet - price within range
                    if range_obj.low <= current_price <= range_obj.high:
                        # Trading within range - neutral but note the levels
                        if direction == 'long':
                            # Better if near range low
                            if current_price < range_obj.low + range_size * 0.3:
                                score = 0.6
                                reasons.append(f"Long near {session_name} ORB low (support)")
                            else:
                                score = 0.45
                                reasons.append(f"Long within {session_name} range (wait for breakout)")
                        else:
                            # Better if near range high
                            if current_price > range_obj.high - range_size * 0.3:
                                score = 0.6
                                reasons.append(f"Short near {session_name} ORB high (resistance)")
                            else:
                                score = 0.45
                                reasons.append(f"Short within {session_name} range (wait for breakout)")
            
            # If we got a signal from detector that matches our direction, boost
            if signal and signal.get('direction') == direction:
                score = max(score, 0.8)
                reasons.append(f"ORB signal confirmed: {signal.get('reason', 'ORB breakout')}")
            
        except Exception as e:
            self.logger.debug(f"Session ORB scoring failed: {e}")
        
        return max(0, min(1, score)), aligned, reasons, signal
    
    def register_pending_entry(
        self,
        signal_id: str,
        signal_direction: str,
        optimal_entry: float,
        symbol: str,
        max_wait_bars: int = None
    ):
        """
        Register a pending entry to wait for better price.
        
        Args:
            signal_id: Unique signal identifier
            signal_direction: 'long' or 'short'
            optimal_entry: Price to wait for
            symbol: Trading symbol
            max_wait_bars: Maximum bars to wait (default from config)
        """
        self._pending_entries[signal_id] = {
            'direction': signal_direction,
            'optimal_entry': optimal_entry,
            'symbol': symbol,
            'registered_at': datetime.now(),
            'bars_waited': 0,
            'max_wait': max_wait_bars or self.max_wait_bars,
            'active': True
        }
        self.logger.info(f"Registered pending entry {signal_id}: wait for {optimal_entry}")
    
    def check_pending_entries(
        self,
        symbol: str,
        current_price: float,
        current_bar: pd.Series
    ) -> List[Dict[str, Any]]:
        """
        Check if any pending entries should now execute.
        
        Args:
            symbol: Trading symbol
            current_price: Current price
            current_bar: Current bar data
            
        Returns:
            List of entries that are now ready to execute
        """
        ready_entries = []
        
        for signal_id, entry in list(self._pending_entries.items()):
            if not entry['active'] or entry['symbol'] != symbol:
                continue
            
            entry['bars_waited'] += 1
            
            # Check if price reached our target
            if entry['direction'] == 'long':
                if current_price <= entry['optimal_entry']:
                    ready_entries.append({
                        'signal_id': signal_id,
                        'direction': entry['direction'],
                        'entry_price': current_price,
                        'waited_bars': entry['bars_waited'],
                        'reason': f"Price reached optimal entry {entry['optimal_entry']}"
                    })
                    entry['active'] = False
                    
            elif entry['direction'] == 'short':
                if current_price >= entry['optimal_entry']:
                    ready_entries.append({
                        'signal_id': signal_id,
                        'direction': entry['direction'],
                        'entry_price': current_price,
                        'waited_bars': entry['bars_waited'],
                        'reason': f"Price reached optimal entry {entry['optimal_entry']}"
                    })
                    entry['active'] = False
            
            # Check timeout
            if entry['bars_waited'] >= entry['max_wait']:
                # Expired - execute at current price with reduced size
                ready_entries.append({
                    'signal_id': signal_id,
                    'direction': entry['direction'],
                    'entry_price': current_price,
                    'waited_bars': entry['bars_waited'],
                    'reason': f"Wait timeout ({entry['max_wait']} bars)",
                    'timeout': True,
                    'size_mult': 0.5  # Half size on timeout
                })
                entry['active'] = False
        
        # Clean up inactive entries
        self._pending_entries = {
            k: v for k, v in self._pending_entries.items() 
            if v['active'] or (datetime.now() - v['registered_at']).seconds < 3600
        }
        
        return ready_entries
    
    def _detect_price_levels(
        self,
        symbol: str,
        data: pd.DataFrame,
        atr: float
    ) -> List[PriceLevel]:
        """
        Detect significant price levels from market data.
        
        Identifies:
        - Support/Resistance from swing highs/lows
        - Round numbers
        - Previous session high/low
        - EMA levels
        """
        levels = []
        
        if len(data) < 20:
            return levels
        
        tolerance = atr * self.level_tolerance_atr
        close = data['close'].iloc[-1]
        
        # 1. SWING HIGHS/LOWS (Support/Resistance)
        highs = data['high'].values
        lows = data['low'].values
        
        # Find swing highs (local maxima)
        for i in range(2, min(len(highs) - 2, self.sr_lookback)):
            if highs[-i] > highs[-i-1] and highs[-i] > highs[-i+1]:
                # Count touches
                touches = sum(1 for j in range(len(highs)) if abs(highs[j] - highs[-i]) < tolerance)
                if touches >= self.sr_min_touches:
                    strength = min(touches / 5.0, 1.0)
                    levels.append(PriceLevel(
                        price=float(highs[-i]),
                        level_type=PriceLevelType.RESISTANCE,
                        strength=strength,
                        touches=touches,
                        notes=f"Swing high with {touches} touches"
                    ))
        
        # Find swing lows (local minima)
        for i in range(2, min(len(lows) - 2, self.sr_lookback)):
            if lows[-i] < lows[-i-1] and lows[-i] < lows[-i+1]:
                touches = sum(1 for j in range(len(lows)) if abs(lows[j] - lows[-i]) < tolerance)
                if touches >= self.sr_min_touches:
                    strength = min(touches / 5.0, 1.0)
                    levels.append(PriceLevel(
                        price=float(lows[-i]),
                        level_type=PriceLevelType.SUPPORT,
                        strength=strength,
                        touches=touches,
                        notes=f"Swing low with {touches} touches"
                    ))
        
        # 2. ROUND NUMBERS
        # Determine round number step based on price magnitude
        if close > 10000:
            round_step = 1000
        elif close > 1000:
            round_step = 100
        elif close > 100:
            round_step = 10
        else:
            round_step = 1
        
        # Find nearest round numbers
        lower_round = (close // round_step) * round_step
        upper_round = lower_round + round_step
        
        for rn in [lower_round, upper_round]:
            if abs(rn - close) < atr * 3:  # Within 3 ATR
                levels.append(PriceLevel(
                    price=float(rn),
                    level_type=PriceLevelType.ROUND_NUMBER,
                    strength=0.6,
                    touches=0,
                    notes=f"Round number {rn}"
                ))
        
        # 3. PREVIOUS SESSION HIGH/LOW
        if len(data) >= 24:  # Assuming hourly data
            prev_session = data.iloc[-48:-24] if len(data) >= 48 else data.iloc[:24]
            if len(prev_session) > 0:
                prev_high = prev_session['high'].max()
                prev_low = prev_session['low'].min()
                
                levels.append(PriceLevel(
                    price=float(prev_high),
                    level_type=PriceLevelType.PREVIOUS_HIGH,
                    strength=0.8,
                    touches=1,
                    notes="Previous session high"
                ))
                levels.append(PriceLevel(
                    price=float(prev_low),
                    level_type=PriceLevelType.PREVIOUS_LOW,
                    strength=0.8,
                    touches=1,
                    notes="Previous session low"
                ))
        
        # 4. EMA LEVELS
        for period in [20, 50, 200]:
            col = f'ema_{period}'
            if col in data.columns:
                ema_val = data[col].iloc[-1]
                levels.append(PriceLevel(
                    price=float(ema_val),
                    level_type=PriceLevelType.EMA,
                    strength=0.5 + (period / 400),  # Longer EMAs = stronger
                    touches=0,
                    notes=f"EMA {period}"
                ))
        
        # 5. ORDER BLOCK LEVELS (ICT Institutional Zones)
        if self._order_block_detector is not None:
            try:
                # Get active order blocks from detector
                active_obs = self._order_block_detector.get_active_order_blocks()
                for ob in active_obs[:10]:  # Limit to top 10
                    # Use mid-price of order block as the level
                    levels.append(PriceLevel(
                        price=float(ob.mid_price),
                        level_type=PriceLevelType.ORDER_BLOCK,
                        strength=min(0.9, 0.6 + ob.strength * 0.3),  # OBs are strong levels
                        touches=ob.touches,
                        notes=f"{ob.block_type.value} OB ({ob.structure_break.value})"
                    ))
            except Exception as e:
                self.logger.debug(f"Failed to get order block levels: {e}")
        
        # Cache levels
        self._price_levels[symbol] = levels
        
        return levels
    
    def _score_price_levels(
        self,
        direction: str,
        price: float,
        levels: List[PriceLevel],
        atr: float
    ) -> Tuple[float, List[str], List[PriceLevel]]:
        """
        Score entry based on proximity to key levels.
        
        For LONG: We want to enter near support (bouncing up)
        For SHORT: We want to enter near resistance (bouncing down)
        """
        score = 0.5  # Neutral starting point
        reasons = []
        nearby_levels = []
        
        tolerance = atr * 1.5
        
        for level in levels:
            distance = abs(price - level.price)
            
            if distance < tolerance:
                nearby_levels.append(level)
                
                # Calculate proximity score (closer = better)
                proximity = 1.0 - (distance / tolerance)
                level_contribution = proximity * level.strength
                
                if direction == 'long':
                    if level.level_type in [PriceLevelType.SUPPORT, 
                                            PriceLevelType.PREVIOUS_LOW,
                                            PriceLevelType.EMA]:
                        # Good for long: entering at support
                        score += level_contribution * 0.2
                        reasons.append(f"Near {level.level_type.value} @ {level.price:.2f}")
                    elif level.level_type in [PriceLevelType.RESISTANCE,
                                              PriceLevelType.PREVIOUS_HIGH]:
                        # Bad for long: entering at resistance
                        score -= level_contribution * 0.15
                        reasons.append(f"Warning: Near {level.level_type.value} @ {level.price:.2f}")
                    # Order Block handling for longs
                    elif level.level_type == PriceLevelType.ORDER_BLOCK:
                        if 'bullish' in level.notes.lower():
                            # Bullish OB = demand zone = good for long
                            score += level_contribution * 0.25
                            reasons.append(f"Near bullish OB @ {level.price:.2f}")
                        else:
                            # Bearish OB = supply zone = resistance for long
                            score -= level_contribution * 0.1
                            reasons.append(f"Near bearish OB @ {level.price:.2f} (resistance)")
                
                elif direction == 'short':
                    if level.level_type in [PriceLevelType.RESISTANCE,
                                            PriceLevelType.PREVIOUS_HIGH]:
                        # Good for short: entering at resistance
                        score += level_contribution * 0.2
                        reasons.append(f"Near {level.level_type.value} @ {level.price:.2f}")
                    elif level.level_type in [PriceLevelType.SUPPORT,
                                              PriceLevelType.PREVIOUS_LOW]:
                        # Bad for short: entering at support
                        score -= level_contribution * 0.15
                        reasons.append(f"Warning: Near {level.level_type.value} @ {level.price:.2f}")
                    # Order Block handling for shorts
                    elif level.level_type == PriceLevelType.ORDER_BLOCK:
                        if 'bearish' in level.notes.lower():
                            # Bearish OB = supply zone = good for short
                            score += level_contribution * 0.25
                            reasons.append(f"Near bearish OB @ {level.price:.2f}")
                        else:
                            # Bullish OB = demand zone = support for short
                            score -= level_contribution * 0.1
                            reasons.append(f"Near bullish OB @ {level.price:.2f} (support)")
                
                # Round numbers are neutral-to-good for both directions
                if level.level_type == PriceLevelType.ROUND_NUMBER:
                    score += level_contribution * 0.05
        
        return max(0, min(1, score)), reasons, nearby_levels
    
    def _score_momentum(
        self,
        direction: str,
        data: pd.DataFrame
    ) -> Tuple[float, bool, List[str]]:
        """
        Score momentum alignment with entry direction.
        
        We want momentum in our favor, or at least not against us.
        """
        if len(data) < self.momentum_bars + 1:
            return 0.5, True, []
        
        reasons = []
        
        # Calculate short-term momentum
        recent_close = data['close'].iloc[-self.momentum_bars:].values
        momentum = (recent_close[-1] - recent_close[0]) / recent_close[0] if recent_close[0] > 0 else 0
        
        # Calculate momentum direction strength
        up_bars = sum(1 for i in range(1, len(recent_close)) if recent_close[i] > recent_close[i-1])
        down_bars = len(recent_close) - 1 - up_bars
        
        momentum_direction = 1 if up_bars > down_bars else -1 if down_bars > up_bars else 0
        momentum_strength = abs(up_bars - down_bars) / (len(recent_close) - 1)
        
        # Check RSI if available
        rsi = data['rsi'].iloc[-1] if 'rsi' in data.columns else 50
        
        aligned = True
        score = 0.5
        
        if direction == 'long':
            if momentum_direction > 0:
                score = 0.5 + momentum_strength * 0.3
                reasons.append(f"Bullish momentum ({up_bars}/{len(recent_close)-1} bars)")
            elif momentum_direction < 0:
                score = 0.5 - momentum_strength * 0.25
                aligned = momentum_strength < 0.6
                reasons.append(f"Bearish momentum warning ({down_bars}/{len(recent_close)-1} bars)")
            
            # RSI check
            if rsi < 30:
                score += 0.15
                reasons.append("RSI oversold - good for long")
            elif rsi > 70:
                score -= 0.1
                reasons.append("RSI overbought - risky for long")
        
        elif direction == 'short':
            if momentum_direction < 0:
                score = 0.5 + momentum_strength * 0.3
                reasons.append(f"Bearish momentum ({down_bars}/{len(recent_close)-1} bars)")
            elif momentum_direction > 0:
                score = 0.5 - momentum_strength * 0.25
                aligned = momentum_strength < 0.6
                reasons.append(f"Bullish momentum warning ({up_bars}/{len(recent_close)-1} bars)")
            
            if rsi > 70:
                score += 0.15
                reasons.append("RSI overbought - good for short")
            elif rsi < 30:
                score -= 0.1
                reasons.append("RSI oversold - risky for short")
        
        return max(0, min(1, score)), aligned, reasons
    
    def _score_timing(
        self,
        direction: str,
        price: float,
        data: pd.DataFrame,
        atr: float,
        levels: List[PriceLevel]
    ) -> Tuple[float, List[str], bool, Optional[float]]:
        """
        Score entry timing and suggest better entry if available.
        
        Checks:
        - Are we chasing price?
        - Is there a retest coming?
        - Is price extended from key levels?
        """
        reasons = []
        score = 0.5
        wait_for_better = False
        optimal_entry = None
        
        if len(data) < 10:
            return score, reasons, wait_for_better, optimal_entry
        
        # Calculate recent range
        recent_high = data['high'].iloc[-10:].max()
        recent_low = data['low'].iloc[-10:].min()
        recent_range = recent_high - recent_low
        
        # Position within recent range
        if recent_range > 0:
            range_position = (price - recent_low) / recent_range
            
            if direction == 'long':
                if range_position > 0.8:
                    # Near recent high - chasing
                    score -= 0.2
                    reasons.append("Buying near recent high (chasing)")
                    wait_for_better = True
                    optimal_entry = recent_low + recent_range * 0.3  # Buy lower
                elif range_position < 0.3:
                    # Near recent low - good entry
                    score += 0.2
                    reasons.append("Buying near recent low (optimal)")
                else:
                    reasons.append(f"Mid-range entry ({range_position:.0%} of range)")
                    
            elif direction == 'short':
                if range_position < 0.2:
                    # Near recent low - chasing
                    score -= 0.2
                    reasons.append("Selling near recent low (chasing)")
                    wait_for_better = True
                    optimal_entry = recent_high - recent_range * 0.3  # Sell higher
                elif range_position > 0.7:
                    # Near recent high - good entry
                    score += 0.2
                    reasons.append("Selling near recent high (optimal)")
                else:
                    reasons.append(f"Mid-range entry ({range_position:.0%} of range)")
        
        # Check for extension from EMA
        for col in ['ema_20', 'ema_50']:
            if col in data.columns:
                ema = data[col].iloc[-1]
                extension = abs(price - ema) / atr if atr > 0 else 0
                
                if extension > 2:
                    score -= 0.1
                    reasons.append(f"Extended {extension:.1f} ATR from {col}")
                    
                    if direction == 'long':
                        if price > ema:
                            wait_for_better = True
                            optimal_entry = ema + atr * 0.5
                    elif direction == 'short':
                        if price < ema:
                            wait_for_better = True
                            optimal_entry = ema - atr * 0.5
                break
        
        return max(0, min(1, score)), reasons, wait_for_better, optimal_entry
    
    def _score_structure(
        self,
        direction: str,
        data: pd.DataFrame
    ) -> Tuple[float, List[str]]:
        """
        Score market structure alignment.
        
        Checks higher-timeframe trend and structure.
        """
        if len(data) < 50:
            return 0.5, []
        
        reasons = []
        score = 0.5
        
        # Check if making higher highs/lows (uptrend) or lower highs/lows (downtrend)
        recent = data.iloc[-20:]
        older = data.iloc[-50:-20]
        
        recent_high = recent['high'].max()
        recent_low = recent['low'].min()
        older_high = older['high'].max()
        older_low = older['low'].min()
        
        higher_highs = recent_high > older_high
        higher_lows = recent_low > older_low
        lower_highs = recent_high < older_high
        lower_lows = recent_low < older_low
        
        if direction == 'long':
            if higher_highs and higher_lows:
                score += 0.25
                reasons.append("Structure: Higher highs & lows (bullish)")
            elif lower_highs and lower_lows:
                score -= 0.2
                reasons.append("Structure: Lower highs & lows (bearish - against long)")
            elif higher_lows:
                score += 0.1
                reasons.append("Structure: Higher lows (bullish bias)")
                
        elif direction == 'short':
            if lower_highs and lower_lows:
                score += 0.25
                reasons.append("Structure: Lower highs & lows (bearish)")
            elif higher_highs and higher_lows:
                score -= 0.2
                reasons.append("Structure: Higher highs & lows (bullish - against short)")
            elif lower_highs:
                score += 0.1
                reasons.append("Structure: Lower highs (bearish bias)")
        
        return max(0, min(1, score)), reasons
    
    def _compute_atr(self, data: pd.DataFrame, period: int = 14) -> float:
        """Compute ATR from market data."""
        if len(data) < period:
            return 0.0
        
        if 'atr' in data.columns:
            return float(data['atr'].iloc[-1])
        
        # Manual calculation
        high = data['high'].values
        low = data['low'].values
        close = data['close'].values
        
        tr = np.maximum(
            high[1:] - low[1:],
            np.maximum(
                np.abs(high[1:] - close[:-1]),
                np.abs(low[1:] - close[:-1])
            )
        )
        
        atr = np.mean(tr[-period:]) if len(tr) >= period else np.mean(tr)
        return float(atr)


# Module-level singleton
_confluence_filter: Optional[EntryConfluenceFilter] = None


def get_entry_confluence_filter(**kwargs) -> EntryConfluenceFilter:
    """Get or create the entry confluence filter singleton."""
    global _confluence_filter
    if _confluence_filter is None:
        _confluence_filter = EntryConfluenceFilter(**kwargs)
    return _confluence_filter


def analyze_entry(
    signal_direction: str,
    current_price: float,
    symbol: str,
    market_data: pd.DataFrame,
    atr: Optional[float] = None
) -> EntryConfluenceResult:
    """Convenience function to analyze entry quality."""
    return get_entry_confluence_filter().analyze_entry(
        signal_direction, current_price, symbol, market_data, atr
    )
