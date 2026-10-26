"""
Chart Manager - Dynamic Visual Reasoning Layer for Cthulu

This module represents Cthulu's "visual thinking" - the ability to maintain,
track, and reason about price levels, zones, trend lines, channels, and 
market structure in a way that mirrors how professional traders "see" charts.

ARCHITECTURE:
┌─────────────────────────────────────────────────────────────────────────┐
│                         CHART MANAGER (Non-Blocking)                     │
├─────────────────────────────────────────────────────────────────────────┤
│  READ LAYER (Sync)          │  WRITE LAYER (Async)                      │
│  ─────────────────          │  ────────────────────                     │
│  • Order Blocks             │  • Zone Creation                          │
│  • Session ORB              │  • Level Updates                          │
│  • Structure Detector       │  • State Persistence                      │
│  • Support/Resistance       │  • Event Logging                          │
├─────────────────────────────────────────────────────────────────────────┤
│                         ZONE STATE MACHINE                               │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐              │
│  │ PENDING │ -> │ ACTIVE  │ -> │ TESTED  │ -> │ BROKEN  │              │
│  └─────────┘    └─────────┘    └─────────┘    └─────────┘              │
│       │              │              │              │                    │
│       v              v              v              v                    │
│   [Created]      [Touched]     [Rejected]    [Violated]                │
├─────────────────────────────────────────────────────────────────────────┤
│                         TREND LINE ENGINE                                │
│  • Dynamic channels from swing points                                   │
│  • Fibonacci projections from structure                                 │
│  • Regression channels with confidence bands                            │
└─────────────────────────────────────────────────────────────────────────┘

INTEGRATION POINTS:
- entry_confluence.py: Reads zone state for scoring
- order_blocks.py: Feeds OB detection data
- session_orb.py: Feeds ORB levels
- structure_detector.py: Feeds BOS/ChoCH events

Part of Cthulu v6.0.0 APEX - Visual Reasoning System
"""

from __future__ import annotations
import asyncio
import threading
import queue
import os
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple, Callable, Set
from datetime import datetime, timedelta
from enum import Enum, auto
from collections import defaultdict
import logging
import json
import uuid

logger = logging.getLogger("cthulu.chart_manager")


# ============================================================================
# ENUMS & DATA STRUCTURES
# ============================================================================

class ZoneType(Enum):
    """Types of price zones tracked by the chart manager."""
    ORDER_BLOCK_BULLISH = "ob_bullish"    # Demand zone (expect bounce up)
    ORDER_BLOCK_BEARISH = "ob_bearish"    # Supply zone (expect rejection down)
    ORB_HIGH = "orb_high"                  # Opening range high
    ORB_LOW = "orb_low"                    # Opening range low
    SUPPORT = "support"                    # Horizontal support level
    RESISTANCE = "resistance"              # Horizontal resistance level
    FVG_BULLISH = "fvg_bullish"           # Fair Value Gap (bullish imbalance)
    FVG_BEARISH = "fvg_bearish"           # Fair Value Gap (bearish imbalance)
    TREND_SUPPORT = "trend_support"        # Ascending trend line
    TREND_RESISTANCE = "trend_resistance"  # Descending trend line
    CHANNEL_UPPER = "channel_upper"        # Channel boundary
    CHANNEL_LOWER = "channel_lower"        # Channel boundary
    FIBONACCI = "fibonacci"                # Fibonacci retracement level
    VWAP = "vwap"                          # Volume weighted average price
    POC = "poc"                            # Point of Control (volume profile)


class ZoneState(Enum):
    """Lifecycle state of a price zone."""
    PENDING = auto()    # Just created, not yet validated
    ACTIVE = auto()     # Valid and being tracked
    TESTED = auto()     # Price has touched but zone held
    WEAKENED = auto()   # Multiple tests, zone integrity questionable
    BROKEN = auto()     # Price violated the zone decisively
    MITIGATED = auto()  # Zone has been filled (for OB/FVG)
    EXPIRED = auto()    # Zone too old, no longer relevant


class ZoneEvent(Enum):
    """Events that can occur at a zone."""
    CREATED = "created"
    TOUCHED = "touched"        # Price touched zone boundary
    REJECTED = "rejected"      # Price rejected from zone (bounce)
    PIERCED = "pierced"        # Price temporarily violated but recovered
    BROKEN = "broken"          # Price decisively broke through
    RECLAIMED = "reclaimed"    # Price came back through after break
    MITIGATED = "mitigated"    # Zone filled (OB specific)
    EXPIRED = "expired"        # Zone aged out


class TrendDirection(Enum):
    """Trend direction classification."""
    UP = 1
    DOWN = -1
    SIDEWAYS = 0


@dataclass
class PriceZone:
    """
    Represents a significant price zone on the chart.
    
    A zone is a price range where we expect meaningful price action
    (bounces, rejections, breaks, etc.)
    """
    id: str
    zone_type: ZoneType
    upper: float              # Upper boundary of zone
    lower: float              # Lower boundary of zone
    state: ZoneState = ZoneState.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_touched: Optional[datetime] = None
    touch_count: int = 0
    rejection_count: int = 0
    pierce_count: int = 0
    strength: float = 1.0     # 0-1, decays with touches
    source_module: str = ""   # Which module created this zone
    timeframe: str = "M30"    # Source timeframe for MTF tracking
    start_time: Optional[datetime] = None  # When zone was formed (for chart drawing)
    end_time: Optional[datetime] = None    # Extended to (None = extend to current)
    metadata: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    
    @property
    def midpoint(self) -> float:
        """Zone midpoint price."""
        return (self.upper + self.lower) / 2
    
    @property
    def size(self) -> float:
        """Zone size in price units."""
        return self.upper - self.lower
    
    @property
    def age_minutes(self) -> float:
        """Age of zone in minutes."""
        return (datetime.utcnow() - self.created_at).total_seconds() / 60
    
    @property
    def is_valid(self) -> bool:
        """Whether zone is still valid for trading."""
        return self.state in [ZoneState.PENDING, ZoneState.ACTIVE, ZoneState.TESTED]
    
    @property
    def effective_strength(self) -> float:
        """Strength adjusted for age and touches."""
        base = self.strength
        # Decay for touches (each touch weakens by 15%)
        touch_decay = 0.85 ** self.touch_count
        # Boost for rejections (each rejection strengthens by 10%)
        rejection_boost = 1.10 ** min(self.rejection_count, 3)
        # Age decay (lose 5% per hour after first hour)
        age_hours = self.age_minutes / 60
        age_decay = 1.0 if age_hours < 1 else 0.95 ** (age_hours - 1)
        return min(1.0, base * touch_decay * rejection_boost * age_decay)
    
    def record_event(self, event: ZoneEvent, price: float, details: Dict = None):
        """Record an event on this zone."""
        self.events.append({
            'event': event.value,
            'price': price,
            'timestamp': datetime.utcnow().isoformat(),
            'details': details or {}
        })
        
        if event == ZoneEvent.TOUCHED:
            self.touch_count += 1
            self.last_touched = datetime.utcnow()
        elif event == ZoneEvent.REJECTED:
            self.rejection_count += 1
        elif event == ZoneEvent.PIERCED:
            self.pierce_count += 1


@dataclass
class TrendLine:
    """
    Represents a trend line drawn between swing points.
    """
    id: str
    direction: TrendDirection
    start_price: float
    start_time: datetime
    end_price: float
    end_time: datetime
    slope: float              # Price change per bar
    touches: int = 0
    is_valid: bool = True
    strength: float = 1.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def price_at_time(self, target_time: datetime) -> float:
        """Calculate expected price at a given time."""
        time_delta = (target_time - self.start_time).total_seconds()
        start_delta = (self.end_time - self.start_time).total_seconds()
        if start_delta == 0:
            return self.start_price
        price_delta = self.end_price - self.start_price
        return self.start_price + (price_delta * time_delta / start_delta)
    
    def distance_to_price(self, price: float, current_time: datetime) -> float:
        """Calculate distance from trend line to given price."""
        expected = self.price_at_time(current_time)
        return price - expected


@dataclass
class Channel:
    """
    Represents a price channel defined by parallel trend lines.
    """
    id: str
    upper_line: TrendLine
    lower_line: TrendLine
    direction: TrendDirection
    width: float
    is_valid: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def midline_slope(self) -> float:
        """Average slope of channel."""
        return (self.upper_line.slope + self.lower_line.slope) / 2


@dataclass
class ChartState:
    """
    Complete state of a chart's visual analysis.
    
    This is the master object that represents how Cthulu "sees" the chart.
    """
    symbol: str
    timeframe: str
    zones: Dict[str, PriceZone] = field(default_factory=dict)
    trend_lines: Dict[str, TrendLine] = field(default_factory=dict)
    channels: Dict[str, Channel] = field(default_factory=dict)
    current_trend: TrendDirection = TrendDirection.SIDEWAYS
    trend_strength: float = 0.5
    last_updated: datetime = field(default_factory=datetime.utcnow)
    
    # Quick lookup indices
    active_support_zones: List[str] = field(default_factory=list)
    active_resistance_zones: List[str] = field(default_factory=list)
    
    def get_active_zones(self, zone_type: ZoneType = None) -> List[PriceZone]:
        """Get all active zones, optionally filtered by type."""
        zones = [z for z in self.zones.values() if z.is_valid]
        if zone_type:
            zones = [z for z in zones if z.zone_type == zone_type]
        return sorted(zones, key=lambda z: z.effective_strength, reverse=True)
    
    def get_zones_near_price(self, price: float, tolerance: float) -> List[PriceZone]:
        """Get zones within tolerance of price."""
        zones = []
        for zone in self.zones.values():
            if not zone.is_valid:
                continue
            # Check if price is within zone or within tolerance of zone boundaries
            in_zone = zone.lower <= price <= zone.upper
            near_upper = abs(price - zone.upper) <= tolerance
            near_lower = abs(price - zone.lower) <= tolerance
            if in_zone or near_upper or near_lower:
                zones.append(zone)
        return zones


# ============================================================================
# CHART MANAGER - Core Implementation
# ============================================================================

class ChartManager:
    """
    Non-blocking Chart Manager for dynamic zone/level tracking.
    
    Architecture:
    - Synchronous reads for real-time decision making
    - Asynchronous writes for state updates (non-blocking)
    - Event-driven zone lifecycle management
    - Integration with all cognition modules
    
    Thread Safety:
    - Uses threading.Lock for state access
    - Write operations queued for async processing
    - Read operations are lock-protected but fast
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the Chart Manager.
        
        Args:
            config: Configuration dictionary with:
                - max_zones_per_type: Max zones to track per type
                - zone_expiry_hours: Hours before zone expires
                - min_zone_strength: Minimum strength to keep zone
                - enable_trend_lines: Whether to compute trend lines
                - enable_channels: Whether to compute channels
                - async_writes: Use async write queue
        """
        self.config = config or {}
        self.logger = logging.getLogger("cthulu.chart_manager")
        
        # Configuration
        self.max_zones_per_type = self.config.get('max_zones_per_type', 20)
        self.zone_expiry_hours = self.config.get('zone_expiry_hours', 48)
        self.min_zone_strength = self.config.get('min_zone_strength', 0.2)
        self.enable_trend_lines = self.config.get('enable_trend_lines', True)
        self.enable_channels = self.config.get('enable_channels', True)
        self.async_writes = self.config.get('async_writes', True)
        
        # State storage (per symbol)
        self._chart_states: Dict[str, ChartState] = {}
        self._state_lock = threading.RLock()
        
        # Async write queue
        self._write_queue: queue.Queue = queue.Queue()
        self._write_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        
        # Event callbacks
        self._event_callbacks: Dict[ZoneEvent, List[Callable]] = defaultdict(list)
        
        # Statistics
        self._stats = {
            'zones_created': 0,
            'zones_broken': 0,
            'zones_rejected': 0,
            'writes_queued': 0,
            'writes_processed': 0
        }
        
        # Start async writer if enabled
        if self.async_writes:
            self._start_write_thread()
        
        self.logger.info(f"ChartManager initialized (async_writes={self.async_writes})")
    
    def _start_write_thread(self):
        """Start the async write processing thread."""
        self._write_thread = threading.Thread(
            target=self._write_processor,
            name="ChartManager-Writer",
            daemon=True
        )
        self._write_thread.start()
    
    def _write_processor(self):
        """Background thread for processing write operations."""
        while not self._shutdown_event.is_set():
            try:
                # Get write operation from queue (with timeout to allow shutdown check)
                try:
                    operation = self._write_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                
                # Process the operation
                op_type = operation.get('type')
                op_data = operation.get('data')
                
                with self._state_lock:
                    if op_type == 'create_zone':
                        self._process_create_zone(op_data)
                    elif op_type == 'update_zone':
                        self._process_update_zone(op_data)
                    elif op_type == 'record_event':
                        self._process_record_event(op_data)
                    elif op_type == 'cleanup':
                        self._process_cleanup(op_data)
                
                self._stats['writes_processed'] += 1
                self._write_queue.task_done()
                
            except Exception as e:
                self.logger.error(f"Write processor error: {e}")
    
    def shutdown(self):
        """Shutdown the chart manager gracefully."""
        self._shutdown_event.set()
        if self._write_thread:
            self._write_thread.join(timeout=5.0)
        self.logger.info("ChartManager shutdown complete")
    
    def _auto_export(self, symbol: str, timeframe: str):
        """Auto-export chart state to JSON for MT5 EA consumption (MTF by default)."""
        try:
            exporter = ChartDrawingsExporter()
            # Export multi-timeframe by default for comprehensive chart drawings
            exporter.export_to_file(self, symbol, timeframe, multi_timeframe=True)
        except Exception as e:
            self.logger.warning(f"Auto-export failed: {e}")
    
    # ========================================================================
    # READ OPERATIONS (Synchronous - for real-time decision making)
    # ========================================================================
    
    def get_chart_state(self, symbol: str, timeframe: str = "M30") -> ChartState:
        """
        Get the current chart state for a symbol.
        
        This is a synchronous read operation - fast and thread-safe.
        
        Args:
            symbol: Trading symbol
            timeframe: Chart timeframe
            
        Returns:
            ChartState object with all tracked zones, lines, etc.
        """
        with self._state_lock:
            key = f"{symbol}_{timeframe}"
            if key not in self._chart_states:
                self._chart_states[key] = ChartState(
                    symbol=symbol,
                    timeframe=timeframe
                )
            return self._chart_states[key]
    
    def get_zones_for_entry(
        self,
        symbol: str,
        direction: str,
        current_price: float,
        atr: float,
        timeframe: str = "M30"
    ) -> Dict[str, Any]:
        """
        Get zone analysis for entry decision.
        
        This is the primary read interface for entry_confluence.py.
        
        Args:
            symbol: Trading symbol
            direction: 'long' or 'short'
            current_price: Current market price
            atr: Current ATR for tolerance calculation
            timeframe: Chart timeframe
            
        Returns:
            Dictionary with zone analysis:
            - supporting_zones: Zones that support this entry direction
            - opposing_zones: Zones that oppose this entry direction
            - nearest_support: Nearest support zone
            - nearest_resistance: Nearest resistance zone
            - zone_score: Overall zone confluence score (0-1)
            - warnings: List of warning messages
        """
        state = self.get_chart_state(symbol, timeframe)
        tolerance = atr * 1.5
        
        supporting_zones = []
        opposing_zones = []
        warnings = []
        
        # Find zones near current price
        nearby_zones = state.get_zones_near_price(current_price, tolerance)
        
        for zone in nearby_zones:
            # Determine if zone supports or opposes the trade direction
            is_support_zone = zone.zone_type in [
                ZoneType.ORDER_BLOCK_BULLISH,
                ZoneType.ORB_LOW,
                ZoneType.SUPPORT,
                ZoneType.FVG_BULLISH,
                ZoneType.TREND_SUPPORT,
                ZoneType.CHANNEL_LOWER
            ]
            is_resistance_zone = zone.zone_type in [
                ZoneType.ORDER_BLOCK_BEARISH,
                ZoneType.ORB_HIGH,
                ZoneType.RESISTANCE,
                ZoneType.FVG_BEARISH,
                ZoneType.TREND_RESISTANCE,
                ZoneType.CHANNEL_UPPER
            ]
            
            if direction == 'long':
                if is_support_zone and current_price <= zone.upper + tolerance * 0.5:
                    # Long entry at support = good
                    supporting_zones.append(zone)
                elif is_resistance_zone and current_price >= zone.lower - tolerance * 0.5:
                    # Long entry at resistance = bad
                    opposing_zones.append(zone)
                    warnings.append(f"Long entry near {zone.zone_type.value} resistance")
            
            elif direction == 'short':
                if is_resistance_zone and current_price >= zone.lower - tolerance * 0.5:
                    # Short entry at resistance = good
                    supporting_zones.append(zone)
                elif is_support_zone and current_price <= zone.upper + tolerance * 0.5:
                    # Short entry at support = bad
                    opposing_zones.append(zone)
                    warnings.append(f"Short entry near {zone.zone_type.value} support")
        
        # Calculate zone confluence score
        support_strength = sum(z.effective_strength for z in supporting_zones)
        oppose_strength = sum(z.effective_strength for z in opposing_zones)
        
        if support_strength + oppose_strength > 0:
            zone_score = support_strength / (support_strength + oppose_strength)
        else:
            zone_score = 0.5  # Neutral if no zones
        
        # Boost score if multiple supporting zones
        if len(supporting_zones) >= 2:
            zone_score = min(1.0, zone_score * 1.15)
        
        # Find nearest support/resistance
        all_support = [z for z in state.zones.values() 
                      if z.is_valid and z.zone_type in [
                          ZoneType.ORDER_BLOCK_BULLISH, ZoneType.ORB_LOW, 
                          ZoneType.SUPPORT, ZoneType.CHANNEL_LOWER
                      ]]
        all_resistance = [z for z in state.zones.values() 
                         if z.is_valid and z.zone_type in [
                             ZoneType.ORDER_BLOCK_BEARISH, ZoneType.ORB_HIGH,
                             ZoneType.RESISTANCE, ZoneType.CHANNEL_UPPER
                         ]]
        
        # Filter to zones below/above price
        supports_below = [z for z in all_support if z.upper < current_price]
        resistances_above = [z for z in all_resistance if z.lower > current_price]
        
        nearest_support = max(supports_below, key=lambda z: z.upper) if supports_below else None
        nearest_resistance = min(resistances_above, key=lambda z: z.lower) if resistances_above else None
        
        return {
            'supporting_zones': supporting_zones,
            'opposing_zones': opposing_zones,
            'nearest_support': nearest_support,
            'nearest_resistance': nearest_resistance,
            'zone_score': zone_score,
            'warnings': warnings,
            'total_zones': len(state.zones),
            'active_zones': len([z for z in state.zones.values() if z.is_valid])
        }
    
    def get_key_levels(
        self,
        symbol: str,
        current_price: float,
        num_levels: int = 5,
        timeframe: str = "M30"
    ) -> Dict[str, List[float]]:
        """
        Get key support and resistance levels.
        
        Args:
            symbol: Trading symbol
            current_price: Current market price
            num_levels: Number of levels to return each direction
            timeframe: Chart timeframe
            
        Returns:
            Dictionary with 'support' and 'resistance' level lists
        """
        state = self.get_chart_state(symbol, timeframe)
        
        supports = []
        resistances = []
        
        for zone in state.zones.values():
            if not zone.is_valid:
                continue
            
            # Categorize by type and position relative to price
            if zone.midpoint < current_price:
                supports.append((zone.upper, zone.effective_strength, zone))
            else:
                resistances.append((zone.lower, zone.effective_strength, zone))
        
        # Sort by proximity and strength
        supports.sort(key=lambda x: (-x[0], -x[1]))  # Highest (closest) first
        resistances.sort(key=lambda x: (x[0], -x[1]))  # Lowest (closest) first
        
        return {
            'support': [s[0] for s in supports[:num_levels]],
            'resistance': [r[0] for r in resistances[:num_levels]],
            'support_zones': [s[2] for s in supports[:num_levels]],
            'resistance_zones': [r[2] for r in resistances[:num_levels]]
        }
    
    def get_risk_reward_context(
        self,
        symbol: str,
        entry_price: float,
        direction: str,
        timeframe: str = "M30"
    ) -> Dict[str, Any]:
        """
        Get R:R context based on zone structure.
        
        Identifies logical stop loss and take profit levels based
        on the current zone structure.
        
        Args:
            symbol: Trading symbol
            entry_price: Proposed entry price
            direction: 'long' or 'short'
            timeframe: Chart timeframe
            
        Returns:
            Dictionary with suggested SL/TP levels and R:R ratio
        """
        levels = self.get_key_levels(symbol, entry_price, num_levels=3, timeframe=timeframe)
        
        if direction == 'long':
            # SL below nearest support
            if levels['support']:
                suggested_sl = levels['support'][0] * 0.998  # Slightly below
            else:
                suggested_sl = None
            
            # TP at nearest resistance
            if levels['resistance']:
                suggested_tp = levels['resistance'][0] * 0.998  # Slightly before
            else:
                suggested_tp = None
        
        else:  # short
            # SL above nearest resistance
            if levels['resistance']:
                suggested_sl = levels['resistance'][0] * 1.002  # Slightly above
            else:
                suggested_sl = None
            
            # TP at nearest support
            if levels['support']:
                suggested_tp = levels['support'][0] * 1.002  # Slightly before
            else:
                suggested_tp = None
        
        # Calculate R:R
        if suggested_sl and suggested_tp:
            risk = abs(entry_price - suggested_sl)
            reward = abs(suggested_tp - entry_price)
            rr_ratio = reward / risk if risk > 0 else 0
        else:
            rr_ratio = None
        
        return {
            'suggested_sl': suggested_sl,
            'suggested_tp': suggested_tp,
            'rr_ratio': rr_ratio,
            'support_levels': levels['support'],
            'resistance_levels': levels['resistance']
        }
    
    # ========================================================================
    # WRITE OPERATIONS (Async - non-blocking)
    # ========================================================================
    
    def create_zone(
        self,
        symbol: str,
        zone_type: ZoneType,
        upper: float,
        lower: float,
        source_module: str = "",
        metadata: Dict[str, Any] = None,
        timeframe: str = "M30"
    ) -> str:
        """
        Create a new price zone.
        
        This is an async write operation - returns immediately.
        
        Args:
            symbol: Trading symbol
            zone_type: Type of zone
            upper: Upper boundary
            lower: Lower boundary
            source_module: Which module created this zone
            metadata: Additional zone metadata
            timeframe: Chart timeframe
            
        Returns:
            Zone ID
        """
        zone_id = str(uuid.uuid4())[:8]
        
        operation = {
            'type': 'create_zone',
            'data': {
                'zone_id': zone_id,
                'symbol': symbol,
                'timeframe': timeframe,
                'zone_type': zone_type,
                'upper': upper,
                'lower': lower,
                'source_module': source_module,
                'metadata': metadata or {}
            }
        }
        
        if self.async_writes:
            self._write_queue.put(operation)
            self._stats['writes_queued'] += 1
        else:
            with self._state_lock:
                self._process_create_zone(operation['data'])
        
        return zone_id
    
    def _process_create_zone(self, data: Dict[str, Any]):
        """Process zone creation (called by write thread)."""
        key = f"{data['symbol']}_{data['timeframe']}"
        
        if key not in self._chart_states:
            self._chart_states[key] = ChartState(
                symbol=data['symbol'],
                timeframe=data['timeframe']
            )
        
        state = self._chart_states[key]
        
        zone = PriceZone(
            id=data['zone_id'],
            zone_type=data['zone_type'],
            upper=data['upper'],
            lower=data['lower'],
            source_module=data['source_module'],
            metadata=data['metadata']
        )
        
        state.zones[zone.id] = zone
        self._stats['zones_created'] += 1
        
        # Update quick lookup indices
        if zone.zone_type in [ZoneType.ORDER_BLOCK_BULLISH, ZoneType.SUPPORT, 
                              ZoneType.ORB_LOW, ZoneType.CHANNEL_LOWER]:
            state.active_support_zones.append(zone.id)
        elif zone.zone_type in [ZoneType.ORDER_BLOCK_BEARISH, ZoneType.RESISTANCE,
                                ZoneType.ORB_HIGH, ZoneType.CHANNEL_UPPER]:
            state.active_resistance_zones.append(zone.id)
        
        # Prune excess zones
        self._prune_zones_by_type(state, data['zone_type'])
        
        # Auto-export to JSON for MT5
        self._auto_export(data['symbol'], data['timeframe'])
        
        self.logger.debug(f"Zone created: {zone.zone_type.value} @ {zone.lower:.2f}-{zone.upper:.2f}")
    
    def update_zone_state(
        self,
        symbol: str,
        zone_id: str,
        new_state: ZoneState,
        timeframe: str = "M30"
    ):
        """Update the state of an existing zone."""
        operation = {
            'type': 'update_zone',
            'data': {
                'symbol': symbol,
                'timeframe': timeframe,
                'zone_id': zone_id,
                'new_state': new_state
            }
        }
        
        if self.async_writes:
            self._write_queue.put(operation)
        else:
            with self._state_lock:
                self._process_update_zone(operation['data'])
    
    def _process_update_zone(self, data: Dict[str, Any]):
        """Process zone state update."""
        key = f"{data['symbol']}_{data['timeframe']}"
        state = self._chart_states.get(key)
        if not state:
            return
        
        zone = state.zones.get(data['zone_id'])
        if not zone:
            return
        
        zone.state = data['new_state']
        
        if data['new_state'] == ZoneState.BROKEN:
            self._stats['zones_broken'] += 1
    
    def record_zone_event(
        self,
        symbol: str,
        zone_id: str,
        event: ZoneEvent,
        price: float,
        details: Dict[str, Any] = None,
        timeframe: str = "M30"
    ):
        """Record an event on a zone."""
        operation = {
            'type': 'record_event',
            'data': {
                'symbol': symbol,
                'timeframe': timeframe,
                'zone_id': zone_id,
                'event': event,
                'price': price,
                'details': details or {}
            }
        }
        
        if self.async_writes:
            self._write_queue.put(operation)
        else:
            with self._state_lock:
                self._process_record_event(operation['data'])
    
    def _process_record_event(self, data: Dict[str, Any]):
        """Process zone event recording."""
        key = f"{data['symbol']}_{data['timeframe']}"
        state = self._chart_states.get(key)
        if not state:
            return
        
        zone = state.zones.get(data['zone_id'])
        if not zone:
            return
        
        zone.record_event(data['event'], data['price'], data['details'])
        
        # Update zone state based on event
        if data['event'] == ZoneEvent.REJECTED:
            self._stats['zones_rejected'] += 1
            if zone.state == ZoneState.PENDING:
                zone.state = ZoneState.ACTIVE
            elif zone.state == ZoneState.ACTIVE:
                zone.state = ZoneState.TESTED
        
        elif data['event'] == ZoneEvent.BROKEN:
            zone.state = ZoneState.BROKEN
        
        elif data['event'] == ZoneEvent.MITIGATED:
            zone.state = ZoneState.MITIGATED
        
        # Auto-export on significant state changes
        if data['event'] in [ZoneEvent.BROKEN, ZoneEvent.MITIGATED, ZoneEvent.REJECTED]:
            self._auto_export(data['symbol'], data['timeframe'])
        
        # Trigger callbacks
        for callback in self._event_callbacks.get(data['event'], []):
            try:
                callback(zone, data)
            except Exception as e:
                self.logger.error(f"Event callback error: {e}")
    
    def _prune_zones_by_type(self, state: ChartState, zone_type: ZoneType):
        """Remove excess zones of a given type."""
        zones_of_type = [z for z in state.zones.values() if z.zone_type == zone_type]
        
        if len(zones_of_type) > self.max_zones_per_type:
            # Sort by strength (weakest first)
            zones_of_type.sort(key=lambda z: z.effective_strength)
            
            # Remove weakest until we're under the limit
            for zone in zones_of_type[:len(zones_of_type) - self.max_zones_per_type]:
                del state.zones[zone.id]
                
                # Update indices
                if zone.id in state.active_support_zones:
                    state.active_support_zones.remove(zone.id)
                if zone.id in state.active_resistance_zones:
                    state.active_resistance_zones.remove(zone.id)
    
    def cleanup_expired_zones(self, symbol: str = None, timeframe: str = "M30"):
        """Remove expired and weak zones."""
        operation = {
            'type': 'cleanup',
            'data': {
                'symbol': symbol,
                'timeframe': timeframe
            }
        }
        
        if self.async_writes:
            self._write_queue.put(operation)
        else:
            with self._state_lock:
                self._process_cleanup(operation['data'])
    
    def _process_cleanup(self, data: Dict[str, Any]):
        """Process zone cleanup."""
        keys_to_clean = []
        
        if data['symbol']:
            keys_to_clean.append(f"{data['symbol']}_{data['timeframe']}")
        else:
            keys_to_clean = list(self._chart_states.keys())
        
        expiry_threshold = datetime.utcnow() - timedelta(hours=self.zone_expiry_hours)
        
        for key in keys_to_clean:
            state = self._chart_states.get(key)
            if not state:
                continue
            
            zones_to_remove = []
            for zone_id, zone in state.zones.items():
                # Remove if expired
                if zone.created_at < expiry_threshold:
                    zones_to_remove.append(zone_id)
                    continue
                
                # Remove if too weak
                if zone.effective_strength < self.min_zone_strength:
                    zones_to_remove.append(zone_id)
                    continue
                
                # Remove if broken/mitigated/expired
                if zone.state in [ZoneState.BROKEN, ZoneState.MITIGATED, ZoneState.EXPIRED]:
                    zones_to_remove.append(zone_id)
            
            for zone_id in zones_to_remove:
                del state.zones[zone_id]
                if zone_id in state.active_support_zones:
                    state.active_support_zones.remove(zone_id)
                if zone_id in state.active_resistance_zones:
                    state.active_resistance_zones.remove(zone_id)
    
    # ========================================================================
    # INTEGRATION - Sync with Cognition Modules
    # ========================================================================
    
    def sync_from_order_blocks(
        self,
        order_blocks: List[Any],  # List of OrderBlock objects
        symbol: str,
        timeframe: str = "M30"
    ):
        """
        Sync zones from Order Block detector.
        
        Called by entry_confluence or trading_loop to keep zones in sync.
        """
        for ob in order_blocks:
            # Check if we already have this OB
            existing = self._find_matching_zone(
                symbol, timeframe, ob.low, ob.high, 
                [ZoneType.ORDER_BLOCK_BULLISH, ZoneType.ORDER_BLOCK_BEARISH]
            )
            
            if existing:
                continue  # Already tracked
            
            # Determine zone type
            zone_type = (ZoneType.ORDER_BLOCK_BULLISH 
                        if str(ob.block_type).lower() == 'bullish' or 'bullish' in str(ob.block_type).lower()
                        else ZoneType.ORDER_BLOCK_BEARISH)
            
            # Create zone
            self.create_zone(
                symbol=symbol,
                zone_type=zone_type,
                upper=ob.high,
                lower=ob.low,
                source_module="order_blocks",
                metadata={
                    'structure_break': str(getattr(ob, 'structure_break', 'unknown')),
                    'touches': getattr(ob, 'touches', 0),
                    'timestamp': str(getattr(ob, 'timestamp', datetime.utcnow()))
                },
                timeframe=timeframe
            )
    
    def sync_from_session_orb(
        self,
        active_ranges: Dict[str, Any],  # Dict of session -> OpeningRange
        symbol: str,
        timeframe: str = "M30"
    ):
        """
        Sync zones from Session ORB detector.
        """
        for session_name, range_obj in active_ranges.items():
            if not range_obj.is_complete:
                continue  # Only sync completed ranges
            
            # Check for existing ORB zones
            existing_high = self._find_matching_zone(
                symbol, timeframe, range_obj.high * 0.999, range_obj.high * 1.001,
                [ZoneType.ORB_HIGH]
            )
            existing_low = self._find_matching_zone(
                symbol, timeframe, range_obj.low * 0.999, range_obj.low * 1.001,
                [ZoneType.ORB_LOW]
            )
            
            if not existing_high:
                # Create ORB high zone (thin zone around the level)
                zone_size = (range_obj.high - range_obj.low) * 0.05
                self.create_zone(
                    symbol=symbol,
                    zone_type=ZoneType.ORB_HIGH,
                    upper=range_obj.high + zone_size,
                    lower=range_obj.high,
                    source_module="session_orb",
                    metadata={
                        'session': session_name,
                        'range_size': range_obj.high - range_obj.low,
                        'breakout_direction': getattr(range_obj, 'breakout_direction', None)
                    },
                    timeframe=timeframe
                )
            
            if not existing_low:
                zone_size = (range_obj.high - range_obj.low) * 0.05
                self.create_zone(
                    symbol=symbol,
                    zone_type=ZoneType.ORB_LOW,
                    upper=range_obj.low,
                    lower=range_obj.low - zone_size,
                    source_module="session_orb",
                    metadata={
                        'session': session_name,
                        'range_size': range_obj.high - range_obj.low,
                        'breakout_direction': getattr(range_obj, 'breakout_direction', None)
                    },
                    timeframe=timeframe
                )
    
    def sync_from_structure_detector(
        self,
        swing_highs: List[float],
        swing_lows: List[float],
        symbol: str,
        timeframe: str = "M30"
    ):
        """
        Sync support/resistance zones from structure detector swing points.
        """
        # Convert swing highs to resistance zones
        for price in swing_highs[-5:]:  # Only recent swings
            existing = self._find_matching_zone(
                symbol, timeframe, price * 0.998, price * 1.002,
                [ZoneType.RESISTANCE]
            )
            if not existing:
                self.create_zone(
                    symbol=symbol,
                    zone_type=ZoneType.RESISTANCE,
                    upper=price * 1.001,
                    lower=price * 0.999,
                    source_module="structure_detector",
                    timeframe=timeframe
                )
        
        # Convert swing lows to support zones
        for price in swing_lows[-5:]:
            existing = self._find_matching_zone(
                symbol, timeframe, price * 0.998, price * 1.002,
                [ZoneType.SUPPORT]
            )
            if not existing:
                self.create_zone(
                    symbol=symbol,
                    zone_type=ZoneType.SUPPORT,
                    upper=price * 1.001,
                    lower=price * 0.999,
                    source_module="structure_detector",
                    timeframe=timeframe
                )
    
    def _find_matching_zone(
        self,
        symbol: str,
        timeframe: str,
        lower: float,
        upper: float,
        zone_types: List[ZoneType]
    ) -> Optional[PriceZone]:
        """Find an existing zone that matches the given parameters."""
        with self._state_lock:
            key = f"{symbol}_{timeframe}"
            state = self._chart_states.get(key)
            if not state:
                return None
            
            for zone in state.zones.values():
                if zone.zone_type not in zone_types:
                    continue
                
                # Check for overlap
                if zone.lower <= upper and zone.upper >= lower:
                    return zone
            
            return None
    
    # ========================================================================
    # PRICE ACTION ANALYSIS
    # ========================================================================
    
    def process_price_update(
        self,
        symbol: str,
        current_price: float,
        current_bar: pd.Series,
        timeframe: str = "M30"
    ):
        """
        Process a price update and check for zone interactions.
        
        This should be called on each new bar to:
        1. Detect zone touches/tests
        2. Detect zone breaks
        3. Update zone states
        
        Args:
            symbol: Trading symbol
            current_price: Current close price
            current_bar: Current bar data (OHLC)
            timeframe: Chart timeframe
        """
        state = self.get_chart_state(symbol, timeframe)
        
        bar_high = current_bar.get('high', current_price)
        bar_low = current_bar.get('low', current_price)
        
        for zone_id, zone in list(state.zones.items()):
            if not zone.is_valid:
                continue
            
            # Check if bar interacted with zone
            touched_upper = bar_high >= zone.upper and bar_low < zone.upper
            touched_lower = bar_low <= zone.lower and bar_high > zone.lower
            in_zone = bar_low <= zone.upper and bar_high >= zone.lower
            
            if not in_zone:
                continue  # No interaction
            
            # Determine interaction type
            if zone.zone_type in [ZoneType.ORDER_BLOCK_BULLISH, ZoneType.SUPPORT,
                                  ZoneType.ORB_LOW, ZoneType.CHANNEL_LOWER]:
                # Support zones - break is close below, rejection is bounce up
                if current_price < zone.lower:
                    self.record_zone_event(symbol, zone_id, ZoneEvent.BROKEN, current_price, timeframe=timeframe)
                elif bar_low <= zone.upper and current_price > zone.midpoint:
                    self.record_zone_event(symbol, zone_id, ZoneEvent.REJECTED, current_price, timeframe=timeframe)
                else:
                    self.record_zone_event(symbol, zone_id, ZoneEvent.TOUCHED, current_price, timeframe=timeframe)
            
            elif zone.zone_type in [ZoneType.ORDER_BLOCK_BEARISH, ZoneType.RESISTANCE,
                                    ZoneType.ORB_HIGH, ZoneType.CHANNEL_UPPER]:
                # Resistance zones - break is close above, rejection is bounce down
                if current_price > zone.upper:
                    self.record_zone_event(symbol, zone_id, ZoneEvent.BROKEN, current_price, timeframe=timeframe)
                elif bar_high >= zone.lower and current_price < zone.midpoint:
                    self.record_zone_event(symbol, zone_id, ZoneEvent.REJECTED, current_price, timeframe=timeframe)
                else:
                    self.record_zone_event(symbol, zone_id, ZoneEvent.TOUCHED, current_price, timeframe=timeframe)
    
    # ========================================================================
    # EVENT SYSTEM
    # ========================================================================
    
    def on_event(self, event: ZoneEvent, callback: Callable):
        """Register a callback for zone events."""
        self._event_callbacks[event].append(callback)
    
    def off_event(self, event: ZoneEvent, callback: Callable):
        """Unregister a callback."""
        if callback in self._event_callbacks.get(event, []):
            self._event_callbacks[event].remove(callback)
    
    # ========================================================================
    # STATISTICS & REPORTING
    # ========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get chart manager statistics."""
        with self._state_lock:
            total_zones = sum(len(s.zones) for s in self._chart_states.values())
            active_zones = sum(
                len([z for z in s.zones.values() if z.is_valid])
                for s in self._chart_states.values()
            )
        
        return {
            **self._stats,
            'total_zones': total_zones,
            'active_zones': active_zones,
            'symbols_tracked': len(self._chart_states),
            'write_queue_size': self._write_queue.qsize()
        }
    
    def get_summary(self, symbol: str, timeframe: str = "M30") -> Dict[str, Any]:
        """Get a summary of chart state for a symbol."""
        state = self.get_chart_state(symbol, timeframe)
        
        zone_counts = defaultdict(int)
        for zone in state.zones.values():
            zone_counts[zone.zone_type.value] += 1
        
        return {
            'symbol': symbol,
            'timeframe': timeframe,
            'total_zones': len(state.zones),
            'active_zones': len([z for z in state.zones.values() if z.is_valid]),
            'zone_counts': dict(zone_counts),
            'current_trend': state.current_trend.name,
            'trend_strength': state.trend_strength,
            'last_updated': state.last_updated.isoformat()
        }


# ============================================================================
# MODULE-LEVEL SINGLETON
# ============================================================================

_chart_manager: Optional[ChartManager] = None


def get_chart_manager(config: Dict[str, Any] = None, **kwargs) -> ChartManager:
    """
    Get or create the chart manager singleton.
    
    Args:
        config: Configuration dictionary to pass to ChartManager
        **kwargs: Additional keyword arguments for ChartManager
        
    Returns:
        ChartManager singleton instance
    """
    global _chart_manager
    if _chart_manager is None:
        # Merge config dict with kwargs
        merged_config = config or {}
        merged_config.update(kwargs)
        _chart_manager = ChartManager(merged_config)
    return _chart_manager


def shutdown_chart_manager():
    """Shutdown the chart manager."""
    global _chart_manager
    if _chart_manager:
        _chart_manager.shutdown()
        _chart_manager = None


# ============================================================================
# JSON EXPORT - For MT5 EA and External Charting
# ============================================================================

class ChartDrawingsExporter:
    """
    Exports chart drawings to JSON format for:
    1. MT5 Expert Advisor (reads file to draw on chart)
    2. Angular UI via WebSocket (TradingView widget)
    
    MULTI-TIMEFRAME SUPPORT:
    - Aggregates zones from M30, H1, H4, D1 into single output
    - Higher timeframe zones get higher priority/visibility
    - Zones are tagged with source timeframe for filtering
    
    JSON Schema v2:
    {
        "symbol": "BTCUSD#",
        "timestamp": "2026-01-11T16:00:00Z",
        "version": 2,
        "timeframes": ["M30", "H1", "H4", "D1"],
        "zones": [...],
        "trend_lines": [...],
        "channels": [...],
        "levels": [...],
        "annotations": [...]
    }
    """
    
    # Timeframe priority (higher = more important)
    TIMEFRAME_PRIORITY = {
        "M1": 1, "M5": 2, "M15": 3, "M30": 4,
        "H1": 5, "H4": 6, "D1": 7, "W1": 8, "MN1": 9
    }
    
    def __init__(self, output_dir: str = None):
        """
        Initialize the exporter.
        
        Args:
            output_dir: Directory for JSON output files.
                       Default: C:\\workspace\\cthulu\\data\\drawings
        """
        self.output_dir = output_dir or r"C:\workspace\cthulu\data\drawings"
        self.logger = logging.getLogger("cthulu.chart_exporter")
        
        # Ensure output directory exists
        import os
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Version for schema compatibility
        self.schema_version = 2
    
    def export_multi_timeframe(
        self,
        chart_manager: ChartManager,
        symbol: str,
        timeframes: List[str] = None,
        include_expired: bool = False
    ) -> Dict[str, Any]:
        """
        Export chart state from multiple timeframes into a single JSON.
        
        This is the primary export method - aggregates all relevant zones
        from multiple timeframes for comprehensive chart drawing.
        
        Args:
            chart_manager: ChartManager instance
            symbol: Trading symbol
            timeframes: List of timeframes to export (default: M30, H1, H4, D1)
            include_expired: Include broken/expired zones
            
        Returns:
            JSON-serializable dictionary with all zones
        """
        if timeframes is None:
            timeframes = ["M30", "H1", "H4", "D1"]
        
        all_zones = []
        all_trendlines = []
        all_channels = []
        all_levels = []
        
        for tf in timeframes:
            state = chart_manager.get_chart_state(symbol, tf)
            tf_priority = self.TIMEFRAME_PRIORITY.get(tf, 4)
            
            # Convert zones with timeframe tagging
            for zone in state.zones.values():
                if not include_expired and not zone.is_valid:
                    continue
                
                # Boost strength for higher timeframes
                adjusted_strength = zone.effective_strength * (1 + (tf_priority - 4) * 0.1)
                adjusted_strength = min(1.0, adjusted_strength)
                
                all_zones.append({
                    "id": f"{tf}_{zone.id}",
                    "type": zone.zone_type.value,
                    "upper": zone.upper,
                    "lower": zone.lower,
                    "midpoint": zone.midpoint,
                    "state": zone.state.name,
                    "strength": round(adjusted_strength, 3),
                    "touches": zone.touch_count,
                    "rejections": zone.rejection_count,
                    "created_at": zone.created_at.isoformat(),
                    "start_time": (zone.start_time or zone.created_at).isoformat(),
                    "end_time": zone.end_time.isoformat() if zone.end_time else None,
                    "last_touched": zone.last_touched.isoformat() if zone.last_touched else None,
                    "source": zone.source_module,
                    "timeframe": tf,
                    "priority": tf_priority,
                    "color": self._get_zone_color(zone, tf),
                    "style": self._get_zone_style(zone, tf)
                })
            
            # Trend lines with timeframe
            for tl in state.trend_lines.values():
                if not tl.is_valid:
                    continue
                
                all_trendlines.append({
                    "id": f"{tf}_{tl.id}",
                    "direction": tl.direction.name,
                    "start_price": tl.start_price,
                    "start_time": tl.start_time.isoformat(),
                    "end_price": tl.end_price,
                    "end_time": tl.end_time.isoformat(),
                    "slope": tl.slope,
                    "touches": tl.touches,
                    "strength": round(tl.strength, 3),
                    "timeframe": tf,
                    "color": "#FFD700" if tl.direction == TrendDirection.UP else "#FF6B6B",
                    "style": "dashed" if tl.touches < 2 else "solid",
                    "width": 1 + (tf_priority - 4)  # Thicker lines for higher TF
                })
            
            # Channels with timeframe
            for ch in state.channels.values():
                if not ch.is_valid:
                    continue
                
                all_channels.append({
                    "id": f"{tf}_{ch.id}",
                    "direction": ch.direction.name,
                    "upper_line": {
                        "start_price": ch.upper_line.start_price,
                        "end_price": ch.upper_line.end_price,
                        "start_time": ch.upper_line.start_time.isoformat(),
                        "end_time": ch.upper_line.end_time.isoformat()
                    },
                    "lower_line": {
                        "start_price": ch.lower_line.start_price,
                        "end_price": ch.lower_line.end_price,
                        "start_time": ch.lower_line.start_time.isoformat(),
                        "end_time": ch.lower_line.end_time.isoformat()
                    },
                    "width": ch.width,
                    "timeframe": tf,
                    "fill_color": f"rgba(100, 149, 237, {0.05 + tf_priority * 0.02})",
                    "border_color": "#6495ED"
                })
        
        # Sort zones by priority (higher timeframe first) then by strength
        all_zones.sort(key=lambda z: (-z['priority'], -z['strength']))
        
        # Deduplicate overlapping zones (keep higher TF)
        all_zones = self._deduplicate_zones(all_zones)
        
        # Get key levels (use M30 as base, but merge from all TFs)
        all_levels = self._aggregate_key_levels(chart_manager, symbol, timeframes)
        
        # Build final JSON structure
        export_data = {
            "symbol": symbol,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "version": self.schema_version,
            "timeframes": timeframes,
            "zones": all_zones,
            "trend_lines": all_trendlines,
            "channels": all_channels,
            "levels": all_levels,
            "stats": {
                "total_zones": len(all_zones),
                "by_timeframe": {tf: len([z for z in all_zones if z['timeframe'] == tf]) for tf in timeframes},
                "by_type": self._count_by_type(all_zones)
            }
        }
        
        return export_data
    
    def _deduplicate_zones(self, zones: List[Dict]) -> List[Dict]:
        """Remove duplicate zones that overlap significantly."""
        if not zones:
            return zones
        
        unique_zones = []
        for zone in zones:
            is_duplicate = False
            for existing in unique_zones:
                # Check for overlap (>50% overlap = duplicate)
                overlap_upper = min(zone['upper'], existing['upper'])
                overlap_lower = max(zone['lower'], existing['lower'])
                if overlap_upper > overlap_lower:
                    overlap_size = overlap_upper - overlap_lower
                    zone_size = zone['upper'] - zone['lower']
                    if zone_size > 0 and overlap_size / zone_size > 0.5:
                        is_duplicate = True
                        break
            
            if not is_duplicate:
                unique_zones.append(zone)
        
        return unique_zones
    
    def _aggregate_key_levels(
        self,
        chart_manager: ChartManager,
        symbol: str,
        timeframes: List[str]
    ) -> List[Dict]:
        """Aggregate key levels from all timeframes."""
        levels_dict = {}  # price -> level info
        
        for tf in timeframes:
            tf_priority = self.TIMEFRAME_PRIORITY.get(tf, 4)
            levels = chart_manager.get_key_levels(symbol, 0, num_levels=5, timeframe=tf)
            
            for price in levels.get('support', []):
                # Round to avoid floating point duplicates
                key = round(price, 2)
                if key not in levels_dict or levels_dict[key]['priority'] < tf_priority:
                    levels_dict[key] = {
                        "price": price,
                        "type": "support",
                        "color": "#00FF9D",
                        "style": "dotted" if tf_priority < 5 else "dashed",
                        "label": f"S{tf[0]} {price:.0f}",
                        "timeframe": tf,
                        "priority": tf_priority,
                        "width": 1 + max(0, tf_priority - 4)
                    }
            
            for price in levels.get('resistance', []):
                key = round(price, 2)
                if key not in levels_dict or levels_dict[key]['priority'] < tf_priority:
                    levels_dict[key] = {
                        "price": price,
                        "type": "resistance",
                        "color": "#FF3E3E",
                        "style": "dotted" if tf_priority < 5 else "dashed",
                        "label": f"R{tf[0]} {price:.0f}",
                        "timeframe": tf,
                        "priority": tf_priority,
                        "width": 1 + max(0, tf_priority - 4)
                    }
        
        # Sort by priority then price
        return sorted(levels_dict.values(), key=lambda x: (-x['priority'], x['price']))
    
    def _count_by_type(self, zones: List[Dict]) -> Dict[str, int]:
        """Count zones by type."""
        counts = {}
        for zone in zones:
            t = zone['type']
            counts[t] = counts.get(t, 0) + 1
        return counts
    
    def export_to_json(
        self,
        chart_manager: ChartManager,
        symbol: str,
        timeframe: str = "M30",
        include_expired: bool = False
    ) -> Dict[str, Any]:
        """
        Export chart state to JSON format (single timeframe).
        
        For backward compatibility - prefer export_multi_timeframe().
        """
        # Use multi-timeframe export with single TF for consistency
        return self.export_multi_timeframe(
            chart_manager, symbol, [timeframe], include_expired
        )
    
    def export_to_file(
        self,
        chart_manager: ChartManager,
        symbol: str,
        timeframe: str = "M30",
        multi_timeframe: bool = True
    ) -> str:
        """
        Export chart state to JSON file.
        
        Args:
            chart_manager: ChartManager instance
            symbol: Trading symbol
            timeframe: Primary timeframe (or base for MTF export)
            multi_timeframe: Export all timeframes (M30, H1, H4, D1)
            
        Returns:
            Path to exported file
        """
        if multi_timeframe:
            export_data = self.export_multi_timeframe(chart_manager, symbol)
        else:
            export_data = self.export_to_json(chart_manager, symbol, timeframe)
        
        # Create filename - use symbol only for MTF (contains all TFs)
        safe_symbol = symbol.replace("#", "").replace("/", "_")
        if multi_timeframe:
            filename = f"{safe_symbol}_MTF_drawings.json"
        else:
            filename = f"{safe_symbol}_{timeframe}_drawings.json"
        filepath = os.path.join(self.output_dir, filename)
        
        # Write JSON file to Cthulu data folder
        with open(filepath, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        # Also copy to MT5 common folder for EA access
        self._copy_to_mt5_common(filename, export_data)
        
        self.logger.debug(f"Exported drawings to {filepath}")
        return filepath
        
        # Also copy to MT5 common folder for EA access
        self._copy_to_mt5_common(filename, export_data)
        
        self.logger.debug(f"Exported drawings to {filepath}")
        return filepath
    
    def _copy_to_mt5_common(self, filename: str, data: Dict[str, Any]):
        """
        Copy JSON file to MT5 common folder for EA access.
        
        MT5 can only read files from:
        - MQL5/Files folder (terminal specific)
        - Common/Files folder (shared across terminals)
        """
        try:
            # MT5 common files folder (shared across all terminals)
            appdata = os.environ.get('APPDATA', '')
            mt5_common = os.path.join(appdata, 'MetaQuotes', 'Terminal', 'Common', 'Files')
            
            if os.path.exists(mt5_common):
                common_filepath = os.path.join(mt5_common, filename)
                with open(common_filepath, 'w') as f:
                    json.dump(data, f, indent=2)
                self.logger.debug(f"Copied to MT5 common: {common_filepath}")
        except Exception as e:
            self.logger.warning(f"Failed to copy to MT5 common folder: {e}")
    
    def _get_zone_color(self, zone: PriceZone, timeframe: str = "M30") -> str:
        """Get display color for zone type, adjusted by timeframe."""
        color_map = {
            ZoneType.ORDER_BLOCK_BULLISH: "#00FF9D",   # Green
            ZoneType.ORDER_BLOCK_BEARISH: "#FF3E3E",   # Red
            ZoneType.ORB_HIGH: "#FFD700",              # Gold
            ZoneType.ORB_LOW: "#FFD700",               # Gold
            ZoneType.SUPPORT: "#00CED1",              # Dark Cyan
            ZoneType.RESISTANCE: "#FF6B6B",           # Light Red
            ZoneType.FVG_BULLISH: "#32CD32",          # Lime Green
            ZoneType.FVG_BEARISH: "#DC143C",          # Crimson
            ZoneType.TREND_SUPPORT: "#4169E1",        # Royal Blue
            ZoneType.TREND_RESISTANCE: "#8B0000",     # Dark Red
            ZoneType.CHANNEL_UPPER: "#6495ED",        # Cornflower Blue
            ZoneType.CHANNEL_LOWER: "#6495ED",        # Cornflower Blue
            ZoneType.FIBONACCI: "#DDA0DD",            # Plum
            ZoneType.VWAP: "#9370DB",                 # Medium Purple
            ZoneType.POC: "#FF8C00"                   # Dark Orange
        }
        return color_map.get(zone.zone_type, "#808080")
    
    def _get_zone_style(self, zone: PriceZone, timeframe: str = "M30") -> Dict[str, Any]:
        """Get display style for zone, adjusted by timeframe."""
        tf_priority = self.TIMEFRAME_PRIORITY.get(timeframe, 4)
        
        # Opacity based on strength + timeframe boost
        base_opacity = 0.1 + (zone.effective_strength * 0.25)
        tf_opacity_boost = (tf_priority - 4) * 0.05  # Higher TF = more visible
        opacity = min(0.5, base_opacity + tf_opacity_boost)
        
        # Border style based on state
        border_style = "solid"
        if zone.state == ZoneState.TESTED:
            border_style = "dashed"
        elif zone.state == ZoneState.WEAKENED:
            border_style = "dotted"
        
        # Border width based on timeframe
        border_width = 1 + max(0, tf_priority - 4)
        if zone.effective_strength >= 0.7:
            border_width += 1
        
        return {
            "fill_opacity": round(opacity, 2),
            "border_style": border_style,
            "border_width": border_width
        }


# Export function for external use
def export_chart_drawings(
    symbol: str,
    timeframe: str = "M30",
    to_file: bool = True,
    multi_timeframe: bool = True
) -> Dict[str, Any]:
    """
    Export chart drawings for a symbol.
    
    Convenience function that uses the global chart manager.
    
    Args:
        symbol: Trading symbol
        timeframe: Chart timeframe (base for MTF)
        to_file: Also write to JSON file
        multi_timeframe: Export all timeframes (M30, H1, H4, D1)
        
    Returns:
        JSON-serializable dictionary of drawings
    """
    cm = get_chart_manager()
    exporter = ChartDrawingsExporter()
    
    if multi_timeframe:
        data = exporter.export_multi_timeframe(cm, symbol)
    else:
        data = exporter.export_to_json(cm, symbol, timeframe)
    
    if to_file:
        exporter.export_to_file(cm, symbol, timeframe, multi_timeframe)
    
    return data
